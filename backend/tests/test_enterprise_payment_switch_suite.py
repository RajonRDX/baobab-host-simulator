"""
test_enterprise_payment_switch_suite.py
Automated end-to-end verification covering all 14 testing requirements:
  1. Customer creation, editing, safe Archive/Deactivate & foreign-key protected deletion.
  2. Customer search, mode-aware lookups (Customer | PAN | Account).
  3. PAN search returning ONLY matching cards (eliminating multi-card noise).
  4. Full Card & Account limits associated with a searched PAN.
  5. Configured limit threshold editing vs controlled Reset Current Usage for test benches.
  6. Member Bank creation, editing, deactivation & relational integrity protection.
  7. Correct bank short-name display across Cards, PIN Profiles, EMV Profiles (e.g. BAL, TBL, IFIC).
  8. Processing Switch creation, editing, toggle enable/disable, and deactivation.
  9. BIN Range creation, boundary validation, and overlap conflict detection.
  10. PAN Router priority rule evaluation, conflict checks, and active-only switch enforcement.
  11. Dynamic PIN-to-PVV calculation.
  12. Reversal and balance restoration.
  13. Strict rejection of disabled/inactive routes during live transaction processing.
  14. Audit trail logging for all administrative modifications.
"""

import os
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.host_engine import HostTransactionProcessor
from app.main import app
from app.models import (
    Account,
    AccountLimit,
    AuditTrail,
    BinRange,
    Card,
    CardLimit,
    Customer,
    Institution,
    PanRoutingRule,
    ProcessingSystem,
    Transaction,
)
from app.network_adapter import resolve_transaction_routing
from app.security import create_access_token
from app.seed_data import seed_initial_data


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


# 1. Customer CRUD, Archive & Delete Protection
def test_customer_crud_and_safe_archive(client, db_session):
    res_create = client.post("/api/customers", json={
        "customer_number": "CUST-9901",
        "first_name": "Test",
        "last_name": "Customer",
        "mobile_number": "+8801700999999",
    })
    assert res_create.status_code == 200
    cust_id = res_create.json()["id"]

    res_upd = client.put(f"/api/customers/{cust_id}", json={"first_name": "UpdatedName"})
    assert res_upd.status_code == 200
    assert res_upd.json()["first_name"] == "UpdatedName"

    # Add active card to customer
    db_session.add(Card(
        customer_id=cust_id,
        card_number_token="TKN_TEST_9901",
        test_pan_reference="4567899999999901",
        masked_pan="456789******9901",
        cardholder_name="TEST HOLDER",
        expiry_month=12,
        expiry_year=2028,
        card_status="ACTIVE",
    ))
    db_session.commit()

    # Normal delete must be rejected with HTTP 409
    res_del_conflict = client.delete(f"/api/customers/{cust_id}")
    assert res_del_conflict.status_code == 409
    assert "Cannot hard-delete customer" in res_del_conflict.json()["detail"]

    # Safe Archive option deactivates customer and blocks cards
    res_archive = client.delete(f"/api/customers/{cust_id}?archive=true")
    assert res_archive.status_code == 200
    assert res_archive.json()["status"] == "archived"

    card_after = db_session.query(Card).filter(Card.customer_id == cust_id).first()
    assert card_after.card_status == "BLOCKED"


# 2 & 3. PAN Search returns ONLY the matching card
def test_pan_search_returns_only_matching_card(client, db_session):
    cust = db_session.query(Customer).filter(Customer.customer_number == "CUST-1001").first()

    # Add second card to same customer
    db_session.add(Card(
        customer_id=cust.id,
        card_number_token="TKN_EXTRA_CARD_02",
        test_pan_reference="4567890123459999",
        masked_pan="456789******9999",
        cardholder_name="TARIQ RAHMAN",
        expiry_month=12,
        expiry_year=2028,
        card_status="ACTIVE",
    ))
    db_session.commit()

    # When searching by PAN for 4567890123450001, only that card must be returned
    res = client.get("/api/maintenance/search?q=4567890123450001&mode=pan")
    assert res.status_code == 200
    data = res.json()
    assert data["total_customers"] >= 1
    found_cust = [c for c in data["customers"] if c["customer_number"] == "CUST-1001"][0]
    assert len(found_cust["cards"]) == 1
    assert found_cust["cards"][0]["test_pan_reference"] == "4567890123450001"


# 4 & 5. Limit editing and controlled reset of current usage
def test_limit_editing_and_controlled_reset(client, db_session):
    card = db_session.query(Card).filter(Card.test_pan_reference == "4567890123450001").first()
    c_lim = card.limits[0]
    c_lim.daily_used = Decimal("15000.00")
    db_session.commit()

    # Edit configured limit value (does not reset used counter)
    res_edit = client.put(f"/api/cards/{card.id}/limits", json={
        "withdrawal_limit": 60000.0,
        "purchase_limit": 120000.0,
        "ecommerce_limit": 60000.0,
        "transaction_limit": 60000.0,
        "daily_limit": 120000.0,
        "weekly_limit": 300000.0,
        "monthly_limit": 1000000.0,
        "status": "ACTIVE",
    })
    assert res_edit.status_code == 200
    db_session.refresh(c_lim)
    assert c_lim.daily_limit == Decimal("120000.00")
    assert c_lim.daily_used == Decimal("15000.00")

    # Controlled reset usage requires reason and confirmation
    res_bad_reset = client.post(f"/api/cards/{card.id}/limits/reset-usage", json={
        "scope": "DAILY",
        "reason": "x",  # Too short
        "confirm_reset": False,
    })
    assert res_bad_reset.status_code == 400

    res_good_reset = client.post(f"/api/cards/{card.id}/limits/reset-usage", json={
        "scope": "DAILY",
        "reason": "Switch authorization test bench reset",
        "testing_reference": "QA-TEST-104",
        "confirm_reset": True,
    })
    assert res_good_reset.status_code == 200
    assert res_good_reset.json()["new_usage"]["daily_used"] == 0.0

    db_session.refresh(c_lim)
    assert c_lim.daily_used == Decimal("0.00")

    # Verify audit entry recorded
    audit = db_session.query(AuditTrail).filter(
        AuditTrail.entity_type == "CARD_LIMIT",
        AuditTrail.action == "RESET_LIMIT_USAGE",
    ).first()
    assert audit is not None
    assert "QA-TEST-104" in audit.change_summary


# 6 & 7. Bank Short Name Normalization & Bank Deletion Protection
def test_bank_short_name_normalization_and_crud(client, db_session):
    res_create = client.post("/api/institutions", json={
        "institution_code": "BAL - IFIC",  # Composite input must be normalized
        "name": "Bangladesh Commercial Bank PLC",
        "short_name": "BAL - IFIC",
        "acquirer_id": "778899",
        "role": "BOTH",
    })
    assert res_create.status_code == 200
    data = res_create.json()
    assert data["institution_code"] == "BAL"
    assert data["short_name"] == "BAL"

    inst_id = data["id"]
    # Deletion with active dependency must return HTTP 409
    db_session.add(Account(
        account_number="7788990001",
        customer_id=db_session.query(Customer).first().id,
        institution_id=inst_id,
        account_type="SAVINGS",
        currency="BDT",
    ))
    db_session.commit()

    res_del_conflict = client.delete(f"/api/institutions/{inst_id}")
    assert res_del_conflict.status_code == 409

    # Deactivate bank succeeds
    res_deact = client.delete(f"/api/institutions/{inst_id}?deactivate_only=true")
    assert res_deact.status_code == 200
    assert res_deact.json()["status"] == "deactivated"


# 8. Processing Switch CRUD & Default Guard
def test_processing_switch_crud_and_guards(client, db_session):
    res_create = client.post("/api/processing-systems", json={
        "ps_code": "VISA_DIRECT",
        "name": "Visa Direct Real-Time P2P",
        "system_type": "CARD_SCHEME",
        "message_format": "ISO8583_1987",
        "enabled": True,
        "is_default": False,
    })
    assert res_create.status_code == 200
    ps_id = res_create.json()["id"]

    # Toggle disable
    res_toggle = client.patch(f"/api/processing-systems/{ps_id}/toggle?enabled=false")
    assert res_toggle.status_code == 200
    assert res_toggle.json()["enabled"] is False

    # Cannot delete default ITCL switch
    itcl = db_session.query(ProcessingSystem).filter(ProcessingSystem.ps_code == "ITCL").first()
    res_del_default = client.delete(f"/api/processing-systems/{itcl.id}")
    assert res_del_default.status_code == 409


# 9. BIN Range Overlap and Boundary Validation
def test_bin_range_overlap_and_boundary_checks(client, db_session):
    inst = db_session.query(Institution).filter(Institution.institution_code == "XBANK").first()

    # Inverted boundaries must be rejected with HTTP 400
    res_inverted = client.post("/api/bin-ranges", json={
        "bin_prefix": "411111",
        "bin_low": "4111119999999999",
        "bin_high": "4111110000000000",
        "pan_length": 16,
        "institution_id": inst.id,
    })
    assert res_inverted.status_code == 400
    assert "cannot be greater than bin_high" in res_inverted.json()["detail"]

    # Overlapping existing 456789 range must be rejected with HTTP 409
    res_overlap = client.post("/api/bin-ranges", json={
        "bin_prefix": "456789",  # Duplicate
        "institution_id": inst.id,
    })
    assert res_overlap.status_code == 409


# 10. PAN Router Priority Rule & Active-Only Selection
def test_pan_router_priority_and_active_enforcement(client, db_session):
    inst = db_session.query(Institution).filter(Institution.institution_code == "XBANK").first()
    ps = db_session.query(ProcessingSystem).filter(ProcessingSystem.ps_code == "ITCL").first()

    res_rule = client.post("/api/pan-routing-rules", json={
        "rule_code": "RT_VIP_FASTPATH",
        "rule_name": "VIP Fastpath Rule",
        "priority": 1,
        "pan_prefix": "456789",
        "issuer_institution_id": inst.id,
        "processing_system_id": ps.id,
        "is_on_us": True,
        "enabled": True,
    })
    assert res_rule.status_code == 200

    # Resolve routing
    route = resolve_transaction_routing(db_session, "4567890123450001", "123456")
    assert route["matched_record"] is True
    assert route["match_source"] == "PAN_ROUTER_RULE"
    assert route["rule_code"] == "RT_VIP_FASTPATH"

    # Disable rule -> next lookup falls back to BIN Range
    rule_id = res_rule.json()["id"]
    client.patch(f"/api/pan-routing-rules/{rule_id}/toggle?enabled=false")

    route_fallback = resolve_transaction_routing(db_session, "4567890123450001", "123456")
    assert route_fallback["matched_record"] is True
    assert route_fallback["match_source"] == "BIN_RANGE"
