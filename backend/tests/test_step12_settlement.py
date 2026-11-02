"""
test_step12_settlement.py — Tests for Step 12 Clearing, Daily Settlement & Reconciliation
"""

import os
import pytest
from decimal import Decimal
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import SettlementBatch, SettlementEntry, SettlementPosition, Transaction
from app.settlement_service import calculate_fees, execute_daily_cutover, get_reconciliation_summary
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


def test_calculate_fees():
    # ATM withdrawal fee check
    atm_fees = calculate_fees(Decimal("2500.00"), "10", "ITCL")
    assert atm_fees["interchange_fee"] == Decimal("15.00")
    assert atm_fees["scheme_fee"] == Decimal("2.50")

    # POS purchase percentage fee check (1.5% interchange)
    pos_fees = calculate_fees(Decimal("10000.00"), "40", "ITCL")
    assert pos_fees["interchange_fee"] == Decimal("150.00")


def test_execute_daily_cutover(db_session):
    # 1. Submit an approved transaction
    proc = HostTransactionProcessor(db_session)
    res = proc.process_transaction({
        "transaction_code": "10",
        "mti": "0200",
        "test_clear_pin_helper": "1234",
        "fields": {
            "2": "4567890123450001",
            "3": "0100000",
            "4": "000000200000",  # 2,000.00 BDT
            "11": "800001",
            "37": "000099800001",
            "41": "ATM01",
            "49": "050",
        },
    })
    assert res["response_code"] == "00"

    # 2. Execute cutover
    cutover = execute_daily_cutover(db_session, "ITCL", "test_admin")
    assert cutover["status"] == "CLOSED"
    assert cutover["total_transactions"] >= 1
    assert cutover["total_amount"] >= 2000.0

    # 3. Verify database records
    batch = db_session.query(SettlementBatch).filter(SettlementBatch.id == cutover["batch_id"]).first()
    assert batch is not None

    positions = db_session.query(SettlementPosition).filter(SettlementPosition.batch_id == batch.id).all()
    assert len(positions) >= 1


def test_reconciliation_endpoint(client, db_session):
    res = client.get("/api/settlement/reconciliation")
    assert res.status_code == 200
    data = res.json()
    assert "total_approved_transactions" in data
    assert "reconciliation_status" in data
