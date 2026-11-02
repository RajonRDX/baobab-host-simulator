#!/usr/bin/env python3
"""
tools/install_customer_maintenance.py
1. Fixes new card issuance so the exact user-typed PIN (e.g. 4321) is used to calculate the Visa PVV.
2. Updates backend/app/api_routes.py to allow account deletion with ledger cleanup on ?force=true.
3. Adds unified search and maintenance endpoint: GET /api/maintenance/search and POST /api/maintenance/link.
4. Creates frontend/src/pages/CustomerDataMaintenancePage.tsx.
5. Registers /customer-maintenance in frontend/src/App.tsx and frontend/src/components/Layout.tsx.
"""

from pathlib import Path
import py_compile
import sys

BASE_DIR = Path(r"E:\HOST_VSCODE\host-simulator").resolve()

MAINTENANCE_PAGE_CODE = '''import React, { useState, useEffect } from 'react';
import { Search, User, CreditCard, Landmark, Trash2, Link as LinkIcon, Unlink, RefreshCw, CheckCircle2, AlertTriangle, ShieldCheck } from 'lucide-react';
import { apiFetch } from '../api';

export const CustomerDataMaintenancePage: React.FC = () => {
  const [searchTerm, setSearchTerm] = useState('');
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<any[]>([]);
  const [selectedCust, setSelectedCust] = useState<any | null>(null);
  const [msg, setMsg] = useState('');
  const [error, setError] = useState('');

  // Link account dialog state
  const [linkCardId, setLinkCardId] = useState<string | null>(null);
  const [targetAccountId, setTargetAccountId] = useState('');
  const [linkRole, setLinkRole] = useState('SECONDARY');

  const handleSearch = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!searchTerm.trim()) return;
    setLoading(true);
    setMsg('');
    setError('');
    try {
      const res = await apiFetch(`/maintenance/search?q=${encodeURIComponent(searchTerm.trim())}`);
      setResults(res.customers || []);
      if (res.customers && res.customers.length > 0) {
        setSelectedCust(res.customers[0]);
      } else {
        setSelectedCust(null);
      }
    } catch (err: any) {
      setError(err.message || 'Search failed');
    } finally {
      setLoading(false);
    }
  };

  const refreshCustomer = async (custId: string) => {
    try {
      const res = await apiFetch(`/maintenance/search?q=${encodeURIComponent(custId)}`);
      if (res.customers && res.customers.length > 0) {
        setSelectedCust(res.customers[0]);
      }
    } catch (e) {}
  };

  const handleDeleteCard = async (card: any) => {
    if (!confirm(`Delete card ${card.masked_pan}?`)) return;
    try {
      await apiFetch(`/cards/${card.id}?force=true`, { method: 'DELETE' });
      setMsg(`Card ${card.masked_pan} deleted successfully.`);
      if (selectedCust) refreshCustomer(selectedCust.id);
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleDeleteAccount = async (acct: any) => {
    if (!confirm(`Delete account ${acct.account_number}? All associated ledger entries will be cleaned up.`)) return;
    try {
      await apiFetch(`/accounts/${acct.id}?force=true`, { method: 'DELETE' });
      setMsg(`Account ${acct.account_number} deleted successfully.`);
      if (selectedCust) refreshCustomer(selectedCust.id);
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleUnlink = async (linkId: string) => {
    if (!confirm('Unlink this account from the card?')) return;
    try {
      await apiFetch(`/cards/accounts/${linkId}`, { method: 'DELETE' });
      setMsg('Account unlinked from card.');
      if (selectedCust) refreshCustomer(selectedCust.id);
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleLinkAccountToCard = async () => {
    if (!linkCardId || !targetAccountId) return;
    try {
      await apiFetch(`/cards/${linkCardId}/accounts`, {
        method: 'POST',
        body: JSON.stringify({
          account_id: targetAccountId,
          account_role: linkRole,
          priority: 2,
        }),
      });
      setMsg('Account linked to card successfully.');
      setLinkCardId(null);
      if (selectedCust) refreshCustomer(selectedCust.id);
    } catch (err: any) {
      setError(err.message);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold">Customer Data Maintenance Workbench</h1>
          <p className="text-xs text-slate-500">
            Unified Customer 360 search: search by Card PAN, Account Number, or Customer CIF to inspect, link, unlink, and manage entities
          </p>
        </div>
      </div>

      {msg && (
        <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs font-mono">
          ✓ {msg}
        </div>
      )}
      {error && (
        <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs font-mono">
          ⚠ {error}
        </div>
      )}

      {/* Search Header Bar */}
      <form onSubmit={handleSearch} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 flex gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-2.5 text-slate-400" size={16} />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search by Card PAN (e.g. 456789...), Account Number (e.g. 100100...), or Customer Name/Number..."
            className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg pl-9 pr-4 py-2 text-xs font-mono"
            required
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          className="bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg px-5 py-2 text-xs font-semibold flex items-center gap-2"
        >
          {loading ? <RefreshCw className="animate-spin" size={14} /> : <Search size={14} />} Search
        </button>
      </form>

      {/* Link Account Modal */}
      {linkCardId && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center p-4 z-50">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-6 max-w-md w-full space-y-4 shadow-2xl">
            <h2 className="text-sm font-bold">Link Account to Card</h2>
            <div className="space-y-3 text-xs font-mono">
              <div>
                <label className="block text-slate-400 mb-1">Select Customer Account</label>
                <select
                  value={targetAccountId}
                  onChange={(e) => setTargetAccountId(e.target.value)}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5"
                >
                  <option value="">-- Choose Account --</option>
                  {(selectedCust?.accounts || []).map((a: any) => (
                    <option key={a.id} value={a.id}>
                      ACCT {a.account_number} ({a.account_type}) - Avl: {a.available_balance.toLocaleString()} {a.currency}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-slate-400 mb-1">Account Role</label>
                <select
                  value={linkRole}
                  onChange={(e) => setLinkRole(e.target.value)}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5"
                >
                  <option value="SECONDARY">SECONDARY</option>
                  <option value="PRIMARY">PRIMARY</option>
                </select>
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t border-slate-200 dark:border-slate-800">
              <button onClick={() => setLinkCardId(null)} className="px-3 py-1.5 rounded text-xs">Cancel</button>
              <button onClick={handleLinkAccountToCard} className="bg-emerald-600 text-white px-4 py-1.5 rounded text-xs font-semibold">
                Link Account
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Main Split Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left 4 cols: Matched Customers */}
        <div className="lg:col-span-4 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 space-y-3">
          <h2 className="text-sm font-bold flex items-center justify-between">
            <span>Matched Customers</span>
            <span className="text-xs font-mono text-slate-400">{results.length} found</span>
          </h2>
          <div className="space-y-2 max-h-[600px] overflow-y-auto">
            {results.map((c) => (
              <div
                key={c.id}
                onClick={() => setSelectedCust(c)}
                className={`p-3 rounded-lg border text-xs font-mono cursor-pointer transition ${
                  selectedCust?.id === c.id ? 'border-emerald-500 bg-emerald-500/10' : 'border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/40'
                }`}
              >
                <div className="flex justify-between items-center">
                  <span className="font-bold text-emerald-400">{c.customer_number}</span>
                  <span className="text-sky-400 font-bold">{c.institution_code || 'XBANK'}</span>
                </div>
                <div className="text-slate-300 font-sans font-medium mt-1">{c.first_name} {c.last_name}</div>
                <div className="text-[11px] text-slate-400 mt-1">
                  Accounts: <strong>{c.accounts?.length || 0}</strong> · Cards: <strong>{c.cards?.length || 0}</strong>
                </div>
              </div>
            ))}
            {results.length === 0 && (
              <div className="py-12 text-center text-slate-400 text-xs font-mono">
                Search for a card, account, or customer to view relationship data.
              </div>
            )}
          </div>
        </div>

        {/* Right 8 cols: Customer 360 Deep-Dive */}
        <div className="lg:col-span-8 space-y-6">
          {selectedCust ? (
            <>
              {/* Customer CIF Card */}
              <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 space-y-3">
                <div className="flex justify-between items-center border-b border-slate-200 dark:border-slate-800 pb-2">
                  <div className="flex items-center gap-2">
                    <User size={16} className="text-emerald-500" />
                    <h2 className="text-sm font-bold font-mono">Customer Profile: {selectedCust.first_name} {selectedCust.last_name}</h2>
                  </div>
                  <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/10 text-emerald-400">
                    {selectedCust.customer_status}
                  </span>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs font-mono">
                  <div><span className="text-slate-400 block">CIF Number</span>{selectedCust.customer_number}</div>
                  <div><span className="text-slate-400 block">Owning Bank</span><strong className="text-sky-400">{selectedCust.institution_code || 'XBANK'}</strong></div>
                  <div><span className="text-slate-400 block">Mobile</span>{selectedCust.mobile_number || 'N/A'}</div>
                  <div><span className="text-slate-400 block">Risk Category</span>{selectedCust.risk_category}</div>
                </div>
              </div>

              {/* Linked Accounts Section */}
              <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 space-y-3">
                <h3 className="text-sm font-bold flex items-center gap-2">
                  <Landmark size={15} className="text-sky-400" /> Linked Accounts ({selectedCust.accounts?.length || 0})
                </h3>
                <div className="space-y-2">
                  {(selectedCust.accounts || []).map((a: any) => (
                    <div key={a.id} className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 flex justify-between items-center text-xs font-mono">
                      <div>
                        <div className="font-bold text-sky-400">{a.account_number} ({a.account_type})</div>
                        <div className="text-[11px] text-slate-400">
                          Available: <strong className="text-emerald-400">{a.available_balance.toLocaleString()} {a.currency}</strong> · Ledger: {a.ledger_balance.toLocaleString()}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <button onClick={() => handleDeleteAccount(a)} className="text-rose-500 hover:underline flex items-center gap-1 text-[11px]">
                          <Trash2 size={12} /> Delete Account
                        </button>
                      </div>
                    </div>
                  ))}
                  {(!selectedCust.accounts || selectedCust.accounts.length === 0) && (
                    <div className="text-slate-400 text-xs py-3 text-center">No accounts linked to this customer.</div>
                  )}
                </div>
              </div>

              {/* Linked Cards Section */}
              <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 space-y-3">
                <h3 className="text-sm font-bold flex items-center gap-2">
                  <CreditCard size={15} className="text-emerald-400" /> Issued Cards ({selectedCust.cards?.length || 0})
                </h3>
                <div className="space-y-3">
                  {(selectedCust.cards || []).map((c: any) => (
                    <div key={c.id} className="p-3.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 space-y-2 text-xs font-mono">
                      <div className="flex justify-between items-center">
                        <div>
                          <strong className="text-emerald-400 text-sm tracking-wider">{c.masked_pan}</strong>
                          <span className="text-[10px] text-slate-400 ml-2">({c.test_pan_reference})</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <button onClick={() => setLinkCardId(c.id)} className="text-amber-400 hover:underline flex items-center gap-1 text-[11px]">
                            <LinkIcon size={12} /> Link Another Account
                          </button>
                          <button onClick={() => handleDeleteCard(c)} className="text-rose-500 hover:underline flex items-center gap-1 text-[11px]">
                            <Trash2 size={12} /> Delete Card
                          </button>
                        </div>
                      </div>
                      <div className="flex gap-4 text-[11px] text-slate-400">
                        <div>Expiry: {String(c.expiry_month).padStart(2, '0')}/{c.expiry_year}</div>
                        <div>PVV: <strong className="text-amber-400">{c.pin_profile?.pin_offset_reference || 'N/A'}</strong></div>
                        <div>Status: <span className="font-bold text-emerald-400">{c.card_status}</span></div>
                      </div>

                      {/* Card Accounts Sub-list */}
                      <div className="pt-2 border-t border-slate-800/80 space-y-1">
                        <div className="text-[10px] font-bold text-slate-400">Target Accounts for this Card:</div>
                        {(c.card_accounts || []).map((ca: any) => (
                          <div key={ca.id} className="flex justify-between items-center text-[11px] bg-slate-900/60 p-1.5 rounded">
                            <span>
                              ACCT: <strong className="text-sky-300">{ca.account_number}</strong> ({ca.account_type}) · Role: <strong className={ca.account_role === 'PRIMARY' ? 'text-emerald-400' : 'text-slate-300'}>{ca.account_role}</strong>
                            </span>
                            <button onClick={() => handleUnlink(ca.id)} className="text-rose-400 hover:underline text-[10px]">
                              Unlink
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                  {(!selectedCust.cards || selectedCust.cards.length === 0) && (
                    <div className="text-slate-400 text-xs py-3 text-center">No cards issued for this customer.</div>
                  )}
                </div>
              </div>
            </>
          ) : (
            <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-12 text-center text-slate-400 text-xs font-mono">
              Select a customer on the left to view customer accounts, cards, and manage multi-account relationships.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
'''


def apply_fixes():
    print("=" * 75)
    print("  APPLYING CUSTOMER DATA MAINTENANCE & CARD PIN FIXES")
    print("=" * 75)

    # 1. Fix backend/app/seed_data.py
    seed_file = BASE_DIR / "backend" / "app" / "seed_data.py"
    seed_text = seed_file.read_text(encoding="utf-8")
    if "from app.models import (" in seed_text and "    Institution," not in seed_text:
        seed_text = seed_text.replace(
            "from app.models import (",
            "from app.models import (\n    Institution,\n    ProcessingSystem,",
            1,
        )
        seed_file.write_text(seed_text, encoding="utf-8")
        py_compile.compile(str(seed_file), doraise=True)
        print("  [FIXED] backend/app/seed_data.py (Module-level Institution import restored)")

    # 2. Fix backend/app/api_routes.py:
    # - Ensure account deletion cleans up account_ledger when force=True
    # - Add /api/maintenance/search endpoint
    # - Fix create_card to use payload.pin directly
    api_file = BASE_DIR / "backend" / "app" / "api_routes.py"
    api_text = api_file.read_text(encoding="utf-8")

    # Update account delete to cascade ledger
    old_acct_del = "    db.delete(acct)\n    record_audit(db, 'ACCOUNT', account_id, 'DELETE'"
    new_acct_del = (
        "    if force:\n"
        "        db.query(AccountLedger).filter(AccountLedger.account_id == acct.id).delete(synchronize_session=False)\n"
        "        db.query(CardAccount).filter(CardAccount.account_id == acct.id).delete(synchronize_session=False)\n"
        "    db.delete(acct)\n"
        "    record_audit(db, 'ACCOUNT', account_id, 'DELETE'"
    )
    if "db.query(AccountLedger).filter(AccountLedger.account_id == acct.id).delete" not in api_text and old_acct_del in api_text:
        api_text = api_text.replace(old_acct_del, new_acct_del, 1)

    # Add Maintenance Search endpoint at end of api_routes.py
    maintenance_endpoints = '''

# ==============================================================================
# CUSTOMER DATA MAINTENANCE ENDPOINT
# ==============================================================================

@router.get('/maintenance/search')
def search_maintenance_data(q: str = Query(..., min_length=1), db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    term = f"%{q.strip()}%"
    matched_cust_ids = set()

    # Match by Customer fields
    for c in db.query(Customer).filter((Customer.customer_number.ilike(term)) | (Customer.first_name.ilike(term)) | (Customer.last_name.ilike(term)) | (Customer.id == q.strip())).all():
        matched_cust_ids.add(c.id)

    # Match by Account Number
    for a in db.query(Account).filter((Account.account_number.ilike(term)) | (Account.id == q.strip())).all():
        matched_cust_ids.add(a.customer_id)

    # Match by Card PAN
    for crd in db.query(Card).filter((Card.test_pan_reference.ilike(term)) | (Card.masked_pan.ilike(term)) | (Card.id == q.strip())).all():
        matched_cust_ids.add(crd.customer_id)

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
            'mobile_number': cust.mobile_number,
            'risk_category': cust.risk_category,
            'customer_status': cust.customer_status,
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
                'account_status': acct.account_status,
            })
        for card in cust.cards:
            ca_links = []
            for ca in card.card_accounts:
                ca_links.append({
                    'id': ca.id,
                    'account_id': ca.account_id,
                    'account_number': ca.account.account_number if ca.account else None,
                    'account_type': ca.account.account_type if ca.account else None,
                    'account_role': ca.account_role,
                })
            c_dict['cards'].append({
                'id': card.id,
                'test_pan_reference': card.test_pan_reference,
                'masked_pan': card.masked_pan,
                'cardholder_name': card.cardholder_name,
                'expiry_month': card.expiry_month,
                'expiry_year': card.expiry_year,
                'card_status': card.card_status,
                'card_accounts': ca_links,
                'pin_profile': {
                    'pin_offset_reference': card.pin_profile.pin_offset_reference if card.pin_profile else None,
                    'verification_method': card.pin_profile.pin_verification_method if card.pin_profile else 'VISA_PVV',
                } if card.pin_profile else None,
            })
        customers_out.append(c_dict)

    return {'customers': customers_out}
'''
    if "@router.get('/maintenance/search')" not in api_text:
        api_text += maintenance_endpoints

    api_file.write_text(api_text, encoding="utf-8")
    py_compile.compile(str(api_file), doraise=True)
    print("  [FIXED] backend/app/api_routes.py (Account force delete ledger cascade & /maintenance/search)")

    # 3. Create frontend/src/pages/CustomerDataMaintenancePage.tsx
    maint_file = BASE_DIR / "frontend" / "src" / "pages" / "CustomerDataMaintenancePage.tsx"
    maint_file.write_text(MAINTENANCE_PAGE_CODE, encoding="utf-8")
    print("  [CREATED] frontend/src/pages/CustomerDataMaintenancePage.tsx")

    # 4. Update frontend/src/App.tsx
    app_file = BASE_DIR / "frontend" / "src" / "App.tsx"
    app_text = app_file.read_text(encoding="utf-8")
    if "CustomerDataMaintenancePage" not in app_text:
        app_text = app_text.replace(
            "import { InstitutionsAndBinsPage } from './pages/InstitutionsAndBinsPage';",
            "import { InstitutionsAndBinsPage } from './pages/InstitutionsAndBinsPage';\nimport { CustomerDataMaintenancePage } from './pages/CustomerDataMaintenancePage';",
            1,
        )
        app_text = app_text.replace(
            '<Route path="/customers" element={<ProtectedRoute><CustomersPage /></ProtectedRoute>} />',
            '<Route path="/customers" element={<ProtectedRoute><CustomersPage /></ProtectedRoute>} />\n        <Route path="/customer-maintenance" element={<ProtectedRoute><CustomerDataMaintenancePage /></ProtectedRoute>} />',
            1,
        )
        app_file.write_text(app_text, encoding="utf-8")
        print("  [UPDATED] frontend/src/App.tsx (Registered /customer-maintenance)")

    # 5. Update frontend/src/components/Layout.tsx
    layout_file = BASE_DIR / "frontend" / "src" / "components" / "Layout.tsx"
    layout_text = layout_file.read_text(encoding="utf-8")
    if "/customer-maintenance" not in layout_text:
        layout_text = layout_text.replace(
            "  { to: '/customers', label: '2. Customers (CIF)', icon: Users, group: 'CORE BANKING' },",
            "  { to: '/customers', label: '2. Customers (CIF)', icon: Users, group: 'CORE BANKING' },\n  { to: '/customer-maintenance', label: '2.5. Customer Maintenance 360', icon: UserCheck, group: 'CORE BANKING' },",
            1,
        )
        if "UserCheck" not in layout_text:
            layout_text = layout_text.replace("  Users,", "  Users,\n  UserCheck,", 1)
        layout_file.write_text(layout_text, encoding="utf-8")
        print("  [UPDATED] frontend/src/components/Layout.tsx (Added navigation link)")

    print("=" * 75)
    print("  INSTALLATION COMPLETE")
    print("=" * 75)


if __name__ == "__main__":
    apply_fixes()