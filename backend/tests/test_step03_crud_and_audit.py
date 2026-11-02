"""
test_step03_crud_and_audit.py — Tests for Step 3 CRUD & Audit Trail
"""

import os
import pytest
from decimal import Decimal
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Account, AuditTrail, Card, Customer, Institution
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


def test_customer_update_creates_audit_entry(client, db_session):
    cust = db_session.query(Customer).first()
    assert cust is not None

    update_payload = {
        "first_name": "Tariq Updated",
        "email": "tariq.new@example.test",
        "risk_category": "VIP"
    }
    res = client.put(f"/api/customers/{cust.id}", json=update_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["first_name"] == "Tariq Updated"
    assert data["risk_category"] == "VIP"

    audit = (
        db_session.query(AuditTrail)
        .filter(AuditTrail.entity_type == "CUSTOMER", AuditTrail.entity_id == cust.id)
        .order_by(AuditTrail.created_at.desc())
        .first()
    )
    assert audit is not None
    assert audit.action == "UPDATE"
    assert audit.before_state["first_name"] == "Tariq"
    assert audit.after_state["first_name"] == "Tariq Updated"


def test_delete_customer_with_linked_accounts_fails_409(client, db_session):
    cust = db_session.query(Customer).filter(Customer.accounts.any()).first()
    assert cust is not None

    # Normal delete without force must return 409 Conflict
    res = client.delete(f"/api/customers/{cust.id}")
    assert res.status_code == 409
    assert "active accounts" in res.json()["detail"].lower()


def test_card_update_and_audit(client, db_session):
    card = db_session.query(Card).first()
    assert card is not None

    payload = {
        "cardholder_name": "NEW CARDHOLDER NAME",
        "expiry_month": 11,
        "expiry_year": 2029,
        "card_status": "BLOCKED"
    }
    res = client.put(f"/api/cards/{card.id}", json=payload)
    assert res.status_code == 200
    assert res.json()["cardholder_name"] == "NEW CARDHOLDER NAME"
    assert res.json()["card_status"] == "BLOCKED"

    audit = (
        db_session.query(AuditTrail)
        .filter(AuditTrail.entity_type == "CARD", AuditTrail.entity_id == card.id)
        .order_by(AuditTrail.created_at.desc())
        .first()
    )
    assert audit is not None
    assert audit.action == "UPDATE"
    assert audit.after_state["card_status"] == "BLOCKED"


def test_query_audit_trail_endpoint(client, db_session):
    res = client.get("/api/audit-trail")
    assert res.status_code == 200
    assert isinstance(res.json(), list)
