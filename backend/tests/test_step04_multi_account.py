"""
test_step04_multi_account.py — Tests for Step 4 Card & Account Multi-Linking and DE3 routing
"""

import os
import pytest
from decimal import Decimal
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Account, Card, CardAccount, Customer, Transaction
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


def test_link_multiple_accounts_to_card(client, db_session):
    card = db_session.query(Card).first()
    cust = card.customer

    # Create a secondary CURRENT account for the customer
    sec_acct = Account(
        account_number="2002009999",
        customer_id=cust.id,
        account_type="CURRENT",
        currency="BDT",
        available_balance=Decimal("50000.00"),
        ledger_balance=Decimal("50000.00"),
        account_status="ACTIVE",
        institution_id=card.institution_id,
    )
    db_session.add(sec_acct)
    db_session.commit()

    # Link secondary account to card via API
    payload = {
        "account_id": sec_acct.id,
        "account_role": "SECONDARY",
        "priority": 2,
    }
    res = client.post(f"/api/cards/{card.id}/accounts", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["account_number"] == "2002009999"
    assert data["account_role"] == "SECONDARY"
    assert data["priority"] == 2

    # Query card accounts
    get_res = client.get(f"/api/cards/{card.id}/accounts")
    assert get_res.status_code == 200
    links = get_res.json()
    assert len(links) >= 2


def test_de3_account_selection_savings_vs_current(db_session):
    proc = HostTransactionProcessor(db_session)
    card = db_session.query(Card).filter(Card.test_pan_reference == "4567890123450001").first()

    # Seeded primary account is SAVINGS (balance: 150,000.00)
    primary_acct = db_session.query(Account).filter(Account.id == card.linked_account_id).first()
    assert primary_acct.account_type == "SAVINGS"

    # Add a CURRENT account with 20,000.00 balance
    curr_acct = Account(
        account_number="2002008888",
        customer_id=card.customer_id,
        account_type="CURRENT",
        currency="BDT",
        available_balance=Decimal("20000.00"),
        ledger_balance=Decimal("20000.00"),
        account_status="ACTIVE",
        institution_id=card.institution_id,
    )
    db_session.add(curr_acct)
    db_session.flush()

    # Link CURRENT account to the card
    db_session.add(
        CardAccount(
            card_id=card.id,
            account_id=curr_acct.id,
            account_role="SECONDARY",
            currency="BDT",
            priority=2,
            status="ACTIVE",
        )
    )
    db_session.commit()

    # Transaction 1: DE3 = 0100100 (digits 3-4 = 01 -> Current/Checking account requested)
    res_curr = proc.process_transaction({
        "transaction_code": "10",
        "mti": "0200",
        "test_clear_pin_helper": "1234",
        "fields": {
            "2": card.test_pan_reference,
            "3": "0100100",  # 010 (tran code) + 01 (From Checking) + 00 (To Unspecified)
            "4": "000000050000",  # 500.00 BDT
            "11": "400001",
            "37": "000099000001",
            "41": "ATM01",
            "49": "050",
        },
    })
    assert res_curr["response_code"] == "00"
    tx_curr = db_session.query(Transaction).filter(Transaction.id == res_curr["transaction_id"]).first()
    assert tx_curr.account_id == curr_acct.id

    # Transaction 2: DE3 = 0101100 (digits 3-4 = 11 -> Savings account requested)
    res_sav = proc.process_transaction({
        "transaction_code": "10",
        "mti": "0200",
        "test_clear_pin_helper": "1234",
        "fields": {
            "2": card.test_pan_reference,
            "3": "0101100",  # 010 (tran code) + 11 (From Savings) + 00 (To Unspecified)
            "4": "000000050000",  # 500.00 BDT
            "11": "400002",
            "37": "000099000002",
            "41": "ATM01",
            "49": "050",
        },
    })
    assert res_sav["response_code"] == "00"
    tx_sav = db_session.query(Transaction).filter(Transaction.id == res_sav["transaction_id"]).first()
    assert tx_sav.account_id == primary_acct.id
