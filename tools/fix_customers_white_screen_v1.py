#!/usr/bin/env python3
"""
tools/fix_customers_white_screen.py
====================================
FIX: /#/customers is a blank/black page.

Root cause (confirmed):
  CustomersPage in BankingEntities.tsx contains:
    1. A dead function handleUpdateAccount that uses undeclared `editAcct`
    2. JSX:  {editAcct && ( ... modal ... )}

  Because `editAcct` is evaluated during every render and was never declared
  with useState, JavaScript throws ReferenceError → React dies → white/black page.

This script replaces the entire broken CustomersPage with a clean, working version.
Idempotent and safe to run multiple times.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve()
# Project root = parent of tools/ if script lives in tools/, else current dir
if SCRIPT.parent.name == "tools":
    ROOT = SCRIPT.parent.parent
else:
    ROOT = Path.cwd()

TARGET = ROOT / "frontend" / "src" / "pages" / "BankingEntities.tsx"

CLEAN_CUSTOMERS_PAGE = r'''export const CustomersPage: React.FC = () => {
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
      setErrorBanner('');
      const q = searchTerm ? `&q=${encodeURIComponent(searchTerm)}` : '';
      const [cRes, iList] = await Promise.all([
        apiFetch(`/customers?page=${page}&page_size=15${q}`),
        apiFetch('/institutions').catch(() => []),
      ]);
      const items = Array.isArray(cRes) ? cRes : (cRes?.items || []);
      setCustomers(items);
      setTotalCount(cRes?.total ?? items.length);
      setTotalPages(cRes?.total_pages || 1);
      const inst = Array.isArray(iList) ? iList : [];
      setInstitutions(inst);
      if (!form.institution_id && inst.length > 0) {
        setForm((prev) => ({ ...prev, institution_id: inst[0].id }));
      }
    } catch (err: any) {
      console.error(err);
      setErrorBanner(err?.message || 'Failed to load customers');
      setCustomers([]);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setErrorBanner('');
      await apiFetch('/customers', { method: 'POST', body: JSON.stringify(form) });
      setForm({
        ...form,
        customer_number: `CUST-${Math.floor(1006 + Math.random() * 9000)}`,
        first_name: '',
        last_name: '',
      });
      load();
    } catch (err: any) {
      setErrorBanner(err.message || 'Create failed');
    }
  };

  const handleUpdateCustomer = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editCust) return;
    setErrorBanner('');
    try {
      await apiFetch(`/customers/${editCust.id}`, {
        method: 'PUT',
        body: JSON.stringify({
          first_name: editCust.first_name,
          last_name: editCust.last_name,
          email: editCust.email,
          mobile_number: editCust.mobile_number,
          risk_category: editCust.risk_category,
          customer_status: editCust.customer_status,
        }),
      });
      setEditCust(null);
      load();
    } catch (err: any) {
      setErrorBanner(err.message || 'Update failed');
    }
  };

  const handleDeleteCustomer = async (c: any, force: boolean = false) => {
    setErrorBanner('');
    if (!force && !confirm(`Are you sure you want to delete customer ${c.customer_number}?`)) return;
    try {
      await apiFetch(`/customers/${c.id}${force ? '?force=true' : ''}`, { method: 'DELETE' });
      load();
    } catch (err: any) {
      const msg = err.message || '';
      if (msg.includes('409') || msg.toLowerCase().includes('cannot delete')) {
        if (confirm(`${msg}\n\nDo you want to FORCE delete this customer for lab testing?`)) {
          handleDeleteCustomer(c, true);
        }
      } else {
        setErrorBanner(msg);
      }
    }
  };

  const toggleStatus = async (c: any) => {
    try {
      const next = c.customer_status === 'ACTIVE' ? 'BLOCKED' : 'ACTIVE';
      await apiFetch(`/customers/${c.id}/status?status=${next}`, { method: 'PATCH' });
      load();
    } catch (err: any) {
      setErrorBanner(err.message || 'Status change failed');
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold">Customer Management (CIF)</h1>
        <p className="text-xs text-slate-500">
          Create, manage, and audit synthetic banking host customers across member banks
        </p>
      </div>

      {errorBanner && (
        <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs font-mono flex items-center justify-between gap-2">
          <span>{errorBanner}</span>
          <button type="button" onClick={() => setErrorBanner('')} className="opacity-70 hover:opacity-100">
            ✕
          </button>
        </div>
      )}

      {/* Edit Customer Modal */}
      {editCust && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center p-4 z-50">
          <form
            onSubmit={handleUpdateCustomer}
            className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-6 max-w-md w-full space-y-4 shadow-2xl"
          >
            <h2 className="text-sm font-bold">Edit Customer {editCust.customer_number}</h2>
            <div className="space-y-3 text-xs font-mono">
              <div>
                <label className="block text-slate-400 mb-1">First Name</label>
                <input
                  value={editCust.first_name || ''}
                  onChange={(e) => setEditCust({ ...editCust, first_name: e.target.value })}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5"
                  required
                />
              </div>
              <div>
                <label className="block text-slate-400 mb-1">Last Name</label>
                <input
                  value={editCust.last_name || ''}
                  onChange={(e) => setEditCust({ ...editCust, last_name: e.target.value })}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5"
                />
              </div>
              <div>
                <label className="block text-slate-400 mb-1">Email</label>
                <input
                  value={editCust.email || ''}
                  onChange={(e) => setEditCust({ ...editCust, email: e.target.value })}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5"
                />
              </div>
              <div>
                <label className="block text-slate-400 mb-1">Mobile</label>
                <input
                  value={editCust.mobile_number || ''}
                  onChange={(e) => setEditCust({ ...editCust, mobile_number: e.target.value })}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5"
                />
              </div>
              <div>
                <label className="block text-slate-400 mb-1">Risk Category</label>
                <select
                  value={editCust.risk_category || 'NORMAL'}
                  onChange={(e) => setEditCust({ ...editCust, risk_category: e.target.value })}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5"
                >
                  <option value="NORMAL">NORMAL</option>
                  <option value="VIP">VIP</option>
                  <option value="HIGH">HIGH</option>
                </select>
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t border-slate-200 dark:border-slate-800">
              <button type="button" onClick={() => setEditCust(null)} className="px-3 py-1.5 rounded text-xs">
                Cancel
              </button>
              <button
                type="submit"
                className="bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-1.5 rounded text-xs font-semibold"
              >
                Save Changes
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Create form */}
      <form
        onSubmit={handleCreate}
        className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 grid grid-cols-1 md:grid-cols-7 gap-3"
      >
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
          {institutions.length === 0 && <option value="">No banks loaded</option>}
          {institutions.map((inst: any) => (
            <option key={inst.id} value={inst.id}>
              {inst.institution_code} — {inst.short_name || inst.name}
            </option>
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
        <button
          type="submit"
          className="bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg px-4 py-2 text-xs font-semibold"
        >
          + Create Customer
        </button>
      </form>

      {/* Search + pagination */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4">
        <div className="flex items-center gap-2 flex-1 max-w-md">
          <input
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                setPage(1);
                load();
              }
            }}
            placeholder="Search customer no, name, phone, or email..."
            className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-1.5 text-xs font-mono"
          />
          <button
            type="button"
            onClick={() => {
              setPage(1);
              load();
            }}
            className="bg-emerald-600 text-white px-3 py-1.5 rounded-lg text-xs font-semibold"
          >
            Search
          </button>
        </div>
        <div className="flex items-center gap-2 text-xs font-mono text-slate-400">
          <span>
            Total: <strong className="text-emerald-500">{totalCount}</strong>
          </span>
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
            className="px-2.5 py-1 rounded border border-slate-300 dark:border-slate-700 disabled:opacity-40"
          >
            Prev
          </button>
          <span>
            Page {page} of {totalPages}
          </span>
          <button
            type="button"
            disabled={page >= totalPages}
            onClick={() => setPage(page + 1)}
            className="px-2.5 py-1 rounded border border-slate-300 dark:border-slate-700 disabled:opacity-40"
          >
            Next
          </button>
        </div>
      </div>

      {/* Table */}
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
            {customers.length === 0 && (
              <tr>
                <td colSpan={7} className="py-8 text-center text-slate-400">
                  No customers found. Create one above or adjust search.
                </td>
              </tr>
            )}
            {customers.map((c: any) => (
              <tr key={c.id}>
                <td className="py-2.5 font-bold text-emerald-500">{c.customer_number}</td>
                <td className="py-2.5 text-sky-400 font-bold">{c.institution_code || 'XBANK'}</td>
                <td className="py-2.5 font-sans font-medium">
                  {c.first_name} {c.last_name}
                </td>
                <td className="py-2.5">{c.mobile_number}</td>
                <td className="py-2.5">{c.risk_category}</td>
                <td className="py-2.5">
                  <span
                    className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                      c.customer_status === 'ACTIVE'
                        ? 'bg-emerald-500/10 text-emerald-500'
                        : 'bg-rose-500/10 text-rose-500'
                    }`}
                  >
                    {c.customer_status}
                  </span>
                </td>
                <td className="py-2.5">
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setEditCust({ ...c })}
                      className="text-emerald-500 hover:underline text-[11px]"
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      onClick={() => toggleStatus(c)}
                      className="text-sky-500 hover:underline text-[11px]"
                    >
                      {c.customer_status === 'ACTIVE' ? 'Block' : 'Activate'}
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDeleteCustomer(c)}
                      className="text-rose-500 hover:underline text-[11px]"
                    >
                      Delete
                    </button>
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

'''


def main() -> int:
    dry = "--dry-run" in sys.argv

    print("=" * 70)
    print("  FIX: /#/customers white/black screen (undeclared editAcct)")
    print("=" * 70)
    print(f"  Target: {TARGET}")

    if not TARGET.exists():
        print(f"\n  [ERROR] File not found: {TARGET}")
        print("  Run this script from your host-simulator project root")
        print("  (the folder that contains frontend/ and tools/).")
        return 1

    text = TARGET.read_text(encoding="utf-8")

    # Already fixed?
    c_start = text.find("export const CustomersPage")
    c_end = text.find("export const CardsPage")
    if c_start >= 0 and c_end > c_start:
        segment = text[c_start:c_end]
        if "editAcct" not in segment and "handleUpdateAccount" not in segment:
            print("  [OK] editAcct / handleUpdateAccount already gone — page should work.")
            print("  If still blank, hard-refresh browser (Ctrl+Shift+R) and check F12 console.")
            return 0

    if "editAcct" in text:
        print("  [FOUND] Broken editAcct references — replacing CustomersPage...")
    else:
        print("  [INFO] Replacing CustomersPage with clean version...")

    # Replace from "export const CustomersPage" up to (but not including) "export const CardsPage"
    pattern = re.compile(
        r"export const CustomersPage: React\.FC = \(\) => \{.*?"
        r"(?=export const CardsPage)",
        re.DOTALL,
    )

    match = pattern.search(text)
    if not match:
        print("  [ERROR] Could not locate CustomersPage block (export const CustomersPage ... CardsPage).")
        print("  Manual fix: open frontend/src/pages/BankingEntities.tsx and delete every line")
        print("  that contains 'editAcct' or 'handleUpdateAccount' inside CustomersPage.")
        return 1

    new_text = pattern.sub(CLEAN_CUSTOMERS_PAGE + "\n\n", text, count=1)

    # Verify clean
    c_start = new_text.find("export const CustomersPage")
    c_end = new_text.find("export const CardsPage")
    segment = new_text[c_start:c_end]
    if "editAcct" in segment or "handleUpdateAccount" in segment:
        print("  [ERROR] Replacement still contains editAcct — aborting write.")
        return 1

    if dry:
        print("  [DRY-RUN] Would write clean CustomersPage (no editAcct).")
        print("  Re-run without --dry-run to apply.")
        return 0

    TARGET.write_text(new_text, encoding="utf-8", newline="\n")
    print("  [WRITE] frontend/src/pages/BankingEntities.tsx")
    print()
    print("  DONE. Next steps:")
    print("    1. If Vite is running, it should hot-reload.")
    print("    2. Hard refresh the browser: Ctrl+Shift+R (or Cmd+Shift+R)")
    print("    3. Open http://localhost:5173/#/customers")
    print("    4. If still blank, open F12 → Console and paste any red error here.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
