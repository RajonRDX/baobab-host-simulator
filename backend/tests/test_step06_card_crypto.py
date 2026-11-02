"""
test_step06_card_crypto.py — Tests for Step 6 Luhn Generation, Visa PVV, CVV, and PIN Change
"""

import os
import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Card, PinProfile
from app.card_crypto_service import (
    calculate_cvv_detailed,
    calculate_luhn_check_digit,
    calculate_visa_pvv_detailed,
    generate_luhn_pan,
    pack_pin_block_detailed,
    validate_luhn,
)
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


def test_luhn_generation_and_validation():
    pan = generate_luhn_pan("456789", 16)
    assert pan.startswith("456789")
    assert len(pan) == 16
    assert validate_luhn(pan) is True
    # Invalidate check digit
    bad_pan = pan[:-1] + str((int(pan[-1]) + 1) % 10)
    assert validate_luhn(bad_pan) is False


def test_visa_pvv_calculation():
    # Test known vector
    res = calculate_visa_pvv_detailed("4567890123450001", "1234", "1", "PVK_VISA_01")
    assert len(res["calculated_pvv"]) == 4
    assert res["calculated_pvv"].isdigit()


def test_cvv_derivation():
    res = calculate_cvv_detailed("4567890123450001", "2812", "101")
    assert len(res["calculated_cvv"]) == 3
    assert res["calculated_cvv"].isdigit()


def test_iso0_pin_block_packing():
    res = pack_pin_block_detailed("1234", "4567890123450001", "ISO_0")
    assert len(res["encrypted_pin_block"]) == 16
    assert len(res["clear_pin_block"]) == 16


def test_card_pin_change_endpoint(client, db_session):
    card = db_session.query(Card).first()
    pin_prof_before = card.pin_profile.pin_offset_reference

    # Change PIN to 4321
    res = client.post(f"/api/cards/{card.id}/pin", json={"new_pin": "4321"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "updated"
    assert data["new_pvv"] != pin_prof_before

    db_session.refresh(card.pin_profile)
    assert card.pin_profile.pin_offset_reference == data["new_pvv"]
    assert card.pin_profile.retry_counter == 0
