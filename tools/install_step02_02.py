#!/usr/bin/env python3
"""
INSTALLER: tools/install_step02_02.py
STEP 2 — Link Institutions to Payment Objects & Transaction Attributes — Script 2 of 2
Updates:
  1. frontend/src/pages/BankingEntities.tsx (adds institution dropdowns & bank badges to Customers, Accounts, Cards)
  2. frontend/src/pages/SimulatorAndJournal.tsx (adds On-Us/Off-Us, ps_code, and Bank badges to Simulator & Journal)
  3. frontend/src/pages/HsmAndMonitorPages.tsx (adds institution selector to Key Management)
"""

from pathlib import Path
import sys

BASE_DIR = Path(r"E:\HOST_VSCODE\host-simulator").resolve()
sys.path.insert(0, str(BASE_DIR))

from tools.patcher import PatcherSession, parse_installer_args


def main() -> int:
    args = parse_installer_args("Step 02_02: Frontend Entity Forms, Badges, and Transaction Journal Updates")
    session = PatcherSession(
        step_id="step02_02",
        title="Update Frontend Pages with Institution Selectors, Bank Badges, and On-Us/Off-Us Routing Flags",
        dry_run=args.dry_run,
    )

    # 1. Patch frontend/src/pages/BankingEntities.tsx
    # Add institutions state and select dropdown to CustomersPage
    session.patch_file(
        "frontend/src/pages/BankingEntities.tsx",
        [
            # CustomersPage: fetch institutions and add institution_id to form
            {
                "marker": "step02_02:customers_inst_state",
                "action": "insert_after",
                "anchor": "  const [customers, setCustomers] = useState<any[]>([]);",
                "text": "  const [institutions, setInstitutions] = useState<any[]>([]);",
            },
            {
                "marker": "step02_02:customers_inst_form_field",
                "action": "insert_after",
                "anchor": "    risk_category: 'NORMAL',",
                "text": "    institution_id: '',",
            },
            {
                "marker": "step02_02:customers_inst_fetch",
                "action": "replace",
                "anchor": "  const load = async () => setCustomers(await apiFetch('/customers'));",
                "text": (
                    "  const load = async () => {\n"
                    "    const [cList, iList] = await Promise.all([apiFetch('/customers'), apiFetch('/institutions')]);\n"
                    "    setCustomers(cList);\n"
                    "    setInstitutions(iList);\n"
                    "    if (!form.institution_id && iList.length > 0) {\n"
                    "      setForm((prev) => ({ ...prev, institution_id: iList[0].id }));\n"
                    "    }\n"
                    "  };"
                ),
            },
            {
                "marker": "step02_02:customers_inst_dropdown",
                "action": "insert_after",
                "anchor": '        <input\n          value={form.customer_number}\n          onChange={(e) => setForm({ ...form, customer_number: e.target.value })}\n          placeholder="Customer Number"\n          className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono"\n          required\n        />',
                "text": (
                    '        <select\n'
                    '          value={form.institution_id}\n'
                    '          onChange={(e) => setForm({ ...form, institution_id: e.target.value })}\n'
                    '          className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono"\n'
                    '        >\n'
                    '          {institutions.map((inst) => (\n'
                    '            <option key={inst.id} value={inst.id}>{inst.institution_code} — {inst.short_name || inst.name}</option>\n'
                    '          ))}\n'
                    '        </select>'
                ),
            },
            # Customers Table: add Bank column header & row cell
            {
                "marker": "step02_02:customers_table_inst_th",
                "action": "insert_after",
                "anchor": '              <th className="py-2.5">Customer No</th>',
                "text": '              <th className="py-2.5">Bank</th>',
            },
            {
                "marker": "step02_02:customers_table_inst_td",
                "action": "insert_after",
                "anchor": '                <td className="py-2.5 font-bold text-emerald-500">{c.customer_number}</td>',
                "text": '                <td className="py-2.5 text-sky-400 font-bold">{c.institution_code || "XBANK"}</td>',
            },

            # CardsPage: fetch institutions and add institution_id to form
            {
                "marker": "step02_02:cards_inst_state",
                "action": "insert_after",
                "anchor": "  const [accounts, setAccounts] = useState<any[]>([]);",
                "text": "  const [institutions, setInstitutions] = useState<any[]>([]);",
            },
            {
                "marker": "step02_02:cards_inst_form_field",
                "action": "insert_after",
                "anchor": "    card_product: 'VISA_DEBIT_CLASSIC',",
                "text": "    institution_id: '',",
            },
            {
                "marker": "step02_02:cards_inst_load",
                "action": "replace",
                "anchor": (
                    "    const [cList, custList, acctList] = await Promise.all([\n"
                    "      apiFetch('/cards'),\n"
                    "      apiFetch('/customers'),\n"
                    "      apiFetch('/accounts'),\n"
                    "    ]);\n"
                    "    setCards(cList);\n"
                    "    setCustomers(custList);\n"
                    "    setAccounts(acctList);"
                ),
                "text": (
                    "    const [cList, custList, acctList, iList] = await Promise.all([\n"
                    "      apiFetch('/cards'),\n"
                    "      apiFetch('/customers'),\n"
                    "      apiFetch('/accounts'),\n"
                    "      apiFetch('/institutions'),\n"
                    "    ]);\n"
                    "    setCards(cList);\n"
                    "    setCustomers(custList);\n"
                    "    setAccounts(acctList);\n"
                    "    setInstitutions(iList);\n"
                    "    if (!form.institution_id && iList.length > 0) {\n"
                    "      setForm((f) => ({ ...f, institution_id: iList[0].id }));\n"
                    "    }"
                ),
            },
            {
                "marker": "step02_02:cards_inst_dropdown",
                "action": "insert_after",
                "anchor": (
                    '          {accounts.map((a) => (\n'
                    '            <option key={a.id} value={a.id}>\n'
                    '              ACCT {a.account_number} ({a.currency})\n'
                    '            </option>\n'
                    '          ))}\n'
                    '        </select>'
                ),
                "text": (
                    '        <select\n'
                    '          value={form.institution_id}\n'
                    '          onChange={(e) => setForm({ ...form, institution_id: e.target.value })}\n'
                    '          className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono"\n'
                    '        >\n'
                    '          {institutions.map((i) => (\n'
                    '            <option key={i.id} value={i.id}>{i.institution_code} — {i.short_name || i.name}</option>\n'
                    '          ))}\n'
                    '        </select>'
                ),
            },
            # Cards Table: add Bank column header & row cell
            {
                "marker": "step02_02:cards_table_inst_th",
                "action": "insert_after",
                "anchor": '              <th className="py-2.5">Sim Ref (Test Only)</th>',
                "text": '              <th className="py-2.5">Bank</th>',
            },
            {
                "marker": "step02_02:cards_table_inst_td",
                "action": "insert_after",
                "anchor": '                <td className="py-2.5 text-slate-400">{c.test_pan_reference}</td>',
                "text": '                <td className="py-2.5 text-sky-400 font-bold">{c.institution_code || "XBANK"}</td>',
            },

            # AccountsPage: fetch institutions and add institution_id to form
            {
                "marker": "step02_02:accounts_inst_state",
                "action": "insert_after",
                "anchor": "  const [customers, setCustomers] = useState<any[]>([]);",
                "text": "  const [institutions, setInstitutions] = useState<any[]>([]);",
            },
            {
                "marker": "step02_02:accounts_inst_form_field",
                "action": "insert_after",
                "anchor": "    overdraft_limit: '0.00',",
                "text": "    institution_id: '',",
            },
            {
                "marker": "step02_02:accounts_inst_load",
                "action": "replace",
                "anchor": "    const [aList, cList] = await Promise.all([apiFetch('/accounts'), apiFetch('/customers')]);\n    setAccounts(aList);\n    setCustomers(cList);",
                "text": (
                    "    const [aList, cList, iList] = await Promise.all([apiFetch('/accounts'), apiFetch('/customers'), apiFetch('/institutions')]);\n"
                    "    setAccounts(aList);\n"
                    "    setCustomers(cList);\n"
                    "    setInstitutions(iList);\n"
                    "    if (!form.institution_id && iList.length > 0) {\n"
                    "      setForm((f) => ({ ...f, institution_id: iList[0].id }));\n"
                    "    }"
                ),
            },
            {
                "marker": "step02_02:accounts_inst_dropdown",
                "action": "insert_after",
                "anchor": (
                    '          {customers.map((c) => (\n'
                    '            <option key={c.id} value={c.id}>\n'
                    '              {c.customer_number} - {c.first_name}\n'
                    '            </option>\n'
                    '          ))}\n'
                    '        </select>'
                ),
                "text": (
                    '        <select\n'
                    '          value={form.institution_id}\n'
                    '          onChange={(e) => setForm({ ...form, institution_id: e.target.value })}\n'
                    '          className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono"\n'
                    '        >\n'
                    '          {institutions.map((i) => (\n'
                    '            <option key={i.id} value={i.id}>{i.institution_code} — {i.short_name || i.name}</option>\n'
                    '          ))}\n'
                    '        </select>'
                ),
            },
            # Accounts Table: add Bank column header & row cell
            {
                "marker": "step02_02:accounts_table_inst_th",
                "action": "insert_after",
                "anchor": '              <th className="py-2.5">Customer</th>',
                "text": '              <th className="py-2.5">Bank</th>',
            },
            {
                "marker": "step02_02:accounts_table_inst_td",
                "action": "insert_after",
                "anchor": '                <td className="py-2.5 font-sans">{a.customer_name}</td>',
                "text": '                <td className="py-2.5 text-sky-400 font-bold">{a.institution_code || "XBANK"}</td>',
            },
        ],
    )

    # 2. Patch frontend/src/pages/SimulatorAndJournal.tsx
    session.patch_file(
        "frontend/src/pages/SimulatorAndJournal.tsx",
        [
            # Simulator outcome: display ps_code and On-Us badge
            {
                "marker": "step02_02:sim_outcome_routing_badges",
                "action": "insert_after",
                "anchor": (
                    '                <div className="p-2 rounded bg-slate-50 dark:bg-slate-950">\n'
                    '                  <span className="text-slate-400">Response MTI:</span> {txResponse.response_mti}\n'
                    '                </div>'
                ),
                "text": (
                    '                <div className="p-2 rounded bg-slate-50 dark:bg-slate-950">\n'
                    '                  <span className="text-slate-400">Switch & Route:</span> <span className="text-emerald-400 font-bold">{txResponse.ps_code || "ITCL"}</span> ({txResponse.is_on_us ? "ON-US" : "OFF-US"})\n'
                    '                </div>'
                ),
            },
            # Transaction Journal Table: add Route & Switch columns
            {
                "marker": "step02_02:journal_table_route_th",
                "action": "insert_after",
                "anchor": '              <th className="py-2.5">MTI / Code</th>',
                "text": '              <th className="py-2.5">Switch / Route</th>',
            },
            {
                "marker": "step02_02:journal_table_route_td",
                "action": "insert_after",
                "anchor": (
                    '                <td className="py-2.5">\n'
                    '                  {t.mti} (Code {t.transaction_code || \'N/A\'})\n'
                    '                </td>'
                ),
                "text": (
                    '                <td className="py-2.5">\n'
                    '                  <span className="text-emerald-400 font-bold">{t.ps_code || "ITCL"}</span>\n'
                    '                  <span className={`ml-1.5 px-1.5 py-0.5 rounded text-[10px] font-bold ${t.is_on_us ? "bg-emerald-500/10 text-emerald-400" : "bg-sky-500/10 text-sky-400"}`}>\n'
                    '                    {t.is_on_us ? "ON-US" : "OFF-US"}\n'
                    '                  </span>\n'
                    '                </td>'
                ),
            },
            # Transaction Details: add Issuer & Acquirer Bank cards
            {
                "marker": "step02_02:tx_details_bank_cards",
                "action": "insert_after",
                "anchor": "          ['Amount', `${tx.transaction_amount.toLocaleString()} ${tx.currency}`],",
                "text": (
                    "          ['Switch System', `${tx.ps_code || 'ITCL'} (${tx.is_on_us ? 'ON-US' : 'OFF-US'})`],\n"
                    "          ['Issuing Bank', tx.issuer_code || 'XBANK'],\n"
                    "          ['Acquiring Bank', tx.acquirer_code || 'XBANK'],"
                ),
            },
        ],
    )

    # 3. Patch frontend/src/pages/HsmAndMonitorPages.tsx
    session.patch_file(
        "frontend/src/pages/HsmAndMonitorPages.tsx",
        [
            {
                "marker": "step02_02:hsm_key_inst_state",
                "action": "insert_after",
                "anchor": "  const [keys, setKeys] = useState<any[]>([]);",
                "text": "  const [institutions, setInstitutions] = useState<any[]>([]);",
            },
            {
                "marker": "step02_02:hsm_key_inst_form_field",
                "action": "insert_after",
                "anchor": "    key_status: 'ACTIVE',",
                "text": "    institution_id: '',",
            },
            {
                "marker": "step02_02:hsm_key_load_inst",
                "action": "replace",
                "anchor": "  const load = async () => setKeys(await apiFetch('/hsm/keys'));",
                "text": (
                    "  const load = async () => {\n"
                    "    const [kList, iList] = await Promise.all([apiFetch('/hsm/keys'), apiFetch('/institutions')]);\n"
                    "    setKeys(kList);\n"
                    "    setInstitutions(iList);\n"
                    "    if (!form.institution_id && iList.length > 0) {\n"
                    "      setForm((prev) => ({ ...prev, institution_id: iList[0].id }));\n"
                    "    }\n"
                    "  };"
                ),
            },
            {
                "marker": "step02_02:hsm_key_inst_dropdown",
                "action": "insert_after",
                "anchor": (
                    '          {[\'ZMK\', \'TMK\', \'ZPK\', \'AWK\', \'IWK\', \'PVK\', \'CVK\', \'TAK\', \'MK-AC\'].map((t) => (\n'
                    '            <option key={t} value={t}>\n'
                    '              {t}\n'
                    '            </option>\n'
                    '          ))}\n'
                    '        </select>'
                ),
                "text": (
                    '        <select\n'
                    '          value={form.institution_id}\n'
                    '          onChange={(e) => setForm({ ...form, institution_id: e.target.value })}\n'
                    '          className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono"\n'
                    '        >\n'
                    '          <option value="">System Key (ITCL Switch)</option>\n'
                    '          {institutions.map((i) => (\n'
                    '            <option key={i.id} value={i.id}>{i.institution_code} — {i.short_name || i.name}</option>\n'
                    '          ))}\n'
                    '        </select>'
                ),
            },
            # Key Reference Table: add Owning Bank column
            {
                "marker": "step02_02:hsm_key_table_inst_th",
                "action": "insert_after",
                "anchor": '              <th className="py-2.5">Name</th>',
                "text": '              <th className="py-2.5">Owning Bank / Switch</th>',
            },
            {
                "marker": "step02_02:hsm_key_table_inst_td",
                "action": "insert_after",
                "anchor": '                <td className="py-2.5 font-sans">{k.key_name}</td>',
                "text": '                <td className="py-2.5 text-sky-400 font-bold">{k.institution_code || "ITCL SWITCH"}</td>',
            },
        ],
    )

    session.record_progress(
        completed=[
            "Added institution selector dropdowns and table badges to Customers, Accounts, and Cards in `frontend/src/pages/BankingEntities.tsx`.",
            "Added switch (`ps_code`) and routing (`ON-US` / `OFF-US`) indicators to the Simulator outcome and Transaction Journal in `frontend/src/pages/SimulatorAndJournal.tsx`.",
            "Added Issuing Bank and Acquiring Bank detail cards to `TransactionDetailsPage`.",
            "Added institution selector dropdown and owning bank table column to `frontend/src/pages/HsmAndMonitorPages.tsx`.",
        ],
        remaining=[
            "STEP 3 — Full CRUD and Audit Trail (PUT & DELETE with safety checks, confirmation dialogs, and `audit_trail` table across all banking and configuration entities).",
        ],
        modified_files=[
            "frontend/src/pages/BankingEntities.tsx",
            "frontend/src/pages/SimulatorAndJournal.tsx",
            "frontend/src/pages/HsmAndMonitorPages.tsx",
        ],
    )

    session.record_contracts(
        section_title="Step 2.2 — Frontend Institution Selectors & Routing Telemetry",
        contract_items=[
            "**Customer Creation**: Includes Institution dropdown, displaying bank tag in customer table.",
            "**Account Creation**: Includes Institution dropdown, displaying bank tag in account table.",
            "**Card Creation**: Includes Institution dropdown, displaying bank tag in card table.",
            "**Transaction Journal**: Displays switch code (e.g. `ITCL`) and routing tag (`ON-US` vs `OFF-US`).",
            "**Key Management**: Keys can be registered to specific member banks or marked as System Key.",
        ],
    )

    return session.finish()


if __name__ == "__main__":
    sys.exit(main())