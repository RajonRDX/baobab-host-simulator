"""
backend/tests/test_step13_limits_and_profiles.py
=================================================
Comprehensive Automated Pytest Suite for Advanced Card Limits, Account Limits,
BIN-to-Card-Profile Association, Authorization Profiles, Transaction Code Permissions,
Limit Calculation Engine, Idempotent Consumption, and Reversal Restoration.
"""

from decimal import Decimal
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.host_engine import HostTransactionProcessor
from app.limit_engine import LimitCalculationEngine, compare_decimal_values, compute_reset_window
from app.models import (
    Account,
    AuthorizationProfile,
    AuthProfileLimitAssignment,
    AuthProfileTxCodePermission,
    BinRange,
    Card,
    CardProfile,
    Customer,
    Institution,
    LimitDefinition,
    LimitTransactionConsumption,
    LimitUsageRecord,
    ProcessingSystem,
    TransactionCode,
    TxCodeLimitImpact,
)
from app.seed_limits_profiles import seed_limits_and_authorization_profiles


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionTesting = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionTesting()

    # Seed basic processing systems & institutions
    ps = ProcessingSystem(ps_code="ITCL", name="ITCL Host Switch", system_type="HOST_SWITCH", enabled=True)
    session.add(ps)
    session.flush()

    inst = Institution(
        institution_code="XBANK",
        name="xBank PLC",
        acquirer_id="123456",
        processing_system_id=ps.id,
        status="ACTIVE",
    )
    session.add(inst)
    session.flush()

    # Seed TransactionCodes
    tc_pur = TransactionCode(
        transaction_code="10",
        transaction_name="ATM Cash Withdrawal",
        processing_code="0100000",
        financial_flag=True,
        debit_flag=True,
        active=True,
    )
    tc_pos = TransactionCode(
        transaction_code="40",
        transaction_name="POS Purchase",
        processing_code="0000000",
        financial_flag=True,
        debit_flag=True,
        active=True,
    )
    tc_bi = TransactionCode(
        transaction_code="30",
        transaction_name="Balance Inquiry",
        processing_code="3000000",
        financial_flag=False,
        balance_inquiry_flag=True,
        active=True,
    )
    session.add_all([tc_pur, tc_pos, tc_bi])
    session.flush()

    # Seed BIN Range
    br = BinRange(
        bin_prefix="456789",
        bin_low="4567890000000000",
        bin_high="4567899999999999",
        pan_length=16,
        institution_id=inst.id,
        processing_system_id=ps.id,
        card_type="DEBIT",
        card_product="VISA_DEBIT_CLASSIC",
        scheme="VISA",
        status="ACTIVE",
    )
    session.add(br)
    session.flush()

    # Seed Customer & Account
    cust = Customer(customer_number="CUST-001", first_name="Mehedi", last_name="Rajon", institution_id=inst.id)
    session.add(cust)
    session.flush()

    acct = Account(
        account_number="ACC-XBANK-001",
        customer_id=cust.id,
        account_type="SAVINGS",
        currency="BDT",
        available_balance=Decimal("500000.00"),
        ledger_balance=Decimal("500000.00"),
        account_status="ACTIVE",
        institution_id=inst.id,
    )
    session.add(acct)
    session.flush()

    # Seed Card
    card = Card(
        customer_id=cust.id,
        card_number_token="TOKEN-PAN-001",
        test_pan_reference="4567890123450001",
        masked_pan="456789******0001",
        cardholder_name="MEHEDI HASAN RAJON",
        expiry_month=12,
        expiry_year=2028,
        card_type="DEBIT",
        card_product="VISA_CLASSIC",
        card_status="ACTIVE",
        linked_account_id=acct.id,
        institution_id=inst.id,
    )
    session.add(card)
    session.flush()

    # Run full limits & auth profiles seed
    seed_limits_and_authorization_profiles(session)

    yield session
    session.close()


def test_comparison_operators():
    assert compare_decimal_values(Decimal("11000.00"), ">", Decimal("10000.00")) is True
    assert compare_decimal_values(Decimal("10000.00"), ">", Decimal("10000.00")) is False
    assert compare_decimal_values(Decimal("10000.00"), ">=", Decimal("10000.00")) is True
    assert compare_decimal_values(Decimal("9999.00"), "<=", Decimal("10000.00")) is True
    assert compare_decimal_values(Decimal("10000.00"), "=", Decimal("10000.00")) is True
    assert compare_decimal_values(Decimal("5000.00"), "!=", Decimal("10000.00")) is True


def test_reset_windows():
    dt = datetime(2026, 11, 8, 14, 30, 0, tzinfo=timezone.utc)
    key_d, start_d, end_d = compute_reset_window("DAILY", dt)
    assert key_d == "DAILY:2026-11-08"
    assert start_d.isoformat() == "2026-11-08T00:00:00+00:00"
    assert end_d.isoformat() == "2026-11-09T00:00:00+00:00"

    key_w, start_w, end_w = compute_reset_window("WEEKLY", dt)
    assert key_w.startswith("WEEKLY:")
    assert (end_w - start_w).days == 7


def test_card_profile_and_auth_profile_inheritance(db_session):
    card = db_session.query(Card).filter(Card.test_pan_reference == "4567890123450001").first()
    engine = LimitCalculationEngine(db_session)

    # 1. BIN Resolution
    matched_bin = engine.resolve_bin_for_pan(card.test_pan_reference)
    assert matched_bin is not None
    assert matched_bin.bin_prefix == "456789"

    # 2. Card Profile Inheritance
    bin_range, card_prof = engine.resolve_card_profile(card)
    assert bin_range is not None
    assert card_prof is not None
    assert card_prof.profile_code == "VISA_CLASSIC"

    # 3. Authorization Profile Resolution
    auth_prof = engine.resolve_authorization_profile(card_prof)
    assert auth_prof is not None
    assert auth_prof.auth_profile_code == "VISA_CLASSIC_STANDARD"


def test_authorization_pipeline_limit_exceeded(db_session):
    card = db_session.query(Card).filter(Card.test_pan_reference == "4567890123450001").first()
    account = db_session.query(Account).filter(Account.id == card.linked_account_id).first()

    processor = HostTransactionProcessor(db_session)
    # Transaction amount 150,000 BDT exceeds card daily limit (100,000 BDT) or per-tx limit
    req = {
        "transaction_code": "10",
        "mti": "0200",
        "test_clear_pin_helper": "1234",
        "fields": {
            "2": card.test_pan_reference,
            "3": "0100000",
            "4": "000015000000",  # 150,000.00 BDT
            "11": "990001",
            "32": "123456",
            "37": "990000000001",
            "41": "ATM01",
            "49": "BDT",
        },
    }
    res = processor.process_transaction(req)
    assert res["authorization_status"] == "DECLINED"
    assert res["response_code"] == "61"  # Exceeds limit


def test_approved_transaction_consumes_usage_and_reversal_restores(db_session):
    card = db_session.query(Card).filter(Card.test_pan_reference == "4567890123450001").first()
    account = db_session.query(Account).filter(Account.id == card.linked_account_id).first()
    engine = LimitCalculationEngine(db_session)

    # 1. Initial usage should be 0
    ldef = db_session.query(LimitDefinition).filter(LimitDefinition.limit_code == "100").first()
    prev_val, win_key, _ = engine.get_current_limit_value(ldef, target_entity_id=card.id)
    assert prev_val == Decimal("0.00")

    # 2. Execute Approved Transaction (Amount 10,000 BDT)
    processor = HostTransactionProcessor(db_session)
    req = {
        "transaction_code": "10",
        "mti": "0200",
        "test_clear_pin_helper": "1234",
        "fields": {
            "2": card.test_pan_reference,
            "3": "0100000",
            "4": "000001000000",  # 10,000.00 BDT
            "11": "990002",
            "32": "123456",
            "37": "990000000002",
            "41": "ATM01",
            "49": "BDT",
        },
    }
    res = processor.process_transaction(req)
    assert res["authorization_status"] == "APPROVED"
    assert res["response_code"] == "00"

    # 3. Verify usage incremented by 10,000
    new_val, _, _ = engine.get_current_limit_value(ldef, target_entity_id=card.id)
    assert new_val == Decimal("10000.00")

    # 4. Execute Reversal (MTI 0400, matching RRN 990000000002)
    rev_req = {
        "transaction_code": "10",
        "mti": "0400",
        "fields": {
            "2": card.test_pan_reference,
            "3": "0100000",
            "4": "000001000000",
            "11": "990003",
            "32": "123456",
            "37": "990000000002",
            "41": "ATM01",
            "49": "BDT",
        },
    }
    rev_res = processor.process_transaction(rev_req)
    assert rev_res["authorization_status"] == "APPROVED"

    # 5. Verify usage restored back to 0.00
    restored_val, _, _ = engine.get_current_limit_value(ldef, target_entity_id=card.id)
    assert restored_val == Decimal("0.00")

    # 6. Verify idempotent reversal: repeated reversal does not decrement usage below 0
    rev_res_dup = processor.process_transaction(rev_req)
    # Original transaction already marked reversed, so lookup fails with RC 15
    assert rev_res_dup["response_code"] == "15"
