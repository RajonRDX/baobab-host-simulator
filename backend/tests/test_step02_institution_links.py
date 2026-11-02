"""
test_step02_institution_links.py — Tests for Step 2 Institution Linking & Transaction Scoping
"""

import os
import pytest
from decimal import Decimal
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Account, Card, Customer, Institution, ProcessingSystem, Transaction
from app.host_engine import HostTransactionProcessor
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


def test_entities_have_institution_links(db_session):
    xbank = db_session.query(Institution).filter(Institution.institution_code == "XBANK").first()
    assert xbank is not None

    cust = db_session.query(Customer).first()
    assert cust.institution_id == xbank.id

    acct = db_session.query(Account).first()
    assert acct.institution_id == xbank.id

    card = db_session.query(Card).first()
    assert card.institution_id == xbank.id


def test_transaction_records_institution_and_ps_code(db_session):
    proc = HostTransactionProcessor(db_session)
    res = proc.process_transaction({
        "transaction_code": "10",
        "mti": "0200",
        "test_clear_pin_helper": "1234",
        "fields": {
            "2": "4567890123450001",
            "3": "0100000",
            "4": "000000150000",
            "11": "300001",
            "32": "123456",  # XBANK acquirer ID
            "37": "000095000001",
            "41": "ATM01",
            "49": "050",
        },
    })
    assert res["response_code"] == "00"

    tx = db_session.query(Transaction).filter(Transaction.id == res["transaction_id"]).first()
    assert tx is not None
    assert tx.ps_code == "ITCL"
    assert tx.is_on_us is True
    assert tx.issuer_institution_id is not None
    assert tx.acquirer_institution_id is not None
    assert tx.issuer_institution_id == tx.acquirer_institution_id


def test_api_creates_card_with_institution(client, db_session):
    ybank = db_session.query(Institution).filter(Institution.institution_code == "YBANK").first()
    cust = db_session.query(Customer).first()
    acct = db_session.query(Account).first()

    payload = {
        "customer_id": cust.id,
        "test_pan_reference": "5123450123459999",
        "cardholder_name": "YBANK TEST HOLDER",
        "expiry_month": 12,
        "expiry_year": 2028,
        "linked_account_id": acct.id,
        "institution_id": ybank.id,
    }
    res = client.post("/api/cards", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["institution_id"] == ybank.id
    assert data["institution_code"] == "YBANK"
