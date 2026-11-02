"""
test_step10_hsm_keys.py — Tests for Step 10 HSM Key Management & Key Ceremony
"""

import os
import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import HsmKeyReference
from app.key_ceremony_service import (
    assemble_components,
    enforce_des_odd_parity,
    export_key_under_zmk,
    generate_random_des_key,
    import_key_under_zmk,
    split_key_into_components,
    validate_des_parity,
)
from app.seed_data import seed_initial_data
from app.security import create_access_token
from app.config import settings


@pytest.fixture()
def db_session():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    seed_initial_data(session)
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session):
    with TestClient(app) as c:
        token = create_access_token(subject=settings.ADMIN_USERNAME)
        c.headers = {"Authorization": f"Bearer {token}"}
        yield c


def test_odd_parity_enforcement_and_validation():
    # Known key
    raw_key = "0123456789ABCDEF0123456789ABCDEF"
    parity_key = enforce_des_odd_parity(raw_key)
    assert validate_des_parity(parity_key) is True


def test_split_and_assemble_three_components():
    rand = generate_random_des_key(128)
    orig_key = rand["key_hex"]
    orig_kcv = rand["kcv"]

    # Split into 3 parts
    split = split_key_into_components(orig_key, 3)
    assert len(split["components"]) == 3

    # Assemble back
    comps = [c["hex"] for c in split["components"]]
    assembled = assemble_components(comps)
    assert assembled["kcv"] == orig_kcv


def test_assemble_and_register_endpoint(client, db_session):
    payload = {
        "key_identifier": "AWK_TEST_CEREMONY_01",
        "key_type": "AWK",
        "components": [
            "11111111111111111111111111111111",
            "22222222222222222222222222222222"
        ]
    }
    res = client.post("/api/hsm/ceremony/assemble-components", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["key_identifier"] == "AWK_TEST_CEREMONY_01"
    assert len(data["kvc"]) == 6

    # Verify key was persisted into the database with its clear hex
    key_db = db_session.query(HsmKeyReference).filter(HsmKeyReference.key_identifier == "AWK_TEST_CEREMONY_01").first()
    assert key_db is not None
    assert key_db.clear_key_hex is not None


def test_export_and_import_under_zmk():
    zmk = "0123456789ABCDEF0123456789ABCDEF"
    working_key = "1A2B3C4D5E6F70811A2B3C4D5E6F7081"

    exported = export_key_under_zmk(working_key, zmk)
    assert len(exported["encrypted_key_hex"]) == 32

    imported = import_key_under_zmk(exported["encrypted_key_hex"], zmk)
    assert imported["kcv"] == exported["key_kcv"]
