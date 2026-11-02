"""
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
