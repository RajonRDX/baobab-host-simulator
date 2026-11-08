#!/usr/bin/env python3
"""
FILE 1 OF 3: tools/install_lmk_key_mgmt_part1_models_and_service.py
Implements LMK-Centric Key Management & Key Ownership (Part 1):
  1. Extends HsmKeyReference in backend/app/models.py with:
     - provider_type ('INTERNAL_HSM' | 'EXTERNAL_HSM')
     - thales_key_type_code ('000', '001', '002', '003', '008', '009', '109', '402', etc.)
     - key_scheme ('U', 'T', 'S', 'Z', 'X', 'Y')
     - key_version (int, default 1)
     - lmk_id ('00')
     - lmk_check_value (16H LMK domain identifier, e.g. 'D3B82A0000000000')
     - encrypted_key_block (LMK-protected key token 'U...' or 'S...')
     - exportable_flag (bool)
     - rotated_from_key_id (optional lineage reference)
  2. Extends backend/app/schemas.py with LMK Key Management request/response schemas.
  3. Creates backend/app/lmk_key_management_service.py implementing:
     - Live Soft-HSM LMK domain interrogation via Thales NC -> ND
     - External key generation via Thales A0 -> A1 (Mode 0 & Mode 1)
     - External key import under ZMK/TMK via Thales A6 -> A7
     - External key export under ZMK/TMK via Thales A8 -> A9
     - External key KCV & parity verification via Thales BU -> BV
     - Key rotation (A0 new version + supersede old version)
     - Strict provider & LMK domain isolation (never stores clear keys for External HSM)
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def patch_models() -> None:
    models_path = ROOT / "backend" / "app" / "models.py"
    content = models_path.read_text(encoding="utf-8")

    marker = "# [PATCH lmk_centric_key_mgmt:hsm_key_columns]"
    if marker in content:
        print("[SKIP] backend/app/models.py already contains LMK key management columns.")
        return

    target = '    key_status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")'
    replacement = f"""    key_status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
{marker}
    provider_type: Mapped[str] = mapped_column(String(30), nullable=False, default="INTERNAL_HSM", index=True)
    thales_key_type_code: Mapped[str] = mapped_column(String(10), nullable=False, default="001")
    key_scheme: Mapped[str] = mapped_column(String(10), nullable=False, default="U")
    key_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    lmk_id: Mapped[str] = mapped_column(String(10), nullable=False, default="00")
    lmk_check_value: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    encrypted_key_block: Mapped[Optional[str]] = mapped_column(String(256))
    kcv_type: Mapped[str] = mapped_column(String(10), nullable=False, default="6H")
    exportable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    rotated_from_key_id: Mapped[Optional[str]] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)"""

    if target not in content:
        raise RuntimeError("Could not locate HsmKeyReference.key_status in backend/app/models.py")

    # Check if created_at already exists on HsmKeyReference
    hsm_block_idx = content.index("class HsmKeyReference(Base):")
    next_class_idx = content.index("class ", hsm_block_idx + 10)
    hsm_block = content[hsm_block_idx:next_class_idx]
    if "created_at:" in hsm_block:
        replacement = replacement.split("    created_at:")[0].rstrip()

    updated = content.replace(target, replacement, 1)
    models_path.write_text(updated, encoding="utf-8")
    print("[OK] Patched backend/app/models.py with LMK ownership & provider isolation columns.")


def patch_schemas() -> None:
    schemas_path = ROOT / "backend" / "app" / "schemas.py"
    content = schemas_path.read_text(encoding="utf-8")

    marker = "# [PATCH lmk_centric_key_mgmt:schemas]"
    if marker in content:
        print("[SKIP] backend/app/schemas.py already contains LMK key management schemas.")
        return

    addition = f"""

{marker}
class ExternalKeyGenerateRequest(BaseModel):
    key_identifier: str = Field(..., min_length=2, max_length=120, description="Host key alias, e.g. ZPK_EXT_ISS_01")
    key_name: str = Field("External Soft-HSM Key", max_length=100)
    key_type: str = Field("ZPK", description="Logical type: ZMK, TMK, ZPK, TPK, PVK, CVK, TAK, ZAK, BDK, MK-AC, ZEK, DEK, TEK")
    thales_key_type_code: Optional[str] = Field(None, description="Explicit 3-char Thales key type: 000, 001, 002, 003, 008, 009, 109, 402, 00A, 00B")
    key_usage: Optional[str] = Field(None, description="Usage description or TR-31 usage code")
    key_scheme: str = Field("U", description="LMK encryption scheme: U (Double 3DES), T (Triple 3DES), S (Thales Key Block), Z (Single DES)")
    mode: str = Field("0", description="A0 Mode: '0' = Generate under LMK only, '1' = Generate + Export under ZMK/TMK")
    export_zmk_key_identifier: Optional[str] = Field(None, description="When mode='1', alias of ZMK/TMK in Host DB")
    export_scheme: str = Field("U", description="Export scheme under ZMK/TMK when mode='1'")
    is_tmk_export: bool = Field(False, description="True to set ';1' TMK flag on A0 mode 1 export")
    lmk_id: str = Field("00", description="2-digit Thales LMK slot identifier")
    institution_id: Optional[str] = None
    processing_system_id: Optional[str] = None


class ExternalKeyImportRequest(BaseModel):
    key_identifier: str = Field(..., min_length=2, max_length=120, description="Alias for imported key")
    key_name: str = Field("Imported Soft-HSM Key", max_length=100)
    key_type: str = Field("ZPK")
    thales_key_type_code: Optional[str] = Field(None, description="3-char Thales key type, e.g. 001, 002, 003, 402, 109")
    key_usage: Optional[str] = None
    zmk_key_identifier: str = Field(..., description="Alias of LMK-protected ZMK/TMK in Host DB")
    encrypted_key_under_zmk: str = Field(..., min_length=16, description="Working key encrypted under ZMK (e.g. U + 32H)")
    key_scheme_lmk: str = Field("U", description="Target LMK scheme: U, T, or S")
    is_tmk: bool = Field(False, description="True if wrapping key is a TMK (;1)")
    lmk_id: str = Field("00")
    institution_id: Optional[str] = None
    processing_system_id: Optional[str] = None


class ExternalKeyExportRequest(BaseModel):
    key_identifier: str = Field(..., description="Alias of working key protected under Soft-HSM LMK")
    zmk_key_identifier: str = Field(..., description="Alias of ZMK/TMK protected under Soft-HSM LMK")
    export_scheme: str = Field("U", description="Key scheme under ZMK/TMK: U, T, X, Y, 0")
    is_tmk: bool = Field(False, description="True if exporting under TMK (;1)")
    lmk_id: str = Field("00")


class ExternalKeyRotateRequest(BaseModel):
    key_identifier: str = Field(..., description="Existing key alias to rotate via Soft-HSM A0")
    new_key_scheme: Optional[str] = None
    export_zmk_key_identifier: Optional[str] = None


class HsmProviderSwitchRequest(BaseModel):
    provider_mode: str = Field(..., description="'INTERNAL_HSM' (SOFT_HSM_LOCAL) or 'EXTERNAL_HSM' (SOFT_HSM_REMOTE)")
    remote_url: Optional[str] = Field(None, description="Base URL or /api/host/command URL of External Soft-HSM")
"""
    schemas_path.write_text(content + addition, encoding="utf-8")
    print("[OK] Patched backend/app/schemas.py with LMK key management schemas.")


def write_lmk_service() -> None:
    service_path = ROOT / "backend" / "app" / "lmk_key_management_service.py"
    code = '''"""
lmk_key_management_service.py — LMK-Centric Key Management & Cryptographic Ownership Service
=============================================================================================
Enforces strict Thales payShield 10K LMK domain ownership and provider isolation:
  - When External Soft-HSM is active, ALL key generation (A0), import (A6), export (A8),
    KCV verification (BU), and LMK diagnostics (NC) execute on the External Soft-HSM.
  - Clear key material is NEVER requested (`synthetic_mode=False`), NEVER returned to the
    frontend, and NEVER stored in the Host database for External HSM keys.
  - Only LMK-encrypted key tokens (`U...`, `T...`, `S...`, `Z...`) and non-sensitive metadata
    (alias, key type, usage, scheme, version, KCV, LMK domain check value) are stored.
  - Keys belonging to `INTERNAL_HSM` and `EXTERNAL_HSM` (or a mismatched LMK check value)
    are strictly isolated and never silently substituted.
"""

import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from app.audit_service import record_audit, serialize_entity
from app.config import settings
from app.logging_service import record_system_log
from app.models import HsmAuditLog, HsmKeyReference, HsmOperation

# Canonical mapping between Host logical key types and Thales 3-character Variant Key Type codes
# Verified against PUGD0537-004 Section 3.1 (p. 36) & Soft-HSM backend/lmk_manager.py
THALES_KEY_TYPE_MAP: Dict[str, Dict[str, str]] = {
    "ZMK":   {"code": "000", "pair": "04_05", "variant": "0", "usage": "ZONE_MASTER_KEY", "tr31_usage": "52", "bu_code": "00"},
    "KML":   {"code": "200", "pair": "04_05", "variant": "2", "usage": "VISACASH_MASTER_KEY", "tr31_usage": "31", "bu_code": "00"},
    "ZPK":   {"code": "001", "pair": "06_07", "variant": "0", "usage": "INTERCHANGE_PIN_TRANSLATION", "tr31_usage": "72", "bu_code": "01"},
    "AWK":   {"code": "001", "pair": "06_07", "variant": "0", "usage": "ACQUIRER_WORKING_PIN_KEY", "tr31_usage": "72", "bu_code": "01"},
    "IWK":   {"code": "001", "pair": "06_07", "variant": "0", "usage": "ISSUER_WORKING_PIN_KEY", "tr31_usage": "72", "bu_code": "01"},
    "TMK":   {"code": "002", "pair": "14_15", "variant": "0", "usage": "TERMINAL_MASTER_KEY", "tr31_usage": "51", "bu_code": "02"},
    "TPK":   {"code": "002", "pair": "14_15", "variant": "0", "usage": "TERMINAL_PIN_KEY", "tr31_usage": "71", "bu_code": "02"},
    "PVK":   {"code": "002", "pair": "14_15", "variant": "0", "usage": "PIN_VERIFICATION_KEY", "tr31_usage": "V2", "bu_code": "02"},
    "IKEY":  {"code": "302", "pair": "14_15", "variant": "3", "usage": "DUKPT_INITIAL_KEY", "tr31_usage": "B1", "bu_code": "02"},
    "CVK":   {"code": "402", "pair": "14_15", "variant": "4", "usage": "CARD_VERIFICATION_KEY", "tr31_usage": "C0", "bu_code": "02"},
    "TAK":   {"code": "003", "pair": "16_17", "variant": "0", "usage": "TERMINAL_AUTH_MAC_KEY", "tr31_usage": "M3", "bu_code": "03"},
    "WWK":   {"code": "006", "pair": "22_23", "variant": "0", "usage": "WATCHWORD_KEY", "tr31_usage": "01", "bu_code": "02"},
    "ZAK":   {"code": "008", "pair": "14_15", "variant": "0", "usage": "ZONE_AUTH_MAC_KEY", "tr31_usage": "M3", "bu_code": "08"},
    "BDK":   {"code": "009", "pair": "28_29", "variant": "0", "usage": "DUKPT_BASE_DERIVATION_KEY", "tr31_usage": "B0", "bu_code": "09"},
    "MK-AC": {"code": "109", "pair": "28_29", "variant": "0", "usage": "EMV_MASTER_KEY_AC", "tr31_usage": "E0", "bu_code": "09"},
    "MK-SMI":{"code": "209", "pair": "28_29", "variant": "2", "usage": "EMV_MASTER_KEY_SMI", "tr31_usage": "E2", "bu_code": "09"},
    "MK-SMC":{"code": "309", "pair": "28_29", "variant": "3", "usage": "EMV_MASTER_KEY_SMC", "tr31_usage": "E1", "bu_code": "09"},
    "ZEK":   {"code": "00A", "pair": "30_31", "variant": "0", "usage": "ZONE_ENCRYPTION_KEY", "tr31_usage": "22", "bu_code": "02"},
    "DEK":   {"code": "00B", "pair": "32_33", "variant": "0", "usage": "DATA_ENCRYPTION_KEY", "tr31_usage": "21", "bu_code": "02"},
    "TEK":   {"code": "30B", "pair": "32_33", "variant": "3", "usage": "TERMINAL_ENCRYPTION_KEY", "tr31_usage": "23", "bu_code": "02"},
    "KEK":   {"code": "107", "pair": "24_25", "variant": "1", "usage": "EMV_TRANSPORT_KEK", "tr31_usage": "54", "bu_code": "02"},
}


def resolve_thales_key_meta(key_type: str, explicit_code: Optional[str] = None) -> Dict[str, str]:
    kt_up = (key_type or "ZPK").upper().strip()
    meta = dict(THALES_KEY_TYPE_MAP.get(kt_up, THALES_KEY_TYPE_MAP["ZPK"]))
    if explicit_code and len(explicit_code.strip()) == 3:
        code_up = explicit_code.strip().upper()
        meta["code"] = code_up
        for k, v in THALES_KEY_TYPE_MAP.items():
            if v["code"] == code_up:
                meta["pair"] = v["pair"]
                meta["variant"] = v["variant"]
                meta["bu_code"] = v["bu_code"]
                break
    return meta


def inspect_key_token_format(token_str: str) -> Dict[str, Any]:
    """
    Inspects a key token returned by the Soft-HSM to verify whether it is a valid
    LMK-encrypted key block or variant token and never a clear key without scheme validation.
    """
    tok = (token_str or "").strip()
    if not tok:
        return {"valid": False, "reason": "Empty key token"}

    first = tok[0].upper()
    if first in ("U", "X") and len(tok) == 33 and all(c in "0123456789ABCDEFabcdef" for c in tok[1:]):
        return {
            "valid": True,
            "representation": "VARIANT_DOUBLE_LENGTH_TOKEN" if first == "U" else "X917_DOUBLE_LENGTH_TOKEN",
            "scheme": first,
            "key_length_bits": 128,
            "len_flag_bu": "1",
            "token": tok.upper(),
        }
    if first in ("T", "Y") and len(tok) == 49 and all(c in "0123456789ABCDEFabcdef" for c in tok[1:]):
        return {
            "valid": True,
            "representation": "VARIANT_TRIPLE_LENGTH_TOKEN" if first == "T" else "X917_TRIPLE_LENGTH_TOKEN",
            "scheme": first,
            "key_length_bits": 192,
            "len_flag_bu": "2",
            "token": tok.upper(),
        }
    if first == "Z" and len(tok) == 17 and all(c in "0123456789ABCDEFabcdef" for c in tok[1:]):
        return {
            "valid": True,
            "representation": "VARIANT_SINGLE_LENGTH_TOKEN",
            "scheme": "Z",
            "key_length_bits": 64,
            "len_flag_bu": "0",
            "token": tok.upper(),
        }
    if first in ("S", "R") and len(tok) >= 24 and tok[2:6].isdigit():
        kb_len = int(tok[2:6])
        if len(tok) == kb_len:
            usage = tok[6:8]
            alg = tok[8:9]
            ver = tok[10:12]
            return {
                "valid": True,
                "representation": "THALES_KEY_BLOCK" if first == "S" else "TR31_KEY_BLOCK",
                "scheme": first,
                "key_length_bits": 128,
                "len_flag_bu": "1",
                "header_usage": usage,
                "header_algorithm": alg,
                "header_version": int(ver) if ver.isdigit() else 1,
                "token": tok,
            }
    return {"valid": False, "reason": f"Unrecognized or unsafe key representation (len={len(tok)})"}


class ExternalSoftHSMBridge:
    """
    Low-level HTTP client to the External Thales payShield 10K Soft-HSM.
    Always sets `synthetic_mode=False` for key management so clear keys never leave the Soft-HSM.
    """

    def __init__(self, remote_url: Optional[str] = None, timeout_seconds: int = 45):
        raw_url = (remote_url or settings.HSM_REMOTE_URL or "http://127.0.0.1:8000").strip().rstrip("/")
        if raw_url.endswith("/api/hsm/execute") or raw_url.endswith("/api/host/command") or raw_url.endswith("/api/hsm_api"):
            self.base_url = raw_url.rsplit("/api/", 1)[0]
            self.execute_url = raw_url
        else:
            self.base_url = raw_url
            self.execute_url = f"{self.base_url}/api/host/command"
        self.status_url = f"{self.base_url}/api/status"
        self.keys_url = f"{self.base_url}/api/keys"
        self.timeout = timeout_seconds

    def execute_command(
        self,
        raw_command: str,
        header_length: int = 4,
        synthetic_mode: bool = False,
        source_host: str = "BAOBAB_HOST_KEY_MANAGER",
    ) -> Dict[str, Any]:
        payload = json.dumps({
            "command": raw_command,
            "header_length": header_length,
            "synthetic_mode": synthetic_mode,
            "source_host": source_host,
            "framing": "ASCII",
        }).encode("utf-8")

        req = urllib.request.Request(
            self.execute_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                # Defensive scrub: ensure clear_key is never retained in Host memory
                if isinstance(data.get("crypto_metadata"), dict):
                    data["crypto_metadata"].pop("clear_key", None)
                return data
        except urllib.error.URLError as exc:
            raise ConnectionError(f"External Soft-HSM unreachable at {self.execute_url}: {exc}") from exc

    def fetch_status(self) -> Dict[str, Any]:
        req = urllib.request.Request(self.status_url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception:
            # Fallback to NC command if /api/status is not exposed (e.g. serverless function)
            nc_res = self.execute_command("0000NC", synthetic_mode=False)
            raw_resp = nc_res.get("raw_response", "")
            lmk_kcv = raw_resp[8:24] if len(raw_resp) >= 24 else "UNKNOWN"
            fw = raw_resp[24:] if len(raw_resp) > 24 else "1347-0900"
            return {
                "status": "ONLINE" if nc_res.get("status_code") == "00" else "ERROR",
                "hsm_state": "AUTHORIZED_ONLINE",
                "firmware": fw,
                "lmk_check_value": lmk_kcv,
                "storage": {"mode": "COMMAND_ONLY_ENDPOINT", "persistent_cloud_db": False},
            }

    def fetch_seeded_remote_keys(self) -> List[Dict[str, Any]]:
        """
        Fetches the Soft-HSM's pre-seeded keystore metadata via GET /api/keys,
        stripping `clear_key` immediately so the Host only ever sees LMK-encrypted tokens.
        """
        req = urllib.request.Request(self.keys_url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                raw_keys = body.get("keys", [])
                sanitized = []
                for k in raw_keys:
                    sanitized.append({
                        "key_id": k.get("key_id"),
                        "key_label": k.get("key_label"),
                        "key_type": k.get("key_type"),
                        "scheme": k.get("scheme", "U"),
                        "lmk_cryptogram": k.get("lmk_cryptogram"),
                        "kcv": k.get("kcv"),
                        "created_at": k.get("created_at"),
                    })
                return sanitized
        except Exception:
            return []


class LMKKeyManagementService:
    """
    Coordinates LMK-centric key lifecycle management, LMK domain verification,
    and provider isolation between INTERNAL_HSM and EXTERNAL_HSM.
    """

    def __init__(self, db: Session):
        self.db = db
        self.bridge = ExternalSoftHSMBridge()

    @staticmethod
    def is_external_hsm_active() -> bool:
        return settings.HSM_MODE.upper() in ("SOFT_HSM_REMOTE", "EXTERNAL_HSM")

    @staticmethod
    def active_provider_type() -> str:
        return "EXTERNAL_HSM" if LMKKeyManagementService.is_external_hsm_active() else "INTERNAL_HSM"

    def get_lmk_and_provider_status(self) -> Dict[str, Any]:
        """
        Queries the active HSM provider for LMK status, LMK check value (NC/ND),
        firmware revision (VR/VS), operational state (NO/NP), and persistence risk analysis.
        """
        provider = self.active_provider_type()
        internal_count = self.db.query(HsmKeyReference).filter(
            HsmKeyReference.provider_type == "INTERNAL_HSM"
        ).count()
        external_count = self.db.query(HsmKeyReference).filter(
            HsmKeyReference.provider_type == "EXTERNAL_HSM"
        ).count()

        if provider == "INTERNAL_HSM":
            from app.hsm_adapter import SoftHsmCryptoCore
            base_lmk = SoftHsmCryptoCore.DEFAULT_LMK["04_05"]
            kcv6 = SoftHsmCryptoCore.calculate_kcv(base_lmk)
            return {
                "active_provider": "INTERNAL_HSM",
                "hsm_mode": settings.HSM_MODE,
                "online": True,
                "hsm_state": "INTERNAL_SIMULATOR_READY",
                "lmk_id": "00",
                "lmk_check_value": f"{kcv6}0000000000",
                "lmk_kcv_short": kcv6,
                "firmware": "INTERNAL-SIM-1.0",
                "software_revision": "BAOBAB Internal Soft-HSM Core",
                "remote_url": settings.HSM_REMOTE_URL,
                "key_counts": {"internal_keys": internal_count, "external_keys": external_count},
                "persistence_audit": {
                    "lmk_generation_mechanism": "Internal static 5-pair Variant LMK table",
                    "lmk_storage_location": "Host Simulator process memory (app/hsm_adapter.py)",
                    "survives_restarts": True,
                    "survives_redeploy": True,
                    "ephemeral_risk": "LOW (Internal simulation mode)",
                },
            }

        # External Soft-HSM active: run real NC diagnostics and /api/status check
        try:
            status_info = self.bridge.fetch_status()
            nc_tx = self.bridge.execute_command("0000NC", synthetic_mode=False)
            raw_nc = nc_tx.get("raw_response", "")
            lmk_check_val = status_info.get("lmk_check_value") or (raw_nc[8:24] if len(raw_nc) >= 24 else "UNKNOWN")
            fw = status_info.get("firmware") or (raw_nc[24:] if len(raw_nc) > 24 else "1347-0900")
            storage_meta = status_info.get("storage", {})
            is_ephemeral = not bool(storage_meta.get("persistent_cloud_db", False))

            # Check if any stored EXTERNAL_HSM keys have a mismatched LMK domain
            mismatched_keys = (
                self.db.query(HsmKeyReference)
                .filter(
                    HsmKeyReference.provider_type == "EXTERNAL_HSM",
                    HsmKeyReference.lmk_check_value != None,  # noqa: E711
                    HsmKeyReference.lmk_check_value != lmk_check_val,
                )
                .count()
            )

            return {
                "active_provider": "EXTERNAL_HSM",
                "hsm_mode": settings.HSM_MODE,
                "online": nc_tx.get("status_code") == "00",
                "hsm_state": status_info.get("hsm_state", "AUTHORIZED_ONLINE"),
                "lmk_id": "00",
                "lmk_check_value": lmk_check_val,
                "lmk_kcv_short": lmk_check_val[:6],
                "firmware": fw,
                "software_revision": f"Thales payShield 10K v{status_info.get('version', '3.5.0')} Soft-HSM",
                "remote_url": self.bridge.execute_url,
                "diagnostic_nc_response": raw_nc,
                "key_counts": {
                    "internal_keys": internal_count,
                    "external_keys": external_count,
                    "lmk_domain_mismatched_keys": mismatched_keys,
                },
                "persistence_audit": {
                    "lmk_generation_mechanism": "Deterministic 12-pair Variant LMK table (DEFAULT_LMK_TABLE in backend/lmk_manager.py)",
                    "lmk_storage_location": "Soft-HSM process memory (RAM); default table compiled in source code",
                    "survives_restarts": True,
                    "survives_redeploy": True,
                    "custom_lmk_survives_restart": False,
                    "soft_hsm_storage_mode": storage_meta.get("mode", "EPHEMERAL_MEMORY"),
                    "persistent_cloud_db": bool(storage_meta.get("persistent_cloud_db", False)),
                    "ephemeral_risk": (
                        "CRITICAL_NOTICE: Soft-HSM runs on Render Free ephemeral storage without DATABASE_URL. "
                        "However, because the Host Simulator stores LMK-encrypted key blocks (U.../S...) in the Host DB "
                        "and the Soft-HSM Default LMK (KCV D3B82A) is deterministic across restarts, Host-stored "
                        "encrypted key blocks remain valid across restarts unless POST /api/lmk is mutated."
                        if is_ephemeral else "PROTECTED (PostgreSQL cloud sync enabled)"
                    ),
                },
            }
        except Exception as exc:
            return {
                "active_provider": "EXTERNAL_HSM",
                "hsm_mode": settings.HSM_MODE,
                "online": False,
                "hsm_state": "OFFLINE_UNREACHABLE",
                "lmk_id": "00",
                "lmk_check_value": "UNREACHABLE",
                "lmk_kcv_short": "ERR",
                "firmware": "N/A",
                "remote_url": self.bridge.execute_url,
                "error": str(exc),
                "key_counts": {"internal_keys": internal_count, "external_keys": external_count},
            }

    def sync_default_external_keys(self, current_user: str = "admin") -> Dict[str, Any]:
        """
        Synchronizes the Soft-HSM's default LMK-encrypted keys (ZMK_MAIN, TMK_POS_01,
        AWK_ATM_01, IWK_SW_01, PVK_VISA_01, MK_AC_EMV01, CVK_ISS_01, TAK_MAC_01)
        into the Host Simulator under provider_type='EXTERNAL_HSM' without storing any clear keys.
        Verifies each key token using the Soft-HSM BU (Generate KCV) command.
        """
        lmk_status = self.get_lmk_and_provider_status()
        if not lmk_status.get("online"):
            raise ConnectionError(lmk_status.get("error") or "External Soft-HSM is offline")

        lmk_check_val = lmk_status["lmk_check_value"]
        remote_keys = self.bridge.fetch_seeded_remote_keys()
        synced: List[str] = []

        # Map Soft-HSM default key IDs to Host Simulator standard aliases
        alias_map = {
            "ZMK_MAIN": ("ZMK_MAIN", "ZMK", "000"),
            "TMK_POS_01": ("TMK_POS_01", "TMK", "002"),
            "AWK_ATM_01": ("AWK_ATM_01", "AWK", "001"),
            "IWK_SW_01": ("IWK_SW_01", "IWK", "001"),
            "PVK_VISA_01": ("PVK_VISA_01", "PVK", "008"),
            "MK_AC_EMV01": ("MK_AC_EMV01", "MK-AC", "109"),
            "CVK_ISS_01": ("CVK_MAIN_01", "CVK", "402"),
            "TAK_MAC_01": ("TAK_MAC_01", "TAK", "003"),
        }

        for rk in remote_keys:
            rk_id = rk.get("key_id") or ""
            token = rk.get("lmk_cryptogram") or ""
            fmt = inspect_key_token_format(token)
            if not fmt["valid"]:
                continue

            host_alias, logical_type, thales_code = alias_map.get(
                rk_id, (rk_id, "ZPK", rk.get("key_type", "001"))
            )
            meta = resolve_thales_key_meta(logical_type, thales_code)

            # Verify token on Soft-HSM via BU command
            bu_cmd = f"0000BU{meta['bu_code']}{fmt['len_flag_bu']}{fmt['token']}"
            bu_tx = self.bridge.execute_command(bu_cmd, synthetic_mode=False)
            raw_bu = bu_tx.get("raw_response", "")
            verified_kcv = raw_bu[8:14] if (bu_tx.get("status_code") == "00" and len(raw_bu) >= 14) else rk.get("kcv", "000000")

            # Store under an External-specific alias if an INTERNAL_HSM key already uses the base identifier,
            # or update/create the record with provider_type='EXTERNAL_HSM'
            existing = self.db.query(HsmKeyReference).filter(HsmKeyReference.key_identifier == host_alias).first()
            if existing and existing.provider_type == "INTERNAL_HSM":
                ext_alias = f"{host_alias}_EXT"
            else:
                ext_alias = host_alias

            target_rec = self.db.query(HsmKeyReference).filter(HsmKeyReference.key_identifier == ext_alias).first()
            if target_rec:
                target_rec.encrypted_key_block = fmt["token"]
                target_rec.hsm_key_reference = fmt["token"]
                target_rec.kvc = verified_kcv
                target_rec.lmk_check_value = lmk_check_val
                target_rec.thales_key_type_code = meta["code"]
                target_rec.key_scheme = fmt["scheme"]
                target_rec.provider_type = "EXTERNAL_HSM"
                target_rec.clear_key_hex = None
                target_rec.key_status = "ACTIVE"
            else:
                target_rec = HsmKeyReference(
                    key_name=rk.get("key_label") or f"External {logical_type}",
                    key_type=logical_type,
                    key_usage=meta["usage"],
                    key_identifier=ext_alias,
                    kvc=verified_kcv,
                    algorithm="3DES_2KEY" if fmt["key_length_bits"] == 128 else "3DES_3KEY",
                    key_length=fmt["key_length_bits"],
                    hsm_key_reference=fmt["token"],
                    encrypted_key_block=fmt["token"],
                    clear_key_hex=None,  # NEVER store clear key for External Soft-HSM
                    provider_type="EXTERNAL_HSM",
                    thales_key_type_code=meta["code"],
                    key_scheme=fmt["scheme"],
                    key_version=1,
                    lmk_id="00",
                    lmk_check_value=lmk_check_val,
                    key_status="ACTIVE",
                )
                self.db.add(target_rec)
            synced.append(ext_alias)

        self.db.commit()
        return {
            "status": "SYNCED",
            "lmk_check_value": lmk_check_val,
            "synced_key_aliases": synced,
            "count": len(synced),
        }

    def generate_key_via_soft_hsm_a0(
        self,
        payload: Dict[str, Any],
        current_user: str = "admin",
    ) -> Dict[str, Any]:
        """
        Executes Thales Command A0 on the External Soft-HSM to generate a new key under LMK
        (Mode 0) or under LMK + ZMK/TMK export (Mode 1).
        Inspects the A1 response format, verifies no clear key is stored, and records the
        LMK-encrypted key block in `hsm_key_references`.
        """
        lmk_status = self.get_lmk_and_provider_status()
        if not lmk_status.get("online"):
            raise ConnectionError("External Soft-HSM is unreachable; cannot execute A0 key generation.")
        live_lmk_kcv = lmk_status["lmk_check_value"]

        alias = payload["key_identifier"].strip()
        existing = self.db.query(HsmKeyReference).filter(HsmKeyReference.key_identifier == alias).first()
        if existing:
            raise ValueError(f"Key alias '{alias}' already exists. Use key rotation to create a new version.")

        logical_type = payload.get("key_type", "ZPK").upper().strip()
        meta = resolve_thales_key_meta(logical_type, payload.get("thales_key_type_code"))
        scheme_lmk = (payload.get("key_scheme") or "U").upper().strip()
        mode = str(payload.get("mode") or "0").upper().strip()
        lmk_id = (payload.get("lmk_id") or "00").zfill(2)

        cmd_body = f"{mode}{meta['code']}{scheme_lmk}"
        zmk_export_alias = payload.get("export_zmk_key_identifier")
        if mode in ("1", "B"):
            if not zmk_export_alias:
                raise ValueError("Mode '1' (Generate & Export) requires `export_zmk_key_identifier`.")
            zmk_rec = self.resolve_external_key_record(zmk_export_alias, live_lmk_kcv)
            zmk_flag = ";1" if payload.get("is_tmk_export") else ";0"
            exp_scheme = (payload.get("export_scheme") or "U").upper().strip()
            cmd_body += f"{zmk_flag}{zmk_rec.encrypted_key_block}{exp_scheme}"

        if lmk_id != "00":
            cmd_body += f"%{lmk_id}"

        raw_cmd = f"0000A0{cmd_body}"
        t0 = time.perf_counter()
        tx = self.bridge.execute_command(raw_cmd, synthetic_mode=False)
        dur_ms = max(1, int((time.perf_counter() - t0) * 1000))

        status_code = tx.get("status_code", "15")
        raw_resp = tx.get("raw_response", "")
        if status_code != "00":
            self._record_hsm_op("KEY_GENERATE_A0", None, raw_cmd, raw_resp, "DECLINED", status_code, dur_ms)
            raise ValueError(f"Soft-HSM rejected A0 command with Error {status_code}: {tx.get('status_description')}")

        # Parse A1 response: 0000A100 + <Key_Under_LMK> + [<Key_Under_ZMK>] + <6H_KCV>
        body_after_status = raw_resp[8:]
        kcv = body_after_status[-6:].upper()
        keys_portion = body_after_status[:-6]

        # Extract LMK key token from parsed_response or token reader
        lmk_token = ""
        zmk_export_token = None
        for item in tx.get("parsed_response", []):
            if item.get("tag") == "Key under LMK":
                lmk_token = item.get("value", "")
            elif item.get("tag") == "Key under ZMK/TMK":
                zmk_export_token = item.get("value", "")

        if not lmk_token:
            lmk_token = keys_portion

        token_inspection = inspect_key_token_format(lmk_token)
        if not token_inspection["valid"]:
            raise ValueError(f"Returned A1 key failed format safety inspection: {token_inspection.get('reason')}")

        key_rec = HsmKeyReference(
            key_name=payload.get("key_name") or f"External {logical_type} ({alias})",
            key_type=logical_type,
            key_usage=payload.get("key_usage") or meta["usage"],
            key_identifier=alias,
            kvc=kcv,
            algorithm="3DES_3KEY" if token_inspection["key_length_bits"] == 192 else "3DES_2KEY",
            key_length=token_inspection["key_length_bits"],
            hsm_key_reference=token_inspection["token"],
            encrypted_key_block=token_inspection["token"],
            clear_key_hex=None,  # Mandatory: never store clear key
            provider_type="EXTERNAL_HSM",
            thales_key_type_code=meta["code"],
            key_scheme=token_inspection["scheme"],
            key_version=1,
            lmk_id=lmk_id,
            lmk_check_value=live_lmk_kcv,
            exportable=True,
            institution_id=payload.get("institution_id"),
            processing_system_id=payload.get("processing_system_id"),
            key_status="ACTIVE",
        )
        self.db.add(key_rec)
        self.db.flush()

        self._record_hsm_op("KEY_GENERATE_A0", key_rec, raw_cmd, raw_resp, "APPROVED", "00", dur_ms)
        record_audit(
            self.db,
            "HSM_KEY",
            key_rec.id,
            "EXTERNAL_A0_GENERATE",
            performed_by=current_user,
            after_state=serialize_entity(key_rec),
            change_summary=f"Generated {logical_type} key '{alias}' on External Soft-HSM via A0 (KCV: {kcv}, LMK: {live_lmk_kcv[:6]})",
        )
        self.db.commit()
        self.db.refresh(key_rec)

        return {
            "status": "GENERATED",
            "command_executed": "A0",
            "hsm_response_code": "A1",
            "error_code": "00",
            "raw_request": raw_cmd,
            "raw_response": raw_resp,
            "key": self.serialize_key_safe(key_rec),
            "token_inspection": token_inspection,
            "exported_key_under_zmk": zmk_export_token,
        }

    def import_key_via_soft_hsm_a6(
        self,
        payload: Dict[str, Any],
        current_user: str = "admin",
    ) -> Dict[str, Any]:
        """
        Executes Thales Command A6 on the External Soft-HSM to import a working key encrypted
        under a ZMK or TMK and re-encrypt it under the Soft-HSM's LMK variant.
        """
        lmk_status = self.get_lmk_and_provider_status()
        if not lmk_status.get("online"):
            raise ConnectionError("External Soft-HSM is unreachable; cannot execute A6 key import.")
        live_lmk_kcv = lmk_status["lmk_check_value"]

        zmk_rec = self.resolve_external_key_record(payload["zmk_key_identifier"], live_lmk_kcv)
        logical_type = payload.get("key_type", "ZPK").upper().strip()
        meta = resolve_thales_key_meta(logical_type, payload.get("thales_key_type_code"))
        scheme_lmk = (payload.get("key_scheme_lmk") or "U").upper().strip()
        enc_under_zmk = payload["encrypted_key_under_zmk"].strip().upper()
        if enc_under_zmk[0] not in ("U", "T", "Z", "X", "Y", "S", "R") and len(enc_under_zmk) == 32:
            enc_under_zmk = f"U{enc_under_zmk}"

        tmk_flag = ";1" if payload.get("is_tmk") else ""
        raw_cmd = f"0000A6{meta['code']}{tmk_flag}{zmk_rec.encrypted_key_block}{enc_under_zmk}{scheme_lmk}"

        t0 = time.perf_counter()
        tx = self.bridge.execute_command(raw_cmd, synthetic_mode=False)
        dur_ms = max(1, int((time.perf_counter() - t0) * 1000))

        status_code = tx.get("status_code", "15")
        raw_resp = tx.get("raw_response", "")
        if status_code != "00":
            self._record_hsm_op("KEY_IMPORT_A6", zmk_rec, raw_cmd, raw_resp, "DECLINED", status_code, dur_ms)
            raise ValueError(f"Soft-HSM rejected A6 import with Error {status_code}: {tx.get('status_description')}")

        body_after_status = raw_resp[8:]
        kcv = body_after_status[-6:].upper()
        lmk_token = body_after_status[:-6]
        token_inspection = inspect_key_token_format(lmk_token)
        if not token_inspection["valid"]:
            raise ValueError(f"Imported A7 key token failed format inspection: {token_inspection.get('reason')}")

        alias = payload["key_identifier"].strip()
        key_rec = self.db.query(HsmKeyReference).filter(HsmKeyReference.key_identifier == alias).first()
        if key_rec:
            if key_rec.provider_type != "EXTERNAL_HSM":
                raise ValueError(f"Key alias '{alias}' belongs to INTERNAL_HSM and cannot be overwritten by EXTERNAL_HSM.")
            key_rec.encrypted_key_block = token_inspection["token"]
            key_rec.hsm_key_reference = token_inspection["token"]
            key_rec.kvc = kcv
            key_rec.key_scheme = token_inspection["scheme"]
            key_rec.thales_key_type_code = meta["code"]
            key_rec.lmk_check_value = live_lmk_kcv
            key_rec.key_version = (key_rec.key_version or 1) + 1
            key_rec.clear_key_hex = None
            key_rec.parent_key_id = zmk_rec.id
        else:
            key_rec = HsmKeyReference(
                key_name=payload.get("key_name") or f"Imported {logical_type} ({alias})",
                key_type=logical_type,
                key_usage=payload.get("key_usage") or meta["usage"],
                key_identifier=alias,
                kvc=kcv,
                algorithm="3DES_3KEY" if token_inspection["key_length_bits"] == 192 else "3DES_2KEY",
                key_length=token_inspection["key_length_bits"],
                hsm_key_reference=token_inspection["token"],
                encrypted_key_block=token_inspection["token"],
                clear_key_hex=None,
                parent_key_id=zmk_rec.id,
                provider_type="EXTERNAL_HSM",
                thales_key_type_code=meta["code"],
                key_scheme=token_inspection["scheme"],
                key_version=1,
                lmk_id=payload.get("lmk_id") or "00",
                lmk_check_value=live_lmk_kcv,
                institution_id=payload.get("institution_id"),
                processing_system_id=payload.get("processing_system_id"),
                key_status="ACTIVE",
            )
            self.db.add(key_rec)
            self.db.flush()

        self._record_hsm_op("KEY_IMPORT_A6", key_rec, raw_cmd, raw_resp, "APPROVED", "00", dur_ms)
        record_audit(
            self.db,
            "HSM_KEY",
            key_rec.id,
            "EXTERNAL_A6_IMPORT",
            performed_by=current_user,
            after_state=serialize_entity(key_rec),
            change_summary=f"Imported key '{alias}' under ZMK '{zmk_rec.key_identifier}' via Soft-HSM A6 (KCV: {kcv})",
        )
        self.db.commit()
        self.db.refresh(key_rec)

        return {
            "status": "IMPORTED",
            "command_executed": "A6",
            "hsm_response_code": "A7",
            "error_code": "00",
            "raw_request": raw_cmd,
            "raw_response": raw_resp,
            "key": self.serialize_key_safe(key_rec),
            "token_inspection": token_inspection,
        }

    def export_key_via_soft_hsm_a8(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes Thales Command A8 on the External Soft-HSM to translate a key from
        LMK encryption to ZMK/TMK encryption for external distribution.
        """
        lmk_status = self.get_lmk_and_provider_status()
        if not lmk_status.get("online"):
            raise ConnectionError("External Soft-HSM is unreachable; cannot execute A8 key export.")
        live_lmk_kcv = lmk_status["lmk_check_value"]

        target_rec = self.resolve_external_key_record(payload["key_identifier"], live_lmk_kcv)
        zmk_rec = self.resolve_external_key_record(payload["zmk_key_identifier"], live_lmk_kcv)

        meta = resolve_thales_key_meta(target_rec.key_type, target_rec.thales_key_type_code)
        out_scheme = (payload.get("export_scheme") or "U").upper().strip()
        tmk_flag = ";1" if payload.get("is_tmk") else ""

        raw_cmd = f"0000A8{meta['code']}{tmk_flag}{zmk_rec.encrypted_key_block}{target_rec.encrypted_key_block}{out_scheme}"
        t0 = time.perf_counter()
        tx = self.bridge.execute_command(raw_cmd, synthetic_mode=False)
        dur_ms = max(1, int((time.perf_counter() - t0) * 1000))

        status_code = tx.get("status_code", "15")
        raw_resp = tx.get("raw_response", "")
        if status_code != "00":
            self._record_hsm_op("KEY_EXPORT_A8", target_rec, raw_cmd, raw_resp, "DECLINED", status_code, dur_ms)
            raise ValueError(f"Soft-HSM rejected A8 export with Error {status_code}: {tx.get('status_description')}")

        body_after_status = raw_resp[8:]
        kcv = body_after_status[-6:].upper()
        exported_cryptogram = body_after_status[:-6]

        self._record_hsm_op("KEY_EXPORT_A8", target_rec, raw_cmd, raw_resp, "APPROVED", "00", dur_ms)
        self.db.commit()

        return {
            "status": "EXPORTED",
            "command_executed": "A8",
            "hsm_response_code": "A9",
            "error_code": "00",
            "key_identifier": target_rec.key_identifier,
            "zmk_key_identifier": zmk_rec.key_identifier,
            "key_under_zmk": exported_cryptogram,
            "kcv": kcv,
            "raw_request": raw_cmd,
            "raw_response": raw_resp,
        }

    def verify_key_kcv_via_soft_hsm_bu(self, key_identifier: str) -> Dict[str, Any]:
        """
        Executes Thales Command BU on the External Soft-HSM to verify the LMK key block's
        integrity, odd parity, and Key Check Value (KCV).
        """
        lmk_status = self.get_lmk_and_provider_status()
        if not lmk_status.get("online"):
            raise ConnectionError("External Soft-HSM is unreachable; cannot execute BU KCV check.")
        live_lmk_kcv = lmk_status["lmk_check_value"]

        key_rec = self.resolve_external_key_record(key_identifier, live_lmk_kcv)
        meta = resolve_thales_key_meta(key_rec.key_type, key_rec.thales_key_type_code)
        fmt = inspect_key_token_format(key_rec.encrypted_key_block or key_rec.hsm_key_reference)
        if not fmt["valid"]:
            raise ValueError(f"Stored key token for '{key_identifier}' is invalid: {fmt.get('reason')}")

        raw_cmd = f"0000BU{meta['bu_code']}{fmt['len_flag_bu']}{fmt['token']}"
        t0 = time.perf_counter()
        tx = self.bridge.execute_command(raw_cmd, synthetic_mode=False)
        dur_ms = max(1, int((time.perf_counter() - t0) * 1000))

        status_code = tx.get("status_code", "15")
        raw_resp = tx.get("raw_response", "")
        if status_code != "00":
            self._record_hsm_op("KEY_KCV_BU", key_rec, raw_cmd, raw_resp, "DECLINED", status_code, dur_ms)
            raise ValueError(f"Soft-HSM BU KCV check failed with Error {status_code}")

        kcv16 = raw_resp[8:24]
        kcv6 = kcv16[:6].upper()
        kcv_matched = kcv6 == (key_rec.kvc or "").upper()[:6]

        self._record_hsm_op("KEY_KCV_BU", key_rec, raw_cmd, raw_resp, "APPROVED", "00", dur_ms)
        self.db.commit()

        return {
            "status": "VERIFIED" if kcv_matched else "KCV_MISMATCH",
            "command_executed": "BU",
            "hsm_response_code": "BV",
            "error_code": "00",
            "key_identifier": key_rec.key_identifier,
            "stored_kvc": key_rec.kvc,
            "calculated_kvc": kcv6,
            "calculated_kvc_16h": kcv16,
            "kcv_matched": kcv_matched,
            "lmk_check_value": live_lmk_kcv,
            "raw_request": raw_cmd,
            "raw_response": raw_resp,
        }

    def rotate_external_key(
        self,
        key_identifier: str,
        new_scheme: Optional[str] = None,
        export_zmk_key_identifier: Optional[str] = None,
        current_user: str = "admin",
    ) -> Dict[str, Any]:
        """
        Rotates an active External Soft-HSM key by executing A0 on the Soft-HSM to generate
        a fresh cryptogram under the active LMK domain, archiving the prior version as
        `SUPERSEDED_<key_id>_V<ver>`, and updating the primary alias to the new version.
        """
        lmk_status = self.get_lmk_and_provider_status()
        if not lmk_status.get("online"):
            raise ConnectionError("External Soft-HSM is unreachable; cannot rotate key.")
        live_lmk_kcv = lmk_status["lmk_check_value"]

        curr_rec = self.resolve_external_key_record(key_identifier, expected_lmk_kcv=None)
        old_ver = curr_rec.key_version or 1
        scheme = (new_scheme or curr_rec.key_scheme or "U").upper().strip()
        meta = resolve_thales_key_meta(curr_rec.key_type, curr_rec.thales_key_type_code)

        mode = "1" if export_zmk_key_identifier else "0"
        cmd_body = f"{mode}{meta['code']}{scheme}"
        if export_zmk_key_identifier:
            zmk_rec = self.resolve_external_key_record(export_zmk_key_identifier, live_lmk_kcv)
            cmd_body += f";0{zmk_rec.encrypted_key_block}U"

        raw_cmd = f"0000A0{cmd_body}"
        t0 = time.perf_counter()
        tx = self.bridge.execute_command(raw_cmd, synthetic_mode=False)
        dur_ms = max(1, int((time.perf_counter() - t0) * 1000))

        status_code = tx.get("status_code", "15")
        raw_resp = tx.get("raw_response", "")
        if status_code != "00":
            raise ValueError(f"Soft-HSM A0 key rotation failed with Error {status_code}")

        body_after_status = raw_resp[8:]
        new_kcv = body_after_status[-6:].upper()
        lmk_token = ""
        zmk_export_token = None
        for item in tx.get("parsed_response", []):
            if item.get("tag") == "Key under LMK":
                lmk_token = item.get("value", "")
            elif item.get("tag") == "Key under ZMK/TMK":
                zmk_export_token = item.get("value", "")
        if not lmk_token:
            lmk_token = body_after_status[:-6]

        token_inspection = inspect_key_token_format(lmk_token)
        if not token_inspection["valid"]:
            raise ValueError(f"Rotated key token failed format inspection: {token_inspection.get('reason')}")

        # Archive old version record for audit lineage
        archive_alias = f"{curr_rec.key_identifier}_V{old_ver}_{curr_rec.kvc}"
        archived_copy = HsmKeyReference(
            key_name=f"{curr_rec.key_name} (Archived v{old_ver})",
            key_type=curr_rec.key_type,
            key_usage=curr_rec.key_usage,
            key_identifier=archive_alias,
            kvc=curr_rec.kvc,
            algorithm=curr_rec.algorithm,
            key_length=curr_rec.key_length,
            hsm_key_reference=curr_rec.hsm_key_reference,
            encrypted_key_block=curr_rec.encrypted_key_block,
            clear_key_hex=None,
            provider_type="EXTERNAL_HSM",
            thales_key_type_code=curr_rec.thales_key_type_code,
            key_scheme=curr_rec.key_scheme,
            key_version=old_ver,
            lmk_id=curr_rec.lmk_id,
            lmk_check_value=curr_rec.lmk_check_value,
            institution_id=curr_rec.institution_id,
            processing_system_id=curr_rec.processing_system_id,
            key_status="SUPERSEDED",
        )
        self.db.add(archived_copy)
        self.db.flush()

        before = serialize_entity(curr_rec)
        curr_rec.encrypted_key_block = token_inspection["token"]
        curr_rec.hsm_key_reference = token_inspection["token"]
        curr_rec.kvc = new_kcv
        curr_rec.key_scheme = token_inspection["scheme"]
        curr_rec.key_version = old_ver + 1
        curr_rec.lmk_check_value = live_lmk_kcv
        curr_rec.rotated_from_key_id = archived_copy.id
        curr_rec.clear_key_hex = None
        curr_rec.key_status = "ACTIVE"
        after = serialize_entity(curr_rec)

        self._record_hsm_op("KEY_ROTATE_A0", curr_rec, raw_cmd, raw_resp, "APPROVED", "00", dur_ms)
        record_audit(
            self.db,
            "HSM_KEY",
            curr_rec.id,
            "KEY_ROTATION",
            performed_by=current_user,
            before_state=before,
            after_state=after,
            change_summary=f"Rotated External Soft-HSM key '{curr_rec.key_identifier}' v{old_ver} -> v{curr_rec.key_version} (New KCV: {new_kcv})",
        )
        self.db.commit()
        self.db.refresh(curr_rec)

        return {
            "status": "ROTATED",
            "command_executed": "A0",
            "previous_version": old_ver,
            " archived_key_identifier": archive_alias,
            "new_version": curr_rec.key_version,
            "key": self.serialize_key_safe(curr_rec),
            "exported_key_under_zmk": zmk_export_token,
        }

    def resolve_external_key_record(
        self,
        key_identifier: str,
        expected_lmk_kcv: Optional[str] = None,
    ) -> HsmKeyReference:
        """
        Resolves an External Soft-HSM key by alias, strictly enforcing:
          1. Provider isolation (must be `EXTERNAL_HSM`, never silently falling back to `INTERNAL_HSM`)
          2. Active key status (`ACTIVE`)
          3. LMK domain compatibility (`lmk_check_value` must match the live Soft-HSM LMK domain)
          4. Valid LMK-encrypted key block (`U...`, `T...`, `S...`, `Z...`)
        """
        candidates = [key_identifier, f"{key_identifier}_EXT"]
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
            internal_exists = (
                self.db.query(HsmKeyReference)
                .filter(
                    HsmKeyReference.key_identifier == key_identifier,
                    HsmKeyReference.provider_type == "INTERNAL_HSM",
                )
                .first()
            )
            if internal_exists:
                raise ValueError(
                    f"Provider Isolation Violation: Key '{key_identifier}' belongs to INTERNAL_HSM and "
                    f"cannot be used when EXTERNAL_HSM is active. Sync or generate an External Soft-HSM key."
                )
            raise ValueError(f"External Soft-HSM key '{key_identifier}' not found in Host inventory.")

        if rec.key_status != "ACTIVE":
            raise ValueError(f"External Soft-HSM key '{rec.key_identifier}' has status '{rec.key_status}' and cannot be used.")

        if expected_lmk_kcv and rec.lmk_check_value and rec.lmk_check_value != expected_lmk_kcv:
            raise ValueError(
                f"LMK Domain Mismatch: Key '{rec.key_identifier}' is protected under LMK domain "
                f"'{rec.lmk_check_value[:6]}', but the active External Soft-HSM LMK domain is '{expected_lmk_kcv[:6]}'. "
                f"Cross-domain key usage without translation is prohibited."
            )

        token = rec.encrypted_key_block or rec.hsm_key_reference
        fmt = inspect_key_token_format(token)
        if not fmt["valid"]:
            raise ValueError(
                f"Key '{rec.key_identifier}' does not contain a valid Soft-HSM LMK key block: {fmt.get('reason')}"
            )
        return rec

    @staticmethod
    def serialize_key_safe(k: HsmKeyReference) -> Dict[str, Any]:
        """
        Serializes an HsmKeyReference for API/UI consumption while guaranteeing
        `clear_key_hex` is NEVER exposed.
        """
        tok = k.encrypted_key_block or k.hsm_key_reference or ""
        masked_block = f"{tok[:7]}...{tok[-6:]}" if len(tok) > 16 else tok
        return {
            "id": k.id,
            "key_identifier": k.key_identifier,
            "key_name": k.key_name,
            "key_type": k.key_type,
            "thales_key_type_code": getattr(k, "thales_key_type_code", "001"),
            "key_usage": k.key_usage,
            "key_scheme": getattr(k, "key_scheme", "U"),
            "key_version": getattr(k, "key_version", 1),
            "key_status": k.key_status,
            "kvc": k.kvc,
            "algorithm": k.algorithm,
            "key_length": k.key_length,
            "provider_type": getattr(k, "provider_type", "INTERNAL_HSM"),
            "lmk_id": getattr(k, "lmk_id", "00"),
            "lmk_check_value": getattr(k, "lmk_check_value", None),
            "encrypted_key_block": tok if getattr(k, "provider_type", "") == "EXTERNAL_HSM" else k.hsm_key_reference,
            "masked_key_block": masked_block,
            "exportable": getattr(k, "exportable", True),
            "rotated_from_key_id": getattr(k, "rotated_from_key_id", None),
            "institution_id": k.institution_id,
            "processing_system_id": k.processing_system_id,
            "created_at": k.created_at.isoformat() if getattr(k, "created_at", None) else None,
        }

    def _record_hsm_op(
        self,
        op_type: str,
        key_rec: Optional[HsmKeyReference],
        raw_req: str,
        raw_resp: str,
        status: str,
        err_code: str,
        dur_ms: int,
    ) -> None:
        op = HsmOperation(
            operation_type=f"{op_type} (EXTERNAL_HSM)",
            key_reference_id=key_rec.id if key_rec else None,
            request_reference=f"EXT-{int(time.time() * 1000)}",
            sanitized_request={"raw_command": raw_req, "provider": "EXTERNAL_HSM"},
            sanitized_response={"raw_response": raw_resp, "provider": "EXTERNAL_HSM"},
            response_status=status,
            error_code=err_code,
            duration_ms=dur_ms,
        )
        self.db.add(op)
        self.db.flush()
'''
    service_path.write_text(code, encoding="utf-8")
    print(f"[OK] Created {service_path}")


if __name__ == "__main__":
    print("=" * 76)
    print(" Installing LMK-Centric Key Management — PART 1 (Models, Schemas & Service)")
    print("=" * 76)
    patch_models()
    patch_schemas()
    write_lmk_service()
    print("=" * 76)
    print(" Part 1 complete. Run Part 2 next.")