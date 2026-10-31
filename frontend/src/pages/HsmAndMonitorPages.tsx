import React, { useEffect, useState } from 'react';
import { Cpu, KeyRound, Activity, Download, Pause, Play, RefreshCw } from 'lucide-react';
import { apiFetch } from '../api';

// ============================================================================
// PAGE 11: HOST KEY MANAGEMENT
// ============================================================================
export const HostKeyManagementPage: React.FC = () => {
  const [keys, setKeys] = useState<any[]>([]);
  const [form, setForm] = useState({
    key_name: '',
    key_type: 'ZPK',
    key_usage: 'PIN_ENCRYPTION',
    key_identifier: `KEY_${Math.floor(100 + Math.random() * 900)}`,
    kvc: 'A1B2C3',
    algorithm: '3DES_2KEY',
    key_length: 128,
    hsm_key_reference: 'LMK_PROTECTED_SLOT_REF',
    key_status: 'ACTIVE',
  });

  const load = async () => setKeys(await apiFetch('/hsm/keys'));
  useEffect(() => {
    load();
  }, []);

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    await apiFetch('/hsm/keys', { method: 'POST', body: JSON.stringify(form) });
    load();
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold">Host Cryptographic Key Management</h1>
        <p className="text-xs text-slate-500">
          Register key references and KVC metadata for ZMK, ZPK, TMK, AWK, IWK, PVK, CVK, TAK, and MK-AC (clear keys remain inside the Soft-HSM boundary)
        </p>
      </div>

      <form
        onSubmit={handleRegister}
        className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 grid grid-cols-1 md:grid-cols-6 gap-3"
      >
        <input
          value={form.key_identifier}
          onChange={(e) => setForm({ ...form, key_identifier: e.target.value })}
          placeholder="Key Identifier"
          className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono"
          required
        />
        <input
          value={form.key_name}
          onChange={(e) => setForm({ ...form, key_name: e.target.value })}
          placeholder="Key Name / Description"
          className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs"
          required
        />
        <select
          value={form.key_type}
          onChange={(e) => setForm({ ...form, key_type: e.target.value })}
          className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono"
        >
          {['ZMK', 'TMK', 'ZPK', 'AWK', 'IWK', 'PVK', 'CVK', 'TAK', 'MK-AC'].map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <input
          value={form.kvc}
          onChange={(e) => setForm({ ...form, kvc: e.target.value.toUpperCase() })}
          placeholder="6-Hex KVC"
          maxLength={6}
          className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono"
          required
        />
        <input
          value={form.hsm_key_reference}
          onChange={(e) => setForm({ ...form, hsm_key_reference: e.target.value })}
          placeholder="Protected HSM Slot / LMK Cryptogram Ref"
          className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono"
          required
        />
        <button
          type="submit"
          className="bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg px-4 py-2 text-xs font-semibold"
        >
          + Register Key Ref
        </button>
      </form>

      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 overflow-x-auto">
        <table className="w-full text-left text-xs font-mono">
          <thead>
            <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-400">
              <th className="py-2.5">Key Identifier</th>
              <th className="py-2.5">Name</th>
              <th className="py-2.5">Type / Usage</th>
              <th className="py-2.5">Algorithm</th>
              <th className="py-2.5">KVC</th>
              <th className="py-2.5">Protected HSM Reference</th>
              <th className="py-2.5">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200/60 dark:divide-slate-800/60">
            {keys.map((k) => (
              <tr key={k.id}>
                <td className="py-2.5 font-bold text-emerald-500">{k.key_identifier}</td>
                <td className="py-2.5 font-sans">{k.key_name}</td>
                <td className="py-2.5">
                  {k.key_type} ({k.key_usage})
                </td>
                <td className="py-2.5">
                  {k.algorithm} ({k.key_length}-bit)
                </td>
                <td className="py-2.5 font-bold text-amber-500">{k.kvc}</td>
                <td className="py-2.5 text-sky-400">{k.hsm_key_reference}</td>
                <td className="py-2.5">{k.key_status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

// ============================================================================
// PAGE 12: HSM OPERATION WORKBENCH
// ============================================================================
const HSM_OPS = [
  { id: 'PIN_VERIFY', label: 'PIN & Visa PVV Verify (Thales DC/DD)', defaultKey: 'PVK_VISA_01' },
  { id: 'PIN_TRANSLATE', label: 'PIN Block Translate AWK ➔ IWK (Thales CA/CB)', defaultKey: 'AWK_ATM_01' },
  { id: 'CVV_VERIFY', label: 'CVV / CVC Verification (Thales CY/CZ)', defaultKey: 'CVK_MAIN_01' },
  { id: 'MAC_GENERATE', label: 'Retail MAC Generate (Thales M6/M7)', defaultKey: 'TAK_MAC_01' },
  { id: 'MAC_VERIFY', label: 'Retail MAC Verify (Thales M8/M9)', defaultKey: 'TAK_MAC_01' },
  { id: 'ARQC_VERIFY', label: 'EMV DE55 ARQC Verify & ARPC Gen (Thales KQ/KR)', defaultKey: 'MK_AC_EMV01' },
  { id: 'KEY_CHECK', label: 'Key Check Value / KVC Verify (Thales BU/BV)', defaultKey: 'ZMK_MAIN' },
];

export const HsmWorkbenchPage: React.FC = () => {
  const [selectedOp, setSelectedOp] = useState(HSM_OPS[0]);
  const [pan, setPan] = useState('4567890123450001');
  const [clearPinHelper, setClearPinHelper] = useState('1234');
  const [pvv, setPvv] = useState('0416');
  const [cvv, setCvv] = useState('011');
  const [dataHex, setDataHex] = useState('48656C6C6F20576F726C64');
  const [de55Hex, setDe55Hex] = useState(
    '9F02060000000050009F03060000000000009F1A020050950500000080005F2A0200509A032610209C01009F370411223344820219809F360200459F2608A1B2C3D4E5F601025F340101'
  );
  const [result, setResult] = useState<any>(null);

  const runOperation = async () => {
    const res = await apiFetch('/hsm/workbench/execute', {
      method: 'POST',
      body: JSON.stringify({
        operation: selectedOp.id,
        key_identifier: selectedOp.defaultKey,
        secondary_key_identifier: 'IWK_SW_01',
        pan,
        clear_pin_for_test_packing: clearPinHelper,
        pvv_or_offset: pvv,
        cvv,
        data_hex: dataHex,
        de55_hex: de55Hex,
      }),
    });
    setResult(res);
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold">HSM Cryptographic Operation Workbench</h1>
        <p className="text-xs text-slate-500">
          Interactive server-side test bench for Thales payShield 10K Soft-HSM commands (no clear PINs or keys exposed)
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 space-y-2">
          <h2 className="text-sm font-bold mb-2">Supported HSM Operations</h2>
          {HSM_OPS.map((op) => (
            <button
              key={op.id}
              onClick={() => {
                setSelectedOp(op);
                setResult(null);
              }}
              className={`w-full text-left p-3 rounded-lg border text-xs font-mono transition ${
                selectedOp.id === op.id
                  ? 'border-emerald-500 bg-emerald-500/10 text-emerald-400 font-bold'
                  : 'border-slate-200 dark:border-slate-800'
              }`}
            >
              <div>{op.label}</div>
              <div className="text-[10px] text-slate-400 mt-0.5">Default Key: {op.defaultKey}</div>
            </button>
          ))}
        </div>

        <div className="lg:col-span-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-6 space-y-4">
          <h2 className="text-sm font-bold font-mono text-emerald-500">{selectedOp.label}</h2>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs font-mono">
            <div>
              <label className="block text-slate-400 mb-1">Synthetic Card PAN</label>
              <input
                value={pan}
                onChange={(e) => setPan(e.target.value)}
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-2"
              />
            </div>
            <div>
              <label className="block text-slate-400 mb-1">Server Test PIN (Packed under AWK)</label>
              <input
                type="password"
                value={clearPinHelper}
                onChange={(e) => setClearPinHelper(e.target.value)}
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-2"
              />
            </div>
            <div>
              <label className="block text-slate-400 mb-1">Expected PVV / CVV</label>
              <input
                value={selectedOp.id === 'CVV_VERIFY' ? cvv : pvv}
                onChange={(e) =>
                  selectedOp.id === 'CVV_VERIFY' ? setCvv(e.target.value) : setPvv(e.target.value)
                }
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-2"
              />
            </div>
          </div>

          {selectedOp.id.includes('ARQC') && (
            <div>
              <label className="block text-xs font-mono text-slate-400 mb-1">
                DE55 EMV TLV Hex Payload
              </label>
              <textarea
                rows={3}
                value={de55Hex}
                onChange={(e) => setDe55Hex(e.target.value)}
                className="w-full bg-slate-950 text-emerald-300 border border-slate-800 rounded p-2.5 text-xs font-mono"
              />
            </div>
          )}

          <button
            onClick={runOperation}
            className="bg-emerald-600 hover:bg-emerald-500 text-white font-semibold px-5 py-2 rounded-lg text-xs font-mono"
          >
            Execute HSM Command ➔
          </button>

          {result && (
            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono space-y-2">
              <div className="flex justify-between">
                <span className="text-slate-400">Audit Reference: {result.audit_reference}</span>
                <span className="text-emerald-400 font-bold">
                  Status: {result.status} (Error Code: {result.error_code}) · {result.duration_ms} ms
                </span>
              </div>
              <pre className="text-sky-300 overflow-x-auto pt-2 border-t border-slate-800">
                {JSON.stringify(
                  {
                    key_identifier: result.key_identifier,
                    kvc: result.kvc,
                    sanitized_request: result.sanitized_request,
                    sanitized_response: result.sanitized_response,
                  },
                  null,
                  2
                )}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

// ============================================================================
// PAGE 13: HOST EXECUTION MONITOR (5 Tabs + Live Polling / WebSocket)
// ============================================================================
export const HostExecutionMonitorPage: React.FC = () => {
  const [tab, setTab] = useState<'TX' | 'HSM' | 'SYS' | 'MSG' | 'DB'>('TX');
  const [traces, setTraces] = useState<any>(null);
  const [live, setLive] = useState(true);
  const [search, setSearch] = useState('');

  const load = async () => {
    try {
      const res = await apiFetch('/monitor/traces');
      setTraces(res);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    load();
    if (!live) return;
    const timer = setInterval(load, 2500);
    return () => clearInterval(timer);
  }, [live]);

  const exportCsv = () => {
    if (!traces) return;
    const rows = (traces.system_logs || []).map(
      (l: any) => `"${l.created_at}","${l.severity}","${l.component}","${l.event_name}","${l.message}"`
    );
    const blob = new Blob([['Timestamp,Severity,Component,Event,Message', ...rows].join('\n')], {
      type: 'text/csv',
    });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'baobab_host_execution_logs.csv';
    a.click();
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold">Host Execution Monitor</h1>
          <p className="text-xs text-slate-500">
            Real-time background trace of transaction checks, HSM commands, wire messages, and database operations
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Filter traces..."
            className="bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-1.5 text-xs font-mono"
          />
          <button
            onClick={() => setLive(!live)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono font-bold ${
              live ? 'bg-emerald-600 text-white' : 'bg-amber-600 text-white'
            }`}
          >
            {live ? <Pause size={13} /> : <Play size={13} />}
            {live ? 'LIVE STREAM ON' : 'PAUSED'}
          </button>
          <button
            onClick={exportCsv}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 text-white text-xs font-mono"
          >
            <Download size={13} /> Export CSV
          </button>
        </div>
      </div>

      {/* 5 Monitor Tabs */}
      <div className="flex flex-wrap gap-2 border-b border-slate-200 dark:border-slate-800 pb-2">
        {[
          ['TX', 'A. Transaction Trace'],
          ['HSM', 'B. HSM Trace'],
          ['SYS', 'C. Host System Log'],
          ['MSG', 'D. Message Trace'],
          ['DB', 'E. Database Activity'],
        ].map(([k, label]) => (
          <button
            key={k}
            onClick={() => setTab(k as any)}
            className={`px-4 py-2 rounded-lg text-xs font-mono font-bold transition ${
              tab === k
                ? 'bg-emerald-600 text-white'
                : 'bg-white dark:bg-slate-900 text-slate-500 hover:text-slate-900 dark:hover:text-white'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="bg-slate-950 border border-slate-800 rounded-xl p-5 text-xs font-mono text-slate-200 max-h-[540px] overflow-y-auto space-y-2">
        {tab === 'TX' &&
          (traces?.transaction_checks || [])
            .filter((c: any) => JSON.stringify(c).toLowerCase().includes(search.toLowerCase()))
            .map((c: any) => (
              <div key={c.id} className="p-2.5 rounded bg-slate-900 border border-slate-800 flex justify-between">
                <div>
                  <span className="text-emerald-400 font-bold">[Step #{c.check_order} {c.check_name}]</span>{' '}
                  {c.message}
                </div>
                <span className="text-amber-400">
                  {c.check_status} (RC {c.response_code}) · {c.duration_ms}ms
                </span>
              </div>
            ))}

        {tab === 'HSM' &&
          (traces?.hsm_traces || [])
            .filter((h: any) => JSON.stringify(h).toLowerCase().includes(search.toLowerCase()))
            .map((h: any) => (
              <div key={h.id} className="p-3 rounded bg-slate-900 border border-slate-800 space-y-1">
                <div className="flex justify-between">
                  <span className="text-amber-400 font-bold">
                    {h.operation_type} — Ref: {h.request_reference}
                  </span>
                  <span className="text-emerald-400">
                    {h.response_status} (EC {h.error_code}) · {h.duration_ms}ms
                  </span>
                </div>
                <div className="text-slate-400">
                  Req: {JSON.stringify(h.sanitized_request)} | Resp: {JSON.stringify(h.sanitized_response)}
                </div>
              </div>
            ))}

        {tab === 'SYS' &&
          (traces?.system_logs || [])
            .filter((l: any) => JSON.stringify(l).toLowerCase().includes(search.toLowerCase()))
            .map((l: any) => (
              <div key={l.id} className="p-2.5 rounded bg-slate-900 border border-slate-800 flex justify-between">
                <div>
                  <span className="text-sky-400">[{l.severity}]</span>{' '}
                  <span className="text-emerald-400">{l.component}.{l.event_name}:</span> {l.message}
                </div>
                <span className="text-slate-500">{new Date(l.created_at).toLocaleTimeString()}</span>
              </div>
            ))}

        {tab === 'MSG' &&
          (traces?.message_traces || []).map((m: any) => (
            <div key={m.id} className="p-3 rounded bg-slate-900 border border-slate-800 space-y-1">
              <div className="text-emerald-400 font-bold">
                [{m.message_type} · MTI {m.mti} · Format {m.message_format}]
              </div>
              <div className="break-all text-amber-200">{m.sanitized_message}</div>
            </div>
          ))}

        {tab === 'DB' &&
          (traces?.transaction_checks || [])
            .filter((c: any) =>
              ['Lookup', 'Selection', 'Limit', 'Balance', 'Ledger'].some((k) => c.check_name.includes(k))
            )
            .map((c: any) => (
              <div key={c.id} className="p-2.5 rounded bg-slate-900 border border-slate-800 flex justify-between">
                <div>
                  <span className="text-indigo-400 font-bold">[DB OPERATION: {c.check_name}]</span>{' '}
                  {c.message}
                </div>
                <span className="text-emerald-400">{c.check_status}</span>
              </div>
            ))}
      </div>
    </div>
  );
};

// ============================================================================
// PAGES 16 & 17: SYSTEM LOGS & NOTIFICATIONS SIMULATOR
// ============================================================================
export const SystemLogsPage: React.FC = () => {
  const [traces, setTraces] = useState<any>(null);
  useEffect(() => {
    apiFetch('/monitor/traces').then(setTraces).catch(console.error);
  }, []);

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold">Sanitized System Audit Logs</h1>
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 overflow-x-auto">
        <table className="w-full text-left text-xs font-mono">
          <thead>
            <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-400">
              <th className="py-2">Timestamp</th>
              <th className="py-2">Severity</th>
              <th className="py-2">Component</th>
              <th className="py-2">Event</th>
              <th className="py-2">Message</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200/60 dark:divide-slate-800/60">
            {(traces?.system_logs || []).map((l: any) => (
              <tr key={l.id}>
                <td className="py-2">{new Date(l.created_at).toLocaleString()}</td>
                <td className="py-2 font-bold text-emerald-500">{l.severity}</td>
                <td className="py-2">{l.component}</td>
                <td className="py-2">{l.event_name}</td>
                <td className="py-2 font-sans">{l.message}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export const NotificationsSimulatorPage: React.FC = () => {
  const [traces, setTraces] = useState<any>(null);
  useEffect(() => {
    apiFetch('/monitor/traces').then(setTraces).catch(console.error);
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold">Customer Notifications Simulator</h1>
        <p className="text-xs text-slate-500">
          Simulated SMS and alert dispatches generated after host authorization decisions
        </p>
      </div>
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 space-y-3">
        {(traces?.notifications || []).map((n: any) => (
          <div
            key={n.id}
            className="p-3.5 rounded-lg border border-slate-200 dark:border-slate-800 flex justify-between items-center text-xs font-mono"
          >
            <div>
              <div className="text-emerald-500 font-bold">
                [{n.notification_type}] To: {n.recipient_masked}
              </div>
              <div className="mt-1 font-sans">{n.message_template}</div>
            </div>
            <span className="px-2 py-1 rounded bg-emerald-500/10 text-emerald-500 text-[10px] font-bold">
              {n.delivery_status}
            </span>
          </div>
        ))}
        {(traces?.notifications || []).length === 0 && (
          <div className="text-xs font-mono text-slate-400 py-6 text-center">
            Submit a transaction in the Transaction Simulator to generate simulated SMS alerts.
          </div>
        )}
      </div>
    </div>
  );
};
