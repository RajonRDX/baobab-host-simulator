#!/usr/bin/env python3
"""
INSTALLER: tools/install_step03_02.py
STEP 3 — Full CRUD and Audit Trail — Script 2 of 3
Adds:
  1. CardProfile Pydantic schemas (Create, Update, Out) in backend/app/schemas.py
  2. HsmKeyReferenceUpdate and ResponseCodeUpdate schemas
  3. PUT and DELETE endpoints with audit logging for Card Profiles, Transaction Codes,
     Response Codes, Host Parameters, and HSM Keys in backend/app/api_routes.py
  4. Automated Pytest test suite in backend/tests/test_step03_config_crud.py
"""

from pathlib import Path
import sys

BASE_DIR = Path(r"E:\HOST_VSCODE\host-simulator").resolve()
sys.path.insert(0, str(BASE_DIR))

from tools.patcher import PatcherSession, parse_installer_args

TEST_CONFIG_CRUD_CODE = '''"""
test_step03_config_crud.py — Tests for Step 3 Configuration & Key CRUD with Audit Trail
"""

import os
import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import AuditTrail, Card, CardProfile, HostParameter, HsmKeyReference, TransactionCode
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


def test_card_profile_crud_and_conflict_check(client, db_session):
    # 1. Create a custom profile
    payload = {
        "profile_code": "PROF_CUSTOM_01",
        "profile_name": "Custom Student Debit Profile",
        "card_product": "VISA_STUDENT",
        "domestic_enabled": True,
        "international_enabled": False,
        "ecommerce_enabled": False,
        "contactless_enabled": True,
        "cash_enabled": True
    }
    create_res = client.post("/api/card-profiles", json=payload)
    assert create_res.status_code == 200
    prof_id = create_res.json()["id"]

    # 2. Update the profile
    update_res = client.put(f"/api/card-profiles/{prof_id}", json={"ecommerce_enabled": True})
    assert update_res.status_code == 200
    assert update_res.json()["ecommerce_enabled"] is True

    # 3. Check audit trail
    audit = db_session.query(AuditTrail).filter(
        AuditTrail.entity_type == "CARD_PROFILE",
        AuditTrail.entity_id == prof_id,
        AuditTrail.action == "UPDATE"
    ).first()
    assert audit is not None
    assert audit.after_state["ecommerce_enabled"] is True

    # 4. Deleting a profile referenced by cards must return 409
    std_prof = db_session.query(CardProfile).filter(CardProfile.profile_code == "PROF_DOM_STD").first()
    del_conflict = client.delete(f"/api/card-profiles/{std_prof.id}")
    assert del_conflict.status_code == 409

    # 5. Deleting unreferenced custom profile succeeds
    del_ok = client.delete(f"/api/card-profiles/{prof_id}")
    assert del_ok.status_code == 200


def test_transaction_code_delete(client, db_session):
    tc = TransactionCode(
        transaction_code="99",
        transaction_name="Test Temp Code",
        processing_code="0990000",
        default_mti="0200"
    )
    db_session.add(tc)
    db_session.commit()

    del_res = client.delete(f"/api/transaction-codes/{tc.id}")
    assert del_res.status_code == 200

    audit = db_session.query(AuditTrail).filter(
        AuditTrail.entity_type == "TRANSACTION_CODE",
        AuditTrail.entity_id == tc.id,
        AuditTrail.action == "DELETE"
    ).first()
    assert audit is not None


def test_hsm_key_update_and_audit(client, db_session):
    key = db_session.query(HsmKeyReference).first()
    assert key is not None

    upd_res = client.put(f"/api/hsm/keys/{key.id}", json={"key_name": "Updated Key Name", "key_status": "INACTIVE"})
    assert upd_res.status_code == 200
    assert upd_res.json()["key_name"] == "Updated Key Name"
    assert upd_res.json()["key_status"] == "INACTIVE"

    audit = db_session.query(AuditTrail).filter(
        AuditTrail.entity_type == "HSM_KEY",
        AuditTrail.entity_id == key.id,
        AuditTrail.action == "UPDATE"
    ).first()
    assert audit is not None
    assert audit.after_state["key_name"] == "Updated Key Name"
'''


def main() -> int:
    args = parse_installer_args("Step 03_02: CRUD and Audit Trail for Config & Cryptographic Resources")
    session = PatcherSession(
        step_id="step03_02",
        title="Add Full CRUD and Audit Trail for Card Profiles, Config Parameters, and HSM Keys",
        dry_run=args.dry_run,
    )

    # 1. Patch backend/app/schemas.py to add CardProfile schemas, HsmKeyReferenceUpdate, and ResponseCodeUpdate
    session.patch_file(
        "backend/app/schemas.py",
        [
            {
                "marker": "step03_02:schemas_card_profile_and_key_updates",
                "action": "append",
                "text": (
                    "\n# ==============================================================================\n"
                    "# CARD PROFILE, KEY & RESPONSE CODE UPDATE SCHEMAS (STEP 3.2)\n"
                    "# ==============================================================================\n\n"
                    "class CardProfileCreate(BaseModel):\n"
                    "    profile_code: str\n"
                    "    profile_name: str\n"
                    '    card_product: str = "VISA_DEBIT_CLASSIC"\n'
                    "    transaction_permissions: Dict[str, Any] = Field(default_factory=dict)\n"
                    "    domestic_enabled: bool = True\n"
                    "    international_enabled: bool = False\n"
                    "    ecommerce_enabled: bool = True\n"
                    "    contactless_enabled: bool = True\n"
                    "    cash_enabled: bool = True\n"
                    '    status: str = "ACTIVE"\n\n\n'
                    "class CardProfileUpdate(BaseModel):\n"
                    "    profile_name: Optional[str] = None\n"
                    "    card_product: Optional[str] = None\n"
                    "    transaction_permissions: Optional[Dict[str, Any]] = None\n"
                    "    domestic_enabled: Optional[bool] = None\n"
                    "    international_enabled: Optional[bool] = None\n"
                    "    ecommerce_enabled: Optional[bool] = None\n"
                    "    contactless_enabled: Optional[bool] = None\n"
                    "    cash_enabled: Optional[bool] = None\n"
                    "    status: Optional[str] = None\n\n\n"
                    "class CardProfileOut(CardProfileCreate):\n"
                    "    id: str\n"
                    "    model_config = ConfigDict(from_attributes=True)\n\n\n"
                    "class HsmKeyReferenceUpdate(BaseModel):\n"
                    "    key_name: Optional[str] = None\n"
                    "    key_usage: Optional[str] = None\n"
                    "    kvc: Optional[str] = None\n"
                    "    key_status: Optional[str] = None\n"
                    "    institution_id: Optional[str] = None\n"
                    "    processing_system_id: Optional[str] = None\n\n\n"
                    "class ResponseCodeUpdate(BaseModel):\n"
                    "    response_description: Optional[str] = None\n"
                    "    response_category: Optional[str] = None\n"
                    "    approved_flag: Optional[bool] = None\n"
                    "    retry_allowed: Optional[bool] = None\n"
                    "    active: Optional[bool] = None\n"
                ),
            }
        ],
    )

    # 2. Patch backend/app/api_routes.py to add card profile CRUD, key updates, and parameter/code deletions
    session.patch_file(
        "backend/app/api_routes.py",
        [
            # Add schema imports
            {
                "marker": "step03_02:api_routes_more_schemas",
                "action": "insert_after",
                "anchor": "    CardUpdate,",
                "text": (
                    "    CardProfileCreate,\n"
                    "    CardProfileOut,\n"
                    "    CardProfileUpdate,\n"
                    "    HsmKeyReferenceUpdate,"
                ),
            },
            # Add Card Profile CRUD endpoints
            {
                "marker": "step03_02:card_profile_endpoints",
                "action": "insert_before",
                "anchor": "# ==============================================================================\n# 3. TRANSACTION CODES, HOST CONFIGURATION & RESPONSE CODES",
                "text": (
                    "# --- CARD PROFILES CRUD ---\n\n"
                    "@router.get('/card-profiles', response_model=List[CardProfileOut])\n"
                    "def list_card_profiles(db: Session = Depends(get_db), _: str = Depends(get_current_user)):\n"
                    "    return db.query(CardProfile).order_by(CardProfile.profile_code.asc()).all()\n\n\n"
                    "@router.post('/card-profiles', response_model=CardProfileOut)\n"
                    "def create_card_profile(payload: CardProfileCreate, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):\n"
                    "    p_code = payload.profile_code.upper().strip()\n"
                    "    existing = db.query(CardProfile).filter(CardProfile.profile_code == p_code).first()\n"
                    "    if existing:\n"
                    "        raise HTTPException(status_code=400, detail=f'Card profile {p_code} already exists')\n"
                    "    prof = CardProfile(**payload.model_dump())\n"
                    "    prof.profile_code = p_code\n"
                    "    db.add(prof)\n"
                    "    db.flush()\n"
                    "    record_audit(db, 'CARD_PROFILE', prof.id, 'CREATE', performed_by=current_user, after_state=serialize_entity(prof),\n"
                    "                 change_summary=f'Created card profile {prof.profile_code}')\n"
                    "    db.commit()\n"
                    "    db.refresh(prof)\n"
                    "    return prof\n\n\n"
                    "@router.put('/card-profiles/{profile_id}', response_model=CardProfileOut)\n"
                    "def update_card_profile(profile_id: str, payload: CardProfileUpdate, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):\n"
                    "    prof = db.query(CardProfile).filter(CardProfile.id == profile_id).first()\n"
                    "    if not prof:\n"
                    "        raise HTTPException(status_code=404, detail='Card profile not found')\n"
                    "    before = serialize_entity(prof)\n"
                    "    for k, v in payload.model_dump(exclude_unset=True).items():\n"
                    "        setattr(prof, k, v)\n"
                    "    after = serialize_entity(prof)\n"
                    "    record_audit(db, 'CARD_PROFILE', prof.id, 'UPDATE', performed_by=current_user, before_state=before, after_state=after,\n"
                    "                 change_summary=f'Updated card profile {prof.profile_code}')\n"
                    "    db.commit()\n"
                    "    db.refresh(prof)\n"
                    "    return prof\n\n\n"
                    "@router.delete('/card-profiles/{profile_id}')\n"
                    "def delete_card_profile(profile_id: str, force: bool = Query(False), db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):\n"
                    "    prof = db.query(CardProfile).filter(CardProfile.id == profile_id).first()\n"
                    "    if not prof:\n"
                    "        raise HTTPException(status_code=404, detail='Card profile not found')\n"
                    "    has_cards = db.query(Card).filter(Card.card_profile_id == prof.id).first() is not None\n"
                    "    if has_cards and not force:\n"
                    "        raise HTTPException(status_code=409, detail=f'Cannot delete card profile {prof.profile_code} assigned to active cards. Reassign cards first or use ?force=true')\n"
                    "    before = serialize_entity(prof)\n"
                    "    db.delete(prof)\n"
                    "    record_audit(db, 'CARD_PROFILE', profile_id, 'DELETE', performed_by=current_user, before_state=before,\n"
                    "                 change_summary=f'Deleted card profile {prof.profile_code} (Force: {force})')\n"
                    "    db.commit()\n"
                    "    return {'status': 'deleted', 'profile_id': profile_id}\n\n"
                ),
            },
            # Delete Transaction Code endpoint
            {
                "marker": "step03_02:delete_transaction_code",
                "action": "insert_after",
                "anchor": (
                    "    tc = TransactionCode(**payload.model_dump())\n"
                    "    db.add(tc)\n"
                    "    db.commit()\n"
                    "    db.refresh(tc)\n"
                    "    return tc"
                ),
                "text": (
                    "\n\n@router.delete('/transaction-codes/{tc_id}')\n"
                    "def delete_transaction_code(tc_id: str, force: bool = Query(False), db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):\n"
                    "    tc = db.query(TransactionCode).filter(TransactionCode.id == tc_id).first()\n"
                    "    if not tc:\n"
                    "        raise HTTPException(status_code=404, detail='Transaction code not found')\n"
                    "    has_tx = db.query(Transaction).filter(Transaction.transaction_code == tc.transaction_code).first() is not None\n"
                    "    if has_tx and not force:\n"
                    "        raise HTTPException(status_code=409, detail=f'Cannot delete code {tc.transaction_code} referenced by transactions in journal. Deactivate it instead or use ?force=true')\n"
                    "    before = serialize_entity(tc)\n"
                    "    db.delete(tc)\n"
                    "    record_audit(db, 'TRANSACTION_CODE', tc_id, 'DELETE', performed_by=current_user, before_state=before,\n"
                    "                 change_summary=f'Deleted transaction code {tc.transaction_code}')\n"
                    "    db.commit()\n"
                    "    return {'status': 'deleted', 'transaction_code_id': tc_id}"
                ),
            },
            # Delete Host Parameter endpoint
            {
                "marker": "step03_02:delete_host_parameter",
                "action": "insert_after",
                "anchor": (
                    "    db.commit()\n"
                    '    return {"status": "updated", "id": param.id}'
                ),
                "text": (
                    "\n\n@router.delete('/host-parameters/{param_id}')\n"
                    "def delete_host_parameter(param_id: str, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):\n"
                    "    param = db.query(HostParameter).filter(HostParameter.id == param_id).first()\n"
                    "    if not param:\n"
                    "        raise HTTPException(status_code=404, detail='Parameter not found')\n"
                    "    before = serialize_entity(param)\n"
                    "    db.delete(param)\n"
                    "    record_audit(db, 'HOST_PARAMETER', param_id, 'DELETE', performed_by=current_user, before_state=before,\n"
                    "                 change_summary=f'Deleted host parameter {param.parameter_group}.{param.parameter_name}')\n"
                    "    db.commit()\n"
                    "    return {'status': 'deleted', 'id': param_id}"
                ),
            },
            # Delete Response Code endpoint
            {
                "marker": "step03_02:delete_response_code",
                "action": "insert_after",
                "anchor": (
                    "    db.add(rc)\n"
                    "    db.commit()\n"
                    '    return {"status": "created", "response_code": rc_val}'
                ),
                "text": (
                    "\n\n@router.delete('/response-codes/{rc_id}')\n"
                    "def delete_response_code(rc_id: str, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):\n"
                    "    rc = db.query(ResponseCode).filter(ResponseCode.id == rc_id).first()\n"
                    "    if not rc:\n"
                    "        raise HTTPException(status_code=404, detail='Response code not found')\n"
                    "    before = serialize_entity(rc)\n"
                    "    db.delete(rc)\n"
                    "    record_audit(db, 'RESPONSE_CODE', rc_id, 'DELETE', performed_by=current_user, before_state=before,\n"
                    "                 change_summary=f'Deleted response code {rc.response_code}')\n"
                    "    db.commit()\n"
                    "    return {'status': 'deleted', 'id': rc_id}"
                ),
            },
            # Update & Delete HSM Key endpoints
            {
                "marker": "step03_02:hsm_key_put_and_delete",
                "action": "insert_after",
                "anchor": (
                    "    record_system_log(db, \"INFO\", \"HSMKeyManagement\", \"KEY_REGISTERED\", f\"Registered key reference {key_rec.key_identifier} (KVC {key_rec.kvc})\")\n"
                    "    db.commit()\n"
                    "    db.refresh(key_rec)\n"
                    "    return key_rec"
                ),
                "text": (
                    "\n\n@router.put('/hsm/keys/{key_id}', response_model=HsmKeyReferenceOut)\n"
                    "def update_hsm_key(key_id: str, payload: HsmKeyReferenceUpdate, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):\n"
                    "    key_rec = db.query(HsmKeyReference).filter(HsmKeyReference.id == key_id).first()\n"
                    "    if not key_rec:\n"
                    "        raise HTTPException(status_code=404, detail='HSM Key not found')\n"
                    "    before = serialize_entity(key_rec)\n"
                    "    for k, v in payload.model_dump(exclude_unset=True).items():\n"
                    "        setattr(key_rec, k, v)\n"
                    "    after = serialize_entity(key_rec)\n"
                    "    record_audit(db, 'HSM_KEY', key_rec.id, 'UPDATE', performed_by=current_user, before_state=before, after_state=after,\n"
                    "                 change_summary=f'Updated HSM key reference {key_rec.key_identifier}')\n"
                    "    db.commit()\n"
                    "    db.refresh(key_rec)\n"
                    "    return key_rec\n\n\n"
                    "@router.delete('/hsm/keys/{key_id}')\n"
                    "def delete_hsm_key(key_id: str, force: bool = Query(False), db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):\n"
                    "    key_rec = db.query(HsmKeyReference).filter(HsmKeyReference.id == key_id).first()\n"
                    "    if not key_rec:\n"
                    "        raise HTTPException(status_code=404, detail='HSM Key not found')\n"
                    "    has_ops = db.query(HsmOperation).filter(HsmOperation.key_reference_id == key_rec.id).first() is not None\n"
                    "    if has_ops and not force:\n"
                    "        raise HTTPException(status_code=409, detail=f'Cannot delete key {key_rec.key_identifier} referenced in HSM operation audit history. Deactivate it instead or use ?force=true')\n"
                    "    before = serialize_entity(key_rec)\n"
                    "    db.delete(key_rec)\n"
                    "    record_audit(db, 'HSM_KEY', key_id, 'DELETE', performed_by=current_user, before_state=before,\n"
                    "                 change_summary=f'Deleted HSM key reference {key_rec.key_identifier}')\n"
                    "    db.commit()\n"
                    "    return {'status': 'deleted', 'key_id': key_id}"
                ),
            },
        ],
    )

    # 3. Write automated test suite backend/tests/test_step03_config_crud.py
    session.write_file("backend/tests/test_step03_config_crud.py", TEST_CONFIG_CRUD_CODE)

    session.record_progress(
        completed=[
            "Added CardProfile Pydantic schemas in `backend/app/schemas.py`.",
            "Added `GET`, `POST`, `PUT`, and `DELETE` endpoints for Card Profiles with 409 conflict checks against cards.",
            "Added `DELETE` endpoints for Transaction Codes, Response Codes, and Host Parameters with audit logging.",
            "Added `PUT` and `DELETE` endpoints for HSM Key References with 409 conflict protection against `hsm_operations`.",
            "Created automated Pytest test suite `backend/tests/test_step03_config_crud.py`.",
        ],
        remaining=[
            "Step 3 Script 3 of 3 (`tools/install_step03_03.py`): Implement frontend Edit Modals, Delete Confirmation Dialogs, 409 Conflict alerts, and the Audit Trail Viewer page.",
        ],
        modified_files=[
            "backend/app/schemas.py",
            "backend/app/api_routes.py",
            "backend/tests/test_step03_config_crud.py",
        ],
    )

    session.record_contracts(
        section_title="Step 3.2 — Configuration & Cryptographic Resource CRUD and Audit",
        contract_items=[
            "**GET /api/card-profiles**: Lists all configured card profiles.",
            "**POST /api/card-profiles**: Creates a new card profile.",
            "**PUT /api/card-profiles/{id}**: Updates profile channel permissions with audit logging.",
            "**DELETE /api/card-profiles/{id}**: Removes profile (returns 409 Conflict if assigned to active cards unless `?force=true`).",
            "**DELETE /api/transaction-codes/{id}**: Decommission transaction codes.",
            "**DELETE /api/response-codes/{id}**: Removes response code mapping.",
            "**DELETE /api/host-parameters/{id}**: Removes host authorization parameter.",
            "**PUT /api/hsm/keys/{id}**: Updates HSM key name, status, or usage.",
            "**DELETE /api/hsm/keys/{id}**: Removes key reference (returns 409 Conflict if historical cryptographic operations reference key unless `?force=true`).",
        ],
    )

    return session.finish()


if __name__ == "__main__":
    sys.exit(main())