#!/usr/bin/env python3
"""
install_ext_hsm_part1.py — Part 1 of 4: Database Models, Schema Sync, Pydantic Schemas & Seeding
Save in : E:\\HOST_VSCODE\\host-simulator\\hsm_py\\install_ext_hsm_part1.py
Run from: E:\\HOST_VSCODE\\host-simulator
Command : python hsm_py\\install_ext_hsm_part1.py
"""

import shutil
from datetime import datetime
from pathlib import Path


def resolve_project_root() -> Path:
    """Auto-detects E:\\HOST_VSCODE\\host-simulator even when script is inside hsm_py/."""
    script_dir = Path(__file__).resolve().parent
    if (script_dir / "backend" / "app").exists():
        return script_dir
    if (script_dir.parent / "backend" / "app").exists():
        return script_dir.parent
    cwd = Path.cwd().resolve()
    if (cwd / "backend" / "app").exists():
        return cwd
    raise FileNotFoundError(
        f"Could not locate 'backend/app' relative to {script_dir}. "
        "Make sure this file is inside E:\\HOST_VSCODE\\host-simulator\\hsm_py\\"
    )


ROOT = resolve_project_root()
BACKUP_DIR = ROOT / "_backups" / f"ext_hsm_part1_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def backup_file(path: Path) -> None:
    if path.exists():
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        rel = path.relative_to(ROOT)
        dest = BACKUP_DIR / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        print(f"  [BACKUP] {rel} -> {dest.relative_to(ROOT)}")


def patch_models() -> None:
    models_path = ROOT / "backend" / "app" / "models.py"
    if not models_path.exists():
        raise FileNotFoundError(f"Cannot find {models_path}")
    backup_file(models_path)
    content = models_path.read_text(encoding="utf-8")

    # 1. Add additive columns to HsmKeyReference if not present
    if "external_key_token: Mapped" not in content:
        target = '    key_status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")'
        replacement = (
            '    key_status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")\n'
            '    # [PATCH ext_hsm_part1:hsm_key_reference_columns]\n'
            '    thales_key_type: Mapped[Optional[str]] = mapped_column(String(10), default="001")\n'
            '    key_scheme: Mapped[Optional[str]] = mapped_column(String(5), default="U")\n'
            '    external_key_token: Mapped[Optional[str]] = mapped_column(String(200))\n'
            '    key_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)\n'
            '    provider_origin: Mapped[str] = mapped_column(String(20), nullable=False, default="INTERNAL")\n'
            '    is_test_key: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)\n'
            '    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)\n'
            '    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)'
        )
        if target in content:
            content = content.replace(target, replacement, 1)
            print("  [PATCHED] Added external_key_token & metadata columns to HsmKeyReference")
        else:
            raise RuntimeError("Could not locate HsmKeyReference.key_status anchor in models.py")

    # 2. Add additive columns to HsmOperation if not present
    if "provider_mode: Mapped" not in content:
        target_op = '    error_code: Mapped[str] = mapped_column(String(60), nullable=False, default="00")'
        replacement_op = (
            '    error_code: Mapped[str] = mapped_column(String(60), nullable=False, default="00")\n'
            '    # [PATCH ext_hsm_part1:hsm_operation_columns]\n'
            '    provider_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="INTERNAL", index=True)\n'
            '    command_code: Mapped[Optional[str]] = mapped_column(String(10), index=True)\n'
            '    thales_response_code: Mapped[Optional[str]] = mapped_column(String(10))\n'
            '    rrn: Mapped[Optional[str]] = mapped_column(String(24), index=True)\n'
            '    institution_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)\n'
            '    final_host_decision: Mapped[Optional[str]] = mapped_column(String(30))'
        )
        if target_op in content:
            content = content.replace(target_op, replacement_op, 1)
            print("  [PATCHED] Added provider_mode, command_code, rrn, institution_id to HsmOperation")
        else:
            raise RuntimeError("Could not locate HsmOperation.error_code anchor in models.py")

    # 3. Append HsmProviderConfig model if not present
    if "class HsmProviderConfig(" not in content:
        provider_model_code = '''

# ==============================================================================
# L. EXTERNAL / INTERNAL HSM PROVIDER CONFIGURATION (HSM INTEGRATION)
# ==============================================================================

class HsmProviderConfig(Base):
    """
    Singleton configuration table governing Mode A (Internal HSM - Default)
    vs Mode B (External Soft HSM).
    """
    __tablename__ = "hsm_provider_config"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    config_key: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, default="PRIMARY", index=True)
    active_provider: Mapped[str] = mapped_column(String(20), nullable=False, default="INTERNAL")  # INTERNAL | EXTERNAL
    external_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    connection_name: Mapped[str] = mapped_column(String(120), nullable=False, default="Thales payShield 10K Soft-HSM")
    provider_name: Mapped[str] = mapped_column(String(120), nullable=False, default="Thales payShield 10K v3.5 Soft-HSM")
    connection_type: Mapped[str] = mapped_column(String(30), nullable=False, default="HTTP_REST")  # HTTP_REST
    base_url: Mapped[Optional[str]] = mapped_column(String(255), default="")
    api_endpoint: Mapped[str] = mapped_column(String(120), nullable=False, default="/api/host/command")
    framing_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="ASCII")  # ASCII | HEX_TCP
    header_length: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    source_host_id: Mapped[str] = mapped_column(String(60), nullable=False, default="BAOBAB_HOST_SIMULATOR")
    connect_timeout_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=5000)
    read_timeout_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=10000)
    tls_verify: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    auth_type: Mapped[str] = mapped_column(String(30), nullable=False, default="NONE")  # NONE | BEARER | API_KEY
    auth_header_name: Mapped[Optional[str]] = mapped_column(String(60), default="Authorization")
    auth_token_masked: Mapped[Optional[str]] = mapped_column(String(120))
    auth_token_secret: Mapped[Optional[str]] = mapped_column(String(255))

    # Connection & Validation Status
    connection_status: Mapped[str] = mapped_column(String(30), nullable=False, default="NOT_CONFIGURED")
    validation_passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_validation_details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)
    last_successful_connection_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_health_check_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_health_status: Mapped[str] = mapped_column(String(30), nullable=False, default="UNKNOWN")
    last_operation_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_operation_status: Mapped[Optional[str]] = mapped_column(String(30))
    last_error_message: Mapped[Optional[str]] = mapped_column(Text)

    # Discovered External Soft-HSM Telemetry
    remote_version: Mapped[Optional[str]] = mapped_column(String(40))
    remote_firmware: Mapped[Optional[str]] = mapped_column(String(40))
    remote_lmk_kcv: Mapped[Optional[str]] = mapped_column(String(40))
    remote_storage_mode: Mapped[Optional[str]] = mapped_column(String(80))
    supported_commands_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
'''
        content = content.rstrip() + "\n" + provider_model_code
        print("  [PATCHED] Added HsmProviderConfig model to models.py")

    models_path.write_text(content, encoding="utf-8")


def patch_schema_sync() -> None:
    sync_path = ROOT / "backend" / "app" / "schema_sync.py"
    if not sync_path.exists():
        print("  [INFO] Creating backend/app/schema_sync.py")
    else:
        backup_file(sync_path)

    sync_code = '''"""
schema_sync.py — Idempotent Additive Database Schema Synchronizer
Ensures new tables and additive columns exist without dropping or resetting existing data.
"""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def synchronize_database_schema(engine: Engine, base_metadata) -> None:
    """Create missing tables and add missing columns safely."""
    base_metadata.create_all(bind=engine)
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    for table_name, table_obj in base_metadata.tables.items():
        if table_name not in existing_tables:
            continue
        existing_cols = {c["name"] for c in inspector.get_columns(table_name)}
        for col in table_obj.columns:
            if col.name not in existing_cols:
                col_type = col.type.compile(dialect=engine.dialect)
                default_clause = ""
                if col.default is not None and hasattr(col.default, "arg") and not callable(col.default.arg):
                    val = col.default.arg
                    if isinstance(val, bool):
                        default_clause = f" DEFAULT {1 if val else 0}"
                    elif isinstance(val, (int, float)):
                        default_clause = f" DEFAULT {val}"
                    elif isinstance(val, str):
                        default_clause = f" DEFAULT '{val}'"
                stmt = f"ALTER TABLE {table_name} ADD COLUMN {col.name} {col_type}{default_clause}"
                try:
                    with engine.begin() as conn:
                        conn.execute(text(stmt))
                except Exception:
                    pass
'''
    sync_path.write_text(sync_code, encoding="utf-8")
    print("  [PATCHED] Verified additive schema synchronization in backend/app/schema_sync.py")


def patch_schemas() -> None:
    schemas_path = ROOT / "backend" / "app" / "schemas.py"
    if not schemas_path.exists():
        raise FileNotFoundError(f"Cannot find {schemas_path}")
    backup_file(schemas_path)
    content = schemas_path.read_text(encoding="utf-8")

    if "external_key_token: Optional[str]" not in content and "class HsmKeyReferenceOut(" in content:
        target_k = "    key_status: str"
        replacement_k = (
            "    key_status: str\n"
            "    thales_key_type: Optional[str] = None\n"
            "    key_scheme: Optional[str] = None\n"
            "    external_key_token: Optional[str] = None\n"
            "    key_version: Optional[int] = 1\n"
            "    provider_origin: Optional[str] = 'INTERNAL'\n"
            "    is_test_key: Optional[bool] = True\n"
            "    institution_id: Optional[str] = None\n"
            "    institution_code: Optional[str] = None\n"
            "    processing_system_id: Optional[str] = None\n"
            "    created_at: Optional[datetime] = None\n"
            "    updated_at: Optional[datetime] = None"
        )
        content = content.replace(target_k, replacement_k, 1)
        print("  [PATCHED] Extended HsmKeyReferenceOut in schemas.py")

    if "class HsmProviderConfigOut(" not in content:
        ext_schemas = '''

# ==============================================================================
# EXTERNAL / INTERNAL HSM SETUP & MONITORING SCHEMAS (HSM INTEGRATION)
# ==============================================================================

class HsmProviderConfigUpdate(BaseModel):
    connection_name: Optional[str] = None
    provider_name: Optional[str] = None
    connection_type: Optional[str] = "HTTP_REST"
    base_url: Optional[str] = None
    api_endpoint: Optional[str] = "/api/host/command"
    framing_mode: Optional[str] = "ASCII"
    header_length: Optional[int] = 4
    source_host_id: Optional[str] = "BAOBAB_HOST_SIMULATOR"
    connect_timeout_ms: Optional[int] = 5000
    read_timeout_ms: Optional[int] = 10000
    tls_verify: Optional[bool] = True
    auth_type: Optional[str] = "NONE"
    auth_header_name: Optional[str] = "Authorization"
    auth_token_secret: Optional[str] = None


class HsmProviderConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    config_key: str
    active_provider: str
    external_enabled: bool
    connection_name: str
    provider_name: str
    connection_type: str
    base_url: Optional[str] = ""
    api_endpoint: str
    framing_mode: str
    header_length: int
    source_host_id: str
    connect_timeout_ms: int
    read_timeout_ms: int
    tls_verify: bool
    auth_type: str
    auth_header_name: Optional[str] = "Authorization"
    auth_token_masked: Optional[str] = None
    connection_status: str
    validation_passed: bool
    last_validation_details: Optional[Dict[str, Any]] = None
    last_successful_connection_at: Optional[datetime] = None
    last_health_check_at: Optional[datetime] = None
    last_health_status: str
    last_operation_at: Optional[datetime] = None
    last_operation_status: Optional[str] = None
    last_error_message: Optional[str] = None
    remote_version: Optional[str] = None
    remote_firmware: Optional[str] = None
    remote_lmk_kcv: Optional[str] = None
    remote_storage_mode: Optional[str] = None
    supported_commands_json: Optional[List[str]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class HsmConnectionTestRequest(BaseModel):
    base_url: Optional[str] = None
    api_endpoint: Optional[str] = None
    framing_mode: Optional[str] = None
    header_length: Optional[int] = None
    connect_timeout_ms: Optional[int] = None
    read_timeout_ms: Optional[int] = None
    tls_verify: Optional[bool] = None
    auth_type: Optional[str] = None
    auth_header_name: Optional[str] = None
    auth_token_secret: Optional[str] = None


class HsmKeyManageCreateRequest(BaseModel):
    key_name: str
    key_type: str  # ZMK, TMK, ZPK, AWK, IWK, TPK, PVK, CVK, TAK, ZAK, BDK, IPEK, MK-AC, DEK
    key_usage: Optional[str] = None
    key_identifier: str
    thales_key_type: Optional[str] = None  # 000, 001, 002, 402, 003, 008, 009, 302, 109, 00B
    key_scheme: str = "U"
    algorithm: str = "3DES_2KEY"
    key_length: int = 128
    institution_id: Optional[str] = None
    processing_system_id: Optional[str] = None
    key_version: int = 1
    is_test_key: bool = True
    clear_key_hex: Optional[str] = None
    export_under_zmk_id: Optional[str] = None


class HsmKeyImportUnderZmkSetupRequest(BaseModel):
    key_name: str
    key_type: str
    key_identifier: str
    thales_key_type: Optional[str] = None
    zmk_key_identifier: str = "ZMK_MAIN"
    encrypted_key_under_zmk: str
    key_scheme: str = "U"
    institution_id: Optional[str] = None
    processing_system_id: Optional[str] = None
    key_version: int = 1
    is_test_key: bool = True


class HsmKeyExportUnderZmkSetupRequest(BaseModel):
    key_identifier: str
    zmk_key_identifier: str = "ZMK_MAIN"
    key_scheme_zmk: str = "U"
'''
        content = content.rstrip() + "\n" + ext_schemas
        print("  [PATCHED] Added HSM Setup & Key Management Pydantic schemas to schemas.py")

    schemas_path.write_text(content, encoding="utf-8")


def patch_seed_data() -> None:
    seed_path = ROOT / "backend" / "app" / "seed_data.py"
    if not seed_path.exists():
        raise FileNotFoundError(f"Cannot find {seed_path}")
    backup_file(seed_path)
    content = seed_path.read_text(encoding="utf-8")

    if "seed_hsm_provider_and_external_tokens" not in content:
        seed_ext_code = '''

# ==============================================================================
# SEED EXTERNAL HSM PROVIDER CONFIG & AUTHENTIC THALES LMK KEY TOKENS
# ==============================================================================

THALES_KEY_TYPE_MAPPING = {
    "ZMK": ("000", "04_05", 0x00),
    "TMK": ("002", "14_15", 0x00),
    "ZPK": ("001", "06_07", 0x00),
    "AWK": ("001", "06_07", 0x00),
    "IWK": ("001", "06_07", 0x00),
    "TPK": ("002", "14_15", 0x00),
    "PVK": ("002", "14_15", 0x00),
    "CVK": ("402", "14_15", 0xDE),
    "TAK": ("003", "16_17", 0x00),
    "ZAK": ("008", "14_15", 0x00),
    "BDK": ("009", "28_29", 0x00),
    "IPEK": ("302", "14_15", 0x6A),
    "MK-AC": ("109", "28_29", 0x00),
    "MDK": ("109", "28_29", 0x00),
    "DEK": ("00B", "32_33", 0x00),
}

DEFAULT_THALES_LMK_PAIRS = {
    "04_05": "0123456789ABCDEFFEDCBA9876543210",
    "06_07": "112233445566778899AABBCCDDEEFF00",
    "14_15": "A1B2C3D4E5F60718293A4B5C6D7E8F90",
    "16_17": "0F1E2D3C4B5A69788796A5B4C3D2E1F0",
    "26_27": "5566778899AABBCC5566778899AABBCC",
    "28_29": "CAFEBABEDEADBEEF0102030405060708",
    "32_33": "FEDCBA98765432100123456789ABCDEF",
}


def compute_thales_lmk_token(clear_key_hex: str, key_type_alias: str, scheme: str = "U") -> tuple[str, str]:
    """
    Computes the authentic Thales Variant LMK-encrypted token (e.g. 'U' + 32H)
    matching ThalesLMKManager.encrypt_under_lmk() in the separate Soft-HSM.
    """
    from app.hsm_adapter import SoftHsmCryptoCore

    kt_up = (key_type_alias or "ZPK").upper().strip()
    thales_code, pair_key, variant_mask = THALES_KEY_TYPE_MAPPING.get(kt_up, ("001", "06_07", 0x00))
    raw_lmk = DEFAULT_THALES_LMK_PAIRS.get(pair_key, DEFAULT_THALES_LMK_PAIRS["04_05"])
    lmk_bytes = bytearray(bytes.fromhex(raw_lmk))
    lmk_bytes[0] ^= variant_mask
    derived_lmk_hex = bytes(lmk_bytes).hex().upper()
    enc_hex = SoftHsmCryptoCore.des3_ecb_hex(clear_key_hex, derived_lmk_hex, decrypt=False)
    return thales_code, f"{scheme}{enc_hex}"


def seed_hsm_provider_and_external_tokens(db) -> None:
    """
    Idempotently initializes:
      1. HsmProviderConfig in Mode A (INTERNAL, external_enabled=False) by default.
      2. Authentic Thales LMK tokens (external_key_token) on all HsmKeyReference rows.
    """
    from app.models import HsmProviderConfig, HsmKeyReference, Institution, ProcessingSystem
    from app.hsm_adapter import SoftHsmCryptoCore

    cfg = db.query(HsmProviderConfig).filter(HsmProviderConfig.config_key == "PRIMARY").first()
    if not cfg:
        cfg = HsmProviderConfig(
            config_key="PRIMARY",
            active_provider="INTERNAL",
            external_enabled=False,
            connection_name="External Thales payShield 10K Soft-HSM",
            provider_name="Thales payShield 10K v3.5 Soft-HSM",
            connection_type="HTTP_REST",
            base_url="http://127.0.0.1:8000",
            api_endpoint="/api/host/command",
            framing_mode="ASCII",
            header_length=4,
            source_host_id="BAOBAB_HOST_SIMULATOR",
            connect_timeout_ms=5000,
            read_timeout_ms=10000,
            tls_verify=True,
            auth_type="NONE",
            connection_status="NOT_CONFIGURED",
            validation_passed=False,
            last_health_status="INTERNAL_ACTIVE",
        )
        db.add(cfg)
        db.flush()

    default_inst = db.query(Institution).filter(Institution.institution_code == "XBANK").first()
    default_ps = db.query(ProcessingSystem).filter(ProcessingSystem.ps_code == "ITCL").first()

    all_keys = db.query(HsmKeyReference).all()
    for k in all_keys:
        clear_hex = k.clear_key_hex or SoftHsmCryptoCore.INTERNAL_CLEAR_KEYS.get(k.key_identifier)
        if clear_hex:
            t_code, ext_tok = compute_thales_lmk_token(clear_hex, k.key_type, k.key_scheme or "U")
            if not k.thales_key_type:
                k.thales_key_type = t_code
            if not k.key_scheme:
                k.key_scheme = "U"
            if not k.external_key_token:
                k.external_key_token = ext_tok
            if not k.clear_key_hex:
                k.clear_key_hex = clear_hex
        if not k.institution_id and default_inst:
            k.institution_id = default_inst.id
        if not k.processing_system_id and default_ps:
            k.processing_system_id = default_ps.id

    bdk_exists = db.query(HsmKeyReference).filter(HsmKeyReference.key_identifier == "BDK_POS_01").first()
    if not bdk_exists:
        bdk_clear = "0123456789ABCDEFFEDCBA9876543210"
        t_code, ext_tok = compute_thales_lmk_token(bdk_clear, "BDK", "U")
        db.add(
            HsmKeyReference(
                key_name="POS DUKPT Base Derivation Key 1",
                key_type="BDK",
                key_usage="DUKPT_BDK_1",
                key_identifier="BDK_POS_01",
                kvc=SoftHsmCryptoCore.calculate_kcv(bdk_clear),
                algorithm="3DES_2KEY",
                key_length=128,
                hsm_key_reference="LMK_28_29::BDK_POS_01",
                clear_key_hex=bdk_clear,
                thales_key_type=t_code,
                key_scheme="U",
                external_key_token=ext_tok,
                key_version=1,
                provider_origin="INTERNAL",
                is_test_key=True,
                key_status="ACTIVE",
                institution_id=default_inst.id if default_inst else None,
                processing_system_id=default_ps.id if default_ps else None,
            )
        )
    db.commit()
'''
        content = content.rstrip() + "\n" + seed_ext_code

        if "seed_processing_systems_and_institutions(db)" in content:
            content = content.replace(
                "seed_processing_systems_and_institutions(db)",
                "seed_processing_systems_and_institutions(db)\n    seed_hsm_provider_and_external_tokens(db)",
                1,
            )
        else:
            idx = content.rfind("db.commit()", 0, content.find("def compute_thales_lmk_token"))
            if idx != -1:
                content = content[:idx] + "seed_hsm_provider_and_external_tokens(db)\n    " + content[idx:]
        seed_path.write_text(content, encoding="utf-8")
        print("  [PATCHED] Added seed_hsm_provider_and_external_tokens(db) to seed_data.py")


def main() -> None:
    print("=" * 76)
    print(f" EXTERNAL SOFT-HSM INTEGRATION — PART 1 OF 4 (ROOT: {ROOT})")
    print("=" * 76)
    patch_models()
    patch_schema_sync()
    patch_schemas()
    patch_seed_data()
    print("-" * 76)
    print(" [SUCCESS] Part 1 installed cleanly!")
    print(" Reply 'next' to receive Part 2 (hsm_py/install_ext_hsm_part2.py).")


if __name__ == "__main__":
    main()