"""
test_step05_search_and_pagination.py — Tests for Step 5 Search and Pagination
"""

import os
import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Customer, Card, Account, Transaction
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


def test_customer_pagination_and_search(client, db_session):
    # Test search by partial name
    res = client.get("/api/customers?q=Tariq&page=1&page_size=10")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert data["total"] >= 1
    assert any("Tariq" in c["first_name"] for c in data["items"])


def test_card_search_by_partial_pan_and_status(client, db_session):
    # Test search by partial PAN digits "0003" (which is seeded as BLOCKED)
    res = client.get("/api/cards?pan=0003&status=BLOCKED")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert data["total"] == 1
    assert data["items"][0]["card_status"] == "BLOCKED"


def test_transaction_journal_filtering(client, db_session):
    # Create test transactions
    from app.host_engine import HostTransactionProcessor
    proc = HostTransactionProcessor(db_session)
    proc.process_transaction({
        "transaction_code": "10",
        "mti": "0200",
        "test_clear_pin_helper": "1234",
        "fields": {
            "2": "4567890123450001",
            "3": "0100000",
            "4": "000000250000",
            "11": "555001",
            "37": "000099555001",
            "41": "ATM01",
            "49": "050",
        },
    })

    # Search by STAN
    res_stan = client.get("/api/transactions?stan=555001")
    assert res_stan.status_code == 200
    data_stan = res_stan.json()
    assert data_stan["total"] == 1
    assert data_stan["items"][0]["stan"] == "555001"

    # Search by Amount range (2,000 to 3,000)
    res_amt = client.get("/api/transactions?min_amount=2000&max_amount=3000")
    assert res_amt.status_code == 200
    assert res_amt.json()["total"] >= 1
