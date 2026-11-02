#!/usr/bin/env python3
"""
INSTALLER: tools/install_step01_03.py
STEP 1 — Bank, Processing System & BIN Management — Script 3 of 3
Creates:
  1. frontend/src/pages/InstitutionsAndBinsPage.tsx
Modifies:
  - frontend/src/App.tsx (registers /institutions route)
  - frontend/src/components/Layout.tsx (adds navigation item under CORE BANKING)
"""

from pathlib import Path
import sys

BASE_DIR = Path(r"E:\HOST_VSCODE\host-simulator").resolve()
sys.path.insert(0, str(BASE_DIR))

from tools.patcher import PatcherSession, parse_installer_args

INSTITUTIONS_PAGE_CODE = '''import React, { useEffect, useState } from 'react';
import { Landmark, Cpu, Network, CreditCard, Plus, Trash2, Search, CheckCircle2 } from 'lucide-react';
import { apiFetch } from '../api';

export const InstitutionsAndBinsPage: React.FC = () => {
  const [tab, setTab] = useState<'INST' | 'PS' | 'NET' | 'BINS'>('INST');
  const [institutions, setInstitutions] = useState<any[]>([]);
  const [processingSystems, setProcessingSystems] = useState<any[]>([]);
  const [networks, setNetworks] = useState<any[]>([]);
  const [bins, setBins] = useState<any[]>([]);
  const [lookupPan, setLookupPan] = useState('4567890123450001');
  const [lookupResult, setLookupResult] = useState<any>(null);
  const [msg, setMsg] = useState('');

  // Forms state
  const [instForm, setInstForm] = useState({
    institution_code: 'IFIC',
    name: 'IFIC Bank PLC',
    short_name: 'IFIC',
    acquirer_id: '554433',
    forwarding_id: '554433',
    role: 'BOTH',
    ps_code: 'ITCL',
    country_code: '050',
    currency: 'BDT',
    settlement_account_number: 'SETL-IFIC-001',
  });

  const [binForm, setBinForm] = useState({
    bin_prefix: '456795',
    institution_id: '',
    card_type: 'DEBIT',
    card_product: 'VISA_DEBIT_GOLD',
    scheme: 'ITCL',
    is_on_us: true,
  });

  const loadAll = async () => {
    try {
      const [iList, psList, bList] = await Promise.all([
        apiFetch('/institutions'),
        apiFetch('/processing-systems'),
        apiFetch('/bin-ranges'),
      ]);
      setInstitutions(iList);
      setProcessingSystems(psList);
      setBins(bList);
      if (iList.length > 0 && !binForm.institution_id) {
        setBinForm((f) => ({ ...f, institution_id: iList[0].id }));
      }
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    loadAll();
  }, []);

  const handleCreateInstitution = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await apiFetch('/institutions', {
        method: 'POST',
        body: JSON.stringify(instForm),
      });
      setMsg(`Successfully registered institution ${instForm.institution_code} under ITCL switch.`);
      loadAll();
    } catch (err: any) {
      setMsg(`Error: ${err.message}`);
    }
  };

  const handleCreateBin = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await apiFetch('/bin-ranges', {
        method: 'POST',
        body: JSON.stringify(binForm),
      });
      setMsg(`Successfully added BIN range prefix ${binForm.bin_prefix}`);
      loadAll();
    } catch (err: any) {
      setMsg(`Error: ${err.message}`);
    }
  };

  const handleLookupPan = async () => {
    try {
      const res = await apiFetch(`/bin-ranges/lookup/${lookupPan}`);
      setLookupResult(res);
    } catch (err: any) {
      setLookupResult({ found: false, message: err.message });
    }
  };

  const handleDeleteInstitution = async (id: string) => {
    if (!confirm('Are you sure you want to delete this institution?')) return;
    try {
      await apiFetch(`/institutions/${id}`, { method: 'DELETE' });
      setMsg('Institution deleted successfully.');
      loadAll();
    } catch (err: any) {
      setMsg(`Cannot delete: ${err.message}`);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold">Institution, Processing System & BIN Switch Manager</h1>
          <p className="text-xs text-slate-500">
            Manage multi-bank participation under the ITCL-first core switch, external card schemes (Visa/Mastercard/NPSB), and BIN routing tables
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono px-2.5 py-1 rounded bg-emerald-500/10 text-emerald-500 border border-emerald-500/20 font-bold">
            Core Switch: ITCL (Default)
          </span>
        </div>
      </div>

      {msg && (
        <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs font-mono flex justify-between items-center">
          <span>{msg}</span>
          <button onClick={() => setMsg('')} className="text-slate-400 hover:text-white">×</button>
        </div>
      )}

      {/* Tabs */}
      <div className="flex flex-wrap gap-2 border-b border-slate-200 dark:border-slate-800 pb-2">
        {[
          ['INST', '1. Member Banks (Institutions)', Landmark],
          ['PS', '2. Processing Systems (Switches)', Cpu],
          ['NET', '3. Multi-Network Memberships', Network],
          ['BINS', '4. BIN Ranges & PAN Router', CreditCard],
        ].map(([k, label, Icon]: any) => (
          <button
            key={k}
            onClick={() => setTab(k)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-mono font-bold transition ${
              tab === k
                ? 'bg-emerald-600 text-white shadow-sm'
                : 'bg-white dark:bg-slate-900 text-slate-500 hover:text-slate-900 dark:hover:text-white border border-slate-200 dark:border-slate-800'
            }`}
          >
            <Icon size={15} />
            <span>{label}</span>
          </button>
        ))}
      </div>

      {/* TAB 1: INSTITUTIONS */}
      {tab === 'INST' && (
        <div className="space-y-6">
          <form
            onSubmit={handleCreateInstitution}
            className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 grid grid-cols-1 md:grid-cols-4 gap-3"
          >
            <div>
              <label className="block text-[11px] font-mono text-slate-400 mb-1">Institution Code</label>
              <input
                value={instForm.institution_code}
                onChange={(e) => setInstForm({ ...instForm, institution_code: e.target.value })}
                placeholder="e.g. IFIC"
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-2 text-xs font-mono"
                required
              />
            </div>
            <div>
              <label className="block text-[11px] font-mono text-slate-400 mb-1">Bank Name</label>
              <input
                value={instForm.name}
                onChange={(e) => setInstForm({ ...instForm, name: e.target.value })}
                placeholder="Bank Name PLC"
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-2 text-xs"
                required
              />
            </div>
            <div>
              <label className="block text-[11px] font-mono text-slate-400 mb-1">Acquirer ID (DE32)</label>
              <input
                value={instForm.acquirer_id}
                onChange={(e) => setInstForm({ ...instForm, acquirer_id: e.target.value })}
                placeholder="6-digit DE32"
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-2 text-xs font-mono"
                required
              />
            </div>
            <div>
              <label className="block text-[11px] font-mono text-slate-400 mb-1">Primary Host Switch</label>
              <input
                value="ITCL (Default)"
                disabled
                className="w-full bg-slate-100 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-2 text-xs font-mono text-emerald-500"
              />
            </div>
            <div className="md:col-span-4 flex justify-end">
              <button
                type="submit"
                className="flex items-center gap-1.5 bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-lg text-xs font-semibold"
              >
                <Plus size={14} /> Register Bank Under ITCL
              </button>
            </div>
          </form>

          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 overflow-x-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-400">
                  <th className="py-2.5">Code</th>
                  <th className="py-2.5">Bank Name</th>
                  <th className="py-2.5">Acquirer ID (DE32)</th>
                  <th className="py-2.5">Role</th>
                  <th className="py-2.5">Primary Switch</th>
                  <th className="py-2.5">Status</th>
                  <th className="py-2.5">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200/60 dark:divide-slate-800/60">
                {institutions.map((i) => (
                  <tr key={i.id}>
                    <td className="py-2.5 font-bold text-emerald-500">{i.institution_code}</td>
                    <td className="py-2.5 font-sans font-medium">{i.name}</td>
                    <td className="py-2.5">{i.acquirer_id}</td>
                    <td className="py-2.5">{i.role}</td>
                    <td className="py-2.5 text-sky-400 font-bold">{i.ps_code} ({i.ps_name})</td>
                    <td className="py-2.5">
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/10 text-emerald-500">
                        {i.status}
                      </span>
                    </td>
                    <td className="py-2.5">
                      <button
                        onClick={() => handleDeleteInstitution(i.id)}
                        className="text-rose-500 hover:underline flex items-center gap-1 text-[11px]"
                      >
                        <Trash2 size={13} /> Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* TAB 2: PROCESSING SYSTEMS */}
      {tab === 'PS' && (
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 overflow-x-auto">
          <h2 className="text-sm font-bold mb-3">Configured Processing Switches & Schemes</h2>
          <table className="w-full text-left text-xs font-mono">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-400">
                <th className="py-2.5">PS Code</th>
                <th className="py-2.5">Switch Name</th>
                <th className="py-2.5">System Type</th>
                <th className="py-2.5">Message Format</th>
                <th className="py-2.5">Default Host</th>
                <th className="py-2.5">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200/60 dark:divide-slate-800/60">
              {processingSystems.map((ps) => (
                <tr key={ps.id}>
                  <td className="py-2.5 font-bold text-emerald-500">{ps.ps_code}</td>
                  <td className="py-2.5 font-sans font-medium">{ps.name}</td>
                  <td className="py-2.5">{ps.system_type}</td>
                  <td className="py-2.5 text-sky-400">{ps.message_format}</td>
                  <td className="py-2.5">{ps.is_default ? 'YES (ITCL Primary)' : 'NO'}</td>
                  <td className="py-2.5">
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/10 text-emerald-500">
                      {ps.enabled ? 'ENABLED' : 'DISABLED'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* TAB 3: MULTI-NETWORK MEMBERSHIPS */}
      {tab === 'NET' && (
        <div className="space-y-6">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5">
            <h2 className="text-sm font-bold mb-2">Multi-Network Switch Participation</h2>
            <p className="text-xs text-slate-500 mb-4">
              Banks operating on the ITCL core switch can participate in Visa, Mastercard, or NPSB via dedicated member routing IDs.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs font-mono">
              {institutions.map((inst) => (
                <div key={inst.id} className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 space-y-2">
                  <div className="font-bold text-emerald-500">{inst.institution_code} — {inst.name}</div>
                  <div className="text-slate-400 text-[11px]">Primary Switch: {inst.ps_code}</div>
                  <div className="pt-2 border-t border-slate-200 dark:border-slate-800 text-[11px] text-sky-400">
                    Member ID: ITCL-{inst.institution_code}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* TAB 4: BIN RANGES & PAN ROUTER */}
      {tab === 'BINS' && (
        <div className="space-y-6">
          {/* PAN Router Test Tool */}
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 space-y-4">
            <h2 className="text-sm font-bold flex items-center gap-2">
              <Search size={16} className="text-emerald-500" /> Live BIN Prefix PAN Routing Test
            </h2>
            <div className="flex gap-2">
              <input
                value={lookupPan}
                onChange={(e) => setLookupPan(e.target.value)}
                placeholder="Enter 16-digit PAN..."
                className="flex-1 bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono"
              />
              <button
                onClick={handleLookupPan}
                className="bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-lg text-xs font-semibold"
              >
                Lookup PAN Routing
              </button>
            </div>
            {lookupResult && (
              <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono space-y-1">
                {lookupResult.found ? (
                  <>
                    <div className="text-emerald-400 font-bold flex items-center gap-1.5">
                      <CheckCircle2 size={15} /> PAN Routed Successfully
                    </div>
                    <div className="text-slate-300">BIN Prefix: <span className="text-amber-400">{lookupResult.bin_prefix}</span></div>
                    <div className="text-slate-300">Issuing Bank: <span className="text-sky-400">{lookupResult.institution.name} ({lookupResult.institution.code})</span></div>
                    <div className="text-slate-300">Processing System: <span className="text-emerald-400">{lookupResult.processing_system.name}</span></div>
                    <div className="text-slate-300">Card Product: {lookupResult.card_product} ({lookupResult.scheme})</div>
                    <div className="text-slate-300">Routing Type: {lookupResult.is_on_us ? 'ON-US (Internal ITCL)' : 'OFF-US (External Switch)'}</div>
                  </>
                ) : (
                  <div className="text-rose-400">{lookupResult.message}</div>
                )}
              </div>
            )}
          </div>

          {/* Add BIN Form */}
          <form
            onSubmit={handleCreateBin}
            className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 grid grid-cols-1 md:grid-cols-5 gap-3"
          >
            <input
              value={binForm.bin_prefix}
              onChange={(e) => setBinForm({ ...binForm, bin_prefix: e.target.value })}
              placeholder="BIN Prefix (6 digits)"
              maxLength={12}
              className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-2 text-xs font-mono"
              required
            />
            <select
              value={binForm.institution_id}
              onChange={(e) => setBinForm({ ...binForm, institution_id: e.target.value })}
              className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-2 text-xs font-mono"
            >
              {institutions.map((i) => (
                <option key={i.id} value={i.id}>{i.institution_code} — {i.name}</option>
              ))}
            </select>
            <input
              value={binForm.card_product}
              onChange={(e) => setBinForm({ ...binForm, card_product: e.target.value })}
              placeholder="Card Product Name"
              className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-2 text-xs font-mono"
              required
            />
            <select
              value={binForm.scheme}
              onChange={(e) => setBinForm({ ...binForm, scheme: e.target.value })}
              className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-2 text-xs font-mono"
            >
              <option value="ITCL">ITCL Scheme</option>
              <option value="VISA">Visa</option>
              <option value="MASTERCARD">Mastercard</option>
              <option value="NPSB">NPSB</option>
            </select>
            <button
              type="submit"
              className="bg-emerald-600 hover:bg-emerald-500 text-white rounded px-4 py-2 text-xs font-semibold"
            >
              + Add BIN Range
            </button>
          </form>

          {/* BIN Table */}
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 overflow-x-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-400">
                  <th className="py-2.5">BIN Prefix</th>
                  <th className="py-2.5">Issuing Bank</th>
                  <th className="py-2.5">Processing System</th>
                  <th className="py-2.5">Card Product</th>
                  <th className="py-2.5">Scheme</th>
                  <th className="py-2.5">On-Us?</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200/60 dark:divide-slate-800/60">
                {bins.map((b) => (
                  <tr key={b.id}>
                    <td className="py-2.5 font-bold text-emerald-500">{b.bin_prefix}</td>
                    <td className="py-2.5 font-sans font-medium">{b.institution_name} ({b.institution_code})</td>
                    <td className="py-2.5 text-sky-400">{b.ps_code}</td>
                    <td className="py-2.5">{b.card_product}</td>
                    <td className="py-2.5">{b.scheme}</td>
                    <td className="py-2.5">{b.is_on_us ? 'YES' : 'NO'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
'''


def main() -> int:
    args = parse_installer_args("Step 01_03: React Institutions and BIN Manager Page UI + Routing & Navigation")
    session = PatcherSession(
        step_id="step01_03",
        title="Implement Institutions & BINs React Workbench UI and Navigation",
        dry_run=args.dry_run,
    )

    # 1. Write frontend/src/pages/InstitutionsAndBinsPage.tsx
    session.write_file("frontend/src/pages/InstitutionsAndBinsPage.tsx", INSTITUTIONS_PAGE_CODE)

    # 2. Patch frontend/src/App.tsx to add /institutions route
    session.patch_file(
        "frontend/src/App.tsx",
        [
            {
                "marker": "step01_03:app_import_institutions",
                "action": "insert_after",
                "anchor": "import {\n  CustomersPage,\n  CardsPage,\n  AccountsPage,\n  CardLimitsPage,\n  AccountLimitsPage,\n} from './pages/BankingEntities';",
                "text": "import { InstitutionsAndBinsPage } from './pages/InstitutionsAndBinsPage';",
            },
            {
                "marker": "step01_03:app_route_institutions",
                "action": "insert_after",
                "anchor": "        <Route\n          path=\"/accounts\"\n          element={\n            <ProtectedRoute>\n              <AccountsPage />\n            </ProtectedRoute>\n          }\n        />",
                "text": (
                    "        <Route\n"
                    "          path=\"/institutions\"\n          element={\n"
                    "            <ProtectedRoute>\n"
                    "              <InstitutionsAndBinsPage />\n"
                    "            </ProtectedRoute>\n"
                    "          }\n"
                    "        />"
                ),
            },
        ],
    )

    # 3. Patch frontend/src/components/Layout.tsx to add navigation item under CORE BANKING
    session.patch_file(
        "frontend/src/components/Layout.tsx",
        [
            {
                "marker": "step01_03:layout_nav_institutions",
                "action": "insert_after",
                "anchor": "  { to: '/accounts', label: '4. Accounts & Ledger', icon: Landmark, group: 'CORE BANKING' },",
                "text": "  { to: '/institutions', label: '1.5. Banks & Switch BINS', icon: Network, group: 'CORE BANKING' },",
            }
        ],
    )

    session.record_progress(
        completed=[
            "Created React UI page `frontend/src/pages/InstitutionsAndBinsPage.tsx` with 4 interactive tabs (Member Banks, Processing Systems, Multi-Network Memberships, and BIN Ranges + Live PAN Routing Test).",
            "Added `/institutions` route in `frontend/src/App.tsx`.",
            "Added navigation link in `frontend/src/components/Layout.tsx` under CORE BANKING.",
        ],
        remaining=[
            "STEP 2 — Link Institutions to Payment Objects (Customers, Accounts, Cards, HSM Keys) and Transaction Attributes (`issuer_institution_id`, `acquirer_institution_id`, `ps_code`).",
        ],
        modified_files=[
            "frontend/src/pages/InstitutionsAndBinsPage.tsx",
            "frontend/src/App.tsx",
            "frontend/src/components/Layout.tsx",
        ],
    )

    session.record_contracts(
        section_title="Step 1.3 — Institutions & BINs Frontend Workbench",
        contract_items=[
            "**React Route**: `/#/institutions` (`InstitutionsAndBinsPage`)",
            "**Navigation**: Added under 'CORE BANKING' as '1.5. Banks & Switch BINS'.",
            "**Tabs**: Member Banks (defaulting creation to ITCL), Processing Systems, Multi-Network Links, and BIN Prefix PAN Router.",
        ],
    )

    return session.finish()


if __name__ == "__main__":
    sys.exit(main())