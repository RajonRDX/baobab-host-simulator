import React, { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  Play,
  CheckCircle2,
  Code2,
  RotateCcw,
  Copy,
  Sparkles,
  AlertTriangle,
  Search,
  ArrowLeft,
} from 'lucide-react';
import { apiFetch } from '../api';

// ============================================================================
// PAGE 8: TIC / ISO TRANSACTION SIMULATOR WORKBENCH
// ============================================================================
export const TransactionSimulatorPage: React.FC = () => {
  const [catalog, setCatalog] = useState<any>(null);
  const [txCode, setTxCode] = useState('10');
  const [mti, setMti] = useState('0200');
  const [clearPinHelper, setClearPinHelper] = useState('1234');
  const [fields, setFields] = useState<Record<string, string>>({
    '2': '4567890123450001',
    '3': '0100000',
    '4': '000000250000',
    '7': '1031123000',
    '11': '100001',
    '12': '123000',
    '13': '1031',
    '14': '2812',
    '18': '5411',
    '22': '051',
    '25': '000',
    '32': '123456',
    '37': '000020526001',
    '41': 'ATM00001',
    '49': 'BDT',
  });
  const [enabledFields, setEnabledFields] = useState<Record<string, boolean>>({
    '2': true,
    '3': true,
    '4': true,
    '7': true,
    '11': true,
    '12': true,
    '13': true,
    '14': true,
    '18': true,
    '22': true,
    '25': true,
    '32': true,
    '37': true,
    '41': true,
    '49': true,
  });
  const [newFieldNum, setNewFieldNum] = useState('55');
  const [rawTic, setRawTic] = useState('');
  const [compactTic, setCompactTic] = useState('');
  const [decodedView, setDecodedView] = useState<any>(null);
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});
  const [txResponse, setTxResponse] = useState<any>(null);
  const [submitting, setSubmitting] = useState(false);
// [PATCH step09:simulator_persistence_state]
  const [sessionRestored, setSessionRestored] = useState(false);
  const [parseModalOpen, setParseModalOpen] = useState(false);
  const [rawToParse, setRawToParse] = useState('');
  const [detectedFormat, setDetectedFormat] = useState('');

  useEffect(() => {
    apiFetch('/simulator/catalog').then(setCatalog).catch(console.error);
  }, []);
// [PATCH step09:simulator_load_session_storage]

  // Step 9: Restore persistent state from sessionStorage on mount
  useEffect(() => {
    try {
      const saved = sessionStorage.getItem('BAOBAB_SIMULATOR_STATE');
      if (saved) {
        const s = JSON.parse(saved);
        if (s.fields) setFields(s.fields);
        if (s.txCode) setTxCode(s.txCode);
        if (s.mti) setMti(s.mti);
        if (s.clearPinHelper) setClearPinHelper(s.clearPinHelper);
        if (s.enabledFields) setEnabledFields(s.enabledFields);
        if (s.rawTic) setRawTic(s.rawTic);
        if (s.compactTic) setCompactTic(s.compactTic);
        if (s.txResponse) setTxResponse(s.txResponse);
        setSessionRestored(true);
      }
    } catch (e) {
      console.warn('Could not restore simulator state', e);
    }
  }, []);

  // Persist simulator state to sessionStorage whenever fields/options change
  useEffect(() => {
    try {
      sessionStorage.setItem('BAOBAB_SIMULATOR_STATE', JSON.stringify({
        fields,
        txCode,
        mti,
        clearPinHelper,
        enabledFields,
        rawTic,
        compactTic,
        txResponse,
      }));
    } catch (e) {}
  }, [fields, txCode, mti, clearPinHelper, enabledFields, rawTic, compactTic, txResponse]);

  const resetToDefaults = () => {
    sessionStorage.removeItem('BAOBAB_SIMULATOR_STATE');
    setTxCode('10');
    setMti('0200');
    setClearPinHelper('1234');
    setFields({
      '2': '4567890123450001',
      '3': '0100000',
      '4': '000000250000',
      '7': '1031123000',
      '11': '100001',
      '12': '123000',
      '13': '1031',
      '14': '2812',
      '18': '5411',
      '22': '051',
      '25': '000',
      '32': '123456',
      '37': '000020526001',
      '41': 'ATM00001',
      '49': 'BDT',
    });
    setTxResponse(null);
    setRawTic('');
    setCompactTic('');
    setSessionRestored(false);
  };

  const handleParseRawWire = async () => {
    if (!rawToParse.trim()) return;
    try {
      const res = await apiFetch('/simulator/parse-raw', {
        method: 'POST',
        body: JSON.stringify({ raw_message: rawToParse }),
      });
      if (!res.valid) {
        alert(res.error || 'Failed to parse raw wire message');
        return;
      }
      setDetectedFormat(res.format);
      setMti(res.mti);
      if (res.derived_transaction_code) setTxCode(res.derived_transaction_code);
      setFields(res.fields);
      const en: Record<string, boolean> = {};
      Object.keys(res.fields).forEach((k) => (en[k] = true));
      setEnabledFields(en);
      setRawTic(rawToParse);
      setParseModalOpen(false);
    } catch (err: any) {
      alert(err.message);
    }
  };


  const getActiveFields = () => {
    const out: Record<string, string> = {};
    Object.entries(fields).forEach(([k, v]) => {
      if (enabledFields[k] !== false && v !== '') {
        out[k] = v;
      }
    });
    return out;
  };

  const loadScenario = (scen: any) => {
    setTxCode(scen.transaction_code || '10');
    setMti(scen.mti || '0200');
    setClearPinHelper(scen.test_clear_pin_helper || '');
    setFields(scen.fields || {});
    const en: Record<string, boolean> = {};
    Object.keys(scen.fields || {}).forEach((k) => (en[k] = true));
    setEnabledFields(en);
    setValidationErrors({});
    setTxResponse(null);
  };

  const handleBuildAndValidate = async () => {
    setValidationErrors({});
    const res = await apiFetch('/simulator/build', {
      method: 'POST',
      body: JSON.stringify({
        mti,
        fields: getActiveFields(),
      }),
    });
    if (!res.valid) {
      setValidationErrors(res.errors || {});
    } else {
      setRawTic(res.raw_tic_message);
      setCompactTic(res.compact_tic);
      setDecodedView(res.decoded);
    }
  };

  const handleDecodeRaw = async () => {
    if (!rawTic.trim()) return;
    const dec = await apiFetch('/simulator/decode', {
      method: 'POST',
      body: JSON.stringify({ raw_tic_message: rawTic }),
    });
    setDecodedView(dec);
    if (dec.valid && dec.raw_fields) {
      setMti(dec.mti || '0200');
      setFields(dec.raw_fields);
      const en: Record<string, boolean> = {};
      Object.keys(dec.raw_fields).forEach((k) => (en[k] = true));
      setEnabledFields(en);
    }
  };

  const handleSubmitTransaction = async () => {
    setSubmitting(true);
    setValidationErrors({});
    try {
      const res = await apiFetch('/simulator/submit', {
        method: 'POST',
        body: JSON.stringify({
          transaction_code: txCode,
          mti,
          fields: getActiveFields(),
          test_clear_pin_helper: clearPinHelper || undefined,
          source_channel: 'SIMULATOR',
        }),
      });
      setTxResponse(res);
      setRawTic(res.sanitized_request_tic || rawTic);
      setCompactTic(res.compact_response_tic || '');
    } catch (e: any) {
      alert(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  const addFieldToEditor = () => {
    if (!newFieldNum) return;
    setFields({ ...fields, [newFieldNum]: '' });
    setEnabledFields({ ...enabledFields, [newFieldNum]: true });
  };

  const bumpStanAndRrn = () => {
    const nextStan = String((parseInt(fields['11'] || '100000', 10) + 1) % 999999).padStart(6, '0');
    const nextRrn = String(parseInt(fields['37'] || '20526000', 10) + 1).padStart(12, '0');
    setFields({ ...fields, '11': nextStan, '37': nextRrn });
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold">TIC / ISO 8583 Transaction Simulator Workbench</h1>
          <p className="text-xs text-slate-500">
            Compass Plus TW International Protocol (v2.164e) field builder, validator, and live HostTransactionProcessor submission
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
// [PATCH step09:simulator_header_buttons]
          {sessionRestored && (
            <span className="flex items-center gap-1 text-[11px] font-mono px-2.5 py-1 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-bold">
              ✓ Session Restored
            </span>
          )}
          <button
            onClick={() => setParseModalOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold"
          >
            Universal Wire Parser (TIC/ISO)
          </button>
          <button
            onClick={resetToDefaults}
            className="px-2.5 py-1.5 rounded-lg bg-slate-200 dark:bg-slate-800 text-xs font-mono hover:bg-slate-300 dark:hover:bg-slate-700"
            title="Reset Simulator to default values"
          >
            Reset Defaults
          </button>

          <button
            onClick={bumpStanAndRrn}
            className="px-3 py-1.5 rounded-lg bg-slate-200 dark:bg-slate-800 text-xs font-mono hover:bg-slate-300 dark:hover:bg-slate-700"
          >
            + Increment STAN/RRN
          </button>
          <button
            onClick={handleBuildAndValidate}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold"
          >
            <Code2 size={14} /> Build & Validate TIC
          </button>
          <button
            onClick={handleSubmitTransaction}
            disabled={submitting}
            className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold shadow"
          >
            <Play size={14} /> {submitting ? 'Processing...' : 'Submit Transaction to Host'}
          </button>
        </div>
      </div>

// [PATCH step09:simulator_render_parse_modal]
      {parseModalOpen && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center p-4 z-50">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-6 max-w-xl w-full space-y-4 shadow-2xl">
            <div className="flex justify-between items-center border-b border-slate-200 dark:border-slate-800 pb-3">
              <h2 className="text-sm font-bold">Universal Wire Message Parser</h2>
              <button onClick={() => setParseModalOpen(false)} className="text-slate-400 hover:text-white text-lg">×</button>
            </div>
            <p className="text-xs text-slate-500 font-sans">
              Paste any raw wire string below. The host will auto-detect whether it is a Compass Plus TIC/TCI v2.164e message (A4M header) or standard ISO 8583:1987 message with hex bitmap, unpack all fields, and load them directly into your simulator editor.
            </p>
            <textarea
              rows={4}
              value={rawToParse}
              onChange={(e) => setRawToParse(e.target.value)}
              placeholder="Paste raw string here (e.g. A4M0200... or 0200702004...)"
              className="w-full bg-slate-950 text-emerald-300 border border-slate-800 rounded p-2.5 text-xs font-mono"
            />
            <div className="flex justify-between items-center pt-2 border-t border-slate-200 dark:border-slate-800">
              <div className="flex gap-2">
                <button
                  onClick={() => setRawToParse("02007220000008008000164567890123450001010000000000100000100001000020526001050")}
                  className="text-[11px] font-mono text-sky-400 hover:underline"
                >
                  Load Sample ISO 8583
                </button>
              </div>
              <div className="flex gap-2">
                <button onClick={() => setParseModalOpen(false)} className="px-3 py-1.5 rounded text-xs">Cancel</button>
                <button onClick={handleParseRawWire} className="bg-emerald-600 text-white px-4 py-1.5 rounded text-xs font-semibold">Parse & Load Fields</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Sample Scenarios Bar */}
      {catalog?.sample_scenarios && (
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4">
          <div className="text-xs font-mono uppercase text-slate-400 mb-2 flex items-center gap-1.5">
            <Sparkles size={13} className="text-emerald-500" /> Load Real Backend Test Scenario:
          </div>
          <div className="flex flex-wrap gap-2">
            {catalog.sample_scenarios.map((s: any) => (
              <button
                key={s.key}
                onClick={() => loadScenario(s)}
                className="text-xs font-mono px-3 py-1.5 rounded-lg border border-slate-300 dark:border-slate-700 hover:border-emerald-500 hover:text-emerald-400 transition"
              >
                {s.name}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Main Workbench Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left 7 Cols: Setup & Dynamic ISO/TIC Field Editor */}
        <div className="lg:col-span-7 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 space-y-4">
          <h2 className="text-sm font-bold border-b border-slate-200 dark:border-slate-800 pb-2">
            1. Transaction Setup & TIC/ISO Field Editor
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            <div>
              <label className="block text-[11px] font-mono text-slate-400 mb-1">Transaction Code</label>
              <select
                value={txCode}
                onChange={(e) => {
                  const nextCode = e.target.value;
                  setTxCode(nextCode);
                  const found = catalog?.transaction_codes?.find((c: any) => c.transaction_code === nextCode);
                  if (found) {
                    setMti(found.default_mti);
                    setFields({ ...fields, '3': found.processing_code });
                  }
                }}
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5 text-xs font-mono"
              >
                {(catalog?.transaction_codes || []).map((c: any) => (
                  <option key={c.transaction_code} value={c.transaction_code}>
                    Code {c.transaction_code} — {c.transaction_name}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-[11px] font-mono text-slate-400 mb-1">MTI</label>
              <select
                value={mti}
                onChange={(e) => setMti(e.target.value)}
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5 text-xs font-mono"
              >
                <option value="0100">0100 — Auth Request</option>
                <option value="0200">0200 — Financial Request</option>
                <option value="0400">0400 — Reversal Request</option>
                <option value="0420">0420 — Reversal Advice</option>
                <option value="0800">0800 — Network Mgmt</option>
              </select>
            </div>

            <div>
              <label className="block text-[11px] font-mono text-slate-400 mb-1">Select Synthetic Card</label>
              <select
                value={fields['2'] || ''}
                onChange={(e) => setFields({ ...fields, '2': e.target.value })}
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5 text-xs font-mono"
              >
                {(catalog?.test_cards || []).map((c: any) => (
                  <option key={c.id} value={c.test_pan_reference}>
                    {c.masked_pan} ({c.card_status})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-[11px] font-mono text-slate-400 mb-1">
                Server PIN Helper (Packs DE52)
              </label>
              <input
                type="password"
                value={clearPinHelper}
                onChange={(e) => setClearPinHelper(e.target.value)}
                placeholder="e.g. 1234 (Valid) or 9999"
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5 text-xs font-mono"
              />
            </div>
          </div>

          {/* Add Field Row */}
          <div className="flex items-center gap-2 pt-2">
            <select
              value={newFieldNum}
              onChange={(e) => setNewFieldNum(e.target.value)}
              className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5 text-xs font-mono"
            >
              {(catalog?.field_definitions || []).map((f: any) => (
                <option key={f.field_number} value={String(f.field_number)}>
                  DE{f.field_number} — {f.name} ({f.data_type}, {f.length_type}
                  {f.fixed_length ? ` ${f.fixed_length}` : ''})
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={addFieldToEditor}
              className="bg-slate-800 hover:bg-slate-700 text-white px-3 py-1.5 rounded text-xs font-mono"
            >
              + Enable Field
            </button>
          </div>

          {/* Field List */}
          <div className="space-y-2 max-h-[420px] overflow-y-auto pr-1">
            {Object.keys(fields)
              .sort((a, b) => Number(a) - Number(b))
              .map((fnum) => {
                const def = catalog?.field_definitions?.find(
                  (d: any) => String(d.field_number) === String(fnum)
                );
                const err = validationErrors[`DE${fnum}`];
                const isMandatory = ['2', '3', '4', '11', '37', '41', '49'].includes(fnum);
                return (
                  <div
                    key={fnum}
                    className={`p-2.5 rounded-lg border text-xs font-mono ${
                      err
                        ? 'border-rose-500 bg-rose-500/5'
                        : 'border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/50'
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <input
                        type="checkbox"
                        checked={enabledFields[fnum] !== false}
                        onChange={(e) =>
                          setEnabledFields({ ...enabledFields, [fnum]: e.target.checked })
                        }
                      />
                      <span className="w-14 font-bold text-emerald-500">
                        DE{fnum}
                        {isMandatory && <span className="text-rose-500">*</span>}
                      </span>
                      <span className="w-48 truncate text-slate-500 font-sans">
                        {def ? def.name : `TIC Field ${fnum}`}
                      </span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-200 dark:bg-slate-800 text-slate-500">
                        {def ? `${def.data_type} · ${def.length_type}${def.fixed_length ? `(${def.fixed_length})` : ''}` : ''}
                      </span>
                      <input
                        value={fields[fnum]}
                        onChange={(e) => setFields({ ...fields, [fnum]: e.target.value })}
                        disabled={enabledFields[fnum] === false}
                        className="flex-1 bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1 text-xs font-mono"
                      />
                    </div>
                    {err && <div className="text-rose-500 text-[11px] mt-1 pl-7">⚠ {err}</div>}
                  </div>
                );
              })}
          </div>
        </div>

        {/* Right 5 Cols: Raw TIC Editor, Decoded Inspector & Host Execution Result */}
        <div className="lg:col-span-5 space-y-5">
          {/* Raw TIC Message Box */}
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 space-y-3">
            <div className="flex justify-between items-center">
              <h2 className="text-sm font-bold">2. Raw TIC / TCI Wire Message (A4M Header)</h2>
              <div className="flex gap-2">
                <button
                  onClick={handleDecodeRaw}
                  className="text-[11px] font-mono px-2.5 py-1 rounded bg-slate-800 text-sky-400 hover:bg-slate-700"
                >
                  Decode Raw ➔ Fields
                </button>
                <button
                  onClick={() => navigator.clipboard.writeText(rawTic)}
                  className="text-[11px] font-mono px-2 py-1 rounded bg-slate-200 dark:bg-slate-800"
                  title="Copy Raw Message"
                >
                  <Copy size={12} />
                </button>
              </div>
            </div>
            <textarea
              rows={3}
              value={rawTic}
              onChange={(e) => setRawTic(e.target.value)}
              placeholder="A4M020000200..."
              className="w-full bg-slate-950 text-emerald-300 border border-slate-800 rounded-lg p-3 text-xs font-mono"
            />
            {compactTic && (
              <div>
                <div className="text-[11px] font-mono text-slate-400 mb-1">
                  Compact TIC Format (Ý / ³ Delimiters):
                </div>
                <div className="bg-slate-950 text-amber-300 border border-slate-800 rounded-lg p-2.5 text-[11px] font-mono break-all">
                  {compactTic}
                </div>
              </div>
            )}
          </div>

          {/* Host Authorization Outcome & Step-by-Step Trace */}
          {txResponse && (
            <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 space-y-4">
              <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 pb-3">
                <div>
                  <div className="text-xs font-mono text-slate-400">
                    {txResponse.transaction_reference}
                  </div>
                  <div className="text-base font-bold font-mono mt-0.5">
                    RC {txResponse.response_code} ({txResponse.response_tic_f39}) —{' '}
                    {txResponse.response_message}
                  </div>
                </div>
                <span
                  className={`px-3 py-1 rounded-full text-xs font-mono font-bold ${
                    txResponse.authorization_status === 'APPROVED'
                      ? 'bg-emerald-500/15 text-emerald-500 border border-emerald-500/30'
                      : 'bg-rose-500/15 text-rose-500 border border-rose-500/30'
                  }`}
                >
                  {txResponse.authorization_status}
                </span>
              </div>

              <div className="grid grid-cols-2 gap-2 text-xs font-mono">
                <div className="p-2 rounded bg-slate-50 dark:bg-slate-950">
                  <span className="text-slate-400">Response MTI:</span> {txResponse.response_mti}
                </div>
// [PATCH step02_02:sim_outcome_routing_badges]
                <div className="p-2 rounded bg-slate-50 dark:bg-slate-950">
                  <span className="text-slate-400">Switch & Route:</span> <span className="text-emerald-400 font-bold">{txResponse.ps_code || "ITCL"}</span> ({txResponse.is_on_us ? "ON-US" : "OFF-US"})
                </div>
                <div className="p-2 rounded bg-slate-50 dark:bg-slate-950">
                  <span className="text-slate-400">New Balance:</span>{' '}
                  {txResponse.account_balance_after !== null
                    ? `${txResponse.account_balance_after.toLocaleString()} ${txResponse.currency}`
                    : 'Unchanged'}
                </div>
              </div>

              <div>
                <div className="text-xs font-mono uppercase text-slate-400 mb-2">
                  HostTransactionProcessor Execution Trace ({txResponse.checks?.length || 0} Steps):
                </div>
                <div className="space-y-1.5 max-h-64 overflow-y-auto">
                  {(txResponse.checks || []).map((c: any) => (
                    <div
                      key={c.check_order}
                      className="flex items-start justify-between gap-2 p-2 rounded bg-slate-50 dark:bg-slate-950 text-xs font-mono border border-slate-200/60 dark:border-slate-800"
                    >
                      <div>
                        <span className="font-bold text-slate-400 mr-1.5">#{c.check_order}</span>
                        <span className="font-bold">{c.check_name}:</span>{' '}
                        <span className="text-slate-500 dark:text-slate-300">{c.message}</span>
                      </div>
                      <span
                        className={`shrink-0 px-1.5 py-0.5 rounded text-[10px] font-bold ${
                          c.check_status === 'PASSED'
                            ? 'bg-emerald-500/10 text-emerald-500'
                            : 'bg-rose-500/10 text-rose-500'
                        }`}
                      >
                        {c.check_status} (RC {c.response_code})
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Decoded View */}
          {decodedView && (
            <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 space-y-2">
              <h3 className="text-xs font-mono uppercase text-slate-400">
                Decoded TIC v2.164e Structure
              </h3>
              <pre className="bg-slate-950 text-sky-300 p-3 rounded-lg text-[11px] font-mono overflow-x-auto max-h-60">
                {JSON.stringify(decodedView.detailed_fields || decodedView, null, 2)}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

// ============================================================================
// PAGE 9: TRANSACTION JOURNAL
// ============================================================================
export const TransactionJournalPage: React.FC = () => {
  const [txs, setTxs] = useState<any[]>([]);
  const [stan, setStan] = useState('');
  const [rrn, setRrn] = useState('');
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalTxs, setTotalTxs] = useState(0);

  const load = async (p: number = page) => {
    const params = new URLSearchParams({ page: String(p), page_size: '25' });
    if (stan) params.set('stan', stan);
    if (rrn) params.set('rrn', rrn);
    if (status) params.set('status', status);
    const res = await apiFetch(`/transactions?${params.toString()}`);
    const items = Array.isArray(res) ? res : (res.items || []);
    setTxs(items);
    setTotalTxs(Array.isArray(res) ? items.length : (res.total ?? items.length));
    setTotalPages(Array.isArray(res) ? 1 : (res.total_pages || 1));
  };

  useEffect(() => {
    load(page);
  }, [page]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold">Host Transaction Journal</h1>
          <p className="text-xs text-slate-500">
            Complete immutable audit log of all processed authorizations, financial postings, and reversals
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <input
            value={stan}
            onChange={(e) => setStan(e.target.value)}
            placeholder="Filter STAN..."
            className="bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-1.5 text-xs font-mono"
          />
          <input
            value={rrn}
            onChange={(e) => setRrn(e.target.value)}
            placeholder="Filter RRN..."
            className="bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-1.5 text-xs font-mono"
          />
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-1.5 text-xs font-mono"
          >
            <option value="">ALL OUTCOMES</option>
            <option value="APPROVED">APPROVED</option>
            <option value="DECLINED">DECLINED</option>
          </select>
          <button
            onClick={() => { setPage(1); load(1); }}
            className="flex items-center gap-1 bg-emerald-600 text-white px-3.5 py-1.5 rounded-lg text-xs font-semibold"
          >
            <Search size={14} /> Search
          </button>
        </div>
      </div>

      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 overflow-x-auto">
        <table className="w-full text-left text-xs font-mono">
          <thead>
            <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-400">
              <th className="py-2.5">Reference</th>
              <th className="py-2.5">MTI / Code</th>
// [PATCH step02_02:journal_table_route_th]
              <th className="py-2.5">Switch / Route</th>
              <th className="py-2.5">STAN / RRN</th>
              <th className="py-2.5">Masked PAN</th>
              <th className="py-2.5">Amount</th>
              <th className="py-2.5">RC</th>
              <th className="py-2.5">Outcome</th>
              <th className="py-2.5">Timestamp</th>
              <th className="py-2.5">Inspect</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200/60 dark:divide-slate-800/60">
            {txs.map((t) => (
              <tr key={t.id}>
                <td className="py-2.5 font-bold text-sky-500">{t.transaction_reference}</td>
                <td className="py-2.5">
                  {t.mti} (Code {t.transaction_code || 'N/A'})
                </td>
// [PATCH step02_02:journal_table_route_td]
                <td className="py-2.5">
                  <span className="text-emerald-400 font-bold">{t.ps_code || "ITCL"}</span>
                  <span className={`ml-1.5 px-1.5 py-0.5 rounded text-[10px] font-bold ${t.is_on_us ? "bg-emerald-500/10 text-emerald-400" : "bg-sky-500/10 text-sky-400"}`}>
                    {t.is_on_us ? "ON-US" : "OFF-US"}
                  </span>
                </td>
                <td className="py-2.5">
                  {t.stan} / {t.rrn}
                </td>
                <td className="py-2.5">{t.masked_pan}</td>
                <td className="py-2.5 font-bold">
                  {t.transaction_amount.toLocaleString()} {t.currency}
                </td>
                <td className="py-2.5 font-bold">{t.response_code}</td>
                <td className="py-2.5">
                  <span
                    className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                      t.authorization_status === 'APPROVED'
                        ? 'bg-emerald-500/10 text-emerald-500'
                        : 'bg-rose-500/10 text-rose-500'
                    }`}
                  >
                    {t.authorization_status} ({t.transaction_status})
                  </span>
                </td>
                <td className="py-2.5">{new Date(t.created_at).toLocaleTimeString()}</td>
                <td className="py-2.5">
                  <Link
                    to={`/transactions/${t.id}`}
                    className="text-emerald-500 hover:underline font-bold"
                  >
                    Details ➔
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
// [PATCH step05:journal_pagination_bar_fixed]
        </table>
      </div>

      <div className="flex justify-between items-center bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-3 text-xs font-mono">
        <div className="text-slate-400">Total Journal Records: <strong className="text-emerald-500">{totalTxs}</strong></div>
        <div className="flex items-center gap-2">
          <button disabled={page <= 1} onClick={() => setPage(page - 1)} className="px-3 py-1 rounded border border-slate-300 dark:border-slate-700 disabled:opacity-40">Previous</button>
          <span>Page {page} of {totalPages}</span>
          <button disabled={page >= totalPages} onClick={() => setPage(page + 1)} className="px-3 py-1 rounded border border-slate-300 dark:border-slate-700 disabled:opacity-40">Next</button>
        </div>
      </div>
    </div>
  );
};

// ============================================================================
// PAGE 10: TRANSACTION DETAILS
// ============================================================================
export const TransactionDetailsPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [detail, setDetail] = useState<any>(null);

  useEffect(() => {
    if (id) apiFetch(`/transactions/${id}`).then(setDetail).catch(console.error);
  }, [id]);

  if (!detail) {
    return <div className="text-xs font-mono text-slate-400">Loading transaction trace...</div>;
  }

  const tx = detail.transaction;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <Link
            to="/transactions"
            className="inline-flex items-center gap-1 text-xs font-mono text-emerald-500 hover:underline mb-1"
          >
            <ArrowLeft size={14} /> Back to Transaction Journal
          </Link>
          <h1 className="text-xl font-bold font-mono">{tx.transaction_reference}</h1>
        </div>
        <span
          className={`px-3 py-1 rounded-full text-xs font-mono font-bold ${
            tx.authorization_status === 'APPROVED'
              ? 'bg-emerald-500/15 text-emerald-500'
              : 'bg-rose-500/15 text-rose-500'
          }`}
        >
          {tx.authorization_status} — RC {tx.response_code} ({tx.response_message})
        </span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-6 gap-3 text-xs font-mono">
        {[
          ['MTI', tx.mti],
          ['Processing Code', tx.processing_code],
          ['STAN', tx.stan],
          ['RRN', tx.rrn],
          ['Masked PAN', tx.masked_pan],
          ['Amount', `${tx.transaction_amount.toLocaleString()} ${tx.currency}`],
// [PATCH step02_02:tx_details_bank_cards]
          ['Switch System', `${tx.ps_code || 'ITCL'} (${tx.is_on_us ? 'ON-US' : 'OFF-US'})`],
          ['Issuing Bank', tx.issuer_code || 'XBANK'],
          ['Acquiring Bank', tx.acquirer_code || 'XBANK'],
        ].map(([k, v]) => (
          <div
            key={k}
            className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-3"
          >
            <div className="text-slate-400 text-[10px]">{k}</div>
            <div className="font-bold mt-1">{v}</div>
          </div>
        ))}
      </div>

      {/* Step-by-Step Checks */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5">
        <h2 className="text-sm font-bold mb-3">Authorization Checks Executed</h2>
        <div className="space-y-2">
          {detail.checks.map((c: any) => (
            <div
              key={c.check_order}
              className="flex justify-between items-center p-2.5 rounded bg-slate-50 dark:bg-slate-950 text-xs font-mono"
            >
              <div>
                <span className="text-slate-400 mr-2">Step {c.check_order}:</span>
                <span className="font-bold">{c.check_name}</span> — {c.message}
              </div>
              <span
                className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                  c.check_status === 'PASSED'
                    ? 'bg-emerald-500/10 text-emerald-500'
                    : 'bg-rose-500/10 text-rose-500'
                }`}
              >
                {c.check_status} ({c.duration_ms} ms)
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Sanitized Wire Messages */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 space-y-3">
        <h2 className="text-sm font-bold">Sanitized TIC Request & Response Messages</h2>
        {detail.messages.map((m: any, i: number) => (
          <div key={i} className="p-3 rounded bg-slate-950 text-xs font-mono space-y-1">
            <div className="text-emerald-400 font-bold">
              [{m.message_type} — MTI {m.mti}]
            </div>
            <div className="text-slate-200 break-all">{m.sanitized_message}</div>
          </div>
        ))}
      </div>
    </div>
  );
};
