"""
test_step11_routing.py — Tests for Step 11 On-Us/Off-Us Routing & Network Simulators
"""

import os
import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import BinRange, NetworkProfile
from app.network_adapter import SimulatedNetworkAdapter, resolve_transaction_routing
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


def test_on_us_routing_resolution(db_session):
    # 456789 is seeded as On-Us under XBANK / ITCL
    route = resolve_transaction_routing(db_session, "4567890123450001")
    assert route["is_on_us"] is True
    assert route["routing_target"] == "ON_US_HOST"


def test_off_us_network_routing_and_simulation(db_session):
    # Register an Off-Us Visa BIN 411111
    from app.models import Institution, ProcessingSystem
    xbank = db_session.query(Institution).first()
    visa_ps = db_session.query(ProcessingSystem).filter(ProcessingSystem.ps_code == "VISA").first()

    db_session.add(
        BinRange(
            bin_prefix="411111",
            bin_low="4111110000000000",
            bin_high="4111119999999999",
            institution_id=xbank.id,
            processing_system_id=visa_ps.id,
            card_product="VISA_EXTERNAL",
            scheme="VISA",
            is_on_us=False,
        )
    )
    # Ensure NetworkProfile for VISA exists
    if not db_session.query(NetworkProfile).filter(NetworkProfile.network_name == "VISA_SCHEME").first():
        db_session.add(
            NetworkProfile(
                network_name="VISA_SCHEME",
                network_type="CARD_SCHEME",
                enabled=True,
                simulation_mode="ALWAYS_APPROVE",
                simulated_response_code="00",
            )
        )
    db_session.commit()

    # Route PAN 4111110123450001
    route = resolve_transaction_routing(db_session, "4111110123450001")
    assert route["is_on_us"] is False
    assert route["destination_network"] == "VISA_SCHEME"

    # Execute simulation
    adapter = SimulatedNetworkAdapter(db_session, "VISA_SCHEME")
    resp = adapter.route_transaction({"pan": "4111110123450001", "fields": {}})
    assert resp["network_status"] == "APPROVED"
    assert resp["response_code"] == "00"


def test_network_timeout_triggers_reversal_requirement(db_session):
    adapter = SimulatedNetworkAdapter(db_session, "VISA_TIMEOUT_TEST")
    # Add profile configured for TIMEOUT
    db_session.add(
        NetworkProfile(
            network_name="VISA_TIMEOUT_TEST",
            network_type="CARD_SCHEME",
            enabled=True,
            simulation_mode="TIMEOUT",
        )
    )
    db_session.commit()

    resp = adapter.route_transaction({"pan": "4111110123450001", "fields": {}})
    assert resp["network_status"] == "TIMEOUT"
    assert resp["response_code"] == "91"
    assert resp["requires_reversal"] is True
