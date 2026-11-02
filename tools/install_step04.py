#!/usr/bin/env python3
"""
INSTALLER: tools/install_step04.py
STEP 4 — Card and Account Multi-Linking (Single Unified Installer)
Adds:
  1. Pydantic v2 schemas for CardAccount multi-linking in backend/app/schemas.py
  2. Full CRUD endpoints for managing card-account relationships in backend/app/api_routes.py
  3. Dynamic DE3 (digits 3-4) account selection logic in backend/app/host_engine.py
  4. Multi-account management modal in frontend/src/pages/BankingEntities.tsx
  5. Automated Pytest test suite in backend/tests/test_step04_multi_account.py
"""

from pathlib import Path
import sys

BASE_DIR = Path(r"E:\HOST_VSCODE\host-simulator").resolve()
sys.path.insert(0, str(BASE_DIR))

from tools.patcher import PatcherSession, parse_installer_args

TEST_STEP04_CODE = '''"""
test_step04_multi_account.py — Tests for Step 4 Card & Account Multi-Linking and DE3 routing
"""

import os
import pytest
from decimal import Decimal
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Account, Card, CardAccount, Customer, Transaction
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


def test_link_multiple_accounts_to_card(client, db_session):
    card = db_session.query(Card).first()
    cust = card.customer

    # Create a secondary CURRENT account for the customer
    sec_acct = Account(
        account_number="2002009999",
        customer_id=cust.id,
        account_type="CURRENT",
        currency="BDT",
        available_balance=Decimal("50000.00"),
        ledger_balance=Decimal("50000.00"),
        account_status="ACTIVE",
        institution_id=card.institution_id,
    )
    db_session.add(sec_acct)
    db_session.commit()

    # Link secondary account to card via API
    payload = {
        "account_id": sec_acct.id,
        "account_role": "SECONDARY",
        "priority": 2,
    }
    res = client.post(f"/api/cards/{card.id}/accounts", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["account_number"] == "2002009999"
    assert data["account_role"] == "SECONDARY"
    assert data["priority"] == 2

    # Query card accounts
    get_res = client.get(f"/api/cards/{card.id}/accounts")
    assert get_res.status_code == 200
    links = get_res.json()
    assert len(links) >= 2


def test_de3_account_selection_savings_vs_current(db_session):
    proc = HostTransactionProcessor(db_session)
    card = db_session.query(Card).filter(Card.test_pan_reference == "4567890123450001").first()

    # Seeded primary account is SAVINGS (balance: 150,000.00)
    primary_acct = db_session.query(Account).filter(Account.id == card.linked_account_id).first()
    assert primary_acct.account_type == "SAVINGS"

    # Add a CURRENT account with 20,000.00 balance
    curr_acct = Account(
        account_number="2002008888",
        customer_id=card.customer_id,
        account_type="CURRENT",
        currency="BDT",
        available_balance=Decimal("20000.00"),
        ledger_balance=Decimal("20000.00"),
        account_status="ACTIVE",
        institution_id=card.institution_id,
    )
    db_session.add(curr_acct)
    db_session.flush()

    # Link CURRENT account to the card
    db_session.add(
        CardAccount(
            card_id=card.id,
            account_id=curr_acct.id,
            account_role="SECONDARY",
            currency="BDT",
            priority=2,
            status="ACTIVE",
        )
    )
    db_session.commit()

    # Transaction 1: DE3 = 0100100 (digits 3-4 = 01 -> Current/Checking account requested)
    res_curr = proc.process_transaction({
        "transaction_code": "10",
        "mti": "0200",
        "test_clear_pin_helper": "1234",
        "fields": {
            "2": card.test_pan_reference,
            "3": "0100100",  # 010 (tran code) + 01 (From Checking) + 00 (To Unspecified)
            "4": "000000050000",  # 500.00 BDT
            "11": "400001",
            "37": "000099000001",
            "41": "ATM01",
            "49": "BDT",
        },
    })
    assert res_curr["response_code"] == "00"
    tx_curr = db_session.query(Transaction).filter(Transaction.id == res_curr["transaction_id"]).first()
    assert tx_curr.account_id == curr_acct.id

    # Transaction 2: DE3 = 0101100 (digits 3-4 = 11 -> Savings account requested)
    res_sav = proc.process_transaction({
        "transaction_code": "10",
        "mti": "0200",
        "test_clear_pin_helper": "1234",
        "fields": {
            "2": card.test_pan_reference,
            "3": "0101100",  # 010 (tran code) + 11 (From Savings) + 00 (To Unspecified)
            "4": "000000050000",  # 500.00 BDT
            "11": "400002",
            "37": "000099000002",
            "41": "ATM01",
            "49": "BDT",
        },
    })
    assert res_sav["response_code"] == "00"
    tx_sav = db_session.query(Transaction).filter(Transaction.id == res_sav["transaction_id"]).first()
    assert tx_sav.account_id == primary_acct.id
'''


def main() -> int:
    args = parse_installer_args("Step 04: Complete Card and Account Multi-Linking")
    session = PatcherSession(
        step_id="step04",
        title="Implement Complete Multi-Account Card Linking & DE3 Account Selection Engine",
        dry_run=args.dry_run,
    )

    # 1. Patch backend/app/schemas.py to add CardAccount schemas
    session.patch_file(
        "backend/app/schemas.py",
        [
            {
                "marker": "step04:schemas_card_account_links",
                "action": "append",
                "text": (
                    "\n# ==============================================================================\n"
                    "# STEP 4 SCHEMAS: CARD & ACCOUNT MULTI-LINKING\n"
                    "# ==============================================================================\n\n"
                    "class CardAccountLinkCreate(BaseModel):\n"
                    "    account_id: str\n"
                    '    account_role: str = "SECONDARY"  # PRIMARY, SECONDARY\n'
                    "    priority: int = 2\n"
                    '    status: str = "ACTIVE"\n\n\n'
                    "class CardAccountLinkUpdate(BaseModel):\n"
                    "    account_role: Optional[str] = None\n"
                    "    priority: Optional[int] = None\n"
                    "    status: Optional[str] = None\n\n\n"
                    "class CardAccountLinkOut(BaseModel):\n"
                    "    id: str\n"
                    "    card_id: str\n"
                    "    account_id: str\n"
                    "    account_number: Optional[str] = None\n"
                    "    account_type: Optional[str] = None\n"
                    "    currency: str\n"
                    "    available_balance: Optional[float] = None\n"
                    "    account_role: str\n"
                    "    priority: int\n"
                    "    status: str\n"
                    "    model_config = ConfigDict(from_attributes=True)\n"
                ),
            }
        ],
    )

    # 2. Patch backend/app/api_routes.py to add endpoints for card accounts
    session.patch_file(
        "backend/app/api_routes.py",
        [
            {
                "marker": "step04:api_routes_schema_imports",
                "action": "insert_after",
                "anchor": "    CardUpdate,",
                "text": (
                    "    CardAccountLinkCreate,\n"
                    "    CardAccountLinkOut,\n"
                    "    CardAccountLinkUpdate,"
                ),
            },
            {
                "marker": "step04:api_card_account_endpoints",
                "action": "insert_before",
                "anchor": "# ==============================================================================\n# 3. TRANSACTION CODES, HOST CONFIGURATION & RESPONSE CODES",
                "text": (
                    "# --- CARD & ACCOUNT MULTI-LINKING (STEP 4) ---\n\n"
                    "@router.get('/cards/{card_id}/accounts', response_model=List[CardAccountLinkOut])\n"
                    "def list_card_accounts(card_id: str, db: Session = Depends(get_db), _: str = Depends(get_current_user)):\n"
                    "    card = db.query(Card).filter(Card.id == card_id).first()\n"
                    "    if not card:\n"
                    "        raise HTTPException(status_code=404, detail='Card not found')\n"
                    "    links = db.query(CardAccount).filter(CardAccount.card_id == card.id).order_by(CardAccount.priority.asc()).all()\n"
                    "    out = []\n"
                    "    for l in links:\n"
                    "        acct = l.account\n"
                    "        out.append({\n"
                    "            'id': l.id,\n"
                    "            'card_id': l.card_id,\n"
                    "            'account_id': l.account_id,\n"
                    "            'account_number': acct.account_number if acct else None,\n"
                    "            'account_type': acct.account_type if acct else None,\n"
                    "            'currency': l.currency,\n"
                    "            'available_balance': float(acct.available_balance) if acct else 0.0,\n"
                    "            'account_role': l.account_role,\n"
                    "            'priority': l.priority,\n"
                    "            'status': l.status,\n"
                    "        })\n"
                    "    return out\n\n\n"
                    "@router.post('/cards/{card_id}/accounts', response_model=CardAccountLinkOut)\n"
                    "def link_account_to_card(card_id: str, payload: CardAccountLinkCreate, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):\n"
                    "    card = db.query(Card).filter(Card.id == card_id).first()\n"
                    "    if not card:\n"
                    "        raise HTTPException(status_code=404, detail='Card not found')\n"
                    "    acct = db.query(Account).filter(Account.id == payload.account_id).first()\n"
                    "    if not acct:\n"
                    "        raise HTTPException(status_code=404, detail='Account not found')\n"
                    "    existing = db.query(CardAccount).filter(CardAccount.card_id == card.id, CardAccount.account_id == acct.id).first()\n"
                    "    if existing:\n"
                    "        raise HTTPException(status_code=400, detail='Account is already linked to this card')\n\n"
                    "    if payload.account_role == 'PRIMARY':\n"
                    "        db.query(CardAccount).filter(CardAccount.card_id == card.id).update({'account_role': 'SECONDARY'}, synchronize_session=False)\n"
                    "        card.linked_account_id = acct.id\n\n"
                    "    link = CardAccount(\n"
                    "        card_id=card.id,\n"
                    "        account_id=acct.id,\n"
                    "        account_role=payload.account_role,\n"
                    "        currency=acct.currency,\n"
                    "        priority=payload.priority,\n"
                    "        status=payload.status,\n"
                    "    )\n"
                    "    db.add(link)\n"
                    "    db.flush()\n"
                    "    record_audit(db, 'CARD_ACCOUNT', link.id, 'CREATE', performed_by=current_user,\n"
                    "                 after_state=serialize_entity(link),\n"
                    "                 change_summary=f'Linked account {acct.account_number} to card {card.masked_pan} as {payload.account_role}')\n"
                    "    db.commit()\n"
                    "    db.refresh(link)\n"
                    "    return {\n"
                    "        'id': link.id,\n"
                    "        'card_id': link.card_id,\n"
                    "        'account_id': link.account_id,\n"
                    "        'account_number': acct.account_number,\n"
                    "        'account_type': acct.account_type,\n"
                    "        'currency': link.currency,\n"
                    "        'available_balance': float(acct.available_balance),\n"
                    "        'account_role': link.account_role,\n"
                    "        'priority': link.priority,\n"
                    "        'status': link.status,\n"
                    "    }\n\n\n"
                    "@router.put('/cards/accounts/{link_id}', response_model=CardAccountLinkOut)\n"
                    "def update_card_account_link(link_id: str, payload: CardAccountLinkUpdate, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):\n"
                    "    link = db.query(CardAccount).filter(CardAccount.id == link_id).first()\n"
                    "    if not link:\n"
                    "        raise HTTPException(status_code=404, detail='Card account link not found')\n"
                    "    before = serialize_entity(link)\n"
                    "    if payload.account_role == 'PRIMARY':\n"
                    "        db.query(CardAccount).filter(CardAccount.card_id == link.card_id).update({'account_role': 'SECONDARY'}, synchronize_session=False)\n"
                    "        card = db.query(Card).filter(Card.id == link.card_id).first()\n"
                    "        if card:\n"
                    "            card.linked_account_id = link.account_id\n\n"
                    "    for k, v in payload.model_dump(exclude_unset=True).items():\n"
                    "        setattr(link, k, v)\n"
                    "    after = serialize_entity(link)\n"
                    "    record_audit(db, 'CARD_ACCOUNT', link.id, 'UPDATE', performed_by=current_user, before_state=before, after_state=after,\n"
                    "                 change_summary=f'Updated card account link {link.id}')\n"
                    "    db.commit()\n"
                    "    db.refresh(link)\n"
                    "    acct = link.account\n"
                    "    return {\n"
                    "        'id': link.id,\n"
                    "        'card_id': link.card_id,\n"
                    "        'account_id': link.account_id,\n"
                    "        'account_number': acct.account_number if acct else None,\n"
                    "        'account_type': acct.account_type if acct else None,\n"
                    "        'currency': link.currency,\n"
                    "        'available_balance': float(acct.available_balance) if acct else 0.0,\n"
                    "        'account_role': link.account_role,\n"
                    "        'priority': link.priority,\n"
                    "        'status': link.status,\n"
                    "    }\n\n\n"
                    "@router.delete('/cards/accounts/{link_id}')\n"
                    "def unlink_account_from_card(link_id: str, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):\n"
                    "    link = db.query(CardAccount).filter(CardAccount.id == link_id).first()\n"
                    "    if not link:\n"
                    "        raise HTTPException(status_code=404, detail='Card account link not found')\n"
                    "    remaining = db.query(CardAccount).filter(CardAccount.card_id == link.card_id).count()\n"
                    "    if remaining <= 1:\n"
                    "        raise HTTPException(status_code=400, detail='Cannot unlink the only account from a card. A card must have at least one linked account.')\n"
                    "    before = serialize_entity(link)\n"
                    "    db.delete(link)\n"
                    "    record_audit(db, 'CARD_ACCOUNT', link_id, 'DELETE', performed_by=current_user, before_state=before,\n"
                    "                 change_summary=f'Unlinked account {link.account_id} from card {link.card_id}')\n"
                    "    db.commit()\n"
                    "    return {'status': 'deleted', 'link_id': link_id}\n\n"
                ),
            },
        ],
    )

    # 3. Patch backend/app/host_engine.py to select target account using DE3 digits 3-4
    session.patch_file(
        "backend/app/host_engine.py",
        [
            {
                "marker": "step04:host_engine_de3_account_selection",
                "action": "replace",
                "anchor": (
                    "        card_acct = (\n"
                    "            self.db.query(CardAccount)\n"
                    "            .filter(CardAccount.card_id == card.id, CardAccount.status == \"ACTIVE\")\n"
                    "            .order_by(CardAccount.priority.asc())\n"
                    "            .first()\n"
                    "        )\n"
                    "        account_id = card_acct.account_id if card_acct else card.linked_account_id"
                ),
                "text": (
                    "        # Step 4: Multi-Account Resolution via DE3 Processing Code (Digits 3-4 = From Account Type)\n"
                    "        # 01 = Checking / Current, 11 = Savings, 31 = Credit, 00 = Default Primary\n"
                    "        from_acct_type = proc_code[3:5] if len(proc_code) >= 5 else '00'\n"
                    "        acct_type_target = None\n"
                    "        if from_acct_type in ('01', '02', '20'):\n"
                    "            acct_type_target = 'CURRENT'\n"
                    "        elif from_acct_type in ('10', '11'):\n"
                    "            acct_type_target = 'SAVINGS'\n"
                    "        elif from_acct_type in ('30', '31'):\n"
                    "            acct_type_target = 'CREDIT'\n\n"
                    "        active_card_accts = (\n"
                    "            self.db.query(CardAccount)\n"
                    "            .filter(CardAccount.card_id == card.id, CardAccount.status == 'ACTIVE')\n"
                    "            .order_by(CardAccount.priority.asc())\n"
                    "            .all()\n"
                    "        )\n\n"
                    "        selected_card_acct = None\n"
                    "        if acct_type_target and active_card_accts:\n"
                    "            for ca in active_card_accts:\n"
                    "                if ca.account and ca.account.account_type == acct_type_target:\n"
                    "                    selected_card_acct = ca\n"
                    "                    break\n\n"
                    "        if not selected_card_acct and active_card_accts:\n"
                    "            selected_card_acct = active_card_accts[0]\n\n"
                    "        account_id = selected_card_acct.account_id if selected_card_acct else card.linked_account_id"
                ),
            }
        ],
    )

    # 4. Patch frontend/src/pages/BankingEntities.tsx to add Multi-Account Modal in CardsPage
    session.patch_file(
        "frontend/src/pages/BankingEntities.tsx",
        [
            {
                "marker": "step04:cards_multi_account_state",
                "action": "insert_after",
                "anchor": "  const [institutions, setInstitutions] = useState<any[]>([]);",
                "text": (
                    "  const [selectedCardForAccts, setSelectedCardForAccts] = useState<any | null>(null);\n"
                    "  const [cardAccounts, setCardAccounts] = useState<any[]>([]);\n"
                    "  const [newLinkAccountId, setNewLinkAccountId] = useState('');\n"
                    "  const [newLinkRole, setNewLinkRole] = useState('SECONDARY');"
                ),
            },
            {
                "marker": "step04:cards_multi_account_handlers",
                "action": "insert_before",
                "anchor": "  return (",
                "text": (
                    "  const openAccountManager = async (c: any) => {\n"
                    "    setSelectedCardForAccts(c);\n"
                    "    const links = await apiFetch(`/cards/${c.id}/accounts`);\n"
                    "    setCardAccounts(links);\n"
                    "    if (accounts.length > 0) setNewLinkAccountId(accounts[0].id);\n"
                    "  };\n\n"
                    "  const handleLinkAccount = async () => {\n"
                    "    if (!selectedCardForAccts || !newLinkAccountId) return;\n"
                    "    try {\n"
                    "      await apiFetch(`/cards/${selectedCardForAccts.id}/accounts`, {\n"
                    "        method: 'POST',\n"
                    "        body: JSON.stringify({\n"
                    "          account_id: newLinkAccountId,\n"
                    "          account_role: newLinkRole,\n"
                    "          priority: cardAccounts.length + 1,\n"
                    "        }),\n"
                    "      });\n"
                    "      const links = await apiFetch(`/cards/${selectedCardForAccts.id}/accounts`);\n"
                    "      setCardAccounts(links);\n"
                    "    } catch (err: any) {\n"
                    "      alert(err.message);\n"
                    "    }\n"
                    "  };\n\n"
                    "  const handleSetPrimary = async (linkId: string) => {\n"
                    "    try {\n"
                    "      await apiFetch(`/cards/accounts/${linkId}`, {\n"
                    "        method: 'PUT',\n"
                    "        body: JSON.stringify({ account_role: 'PRIMARY', priority: 1 }),\n"
                    "      });\n"
                    "      const links = await apiFetch(`/cards/${selectedCardForAccts.id}/accounts`);\n"
                    "      setCardAccounts(links);\n"
                    "    } catch (err: any) {\n"
                    "      alert(err.message);\n"
                    "    }\n"
                    "  };\n\n"
                    "  const handleUnlink = async (linkId: string) => {\n"
                    "    if (!confirm('Unlink this account from the card?')) return;\n"
                    "    try {\n"
                    "      await apiFetch(`/cards/accounts/${linkId}`, { method: 'DELETE' });\n"
                    "      const links = await apiFetch(`/cards/${selectedCardForAccts.id}/accounts`);\n"
                    "      setCardAccounts(links);\n"
                    "    } catch (err: any) {\n"
                    "      alert(err.message);\n"
                    "    }\n"
                    "  };\n"
                ),
            },
            # Add "Manage Accounts" button in Cards table
            {
                "marker": "step04:cards_table_manage_accounts_btn",
                "action": "insert_after",
                "anchor": (
                    '                    onClick={() => toggleCardStatus(c)}\n'
                    '                    className="text-sky-500 hover:underline text-[11px]"\n'
                    '                  >\n'
                    '                    {c.card_status === \'ACTIVE\' ? \'Block Card\' : \'Activate\'}\n'
                    '                  </button>'
                ),
                "text": (
                    '\n                  <button\n'
                    '                    onClick={() => openAccountManager(c)}\n'
                    '                    className="text-amber-500 hover:underline text-[11px] ml-2.5"\n'
                    '                  >\n'
                    '                    Linked Accts\n'
                    '                  </button>'
                ),
            },
            # Render Multi-Account Modal in CardsPage
            {
                "marker": "step04:render_multi_account_modal",
                "action": "insert_before",
                "anchor": "      <form\n        onSubmit={handleIssue}",
                "text": (
                    '      {selectedCardForAccts && (\n'
                    '        <div className="fixed inset-0 bg-black/60 flex items-center justify-center p-4 z-50">\n'
                    '          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-6 max-w-xl w-full space-y-4 shadow-2xl">\n'
                    '            <div className="flex justify-between items-center border-b border-slate-200 dark:border-slate-800 pb-3">\n'
                    '              <div>\n'
                    '                <h2 className="text-sm font-bold">Multi-Account Manager</h2>\n'
                    '                <div className="text-xs font-mono text-emerald-500">Card: {selectedCardForAccts.masked_pan}</div>\n'
                    '              </div>\n'
                    '              <button onClick={() => setSelectedCardForAccts(null)} className="text-slate-400 hover:text-white text-lg">×</button>\n'
                    '            </div>\n'
                    '            <div className="space-y-2 max-h-56 overflow-y-auto">\n'
                    '              {cardAccounts.map((l) => (\n'
                    '                <div key={l.id} className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 flex justify-between items-center text-xs font-mono bg-slate-50 dark:bg-slate-950">\n'
                    '                  <div>\n'
                    '                    <span className="font-bold text-sky-400">{l.account_number}</span> ({l.account_type}) · Avl: {l.available_balance.toLocaleString()} {l.currency}\n'
                    '                    <div className="text-[10px] text-slate-400">Priority: {l.priority} | Role: <span className={l.account_role === "PRIMARY" ? "text-emerald-400 font-bold" : "text-slate-300"}>{l.account_role}</span></div>\n'
                    '                  </div>\n'
                    '                  <div className="flex items-center gap-2">\n'
                    '                    {l.account_role !== "PRIMARY" && (\n'
                    '                      <button onClick={() => handleSetPrimary(l.id)} className="text-emerald-500 hover:underline text-[11px]">Set Primary</button>\n'
                    '                    )}\n'
                    '                    <button onClick={() => handleUnlink(l.id)} className="text-rose-500 hover:underline text-[11px]">Unlink</button>\n'
                    '                  </div>\n'
                    '                </div>\n'
                    '              ))}\n'
                    '            </div>\n'
                    '            <div className="pt-3 border-t border-slate-200 dark:border-slate-800 flex gap-2">\n'
                    '              <select value={newLinkAccountId} onChange={(e) => setNewLinkAccountId(e.target.value)} className="flex-1 bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5 text-xs font-mono">\n'
                    '                {accounts.map((a) => (\n'
                    '                  <option key={a.id} value={a.id}>ACCT {a.account_number} ({a.account_type}) — {a.customer_name}</option>\n'
                    '                ))}\n'
                    '              </select>\n'
                    '              <select value={newLinkRole} onChange={(e) => setNewLinkRole(e.target.value)} className="w-32 bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5 text-xs font-mono">\n'
                    '                <option value="SECONDARY">SECONDARY</option>\n'
                    '                <option value="PRIMARY">PRIMARY</option>\n'
                    '              </select>\n'
                    '              <button onClick={handleLinkAccount} className="bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-1.5 rounded text-xs font-semibold">+ Link Account</button>\n'
                    '            </div>\n'
                    '          </div>\n'
                    '        </div>\n'
                    '      )}\n'
                ),
            },
        ],
    )

    # 5. Write automated pytest test suite backend/tests/test_step04_multi_account.py
    session.write_file("backend/tests/test_step04_multi_account.py", TEST_STEP04_CODE)

    session.record_progress(
        completed=[
            "Added `CardAccountLinkCreate`, `CardAccountLinkUpdate`, and `CardAccountLinkOut` schemas in `backend/app/schemas.py`.",
            "Added REST endpoints for listing, linking, setting primary, and unlinking card accounts in `backend/app/api_routes.py`.",
            "Updated `HostTransactionProcessor` in `backend/app/host_engine.py` to route authorizations based on `DE3` digits 3-4 (`01` Current, `11` Savings, `31` Credit).",
            "Added interactive Multi-Account management modal in `frontend/src/pages/BankingEntities.tsx`.",
            "Added automated Pytest test suite `backend/tests/test_step04_multi_account.py`.",
        ],
        remaining=[
            "STEP 5 — Advanced Search and Pagination (server-side search, filtering, and pagination across Cards, Customers, Accounts, and Transaction Journal).",
        ],
        modified_files=[
            "backend/app/schemas.py",
            "backend/app/api_routes.py",
            "backend/app/host_engine.py",
            "frontend/src/pages/BankingEntities.tsx",
            "backend/tests/test_step04_multi_account.py",
        ],
    )

    session.record_contracts(
        section_title="Step 4 — Card & Account Multi-Linking Public Contracts",
        contract_items=[
            "**GET /api/cards/{card_id}/accounts**: Lists all linked accounts for a card with role and priority.",
            "**POST /api/cards/{card_id}/accounts**: Links an additional account to a card (designating as PRIMARY or SECONDARY).",
            "**PUT /api/cards/accounts/{link_id}**: Updates account role (e.g. promoting to PRIMARY) and priority.",
            "**DELETE /api/cards/accounts/{link_id}**: Unlinks account (preventing unlinking if only 1 account remains).",
            "**DE3 Account Selection**: `HostTransactionProcessor` evaluates `DE3` digits 3-4 to debit from `SAVINGS` (`11`), `CURRENT` (`01`), or fallback to `PRIMARY` account.",
        ],
    )

    return session.finish()


if __name__ == "__main__":
    sys.exit(main())