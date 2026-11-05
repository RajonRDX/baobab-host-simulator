"""
test_simulator_workbench.py - Tests for the upgraded simulator workbench:
last STAN / RRN lookup and saved simulator cases.
"""

import os

import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.host_engine import HostTransactionProcessor
from app.main import app
from app.security import create_access_token
from app.seed_data import seed_initial_data
from app.simulator_workbench_router import increment_trailing_number


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


def _atm(rrn, stan):
    return {
        "mti": "0200",
        "transaction_code": "10",
        "test_clear_pin_helper": "1234",
        "fields": {
            "2": "4567890123450001",
            "3": "0100000",
            "4": "000000100000",
            "11": stan,
            "37": rrn,
            "41": "ATM01",
            "49": "050",
        },
    }


def test_increment_trailing_number_keeps_width():
    assert increment_trailing_number("100023", "x") == "100024"
    assert increment_trailing_number("000020526009", "x") == "000020526010"
    assert increment_trailing_number("ABC0099", "x") == "ABC0100"
    assert increment_trailing_number("ABC", "x") == "ABC"
    assert increment_trailing_number("", "fallback") == "fallback"


def test_next_ids_follow_the_last_transaction(client, db_session):
    HostTransactionProcessor(db_session).process_transaction(_atm("000088800041", "880041"))
    data = client.get("/api/simulator-workbench/next-ids").json()
    assert data["has_history"] is True
    assert data["last_stan"] == "880041"
    assert data["last_rrn"] == "000088800041"
    assert data["next_stan"] == "880042"
    assert data["next_rrn"] == "000088800042"


def test_saved_case_lifecycle(client):
    body = {
        "name": "ATM withdrawal",
        "description": "baseline",
        "mti": "0200",
        "transaction_code": "10",
        "clear_pin_helper": "1234",
        "fields": {"2": "4567890123450001", "11": "100001"},
        "enabled_fields": {"2": True, "11": True},
    }
    created = client.post("/api/simulator-workbench/cases", json=body)
    assert created.status_code == 200
    case_id = created.json()["id"]

    # same name without overwrite is rejected, with overwrite it replaces the case
    assert client.post("/api/simulator-workbench/cases", json=body).status_code == 409
    replaced = client.post("/api/simulator-workbench/cases", json=dict(body, description="v2", overwrite=True))
    assert replaced.json()["id"] == case_id and replaced.json()["description"] == "v2"

    listing = client.get("/api/simulator-workbench/cases").json()
    assert [c["name"] for c in listing] == ["ATM withdrawal"]
    assert listing[0]["fields"]["11"] == "100001"

    updated = client.put(
        f"/api/simulator-workbench/cases/{case_id}",
        json=dict(body, name="ATM withdrawal v2", fields={"2": "4567890123450001", "11": "100002"}),
    )
    assert updated.status_code == 200 and updated.json()["fields"]["11"] == "100002"

    assert client.delete(f"/api/simulator-workbench/cases/{case_id}").status_code == 200
    assert client.get(f"/api/simulator-workbench/cases/{case_id}").status_code == 404
