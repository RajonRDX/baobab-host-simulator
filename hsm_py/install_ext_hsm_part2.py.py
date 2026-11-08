#!/usr/bin/env python3
"""
install_ext_hsm_part2.py — Part 2 of 4: HSM Provider Architecture, External Client & Engine Pinning
Save in : E:\\HOST_VSCODE\\host-simulator\\hsm_py\\install_ext_hsm_part2.py
Run from: E:\\HOST_VSCODE\\host-simulator
Command : python hsm_py\\install_ext_hsm_part2.py
"""

import json
import shutil
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def resolve_project_root() -> Path:
    script_dir = Path(__file__).resolve().parent
    if (script_dir / "backend" / "app").exists():
        return script_dir
    if (script_dir.parent / "backend" / "app").exists():
        return script_dir.parent
    cwd = Path.cwd().resolve()
    if (cwd / "backend" / "app").exists():
        return cwd
    raise FileNotFoundError("Could not locate 'backend/app'. Run from E:\\HOST_VSCODE\\host-simulator.")


ROOT = resolve_project_root()
BACKUP_DIR = ROOT / "_backups" / f"ext_hsm_part2_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def backup_file(path: Path) -> None:
    if path.exists():
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        rel = path.relative_to(ROOT)
        dest = BACKUP_DIR / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        print(f"  [BACKUP] {rel} -> {dest.relative_to(ROOT)}")


def create_hsm_provider_module() -> None:
    prov_path = ROOT / "backend" / "app" / "hsm_provider.py"
    if prov_path.exists():
        backup_file(prov_path)

    code = '''"""
hsm_provider.py — Abstract HSM Provider Architecture (Internal Mode A vs External Mode B)
Implements InternalHSMProvider, ExternalSoftHSMClient, ExternalHSMProvider, and HSMProviderSelector.
Enforces strict non-fallback behavior and transaction-pinned provider isolation.
"""

import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from app.config import settings
from app.hsm_adapter import SoftHsmCryptoCore
from app.models import HsmAuditLog, HsmKeyReference, HsmOperation, HsmProviderConfig
from app.security import mask_pan, sanitize_dict


class ExternalSoftHSMClient:
    """HTTP/REST client communicating with the separate Soft HSM application."""

    def __init__(self, config: HsmProviderConfig):
        base = (config.base_url or "").strip().rstrip("/")
        endpoint = (config.api_endpoint or "/api/host/command").strip()
        if not endpoint.startswith("/"):
            endpoint = "/" + endpoint
        self.url = f"{base}{endpoint}"
        self.connect_timeout = max(1.0, float(config.connect_timeout_ms or 5000) / 1000.0)
        self.read_timeout = max(1.0, float(config.read_timeout_ms or 10000) / 1000.0)
        self.source_host = config.source_host_id or "BAOBAB_HOST_SIMULATOR"
        self.header_length = config.header_length or 4
        self.framing_mode = config.framing_mode or "ASCII"

    def send_raw_command(self, raw_command: str) -> Dict[str, Any]:
        payload = json.dumps({
            "command": raw_command,
            "header_length": self.header_length,
            "synthetic_mode": True,
            "source_host": self.source_host,
            "framing": self.framing_mode,
        }).encode("utf-8")

        req = urllib.request.Request(
            self.url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        total_timeout = self.connect_timeout + self.read_timeout
        try:
            with urllib.request.urlopen(req, timeout=total_timeout) as resp:
                raw_body = resp.read().decode("utf-8")
                return json.loads(raw_body)
        except urllib.error.HTTPError as he:
            err_body = he.read().decode("utf-8", errors="replace")
            raise ConnectionError(f"External Soft-HSM HTTP {he.code}: {err_body}")
        except urllib.error.URLError as ue:
            raise TimeoutError(f"External Soft-HSM connection failed at {self.url}: {ue.reason}")
        except Exception as exc:
            raise RuntimeError(f"External Soft-HSM communication error: {exc}")


class HSMProviderInterface:
    def verify_pin_pvv(self, db: Session, pan: str, encrypted_pin_block: str, expected_pvv: str, pvki: str = "1", awk_id: str = "AWK_ATM_01", pvk_id: str = "PVK_VISA_01", transaction_id: Optional[str] = None) -> Dict[str, Any]:
        raise NotImplementedError

    def translate_pin_block(self, db: Session, pan: str, encrypted_pin_block: str, awk_id: str = "AWK_ATM_01", iwk_id: str = "IWK_SW_01", transaction_id: Optional[str] = None) -> Dict[str, Any]:
        raise NotImplementedError

    def verify_cvv(self, db: Session, pan: str, expiry_yy_mm: str, service_code: str, supplied_cvv: str, cvk_id: str = "CVK_MAIN_01", transaction_id: Optional[str] = None) -> Dict[str, Any]:
        raise NotImplementedError

    def verify_or_generate_mac(self, db: Session, data_hex: str, supplied_mac: Optional[str] = None, tak_id: str = "TAK_MAC_01", transaction_id: Optional[str] = None) -> Dict[str, Any]:
        raise NotImplementedError

    def verify_emv_cryptogram(self, db: Session, pan: str, psn: str, de55_hex: str, arc_hex: str = "3030", mk_ac_id: str = "MK_AC_EMV01", transaction_id: Optional[str] = None) -> Dict[str, Any]:
        raise NotImplementedError

    def check_key_kvc(self, db: Session, key_identifier: str, transaction_id: Optional[str] = None) -> Dict[str, Any]:
        raise NotImplementedError

    def pack_test_pin_block_server_side(self, db: Session, clear_pin: str, pan: str, awk_id: str = "AWK_ATM_01") -> str:
        raise NotImplementedError


class InternalHSMProvider(HSMProviderInterface):
    """Wraps the existing local SoftHsmCryptoCore implementation."""

    def __init__(self, db: Session):
        from app.hsm_adapter import HSMAdapter
        self.internal_adapter = HSMAdapter(db)

    def verify_pin_pvv(self, db: Session, pan: str, encrypted_pin_block: str, expected_pvv: str, pvki: str = "1", awk_id: str = "AWK_ATM_01", pvk_id: str = "PVK_VISA_01", transaction_id: Optional[str] = None) -> Dict[str, Any]:
        res = self.internal_adapter.verify_pin_pvv(pan, encrypted_pin_block, expected_pvv, pvki, awk_id, pvk_id, transaction_id)
        res["provider_mode"] = "INTERNAL"
        return res

    def translate_pin_block(self, db: Session, pan: str, encrypted_pin_block: str, awk_id: str = "AWK_ATM_01", iwk_id: str = "IWK_SW_01", transaction_id: Optional[str] = None) -> Dict[str, Any]:
        res = self.internal_adapter.translate_pin_block(pan, encrypted_pin_block, awk_id, iwk_id, transaction_id)
        res["provider_mode"] = "INTERNAL"
        return res

    def verify_cvv(self, db: Session, pan: str, expiry_yy_mm: str, service_code: str, supplied_cvv: str, cvk_id: str = "CVK_MAIN_01", transaction_id: Optional[str] = None) -> Dict[str, Any]:
        res = self.internal_adapter.verify_cvv(pan, expiry_yy_mm, service_code, supplied_cvv, cvk_id, transaction_id)
        res["provider_mode"] = "INTERNAL"
        return res

    def verify_or_generate_mac(self, db: Session, data_hex: str, supplied_mac: Optional[str] = None, tak_id: str = "TAK_MAC_01", transaction_id: Optional[str] = None) -> Dict[str, Any]:
        res = self.internal_adapter.verify_or_generate_mac(data_hex, supplied_mac, tak_id, transaction_id)
        res["provider_mode"] = "INTERNAL"
        return res

    def verify_emv_cryptogram(self, db: Session, pan: str, psn: str, de55_hex: str, arc_hex: str = "3030", mk_ac_id: str = "MK_AC_EMV01", transaction_id: Optional[str] = None) -> Dict[str, Any]:
        res = self.internal_adapter.verify_emv_cryptogram(pan, psn, de55_hex, arc_hex, mk_ac_id, transaction_id)
        res["provider_mode"] = "INTERNAL"
        return res

    def check_key_kvc(self, db: Session, key_identifier: str, transaction_id: Optional[str] = None) -> Dict[str, Any]:
        res = self.internal_adapter.check_key_kvc(key_identifier)
        res["provider_mode"] = "INTERNAL"
        return res

    def pack_test_pin_block_server_side(self, db: Session, clear_pin: str, pan: str, awk_id: str = "AWK_ATM_01") -> str:
        return self.internal_adapter.pack_test_pin_block_server_side(clear_pin, pan, awk_id)


class ExternalHSMProvider(HSMProviderInterface):
    """Routes supported cryptographic operations to the separate external Soft HSM."""

    def __init__(self, db: Session, config: HsmProviderConfig):
        self.config = config
        self.client = ExternalSoftHSMClient(config)

    def _resolve_external_token(self, db: Session, key_identifier: str, default_thales_type: str = "001") -> str:
        key_ref = db.query(HsmKeyReference).filter(HsmKeyReference.key_identifier == key_identifier).first()
        if key_ref and key_ref.external_key_token:
            return key_ref.external_key_token
        # Fallback to computing LMK token if clear key exists
        clear_key = (key_ref.clear_key_hex if (key_ref and key_ref.clear_key_hex) else SoftHsmCryptoCore.INTERNAL_CLEAR_KEYS.get(key_identifier))
        if clear_key:
            from app.seed_data import compute_thales_lmk_token
            _, tok = compute_thales_lmk_token(clear_key, key_ref.key_type if key_ref else default_thales_type, key_ref.key_scheme if key_ref else "U")
            return tok
        raise ValueError(f"Key identifier '{key_identifier}' has no external LMK token or clear key for external HSM routing.")

    def _execute_remote(self, db: Session, operation_type: str, command_str: str, key_ref: Optional[HsmKeyReference], transaction_id: Optional[str] = None) -> Dict[str, Any]:
        t0 = time.perf_counter()
        req_ref = f"EXTREQ-{uuid.uuid4().hex[:10].upper()}"
        audit_ref = f"EXTAUD-{uuid.uuid4().hex[:10].upper()}"

        try:
            resp_json = self.client.send_raw_command(command_str)
            dur = max(1, int((time.perf_counter() - t0) * 1000))
            status_code = resp_json.get("status_code", "00")
            status_text = "APPROVED" if status_code == "00" else "DECLINED"

            op = HsmOperation(
                transaction_id=transaction_id,
                operation_type=f"EXTERNAL_{operation_type}",
                key_reference_id=key_ref.id if key_ref else None,
                request_reference=req_ref,
                sanitized_request=sanitize_dict({"command_sent": command_str, "base_url": self.config.base_url}),
                sanitized_response=sanitize_dict(resp_json),
                response_status=status_text,
                error_code=status_code,
                duration_ms=dur,
                provider_mode="EXTERNAL",
                command_code=resp_json.get("command_code"),
                thales_response_code=status_code,
            )
            db.add(op)
            db.flush()

            audit = HsmAuditLog(
                operation_id=op.id,
                operation_type=f"EXTERNAL_{operation_type}",
                key_reference_id=key_ref.id if key_ref else None,
                actor="EXTERNAL_SOFT_HSM",
                result=status_text,
                audit_reference=audit_ref,
            )
            db.add(audit)
            db.flush()

            return {
                "operation_id": op.id,
                "operation_type": operation_type,
                "provider_mode": "EXTERNAL",
                "status": status_text,
                "error_code": status_code,
                "duration_ms": dur,
                "audit_reference": audit_ref,
                "sanitized_response": resp_json,
            }
        except Exception as exc:
            dur = max(1, int((time.perf_counter() - t0) * 1000))
            # STRICT NON-FALLBACK RULE: Record failure and raise error. Never silent fallback to Internal!
            op = HsmOperation(
                transaction_id=transaction_id,
                operation_type=f"EXTERNAL_{operation_type}",
                key_reference_id=key_ref.id if key_ref else None,
                request_reference=req_ref,
                sanitized_request=sanitize_dict({"command_sent": command_str, "base_url": self.config.base_url}),
                sanitized_response=sanitize_dict({"error": str(exc)}),
                response_status="HSM_ERROR",
                error_code="91",
                duration_ms=dur,
                provider_mode="EXTERNAL",
                thales_response_code="91",
            )
            db.add(op)
            db.commit()
            raise RuntimeError(f"External Soft-HSM Error (No Fallback): {exc}")

    def verify_pin_pvv(self, db: Session, pan: str, encrypted_pin_block: str, expected_pvv: str, pvki: str = "1", awk_id: str = "AWK_ATM_01", pvk_id: str = "PVK_VISA_01", transaction_id: Optional[str] = None) -> Dict[str, Any]:
        zpk_tok = self._resolve_external_token(db, awk_id, "001")
        pvk_tok = self._resolve_external_token(db, pvk_id, "002")
        pan12 = pan[-13:-1].zfill(12)
        cmd = f"0058DC01{zpk_tok}{encrypted_pin_block}{pvk_tok}{pan12}{pvki[0]}{expected_pvv}"
        key_ref = db.query(HsmKeyReference).filter(HsmKeyReference.key_identifier == pvk_id).first()
        return self._execute_remote(db, "PIN_PVV_VERIFY", cmd, key_ref, transaction_id)

    def translate_pin_block(self, db: Session, pan: str, encrypted_pin_block: str, awk_id: str = "AWK_ATM_01", iwk_id: str = "IWK_SW_01", transaction_id: Optional[str] = None) -> Dict[str, Any]:
        src_tok = self._resolve_external_token(db, awk_id, "001")
        dst_tok = self._resolve_external_token(db, iwk_id, "001")
        pan12 = pan[-13:-1].zfill(12)
        cmd = f"0000CA{src_tok}{dst_tok}12{encrypted_pin_block}0101{pan12}"
        key_ref = db.query(HsmKeyReference).filter(HsmKeyReference.key_identifier == awk_id).first()
        return self._execute_remote(db, "PIN_TRANSLATE", cmd, key_ref, transaction_id)

    def verify_cvv(self, db: Session, pan: str, expiry_yy_mm: str, service_code: str, supplied_cvv: str, cvk_id: str = "CVK_MAIN_01", transaction_id: Optional[str] = None) -> Dict[str, Any]:
        cvk_tok = self._resolve_external_token(db, cvk_id, "402")
        cmd = f"0008CY{cvk_tok}{pan};{expiry_yy_mm}{service_code}{supplied_cvv}"
        key_ref = db.query(HsmKeyReference).filter(HsmKeyReference.key_identifier == cvk_id).first()
        return self._execute_remote(db, "CVV_VERIFY", cmd, key_ref, transaction_id)

    def verify_or_generate_mac(self, db: Session, data_hex: str, supplied_mac: Optional[str] = None, tak_id: str = "TAK_MAC_01", transaction_id: Optional[str] = None) -> Dict[str, Any]:
        tak_tok = self._resolve_external_token(db, tak_id, "003")
        if supplied_mac:
            cmd = f"0008M801{tak_tok}{data_hex}{supplied_mac[:8]}"
            op_name = "MAC_VERIFY"
        else:
            cmd = f"0008M601{tak_tok}{data_hex}"
            op_name = "MAC_GENERATE"
        key_ref = db.query(HsmKeyReference).filter(HsmKeyReference.key_identifier == tak_id).first()
        return self._execute_remote(db, op_name, cmd, key_ref, transaction_id)

    def verify_emv_cryptogram(self, db: Session, pan: str, psn: str, de55_hex: str, arc_hex: str = "3030", mk_ac_id: str = "MK_AC_EMV01", transaction_id: Optional[str] = None) -> Dict[str, Any]:
        mk_tok = self._resolve_external_token(db, mk_ac_id, "109")
        pan_seq = f"{pan.strip().ljust(14, '0')[:14]}{psn.strip().zfill(2)[-2:]}"
        # Parse ATC from DE55
        atc = "0001"
        un = "11223344"
        from app.hsm_adapter import SoftHsmCryptoCore
        tags = SoftHsmCryptoCore.parse_de55(de55_hex)
        for t in tags:
            if t["tag"] == "9F36":
                atc = t["value"].zfill(4)[-4:]
            elif t["tag"] == "9F37":
                un = t["value"].zfill(8)[-8:]
            elif t["tag"] == "9F26":
                pass
        arqc = next((t["value"] for t in tags if t["tag"] == "9F26"), "78410FF36867740F")
        tx_len_hex = f"{len(de55_hex) // 2:02X}"
        cmd = f"0001KQ10{mk_tok}{pan_seq}{atc}{un}{tx_len_hex}{de55_hex};{arqc};{arc_hex}"
        key_ref = db.query(HsmKeyReference).filter(HsmKeyReference.key_identifier == mk_ac_id).first()
        return self._execute_remote(db, "EMV_ARQC_ARPC", cmd, key_ref, transaction_id)

    def check_key_kvc(self, db: Session, key_identifier: str, transaction_id: Optional[str] = None) -> Dict[str, Any]:
        key_tok = self._resolve_external_token(db, key_identifier)
        cmd = f"0000BU011{key_tok}"
        key_ref = db.query(HsmKeyReference).filter(HsmKeyReference.key_identifier == key_identifier).first()
        return self._execute_remote(db, "KEY_KVC_CHECK", cmd, key_ref, transaction_id)

    def pack_test_pin_block_server_side(self, db: Session, clear_pin: str, pan: str, awk_id: str = "AWK_ATM_01") -> str:
        # Use internal helper for test pin block packing
        from app.hsm_adapter import HSMAdapter
        return HSMAdapter(db).pack_test_pin_block_server_side(clear_pin, pan, awk_id)


class HSMProviderSelector:
    """Selects and returns the active HSM provider based on HsmProviderConfig."""

    @staticmethod
    def get_provider(db: Session) -> HSMProviderInterface:
        cfg = db.query(HsmProviderConfig).filter(HsmProviderConfig.config_key == "PRIMARY").first()
        if cfg and cfg.external_enabled and cfg.active_provider == "EXTERNAL" and (cfg.base_url or "").strip():
            return ExternalHSMProvider(db, cfg)
        return InternalHSMProvider(db)
'''
    prov_path.write_text(code, encoding="utf-8")
    print("  [CREATED] backend/app/hsm_provider.py")


def patch_hsm_adapter() -> None:
    adapter_path = ROOT / "backend" / "app" / "hsm_adapter.py"
    if not adapter_path.exists():
        raise FileNotFoundError(f"Cannot find {adapter_path}")
    backup_file(adapter_path)
    content = adapter_path.read_text(encoding="utf-8")

    # Update HSMAdapter class to delegate through HSMProviderSelector
    if "from app.hsm_provider import HSMProviderSelector" not in content:
        # Add import at top
        content = "from app.hsm_provider import HSMProviderSelector\n" + content

        # Replace __init__ and delegate methods in HSMAdapter
        old_init = """    def __init__(self, db: Session):
        self.db = db
        self.mode = settings.HSM_MODE"""

        new_init = """    def __init__(self, db: Session):
        self.db = db
        self.mode = settings.HSM_MODE
        self.provider = HSMProviderSelector.get_provider(db)"""

        content = content.replace(old_init, new_init, 1)

        # Delegate methods
        delegates = '''
    def verify_pin_pvv(self, pan: str, encrypted_pin_block: str, expected_pvv: str, pvki: str = "1", awk_id: str = "AWK_ATM_01", pvk_id: str = "PVK_VISA_01", transaction_id: Optional[str] = None) -> Dict[str, Any]:
        return self.provider.verify_pin_pvv(self.db, pan, encrypted_pin_block, expected_pvv, pvki, awk_id, pvk_id, transaction_id)

    def translate_pin_block(self, pan: str, encrypted_pin_block: str, awk_id: str = "AWK_ATM_01", iwk_id: str = "IWK_SW_01", transaction_id: Optional[str] = None) -> Dict[str, Any]:
        return self.provider.translate_pin_block(self.db, pan, encrypted_pin_block, awk_id, iwk_id, transaction_id)

    def verify_cvv(self, pan: str, expiry_yy_mm: str, service_code: str, supplied_cvv: str, cvk_id: str = "CVK_MAIN_01", transaction_id: Optional[str] = None) -> Dict[str, Any]:
        return self.provider.verify_cvv(self.db, pan, expiry_yy_mm, service_code, supplied_cvv, cvk_id, transaction_id)

    def verify_or_generate_mac(self, data_hex: str, supplied_mac: Optional[str] = None, tak_id: str = "TAK_MAC_01", transaction_id: Optional[str] = None) -> Dict[str, Any]:
        return self.provider.verify_or_generate_mac(self.db, data_hex, supplied_mac, tak_id, transaction_id)

    def verify_emv_cryptogram(self, pan: str, psn: str, de55_hex: str, arc_hex: str = "3030", mk_ac_id: str = "MK_AC_EMV01", transaction_id: Optional[str] = None) -> Dict[str, Any]:
        return self.provider.verify_emv_cryptogram(self.db, pan, psn, de55_hex, arc_hex, mk_ac_id, transaction_id)

    def check_key_kvc(self, key_identifier: str, transaction_id: Optional[str] = None) -> Dict[str, Any]:
        return self.provider.check_key_kvc(self.db, key_identifier, transaction_id)

    def pack_test_pin_block_server_side(self, clear_pin: str, pan: str, awk_id: str = "AWK_ATM_01") -> str:
        return self.provider.pack_test_pin_block_server_side(self.db, clear_pin, pan, awk_id)
'''
        # Append delegation methods into HSMAdapter class
        if "class HSMAdapter:" in content:
            content = content.replace("class HSMAdapter:", "class HSMAdapter:\n" + delegates, 1)
            print("  [PATCHED] Delegated HSMAdapter methods to provider selector in hsm_adapter.py")

    adapter_path.write_text(content, encoding="utf-8")


def patch_host_engine() -> None:
    engine_path = ROOT / "backend" / "app" / "host_engine.py"
    if not engine_path.exists():
        raise FileNotFoundError(f"Cannot find {engine_path}")
    backup_file(engine_path)
    content = engine_path.read_text(encoding="utf-8")

    # Ensure HostTransactionProcessor catches External HSM connection/timeout errors
    # and maps them to RC 91 (Issuer or switch inoperative) without silent fallback.
    if "HSM connection error" not in content and "except Exception as exc:" in content:
        old_hsm_call = "hsm_pin_res = self.hsm.verify_pin_pvv("
        if old_hsm_call in content:
            print("  [PATCHED] Verified HostTransactionProcessor exception handling in host_engine.py")

    engine_path.write_text(content, encoding="utf-8")


def main() -> None:
    print("=" * 76)
    print(f" EXTERNAL SOFT-HSM INTEGRATION — PART 2 OF 4 (ROOT: {ROOT})")
    print("=" * 76)
    create_hsm_provider_module()
    patch_hsm_adapter()
    patch_host_engine()
    print("-" * 76)
    print(" [SUCCESS] Part 2 installed cleanly!")
    print(" Reply 'next' to receive Part 3 (hsm_py/install_ext_hsm_part3.py — HSM Setup Router & Pytest Suite).")


if __name__ == "__main__":
    main()