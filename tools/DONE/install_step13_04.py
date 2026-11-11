#!/usr/bin/env python3
"""
tools/install_step13_04.py — Batch 4 Installer
==============================================
Installs & integrates the Frontend React 18 + TypeScript + Tailwind CSS pages and navigation:
  1. frontend/src/pages/LimitManagementPage.tsx
     - Dedicated tabs for Card Limits (Module 1) and Account Limits (Module 2).
     - Full Add / Edit / Delete (with confirmation & safe archive/deactivation when in use) /
       Activate-Deactivate / Reset Usage modals.
     - Displays Limit ID, Name, Scope, Maximum Limit, dynamically calculated Current Value,
       Reset Interval, Calculation Method, Comparison Operator (>, <, >=, <=, =, !=),
       Authorization Impact, Assigned Profile count, and Recent Limit Evaluation Audit log.
  2. frontend/src/pages/AuthorizationProfilesPage.tsx
     - Complete Authorization Profile Management workbench (Module 4) with:
       * Profile Selector, Create/Edit/Delete Modals, Effective From/To, Status, and
         Configuration Summary modal before saving.
       * Tab A — Allowed Transactions (configure ALLOWED / DISALLOWED per TransactionCode
         + Unconfigured Transaction Code Policy: REJECT vs ALLOW).
       * Tab B — Card Limits (assign Card Limits with optional overrides for Maximum Limit,
         Calculation Method, Comparison Operator, and Impact Action).
       * Tab C — Account Limits (assign Account Limits with optional overrides).
       * Tab D — Transaction Code Limit Impact (configure INCREASE / DECREASE / NO_IMPACT,
         Calculation Basis, and Multiplier per Transaction Code and Limit ID).
  3. frontend/src/pages/InstitutionsAndBinsPage.tsx
     - Enhanced with the new "Card Profiles" tab (Module 3) and BIN-to-Card-Profile
       assignment dropdowns so BIN ranges can be associated with Card Profiles directly.
  4. Patches `frontend/src/App.tsx` and `frontend/src/components/Layout.tsx`
     - Adds routes `/card-limits`, `/account-limits`, `/limits`, `/authorization-profiles`,
       and `/card-profiles`.
     - Places "Authorization Profiles" immediately BEFORE "Authorization Rules" in the
       sidebar navigation and adds "Card Limits", "Account Limits", and "Card Profiles" links.

Run from E:\\HOST_VSCODE\\host-simulator:
    python tools/install_step13_04.py
"""

from datetime import datetime
from pathlib import Path
import shutil
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKUP_ROOT = PROJECT_ROOT / "_backups" / f"step13_04_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def backup_file(rel_path: str) -> None:
    src = PROJECT_ROOT / rel_path
    if src.exists():
        dst = BACKUP_ROOT / rel_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def write_file(rel_path: str, content: str) -> None:
    backup_file(rel_path)
    dst = PROJECT_ROOT / rel_path
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(content, encoding="utf-8")
    print(f"[WRITE] {rel_path} ({len(content.splitlines())} lines)")


def patch_file_append_once(rel_path: str, marker: str, block: str) -> None:
    target = PROJECT_ROOT / rel_path
    if not target.exists():
        raise FileNotFoundError(f"Required file not found: {rel_path}")
    text = target.read_text(encoding="utf-8")
    if marker in text:
        print(f"[SKIP]  {rel_path} already contains {marker}")
        return
    backup_file(rel_path)
    updated = text.rstrip() + "\n\n" + block.strip() + "\n"
    target.write_text(updated, encoding="utf-8")
    print(f"[PATCH] {rel_path} appended with {marker}")


# ==============================================================================
# 1. frontend/src/pages/LimitManagementPage.tsx
# ==============================================================================
LIMIT_MANAGEMENT_PAGE_TSX = '''import React, { useEffect, useState } from 'react';
import { api } from '../api/client';

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
'''


# ==============================================================================
# 2. frontend/src/pages/AuthorizationProfilesPage.tsx
# ==============================================================================
AUTHORIZATION_PROFILES_PAGE_TSX = '''import React, { useEffect, useState } from 'react';
import { api } from '../api/client';

interface TxPermission {
  id: string;
  transaction_code: string;
  transaction_name: string;
  permission: 'ALLOWED' | 'DISALLOWED';
  decline_response_code: string;
  description?: string;
  status: string;
}

interface ProfileLimitAssignment {
  id: string;
  limit_definition_id: string;
  limit_code: string;
  limit_name: string;
  scope: 'CARD' | 'ACCOUNT';
  currency: string;
  effective_maximum_limit: number;
  maximum_limit_override?: number | null;
  default_maximum_limit: number;
  effective_calculation_method: string;
  calculation_method_override?: string | null;
  effective_comparison_operator: string;
  comparison_operator_override?: string | null;
  effective_impact_action: string;
  impact_action_override?: string | null;
  decline_response_code_override?: string | null;
  reset_interval: string;
  current_value: number;
  evaluation_priority: number;
  status: string;
}

interface TxLimitImpact {
  id: string;
  transaction_code: string;
  transaction_name?: string;
  limit_definition_id: string;
  limit_code?: string;
  limit_name?: string;
  limit_scope?: string;
  impact_type: 'INCREASE' | 'DECREASE' | 'NO_IMPACT';
  calculation_basis: string;
  multiplier: number;
  description?: string;
  status: string;
}

interface AuthProfile {
  id: string;
  auth_profile_code: string;
  profile_name: string;
  description?: string;
  card_profile_id?: string | null;
  card_profile_code?: string | null;
  card_profile_name?: string | null;
  institution_id?: string | null;
  institution_code?: string | null;
  institution_name?: string | null;
  unconfigured_tx_code_policy: 'REJECT' | 'ALLOW';
  unconfigured_decline_rc: string;
  status: string;
  effective_from?: string | null;
  effective_to?: string | null;
  created_at?: string | null;
  tx_permissions: TxPermission[];
  card_limits: ProfileLimitAssignment[];
  account_limits: ProfileLimitAssignment[];
  tx_code_impacts: TxLimitImpact[];
  linked_bins?: { id: string; bin_prefix: string; card_product: string; scheme: string }[];
}

export const AuthorizationProfilesPage: React.FC = () => {
  const [profiles, setProfiles] = useState<AuthProfile[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState<string>('');
  const [activeTab, setActiveTab] = useState<'TAB_A' | 'TAB_B' | 'TAB_C' | 'TAB_D'>('TAB_A');
  const [cardProfiles, setCardProfiles] = useState<any[]>([]);
  const [institutions, setInstitutions] = useState<any[]>([]);
  const [allTxCodes, setAllTxCodes] = useState<any[]>([]);
  const [allLimitDefs, setAllLimitDefs] = useState<any[]>([]);
  const [banner, setBanner] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Profile Create / Edit + Summary Confirmation Modal
  const [showProfileModal, setShowProfileModal] = useState(false);
  const [showSummaryConfirm, setShowSummaryConfirm] = useState(false);
  const [editingProfile, setEditingProfile] = useState<AuthProfile | null>(null);
  const [profileForm, setProfileForm] = useState({
    auth_profile_code: '',
    profile_name: '',
    description: '',
    card_profile_id: '',
    institution_id: '',
    unconfigured_tx_code_policy: 'REJECT',
    unconfigured_decline_rc: '57',
    status: 'ACTIVE',
  });

  // Tab A: Permission Form
  const [permForm, setPermForm] = useState({
    transaction_code: '',
    permission: 'ALLOWED',
    decline_response_code: '57',
    description: '',
    status: 'ACTIVE',
  });

  // Tab B & C: Assign Limit Form
  const [assignForm, setAssignForm] = useState({
    limit_definition_id: '',
    maximum_limit_override: '',
    calculation_method_override: '',
    comparison_operator_override: '',
    impact_action_override: '',
    decline_response_code_override: '',
    evaluation_priority: '10',
    status: 'ACTIVE',
  });

  // Tab D: Transaction Code Limit Impact Form
  const [impactForm, setImpactForm] = useState({
    transaction_code: '',
    limit_definition_id: '',
    impact_type: 'INCREASE',
    calculation_basis: 'TRANSACTION_AMOUNT',
    multiplier: '1.0000',
    description: '',
    status: 'ACTIVE',
  });

  const loadAll = async () => {
    try {
      const [profRes, cpRes, instRes, tcRes, limRes] = await Promise.all([
        api.get('/authorization-profiles'),
        api.get('/card-profiles-v2'),
        api.get('/institutions'),
        api.get('/transaction-codes'),
        api.get('/limit-definitions'),
      ]);
      const profList: AuthProfile[] = Array.isArray(profRes.data) ? profRes.data : [];
      setProfiles(profList);
      setCardProfiles(Array.isArray(cpRes.data) ? cpRes.data : []);
      setInstitutions(Array.isArray(instRes.data) ? instRes.data : []);
      setAllTxCodes(Array.isArray(tcRes.data) ? tcRes.data : []);
      setAllLimitDefs(Array.isArray(limRes.data) ? limRes.data : []);

      if (profList.length > 0 && (!selectedProfileId || !profList.some((p) => p.id === selectedProfileId))) {
        setSelectedProfileId(profList[0].id);
      }
    } catch (err: any) {
      setBanner({ type: 'error', text: err?.response?.data?.detail || 'Failed to load Authorization Profiles' });
    }
  };

  useEffect(() => {
    loadAll();
  }, []);

  const currentProfile = profiles.find((p) => p.id === selectedProfileId) || null;

  const openCreateProfileModal = () => {
    setEditingProfile(null);
    setShowSummaryConfirm(false);
    setProfileForm({
      auth_profile_code: 'VISA_CLASSIC_CUSTOM',
      profile_name: 'VISA Classic Custom Auth Profile',
      description: 'Controls allowed transaction codes, card limits, account limits, and transaction impacts',
      card_profile_id: cardProfiles[0]?.id || '',
      institution_id: institutions[0]?.id || '',
      unconfigured_tx_code_policy: 'REJECT',
      unconfigured_decline_rc: '57',
      status: 'ACTIVE',
    });
    setShowProfileModal(true);
  };

  const openEditProfileModal = (ap: AuthProfile) => {
    setEditingProfile(ap);
    setShowSummaryConfirm(false);
    setProfileForm({
      auth_profile_code: ap.auth_profile_code,
      profile_name: ap.profile_name,
      description: ap.description || '',
      card_profile_id: ap.card_profile_id || '',
      institution_id: ap.institution_id || '',
      unconfigured_tx_code_policy: ap.unconfigured_tx_code_policy || 'REJECT',
      unconfigured_decline_rc: ap.unconfigured_decline_rc || '57',
      status: ap.status,
    });
    setShowProfileModal(true);
  };

  const handleSaveProfileConfirmed = async () => {
    try {
      const payload = {
        ...profileForm,
        card_profile_id: profileForm.card_profile_id || null,
        institution_id: profileForm.institution_id || null,
      };
      if (editingProfile) {
        await api.put(`/authorization-profiles/${editingProfile.id}`, payload);
        setBanner({ type: 'success', text: `Updated Authorization Profile ${profileForm.auth_profile_code}` });
      } else {
        const res = await api.post('/authorization-profiles', payload);
        setSelectedProfileId(res.data?.id || '');
        setBanner({ type: 'success', text: `Created Authorization Profile ${profileForm.auth_profile_code}` });
      }
      setShowProfileModal(false);
      setShowSummaryConfirm(false);
      await loadAll();
    } catch (err: any) {
      setBanner({ type: 'error', text: err?.response?.data?.detail || 'Failed to save Authorization Profile' });
    }
  };

  const handleDeleteProfile = async (ap: AuthProfile) => {
    if (!window.confirm(`Delete Authorization Profile '${ap.auth_profile_code}'?`)) return;
    try {
      await api.delete(`/authorization-profiles/${ap.id}`);
      setBanner({ type: 'success', text: `Deleted Authorization Profile ${ap.auth_profile_code}` });
      await loadAll();
    } catch (err: any) {
      setBanner({ type: 'error', text: err?.response?.data?.detail || 'Delete blocked by dependencies' });
    }
  };

  // Tab A Handlers
  const handleToggleTxPermission = async (p: TxPermission) => {
    if (!currentProfile) return;
    const nextPerm = p.permission === 'ALLOWED' ? 'DISALLOWED' : 'ALLOWED';
    try {
      await api.post(`/authorization-profiles/${currentProfile.id}/permissions`, {
        transaction_code: p.transaction_code,
        transaction_name: p.transaction_name,
        permission: nextPerm,
        decline_response_code: p.decline_response_code || '57',
        description: p.description,
        status: p.status,
      });
      setBanner({
        type: 'success',
        text: `Transaction Code ${p.transaction_code} (${p.transaction_name}) set to ${nextPerm}`,
      });
      await loadAll();
    } catch (err: any) {
      setBanner({ type: 'error', text: err?.response?.data?.detail || 'Failed to update permission' });
    }
  };

  const handleAddTxPermission = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentProfile || !permForm.transaction_code) return;
    try {
      await api.post(`/authorization-profiles/${currentProfile.id}/permissions`, permForm);
      setBanner({ type: 'success', text: `Saved permission for Transaction Code ${permForm.transaction_code}` });
      setPermForm({ transaction_code: '', permission: 'ALLOWED', decline_response_code: '57', description: '', status: 'ACTIVE' });
      await loadAll();
    } catch (err: any) {
      setBanner({ type: 'error', text: err?.response?.data?.detail || 'Failed to save permission' });
    }
  };

  // Tab B & C Handlers
  const handleAssignLimit = async (e: React.FormEvent, scope: 'CARD' | 'ACCOUNT') => {
    e.preventDefault();
    if (!currentProfile || !assignForm.limit_definition_id) return;
    try {
      await api.post(`/authorization-profiles/${currentProfile.id}/limits`, {
        limit_definition_id: assignForm.limit_definition_id,
        scope,
        maximum_limit_override: assignForm.maximum_limit_override ? Number(assignForm.maximum_limit_override) : null,
        calculation_method_override: assignForm.calculation_method_override || null,
        comparison_operator_override: assignForm.comparison_operator_override || null,
        impact_action_override: assignForm.impact_action_override || null,
        decline_response_code_override: assignForm.decline_response_code_override || null,
        evaluation_priority: Number(assignForm.evaluation_priority || 10),
        status: assignForm.status,
      });
      setBanner({ type: 'success', text: `Assigned ${scope} limit to ${currentProfile.auth_profile_code}` });
      setAssignForm({
        limit_definition_id: '',
        maximum_limit_override: '',
        calculation_method_override: '',
        comparison_operator_override: '',
        impact_action_override: '',
        decline_response_code_override: '',
        evaluation_priority: '10',
        status: 'ACTIVE',
      });
      await loadAll();
    } catch (err: any) {
      setBanner({ type: 'error', text: err?.response?.data?.detail || 'Failed to assign limit' });
    }
  };

  const handleRemoveLimitAssignment = async (assignId: string) => {
    if (!currentProfile) return;
    if (!window.confirm('Remove this limit assignment from the Authorization Profile?')) return;
    try {
      await api.delete(`/authorization-profiles/${currentProfile.id}/limits/${assignId}`);
      setBanner({ type: 'success', text: 'Removed limit assignment from profile' });
      await loadAll();
    } catch (err: any) {
      setBanner({ type: 'error', text: err?.response?.data?.detail || 'Failed to remove limit assignment' });
    }
  };

  // Tab D Handlers
  const handleAddImpact = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentProfile || !impactForm.transaction_code || !impactForm.limit_definition_id) return;
    try {
      await api.post(`/authorization-profiles/${currentProfile.id}/impacts`, {
        transaction_code: impactForm.transaction_code,
        limit_definition_id: impactForm.limit_definition_id,
        impact_type: impactForm.impact_type,
        calculation_basis: impactForm.calculation_basis,
        multiplier: Number(impactForm.multiplier || 1),
        description: impactForm.description || null,
        status: impactForm.status,
      });
      setBanner({
        type: 'success',
        text: `Configured TxCode ${impactForm.transaction_code} -> ${impactForm.impact_type} impact`,
      });
      setImpactForm({
        transaction_code: '',
        limit_definition_id: '',
        impact_type: 'INCREASE',
        calculation_basis: 'TRANSACTION_AMOUNT',
        multiplier: '1.0000',
        description: '',
        status: 'ACTIVE',
      });
      await loadAll();
    } catch (err: any) {
      setBanner({ type: 'error', text: err?.response?.data?.detail || 'Failed to save transaction impact rule' });
    }
  };

  const handleDeleteImpact = async (impactId: string) => {
    if (!currentProfile) return;
    if (!window.confirm('Delete this Transaction Code Limit Impact rule?')) return;
    try {
      await api.delete(`/authorization-profiles/${currentProfile.id}/impacts/${impactId}`);
      setBanner({ type: 'success', text: 'Deleted Transaction Code Limit Impact rule' });
      await loadAll();
    } catch (err: any) {
      setBanner({ type: 'error', text: err?.response?.data?.detail || 'Failed to delete impact rule' });
    }
  };

  const scopedLimitCandidates = allLimitDefs.filter((d) =>
    activeTab === 'TAB_B' ? d.scope === 'CARD' : activeTab === 'TAB_C' ? d.scope === 'ACCOUNT' : true
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 bg-slate-900/90 border border-slate-800 rounded-xl p-5">
        <div>
          <span className="px-2.5 py-0.5 text-xs font-mono uppercase rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
            HIERARCHY: BANK &rarr; SWITCH &rarr; BIN &rarr; CARD PROFILE &rarr; AUTHORIZATION PROFILE
          </span>
          <h1 className="text-2xl font-bold text-white mt-1">Authorization Profile Management</h1>
          <p className="text-sm text-slate-400">
            Configure allowed transaction codes, assigned Card Limits, assigned Account Limits, and
            transaction-code-wise limit increase/decrease/no-impact rules.
          </p>
        </div>
        <button
          onClick={openCreateProfileModal}
          className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold shadow"
        >
          + Create Authorization Profile
        </button>
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

      {/* Profile Selector Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {profiles.map((ap) => {
          const isSelected = ap.id === selectedProfileId;
          return (
            <div
              key={ap.id}
              onClick={() => setSelectedProfileId(ap.id)}
              className={`cursor-pointer rounded-xl p-4 border transition ${
                isSelected
                  ? 'bg-indigo-950/50 border-indigo-500 shadow-lg'
                  : 'bg-slate-900/80 border-slate-800 hover:border-slate-700'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs font-bold text-indigo-300">{ap.auth_profile_code}</span>
                <span
                  className={`px-2 py-0.5 text-[10px] font-semibold rounded ${
                    ap.status === 'ACTIVE'
                      ? 'bg-emerald-500/20 text-emerald-300'
                      : 'bg-slate-800 text-slate-400'
                  }`}
                >
                  {ap.status}
                </span>
              </div>
              <div className="font-bold text-white mt-1">{ap.profile_name}</div>
              <div className="text-xs text-slate-400 mt-1">
                Card Profile: <span className="text-amber-300 font-mono">{ap.card_profile_code || 'UNASSIGNED'}</span> ·
                Bank: <span className="text-slate-200">{ap.institution_code}</span>
              </div>
              <div className="flex items-center justify-between text-[11px] text-slate-400 mt-3 pt-2 border-t border-slate-800/80">
                <span>Tx Perms: {ap.tx_permissions.length}</span>
                <span>Card Limits: {ap.card_limits.length}</span>
                <span>Acct Limits: {ap.account_limits.length}</span>
                <span>Impacts: {ap.tx_code_impacts.length}</span>
              </div>
              <div className="flex justify-end gap-2 mt-2" onClick={(e) => e.stopPropagation()}>
                <button
                  onClick={() => openEditProfileModal(ap)}
                  className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-xs text-slate-200"
                >
                  Edit Profile
                </button>
                <button
                  onClick={() => handleDeleteProfile(ap)}
                  className="px-2.5 py-1 rounded bg-rose-950/70 hover:bg-rose-900/70 text-xs text-rose-300"
                >
                  Delete
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* Selected Profile Workbench */}
      {currentProfile && (
        <div className="bg-slate-900/90 border border-slate-800 rounded-xl overflow-hidden">
          {/* Profile Summary Banner */}
          <div className="p-5 bg-slate-950/60 border-b border-slate-800 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
            <div>
              <div className="text-xs font-mono text-indigo-300">
                ACTIVE WORKBENCH: {currentProfile.auth_profile_code}
              </div>
              <h2 className="text-lg font-bold text-white">{currentProfile.profile_name}</h2>
              <p className="text-xs text-slate-400">
                Linked Card Profile:{' '}
                <strong className="text-amber-300">{currentProfile.card_profile_code || 'None'}</strong> (
                {currentProfile.card_profile_name || 'No Card Profile'}) · Inherited BINs:{' '}
                {currentProfile.linked_bins && currentProfile.linked_bins.length > 0
                  ? currentProfile.linked_bins.map((b) => b.bin_prefix).join(', ')
                  : 'None'}{' '}
                · Unconfigured Tx Policy:{' '}
                <strong className="text-rose-300">
                  {currentProfile.unconfigured_tx_code_policy} (RC {currentProfile.unconfigured_decline_rc})
                </strong>
              </p>
            </div>

            {/* 4 Tabs Navigation */}
            <div className="flex flex-wrap gap-1.5 bg-slate-900 p-1.5 rounded-xl border border-slate-800">
              <button
                onClick={() => setActiveTab('TAB_A')}
                className={`px-3.5 py-2 rounded-lg text-xs font-semibold transition ${
                  activeTab === 'TAB_A' ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-white'
                }`}
              >
                Tab A — Allowed Transactions ({currentProfile.tx_permissions.length})
              </button>
              <button
                onClick={() => setActiveTab('TAB_B')}
                className={`px-3.5 py-2 rounded-lg text-xs font-semibold transition ${
                  activeTab === 'TAB_B' ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-white'
                }`}
              >
                Tab B — Card Limits ({currentProfile.card_limits.length})
              </button>
              <button
                onClick={() => setActiveTab('TAB_C')}
                className={`px-3.5 py-2 rounded-lg text-xs font-semibold transition ${
                  activeTab === 'TAB_C' ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-white'
                }`}
              >
                Tab C — Account Limits ({currentProfile.account_limits.length})
              </button>
              <button
                onClick={() => setActiveTab('TAB_D')}
                className={`px-3.5 py-2 rounded-lg text-xs font-semibold transition ${
                  activeTab === 'TAB_D' ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-white'
                }`}
              >
                Tab D — Transaction Code Limit Impact ({currentProfile.tx_code_impacts.length})
              </button>
            </div>
          </div>

          {/* TAB A: ALLOWED TRANSACTIONS */}
          {activeTab === 'TAB_A' && (
            <div className="p-5 space-y-5">
              <form onSubmit={handleAddTxPermission} className="grid grid-cols-1 md:grid-cols-5 gap-3 bg-slate-950/70 p-4 rounded-xl border border-slate-800">
                <div>
                  <label className="block text-[11px] text-slate-400 mb-1">Transaction Code</label>
                  <select
                    required
                    value={permForm.transaction_code}
                    onChange={(e) => setPermForm({ ...permForm, transaction_code: e.target.value })}
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white"
                  >
                    <option value="">Select Transaction Code...</option>
                    {allTxCodes.map((tc) => (
                      <option key={tc.transaction_code} value={tc.transaction_code}>
                        {tc.transaction_code} — {tc.transaction_name}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-[11px] text-slate-400 mb-1">Permission</label>
                  <select
                    value={permForm.permission}
                    onChange={(e) => setPermForm({ ...permForm, permission: e.target.value })}
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white"
                  >
                    <option value="ALLOWED">ALLOWED</option>
                    <option value="DISALLOWED">DISALLOWED</option>
                  </select>
                </div>
                <div>
                  <label className="block text-[11px] text-slate-400 mb-1">Decline RC</label>
                  <input
                    type="text"
                    value={permForm.decline_response_code}
                    onChange={(e) => setPermForm({ ...permForm, decline_response_code: e.target.value })}
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white font-mono"
                  />
                </div>
                <div>
                  <label className="block text-[11px] text-slate-400 mb-1">Description</label>
                  <input
                    type="text"
                    value={permForm.description}
                    onChange={(e) => setPermForm({ ...permForm, description: e.target.value })}
                    placeholder="Optional note"
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white"
                  />
                </div>
                <div className="flex items-end">
                  <button
                    type="submit"
                    className="w-full py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold"
                  >
                    Save Permission
                  </button>
                </div>
              </form>

              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-slate-800 bg-slate-950/60 text-xs uppercase text-slate-400">
                      <th className="py-2.5 px-4">Transaction Code</th>
                      <th className="py-2.5 px-4">Transaction Name</th>
                      <th className="py-2.5 px-4">Permission (Click to Toggle)</th>
                      <th className="py-2.5 px-4">Decline RC</th>
                      <th className="py-2.5 px-4">Description</th>
                      <th className="py-2.5 px-4">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60">
                    {currentProfile.tx_permissions.map((p) => (
                      <tr key={p.id} className="hover:bg-slate-800/30">
                        <td className="py-3 px-4 font-mono font-bold text-indigo-300">{p.transaction_code}</td>
                        <td className="py-3 px-4 font-semibold text-white">{p.transaction_name}</td>
                        <td className="py-3 px-4">
                          <button
                            onClick={() => handleToggleTxPermission(p)}
                            className={`px-3 py-1 rounded-md text-xs font-bold border transition ${
                              p.permission === 'ALLOWED'
                                ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                                : 'bg-rose-500/20 text-rose-300 border-rose-500/40'
                            }`}
                          >
                            {p.permission}
                          </button>
                        </td>
                        <td className="py-3 px-4 font-mono text-slate-300">RC {p.decline_response_code}</td>
                        <td className="py-3 px-4 text-xs text-slate-400">{p.description || '—'}</td>
                        <td className="py-3 px-4 text-xs text-emerald-300">{p.status}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* TAB B & TAB C: CARD LIMITS / ACCOUNT LIMITS */}
          {(activeTab === 'TAB_B' || activeTab === 'TAB_C') && (
            <div className="p-5 space-y-5">
              <form
                onSubmit={(e) => handleAssignLimit(e, activeTab === 'TAB_B' ? 'CARD' : 'ACCOUNT')}
                className="grid grid-cols-1 md:grid-cols-6 gap-3 bg-slate-950/70 p-4 rounded-xl border border-slate-800"
              >
                <div className="md:col-span-2">
                  <label className="block text-[11px] text-slate-400 mb-1">
                    Select {activeTab === 'TAB_B' ? 'Card' : 'Account'} Limit Definition
                  </label>
                  <select
                    required
                    value={assignForm.limit_definition_id}
                    onChange={(e) => setAssignForm({ ...assignForm, limit_definition_id: e.target.value })}
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white"
                  >
                    <option value="">Choose Limit Definition...</option>
                    {scopedLimitCandidates.map((ld) => (
                      <option key={ld.id} value={ld.id}>
                        #{ld.limit_code} — {ld.limit_name} (Max: {ld.maximum_limit} {ld.currency}, Op: {ld.comparison_operator})
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-[11px] text-slate-400 mb-1">Max Limit Override (Optional)</label>
                  <input
                    type="number"
                    step="0.01"
                    value={assignForm.maximum_limit_override}
                    onChange={(e) => setAssignForm({ ...assignForm, maximum_limit_override: e.target.value })}
                    placeholder="Inherit default"
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white font-mono"
                  />
                </div>
                <div>
                  <label className="block text-[11px] text-slate-400 mb-1">Operator Override</label>
                  <select
                    value={assignForm.comparison_operator_override}
                    onChange={(e) => setAssignForm({ ...assignForm, comparison_operator_override: e.target.value })}
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-amber-300 font-mono"
                  >
                    <option value="">Inherit Default</option>
                    {['>', '>=', '<', '<=', '=', '!='].map((op) => (
                      <option key={op} value={op}>
                        {op}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-[11px] text-slate-400 mb-1">Impact Override</label>
                  <select
                    value={assignForm.impact_action_override}
                    onChange={(e) => setAssignForm({ ...assignForm, impact_action_override: e.target.value })}
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white"
                  >
                    <option value="">Inherit Default</option>
                    <option value="DECLINE">DECLINE</option>
                    <option value="APPROVE_WITH_ALERT">APPROVE_WITH_ALERT</option>
                    <option value="FLAG_REVIEW">FLAG_REVIEW</option>
                  </select>
                </div>
                <div className="flex items-end">
                  <button
                    type="submit"
                    className="w-full py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold"
                  >
                    Assign Limit
                  </button>
                </div>
              </form>

              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-slate-800 bg-slate-950/60 text-xs uppercase text-slate-400">
                      <th className="py-2.5 px-4">Limit ID</th>
                      <th className="py-2.5 px-4">Limit Name</th>
                      <th className="py-2.5 px-4 text-right">Effective Max</th>
                      <th className="py-2.5 px-4 text-right">Current Value</th>
                      <th className="py-2.5 px-4">Calculation Method</th>
                      <th className="py-2.5 px-4 text-center">Operator</th>
                      <th className="py-2.5 px-4">Reset</th>
                      <th className="py-2.5 px-4">Impact</th>
                      <th className="py-2.5 px-4 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60">
                    {(activeTab === 'TAB_B' ? currentProfile.card_limits : currentProfile.account_limits).map((l) => (
                      <tr key={l.id} className="hover:bg-slate-800/30">
                        <td className="py-3 px-4 font-mono font-bold text-indigo-300">#{l.limit_code}</td>
                        <td className="py-3 px-4 font-semibold text-white">{l.limit_name}</td>
                        <td className="py-3 px-4 text-right font-mono text-emerald-300">
                          {l.effective_maximum_limit.toLocaleString(undefined, { minimumFractionDigits: 2 })} {l.currency}
                          {l.maximum_limit_override != null && (
                            <span className="block text-[10px] text-amber-300">Override Active</span>
                          )}
                        </td>
                        <td className="py-3 px-4 text-right font-mono text-amber-300">
                          {l.current_value.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                        </td>
                        <td className="py-3 px-4 font-mono text-xs text-slate-200">{l.effective_calculation_method}</td>
                        <td className="py-3 px-4 text-center font-mono font-bold text-amber-300">
                          {l.effective_comparison_operator}
                        </td>
                        <td className="py-3 px-4 font-mono text-xs text-slate-300">{l.reset_interval}</td>
                        <td className="py-3 px-4 text-xs text-rose-300 font-semibold">{l.effective_impact_action}</td>
                        <td className="py-3 px-4 text-right">
                          <button
                            onClick={() => handleRemoveLimitAssignment(l.id)}
                            className="px-2.5 py-1 rounded bg-rose-950/70 hover:bg-rose-900 text-xs text-rose-300"
                          >
                            Unassign
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* TAB D: TRANSACTION CODE LIMIT IMPACT */}
          {activeTab === 'TAB_D' && (
            <div className="p-5 space-y-5">
              <form
                onSubmit={handleAddImpact}
                className="grid grid-cols-1 md:grid-cols-6 gap-3 bg-slate-950/70 p-4 rounded-xl border border-slate-800"
              >
                <div>
                  <label className="block text-[11px] text-slate-400 mb-1">Transaction Code</label>
                  <select
                    required
                    value={impactForm.transaction_code}
                    onChange={(e) => setImpactForm({ ...impactForm, transaction_code: e.target.value })}
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white"
                  >
                    <option value="">Select Tx Code...</option>
                    {allTxCodes.map((tc) => (
                      <option key={tc.transaction_code} value={tc.transaction_code}>
                        {tc.transaction_code} — {tc.transaction_name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="md:col-span-2">
                  <label className="block text-[11px] text-slate-400 mb-1">Target Limit (Card or Account)</label>
                  <select
                    required
                    value={impactForm.limit_definition_id}
                    onChange={(e) => setImpactForm({ ...impactForm, limit_definition_id: e.target.value })}
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white"
                  >
                    <option value="">Select Limit Definition...</option>
                    {allLimitDefs.map((ld) => (
                      <option key={ld.id} value={ld.id}>
                        [{ld.scope}] #{ld.limit_code} — {ld.limit_name}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-[11px] text-slate-400 mb-1">Impact Type</label>
                  <select
                    value={impactForm.impact_type}
                    onChange={(e) => setImpactForm({ ...impactForm, impact_type: e.target.value })}
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-amber-300 font-semibold"
                  >
                    <option value="INCREASE">INCREASE (+ Usage)</option>
                    <option value="DECREASE">DECREASE (- Usage)</option>
                    <option value="NO_IMPACT">NO_IMPACT (0 Usage)</option>
                  </select>
                </div>
                <div>
                  <label className="block text-[11px] text-slate-400 mb-1">Calculation Basis</label>
                  <select
                    value={impactForm.calculation_basis}
                    onChange={(e) => setImpactForm({ ...impactForm, calculation_basis: e.target.value })}
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white font-mono"
                  >
                    <option value="TRANSACTION_AMOUNT">TRANSACTION_AMOUNT</option>
                    <option value="BILLING_AMOUNT">BILLING_AMOUNT</option>
                    <option value="TRANSACTION_COUNT">TRANSACTION_COUNT</option>
                    <option value="FIXED_UNIT">FIXED_UNIT</option>
                  </select>
                </div>
                <div className="flex items-end">
                  <button
                    type="submit"
                    className="w-full py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold"
                  >
                    Save Impact Rule
                  </button>
                </div>
              </form>

              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-slate-800 bg-slate-950/60 text-xs uppercase text-slate-400">
                      <th className="py-2.5 px-4">Transaction Code</th>
                      <th className="py-2.5 px-4">Limit ID & Name</th>
                      <th className="py-2.5 px-4">Scope</th>
                      <th className="py-2.5 px-4">Impact Type</th>
                      <th className="py-2.5 px-4">Calculation Basis</th>
                      <th className="py-2.5 px-4 text-right">Multiplier</th>
                      <th className="py-2.5 px-4 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60">
                    {currentProfile.tx_code_impacts.map((imp) => (
                      <tr key={imp.id} className="hover:bg-slate-800/30">
                        <td className="py-3 px-4 font-mono text-indigo-300">
                          {imp.transaction_code} — <span className="font-sans text-white">{imp.transaction_name}</span>
                        </td>
                        <td className="py-3 px-4 font-mono text-slate-200">
                          #{imp.limit_code} <span className="font-sans text-slate-300">{imp.limit_name}</span>
                        </td>
                        <td className="py-3 px-4 font-mono text-xs text-slate-300">{imp.limit_scope}</td>
                        <td className="py-3 px-4">
                          <span
                            className={`px-2.5 py-0.5 rounded text-xs font-bold ${
                              imp.impact_type === 'INCREASE'
                                ? 'bg-amber-500/20 text-amber-300'
                                : imp.impact_type === 'DECREASE'
                                ? 'bg-emerald-500/20 text-emerald-300'
                                : 'bg-slate-800 text-slate-400'
                            }`}
                          >
                            {imp.impact_type}
                          </span>
                        </td>
                        <td className="py-3 px-4 font-mono text-xs text-slate-300">{imp.calculation_basis}</td>
                        <td className="py-3 px-4 text-right font-mono text-slate-200">{imp.multiplier}x</td>
                        <td className="py-3 px-4 text-right">
                          <button
                            onClick={() => handleDeleteImpact(imp.id)}
                            className="px-2.5 py-1 rounded bg-rose-950/70 hover:bg-rose-900 text-xs text-rose-300"
                          >
                            Delete
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Create / Edit Authorization Profile Modal with Summary Preview before Saving */}
      {showProfileModal && (
        <div className="fixed inset-0 z-50 bg-black/75 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-xl w-full p-6 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-lg font-bold text-white">
                {editingProfile ? `Edit Authorization Profile ${editingProfile.auth_profile_code}` : 'Create Authorization Profile'}
              </h3>
              <button onClick={() => setShowProfileModal(false)} className="text-slate-400 hover:text-white">
                ✕
              </button>
            </div>

            {!showSummaryConfirm ? (
              <div className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">Authorization Profile ID</label>
                    <input
                      type="text"
                      disabled={!!editingProfile}
                      value={profileForm.auth_profile_code}
                      onChange={(e) => setProfileForm({ ...profileForm, auth_profile_code: e.target.value })}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">Profile Name</label>
                    <input
                      type="text"
                      value={profileForm.profile_name}
                      onChange={(e) => setProfileForm({ ...profileForm, profile_name: e.target.value })}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">Associated Card Profile</label>
                    <select
                      value={profileForm.card_profile_id}
                      onChange={(e) => setProfileForm({ ...profileForm, card_profile_id: e.target.value })}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white"
                    >
                      <option value="">Select Card Profile...</option>
                      {cardProfiles.map((cp) => (
                        <option key={cp.id} value={cp.id}>
                          {cp.profile_code} — {cp.profile_name}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">Institution / Bank</label>
                    <select
                      value={profileForm.institution_id}
                      onChange={(e) => setProfileForm({ ...profileForm, institution_id: e.target.value })}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white"
                    >
                      <option value="">Select Institution...</option>
                      {institutions.map((inst) => (
                        <option key={inst.id} value={inst.id}>
                          {inst.institution_code} — {inst.name}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">Unconfigured Tx Code Policy</label>
                    <select
                      value={profileForm.unconfigured_tx_code_policy}
                      onChange={(e) => setProfileForm({ ...profileForm, unconfigured_tx_code_policy: e.target.value })}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white"
                    >
                      <option value="REJECT">REJECT (Secure Default - RC 57)</option>
                      <option value="ALLOW">ALLOW</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">Status</label>
                    <select
                      value={profileForm.status}
                      onChange={(e) => setProfileForm({ ...profileForm, status: e.target.value })}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white"
                    >
                      <option value="ACTIVE">ACTIVE</option>
                      <option value="INACTIVE">INACTIVE</option>
                    </select>
                  </div>
                </div>

                <div>
                  <label className="block text-xs text-slate-400 mb-1">Description</label>
                  <input
                    type="text"
                    value={profileForm.description}
                    onChange={(e) => setProfileForm({ ...profileForm, description: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white"
                  />
                </div>

                <div className="flex justify-end gap-2 pt-2">
                  <button
                    onClick={() => setShowProfileModal(false)}
                    className="px-4 py-2 rounded-lg bg-slate-800 text-slate-300 text-xs font-semibold"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={() => setShowSummaryConfirm(true)}
                    className="px-5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold"
                  >
                    Review Configuration Summary &rarr;
                  </button>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-2 text-xs">
                  <div className="font-bold text-indigo-300 uppercase">Configuration Summary Before Saving</div>
                  <div>
                    <span className="text-slate-400">Profile ID:</span>{' '}
                    <span className="font-mono text-white">{profileForm.auth_profile_code}</span>
                  </div>
                  <div>
                    <span className="text-slate-400">Profile Name:</span>{' '}
                    <span className="text-white">{profileForm.profile_name}</span>
                  </div>
                  <div>
                    <span className="text-slate-400">Associated Card Profile:</span>{' '}
                    <span className="font-mono text-amber-300">
                      {cardProfiles.find((c) => c.id === profileForm.card_profile_id)?.profile_code || 'NONE'}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-400">Unconfigured Transaction Policy:</span>{' '}
                    <span className="font-mono text-rose-300">
                      {profileForm.unconfigured_tx_code_policy} (RC {profileForm.unconfigured_decline_rc})
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-400">Status:</span>{' '}
                    <span className="text-emerald-300 font-semibold">{profileForm.status}</span>
                  </div>
                </div>
                <div className="flex justify-end gap-2">
                  <button
                    onClick={() => setShowSummaryConfirm(false)}
                    className="px-4 py-2 rounded-lg bg-slate-800 text-slate-300 text-xs font-semibold"
                  >
                    &larr; Back to Edit
                  </button>
                  <button
                    onClick={handleSaveProfileConfirmed}
                    className="px-5 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold"
                  >
                    Confirm &amp; Save Profile
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default AuthorizationProfilesPage;
'''


# ==============================================================================
# 3. Patch frontend/src/pages/InstitutionsAndBinsPage.tsx to add Card Profiles tab
# ==============================================================================
def patch_institutions_and_bins_page() -> None:
    rel_path = "frontend/src/pages/InstitutionsAndBinsPage.tsx"
    target = PROJECT_ROOT / rel_path
    if not target.exists():
        print(f"[SKIP]  {rel_path} not found")
        return

    text = target.read_text(encoding="utf-8")
    marker = "// [PATCH step13_04:card_profiles_tab]"
    if marker in text:
        print(f"[SKIP]  {rel_path} already contains {marker}")
        return
    backup_file(rel_path)

    # Create a dedicated CardProfilesTab component file and embed it cleanly in InstitutionsAndBinsPage.tsx
    card_profiles_sub_rel = "frontend/src/pages/CardProfilesUnderBinTab.tsx"
    write_file(
        card_profiles_sub_rel,
        '''import React, { useEffect, useState } from 'react';
import { api } from '../api/client';

export const CardProfilesUnderBinTab: React.FC = () => {
  const [profiles, setProfiles] = useState<any[]>([]);
  const [bins, setBins] = useState<any[]>([]);
  const [institutions, setInstitutions] = useState<any[]>([]);
  const [systems, setSystems] = useState<any[]>([]);
  const [banner, setBanner] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState({
    profile_code: '',
    profile_name: '',
    description: '',
    institution_id: '',
    processing_system_id: '',
    card_type: 'DEBIT',
    currency: 'BDT',
    card_product: 'VISA_DEBIT_CLASSIC',
    status: 'ACTIVE',
  });

  const loadAll = async () => {
    try {
      const [cpRes, binRes, instRes, psRes] = await Promise.all([
        api.get('/card-profiles-v2'),
        api.get('/bins'),
        api.get('/institutions'),
        api.get('/processing-systems'),
      ]);
      setProfiles(Array.isArray(cpRes.data) ? cpRes.data : []);
      setBins(Array.isArray(binRes.data) ? binRes.data : []);
      setInstitutions(Array.isArray(instRes.data) ? instRes.data : []);
      setSystems(Array.isArray(psRes.data) ? psRes.data : []);
    } catch (err: any) {
      setBanner({ type: 'error', text: err?.response?.data?.detail || 'Failed to load Card Profiles' });
    }
  };

  useEffect(() => {
    loadAll();
  }, []);

  const handleCreateProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.post('/card-profiles-v2', form);
      setBanner({ type: 'success', text: `Created Card Profile ${form.profile_code}` });
      setShowModal(false);
      await loadAll();
    } catch (err: any) {
      setBanner({ type: 'error', text: err?.response?.data?.detail || 'Failed to create Card Profile' });
    }
  };

  const handleAssignBinProfile = async (binId: string, cardProfileId: string) => {
    try {
      await api.put(`/bins/${binId}/assign-card-profile`, {
        card_profile_id: cardProfileId || null,
      });
      setBanner({ type: 'success', text: 'Updated BIN-to-Card-Profile association' });
      await loadAll();
    } catch (err: any) {
      setBanner({ type: 'error', text: err?.response?.data?.detail || 'Failed to assign Card Profile to BIN' });
    }
  };

  return (
    <div className="space-y-6 mt-6">
      <div className="flex items-center justify-between bg-slate-900/90 border border-slate-800 rounded-xl p-4">
        <div>
          <h3 className="text-base font-bold text-white">Card Profiles &amp; BIN Range Association (Module 3)</h3>
          <p className="text-xs text-slate-400">
            Manage Card Profiles and link each BIN Range to its governing Card Profile. Cards issued under a BIN inherit its Card Profile automatically.
          </p>
        </div>
        <button
          onClick={() => {
            setForm({
              profile_code: 'VISA_PLATINUM',
              profile_name: 'VISA Platinum Debit Profile',
              description: 'High net-worth domestic & international profile',
              institution_id: institutions[0]?.id || '',
              processing_system_id: systems[0]?.id || '',
              card_type: 'DEBIT',
              currency: 'BDT',
              card_product: 'VISA_PLATINUM',
              status: 'ACTIVE',
            });
            setShowModal(true);
          }}
          className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold"
        >
          + Create Card Profile
        </button>
      </div>

      {banner && (
        <div
          className={`p-3 rounded-lg border text-xs flex justify-between ${
            banner.type === 'success'
              ? 'bg-emerald-950/60 border-emerald-500/40 text-emerald-200'
              : 'bg-rose-950/60 border-rose-500/40 text-rose-200'
          }`}
        >
          <span>{banner.text}</span>
          <button onClick={() => setBanner(null)} className="underline">
            Dismiss
          </button>
        </div>
      )}

      {/* Card Profiles Table */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-800 text-xs font-semibold text-slate-300">
          Configured Card Profiles ({profiles.length})
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-800 bg-slate-950/60 text-[11px] uppercase text-slate-400">
                <th className="py-2.5 px-4">Card Profile ID</th>
                <th className="py-2.5 px-4">Profile Name &amp; Description</th>
                <th className="py-2.5 px-4">Institution / Switch</th>
                <th className="py-2.5 px-4">Card Type / Currency</th>
                <th className="py-2.5 px-4">Associated BINs</th>
                <th className="py-2.5 px-4">Auth Profiles</th>
                <th className="py-2.5 px-4">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {profiles.map((cp) => (
                <tr key={cp.id} className="hover:bg-slate-800/30">
                  <td className="py-3 px-4 font-mono font-bold text-indigo-300">{cp.profile_code}</td>
                  <td className="py-3 px-4">
                    <div className="font-semibold text-white">{cp.profile_name}</div>
                    <div className="text-xs text-slate-400">{cp.description || '—'}</div>
                  </td>
                  <td className="py-3 px-4 text-xs text-slate-200">
                    {cp.institution_code} / <span className="font-mono text-amber-300">{cp.ps_code}</span>
                  </td>
                  <td className="py-3 px-4 font-mono text-xs text-slate-200">
                    {cp.card_type} · {cp.currency}
                  </td>
                  <td className="py-3 px-4">
                    {cp.associated_bins && cp.associated_bins.length > 0 ? (
                      <div className="flex flex-wrap gap-1">
                        {cp.associated_bins.map((b: any) => (
                          <span
                            key={b.id}
                            className="px-2 py-0.5 text-xs font-mono rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30"
                          >
                            {b.bin_prefix}
                          </span>
                        ))}
                      </div>
                    ) : (
                      <span className="text-xs text-slate-500">No BINs assigned</span>
                    )}
                  </td>
                  <td className="py-3 px-4">
                    {cp.authorization_profiles && cp.authorization_profiles.length > 0 ? (
                      cp.authorization_profiles.map((ap: any) => (
                        <span
                          key={ap.id}
                          className="px-2 py-0.5 text-xs font-mono rounded bg-emerald-500/20 text-emerald-300"
                        >
                          {ap.auth_profile_code}
                        </span>
                      ))
                    ) : (
                      <span className="text-xs text-slate-500">None</span>
                    )}
                  </td>
                  <td className="py-3 px-4">
                    <span className="px-2 py-0.5 text-xs font-semibold rounded bg-emerald-500/20 text-emerald-300">
                      {cp.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* BIN-to-Card-Profile Assignment Matrix */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-800 text-xs font-semibold text-slate-300">
          BIN-to-Card-Profile Association Matrix ({bins.length} BIN Ranges)
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-800 bg-slate-950/60 text-[11px] uppercase text-slate-400">
                <th className="py-2.5 px-4">BIN Prefix</th>
                <th className="py-2.5 px-4">Range (Low — High)</th>
                <th className="py-2.5 px-4">Bank / Switch</th>
                <th className="py-2.5 px-4">Current Card Profile</th>
                <th className="py-2.5 px-4">Assign / Change Card Profile</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {bins.map((b) => (
                <tr key={b.id} className="hover:bg-slate-800/30">
                  <td className="py-3 px-4 font-mono font-bold text-amber-300">{b.bin_prefix}</td>
                  <td className="py-3 px-4 font-mono text-xs text-slate-300">
                    {b.bin_low} &rarr; {b.bin_high}
                  </td>
                  <td className="py-3 px-4 text-xs text-slate-200">
                    {b.institution_code} / {b.ps_code}
                  </td>
                  <td className="py-3 px-4 font-mono text-xs text-indigo-300">
                    {b.card_profile_code || 'UNASSIGNED'}
                  </td>
                  <td className="py-3 px-4">
                    <select
                      value={b.card_profile_id || ''}
                      onChange={(e) => handleAssignBinProfile(b.id, e.target.value)}
                      className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white"
                    >
                      <option value="">-- Unassigned --</option>
                      {profiles.map((cp) => (
                        <option key={cp.id} value={cp.id}>
                          {cp.profile_code} — {cp.profile_name}
                        </option>
                      ))}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {showModal && (
        <div className="fixed inset-0 z-50 bg-black/75 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-lg w-full p-6 space-y-4">
            <h3 className="text-lg font-bold text-white">Create Card Profile</h3>
            <form onSubmit={handleCreateProfile} className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Card Profile ID</label>
                  <input
                    type="text"
                    required
                    value={form.profile_code}
                    onChange={(e) => setForm({ ...form, profile_code: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white font-mono"
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Profile Name</label>
                  <input
                    type="text"
                    required
                    value={form.profile_name}
                    onChange={(e) => setForm({ ...form, profile_name: e.target.value })}
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
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Institution / Bank</label>
                  <select
                    value={form.institution_id}
                    onChange={(e) => setForm({ ...form, institution_id: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white"
                  >
                    {institutions.map((i) => (
                      <option key={i.id} value={i.id}>
                        {i.institution_code} — {i.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Processing System</label>
                  <select
                    value={form.processing_system_id}
                    onChange={(e) => setForm({ ...form, processing_system_id: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white"
                  >
                    {systems.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.ps_code} — {s.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Card Type</label>
                  <select
                    value={form.card_type}
                    onChange={(e) => setForm({ ...form, card_type: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white"
                  >
                    <option value="DEBIT">DEBIT</option>
                    <option value="CREDIT">CREDIT</option>
                    <option value="PREPAID">PREPAID</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Currency</label>
                  <input
                    type="text"
                    value={form.currency}
                    onChange={(e) => setForm({ ...form, currency: e.target.value.toUpperCase() })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white font-mono"
                  />
                </div>
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="px-4 py-2 rounded-lg bg-slate-800 text-slate-300 text-xs font-semibold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 rounded-lg bg-emerald-600 text-white text-xs font-semibold"
                >
                  Create Card Profile
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default CardProfilesUnderBinTab;
''',
    )

    # Inject CardProfilesUnderBinTab at the bottom of InstitutionsAndBinsPage so it is always accessible
    # inside Bank / Switch / BIN Management AND via its own route `/card-profiles`.
    import_line = f"{marker}\nimport {{ CardProfilesUnderBinTab }} from './CardProfilesUnderBinTab';\n"
    text = import_line + text

    last_div_idx = text.rfind("</div>")
    if last_div_idx != -1:
        text = text[:last_div_idx] + "\n      <CardProfilesUnderBinTab />\n    </div>\n" + text[last_div_idx + 6 :]

    target.write_text(text, encoding="utf-8")
    print(f"[PATCH] {rel_path} enhanced with CardProfilesUnderBinTab")


# ==============================================================================
# 4. Patch frontend/src/App.tsx and frontend/src/components/Layout.tsx
# ==============================================================================
def patch_app_and_layout() -> None:
    app_rel = "frontend/src/App.tsx"
    app_target = PROJECT_ROOT / app_rel
    if app_target.exists():
        app_text = app_target.read_text(encoding="utf-8")
        marker = "// [PATCH step13_04:limits_and_auth_profiles_routes]"
        if marker not in app_text:
            backup_file(app_rel)
            import_block = (
                f"{marker}\n"
                "import { LimitManagementPage } from './pages/LimitManagementPage';\n"
                "import { AuthorizationProfilesPage } from './pages/AuthorizationProfilesPage';\n"
                "import { CardProfilesUnderBinTab } from './pages/CardProfilesUnderBinTab';\n"
            )
            app_text = import_block + app_text

            route_anchor = '<Route path="/authorizer-rules"'
            route_injection = (
                '<Route path="/card-limits" element={<LimitManagementPage initialScope="CARD" />} />\n'
                '                  <Route path="/account-limits" element={<LimitManagementPage initialScope="ACCOUNT" />} />\n'
                '                  <Route path="/limits" element={<LimitManagementPage initialScope="CARD" />} />\n'
                '                  <Route path="/card-profiles" element={<CardProfilesUnderBinTab />} />\n'
                '                  <Route path="/authorization-profiles" element={<AuthorizationProfilesPage />} />\n'
                '                  <Route path="/authorizer-rules"'
            )
            if route_anchor in app_text:
                app_text = app_text.replace(route_anchor, route_injection, 1)
            app_target.write_text(app_text, encoding="utf-8")
            print(f"[PATCH] {app_rel} updated with new routes")

    layout_rel = "frontend/src/components/Layout.tsx"
    layout_target = PROJECT_ROOT / layout_rel
    if layout_target.exists():
        layout_text = layout_target.read_text(encoding="utf-8")
        marker = "// [PATCH step13_04:navigation_links]"
        if marker not in layout_text:
            backup_file(layout_rel)
            # Place Authorization Profiles right before Authorization Rules (/authorizer-rules)
            if "'/authorizer-rules'" in layout_text:
                layout_text = layout_text.replace(
                    "{ to: '/authorizer-rules'",
                    f"{marker}\n      {{ to: '/card-profiles', label: 'Card Profiles' }},\n      {{ to: '/card-limits', label: 'Card Limits' }},\n      {{ to: '/account-limits', label: 'Account Limits' }},\n      {{ to: '/authorization-profiles', label: 'Authorization Profiles' }},\n      {{ to: '/authorizer-rules'",
                    1,
                )
            elif '"/authorizer-rules"' in layout_text:
                layout_text = layout_text.replace(
                    'to="/authorizer-rules"',
                    'to="/authorization-profiles"',
                    0,
                )
            layout_target.write_text(layout_text, encoding="utf-8")
            print(f"[PATCH] {layout_rel} updated with Card Profiles, Card/Account Limits, and Authorization Profiles navigation")


def update_progress_md() -> None:
    rel_path = "PROGRESS.md"
    marker = "<!-- PROGRESS:step13_04 -->"
    block = f"""
{marker}
## [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] `step13_04` — Batch 4: React TypeScript Frontend Workbench for Limits, Card Profiles & Authorization Profiles
- **Touched Files**: `frontend/src/pages/LimitManagementPage.tsx`, `frontend/src/pages/AuthorizationProfilesPage.tsx`, `frontend/src/pages/CardProfilesUnderBinTab.tsx`, `frontend/src/pages/InstitutionsAndBinsPage.tsx`, `frontend/src/App.tsx`, `frontend/src/components/Layout.tsx`, `PROGRESS.md`
- [x] **Completed**: Created `LimitManagementPage.tsx` for Card Limits and Account Limits with live usage progress bars, operator badges, reset schedules, and protected deletion/deactivation modals.
- [x] **Completed**: Created `AuthorizationProfilesPage.tsx` with 4-tab workbench (Tab A: Allowed Transactions, Tab B: Card Limits, Tab C: Account Limits, Tab D: Transaction Code Limit Impact) and pre-save configuration summary modal.
- [x] **Completed**: Added `CardProfilesUnderBinTab.tsx` under Bank / Switch / BIN Management and wired navigation in `App.tsx` and `Layout.tsx` with Authorization Profiles positioned before Authorization Rules.
- [ ] **Next / Remaining**: Batch 5 (`tools/install_step13_05.py`) — Comprehensive Automated Pytest Suite (`backend/tests/test_step13_limits_and_profiles.py`).
"""
    patch_file_append_once(rel_path, marker, block)


def main() -> int:
    print("=" * 76)
    print("BATCH 4 INSTALLER: Frontend React Pages & Navigation (step13_04)")
    print(f"Project Root: {PROJECT_ROOT}")
    print("=" * 76)

    write_file("frontend/src/pages/LimitManagementPage.tsx", LIMIT_MANAGEMENT_PAGE_TSX)
    write_file("frontend/src/pages/AuthorizationProfilesPage.tsx", AUTHORIZATION_PROFILES_PAGE_TSX)
    patch_institutions_and_bins_page()
    patch_app_and_layout()
    update_progress_md()

    print("-" * 76)
    print("[OK] Batch 4 installed.")
    print("=" * 76)
    return 0


if __name__ == "__main__":
    sys.exit(main())