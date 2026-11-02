#!/usr/bin/env python3
"""
INSTALLER: tools/install_step03_01.py
STEP 3 — Full CRUD and Audit Trail — Script 1 of 3
Adds:
  1. AuditTrail ORM model in backend/app/models.py
  2. Pydantic v2 schemas for CustomerUpdate, AccountUpdate, CardUpdate, AuditTrailOut in backend/app/schemas.py
  3. backend/app/audit_service.py for capturing before/after state diffs
  4. PUT and DELETE endpoints with 409 Conflict protection for Customers, Accounts, Cards
  5. GET /api/audit-trail endpoint in backend/app/api_routes.py
  6. Automated Pytest test suite in backend/tests/test_step03_crud_and_audit.py
"""

from pathlib import Path
import sys

BASE_DIR = Path(r"E:\HOST_VSCODE\host-simulator").resolve()
sys.path.insert(0, str(BASE_DIR))

from tools.patcher import PatcherSession, parse_installer_args

AUDIT_SERVICE_CODE = '''"""
audit_service.py — Entity Snapshot and Audit Trail Logger
Captures before/after JSON states and diff summaries for regulatory audit compliance.
"""

from typing import Any, Dict, Optional
from sqlalchemy.orm import Session
from app.models import AuditTrail


def serialize_entity(entity: Any) -> Dict[str, Any]:
    """Serialize a SQLAlchemy declarative model into a clean JSON-serializable dict."""
    if entity is None:
        return {}
    out: Dict[str, Any] = {}
    for col in entity.__table__.columns:
        val = getattr(entity, col.name, None)
        if hasattr(val, "isoformat"):
            out[col.name] = val.isoformat()
        elif hasattr(val, "__float__"):
            out[col.name] = float(val)
        else:
            out[col.name] = val
    return out


def record_audit(
    db: Session,
    entity_type: str,
    entity_id: str,
    action: str,
    performed_by: str = "admin",
    before_state: Optional[Dict[str, Any]] = None,
    after_state: Optional[Dict[str, Any]] = None,
    change_summary: Optional[str] = None,
) -> AuditTrail:
    """Record an immutable audit trail entry."""
    entry = AuditTrail(
        entity_type=entity_type.upper(),
        entity_id=str(entity_id),
        action=action.upper(),
        performed_by=performed_by,
        before_state=before_state,
        after_state=after_state,
        change_summary=change_summary,
    )
    db.add(entry)
    db.flush()
    return entry
'''

TEST_STEP03_CODE = '''"""
test_step03_crud_and_audit.py — Tests for Step 3 CRUD & Audit Trail
"""

import os
import pytest
from decimal import Decimal
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Account, AuditTrail, Card, Customer, Institution
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


def test_customer_update_creates_audit_entry(client, db_session):
    cust = db_session.query(Customer).first()
    assert cust is not None

    update_payload = {
        "first_name": "Tariq Updated",
        "email": "tariq.new@example.test",
        "risk_category": "VIP"
    }
    res = client.put(f"/api/customers/{cust.id}", json=update_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["first_name"] == "Tariq Updated"
    assert data["risk_category"] == "VIP"

    audit = (
        db_session.query(AuditTrail)
        .filter(AuditTrail.entity_type == "CUSTOMER", AuditTrail.entity_id == cust.id)
        .order_by(AuditTrail.created_at.desc())
        .first()
    )
    assert audit is not None
    assert audit.action == "UPDATE"
    assert audit.before_state["first_name"] == "Tariq"
    assert audit.after_state["first_name"] == "Tariq Updated"


def test_delete_customer_with_linked_accounts_fails_409(client, db_session):
    cust = db_session.query(Customer).filter(Customer.accounts.any()).first()
    assert cust is not None

    # Normal delete without force must return 409 Conflict
    res = client.delete(f"/api/customers/{cust.id}")
    assert res.status_code == 409
    assert "active accounts" in res.json()["detail"].lower()


def test_card_update_and_audit(client, db_session):
    card = db_session.query(Card).first()
    assert card is not None

    payload = {
        "cardholder_name": "NEW CARDHOLDER NAME",
        "expiry_month": 11,
        "expiry_year": 2029,
        "card_status": "BLOCKED"
    }
    res = client.put(f"/api/cards/{card.id}", json=payload)
    assert res.status_code == 200
    assert res.json()["cardholder_name"] == "NEW CARDHOLDER NAME"
    assert res.json()["card_status"] == "BLOCKED"

    audit = (
        db_session.query(AuditTrail)
        .filter(AuditTrail.entity_type == "CARD", AuditTrail.entity_id == card.id)
        .order_by(AuditTrail.created_at.desc())
        .first()
    )
    assert audit is not None
    assert audit.action == "UPDATE"
    assert audit.after_state["card_status"] == "BLOCKED"


def test_query_audit_trail_endpoint(client, db_session):
    res = client.get("/api/audit-trail")
    assert res.status_code == 200
    assert isinstance(res.json(), list)
'''


def main() -> int:
    args = parse_installer_args("Step 03_01: Backend AuditTrail Model, Service, and Entity CRUD Endpoints")
    session = PatcherSession(
        step_id="step03_01",
        title="Add AuditTrail Model, Audit Service, and PUT/DELETE Endpoints for Customers, Accounts, Cards",
        dry_run=args.dry_run,
    )

    # 1. Write backend/app/audit_service.py
    session.write_file("backend/app/audit_service.py", AUDIT_SERVICE_CODE)

    # 2. Patch backend/app/models.py to add AuditTrail ORM model
    session.patch_file(
        "backend/app/models.py",
        [
            {
                "marker": "step03_01:audit_trail_model",
                "action": "append",
                "text": (
                    "\n# ==============================================================================\n"
                    "# G. AUDIT TRAIL LOGGING (STEP 3)\n"
                    "# ==============================================================================\n\n"
                    "class AuditTrail(Base):\n"
                    '    __tablename__ = "audit_trail"\n\n'
                    "    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)\n"
                    "    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # CUSTOMER, ACCOUNT, CARD, etc.\n"
                    "    entity_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)\n"
                    "    action: Mapped[str] = mapped_column(String(20), nullable=False)  # CREATE, UPDATE, DELETE, STATUS_CHANGE\n"
                    '    performed_by: Mapped[str] = mapped_column(String(100), nullable=False, default="admin")\n'
                    "    before_state: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)\n"
                    "    after_state: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)\n"
                    "    change_summary: Mapped[Optional[str]] = mapped_column(Text)\n"
                    "    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)\n"
                ),
            }
        ],
    )

    # 3. Patch backend/app/schemas.py to add update schemas and AuditTrailOut
    session.patch_file(
        "backend/app/schemas.py",
        [
            {
                "marker": "step03_01:schemas_update_and_audit",
                "action": "append",
                "text": (
                    "\n# ==============================================================================\n"
                    "# STEP 3 SCHEMAS: FULL CRUD UPDATES & AUDIT TRAIL\n"
                    "# ==============================================================================\n\n"
                    "class CustomerUpdate(BaseModel):\n"
                    "    first_name: Optional[str] = None\n"
                    "    last_name: Optional[str] = None\n"
                    "    date_of_birth: Optional[date] = None\n"
                    "    email: Optional[str] = None\n"
                    "    mobile_number: Optional[str] = None\n"
                    "    address: Optional[str] = None\n"
                    "    customer_status: Optional[str] = None\n"
                    "    risk_category: Optional[str] = None\n"
                    "    institution_id: Optional[str] = None\n\n\n"
                    "class AccountUpdate(BaseModel):\n"
                    "    account_type: Optional[str] = None\n"
                    "    overdraft_limit: Optional[Decimal] = None\n"
                    "    account_status: Optional[str] = None\n"
                    "    branch_code: Optional[str] = None\n"
                    "    institution_id: Optional[str] = None\n\n\n"
                    "class CardUpdate(BaseModel):\n"
                    "    cardholder_name: Optional[str] = None\n"
                    "    expiry_month: Optional[int] = Field(None, ge=1, le=12)\n"
                    "    expiry_year: Optional[int] = Field(None, ge=2024, le=2040)\n"
                    "    card_status: Optional[str] = None\n"
                    "    card_product: Optional[str] = None\n"
                    "    linked_account_id: Optional[str] = None\n"
                    "    card_profile_id: Optional[str] = None\n"
                    "    institution_id: Optional[str] = None\n\n\n"
                    "class AuditTrailOut(BaseModel):\n"
                    "    id: str\n"
                    "    entity_type: str\n"
                    "    entity_id: str\n"
                    "    action: str\n"
                    "    performed_by: str\n"
                    "    before_state: Optional[Dict[str, Any]] = None\n"
                    "    after_state: Optional[Dict[str, Any]] = None\n"
                    "    change_summary: Optional[str] = None\n"
                    "    created_at: datetime\n"
                    "    model_config = ConfigDict(from_attributes=True)\n"
                ),
            }
        ],
    )

    # 4. Patch backend/app/api_routes.py to add PUT & DELETE for Customer, Account, Card, and GET /api/audit-trail
    session.patch_file(
        "backend/app/api_routes.py",
        [
            # Add audit imports
            {
                "marker": "step03_01:api_routes_audit_imports",
                "action": "insert_after",
                "anchor": "from app.logging_service import monitor_hub, record_system_log",
                "text": "from app.audit_service import record_audit, serialize_entity",
            },
            # Add model & schema imports
            {
                "marker": "step03_01:api_routes_audit_model_import",
                "action": "insert_after",
                "anchor": "    AccountLimit,",
                "text": "    AuditTrail,",
            },
            {
                "marker": "step03_01:api_routes_audit_schema_import",
                "action": "insert_after",
                "anchor": "    AccountOut,",
                "text": (
                    "    AccountUpdate,\n"
                    "    AuditTrailOut,\n"
                    "    CardUpdate,\n"
                    "    CustomerUpdate,"
                ),
            },
            # Add PUT and DELETE endpoints for Customers
            {
                "marker": "step03_01:api_customer_put_delete",
                "action": "insert_after",
                "anchor": (
                    "    cust.customer_status = status.upper()\n"
                    "    db.commit()\n"
                    '    return {"id": cust.id, "customer_status": cust.customer_status}'
                ),
                "text": (
                    "\n\n@router.put('/customers/{customer_id}', response_model=CustomerOut)\n"
                    "def update_customer(customer_id: str, payload: CustomerUpdate, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):\n"
                    "    cust = db.query(Customer).filter(Customer.id == customer_id).first()\n"
                    "    if not cust:\n"
                    "        raise HTTPException(status_code=404, detail='Customer not found')\n"
                    "    before = serialize_entity(cust)\n"
                    "    for k, v in payload.model_dump(exclude_unset=True).items():\n"
                    "        setattr(cust, k, v)\n"
                    "    after = serialize_entity(cust)\n"
                    "    record_audit(db, 'CUSTOMER', cust.id, 'UPDATE', performed_by=current_user, before_state=before, after_state=after,\n"
                    "                 change_summary=f'Updated customer {cust.customer_number}')\n"
                    "    db.commit()\n"
                    "    db.refresh(cust)\n"
                    "    return cust\n\n\n"
                    "@router.delete('/customers/{customer_id}')\n"
                    "def delete_customer(customer_id: str, force: bool = Query(False), db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):\n"
                    "    cust = db.query(Customer).filter(Customer.id == customer_id).first()\n"
                    "    if not cust:\n"
                    "        raise HTTPException(status_code=404, detail='Customer not found')\n"
                    "    if not force and (cust.accounts or cust.cards):\n"
                    "        raise HTTPException(status_code=409, detail=f'Cannot delete customer {cust.customer_number} with active accounts or cards. Remove them first or use ?force=true')\n"
                    "    before = serialize_entity(cust)\n"
                    "    db.delete(cust)\n"
                    "    record_audit(db, 'CUSTOMER', customer_id, 'DELETE', performed_by=current_user, before_state=before,\n"
                    "                 change_summary=f'Deleted customer {cust.customer_number} (Force: {force})')\n"
                    "    db.commit()\n"
                    "    return {'status': 'deleted', 'customer_id': customer_id}"
                ),
            },
            # Add PUT and DELETE endpoints for Accounts
            {
                "marker": "step03_01:api_account_put_delete",
                "action": "insert_after",
                "anchor": (
                    "    for k, v in payload.model_dump().items():\n"
                    "        setattr(lim, k, v)\n"
                    "    db.commit()\n"
                    '    return {"status": "updated", "account_id": account_id}'
                ),
                "text": (
                    "\n\n@router.put('/accounts/{account_id}', response_model=AccountOut)\n"
                    "def update_account(account_id: str, payload: AccountUpdate, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):\n"
                    "    acct = db.query(Account).filter(Account.id == account_id).first()\n"
                    "    if not acct:\n"
                    "        raise HTTPException(status_code=404, detail='Account not found')\n"
                    "    before = serialize_entity(acct)\n"
                    "    for k, v in payload.model_dump(exclude_unset=True).items():\n"
                    "        setattr(acct, k, v)\n"
                    "    after = serialize_entity(acct)\n"
                    "    record_audit(db, 'ACCOUNT', acct.id, 'UPDATE', performed_by=current_user, before_state=before, after_state=after,\n"
                    "                 change_summary=f'Updated account {acct.account_number}')\n"
                    "    db.commit()\n"
                    "    db.refresh(acct)\n"
                    "    return acct\n\n\n"
                    "@router.delete('/accounts/{account_id}')\n"
                    "def delete_account(account_id: str, force: bool = Query(False), db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):\n"
                    "    acct = db.query(Account).filter(Account.id == account_id).first()\n"
                    "    if not acct:\n"
                    "        raise HTTPException(status_code=404, detail='Account not found')\n"
                    "    if not force:\n"
                    "        if acct.available_balance != 0 or acct.ledger_balance != 0:\n"
                    "            raise HTTPException(status_code=409, detail=f'Cannot delete account {acct.account_number} with non-zero balance ({acct.available_balance} {acct.currency}). Zero the balance or use ?force=true')\n"
                    "        if acct.ledger_entries:\n"
                    "            raise HTTPException(status_code=409, detail=f'Cannot delete account {acct.account_number} with existing ledger transactions. Close status instead or use ?force=true')\n"
                    "    before = serialize_entity(acct)\n"
                    "    db.delete(acct)\n"
                    "    record_audit(db, 'ACCOUNT', account_id, 'DELETE', performed_by=current_user, before_state=before,\n"
                    "                 change_summary=f'Deleted account {acct.account_number} (Force: {force})')\n"
                    "    db.commit()\n"
                    "    return {'status': 'deleted', 'account_id': account_id}"
                ),
            },
            # Add PUT and DELETE endpoints for Cards
            {
                "marker": "step03_01:api_card_put_delete",
                "action": "insert_after",
                "anchor": (
                    "    for k, v in payload.model_dump().items():\n"
                    "        setattr(lim, k, v)\n"
                    "    db.commit()\n"
                    '    return {"status": "updated", "card_id": card_id}'
                ),
                "text": (
                    "\n\n@router.put('/cards/{card_id}', response_model=CardOut)\n"
                    "def update_card(card_id: str, payload: CardUpdate, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):\n"
                    "    card = db.query(Card).filter(Card.id == card_id).first()\n"
                    "    if not card:\n"
                    "        raise HTTPException(status_code=404, detail='Card not found')\n"
                    "    before = serialize_entity(card)\n"
                    "    for k, v in payload.model_dump(exclude_unset=True).items():\n"
                    "        setattr(card, k, v)\n"
                    "    after = serialize_entity(card)\n"
                    "    record_audit(db, 'CARD', card.id, 'UPDATE', performed_by=current_user, before_state=before, after_state=after,\n"
                    "                 change_summary=f'Updated card {card.masked_pan}')\n"
                    "    db.commit()\n"
                    "    db.refresh(card)\n"
                    "    return card\n\n\n"
                    "@router.delete('/cards/{card_id}')\n"
                    "def delete_card(card_id: str, force: bool = Query(False), db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):\n"
                    "    card = db.query(Card).filter(Card.id == card_id).first()\n"
                    "    if not card:\n"
                    "        raise HTTPException(status_code=404, detail='Card not found')\n"
                    "    has_tx = db.query(Transaction).filter(Transaction.card_id == card.id).first() is not None\n"
                    "    if has_tx and not force:\n"
                    "        raise HTTPException(status_code=409, detail=f'Cannot delete card {card.masked_pan} with historical transactions in journal. Block status instead or use ?force=true')\n"
                    "    before = serialize_entity(card)\n"
                    "    db.delete(card)\n"
                    "    record_audit(db, 'CARD', card_id, 'DELETE', performed_by=current_user, before_state=before,\n"
                    "                 change_summary=f'Deleted card {card.masked_pan} (Force: {force})')\n"
                    "    db.commit()\n"
                    "    return {'status': 'deleted', 'card_id': card_id}"
                ),
            },
            # Add GET /api/audit-trail endpoint
            {
                "marker": "step03_01:api_audit_trail_list",
                "action": "insert_after",
                "anchor": (
                    "    recent_logs = (\n"
                    "        db.query(SystemLog)\n"
                    "        .order_by(SystemLog.created_at.desc())\n"
                    "        .limit(8)\n"
                    "        .all()\n"
                    "    )"
                ),
                "text": "",  # placeholder
            },
            {
                "marker": "step03_01:api_audit_trail_endpoint",
                "action": "append",
                "text": (
                    "\n\n@router.get('/audit-trail', response_model=List[AuditTrailOut])\n"
                    "def list_audit_trail(\n"
                    "    entity_type: Optional[str] = Query(None),\n"
                    "    entity_id: Optional[str] = Query(None),\n"
                    "    limit: int = Query(100, ge=1, le=500),\n"
                    "    db: Session = Depends(get_db),\n"
                    "    _: str = Depends(get_current_user),\n"
                    "):\n"
                    "    q = db.query(AuditTrail)\n"
                    "    if entity_type:\n"
                    "        q = q.filter(AuditTrail.entity_type == entity_type.upper())\n"
                    "    if entity_id:\n"
                    "        q = q.filter(AuditTrail.entity_id == entity_id)\n"
                    "    return q.order_by(AuditTrail.created_at.desc()).limit(limit).all()\n"
                ),
            },
        ],
    )

    # 5. Write automated test suite backend/tests/test_step03_crud_and_audit.py
    session.write_file("backend/tests/test_step03_crud_and_audit.py", TEST_STEP03_CODE)

    session.record_progress(
        completed=[
            "Created `AuditTrail` ORM model in `backend/app/models.py` for immutable entity change logging.",
            "Created `backend/app/audit_service.py` to capture before/after JSON states and diff summaries.",
            "Added Pydantic v2 schemas (`CustomerUpdate`, `AccountUpdate`, `CardUpdate`, `AuditTrailOut`) in `backend/app/schemas.py`.",
            "Added PUT and DELETE endpoints with 409 Conflict protection for Customers, Accounts, and Cards in `backend/app/api_routes.py`.",
            "Added `GET /api/audit-trail` endpoint.",
            "Added automated Pytest test suite `backend/tests/test_step03_crud_and_audit.py`.",
        ],
        remaining=[
            "Step 3 Script 2 of 3 (`tools/install_step03_02.py`): Implement PUT/DELETE and audit logging for Host Parameters, Transaction Codes, Card Profiles, Limits, and HSM Key References.",
            "Step 3 Script 3 of 3 (`tools/install_step03_03.py`): Implement frontend Edit Modals, Delete Confirmation Dialogs with 409 error banners, and the Audit Trail Viewer page.",
        ],
        modified_files=[
            "backend/app/models.py",
            "backend/app/schemas.py",
            "backend/app/audit_service.py",
            "backend/app/api_routes.py",
            "backend/tests/test_step03_crud_and_audit.py",
        ],
    )

    session.record_contracts(
        section_title="Step 3.1 — Full CRUD & Audit Trail (Core Entities)",
        contract_items=[
            "**Table `audit_trail`**: `id`, `entity_type`, `entity_id`, `action` (`CREATE`/`UPDATE`/`DELETE`), `performed_by`, `before_state` (JSON), `after_state` (JSON), `change_summary`, `created_at`.",
            "**PUT /api/customers/{id}**: Updates customer profile with audit logging.",
            "**DELETE /api/customers/{id}**: Deletes customer (returns 409 Conflict if linked accounts or cards exist unless `?force=true`).",
            "**PUT /api/accounts/{id}**: Updates account metadata/overdraft.",
            "**DELETE /api/accounts/{id}**: Deletes account (returns 409 Conflict if balance > 0 or ledger entries exist unless `?force=true`).",
            "**PUT /api/cards/{id}**: Updates card details.",
            "**DELETE /api/cards/{id}**: Deletes card (returns 409 Conflict if historical journal entries exist unless `?force=true`).",
            "**GET /api/audit-trail**: Returns filtered audit trail records.",
        ],
    )

    return session.finish()


if __name__ == "__main__":
    sys.exit(main())