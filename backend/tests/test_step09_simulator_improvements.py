"""
test_step09_simulator_improvements.py — Tests for Step 9 Dual-Codec Parser & Persistent State
"""

import os
import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.database import Base, SessionLocal, engine
from app.main import app
from app.iso_standard_codec import build_iso8583_1987, decode_iso8583_1987
from app.iso_tic import build_tic_message
from app.seed_data import seed_initial_data
from app.security import create_access_token
from app.config import settings


@pytest.fixture()
def client():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    seed_initial_data(db)
    db.close()
    with TestClient(app) as c:
        token = create_access_token(subject=settings.ADMIN_USERNAME)
        c.headers = {"Authorization": f"Bearer {token}"}
        yield c
    Base.metadata.drop_all(bind=engine)


def test_standard_iso8583_pack_and_unpack():
    fields = {
        2: "4567890123450001",
        3: "010000",
        4: "000000100000",
        11: "123456",
        37: "000020526991",
        41: "ATM00001",
        49: "050"
    }
    raw = build_iso8583_1987("0200", fields)
    assert raw.startswith("0200")
    
    decoded = decode_iso8583_1987(raw)
    assert decoded["valid"] is True
    assert decoded["format"] == "ISO8583_1987"
    assert decoded["mti"] == "0200"
    assert decoded["raw_fields"]["2"] == "4567890123450001"
    assert decoded["raw_fields"]["11"] == "123456"
    assert decoded["derived_transaction_code"] == "01"


def test_parse_raw_endpoint_detects_tic_v2164e(client):
    # TIC message starts with A4M
    tic_raw, _ = build_tic_message("0200", {2: "4567890123450001", 3: "0100000", 4: "000000100000", 11: "998877", 49: "BDT"})
    res = client.post("/api/simulator/parse-raw", json={"raw_message": tic_raw})
    assert res.status_code == 200
    data = res.json()
    assert data["format"] == "TIC_V2164E"
    assert data["mti"] == "0200"
    assert data["fields"]["11"] == "998877"


def test_parse_raw_endpoint_detects_standard_iso8583(client):
    # Standard ISO message starts with 0200 + hex bitmap
    iso_raw = build_iso8583_1987("0200", {2: "4567890123450002", 3: "010000", 4: "000000250000", 11: "334455"})
    res = client.post("/api/simulator/parse-raw", json={"raw_message": iso_raw})
    assert res.status_code == 200
    data = res.json()
    assert data["format"] == "ISO8583_1987"
    assert data["mti"] == "0200"
    assert data["fields"]["2"] == "4567890123450002"
    assert data["fields"]["11"] == "334455"
