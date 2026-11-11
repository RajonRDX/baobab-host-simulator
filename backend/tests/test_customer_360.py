import os
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Card, CardLimit, AccountLimit, Customer, Transaction, PinProfile, CardProfile
from app.models_limits_profiles import LimitUsageRecord, AuthProfileLimitAssignment, LimitDefinition
from app.limit_engine import compute_reset_window
from app.seed_data import seed_initial_data
from app.security import create_access_token
from app.config import settings


@pytest.fixture()
def db_session():
    Base.metadata.create_all(bind=engine)
    # other test modules (e.g. the LMK provider switch test) leave settings.HSM_MODE on EXTERNAL: pin it for these tests
    previous_mode = settings.HSM_MODE
    settings.HSM_MODE = "SOFT_HSM_LOCAL"
    session = SessionLocal()
    seed_initial_data(session)
    yield session
    session.close()
    settings.HSM_MODE = previous_mode
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session):
    with TestClient(app) as c:
        token = create_access_token(subject=settings.ADMIN_USERNAME)
        c.headers = {"Authorization": f"Bearer {token}"}
        yield c


def _card_with_profile(db):
    card = db.query(Card).first()
    cp = db.query(CardProfile).filter(CardProfile.profile_code == "VISA_CLASSIC").first()
    card.card_profile_id = cp.id
    db.commit()
    return card


def test_customer_extra_fields_roundtrip_and_search(client, db_session):
    cust = db_session.query(Customer).first()
    r = client.put(f"/api/customers/{cust.id}", json={
        "father_name": "Abdul Karim", "mother_name": "Rahima Begum", "date_of_birth": "1990-05-17",
        "nid_number": "1990123456789", "passport_number": "BK0123456", "passport_expiry_date": "2032-01-31",
        "address": "House 12, Road 5, Dhanmondi", "city": "Dhaka", "gender": "MALE",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["father_name"] == "Abdul Karim" and body["nid_number"] == "1990123456789"

    # search by NID finds the customer and returns every new field + dob + email + mobile
    s = client.get("/api/maintenance/search", params={"q": "1990123456789", "mode": "customer"}).json()
    assert s["total_customers"] == 1
    c = s["customers"][0]
    for k in ("father_name", "mother_name", "date_of_birth", "nid_number", "passport_number",
              "passport_expiry_date", "email", "mobile_number", "city", "kyc_status"):
        assert k in c
    assert c["date_of_birth"] == "1990-05-17" and c["passport_expiry_date"] == "2032-01-31"

    # create a customer with the new fields
    r = client.post("/api/customers", json={
        "customer_number": "CUST-NEW-1", "first_name": "Rajon", "mother_name": "M", "nid_number": "123",
    })
    assert r.status_code == 200, r.text
    assert r.json()["mother_name"] == "M"


def test_limits_360_reset_and_edit(client, db_session):
    card = _card_with_profile(db_session)
    c_lim = db_session.query(CardLimit).filter(CardLimit.card_id == card.id).first()
    c_lim.daily_used = Decimal("4000.00"); c_lim.weekly_used = Decimal("9000.00")
    ca = card.card_accounts[0]
    a_lim = db_session.query(AccountLimit).filter(AccountLimit.account_id == ca.account_id).first()
    a_lim.daily_used = Decimal("2500.00")
    # profile usage record for limit 100 (DAILY card limit)
    ldef = db_session.query(LimitDefinition).filter(LimitDefinition.limit_code == "100").first()
    key, ws, we = compute_reset_window("DAILY")
    db_session.add(LimitUsageRecord(scope="CARD", target_entity_id=card.id, limit_definition_id=ldef.id,
                                    window_key=key, window_start=ws, window_end=we,
                                    consumed_amount=Decimal("7500.00"), consumed_count=3))
    db_session.commit()

    res = client.get(f"/api/maintenance/card/{card.id}/limits")
    assert res.status_code == 200, res.text
    data = res.json()
    legacy_daily = next(r for r in data["legacy"]["card"]["rows"] if r["key"] == "daily_limit")
    assert legacy_daily["used"] == 4000.0 and legacy_daily["max"] > 0 and legacy_daily["percent"] is not None
    acct_daily = next(r for r in data["legacy"]["accounts"][0]["rows"] if r["key"] == "daily_limit")
    assert acct_daily["used"] == 2500.0
    assert data["profile"]["info"]["auth_profile_code"] == "VISA_CLASSIC_STANDARD"
    prof = next(r for r in data["profile"]["rows"] if r["limit_code"] == "100")
    assert prof["used"] == 7500.0 and prof["remaining"] == prof["max"] - 7500.0 and prof["resets_at"]

    # edit profile max (override on the assignment) then verify
    r = client.put(f"/api/maintenance/profile-limit/{prof['assignment_id']}/max", json={"maximum_limit": "123456.50"})
    assert r.status_code == 200 and r.json()["maximum_limit_override"] == 123456.5
    again = client.get(f"/api/maintenance/card/{card.id}/limits").json()
    assert next(x for x in again["profile"]["rows"] if x["limit_code"] == "100")["max"] == 123456.5

    # edit legacy thresholds (partial)
    r = client.patch(f"/api/maintenance/card/{card.id}/legacy-limits", json={"daily_limit": "55000", "status": "ACTIVE"})
    assert r.status_code == 200
    r = client.patch(f"/api/maintenance/account/{ca.account_id}/legacy-limits", json={"per_transaction_limit": "9999"})
    assert r.status_code == 200
    assert client.patch(f"/api/maintenance/card/{card.id}/legacy-limits", json={"daily_limit": "-5"}).status_code == 400

    # reset only DAILY legacy counters (weekly must stay)
    r = client.post(f"/api/maintenance/card/{card.id}/limits/reset", json={"target": "LEGACY", "period": "DAILY", "reason": "unit test"})
    assert r.status_code == 200, r.text
    db_session.expire_all()
    c_lim = db_session.query(CardLimit).filter(CardLimit.card_id == card.id).first()
    assert c_lim.daily_used == 0 and c_lim.weekly_used == Decimal("9000.00")
    # profile usage untouched by a LEGACY reset
    assert db_session.query(LimitUsageRecord).first().consumed_amount == Decimal("7500.00")

    # reset profile usage
    r = client.post(f"/api/maintenance/card/{card.id}/limits/reset", json={"target": "PROFILE", "reason": "unit test"})
    assert r.status_code == 200 and r.json()["profile_records_reset"] >= 1
    db_session.expire_all()
    assert db_session.query(LimitUsageRecord).first().consumed_amount == 0

    # validation
    assert client.post(f"/api/maintenance/card/{card.id}/limits/reset", json={"target": "X", "reason": "abc"}).status_code == 400
    assert client.post(f"/api/maintenance/card/{card.id}/limits/reset", json={"target": "ALL", "reason": "a"}).status_code == 422


def test_card_without_auth_profile_has_note(client, db_session):
    card = db_session.query(Card).first()  # seed card resolves PROF_DOM_STD which has no auth profile
    data = client.get(f"/api/maintenance/card/{card.id}/limits").json()
    assert data["profile"]["rows"] == [] and data["profile"]["info"]["note"]


def test_edit_card_expiry_recalculates_cvv(client, db_session):
    card = db_session.query(Card).first()
    before = db_session.query(PinProfile).filter(PinProfile.card_id == card.id).first().cvv_reference
    r = client.put(f"/api/maintenance/card/{card.id}", json={"expiry_month": 3, "expiry_year": 2031, "cardholder_name": "rajon test"})
    assert r.status_code == 200, r.text
    assert r.json()["expiry_month"] == 3 and r.json()["expiry_year"] == 2031 and r.json()["cvv_regenerated"] is True
    db_session.expire_all()
    c2 = db_session.query(Card).filter(Card.id == card.id).first()
    assert (c2.expiry_month, c2.expiry_year, c2.cardholder_name) == (3, 2031, "RAJON TEST")
    after = db_session.query(PinProfile).filter(PinProfile.card_id == card.id).first().cvv_reference
    assert after and after != before
    # past expiry is allowed (to test expired-card declines)
    assert client.put(f"/api/maintenance/card/{card.id}", json={"expiry_month": 1, "expiry_year": 2020}).status_code == 200
    assert client.put(f"/api/maintenance/card/{card.id}", json={"expiry_month": 13}).status_code == 422


def test_issue_card_with_custom_expiry_and_generate_test_card(client, db_session):
    cust = db_session.query(Customer).first()
    acct = cust.accounts[0]
    r = client.post("/api/cards", json={
        "customer_id": cust.id, "test_pan_reference": "4567890123459999", "cardholder_name": "Custom Exp",
        "expiry_month": 7, "expiry_year": 2035, "linked_account_id": acct.id, "pin": "4321"})
    assert r.status_code == 200, r.text
    assert (r.json()["expiry_month"], r.json()["expiry_year"]) == (7, 2035)
    r = client.post("/api/cards/generate-test-card", json={"bin_prefix": "456789", "expiry_month": 9, "expiry_year": 2033})
    assert r.status_code == 200, r.text
    assert (r.json()["expiry_month"], r.json()["expiry_year"]) == (9, 2033)
    r = client.post("/api/cards/generate-test-card", json={"bin_prefix": "456789"})
    assert r.json()["expiry_year"] == datetime.now(timezone.utc).year + 3


def test_transactions_endpoint(client, db_session):
    card = db_session.query(Card).first()
    cust = card.customer
    now = datetime.now(timezone.utc)
    for i, rc in enumerate(["00", "51", "00"]):
        db_session.add(Transaction(
            transaction_reference=f"T360-{i}", mti="0200", processing_code="010000", transaction_code="010",
            stan=f"00000{i}", rrn=f"RRN00000000{i}", masked_pan=card.masked_pan, card_id=card.id,
            customer_id=cust.id, transaction_amount=Decimal("100.00") * (i + 1), billing_amount=Decimal("100.00"),
            currency="BDT", transaction_datetime=now.replace(microsecond=i), response_code=rc,
            response_message="x", authorization_status="APPROVED" if rc == "00" else "DECLINED"))
    # a declined attempt that has no card_id but the same masked PAN must still be listed
    db_session.add(Transaction(
        transaction_reference="T360-orphan", mti="0200", processing_code="010000", stan="000099", rrn="RRN000000099",
        masked_pan=card.masked_pan, transaction_amount=Decimal("5.00"), billing_amount=Decimal("5.00"),
        currency="BDT", response_code="14", response_message="Invalid card", authorization_status="DECLINED"))
    db_session.commit()
    d = client.get("/api/maintenance/transactions", params={"card_id": card.id, "limit": 10}).json()
    assert d["total"] == 4 and d["summary"]["approved"] == 2 and d["summary"]["declined"] == 2
    assert d["items"][0]["reference"].startswith("T360") and "amount" in d["items"][0]
    assert client.get("/api/maintenance/transactions", params={"customer_id": cust.id}).status_code == 200
    assert client.get("/api/maintenance/transactions", params={"account_id": card.card_accounts[0].account_id}).status_code == 200
    assert client.get("/api/maintenance/transactions").status_code == 400
    assert client.get("/api/maintenance/transactions", params={"card_id": "nope"}).status_code == 404
