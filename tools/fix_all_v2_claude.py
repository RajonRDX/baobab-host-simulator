#!/usr/bin/env python3
"""
tools/fix_all_v2.py — RAJON Host Simulator: consolidated fix + Customer-Maintenance 360 rebuild
==============================================================================================

Run from anywhere:

    python tools/fix_all_v2.py               # apply
    python tools/fix_all_v2.py --dry-run     # show what would change, write nothing
    python tools/fix_all_v2.py --run-tests   # apply, then run backend pytest
    python tools/fix_all_v2.py --base "E:\\HOST_VSCODE\\host-simulator"

Properties
  * ALL-OR-NOTHING: every edit is staged in memory first; if any anchor is missing nothing is written.
  * IDEMPOTENT: running it twice is safe (already-applied edits are reported as SKIP).
  * Windows safe: CRLF files stay CRLF.  Originals are copied to  _backups/fix_all_v2_<timestamp>/ .
  * Never touches .env or *.db files.

What it fixes
  FRONTEND
    1. App.tsx: removes the `// [PATCH ...]` lines that were rendered as literal text inside <Routes>,
       fixes the mis-indented route.
    2. BankingEntities.tsx: CustomersPage referenced `editAcct` / `handleUpdateAccount` that were never
       declared (TypeScript build error => the whole Customers tab was dead).  CustomersPage is rebuilt
       (live search, status filter, create drawer, edit modal, link to 360 view).
    3. CustomerDataMaintenancePage.tsx: rebuilt.  Tabs CUSTOMER | PAN | ACCOUNT, live fetch, only the
       matched record is shown (searching a PAN no longer returns every card of the customer), and
       you can change the linked account, change the owning customer, or change the balance.
  BACKEND
    4. NEW routers/maintenance_router.py (lookup, reassign customer, swap linked account, adjust balance).
    5. 0220 financial advice no longer posts a second debit when it confirms an approved 0200.
    6. Authorizer rule context now receives card_limit (daily_used rules worked on a stale 0.0 before).
    7. ApiAuditLog no longer stores the Authorization bearer token / passwords / PIN data.
    8. /logs/correlation/{id} now resolves transaction references (the SWITCH_TX rows of the log portal).
    9. Settlement: on-us transactions no longer create self-cancelling debit/credit volume, and a 0220
       that merely confirms an approved 0200 is not settled twice.
   10. DE49 fix: simulator sample scenarios + run-scenarios sent "BDT" (invalid for numeric DE49 =>
       RC 30).  Now "050".  Numeric ISO-4217 is mapped to alpha for the stored currency / rule context.
   11. PVV decimalisation lives in ONE place; card_crypto_service now resolves PVK/CVK/AWK from the DB
       first (like the HSM adapter does) so PIN changes verify after a key ceremony.
   12. Startup warning (or hard fail with ENFORCE_SECURE_DEFAULTS=true) for default SECRET_KEY / ADMIN_PASSWORD.
   13. Stray `# [PATCH ...]` comments removed from api_routes.py and schemas.py.
   14. New regression tests: backend/tests/test_fix_v2.py
"""

import argparse
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

STEP_ID = "fix_all_v2"
PROTECTED_NAMES = {".env", "baobab_host.db", "baobab_host.db-journal", "baobab_host.db-wal"}
PROTECTED_SUFFIXES = {".db", ".sqlite", ".sqlite3"}


class PatchError(Exception):
    pass


NEW_FILES = {
    'backend/app/routers/maintenance_router.py': '"""\nmaintenance_router.py — Customer Data Maintenance 360 (v2)\n\nMode-aware lookup (CUSTOMER / PAN / ACCOUNT) plus atomic maintenance actions:\n  * change the customer that owns a card or an account\n  * swap the account linked to a card (keeps role / priority)\n  * adjust / set the balance of an account (audited)\n\nEvery result uses ONE unified shape so the UI can render the same 360 view:\n    {kind, customer, cards[], accounts[]}\n  - mode=customer -> all cards + accounts of the matched customer\n  - mode=pan      -> ONLY the matched card (+ the accounts linked to it)\n  - mode=account  -> ONLY the matched account (+ the cards linked to it)\n"""\n\nfrom decimal import Decimal, InvalidOperation\nfrom typing import Any, Dict, List, Optional\n\nfrom fastapi import APIRouter, Depends, HTTPException, Query\nfrom pydantic import BaseModel, Field\nfrom sqlalchemy import func, or_\nfrom sqlalchemy.orm import Session\n\nfrom app.audit_service import record_audit, serialize_entity\nfrom app.database import get_db\nfrom app.logging_service import record_system_log\nfrom app.models import Account, Card, CardAccount, Customer\nfrom app.security import get_current_user\n\nrouter = APIRouter(prefix="/api/maintenance", tags=["Customer Data Maintenance"])\n\nVALID_MODES = ("customer", "pan", "account")\n\n\n# ----------------------------------------------------------------------------\n# Request models\n# ----------------------------------------------------------------------------\nclass ReassignCustomerRequest(BaseModel):\n    customer_id: str\n    move_linked_accounts: bool = False  # card reassignment only\n\n\nclass SwapAccountRequest(BaseModel):\n    link_id: str\n    new_account_id: str\n\n\nclass BalanceAdjustRequest(BaseModel):\n    operation: str = Field("SET", description="SET | CREDIT | DEBIT")\n    amount: Decimal\n    sync_ledger: bool = True\n    reason: Optional[str] = None\n\n\n# ----------------------------------------------------------------------------\n# Serializers\n# ----------------------------------------------------------------------------\ndef _customer_out(c: Customer) -> Dict[str, Any]:\n    return {\n        "id": c.id,\n        "customer_number": c.customer_number,\n        "first_name": c.first_name,\n        "last_name": c.last_name,\n        "full_name": f"{c.first_name} {c.last_name or \'\'}".strip(),\n        "email": c.email,\n        "mobile_number": c.mobile_number,\n        "risk_category": c.risk_category,\n        "customer_status": c.customer_status,\n        "institution_id": c.institution_id,\n        "institution_code": c.institution.institution_code if c.institution else "XBANK",\n    }\n\n\ndef _account_out(a: Account, owner: bool = True) -> Dict[str, Any]:\n    out = {\n        "id": a.id,\n        "account_number": a.account_number,\n        "account_type": a.account_type,\n        "currency": a.currency,\n        "available_balance": float(a.available_balance),\n        "ledger_balance": float(a.ledger_balance),\n        "overdraft_limit": float(a.overdraft_limit),\n        "account_status": a.account_status,\n        "branch_code": a.branch_code,\n        "customer_id": a.customer_id,\n        "institution_code": a.institution.institution_code if a.institution else None,\n    }\n    if owner and a.customer:\n        out["customer_number"] = a.customer.customer_number\n        out["customer_name"] = f"{a.customer.first_name} {a.customer.last_name or \'\'}".strip()\n    return out\n\n\ndef _card_links(db: Session, card: Card) -> List[Dict[str, Any]]:\n    # Heal: a card with linked_account_id but no CardAccount row gets its PRIMARY link\n    if not card.card_accounts and card.linked_account_id:\n        fb = db.query(Account).filter(Account.id == card.linked_account_id).first()\n        if fb:\n            db.add(CardAccount(card_id=card.id, account_id=fb.id, account_role="PRIMARY",\n                               currency=fb.currency, priority=1, status="ACTIVE"))\n            db.commit()\n            db.refresh(card)\n    links = []\n    for ca in sorted(card.card_accounts, key=lambda x: x.priority):\n        acct = ca.account\n        links.append({\n            "link_id": ca.id,\n            "account_id": ca.account_id,\n            "account_number": acct.account_number if acct else "UNKNOWN",\n            "account_type": acct.account_type if acct else None,\n            "available_balance": float(acct.available_balance) if acct else 0.0,\n            "currency": ca.currency,\n            "account_role": ca.account_role,\n            "priority": ca.priority,\n            "status": ca.status,\n            "owner_customer_id": acct.customer_id if acct else None,\n        })\n    return links\n\n\ndef _card_out(db: Session, card: Card) -> Dict[str, Any]:\n    pp = card.pin_profile\n    return {\n        "id": card.id,\n        "customer_id": card.customer_id,\n        "pan": card.test_pan_reference,\n        "masked_pan": card.masked_pan,\n        "cardholder_name": card.cardholder_name,\n        "expiry_month": card.expiry_month,\n        "expiry_year": card.expiry_year,\n        "card_type": card.card_type,\n        "card_product": card.card_product,\n        "card_status": card.card_status,\n        "linked_account_id": card.linked_account_id,\n        "institution_code": card.institution.institution_code if card.institution else None,\n        "links": _card_links(db, card),\n        "pin_profile": {\n            "verification_method": pp.pin_verification_method,\n            "pvk_key_reference": pp.pvk_key_reference,\n            "pvv": pp.pin_offset_reference,\n        } if pp else None,\n    }\n\n\ndef _accounts_of_card(card: Card) -> List[Account]:\n    seen, out = set(), []\n    for ca in sorted(card.card_accounts, key=lambda x: x.priority):\n        if ca.account and ca.account.id not in seen:\n            seen.add(ca.account.id)\n            out.append(ca.account)\n    return out\n\n\ndef _cards_of_account(db: Session, acct: Account) -> List[Card]:\n    ids = {r[0] for r in db.query(CardAccount.card_id).filter(CardAccount.account_id == acct.id).all()}\n    ids |= {r[0] for r in db.query(Card.id).filter(Card.linked_account_id == acct.id).all()}\n    if not ids:\n        return []\n    return db.query(Card).filter(Card.id.in_(ids)).order_by(Card.created_at.desc()).all()\n\n\n# ----------------------------------------------------------------------------\n# Lookup\n# ----------------------------------------------------------------------------\n@router.get("/lookup")\ndef maintenance_lookup(\n    mode: str = Query("customer"),\n    q: Optional[str] = Query(None),\n    limit: int = Query(25, ge=1, le=100),\n    db: Session = Depends(get_db),\n    _: str = Depends(get_current_user),\n):\n    mode = (mode or "customer").lower()\n    if mode not in VALID_MODES:\n        raise HTTPException(status_code=400, detail=f"mode must be one of {\', \'.join(VALID_MODES)}")\n    term_raw = (q or "").strip()\n    like = f"%{term_raw}%"\n    results: List[Dict[str, Any]] = []\n\n    if mode == "customer":\n        qry = db.query(Customer)\n        if term_raw:\n            full = func.trim(Customer.first_name + " " + func.coalesce(Customer.last_name, ""))\n            qry = qry.filter(or_(\n                Customer.customer_number.ilike(like),\n                Customer.first_name.ilike(like),\n                Customer.last_name.ilike(like),\n                full.ilike(like),\n                Customer.mobile_number.ilike(like),\n                Customer.email.ilike(like),\n                Customer.id == term_raw,\n            ))\n        total = qry.count()\n        for cust in qry.order_by(Customer.created_at.desc()).limit(limit).all():\n            results.append({\n                "kind": "customer",\n                "customer": _customer_out(cust),\n                "cards": [_card_out(db, c) for c in cust.cards],\n                "accounts": [_account_out(a, owner=False) for a in cust.accounts],\n            })\n\n    elif mode == "pan":\n        qry = db.query(Card)\n        if term_raw:\n            digits = "".join(ch for ch in term_raw if ch.isdigit())\n            conds = [Card.masked_pan.ilike(like), Card.id == term_raw]\n            if digits:\n                conds.append(Card.test_pan_reference.like(f"%{digits}%"))\n            qry = qry.filter(or_(*conds))\n        total = qry.count()\n        for card in qry.order_by(Card.created_at.desc()).limit(limit).all():\n            results.append({\n                "kind": "pan",\n                "customer": _customer_out(card.customer),\n                "cards": [_card_out(db, card)],\n                "accounts": [_account_out(a) for a in _accounts_of_card(card)],\n            })\n\n    else:  # account\n        qry = db.query(Account)\n        if term_raw:\n            qry = qry.filter(or_(Account.account_number.ilike(like), Account.id == term_raw))\n        total = qry.count()\n        for acct in qry.order_by(Account.account_number.asc()).limit(limit).all():\n            results.append({\n                "kind": "account",\n                "customer": _customer_out(acct.customer),\n                "cards": [_card_out(db, c) for c in _cards_of_account(db, acct)],\n                "accounts": [_account_out(acct)],\n            })\n\n    return {"mode": mode, "query": term_raw, "total": total, "results": results}\n\n\n@router.get("/account-options")\ndef account_options(\n    q: Optional[str] = Query(None),\n    limit: int = Query(30, ge=1, le=100),\n    db: Session = Depends(get_db),\n    _: str = Depends(get_current_user),\n):\n    """Accounts that can be picked as a link / swap target."""\n    qry = db.query(Account)\n    if q and q.strip():\n        like = f"%{q.strip()}%"\n        qry = qry.join(Customer, Customer.id == Account.customer_id).filter(or_(\n            Account.account_number.ilike(like),\n            Customer.customer_number.ilike(like),\n            Customer.first_name.ilike(like),\n            Customer.last_name.ilike(like),\n        ))\n    return [_account_out(a) for a in qry.order_by(Account.account_number.asc()).limit(limit).all()]\n\n\n# ----------------------------------------------------------------------------\n# Actions\n# ----------------------------------------------------------------------------\n@router.post("/cards/{card_id}/reassign-customer")\ndef reassign_card_customer(\n    card_id: str,\n    payload: ReassignCustomerRequest,\n    db: Session = Depends(get_db),\n    current_user: str = Depends(get_current_user),\n):\n    card = db.query(Card).filter(Card.id == card_id).first()\n    if not card:\n        raise HTTPException(status_code=404, detail="Card not found")\n    target = db.query(Customer).filter(Customer.id == payload.customer_id).first()\n    if not target:\n        raise HTTPException(status_code=404, detail="Target customer not found")\n    if card.customer_id == target.id:\n        raise HTTPException(status_code=400, detail="Card already belongs to this customer")\n\n    before = serialize_entity(card)\n    old_customer = card.customer\n    card.customer_id = target.id\n    moved = 0\n    if payload.move_linked_accounts:\n        for acct in _accounts_of_card(card):\n            if acct.customer_id != target.id:\n                acct.customer_id = target.id\n                moved += 1\n    db.flush()\n    record_audit(db, "CARD", card.id, "REASSIGN_CUSTOMER", performed_by=current_user,\n                 before_state=before, after_state=serialize_entity(card),\n                 change_summary=(f"Card {card.masked_pan} moved from {old_customer.customer_number if old_customer else \'?\'} "\n                                 f"to {target.customer_number} (accounts moved: {moved})"))\n    record_system_log(db, "INFO", "MaintenanceService", "CARD_REASSIGNED",\n                      f"Card {card.masked_pan} -> customer {target.customer_number}")\n    db.commit()\n    return {"status": "ok", "card_id": card.id, "customer_id": target.id, "accounts_moved": moved}\n\n\n@router.post("/accounts/{account_id}/reassign-customer")\ndef reassign_account_customer(\n    account_id: str,\n    payload: ReassignCustomerRequest,\n    db: Session = Depends(get_db),\n    current_user: str = Depends(get_current_user),\n):\n    acct = db.query(Account).filter(Account.id == account_id).first()\n    if not acct:\n        raise HTTPException(status_code=404, detail="Account not found")\n    target = db.query(Customer).filter(Customer.id == payload.customer_id).first()\n    if not target:\n        raise HTTPException(status_code=404, detail="Target customer not found")\n    if acct.customer_id == target.id:\n        raise HTTPException(status_code=400, detail="Account already belongs to this customer")\n\n    before = serialize_entity(acct)\n    old = acct.customer\n    cross_bank = bool(acct.institution_id and target.institution_id and acct.institution_id != target.institution_id)\n    acct.customer_id = target.id\n    db.flush()\n    record_audit(db, "ACCOUNT", acct.id, "REASSIGN_CUSTOMER", performed_by=current_user,\n                 before_state=before, after_state=serialize_entity(acct),\n                 change_summary=f"Account {acct.account_number} moved from {old.customer_number if old else \'?\'} to {target.customer_number}")\n    db.commit()\n    return {"status": "ok", "account_id": acct.id, "customer_id": target.id, "cross_bank": cross_bank}\n\n\n@router.post("/cards/{card_id}/swap-account")\ndef swap_card_account(\n    card_id: str,\n    payload: SwapAccountRequest,\n    db: Session = Depends(get_db),\n    current_user: str = Depends(get_current_user),\n):\n    """Replace the account of an existing card link; role / priority are preserved."""\n    card = db.query(Card).filter(Card.id == card_id).first()\n    if not card:\n        raise HTTPException(status_code=404, detail="Card not found")\n    link = db.query(CardAccount).filter(CardAccount.id == payload.link_id, CardAccount.card_id == card.id).first()\n    if not link:\n        raise HTTPException(status_code=404, detail="Link not found on this card")\n    new_acct = db.query(Account).filter(Account.id == payload.new_account_id).first()\n    if not new_acct:\n        raise HTTPException(status_code=404, detail="New account not found")\n    if new_acct.id == link.account_id:\n        raise HTTPException(status_code=400, detail="Card is already linked to that account in this slot")\n    dup = db.query(CardAccount).filter(CardAccount.card_id == card.id, CardAccount.account_id == new_acct.id).first()\n    if dup:\n        raise HTTPException(status_code=400, detail="New account is already linked to this card")\n\n    before = serialize_entity(link)\n    old_account_id = link.account_id\n    link.account_id = new_acct.id\n    link.currency = new_acct.currency\n    if card.linked_account_id == old_account_id or link.account_role == "PRIMARY":\n        card.linked_account_id = new_acct.id\n    db.flush()\n    record_audit(db, "CARD_ACCOUNT", link.id, "SWAP_ACCOUNT", performed_by=current_user,\n                 before_state=before, after_state=serialize_entity(link),\n                 change_summary=f"Card {card.masked_pan}: link account swapped to {new_acct.account_number}")\n    db.commit()\n    return {"status": "ok", "link_id": link.id, "account_id": new_acct.id, "account_number": new_acct.account_number}\n\n\n@router.post("/accounts/{account_id}/balance")\ndef adjust_account_balance(\n    account_id: str,\n    payload: BalanceAdjustRequest,\n    db: Session = Depends(get_db),\n    current_user: str = Depends(get_current_user),\n):\n    acct = db.query(Account).filter(Account.id == account_id).first()\n    if not acct:\n        raise HTTPException(status_code=404, detail="Account not found")\n    op = (payload.operation or "SET").upper()\n    if op not in ("SET", "CREDIT", "DEBIT"):\n        raise HTTPException(status_code=400, detail="operation must be SET, CREDIT or DEBIT")\n    try:\n        amount = Decimal(payload.amount).quantize(Decimal("0.01"))\n    except (InvalidOperation, ValueError):\n        raise HTTPException(status_code=400, detail="Invalid amount")\n    if op in ("CREDIT", "DEBIT") and amount <= 0:\n        raise HTTPException(status_code=400, detail="Amount must be greater than zero")\n\n    before = serialize_entity(acct)\n    avail, ledger = Decimal(acct.available_balance), Decimal(acct.ledger_balance)\n    if op == "SET":\n        new_avail = amount\n        new_ledger = amount if payload.sync_ledger else ledger\n    elif op == "CREDIT":\n        new_avail, new_ledger = avail + amount, ledger + (amount if payload.sync_ledger else 0)\n    else:\n        new_avail, new_ledger = avail - amount, ledger - (amount if payload.sync_ledger else 0)\n\n    floor = -Decimal(acct.overdraft_limit or 0)\n    if new_avail < floor:\n        raise HTTPException(status_code=400,\n                            detail=f"Resulting balance {new_avail} would breach overdraft limit {acct.overdraft_limit}")\n\n    acct.available_balance = new_avail\n    acct.ledger_balance = new_ledger\n    db.flush()\n    record_audit(db, "ACCOUNT", acct.id, "BALANCE_ADJUST", performed_by=current_user,\n                 before_state=before, after_state=serialize_entity(acct),\n                 change_summary=f"{op} {amount} on {acct.account_number}: {avail} -> {new_avail}"\n                                + (f" | reason: {payload.reason}" if payload.reason else ""))\n    db.commit()\n    db.refresh(acct)\n    return {"status": "ok", "account": _account_out(acct)}\n',
    'backend/tests/test_fix_v2.py': '"""\ntest_fix_v2.py — Regression tests for fix_all_v2:\nmaintenance lookup (customer / PAN / account), reassign, swap, balance adjust,\n0220 no double posting, redaction of sensitive audit data, correlation fallback.\n"""\n\nimport os\nfrom decimal import Decimal\n\nimport pytest\nfrom fastapi.testclient import TestClient\n\nos.environ["DATABASE_URL"] = "sqlite:///:memory:"\n\nfrom app.config import settings\nfrom app.database import Base, SessionLocal, engine\nfrom app.host_engine import HostTransactionProcessor\nfrom app.main import app\nfrom app.models import Account, ApiAuditLog, AuditTrail, Card, CardAccount, Customer, Transaction\nfrom app.security import create_access_token\nfrom app.seed_data import seed_initial_data\n\n\n@pytest.fixture()\ndef db_session():\n    Base.metadata.create_all(bind=engine)\n    session = SessionLocal()\n    seed_initial_data(session)\n    yield session\n    session.close()\n    Base.metadata.drop_all(bind=engine)\n\n\n@pytest.fixture()\ndef client(db_session):\n    with TestClient(app) as c:\n        token = create_access_token(subject=settings.ADMIN_USERNAME)\n        c.headers = {"Authorization": f"Bearer {token}"}\n        yield c\n\n\ndef _second_customer_with_account(db):\n    base = db.query(Card).first().customer\n    cust = Customer(customer_number="CUST-V2-02", first_name="Second", last_name="Person",\n                    institution_id=base.institution_id, mobile_number="+8801711111111")\n    db.add(cust)\n    db.flush()\n    acct = Account(account_number="9900110022", customer_id=cust.id, account_type="CURRENT", currency="BDT",\n                   available_balance=Decimal("1000.00"), ledger_balance=Decimal("1000.00"),\n                   institution_id=base.institution_id)\n    db.add(acct)\n    db.commit()\n    return cust, acct\n\n\n# ----------------------------- lookup modes ---------------------------------\ndef test_lookup_pan_returns_only_the_matched_card(client, db_session):\n    card = db_session.query(Card).first()\n    # give the customer a 2nd card so the old "customer search" behaviour would return two\n    extra = Card(customer_id=card.customer_id, card_number_token="tok-v2-x", test_pan_reference="4567890123459999",\n                 masked_pan="456789******9999", cardholder_name="EXTRA", expiry_month=12, expiry_year=2030,\n                 institution_id=card.institution_id)\n    db_session.add(extra)\n    db_session.commit()\n\n    res = client.get("/api/maintenance/lookup", params={"mode": "pan", "q": card.test_pan_reference})\n    assert res.status_code == 200\n    data = res.json()\n    assert data["total"] == 1\n    r = data["results"][0]\n    assert r["kind"] == "pan"\n    assert [c["id"] for c in r["cards"]] == [card.id]\n    assert r["customer"]["id"] == card.customer_id\n\n\ndef test_lookup_customer_and_account_modes(client, db_session):\n    card = db_session.query(Card).first()\n    cust = card.customer\n    res = client.get("/api/maintenance/lookup", params={"mode": "customer", "q": cust.customer_number}).json()\n    assert res["results"][0]["customer"]["id"] == cust.id\n    assert len(res["results"][0]["accounts"]) >= 1\n\n    acct = db_session.query(Account).filter(Account.customer_id == cust.id).first()\n    res = client.get("/api/maintenance/lookup", params={"mode": "account", "q": acct.account_number}).json()\n    assert res["results"][0]["kind"] == "account"\n    assert res["results"][0]["accounts"][0]["id"] == acct.id\n\n    bad = client.get("/api/maintenance/lookup", params={"mode": "nope"})\n    assert bad.status_code == 400\n\n\n# ----------------------------- actions --------------------------------------\ndef test_reassign_card_and_account_customer(client, db_session):\n    card = db_session.query(Card).first()\n    orig_cust_id = card.customer_id\n    new_cust, new_acct = _second_customer_with_account(db_session)\n\n    r = client.post(f"/api/maintenance/cards/{card.id}/reassign-customer",\n                    json={"customer_id": new_cust.id, "move_linked_accounts": True})\n    assert r.status_code == 200 and r.json()["accounts_moved"] >= 1\n    db_session.expire_all()\n    assert db_session.query(Card).filter(Card.id == card.id).first().customer_id == new_cust.id\n\n    r = client.post(f"/api/maintenance/accounts/{new_acct.id}/reassign-customer", json={"customer_id": orig_cust_id})\n    assert r.status_code == 200\n    # same owner again is rejected\n    r = client.post(f"/api/maintenance/accounts/{new_acct.id}/reassign-customer", json={"customer_id": orig_cust_id})\n    assert r.status_code == 400\n    assert db_session.query(AuditTrail).filter(AuditTrail.action == "REASSIGN_CUSTOMER").count() >= 2\n\n\ndef test_swap_linked_account_keeps_role(client, db_session):\n    card = db_session.query(Card).first()\n    link = db_session.query(CardAccount).filter(CardAccount.card_id == card.id).first()\n    role = link.account_role\n    _, other = _second_customer_with_account(db_session)\n\n    r = client.post(f"/api/maintenance/cards/{card.id}/swap-account", json={"link_id": link.id, "new_account_id": other.id})\n    assert r.status_code == 200\n    db_session.expire_all()\n    link = db_session.query(CardAccount).filter(CardAccount.id == link.id).first()\n    assert link.account_id == other.id and link.account_role == role\n    if role == "PRIMARY":\n        assert db_session.query(Card).filter(Card.id == card.id).first().linked_account_id == other.id\n\n    # already linked -> 400\n    r = client.post(f"/api/maintenance/cards/{card.id}/swap-account", json={"link_id": link.id, "new_account_id": other.id})\n    assert r.status_code == 400\n\n\ndef test_balance_adjust_set_credit_debit_and_overdraft_guard(client, db_session):\n    acct = db_session.query(Account).first()\n    base = f"/api/maintenance/accounts/{acct.id}/balance"\n\n    r = client.post(base, json={"operation": "SET", "amount": 500, "reason": "test"})\n    assert r.status_code == 200\n    assert r.json()["account"]["available_balance"] == 500.0 and r.json()["account"]["ledger_balance"] == 500.0\n\n    assert client.post(base, json={"operation": "CREDIT", "amount": 250.5}).json()["account"]["available_balance"] == 750.5\n    assert client.post(base, json={"operation": "DEBIT", "amount": 50.5}).json()["account"]["available_balance"] == 700.0\n\n    # cannot go below -overdraft\n    r = client.post(base, json={"operation": "DEBIT", "amount": 10_000_000})\n    assert r.status_code == 400\n    assert client.post(base, json={"operation": "CREDIT", "amount": 0}).status_code == 400\n    assert db_session.query(AuditTrail).filter(AuditTrail.action == "BALANCE_ADJUST").count() == 3\n\n\n# ----------------------------- engine / audit fixes -------------------------\ndef _atm(rrn, stan, mti="0200", amt="000000100000"):\n    return {\n        "mti": mti,\n        "transaction_code": "10",\n        "test_clear_pin_helper": "1234",\n        "fields": {"2": "4567890123450001", "3": "0100000", "4": amt, "11": stan, "37": rrn, "41": "ATM01", "49": "050"},\n    }\n\n\ndef test_0220_advice_for_approved_0200_does_not_debit_again(db_session):\n    acct = db_session.query(Account).first()\n    proc = HostTransactionProcessor(db_session)\n    first = proc.process_transaction(_atm("000077700001", "770001"))\n    assert first["response_code"] == "00"\n    db_session.expire_all()\n    after_first = Decimal(db_session.query(Account).filter(Account.id == acct.id).first().available_balance)\n\n    adv = HostTransactionProcessor(db_session).process_transaction(_atm("000077700001", "770002", mti="0220"))\n    assert adv["response_code"] == "00"\n    db_session.expire_all()\n    after_adv = Decimal(db_session.query(Account).filter(Account.id == acct.id).first().available_balance)\n    assert after_adv == after_first  # advice must not post a second debit\n\n\ndef test_audit_log_redacts_authorization_header_and_secrets(client, db_session):\n    client.post("/api/auth/login", json={"username": settings.ADMIN_USERNAME, "password": "wrong-password"})\n    client.get("/api/maintenance/lookup", params={"mode": "customer"})\n    logs = db_session.query(ApiAuditLog).all()\n    assert logs, "middleware should persist api audit rows"\n    for row in logs:\n        hdrs = {k.lower(): v for k, v in (row.request_headers or {}).items()}\n        assert hdrs.get("authorization", "***") == "***"\n        assert "password" not in str(row.request_body).replace("\'password\': \'***\'", "").replace(\'"password": "***"\', "")\n\n\ndef test_correlation_endpoint_resolves_transaction_reference(client, db_session):\n    proc = HostTransactionProcessor(db_session)\n    proc.process_transaction(_atm("000066600001", "660001"))\n    tx = db_session.query(Transaction).order_by(Transaction.created_at.desc()).first()\n    res = client.get(f"/api/logs/correlation/{tx.transaction_reference}")\n    assert res.status_code == 200\n    assert res.json()["transaction"]["transaction_reference"] == tx.transaction_reference\n\n\ndef test_simulator_catalog_uses_numeric_currency(client):\n    cat = client.get("/api/simulator/catalog")\n    assert cat.status_code == 200\n    scenarios = cat.json()["sample_scenarios"]\n    assert scenarios\n    for s in scenarios:\n        assert s["fields"]["49"].isdigit(), f"{s[\'key\']} sends non-numeric DE49"\n',
    'frontend/src/App.tsx': r"""import React from 'react';
import { HashRouter, Routes, Route, Navigate } from 'react-router-dom';
import { getToken } from './api';
import { Layout } from './components/Layout';
import { LoginPage, DashboardPage } from './pages/LoginAndDashboard';
import {
  CustomersPage,
  CardsPage,
  AccountsPage,
  CardLimitsPage,
  AccountLimitsPage,
} from './pages/BankingEntities';
import { InstitutionsAndBinsPage } from './pages/InstitutionsAndBinsPage';
import { CustomerDataMaintenancePage } from './pages/CustomerDataMaintenancePage';
import { AuditTrailPage } from './pages/AuditTrailPage';
import { CardCryptoLabPage } from './pages/CardCryptoLabPage';
import { KeyCeremonyWorkbenchPage } from './pages/KeyCeremonyWorkbenchPage';
import { NetworkRoutingPage } from './pages/NetworkRoutingPage';
import { ClearingAndSettlementPage } from './pages/ClearingAndSettlementPage';
import { UnifiedLogPortalPage } from './pages/UnifiedLogPortalPage';
import { AuthorizerRulesPage } from './pages/AuthorizerRulesPage';
import {
  TransactionCodesPage,
  HostConfigurationPage,
  ResponseCodesPage,
} from './pages/HostConfigPages';
import {
  TransactionSimulatorPage,
  TransactionJournalPage,
  TransactionDetailsPage,
} from './pages/SimulatorAndJournal';
import {
  HostKeyManagementPage,
  HsmWorkbenchPage,
  HostExecutionMonitorPage,
  SystemLogsPage,
  NotificationsSimulatorPage,
} from './pages/HsmAndMonitorPages';

const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  if (!getToken()) {
    return <Navigate to="/login" replace />;
  }
  return <Layout>{children}</Layout>;
};

export const App: React.FC = () => {
  return (
    <HashRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <DashboardPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/customers"
          element={
            <ProtectedRoute>
              <CustomersPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/cards"
          element={
            <ProtectedRoute>
              <CardsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/accounts"
          element={
            <ProtectedRoute>
              <AccountsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/institutions"
          element={
            <ProtectedRoute>
              <InstitutionsAndBinsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/card-limits"
          element={
            <ProtectedRoute>
              <CardLimitsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/account-limits"
          element={
            <ProtectedRoute>
              <AccountLimitsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/transaction-codes"
          element={
            <ProtectedRoute>
              <TransactionCodesPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/authorizer-rules"
          element={
            <ProtectedRoute>
              <AuthorizerRulesPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/network-routing"
          element={
            <ProtectedRoute>
              <NetworkRoutingPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/settlement"
          element={
            <ProtectedRoute>
              <ClearingAndSettlementPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/simulator"
          element={
            <ProtectedRoute>
              <TransactionSimulatorPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/transactions"
          element={
            <ProtectedRoute>
              <TransactionJournalPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/transactions/:id"
          element={
            <ProtectedRoute>
              <TransactionDetailsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/hsm-keys"
          element={
            <ProtectedRoute>
              <HostKeyManagementPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/hsm-workbench"
          element={
            <ProtectedRoute>
              <HsmWorkbenchPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/card-lab"
          element={
            <ProtectedRoute>
              <CardCryptoLabPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/key-ceremony"
          element={
            <ProtectedRoute>
              <KeyCeremonyWorkbenchPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/monitor"
          element={
            <ProtectedRoute>
              <HostExecutionMonitorPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/host-config"
          element={
            <ProtectedRoute>
              <HostConfigurationPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/response-codes"
          element={
            <ProtectedRoute>
              <ResponseCodesPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/system-logs"
          element={
            <ProtectedRoute>
              <SystemLogsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/audit-trail"
          element={
            <ProtectedRoute>
              <AuditTrailPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/log-portal"
          element={
            <ProtectedRoute>
              <UnifiedLogPortalPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/notifications"
          element={
            <ProtectedRoute>
              <NotificationsSimulatorPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/customer-maintenance"
          element={
            <ProtectedRoute>
              <CustomerDataMaintenancePage />
            </ProtectedRoute>
          }
        />
      </Routes>
    </HashRouter>
  );
};

export default App;
""",
    'frontend/src/pages/CustomerDataMaintenancePage.tsx': r"""import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  ArrowLeftRight,
  CheckCircle2,
  CreditCard,
  Eye,
  EyeOff,
  Hash,
  KeyRound,
  Landmark,
  Link2,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  ShieldAlert,
  Star,
  Trash2,
  Unlink,
  User,
  Wallet,
  X,
} from 'lucide-react';
import { apiFetch } from '../api';

// ============================================================================
// Types & helpers
// ============================================================================
type Mode = 'customer' | 'pan' | 'account';

const MODES: { key: Mode; label: string; hint: string; icon: React.ReactNode }[] = [
  { key: 'customer', label: 'Customer', hint: 'Customer no, name, mobile or email', icon: <User size={14} /> },
  { key: 'pan', label: 'PAN', hint: 'Full or partial card number (or masked PAN)', icon: <CreditCard size={14} /> },
  { key: 'account', label: 'Account', hint: 'Account number', icon: <Landmark size={14} /> },
];

const fmt = (n: any, ccy = '') =>
  `${Number(n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}${ccy ? ` ${ccy}` : ''}`;

const groupPan = (pan: string) => (pan || '').replace(/(.{4})/g, '$1 ').trim();
// seed data stores masked_pan unmasked, so always derive the masked form from the PAN itself
const maskPan = (pan: string) => (pan && pan.length > 10 ? `${pan.slice(0, 6)}${'*'.repeat(pan.length - 10)}${pan.slice(-4)}` : pan || '');

const inputCls =
  'w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-emerald-500/40 focus:border-emerald-500';

const statusTone = (s: string) =>
  s === 'ACTIVE'
    ? 'bg-emerald-500/10 text-emerald-500 border-emerald-500/30'
    : s === 'BLOCKED' || s === 'CLOSED' || s === 'LOST' || s === 'STOLEN'
    ? 'bg-rose-500/10 text-rose-500 border-rose-500/30'
    : 'bg-amber-500/10 text-amber-500 border-amber-500/30';

const Badge: React.FC<{ tone?: string; children: React.ReactNode }> = ({ tone, children }) => (
  <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[10px] font-bold tracking-wide ${tone || 'bg-slate-500/10 text-slate-400 border-slate-500/30'}`}>
    {children}
  </span>
);

const Modal: React.FC<{ title: string; subtitle?: string; onClose: () => void; children: React.ReactNode; footer?: React.ReactNode }> = ({
  title,
  subtitle,
  onClose,
  children,
  footer,
}) => {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);
  return (
  <div className="fixed inset-0 z-50 bg-slate-950/70 backdrop-blur-sm flex items-center justify-center p-4" onClick={onClose}>
    <div
      className="w-full max-w-md bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-2xl shadow-2xl overflow-hidden"
      onClick={(e) => e.stopPropagation()}
    >
      <div className="flex items-start justify-between px-5 py-4 border-b border-slate-200 dark:border-slate-800">
        <div>
          <h3 className="text-sm font-bold">{title}</h3>
          {subtitle && <p className="text-[11px] text-slate-400 font-mono mt-0.5">{subtitle}</p>}
        </div>
        <button onClick={onClose} className="p-1 rounded-md hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-400">
          <X size={16} />
        </button>
      </div>
      <div className="p-5 space-y-3 text-xs">{children}</div>
      {footer && <div className="px-5 py-3 border-t border-slate-200 dark:border-slate-800 flex justify-end gap-2 bg-slate-50/60 dark:bg-slate-950/40">{footer}</div>}
    </div>
  </div>
  );
};

const Btn: React.FC<{
  onClick?: () => void;
  tone?: 'primary' | 'ghost' | 'danger' | 'sky';
  disabled?: boolean;
  children: React.ReactNode;
  title?: string;
  type?: 'button' | 'submit';
}> = ({ onClick, tone = 'ghost', disabled, children, title, type = 'button' }) => {
  const tones: Record<string, string> = {
    primary: 'bg-emerald-600 hover:bg-emerald-500 text-white border-emerald-600',
    ghost: 'bg-transparent hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300 border-slate-300 dark:border-slate-700',
    danger: 'bg-transparent hover:bg-rose-500/10 text-rose-500 border-rose-500/40',
    sky: 'bg-transparent hover:bg-sky-500/10 text-sky-500 border-sky-500/40',
  };
  return (
    <button
      type={type}
      title={title}
      disabled={disabled}
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-[11px] font-semibold transition disabled:opacity-40 disabled:cursor-not-allowed ${tones[tone]}`}
    >
      {children}
    </button>
  );
};

const resultKey = (r: any): string =>
  r.kind === 'customer' ? r.customer.id : r.kind === 'pan' ? r.cards[0]?.id : r.accounts[0]?.id;

// ============================================================================
// Page
// ============================================================================
export const CustomerDataMaintenancePage: React.FC = () => {
  const [params, setParams] = useSearchParams();
  const initialMode = (MODES.find((m) => m.key === params.get('mode'))?.key || 'customer') as Mode;

  const [mode, setMode] = useState<Mode>(initialMode);
  const [term, setTerm] = useState(params.get('q') || '');
  const [results, setResults] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [selected, setSelected] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState('');
  const [error, setError] = useState('');
  const [revealPan, setRevealPan] = useState<Record<string, boolean>>({});

  // modals
  const [balanceAcct, setBalanceAcct] = useState<any | null>(null);
  const [editAcct, setEditAcct] = useState<any | null>(null);
  const [pinCard, setPinCard] = useState<any | null>(null);
  const [custModal, setCustModal] = useState<{ kind: 'card' | 'account'; item: any } | null>(null);
  const [linkModal, setLinkModal] = useState<{ card: any; swap?: any } | null>(null);

  const reqId = useRef(0);

  const flash = (m: string) => {
    setError('');
    setMsg(m);
    window.setTimeout(() => setMsg((cur) => (cur === m ? '' : cur)), 6000);
  };

  const load = useCallback(
    async (m: Mode, q: string, keepSelection = true) => {
      const id = ++reqId.current;
      setLoading(true);
      setError('');
      try {
        const res = await apiFetch(`/maintenance/lookup?mode=${m}&q=${encodeURIComponent(q.trim())}&limit=25`);
        if (id !== reqId.current) return; // a newer request superseded this one
        const list: any[] = res.results || [];
        setResults(list);
        setTotal(res.total || list.length);
        setSelected((cur) => (keepSelection && list.some((r) => resultKey(r) === cur) ? cur : list[0] ? resultKey(list[0]) : ''));
      } catch (e: any) {
        if (id === reqId.current) setError(e.message || 'Lookup failed');
      } finally {
        if (id === reqId.current) setLoading(false);
      }
    },
    []
  );

  // live search (debounced) whenever mode or text changes
  useEffect(() => {
    const t = window.setTimeout(() => {
      load(mode, term, false);
      const next: Record<string, string> = { mode };
      if (term.trim()) next.q = term.trim();
      setParams(next, { replace: true });
    }, 300);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, term]);

  const refresh = () => load(mode, term, true);

  const active = useMemo(() => results.find((r) => resultKey(r) === selected) || null, [results, selected]);

  // generic action runner -> toast + refresh
  const run = async (fn: () => Promise<any>, ok: string) => {
    setMsg('');
    setError('');
    try {
      await fn();
      flash(ok);
      await refresh();
      return true;
    } catch (e: any) {
      setError(e.message || 'Action failed');
      return false;
    }
  };

  // ------------------------------- actions -----------------------------------
  const toggleCard = (card: any) => {
    const next = card.card_status === 'ACTIVE' ? 'BLOCKED' : 'ACTIVE';
    run(() => apiFetch(`/cards/${card.id}`, { method: 'PUT', body: JSON.stringify({ card_status: next }) }), `Card ${card.masked_pan} is now ${next}`);
  };
  const deleteCard = (card: any) => {
    if (!confirm(`Delete card ${card.masked_pan}? This cannot be undone.`)) return;
    run(() => apiFetch(`/cards/${card.id}?force=true`, { method: 'DELETE' }), `Card ${card.masked_pan} deleted`);
  };
  const deleteAccount = (a: any) => {
    if (!confirm(`Delete account ${a.account_number}? Card links and ledger rows are removed.`)) return;
    run(() => apiFetch(`/accounts/${a.id}?force=true`, { method: 'DELETE' }), `Account ${a.account_number} deleted`);
  };
  const unlink = (card: any, l: any) => {
    if (!confirm(`Unlink ${l.account_number} from ${card.masked_pan}?`)) return;
    run(() => apiFetch(`/cards/accounts/${l.link_id}`, { method: 'DELETE' }), `Unlinked ${l.account_number}`);
  };
  const makePrimary = (l: any) =>
    run(() => apiFetch(`/cards/accounts/${l.link_id}`, { method: 'PUT', body: JSON.stringify({ account_role: 'PRIMARY', priority: 1 }) }), `${l.account_number} is now PRIMARY`);

  // ------------------------------- render ------------------------------------
  const modeMeta = MODES.find((m) => m.key === mode)!;

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Customer Data Maintenance</h1>
          <p className="text-xs text-slate-500">Look up by customer, PAN or account — then re-link accounts, move ownership or fix balances.</p>
        </div>
        <Btn onClick={refresh} title="Reload">
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} /> Refresh
        </Btn>
      </div>

      {/* Search bar with mode tabs */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-4 space-y-3 shadow-sm">
        <div className="inline-flex p-1 rounded-xl bg-slate-100 dark:bg-slate-950 border border-slate-200 dark:border-slate-800">
          {MODES.map((m) => (
            <button
              key={m.key}
              onClick={() => {
                setMode(m.key);
                setSelected('');
              }}
              className={`flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-semibold transition ${
                mode === m.key ? 'bg-emerald-600 text-white shadow' : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
              }`}
            >
              {m.icon} {m.label}
            </button>
          ))}
        </div>
        <div className="relative">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            autoFocus
            value={term}
            onChange={(e) => setTerm(e.target.value)}
            placeholder={modeMeta.hint}
            className={`${inputCls} pl-9 py-2.5 text-sm`}
          />
          {term && (
            <button onClick={() => setTerm('')} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200">
              <X size={14} />
            </button>
          )}
        </div>
        <div className="flex items-center justify-between text-[11px] font-mono text-slate-400">
          <span>
            {loading ? 'Searching…' : `${total} ${modeMeta.label.toLowerCase()} match${total === 1 ? '' : 'es'}`}
            {total > results.length && ` (showing first ${results.length})`}
          </span>
          <span>Results update as you type</span>
        </div>
      </div>

      {msg && (
        <div className="flex items-center gap-2 p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-500 text-xs font-mono">
          <CheckCircle2 size={14} /> {msg}
        </div>
      )}
      {error && (
        <div className="flex items-center gap-2 p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs font-mono">
          <ShieldAlert size={14} /> {error}
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-[320px_1fr] gap-5 items-start">
        {/* Result list */}
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl overflow-hidden shadow-sm">
          <div className="px-4 py-2.5 border-b border-slate-200 dark:border-slate-800 text-[11px] font-bold uppercase tracking-wider text-slate-400">
            Results
          </div>
          <div className="max-h-[70vh] overflow-y-auto divide-y divide-slate-200/60 dark:divide-slate-800/60">
            {loading && results.length === 0 &&
              [0, 1, 2].map((i) => <div key={i} className="m-3 h-14 rounded-xl bg-slate-100 dark:bg-slate-800 animate-pulse" />)}
            {!loading && results.length === 0 && <div className="p-6 text-center text-xs text-slate-400">No {modeMeta.label.toLowerCase()} found.</div>}
            {results.map((r) => {
              const key = resultKey(r);
              const isSel = key === selected;
              const card = r.cards[0];
              const acct = r.accounts[0];
              return (
                <button
                  key={key}
                  onClick={() => setSelected(key)}
                  className={`w-full text-left px-4 py-3 transition border-l-4 ${
                    isSel ? 'bg-emerald-500/10 border-emerald-500' : 'border-transparent hover:bg-slate-50 dark:hover:bg-slate-800/50'
                  }`}
                >
                  {r.kind === 'customer' && (
                    <>
                      <div className="font-semibold text-xs">{r.customer.full_name}</div>
                      <div className="text-[11px] font-mono text-emerald-500">{r.customer.customer_number}</div>
                      <div className="text-[10px] text-slate-400 mt-0.5">
                        {r.customer.institution_code} · {r.cards.length} card{r.cards.length === 1 ? '' : 's'} · {r.accounts.length} acct
                      </div>
                    </>
                  )}
                  {r.kind === 'pan' && card && (
                    <>
                      <div className="font-mono text-xs font-bold">{card.masked_pan}</div>
                      <div className="text-[11px] text-slate-400">{card.cardholder_name}</div>
                      <div className="text-[10px] text-emerald-500 font-mono mt-0.5">{r.customer.customer_number}</div>
                    </>
                  )}
                  {r.kind === 'account' && acct && (
                    <>
                      <div className="font-mono text-xs font-bold">{acct.account_number}</div>
                      <div className="text-[11px] text-slate-400">
                        {acct.account_type} · {fmt(acct.available_balance, acct.currency)}
                      </div>
                      <div className="text-[10px] text-emerald-500 font-mono mt-0.5">{r.customer.customer_number}</div>
                    </>
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {/* Workspace */}
        <div className="space-y-5 min-w-0">
          {!active && !loading && (
            <div className="bg-white dark:bg-slate-900 border border-dashed border-slate-300 dark:border-slate-700 rounded-2xl p-12 text-center text-xs text-slate-400">
              Pick a result to open its 360° workspace.
            </div>
          )}

          {active && (
            <>
              {/* Customer banner */}
              <div className="rounded-2xl p-5 bg-gradient-to-br from-emerald-600/90 via-teal-600/80 to-sky-700/80 text-white shadow-lg flex flex-wrap items-center gap-4">
                <div className="h-12 w-12 rounded-full bg-white/20 flex items-center justify-center text-lg font-bold">
                  {(active.customer.first_name || '?')[0]}
                </div>
                <div className="min-w-0">
                  <div className="text-base font-bold truncate">{active.customer.full_name}</div>
                  <div className="text-[11px] font-mono opacity-90">
                    {active.customer.customer_number} · {active.customer.institution_code} · {active.customer.mobile_number || 'no mobile'}
                  </div>
                </div>
                <div className="ml-auto flex items-center gap-2">
                  <Badge tone="bg-white/15 text-white border-white/30">{active.customer.risk_category}</Badge>
                  <Badge tone="bg-white/15 text-white border-white/30">{active.customer.customer_status}</Badge>
                </div>
              </div>

              {/* Cards */}
              <section className="space-y-3">
                <h2 className="text-[11px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                  <CreditCard size={13} /> Cards ({active.cards.length})
                </h2>
                {active.cards.length === 0 && <div className="text-xs text-slate-400 p-4 border border-dashed border-slate-300 dark:border-slate-700 rounded-xl">No cards.</div>}
                {active.cards.map((card: any) => {
                  const shown = revealPan[card.id];
                  return (
                    <div key={card.id} className="grid grid-cols-1 lg:grid-cols-[260px_1fr] gap-4 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-4 shadow-sm">
                      {/* visual card */}
                      <div className={`rounded-xl p-4 text-white flex flex-col justify-between min-h-[150px] shadow-md ${card.card_status === 'ACTIVE' ? 'bg-gradient-to-br from-slate-800 via-slate-700 to-emerald-700' : 'bg-gradient-to-br from-slate-700 via-slate-600 to-rose-800'}`}>
                        <div className="flex items-center justify-between text-[10px] tracking-widest opacity-80">
                          <span>{card.card_product}</span>
                          <button onClick={() => setRevealPan({ ...revealPan, [card.id]: !shown })} className="opacity-80 hover:opacity-100" title="Show / hide PAN">
                            {shown ? <EyeOff size={14} /> : <Eye size={14} />}
                          </button>
                        </div>
                        <div className="font-mono text-sm tracking-widest">{shown ? groupPan(card.pan) : groupPan(maskPan(card.pan))}</div>
                        <div className="flex items-end justify-between text-[10px] font-mono">
                          <span className="truncate max-w-[130px]">{card.cardholder_name}</span>
                          <span>{String(card.expiry_month).padStart(2, '0')}/{String(card.expiry_year).slice(-2)}</span>
                        </div>
                      </div>

                      {/* details & actions */}
                      <div className="space-y-3 min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge tone={statusTone(card.card_status)}>{card.card_status}</Badge>
                          <Badge>{card.card_type}</Badge>
                          {card.institution_code && <Badge tone="bg-sky-500/10 text-sky-400 border-sky-500/30">{card.institution_code}</Badge>}
                          {card.pin_profile && <Badge>{card.pin_profile.verification_method} · {card.pin_profile.pvv || '—'}</Badge>}
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <Btn onClick={() => setCustModal({ kind: 'card', item: card })} tone="sky"><ArrowLeftRight size={12} /> Change customer</Btn>
                          <Btn onClick={() => { setPinCard(card); }}><KeyRound size={12} /> Change PIN</Btn>
                          <Btn onClick={() => toggleCard(card)}>{card.card_status === 'ACTIVE' ? 'Block' : 'Activate'}</Btn>
                          <Btn onClick={() => deleteCard(card)} tone="danger"><Trash2 size={12} /> Delete</Btn>
                        </div>

                        {/* linked accounts */}
                        <div className="rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden">
                          <div className="flex items-center justify-between px-3 py-2 bg-slate-50 dark:bg-slate-950/60 text-[11px] font-bold text-slate-400 uppercase tracking-wider">
                            <span className="flex items-center gap-1.5"><Link2 size={12} /> Linked accounts ({card.links.length})</span>
                            <Btn onClick={() => setLinkModal({ card })} tone="primary"><Plus size={12} /> Link account</Btn>
                          </div>
                          {card.links.length === 0 && <div className="p-3 text-[11px] text-slate-400">No account linked — this card cannot transact.</div>}
                          {card.links.map((l: any) => (
                            <div key={l.link_id} className="flex flex-wrap items-center gap-2 px-3 py-2.5 border-t border-slate-200/70 dark:border-slate-800/70">
                              <div className="min-w-0 flex-1">
                                <div className="font-mono text-xs font-bold">{l.account_number}</div>
                                <div className="text-[10px] text-slate-400">{l.account_type} · {fmt(l.available_balance, l.currency)}{l.owner_customer_id !== card.customer_id && ' · other owner'}</div>
                              </div>
                              <Badge tone={l.account_role === 'PRIMARY' ? 'bg-amber-500/10 text-amber-500 border-amber-500/30' : undefined}>
                                {l.account_role === 'PRIMARY' && <Star size={9} />} {l.account_role} #{l.priority}
                              </Badge>
                              {l.account_role !== 'PRIMARY' && <Btn onClick={() => makePrimary(l)}>Make primary</Btn>}
                              <Btn onClick={() => setLinkModal({ card, swap: l })} tone="sky" title="Replace this link with another account"><Pencil size={12} /> Change</Btn>
                              <Btn onClick={() => unlink(card, l)} tone="danger" title="Unlink"><Unlink size={12} /></Btn>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </section>

              {/* Accounts */}
              <section className="space-y-3">
                <h2 className="text-[11px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                  <Landmark size={13} /> Accounts ({active.accounts.length})
                </h2>
                {active.accounts.length === 0 && <div className="text-xs text-slate-400 p-4 border border-dashed border-slate-300 dark:border-slate-700 rounded-xl">No accounts.</div>}
                <div className="grid grid-cols-1 2xl:grid-cols-2 gap-4">
                  {active.accounts.map((a: any) => (
                    <div key={a.id} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-4 shadow-sm space-y-3">
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <div className="font-mono text-sm font-bold flex items-center gap-1.5"><Hash size={13} className="text-slate-400" />{a.account_number}</div>
                          <div className="text-[11px] text-slate-400">{a.account_type} · branch {a.branch_code || '0001'}{a.institution_code ? ` · ${a.institution_code}` : ''}</div>
                          {a.customer_number && active.kind !== 'customer' && (
                            <div className="text-[10px] text-emerald-500 font-mono mt-0.5">Owner {a.customer_number} — {a.customer_name}</div>
                          )}
                        </div>
                        <Badge tone={statusTone(a.account_status)}>{a.account_status}</Badge>
                      </div>
                      <div className="rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 p-3 grid grid-cols-3 gap-2 text-center">
                        <div>
                          <div className="text-[10px] uppercase tracking-wider text-slate-400">Available</div>
                          <div className="text-sm font-bold text-emerald-500 font-mono">{fmt(a.available_balance)}</div>
                        </div>
                        <div>
                          <div className="text-[10px] uppercase tracking-wider text-slate-400">Ledger</div>
                          <div className="text-sm font-bold font-mono">{fmt(a.ledger_balance)}</div>
                        </div>
                        <div>
                          <div className="text-[10px] uppercase tracking-wider text-slate-400">Overdraft</div>
                          <div className="text-sm font-bold font-mono">{fmt(a.overdraft_limit)}</div>
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <Btn onClick={() => setBalanceAcct(a)} tone="primary"><Wallet size={12} /> Change balance</Btn>
                        <Btn onClick={() => setCustModal({ kind: 'account', item: a })} tone="sky"><ArrowLeftRight size={12} /> Change customer</Btn>
                        <Btn onClick={() => setEditAcct({ ...a })}><Pencil size={12} /> Edit</Btn>
                        <Btn onClick={() => deleteAccount(a)} tone="danger"><Trash2 size={12} /></Btn>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            </>
          )}
        </div>
      </div>

      {/* ----------------------------- Modals -------------------------------- */}
      {balanceAcct && (
        <BalanceModal
          acct={balanceAcct}
          onClose={() => setBalanceAcct(null)}
          onSubmit={async (body) => {
            const ok = await run(
              () => apiFetch(`/maintenance/accounts/${balanceAcct.id}/balance`, { method: 'POST', body: JSON.stringify(body) }),
              `Balance updated for ${balanceAcct.account_number}`
            );
            if (ok) setBalanceAcct(null);
          }}
        />
      )}
      {editAcct && (
        <Modal
          title="Edit account"
          subtitle={editAcct.account_number}
          onClose={() => setEditAcct(null)}
          footer={
            <>
              <Btn onClick={() => setEditAcct(null)}>Cancel</Btn>
              <Btn
                tone="primary"
                onClick={async () => {
                  const ok = await run(
                    () =>
                      apiFetch(`/accounts/${editAcct.id}`, {
                        method: 'PUT',
                        body: JSON.stringify({
                          account_type: editAcct.account_type,
                          account_status: editAcct.account_status,
                          overdraft_limit: editAcct.overdraft_limit,
                        }),
                      }),
                    `Account ${editAcct.account_number} updated`
                  );
                  if (ok) setEditAcct(null);
                }}
              >
                Save
              </Btn>
            </>
          }
        >
          <label className="block text-slate-400">Account type</label>
          <select value={editAcct.account_type} onChange={(e) => setEditAcct({ ...editAcct, account_type: e.target.value })} className={inputCls}>
            <option>SAVINGS</option><option>CURRENT</option><option>CREDIT</option>
          </select>
          <label className="block text-slate-400">Status</label>
          <select value={editAcct.account_status} onChange={(e) => setEditAcct({ ...editAcct, account_status: e.target.value })} className={inputCls}>
            <option>ACTIVE</option><option>BLOCKED</option><option>CLOSED</option>
          </select>
          <label className="block text-slate-400">Overdraft limit</label>
          <input type="number" step="0.01" min="0" value={editAcct.overdraft_limit} onChange={(e) => setEditAcct({ ...editAcct, overdraft_limit: e.target.value })} className={inputCls} />
        </Modal>
      )}
      {pinCard && (
        <PinModal
          card={pinCard}
          onClose={() => setPinCard(null)}
          onSubmit={async (pin) => {
            try {
              const res = await apiFetch(`/cards/${pinCard.id}/pin`, { method: 'POST', body: JSON.stringify({ new_pin: pin }) });
              flash(`PIN changed for ${pinCard.masked_pan} — new PVV/offset ${res.new_pvv}`);
              setPinCard(null);
              await refresh();
            } catch (e: any) {
              setError(e.message);
            }
          }}
        />
      )}
      {custModal && (
        <ChangeCustomerModal
          kind={custModal.kind}
          item={custModal.item}
          onClose={() => setCustModal(null)}
          onSubmit={async (customerId, moveAccounts) => {
            const base = custModal.kind === 'card' ? `/maintenance/cards/${custModal.item.id}` : `/maintenance/accounts/${custModal.item.id}`;
            const ok = await run(
              () => apiFetch(`${base}/reassign-customer`, { method: 'POST', body: JSON.stringify({ customer_id: customerId, move_linked_accounts: moveAccounts }) }),
              custModal.kind === 'card' ? 'Card moved to the new customer' : 'Account moved to the new customer'
            );
            if (ok) setCustModal(null);
          }}
        />
      )}
      {linkModal && (
        <LinkAccountModal
          card={linkModal.card}
          swap={linkModal.swap}
          onClose={() => setLinkModal(null)}
          onSubmit={async (accountId, role) => {
            const ok = await run(
              () =>
                linkModal.swap
                  ? apiFetch(`/maintenance/cards/${linkModal.card.id}/swap-account`, {
                      method: 'POST',
                      body: JSON.stringify({ link_id: linkModal.swap.link_id, new_account_id: accountId }),
                    })
                  : apiFetch(`/cards/${linkModal.card.id}/accounts`, {
                      method: 'POST',
                      body: JSON.stringify({ account_id: accountId, account_role: role, priority: role === 'PRIMARY' ? 1 : linkModal.card.links.length + 1 }),
                    }),
              linkModal.swap ? 'Linked account changed' : 'Account linked'
            );
            if (ok) setLinkModal(null);
          }}
        />
      )}
    </div>
  );
};

// ============================================================================
// Modals
// ============================================================================
const BalanceModal: React.FC<{ acct: any; onClose: () => void; onSubmit: (b: any) => Promise<void> }> = ({ acct, onClose, onSubmit }) => {
  const [operation, setOperation] = useState<'SET' | 'CREDIT' | 'DEBIT'>('SET');
  const [amount, setAmount] = useState(String(acct.available_balance));
  const [sync, setSync] = useState(true);
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);

  const amt = Number(amount);
  const valid = amount !== '' && !Number.isNaN(amt) && (operation === 'SET' || amt > 0);
  const preview = !valid ? null : operation === 'SET' ? amt : operation === 'CREDIT' ? acct.available_balance + amt : acct.available_balance - amt;

  return (
    <Modal
      title="Change balance"
      subtitle={`${acct.account_number} · ${acct.currency}`}
      onClose={onClose}
      footer={
        <>
          <Btn onClick={onClose}>Cancel</Btn>
          <Btn
            tone="primary"
            disabled={!valid || busy}
            onClick={async () => {
              setBusy(true);
              await onSubmit({ operation, amount: amt, sync_ledger: sync, reason: reason || null });
              setBusy(false);
            }}
          >
            Apply
          </Btn>
        </>
      }
    >
      <div className="grid grid-cols-3 gap-1 p-1 rounded-lg bg-slate-100 dark:bg-slate-950 border border-slate-200 dark:border-slate-800">
        {(['SET', 'CREDIT', 'DEBIT'] as const).map((o) => (
          <button
            key={o}
            onClick={() => {
              setOperation(o);
              setAmount(o === 'SET' ? String(acct.available_balance) : '');
            }}
            className={`py-1.5 rounded-md text-[11px] font-bold ${operation === o ? 'bg-emerald-600 text-white' : 'text-slate-500'}`}
          >
            {o === 'SET' ? 'Set to' : o === 'CREDIT' ? 'Add (+)' : 'Deduct (−)'}
          </button>
        ))}
      </div>
      <input autoFocus type="number" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="Amount" className={`${inputCls} text-base font-bold text-emerald-500`} />
      <div className="flex items-center justify-between rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 px-3 py-2 font-mono">
        <span className="text-slate-400">Current → New</span>
        <span>
          {fmt(acct.available_balance)} → <strong className={preview !== null && preview < 0 ? 'text-rose-500' : 'text-emerald-500'}>{preview === null ? '—' : fmt(preview)}</strong>
        </span>
      </div>
      <label className="flex items-center gap-2 text-slate-500">
        <input type="checkbox" checked={sync} onChange={(e) => setSync(e.target.checked)} /> Apply the same change to the ledger balance
      </label>
      <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason (stored in audit trail)" className={inputCls} />
    </Modal>
  );
};

const PinModal: React.FC<{ card: any; onClose: () => void; onSubmit: (pin: string) => Promise<void> }> = ({ card, onClose, onSubmit }) => {
  const [pin, setPin] = useState('1234');
  const ok = /^\d{4,12}$/.test(pin);
  return (
    <Modal
      title="Change card PIN"
      subtitle={card.masked_pan}
      onClose={onClose}
      footer={
        <>
          <Btn onClick={onClose}>Cancel</Btn>
          <Btn tone="primary" disabled={!ok} onClick={() => onSubmit(pin)}>Update PIN</Btn>
        </>
      }
    >
      <p className="text-slate-400">The PVV / offset is recalculated by the Soft-HSM. Test lab PINs only.</p>
      <input value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))} maxLength={12} className={`${inputCls} text-lg tracking-[0.4em] text-center`} />
      {!ok && <p className="text-rose-400">PIN must be 4–12 digits.</p>}
    </Modal>
  );
};

const ChangeCustomerModal: React.FC<{
  kind: 'card' | 'account';
  item: any;
  onClose: () => void;
  onSubmit: (customerId: string, moveAccounts: boolean) => Promise<void>;
}> = ({ kind, item, onClose, onSubmit }) => {
  const [q, setQ] = useState('');
  const [options, setOptions] = useState<any[]>([]);
  const [picked, setPicked] = useState<any | null>(null);
  const [move, setMove] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const t = window.setTimeout(async () => {
      try {
        const res = await apiFetch(`/customers?q=${encodeURIComponent(q.trim())}&page_size=8`);
        setOptions(res.items || []);
      } catch {
        setOptions([]);
      }
    }, 250);
    return () => window.clearTimeout(t);
  }, [q]);

  const currentId = item.customer_id;
  return (
    <Modal
      title={kind === 'card' ? 'Move card to another customer' : 'Move account to another customer'}
      subtitle={kind === 'card' ? item.masked_pan : item.account_number}
      onClose={onClose}
      footer={
        <>
          <Btn onClick={onClose}>Cancel</Btn>
          <Btn
            tone="primary"
            disabled={!picked || busy}
            onClick={async () => {
              setBusy(true);
              await onSubmit(picked.id, move);
              setBusy(false);
            }}
          >
            Move
          </Btn>
        </>
      }
    >
      <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search customer no / name / mobile…" className={inputCls} />
      <div className="max-h-52 overflow-y-auto rounded-lg border border-slate-200 dark:border-slate-800 divide-y divide-slate-200/60 dark:divide-slate-800/60">
        {options.length === 0 && <div className="p-3 text-slate-400">No customers.</div>}
        {options.map((c) => (
          <button
            key={c.id}
            disabled={c.id === currentId}
            onClick={() => setPicked(c)}
            className={`w-full text-left px-3 py-2 disabled:opacity-40 ${picked?.id === c.id ? 'bg-emerald-500/10' : 'hover:bg-slate-50 dark:hover:bg-slate-800/50'}`}
          >
            <div className="font-semibold">{c.first_name} {c.last_name}</div>
            <div className="text-[10px] font-mono text-emerald-500">{c.customer_number} · {c.institution_code}{c.id === currentId ? ' · current owner' : ''}</div>
          </button>
        ))}
      </div>
      {kind === 'card' && (
        <label className="flex items-center gap-2 text-slate-500">
          <input type="checkbox" checked={move} onChange={(e) => setMove(e.target.checked)} /> Also move the accounts linked to this card
        </label>
      )}
      {picked && <p className="text-[11px] text-amber-500">Will be assigned to {picked.customer_number}. A cross-bank move can change routing for this {kind}.</p>}
    </Modal>
  );
};

const LinkAccountModal: React.FC<{
  card: any;
  swap?: any;
  onClose: () => void;
  onSubmit: (accountId: string, role: string) => Promise<void>;
}> = ({ card, swap, onClose, onSubmit }) => {
  const [q, setQ] = useState('');
  const [options, setOptions] = useState<any[]>([]);
  const [picked, setPicked] = useState<any | null>(null);
  const [role, setRole] = useState('SECONDARY');
  const [busy, setBusy] = useState(false);
  const linked = new Set<string>(card.links.map((l: any) => l.account_id));

  useEffect(() => {
    const t = window.setTimeout(async () => {
      try {
        setOptions(await apiFetch(`/maintenance/account-options?q=${encodeURIComponent(q.trim())}&limit=30`));
      } catch {
        setOptions([]);
      }
    }, 250);
    return () => window.clearTimeout(t);
  }, [q]);

  return (
    <Modal
      title={swap ? 'Change linked account' : 'Link account to card'}
      subtitle={swap ? `${card.masked_pan} · replacing ${swap.account_number} (${swap.account_role})` : card.masked_pan}
      onClose={onClose}
      footer={
        <>
          <Btn onClick={onClose}>Cancel</Btn>
          <Btn
            tone="primary"
            disabled={!picked || busy}
            onClick={async () => {
              setBusy(true);
              await onSubmit(picked.id, role);
              setBusy(false);
            }}
          >
            {swap ? 'Replace' : 'Link'}
          </Btn>
        </>
      }
    >
      <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search account no / owner…" className={inputCls} />
      <div className="max-h-56 overflow-y-auto rounded-lg border border-slate-200 dark:border-slate-800 divide-y divide-slate-200/60 dark:divide-slate-800/60">
        {options.length === 0 && <div className="p-3 text-slate-400">No accounts.</div>}
        {options.map((a) => {
          const already = linked.has(a.id);
          return (
            <button
              key={a.id}
              disabled={already}
              onClick={() => setPicked(a)}
              className={`w-full text-left px-3 py-2 disabled:opacity-40 ${picked?.id === a.id ? 'bg-emerald-500/10' : 'hover:bg-slate-50 dark:hover:bg-slate-800/50'}`}
            >
              <div className="font-mono font-bold">{a.account_number} <span className="font-sans font-normal text-slate-400">· {a.account_type}</span></div>
              <div className="text-[10px] text-slate-400">
                {a.customer_name} ({a.customer_number}) · {fmt(a.available_balance, a.currency)}{already ? ' · already linked' : ''}
              </div>
            </button>
          );
        })}
      </div>
      {!swap && (
        <>
          <label className="block text-slate-400">Role</label>
          <select value={role} onChange={(e) => setRole(e.target.value)} className={inputCls}>
            <option value="SECONDARY">SECONDARY</option>
            <option value="PRIMARY">PRIMARY (demotes the current primary)</option>
          </select>
        </>
      )}
    </Modal>
  );
};

export default CustomerDataMaintenancePage;
""",
}

CUSTOMERS_PAGE_SEGMENT = r"""// ============================================================================
// PAGE 2: CUSTOMERS (CIF)
// ============================================================================
export const CustomersPage: React.FC = () => {
  const navigate = useNavigate();
  const [customers, setCustomers] = useState<any[]>([]);
  const [institutions, setInstitutions] = useState<any[]>([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [loading, setLoading] = useState(false);
  const [editCust, setEditCust] = useState<any | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [errorBanner, setErrorBanner] = useState('');
  const [okBanner, setOkBanner] = useState('');
  const reqId = React.useRef(0);

  const newCustNo = () => `CUST-${Math.floor(1006 + Math.random() * 9000)}`;
  const emptyForm = () => ({
    customer_number: newCustNo(),
    first_name: '',
    last_name: '',
    email: '',
    mobile_number: '+8801700000099',
    address: 'Dhaka, Bangladesh',
    customer_status: 'ACTIVE',
    risk_category: 'NORMAL',
    institution_id: '',
  });
  const [form, setForm] = useState(emptyForm());

  const inputCls =
    'w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-emerald-500/40 focus:border-emerald-500';

  const load = React.useCallback(async () => {
    const id = ++reqId.current;
    setLoading(true);
    try {
      const qs = new URLSearchParams({ page: String(page), page_size: '15' });
      if (searchTerm.trim()) qs.set('q', searchTerm.trim());
      if (statusFilter) qs.set('status', statusFilter);
      const [cRes, iList] = await Promise.all([apiFetch(`/customers?${qs.toString()}`), apiFetch('/institutions')]);
      if (id !== reqId.current) return;
      const items = cRes.items || cRes;
      setCustomers(items);
      setTotalCount(cRes.total ?? items.length);
      setTotalPages(cRes.total_pages || 1);
      setInstitutions(iList);
      setForm((prev) => (!prev.institution_id && iList.length > 0 ? { ...prev, institution_id: iList[0].id } : prev));
    } catch (err: any) {
      if (id === reqId.current) setErrorBanner(err.message || 'Failed to load customers');
    } finally {
      if (id === reqId.current) setLoading(false);
    }
  }, [page, searchTerm, statusFilter]);

  // live search: debounce typing, reload on page / filter change
  useEffect(() => {
    const t = window.setTimeout(load, 250);
    return () => window.clearTimeout(t);
  }, [load]);

  const flash = (m: string) => {
    setErrorBanner('');
    setOkBanner(m);
    window.setTimeout(() => setOkBanner((c) => (c === m ? '' : c)), 5000);
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorBanner('');
    try {
      await apiFetch('/customers', { method: 'POST', body: JSON.stringify(form) });
      flash(`Customer ${form.customer_number} created`);
      setForm({ ...emptyForm(), institution_id: form.institution_id });
      setShowCreate(false);
      setPage(1);
      load();
    } catch (err: any) {
      setErrorBanner(err.message);
    }
  };

  const handleUpdateCustomer = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorBanner('');
    try {
      await apiFetch(`/customers/${editCust.id}`, {
        method: 'PUT',
        body: JSON.stringify({
          first_name: editCust.first_name,
          last_name: editCust.last_name,
          email: editCust.email,
          mobile_number: editCust.mobile_number,
          address: editCust.address,
          risk_category: editCust.risk_category,
          customer_status: editCust.customer_status,
        }),
      });
      flash(`Customer ${editCust.customer_number} updated`);
      setEditCust(null);
      load();
    } catch (err: any) {
      setErrorBanner(err.message);
    }
  };

  const handleDeleteCustomer = async (c: any, force: boolean = false) => {
    setErrorBanner('');
    if (!force && !confirm(`Delete customer ${c.customer_number}?`)) return;
    try {
      await apiFetch(`/customers/${c.id}${force ? '?force=true' : ''}`, { method: 'DELETE' });
      flash(`Customer ${c.customer_number} deleted`);
      load();
    } catch (err: any) {
      if (!force && err.message.toLowerCase().includes('cannot delete')) {
        if (confirm(`${err.message}\n\nFORCE delete this customer together with its accounts and cards (lab only)?`)) {
          handleDeleteCustomer(c, true);
        }
      } else {
        setErrorBanner(err.message);
      }
    }
  };

  const toggleStatus = async (c: any) => {
    const next = c.customer_status === 'ACTIVE' ? 'BLOCKED' : 'ACTIVE';
    try {
      await apiFetch(`/customers/${c.id}/status?status=${next}`, { method: 'PATCH' });
      load();
    } catch (err: any) {
      setErrorBanner(err.message);
    }
  };

  const riskTone = (r: string) =>
    r === 'VIP' ? 'bg-amber-500/10 text-amber-500 border-amber-500/30' : r === 'HIGH' ? 'bg-rose-500/10 text-rose-500 border-rose-500/30' : 'bg-slate-500/10 text-slate-400 border-slate-500/30';

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Customer Management (CIF)</h1>
          <p className="text-xs text-slate-500">Create, manage and audit synthetic host customers across member banks</p>
        </div>
        <button
          onClick={() => setShowCreate((v) => !v)}
          className="bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg px-4 py-2 text-xs font-semibold shadow"
        >
          {showCreate ? 'Close' : '+ New customer'}
        </button>
      </div>

      {okBanner && <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-500 text-xs font-mono">{okBanner}</div>}
      {errorBanner && (
        <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs font-mono flex justify-between gap-3">
          <span>{errorBanner}</span>
          <button onClick={() => setErrorBanner('')} className="opacity-70 hover:opacity-100">✕</button>
        </div>
      )}

      {showCreate && (
        <form onSubmit={handleCreate} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 grid grid-cols-1 md:grid-cols-4 gap-3 shadow-sm">
          <input value={form.customer_number} onChange={(e) => setForm({ ...form, customer_number: e.target.value })} placeholder="Customer Number" className={`${inputCls} font-mono`} required />
          <select value={form.institution_id} onChange={(e) => setForm({ ...form, institution_id: e.target.value })} className={`${inputCls} font-mono`}>
            {institutions.map((inst) => (
              <option key={inst.id} value={inst.id}>{inst.institution_code} — {inst.short_name || inst.name}</option>
            ))}
          </select>
          <input value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} placeholder="First name" className={inputCls} required />
          <input value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} placeholder="Last name" className={inputCls} />
          <input value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="Email" className={inputCls} />
          <input value={form.mobile_number} onChange={(e) => setForm({ ...form, mobile_number: e.target.value })} placeholder="Mobile" className={`${inputCls} font-mono`} />
          <select value={form.risk_category} onChange={(e) => setForm({ ...form, risk_category: e.target.value })} className={`${inputCls} font-mono`}>
            <option value="NORMAL">RISK: NORMAL</option>
            <option value="VIP">RISK: VIP</option>
            <option value="HIGH">RISK: HIGH</option>
          </select>
          <button type="submit" className="bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg px-4 py-2 text-xs font-semibold">Create customer</button>
        </form>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-4 shadow-sm">
        <div className="flex flex-wrap items-center gap-2 flex-1">
          <input
            value={searchTerm}
            onChange={(e) => { setSearchTerm(e.target.value); setPage(1); }}
            placeholder="Search customer no, name, phone or email…"
            className={`${inputCls} max-w-md font-mono`}
          />
          <select value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }} className={`${inputCls} w-auto font-mono`}>
            <option value="">All status</option>
            <option value="ACTIVE">ACTIVE</option>
            <option value="BLOCKED">BLOCKED</option>
          </select>
        </div>
        <div className="flex items-center gap-2 text-xs font-mono text-slate-400">
          <span>{loading ? 'Loading…' : <>Total <strong className="text-emerald-500">{totalCount}</strong></>}</span>
          <button disabled={page <= 1} onClick={() => setPage(page - 1)} className="px-2.5 py-1 rounded-lg border border-slate-300 dark:border-slate-700 disabled:opacity-40">Prev</button>
          <span>{page} / {totalPages}</span>
          <button disabled={page >= totalPages} onClick={() => setPage(page + 1)} className="px-2.5 py-1 rounded-lg border border-slate-300 dark:border-slate-700 disabled:opacity-40">Next</button>
        </div>
      </div>

      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-2 overflow-x-auto shadow-sm">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="text-slate-400 text-[11px] uppercase tracking-wider">
              <th className="px-3 py-2.5">Customer</th>
              <th className="px-3 py-2.5">Bank</th>
              <th className="px-3 py-2.5">Mobile</th>
              <th className="px-3 py-2.5">Risk</th>
              <th className="px-3 py-2.5">Status</th>
              <th className="px-3 py-2.5 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200/60 dark:divide-slate-800/60">
            {customers.length === 0 && (
              <tr><td colSpan={6} className="px-3 py-10 text-center text-slate-400">{loading ? 'Loading…' : 'No customers match.'}</td></tr>
            )}
            {customers.map((c) => (
              <tr key={c.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/40">
                <td className="px-3 py-2.5">
                  <div className="flex items-center gap-3">
                    <div className="h-8 w-8 rounded-full bg-emerald-500/15 text-emerald-500 flex items-center justify-center font-bold">{(c.first_name || '?')[0]}</div>
                    <div>
                      <div className="font-semibold">{c.first_name} {c.last_name}</div>
                      <div className="font-mono text-[11px] text-emerald-500">{c.customer_number}</div>
                    </div>
                  </div>
                </td>
                <td className="px-3 py-2.5 font-mono font-bold text-sky-400">{c.institution_code || 'XBANK'}</td>
                <td className="px-3 py-2.5 font-mono">{c.mobile_number}</td>
                <td className="px-3 py-2.5"><span className={`px-2 py-0.5 rounded-full border text-[10px] font-bold ${riskTone(c.risk_category)}`}>{c.risk_category}</span></td>
                <td className="px-3 py-2.5">
                  <span className={`px-2 py-0.5 rounded-full border text-[10px] font-bold ${c.customer_status === 'ACTIVE' ? 'bg-emerald-500/10 text-emerald-500 border-emerald-500/30' : 'bg-rose-500/10 text-rose-500 border-rose-500/30'}`}>{c.customer_status}</span>
                </td>
                <td className="px-3 py-2.5">
                  <div className="flex items-center justify-end gap-3 text-[11px]">
                    <button onClick={() => navigate(`/customer-maintenance?mode=customer&q=${encodeURIComponent(c.customer_number)}`)} className="text-violet-400 hover:underline">360° view</button>
                    <button onClick={() => setEditCust({ ...c })} className="text-emerald-500 hover:underline">Edit</button>
                    <button onClick={() => toggleStatus(c)} className="text-sky-500 hover:underline">{c.customer_status === 'ACTIVE' ? 'Block' : 'Activate'}</button>
                    <button onClick={() => handleDeleteCustomer(c)} className="text-rose-500 hover:underline">Delete</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {editCust && (
        <div className="fixed inset-0 bg-slate-950/70 backdrop-blur-sm flex items-center justify-center p-4 z-50" onClick={() => setEditCust(null)}>
          <form onSubmit={handleUpdateCustomer} onClick={(e) => e.stopPropagation()} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-2xl p-6 max-w-md w-full space-y-3 shadow-2xl text-xs">
            <h2 className="text-sm font-bold">Edit customer <span className="font-mono text-emerald-500">{editCust.customer_number}</span></h2>
            <input value={editCust.first_name || ''} onChange={(e) => setEditCust({ ...editCust, first_name: e.target.value })} placeholder="First name" className={inputCls} required />
            <input value={editCust.last_name || ''} onChange={(e) => setEditCust({ ...editCust, last_name: e.target.value })} placeholder="Last name" className={inputCls} />
            <input value={editCust.email || ''} onChange={(e) => setEditCust({ ...editCust, email: e.target.value })} placeholder="Email" className={inputCls} />
            <input value={editCust.mobile_number || ''} onChange={(e) => setEditCust({ ...editCust, mobile_number: e.target.value })} placeholder="Mobile" className={`${inputCls} font-mono`} />
            <div className="grid grid-cols-2 gap-3">
              <select value={editCust.risk_category} onChange={(e) => setEditCust({ ...editCust, risk_category: e.target.value })} className={inputCls}>
                <option value="NORMAL">NORMAL</option><option value="VIP">VIP</option><option value="HIGH">HIGH</option>
              </select>
              <select value={editCust.customer_status} onChange={(e) => setEditCust({ ...editCust, customer_status: e.target.value })} className={inputCls}>
                <option value="ACTIVE">ACTIVE</option><option value="BLOCKED">BLOCKED</option>
              </select>
            </div>
            <div className="flex justify-end gap-2 pt-3 border-t border-slate-200 dark:border-slate-800">
              <button type="button" onClick={() => setEditCust(null)} className="px-3 py-1.5 rounded-lg text-xs">Cancel</button>
              <button type="submit" className="bg-emerald-600 text-white px-4 py-1.5 rounded-lg text-xs font-semibold">Save changes</button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
};

"""

REPLACEMENTS = [
    ('backend/app/host_engine.py',
     r"""from app.rules_evaluator import SafeAstEvaluator, build_rule_context""",
     r"""from app.rules_evaluator import SafeAstEvaluator, build_rule_context, ccy_alpha""",
     'engine: import ccy_alpha'),
    ('backend/app/host_engine.py',
     r"""        if mti == '0220':
            self._add_check('Financial Advice Presentment (0220)', 'PASSED', '00', f'Received clearing advice for RRN {rrn}')
""",
     r"""        if mti == '0220':
            # FIX v2: an advice that confirms an already-approved 0200 must NOT debit the account again.
            dup_advice = self.db.query(Transaction).filter(
                Transaction.rrn == rrn,
                Transaction.stan == stan,
                Transaction.mti == '0220',
                Transaction.authorization_status == 'APPROVED',
            ).first()
            if dup_advice:
                self._add_check('Financial Advice Presentment (0220)', 'FAILED', '94', f'Duplicate advice for RRN {rrn}')
                return self._finalize_transaction(
                    tx_id=tx_id, tx_ref=tx_ref, mti=mti, fields=input_fields, response_code='94',
                    raw_request_msg=raw_req_msg,
                    source_channel=request_data.get('source_channel', 'SIMULATOR'),
                    idempotency_key=idem_key,
                )
            original_0200 = self.db.query(Transaction).filter(
                Transaction.rrn == rrn,
                Transaction.mti == '0200',
                Transaction.authorization_status == 'APPROVED',
            ).first()
            if original_0200:
                self._add_check(
                    'Financial Advice Presentment (0220)', 'PASSED', '00',
                    f'Advice matches approved original {original_0200.transaction_reference}; no second posting',
                )
                return self._finalize_transaction(
                    tx_id=tx_id, tx_ref=tx_ref, mti=mti, fields=input_fields, response_code='00',
                    raw_request_msg=raw_req_msg,
                    tx_code=original_0200.transaction_code,
                    source_channel=request_data.get('source_channel', 'SIMULATOR'),
                    idempotency_key=idem_key,
                    issuer_institution_id=original_0200.issuer_institution_id,
                    acquirer_institution_id=original_0200.acquirer_institution_id,
                    ps_code=original_0200.ps_code or 'ITCL',
                )
            self._add_check('Financial Advice Presentment (0220)', 'PASSED', '00',
                            f'No original found for RRN {rrn}; presenting as stand-in advice')
""",
     'engine: 0220 advice no longer double-debits'),
    ('backend/app/host_engine.py',
     r"""        rule_ctx = build_rule_context(
            mti=mti,""",
     r"""        rule_card_limit = (
            self.db.query(CardLimit).filter(CardLimit.card_id == card.id, CardLimit.status == "ACTIVE").first()
            if card else None
        )
        rule_ctx = build_rule_context(
            mti=mti,""",
     'engine: load card_limit before rule evaluation'),
    ('backend/app/host_engine.py',
     r"""            ps_code=ps_code_val,
        )
        active_rules = self.db.query(AuthorizerRule)""",
     r"""            ps_code=ps_code_val,
            card_limit=rule_card_limit,
        )
        active_rules = self.db.query(AuthorizerRule)""",
     'engine: pass card_limit into build_rule_context'),
    ('backend/app/host_engine.py',
     r"""        currency = input_fields.get("49", "BDT")""",
     r"""        currency = ccy_alpha(input_fields.get("49", "050"))""",
     'engine: DE49 numeric -> alpha currency'),
    ('backend/app/host_engine.py',
     r"""currency=account.currency if account else fields.get("49", "BDT"),""",
     r"""currency=account.currency if account else ccy_alpha(fields.get("49", "050")),""",
     'engine: stored currency alpha'),
    ('backend/app/rules_evaluator.py',
     r"""def build_rule_context(""",
     '# ISO 4217 numeric -> alpha (DE49 is numeric on the wire; rules and storage use alpha codes)\nCCY_NUM_TO_ALPHA = {\n    "050": "BDT", "840": "USD", "978": "EUR", "826": "GBP", "356": "INR",\n    "392": "JPY", "702": "SGD", "784": "AED", "682": "SAR", "156": "CNY",\n}\n\n\ndef ccy_alpha(code: str) -> str:\n    """\'050\' -> \'BDT\'. Already-alpha codes pass through; unknown numerics are returned unchanged."""\n    c = str(code or "").strip().upper()\n    return CCY_NUM_TO_ALPHA.get(c.zfill(3), c) if c.isdigit() else (c or "BDT")\n\n\ndef build_rule_context(',
     'rules: ccy_alpha helper'),
    ('backend/app/rules_evaluator.py',
     r"""        "currency": fields.get("49", "BDT"),""",
     r"""        "currency": ccy_alpha(fields.get("49", "050")),
        "currency_code": fields.get("49", "050"),""",
     'rules: context currency alpha + numeric'),
    ('backend/app/context_trace.py',
     r"""class CorrelationTraceMiddleware(BaseHTTPMiddleware):""",
     'from app.config import settings as _settings\n\n_SENSITIVE_HEADERS = {"authorization", "proxy-authorization", "cookie", "set-cookie", "x-api-key"}\n_SENSITIVE_KEYS = {"password", "new_pin", "pin", "pin_block", "test_clear_pin_helper", "clear_key_hex", "key_hex"}\n_SENSITIVE_SUBSTR = ("password", "secret", "clear_key", "private")\n\n\ndef redact_headers(headers) -> Dict[str, str]:\n    """Copy request headers for the audit log without credentials."""\n    return {k: ("***" if k.lower() in _SENSITIVE_HEADERS else v) for k, v in dict(headers).items()}\n\n\ndef redact_body(obj: Any, _parent: str = "") -> Any:\n    """Mask passwords / PIN material (always) and PAN in DE2 (only when LOG_RAW_DATA is off)."""\n    if isinstance(obj, dict):\n        out: Dict[str, Any] = {}\n        for k, v in obj.items():\n            lk = str(k).lower()\n            if lk in _SENSITIVE_KEYS or any(s in lk for s in _SENSITIVE_SUBSTR):\n                out[k] = "***"\n            elif _parent == "fields" and str(k) == "52":\n                out[k] = "***"\n            elif _parent == "fields" and str(k) == "2" and isinstance(v, str) and len(v) > 10 \\\n                    and not getattr(_settings, "LOG_RAW_DATA", True):\n                out[k] = v[:6] + "*" * (len(v) - 10) + v[-4:]\n            else:\n                out[k] = redact_body(v, lk)\n        return out\n    if isinstance(obj, list):\n        return [redact_body(i, _parent) for i in obj]\n    return obj\n\n\nclass CorrelationTraceMiddleware(BaseHTTPMiddleware):',
     'trace: redaction helpers'),
    ('backend/app/context_trace.py',
     r"""request_headers=dict(request.headers),""",
     r"""request_headers=redact_headers(request.headers),""",
     'trace: redact Authorization header in ApiAuditLog'),
    ('backend/app/context_trace.py',
     r"""request_body=req_body,""",
     r"""request_body=redact_body(req_body),""",
     'trace: redact secrets in request body'),
    ('backend/app/api_routes.py',
     '"49": "BDT"',
     '"49": "050"',
     'api: sample scenarios DE49 numeric', {'replace_all': True}),
    ('backend/app/api_routes.py',
     r"""'49': 'BDT'""",
     r"""'49': '050'""",
     'api: run-scenarios DE49 numeric', {'replace_all': True}),
    ('backend/app/api_routes.py',
     r"""    api_log = db.query(ApiAuditLog).filter(ApiAuditLog.correlation_id == correlation_id).first()
    crypto_steps = db.query(CryptoEvent).filter(CryptoEvent.correlation_id == correlation_id).order_by(CryptoEvent.step_number.asc()).all()
    return {
        'correlation_id': correlation_id,
        'api_audit': serialize_entity(api_log) if api_log else None,
        'crypto_steps': [serialize_entity(c) for c in crypto_steps],
    }""",
     r"""    api_log = db.query(ApiAuditLog).filter(ApiAuditLog.correlation_id == correlation_id).first()
    crypto_steps = db.query(CryptoEvent).filter(CryptoEvent.correlation_id == correlation_id).order_by(CryptoEvent.step_number.asc()).all()
    # SWITCH_TX rows of the log portal carry the transaction_reference, HSM rows the request_reference
    tx = db.query(Transaction).filter(Transaction.transaction_reference == correlation_id).first()
    hsm_ops = db.query(HsmOperation).filter(HsmOperation.request_reference == correlation_id).all()
    return {
        'correlation_id': correlation_id,
        'api_audit': serialize_entity(api_log) if api_log else None,
        'crypto_steps': [serialize_entity(c) for c in crypto_steps],
        'transaction': {
            'id': tx.id,
            'transaction_reference': tx.transaction_reference,
            'mti': tx.mti,
            'transaction_code': tx.transaction_code,
            'stan': tx.stan,
            'rrn': tx.rrn,
            'masked_pan': tx.masked_pan,
            'transaction_amount': float(tx.transaction_amount),
            'currency': tx.currency,
            'authorization_status': tx.authorization_status,
            'created_at': tx.created_at.isoformat() if tx.created_at else None,
        } if tx else None,
        'hsm_operations': [serialize_entity(h) for h in hsm_ops],
    }""",
     'api: correlation endpoint resolves transaction / HSM references'),
    ('backend/app/settlement_service.py',
     r"""        .all()
    )

    batch = SettlementBatch(""",
     r"""        .all()
    )
    # FIX v2: a 0220 that only confirms an already-approved 0200 (same RRN) must not be settled twice
    approved_0200_rrns = {
        r[0] for r in db.query(Transaction.rrn)
        .filter(Transaction.mti == "0200", Transaction.authorization_status == "APPROVED").all()
    }
    unsettled_txs = [t for t in unsettled_txs if not (t.mti == "0220" and t.rrn in approved_0200_rrns)]

    batch = SettlementBatch(""",
     'settlement: skip 0220 duplicates of approved 0200'),
    ('backend/app/settlement_service.py',
     r"""        # Multi-lateral position tracking
        if tx.issuer_institution_id:
            _ensure_inst(tx.issuer_institution_id)
            # Issuer owes the settlement switch for customer withdrawals
            positions[tx.issuer_institution_id]["debit_volume"] += tx.transaction_amount
            positions[tx.issuer_institution_id]["debit_count"] += 1
            # Issuer receives interchange fee
            positions[tx.issuer_institution_id]["net_fee"] += ic_fee

        if tx.acquirer_institution_id:
            _ensure_inst(tx.acquirer_institution_id)
            # Acquirer is credited with the cash dispensed
            positions[tx.acquirer_institution_id]["credit_volume"] += tx.transaction_amount
            positions[tx.acquirer_institution_id]["credit_count"] += 1
            # Acquirer pays interchange fee and switch fee
            positions[tx.acquirer_institution_id]["net_fee"] -= total_fee
""",
     r"""        # Multi-lateral position tracking
        on_us = bool(tx.issuer_institution_id and tx.issuer_institution_id == tx.acquirer_institution_id)
        if on_us:
            # FIX v2: a bank does not settle with itself — no volume, no interchange; only the switch fee is owed.
            _ensure_inst(tx.issuer_institution_id)
            positions[tx.issuer_institution_id]["net_fee"] -= sch_fee
            continue

        if tx.issuer_institution_id:
            _ensure_inst(tx.issuer_institution_id)
            # Issuer owes the settlement switch for customer withdrawals
            positions[tx.issuer_institution_id]["debit_volume"] += tx.transaction_amount
            positions[tx.issuer_institution_id]["debit_count"] += 1
            # Issuer receives interchange fee
            positions[tx.issuer_institution_id]["net_fee"] += ic_fee

        if tx.acquirer_institution_id:
            _ensure_inst(tx.acquirer_institution_id)
            # Acquirer is credited with the cash dispensed
            positions[tx.acquirer_institution_id]["credit_volume"] += tx.transaction_amount
            positions[tx.acquirer_institution_id]["credit_count"] += 1
            # Acquirer pays interchange fee and switch fee
            positions[tx.acquirer_institution_id]["net_fee"] -= total_fee
""",
     'settlement: on-us transactions no longer self-cancel'),
    ('backend/app/hsm_adapter.py',
     r"""        cipher = cls.des3_ecb_hex(tsp, pvk_hex, decrypt=False)
        pvv = "".join(ch for ch in cipher if ch.isdigit())
        for ch in cipher:
            if ch in "ABCDEF":
                pvv += str(int(ch, 16) - 10)
        return pvv[:4]
""",
     '        cipher = cls.des3_ecb_hex(tsp, pvk_hex, decrypt=False)\n        return cls.decimalize_pvv(cipher)[:4]\n\n    @staticmethod\n    def decimalize_pvv(cipher_hex: str) -> str:\n        """Visa PVV decimalisation: digits 0-9 left to right, then A-F mapped to 0-5 (hex value - 10)."""\n        digits = "".join(ch for ch in cipher_hex if ch.isdigit())\n        alphas = "".join(str(int(ch, 16) - 10) for ch in cipher_hex if ch in "ABCDEF")\n        return digits + alphas\n',
     'hsm: single PVV decimalisation'),
    ('backend/app/config.py',
     r"""    LOG_RAW_DATA: bool = True
""",
     r"""    LOG_RAW_DATA: bool = True
    # When true the app refuses to start with the built-in SECRET_KEY / ADMIN_PASSWORD (set it on Render).
    ENFORCE_SECURE_DEFAULTS: bool = False
""",
     'config: ENFORCE_SECURE_DEFAULTS flag'),
    ('backend/app/config.py',
     r"""    @property
    def cors_origin_list(self) -> List[str]:""",
     r"""    def insecure_defaults(self) -> List[str]:
        problems: List[str] = []
        if self.SECRET_KEY.startswith("dev-secret-key"):
            problems.append("SECRET_KEY is the built-in development value")
        if self.ADMIN_PASSWORD == "AdminPassword123!":
            problems.append("ADMIN_PASSWORD is the built-in default")
        return problems

    @property
    def cors_origin_list(self) -> List[str]:""",
     'config: insecure_defaults()'),
    ('backend/app/main.py',
     r"""from app.routers.institutions_router import router as institutions_router
""",
     r"""from app.routers.institutions_router import router as institutions_router
from app.routers.maintenance_router import router as maintenance_router
""",
     'main: import maintenance router'),
    ('backend/app/main.py',
     r"""app.include_router(institutions_router)
""",
     r"""app.include_router(institutions_router)
app.include_router(maintenance_router)
""",
     'main: include maintenance router'),
    ('backend/app/main.py',
     r"""    init_db()
    db = SessionLocal()""",
     r"""    problems = settings.insecure_defaults()
    if problems:
        import logging
        logging.getLogger("uvicorn.error").warning("INSECURE CONFIG: %s — override via environment variables.", "; ".join(problems))
        if settings.ENFORCE_SECURE_DEFAULTS:
            raise RuntimeError("Refusing to start: " + "; ".join(problems))
    init_db()
    db = SessionLocal()""",
     'main: warn / refuse insecure defaults'),
]

PROGRESS_BLOCK = r"""<!-- PROGRESS:fix_all_v2 -->
## [@@TS@@] `fix_all_v2` — Consolidated fixes + Customer Maintenance 360 rebuild
- **Touched Files**: `frontend/src/App.tsx`, `frontend/src/pages/BankingEntities.tsx`, `frontend/src/pages/CustomerDataMaintenancePage.tsx`, `backend/app/routers/maintenance_router.py`, `backend/app/{host_engine,rules_evaluator,context_trace,api_routes,settlement_service,hsm_adapter,card_crypto_service,config,main,schemas}.py`, `backend/tests/test_fix_v2.py`
- [x] **Completed**: Customers tab build error (undeclared `editAcct`), App.tsx stray patch text, tabbed CUSTOMER/PAN/ACCOUNT maintenance workbench with re-link / change customer / change balance, 0220 double-debit, rule ctx `card_limit`, audit token redaction, correlation lookup for SWITCH_TX rows, on-us settlement netting, DE49 numeric currency, shared PVV decimalisation, DB-first crypto key resolution, secure-default warning.
- **Do NOT re-run** `fix_card_issue_and_pvv.py`, `fix_dynamic_maintenance_and_cards.py`, `repair_all_pending.py` — they overwrite `BankingEntities.tsx` / `CustomerDataMaintenancePage.tsx` with older versions.
""".replace('@@TS@@', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

CONTRACT_BLOCK = r"""<!-- CONTRACT:fix_all_v2 -->
## Customer Data Maintenance 360 (fix_all_v2)
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/maintenance/lookup?mode=customer\|pan\|account&q=` | Unified 360 record `{kind, customer, cards[], accounts[]}`; `pan` returns ONLY the matched card, `account` ONLY the matched account |
| GET | `/api/maintenance/account-options?q=` | Accounts selectable as link / swap target |
| POST | `/api/maintenance/cards/{id}/reassign-customer` | `{customer_id, move_linked_accounts}` |
| POST | `/api/maintenance/accounts/{id}/reassign-customer` | `{customer_id}` |
| POST | `/api/maintenance/cards/{id}/swap-account` | `{link_id, new_account_id}` keeps role + priority |
| POST | `/api/maintenance/accounts/{id}/balance` | `{operation: SET\|CREDIT\|DEBIT, amount, sync_ledger, reason}` — audited, honours overdraft floor |

Notes: `ApiAuditLog` redacts `Authorization`, cookies, passwords and PIN material. `GET /api/logs/correlation/{id}` also resolves transaction / HSM references.
"""



# ---------------------------------------------------------------------------
# machinery
# ---------------------------------------------------------------------------
class Workspace:
    def __init__(self, base: Path):
        self.base = base
        self.staged: Dict[str, str] = {}      # rel -> new normalised (LF) text
        self.original: Dict[str, str] = {}    # rel -> original normalised text ('' if new file)
        self.crlf: Dict[str, bool] = {}
        self.log: List[Tuple[str, str, str]] = []

    def path(self, rel: str) -> Path:
        p = (self.base / rel).resolve()
        if not p.is_relative_to(self.base):
            raise PatchError(f"path escapes base dir: {rel}")
        if p.name in PROTECTED_NAMES or p.suffix.lower() in PROTECTED_SUFFIXES:
            raise PatchError(f"refusing to touch protected file: {rel}")
        return p

    def read(self, rel: str) -> str:
        if rel in self.staged:
            return self.staged[rel]
        p = self.path(rel)
        if not p.exists():
            raise PatchError(f"file not found: {rel}")
        raw = p.read_bytes().decode("utf-8")
        self.crlf[rel] = "\r\n" in raw
        text = raw.replace("\r\n", "\n")
        self.original[rel] = text
        self.staged[rel] = text
        return text

    def set(self, rel: str, text: str, note: str) -> None:
        if rel not in self.staged:
            p = self.path(rel)
            if p.exists():
                self.read(rel)
            else:
                self.original[rel] = ""
                self.crlf[rel] = True  # repo is edited on Windows
        if self.staged.get(rel) == text:
            self.log.append(("SKIP", rel, note + " (already applied)"))
            return
        self.staged[rel] = text
        self.log.append(("EDIT" if self.original.get(rel) else "NEW ", rel, note))

    # -- primitives ---------------------------------------------------------
    def replace(self, rel: str, old: str, new: str, note: str, count: int = 1, replace_all: bool = False) -> None:
        text = self.read(rel)
        # already applied?  (`new` often CONTAINS `old`, so check `new` first; for replace_all the
        # replacement text may legitimately exist elsewhere, so there only "no old left" counts)
        applied = (old not in text) if replace_all else (new in text)
        if applied and new in text:
            self.log.append(("SKIP", rel, note + " (already applied)"))
            return
        n = text.count(old)
        if n == 0:
            raise PatchError(f"[{note}] anchor not found in {rel}:\n---\n{old[:300]}\n---")
        if n != count and not replace_all:
            raise PatchError(f"[{note}] anchor occurs {n}x (expected {count}) in {rel}")
        self.set(rel, text.replace(old, new), note)

    def write_file(self, rel: str, content: str, note: str) -> None:
        self.set(rel, content.replace("\r\n", "\n"), note)

    def append_once(self, rel: str, marker: str, block: str, note: str) -> None:
        text = self.read(rel)
        if marker in text:
            self.log.append(("SKIP", rel, note + " (already applied)"))
            return
        self.set(rel, text.rstrip("\n") + "\n\n" + block.strip("\n") + "\n", note)

    # -- flush --------------------------------------------------------------
    def commit(self, backup_dir: Path) -> None:
        for rel, text in self.staged.items():
            if text == self.original.get(rel):
                continue
            p = self.path(rel)
            if p.exists():
                dest = backup_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dest)
            p.parent.mkdir(parents=True, exist_ok=True)
            out = text.replace("\n", "\r\n") if self.crlf.get(rel) else text
            p.write_bytes(out.encode("utf-8"))


# ---------------------------------------------------------------------------
# custom operations
# ---------------------------------------------------------------------------
def op_replace_customers_page(ws: Workspace) -> None:
    rel = "frontend/src/pages/BankingEntities.tsx"
    text = ws.read(rel)
    sep = "// " + "=" * 76 + "\n"
    start_marker = sep + "// PAGE 2: CUSTOMERS (CIF)\n"
    end_marker = sep + "// PAGE 3: CARDS & PROFILES\n"
    if "FIX_ALL_V2_CUSTOMERS_PAGE" in text:
        ws.log.append(("SKIP", rel, "CustomersPage rebuild (already applied)"))
        return
    a, b = text.find(start_marker), text.find(end_marker)
    if a < 0 or b < 0 or b < a:
        raise PatchError("CustomersPage boundaries not found in BankingEntities.tsx")
    new_segment = "// FIX_ALL_V2_CUSTOMERS_PAGE\n" + CUSTOMERS_PAGE_SEGMENT.replace("\r\n", "\n").lstrip("\n")
    text = text[:a] + new_segment + text[b:]
    imp_old = "import { apiFetch } from '../api';"
    if "useNavigate" not in text.split("export const CustomersPage")[0]:
        if imp_old not in text:
            raise PatchError("apiFetch import not found in BankingEntities.tsx")
        text = text.replace(imp_old, "import { useNavigate } from 'react-router-dom';\n" + imp_old, 1)
    ws.set(rel, text, "CustomersPage rebuilt (fixes undeclared editAcct build error)")


def op_card_crypto_db_keys(ws: Workspace) -> None:
    rel = "backend/app/card_crypto_service.py"
    text = ws.read(rel)
    if "def _clear_key(" in text:
        ws.log.append(("SKIP", rel, "DB-first key resolution (already applied)"))
    else:
        text = text.replace("SoftHsmCryptoCore.INTERNAL_CLEAR_KEYS.get(", "_clear_key(")
        helper = '''

def _clear_key(key_id: str, default: str) -> str:
    """Resolve a clear key the same way HSMAdapter._resolve_key does:
    DB (key-ceremony) value first, then the built-in lab key, then the lab default."""
    try:
        from app.database import SessionLocal
        from app.models import HsmKeyReference

        db = SessionLocal()
        try:
            ref = db.query(HsmKeyReference).filter(HsmKeyReference.key_identifier == key_id).first()
            if ref and ref.clear_key_hex:
                return ref.clear_key_hex
        finally:
            db.close()
    except Exception:
        pass
    return SoftHsmCryptoCore.INTERNAL_CLEAR_KEYS.get(key_id, default)
'''
        anchor = "from app.hsm_adapter import SoftHsmCryptoCore\n"
        if anchor not in text:
            raise PatchError("card_crypto_service import anchor not found")
        text = text.replace(anchor, anchor + helper, 1)
        ws.set(rel, text, "card_crypto_service resolves keys DB-first")
    ws.replace(
        rel,
        '''    digits_found = [ch for ch in cipher if ch.isdigit()]
    decimalized_alphas = [str(int(ch, 16) - 10) for ch in cipher if ch in "ABCDEF"]
    combined = "".join(digits_found + decimalized_alphas)
    pvv = combined[:4]''',
        '''    combined = SoftHsmCryptoCore.decimalize_pvv(cipher)  # single source of truth
    pvv = combined[:4]''',
        "card_crypto_service uses shared PVV decimalisation",
    )


PATCH_COMMENT_RE = re.compile(r"^[ \t]*# \[PATCH [^\]\n]*\][ \t]*\n", re.M)


def op_strip_patch_comments(ws: Workspace) -> None:
    for rel in ("backend/app/api_routes.py", "backend/app/schemas.py"):
        text = ws.read(rel)
        new = PATCH_COMMENT_RE.sub("", text)
        if new == text:
            ws.log.append(("SKIP", rel, "stray # [PATCH ...] comments (none left)"))
        else:
            ws.set(rel, new, f"removed {len(PATCH_COMMENT_RE.findall(text))} stray # [PATCH ...] comments")


# ---------------------------------------------------------------------------
def find_base(arg: str) -> Path:
    if arg:
        return Path(arg).resolve()
    here = Path(__file__).resolve().parent
    for cand in (here.parent, here, Path.cwd(), Path(r"E:\HOST_VSCODE\host-simulator")):
        if (cand / "backend").is_dir() and (cand / "frontend").is_dir():
            return cand.resolve()
    raise SystemExit("Could not locate the project root. Pass --base <path>.")


def build(ws: Workspace) -> None:
    for rel, content in NEW_FILES.items():
        ws.write_file(rel, content, "write file")
    for spec in REPLACEMENTS:
        rel, old, new, note = spec[:4]
        kw = spec[4] if len(spec) > 4 else {}
        ws.replace(rel, old, new, note, **kw)
    op_replace_customers_page(ws)
    op_card_crypto_db_keys(ws)
    op_strip_patch_comments(ws)  # keep last: other anchors never contain PATCH markers
    ws.append_once("PROGRESS.md", "<!-- PROGRESS:fix_all_v2 -->", PROGRESS_BLOCK, "PROGRESS.md entry")
    ws.append_once("docs/CONTRACTS.md", "<!-- CONTRACT:fix_all_v2 -->", CONTRACT_BLOCK, "CONTRACTS.md entry")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="", help="project root (default: auto-detect)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--run-tests", action="store_true", help="run backend pytest after applying")
    args = ap.parse_args()

    base = find_base(args.base)
    print(f"Project root : {base}")
    ws = Workspace(base)
    try:
        build(ws)
    except PatchError as e:
        print(f"\nABORTED — nothing was written.\n{e}")
        return 2

    # syntax-check every staged python file BEFORE touching disk
    with tempfile.TemporaryDirectory() as td:
        for rel, text in ws.staged.items():
            if rel.endswith(".py") and text != ws.original.get(rel):
                tmp = Path(td) / "chk.py"
                tmp.write_text(text, encoding="utf-8")
                try:
                    py_compile.compile(str(tmp), doraise=True)
                except py_compile.PyCompileError as e:
                    print(f"\nABORTED — staged {rel} does not compile:\n{e}")
                    return 3

    for status, rel, note in ws.log:
        print(f"  [{status}] {rel}  —  {note}")
    changed = [r for r, t in ws.staged.items() if t != ws.original.get(r)]
    print(f"\n{len(changed)} file(s) {'would change' if args.dry_run else 'to write'}.")
    if args.dry_run:
        return 0

    backup = base / "_backups" / f"{STEP_ID}_{datetime.now():%Y%m%d_%H%M%S}"
    ws.commit(backup)
    print(f"Backups      : {backup}")
    print("Done.")

    if args.run_tests:
        print("\nRunning backend tests ...")
        rc = subprocess.call([sys.executable, "-m", "pytest", "-q"], cwd=str(base / "backend"))
        return rc
    print("\nNext:  cd backend && python -m pytest -q      |      cd frontend && npm run build")
    return 0


if __name__ == "__main__":
    sys.exit(main())
