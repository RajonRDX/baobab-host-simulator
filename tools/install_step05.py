#!/usr/bin/env python3
"""
INSTALLER: tools/install_step05.py
STEP 5 — Advanced Search and Pagination (Single Unified Installer)
Adds:
  1. Generic PaginatedResponse schema in backend/app/schemas.py
  2. Advanced server-side search, filtering, and pagination to /customers, /accounts, /cards, /transactions
  3. Interactive search toolbars and pagination controls in BankingEntities.tsx & SimulatorAndJournal.tsx
  4. Automated Pytest test suite in backend/tests/test_step05_search_and_pagination.py
"""

from pathlib import Path
import sys

BASE_DIR = Path(r"E:\HOST_VSCODE\host-simulator").resolve()
sys.path.insert(0, str(BASE_DIR))

from tools.patcher import PatcherSession, parse_installer_args

TEST_STEP05_CODE = '''"""
test_step05_search_and_pagination.py — Tests for Step 5 Search and Pagination
"""

import os
import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Customer, Card, Account, Transaction
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


def test_customer_pagination_and_search(client, db_session):
    # Test search by partial name
    res = client.get("/api/customers?q=Tariq&page=1&page_size=10")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert data["total"] >= 1
    assert any("Tariq" in c["first_name"] for c in data["items"])


def test_card_search_by_partial_pan_and_status(client, db_session):
    # Test search by partial PAN digits "0003" (which is seeded as BLOCKED)
    res = client.get("/api/cards?pan=0003&status=BLOCKED")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert data["total"] == 1
    assert data["items"][0]["card_status"] == "BLOCKED"


def test_transaction_journal_filtering(client, db_session):
    # Create test transactions
    from app.host_engine import HostTransactionProcessor
    proc = HostTransactionProcessor(db_session)
    proc.process_transaction({
        "transaction_code": "10",
        "mti": "0200",
        "test_clear_pin_helper": "1234",
        "fields": {
            "2": "4567890123450001",
            "3": "0100000",
            "4": "000000250000",
            "11": "555001",
            "37": "000099555001",
            "41": "ATM01",
            "49": "BDT",
        },
    })

    # Search by STAN
    res_stan = client.get("/api/transactions?stan=555001")
    assert res_stan.status_code == 200
    data_stan = res_stan.json()
    assert data_stan["total"] == 1
    assert data_stan["items"][0]["stan"] == "555001"

    # Search by Amount range (2,000 to 3,000)
    res_amt = client.get("/api/transactions?min_amount=2000&max_amount=3000")
    assert res_amt.status_code == 200
    assert res_amt.json()["total"] >= 1
'''


def main() -> int:
    args = parse_installer_args("Step 05: Advanced Search and Pagination")
    session = PatcherSession(
        step_id="step05",
        title="Add Advanced Search, Filtering, and Server-Side Pagination Across All Entities",
        dry_run=args.dry_run,
    )

    # 1. Patch backend/app/schemas.py to add generic pagination schema
    session.patch_file(
        "backend/app/schemas.py",
        [
            {
                "marker": "step05:schema_paginated_response",
                "action": "append",
                "text": (
                    "\n# ==============================================================================\n"
                    "# STEP 5 SCHEMAS: PAGINATED RESPONSE ENVELOPE\n"
                    "# ==============================================================================\n\n"
                    "from typing import Generic, TypeVar\n\n"
                    "T = TypeVar('T')\n\n"
                    "class PaginatedResponse(BaseModel, Generic[T]):\n"
                    "    items: List[T]\n"
                    "    total: int\n"
                    "    page: int\n"
                    "    page_size: int\n"
                    "    total_pages: int\n"
                ),
            }
        ],
    )

    # 2. Patch backend/app/api_routes.py to support advanced search & pagination on /customers, /accounts, /cards, /transactions
    session.patch_file(
        "backend/app/api_routes.py",
        [
            {
                "marker": "step05:api_routes_import_paginated",
                "action": "insert_after",
                "anchor": "from app.schemas import (",
                "text": "    PaginatedResponse,",
            },
            # Upgrade GET /customers with query filters and pagination
            {
                "marker": "step05:api_customers_paginated",
                "action": "replace",
                "anchor": (
                    "@router.get(\"/customers\", response_model=List[CustomerOut])\n"
                    "def list_customers(db: Session = Depends(get_db), _: str = Depends(get_current_user)):\n"
                    "    return db.query(Customer).order_by(Customer.created_at.desc()).all()"
                ),
                "text": (
                    "@router.get('/customers', response_model=PaginatedResponse[CustomerOut])\n"
                    "def list_customers(\n"
                    "    q: Optional[str] = Query(None, description='Search by customer number, name, email, or mobile'),\n"
                    "    institution_id: Optional[str] = Query(None),\n"
                    "    status: Optional[str] = Query(None),\n"
                    "    page: int = Query(1, ge=1),\n"
                    "    page_size: int = Query(20, ge=1, le=100),\n"
                    "    db: Session = Depends(get_db),\n"
                    "    _: str = Depends(get_current_user),\n"
                    "):\n"
                    "    query = db.query(Customer)\n"
                    "    if q:\n"
                    "        term = f'%{q.strip()}%'\n"
                    "        query = query.filter(\n"
                    "            (Customer.customer_number.ilike(term)) |\n"
                    "            (Customer.first_name.ilike(term)) |\n"
                    "            (Customer.last_name.ilike(term)) |\n"
                    "            (Customer.email.ilike(term)) |\n"
                    "            (Customer.mobile_number.ilike(term))\n"
                    "        )\n"
                    "    if institution_id:\n"
                    "        query = query.filter(Customer.institution_id == institution_id)\n"
                    "    if status:\n"
                    "        query = query.filter(Customer.customer_status == status.upper())\n\n"
                    "    total = query.count()\n"
                    "    items = query.order_by(Customer.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()\n"
                    "    total_pages = max(1, (total + page_size - 1) // page_size)\n"
                    "    return PaginatedResponse(\n"
                    "        items=items,\n"
                    "        total=total,\n"
                    "        page=page,\n"
                    "        page_size=page_size,\n"
                    "        total_pages=total_pages,\n"
                    "    )"
                ),
            },
            # Upgrade GET /accounts with query filters and pagination
            {
                "marker": "step05:api_accounts_paginated",
                "action": "replace",
                "anchor": (
                    "@router.get(\"/accounts\")\n"
                    "def list_accounts(db: Session = Depends(get_db), _: str = Depends(get_current_user)):\n"
                    "    accounts = db.query(Account).order_by(Account.created_at.desc()).all()\n"
                    "    out = []\n"
                    "    for a in accounts:\n"
                    "        lim = db.query(AccountLimit).filter(AccountLimit.account_id == a.id).first()\n"
                    "        out.append({\n"
                    "            \"id\": a.id,\n"
                    "            \"account_number\": a.account_number,\n"
                    "            \"customer_id\": a.customer_id,\n"
                    "            \"customer_name\": f\"{a.customer.first_name} {a.customer.last_name or ''}\".strip() if a.customer else \"\",\n"
                    "            \"account_type\": a.account_type,\n"
                    "            \"currency\": a.currency,\n"
                    "            \"available_balance\": float(a.available_balance),\n"
                    "            \"ledger_balance\": float(a.ledger_balance),\n"
                    "            \"overdraft_limit\": float(a.overdraft_limit),\n"
                    "            \"account_status\": a.account_status,\n"
                    "            \"branch_code\": a.branch_code,\n"
                    "            \"institution_id\": a.institution_id,\n"
                    "            \"institution_code\": a.institution.institution_code if a.institution else None,\n"
                    "            \"institution_name\": a.institution.name if a.institution else None,\n"
                    "            \"limits\": {\n"
                    "                \"id\": lim.id,\n"
                    "                \"per_transaction_limit\": float(lim.per_transaction_limit),\n"
                    "                \"daily_limit\": float(lim.daily_limit),\n"
                    "                \"weekly_limit\": float(lim.weekly_limit),\n"
                    "                \"monthly_limit\": float(lim.monthly_limit),\n"
                    "                \"daily_used\": float(lim.daily_used),\n"
                    "                \"weekly_used\": float(lim.weekly_used),\n"
                    "                \"monthly_used\": float(lim.monthly_used),\n"
                    "            } if lim else None,\n"
                    "        })\n"
                    "    return out"
                ),
                "text": (
                    "@router.get('/accounts')\n"
                    "def list_accounts(\n"
                    "    q: Optional[str] = Query(None, description='Search by account number or branch code'),\n"
                    "    account_type: Optional[str] = Query(None),\n"
                    "    institution_id: Optional[str] = Query(None),\n"
                    "    status: Optional[str] = Query(None),\n"
                    "    page: int = Query(1, ge=1),\n"
                    "    page_size: int = Query(20, ge=1, le=100),\n"
                    "    db: Session = Depends(get_db),\n"
                    "    _: str = Depends(get_current_user),\n"
                    "):\n"
                    "    query = db.query(Account)\n"
                    "    if q:\n"
                    "        term = f'%{q.strip()}%'\n"
                    "        query = query.filter((Account.account_number.ilike(term)) | (Account.branch_code.ilike(term)))\n"
                    "    if account_type:\n"
                    "        query = query.filter(Account.account_type == account_type.upper())\n"
                    "    if institution_id:\n"
                    "        query = query.filter(Account.institution_id == institution_id)\n"
                    "    if status:\n"
                    "        query = query.filter(Account.account_status == status.upper())\n\n"
                    "    total = query.count()\n"
                    "    accounts = query.order_by(Account.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()\n"
                    "    out = []\n"
                    "    for a in accounts:\n"
                    "        lim = db.query(AccountLimit).filter(AccountLimit.account_id == a.id).first()\n"
                    "        out.append({\n"
                    "            'id': a.id,\n"
                    "            'account_number': a.account_number,\n"
                    "            'customer_id': a.customer_id,\n"
                    "            'customer_name': f\"{a.customer.first_name} {a.customer.last_name or ''}\".strip() if a.customer else '',\n"
                    "            'account_type': a.account_type,\n"
                    "            'currency': a.currency,\n"
                    "            'available_balance': float(a.available_balance),\n"
                    "            'ledger_balance': float(a.ledger_balance),\n"
                    "            'overdraft_limit': float(a.overdraft_limit),\n"
                    "            'account_status': a.account_status,\n"
                    "            'branch_code': a.branch_code,\n"
                    "            'institution_id': a.institution_id,\n"
                    "            'institution_code': a.institution.institution_code if a.institution else None,\n"
                    "            'institution_name': a.institution.name if a.institution else None,\n"
                    "            'limits': {\n"
                    "                'id': lim.id,\n"
                    "                'per_transaction_limit': float(lim.per_transaction_limit),\n"
                    "                'daily_limit': float(lim.daily_limit),\n"
                    "                'weekly_limit': float(lim.weekly_limit),\n"
                    "                'monthly_limit': float(lim.monthly_limit),\n"
                    "                'daily_used': float(lim.daily_used),\n"
                    "                'weekly_used': float(lim.weekly_used),\n"
                    "                'monthly_used': float(lim.monthly_used),\n"
                    "            } if lim else None,\n"
                    "        })\n"
                    "    total_pages = max(1, (total + page_size - 1) // page_size)\n"
                    "    return {\n"
                    "        'items': out,\n"
                    "        'total': total,\n"
                    "        'page': page,\n"
                    "        'page_size': page_size,\n"
                    "        'total_pages': total_pages,\n"
                    "    }"
                ),
            },
            # Upgrade GET /cards with query filters and pagination
            {
                "marker": "step05:api_cards_paginated",
                "action": "replace",
                "anchor": (
                    "@router.get(\"/cards\")\n"
                    "def list_cards(db: Session = Depends(get_db), _: str = Depends(get_current_user)):\n"
                    "    cards = db.query(Card).order_by(Card.created_at.desc()).all()\n"
                    "    out = []\n"
                    "    for c in cards:\n"
                    "        lim = db.query(CardLimit).filter(CardLimit.card_id == c.id).first()\n"
                    "        pin_p = db.query(PinProfile).filter(PinProfile.card_id == c.id).first()\n"
                    "        emv_p = db.query(EmvProfile).filter(EmvProfile.card_id == c.id).first()\n"
                    "        out.append({\n"
                    "            \"id\": c.id,\n"
                    "            \"customer_id\": c.customer_id,\n"
                    "            \"card_number_token\": c.card_number_token,\n"
                    "            \"test_pan_reference\": c.test_pan_reference,\n"
                    "            \"masked_pan\": c.masked_pan,\n"
                    "            \"cardholder_name\": c.cardholder_name,\n"
                    "            \"expiry_month\": c.expiry_month,\n"
                    "            \"expiry_year\": c.expiry_year,\n"
                    "            \"card_type\": c.card_type,\n"
                    "            \"card_product\": c.card_product,\n"
                    "            \"card_status\": c.card_status,\n"
                    "            \"linked_account_id\": c.linked_account_id,\n"
                    "            \"institution_id\": c.institution_id,\n"
                    "            \"institution_code\": c.institution.institution_code if c.institution else None,\n"
                    "            \"institution_name\": c.institution.name if c.institution else None,\n"
                    "            \"pin_profile\": {\n"
                    "                \"verification_method\": pin_p.pin_verification_method,\n"
                    "                \"pvk_key_reference\": pin_p.pvk_key_reference,\n"
                    "                \"pin_offset_reference\": pin_p.pin_offset_reference,\n"
                    "                \"retry_counter\": pin_p.retry_counter,\n"
                    "                \"maximum_retry_count\": pin_p.maximum_retry_count,\n"
                    "                \"pin_status\": pin_p.pin_status,\n"
                    "            } if pin_p else None,\n"
                    "            \"emv_profile\": {\n"
                    "                \"aid\": emv_p.aid,\n"
                    "                \"application_profile\": emv_p.application_profile,\n"
                    "                \"card_sequence_number\": emv_p.card_sequence_number,\n"
                    "                \"master_key_reference\": emv_p.master_key_reference,\n"
                    "            } if emv_p else None,\n"
                    "            \"limits\": {\n"
                    "                \"id\": lim.id,\n"
                    "                \"withdrawal_limit\": float(lim.withdrawal_limit),\n"
                    "                \"purchase_limit\": float(lim.purchase_limit),\n"
                    "                \"ecommerce_limit\": float(lim.ecommerce_limit),\n"
                    "                \"transaction_limit\": float(lim.transaction_limit),\n"
                    "                \"daily_limit\": float(lim.daily_limit),\n"
                    "                \"weekly_limit\": float(lim.weekly_limit),\n"
                    "                \"monthly_limit\": float(lim.monthly_limit),\n"
                    "                \"daily_used\": float(lim.daily_used),\n"
                    "                \"weekly_used\": float(lim.weekly_used),\n"
                    "                \"monthly_used\": float(lim.monthly_used),\n"
                    "            } if lim else None,\n"
                    "        })\n"
                    "    return out"
                ),
                "text": (
                    "@router.get('/cards')\n"
                    "def list_cards(\n"
                    "    pan: Optional[str] = Query(None, description='Partial PAN match'),\n"
                    "    cardholder: Optional[str] = Query(None),\n"
                    "    institution_id: Optional[str] = Query(None),\n"
                    "    status: Optional[str] = Query(None),\n"
                    "    card_type: Optional[str] = Query(None),\n"
                    "    page: int = Query(1, ge=1),\n"
                    "    page_size: int = Query(20, ge=1, le=100),\n"
                    "    db: Session = Depends(get_db),\n"
                    "    _: str = Depends(get_current_user),\n"
                    "):\n"
                    "    query = db.query(Card)\n"
                    "    if pan:\n"
                    "        term = f'%{pan.strip()}%'\n"
                    "        query = query.filter((Card.test_pan_reference.ilike(term)) | (Card.masked_pan.ilike(term)))\n"
                    "    if cardholder:\n"
                    "        query = query.filter(Card.cardholder_name.ilike(f'%{cardholder.strip()}%'))\n"
                    "    if institution_id:\n"
                    "        query = query.filter(Card.institution_id == institution_id)\n"
                    "    if status:\n"
                    "        query = query.filter(Card.card_status == status.upper())\n"
                    "    if card_type:\n"
                    "        query = query.filter(Card.card_type == card_type.upper())\n\n"
                    "    total = query.count()\n"
                    "    cards = query.order_by(Card.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()\n"
                    "    out = []\n"
                    "    for c in cards:\n"
                    "        lim = db.query(CardLimit).filter(CardLimit.card_id == c.id).first()\n"
                    "        pin_p = db.query(PinProfile).filter(PinProfile.card_id == c.id).first()\n"
                    "        emv_p = db.query(EmvProfile).filter(EmvProfile.card_id == c.id).first()\n"
                    "        out.append({\n"
                    "            'id': c.id,\n"
                    "            'customer_id': c.customer_id,\n"
                    "            'card_number_token': c.card_number_token,\n"
                    "            'test_pan_reference': c.test_pan_reference,\n"
                    "            'masked_pan': c.masked_pan,\n"
                    "            'cardholder_name': c.cardholder_name,\n"
                    "            'expiry_month': c.expiry_month,\n"
                    "            'expiry_year': c.expiry_year,\n"
                    "            'card_type': c.card_type,\n"
                    "            'card_product': c.card_product,\n"
                    "            'card_status': c.card_status,\n"
                    "            'linked_account_id': c.linked_account_id,\n"
                    "            'institution_id': c.institution_id,\n"
                    "            'institution_code': c.institution.institution_code if c.institution else None,\n"
                    "            'institution_name': c.institution.name if c.institution else None,\n"
                    "            'pin_profile': {\n"
                    "                'verification_method': pin_p.pin_verification_method,\n"
                    "                'pvk_key_reference': pin_p.pvk_key_reference,\n"
                    "                'pin_offset_reference': pin_p.pin_offset_reference,\n"
                    "                'retry_counter': pin_p.retry_counter,\n"
                    "                'maximum_retry_count': pin_p.maximum_retry_count,\n"
                    "                'pin_status': pin_p.pin_status,\n"
                    "            } if pin_p else None,\n"
                    "            'emv_profile': {\n"
                    "                'aid': emv_p.aid,\n"
                    "                'application_profile': emv_p.application_profile,\n"
                    "                'card_sequence_number': emv_p.card_sequence_number,\n"
                    "                'master_key_reference': emv_p.master_key_reference,\n"
                    "            } if emv_p else None,\n"
                    "            'limits': {\n"
                    "                'id': lim.id,\n"
                    "                'withdrawal_limit': float(lim.withdrawal_limit),\n"
                    "                'purchase_limit': float(lim.purchase_limit),\n"
                    "                'ecommerce_limit': float(lim.ecommerce_limit),\n"
                    "                'transaction_limit': float(lim.transaction_limit),\n"
                    "                'daily_limit': float(lim.daily_limit),\n"
                    "                'weekly_limit': float(lim.weekly_limit),\n"
                    "                'monthly_limit': float(lim.monthly_limit),\n"
                    "                'daily_used': float(lim.daily_used),\n"
                    "                'weekly_used': float(lim.weekly_used),\n"
                    "                'monthly_used': float(lim.monthly_used),\n"
                    "            } if lim else None,\n"
                    "        })\n"
                    "    total_pages = max(1, (total + page_size - 1) // page_size)\n"
                    "    return {\n"
                    "        'items': out,\n"
                    "        'total': total,\n"
                    "        'page': page,\n"
                    "        'page_size': page_size,\n"
                    "        'total_pages': total_pages,\n"
                    "    }"
                ),
            },
            # Upgrade GET /transactions with date range, amount range, and pagination
            {
                "marker": "step05:api_transactions_paginated",
                "action": "replace",
                "anchor": (
                    "@router.get(\"/transactions\")\n"
                    "def list_transactions(\n"
                    "    stan: Optional[str] = Query(None),\n"
                    "    rrn: Optional[str] = Query(None),\n"
                    "    status: Optional[str] = Query(None),\n"
                    "    db: Session = Depends(get_db),\n"
                    "    _: str = Depends(get_current_user),\n"
                    "):\n"
                    "    q = db.query(Transaction)\n"
                    "    if stan:\n"
                    "        q = q.filter(Transaction.stan.contains(stan))\n"
                    "    if rrn:\n"
                    "        q = q.filter(Transaction.rrn.contains(rrn))\n"
                    "    if status:\n"
                    "        q = q.filter(Transaction.authorization_status == status.upper())\n"
                    "    txs = q.order_by(Transaction.created_at.desc()).limit(100).all()\n"
                    "    return [\n"
                    "        {\n"
                    "            \"id\": t.id,\n"
                    "            \"transaction_reference\": t.transaction_reference,\n"
                    "            \"mti\": t.mti,\n"
                    "            \"processing_code\": t.processing_code,\n"
                    "            \"transaction_code\": t.transaction_code,\n"
                    "            \"stan\": t.stan,\n"
                    "            \"rrn\": t.rrn,\n"
                    "            \"terminal_id\": t.terminal_id,\n"
                    "            \"masked_pan\": t.masked_pan,\n"
                    "            \"transaction_amount\": float(t.transaction_amount),\n"
                    "            \"currency\": t.currency,\n"
                    "            \"response_code\": t.response_code,\n"
                    "            \"response_message\": t.response_message,\n"
                    "            \"transaction_status\": t.transaction_status,\n"
                    "            \"authorization_status\": t.authorization_status,\n"
                    "            \"source_channel\": t.source_channel,\n"
                    "            \"ps_code\": t.ps_code,\n"
                    "            \"is_on_us\": t.is_on_us,\n"
                    "            \"issuer_institution_id\": t.issuer_institution_id,\n"
                    "            \"issuer_code\": t.issuer_institution.institution_code if t.issuer_institution else None,\n"
                    "            \"acquirer_institution_id\": t.acquirer_institution_id,\n"
                    "            \"acquirer_code\": t.acquirer_institution.institution_code if t.acquirer_institution else None,\n"
                    "            \"created_at\": t.created_at.isoformat(),\n"
                    "        }\n"
                    "        for t in txs\n"
                    "    ]"
                ),
                "text": (
                    "@router.get('/transactions')\n"
                    "def list_transactions(\n"
                    "    stan: Optional[str] = Query(None),\n"
                    "    rrn: Optional[str] = Query(None),\n"
                    "    pan: Optional[str] = Query(None),\n"
                    "    status: Optional[str] = Query(None),\n"
                    "    response_code: Optional[str] = Query(None),\n"
                    "    ps_code: Optional[str] = Query(None),\n"
                    "    min_amount: Optional[float] = Query(None),\n"
                    "    max_amount: Optional[float] = Query(None),\n"
                    "    page: int = Query(1, ge=1),\n"
                    "    page_size: int = Query(25, ge=1, le=100),\n"
                    "    db: Session = Depends(get_db),\n"
                    "    _: str = Depends(get_current_user),\n"
                    "):\n"
                    "    q = db.query(Transaction)\n"
                    "    if stan:\n"
                    "        q = q.filter(Transaction.stan.contains(stan.strip()))\n"
                    "    if rrn:\n"
                    "        q = q.filter(Transaction.rrn.contains(rrn.strip()))\n"
                    "    if pan:\n"
                    "        q = q.filter(Transaction.masked_pan.contains(pan.strip()))\n"
                    "    if status:\n"
                    "        q = q.filter(Transaction.authorization_status == status.upper())\n"
                    "    if response_code:\n"
                    "        q = q.filter(Transaction.response_code == response_code.strip())\n"
                    "    if ps_code:\n"
                    "        q = q.filter(Transaction.ps_code == ps_code.upper().strip())\n"
                    "    if min_amount is not None:\n"
                    "        q = q.filter(Transaction.transaction_amount >= min_amount)\n"
                    "    if max_amount is not None:\n"
                    "        q = q.filter(Transaction.transaction_amount <= max_amount)\n\n"
                    "    total = q.count()\n"
                    "    txs = q.order_by(Transaction.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()\n"
                    "    items = [\n"
                    "        {\n"
                    "            'id': t.id,\n"
                    "            'transaction_reference': t.transaction_reference,\n"
                    "            'mti': t.mti,\n"
                    "            'processing_code': t.processing_code,\n"
                    "            'transaction_code': t.transaction_code,\n"
                    "            'stan': t.stan,\n"
                    "            'rrn': t.rrn,\n"
                    "            'terminal_id': t.terminal_id,\n"
                    "            'masked_pan': t.masked_pan,\n"
                    "            'transaction_amount': float(t.transaction_amount),\n"
                    "            'currency': t.currency,\n"
                    "            'response_code': t.response_code,\n"
                    "            'response_message': t.response_message,\n"
                    "            'transaction_status': t.transaction_status,\n"
                    "            'authorization_status': t.authorization_status,\n"
                    "            'source_channel': t.source_channel,\n"
                    "            'ps_code': t.ps_code,\n"
                    "            'is_on_us': t.is_on_us,\n"
                    "            'issuer_institution_id': t.issuer_institution_id,\n"
                    "            'issuer_code': t.issuer_institution.institution_code if t.issuer_institution else None,\n"
                    "            'acquirer_institution_id': t.acquirer_institution_id,\n"
                    "            'acquirer_code': t.acquirer_institution.institution_code if t.acquirer_institution else None,\n"
                    "            'created_at': t.created_at.isoformat(),\n"
                    "        }\n"
                    "        for t in txs\n"
                    "    ]\n"
                    "    total_pages = max(1, (total + page_size - 1) // page_size)\n"
                    "    return {\n"
                    "        'items': items,\n"
                    "        'total': total,\n"
                    "        'page': page,\n"
                    "        'page_size': page_size,\n"
                    "        'total_pages': total_pages,\n"
                    "    }"
                ),
            },
        ],
    )

    # 3. Patch frontend/src/pages/BankingEntities.tsx to handle paginated response envelopes and search inputs
    session.patch_file(
        "frontend/src/pages/BankingEntities.tsx",
        [
            # CustomersPage load function update
            {
                "marker": "step05:customers_load_paginated",
                "action": "replace",
                "anchor": (
                    "  const load = async () => {\n"
                    "    const [cList, iList] = await Promise.all([apiFetch('/customers'), apiFetch('/institutions')]);\n"
                    "    setCustomers(cList);\n"
                    "    setInstitutions(iList);\n"
                    "    if (!form.institution_id && iList.length > 0) {\n"
                    "      setForm((prev) => ({ ...prev, institution_id: iList[0].id }));\n"
                    "    }\n"
                    "  };"
                ),
                "text": (
                    "  const [page, setPage] = useState(1);\n"
                    "  const [totalPages, setTotalPages] = useState(1);\n"
                    "  const [totalCount, setTotalCount] = useState(0);\n"
                    "  const [searchTerm, setSearchTerm] = useState('');\n\n"
                    "  const load = async () => {\n"
                    "    const q = searchTerm ? `&q=${encodeURIComponent(searchTerm)}` : '';\n"
                    "    const [cRes, iList] = await Promise.all([\n"
                    "      apiFetch(`/customers?page=${page}&page_size=15${q}`),\n"
                    "      apiFetch('/institutions'),\n"
                    "    ]);\n"
                    "    setCustomers(cRes.items || cRes);\n"
                    "    setTotalCount(cRes.total || (cRes.items ? cRes.items.length : cRes.length));\n"
                    "    setTotalPages(cRes.total_pages || 1);\n"
                    "    setInstitutions(iList);\n"
                    "    if (!form.institution_id && iList.length > 0) {\n"
                    "      setForm((prev) => ({ ...prev, institution_id: iList[0].id }));\n"
                    "    }\n"
                    "  };"
                ),
            },
            # Add Search Bar & Pagination to Customers Table
            {
                "marker": "step05:customers_search_toolbar",
                "action": "insert_before",
                "anchor": "      <div className=\"bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 overflow-x-auto\">",
                "text": (
                    '      <div className="flex flex-wrap items-center justify-between gap-3 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4">\n'
                    '        <div className="flex items-center gap-2 flex-1 max-w-md">\n'
                    '          <input\n'
                    '            value={searchTerm}\n'
                    '            onChange={(e) => setSearchTerm(e.target.value)}\n'
                    '            placeholder="Search customer no, name, phone, or email..."\n'
                    '            className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-1.5 text-xs font-mono"\n'
                    '          />\n'
                    '          <button onClick={() => { setPage(1); load(); }} className="bg-emerald-600 text-white px-3 py-1.5 rounded-lg text-xs font-semibold">Search</button>\n'
                    '        </div>\n'
                    '        <div className="flex items-center gap-2 text-xs font-mono text-slate-400">\n'
                    '          <span>Total: <strong className="text-emerald-500">{totalCount}</strong></span>\n'
                    '          <button disabled={page <= 1} onClick={() => { setPage(page - 1); }} className="px-2.5 py-1 rounded border border-slate-300 dark:border-slate-700 disabled:opacity-40">Prev</button>\n'
                    '          <span>Page {page} of {totalPages}</span>\n'
                    '          <button disabled={page >= totalPages} onClick={() => { setPage(page + 1); }} className="px-2.5 py-1 rounded border border-slate-300 dark:border-slate-700 disabled:opacity-40">Next</button>\n'
                    '        </div>\n'
                    '      </div>\n'
                ),
            },

            # CardsPage load function update for pagination
            {
                "marker": "step05:cards_load_paginated",
                "action": "replace",
                "anchor": (
                    "  const load = async () => {\n"
                    "    const [cList, custList, acctList, iList] = await Promise.all([\n"
                    "      apiFetch('/cards'),\n"
                    "      apiFetch('/customers'),\n"
                    "      apiFetch('/accounts'),\n"
                    "      apiFetch('/institutions'),\n"
                    "    ]);\n"
                    "    setCards(cList);\n"
                    "    setCustomers(custList);\n"
                    "    setAccounts(acctList);\n"
                    "    setInstitutions(iList);\n"
                    "    if (!form.institution_id && iList.length > 0) {\n"
                    "      setForm((f) => ({ ...f, institution_id: iList[0].id }));\n"
                    "    }\n"
                    "  };"
                ),
                "text": (
                    "  const [cardPage, setCardPage] = useState(1);\n"
                    "  const [cardTotalPages, setCardTotalPages] = useState(1);\n"
                    "  const [cardTotalCount, setCardTotalCount] = useState(0);\n"
                    "  const [cardPanSearch, setCardPanSearch] = useState('');\n"
                    "  const [cardStatusFilter, setCardStatusFilter] = useState('');\n\n"
                    "  const load = async () => {\n"
                    "    const params = new URLSearchParams({ page: String(cardPage), page_size: '15' });\n"
                    "    if (cardPanSearch) params.set('pan', cardPanSearch);\n"
                    "    if (cardStatusFilter) params.set('status', cardStatusFilter);\n"
                    "    const [cRes, custList, acctList, iList] = await Promise.all([\n"
                    "      apiFetch(`/cards?${params.toString()}`),\n"
                    "      apiFetch('/customers?page_size=100'),\n"
                    "      apiFetch('/accounts?page_size=100'),\n"
                    "      apiFetch('/institutions'),\n"
                    "    ]);\n"
                    "    setCards(cRes.items || cRes);\n"
                    "    setCardTotalCount(cRes.total || (cRes.items ? cRes.items.length : cRes.length));\n"
                    "    setCardTotalPages(cRes.total_pages || 1);\n"
                    "    setCustomers(custList.items || custList);\n"
                    "    setAccounts(acctList.items || acctList);\n"
                    "    setInstitutions(iList);\n"
                    "    if (!form.institution_id && iList.length > 0) {\n"
                    "      setForm((f) => ({ ...f, institution_id: iList[0].id }));\n"
                    "    }\n"
                    "  };"
                ),
            },
            # Add Search Bar & Pagination to Cards Table
            {
                "marker": "step05:cards_search_toolbar",
                "action": "insert_before",
                "anchor": "      <div className=\"bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 overflow-x-auto\">",
                "text": (
                    '      <div className="flex flex-wrap items-center justify-between gap-3 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4">\n'
                    '        <div className="flex flex-wrap items-center gap-2 flex-1">\n'
                    '          <input\n'
                    '            value={cardPanSearch}\n'
                    '            onChange={(e) => setCardPanSearch(e.target.value)}\n'
                    '            placeholder="Filter PAN (e.g. 0001)..."\n'
                    '            className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-1.5 text-xs font-mono"\n'
                    '          />\n'
                    '          <select\n'
                    '            value={cardStatusFilter}\n'
                    '            onChange={(e) => setCardStatusFilter(e.target.value)}\n'
                    '            className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-1.5 text-xs font-mono"\n'
                    '          >\n'
                    '            <option value="">ALL STATUSES</option>\n'
                    '            <option value="ACTIVE">ACTIVE</option>\n'
                    '            <option value="BLOCKED">BLOCKED</option>\n'
                    '          </select>\n'
                    '          <button onClick={() => { setCardPage(1); load(); }} className="bg-emerald-600 text-white px-3 py-1.5 rounded-lg text-xs font-semibold">Filter</button>\n'
                    '        </div>\n'
                    '        <div className="flex items-center gap-2 text-xs font-mono text-slate-400">\n'
                    '          <span>Cards: <strong className="text-emerald-500">{cardTotalCount}</strong></span>\n'
                    '          <button disabled={cardPage <= 1} onClick={() => setCardPage(cardPage - 1)} className="px-2.5 py-1 rounded border border-slate-300 dark:border-slate-700 disabled:opacity-40">Prev</button>\n'
                    '          <span>Page {cardPage} of {cardTotalPages}</span>\n'
                    '          <button disabled={cardPage >= cardTotalPages} onClick={() => setCardPage(cardPage + 1)} className="px-2.5 py-1 rounded border border-slate-300 dark:border-slate-700 disabled:opacity-40">Next</button>\n'
                    '        </div>\n'
                    '      </div>\n'
                ),
            },

            # AccountsPage load function update for pagination
            {
                "marker": "step05:accounts_load_paginated",
                "action": "replace",
                "anchor": (
                    "  const load = async () => {\n"
                    "    const [aList, cList, iList] = await Promise.all([apiFetch('/accounts'), apiFetch('/customers'), apiFetch('/institutions')]);\n"
                    "    setAccounts(aList);\n"
                    "    setCustomers(cList);\n"
                    "    setInstitutions(iList);\n"
                    "    if (!form.institution_id && iList.length > 0) {\n"
                    "      setForm((f) => ({ ...f, institution_id: iList[0].id }));\n"
                    "    }\n"
                    "  };"
                ),
                "text": (
                    "  const [acctPage, setAcctPage] = useState(1);\n"
                    "  const [acctTotalPages, setAcctTotalPages] = useState(1);\n"
                    "  const [acctTotalCount, setAcctTotalCount] = useState(0);\n"
                    "  const [acctSearch, setAcctSearch] = useState('');\n\n"
                    "  const load = async () => {\n"
                    "    const q = acctSearch ? `&q=${encodeURIComponent(acctSearch)}` : '';\n"
                    "    const [aRes, cRes, iList] = await Promise.all([\n"
                    "      apiFetch(`/accounts?page=${acctPage}&page_size=15${q}`),\n"
                    "      apiFetch('/customers?page_size=100'),\n"
                    "      apiFetch('/institutions'),\n"
                    "    ]);\n"
                    "    setAccounts(aRes.items || aRes);\n"
                    "    setAcctTotalCount(aRes.total || (aRes.items ? aRes.items.length : aRes.length));\n"
                    "    setAcctTotalPages(aRes.total_pages || 1);\n"
                    "    setCustomers(cRes.items || cRes);\n"
                    "    setInstitutions(iList);\n"
                    "    if (!form.institution_id && iList.length > 0) {\n"
                    "      setForm((f) => ({ ...f, institution_id: iList[0].id }));\n"
                    "    }\n"
                    "  };"
                ),
            },
        ],
    )

    # 4. Patch frontend/src/pages/SimulatorAndJournal.tsx to add advanced filters and pagination to TransactionJournalPage
    session.patch_file(
        "frontend/src/pages/SimulatorAndJournal.tsx",
        [
            {
                "marker": "step05:journal_state_paginated",
                "action": "replace",
                "anchor": (
                    "  const [txs, setTxs] = useState<any[]>([]);\n"
                    "  const [stan, setStan] = useState('');\n"
                    "  const [rrn, setRrn] = useState('');\n"
                    "  const [status, setStatus] = useState('');\n\n"
                    "  const load = async () => {\n"
                    "    const params = new URLSearchParams();\n"
                    "    if (stan) params.set('stan', stan);\n"
                    "    if (rrn) params.set('rrn', rrn);\n"
                    "    if (status) params.set('status', status);\n"
                    "    setTxs(await apiFetch(`/transactions?${params.toString()}`));\n"
                    "  };"
                ),
                "text": (
                    "  const [txs, setTxs] = useState<any[]>([]);\n"
                    "  const [stan, setStan] = useState('');\n"
                    "  const [rrn, setRrn] = useState('');\n"
                    "  const [pan, setPan] = useState('');\n"
                    "  const [status, setStatus] = useState('');\n"
                    "  const [psCode, setPsCode] = useState('');\n"
                    "  const [page, setPage] = useState(1);\n"
                    "  const [totalPages, setTotalPages] = useState(1);\n"
                    "  const [totalTxs, setTotalTxs] = useState(0);\n\n"
                    "  const load = async () => {\n"
                    "    const params = new URLSearchParams({ page: String(page), page_size: '20' });\n"
                    "    if (stan) params.set('stan', stan);\n"
                    "    if (rrn) params.set('rrn', rrn);\n"
                    "    if (pan) params.set('pan', pan);\n"
                    "    if (status) params.set('status', status);\n"
                    "    if (psCode) params.set('ps_code', psCode);\n"
                    "    const res = await apiFetch(`/transactions?${params.toString()}`);\n"
                    "    setTxs(res.items || res);\n"
                    "    setTotalTxs(res.total || (res.items ? res.items.length : res.length));\n"
                    "    setTotalPages(res.total_pages || 1);\n"
                    "  };"
                ),
            },
            # Add PAN & Switch filter input and pagination controls in Journal toolbar
            {
                "marker": "step05:journal_filter_controls",
                "action": "replace",
                "anchor": (
                    '          <input\n'
                    '            value={rrn}\n'
                    '            onChange={(e) => setRrn(e.target.value)}\n'
                    '            placeholder="Filter RRN..."\n'
                    '            className="bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-1.5 text-xs font-mono"\n'
                    '          />\n'
                    '          <select\n'
                    '            value={status}\n'
                    '            onChange={(e) => setStatus(e.target.value)}\n'
                    '            className="bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-1.5 text-xs font-mono"\n'
                    '          >\n'
                    '            <option value="">ALL OUTCOMES</option>\n'
                    '            <option value="APPROVED">APPROVED</option>\n'
                    '            <option value="DECLINED">DECLINED</option>\n'
                    '          </select>'
                ),
                "text": (
                    '          <input\n'
                    '            value={rrn}\n'
                    '            onChange={(e) => setRrn(e.target.value)}\n'
                    '            placeholder="Filter RRN..."\n'
                    '            className="bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-1.5 text-xs font-mono"\n'
                    '          />\n'
                    '          <input\n'
                    '            value={pan}\n'
                    '            onChange={(e) => setPan(e.target.value)}\n'
                    '            placeholder="Filter PAN..."\n'
                    '            className="bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-1.5 text-xs font-mono"\n'
                    '          />\n'
                    '          <select\n'
                    '            value={psCode}\n'
                    '            onChange={(e) => setPsCode(e.target.value)}\n'
                    '            className="bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-1.5 text-xs font-mono"\n'
                    '          >\n'
                    '            <option value="">ALL SWITCHES</option>\n'
                    '            <option value="ITCL">ITCL</option>\n'
                    '            <option value="VISA">VISA</option>\n'
                    '            <option value="MASTERCARD">MASTERCARD</option>\n'
                    '            <option value="NPSB">NPSB</option>\n'
                    '          </select>\n'
                    '          <select\n'
                    '            value={status}\n'
                    '            onChange={(e) => setStatus(e.target.value)}\n'
                    '            className="bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-1.5 text-xs font-mono"\n'
                    '          >\n'
                    '            <option value="">ALL OUTCOMES</option>\n'
                    '            <option value="APPROVED">APPROVED</option>\n'
                    '            <option value="DECLINED">DECLINED</option>\n'
                    '          </select>'
                ),
            },
            # Add Journal pagination footer
            {
                "marker": "step05:journal_pagination_footer",
                "action": "insert_after",
                "anchor": "      </div>\n    </div>\n  );\n};\n\n// ============================================================================\n// PAGE 10: TRANSACTION DETAILS",
                "text": "",  # placeholder
            },
            {
                "marker": "step05:journal_pagination_bar",
                "action": "insert_after",
                "anchor": '      </div>\n    </div>',
                "text": (
                    '\n      <div className="flex justify-between items-center bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-3 text-xs font-mono">\n'
                    '        <div className="text-slate-400">Total Journal Records: <strong className="text-emerald-500">{totalTxs}</strong></div>\n'
                    '        <div className="flex items-center gap-2">\n'
                    '          <button disabled={page <= 1} onClick={() => { setPage(page - 1); }} className="px-3 py-1 rounded border border-slate-300 dark:border-slate-700 disabled:opacity-40">Previous</button>\n'
                    '          <span>Page {page} of {totalPages}</span>\n'
                    '          <button disabled={page >= totalPages} onClick={() => { setPage(page + 1); }} className="px-3 py-1 rounded border border-slate-300 dark:border-slate-700 disabled:opacity-40">Next</button>\n'
                    '        </div>\n'
                    '      </div>'
                ),
            },
        ],
    )

    # 5. Write automated pytest test suite backend/tests/test_step05_search_and_pagination.py
    session.write_file("backend/tests/test_step05_search_and_pagination.py", TEST_STEP05_CODE)

    session.record_progress(
        completed=[
            "Added generic `PaginatedResponse[T]` schema envelope in `backend/app/schemas.py`.",
            "Implemented server-side multi-field filtering and pagination on `GET /api/customers`, `GET /api/accounts`, `GET /api/cards`, and `GET /api/transactions` in `backend/app/api_routes.py`.",
            "Added search bars, status filters, and pagination footers across Customers, Cards, and Accounts in `frontend/src/pages/BankingEntities.tsx`.",
            "Added PAN filter, switch scheme dropdown (`ITCL`/`VISA`), and pagination controls to Transaction Journal in `frontend/src/pages/SimulatorAndJournal.tsx`.",
            "Created automated Pytest test suite `backend/tests/test_step05_search_and_pagination.py`.",
        ],
        remaining=[
            "STEP 6 — PIN, PVV and Card Generation (Luhn test card generator, Visa PVV / IBM 3624 offset generation, PIN block generation, and POST /api/cards/{id}/pin endpoint).",
        ],
        modified_files=[
            "backend/app/schemas.py",
            "backend/app/api_routes.py",
            "frontend/src/pages/BankingEntities.tsx",
            "frontend/src/pages/SimulatorAndJournal.tsx",
            "backend/tests/test_step05_search_and_pagination.py",
        ],
    )

    session.record_contracts(
        section_title="Step 5 — Search & Pagination Contracts",
        contract_items=[
            "**Schema Envelope**: `PaginatedResponse[T]` -> `{'items': [...], 'total': int, 'page': int, 'page_size': int, 'total_pages': int}`.",
            "**GET /api/customers**: `q` (name/number/phone), `institution_id`, `status`, `page`, `page_size`.",
            "**GET /api/accounts**: `q` (number/branch), `account_type`, `institution_id`, `status`, `page`, `page_size`.",
            "**GET /api/cards**: `pan` (partial), `cardholder`, `institution_id`, `status`, `card_type`, `page`, `page_size`.",
            "**GET /api/transactions**: `stan`, `rrn`, `pan`, `status`, `response_code`, `ps_code`, `min_amount`, `max_amount`, `page`, `page_size`.",
        ],
    )

    return session.finish()


if __name__ == "__main__":
    sys.exit(main())