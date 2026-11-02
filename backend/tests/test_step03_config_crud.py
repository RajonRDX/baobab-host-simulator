"""
test_step03_config_crud.py — Tests for Step 3 Configuration & Key CRUD with Audit Trail
"""

import os
import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import AuditTrail, Card, CardProfile, HostParameter, HsmKeyReference, TransactionCode
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


def test_card_profile_crud_and_conflict_check(client, db_session):
    # 1. Create a custom profile
    payload = {
        "profile_code": "PROF_CUSTOM_01",
        "profile_name": "Custom Student Debit Profile",
        "card_product": "VISA_STUDENT",
        "domestic_enabled": True,
        "international_enabled": False,
        "ecommerce_enabled": False,
        "contactless_enabled": True,
        "cash_enabled": True
    }
    create_res = client.post("/api/card-profiles", json=payload)
    assert create_res.status_code == 200
    prof_id = create_res.json()["id"]

    # 2. Update the profile
    update_res = client.put(f"/api/card-profiles/{prof_id}", json={"ecommerce_enabled": True})
    assert update_res.status_code == 200
    assert update_res.json()["ecommerce_enabled"] is True

    # 3. Check audit trail
    audit = db_session.query(AuditTrail).filter(
        AuditTrail.entity_type == "CARD_PROFILE",
        AuditTrail.entity_id == prof_id,
        AuditTrail.action == "UPDATE"
    ).first()
    assert audit is not None
    assert audit.after_state["ecommerce_enabled"] is True

    # 4. Deleting a profile referenced by cards must return 409
    std_prof = db_session.query(CardProfile).filter(CardProfile.profile_code == "PROF_DOM_STD").first()
    del_conflict = client.delete(f"/api/card-profiles/{std_prof.id}")
    assert del_conflict.status_code == 409

    # 5. Deleting unreferenced custom profile succeeds
    del_ok = client.delete(f"/api/card-profiles/{prof_id}")
    assert del_ok.status_code == 200


def test_transaction_code_delete(client, db_session):
    tc = TransactionCode(
        transaction_code="99",
        transaction_name="Test Temp Code",
        processing_code="0990000",
        default_mti="0200"
    )
    db_session.add(tc)
    db_session.commit()

    del_res = client.delete(f"/api/transaction-codes/{tc.id}")
    assert del_res.status_code == 200

    audit = db_session.query(AuditTrail).filter(
        AuditTrail.entity_type == "TRANSACTION_CODE",
        AuditTrail.entity_id == tc.id,
        AuditTrail.action == "DELETE"
    ).first()
    assert audit is not None


def test_hsm_key_update_and_audit(client, db_session):
    key = db_session.query(HsmKeyReference).first()
    assert key is not None

    upd_res = client.put(f"/api/hsm/keys/{key.id}", json={"key_name": "Updated Key Name", "key_status": "INACTIVE"})
    assert upd_res.status_code == 200
    assert upd_res.json()["key_name"] == "Updated Key Name"
    assert upd_res.json()["key_status"] == "INACTIVE"

    audit = db_session.query(AuditTrail).filter(
        AuditTrail.entity_type == "HSM_KEY",
        AuditTrail.entity_id == key.id,
        AuditTrail.action == "UPDATE"
    ).first()
    assert audit is not None
    assert audit.after_state["key_name"] == "Updated Key Name"
