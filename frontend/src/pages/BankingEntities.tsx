import React, { useEffect, useState } from 'react';
import { apiFetch } from '../api';

// ============================================================================
// PAGE 2: CUSTOMERS
// ============================================================================
export const CustomersPage: React.FC = () => {
  const [customers, setCustomers] = useState<any[]>([]);
  const [form, setForm] = useState({
    customer_number: `CUST-${Math.floor(1006 + Math.random() * 9000)}`,
    first_name: '',
    last_name: '',
    email: '',
    mobile_number: '+8801700000099',
    address: 'Dhaka, Bangladesh',
    customer_status: 'ACTIVE',
    risk_category: 'NORMAL',
  });

  const load = async () => setCustomers(await apiFetch('/customers'));
  useEffect(() => {
    load();
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    await apiFetch('/customers', { method: 'POST', body: JSON.stringify(form) });
    setForm({
      ...form,
      customer_number: `CUST-${Math.floor(1006 + Math.random() * 9000)}`,
      first_name: '',
      last_name: '',
    });
    load();
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
        <p className="text-xs text-slate-500">Create and manage synthetic banking host customers</p>
      </div>

      <form
        onSubmit={handleCreate}
        className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 grid grid-cols-1 md:grid-cols-6 gap-3"
      >
        <input
          value={form.customer_number}
          onChange={(e) => setForm({ ...form, customer_number: e.target.value })}
          placeholder="Customer Number"
          className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono"
          required
        />
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

      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 overflow-x-auto">
        <table className="w-full text-left text-xs font-mono">
          <thead>
            <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-400">
              <th className="py-2.5">Customer No</th>
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
                  <button
                    onClick={() => toggleStatus(c)}
                    className="text-sky-500 hover:underline text-[11px]"
                  >
                    Toggle ACTIVE/BLOCKED
                  </button>
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
  const [form, setForm] = useState({
    customer_id: '',
    linked_account_id: '',
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
    const [cList, custList, acctList] = await Promise.all([
      apiFetch('/cards'),
      apiFetch('/customers'),
      apiFetch('/accounts'),
    ]);
    setCards(cList);
    setCustomers(custList);
    setAccounts(acctList);
    if (!form.customer_id && custList.length > 0 && acctList.length > 0) {
      setForm((f) => ({
        ...f,
        customer_id: custList[0].id,
        linked_account_id: acctList[0].id,
      }));
    }
  };

  useEffect(() => {
    load();
  }, []);

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

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold">Cards, PIN Profiles & EMV Profiles</h1>
        <p className="text-xs text-slate-500">
          Synthetic test cards with tokenized PAN references, PVK/PVV verification metadata, and EMV AID profiles
        </p>
      </div>

      <form
        onSubmit={handleIssue}
        className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 grid grid-cols-1 md:grid-cols-6 gap-3"
      >
        <select
          value={form.customer_id}
          onChange={(e) => setForm({ ...form, customer_id: e.target.value })}
          className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono"
        >
          {customers.map((c) => (
            <option key={c.id} value={c.id}>
              {c.customer_number} - {c.first_name}
            </option>
          ))}
        </select>
        <select
          value={form.linked_account_id}
          onChange={(e) => setForm({ ...form, linked_account_id: e.target.value })}
          className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono"
        >
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              ACCT {a.account_number} ({a.currency})
            </option>
          ))}
        </select>
        <input
          value={form.test_pan_reference}
          onChange={(e) => setForm({ ...form, test_pan_reference: e.target.value })}
          placeholder="Synthetic 16-Digit PAN"
          className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono"
          required
        />
        <input
          value={form.cardholder_name}
          onChange={(e) => setForm({ ...form, cardholder_name: e.target.value })}
          placeholder="Cardholder Name"
          className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono"
          required
        />
        <input
          value={form.pvv_or_offset}
          onChange={(e) => setForm({ ...form, pvv_or_offset: e.target.value })}
          placeholder="PVV Reference"
          className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono"
        />
        <button
          type="submit"
          className="bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg px-4 py-2 text-xs font-semibold"
        >
          + Issue Test Card
        </button>
      </form>

      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 overflow-x-auto">
        <table className="w-full text-left text-xs font-mono">
          <thead>
            <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-400">
              <th className="py-2.5">Masked PAN</th>
              <th className="py-2.5">Sim Ref (Test Only)</th>
              <th className="py-2.5">Cardholder</th>
              <th className="py-2.5">Expiry</th>
              <th className="py-2.5">PIN Profile (PVK / PVV)</th>
              <th className="py-2.5">EMV Profile (AID / MK-AC)</th>
              <th className="py-2.5">Status</th>
              <th className="py-2.5">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200/60 dark:divide-slate-800/60">
            {cards.map((c) => (
              <tr key={c.id}>
                <td className="py-2.5 font-bold text-emerald-500">{c.masked_pan}</td>
                <td className="py-2.5 text-slate-400">{c.test_pan_reference}</td>
                <td className="py-2.5">{c.cardholder_name}</td>
                <td className="py-2.5">
                  {String(c.expiry_month).padStart(2, '0')}/{c.expiry_year}
                </td>
                <td className="py-2.5">
                  {c.pin_profile
                    ? `${c.pin_profile.verification_method} | PVV:${c.pin_profile.pin_offset_reference} | Tries:${c.pin_profile.retry_counter}/${c.pin_profile.maximum_retry_count}`
                    : 'N/A'}
                </td>
                <td className="py-2.5">
                  {c.emv_profile ? `${c.emv_profile.aid} (${c.emv_profile.master_key_reference})` : 'N/A'}
                </td>
                <td className="py-2.5">
                  <span
                    className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                      c.card_status === 'ACTIVE'
                        ? 'bg-emerald-500/10 text-emerald-500'
                        : 'bg-rose-500/10 text-rose-500'
                    }`}
                  >
                    {c.card_status}
                  </span>
                </td>
                <td className="py-2.5">
                  <button
                    onClick={() => toggleCardStatus(c)}
                    className="text-sky-500 hover:underline text-[11px]"
                  >
                    {c.card_status === 'ACTIVE' ? 'Block Card' : 'Activate'}
                  </button>
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
  const [ledger, setLedger] = useState<any[]>([]);
  const [selectedAcct, setSelectedAcct] = useState<string>('');
  const [form, setForm] = useState({
    account_number: `100100${Math.floor(1000 + Math.random() * 8999)}`,
    customer_id: '',
    account_type: 'SAVINGS',
    currency: 'BDT',
    available_balance: '100000.00',
    ledger_balance: '100000.00',
    overdraft_limit: '0.00',
  });

  const load = async () => {
    const [aList, cList] = await Promise.all([apiFetch('/accounts'), apiFetch('/customers')]);
    setAccounts(aList);
    setCustomers(cList);
    if (!form.customer_id && cList.length > 0) {
      setForm((f) => ({ ...f, customer_id: cList[0].id }));
    }
  };

  useEffect(() => {
    load();
  }, []);

  const viewLedger = async (acctId: string) => {
    setSelectedAcct(acctId);
    setLedger(await apiFetch(`/accounts/${acctId}/ledger`));
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    await apiFetch('/accounts', { method: 'POST', body: JSON.stringify(form) });
    load();
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold">Accounts & Atomic Financial Ledger</h1>
        <p className="text-xs text-slate-500">
          Fixed-precision numeric balances with row-level locking and full debit/credit audit trail
        </p>
      </div>

      <form
        onSubmit={handleCreate}
        className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 grid grid-cols-1 md:grid-cols-6 gap-3"
      >
        <input
          value={form.account_number}
          onChange={(e) => setForm({ ...form, account_number: e.target.value })}
          placeholder="Account Number"
          className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono"
          required
        />
        <select
          value={form.customer_id}
          onChange={(e) => setForm({ ...form, customer_id: e.target.value })}
          className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono"
        >
          {customers.map((c) => (
            <option key={c.id} value={c.id}>
              {c.customer_number} - {c.first_name}
            </option>
          ))}
        </select>
        <select
          value={form.account_type}
          onChange={(e) => setForm({ ...form, account_type: e.target.value })}
          className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono"
        >
          <option value="SAVINGS">SAVINGS</option>
          <option value="CURRENT">CURRENT</option>
          <option value="CREDIT">CREDIT</option>
        </select>
        <input
          value={form.available_balance}
          onChange={(e) =>
            setForm({ ...form, available_balance: e.target.value, ledger_balance: e.target.value })
          }
          placeholder="Opening Balance"
          className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono"
        />
        <input
          value={form.overdraft_limit}
          onChange={(e) => setForm({ ...form, overdraft_limit: e.target.value })}
          placeholder="Overdraft Limit"
          className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono"
        />
        <button
          type="submit"
          className="bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg px-4 py-2 text-xs font-semibold"
        >
          + Open Account
        </button>
      </form>

      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 overflow-x-auto">
        <table className="w-full text-left text-xs font-mono">
          <thead>
            <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-400">
              <th className="py-2.5">Account Number</th>
              <th className="py-2.5">Customer</th>
              <th className="py-2.5">Type</th>
              <th className="py-2.5">Available Balance</th>
              <th className="py-2.5">Ledger Balance</th>
              <th className="py-2.5">Overdraft Limit</th>
              <th className="py-2.5">Status</th>
              <th className="py-2.5">Ledger</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200/60 dark:divide-slate-800/60">
            {accounts.map((a) => (
              <tr key={a.id}>
                <td className="py-2.5 font-bold text-emerald-500">{a.account_number}</td>
                <td className="py-2.5 font-sans">{a.customer_name}</td>
                <td className="py-2.5">{a.account_type}</td>
                <td className="py-2.5 font-bold">
                  {a.available_balance.toLocaleString()} {a.currency}
                </td>
                <td className="py-2.5">
                  {a.ledger_balance.toLocaleString()} {a.currency}
                </td>
                <td className="py-2.5">{a.overdraft_limit.toLocaleString()}</td>
                <td className="py-2.5">{a.account_status}</td>
                <td className="py-2.5">
                  <button
                    onClick={() => viewLedger(a.id)}
                    className="text-sky-500 hover:underline text-[11px]"
                  >
                    Inspect Ledger ({a.account_number})
                  </button>
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
                  <td className="py-2">
                    {l.amount.toLocaleString()} {l.currency}
                  </td>
                  <td className="py-2">{l.balance_before.toLocaleString()}</td>
                  <td className="py-2 font-bold">{l.balance_after.toLocaleString()}</td>
                  <td className="py-2">{l.description}</td>
                </tr>
              ))}
              {ledger.length === 0 && (
                <tr>
                  <td colSpan={6} className="py-4 text-center text-slate-400">
                    No ledger postings for this account yet.
                  </td>
                </tr>
              )}
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

  const load = async () => setCards(await apiFetch('/cards'));
  useEffect(() => {
    load();
  }, []);

  const saveLimit = async (card: any) => {
    await apiFetch(`/cards/${card.id}/limits`, {
      method: 'PUT',
      body: JSON.stringify({
        ...card.limits,
        status: 'ACTIVE',
      }),
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
        <h1 className="text-xl font-bold">Card-Level Limits (BAOBAB ATH_CARDLIMIT / CHECKCARDLIMITS)</h1>
        <p className="text-xs text-slate-500">
          Configure per-transaction, daily, weekly, and monthly limits and inspect live usage counters
        </p>
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
            {cards.map((c, idx) =>
              c.limits ? (
                <tr key={c.id}>
                  <td className="py-2 font-bold text-emerald-500">{c.masked_pan}</td>
                  <td className="py-2">
                    <input
                      type="number"
                      value={c.limits.transaction_limit}
                      onChange={(e) => updateField(idx, 'transaction_limit', e.target.value)}
                      className="w-28 bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2 py-1"
                    />
                  </td>
                  <td className="py-2">
                    <input
                      type="number"
                      value={c.limits.daily_limit}
                      onChange={(e) => updateField(idx, 'daily_limit', e.target.value)}
                      className="w-28 bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2 py-1"
                    />
                  </td>
                  <td className="py-2 text-amber-500 font-bold">{c.limits.daily_used.toLocaleString()}</td>
                  <td className="py-2">
                    <input
                      type="number"
                      value={c.limits.weekly_limit}
                      onChange={(e) => updateField(idx, 'weekly_limit', e.target.value)}
                      className="w-28 bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2 py-1"
                    />
                  </td>
                  <td className="py-2">
                    <input
                      type="number"
                      value={c.limits.monthly_limit}
                      onChange={(e) => updateField(idx, 'monthly_limit', e.target.value)}
                      className="w-32 bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2 py-1"
                    />
                  </td>
                  <td className="py-2">
                    <button
                      onClick={() => saveLimit(c)}
                      className="bg-emerald-600 hover:bg-emerald-500 text-white px-3 py-1 rounded text-[11px]"
                    >
                      Save
                    </button>
                  </td>
                </tr>
              ) : null
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export const AccountLimitsPage: React.FC = () => {
  const [accounts, setAccounts] = useState<any[]>([]);
  const [msg, setMsg] = useState('');

  const load = async () => setAccounts(await apiFetch('/accounts'));
  useEffect(() => {
    load();
  }, []);

  const saveLimit = async (acct: any) => {
    await apiFetch(`/accounts/${acct.id}/limits`, {
      method: 'PUT',
      body: JSON.stringify({
        ...acct.limits,
        status: 'ACTIVE',
      }),
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
        <p className="text-xs text-slate-500">
          Configure account velocity and per-transaction limits independent of card limits
        </p>
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
            {accounts.map((a, idx) =>
              a.limits ? (
                <tr key={a.id}>
                  <td className="py-2 font-bold text-emerald-500">{a.account_number}</td>
                  <td className="py-2">
                    <input
                      type="number"
                      value={a.limits.per_transaction_limit}
                      onChange={(e) => updateField(idx, 'per_transaction_limit', e.target.value)}
                      className="w-28 bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2 py-1"
                    />
                  </td>
                  <td className="py-2">
                    <input
                      type="number"
                      value={a.limits.daily_limit}
                      onChange={(e) => updateField(idx, 'daily_limit', e.target.value)}
                      className="w-28 bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2 py-1"
                    />
                  </td>
                  <td className="py-2 text-amber-500 font-bold">{a.limits.daily_used.toLocaleString()}</td>
                  <td className="py-2">
                    <input
                      type="number"
                      value={a.limits.weekly_limit}
                      onChange={(e) => updateField(idx, 'weekly_limit', e.target.value)}
                      className="w-28 bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2 py-1"
                    />
                  </td>
                  <td className="py-2">
                    <input
                      type="number"
                      value={a.limits.monthly_limit}
                      onChange={(e) => updateField(idx, 'monthly_limit', e.target.value)}
                      className="w-32 bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2 py-1"
                    />
                  </td>
                  <td className="py-2">
                    <button
                      onClick={() => saveLimit(a)}
                      className="bg-emerald-600 hover:bg-emerald-500 text-white px-3 py-1 rounded text-[11px]"
                    >
                      Save
                    </button>
                  </td>
                </tr>
              ) : null
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
