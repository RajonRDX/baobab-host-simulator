import React, { useEffect, useState } from 'react';
import { Network, Server, Play, CheckCircle2, XCircle, AlertTriangle, Clock, RefreshCw, Lock, ArrowRight, ShieldCheck } from 'lucide-react';
import { apiFetch } from '../api';

export const NetworkRoutingPage: React.FC = () => {
  const [profiles, setProfiles] = useState<any[]>([]);
  const [testPan, setTestPan] = useState('4567890123450001');
  const [testResult, setTestResult] = useState<any | null>(null);
  const [msg, setMsg] = useState('');

  const loadProfiles = async () => {
    try {
      const res = await apiFetch('/networks/profiles');
      setProfiles(res);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    loadProfiles();
  }, []);

  const handleUpdateMode = async (p: any, mode: string, rc: string = '00', delay: number = 0) => {
    try {
      await apiFetch(`/networks/profiles/${p.id}`, {
        method: 'PUT',
        body: JSON.stringify({
          simulation_mode: mode,
          simulated_response_code: rc,
          simulated_delay_ms: delay,
        }),
      });
      setMsg(`Updated network ${p.network_name} behavior to ${mode}`);
      loadProfiles();
    } catch (err: any) {
      alert(err.message);
    }
  };

  const handleTestRoute = async () => {
    try {
      const res = await apiFetch('/networks/route-test', {
        method: 'POST',
        body: JSON.stringify({ pan: testPan }),
      });
      setTestResult(res);
    } catch (err: any) {
      alert(err.message);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold">Network Routing & Card Scheme Simulators</h1>
          <p className="text-xs text-slate-500">
            Configure external switch behaviors for Visa, Mastercard, and NPSB (Approve, Decline RC, Network Timeout, Link Unavailable)
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono px-2.5 py-1 rounded bg-emerald-500/10 text-emerald-500 border border-emerald-500/20 font-bold">
            Zone PIN Translation: AWK ➔ IWK Enabled
          </span>
        </div>
      </div>

      {msg && (
        <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs font-mono">
          {msg}
        </div>
      )}

      {/* Network Profiles Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {profiles.map((p) => (
          <div key={p.id} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 space-y-4 shadow-sm">
            <div className="flex justify-between items-center border-b border-slate-200 dark:border-slate-800 pb-3">
              <div>
                <h2 className="text-sm font-bold font-mono text-emerald-400">{p.network_name}</h2>
                <div className="text-[11px] text-slate-400 font-sans">{p.network_type}</div>
              </div>
              <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                p.simulation_mode === 'ALWAYS_APPROVE' ? 'bg-emerald-500/10 text-emerald-400' :
                p.simulation_mode === 'TIMEOUT' ? 'bg-amber-500/10 text-amber-400' : 'bg-rose-500/10 text-rose-400'
              }`}>
                {p.simulation_mode}
              </span>
            </div>

            <div className="space-y-3 text-xs font-mono">
              <div>
                <label className="block text-slate-400 mb-1">Simulation Mode</label>
                <select
                  value={p.simulation_mode}
                  onChange={(e) => handleUpdateMode(p, e.target.value, p.simulated_response_code, p.simulated_delay_ms)}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5"
                >
                  <option value="ALWAYS_APPROVE">ALWAYS_APPROVE (RC 00)</option>
                  <option value="DECLINE_WITH_RC">DECLINE_WITH_RC</option>
                  <option value="TIMEOUT">TIMEOUT (RC 91 + Auto-Reversal)</option>
                  <option value="UNAVAILABLE">UNAVAILABLE (RC 91 Link Inoperative)</option>
                </select>
              </div>

              {p.simulation_mode === 'DECLINE_WITH_RC' && (
                <div>
                  <label className="block text-slate-400 mb-1">Simulated Decline Response Code</label>
                  <select
                    value={p.simulated_response_code}
                    onChange={(e) => handleUpdateMode(p, p.simulation_mode, e.target.value, p.simulated_delay_ms)}
                    className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5"
                  >
                    <option value="51">51 — Insufficient Funds</option>
                    <option value="05">05 — Do Not Honor</option>
                    <option value="54">54 — Expired Card</option>
                    <option value="55">55 — Incorrect PIN</option>
                    <option value="61">61 — Exceeds Limit</option>
                  </select>
                </div>
              )}

              <div>
                <label className="block text-slate-400 mb-1">Simulated Network Latency (ms)</label>
                <input
                  type="number"
                  value={p.simulated_delay_ms}
                  onChange={(e) => handleUpdateMode(p, p.simulation_mode, p.simulated_response_code, parseInt(e.target.value) || 0)}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5"
                />
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Interactive PAN Routing Inspector */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 space-y-4">
        <h2 className="text-sm font-bold flex items-center gap-2">
          <Play size={15} className="text-emerald-500" /> Interactive BIN Routing & Outbound Dispatch Test
        </h2>
        <div className="flex gap-2">
          <input
            value={testPan}
            onChange={(e) => setTestPan(e.target.value)}
            placeholder="Enter synthetic PAN (e.g. 456789... or 512345...)"
            className="flex-1 bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono"
          />
          <button
            onClick={handleTestRoute}
            className="bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-lg text-xs font-semibold"
          >
            Resolve Route & Dispatch ➔
          </button>
        </div>

        {testResult && (
          <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono space-y-2">
            <div className="flex justify-between items-center border-b border-slate-800 pb-2">
              <span className="font-bold text-emerald-400">Routing Target: {testResult.routing.routing_target}</span>
              <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${testResult.routing.is_on_us ? 'bg-emerald-500/10 text-emerald-400' : 'bg-sky-500/10 text-sky-400'}`}>
                {testResult.routing.is_on_us ? 'ON-US (Internal ITCL)' : 'OFF-US (External Scheme)'}
              </span>
            </div>
            <div><span className="text-slate-400">Card Scheme:</span> {testResult.routing.scheme}</div>
            <div><span className="text-slate-400">Destination Adapter:</span> {testResult.routing.destination_network || 'None (Internal Host)'}</div>
            {testResult.outbound_response && (
              <div className="pt-2 border-t border-slate-800">
                <div className="text-[11px] text-amber-400 font-bold mb-1">Simulated Network Response:</div>
                <div>Status: <span className="font-bold text-emerald-400">{testResult.outbound_response.network_status}</span> (RC {testResult.outbound_response.response_code})</div>
                <div>Message: {testResult.outbound_response.response_message}</div>
                <div>Auth Code: {testResult.outbound_response.authorization_code}</div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
