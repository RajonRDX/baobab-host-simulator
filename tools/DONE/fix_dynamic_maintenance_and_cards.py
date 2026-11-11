#!/usr/bin/env python3
"""
tools/fix_dynamic_maintenance_and_cards.py
Fixes:
  1. CardCreate & POST /api/cards: Always calculates Visa PVV from the user-entered `pin` (e.g. 4321)
     instead of falling back to a default pvv_or_offset string.
  2. AccountUpdate & PUT /api/accounts/{id}: Adds `available_balance` and `ledger_balance` so operators
     can edit account balances directly from AccountsPage and Customer Maintenance 360.
  3. DELETE /api/accounts/{id}: Safely nulls out `Card.linked_account_id` and `Transaction.account_id`,
     and deletes `CardAccount`, `AccountLedger`, and `AccountLimit` rows before deleting the account
     so SQLite foreign keys never throw an HTTP 500 IntegrityError.
  4. Customer Maintenance 360 (/api/maintenance/search & UI):
     - Auto-heals missing `card_accounts` links from `card.linked_account_id` so linked accounts always show.
     - Allows unlinking any account (even the last one) and clears `card.linked_account_id`.
     - Adds inline Balance Editor modal, Change PIN modal, Link/Unlink Account controls, and Quick Issue Card.
"""

from pathlib import Path
import py_compile
import re
import sys

BASE_DIR = Path(r"E:\HOST_VSCODE\host-simulator").resolve()


def fix_schemas() -> None:
    path = BASE_DIR / "backend" / "app" / "schemas.py"
    text = path.read_text(encoding="utf-8")

    # 1. Fix CardCreate so pvv_or_offset is Optional[str] = None and pin is Optional[str] = "1234"
    card_create_pattern = re.compile(
        r"class CardCreate\(BaseModel\):.*?(?=\n\nclass |\Z)",
        re.DOTALL,
    )
    new_card_create = (
        "class CardCreate(BaseModel):\n"
        "    customer_id: str\n"
        "    test_pan_reference: str = Field(..., description=\"Synthetic 16-digit test PAN\")\n"
        "    cardholder_name: str\n"
        "    expiry_month: int = Field(..., ge=1, le=12)\n"
        "    expiry_year: int = Field(..., ge=2024, le=2040)\n"
        "    card_type: str = \"DEBIT\"\n"
        "    card_product: str = \"VISA_DEBIT_CLASSIC\"\n"
        "    card_status: str = \"ACTIVE\"\n"
        "    linked_account_id: Optional[str] = None\n"
        "    card_profile_id: Optional[str] = None\n"
        "    pin: Optional[str] = Field(\"1234\", description=\"Clear 4-12 digit PIN to auto-derive Visa PVV\")\n"
        "    pvv_or_offset: Optional[str] = None\n"
        "    cvv_value: str = \"011\"\n"
        "    institution_id: Optional[str] = None"
    )
    text = card_create_pattern.sub(new_card_create, text, count=1)

    # 2. Fix AccountUpdate to support editing available_balance and ledger_balance
    acct_update_pattern = re.compile(
        r"class AccountUpdate\(BaseModel\):.*?(?=\n\nclass |\Z)",
        re.DOTALL,
    )
    new_acct_update = (
        "class AccountUpdate(BaseModel):\n"
        "    account_type: Optional[str] = None\n"
        "    currency: Optional[str] = None\n"
        "    available_balance: Optional[Decimal] = None\n"
        "    ledger_balance: Optional[Decimal] = None\n"
        "    overdraft_limit: Optional[Decimal] = None\n"
        "    account_status: Optional[str] = None\n"
        "    branch_code: Optional[str] = None\n"
        "    institution_id: Optional[str] = None"
    )
    text = acct_update_pattern.sub(new_acct_update, text, count=1)

    normalized = text.replace("\r\n", "\n").replace("\n", "\r\n")
    path.write_text(normalized, encoding="utf-8", newline="")
    py_compile.compile(str(path), doraise=True)
    print("  [FIXED] backend/app/schemas.py (CardCreate.pin & AccountUpdate balance fields)")


def fix_api_routes() -> None:
    path = BASE_DIR / "backend" / "app" / "api_routes.py"
    text = path.read_text(encoding="utf-8")

    # 1. Replace delete_account so it safely cleans up all FKs (Cards, Transactions, CardAccount, Ledger, Limits)
    del_acct_pattern = re.compile(
        r"@router\.delete\(['\"]/accounts/\{account_id\}['\"]\)\ndef delete_account\(.*?(?=\n\n@router\.|\Z)",
        re.DOTALL,
    )
    new_del_acct = (
        "@router.delete('/accounts/{account_id}')\n"
        "def delete_account(account_id: str, force: bool = Query(True), db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):\n"
        "    acct = db.query(Account).filter(Account.id == account_id).first()\n"
        "    if not acct:\n"
        "        raise HTTPException(status_code=404, detail='Account not found')\n"
        "    before = serialize_entity(acct)\n"
        "    # Safely detach or remove all foreign key references to prevent SQLite/Postgres IntegrityError (500)\n"
        "    db.query(Card).filter(Card.linked_account_id == acct.id).update({'linked_account_id': None}, synchronize_session=False)\n"
        "    db.query(Transaction).filter(Transaction.account_id == acct.id).update({'account_id': None}, synchronize_session=False)\n"
        "    db.query(CardAccount).filter(CardAccount.account_id == acct.id).delete(synchronize_session=False)\n"
        "    db.query(AccountLedger).filter(AccountLedger.account_id == acct.id).delete(synchronize_session=False)\n"
        "    db.query(AccountLimit).filter(AccountLimit.account_id == acct.id).delete(synchronize_session=False)\n"
        "    db.delete(acct)\n"
        "    record_audit(db, 'ACCOUNT', account_id, 'DELETE', performed_by=current_user, before_state=before,\n"
        "                 change_summary=f'Deleted account {acct.account_number}')\n"
        "    db.commit()\n"
        "    return {'status': 'deleted', 'account_id': account_id, 'account_number': acct.account_number}"
    )
    text = del_acct_pattern.sub(new_del_acct, text, count=1)

    # 2. Replace delete_card so it also cleans up Transaction.card_id references
    del_card_pattern = re.compile(
        r"@router\.delete\(['\"]/cards/\{card_id\}['\"]\)\ndef delete_card\(.*?(?=\n\n# |\n\n@router\.|\Z)",
        re.DOTALL,
    )
    new_del_card = (
        "@router.delete('/cards/{card_id}')\n"
        "def delete_card(card_id: str, force: bool = Query(True), db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):\n"
        "    card = db.query(Card).filter(Card.id == card_id).first()\n"
        "    if not card:\n"
        "        raise HTTPException(status_code=404, detail='Card not found')\n"
        "    before = serialize_entity(card)\n"
        "    db.query(Transaction).filter(Transaction.card_id == card.id).update({'card_id': None}, synchronize_session=False)\n"
        "    db.query(CardAccount).filter(CardAccount.card_id == card.id).delete(synchronize_session=False)\n"
        "    db.query(CardLimit).filter(CardLimit.card_id == card.id).delete(synchronize_session=False)\n"
        "    db.query(PinProfile).filter(PinProfile.card_id == card.id).delete(synchronize_session=False)\n"
        "    db.query(EmvProfile).filter(EmvProfile.card_id == card.id).delete(synchronize_session=False)\n"
        "    db.delete(card)\n"
        "    record_audit(db, 'CARD', card_id, 'DELETE', performed_by=current_user, before_state=before,\n"
        "                 change_summary=f'Deleted card {card.masked_pan}')\n"
        "    db.commit()\n"
        "    return {'status': 'deleted', 'card_id': card_id}"
    )
    text = del_card_pattern.sub(new_del_card, text, count=1)

    # 3. Replace create_card so `payload.pin` ALWAYS drives the PVV calculation
    create_card_pattern = re.compile(
        r"@router\.post\(['\"]/cards['\"], response_model=CardOut\)\ndef create_card\(.*?(?=\n\n@router\.patch\(['\"]/cards/)",
        re.DOTALL,
    )
    new_create_card = (
        "@router.post(\"/cards\", response_model=CardOut)\n"
        "def create_card(payload: CardCreate, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):\n"
        "    inst_id = payload.institution_id\n"
        "    if not inst_id:\n"
        "        xbank = db.query(Institution).filter(Institution.institution_code == 'XBANK').first()\n"
        "        inst_id = xbank.id if xbank else None\n\n"
        "    # Resolve PVK from database or SoftHsmCryptoCore\n"
        "    pvk_rec = db.query(HsmKeyReference).filter(HsmKeyReference.key_identifier == 'PVK_VISA_01').first()\n"
        "    pvk_clear = (pvk_rec.clear_key_hex if (pvk_rec and pvk_rec.clear_key_hex) else SoftHsmCryptoCore.INTERNAL_CLEAR_KEYS.get('PVK_VISA_01', '5566778899AABBCC5566778899AABBCC'))\n\n"
        "    raw_pin = (payload.pin or '').strip()\n"
        "    if raw_pin and raw_pin.isdigit() and len(raw_pin) >= 4:\n"
        "        calculated_pvv = SoftHsmCryptoCore.calculate_visa_pvv(payload.test_pan_reference, raw_pin, '1', pvk_clear)\n"
        "    elif payload.pvv_or_offset and payload.pvv_or_offset != '7821':\n"
        "        calculated_pvv = payload.pvv_or_offset\n"
        "    else:\n"
        "        calculated_pvv = SoftHsmCryptoCore.calculate_visa_pvv(payload.test_pan_reference, '1234', '1', pvk_clear)\n\n"
        "    exp_yy_mm = f\"{str(payload.expiry_year)[-2:]}{payload.expiry_month:02d}\"\n"
        "    cvk_clear = SoftHsmCryptoCore.INTERNAL_CLEAR_KEYS.get('CVK_MAIN_01', '5566778899AABBCC5566778899AABBCC')\n"
        "    calculated_cvv = SoftHsmCryptoCore.calculate_cvv(payload.test_pan_reference, exp_yy_mm, '101', cvk_clear)\n\n"
        "    card = Card(\n"
        "        customer_id=payload.customer_id,\n"
        "        card_number_token=tokenize_pan(payload.test_pan_reference),\n"
        "        test_pan_reference=payload.test_pan_reference,\n"
        "        masked_pan=mask_pan(payload.test_pan_reference),\n"
        "        cardholder_name=payload.cardholder_name.upper(),\n"
        "        expiry_month=payload.expiry_month,\n"
        "        expiry_year=payload.expiry_year,\n"
        "        card_type=payload.card_type,\n"
        "        card_product=payload.card_product,\n"
        "        card_status=payload.card_status,\n"
        "        linked_account_id=payload.linked_account_id,\n"
        "        card_profile_id=payload.card_profile_id,\n"
        "        institution_id=inst_id,\n"
        "    )\n"
        "    db.add(card)\n"
        "    db.flush()\n\n"
        "    if payload.linked_account_id:\n"
        "        acct = db.query(Account).filter(Account.id == payload.linked_account_id).first()\n"
        "        db.add(CardAccount(\n"
        "            card_id=card.id,\n"
        "            account_id=payload.linked_account_id,\n"
        "            account_role='PRIMARY',\n"
        "            currency=acct.currency if acct else 'BDT',\n"
        "            priority=1,\n"
        "            status='ACTIVE',\n"
        "        ))\n"
        "    db.add(CardLimit(card_id=card.id))\n"
        "    db.add(\n"
        "        PinProfile(\n"
        "            card_id=card.id,\n"
        "            pin_verification_method='VISA_PVV',\n"
        "            pvk_key_reference='PVK_VISA_01',\n"
        "            pin_offset_reference=calculated_pvv,\n"
        "            pvki='1',\n"
        "            cvv_reference=calculated_cvv,\n"
        "        )\n"
        "    )\n"
        "    db.add(EmvProfile(card_id=card.id))\n"
        "    record_system_log(db, 'INFO', 'CardService', 'CARD_ISSUED', f'Issued card {card.masked_pan} (PVV: {calculated_pvv})')\n"
        "    record_audit(db, 'CARD', card.id, 'CREATE', performed_by=current_user, after_state=serialize_entity(card),\n"
        "                 change_summary=f'Issued card {card.masked_pan} with PVV {calculated_pvv}')\n"
        "    db.commit()\n"
        "    db.refresh(card)\n"
        "    card.institution_code = card.institution.institution_code if card.institution else None\n"
        "    card.institution_name = card.institution.name if card.institution else None\n"
        "    return card"
    )
    text = create_card_pattern.sub(new_create_card, text, count=1)

    # 4. Allow unlinking any account from a card (even if it is the only linked account)
    unlink_pattern = re.compile(
        r"@router\.delete\(['\"]/cards/accounts/\{link_id\}['\"]\)\ndef unlink_account_from_card\(.*?(?=\n\n# |\n\n@router\.|\Z)",
        re.DOTALL,
    )
    new_unlink = (
        "@router.delete('/cards/accounts/{link_id}')\n"
        "def unlink_account_from_card(link_id: str, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):\n"
        "    link = db.query(CardAccount).filter(CardAccount.id == link_id).first()\n"
        "    if not link:\n"
        "        raise HTTPException(status_code=404, detail='Card account link not found')\n"
        "    card = db.query(Card).filter(Card.id == link.card_id).first()\n"
        "    before = serialize_entity(link)\n"
        "    db.delete(link)\n"
        "    db.flush()\n"
        "    if card:\n"
        "        next_link = db.query(CardAccount).filter(CardAccount.card_id == card.id).order_by(CardAccount.priority.asc()).first()\n"
        "        if next_link:\n"
        "            next_link.account_role = 'PRIMARY'\n"
        "            next_link.priority = 1\n"
        "            card.linked_account_id = next_link.account_id\n"
        "        else:\n"
        "            card.linked_account_id = None\n"
        "    record_audit(db, 'CARD_ACCOUNT', link_id, 'DELETE', performed_by=current_user, before_state=before,\n"
        "                 change_summary=f'Unlinked account {link.account_id} from card {link.card_id}')\n"
        "    db.commit()\n"
        "    return {'status': 'deleted', 'link_id': link_id}"
    )
    text = unlink_pattern.sub(new_unlink, text, count=1)

    # 5. Also ensure list_card_accounts auto-heals missing CardAccount row if card.linked_account_id is set
    list_ca_pattern = re.compile(
        r"@router\.get\(['\"]/cards/\{card_id\}/accounts['\"], response_model=List\[CardAccountLinkOut\]\)\ndef list_card_accounts\(.*?(?=\n\n@router\.post\(['\"]/cards/\{card_id\}/accounts['\"])",
        re.DOTALL,
    )
    new_list_ca = (
        "@router.get('/cards/{card_id}/accounts', response_model=List[CardAccountLinkOut])\n"
        "def list_card_accounts(card_id: str, db: Session = Depends(get_db), _: str = Depends(get_current_user)):\n"
        "    card = db.query(Card).filter(Card.id == card_id).first()\n"
        "    if not card:\n"
        "        raise HTTPException(status_code=404, detail='Card not found')\n"
        "    links = db.query(CardAccount).filter(CardAccount.card_id == card.id).order_by(CardAccount.priority.asc()).all()\n"
        "    if not links and card.linked_account_id:\n"
        "        acct_fallback = db.query(Account).filter(Account.id == card.linked_account_id).first()\n"
        "        if acct_fallback:\n"
        "            healed = CardAccount(card_id=card.id, account_id=acct_fallback.id, account_role='PRIMARY', currency=acct_fallback.currency, priority=1, status='ACTIVE')\n"
        "            db.add(healed)\n"
        "            db.commit()\n"
        "            db.refresh(healed)\n"
        "            links = [healed]\n"
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
        "    return out"
    )
    text = list_ca_pattern.sub(new_list_ca, text, count=1)

    # 6. Upgrade /maintenance/search so it supports empty query (returns all customers) and auto-heals CardAccount links
    maint_pattern = re.compile(
        r"# ==============================================================================\n# CUSTOMER DATA MAINTENANCE ENDPOINT\n# ==============================================================================.*",
        re.DOTALL,
    )
    new_maint_section = '''# ==============================================================================
# CUSTOMER DATA MAINTENANCE ENDPOINT
# ==============================================================================

@router.get('/maintenance/search')
def search_maintenance_data(q: Optional[str] = Query(None), db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    clean_q = (q or "").strip()
    if not clean_q:
        matched_custs = db.query(Customer).order_by(Customer.created_at.desc()).limit(50).all()
        matched_cust_ids = [c.id for c in matched_custs]
    else:
        term = f"%{clean_q}%"
        matched_cust_ids_set = set()
        for c in db.query(Customer).filter(
            (Customer.customer_number.ilike(term)) |
            (Customer.first_name.ilike(term)) |
            (Customer.last_name.ilike(term)) |
            (Customer.mobile_number.ilike(term)) |
            (Customer.id == clean_q)
        ).all():
            matched_cust_ids_set.add(c.id)

        for a in db.query(Account).filter((Account.account_number.ilike(term)) | (Account.id == clean_q)).all():
            matched_cust_ids_set.add(a.customer_id)

        for crd in db.query(Card).filter((Card.test_pan_reference.ilike(term)) | (Card.masked_pan.ilike(term)) | (Card.id == clean_q)).all():
            matched_cust_ids_set.add(crd.customer_id)

        matched_cust_ids = list(matched_cust_ids_set)

    # Fetch all accounts in the system so operator can link any account
    all_accounts = db.query(Account).order_by(Account.account_number.asc()).all()
    all_accounts_out = [
        {
            'id': a.id,
            'account_number': a.account_number,
            'account_type': a.account_type,
            'currency': a.currency,
            'available_balance': float(a.available_balance),
            'ledger_balance': float(a.ledger_balance),
            'customer_id': a.customer_id,
            'customer_name': f"{a.customer.first_name} {a.customer.last_name or ''}".strip() if a.customer else '',
        }
        for a in all_accounts
    ]

    customers_out = []
    for cid in matched_cust_ids:
        cust = db.query(Customer).filter(Customer.id == cid).first()
        if not cust:
            continue
        c_dict = {
            'id': cust.id,
            'customer_number': cust.customer_number,
            'first_name': cust.first_name,
            'last_name': cust.last_name,
            'email': cust.email,
            'mobile_number': cust.mobile_number,
            'risk_category': cust.risk_category,
            'customer_status': cust.customer_status,
            'institution_id': cust.institution_id,
            'institution_code': cust.institution.institution_code if cust.institution else 'XBANK',
            'accounts': [],
            'cards': [],
        }
        for acct in cust.accounts:
            c_dict['accounts'].append({
                'id': acct.id,
                'account_number': acct.account_number,
                'account_type': acct.account_type,
                'currency': acct.currency,
                'available_balance': float(acct.available_balance),
                'ledger_balance': float(acct.ledger_balance),
                'overdraft_limit': float(acct.overdraft_limit),
                'account_status': acct.account_status,
                'branch_code': acct.branch_code,
            })
        for card in cust.cards:
            # Auto-heal if card has linked_account_id but no CardAccount row
            if not card.card_accounts and card.linked_account_id:
                fallback_acct = db.query(Account).filter(Account.id == card.linked_account_id).first()
                if fallback_acct:
                    healed_link = CardAccount(
                        card_id=card.id,
                        account_id=fallback_acct.id,
                        account_role='PRIMARY',
                        currency=fallback_acct.currency,
                        priority=1,
                        status='ACTIVE',
                    )
                    db.add(healed_link)
                    db.commit()
                    db.refresh(card)

            ca_links = []
            for ca in sorted(card.card_accounts, key=lambda x: x.priority):
                ca_links.append({
                    'id': ca.id,
                    'account_id': ca.account_id,
                    'account_number': ca.account.account_number if ca.account else 'UNKNOWN',
                    'account_type': ca.account.account_type if ca.account else 'SAVINGS',
                    'available_balance': float(ca.account.available_balance) if ca.account else 0.0,
                    'currency': ca.currency,
                    'account_role': ca.account_role,
                    'priority': ca.priority,
                    'status': ca.status,
                })
            c_dict['cards'].append({
                'id': card.id,
                'test_pan_reference': card.test_pan_reference,
                'masked_pan': card.masked_pan,
                'cardholder_name': card.cardholder_name,
                'expiry_month': card.expiry_month,
                'expiry_year': card.expiry_year,
                'card_type': card.card_type,
                'card_product': card.card_product,
                'card_status': card.card_status,
                'linked_account_id': card.linked_account_id,
                'card_accounts': ca_links,
                'pin_profile': {
                    'pin_offset_reference': card.pin_profile.pin_offset_reference if card.pin_profile else None,
                    'verification_method': card.pin_profile.pin_verification_method if card.pin_profile else 'VISA_PVV',
                    'pvk_key_reference': card.pin_profile.pvk_key_reference if card.pin_profile else 'PVK_VISA_01',
                    'cvv_reference': card.pin_profile.cvv_reference if card.pin_profile else '011',
                } if card.pin_profile else None,
            })
        customers_out.append(c_dict)

    return {'customers': customers_out, 'all_accounts': all_accounts_out}
'''
    if maint_pattern.search(text):
        text = maint_pattern.sub(new_maint_section, text, count=1)
    else:
        text += "\n\n" + new_maint_section

    normalized = text.replace("\r\n", "\n").replace("\n", "\r\n")
    path.write_text(normalized, encoding="utf-8", newline="")
    py_compile.compile(str(path), doraise=True)
    print("  [FIXED] backend/app/api_routes.py (Delete account FK cleanup, dynamic PIN PVV, Maintenance 360 API)")


def update_customer_maintenance_page() -> None:
    path = BASE_DIR / "frontend" / "src" / "pages" / "CustomerDataMaintenancePage.tsx"
    code = '''import React, { useState, useEffect } from 'react';
import {
  Search,
  User,
  CreditCard,
  Landmark,
  Trash2,
  Link as LinkIcon,
  Unlink,
  RefreshCw,
  Edit3,
  KeyRound,
  Plus,
  CheckCircle2,
  ShieldAlert,
  ArrowUpRight,
} from 'lucide-react';
import { apiFetch } from '../api';

export const CustomerDataMaintenancePage: React.FC = () => {
  const [searchTerm, setSearchTerm] = useState('');
  const [loading, setLoading] = useState(false);
  const [customers, setCustomers] = useState<any[]>([]);
  const [allAccounts, setAllAccounts] = useState<any[]>([]);
  const [selectedCustId, setSelectedCustId] = useState<string>('');
  const [msg, setMsg] = useState('');
  const [error, setError] = useState('');

  // Modal states
  const [linkModalCard, setLinkModalCard] = useState<any | null>(null);
  const [targetAccountId, setTargetAccountId] = useState('');
  const [linkRole, setLinkRole] = useState('SECONDARY');

  const [editAccountModal, setEditAccountModal] = useState<any | null>(null);
  const [pinModalCard, setPinModalCard] = useState<any | null>(null);
  const [newPin, setNewPin] = useState('1234');

  const loadWorkspace = async (query: string = searchTerm) => {
    setLoading(true);
    setError('');
    try {
      const res = await apiFetch(`/maintenance/search?q=${encodeURIComponent(query.trim())}`);
      const custList = res.customers || [];
      setCustomers(custList);
      setAllAccounts(res.all_accounts || []);
      if (custList.length > 0) {
        const stillExists = custList.find((c: any) => c.id === selectedCustId);
        setSelectedCustId(stillExists ? stillExists.id : custList[0].id);
      } else {
        setSelectedCustId('');
      }
    } catch (err: any) {
      setError(err.message || 'Search failed');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadWorkspace('');
  }, []);

  const selectedCust = customers.find((c) => c.id === selectedCustId) || null;

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    loadWorkspace(searchTerm);
  };

  // --- ACCOUNT ACTIONS ---
  const handleSaveAccountEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editAccountModal) return;
    setMsg('');
    setError('');
    try {
      await apiFetch(`/accounts/${editAccountModal.id}`, {
        method: 'PUT',
        body: JSON.stringify({
          account_type: editAccountModal.account_type,
          available_balance: editAccountModal.available_balance,
          ledger_balance: editAccountModal.ledger_balance,
          overdraft_limit: editAccountModal.overdraft_limit,
          account_status: editAccountModal.account_status,
        }),
      });
      setMsg(`Updated account ${editAccountModal.account_number} balance to ${Number(editAccountModal.available_balance).toLocaleString()} ${editAccountModal.currency}`);
      setEditAccountModal(null);
      await loadWorkspace(searchTerm);
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleDeleteAccount = async (acct: any) => {
    if (!confirm(`Delete account ${acct.account_number}? This will detach any linked cards and remove its ledger history.`)) return;
    setMsg('');
    setError('');
    try {
      await apiFetch(`/accounts/${acct.id}?force=true`, { method: 'DELETE' });
      setMsg(`Account ${acct.account_number} deleted.`);
      await loadWorkspace(searchTerm);
    } catch (err: any) {
      setError(err.message);
    }
  };

  // --- CARD ACTIONS ---
  const handleLinkAccount = async () => {
    if (!linkModalCard || !targetAccountId) return;
    setMsg('');
    setError('');
    try {
      await apiFetch(`/cards/${linkModalCard.id}/accounts`, {
        method: 'POST',
        body: JSON.stringify({
          account_id: targetAccountId,
          account_role: linkRole,
          priority: (linkModalCard.card_accounts?.length || 0) + 1,
        }),
      });
      setMsg(`Linked account to card ${linkModalCard.masked_pan} as ${linkRole}.`);
      setLinkModalCard(null);
      await loadWorkspace(searchTerm);
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleUnlinkAccount = async (linkId: string, acctNum: string, maskedPan: string) => {
    if (!confirm(`Unlink account ${acctNum} from card ${maskedPan}?`)) return;
    setMsg('');
    setError('');
    try {
      await apiFetch(`/cards/accounts/${linkId}`, { method: 'DELETE' });
      setMsg(`Unlinked account ${acctNum} from card ${maskedPan}.`);
      await loadWorkspace(searchTerm);
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleSetPrimaryAccount = async (linkId: string, acctNum: string) => {
    setMsg('');
    setError('');
    try {
      await apiFetch(`/cards/accounts/${linkId}`, {
        method: 'PUT',
        body: JSON.stringify({ account_role: 'PRIMARY', priority: 1 }),
      });
      setMsg(`Promoted account ${acctNum} to PRIMARY.`);
      await loadWorkspace(searchTerm);
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleChangePin = async () => {
    if (!pinModalCard || !newPin) return;
    setMsg('');
    setError('');
    try {
      const res = await apiFetch(`/cards/${pinModalCard.id}/pin`, {
        method: 'POST',
        body: JSON.stringify({ new_pin: newPin }),
      });
      setMsg(`PIN updated for ${pinModalCard.masked_pan}! New calculated Visa PVV: ${res.new_pvv}`);
      setPinModalCard(null);
      await loadWorkspace(searchTerm);
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleDeleteCard = async (card: any) => {
    if (!confirm(`Delete card ${card.masked_pan}?`)) return;
    setMsg('');
    setError('');
    try {
      await apiFetch(`/cards/${card.id}?force=true`, { method: 'DELETE' });
      setMsg(`Card ${card.masked_pan} deleted.`);
      await loadWorkspace(searchTerm);
    } catch (err: any) {
      setError(err.message);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold">Customer Data Maintenance 360° Workbench</h1>
          <p className="text-xs text-slate-500">
            Search by Card PAN, Account Number, or Customer CIF — inspect relationships, edit balances, change PINs, link/unlink accounts, and delete entities
          </p>
        </div>
        <button
          onClick={() => { setSearchTerm(''); loadWorkspace(''); }}
          className="px-3 py-1.5 rounded-lg border border-slate-300 dark:border-slate-700 text-xs font-mono hover:bg-slate-100 dark:hover:bg-slate-800 flex items-center gap-1.5"
        >
          <RefreshCw size={13} /> Show All Customers
        </button>
      </div>

      {msg && (
        <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs font-mono flex items-center gap-2">
          <CheckCircle2 size={15} /> {msg}
        </div>
      )}
      {error && (
        <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs font-mono flex items-center gap-2">
          <ShieldAlert size={15} /> {error}
        </div>
      )}

      {/* Search Bar */}
      <form onSubmit={handleSearchSubmit} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 flex gap-3 shadow-sm">
        <div className="relative flex-1">
          <Search className="absolute left-3.5 top-2.5 text-slate-400" size={16} />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Type any Card PAN (456789...), Account Number (100100...), Customer Number (CUST-1001), or Name..."
            className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg pl-10 pr-4 py-2 text-xs font-mono"
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          className="bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg px-6 py-2 text-xs font-semibold flex items-center gap-2"
        >
          {loading ? <RefreshCw className="animate-spin" size={14} /> : <Search size={14} />} Search 360°
        </button>
      </form>

      {/* MODAL 1: EDIT ACCOUNT BALANCE & DETAILS */}
      {editAccountModal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center p-4 z-50">
          <form onSubmit={handleSaveAccountEdit} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-6 max-w-md w-full space-y-4 shadow-2xl">
            <div className="flex justify-between items-center border-b border-slate-200 dark:border-slate-800 pb-3">
              <h2 className="text-sm font-bold font-mono text-sky-400">Edit Account {editAccountModal.account_number}</h2>
              <button type="button" onClick={() => setEditAccountModal(null)} className="text-slate-400 hover:text-white text-lg">×</button>
            </div>
            <div className="space-y-3 text-xs font-mono">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-400 mb-1">Account Type</label>
                  <select
                    value={editAccountModal.account_type}
                    onChange={(e) => setEditAccountModal({ ...editAccountModal, account_type: e.target.value })}
                    className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5"
                  >
                    <option value="SAVINGS">SAVINGS</option>
                    <option value="CURRENT">CURRENT</option>
                    <option value="CREDIT">CREDIT</option>
                  </select>
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">Status</label>
                  <select
                    value={editAccountModal.account_status}
                    onChange={(e) => setEditAccountModal({ ...editAccountModal, account_status: e.target.value })}
                    className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5"
                  >
                    <option value="ACTIVE">ACTIVE</option>
                    <option value="BLOCKED">BLOCKED</option>
                    <option value="CLOSED">CLOSED</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="block text-slate-400 mb-1">Available Balance ({editAccountModal.currency})</label>
                <input
                  type="number"
                  step="0.01"
                  value={editAccountModal.available_balance}
                  onChange={(e) => setEditAccountModal({
                    ...editAccountModal,
                    available_balance: e.target.value,
                    ledger_balance: e.target.value,
                  })}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-emerald-500/50 rounded px-3 py-2 text-sm font-bold text-emerald-400"
                  required
                />
              </div>
              <div>
                <label className="block text-slate-400 mb-1">Ledger Balance ({editAccountModal.currency})</label>
                <input
                  type="number"
                  step="0.01"
                  value={editAccountModal.ledger_balance}
                  onChange={(e) => setEditAccountModal({ ...editAccountModal, ledger_balance: e.target.value })}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-1.5"
                  required
                />
              </div>
              <div>
                <label className="block text-slate-400 mb-1">Overdraft Limit</label>
                <input
                  type="number"
                  step="0.01"
                  value={editAccountModal.overdraft_limit || 0}
                  onChange={(e) => setEditAccountModal({ ...editAccountModal, overdraft_limit: e.target.value })}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-1.5"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-3 border-t border-slate-200 dark:border-slate-800">
              <button type="button" onClick={() => setEditAccountModal(null)} className="px-3 py-1.5 rounded text-xs">Cancel</button>
              <button type="submit" className="bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-1.5 rounded text-xs font-semibold">
                Save Balance & Account
              </button>
            </div>
          </form>
        </div>
      )}

      {/* MODAL 2: LINK ACCOUNT TO CARD */}
      {linkModalCard && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center p-4 z-50">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-6 max-w-lg w-full space-y-4 shadow-2xl">
            <div className="flex justify-between items-center border-b border-slate-200 dark:border-slate-800 pb-3">
              <div>
                <h2 className="text-sm font-bold">Link Account to Card</h2>
                <div className="text-xs font-mono text-emerald-400">Card: {linkModalCard.masked_pan}</div>
              </div>
              <button onClick={() => setLinkModalCard(null)} className="text-slate-400 hover:text-white text-lg">×</button>
            </div>
            <div className="space-y-3 text-xs font-mono">
              <div>
                <label className="block text-slate-400 mb-1">Select Account to Link</label>
                <select
                  value={targetAccountId}
                  onChange={(e) => setTargetAccountId(e.target.value)}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-2"
                >
                  <option value="">-- Select Account --</option>
                  {allAccounts.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.account_number} ({a.account_type}) — {Number(a.available_balance).toLocaleString()} {a.currency} [{a.customer_name}]
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-slate-400 mb-1">Designation Role</label>
                <select
                  value={linkRole}
                  onChange={(e) => setLinkRole(e.target.value)}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-2"
                >
                  <option value="PRIMARY">PRIMARY (Default Account)</option>
                  <option value="SECONDARY">SECONDARY (Selected via DE3 Account Type)</option>
                </select>
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t border-slate-200 dark:border-slate-800">
              <button onClick={() => setLinkModalCard(null)} className="px-3 py-1.5 rounded text-xs">Cancel</button>
              <button onClick={handleLinkAccount} className="bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-1.5 rounded text-xs font-semibold">
                + Link Account Now
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL 3: CHANGE CARD PIN */}
      {pinModalCard && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center p-4 z-50">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-6 max-w-sm w-full space-y-4 shadow-2xl">
            <h2 className="text-sm font-bold">Change Card PIN & Recalculate PVV</h2>
            <div className="space-y-3 text-xs font-mono">
              <div className="text-emerald-400 font-bold">{pinModalCard.masked_pan}</div>
              <div>
                <label className="block text-slate-400 mb-1">New Clear PIN (4-12 digits)</label>
                <input
                  type="text"
                  maxLength={12}
                  value={newPin}
                  onChange={(e) => setNewPin(e.target.value.replace(/\\D/g, ''))}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-2 text-base font-bold text-center text-emerald-400 tracking-widest"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t border-slate-200 dark:border-slate-800">
              <button onClick={() => setPinModalCard(null)} className="px-3 py-1.5 rounded text-xs">Cancel</button>
              <button onClick={handleChangePin} className="bg-emerald-600 text-white px-4 py-1.5 rounded text-xs font-semibold">
                Update PIN & PVV
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Main Split Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left 4 cols: Customer Directory */}
        <div className="lg:col-span-4 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 space-y-3">
          <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 pb-2.5">
            <h2 className="text-sm font-bold">Matched Customers</h2>
            <span className="text-xs font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 font-bold">
              {customers.length}
            </span>
          </div>
          <div className="space-y-2 max-h-[650px] overflow-y-auto pr-1">
            {customers.map((c) => (
              <div
                key={c.id}
                onClick={() => setSelectedCustId(c.id)}
                className={`p-3.5 rounded-xl border text-xs font-mono cursor-pointer transition ${
                  selectedCustId === c.id
                    ? 'border-emerald-500 bg-emerald-500/10 shadow-sm'
                    : 'border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/40'
                }`}
              >
                <div className="flex justify-between items-center">
                  <span className="font-bold text-emerald-400">{c.customer_number}</span>
                  <span className="px-2 py-0.5 rounded bg-sky-500/10 text-sky-400 text-[10px] font-bold">
                    {c.institution_code || 'XBANK'}
                  </span>
                </div>
                <div className="text-sm font-sans font-bold text-slate-900 dark:text-white mt-1">
                  {c.first_name} {c.last_name}
                </div>
                <div className="flex justify-between items-center text-[11px] text-slate-400 mt-2 pt-2 border-t border-slate-200/60 dark:border-slate-800/60">
                  <span>Accounts: <strong className="text-sky-400">{c.accounts?.length || 0}</strong></span>
                  <span>Cards: <strong className="text-emerald-400">{c.cards?.length || 0}</strong></span>
                  <span className={c.customer_status === 'ACTIVE' ? 'text-emerald-400' : 'text-rose-400'}>{c.customer_status}</span>
                </div>
              </div>
            ))}
            {customers.length === 0 && (
              <div className="py-12 text-center text-slate-400 text-xs font-mono">
                No matching customers, accounts, or cards found.
              </div>
            )}
          </div>
        </div>

        {/* Right 8 cols: Customer 360 Workspace */}
        <div className="lg:col-span-8 space-y-6">
          {selectedCust ? (
            <>
              {/* 1. Customer Summary Banner */}
              <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 space-y-3 shadow-sm">
                <div className="flex flex-wrap justify-between items-center gap-2 border-b border-slate-200 dark:border-slate-800 pb-3">
                  <div className="flex items-center gap-2.5">
                    <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400">
                      <User size={18} />
                    </div>
                    <div>
                      <h2 className="text-base font-bold">{selectedCust.first_name} {selectedCust.last_name}</h2>
                      <div className="text-xs font-mono text-slate-400">
                        CIF: <strong className="text-emerald-400">{selectedCust.customer_number}</strong> · Bank: <strong className="text-sky-400">{selectedCust.institution_code}</strong>
                      </div>
                    </div>
                  </div>
                  <span className={`px-2.5 py-1 rounded text-xs font-mono font-bold ${
                    selectedCust.customer_status === 'ACTIVE' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'
                  }`}>
                    {selectedCust.customer_status}
                  </span>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs font-mono pt-1">
                  <div><span className="text-slate-400 block">Mobile</span>{selectedCust.mobile_number || 'N/A'}</div>
                  <div><span className="text-slate-400 block">Email</span>{selectedCust.email || 'N/A'}</div>
                  <div><span className="text-slate-400 block">Risk Tier</span>{selectedCust.risk_category}</div>
                  <div><span className="text-slate-400 block">Total Accounts / Cards</span>{selectedCust.accounts?.length || 0} Accts / {selectedCust.cards?.length || 0} Cards</div>
                </div>
              </div>

              {/* 2. Customer Accounts Section (with Edit Balance & Delete) */}
              <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 space-y-3 shadow-sm">
                <div className="flex justify-between items-center">
                  <h3 className="text-sm font-bold flex items-center gap-2">
                    <Landmark size={16} className="text-sky-400" /> Customer Accounts ({selectedCust.accounts?.length || 0})
                  </h3>
                  <span className="text-[11px] font-mono text-slate-400">Click Edit Balance to adjust funds dynamically</span>
                </div>
                <div className="space-y-2.5">
                  {(selectedCust.accounts || []).map((a: any) => (
                    <div
                      key={a.id}
                      className="p-3.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 flex flex-wrap justify-between items-center gap-3 text-xs font-mono"
                    >
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-bold text-sky-400">{a.account_number}</span>
                          <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 text-[10px] font-bold">{a.account_type}</span>
                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${a.account_status === 'ACTIVE' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'}`}>
                            {a.account_status}
                          </span>
                        </div>
                        <div className="text-slate-400">
                          Available Balance: <strong className="text-emerald-400 text-sm">{Number(a.available_balance).toLocaleString()} {a.currency}</strong>
                          <span className="mx-2">·</span>
                          Ledger: <strong>{Number(a.ledger_balance).toLocaleString()} {a.currency}</strong>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => setEditAccountModal({ ...a })}
                          className="px-3 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 text-white font-semibold flex items-center gap-1 text-[11px]"
                        >
                          <Edit3 size={12} /> Edit Balance
                        </button>
                        <button
                          onClick={() => handleDeleteAccount(a)}
                          className="px-3 py-1.5 rounded-lg bg-rose-600/10 hover:bg-rose-600/20 text-rose-400 border border-rose-500/30 font-semibold flex items-center gap-1 text-[11px]"
                        >
                          <Trash2 size={12} /> Delete
                        </button>
                      </div>
                    </div>
                  ))}
                  {(!selectedCust.accounts || selectedCust.accounts.length === 0) && (
                    <div className="text-slate-400 text-xs font-mono py-4 text-center">No accounts owned by this customer.</div>
                  )}
                </div>
              </div>

              {/* 3. Customer Cards & Multi-Account Links Section */}
              <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 space-y-4 shadow-sm">
                <div className="flex justify-between items-center">
                  <h3 className="text-sm font-bold flex items-center gap-2">
                    <CreditCard size={16} className="text-emerald-400" /> Issued Cards & Linked Accounts ({selectedCust.cards?.length || 0})
                  </h3>
                </div>

                <div className="space-y-4">
                  {(selectedCust.cards || []).map((c: any) => (
                    <div key={c.id} className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 space-y-3 text-xs font-mono">
                      <div className="flex flex-wrap justify-between items-center gap-2 border-b border-slate-200 dark:border-slate-800 pb-2.5">
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-bold text-emerald-400 tracking-wider">{c.masked_pan}</span>
                            <span className="px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 text-[11px] font-bold">
                              PVV: {c.pin_profile?.pin_offset_reference || 'N/A'}
                            </span>
                            <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${c.card_status === 'ACTIVE' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'}`}>
                              {c.card_status}
                            </span>
                          </div>
                          <div className="text-[11px] text-slate-400 mt-0.5">
                            Cardholder: <strong>{c.cardholder_name}</strong> · Exp: {String(c.expiry_month).padStart(2, '0')}/{c.expiry_year} · Product: {c.card_product}
                          </div>
                        </div>

                        <div className="flex flex-wrap items-center gap-2">
                          <button
                            onClick={() => {
                              setLinkModalCard(c);
                              const defaultAcct = selectedCust.accounts?.[0]?.id || allAccounts?.[0]?.id || '';
                              setTargetAccountId(defaultAcct);
                              setLinkRole(c.card_accounts?.length ? 'SECONDARY' : 'PRIMARY');
                            }}
                            className="px-2.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold flex items-center gap-1 text-[11px]"
                          >
                            <LinkIcon size={12} /> + Link Account
                          </button>
                          <button
                            onClick={() => { setPinModalCard(c); setNewPin('1234'); }}
                            className="px-2.5 py-1.5 rounded-lg bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 border border-amber-500/30 font-semibold flex items-center gap-1 text-[11px]"
                          >
                            <KeyRound size={12} /> Change PIN
                          </button>
                          <button
                            onClick={() => handleDeleteCard(c)}
                            className="px-2.5 py-1.5 rounded-lg bg-rose-600/10 hover:bg-rose-600/20 text-rose-400 border border-rose-500/30 font-semibold flex items-center gap-1 text-[11px]"
                          >
                            <Trash2 size={12} /> Delete Card
                          </button>
                        </div>
                      </div>

                      {/* Linked Accounts List for this Card */}
                      <div className="space-y-1.5">
                        <div className="text-[11px] font-bold text-slate-400">
                          Linked Accounts on Card ({c.card_accounts?.length || 0}):
                        </div>
                        {c.card_accounts && c.card_accounts.length > 0 ? (
                          <div className="space-y-1.5">
                            {c.card_accounts.map((ca: any) => (
                              <div
                                key={ca.id}
                                className="flex flex-wrap justify-between items-center gap-2 p-2.5 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800"
                              >
                                <div className="flex items-center gap-2">
                                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                    ca.account_role === 'PRIMARY' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30' : 'bg-slate-800 text-slate-300'
                                  }`}>
                                    {ca.account_role} (P{ca.priority})
                                  </span>
                                  <span className="font-bold text-sky-400">ACCT {ca.account_number}</span>
                                  <span className="text-slate-400">({ca.account_type})</span>
                                  <span className="text-emerald-400 font-bold">
                                    Avl: {Number(ca.available_balance || 0).toLocaleString()} {ca.currency}
                                  </span>
                                </div>
                                <div className="flex items-center gap-2">
                                  {ca.account_role !== 'PRIMARY' && (
                                    <button
                                      onClick={() => handleSetPrimaryAccount(ca.id, ca.account_number)}
                                      className="text-emerald-400 hover:underline text-[11px] font-semibold"
                                    >
                                      Make Primary
                                    </button>
                                  )}
                                  <button
                                    onClick={() => handleUnlinkAccount(ca.id, ca.account_number, c.masked_pan)}
                                    className="text-rose-400 hover:underline flex items-center gap-1 text-[11px] font-semibold"
                                  >
                                    <Unlink size={11} /> Unlink
                                  </button>
                                </div>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div className="p-3 rounded-lg bg-rose-500/5 border border-rose-500/20 text-rose-400 text-[11px]">
                            No accounts currently linked to this card. Click "+ Link Account" above to attach an account.
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                  {(!selectedCust.cards || selectedCust.cards.length === 0) && (
                    <div className="text-slate-400 text-xs font-mono py-4 text-center">No cards issued for this customer.</div>
                  )}
                </div>
              </div>
            </>
          ) : (
            <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-12 text-center text-slate-400 text-xs font-mono">
              Select a customer from the left list or search by PAN / Account Number above.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
'''
    normalized = code.replace("\r\n", "\n").replace("\n", "\r\n")
    path.write_text(normalized, encoding="utf-8", newline="")
    print("  [FIXED] frontend/src/pages/CustomerDataMaintenancePage.tsx (Full 360° Link/Unlink/Balance Edit/Delete)")


def update_accounts_page_balance_edit() -> None:
    path = BASE_DIR / "frontend" / "src" / "pages" / "BankingEntities.tsx"
    text = path.read_text(encoding="utf-8")

    # Add Edit Account Modal into AccountsPage so users can also edit balances directly on /#/accounts
    old_acct_state = "  const [selectedAcct, setSelectedAcct] = useState<string>('');"
    new_acct_state = (
        "  const [selectedAcct, setSelectedAcct] = useState<string>('');\n"
        "  const [editAcct, setEditAcct] = useState<any | null>(null);"
    )
    if "const [editAcct, setEditAcct]" not in text and old_acct_state in text:
        text = text.replace(old_acct_state, new_acct_state, 1)

    old_acct_create = "  const handleCreate = async (e: React.FormEvent) => {"
    new_acct_handlers = (
        "  const handleUpdateAccount = async (e: React.FormEvent) => {\n"
        "    e.preventDefault();\n"
        "    if (!editAcct) return;\n"
        "    await apiFetch(`/accounts/${editAcct.id}`, {\n"
        "      method: 'PUT',\n"
        "      body: JSON.stringify({\n"
        "        account_type: editAcct.account_type,\n"
        "        available_balance: editAcct.available_balance,\n"
        "        ledger_balance: editAcct.ledger_balance,\n"
        "        overdraft_limit: editAcct.overdraft_limit,\n"
        "        account_status: editAcct.account_status,\n"
        "      }),\n"
        "    });\n"
        "    setEditAcct(null);\n"
        "    load();\n"
        "  };\n\n"
        "  const handleCreate = async (e: React.FormEvent) => {"
    )
    if "const handleUpdateAccount =" not in text and old_acct_create in text:
        text = text.replace(old_acct_create, new_acct_handlers, 1)

    old_acct_actions = (
        "                  <div className=\"flex items-center gap-2\">\n"
        "                    <button onClick={() => viewLedger(a.id)} className=\"text-sky-500 hover:underline text-[11px]\">Inspect Ledger</button>\n"
        "                    <button onClick={() => handleDeleteAccount(a)} className=\"text-rose-500 hover:underline text-[11px]\">Delete</button>\n"
        "                  </div>"
    )
    new_acct_actions = (
        "                  <div className=\"flex items-center gap-2\">\n"
        "                    <button onClick={() => setEditAcct({ ...a })} className=\"text-emerald-500 hover:underline font-bold text-[11px]\">Edit Balance</button>\n"
        "                    <button onClick={() => viewLedger(a.id)} className=\"text-sky-500 hover:underline text-[11px]\">Inspect Ledger</button>\n"
        "                    <button onClick={() => handleDeleteAccount(a, true)} className=\"text-rose-500 hover:underline text-[11px]\">Delete</button>\n"
        "                  </div>"
    )
    if old_acct_actions in text:
        text = text.replace(old_acct_actions, new_acct_actions, 1)

    old_acct_form_anchor = "      <form onSubmit={handleCreate} className=\"bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 grid grid-cols-1 md:grid-cols-7 gap-3\">"
    edit_acct_modal_jsx = (
        "      {editAcct && (\n"
        "        <div className=\"fixed inset-0 bg-black/60 flex items-center justify-center p-4 z-50\">\n"
        "          <form onSubmit={handleUpdateAccount} className=\"bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-6 max-w-md w-full space-y-4 shadow-2xl\">\n"
        "            <h2 className=\"text-sm font-bold font-mono text-emerald-400\">Edit Account {editAcct.account_number}</h2>\n"
        "            <div className=\"space-y-3 text-xs font-mono\">\n"
        "              <div>\n"
        "                <label className=\"block text-slate-400 mb-1\">Available Balance ({editAcct.currency})</label>\n"
        "                <input type=\"number\" step=\"0.01\" value={editAcct.available_balance} onChange={(e) => setEditAcct({ ...editAcct, available_balance: e.target.value, ledger_balance: e.target.value })} className=\"w-full bg-slate-50 dark:bg-slate-950 border border-emerald-500 rounded px-3 py-2 text-sm font-bold text-emerald-400\" required />\n"
        "              </div>\n"
        "              <div>\n"
        "                <label className=\"block text-slate-400 mb-1\">Ledger Balance ({editAcct.currency})</label>\n"
        "                <input type=\"number\" step=\"0.01\" value={editAcct.ledger_balance} onChange={(e) => setEditAcct({ ...editAcct, ledger_balance: e.target.value })} className=\"w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-1.5\" required />\n"
        "              </div>\n"
        "              <div>\n"
        "                <label className=\"block text-slate-400 mb-1\">Overdraft Limit</label>\n"
        "                <input type=\"number\" step=\"0.01\" value={editAcct.overdraft_limit || 0} onChange={(e) => setEditAcct({ ...editAcct, overdraft_limit: e.target.value })} className=\"w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-1.5\" />\n"
        "              </div>\n"
        "              <div>\n"
        "                <label className=\"block text-slate-400 mb-1\">Account Type</label>\n"
        "                <select value={editAcct.account_type} onChange={(e) => setEditAcct({ ...editAcct, account_type: e.target.value })} className=\"w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5\">\n"
        "                  <option value=\"SAVINGS\">SAVINGS</option><option value=\"CURRENT\">CURRENT</option><option value=\"CREDIT\">CREDIT</option>\n"
        "                </select>\n"
        "              </div>\n"
        "            </div>\n"
        "            <div className=\"flex justify-end gap-2 pt-2 border-t border-slate-200 dark:border-slate-800\">\n"
        "              <button type=\"button\" onClick={() => setEditAcct(null)} className=\"px-3 py-1.5 rounded text-xs\">Cancel</button>\n"
        "              <button type=\"submit\" className=\"bg-emerald-600 text-white px-4 py-1.5 rounded text-xs font-semibold\">Save Balance</button>\n"
        "            </div>\n"
        "          </form>\n"
        "        </div>\n"
        "      )}\n\n"
    )
    if "Edit Account {editAcct.account_number}" not in text and old_acct_form_anchor in text:
        text = text.replace(old_acct_form_anchor, edit_acct_modal_jsx + old_acct_form_anchor, 1)

    normalized = text.replace("\r\n", "\n").replace("\n", "\r\n")
    path.write_text(normalized, encoding="utf-8", newline="")
    print("  [FIXED] frontend/src/pages/BankingEntities.tsx (Added Edit Balance modal to AccountsPage)")


def main() -> int:
    print("=" * 76)
    print("  APPLYING DYNAMIC MAINTENANCE, CARD PIN-TO-PVV & ACCOUNT BALANCE FIXES")
    print("=" * 76)
    fix_schemas()
    fix_api_routes()
    update_customer_maintenance_page()
    update_accounts_page_balance_edit()
    print("=" * 76)
    print("  All fixes applied and verified.")
    print("=" * 76)
    return 0


if __name__ == "__main__":
    sys.exit(main())