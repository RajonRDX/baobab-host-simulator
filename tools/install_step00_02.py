#!/usr/bin/env python3
"""
INSTALLER: tools/install_step00_02.py
STEP 0 — Prerequisites & Installer Framework — Script 2 of 2
Adds:
  1. _backups/ in .gitignore
  2. LOG_RAW_DATA=True configuration and unmasked raw data visibility in security.py, iso_tic.py, and hsm_adapter.py
  3. Non-destructive startup schema synchronization (backend/app/schema_sync.py) wired into database.py
  4. Automated pytest verification (backend/tests/test_step00_prerequisites.py)
"""

from pathlib import Path
import sys

BASE_DIR = Path(r"E:\HOST_VSCODE\host-simulator").resolve()
sys.path.insert(0, str(BASE_DIR))

from tools.patcher import PatcherSession, parse_installer_args

SCHEMA_SYNC_CODE = '''"""
schema_sync.py — Non-Destructive Database Schema Synchronizer
Automatically creates missing tables and adds missing nullable columns to existing
SQLite / PostgreSQL tables without deleting or altering existing data.
"""

import logging
from typing import Dict, List, Set
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger("baobab.schema_sync")


def _compile_column_type(column, dialect) -> str:
    try:
        return column.type.compile(dialect=dialect)
    except Exception:
        return "TEXT"


def synchronize_database_schema(engine: Engine, base_cls: type[DeclarativeBase]) -> Dict[str, List[str]]:
    """
    1. Creates any brand-new tables registered on `base_cls.metadata`.
    2. Inspects every existing table and issues `ALTER TABLE ... ADD COLUMN ...`
       for any newly defined ORM columns that do not yet exist in the physical database.
    Never drops tables, never drops columns, and never deletes existing rows.
    """
    summary: Dict[str, List[str]] = {"created_tables": [], "added_columns": []}

    inspector = inspect(engine)
    existing_tables: Set[str] = set(inspector.get_table_names())

    # 1. Create missing tables first
    base_cls.metadata.create_all(bind=engine)

    inspector_after = inspect(engine)
    after_tables: Set[str] = set(inspector_after.get_table_names())
    for tbl in sorted(after_tables - existing_tables):
        summary["created_tables"].append(tbl)
        logger.info("[SchemaSync] Created new table: %s", tbl)

    # 2. Check existing tables for missing columns
    with engine.begin() as conn:
        for table_name, table_obj in base_cls.metadata.tables.items():
            if table_name not in existing_tables:
                continue

            db_cols = {c["name"].lower() for c in inspector_after.get_columns(table_name)}
            for col in table_obj.columns:
                if col.name.lower() in db_cols:
                    continue

                col_type_sql = _compile_column_type(col, engine.dialect)
                default_clause = ""

                # If a column has a simple scalar default and is non-nullable, provide a safe default
                if not col.nullable and col.default is not None and getattr(col.default, "is_scalar", False):
                    arg = col.default.arg
                    if isinstance(arg, bool):
                        default_clause = f" DEFAULT {1 if arg else 0}" if engine.dialect.name == "sqlite" else f" DEFAULT {'TRUE' if arg else 'FALSE'}"
                    elif isinstance(arg, (int, float)):
                        default_clause = f" DEFAULT {arg}"
                    elif isinstance(arg, str):
                        safe_str = arg.replace("'", "''")
                        default_clause = f" DEFAULT '{safe_str}'"

                alter_sql = f'ALTER TABLE "{table_name}" ADD COLUMN "{col.name}" {col_type_sql}{default_clause}'
                conn.execute(text(alter_sql))
                summary["added_columns"].append(f"{table_name}.{col.name}")
                logger.info("[SchemaSync] Added missing column: %s.%s (%s)", table_name, col.name, col_type_sql)

    return summary
'''

TEST_STEP00_CODE = '''"""
test_step00_prerequisites.py — Tests for Step 0:
1. LOG_RAW_DATA=True raw visibility & LOG_RAW_DATA=False masking fallback
2. Non-destructive schema synchronization (adding missing columns to existing SQLite tables)
"""

import os
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect, text

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.config import settings
from app.database import Base
from app.iso_tic import build_tic_message, decode_tic_message
from app.schema_sync import synchronize_database_schema
from app.security import mask_pan, mask_raw_tic_message, sanitize_dict


def test_log_raw_data_enabled_by_default():
    assert settings.LOG_RAW_DATA is True
    pan = "4567890123450001"
    # With LOG_RAW_DATA=True, mask_pan and sanitize_dict preserve raw synthetic values
    assert mask_pan(pan) == pan
    sample = {"pan": pan, "pin_block": "1122334455667788", "cvv": "011"}
    sanitized = sanitize_dict(sample)
    assert sanitized["pan"] == pan
    assert sanitized["pin_block"] == "1122334455667788"
    assert sanitized["cvv"] == "011"

    raw_msg, compact = build_tic_message(
        "0200",
        {2: pan, 3: "0100000", 4: "000000100000", 11: "123456", 37: "000020526991", 49: "BDT", 52: "A1B2C3D4E5F60718"},
    )
    assert mask_raw_tic_message(compact) == compact
    decoded = decode_tic_message(raw_msg)
    assert decoded["valid"] is True
    assert decoded["detailed_fields"]["F52 PIN"]["value"] == "A1B2C3D4E5F60718"


def test_log_raw_data_can_be_toggled_off(monkeypatch):
    monkeypatch.setattr(settings, "LOG_RAW_DATA", False)
    pan = "4567890123450001"
    assert mask_pan(pan) == "456789******0001"
    sample = {"pan": pan, "pin_block": "1122334455667788"}
    sanitized = sanitize_dict(sample)
    assert sanitized["pan"] == "456789******0001"
    assert sanitized["pin_block"] == "***MASKED***"


def test_schema_sync_adds_missing_columns_without_data_loss():
    temp_engine = create_engine("sqlite:///:memory:", future=True)
    with temp_engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE customers ("
                "id VARCHAR(36) PRIMARY KEY, "
                "customer_number VARCHAR(40) NOT NULL, "
                "first_name VARCHAR(100) NOT NULL"
                ")"
            )
        )
        conn.execute(
            text("INSERT INTO customers (id, customer_number, first_name) VALUES ('c1', 'CUST-001', 'Mehedi')")
        )

    summary = synchronize_database_schema(temp_engine, Base)
    assert any(col.startswith("customers.") for col in summary["added_columns"])

    inspector = inspect(temp_engine)
    col_names = {c["name"] for c in inspector.get_columns("customers")}
    assert "last_name" in col_names
    assert "risk_category" in col_names

    with temp_engine.connect() as conn:
        row = conn.execute(text("SELECT customer_number, first_name FROM customers WHERE id = 'c1'")).fetchone()
        assert row is not None
        assert row[0] == "CUST-001"
        assert row[1] == "Mehedi"
'''


def main() -> int:
    args = parse_installer_args("Step 00_02: LOG_RAW_DATA, .gitignore, and Startup Schema Sync")
    session = PatcherSession(
        step_id="step00_02",
        title="Configure LOG_RAW_DATA=True, .gitignore, and Startup Schema Synchronization",
        dry_run=args.dry_run,
    )

    # 1. Create or patch .gitignore with _backups/
    gitignore_path = BASE_DIR / ".gitignore"
    if gitignore_path.exists():
        session.patch_file(
            ".gitignore",
            [
                {
                    "marker": "step00_02:gitignore_backups",
                    "action": "append",
                    "text": "_backups/\n",
                }
            ],
        )
    else:
        session.write_file(
            ".gitignore",
            "# BAOBAB Host Simulator .gitignore\n_backups/\n__pycache__/\n*.py[cod]\n.venv/\nvenv/\nnode_modules/\ndist/\n.env\n",
        )

    # 2. Write backend/app/schema_sync.py
    session.write_file("backend/app/schema_sync.py", SCHEMA_SYNC_CODE)

    # 3. Patch backend/app/config.py to add LOG_RAW_DATA: bool = True
    session.patch_file(
        "backend/app/config.py",
        [
            {
                "marker": "step00_02:config_log_raw_data",
                "action": "insert_after",
                "anchor": "    HSM_HEADER_LENGTH: int = 4",
                "text": "    LOG_RAW_DATA: bool = True",
            }
        ],
    )

    # 4. Patch backend/app/security.py so LOG_RAW_DATA=True preserves raw PANs, PIN blocks, and dicts
    session.patch_file(
        "backend/app/security.py",
        [
            {
                "marker": "step00_02:mask_pan_raw",
                "action": "insert_after",
                "anchor": 'def mask_pan(pan: str) -> str:\n    """Mask PAN leaving first 6 and last 4 digits visible."""',
                "text": (
                    "    if getattr(settings, 'LOG_RAW_DATA', True):\n"
                    "        return str(pan or '')"
                ),
            },
            {
                "marker": "step00_02:sanitize_dict_raw",
                "action": "insert_after",
                "anchor": 'def sanitize_dict(data: Any) -> Any:\n    """Recursively mask sensitive fields in dictionaries before logging or saving."""',
                "text": (
                    "    if getattr(settings, 'LOG_RAW_DATA', True):\n"
                    "        return data"
                ),
            },
            {
                "marker": "step00_02:mask_raw_tic_raw",
                "action": "insert_after",
                "anchor": 'def mask_raw_tic_message(raw_msg: str) -> str:\n    """Mask PAN and PIN block sequences inside raw or compact TIC strings."""',
                "text": (
                    "    if getattr(settings, 'LOG_RAW_DATA', True):\n"
                    "        return raw_msg or ''"
                ),
            },
        ],
    )

    # 5. Patch backend/app/iso_tic.py so F52 in decode_tic_message shows raw hex when LOG_RAW_DATA=True
    session.patch_file(
        "backend/app/iso_tic.py",
        [
            {
                "marker": "step00_02:iso_tic_imports",
                "action": "insert_after",
                "anchor": "from app.security import mask_pan, mask_raw_tic_message",
                "text": "from app.config import settings",
            },
            {
                "marker": "step00_02:iso_tic_f52_raw",
                "action": "replace",
                "anchor": (
                    '            elif fnum == 52:\n'
                    '                detailed_fields[f"F{fnum} {fname}"] = {"value": "***ENCRYPTED_PIN_BLOCK***"}\n'
                    '                compact_parts.append(f"F52)****************{SEP}")'
                ),
                "text": (
                    '            elif fnum == 52:\n'
                    '                pin_disp = val if getattr(settings, "LOG_RAW_DATA", True) else "***ENCRYPTED_PIN_BLOCK***"\n'
                    '                pin_comp = val if getattr(settings, "LOG_RAW_DATA", True) else "****************"\n'
                    '                detailed_fields[f"F{fnum} {fname}"] = {"value": pin_disp}\n'
                    '                compact_parts.append(f"F52){pin_comp}{SEP}")'
                ),
            },
        ],
    )

    # 6. Patch backend/app/hsm_adapter.py so PIN_PVV_VERIFY and PIN_TRANSLATE show raw blocks/PVVs when LOG_RAW_DATA=True
    session.patch_file(
        "backend/app/hsm_adapter.py",
        [
            {
                "marker": "step00_02:hsm_pvv_raw_trace",
                "action": "replace",
                "anchor": (
                    '            sanitized_req={\n'
                    '                "command": "DC",\n'
                    '                "masked_pan": mask_pan(pan),\n'
                    '                "awk_key": awk_id,\n'
                    '                "pvk_key": pvk_id,\n'
                    '                "pvki": pvki,\n'
                    '                "pin_block": "***MASKED_ISO0_BLOCK***",\n'
                    '            },'
                ),
                "text": (
                    '            sanitized_req={\n'
                    '                "command": "DC",\n'
                    '                "masked_pan": mask_pan(pan),\n'
                    '                "awk_key": awk_id,\n'
                    '                "pvk_key": pvk_id,\n'
                    '                "pvki": pvki,\n'
                    '                "expected_pvv": expected_pvv if getattr(settings, "LOG_RAW_DATA", True) else "***",\n'
                    '                "pin_block": encrypted_pin_block if getattr(settings, "LOG_RAW_DATA", True) else "***MASKED_ISO0_BLOCK***",\n'
                    '            },'
                ),
            },
            {
                "marker": "step00_02:hsm_translate_raw_trace",
                "action": "replace",
                "anchor": (
                    '            sanitized_resp={\n'
                    '                "thales_response": f"0000CB{err}",\n'
                    '                "destination_pin_block_generated": bool(dest_block),\n'
                    '            },'
                ),
                "text": (
                    '            sanitized_resp={\n'
                    '                "thales_response": f"0000CB{err}",\n'
                    '                "destination_pin_block_generated": bool(dest_block),\n'
                    '                "source_pin_block": encrypted_pin_block if getattr(settings, "LOG_RAW_DATA", True) else "***",\n'
                    '                "destination_pin_block": dest_block if getattr(settings, "LOG_RAW_DATA", True) else "***",\n'
                    '            },'
                ),
            },
        ],
    )

    # 7. Patch backend/app/database.py to invoke synchronize_database_schema inside init_db()
    session.patch_file(
        "backend/app/database.py",
        [
            {
                "marker": "step00_02:database_sync_schema",
                "action": "replace",
                "anchor": (
                    "def init_db() -> None:\n"
                    "    import app.models  # noqa: F401\n"
                    "    Base.metadata.create_all(bind=engine)"
                ),
                "text": (
                    "def init_db() -> None:\n"
                    "    import app.models  # noqa: F401\n"
                    "    from app.schema_sync import synchronize_database_schema\n"
                    "    synchronize_database_schema(engine, Base)"
                ),
            }
        ],
    )

    # 8. Patch backend/app/main.py to expose log_raw_data in /health
    session.patch_file(
        "backend/app/main.py",
        [
            {
                "marker": "step00_02:main_health_raw_flag",
                "action": "insert_after",
                "anchor": '        "hsm_mode": settings.HSM_MODE,',
                "text": '        "log_raw_data": settings.LOG_RAW_DATA,',
            }
        ],
    )

    # 9. Patch backend/tests/test_host_engine.py so roundtrip test checks mask_pan(pan) dynamically
    session.patch_file(
        "backend/tests/test_host_engine.py",
        [
            {
                "marker": "step00_02:test_roundtrip_raw_compatible",
                "action": "replace",
                "anchor": '    assert "456789******0001" in decoded["sanitized_raw"]',
                "text": '    assert mask_pan("4567890123450001") in decoded["sanitized_raw"]',
            }
        ],
    )

    # 10. Write new test file backend/tests/test_step00_prerequisites.py
    session.write_file("backend/tests/test_step00_prerequisites.py", TEST_STEP00_CODE)

    session.record_progress(
        completed=[
            "Added `_backups/` to `.gitignore`.",
            "Added `LOG_RAW_DATA: bool = True` to `backend/app/config.py`.",
            "Updated `security.py`, `iso_tic.py`, and `hsm_adapter.py` so raw PANs, PIN blocks, Track data, and HSM inputs/outputs remain fully visible when `LOG_RAW_DATA=True`.",
            "Created `backend/app/schema_sync.py` and wired `synchronize_database_schema(engine, Base)` into `init_db()` in `backend/app/database.py`.",
            "Added automated pytest suite `backend/tests/test_step00_prerequisites.py`.",
        ],
        remaining=[
            "STEP 1 — Bank, Institution, Processing System (ITCL-first), and BIN Range Management (`install_step01_01.py`, `install_step01_02.py`, `install_step01_03.py`).",
        ],
        modified_files=[
            ".gitignore",
            "backend/app/schema_sync.py",
            "backend/app/config.py",
            "backend/app/security.py",
            "backend/app/iso_tic.py",
            "backend/app/hsm_adapter.py",
            "backend/app/database.py",
            "backend/app/main.py",
            "backend/tests/test_host_engine.py",
            "backend/tests/test_step00_prerequisites.py",
        ],
    )

    session.record_contracts(
        section_title="Raw Data Configuration & Non-Destructive Schema Sync",
        contract_items=[
            "**Setting**: `settings.LOG_RAW_DATA: bool = True` in `backend/app/config.py`",
            "**Function**: `synchronize_database_schema(engine, Base) -> Dict[str, List[str]]` in `backend/app/schema_sync.py`",
            "**Endpoint**: `GET /health` returns `{'status': 'ONLINE', 'application': ..., 'hsm_mode': ..., 'log_raw_data': True}`",
            "**Behavior**: When `LOG_RAW_DATA=True`, `mask_pan()`, `sanitize_dict()`, `mask_raw_tic_message()`, `decode_tic_message()`, and `HSMAdapter` preserve unmasked synthetic test values.",
        ],
    )

    return session.finish()


if __name__ == "__main__":
    sys.exit(main())