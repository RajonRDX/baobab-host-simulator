"""
test_step07_log_portal.py — Tests for Step 7 Correlation Trace & Crypto Event Logging
"""

import os
import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import ApiAuditLog, CryptoEvent
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


def test_correlation_id_header_injected(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert "X-Correlation-ID" in res.headers
    assert res.headers["X-Correlation-ID"].startswith("CORR-")


def test_transaction_generates_granular_crypto_events(client, db_session):
    # Submit transaction with PIN verification
    res = client.post("/api/simulator/submit", json={
        "transaction_code": "10",
        "mti": "0200",
        "test_clear_pin_helper": "1234",
        "fields": {
            "2": "4567890123450001",
            "3": "0100000",
            "4": "000000100000",
            "11": "600001",
            "37": "000099600001",
            "41": "ATM01",
            "49": "050",
        },
    })
    assert res.status_code == 200
    corr_id = res.headers.get("X-Correlation-ID")

    # Verify granular 6-step crypto events recorded in database
    events = db_session.query(CryptoEvent).filter(CryptoEvent.operation_type == "VISA_PVV_VERIFY").all()
    assert len(events) >= 5
    step_names = [e.step_name for e in events]
    assert "INGEST_PIN_BLOCK" in step_names
    assert "DES3_DECRYPT_ISO0" in step_names
    assert "EXTRACT_CLEAR_PIN" in step_names
    assert "CONSTRUCT_TSP" in step_names
    assert "COMPARE_PVV" in step_names


def test_log_timeline_endpoint(client, db_session):
    res = client.get("/api/logs/timeline")
    assert res.status_code == 200
    data = res.json()
    assert "events" in data
    assert isinstance(data["events"], list)
