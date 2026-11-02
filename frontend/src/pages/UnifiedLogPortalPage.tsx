import React, { useEffect, useState } from 'react';
import { Activity, Cpu, Search, CheckCircle2, XCircle, ArrowRight, Pause, Play, RefreshCw, KeyRound, Lock, Eye } from 'lucide-react';
import { apiFetch } from '../api';

export const UnifiedLogPortalPage: React.FC = () => {
  const [tab, setTab] = useState<'ALL' | 'CRYPTO' | 'API'>('ALL');
  const [logs, setLogs] = useState<any[]>([]);
  const [cryptoEvents, setCryptoEvents] = useState<any[]>([]);
  const [search, setSearch] = useState('');
  const [live, setLive] = useState(true);
  const [selectedCorrelation, setSelectedCorrelation] = useState<any | null>(null);

  const loadData = async () => {
    try {
      const q = search ? `?search=${encodeURIComponent(search)}` : '';
      const [tlRes, crRes] = await Promise.all([
        apiFetch(`/logs/timeline${q}`),
        apiFetch('/logs/crypto-events?limit=100'),
      ]);
      setLogs(tlRes.events || []);
      setCryptoEvents(crRes || []);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    loadData();
    if (!live) return;
    const interval = setInterval(loadData, 2500);
    return () => clearInterval(interval);
  }, [live, search]);

  const inspectCorrelation = async (corrId: string) => {
    try {
      const res = await apiFetch(`/logs/correlation/${corrId}`);
      setSelectedCorrelation(res);
    } catch (err: any) {
      alert(err.message);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold">Operational & Cryptographic Log Portal</h1>
          <p className="text-xs text-slate-500">
            End-to-end request tracing via X-Correlation-ID: inspect API dispatches, engine checks, wire messages, and granular 6-step PIN/HSM calculations
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search Correlation ID, STAN, or PAN..."
            className="bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-1.5 text-xs font-mono w-64"
          />
          <button
            onClick={() => setLive(!live)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono font-bold ${
              live ? 'bg-emerald-600 text-white' : 'bg-amber-600 text-white'
            }`}
          >
            {live ? <Pause size={13} /> : <Play size={13} />}
            {live ? 'LIVE AUTO-POLL' : 'PAUSED'}
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex flex-wrap gap-2 border-b border-slate-200 dark:border-slate-800 pb-2">
        {[
          ['ALL', '1. Unified Operation Timeline', Activity],
          ['CRYPTO', '2. Granular 6-Step Crypto Trace', Cpu],
          ['API', '3. API Ingestion Log', Lock],
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

      {/* TAB 1: UNIFIED TIMELINE */}
      {tab === 'ALL' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <div className="lg:col-span-7 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 overflow-x-auto">
            <h2 className="text-sm font-bold mb-3">Chronological Switch Events</h2>
            <div className="space-y-2 max-h-[580px] overflow-y-auto pr-1">
              {logs.map((ev, i) => (
                <div
                  key={i}
                  onClick={() => inspectCorrelation(ev.correlation_id || ev.id)}
                  className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 text-xs font-mono cursor-pointer hover:border-emerald-500 transition space-y-1"
                >
                  <div className="flex justify-between items-center">
                    <span className="font-bold text-emerald-400">[{ev.category}] {ev.title}</span>
                    <span className="text-slate-400 text-[11px]">{new Date(ev.timestamp).toLocaleTimeString()}</span>
                  </div>
                  <div className="text-slate-300 font-sans text-[11px]">{ev.message}</div>
                  <div className="flex justify-between items-center text-[10px] text-slate-400 pt-1 border-t border-slate-800/60">
                    <span>Correlation: <strong className="text-sky-400">{ev.correlation_id || 'N/A'}</strong></span>
                    <span>Status: <strong className="text-amber-400">{ev.status}</strong> · {ev.duration_ms}ms</span>
                  </div>
                </div>
              ))}
              {logs.length === 0 && (
                <div className="py-12 text-center text-slate-400 text-xs font-mono">
                  No operational events logged yet. Submit a transaction or change a PIN to generate traces.
                </div>
              )}
            </div>
          </div>

          <div className="lg:col-span-5 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 space-y-4">
            <h2 className="text-sm font-bold flex items-center gap-2">
              <Eye size={16} className="text-emerald-500" /> Correlated Request Deep Dive
            </h2>
            {selectedCorrelation ? (
              <div className="space-y-3 text-xs font-mono">
                <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 space-y-1">
                  <div>Correlation ID: <span className="text-sky-400 font-bold">{selectedCorrelation.correlation_id}</span></div>
                  <div>HTTP: {selectedCorrelation.api_audit?.http_method} {selectedCorrelation.api_audit?.path} ({selectedCorrelation.api_audit?.status_code})</div>
                  <div>Duration: {selectedCorrelation.api_audit?.duration_ms} ms</div>
                </div>

                {selectedCorrelation.crypto_steps && selectedCorrelation.crypto_steps.length > 0 && (
                  <div>
                    <div className="text-[11px] font-bold text-amber-400 mb-1.5">Granular Cryptographic Steps ({selectedCorrelation.crypto_steps.length}):</div>
                    <div className="space-y-1.5 max-h-72 overflow-y-auto">
                      {selectedCorrelation.crypto_steps.map((st: any) => (
                        <div key={st.id} className="p-2.5 rounded bg-slate-950 border border-slate-800 text-[11px] space-y-1">
                          <div className="flex justify-between text-emerald-400 font-bold">
                            <span>Step {st.step_number}: {st.step_name}</span>
                            <span>{st.status}</span>
                          </div>
                          {st.raw_input && <div><span className="text-slate-400">Input:</span> <span className="break-all text-sky-300">{st.raw_input}</span></div>}
                          {st.raw_output && <div><span className="text-slate-400">Output:</span> <span className="break-all text-amber-300">{st.raw_output}</span></div>}
                          {st.expected_output && <div><span className="text-slate-400">Expected:</span> <span className="break-all text-emerald-300">{st.expected_output}</span></div>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-slate-400 text-xs font-mono py-16 text-center">
                Click any timeline event on the left to inspect its correlated API parameters and HSM cryptographic transformations.
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 2: GRANULAR CRYPTO TRACE */}
      {tab === 'CRYPTO' && (
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 overflow-x-auto">
          <h2 className="text-sm font-bold mb-3">Soft-HSM Granular Transformation Steps (Visa PVV & PIN Translation)</h2>
          <table className="w-full text-left text-xs font-mono">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-400">
                <th className="py-2.5">Correlation ID</th>
                <th className="py-2.5">Step</th>
                <th className="py-2.5">Operation</th>
                <th className="py-2.5">Key (KCV)</th>
                <th className="py-2.5">Raw Input</th>
                <th className="py-2.5">Calculated Output</th>
                <th className="py-2.5">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200/60 dark:divide-slate-800/60">
              {cryptoEvents.map((ev) => (
                <tr key={ev.id}>
                  <td className="py-2.5 text-sky-400 font-bold">{ev.correlation_id}</td>
                  <td className="py-2.5 font-bold">#{ev.step_number} {ev.step_name}</td>
                  <td className="py-2.5">{ev.operation_type}</td>
                  <td className="py-2.5 text-amber-400">{ev.key_id} ({ev.key_kcv})</td>
                  <td className="py-2.5 break-all max-w-xs">{ev.raw_input || 'N/A'}</td>
                  <td className="py-2.5 break-all max-w-xs font-bold text-emerald-400">{ev.raw_output || 'N/A'}</td>
                  <td className="py-2.5">
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/10 text-emerald-500">
                      {ev.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* TAB 3: API AUDIT LOG */}
      {tab === 'API' && (
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 overflow-x-auto">
          <h2 className="text-sm font-bold mb-3">HTTP API Dispatch Logs (X-Correlation-ID Tracked)</h2>
          <div className="space-y-2 text-xs font-mono">
            {logs.filter(l => l.category === 'API').map((apiLog, idx) => (
              <div key={idx} className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 flex justify-between items-center">
                <div>
                  <span className="font-bold text-sky-400">{apiLog.title}</span>
                  <div className="text-[11px] text-slate-400">Correlation: {apiLog.correlation_id}</div>
                </div>
                <div className="text-right">
                  <span className="text-emerald-400 font-bold">{apiLog.status}</span>
                  <div className="text-[10px] text-slate-500">{apiLog.duration_ms} ms</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
