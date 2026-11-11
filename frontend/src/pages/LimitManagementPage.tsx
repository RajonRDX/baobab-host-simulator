import React, { useEffect, useState } from 'react';
import { api } from '../services/api';

interface LimitDef {
  id: string;
  limit_code: string;
  limit_name: string;
  description?: string;
  scope: 'CARD' | 'ACCOUNT';
  currency: string;
  maximum_limit: number;
  current_value: number;
  active_window_key?: string;
  reset_interval: string;
  reset_interval_hours?: number | null;
  reset_anchor_time: string;
  calculation_method: string;
  comparison_operator: string;
  impact_action: string;
  decline_response_code: string;
  institution_id?: string | null;
  institution_code?: string;
  status: string;
  assigned_profiles_count: number;
  historical_usage_count: number;
  created_at?: string;
}

interface EvalAuditItem {
  id: string;
  transaction_reference?: string;
  limit_code: string;
  limit_name: string;
  scope: string;
  transaction_code: string;
  calculation_method: string;
  reset_interval: string;
  maximum_value: number;
  previous_usage: number;
  transaction_impact: number;
  projected_usage: number;
  comparison_operator: string;
  condition_matched: boolean;
  configured_action: string;
  final_result: string;
  response_code: string;
  decline_reason?: string;
  created_at?: string;
}

const CALC_METHODS = [
  'SUM_TRANSACTION_AMOUNT',
  'COUNT_TRANSACTION',
  'MAX_SINGLE_TRANSACTION',
  'MIN_SINGLE_TRANSACTION',
  'SUM_CASH_WITHDRAWAL',
  'SUM_PURCHASE',
  'SUM_TRANSFER',
  'CUSTOM_SUPPORTED_AGGREGATION',
];

const OPERATORS = ['>', '>=', '<', '<=', '=', '!='];
const RESET_INTERVALS = ['DAILY', 'WEEKLY', 'MONTHLY', 'YEARLY', 'PER_TRANSACTION', 'CUSTOM_HOURS'];
const IMPACT_ACTIONS = ['DECLINE', 'APPROVE_WITH_ALERT', 'FLAG_REVIEW'];

export const LimitManagementPage: React.FC<{ initialScope?: 'CARD' | 'ACCOUNT' }> = ({ initialScope = 'CARD' }) => {
  const [activeScope, setActiveScope] = useState<'CARD' | 'ACCOUNT'>(initialScope);
  const [limits, setLimits] = useState<LimitDef[]>([]);
  const [audits, setAudits] = useState<EvalAuditItem[]>([]);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [loading, setLoading] = useState(false);
  const [banner, setBanner] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Add / Edit Modal State
  const [showModal, setShowModal] = useState(false);
  const [editingLimit, setEditingLimit] = useState<LimitDef | null>(null);
  const [form, setForm] = useState({
    limit_code: '',
    limit_name: '',
    description: '',
    scope: initialScope as 'CARD' | 'ACCOUNT',
    currency: 'BDT',
    maximum_limit: '10000',
    reset_interval: 'DAILY',
    reset_interval_hours: '',
    reset_anchor_time: '00:00',
    calculation_method: 'SUM_TRANSACTION_AMOUNT',
    comparison_operator: '>',
    impact_action: 'DECLINE',
    decline_response_code: '61',
    status: 'ACTIVE',
  });

  // Delete confirmation modal
  const [deleteTarget, setDeleteTarget] = useState<LimitDef | null>(null);

  useEffect(() => {
    setActiveScope(initialScope);
  }, [initialScope]);

  const loadData = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set('scope', activeScope);
      if (statusFilter) params.set('status', statusFilter);
      if (search.trim()) params.set('q', search.trim());
      const [limRes, audRes] = await Promise.all([
        api.get(`/limit-definitions?${params.toString()}`),
        api.get(`/limit-evaluations?scope=${activeScope}&limit=25`),
      ]);
      setLimits(Array.isArray(limRes.data) ? limRes.data : []);
      setAudits(Array.isArray(audRes.data) ? audRes.data : []);
    } catch (err: any) {
      setBanner({ type: 'error', text: err?.response?.data?.detail || 'Failed to load limits' });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [activeScope, statusFilter]);

  const openCreateModal = () => {
    setEditingLimit(null);
    setForm({
      limit_code: activeScope === 'CARD' ? '105' : '205',
      limit_name: '',
      description: '',
      scope: activeScope,
      currency: 'BDT',
      maximum_limit: activeScope === 'CARD' ? '25000' : '100000',
      reset_interval: 'DAILY',
      reset_interval_hours: '',
      reset_anchor_time: '00:00',
      calculation_method: 'SUM_TRANSACTION_AMOUNT',
      comparison_operator: '>',
      impact_action: 'DECLINE',
      decline_response_code: '61',
      status: 'ACTIVE',
    });
    setShowModal(true);
  };

  const openEditModal = (lim: LimitDef) => {
    setEditingLimit(lim);
    setForm({
      limit_code: lim.limit_code,
      limit_name: lim.limit_name,
      description: lim.description || '',
      scope: lim.scope,
      currency: lim.currency || 'BDT',
      maximum_limit: String(lim.maximum_limit),
      reset_interval: lim.reset_interval,
      reset_interval_hours: lim.reset_interval_hours ? String(lim.reset_interval_hours) : '',
      reset_anchor_time: lim.reset_anchor_time || '00:00',
      calculation_method: lim.calculation_method,
      comparison_operator: lim.comparison_operator,
      impact_action: lim.impact_action,
      decline_response_code: lim.decline_response_code || '61',
      status: lim.status,
    });
    setShowModal(true);
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setBanner(null);
    try {
      const payload: any = {
        limit_code: form.limit_code.trim(),
        limit_name: form.limit_name.trim(),
        description: form.description.trim() || null,
        scope: form.scope,
        currency: form.currency.trim().toUpperCase(),
        maximum_limit: Number(form.maximum_limit),
        reset_interval: form.reset_interval,
        reset_interval_hours: form.reset_interval === 'CUSTOM_HOURS' && form.reset_interval_hours ? Number(form.reset_interval_hours) : null,
        reset_anchor_time: form.reset_anchor_time || '00:00',
        calculation_method: form.calculation_method,
        comparison_operator: form.comparison_operator,
        impact_action: form.impact_action,
        decline_response_code: form.decline_response_code.trim() || '61',
        status: form.status,
      };
      if (editingLimit) {
        await api.put(`/limit-definitions/${editingLimit.id}`, payload);
        setBanner({ type: 'success', text: `Updated ${form.scope} Limit ${form.limit_code} (${form.limit_name})` });
      } else {
        await api.post('/limit-definitions', payload);
        setBanner({ type: 'success', text: `Created ${form.scope} Limit ${form.limit_code} (${form.limit_name})` });
      }
      setShowModal(false);
      await loadData();
    } catch (err: any) {
      setBanner({ type: 'error', text: err?.response?.data?.detail || 'Failed to save limit definition' });
    }
  };

  const handleToggleStatus = async (lim: LimitDef) => {
    const nextStatus = lim.status === 'ACTIVE' ? 'INACTIVE' : 'ACTIVE';
    try {
      await api.patch(`/limit-definitions/${lim.id}/status?status=${nextStatus}`);
      setBanner({ type: 'success', text: `Limit ${lim.limit_code} status set to ${nextStatus}` });
      await loadData();
    } catch (err: any) {
      setBanner({ type: 'error', text: err?.response?.data?.detail || 'Failed to update status' });
    }
  };

  const handleResetUsage = async (lim: LimitDef) => {
    try {
      const res = await api.post(`/limit-definitions/${lim.id}/reset-usage`);
      setBanner({
        type: 'success',
        text: `Reset active usage counters for Limit ${lim.limit_code} (${res.data?.records_reset ?? 0} window record(s) zeroed)`,
      });
      await loadData();
    } catch (err: any) {
      setBanner({ type: 'error', text: err?.response?.data?.detail || 'Failed to reset usage' });
    }
  };

  const handleConfirmDelete = async (archiveIfInUse: boolean, force: boolean = false) => {
    if (!deleteTarget) return;
    try {
      const res = await api.delete(
        `/limit-definitions/${deleteTarget.id}?archive_if_in_use=${archiveIfInUse}&force=${force}`
      );
      setBanner({
        type: 'success',
        text: res.data?.message || `Deleted limit ${deleteTarget.limit_code}`,
      });
      setDeleteTarget(null);
      await loadData();
    } catch (err: any) {
      setBanner({ type: 'error', text: err?.response?.data?.detail || 'Delete failed' });
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 bg-slate-900/90 border border-slate-800 rounded-xl p-5">
        <div>
          <div className="flex items-center gap-2">
            <span className="px-2.5 py-0.5 text-xs font-mono uppercase rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
              LIMIT CALCULATION ENGINE
            </span>
            <span className="px-2.5 py-0.5 text-xs font-mono uppercase rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
              {activeScope} SCOPE
            </span>
          </div>
          <h1 className="text-2xl font-bold text-white mt-1">
            {activeScope === 'CARD' ? 'Card Limit Management' : 'Account Limit Management'}
          </h1>
          <p className="text-sm text-slate-400">
            Configure reusable {activeScope.toLowerCase()}-level velocity & amount limits with dynamic calculation methods,
            configurable comparison operators (&gt;, &lt;, &gt;=, &lt;=, =, !=), and reset schedules.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="inline-flex rounded-lg bg-slate-950 p-1 border border-slate-800">
            <button
              onClick={() => setActiveScope('CARD')}
              className={`px-4 py-1.5 rounded-md text-xs font-semibold transition ${
                activeScope === 'CARD'
                  ? 'bg-indigo-600 text-white shadow'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              Card Limits (Module 1)
            </button>
            <button
              onClick={() => setActiveScope('ACCOUNT')}
              className={`px-4 py-1.5 rounded-md text-xs font-semibold transition ${
                activeScope === 'ACCOUNT'
                  ? 'bg-indigo-600 text-white shadow'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              Account Limits (Module 2)
            </button>
          </div>

          <button
            onClick={openCreateModal}
            className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold shadow transition"
          >
            + Add New {activeScope === 'CARD' ? 'Card' : 'Account'} Limit
          </button>
        </div>
      </div>

      {banner && (
        <div
          className={`p-4 rounded-xl border text-sm flex items-center justify-between ${
            banner.type === 'success'
              ? 'bg-emerald-950/60 border-emerald-500/40 text-emerald-200'
              : 'bg-rose-950/60 border-rose-500/40 text-rose-200'
          }`}
        >
          <span>{banner.text}</span>
          <button onClick={() => setBanner(null)} className="text-xs underline ml-4">
            Dismiss
          </button>
        </div>
      )}

      {/* Filter Bar */}
      <div className="flex flex-wrap items-center gap-3 bg-slate-900/70 border border-slate-800 rounded-xl p-4">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && loadData()}
          placeholder={`Search ${activeScope.toLowerCase()} limits by Limit ID (e.g. 100) or name...`}
          className="flex-1 min-w-[240px] bg-slate-950 border border-slate-800 rounded-lg px-3.5 py-2 text-sm text-white placeholder-slate-500"
        />
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200"
        >
          <option value="">All Statuses</option>
          <option value="ACTIVE">ACTIVE</option>
          <option value="INACTIVE">INACTIVE</option>
        </select>
        <button
          onClick={loadData}
          className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-200"
        >
          {loading ? 'Refreshing...' : 'Search / Refresh'}
        </button>
      </div>

      {/* Limits Table */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl overflow-hidden">
        <div className="px-5 py-3.5 border-b border-slate-800 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-200">
            Configured {activeScope === 'CARD' ? 'Card' : 'Account'} Limit Definitions ({limits.length})
          </h2>
          <span className="text-xs text-slate-400">
            Condition triggers configured Impact when: <code className="text-amber-300">Projected Value [Operator] Maximum Limit</code>
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-800 bg-slate-950/60 text-[11px] uppercase tracking-wider text-slate-400">
                <th className="py-3 px-4">Limit ID</th>
                <th className="py-3 px-4">Limit Name & Description</th>
                <th className="py-3 px-4 text-right">Maximum Limit</th>
                <th className="py-3 px-4 text-right">Current Value</th>
                <th className="py-3 px-4">Reset Schedule</th>
                <th className="py-3 px-4">Calculation Method</th>
                <th className="py-3 px-4 text-center">Operator</th>
                <th className="py-3 px-4">Impact / Action</th>
                <th className="py-3 px-4 text-center">Status</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/70 text-sm">
              {limits.length === 0 ? (
                <tr>
                  <td colSpan={10} className="py-8 text-center text-slate-500">
                    No {activeScope.toLowerCase()} limits found. Click "+ Add New Limit" to create one.
                  </td>
                </tr>
              ) : (
                limits.map((lim) => {
                  const pct = lim.maximum_limit > 0 ? Math.min(100, Math.round((lim.current_value / lim.maximum_limit) * 100)) : 0;
                  return (
                    <tr key={lim.id} className="hover:bg-slate-800/40 transition">
                      <td className="py-3.5 px-4 font-mono font-bold text-indigo-300">
                        #{lim.limit_code}
                      </td>
                      <td className="py-3.5 px-4">
                        <div className="font-semibold text-white">{lim.limit_name}</div>
                        <div className="text-xs text-slate-400 line-clamp-1">
                          {lim.description || 'No description'}
                        </div>
                        <div className="text-[11px] text-slate-500 mt-0.5">
                          Assigned Profiles: {lim.assigned_profiles_count} · Historical Evaluations: {lim.historical_usage_count}
                        </div>
                      </td>
                      <td className="py-3.5 px-4 text-right font-mono font-semibold text-slate-100">
                        {lim.calculation_method === 'COUNT_TRANSACTION'
                          ? `${lim.maximum_limit.toLocaleString()} TX`
                          : `${lim.maximum_limit.toLocaleString(undefined, { minimumFractionDigits: 2 })} ${lim.currency}`}
                      </td>
                      <td className="py-3.5 px-4 text-right">
                        <div className="font-mono font-semibold text-amber-300">
                          {lim.calculation_method === 'COUNT_TRANSACTION'
                            ? `${lim.current_value.toLocaleString()} TX`
                            : `${lim.current_value.toLocaleString(undefined, { minimumFractionDigits: 2 })} ${lim.currency}`}
                        </div>
                        <div className="w-24 ml-auto h-1.5 bg-slate-800 rounded-full overflow-hidden mt-1">
                          <div
                            className={`h-full ${pct >= 90 ? 'bg-rose-500' : pct >= 60 ? 'bg-amber-400' : 'bg-emerald-500'}`}
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </td>
                      <td className="py-3.5 px-4">
                        <span className="px-2 py-0.5 text-xs font-mono rounded bg-slate-800 text-slate-200 border border-slate-700">
                          {lim.reset_interval}
                        </span>
                        <div className="text-[11px] text-slate-500 mt-0.5 font-mono">
                          {lim.active_window_key}
                        </div>
                      </td>
                      <td className="py-3.5 px-4">
                        <span className="px-2.5 py-0.5 text-xs font-mono rounded bg-indigo-950/80 text-indigo-300 border border-indigo-500/30">
                          {lim.calculation_method}
                        </span>
                      </td>
                      <td className="py-3.5 px-4 text-center">
                        <span className="px-2.5 py-1 text-sm font-mono font-bold rounded bg-amber-500/20 text-amber-300 border border-amber-500/40">
                          {lim.comparison_operator}
                        </span>
                      </td>
                      <td className="py-3.5 px-4">
                        <span
                          className={`px-2 py-0.5 text-xs font-semibold rounded ${
                            lim.impact_action === 'DECLINE'
                              ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                              : 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                          }`}
                        >
                          {lim.impact_action} (RC {lim.decline_response_code})
                        </span>
                      </td>
                      <td className="py-3.5 px-4 text-center">
                        <button
                          onClick={() => handleToggleStatus(lim)}
                          className={`px-2.5 py-0.5 text-xs font-semibold rounded border transition ${
                            lim.status === 'ACTIVE'
                              ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40 hover:bg-emerald-500/30'
                              : 'bg-slate-800 text-slate-400 border-slate-700 hover:text-white'
                          }`}
                        >
                          {lim.status}
                        </button>
                      </td>
                      <td className="py-3.5 px-4 text-right space-x-1.5 whitespace-nowrap">
                        <button
                          onClick={() => openEditModal(lim)}
                          className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-xs text-slate-200"
                        >
                          Edit
                        </button>
                        <button
                          onClick={() => handleResetUsage(lim)}
                          className="px-2.5 py-1 rounded bg-amber-950/70 hover:bg-amber-900/70 text-xs text-amber-300 border border-amber-500/30"
                          title="Reset current window usage counter to 0"
                        >
                          Reset Usage
                        </button>
                        <button
                          onClick={() => setDeleteTarget(lim)}
                          className="px-2.5 py-1 rounded bg-rose-950/70 hover:bg-rose-900/70 text-xs text-rose-300 border border-rose-500/30"
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Live Limit Evaluation History Table */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl overflow-hidden">
        <div className="px-5 py-3.5 border-b border-slate-800 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-200">
            Recent {activeScope} Limit Evaluation Audit Trail ({audits.length})
          </h3>
          <span className="text-xs text-slate-400">
            Real-time trace from HostTransactionProcessor &amp; LimitCalculationEngine
          </span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="border-b border-slate-800 bg-slate-950/60 text-[11px] uppercase text-slate-400">
                <th className="py-2.5 px-3">Limit</th>
                <th className="py-2.5 px-3">Tx Ref / Code</th>
                <th className="py-2.5 px-3 text-right">Previous Usage</th>
                <th className="py-2.5 px-3 text-right">Tx Impact</th>
                <th className="py-2.5 px-3 text-right">Projected Usage</th>
                <th className="py-2.5 px-3 text-center">Condition</th>
                <th className="py-2.5 px-3 text-right">Max Limit</th>
                <th className="py-2.5 px-3 text-center">Verdict</th>
                <th className="py-2.5 px-3">Reason / Timestamp</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {audits.length === 0 ? (
                <tr>
                  <td colSpan={9} className="py-6 text-center text-slate-500">
                    No limit evaluations recorded yet for {activeScope} scope.
                  </td>
                </tr>
              ) : (
                audits.map((a) => (
                  <tr key={a.id} className="hover:bg-slate-800/30">
                    <td className="py-2.5 px-3 font-mono text-indigo-300">
                      #{a.limit_code} <span className="text-slate-300 font-sans">{a.limit_name}</span>
                    </td>
                    <td className="py-2.5 px-3 font-mono text-slate-300">
                      {a.transaction_reference || 'N/A'} (Code {a.transaction_code})
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-slate-300">
                      {a.previous_usage.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-amber-300">
                      +{a.transaction_impact.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono font-bold text-white">
                      {a.projected_usage.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </td>
                    <td className="py-2.5 px-3 text-center font-mono text-amber-300">
                      {a.comparison_operator}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-slate-300">
                      {a.maximum_value.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </td>
                    <td className="py-2.5 px-3 text-center">
                      <span
                        className={`px-2 py-0.5 rounded font-semibold ${
                          a.final_result === 'PASSED'
                            ? 'bg-emerald-500/20 text-emerald-300'
                            : 'bg-rose-500/20 text-rose-300'
                        }`}
                      >
                        {a.final_result} (RC {a.response_code})
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-slate-400">
                      <div>{a.decline_reason || 'Within configured limit threshold'}</div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Add / Edit Limit Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 bg-black/75 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-2xl w-full p-6 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-lg font-bold text-white">
                {editingLimit ? `Edit ${form.scope} Limit #${form.limit_code}` : `Create New ${form.scope} Limit`}
              </h3>
              <button onClick={() => setShowModal(false)} className="text-slate-400 hover:text-white text-sm">
                ✕
              </button>
            </div>

            <form onSubmit={handleSave} className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Limit ID (Unique Code)</label>
                  <input
                    type="text"
                    required
                    disabled={!!editingLimit}
                    value={form.limit_code}
                    onChange={(e) => setForm({ ...form, limit_code: e.target.value })}
                    placeholder="e.g. 100 or 200"
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white font-mono disabled:opacity-60"
                  />
                </div>
                <div className="md:col-span-2">
                  <label className="block text-xs text-slate-400 mb-1">Limit Name</label>
                  <input
                    type="text"
                    required
                    value={form.limit_name}
                    onChange={(e) => setForm({ ...form, limit_name: e.target.value })}
                    placeholder="e.g. Daily Transaction Limit"
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs text-slate-400 mb-1">Description</label>
                <input
                  type="text"
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                  placeholder="Explanation of how this limit is evaluated during authorization"
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white"
                />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Maximum Limit Value</label>
                  <input
                    type="number"
                    step="0.01"
                    required
                    value={form.maximum_limit}
                    onChange={(e) => setForm({ ...form, maximum_limit: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white font-mono"
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Comparison Operator</label>
                  <select
                    value={form.comparison_operator}
                    onChange={(e) => setForm({ ...form, comparison_operator: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-amber-300 font-mono"
                  >
                    {OPERATORS.map((op) => (
                      <option key={op} value={op}>
                        {op} (Projected {op} Maximum)
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Currency</label>
                  <input
                    type="text"
                    maxLength={3}
                    value={form.currency}
                    onChange={(e) => setForm({ ...form, currency: e.target.value.toUpperCase() })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white font-mono"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Calculation Method</label>
                  <select
                    value={form.calculation_method}
                    onChange={(e) => setForm({ ...form, calculation_method: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white font-mono"
                  >
                    {CALC_METHODS.map((m) => (
                      <option key={m} value={m}>
                        {m}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Reset Time / Schedule</label>
                  <select
                    value={form.reset_interval}
                    onChange={(e) => setForm({ ...form, reset_interval: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white font-mono"
                  >
                    {RESET_INTERVALS.map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Authorization Impact / Action</label>
                  <select
                    value={form.impact_action}
                    onChange={(e) => setForm({ ...form, impact_action: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white"
                  >
                    {IMPACT_ACTIONS.map((a) => (
                      <option key={a} value={a}>
                        {a}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Decline Response Code (ISO DE39)</label>
                  <input
                    type="text"
                    maxLength={5}
                    value={form.decline_response_code}
                    onChange={(e) => setForm({ ...form, decline_response_code: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white font-mono"
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Status</label>
                  <select
                    value={form.status}
                    onChange={(e) => setForm({ ...form, status: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white"
                  >
                    <option value="ACTIVE">ACTIVE</option>
                    <option value="INACTIVE">INACTIVE</option>
                  </select>
                </div>
              </div>

              <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-300 font-mono">
                Rule Preview: When <span className="text-indigo-300">{form.calculation_method}</span> ({form.reset_interval}){' '}
                <span className="text-amber-300 font-bold">{form.comparison_operator}</span>{' '}
                <span className="text-emerald-300">{Number(form.maximum_limit || 0).toLocaleString()}</span> &rarr;{' '}
                <span className="text-rose-300 font-bold">
                  {form.impact_action} (RC {form.decline_response_code})
                </span>
              </div>

              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="px-4 py-2 rounded-lg bg-slate-800 text-slate-300 text-xs font-semibold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold"
                >
                  {editingLimit ? 'Save Changes' : 'Create Limit Definition'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Confirmation Dialog */}
      {deleteTarget && (
        <div className="fixed inset-0 z-50 bg-black/75 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-lg w-full p-6 space-y-4">
            <h3 className="text-lg font-bold text-white">
              Delete {deleteTarget.scope} Limit #{deleteTarget.limit_code} ({deleteTarget.limit_name})?
            </h3>
            <p className="text-sm text-slate-300">
              Assigned Profiles: <strong className="text-white">{deleteTarget.assigned_profiles_count}</strong> ·
              Historical Usage Records: <strong className="text-white">{deleteTarget.historical_usage_count}</strong>
            </p>
            {(deleteTarget.assigned_profiles_count > 0 || deleteTarget.historical_usage_count > 0) && (
              <div className="p-3 rounded-lg bg-amber-950/60 border border-amber-500/40 text-xs text-amber-200">
                This limit is assigned to an authorization profile or has historical usage records.
                Deactivating/archiving is recommended to preserve audit history.
              </div>
            )}
            <div className="flex flex-wrap justify-end gap-2 pt-2">
              <button
                onClick={() => setDeleteTarget(null)}
                className="px-3.5 py-2 rounded-lg bg-slate-800 text-slate-300 text-xs font-semibold"
              >
                Cancel
              </button>
              <button
                onClick={() => handleConfirmDelete(true, false)}
                className="px-3.5 py-2 rounded-lg bg-amber-600 hover:bg-amber-500 text-white text-xs font-semibold"
              >
                Safely Deactivate (Recommended)
              </button>
              <button
                onClick={() => handleConfirmDelete(false, true)}
                className="px-3.5 py-2 rounded-lg bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold"
              >
                Force Hard Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default LimitManagementPage;
