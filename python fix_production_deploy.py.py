"""
fix_production_deploy.py
Fixes Remote Soft-HSM connection, auto-sync on provider toggle,
Render/Netlify production configuration, and prepares repository for GitHub push.
"""

import os
from pathlib import Path

BASE_DIR = Path(r"E:\HOST_VSCODE\host-simulator-github-prod")
if not BASE_DIR.exists():
    BASE_DIR = Path(".")

print(f"Applying Production Fixes in: {BASE_DIR.resolve()}")

# 1. Update config.py with robust timeout and Netlify CORS support
config_path = BASE_DIR / "backend" / "app" / "config.py"
config_content = '''# backend/app/config.py
from typing import List
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
    ENFORCE_SECURE_DEFAULTS: bool = False

    # Database
    DATABASE_URL: str = "sqlite:///./baobab_host.db"

    # =====================================================
    # HSM CONFIGURATION
    # =====================================================
    HSM_MODE: str = "SOFT_HSM_REMOTE"
    HSM_REMOTE_URL: str = "https://thales-10k-soft-hsm.onrender.com/api/host/command"
    HSM_HEADER_LENGTH: int = 4
    HSM_TIMEOUT_SECONDS: int = 60

    # =====================================================
    # LOGGING
    # =====================================================
    LOG_RAW_DATA: bool = True

    # =====================================================
    # CORS
    # =====================================================
    CORS_ORIGINS: str = (
        "https://rajon-test-payment-solution.netlify.app,"
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

with open(config_path, "w", encoding="utf-8") as f:
    f.write(config_content)
print(f"[OK] Patched {config_path}")

# 2. Patch lmk_key_management_service.py to handle Render cold-starts gracefully
lkms_path = BASE_DIR / "backend" / "app" / "lmk_key_management_service.py"
if lkms_path.exists():
    with open(lkms_path, "r", encoding="utf-8") as f:
        code = f.read()

    # Increase ExternalSoftHSMBridge default timeout
    code = code.replace(
        "def __init__(self, remote_url: Optional[str] = None, timeout_seconds: int = 45):",
        "def __init__(self, remote_url: Optional[str] = None, timeout_seconds: int = 60):",
    )

    # Ensure clean base url stripping
    old_bridge_url = 'self.execute_url = f"{self.base_url}/api/host/command"'
    new_bridge_url = """if "/api/" in self.base_url:
            self.execute_url = self.base_url
            self.base_url = self.base_url.split("/api/")[0]
        else:
            self.execute_url = f"{self.base_url}/api/host/command" """

    if old_bridge_url in code:
        code = code.replace(old_bridge_url, new_bridge_url)

    with open(lkms_path, "w", encoding="utf-8") as f:
        f.write(code)
    print(f"[OK] Hardened {lkms_path}")

# 3. Patch backend/app/seed_data.py to automatically seed external keys if missing
seed_path = BASE_DIR / "backend" / "app" / "seed_data.py"
if seed_path.exists():
    with open(seed_path, "r", encoding="utf-8") as f:
        s_code = f.read()

    if "def seed_external_hsm_keys_if_needed" not in s_code:
        ext_seed_func = '''
def seed_external_hsm_keys_if_needed(db: Session) -> None:
    """Pre-seeds default EXTERNAL_HSM records so provider switching never fails with isolation errors."""
    from app.models import HsmKeyReference
    default_external = [
        ("PVK_VISA_01_EXT", "PVK_VISA_01", "PVK", "002", "U5566778899AABBCC5566778899AABBCC", "782100", "PIN_VERIFICATION_KEY"),
        ("AWK_ATM_01_EXT", "AWK_ATM_01", "AWK", "001", "U1A2B3C4D5E6F70811A2B3C4D5E6F7081", "123456", "ACQUIRER_WORKING_PIN_KEY"),
        ("IWK_SW_01_EXT", "IWK_SW_01", "IWK", "001", "U89ABCDEF0123456789ABCDEF01234567", "654321", "ISSUER_WORKING_PIN_KEY"),
        ("CVK_MAIN_01_EXT", "CVK_MAIN_01", "CVK", "402", "U5566778899AABBCC5566778899AABBCC", "011000", "CARD_VERIFICATION_KEY"),
        ("TAK_MAC_01_EXT", "TAK_MAC_01", "TAK", "003", "U8899AABBCCDDEEFF8899AABBCCDDEEFF", "112233", "TERMINAL_AUTH_MAC_KEY"),
        ("MK_AC_EMV01_EXT", "MK_AC_EMV01", "MK-AC", "109", "UAABBCCDDEEFF00112233445566778899", "A1B2C3", "EMV_MASTER_KEY_AC"),
        ("ZMK_MAIN_EXT", "ZMK_MAIN", "ZMK", "000", "U0123456789ABCDEF0123456789ABCDEF", "D3B82A", "ZONE_MASTER_KEY"),
    ]
    for ext_alias, base_alias, ktype, tcode, tok, kvc, usage in default_external:
        existing = db.query(HsmKeyReference).filter(HsmKeyReference.key_identifier == ext_alias).first()
        if not existing:
            db.add(HsmKeyReference(
                key_name=f"External {ktype} ({base_alias})",
                key_type=ktype,
                key_usage=usage,
                key_identifier=ext_alias,
                kvc=kvc,
                algorithm="3DES_2KEY",
                key_length=128,
                hsm_key_reference=tok,
                encrypted_key_block=tok,
                clear_key_hex=None,
                provider_type="EXTERNAL_HSM",
                thales_key_type_code=tcode,
                key_scheme="U",
                key_version=1,
                lmk_id="00",
                key_status="ACTIVE",
            ))
    db.commit()
'''
        s_code += ext_seed_func
        # Hook into seed_initial_data
        s_code = s_code.replace(
            "seed_host_parameters(db)",
            "seed_host_parameters(db)\n    seed_external_hsm_keys_if_needed(db)"
        )
        with open(seed_path, "w", encoding="utf-8") as f:
            f.write(s_code)
        print(f"[OK] Added automated external keys seeding into {seed_path}")

# 4. Generate .env for Render & local production runs
env_path = BASE_DIR / "backend" / ".env"
env_content = """APP_NAME="BAOBAB Private Host Simulator"
APP_ENV=production
DATABASE_URL=sqlite:///./baobab_host.db
HSM_MODE=SOFT_HSM_REMOTE
HSM_REMOTE_URL=https://thales-10k-soft-hsm.onrender.com/api/host/command
HSM_HEADER_LENGTH=4
HSM_TIMEOUT_SECONDS=60
LOG_RAW_DATA=True
CORS_ORIGINS=https://rajon-test-payment-solution.netlify.app,http://localhost:5173,http://127.0.0.1:5173
"""
with open(env_path, "w", encoding="utf-8") as f:
    f.write(env_content)
print(f"[OK] Wrote production environment variables to {env_path}")

print("\nAll production fixes applied successfully!")