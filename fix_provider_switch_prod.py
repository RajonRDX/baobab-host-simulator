"""
fix_provider_switch_prod.py
Fixes the INTERNAL <-> EXTERNAL HSM switch in the production Host Simulator.

Run:
    cd E:\\HOST_VSCODE\\host-simulator-github-prod
    python fix_provider_switch_prod.py
    (optional: python fix_provider_switch_prod.py "D:\\other\\folder")

What it changes (3 files, backups are made first):
 1. lmk_key_management_service.py
      seed_fallback_external_keys() is now LOCAL ONLY and NON-DESTRUCTIVE.
      Before: every call (switch, /status, /keys) called the remote HSM, and when the
      Render HSM was asleep it OVERWROTE the real LMK tokens with placeholder tokens.
 2. routers/lmk_key_management_router.py
      Provider switch is now fast: sets the mode, seeds locally, does ONE short probe
      (8s) of the remote HSM and always answers. No more 100s+ cold-start chains.
      /provider and the universal routes now share the same function.
 3. main.py
      _execute_safe_provider_switch was used but never imported (NameError / 500).

Every edit prints [APPLIED], [ALREADY DONE] or [NOT FOUND]. Files are syntax-checked
and restored from backup if anything is wrong.
"""
import re
import sys
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(r"E:\HOST_VSCODE\host-simulator-github-prod")
if len(sys.argv) == 1 and not (ROOT / "backend" / "app").exists():
    ROOT = Path(__file__).resolve().parent  # script placed inside the project folder
APP = ROOT / "backend" / "app"
BACKUP = ROOT / "_backups" / f"provider_switch_fix_{datetime.now():%Y%m%d_%H%M%S}"

failed = False


def load(path):
    raw = path.read_bytes().decode("utf-8")
    crlf = "\r\n" in raw
    return raw.replace("\r\n", "\n"), crlf


def save(path, text, crlf):
    if crlf:
        text = text.replace("\n", "\r\n")
    path.write_bytes(text.encode("utf-8"))


def backup(path):
    BACKUP.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, BACKUP / path.name)


def finish(path, text, crlf, label):
    """Syntax-check, then write. Restore the backup if the result does not compile."""
    global failed
    try:
        compile(text, str(path), "exec")
    except SyntaxError as exc:
        print(f"[FAILED] {label}: result has a syntax error ({exc}); file NOT changed")
        failed = True
        return
    save(path, text, crlf)
    print(f"[APPLIED] {label}")


# ---------------------------------------------------------------- 1. SERVICE
NEW_SEED = '''    # [PATCH provider_switch_fast]
    # LMK cryptograms copied from the live Soft-HSM (your own logs). All other keys are
    # filled with the real tokens by "Sync Keys" (GET /api/keys), never by guesses.
    _KNOWN_GOOD_TOKENS = {
        "AWK_ATM_01_EXT": ("UC8E2A847DA7EC2F0C8E2A847DA7EC2F0", None),
        "PVK_VISA_01_EXT": ("U56D33BE3768CF6DD56D33BE3768CF6DD", "141C6A"),
    }

    def seed_fallback_external_keys(self) -> List[str]:
        """
        LOCAL ONLY (no HTTP call) and NON-DESTRUCTIVE:
          * creates a missing EXTERNAL_HSM row,
          * never overwrites a token that was synced from the real Soft-HSM,
          * only replaces an old placeholder token for AWK/PVK with the verified one.
        """
        placeholder = {i["key_identifier"]: i["encrypted_key_block"] for i in DEFAULT_EXTERNAL_HSM_KEYS}
        seeded_aliases: List[str] = []
        for item in DEFAULT_EXTERNAL_HSM_KEYS:
            ext_alias = item["key_identifier"]
            good_token, good_kvc = self._KNOWN_GOOD_TOKENS.get(ext_alias, (None, None))
            token = good_token or item["encrypted_key_block"]
            kvc_val = good_kvc or item["kvc"]

            rec = (
                self.db.query(HsmKeyReference)
                .filter(HsmKeyReference.key_identifier == ext_alias)
                .first()
            )
            if rec is None:
                self.db.add(
                    HsmKeyReference(
                        key_name=item["key_name"],
                        key_type=item["key_type"],
                        key_usage=item["key_usage"],
                        key_identifier=ext_alias,
                        kvc=kvc_val,
                        algorithm="3DES_2KEY",
                        key_length=128,
                        hsm_key_reference=token,
                        encrypted_key_block=token,
                        clear_key_hex=None,
                        provider_type="EXTERNAL_HSM",
                        thales_key_type_code=item["thales_key_type_code"],
                        key_scheme=item["key_scheme"],
                        key_version=1,
                        lmk_id="00",
                        lmk_check_value=item["lmk_check_value"],
                        key_status="ACTIVE",
                    )
                )
            elif rec.provider_type != "EXTERNAL_HSM":
                rec.provider_type = "EXTERNAL_HSM"
                rec.encrypted_key_block = token
                rec.hsm_key_reference = token
                rec.kvc = kvc_val
                rec.thales_key_type_code = item["thales_key_type_code"]
                rec.key_scheme = item["key_scheme"]
                rec.lmk_id = "00"
                rec.lmk_check_value = item["lmk_check_value"]
                rec.clear_key_hex = None
                rec.key_status = "ACTIVE"
            elif good_token and rec.encrypted_key_block == placeholder.get(ext_alias):
                rec.encrypted_key_block = good_token
                rec.hsm_key_reference = good_token
                rec.kvc = kvc_val
            seeded_aliases.append(ext_alias)

        self.db.commit()
        return seeded_aliases

'''


def patch_service():
    global failed
    path = APP / "lmk_key_management_service.py"
    if not path.exists():
        print(f"[NOT FOUND] {path}")
        failed = True
        return
    text, crlf = load(path)
    if "[PATCH provider_switch_fast]" in text:
        print("[ALREADY DONE] lmk_key_management_service.py")
        return
    start = text.find("    def seed_fallback_external_keys(")
    end = text.find("    def sync_default_external_keys(", start)
    if start < 0 or end < 0:
        print("[NOT FOUND] seed_fallback_external_keys / sync_default_external_keys in service")
        failed = True
        return
    backup(path)
    text = text[:start] + NEW_SEED + text[end:]
    finish(path, text, crlf, "service: seed_fallback_external_keys is local-only and non-destructive")


# ---------------------------------------------------------------- 2. ROUTER
NEW_PROVIDER_ROUTE = '''@router.post("/provider")
def switch_hsm_provider(
    payload: HsmProviderSwitchRequest,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    return _execute_safe_provider_switch(
        {"provider_mode": payload.provider_mode, "remote_url": payload.remote_url}, db
    )
'''

NEW_SAFE_SWITCH = '''# [PATCH provider_switch_fast]
def _execute_safe_provider_switch(payload: Dict[str, Any], db: Session) -> Dict[str, Any]:
    """
    Fast, always-answering provider switch used by /provider and the universal routes.
    No long remote chains: local seed + one short probe of the Soft-HSM (which also wakes Render).
    """
    import json as _json
    import logging as _logging
    import urllib.request as _urlreq

    log = _logging.getLogger("rajon.host")
    raw_target = (
        payload.get("provider_mode")
        or payload.get("provider_type")
        or payload.get("provider")
        or payload.get("hsm_mode")
        or payload.get("mode")
        or payload.get("target_provider")
        or ""
    )
    target = str(raw_target).upper().strip()
    if any(k in target for k in ("EXT", "REMOTE", "THALES", "CLOUD")):
        settings.HSM_MODE = "SOFT_HSM_REMOTE"
        active_provider = "EXTERNAL_HSM"
    elif any(k in target for k in ("INT", "LOCAL")):
        settings.HSM_MODE = "SOFT_HSM_LOCAL"
        active_provider = "INTERNAL_HSM"
    else:
        raise HTTPException(status_code=400, detail="provider_mode must be 'INTERNAL_HSM' or 'EXTERNAL_HSM'")

    remote_url = payload.get("remote_url")
    if remote_url:
        settings.HSM_REMOTE_URL = str(remote_url).strip()

    svc = LMKKeyManagementService(db)
    try:
        svc.seed_fallback_external_keys()  # local only, never overwrites real tokens
    except Exception:
        db.rollback()
        log.exception("seed_fallback_external_keys failed during provider switch")

    counts = {"internal_keys": 0, "external_keys": 0}
    try:
        counts["internal_keys"] = db.query(HsmKeyReference).filter(HsmKeyReference.provider_type == "INTERNAL_HSM").count()
        counts["external_keys"] = db.query(HsmKeyReference).filter(HsmKeyReference.provider_type == "EXTERNAL_HSM").count()
    except Exception:
        db.rollback()

    if active_provider == "INTERNAL_HSM":
        status_info = svc.get_lmk_and_provider_status()  # no network in internal mode
    else:
        online, remote, warning = False, {}, None
        try:
            req = _urlreq.Request(
                svc.bridge.status_url,
                headers={"Accept": "application/json", "User-Agent": "RAJON-Host-Simulator/1.0"},
                method="GET",
            )
            with _urlreq.urlopen(req, timeout=8) as resp:
                remote = _json.loads(resp.read().decode("utf-8"))
                online = True
        except Exception as exc:
            warning = f"External Soft-HSM did not answer in 8s (Render may be waking up): {exc}"
            log.warning(warning)
        lmk_cv = remote.get("lmk_check_value") or ("D3B82A0000000000" if online else "UNREACHABLE")
        status_info = {
            "active_provider": "EXTERNAL_HSM",
            "hsm_mode": settings.HSM_MODE,
            "online": online,
            "hsm_state": remote.get("hsm_state", "AUTHORIZED_ONLINE" if online else "OFFLINE_UNREACHABLE"),
            "lmk_id": "00",
            "lmk_check_value": lmk_cv,
            "lmk_kcv_short": lmk_cv[:6],
            "firmware": remote.get("firmware", "N/A"),
            "remote_url": svc.bridge.execute_url,
            "key_counts": counts,
        }
        if warning:
            status_info["warning"] = warning

    status_info["active_provider"] = active_provider
    status_info["hsm_mode"] = settings.HSM_MODE
    return {
        "status": "OK",
        "switched": True,
        "provider_type": active_provider,
        **status_info,
    }
'''


def patch_router():
    global failed
    path = APP / "routers" / "lmk_key_management_router.py"
    if not path.exists():
        print(f"[NOT FOUND] {path}")
        failed = True
        return
    text, crlf = load(path)
    if "[PATCH provider_switch_fast]" in text:
        print("[ALREADY DONE] lmk_key_management_router.py")
        return
    original = text

    # (a) /provider route -> delegate to the shared fast function
    pattern = re.compile(
        r'@router\.post\("/provider"\)\ndef switch_hsm_provider\(.*?\n    return svc\.get_lmk_and_provider_status\(\)\n',
        re.DOTALL,
    )
    if not pattern.search(text):
        print('[NOT FOUND] @router.post("/provider") switch_hsm_provider block')
        failed = True
        return
    text = pattern.sub(lambda m: NEW_PROVIDER_ROUTE, text, count=1)

    # (b) replace _execute_safe_provider_switch (or append it if it does not exist)
    start = text.find("def _execute_safe_provider_switch(")
    if start >= 0:
        nxt = re.search(r"\n(?=@router\.|def |class )", text[start + 10:])
        end = start + 10 + nxt.start() + 1 if nxt else len(text)
        text = text[:start] + NEW_SAFE_SWITCH + "\n\n" + text[end:]
    else:
        text = text.rstrip("\n") + "\n\n\n" + NEW_SAFE_SWITCH

    backup(path)
    finish(path, text, crlf, "router: fast provider switch (/provider + universal routes)")


# ---------------------------------------------------------------- 3. MAIN
def patch_main():
    global failed
    path = APP / "main.py"
    if not path.exists():
        print(f"[NOT FOUND] {path}")
        failed = True
        return
    text, crlf = load(path)
    imp = "from app.routers.lmk_key_management_router import _execute_safe_provider_switch"
    if imp in text:
        print("[ALREADY DONE] main.py import")
        return
    if "_execute_safe_provider_switch" not in text:
        print("[SKIP] main.py does not use _execute_safe_provider_switch")
        return
    anchor = "from app.lmk_key_management_service import LMKKeyManagementService"
    if anchor not in text:
        print("[NOT FOUND] import anchor in main.py")
        failed = True
        return
    backup(path)
    text = text.replace(anchor, anchor + "\n" + imp, 1)
    finish(path, text, crlf, "main.py: import _execute_safe_provider_switch")


def main():
    print("=" * 70)
    print(f" Fixing provider switch in: {ROOT}")
    print("=" * 70)
    patch_service()
    patch_router()
    patch_main()
    print("=" * 70)
    if failed:
        print(" Finished WITH PROBLEMS - read the [NOT FOUND]/[FAILED] lines above.")
        sys.exit(1)
    print(" Done. Next: git add . && git commit -m \"Fast provider switch\" && git push")
    print(" Then wait for Render to redeploy and test the Key Ceremony switch.")
    print("=" * 70)


if __name__ == "__main__":
    main()
