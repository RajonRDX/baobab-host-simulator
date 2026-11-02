"""
test_step08_authorizer_rules.py — Tests for Step 8 Safe AST Rules Engine
"""

import os
import pytest
from decimal import Decimal
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import AuthorizerRule, Card, Transaction
from app.rules_evaluator import SafeAstEvaluator, SafeEvalError, build_rule_context
from app.host_engine import HostTransactionProcessor
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


def test_safe_ast_evaluator_valid_expressions():
    ctx = {
        "trancode": "10",
        "amount": 25000.0,
        "institution": {"code": "IFIC", "name": "IFIC Bank"},
        "card_status": "ACTIVE",
        "bin": "456789"
    }

    # Match test
    assert SafeAstEvaluator.evaluate('trancode == "10" and amount > 20000', ctx) is True
    assert SafeAstEvaluator.evaluate('institution.code == "IFIC"', ctx) is True
    assert SafeAstEvaluator.evaluate('bin in ["456789", "512345"]', ctx) is True

    # No match test
    assert SafeAstEvaluator.evaluate('amount > 50000', ctx) is False
    assert SafeAstEvaluator.evaluate('card_status != "ACTIVE"', ctx) is False


def test_safe_ast_evaluator_rejects_unsafe_operations():
    ctx = {"amount": 100}
    with pytest.raises(SafeEvalError):
        # Forbidden function calls
        SafeAstEvaluator.evaluate('__import__("os").system("echo 1")', ctx)

    with pytest.raises(SafeEvalError):
        # Forbidden attribute execution
        SafeAstEvaluator.evaluate('amount.__class__.__mro__', ctx)


def test_authorizer_rule_declines_transaction_in_host_engine(db_session):
    # Create a rule rejecting transactions with amount > 10,000 with RC 61
    rule = AuthorizerRule(
        rule_code="TEST_MAX_10K",
        name="Decline over 10K",
        priority=10,
        expression="amount > 10000",
        action="DECLINE",
        response_code="61",
        message="Transaction exceeds custom authorizer rule threshold",
        enabled=True,
    )
    db_session.add(rule)
    db_session.commit()

    proc = HostTransactionProcessor(db_session)
    res = proc.process_transaction({
        "transaction_code": "10",
        "mti": "0200",
        "test_clear_pin_helper": "1234",
        "fields": {
            "2": "4567890123450001",
            "3": "0100000",
            "4": "000001500000",  # 15,000 BDT > 10,000 threshold
            "11": "700001",
            "37": "000099700001",
            "41": "ATM01",
            "49": "050",
        },
    })
    assert res["response_code"] == "61"
    assert res["authorization_status"] == "DECLINED"

    db_session.refresh(rule)
    assert rule.hit_count >= 1
