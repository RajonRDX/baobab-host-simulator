#!/usr/bin/env python3
"""
INSTALLER: tools/install_step02_01.py
STEP 2 — Link Institutions to Payment Objects & Transaction Attributes — Script 1 of 2
Adds:
  1. institution_id foreign keys to Customer, Account, Card, and HsmKeyReference
  2. issuer_institution_id, acquirer_institution_id, ps_code, and is_on_us to Transaction
  3. Pydantic v2 schema extensions
  4. Automatic resolution in HostTransactionProcessor
  5. Backfill in seed_data.py
  6. Automated Pytest test suite
"""

from pathlib import Path
import sys

BASE_DIR = Path(r"E:\HOST_VSCODE\host-simulator").resolve()
sys.path.insert(0, str(BASE_DIR))

from tools.patcher import PatcherSession, parse_installer_args

TEST_STEP02_CODE = '''"""
test_step02_institution_links.py — Tests for Step 2 Institution Linking & Transaction Scoping
"""

import os
import pytest
from decimal import Decimal
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Account, Card, Customer, Institution, ProcessingSystem, Transaction
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


def test_entities_have_institution_links(db_session):
    xbank = db_session.query(Institution).filter(Institution.institution_code == "XBANK").first()
    assert xbank is not None

    cust = db_session.query(Customer).first()
    assert cust.institution_id == xbank.id

    acct = db_session.query(Account).first()
    assert acct.institution_id == xbank.id

    card = db_session.query(Card).first()
    assert card.institution_id == xbank.id


def test_transaction_records_institution_and_ps_code(db_session):
    proc = HostTransactionProcessor(db_session)
    res = proc.process_transaction({
        "transaction_code": "10",
        "mti": "0200",
        "test_clear_pin_helper": "1234",
        "fields": {
            "2": "4567890123450001",
            "3": "0100000",
            "4": "000000150000",
            "11": "300001",
            "32": "123456",  # XBANK acquirer ID
            "37": "000095000001",
            "41": "ATM01",
            "49": "BDT",
        },
    })
    assert res["response_code"] == "00"

    tx = db_session.query(Transaction).filter(Transaction.id == res["transaction_id"]).first()
    assert tx is not None
    assert tx.ps_code == "ITCL"
    assert tx.is_on_us is True
    assert tx.issuer_institution_id is not None
    assert tx.acquirer_institution_id is not None
    assert tx.issuer_institution_id == tx.acquirer_institution_id


def test_api_creates_card_with_institution(client, db_session):
    ybank = db_session.query(Institution).filter(Institution.institution_code == "YBANK").first()
    cust = db_session.query(Customer).first()
    acct = db_session.query(Account).first()

    payload = {
        "customer_id": cust.id,
        "test_pan_reference": "5123450123459999",
        "cardholder_name": "YBANK TEST HOLDER",
        "expiry_month": 12,
        "expiry_year": 2028,
        "linked_account_id": acct.id,
        "institution_id": ybank.id,
    }
    res = client.post("/api/cards", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["institution_id"] == ybank.id
    assert data["institution_code"] == "YBANK"
'''


def main() -> int:
    args = parse_installer_args("Step 02_01: Link Institutions to Entities & Transaction Attributes")
    session = PatcherSession(
        step_id="step02_01",
        title="Add Institution FKs to Customers, Accounts, Cards, Keys & Transaction Switching Attributes",
        dry_run=args.dry_run,
    )

    # 1. Patch backend/app/models.py to add institution_id to Customer, Account, Card, HsmKeyReference, and Transaction
    session.patch_file(
        "backend/app/models.py",
        [
            # Customer.institution_id
            {
                "marker": "step02_01:customer_inst_id",
                "action": "insert_after",
                "anchor": '    customer_status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")',
                "text": (
                    '    institution_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("institutions.id"), index=True)\n'
                    '    institution: Mapped[Optional["Institution"]] = relationship("Institution", foreign_keys=[institution_id])'
                ),
            },
            # Account.institution_id
            {
                "marker": "step02_01:account_inst_id",
                "action": "insert_after",
                "anchor": '    branch_code: Mapped[Optional[str]] = mapped_column(String(20), default="0001")',
                "text": (
                    '    institution_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("institutions.id"), index=True)\n'
                    '    institution: Mapped[Optional["Institution"]] = relationship("Institution", foreign_keys=[institution_id])'
                ),
            },
            # Card.institution_id
            {
                "marker": "step02_01:card_inst_id",
                "action": "insert_after",
                "anchor": '    linked_account_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("accounts.id"))',
                "text": (
                    '    institution_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("institutions.id"), index=True)\n'
                    '    institution: Mapped[Optional["Institution"]] = relationship("Institution", foreign_keys=[institution_id])'
                ),
            },
            # HsmKeyReference.institution_id & processing_system_id
            {
                "marker": "step02_01:hsm_key_inst_id",
                "action": "insert_after",
                "anchor": '    key_status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")',
                "text": (
                    '    institution_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("institutions.id"), index=True)\n'
                    '    processing_system_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("processing_systems.id"), index=True)\n'
                    '    institution: Mapped[Optional["Institution"]] = relationship("Institution", foreign_keys=[institution_id])\n'
                    '    processing_system: Mapped[Optional["ProcessingSystem"]] = relationship("ProcessingSystem", foreign_keys=[processing_system_id])'
                ),
            },
            # Transaction attributes: issuer_institution_id, acquirer_institution_id, ps_code, is_on_us
            {
                "marker": "step02_01:tx_institution_attrs",
                "action": "insert_after",
                "anchor": '    original_transaction_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("transactions.id"))',
                "text": (
                    '    issuer_institution_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("institutions.id"), index=True)\n'
                    '    acquirer_institution_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("institutions.id"), index=True)\n'
                    '    ps_code: Mapped[str] = mapped_column(String(30), nullable=False, default="ITCL")\n'
                    '    is_on_us: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)\n'
                    '    issuer_institution: Mapped[Optional["Institution"]] = relationship("Institution", foreign_keys=[issuer_institution_id])\n'
                    '    acquirer_institution: Mapped[Optional["Institution"]] = relationship("Institution", foreign_keys=[acquirer_institution_id])'
                ),
            },
        ],
    )

    # 2. Patch backend/app/schemas.py to extend Customer, Account, Card, Key, and Transaction schemas with institution fields
    session.patch_file(
        "backend/app/schemas.py",
        [
            # CustomerCreate & CustomerOut
            {
                "marker": "step02_01:schema_customer_inst",
                "action": "insert_after",
                "anchor": '    risk_category: str = "NORMAL"',
                "text": "    institution_id: Optional[str] = None",
            },
            {
                "marker": "step02_01:schema_customer_out_inst",
                "action": "insert_after",
                "anchor": "    created_at: datetime\n    updated_at: datetime",
                "text": "    institution_code: Optional[str] = None\n    institution_name: Optional[str] = None",
            },
            # AccountCreate & AccountOut
            {
                "marker": "step02_01:schema_account_inst",
                "action": "insert_after",
                "anchor": '    branch_code: str = "0001"',
                "text": "    institution_id: Optional[str] = None",
            },
            {
                "marker": "step02_01:schema_account_out_inst",
                "action": "insert_after",
                "anchor": "    id: str\n    created_at: datetime\n    updated_at: datetime",
                "text": "    institution_code: Optional[str] = None\n    institution_name: Optional[str] = None",
            },
            # CardCreate & CardOut
            {
                "marker": "step02_01:schema_card_inst",
                "action": "insert_after",
                "anchor": '    cvv_value: str = "011"',
                "text": "    institution_id: Optional[str] = None",
            },
            {
                "marker": "step02_01:schema_card_out_inst",
                "action": "insert_after",
                "anchor": "    card_profile_id: Optional[str]\n    created_at: datetime",
                "text": "    institution_id: Optional[str] = None\n    institution_code: Optional[str] = None\n    institution_name: Optional[str] = None",
            },
            # HsmKeyReferenceCreate & HsmKeyReferenceOut
            {
                "marker": "step02_01:schema_hsm_key_inst",
                "action": "insert_after",
                "anchor": '    key_status: str = "ACTIVE"',
                "text": "    institution_id: Optional[str] = None\n    processing_system_id: Optional[str] = None",
            },
            {
                "marker": "step02_01:schema_hsm_key_out_inst",
                "action": "insert_after",
                "anchor": "    id: str\n    created_at: datetime",
                "text": "    institution_code: Optional[str] = None\n    ps_code: Optional[str] = None",
            },
        ],
    )

    # 3. Patch backend/app/seed_data.py to link existing seeded entities to XBANK (ITCL)
    session.patch_file(
        "backend/app/seed_data.py",
        [
            {
                "marker": "step02_01:seed_link_existing_entities",
                "action": "insert_after",
                "anchor": "    _, pvk_clear = (\"PVK_VISA_01\", SoftHsmCryptoCore.INTERNAL_CLEAR_KEYS[\"PVK_VISA_01\"])",
                "text": (
                    "    xbank = db.query(Institution).filter(Institution.institution_code == 'XBANK').first()\n"
                    "    xbank_id = xbank.id if xbank else None\n"
                    "    itcl_ps = db.query(ProcessingSystem).filter(ProcessingSystem.ps_code == 'ITCL').first()\n"
                    "    itcl_id = itcl_ps.id if itcl_ps else None"
                ),
            },
            {
                "marker": "step02_01:seed_customer_inst_arg",
                "action": "insert_after",
                "anchor": '            address="Dhaka, Bangladesh (Synthetic Test Record)",\n            customer_status=c_stat,',
                "text": "            institution_id=xbank_id,",
            },
            {
                "marker": "step02_01:seed_account_inst_arg",
                "action": "insert_after",
                "anchor": '            overdraft_limit=Decimal("0.00"),\n            account_status="ACTIVE",',
                "text": "            institution_id=xbank_id,",
            },
            {
                "marker": "step02_01:seed_card_inst_arg",
                "action": "insert_after",
                "anchor": '            linked_account_id=acct.id,\n            card_profile_id=prof_id,',
                "text": "            institution_id=xbank_id,",
            },
            {
                "marker": "step02_01:seed_hsm_key_inst_arg",
                "action": "insert_after",
                "anchor": '                key_status="ACTIVE",',
                "text": "                institution_id=xbank_id,\n                processing_system_id=itcl_id,",
            },
            # Backfill existing records if they were created before Step 2
            {
                "marker": "step02_01:seed_backfill_existing",
                "action": "insert_before",
                "anchor": "    # 5. Configurable Transaction Codes (10, 20, 30, 40)",
                "text": (
                    "    # Backfill Step 2 institution links on pre-existing records\n"
                    "    xbank_rec = db.query(Institution).filter(Institution.institution_code == 'XBANK').first()\n"
                    "    itcl_rec = db.query(ProcessingSystem).filter(ProcessingSystem.ps_code == 'ITCL').first()\n"
                    "    if xbank_rec:\n"
                    "        db.query(Customer).filter(Customer.institution_id.is_(None)).update({'institution_id': xbank_rec.id}, synchronize_session=False)\n"
                    "        db.query(Account).filter(Account.institution_id.is_(None)).update({'institution_id': xbank_rec.id}, synchronize_session=False)\n"
                    "        db.query(Card).filter(Card.institution_id.is_(None)).update({'institution_id': xbank_rec.id}, synchronize_session=False)\n"
                    "        if itcl_rec:\n"
                    "            db.query(HsmKeyReference).filter(HsmKeyReference.institution_id.is_(None)).update({'institution_id': xbank_rec.id, 'processing_system_id': itcl_rec.id}, synchronize_session=False)\n"
                    "        db.commit()\n"
                ),
            },
        ],
    )

    # 4. Patch backend/app/api_routes.py to ingest and return institution_id on Customers, Accounts, Cards, and Keys
    session.patch_file(
        "backend/app/api_routes.py",
        [
            # Import Institution & ProcessingSystem
            {
                "marker": "step02_01:api_routes_inst_imports",
                "action": "insert_after",
                "anchor": "from app.models import (",
                "text": "    BinRange,\n    Institution,\n    ProcessingSystem,",
            },
            # Create Customer with default institution
            {
                "marker": "step02_01:api_customer_create_inst",
                "action": "replace",
                "anchor": (
                    "    cust = Customer(**payload.model_dump())\n"
                    "    db.add(cust)"
                ),
                "text": (
                    "    data = payload.model_dump()\n"
                    "    if not data.get('institution_id'):\n"
                    "        xbank = db.query(Institution).filter(Institution.institution_code == 'XBANK').first()\n"
                    "        if xbank:\n"
                    "            data['institution_id'] = xbank.id\n"
                    "    cust = Customer(**data)\n"
                    "    db.add(cust)"
                ),
            },
            # Create Account with default institution
            {
                "marker": "step02_01:api_account_create_inst",
                "action": "replace",
                "anchor": (
                    "    acct = Account(**payload.model_dump())\n"
                    "    db.add(acct)"
                ),
                "text": (
                    "    data = payload.model_dump()\n"
                    "    if not data.get('institution_id'):\n"
                    "        xbank = db.query(Institution).filter(Institution.institution_code == 'XBANK').first()\n"
                    "        if xbank:\n"
                    "            data['institution_id'] = xbank.id\n"
                    "    acct = Account(**data)\n"
                    "    db.add(acct)"
                ),
            },
            # List Accounts: include institution info
            {
                "marker": "step02_01:api_account_list_inst",
                "action": "insert_after",
                "anchor": '            "branch_code": a.branch_code,',
                "text": (
                    '            "institution_id": a.institution_id,\n'
                    '            "institution_code": a.institution.institution_code if a.institution else None,\n'
                    '            "institution_name": a.institution.name if a.institution else None,'
                ),
            },
            # Create Card: ingest institution_id
            {
                "marker": "step02_01:api_card_create_inst",
                "action": "replace",
                "anchor": (
                    "        linked_account_id=payload.linked_account_id,\n"
                    "        card_profile_id=payload.card_profile_id,\n"
                    "    )\n"
                    "    db.add(card)"
                ),
                "text": (
                    "        linked_account_id=payload.linked_account_id,\n"
                    "        card_profile_id=payload.card_profile_id,\n"
                    "        institution_id=payload.institution_id or (db.query(Institution).filter(Institution.institution_code == 'XBANK').first().id if db.query(Institution).filter(Institution.institution_code == 'XBANK').first() else None),\n"
                    "    )\n"
                    "    db.add(card)"
                ),
            },
            # List Cards: include institution info
            {
                "marker": "step02_01:api_card_list_inst",
                "action": "insert_after",
                "anchor": '            "linked_account_id": c.linked_account_id,',
                "text": (
                    '            "institution_id": c.institution_id,\n'
                    '            "institution_code": c.institution.institution_code if c.institution else None,\n'
                    '            "institution_name": c.institution.name if c.institution else None,'
                ),
            },
            # List Transactions: include institution codes, ps_code, and on_us flag
            {
                "marker": "step02_01:api_tx_list_inst",
                "action": "insert_after",
                "anchor": '            "source_channel": t.source_channel,',
                "text": (
                    '            "ps_code": t.ps_code,\n'
                    '            "is_on_us": t.is_on_us,\n'
                    '            "issuer_institution_id": t.issuer_institution_id,\n'
                    '            "issuer_code": t.issuer_institution.institution_code if t.issuer_institution else None,\n'
                    '            "acquirer_institution_id": t.acquirer_institution_id,\n'
                    '            "acquirer_code": t.acquirer_institution.institution_code if t.acquirer_institution else None,'
                ),
            },
        ],
    )

    # 5. Patch backend/app/host_engine.py to resolve institution attributes during transaction authorization
    session.patch_file(
        "backend/app/host_engine.py",
        [
            {
                "marker": "step02_01:host_engine_imports",
                "action": "insert_after",
                "anchor": "from app.models import (",
                "text": "    BinRange,\n    Institution,\n    ProcessingSystem,",
            },
            # In process_transaction: resolve issuer_institution_id and acquirer_institution_id
            {
                "marker": "step02_01:host_engine_resolve_institutions",
                "action": "insert_after",
                "anchor": '        currency = input_fields.get("49", "BDT")',
                "text": (
                    "        # Step 2: Resolve Acquiring Institution (DE32) & Issuing Institution (Card / BIN prefix)\n"
                    "        de32_acq = input_fields.get('32', '123456')\n"
                    "        acq_inst = self.db.query(Institution).filter(Institution.acquirer_id == de32_acq).first()\n"
                    "        if not acq_inst:\n"
                    "            acq_inst = self.db.query(Institution).filter(Institution.institution_code == 'XBANK').first()\n"
                    "        acquirer_inst_id = acq_inst.id if acq_inst else None\n\n"
                    "        # Resolve issuing institution by card record or BIN range\n"
                    "        issuer_inst_id = None\n"
                    "        ps_code_val = 'ITCL'\n"
                    "        bin_match = self.db.query(BinRange).filter(BinRange.bin_prefix == pan[:6]).first() if len(pan) >= 6 else None\n"
                    "        if bin_match:\n"
                    "            issuer_inst_id = bin_match.institution_id\n"
                    "            if bin_match.processing_system:\n"
                    "                ps_code_val = bin_match.processing_system.ps_code\n"
                    "        elif acq_inst:\n"
                    "            issuer_inst_id = acq_inst.id\n"
                ),
            },
            # Pass resolved institution IDs into _finalize_transaction
            {
                "marker": "step02_01:host_engine_pass_inst_finalize",
                "action": "replace",
                "anchor": (
                    "            source_channel=request_data.get(\"source_channel\", \"SIMULATOR\"),\n"
                    "            idempotency_key=idem_key,\n"
                    "        )"
                ),
                "text": (
                    "            source_channel=request_data.get(\"source_channel\", \"SIMULATOR\"),\n"
                    "            idempotency_key=idem_key,\n"
                    "            issuer_institution_id=card.institution_id if (card and card.institution_id) else issuer_inst_id,\n"
                    "            acquirer_institution_id=acquirer_inst_id,\n"
                    "            ps_code=ps_code_val,\n"
                    "        )"
                ),
            },
            # Update _finalize_transaction signature to accept institution attributes
            {
                "marker": "step02_01:finalize_sig",
                "action": "replace",
                "anchor": (
                    "        original_tx: Optional[Transaction] = None,\n"
                    "        source_channel: str = \"SIMULATOR\",\n"
                    "        idempotency_key: Optional[str] = None,\n"
                    "    ) -> Dict[str, Any]:"
                ),
                "text": (
                    "        original_tx: Optional[Transaction] = None,\n"
                    "        source_channel: str = \"SIMULATOR\",\n"
                    "        idempotency_key: Optional[str] = None,\n"
                    "        issuer_institution_id: Optional[str] = None,\n"
                    "        acquirer_institution_id: Optional[str] = None,\n"
                    "        ps_code: str = \"ITCL\",\n"
                    "    ) -> Dict[str, Any]:"
                ),
            },
            # In _finalize_transaction: assign to Transaction model
            {
                "marker": "step02_01:tx_model_assign_inst",
                "action": "insert_after",
                "anchor": '            source_channel=source_channel,',
                "text": (
                    "            issuer_institution_id=issuer_institution_id or (card.institution_id if card else None),\n"
                    "            acquirer_institution_id=acquirer_institution_id,\n"
                    "            ps_code=ps_code,\n"
                    "            is_on_us=(issuer_institution_id == acquirer_institution_id) if (issuer_institution_id and acquirer_institution_id) else True,"
                ),
            },
            # In _finalize_transaction: return institution info in response payload
            {
                "marker": "step02_01:tx_resp_dict_inst",
                "action": "insert_after",
                "anchor": '            "response_tic_f39": f"000{response_code}",',
                "text": (
                    '            "ps_code": ps_code,\n'
                    '            "is_on_us": tx.is_on_us,\n'
                    '            "issuer_institution_id": tx.issuer_institution_id,\n'
                    '            "acquirer_institution_id": tx.acquirer_institution_id,'
                ),
            },
        ],
    )

    # 6. Write automated test suite backend/tests/test_step02_institution_links.py
    session.write_file("backend/tests/test_step02_institution_links.py", TEST_STEP02_CODE)

    session.record_progress(
        completed=[
            "Added nullable `institution_id` foreign keys to `Customer`, `Account`, `Card`, and `HsmKeyReference` in `backend/app/models.py`.",
            "Added transaction switching attributes `issuer_institution_id`, `acquirer_institution_id`, `ps_code`, and `is_on_us` to `Transaction`.",
            "Updated Pydantic schemas in `backend/app/schemas.py` to accept and serialize institution codes and names.",
            "Updated `seed_data.py` to link existing synthetic records to `XBANK` under `ITCL` and backfill pre-existing rows.",
            "Updated `HostTransactionProcessor` in `backend/app/host_engine.py` to resolve acquiring bank (DE32) and issuing bank (DE2 BIN range) and determine On-Us vs Off-Us status.",
            "Created automated test suite `backend/tests/test_step02_institution_links.py`.",
        ],
        remaining=[
            "Step 2 Script 2 of 2 (`tools/install_step02_02.py`): Update frontend pages (`BankingEntities.tsx`, `SimulatorAndJournal.tsx`, `HsmAndMonitorPages.tsx`) with institution selector dropdowns, table badges, and bank filters.",
        ],
        modified_files=[
            "backend/app/models.py",
            "backend/app/schemas.py",
            "backend/app/seed_data.py",
            "backend/app/api_routes.py",
            "backend/app/host_engine.py",
            "backend/tests/test_step02_institution_links.py",
        ],
    )

    session.record_contracts(
        section_title="Step 2.1 — Institution Scoping & Transaction Switching Attributes",
        contract_items=[
            "**Model Columns**: `customers.institution_id`, `accounts.institution_id`, `cards.institution_id`, `hsm_key_references.institution_id`, `hsm_key_references.processing_system_id`.",
            "**Transaction Columns**: `transactions.issuer_institution_id`, `transactions.acquirer_institution_id`, `transactions.ps_code` (default `'ITCL'`), `transactions.is_on_us` (boolean).",
            "**Host Engine Routing**: `HostTransactionProcessor` resolves `acquirer_institution_id` from `DE32` and `issuer_institution_id` from `card.institution_id` or `BinRange` prefix; calculates `is_on_us` as `(issuer_id == acquirer_id)`.",
        ],
    )

    return session.finish()


if __name__ == "__main__":
    sys.exit(main())