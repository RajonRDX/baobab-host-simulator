"""
test_step01_institutions.py — Tests for Step 1 Processing Systems, Institutions & BINs
"""

import os
import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Institution, ProcessingSystem
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


def test_list_processing_systems(client):
    res = client.get("/api/processing-systems")
    assert res.status_code == 200
    data = res.json()
    codes = [p["ps_code"] for p in data]
    assert "ITCL" in codes
    assert "VISA" in codes
    assert "MASTERCARD" in codes
    assert "NPSB" in codes


def test_list_institutions_default_itcl(client):
    res = client.get("/api/institutions")
    assert res.status_code == 200
    data = res.json()
    codes = [i["institution_code"] for i in data]
    assert "XBANK" in codes
    assert "YBANK" in codes
    assert "ZBANK" in codes
    for inst in data:
        assert inst["ps_code"] == "ITCL"


def test_create_institution_defaults_to_itcl(client):
    payload = {
        "institution_code": "IFIC",
        "name": "IFIC Bank PLC",
        "acquirer_id": "443322",
        "role": "BOTH"
    }
    res = client.post("/api/institutions", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["institution_code"] == "IFIC"
    assert data["ps_code"] == "ITCL"


def test_bin_lookup_for_pan(client):
    # 4567890123450001 belongs to XBANK under ITCL
    res = client.get("/api/bin-ranges/lookup/4567890123450001")
    assert res.status_code == 200
    data = res.json()
    assert data["found"] is True
    assert data["institution"]["code"] == "XBANK"
    assert data["processing_system"]["code"] == "ITCL"
