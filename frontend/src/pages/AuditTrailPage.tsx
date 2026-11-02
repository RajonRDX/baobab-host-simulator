import React, { useEffect, useState } from 'react';
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
