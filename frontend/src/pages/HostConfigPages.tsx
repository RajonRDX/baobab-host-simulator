import React, { useEffect, useState } from 'react';
import { apiFetch } from '../api';

// ============================================================================
// PAGE 7: CONFIGURABLE TRANSACTION CODES (Code 10, 20, 30, 40 & Custom)
// ============================================================================
export const TransactionCodesPage: React.FC = () => {
  const [codes, setCodes] = useState<any[]>([]);
  const [selected, setSelected] = useState<any | null>(null);
  const [savedMsg, setSavedMsg] = useState('');

  const load = async () => {
    const list = await apiFetch('/transaction-codes');
    setCodes(list);
    if (!selected && list.length > 0) setSelected(list[0]);
  };

  useEffect(() => {
    load();
  }, []);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selected) return;
    await apiFetch('/transaction-codes', {
      method: 'POST',
      body: JSON.stringify(selected),
    });
    setSavedMsg(`Saved configuration for Transaction Code ${selected.transaction_code}`);
    load();
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold">Configurable Transaction Codes (Codes 10, 20, 30, 40 & Custom)</h1>
        <p className="text-xs text-slate-500">
          Define what each transaction code means, which MTI/processing code it uses, and which HSM & host checks execute
        </p>
      </div>

      {savedMsg && (
        <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-500 text-xs font-mono">
          {savedMsg}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 space-y-2">
          <div className="flex justify-between items-center mb-2">
            <h2 className="text-sm font-bold">Defined Codes</h2>
            <button
              onClick={() =>
                setSelected({
                  transaction_code: '50',
                  transaction_name: 'New Configurable Transaction',
                  description: 'Custom operator-defined rule set',
                  transaction_category: 'FINANCIAL',
                  processing_code: '0500000',
                  default_mti: '0200',
                  financial_flag: true,
                  balance_inquiry_flag: false,
                  debit_flag: true,
                  credit_flag: false,
                  reversal_allowed: true,
                  pin_required: true,
                  cvv_required: false,
                  pvv_required: true,
                  emv_required: false,
                  mac_required: false,
                  account_check_required: true,
                  card_check_required: true,
                  limit_check_required: true,
                  active: true,
                })
              }
              className="text-xs bg-emerald-600 text-white px-2.5 py-1 rounded font-semibold"
            >
              + New Code
            </button>
          </div>
          {codes.map((c) => (
            <button
              key={c.id}
              onClick={() => setSelected(c)}
              className={`w-full text-left p-3 rounded-lg border transition ${
                selected?.transaction_code === c.transaction_code
                  ? 'border-emerald-500 bg-emerald-500/10'
                  : 'border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/50'
              }`}
            >
              <div className="flex justify-between items-center font-mono text-xs font-bold">
                <span className="text-emerald-500">CODE {c.transaction_code}</span>
                <span>MTI {c.default_mti}</span>
              </div>
              <div className="text-xs font-medium mt-1">{c.transaction_name}</div>
            </button>
          ))}
        </div>

        {selected && (
          <form
            onSubmit={handleSave}
            className="lg:col-span-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-6 space-y-4"
          >
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-xs font-mono text-slate-400 mb-1">Transaction Code</label>
                <input
                  value={selected.transaction_code}
                  onChange={(e) => setSelected({ ...selected, transaction_code: e.target.value })}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono"
                />
              </div>
              <div className="md:col-span-2">
                <label className="block text-xs font-mono text-slate-400 mb-1">Transaction Name (Operator Defined)</label>
                <input
                  value={selected.transaction_name}
                  onChange={(e) => setSelected({ ...selected, transaction_name: e.target.value })}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs"
                />
              </div>
              <div>
                <label className="block text-xs font-mono text-slate-400 mb-1">Default MTI</label>
                <input
                  value={selected.default_mti}
                  onChange={(e) => setSelected({ ...selected, default_mti: e.target.value })}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono"
                />
              </div>
              <div>
                <label className="block text-xs font-mono text-slate-400 mb-1">Processing Code (7-char TIC F3)</label>
                <input
                  value={selected.processing_code}
                  onChange={(e) => setSelected({ ...selected, processing_code: e.target.value })}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono"
                />
              </div>
              <div>
                <label className="block text-xs font-mono text-slate-400 mb-1">Category</label>
                <input
                  value={selected.transaction_category}
                  onChange={(e) => setSelected({ ...selected, transaction_category: e.target.value })}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono"
                />
              </div>
            </div>

            <div className="pt-2 border-t border-slate-200 dark:border-slate-800">
              <div className="text-xs font-mono uppercase text-slate-400 mb-2">
                Authorization & HSM Verification Flags
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs font-mono">
                {[
                  ['financial_flag', 'Financial Posting'],
                  ['debit_flag', 'Debit Account'],
                  ['credit_flag', 'Credit Account'],
                  ['balance_inquiry_flag', 'Balance Inquiry'],
                  ['reversal_allowed', 'Reversal Allowed'],
                  ['pin_required', 'HSM PIN Check'],
                  ['pvv_required', 'HSM PVV Check'],
                  ['cvv_required', 'HSM CVV Check'],
                  ['emv_required', 'HSM EMV ARQC'],
                  ['mac_required', 'HSM MAC Check'],
                  ['card_check_required', 'Card Status/Exp'],
                  ['account_check_required', 'Account Status'],
                  ['limit_check_required', 'Card/Acct Limits'],
                  ['active', 'Code Active'],
                ].map(([key, label]) => (
                  <label key={key} className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={Boolean(selected[key])}
                      onChange={(e) => setSelected({ ...selected, [key]: e.target.checked })}
                      className="rounded border-slate-600 text-emerald-600"
                    />
                    <span>{label}</span>
                  </label>
                ))}
              </div>
            </div>

            <button
              type="submit"
              className="bg-emerald-600 hover:bg-emerald-500 text-white font-semibold px-5 py-2 rounded-lg text-xs"
            >
              Save Transaction Code Rules
            </button>
          </form>
        )}
      </div>
    </div>
  );
};

// ============================================================================
// PAGE 14: HOST CONFIGURATION (RAJON Parameters)
// ============================================================================
export const HostConfigurationPage: React.FC = () => {
  const [params, setParams] = useState<any[]>([]);

  const load = async () => setParams(await apiFetch('/host-parameters'));
  useEffect(() => {
    load();
  }, []);

  const toggleParam = async (p: any) => {
    const currentEnabled = p.parameter_value?.enabled ?? true;
    const updatedValue = { ...p.parameter_value, enabled: !currentEnabled };
    await apiFetch(`/host-parameters/${p.id}`, {
      method: 'PUT',
      body: JSON.stringify({ parameter_value: updatedValue, active: !currentEnabled }),
    });
    load();
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold">Rajon Host Authorization Configuration</h1>
        <p className="text-xs text-slate-500">
          Enable or disable central authorization engine rules (`AUTHORIZEACCTBALANCESTRANS`, `CHECKCARDLIMITS`, `CHECKACCT2CARDLIMITS`)
        </p>
      </div>

      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 overflow-x-auto">
        <table className="w-full text-left text-xs font-mono">
          <thead>
            <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-400">
              <th className="py-2.5">Group</th>
              <th className="py-2.5">Parameter Name</th>
              <th className="py-2.5">Value / Order</th>
              <th className="py-2.5">Description</th>
              <th className="py-2.5">Status</th>
              <th className="py-2.5">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200/60 dark:divide-slate-800/60">
            {params.map((p) => {
              const isEnabled = p.parameter_value?.enabled ?? p.active;
              return (
                <tr key={p.id}>
                  <td className="py-2.5 text-slate-400">{p.parameter_group}</td>
                  <td className="py-2.5 font-bold text-emerald-500">{p.parameter_name}</td>
                  <td className="py-2.5">{JSON.stringify(p.parameter_value)}</td>
                  <td className="py-2.5 font-sans">{p.description}</td>
                  <td className="py-2.5">
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        isEnabled ? 'bg-emerald-500/10 text-emerald-500' : 'bg-rose-500/10 text-rose-500'
                      }`}
                    >
                      {isEnabled ? 'ENABLED' : 'DISABLED'}
                    </span>
                  </td>
                  <td className="py-2.5">
                    <button
                      onClick={() => toggleParam(p)}
                      className="text-sky-500 hover:underline text-[11px]"
                    >
                      Toggle Rule
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};

// ============================================================================
// PAGE 15: RESPONSE CODE MANAGEMENT
// ============================================================================
export const ResponseCodesPage: React.FC = () => {
  const [codes, setCodes] = useState<any[]>([]);
  const [form, setForm] = useState({
    response_code: '',
    response_description: '',
    response_category: 'DECLINE',
    approved_flag: false,
  });

  const load = async () => setCodes(await apiFetch('/response-codes'));
  useEffect(() => {
    load();
  }, []);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    await apiFetch('/response-codes', { method: 'POST', body: JSON.stringify(form) });
    setForm({ response_code: '', response_description: '', response_category: 'DECLINE', approved_flag: false });
    load();
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold">Response Code Mapping</h1>
        <p className="text-xs text-slate-500">Manage TIC DE39 response codes and approval flags</p>
      </div>

      <form
        onSubmit={handleSave}
        className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 grid grid-cols-1 md:grid-cols-5 gap-3"
      >
        <input
          value={form.response_code}
          onChange={(e) => setForm({ ...form, response_code: e.target.value })}
          placeholder="2-Char Code (e.g. 59)"
          maxLength={2}
          className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono"
          required
        />
        <input
          value={form.response_description}
          onChange={(e) => setForm({ ...form, response_description: e.target.value })}
          placeholder="Description"
          className="md:col-span-2 bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs"
          required
        />
        <select
          value={form.response_category}
          onChange={(e) =>
            setForm({
              ...form,
              response_category: e.target.value,
              approved_flag: e.target.value === 'APPROVAL',
            })
          }
          className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono"
        >
          <option value="DECLINE">DECLINE</option>
          <option value="APPROVAL">APPROVAL</option>
          <option value="ERROR">ERROR</option>
        </select>
        <button
          type="submit"
          className="bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg px-4 py-2 text-xs font-semibold"
        >
          + Upsert Code
        </button>
      </form>

      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 overflow-x-auto">
        <table className="w-full text-left text-xs font-mono">
          <thead>
            <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-400">
              <th className="py-2">DE39 Code</th>
              <th className="py-2">TIC F39 (5-Char)</th>
              <th className="py-2">Description</th>
              <th className="py-2">Category</th>
              <th className="py-2">Approved Flag</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200/60 dark:divide-slate-800/60">
            {codes.map((c) => (
              <tr key={c.id}>
                <td className="py-2 font-bold text-emerald-500">{c.response_code}</td>
                <td className="py-2 text-slate-400">000{c.response_code}</td>
                <td className="py-2 font-sans">{c.response_description}</td>
                <td className="py-2">{c.response_category}</td>
                <td className="py-2">{c.approved_flag ? 'TRUE' : 'FALSE'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
