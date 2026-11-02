#!/usr/bin/env python3
"""
tools/repair_all_pending.py
One-shot automated repair script to resolve all ambiguous anchors and pending patches
from Steps 02_01, 02_02, 03_03, 04, 05, and 11.
"""

from pathlib import Path
import re
import sys

BASE_DIR = Path(r"E:\HOST_VSCODE\host-simulator").resolve()
sys.path.insert(0, str(BASE_DIR))

from tools.patcher import PatcherSession, parse_installer_args


def main() -> int:
    args = parse_installer_args("Comprehensive Repair for Steps 2, 3, 4, 5, 11")
    session = PatcherSession(
        step_id="repair_all",
        title="Repair Anchors for Schemas, Host Engine, Models, BankingEntities, and Simulator",
        dry_run=args.dry_run,
    )

    # --------------------------------------------------------------------------
    # 1. FIX backend/app/schemas.py (Step 02_01: CustomerOut institution attributes)
    # --------------------------------------------------------------------------
    session.patch_file(
        "backend/app/schemas.py",
        [
            {
                "marker": "step02_01:schema_customer_out_inst_fixed",
                "action": "replace",
                "anchor": (
                    "class CustomerOut(CustomerCreate):\n"
                    "    id: str\n"
                    "    created_at: datetime\n"
                    "    updated_at: datetime\n"
                    "    model_config = ConfigDict(from_attributes=True)"
                ),
                "text": (
                    "class CustomerOut(CustomerCreate):\n"
                    "    id: str\n"
                    "    institution_code: Optional[str] = None\n"
                    "    institution_name: Optional[str] = None\n"
                    "    created_at: datetime\n"
                    "    updated_at: datetime\n"
                    "    model_config = ConfigDict(from_attributes=True)"
                ),
            }
        ],
    )

    # --------------------------------------------------------------------------
    # 2. FIX backend/app/models.py (Step 11: NetworkProfile simulation columns)
    # --------------------------------------------------------------------------
    session.patch_file(
        "backend/app/models.py",
        [
            {
                "marker": "step11:network_profile_simulation_cols_fixed",
                "action": "replace",
                "anchor": (
                    "class NetworkProfile(Base):\n"
                    '    __tablename__ = "network_profiles"\n\n'
                    "    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)\n"
                    "    network_name: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)\n"
                    '    network_type: Mapped[str] = mapped_column(String(30), nullable=False, default="INTERNAL_SIMULATION")\n'
                    "    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)\n"
                    "    configuration_json: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)"
                ),
                "text": (
                    "class NetworkProfile(Base):\n"
                    '    __tablename__ = "network_profiles"\n\n'
                    "    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)\n"
                    "    network_name: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)\n"
                    '    network_type: Mapped[str] = mapped_column(String(30), nullable=False, default="INTERNAL_SIMULATION")\n'
                    "    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)\n"
                    '    simulation_mode: Mapped[str] = mapped_column(String(30), nullable=False, default="ALWAYS_APPROVE")\n'
                    '    simulated_response_code: Mapped[str] = mapped_column(String(5), nullable=False, default="00")\n'
                    "    simulated_delay_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)\n"
                    "    configuration_json: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)"
                ),
            }
        ],
    )

    # --------------------------------------------------------------------------
    # 3. FIX backend/app/host_engine.py (Step 02_01: Transaction model assignment)
    # --------------------------------------------------------------------------
    session.patch_file(
        "backend/app/host_engine.py",
        [
            {
                "marker": "step02_01:tx_model_assign_inst_fixed",
                "action": "replace",
                "anchor": (
                    "            authorization_status=\"APPROVED\" if approved else \"DECLINED\",\n"
                    "            source_channel=source_channel,\n"
                    "            original_transaction_id=original_tx.id if original_tx else None,"
                ),
                "text": (
                    "            authorization_status=\"APPROVED\" if approved else \"DECLINED\",\n"
                    "            source_channel=source_channel,\n"
                    "            issuer_institution_id=issuer_institution_id or (card.institution_id if card else None),\n"
                    "            acquirer_institution_id=acquirer_institution_id,\n"
                    "            ps_code=ps_code,\n"
                    "            is_on_us=(issuer_institution_id == acquirer_institution_id) if (issuer_institution_id and acquirer_institution_id) else True,\n"
                    "            original_transaction_id=original_tx.id if original_tx else None,"
                ),
            }
        ],
    )

    # --------------------------------------------------------------------------
    # 4. FIX backend/app/api_routes.py (Step 05: Paginated Accounts endpoint)
    # --------------------------------------------------------------------------
    api_routes_path = BASE_DIR / "backend" / "app" / "api_routes.py"
    api_content = api_routes_path.read_text(encoding="utf-8")

    # If list_accounts does not yet have pagination arguments, patch it safely
    if "def list_accounts(" in api_content and "page: int = Query(" not in api_content.split("def list_accounts(")[1].split("def ")[0]:
        session.patch_file(
            "backend/app/api_routes.py",
            [
                {
                    "marker": "step05:api_accounts_paginated_fixed",
                    "action": "replace",
                    "anchor": (
                        "@router.get(\"/accounts\")\n"
                        "def list_accounts(db: Session = Depends(get_db), _: str = Depends(get_current_user)):"
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
                        "        query = query.filter(Account.account_status == status.upper())\n"
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
                        "    return {'items': out, 'total': total, 'page': page, 'page_size': page_size, 'total_pages': total_pages}\n"
                        "def _unused_old_list_accounts():"
                    ),
                }
            ],
        )

    # --------------------------------------------------------------------------
    # 5. RE-WRITE frontend/src/pages/BankingEntities.tsx Cleanly
    # (Consolidates Step 02_02 bank badges, Step 03_03 edit/delete modals,
    #  Step 04 multi-account modal, and Step 05 pagination)
    # --------------------------------------------------------------------------
    banking_entities_complete = '''import React, { useEffect, useState } from 'react';
import { apiFetch } from '../api';

// ============================================================================
// PAGE 2: CUSTOMERS (CIF)
// ============================================================================
export const CustomersPage: React.FC = () => {
  const [customers, setCustomers] = useState<any[]>([]);
  const [institutions, setInstitutions] = useState<any[]>([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [searchTerm, setSearchTerm] = useState('');
  const [editCust, setEditCust] = useState<any | null>(null);
  const [errorBanner, setErrorBanner] = useState('');

  const [form, setForm] = useState({
    customer_number: `CUST-${Math.floor(1006 + Math.random() * 9000)}`,
    first_name: '',
    last_name: '',
    email: '',
    mobile_number: '+8801700000099',
    address: 'Dhaka, Bangladesh',
    customer_status: 'ACTIVE',
    risk_category: 'NORMAL',
    institution_id: '',
  });

  const load = async () => {
    try {
      const q = searchTerm ? `&q=${encodeURIComponent(searchTerm)}` : '';
      const [cRes, iList] = await Promise.all([
        apiFetch(`/customers?page=${page}&page_size=15${q}`),
        apiFetch('/institutions'),
      ]);
      setCustomers(cRes.items || cRes);
      setTotalCount(cRes.total || (cRes.items ? cRes.items.length : cRes.length));
      setTotalPages(cRes.total_pages || 1);
      setInstitutions(iList);
      if (!form.institution_id && iList.length > 0) {
        setForm((prev) => ({ ...prev, institution_id: iList[0].id }));
      }
    } catch (err: any) {
      console.error(err);
    }
  };

  useEffect(() => {
    load();
  }, [page]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await apiFetch('/customers', { method: 'POST', body: JSON.stringify(form) });
      setForm({
        ...form,
        customer_number: `CUST-${Math.floor(1006 + Math.random() * 9000)}`,
        first_name: '',
        last_name: '',
      });
      load();
    } catch (err: any) {
      setErrorBanner(err.message);
    }
  };

  const handleUpdateCustomer = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorBanner('');
    try {
      await apiFetch(`/customers/${editCust.id}`, { method: 'PUT', body: JSON.stringify(editCust) });
      setEditCust(null);
      load();
    } catch (err: any) {
      setErrorBanner(err.message);
    }
  };

  const handleDeleteCustomer = async (c: any, force: boolean = false) => {
    setErrorBanner('');
    if (!force && !confirm(`Are you sure you want to delete customer ${c.customer_number}?`)) return;
    try {
      await apiFetch(`/customers/${c.id}${force ? '?force=true' : ''}`, { method: 'DELETE' });
      load();
    } catch (err: any) {
      if (err.message.includes('409') || err.message.toLowerCase().includes('cannot delete')) {
        if (confirm(`${err.message}\\n\\nDo you want to FORCE delete this customer for lab testing?`)) {
          handleDeleteCustomer(c, true);
        }
      } else {
        setErrorBanner(err.message);
      }
    }
  };

  const toggleStatus = async (c: any) => {
    const next = c.customer_status === 'ACTIVE' ? 'BLOCKED' : 'ACTIVE';
    await apiFetch(`/customers/${c.id}/status?status=${next}`, { method: 'PATCH' });
    load();
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold">Customer Management (CIF)</h1>
        <p className="text-xs text-slate-500">Create, manage, and audit synthetic banking host customers across member banks</p>
      </div>

      {errorBanner && (
        <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs font-mono">
          {errorBanner}
        </div>
      )}

      {editCust && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center p-4 z-50">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-6 max-w-md w-full space-y-4 shadow-2xl">
            <h2 className="text-sm font-bold">Edit Customer {editCust.customer_number}</h2>
            <div className="space-y-3 text-xs font-mono">
              <div>
                <label className="block text-slate-400 mb-1">First Name</label>
                <input value={editCust.first_name} onChange={(e) => setEditCust({ ...editCust, first_name: e.target.value })} className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5" />
              </div>
              <div>
                <label className="block text-slate-400 mb-1">Last Name</label>
                <input value={editCust.last_name || ''} onChange={(e) => setEditCust({ ...editCust, last_name: e.target.value })} className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5" />
              </div>
              <div>
                <label className="block text-slate-400 mb-1">Email</label>
                <input value={editCust.email || ''} onChange={(e) => setEditCust({ ...editCust, email: e.target.value })} className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5" />
              </div>
              <div>
                <label className="block text-slate-400 mb-1">Risk Category</label>
                <select value={editCust.risk_category} onChange={(e) => setEditCust({ ...editCust, risk_category: e.target.value })} className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5">
                  <option value="NORMAL">NORMAL</option><option value="VIP">VIP</option><option value="HIGH">HIGH</option>
                </select>
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t border-slate-200 dark:border-slate-800">
              <button onClick={() => setEditCust(null)} className="px-3 py-1.5 rounded text-xs">Cancel</button>
              <button onClick={handleUpdateCustomer} className="bg-emerald-600 text-white px-4 py-1.5 rounded text-xs font-semibold">Save Changes</button>
            </div>
          </div>
        </div>
      )}

      <form onSubmit={handleCreate} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 grid grid-cols-1 md:grid-cols-7 gap-3">
        <input
          value={form.customer_number}
          onChange={(e) => setForm({ ...form, customer_number: e.target.value })}
          placeholder="Customer Number"
          className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono"
          required
        />
        <select
          value={form.institution_id}
          onChange={(e) => setForm({ ...form, institution_id: e.target.value })}
          className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono"
        >
          {institutions.map((inst) => (
            <option key={inst.id} value={inst.id}>{inst.institution_code} — {inst.short_name || inst.name}</option>
          ))}
        </select>
        <input
          value={form.first_name}
          onChange={(e) => setForm({ ...form, first_name: e.target.value })}
          placeholder="First Name"
          className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs"
          required
        />
        <input
          value={form.last_name}
          onChange={(e) => setForm({ ...form, last_name: e.target.value })}
          placeholder="Last Name"
          className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs"
        />
        <input
          value={form.mobile_number}
          onChange={(e) => setForm({ ...form, mobile_number: e.target.value })}
          placeholder="Mobile"
          className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono"
        />
        <select
          value={form.risk_category}
          onChange={(e) => setForm({ ...form, risk_category: e.target.value })}
          className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono"
        >
          <option value="NORMAL">RISK: NORMAL</option>
          <option value="VIP">RISK: VIP</option>
          <option value="HIGH">RISK: HIGH</option>
        </select>
        <button type="submit" className="bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg px-4 py-2 text-xs font-semibold">
          + Create Customer
        </button>
      </form>

      <div className="flex flex-wrap items-center justify-between gap-3 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4">
        <div className="flex items-center gap-2 flex-1 max-w-md">
          <input
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search customer no, name, phone, or email..."
            className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-1.5 text-xs font-mono"
          />
          <button onClick={() => { setPage(1); load(); }} className="bg-emerald-600 text-white px-3 py-1.5 rounded-lg text-xs font-semibold">Search</button>
        </div>
        <div className="flex items-center gap-2 text-xs font-mono text-slate-400">
          <span>Total: <strong className="text-emerald-500">{totalCount}</strong></span>
          <button disabled={page <= 1} onClick={() => setPage(page - 1)} className="px-2.5 py-1 rounded border border-slate-300 dark:border-slate-700 disabled:opacity-40">Prev</button>
          <span>Page {page} of {totalPages}</span>
          <button disabled={page >= totalPages} onClick={() => setPage(page + 1)} className="px-2.5 py-1 rounded border border-slate-300 dark:border-slate-700 disabled:opacity-40">Next</button>
        </div>
      </div>

      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 overflow-x-auto">
        <table className="w-full text-left text-xs font-mono">
          <thead>
            <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-400">
              <th className="py-2.5">Customer No</th>
              <th className="py-2.5">Bank</th>
              <th className="py-2.5">Full Name</th>
              <th className="py-2.5">Mobile</th>
              <th className="py-2.5">Risk</th>
              <th className="py-2.5">Status</th>
              <th className="py-2.5">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200/60 dark:divide-slate-800/60">
            {customers.map((c) => (
              <tr key={c.id}>
                <td className="py-2.5 font-bold text-emerald-500">{c.customer_number}</td>
                <td className="py-2.5 text-sky-400 font-bold">{c.institution_code || 'XBANK'}</td>
                <td className="py-2.5 font-sans font-medium">{c.first_name} {c.last_name}</td>
                <td className="py-2.5">{c.mobile_number}</td>
                <td className="py-2.5">{c.risk_category}</td>
                <td className="py-2.5">
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${c.customer_status === 'ACTIVE' ? 'bg-emerald-500/10 text-emerald-500' : 'bg-rose-500/10 text-rose-500'}`}>
                    {c.customer_status}
                  </span>
                </td>
                <td className="py-2.5">
                  <div className="flex items-center gap-2">
                    <button onClick={() => setEditCust({ ...c })} className="text-emerald-500 hover:underline text-[11px]">Edit</button>
                    <button onClick={() => toggleStatus(c)} className="text-sky-500 hover:underline text-[11px]">{c.customer_status === 'ACTIVE' ? 'Block' : 'Activate'}</button>
                    <button onClick={() => handleDeleteCustomer(c)} className="text-rose-500 hover:underline text-[11px]">Delete</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

// ============================================================================
// PAGE 3: CARDS & PROFILES
// ============================================================================
export const CardsPage: React.FC = () => {
  const [cards, setCards] = useState<any[]>([]);
  const [customers, setCustomers] = useState<any[]>([]);
  const [accounts, setAccounts] = useState<any[]>([]);
  const [institutions, setInstitutions] = useState<any[]>([]);

  // Multi-account modal state (Step 4)
  const [selectedCardForAccts, setSelectedCardForAccts] = useState<any | null>(null);
  const [cardAccounts, setCardAccounts] = useState<any[]>([]);
  const [newLinkAccountId, setNewLinkAccountId] = useState('');
  const [newLinkRole, setNewLinkRole] = useState('SECONDARY');

  // Pagination & filter state (Step 5)
  const [cardPage, setCardPage] = useState(1);
  const [cardTotalPages, setCardTotalPages] = useState(1);
  const [cardTotalCount, setCardTotalCount] = useState(0);
  const [cardPanSearch, setCardPanSearch] = useState('');
  const [cardStatusFilter, setCardStatusFilter] = useState('');

  const [form, setForm] = useState({
    customer_id: '',
    linked_account_id: '',
    institution_id: '',
    test_pan_reference: `456789012345${Math.floor(1000 + Math.random() * 8999)}`,
    cardholder_name: 'SYNTHETIC CARDHOLDER',
    expiry_month: 12,
    expiry_year: 2028,
    card_type: 'DEBIT',
    card_product: 'VISA_DEBIT_CLASSIC',
    pvv_or_offset: '0416',
    cvv_value: '011',
  });

  const load = async () => {
    try {
      const params = new URLSearchParams({ page: String(cardPage), page_size: '15' });
      if (cardPanSearch) params.set('pan', cardPanSearch);
      if (cardStatusFilter) params.set('status', cardStatusFilter);
      const [cRes, custList, acctList, iList] = await Promise.all([
        apiFetch(`/cards?${params.toString()}`),
        apiFetch('/customers?page_size=100'),
        apiFetch('/accounts?page_size=100'),
        apiFetch('/institutions'),
      ]);
      setCards(cRes.items || cRes);
      setCardTotalCount(cRes.total || (cRes.items ? cRes.items.length : cRes.length));
      setCardTotalPages(cRes.total_pages || 1);
      setCustomers(custList.items || custList);
      setAccounts(acctList.items || acctList);
      setInstitutions(iList);
      if (!form.institution_id && iList.length > 0) {
        setForm((f) => ({ ...f, institution_id: iList[0].id }));
      }
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    load();
  }, [cardPage]);

  const handleIssue = async (e: React.FormEvent) => {
    e.preventDefault();
    await apiFetch('/cards', { method: 'POST', body: JSON.stringify(form) });
    load();
  };

  const toggleCardStatus = async (c: any) => {
    const next = c.card_status === 'ACTIVE' ? 'BLOCKED' : 'ACTIVE';
    await apiFetch(`/cards/${c.id}/status?card_status=${next}`, { method: 'PATCH' });
    load();
  };

  const handleDeleteCard = async (c: any, force: boolean = false) => {
    if (!force && !confirm(`Are you sure you want to delete card ${c.masked_pan}?`)) return;
    try {
      await apiFetch(`/cards/${c.id}${force ? '?force=true' : ''}`, { method: 'DELETE' });
      load();
    } catch (err: any) {
      if (err.message.includes('409') || err.message.toLowerCase().includes('historical transactions')) {
        if (confirm(`${err.message}\\n\\nDo you want to FORCE delete this card for lab testing?`)) {
          handleDeleteCard(c, true);
        }
      } else {
        alert(err.message);
      }
    }
  };

  const openAccountManager = async (c: any) => {
    setSelectedCardForAccts(c);
    const links = await apiFetch(`/cards/${c.id}/accounts`);
    setCardAccounts(links);
    if (accounts.length > 0) setNewLinkAccountId(accounts[0].id);
  };

  const handleLinkAccount = async () => {
    if (!selectedCardForAccts || !newLinkAccountId) return;
    try {
      await apiFetch(`/cards/${selectedCardForAccts.id}/accounts`, {
        method: 'POST',
        body: JSON.stringify({
          account_id: newLinkAccountId,
          account_role: newLinkRole,
          priority: cardAccounts.length + 1,
        }),
      });
      const links = await apiFetch(`/cards/${selectedCardForAccts.id}/accounts`);
      setCardAccounts(links);
    } catch (err: any) {
      alert(err.message);
    }
  };

  const handleSetPrimary = async (linkId: string) => {
    try {
      await apiFetch(`/cards/accounts/${linkId}`, {
        method: 'PUT',
        body: JSON.stringify({ account_role: 'PRIMARY', priority: 1 }),
      });
      const links = await apiFetch(`/cards/${selectedCardForAccts.id}/accounts`);
      setCardAccounts(links);
    } catch (err: any) {
      alert(err.message);
    }
  };

  const handleUnlink = async (linkId: string) => {
    if (!confirm('Unlink this account from the card?')) return;
    try {
      await apiFetch(`/cards/accounts/${linkId}`, { method: 'DELETE' });
      const links = await apiFetch(`/cards/${selectedCardForAccts.id}/accounts`);
      setCardAccounts(links);
    } catch (err: any) {
      alert(err.message);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold">Cards, PIN Profiles & EMV Profiles</h1>
        <p className="text-xs text-slate-500">Synthetic test cards with multi-account linking, bank scoping, and Soft-HSM PIN/EMV profiles</p>
      </div>

      {selectedCardForAccts && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center p-4 z-50">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-6 max-w-xl w-full space-y-4 shadow-2xl">
            <div className="flex justify-between items-center border-b border-slate-200 dark:border-slate-800 pb-3">
              <div>
                <h2 className="text-sm font-bold">Multi-Account Manager</h2>
                <div className="text-xs font-mono text-emerald-500">Card: {selectedCardForAccts.masked_pan}</div>
              </div>
              <button onClick={() => setSelectedCardForAccts(null)} className="text-slate-400 hover:text-white text-lg">×</button>
            </div>
            <div className="space-y-2 max-h-56 overflow-y-auto">
              {cardAccounts.map((l) => (
                <div key={l.id} className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 flex justify-between items-center text-xs font-mono bg-slate-50 dark:bg-slate-950">
                  <div>
                    <span className="font-bold text-sky-400">{l.account_number}</span> ({l.account_type}) · Avl: {l.available_balance.toLocaleString()} {l.currency}
                    <div className="text-[10px] text-slate-400">Priority: {l.priority} | Role: <span className={l.account_role === 'PRIMARY' ? 'text-emerald-400 font-bold' : 'text-slate-300'}>{l.account_role}</span></div>
                  </div>
                  <div className="flex items-center gap-2">
                    {l.account_role !== 'PRIMARY' && (
                      <button onClick={() => handleSetPrimary(l.id)} className="text-emerald-500 hover:underline text-[11px]">Set Primary</button>
                    )}
                    <button onClick={() => handleUnlink(l.id)} className="text-rose-500 hover:underline text-[11px]">Unlink</button>
                  </div>
                </div>
              ))}
            </div>
            <div className="pt-3 border-t border-slate-200 dark:border-slate-800 flex gap-2">
              <select value={newLinkAccountId} onChange={(e) => setNewLinkAccountId(e.target.value)} className="flex-1 bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5 text-xs font-mono">
                {accounts.map((a) => (
                  <option key={a.id} value={a.id}>ACCT {a.account_number} ({a.account_type}) — {a.customer_name}</option>
                ))}
              </select>
              <select value={newLinkRole} onChange={(e) => setNewLinkRole(e.target.value)} className="w-32 bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5 text-xs font-mono">
                <option value="SECONDARY">SECONDARY</option>
                <option value="PRIMARY">PRIMARY</option>
              </select>
              <button onClick={handleLinkAccount} className="bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-1.5 rounded text-xs font-semibold">+ Link Account</button>
            </div>
          </div>
        </div>
      )}

      <form onSubmit={handleIssue} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 grid grid-cols-1 md:grid-cols-6 gap-3">
        <select value={form.institution_id} onChange={(e) => setForm({ ...form, institution_id: e.target.value })} className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono">
          {institutions.map((i) => (
            <option key={i.id} value={i.id}>{i.institution_code} — {i.short_name || i.name}</option>
          ))}
        </select>
        <select value={form.customer_id} onChange={(e) => setForm({ ...form, customer_id: e.target.value })} className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono">
          {customers.map((c) => (
            <option key={c.id} value={c.id}>{c.customer_number} - {c.first_name}</option>
          ))}
        </select>
        <select value={form.linked_account_id} onChange={(e) => setForm({ ...form, linked_account_id: e.target.value })} className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono">
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>ACCT {a.account_number} ({a.currency})</option>
          ))}
        </select>
        <input value={form.test_pan_reference} onChange={(e) => setForm({ ...form, test_pan_reference: e.target.value })} placeholder="Synthetic 16-Digit PAN" className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono" required />
        <input value={form.cardholder_name} onChange={(e) => setForm({ ...form, cardholder_name: e.target.value })} placeholder="Cardholder Name" className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono" required />
        <button type="submit" className="bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg px-4 py-2 text-xs font-semibold">+ Issue Test Card</button>
      </form>

      <div className="flex flex-wrap items-center justify-between gap-3 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4">
        <div className="flex flex-wrap items-center gap-2 flex-1">
          <input value={cardPanSearch} onChange={(e) => setCardPanSearch(e.target.value)} placeholder="Filter PAN (e.g. 0001)..." className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-1.5 text-xs font-mono" />
          <select value={cardStatusFilter} onChange={(e) => setCardStatusFilter(e.target.value)} className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-1.5 text-xs font-mono">
            <option value="">ALL STATUSES</option>
            <option value="ACTIVE">ACTIVE</option>
            <option value="BLOCKED">BLOCKED</option>
          </select>
          <button onClick={() => { setCardPage(1); load(); }} className="bg-emerald-600 text-white px-3 py-1.5 rounded-lg text-xs font-semibold">Filter</button>
        </div>
        <div className="flex items-center gap-2 text-xs font-mono text-slate-400">
          <span>Cards: <strong className="text-emerald-500">{cardTotalCount}</strong></span>
          <button disabled={cardPage <= 1} onClick={() => setCardPage(cardPage - 1)} className="px-2.5 py-1 rounded border border-slate-300 dark:border-slate-700 disabled:opacity-40">Prev</button>
          <span>Page {cardPage} of {cardTotalPages}</span>
          <button disabled={cardPage >= cardTotalPages} onClick={() => setCardPage(cardPage + 1)} className="px-2.5 py-1 rounded border border-slate-300 dark:border-slate-700 disabled:opacity-40">Next</button>
        </div>
      </div>

      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 overflow-x-auto">
        <table className="w-full text-left text-xs font-mono">
          <thead>
            <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-400">
              <th className="py-2.5">Masked PAN</th>
              <th className="py-2.5">Sim Ref (Test Only)</th>
              <th className="py-2.5">Bank</th>
              <th className="py-2.5">Cardholder</th>
              <th className="py-2.5">Expiry</th>
              <th className="py-2.5">PIN Profile (PVK / PVV)</th>
              <th className="py-2.5">Status</th>
              <th className="py-2.5">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200/60 dark:divide-slate-800/60">
            {cards.map((c) => (
              <tr key={c.id}>
                <td className="py-2.5 font-bold text-emerald-500">{c.masked_pan}</td>
                <td className="py-2.5 text-slate-400">{c.test_pan_reference}</td>
                <td className="py-2.5 text-sky-400 font-bold">{c.institution_code || 'XBANK'}</td>
                <td className="py-2.5">{c.cardholder_name}</td>
                <td className="py-2.5">{String(c.expiry_month).padStart(2, '0')}/{c.expiry_year}</td>
                <td className="py-2.5">{c.pin_profile ? `${c.pin_profile.verification_method} | PVV:${c.pin_profile.pin_offset_reference}` : 'N/A'}</td>
                <td className="py-2.5">
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${c.card_status === 'ACTIVE' ? 'bg-emerald-500/10 text-emerald-500' : 'bg-rose-500/10 text-rose-500'}`}>
                    {c.card_status}
                  </span>
                </td>
                <td className="py-2.5">
                  <div className="flex items-center gap-1.5">
                    <button onClick={() => toggleCardStatus(c)} className="text-sky-500 hover:underline text-[11px]">{c.card_status === 'ACTIVE' ? 'Block' : 'Activate'}</button>
                    <button onClick={() => openAccountManager(c)} className="text-amber-500 hover:underline text-[11px]">Linked Accts</button>
                    <button onClick={() => handleDeleteCard(c)} className="text-rose-500 hover:underline text-[11px]">Delete</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

// ============================================================================
// PAGE 4: ACCOUNTS & LEDGER
// ============================================================================
export const AccountsPage: React.FC = () => {
  const [accounts, setAccounts] = useState<any[]>([]);
  const [customers, setCustomers] = useState<any[]>([]);
  const [institutions, setInstitutions] = useState<any[]>([]);
  const [ledger, setLedger] = useState<any[]>([]);
  const [selectedAcct, setSelectedAcct] = useState<string>('');

  const [acctPage, setAcctPage] = useState(1);
  const [acctTotalPages, setAcctTotalPages] = useState(1);
  const [acctTotalCount, setAcctTotalCount] = useState(0);
  const [acctSearch, setAcctSearch] = useState('');

  const [form, setForm] = useState({
    account_number: `100100${Math.floor(1000 + Math.random() * 8999)}`,
    customer_id: '',
    institution_id: '',
    account_type: 'SAVINGS',
    currency: 'BDT',
    available_balance: '100000.00',
    ledger_balance: '100000.00',
    overdraft_limit: '0.00',
  });

  const load = async () => {
    try {
      const q = acctSearch ? `&q=${encodeURIComponent(acctSearch)}` : '';
      const [aRes, cRes, iList] = await Promise.all([
        apiFetch(`/accounts?page=${acctPage}&page_size=15${q}`),
        apiFetch('/customers?page_size=100'),
        apiFetch('/institutions'),
      ]);
      setAccounts(aRes.items || aRes);
      setAcctTotalCount(aRes.total || (aRes.items ? aRes.items.length : aRes.length));
      setAcctTotalPages(aRes.total_pages || 1);
      setCustomers(cRes.items || cRes);
      setInstitutions(iList);
      if (!form.institution_id && iList.length > 0) {
        setForm((f) => ({ ...f, institution_id: iList[0].id }));
      }
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    load();
  }, [acctPage]);

  const viewLedger = async (acctId: string) => {
    setSelectedAcct(acctId);
    setLedger(await apiFetch(`/accounts/${acctId}/ledger`));
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    await apiFetch('/accounts', { method: 'POST', body: JSON.stringify(form) });
    load();
  };

  const handleDeleteAccount = async (a: any, force: boolean = false) => {
    if (!force && !confirm(`Are you sure you want to delete account ${a.account_number}?`)) return;
    try {
      await apiFetch(`/accounts/${a.id}${force ? '?force=true' : ''}`, { method: 'DELETE' });
      load();
    } catch (err: any) {
      if (err.message.includes('409') || err.message.toLowerCase().includes('cannot delete')) {
        if (confirm(`${err.message}\\n\\nDo you want to FORCE delete this account for lab testing?`)) {
          handleDeleteAccount(a, true);
        }
      } else {
        alert(err.message);
      }
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold">Accounts & Atomic Financial Ledger</h1>
        <p className="text-xs text-slate-500">Fixed-precision numeric balances with row-level locking and bank ownership</p>
      </div>

      <form onSubmit={handleCreate} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 grid grid-cols-1 md:grid-cols-7 gap-3">
        <input value={form.account_number} onChange={(e) => setForm({ ...form, account_number: e.target.value })} placeholder="Account Number" className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono" required />
        <select value={form.institution_id} onChange={(e) => setForm({ ...form, institution_id: e.target.value })} className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono">
          {institutions.map((i) => (
            <option key={i.id} value={i.id}>{i.institution_code} — {i.short_name || i.name}</option>
          ))}
        </select>
        <select value={form.customer_id} onChange={(e) => setForm({ ...form, customer_id: e.target.value })} className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono">
          {customers.map((c) => (
            <option key={c.id} value={c.id}>{c.customer_number} - {c.first_name}</option>
          ))}
        </select>
        <select value={form.account_type} onChange={(e) => setForm({ ...form, account_type: e.target.value })} className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono">
          <option value="SAVINGS">SAVINGS</option><option value="CURRENT">CURRENT</option><option value="CREDIT">CREDIT</option>
        </select>
        <input value={form.available_balance} onChange={(e) => setForm({ ...form, available_balance: e.target.value, ledger_balance: e.target.value })} placeholder="Opening Balance" className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono" />
        <input value={form.overdraft_limit} onChange={(e) => setForm({ ...form, overdraft_limit: e.target.value })} placeholder="Overdraft Limit" className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono" />
        <button type="submit" className="bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg px-4 py-2 text-xs font-semibold">+ Open Account</button>
      </form>

      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 overflow-x-auto">
        <table className="w-full text-left text-xs font-mono">
          <thead>
            <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-400">
              <th className="py-2.5">Account Number</th>
              <th className="py-2.5">Bank</th>
              <th className="py-2.5">Customer</th>
              <th className="py-2.5">Type</th>
              <th className="py-2.5">Available Balance</th>
              <th className="py-2.5">Ledger Balance</th>
              <th className="py-2.5">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200/60 dark:divide-slate-800/60">
            {accounts.map((a) => (
              <tr key={a.id}>
                <td className="py-2.5 font-bold text-emerald-500">{a.account_number}</td>
                <td className="py-2.5 text-sky-400 font-bold">{a.institution_code || 'XBANK'}</td>
                <td className="py-2.5 font-sans">{a.customer_name}</td>
                <td className="py-2.5">{a.account_type}</td>
                <td className="py-2.5 font-bold">{a.available_balance.toLocaleString()} {a.currency}</td>
                <td className="py-2.5">{a.ledger_balance.toLocaleString()} {a.currency}</td>
                <td className="py-2.5">
                  <div className="flex items-center gap-2">
                    <button onClick={() => viewLedger(a.id)} className="text-sky-500 hover:underline text-[11px]">Inspect Ledger</button>
                    <button onClick={() => handleDeleteAccount(a)} className="text-rose-500 hover:underline text-[11px]">Delete</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {selectedAcct && (
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5">
          <h2 className="text-sm font-bold mb-3">Account Ledger Entries</h2>
          <table className="w-full text-left text-xs font-mono">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-400">
                <th className="py-2">Timestamp</th>
                <th className="py-2">Type</th>
                <th className="py-2">Amount</th>
                <th className="py-2">Balance Before</th>
                <th className="py-2">Balance After</th>
                <th className="py-2">Description</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200/60 dark:divide-slate-800/60">
              {ledger.map((l) => (
                <tr key={l.id}>
                  <td className="py-2">{new Date(l.created_at).toLocaleString()}</td>
                  <td className="py-2 font-bold text-emerald-500">{l.entry_type}</td>
                  <td className="py-2">{l.amount.toLocaleString()} {l.currency}</td>
                  <td className="py-2">{l.balance_before.toLocaleString()}</td>
                  <td className="py-2 font-bold">{l.balance_after.toLocaleString()}</td>
                  <td className="py-2">{l.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

// ============================================================================
// PAGES 5 & 6: CARD LIMITS & ACCOUNT LIMITS
// ============================================================================
export const CardLimitsPage: React.FC = () => {
  const [cards, setCards] = useState<any[]>([]);
  const [msg, setMsg] = useState('');

  const load = async () => {
    const res = await apiFetch('/cards');
    setCards(res.items || res);
  };
  useEffect(() => { load(); }, []);

  const saveLimit = async (card: any) => {
    await apiFetch(`/cards/${card.id}/limits`, {
      method: 'PUT',
      body: JSON.stringify({ ...card.limits, status: 'ACTIVE' }),
    });
    setMsg(`Updated limits for card ${card.masked_pan}`);
    load();
  };

  const updateField = (idx: number, key: string, val: string) => {
    const copy = [...cards];
    copy[idx].limits[key] = parseFloat(val) || 0;
    setCards(copy);
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold">Card-Level Limits (BAOBAB CHECKCARDLIMITS)</h1>
        <p className="text-xs text-slate-500">Configure per-transaction, daily, weekly, and monthly limits and inspect live usage counters</p>
      </div>
      {msg && <div className="p-3 rounded bg-emerald-500/10 text-emerald-500 text-xs font-mono">{msg}</div>}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 overflow-x-auto">
        <table className="w-full text-left text-xs font-mono">
          <thead>
            <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-400">
              <th className="py-2">Card</th>
              <th className="py-2">Per-TX Limit</th>
              <th className="py-2">Daily Limit</th>
              <th className="py-2">Daily Used</th>
              <th className="py-2">Weekly Limit</th>
              <th className="py-2">Monthly Limit</th>
              <th className="py-2">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200/60 dark:divide-slate-800/60">
            {cards.map((c, idx) => c.limits ? (
              <tr key={c.id}>
                <td className="py-2 font-bold text-emerald-500">{c.masked_pan}</td>
                <td className="py-2">
                  <input type="number" value={c.limits.transaction_limit} onChange={(e) => updateField(idx, 'transaction_limit', e.target.value)} className="w-28 bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2 py-1" />
                </td>
                <td className="py-2">
                  <input type="number" value={c.limits.daily_limit} onChange={(e) => updateField(idx, 'daily_limit', e.target.value)} className="w-28 bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2 py-1" />
                </td>
                <td className="py-2 text-amber-500 font-bold">{c.limits.daily_used.toLocaleString()}</td>
                <td className="py-2">
                  <input type="number" value={c.limits.weekly_limit} onChange={(e) => updateField(idx, 'weekly_limit', e.target.value)} className="w-28 bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2 py-1" />
                </td>
                <td className="py-2">
                  <input type="number" value={c.limits.monthly_limit} onChange={(e) => updateField(idx, 'monthly_limit', e.target.value)} className="w-32 bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2 py-1" />
                </td>
                <td className="py-2">
                  <button onClick={() => saveLimit(c)} className="bg-emerald-600 hover:bg-emerald-500 text-white px-3 py-1 rounded text-[11px]">Save</button>
                </td>
              </tr>
            ) : null)}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export const AccountLimitsPage: React.FC = () => {
  const [accounts, setAccounts] = useState<any[]>([]);
  const [msg, setMsg] = useState('');

  const load = async () => {
    const res = await apiFetch('/accounts');
    setAccounts(res.items || res);
  };
  useEffect(() => { load(); }, []);

  const saveLimit = async (acct: any) => {
    await apiFetch(`/accounts/${acct.id}/limits`, {
      method: 'PUT',
      body: JSON.stringify({ ...acct.limits, status: 'ACTIVE' }),
    });
    setMsg(`Updated account limits for ${acct.account_number}`);
    load();
  };

  const updateField = (idx: number, key: string, val: string) => {
    const copy = [...accounts];
    copy[idx].limits[key] = parseFloat(val) || 0;
    setAccounts(copy);
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold">Account-Level Limits (CHECKACCT2CARDLIMITS)</h1>
        <p className="text-xs text-slate-500">Configure account velocity and per-transaction limits independent of card limits</p>
      </div>
      {msg && <div className="p-3 rounded bg-emerald-500/10 text-emerald-500 text-xs font-mono">{msg}</div>}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 overflow-x-auto">
        <table className="w-full text-left text-xs font-mono">
          <thead>
            <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-400">
              <th className="py-2">Account No</th>
              <th className="py-2">Per-TX Limit</th>
              <th className="py-2">Daily Limit</th>
              <th className="py-2">Daily Used</th>
              <th className="py-2">Weekly Limit</th>
              <th className="py-2">Monthly Limit</th>
              <th className="py-2">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200/60 dark:divide-slate-800/60">
            {accounts.map((a, idx) => a.limits ? (
              <tr key={a.id}>
                <td className="py-2 font-bold text-emerald-500">{a.account_number}</td>
                <td className="py-2">
                  <input type="number" value={a.limits.per_transaction_limit} onChange={(e) => updateField(idx, 'per_transaction_limit', e.target.value)} className="w-28 bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2 py-1" />
                </td>
                <td className="py-2">
                  <input type="number" value={a.limits.daily_limit} onChange={(e) => updateField(idx, 'daily_limit', e.target.value)} className="w-28 bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2 py-1" />
                </td>
                <td className="py-2 text-amber-500 font-bold">{a.limits.daily_used.toLocaleString()}</td>
                <td className="py-2">
                  <input type="number" value={a.limits.weekly_limit} onChange={(e) => updateField(idx, 'weekly_limit', e.target.value)} className="w-28 bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2 py-1" />
                </td>
                <td className="py-2">
                  <input type="number" value={a.limits.monthly_limit} onChange={(e) => updateField(idx, 'monthly_limit', e.target.value)} className="w-32 bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2 py-1" />
                </td>
                <td className="py-2">
                  <button onClick={() => saveLimit(a)} className="bg-emerald-600 hover:bg-emerald-500 text-white px-3 py-1 rounded text-[11px]">Save</button>
                </td>
              </tr>
            ) : null)}
          </tbody>
        </table>
      </div>
    </div>
  );
};
'''
    session.write_file("frontend/src/pages/BankingEntities.tsx", banking_entities_complete)

    # --------------------------------------------------------------------------
    # 6. FIX frontend/src/pages/SimulatorAndJournal.tsx (Step 05: Pagination bar)
    # --------------------------------------------------------------------------
    session.patch_file(
        "frontend/src/pages/SimulatorAndJournal.tsx",
        [
            {
                "marker": "step05:journal_pagination_bar_fixed",
                "action": "replace",
                "anchor": (
                    "        </table>\n"
                    "      </div>\n"
                    "    </div>\n"
                    "  );\n"
                    "};\n\n"
                    "// ============================================================================\n"
                    "// PAGE 10: TRANSACTION DETAILS"
                ),
                "text": (
                    "        </table>\n"
                    "      </div>\n\n"
                    "      <div className=\"flex justify-between items-center bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-3 text-xs font-mono\">\n"
                    "        <div className=\"text-slate-400\">Total Journal Records: <strong className=\"text-emerald-500\">{totalTxs}</strong></div>\n"
                    "        <div className=\"flex items-center gap-2\">\n"
                    "          <button disabled={page <= 1} onClick={() => setPage(page - 1)} className=\"px-3 py-1 rounded border border-slate-300 dark:border-slate-700 disabled:opacity-40\">Previous</button>\n"
                    "          <span>Page {page} of {totalPages}</span>\n"
                    "          <button disabled={page >= totalPages} onClick={() => setPage(page + 1)} className=\"px-3 py-1 rounded border border-slate-300 dark:border-slate-700 disabled:opacity-40\">Next</button>\n"
                    "        </div>\n"
                    "      </div>\n"
                    "    </div>\n"
                    "  );\n"
                    "};\n\n"
                    "// ============================================================================\n"
                    "// PAGE 10: TRANSACTION DETAILS"
                ),
            }
        ],
    )

    session.record_progress(
        completed=[
            "Fixed CustomerOut schema in `backend/app/schemas.py`.",
            "Fixed NetworkProfile simulation columns in `backend/app/models.py`.",
            "Fixed Transaction model assignment in `backend/app/host_engine.py`.",
            "Fixed paginated `/accounts` route in `backend/app/api_routes.py`.",
            "Cleanly replaced `frontend/src/pages/BankingEntities.tsx` consolidating all features from Steps 2, 3, 4, and 5.",
            "Fixed pagination footer in `frontend/src/pages/SimulatorAndJournal.tsx`.",
        ],
        remaining=[],
        modified_files=[
            "backend/app/schemas.py",
            "backend/app/models.py",
            "backend/app/host_engine.py",
            "backend/app/api_routes.py",
            "frontend/src/pages/BankingEntities.tsx",
            "frontend/src/pages/SimulatorAndJournal.tsx",
        ],
    )

    return session.finish()


if __name__ == "__main__":
    sys.exit(main())