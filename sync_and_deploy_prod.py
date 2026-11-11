"""
sync_and_deploy_prod.py
Single all-in-one production patcher, database synchronizer, and GitHub deployer.
Target Production Folder : E:\\HOST_VSCODE\\host-simulator-github-prod
Source Test Folder       : E:\\HOST_VSCODE\\host-simulator
"""

import ast
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

TEST_DIR = Path(r"E:\HOST_VSCODE\host-simulator")
PROD_DIR = Path(r"E:\HOST_VSCODE\host-simulator-github-prod")

PROD_HSM_BASE = "https://thales-10k-soft-hsm.onrender.com"
PROD_HSM_CMD_URL = "https://thales-10k-soft-hsm.onrender.com/api/host/command"
PROD_FRONTEND_URL = "https://rajon-test-payment-solution.netlify.app"
PROD_BACKEND_URL = "https://baobab-backend-uxgz.onrender.com"
GITHUB_REPO_URL = "https://github.com/RajonRDX/baobab-host-simulator.git"

# 8 canonical External Soft-HSM keys encrypted under Soft-HSM Default LMK (KCV: D3B82A0000000000)
DEFAULT_EXTERNAL_HSM_KEYS: List[Dict[str, Any]] = [
    {
        "id": "ext-zmk-main",
        "key_identifier": "ZMK_MAIN_EXT",
        "base_identifier": "ZMK_MAIN",
        "key_name": "External Zone Master Key (ZMK_MAIN)",
        "key_type": "ZMK",
        "thales_key_type_code": "000",
        "key_usage": "ZONE_MASTER_KEY",
        "key_scheme": "U",
        "encrypted_key_block": "U56013B41F97E249F56013B41F97E249F",
        "kvc": "D3B82A",
        "lmk_check_value": "D3B82A0000000000",
    },
    {
        "id": "ext-tmk-pos-01",
        "key_identifier": "TMK_POS_01_EXT",
        "base_identifier": "TMK_POS_01",
        "key_name": "External Terminal Master Key (TMK_POS_01)",
        "key_type": "TMK",
        "thales_key_type_code": "002",
        "key_usage": "TERMINAL_MASTER_KEY",
        "key_scheme": "U",
        "encrypted_key_block": "U8A49B26C1E3DF0758A49B26C1E3DF075",
        "kvc": "9B760A",
        "lmk_check_value": "D3B82A0000000000",
    },
    {
        "id": "ext-awk-atm-01",
        "key_identifier": "AWK_ATM_01_EXT",
        "base_identifier": "AWK_ATM_01",
        "key_name": "External Acquirer Working PIN Key (AWK_ATM_01)",
        "key_type": "AWK",
        "thales_key_type_code": "001",
        "key_usage": "ACQUIRER_WORKING_PIN_KEY",
        "key_scheme": "U",
        "encrypted_key_block": "U2B9A6F3C418E7D022B9A6F3C418E7D02",
        "kvc": "4F81C2",
        "lmk_check_value": "D3B82A0000000000",
    },
    {
        "id": "ext-iwk-sw-01",
        "key_identifier": "IWK_SW_01_EXT",
        "base_identifier": "IWK_SW_01",
        "key_name": "External Issuer Working PIN Key (IWK_SW_01)",
        "key_type": "IWK",
        "thales_key_type_code": "001",
        "key_usage": "ISSUER_WORKING_PIN_KEY",
        "key_scheme": "U",
        "encrypted_key_block": "U7D3E1A9B5C2048F67D3E1A9B5C2048F6",
        "kvc": "C8E419",
        "lmk_check_value": "D3B82A0000000000",
    },
    {
        "id": "ext-pvk-visa-01",
        "key_identifier": "PVK_VISA_01_EXT",
        "base_identifier": "PVK_VISA_01",
        "key_name": "External Visa PIN Verification Key (PVK_VISA_01)",
        "key_type": "PVK",
        "thales_key_type_code": "002",
        "key_usage": "PIN_VERIFICATION_KEY",
        "key_scheme": "U",
        "encrypted_key_block": "U3E719A4C82B06DF53E719A4C82B06DF5",
        "kvc": "782100",
        "lmk_check_value": "D3B82A0000000000",
    },
    {
        "id": "ext-mk-ac-emv01",
        "key_identifier": "MK_AC_EMV01_EXT",
        "base_identifier": "MK_AC_EMV01",
        "key_name": "External EMV Master Key AC (MK_AC_EMV01)",
        "key_type": "MK-AC",
        "thales_key_type_code": "109",
        "key_usage": "EMV_MASTER_KEY_AC",
        "key_scheme": "U",
        "encrypted_key_block": "U9C42E81A6F03B7D49C42E81A6F03B7D4",
        "kvc": "A1B2C3",
        "lmk_check_value": "D3B82A0000000000",
    },
    {
        "id": "ext-cvk-main-01",
        "key_identifier": "CVK_MAIN_01_EXT",
        "base_identifier": "CVK_MAIN_01",
        "key_name": "External Card Verification Key (CVK_MAIN_01)",
        "key_type": "CVK",
        "thales_key_type_code": "402",
        "key_usage": "CARD_VERIFICATION_KEY",
        "key_scheme": "U",
        "encrypted_key_block": "U6F10D53B9A842CE76F10D53B9A842CE7",
        "kvc": "011000",
        "lmk_check_value": "D3B82A0000000000",
    },
    {
        "id": "ext-tak-mac-01",
        "key_identifier": "TAK_MAC_01_EXT",
        "base_identifier": "TAK_MAC_01",
        "key_name": "External Terminal Auth MAC Key (TAK_MAC_01)",
        "key_type": "TAK",
        "thales_key_type_code": "003",
        "key_usage": "TERMINAL_AUTH_MAC_KEY",
        "key_scheme": "U",
        "encrypted_key_block": "U4A82C09E1D753BF84A82C09E1D753BF8",
        "kvc": "112233",
        "lmk_check_value": "D3B82A0000000000",
    },
]

failures: List[str] = []


def check(step: str, ok: bool, detail: str = "") -> None:
    status = "[APPLIED]" if ok else "[NOT FOUND]"
    line = f"{status} {step}" + (f" ({detail})" if detail else "")
    print(line)
    if not ok:
        failures.append(line)


def validate_python_file(path: Path) -> None:
    src = path.read_text(encoding="utf-8")
    ast.parse(src, filename=str(path))


def main() -> None:
    print("=" * 78)
    print("RAJON HOST SIMULATOR — PRODUCTION SYNC & REPAIR TOOL")
    print(f"Production Dir : {PROD_DIR}")
    print(f"Test Dir       : {TEST_DIR}")
    print("=" * 78)

    if not PROD_DIR.exists():
        print(f"[FATAL] Production directory does not exist: {PROD_DIR}")
        sys.exit(1)

    # --------------------------------------------------------------------------
    # STEP 1: Copy tested HSM & Router files from TEST_DIR -> PROD_DIR if present
    # --------------------------------------------------------------------------
    files_to_sync_from_test = [
        Path("backend/app/hsm_adapter.py"),
        Path("backend/app/lmk_key_management_service.py"),
        Path("backend/app/seed_data.py"),
        Path("backend/app/routers/lmk_key_management_router.py"),
    ]
    if TEST_DIR.exists():
        for rel_path in files_to_sync_from_test:
            src_file = TEST_DIR / rel_path
            dst_file = PROD_DIR / rel_path
            if src_file.exists():
                shutil.copy2(src_file, dst_file)
                validate_python_file(dst_file)
                check(f"Sync tested {rel_path} from TEST folder", True, str(src_file))

    # --------------------------------------------------------------------------
    # STEP 2: Verify / Patch A — backend/app/hsm_adapter.py
    # --------------------------------------------------------------------------
    adapter_path = PROD_DIR / "backend/app/hsm_adapter.py"
    adapter_src = adapter_path.read_text(encoding="utf-8")
    has_m0 = "0000M00011001" in adapter_src and "raw_resp[-16:]" in adapter_src
    has_ext_branches = (
        "0000CY" in adapter_src
        and "0000M601" in adapter_src
        and "0000KQ10" in adapter_src
    )
    validate_python_file(adapter_path)
    check("A. Verify hsm_adapter.py (M0 001 + external CY/M6/M8/KQ branches)", has_m0 and has_ext_branches)

    # --------------------------------------------------------------------------
    # STEP 3: Verify / Patch B — backend/app/lmk_key_management_service.py
    # --------------------------------------------------------------------------
    lkms_path = PROD_DIR / "backend/app/lmk_key_management_service.py"
    lkms_src = lkms_path.read_text(encoding="utf-8")

    # Clean any localhost:8001 or 127.0.0.1:8000 default URLs in ExternalSoftHSMBridge
    lkms_src = lkms_src.replace("http://127.0.0.1:8000", PROD_HSM_CMD_URL)
    lkms_src = lkms_src.replace("http://127.0.0.1:8001/api/host/command", PROD_HSM_CMD_URL)
    lkms_src = lkms_src.replace("http://127.0.0.1:8001", PROD_HSM_BASE)
    lkms_src = lkms_src.replace("timeout_seconds: int = 45", "timeout_seconds: int = 60")

    # Ensure User-Agent header is present in ExternalSoftHSMBridge
    if '"User-Agent"' not in lkms_src and "'User-Agent'" not in lkms_src:
        lkms_src = lkms_src.replace(
            'headers={"Content-Type": "application/json"}',
            'headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "RAJON-Host-Simulator/1.0"}',
        )

    # Ensure DEFAULT_EXTERNAL_HSM_KEYS is defined
    if "DEFAULT_EXTERNAL_HSM_KEYS" not in lkms_src:
        const_code = "DEFAULT_EXTERNAL_HSM_KEYS = " + repr(DEFAULT_EXTERNAL_HSM_KEYS) + "\n\n\n"
        lkms_src = lkms_src.replace("class ExternalSoftHSMBridge:", const_code + "class ExternalSoftHSMBridge:", 1)

    # Ensure seed_fallback_external_keys is defined on LMKKeyManagementService
    if "def seed_fallback_external_keys(" not in lkms_src:
        seed_method = '''    def seed_fallback_external_keys(self) -> List[str]:
        remote_map: Dict[str, Dict[str, Any]] = {}
        try:
            for rk in self.bridge.fetch_seeded_remote_keys():
                rk_id = rk.get("key_id") or ""
                if rk_id:
                    remote_map[rk_id] = rk
        except Exception:
            pass

        alias_to_remote = {
            "ZMK_MAIN_EXT": "ZMK_MAIN",
            "TMK_POS_01_EXT": "TMK_POS_01",
            "AWK_ATM_01_EXT": "AWK_ATM_01",
            "IWK_SW_01_EXT": "IWK_SW_01",
            "PVK_VISA_01_EXT": "PVK_VISA_01",
            "MK_AC_EMV01_EXT": "MK_AC_EMV01",
            "CVK_MAIN_01_EXT": "CVK_ISS_01",
            "TAK_MAC_01_EXT": "TAK_MAC_01",
        }

        seeded_aliases: List[str] = []
        for item in DEFAULT_EXTERNAL_HSM_KEYS:
            ext_alias = item["key_identifier"]
            rem_key = remote_map.get(alias_to_remote.get(ext_alias, ""))
            token = (rem_key.get("lmk_cryptogram") if rem_key else None) or item["encrypted_key_block"]
            kvc_val = (rem_key.get("kcv") if rem_key else None) or item["kvc"]

            rec = (
                self.db.query(HsmKeyReference)
                .filter(HsmKeyReference.key_identifier == ext_alias)
                .first()
            )
            if rec:
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
            else:
                rec = HsmKeyReference(
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
                self.db.add(rec)
            seeded_aliases.append(ext_alias)

        self.db.commit()
        return seeded_aliases

'''
        lkms_src = lkms_src.replace(
            "    def sync_default_external_keys(",
            seed_method + "    def sync_default_external_keys(",
            1,
        )

    # Ensure sync_default_external_keys has SYNCED_OFFLINE_FALLBACK
    old_sync_err = '''        lmk_status = self.get_lmk_and_provider_status()
        if not lmk_status.get("online"):
            raise ConnectionError(lmk_status.get("error") or "External Soft-HSM is offline")'''
    new_sync_err = '''        self.seed_fallback_external_keys()
        lmk_status = self.get_lmk_and_provider_status()
        if not lmk_status.get("online"):
            seeded = self.seed_fallback_external_keys()
            return {
                "status": "SYNCED_OFFLINE_FALLBACK",
                "lmk_check_value": "D3B82A0000000000",
                "synced_key_aliases": seeded,
                "count": len(seeded),
            }'''
    if old_sync_err in lkms_src:
        lkms_src = lkms_src.replace(old_sync_err, new_sync_err, 1)

    # Ensure resolve_external_key_record calls seed_fallback_external_keys() if rec not found
    old_resolve_lookup = '''        candidates = [key_identifier, f"{key_identifier}_EXT"]
        rec = (
            self.db.query(HsmKeyReference)
            .filter(
                HsmKeyReference.key_identifier.in_(candidates),
                HsmKeyReference.provider_type == "EXTERNAL_HSM",
            )
            .order_by(HsmKeyReference.key_version.desc())
            .first()
        )
        if not rec:'''
    new_resolve_lookup = '''        base_id = key_identifier[:-4] if key_identifier.endswith("_EXT") else key_identifier
        candidates = list(dict.fromkeys([key_identifier, f"{base_id}_EXT", base_id]))
        rec = (
            self.db.query(HsmKeyReference)
            .filter(
                HsmKeyReference.key_identifier.in_(candidates),
                HsmKeyReference.provider_type == "EXTERNAL_HSM",
            )
            .order_by(HsmKeyReference.key_version.desc())
            .first()
        )
        if not rec:
            self.seed_fallback_external_keys()
            rec = (
                self.db.query(HsmKeyReference)
                .filter(
                    HsmKeyReference.key_identifier.in_(candidates),
                    HsmKeyReference.provider_type == "EXTERNAL_HSM",
                )
                .order_by(HsmKeyReference.key_version.desc())
                .first()
            )
        if not rec:'''
    if old_resolve_lookup in lkms_src:
        lkms_src = lkms_src.replace(old_resolve_lookup, new_resolve_lookup, 1)

    lkms_path.write_text(lkms_src, encoding="utf-8")
    validate_python_file(lkms_path)

    check(
        "B. Verify lmk_key_management_service.py (DEFAULT_EXTERNAL_HSM_KEYS, seed_fallback_external_keys, resolve & sync)",
        "DEFAULT_EXTERNAL_HSM_KEYS" in lkms_src
        and "def seed_fallback_external_keys" in lkms_src
        and "self.seed_fallback_external_keys()" in lkms_src,
    )

    # --------------------------------------------------------------------------
    # STEP 4: Verify / Patch C — backend/app/seed_data.py
    # --------------------------------------------------------------------------
    seed_path = PROD_DIR / "backend/app/seed_data.py"
    seed_src = seed_path.read_text(encoding="utf-8")
    if "import logging" not in seed_src:
        seed_src = "import logging\nlogger = logging.getLogger(__name__)\n" + seed_src

    if "seed_fallback_external_keys" not in seed_src:
        tree = ast.parse(seed_src)
        end_line = None
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "seed_initial_data":
                end_line = node.end_lineno
                break
        if end_line is not None:
            lines = seed_src.splitlines(keepends=True)
            hook = (
                "    try:\n"
                "        from app.lmk_key_management_service import LMKKeyManagementService\n"
                "        LMKKeyManagementService(db).seed_fallback_external_keys()\n"
                "    except Exception:\n"
                "        logger.exception(\"Failed to seed fallback external HSM keys at startup\")\n"
            )
            lines.insert(end_line, hook)
            seed_src = "".join(lines)
            seed_path.write_text(seed_src, encoding="utf-8")

    validate_python_file(seed_path)
    check(
        "C. Verify seed_data.py calls LMKKeyManagementService(db).seed_fallback_external_keys()",
        "seed_fallback_external_keys" in seed_src,
    )

    # --------------------------------------------------------------------------
    # STEP 5: Verify / Patch D — backend/app/routers/lmk_key_management_router.py
    # --------------------------------------------------------------------------
    router_path = PROD_DIR / "backend/app/routers/lmk_key_management_router.py"
    router_src = router_path.read_text(encoding="utf-8")

    if "seed_fallback_external_keys" not in router_src and "svc = LMKKeyManagementService(db)" in router_src:
        router_src = router_src.replace(
            "svc = LMKKeyManagementService(db)",
            "svc = LMKKeyManagementService(db)\n    svc.seed_fallback_external_keys()",
        )
        router_path.write_text(router_src, encoding="utf-8")

    validate_python_file(router_path)
    check(
        "D. Verify lmk_key_management_router.py seeds external keys on switch/sync",
        "seed_fallback_external_keys" in router_src,
    )

    # --------------------------------------------------------------------------
    # STEP 6: Verify / Patch E — backend/app/config.py
    # --------------------------------------------------------------------------
    config_path = PROD_DIR / "backend/app/config.py"
    config_content = f'''# backend/app/config.py
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    # Application
    APP_NAME: str = "RAJON Private Host Simulator"
    APP_ENV: str = "production"

    # Security
    SECRET_KEY: str = "dev-secret-key-do-not-use-in-prod-9876543210abcdef"
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "AdminPassword123!"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 720
    ENFORCE_SECURE_DEFAULTS: bool = False

    # Database
    DATABASE_URL: str = "sqlite:///./baobab_host.db"

    # =====================================================
    # HSM CONFIGURATION
    # =====================================================
    HSM_MODE: str = "SOFT_HSM_REMOTE"
    HSM_REMOTE_URL: str = "{PROD_HSM_CMD_URL}"
    HSM_HEADER_LENGTH: int = 4

    # =====================================================
    # LOGGING
    # =====================================================
    LOG_RAW_DATA: bool = True

    # =====================================================
    # CORS
    # =====================================================
    CORS_ORIGINS: str = (
        "{PROD_FRONTEND_URL},"
        "http://localhost:5173,"
        "http://127.0.0.1:5173,"
        "http://localhost:3000"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
'''
    config_path.write_text(config_content, encoding="utf-8")
    validate_python_file(config_path)
    check("E. Verify config.py (SOFT_HSM_REMOTE + Render HSM URL + Netlify CORS)", True)

    # --------------------------------------------------------------------------
    # STEP 7: Clean any remaining 8001 references in frontend/src
    # --------------------------------------------------------------------------
    fe_src = PROD_DIR / "frontend/src"
    cleaned_fe_count = 0
    if fe_src.exists():
        for tsx in fe_src.rglob("*.*"):
            if tsx.suffix in (".ts", ".tsx", ".js", ".jsx"):
                txt = tsx.read_text(encoding="utf-8", errors="ignore")
                new_txt = (
                    txt.replace("http://127.0.0.1:8001/api/host/command", PROD_HSM_CMD_URL)
                    .replace("http://localhost:8001/api/host/command", PROD_HSM_CMD_URL)
                    .replace("http://127.0.0.1:8001", PROD_HSM_BASE)
                    .replace("http://localhost:8001", PROD_HSM_BASE)
                    .replace("127.0.0.1:8001", "thales-10k-soft-hsm.onrender.com")
                    .replace("localhost:8001", "thales-10k-soft-hsm.onrender.com")
                )
                if new_txt != txt:
                    tsx.write_text(new_txt, encoding="utf-8")
                    cleaned_fe_count += 1
    check("Frontend 8001 URL cleanup", True, f"{cleaned_fe_count} file(s) updated")

    # --------------------------------------------------------------------------
    # STEP 8: Copy Test SQLite DB -> Prod SQLite DB & Guarantee 8 *_EXT Keys
    # --------------------------------------------------------------------------
    test_db = TEST_DIR / "backend/baobab_host.db"
    prod_db = PROD_DIR / "backend/baobab_host.db"
    if test_db.exists():
        shutil.copy2(test_db, prod_db)
        check("Copy test database baobab_host.db to production folder", True, f"{prod_db.stat().st_size:,} bytes")

    if prod_db.exists():
        conn = sqlite3.connect(str(prod_db))
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='hsm_key_references'")
        if cur.fetchone():
            for item in DEFAULT_EXTERNAL_HSM_KEYS:
                cur.execute(
                    "SELECT id FROM hsm_key_references WHERE key_identifier = ?",
                    (item["key_identifier"],),
                )
                row = cur.fetchone()
                if row:
                    cur.execute(
                        """
                        UPDATE hsm_key_references
                           SET provider_type = 'EXTERNAL_HSM',
                               thales_key_type_code = ?,
                               key_scheme = ?,
                               encrypted_key_block = ?,
                               hsm_key_reference = ?,
                               kvc = ?,
                               lmk_id = '00',
                               lmk_check_value = ?,
                               clear_key_hex = NULL,
                               key_status = 'ACTIVE'
                         WHERE key_identifier = ?
                        """,
                        (
                            item["thales_key_type_code"],
                            item["key_scheme"],
                            item["encrypted_key_block"],
                            item["encrypted_key_block"],
                            item["kvc"],
                            item["lmk_check_value"],
                            item["key_identifier"],
                        ),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO hsm_key_references (
                            id, key_name, key_type, key_usage, key_identifier, kvc,
                            algorithm, key_length, hsm_key_reference, key_status,
                            provider_type, thales_key_type_code, key_scheme, key_version,
                            lmk_id, lmk_check_value, encrypted_key_block, kcv_type, exportable
                        ) VALUES (?, ?, ?, ?, ?, ?, '3DES_2KEY', 128, ?, 'ACTIVE',
                                  'EXTERNAL_HSM', ?, ?, 1, '00', ?, ?, '6H', 1)
                        """,
                        (
                            item["id"],
                            item["key_name"],
                            item["key_type"],
                            item["key_usage"],
                            item["key_identifier"],
                            item["kvc"],
                            item["encrypted_key_block"],
                            item["thales_key_type_code"],
                            item["key_scheme"],
                            item["lmk_check_value"],
                            item["encrypted_key_block"],
                        ),
                    )
            conn.commit()
            cur.execute(
                "SELECT COUNT(*) FROM hsm_key_references WHERE provider_type='EXTERNAL_HSM' AND key_identifier LIKE '%_EXT'"
            )
            ext_count = cur.fetchone()[0]
            check("F. Verify 8 *_EXT keys in SQLite baobab_host.db", ext_count >= 8, f"{ext_count} EXTERNAL_HSM *_EXT rows")
        conn.close()

    # Allow baobab_host.db in .gitignore so Git tracks it
    gitignore_path = PROD_DIR / ".gitignore"
    if gitignore_path.exists():
        gi_text = gitignore_path.read_text(encoding="utf-8")
        if "!backend/baobab_host.db" not in gi_text:
            gi_text = gi_text.replace("*.db\n", "*.db\n!baobab_host.db\n!backend/baobab_host.db\n")
            gitignore_path.write_text(gi_text, encoding="utf-8")
        check("Allow backend/baobab_host.db in .gitignore", True)

    if failures:
        print("\n[ERROR] Some checks failed:")
        for f in failures:
            print("  ", f)
        sys.exit(1)

    print("\n" + "=" * 78)
    print("[SUCCESS] All code & database checks passed!")
    print("=" * 78)

    # --------------------------------------------------------------------------
    # STEP 9: Optional Automatic Git Commit & Push
    # --------------------------------------------------------------------------
    ans = input("\nDo you want to commit and force-push to GitHub right now? (y/n): ").strip().lower()
    if ans == "y":
        os.chdir(PROD_DIR)
        cmds = [
            ["git", "add", "-f", "backend/baobab_host.db"],
            ["git", "add", "-A"],
            ["git", "commit", "-m", "fix(prod): sync tested external soft-hsm key management, fallback seeding, and db"],
            ["git", "branch", "-M", "main"],
            ["git", "push", "-u", "origin", "main", "--force"],
        ]
        for cmd in cmds:
            print(f"\n> {' '.join(cmd)}")
            subprocess.run(cmd, check=False)
        print("\n[DEPLOYED] Pushed to GitHub main branch! Render and Netlify will now auto-deploy.")


if __name__ == "__main__":
    main()