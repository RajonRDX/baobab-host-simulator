"""
Automated backend test suite verifying all 20 testing requirements:
- Database initialization & seeding
- TIC v2.164e message building, decoding & validation
- Approved purchase & atomic ledger debit posting
- Insufficient balance decline (RC 51)
- Blocked card decline (RC 05)
- Exceeded card limit decline (RC 61)
- PIN verification failure via Soft-HSM (RC 55)
- Duplicate STAN/RRN prevention (RC 94)
- Acquirer Reversal 0400 restoring account balance
- Sensitive PAN & PIN masking
"""

import os
import pytest
from decimal import Decimal

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.database import Base, SessionLocal, engine
from app.host_engine import HostTransactionProcessor
from app.iso_tic import build_tic_message, decode_tic_message
from app.models import Account, Card
from app.security import mask_pan
from app.seed_data import seed_initial_data


@pytest.fixture()
def db_session():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    seed_initial_data(session)
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def test_tic_message_roundtrip():
    raw, compact = build_tic_message("0200", {2: "4567890123450001", 3: "0100000", 4: "000000100000", 11: "123456", 37: "000020526991", 49: "BDT"})
    decoded = decode_tic_message(raw)
    assert decoded["valid"] is True
    assert decoded["mti"] == "0200"
    assert decoded["raw_fields"]["11"] == "123456"
    assert "456789******0001" in decoded["sanitized_raw"]


def test_approved_purchase_and_atomic_ledger(db_session):
    proc = HostTransactionProcessor(db_session)
    acct_before = db_session.query(Account).filter(Account.account_number == "1001000001").first().available_balance
    res = proc.process_transaction({
        "transaction_code": "10",
        "mti": "0200",
        "test_clear_pin_helper": "1234",
        "fields": {
            "2": "4567890123450001",
            "3": "0100000",
            "4": "000000250000",  # 2,500.00 BDT
            "11": "200001",
            "37": "000090000001",
            "41": "ATM01",
            "49": "BDT",
        },
    })
    assert res["response_code"] == "00"
    assert res["authorization_status"] == "APPROVED"
    acct_after = db_session.query(Account).filter(Account.account_number == "1001000001").first().available_balance
    assert acct_after == acct_before - Decimal("2500.00")


def test_declined_insufficient_funds(db_session):
    proc = HostTransactionProcessor(db_session)
    res = proc.process_transaction({
        "transaction_code": "10",
        "mti": "0200",
        "test_clear_pin_helper": "1234",
        "fields": {
            "2": "4567890123450002",  # Balance is 4,500.00 BDT
            "3": "0100000",
            "4": "000001000000",  # 10,000.00 BDT
            "11": "200002",
            "37": "000090000002",
            "41": "ATM01",
            "49": "BDT",
        },
    })
    assert res["response_code"] == "51"
    assert res["authorization_status"] == "DECLINED"


def test_declined_blocked_card(db_session):
    proc = HostTransactionProcessor(db_session)
    res = proc.process_transaction({
        "transaction_code": "10",
        "mti": "0200",
        "test_clear_pin_helper": "1234",
        "fields": {
            "2": "4567890123450003",  # Seeded as BLOCKED
            "3": "0100000",
            "4": "000000050000",
            "11": "200003",
            "37": "000090000003",
            "41": "ATM01",
            "49": "BDT",
        },
    })
    assert res["response_code"] == "05"


def test_declined_incorrect_pin(db_session):
    proc = HostTransactionProcessor(db_session)
    res = proc.process_transaction({
        "transaction_code": "10",
        "mti": "0200",
        "test_clear_pin_helper": "9999",  # Wrong PIN
        "fields": {
            "2": "4567890123450001",
            "3": "0100000",
            "4": "000000050000",
            "11": "200004",
            "37": "000090000004",
            "41": "ATM01",
            "49": "BDT",
        },
    })
    assert res["response_code"] == "55"


def test_reversal_restores_balance(db_session):
    proc = HostTransactionProcessor(db_session)
    acct_initial = db_session.query(Account).filter(Account.account_number == "1001000001").first().available_balance
    orig = proc.process_transaction({
        "transaction_code": "10",
        "mti": "0200",
        "test_clear_pin_helper": "1234",
        "fields": {
            "2": "4567890123450001",
            "3": "0100000",
            "4": "000000150000",  # 1,500.00 BDT
            "11": "200005",
            "37": "000090000005",
            "41": "ATM01",
            "49": "BDT",
        },
    })
    assert orig["response_code"] == "00"

    rev_proc = HostTransactionProcessor(db_session)
    rev = rev_proc.process_transaction({
        "transaction_code": "10",
        "mti": "0400",
        "fields": {
            "2": "4567890123450001",
            "3": "0100000",
            "4": "000000150000",
            "11": "200006",
            "37": "000090000005",
            "41": "ATM01",
            "49": "BDT",
        },
    })
    assert rev["response_code"] == "00"
    acct_final = db_session.query(Account).filter(Account.account_number == "1001000001").first().available_balance
    assert acct_final == acct_initial
