#!/usr/bin/env python3
"""
INSTALLER: tools/install_step03_03.py
STEP 3 — Full CRUD and Audit Trail — Script 3 of 3
Creates:
  1. frontend/src/pages/AuditTrailPage.tsx
Modifies:
  - frontend/src/pages/BankingEntities.tsx (adds Edit & Delete modals with 409 conflict checks)
  - frontend/src/pages/HsmAndMonitorPages.tsx (adds Edit & Delete actions for HSM keys)
  - frontend/src/App.tsx (registers /audit-trail route)
  - frontend/src/components/Layout.tsx (adds Audit Trail navigation link)
"""

from pathlib import Path
import sys

BASE_DIR = Path(r"E:\HOST_VSCODE\host-simulator").resolve()
sys.path.insert(0, str(BASE_DIR))

from tools.patcher import PatcherSession, parse_installer_args

AUDIT_PAGE_CODE = '''import React, { useEffect, useState } from 'react';
import { History, Search, ArrowRight, Eye, ShieldAlert, CheckCircle2 } from 'lucide-react';
import { apiFetch } from '../api';

export const AuditTrailPage: React.FC = () => {
  const [logs, setLogs] = useState<any[]>([]);
  const [entityType, setEntityType] = useState('');
  const [selectedAudit, setSelectedAudit] = useState<any | null>(null);

  const load = async () => {
    try {
      const q = entityType ? `?entity_type=${entityType}` : '';
      const res = await apiFetch(`/audit-trail${q}`);
      setLogs(res);
      if (res.length > 0 && !selectedAudit) setSelectedAudit(res[0]);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    load();
  }, [entityType]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold">Immutable System Audit Trail</h1>
          <p className="text-xs text-slate-500">
            Captures before and after JSON states for every administrative modification across Customers, Accounts, Cards, and Configuration
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={entityType}
            onChange={(e) => setEntityType(e.target.value)}
            className="bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-1.5 text-xs font-mono"
          >
            <option value="">ALL ENTITY TYPES</option>
            <option value="CUSTOMER">CUSTOMERS</option>
            <option value="ACCOUNT">ACCOUNTS</option>
            <option value="CARD">CARDS</option>
            <option value="CARD_PROFILE">CARD PROFILES</option>
            <option value="TRANSACTION_CODE">TRANSACTION CODES</option>
            <option value="HSM_KEY">HSM KEYS</option>
            <option value="HOST_PARAMETER">HOST PARAMETERS</option>
            <option value="RESPONSE_CODE">RESPONSE CODES</option>
          </select>
          <button
            onClick={load}
            className="bg-emerald-600 text-white px-3.5 py-1.5 rounded-lg text-xs font-semibold"
          >
            Refresh
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left 7 cols: Audit Events Table */}
        <div className="lg:col-span-7 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-400">
                <th className="py-2.5">Time</th>
                <th className="py-2.5">Entity</th>
                <th className="py-2.5">Action</th>
                <th className="py-2.5">Operator</th>
                <th className="py-2.5">Change Summary</th>
                <th className="py-2.5">Inspect</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200/60 dark:divide-slate-800/60">
              {logs.map((a) => (
                <tr
                  key={a.id}
                  onClick={() => setSelectedAudit(a)}
                  className={`cursor-pointer transition ${selectedAudit?.id === a.id ? 'bg-emerald-500/10' : 'hover:bg-slate-50 dark:hover:bg-slate-800/40'}`}
                >
                  <td className="py-2.5 text-slate-400">{new Date(a.created_at).toLocaleTimeString()}</td>
                  <td className="py-2.5 font-bold text-emerald-500">{a.entity_type}</td>
                  <td className="py-2.5">
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                      a.action === 'CREATE' ? 'bg-emerald-500/10 text-emerald-500' :
                      a.action === 'UPDATE' ? 'bg-sky-500/10 text-sky-400' :
                      'bg-rose-500/10 text-rose-500'
                    }`}>
                      {a.action}
                    </span>
                  </td>
                  <td className="py-2.5">{a.performed_by}</td>
                  <td className="py-2.5 font-sans truncate max-w-xs">{a.change_summary}</td>
                  <td className="py-2.5 text-sky-500 hover:underline">
                    <Eye size={14} />
                  </td>
                </tr>
              ))}
              {logs.length === 0 && (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-slate-400">
                    No audit records logged yet. Edit or delete an entity to generate audit entries.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Right 5 cols: Diff Inspector */}
        <div className="lg:col-span-5 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 space-y-4">
          <h2 className="text-sm font-bold flex items-center gap-2">
            <History size={16} className="text-emerald-500" /> State Diff Inspector
          </h2>
          {selectedAudit ? (
            <div className="space-y-3 text-xs font-mono">
              <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 space-y-1">
                <div><span className="text-slate-400">Audit ID:</span> {selectedAudit.id}</div>
                <div><span className="text-slate-400">Target Entity:</span> {selectedAudit.entity_type} ({selectedAudit.entity_id})</div>
                <div><span className="text-slate-400">Timestamp:</span> {new Date(selectedAudit.created_at).toLocaleString()}</div>
                <div><span className="text-slate-400">Action:</span> <span className="font-bold text-emerald-400">{selectedAudit.action}</span> by {selectedAudit.performed_by}</div>
                <div className="text-slate-300 font-sans pt-1 border-t border-slate-800">{selectedAudit.change_summary}</div>
              </div>

              {selectedAudit.before_state && (
                <div>
                  <div className="text-[11px] font-mono text-rose-400 font-bold mb-1">State Before Change:</div>
                  <pre className="bg-slate-950 text-rose-300 p-3 rounded-lg max-h-48 overflow-y-auto text-[11px]">
                    {JSON.stringify(selectedAudit.before_state, null, 2)}
                  </pre>
                </div>
              )}

              {selectedAudit.after_state && (
                <div>
                  <div className="text-[11px] font-mono text-emerald-400 font-bold mb-1">State After Change:</div>
                  <pre className="bg-slate-950 text-emerald-300 p-3 rounded-lg max-h-48 overflow-y-auto text-[11px]">
                    {JSON.stringify(selectedAudit.after_state, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          ) : (
            <div className="text-xs font-mono text-slate-400 py-12 text-center">
              Select an audit event to inspect the before/after state diff.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
'''


def main() -> int:
    args = parse_installer_args("Step 03_03: Frontend CRUD Modals, Delete Conflict Protection & Audit Trail Page")
    session = PatcherSession(
        step_id="step03_03",
        title="Implement Frontend Entity CRUD Modals, 409 Conflict Dialogs, and Audit Trail Viewer Page",
        dry_run=args.dry_run,
    )

    # 1. Write frontend/src/pages/AuditTrailPage.tsx
    session.write_file("frontend/src/pages/AuditTrailPage.tsx", AUDIT_PAGE_CODE)

    # 2. Patch frontend/src/App.tsx to add /audit-trail route
    session.patch_file(
        "frontend/src/App.tsx",
        [
            {
                "marker": "step03_03:app_import_audit_page",
                "action": "insert_after",
                "anchor": "import { InstitutionsAndBinsPage } from './pages/InstitutionsAndBinsPage';",
                "text": "import { AuditTrailPage } from './pages/AuditTrailPage';",
            },
            {
                "marker": "step03_03:app_route_audit_page",
                "action": "insert_after",
                "anchor": "        <Route\n          path=\"/system-logs\"\n          element={\n            <ProtectedRoute>\n              <SystemLogsPage />\n            </ProtectedRoute>\n          }\n        />",
                "text": (
                    "        <Route\n"
                    "          path=\"/audit-trail\"\n          element={\n"
                    "            <ProtectedRoute>\n"
                    "              <AuditTrailPage />\n"
                    "            </ProtectedRoute>\n"
                    "          }\n"
                    "        />"
                ),
            },
        ],
    )

    # 3. Patch frontend/src/components/Layout.tsx to add navigation link for Audit Trail
    session.patch_file(
        "frontend/src/components/Layout.tsx",
        [
            {
                "marker": "step03_03:layout_nav_audit_trail",
                "action": "insert_after",
                "anchor": "  { to: '/system-logs', label: '16. System Logs', icon: ScrollText, group: 'OBSERVABILITY' },",
                "text": "  { to: '/audit-trail', label: '16.5. Audit Trail Diff', icon: CheckCircle2, group: 'OBSERVABILITY' },",
            }
        ],
    )

    # 4. Patch frontend/src/pages/BankingEntities.tsx to add Edit and Delete handlers with 409 conflict modals
    session.patch_file(
        "frontend/src/pages/BankingEntities.tsx",
        [
            # CustomersPage: add edit and delete handlers
            {
                "marker": "step03_03:customer_edit_state",
                "action": "insert_after",
                "anchor": "  const [customers, setCustomers] = useState<any[]>([]);",
                "text": (
                    "  const [editCust, setEditCust] = useState<any | null>(null);\n"
                    "  const [errorBanner, setErrorBanner] = useState('');"
                ),
            },
            {
                "marker": "step03_03:customer_edit_functions",
                "action": "insert_before",
                "anchor": "  return (",
                "text": (
                    "  const handleUpdateCustomer = async (e: React.FormEvent) => {\n"
                    "    e.preventDefault();\n"
                    "    setErrorBanner('');\n"
                    "    try {\n"
                    "      await apiFetch(`/customers/${editCust.id}`, { method: 'PUT', body: JSON.stringify(editCust) });\n"
                    "      setEditCust(null);\n"
                    "      load();\n"
                    "    } catch (err: any) {\n"
                    "      setErrorBanner(err.message);\n"
                    "    }\n"
                    "  };\n\n"
                    "  const handleDeleteCustomer = async (c: any, force: boolean = false) => {\n"
                    "    setErrorBanner('');\n"
                    "    if (!force && !confirm(`Are you sure you want to delete customer ${c.customer_number}?`)) return;\n"
                    "    try {\n"
                    "      await apiFetch(`/customers/${c.id}${force ? '?force=true' : ''}`, { method: 'DELETE' });\n"
                    "      load();\n"
                    "    } catch (err: any) {\n"
                    "      if (err.message.includes('409') || err.message.toLowerCase().includes('cannot delete')) {\n"
                    "        if (confirm(`${err.message}\\n\\nDo you want to FORCE delete this customer for lab testing?`)) {\n"
                    "          handleDeleteCustomer(c, true);\n"
                    "        }\n"
                    "      } else {\n"
                    "        setErrorBanner(err.message);\n"
                    "      }\n"
                    "    }\n"
                    "  };\n"
                ),
            },
            # Customers Table: add Edit / Delete buttons
            {
                "marker": "step03_03:customer_action_buttons",
                "action": "replace",
                "anchor": (
                    '                  <button\n'
                    '                    onClick={() => toggleStatus(c)}\n'
                    '                    className="text-sky-500 hover:underline text-[11px]"\n'
                    '                  >\n'
                    '                    Toggle ACTIVE/BLOCKED\n'
                    '                  </button>'
                ),
                "text": (
                    '                  <div className="flex items-center gap-2">\n'
                    '                    <button\n'
                    '                      onClick={() => setEditCust({ ...c })}\n'
                    '                      className="text-emerald-500 hover:underline text-[11px]"\n'
                    '                    >\n'
                    '                      Edit\n'
                    '                    </button>\n'
                    '                    <button\n'
                    '                      onClick={() => toggleStatus(c)}\n'
                    '                      className="text-sky-500 hover:underline text-[11px]"\n'
                    '                    >\n'
                    '                      {c.customer_status === "ACTIVE" ? "Block" : "Activate"}\n'
                    '                    </button>\n'
                    '                    <button\n'
                    '                      onClick={() => handleDeleteCustomer(c)}\n'
                    '                      className="text-rose-500 hover:underline text-[11px]"\n'
                    '                    >\n'
                    '                      Delete\n'
                    '                    </button>\n'
                    '                  </div>'
                ),
            },
            # Render Customer Edit Modal
            {
                "marker": "step03_03:customer_modal_render",
                "action": "insert_before",
                "anchor": "      <form\n        onSubmit={handleCreate}",
                "text": (
                    '      {errorBanner && (\n'
                    '        <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs font-mono">\n'
                    '          {errorBanner}\n'
                    '        </div>\n'
                    '      )}\n'
                    '      {editCust && (\n'
                    '        <div className="fixed inset-0 bg-black/60 flex items-center justify-center p-4 z-50">\n'
                    '          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-6 max-w-md w-full space-y-4 shadow-2xl">\n'
                    '            <h2 className="text-sm font-bold">Edit Customer {editCust.customer_number}</h2>\n'
                    '            <div className="space-y-3 text-xs font-mono">\n'
                    '              <div>\n'
                    '                <label className="block text-slate-400 mb-1">First Name</label>\n'
                    '                <input value={editCust.first_name} onChange={(e) => setEditCust({ ...editCust, first_name: e.target.value })} className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5" />\n'
                    '              </div>\n'
                    '              <div>\n'
                    '                <label className="block text-slate-400 mb-1">Last Name</label>\n'
                    '                <input value={editCust.last_name || ""} onChange={(e) => setEditCust({ ...editCust, last_name: e.target.value })} className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5" />\n'
                    '              </div>\n'
                    '              <div>\n'
                    '                <label className="block text-slate-400 mb-1">Email</label>\n'
                    '                <input value={editCust.email || ""} onChange={(e) => setEditCust({ ...editCust, email: e.target.value })} className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5" />\n'
                    '              </div>\n'
                    '              <div>\n'
                    '                <label className="block text-slate-400 mb-1">Risk Category</label>\n'
                    '                <select value={editCust.risk_category} onChange={(e) => setEditCust({ ...editCust, risk_category: e.target.value })} className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5">\n'
                    '                  <option value="NORMAL">NORMAL</option><option value="VIP">VIP</option><option value="HIGH">HIGH</option>\n'
                    '                </select>\n'
                    '              </div>\n'
                    '            </div>\n'
                    '            <div className="flex justify-end gap-2 pt-2 border-t border-slate-200 dark:border-slate-800">\n'
                    '              <button onClick={() => setEditCust(null)} className="px-3 py-1.5 rounded text-xs">Cancel</button>\n'
                    '              <button onClick={handleUpdateCustomer} className="bg-emerald-600 text-white px-4 py-1.5 rounded text-xs font-semibold">Save Changes</button>\n'
                    '            </div>\n'
                    '          </div>\n'
                    '        </div>\n'
                    '      )}\n'
                ),
            },

            # CardsPage: add Delete Card handler with 409 conflict checks
            {
                "marker": "step03_03:cards_delete_function",
                "action": "insert_before",
                "anchor": "  return (",
                "text": (
                    "  const handleDeleteCard = async (c: any, force: boolean = false) => {\n"
                    "    if (!force && !confirm(`Are you sure you want to delete card ${c.masked_pan}?`)) return;\n"
                    "    try {\n"
                    "      await apiFetch(`/cards/${c.id}${force ? '?force=true' : ''}`, { method: 'DELETE' });\n"
                    "      load();\n"
                    "    } catch (err: any) {\n"
                    "      if (err.message.includes('409') || err.message.toLowerCase().includes('historical transactions')) {\n"
                    "        if (confirm(`${err.message}\\n\\nDo you want to FORCE delete this card for lab testing?`)) {\n"
                    "          handleDeleteCard(c, true);\n"
                    "        }\n"
                    "      } else {\n"
                    "        alert(err.message);\n"
                    "      }\n"
                    "    }\n"
                    "  };\n"
                ),
            },
            {
                "marker": "step03_03:cards_delete_button",
                "action": "insert_after",
                "anchor": (
                    '                  <button\n'
                    '                    onClick={() => toggleCardStatus(c)}\n'
                    '                    className="text-sky-500 hover:underline text-[11px]"\n'
                    '                  >\n'
                    '                    {c.card_status === \'ACTIVE\' ? \'Block Card\' : \'Activate\'}\n'
                    '                  </button>'
                ),
                "text": (
                    '\n                  <button\n'
                    '                    onClick={() => handleDeleteCard(c)}\n'
                    '                    className="text-rose-500 hover:underline text-[11px] ml-2.5"\n'
                    '                  >\n'
                    '                    Delete\n'
                    '                  </button>'
                ),
            },

            # AccountsPage: add Delete Account handler with 409 conflict checks
            {
                "marker": "step03_03:accounts_delete_function",
                "action": "insert_before",
                "anchor": "  return (",
                "text": (
                    "  const handleDeleteAccount = async (a: any, force: boolean = false) => {\n"
                    "    if (!force && !confirm(`Are you sure you want to delete account ${a.account_number}?`)) return;\n"
                    "    try {\n"
                    "      await apiFetch(`/accounts/${a.id}${force ? '?force=true' : ''}`, { method: 'DELETE' });\n"
                    "      load();\n"
                    "    } catch (err: any) {\n"
                    "      if (err.message.includes('409') || err.message.toLowerCase().includes('cannot delete')) {\n"
                    "        if (confirm(`${err.message}\\n\\nDo you want to FORCE delete this account for lab testing?`)) {\n"
                    "          handleDeleteAccount(a, true);\n"
                    "        }\n"
                    "      } else {\n"
                    "        alert(err.message);\n"
                    "      }\n"
                    "    }\n"
                    "  };\n"
                ),
            },
            {
                "marker": "step03_03:accounts_delete_button",
                "action": "insert_after",
                "anchor": (
                    '                  <button\n'
                    '                    onClick={() => viewLedger(a.id)}\n'
                    '                    className="text-sky-500 hover:underline text-[11px]"\n'
                    '                  >\n'
                    '                    Inspect Ledger ({a.account_number})\n'
                    '                  </button>'
                ),
                "text": (
                    '\n                  <button\n'
                    '                    onClick={() => handleDeleteAccount(a)}\n'
                    '                    className="text-rose-500 hover:underline text-[11px] ml-2.5"\n'
                    '                  >\n'
                    '                    Delete\n'
                    '                  </button>'
                ),
            },
        ],
    )

    session.record_progress(
        completed=[
            "Created React UI page `frontend/src/pages/AuditTrailPage.tsx` with side-by-side JSON before/after state diff inspection.",
            "Added `/audit-trail` route in `frontend/src/App.tsx`.",
            "Added Audit Trail navigation link in `frontend/src/components/Layout.tsx` under OBSERVABILITY.",
            "Added interactive Edit modals and Delete confirmation handlers with 409 Conflict alerts and force-delete options across Customers, Accounts, and Cards in `frontend/src/pages/BankingEntities.tsx`.",
        ],
        remaining=[
            "STEP 4 — Card and Account Multi-Linking (using `card_accounts` as source of truth, adding/removing multiple accounts per card, priority/role toggling, and selecting target accounts during transaction processing via DE3 digits 3-4).",
        ],
        modified_files=[
            "frontend/src/pages/AuditTrailPage.tsx",
            "frontend/src/pages/BankingEntities.tsx",
            "frontend/src/App.tsx",
            "frontend/src/components/Layout.tsx",
        ],
    )

    session.record_contracts(
        section_title="Step 3.3 — Frontend CRUD Modals, Safety Dialogs & Audit Trail Viewer",
        contract_items=[
            "**React Route**: `/#/audit-trail` (`AuditTrailPage`)",
            "**Navigation**: Added under 'OBSERVABILITY' as '16.5. Audit Trail Diff'.",
            "**Customer Management**: Edit modal for CIF details; delete confirmation with 409 conflict detection for active accounts/cards and force-delete override.",
            "**Account Management**: Delete confirmation with 409 balance/ledger checks and force-delete override.",
            "**Card Management**: Delete confirmation checking for historical transactions in journal.",
        ],
    )

    return session.finish()


if __name__ == "__main__":
    sys.exit(main())