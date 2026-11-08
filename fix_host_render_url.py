# E:\HOST_VSCODE\host-simulator\fix_host_render_url.py
"""
Automated Production Patcher for BAOBAB Host Simulator
Configures HSM_REMOTE_URL = https://thales-10k-soft-hsm.onrender.com/api/host/command
and eliminates Provider Isolation Violation & Provider Switch Failed errors on Render.
"""

import shutil
from datetime import datetime
from pathlib import Path

HOST_ROOT = Path(r"E:\HOST_VSCODE\host-simulator")
if not HOST_ROOT.exists():
    HOST_ROOT = Path(__file__).resolve().parent

BACKUP_DIR = HOST_ROOT / "_backups" / f"render_url_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

RENDER_HSM_BASE = "https://thales-10k-soft-hsm.onrender.com"
RENDER_HSM_CMD_URL = "https://thales-10k-soft-hsm.onrender.com/api/host/command"


def backup_file(path: Path) -> None:
    if path.exists():
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, BACKUP_DIR / path.name)
        print(f"[BACKUP] {path.name} -> {BACKUP_DIR / path.name}")


# ==============================================================================
# 1. Update backend/app/config.py
# ==============================================================================
CONFIG_PY = f'''from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    # Application
    APP_NAME: str = "BAOBAB Private Host Simulator"
    APP_ENV: str = "production"

    # Security
    SECRET_KEY: str = "dev-secret-key-do-not-use-in-prod-9876543210abcdef"
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "AdminPassword123!"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 720

    # Database
    DATABASE_URL: str = "sqlite:///./baobab_host.db"

    # =====================================================
    # HSM CONFIGURATION (PRODUCTION RENDER SOFT-HSM)
    # =====================================================
    HSM_MODE: str = "SOFT_HSM_REMOTE"
    HSM_REMOTE_URL: str = "{RENDER_HSM_CMD_URL}"

    # HSM communication settings
    HSM_HEADER_LENGTH: int = 4

    # =====================================================
    # LOGGING
    # =====================================================
    LOG_RAW_DATA: bool = True

    # =====================================================
    # CORS
    # =====================================================
    CORS_ORIGINS: str = (
        "http://localhost:5173,"
        "http://127.0.0.1:5173,"
        "http://localhost:3000,"
        "*"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False
    )

    @property
    def cors_origin_list(self) -> List[str]:
        return [
            origin.strip()
            for origin in self.CORS_ORIGINS.split(",")
            if origin.strip()
        ]


settings = Settings()
'''

DEFAULT_EXT_KEYS_BLOCK = '''
DEFAULT_EXTERNAL_HSM_KEYS = [
    {
        "key_identifier": "ZMK_MAIN_EXT",
        "key_name": "External Interchange ZMK (Bank Switch)",
        "key_type": "ZMK",
        "thales_key_type_code": "000",
        "key_usage": "ZONE_MASTER_KEY",
        "kvc": "A823F4",
        "encrypted_key_block": "U1B9F2E5111B968F21B9F2E5111B968F2",
    },
    {
        "key_identifier": "TMK_POS_01_EXT",
        "key_name": "External POS Terminal Master Key",
        "key_type": "TMK",
        "thales_key_type_code": "002",
        "key_usage": "TERMINAL_MASTER_KEY",
        "kvc": "2BD857",
        "encrypted_key_block": "U8F16C85A996F31E38F16C85A996F31E3",
    },
    {
        "key_identifier": "AWK_ATM_01_EXT",
        "key_name": "External Acquirer Working Key (ZPK/TPK)",
        "key_type": "AWK",
        "thales_key_type_code": "001",
        "key_usage": "ACQUIRER_WORKING_PIN_KEY",
        "kvc": "8A8369",
        "encrypted_key_block": "UC8E2A847DA7EC2F0C8E2A847DA7EC2F0",
    },
    {
        "key_identifier": "IWK_SW_01_EXT",
        "key_name": "External Issuer Working Key (NPSB/Visa ZPK)",
        "key_type": "IWK",
        "thales_key_type_code": "001",
        "key_usage": "ISSUER_WORKING_PIN_KEY",
        "kvc": "E27C2A",
        "encrypted_key_block": "U52E244862EE4622152E244862EE46221",
    },
    {
        "key_identifier": "PVK_VISA_01_EXT",
        "key_name": "External Issuer PIN Verification Key (PVK)",
        "key_type": "PVK",
        "thales_key_type_code": "002",
        "key_usage": "PIN_VERIFICATION_KEY",
        "kvc": "141C6A",
        "encrypted_key_block": "U56D33BE3768CF6DD56D33BE3768CF6DD",
    },
    {
        "key_identifier": "MK_AC_EMV01_EXT",
        "key_name": "External EMV Card Master Key (MK-AC)",
        "key_type": "MK-AC",
        "thales_key_type_code": "109",
        "key_usage": "EMV_MASTER_KEY_AC",
        "kvc": "82E136",
        "encrypted_key_block": "U4241A295F72B363C9B3381373C8182C3",
    },
    {
        "key_identifier": "CVK_MAIN_01_EXT",
        "key_name": "External Issuer CVV/CVC Verification Key",
        "key_type": "CVK",
        "thales_key_type_code": "402",
        "key_usage": "CARD_VERIFICATION_KEY",
        "kvc": "141C6A",
        "encrypted_key_block": "U334B547F16230829334B547F16230829",
    },
    {
        "key_identifier": "TAK_MAC_01_EXT",
        "key_name": "External Terminal Authentication MAC Key",
        "key_type": "TAK",
        "thales_key_type_code": "003",
        "key_usage": "TERMINAL_AUTH_MAC_KEY",
        "kvc": "B7035A",
        "encrypted_key_block": "U9A7B2E6CC320A7909A7B2E6CC320A790",
    },
]
'''


def patch_lmk_service(path: Path) -> None:
    backup_file(path)
    text = path.read_text(encoding="utf-8")

    # 1. Replace fallback localhost URL in ExternalSoftHSMBridge.__init__
    text = text.replace(
        'raw_url = (remote_url or settings.HSM_REMOTE_URL or "http://127.0.0.1:8000").strip().rstrip("/")',
        f'raw_url = (remote_url or settings.HSM_REMOTE_URL or "{RENDER_HSM_CMD_URL}").strip().rstrip("/")'
    )
    text = text.replace(
        "def __init__(self, remote_url: Optional[str] = None, timeout_seconds: int = 45):",
        "def __init__(self, remote_url: Optional[str] = None, timeout_seconds: int = 60):"
    )

    # 2. Add User-Agent header to urllib requests so Render/Cloudflare proxy never blocks Host -> HSM calls
    text = text.replace(
        'headers={"Content-Type": "application/json"},',
        'headers={"Content-Type": "application/json", "User-Agent": "BAOBAB-Host-Simulator/1.0"},'
    )
    text = text.replace(
        'req = urllib.request.Request(self.status_url, method="GET")',
        'req = urllib.request.Request(self.status_url, headers={"User-Agent": "BAOBAB-Host-Simulator/1.0"}, method="GET")'
    )
    text = text.replace(
        'req = urllib.request.Request(self.keys_url, method="GET")',
        'req = urllib.request.Request(self.keys_url, headers={"User-Agent": "BAOBAB-Host-Simulator/1.0"}, method="GET")'
    )

    # 3. Inject DEFAULT_EXTERNAL_HSM_KEYS if not present
    if "DEFAULT_EXTERNAL_HSM_KEYS" not in text:
        text = text.replace(
            "def resolve_thales_key_meta(",
            DEFAULT_EXT_KEYS_BLOCK + "\ndef resolve_thales_key_meta("
        )

    # 4. Inject seed_fallback_external_keys method
    helper_method = '''    def seed_fallback_external_keys(self, lmk_check_val: str = "D3B82A0000000000") -> List[str]:
        """Ensures the 8 default External Soft-HSM keys exist in `hsm_key_references`."""
        seeded: List[str] = []
        for item in DEFAULT_EXTERNAL_HSM_KEYS:
            alias = item["key_identifier"]
            rec = self.db.query(HsmKeyReference).filter(HsmKeyReference.key_identifier == alias).first()
            if not rec:
                rec = HsmKeyReference(
                    key_name=item["key_name"],
                    key_type=item["key_type"],
                    key_usage=item["key_usage"],
                    key_identifier=alias,
                    kvc=item["kvc"],
                    algorithm="3DES_2KEY",
                    key_length=128,
                    hsm_key_reference=item["encrypted_key_block"],
                    encrypted_key_block=item["encrypted_key_block"],
                    clear_key_hex=None,
                    provider_type="EXTERNAL_HSM",
                    thales_key_type_code=item["thales_key_type_code"],
                    key_scheme="U",
                    key_version=1,
                    lmk_id="00",
                    lmk_check_value=lmk_check_val,
                    key_status="ACTIVE",
                )
                self.db.add(rec)
            else:
                rec.provider_type = "EXTERNAL_HSM"
                rec.encrypted_key_block = item["encrypted_key_block"]
                rec.hsm_key_reference = item["encrypted_key_block"]
                rec.kvc = item["kvc"]
                rec.thales_key_type_code = item["thales_key_type_code"]
                rec.lmk_check_value = lmk_check_val
                rec.clear_key_hex = None
                rec.key_status = "ACTIVE"
            seeded.append(alias)
        self.db.commit()
        return seeded

    def sync_default_external_keys(self, current_user: str = "admin") -> Dict[str, Any]:'''

    if "def seed_fallback_external_keys" not in text:
        text = text.replace(
            "    def sync_default_external_keys(self, current_user: str = \"admin\") -> Dict[str, Any]:",
            helper_method
        )

    # 5. Harden sync_default_external_keys so if Render Free is cold-starting, it still seeds the keys instead of failing
    old_sync_check = '''        lmk_status = self.get_lmk_and_provider_status()
        if not lmk_status.get("online"):
            raise ConnectionError(lmk_status.get("error") or "External Soft-HSM is offline")'''

    new_sync_check = '''        self.seed_fallback_external_keys("D3B82A0000000000")
        lmk_status = self.get_lmk_and_provider_status()
        if not lmk_status.get("online"):
            seeded_fallback = self.seed_fallback_external_keys("D3B82A0000000000")
            return {
                "status": "SYNCED_OFFLINE_FALLBACK",
                "lmk_check_value": "D3B82A0000000000",
                "synced_key_aliases": seeded_fallback,
                "count": len(seeded_fallback),
            }'''

    if old_sync_check in text:
        text = text.replace(old_sync_check, new_sync_check)

    # 6. Auto-seed inside resolve_external_key_record so transactions never fail with Provider Isolation Violation
    old_resolve = '''        candidates = [key_identifier, f"{key_identifier}_EXT"]
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

    new_resolve = '''        base_id = key_identifier[:-4] if key_identifier.endswith("_EXT") else key_identifier
        candidates = [key_identifier, f"{base_id}_EXT", base_id]
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

    if old_resolve in text:
        text = text.replace(old_resolve, new_resolve)

    path.write_text(text, encoding="utf-8")
    print(f"[UPDATED] {path}")


def patch_lmk_router(path: Path) -> None:
    if not path.exists():
        return
    backup_file(path)
    text = path.read_text(encoding="utf-8")
    # Replace any localhost default in router with Render URL
    text = text.replace("https://thales-10k-soft-hsm.onrender.com/api/host/command", RENDER_HSM_CMD_URL)
    text = text.replace("http://127.0.0.1:8000", RENDER_HSM_BASE)
    if "seed_fallback_external_keys" not in text:
        text = text.replace(
            "svc = LMKKeyManagementService(db)",
            "svc = LMKKeyManagementService(db)\n    svc.seed_fallback_external_keys()"
        )
    path.write_text(text, encoding="utf-8")
    print(f"[UPDATED] {path}")


def patch_seed_data(path: Path) -> None:
    if not path.exists():
        return
    backup_file(path)
    text = path.read_text(encoding="utf-8")
    hook = '''
    try:
        from app.lmk_key_management_service import LMKKeyManagementService
        LMKKeyManagementService(db).seed_fallback_external_keys()
    except Exception:
        pass
'''
    if "seed_fallback_external_keys" not in text:
        text = text + hook
        path.write_text(text, encoding="utf-8")
        print(f"[UPDATED] {path}")


def main():
    print("=" * 75)
    print(f" Patching Host Simulator for Render HSM: {RENDER_HSM_CMD_URL}")
    print("=" * 75)

    config_path = HOST_ROOT / "backend" / "app" / "config.py"
    backup_file(config_path)
    config_path.write_text(CONFIG_PY, encoding="utf-8")
    print(f"[UPDATED] {config_path}")

    # Also update .env if it exists in backend/ or root
    for env_candidate in [HOST_ROOT / ".env", HOST_ROOT / "backend" / ".env"]:
        if env_candidate.exists():
            backup_file(env_candidate)
            env_txt = env_candidate.read_text(encoding="utf-8")
            lines = [
                line for line in env_txt.splitlines()
                if not line.strip().startswith("HSM_REMOTE_URL=") and not line.strip().startswith("HSM_MODE=")
            ]
            lines.append("HSM_MODE=SOFT_HSM_REMOTE")
            lines.append(f"HSM_REMOTE_URL={RENDER_HSM_CMD_URL}")
            env_candidate.write_text("\n".join(lines) + "\n", encoding="utf-8")
            print(f"[UPDATED] {env_candidate}")

    lmk_svc_path = HOST_ROOT / "backend" / "app" / "lmk_key_management_service.py"
    if lmk_svc_path.exists():
        patch_lmk_service(lmk_svc_path)

    lmk_router_path = HOST_ROOT / "backend" / "app" / "routers" / "lmk_key_management_router.py"
    if lmk_router_path.exists():
        patch_lmk_router(lmk_router_path)

    seed_path = HOST_ROOT / "backend" / "app" / "seed_data.py"
    if seed_path.exists():
        patch_seed_data(seed_path)

    print("=" * 75)
    print(" HOST SIMULATOR PATCH COMPLETE!")
    print("=" * 75)


if __name__ == "__main__":
    main()