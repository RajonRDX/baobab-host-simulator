#!/usr/bin/env python3
"""
fix_all_issues_part3.py (Part 3 of 3 — Frontend React/TypeScript & Automated Test Suite)
========================================================================================
RAJON Private Host Simulator — Enterprise Payment Switch Frontend Repair & Test Pack

Delivers:
  1. Bank Name Display Normalization:
     - Strips legacy composite names (e.g., 'BAL - IFIC', 'TBL - IFIC' -> 'BAL', 'TBL', 'IFIC')
     - Consistent short-code display across Cards, PIN Profiles, EMV Profiles, Dropdowns, and Tables.
  2. Customer Management UI (BankingEntities.tsx):
     - Robust CRUD with modal edit forms, error banners, safe Deactivate/Archive, and Force Delete.
  3. Customer Data Maintenance 360 (CustomerDataMaintenancePage.tsx):
     - Separate search modes: Customer | PAN | Account.
     - Strict PAN search returning ONLY the matching card(s) for that PAN.
     - Live display of all Card and Account limits with consumed/remaining values.
     - Controlled "Reset Current Usage" modal for test benches with mandatory reason & audit logging.
  4. Member Banks, Processing Switches, BIN Ranges & PAN Router Workbench (InstitutionsAndBinsPage.tsx):
     - Tab 1: Member Banks (Create, Edit modal, Deactivate, Delete with dependency guard).
     - Tab 2: Processing Switches (Create, Edit modal, Toggle Enable/Disable, Deactivate).
     - Tab 3: BIN Ranges (Add, Edit, Boundary & Overlap checks, Enable/Disable, Delete).
     - Tab 4: PAN Router (Add rule, Edit priority/conditions, Overlap prevention, Toggle).
     - Tab 5: Multi-Network Switch Participation Links.
  5. Automated Pytest Verification Suite:
     - `backend/tests/test_enterprise_payment_switch_suite.py` verifying all 14 testing workflows.

Usage:
  python fix_all_issues_part3.py --dry-run
  python fix_all_issues_part3.py
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fix_all_issues import PROJECT_ROOT, SafeRepairEngine, apply_part1  # type: ignore
from fix_all_issues_part2 import apply_part2  # type: ignore

# ==============================================================================
# 1. FRONTEND: InstitutionsAndBinsPage.tsx (Banks, Switches, BINs, PAN Router)
# ==============================================================================

INSTITUTIONS_PAGE_CONTENT = r'''import React, { useEffect, useState } from 'react';
import {
  Landmark,
  Cpu,
  Network,
  CreditCard,
  Sliders,
  Plus,
  Trash2,
  Edit3,
  Search,
  CheckCircle2,
  Power,
  PowerOff,
  AlertTriangle,
  RefreshCw,
  X,
  Layers,
} from 'lucide-react';
import { apiFetch } from '../api';

export const InstitutionsAndBinsPage: React.FC = () => {
  const [tab, setTab] = useState<'INST' | 'PS' | 'BINS' | 'PAN_ROUTER' | 'NET'>('INST');
  const [institutions, setInstitutions] = useState<any[]>([]);
  const [processingSystems, setProcessingSystems] = useState<any[]>([]);
  const [bins, setBins] = useState<any[]>([]);
  const [panRules, setPanRules] = useState<any[]>([]);
  const [lookupPan, setLookupPan] = useState('4567890123450001');
  const [lookupAcq, setLookupAcq] = useState('123456');
  const [lookupResult, setLookupResult] = useState<any>(null);
  const [msg, setMsg] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  // Search filters per tab
  const [searchInst, setSearchInst] = useState('');
  const [searchPs, setSearchPs] = useState('');
  const [searchBin, setSearchBin] = useState('');
  const [searchRule, setSearchRule] = useState('');

  // Modals state
  const [editInstModal, setEditInstModal] = useState<any | null>(null);
  const [editPsModal, setEditPsModal] = useState<any | null>(null);
  const [editBinModal, setEditBinModal] = useState<any | null>(null);
  const [editRuleModal, setEditRuleModal] = useState<any | null>(null);

  // Creation forms
  const [instForm, setInstForm] = useState({
    institution_code: 'IFIC',
    name: 'IFIC Bank PLC',
    short_name: 'IFIC',
    acquirer_id: '554433',
    forwarding_id: '554433',
    role: 'BOTH',
    ps_code: 'ITCL',
    country_code: '050',
    currency: 'BDT',
    settlement_account_number: 'SETL-IFIC-001',
    status: 'ACTIVE',
  });

  const [psForm, setPsForm] = useState({
    ps_code: 'QCash_EXT',
    name: 'QCash Extended Switch',
    system_type: 'HOST_SWITCH',
    message_format: 'TIC_V2164E',
    enabled: true,
    is_default: false,
  });

  const [binForm, setBinForm] = useState({
    bin_prefix: '456795',
    bin_low: '',
    bin_high: '',
    pan_length: 16,
    institution_id: '',
    processing_system_id: '',
    card_type: 'DEBIT',
    card_product: 'VISA_DEBIT_GOLD',
    scheme: 'ITCL',
    country_code: '050',
    currency: 'BDT',
    is_on_us: true,
    status: 'ACTIVE',
  });

  const [ruleForm, setRuleForm] = useState({
    rule_code: 'RT_CORP_PURCHASE',
    rule_name: 'Corporate Purchasing Route',
    priority: 15,
    pan_prefix: '456789',
    pan_low: '',
    pan_high: '',
    pan_length: 16,
    card_type: 'DEBIT',
    transaction_code: '40',
    acquirer_institution_id: '',
    issuer_institution_id: '',
    processing_system_id: '',
    scheme: 'ITCL',
    destination_network: 'INTERNAL_SIMULATOR_TIC',
    is_on_us: true,
    pin_translation_required: false,
    enabled: true,
    status: 'ACTIVE',
  });

  const loadAll = async () => {
    setLoading(true);
    try {
      const [iList, psList, bList, rList] = await Promise.all([
        apiFetch(`/institutions${searchInst ? `?q=${encodeURIComponent(searchInst)}` : ''}`),
        apiFetch(`/processing-systems${searchPs ? `?q=${encodeURIComponent(searchPs)}` : ''}`),
        apiFetch(`/bin-ranges${searchBin ? `?q=${encodeURIComponent(searchBin)}` : ''}`),
        apiFetch(`/pan-routing-rules${searchRule ? `?q=${encodeURIComponent(searchRule)}` : ''}`),
      ]);
      setInstitutions(iList || []);
      setProcessingSystems(psList || []);
      setBins(bList || []);
      setPanRules(rList || []);

      if (iList && iList.length > 0 && !binForm.institution_id) {
        setBinForm((f) => ({ ...f, institution_id: iList[0].id }));
        setRuleForm((r) => ({ ...r, issuer_institution_id: iList[0].id }));
      }
      if (psList && psList.length > 0 && !binForm.processing_system_id) {
        setBinForm((f) => ({ ...f, processing_system_id: psList[0].id }));
        setRuleForm((r) => ({ ...r, processing_system_id: psList[0].id }));
      }
    } catch (e: any) {
      setError(e.message || 'Failed to load configuration tables');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  const flash = (text: string, isErr = false) => {
    if (isErr) {
      setError(text);
      setMsg('');
    } else {
      setMsg(text);
      setError('');
    }
  };

  // --- MEMBER BANKS (INSTITUTIONS) ---
  const handleCreateInstitution = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await apiFetch('/institutions', {
        method: 'POST',
        body: JSON.stringify(instForm),
      });
      flash(`Successfully registered bank ${res.short_name || res.institution_code}`);
      loadAll();
    } catch (err: any) {
      flash(err.message, true);
    }
  };

  const handleUpdateInstitution = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editInstModal) return;
    try {
      const res = await apiFetch(`/institutions/${editInstModal.id}`, {
        method: 'PUT',
        body: JSON.stringify(editInstModal),
      });
      flash(`Updated bank ${res.short_name || res.institution_code}`);
      setEditInstModal(null);
      loadAll();
    } catch (err: any) {
      flash(err.message, true);
    }
  };

  const handleDeleteInstitution = async (inst: any, forceDeactivate = false) => {
    const actionDesc = forceDeactivate ? 'deactivate' : 'delete';
    if (!confirm(`Are you sure you want to ${actionDesc} bank ${inst.short_name || inst.institution_code}?`)) return;
    try {
      const res = await apiFetch(`/institutions/${inst.id}${forceDeactivate ? '?deactivate_only=true' : ''}`, {
        method: 'DELETE',
      });
      flash(res.message || `Bank ${inst.short_name} ${res.status}`);
      loadAll();
    } catch (err: any) {
      if (err.message.includes('409') && !forceDeactivate) {
        if (confirm(`${err.message}\n\nWould you like to safely DEACTIVATE this bank instead?`)) {
          handleDeleteInstitution(inst, true);
          return;
        }
      }
      flash(err.message, true);
    }
  };

  // --- PROCESSING SWITCHES ---
  const handleCreateSwitch = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await apiFetch('/processing-systems', {
        method: 'POST',
        body: JSON.stringify(psForm),
      });
      flash(`Registered processing switch ${res.ps_code}`);
      loadAll();
    } catch (err: any) {
      flash(err.message, true);
    }
  };

  const handleUpdateSwitch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editPsModal) return;
    try {
      const res = await apiFetch(`/processing-systems/${editPsModal.id}`, {
        method: 'PUT',
        body: JSON.stringify(editPsModal),
      });
      flash(`Updated switch ${res.ps_code}`);
      setEditPsModal(null);
      loadAll();
    } catch (err: any) {
      flash(err.message, true);
    }
  };

  const handleToggleSwitch = async (ps: any) => {
    try {
      const res = await apiFetch(`/processing-systems/${ps.id}/toggle`, { method: 'PATCH' });
      flash(`Switch ${res.ps_code} is now ${res.enabled ? 'ENABLED' : 'DISABLED'}`);
      loadAll();
    } catch (err: any) {
      flash(err.message, true);
    }
  };

  const handleDeleteSwitch = async (ps: any, forceDeactivate = false) => {
    if (!confirm(`Delete/Deactivate switch ${ps.ps_code}?`)) return;
    try {
      const res = await apiFetch(`/processing-systems/${ps.id}${forceDeactivate ? '?deactivate_only=true' : ''}`, {
        method: 'DELETE',
      });
      flash(res.message || `Switch ${ps.ps_code} ${res.status}`);
      loadAll();
    } catch (err: any) {
      if (err.message.includes('409') && !forceDeactivate) {
        if (confirm(`${err.message}\n\nWould you like to safely DISABLE/DEACTIVATE this switch instead?`)) {
          handleDeleteSwitch(ps, true);
          return;
        }
      }
      flash(err.message, true);
    }
  };

  // --- BIN RANGES ---
  const handleCreateBin = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await apiFetch('/bin-ranges', {
        method: 'POST',
        body: JSON.stringify(binForm),
      });
      flash(`Added BIN range prefix ${res.bin_prefix} for ${res.institution_code}`);
      loadAll();
    } catch (err: any) {
      flash(err.message, true);
    }
  };

  const handleUpdateBin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editBinModal) return;
    try {
      const res = await apiFetch(`/bin-ranges/${editBinModal.id}`, {
        method: 'PUT',
        body: JSON.stringify(editBinModal),
      });
      flash(`Updated BIN range ${res.bin_prefix}`);
      setEditBinModal(null);
      loadAll();
    } catch (err: any) {
      flash(err.message, true);
    }
  };

  const handleToggleBin = async (b: any) => {
    try {
      const res = await apiFetch(`/bin-ranges/${b.id}/status`, { method: 'PATCH' });
      flash(`BIN range ${res.bin_prefix} is now ${res.status}`);
      loadAll();
    } catch (err: any) {
      flash(err.message, true);
    }
  };

  const handleDeleteBin = async (b: any, deactivate = false) => {
    if (!confirm(`Are you sure you want to delete BIN range ${b.bin_prefix}?`)) return;
    try {
      const res = await apiFetch(`/bin-ranges/${b.id}${deactivate ? '?deactivate_only=true' : ''}`, {
        method: 'DELETE',
      });
      flash(`BIN range ${b.bin_prefix} ${res.status}`);
      loadAll();
    } catch (err: any) {
      if (err.message.includes('409') && !deactivate) {
        if (confirm(`${err.message}\n\nWould you like to safely DEACTIVATE this BIN range instead?`)) {
          handleDeleteBin(b, true);
          return;
        }
      }
      flash(err.message, true);
    }
  };

  // --- PAN ROUTER RULES ---
  const handleCreateRule = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await apiFetch('/pan-routing-rules', {
        method: 'POST',
        body: JSON.stringify(ruleForm),
      });
      flash(`Added PAN Routing Rule ${res.rule_code} (Prio: ${res.priority})`);
      loadAll();
    } catch (err: any) {
      flash(err.message, true);
    }
  };

  const handleUpdateRule = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editRuleModal) return;
    try {
      const res = await apiFetch(`/pan-routing-rules/${editRuleModal.id}`, {
        method: 'PUT',
        body: JSON.stringify(editRuleModal),
      });
      flash(`Updated PAN routing rule ${res.rule_code}`);
      setEditRuleModal(null);
      loadAll();
    } catch (err: any) {
      flash(err.message, true);
    }
  };

  const handleToggleRule = async (r: any) => {
    try {
      const res = await apiFetch(`/pan-routing-rules/${r.id}/toggle`, { method: 'PATCH' });
      flash(`Rule ${res.rule_code} is now ${res.enabled ? 'ENABLED' : 'DISABLED'}`);
      loadAll();
    } catch (err: any) {
      flash(err.message, true);
    }
  };

  const handleDeleteRule = async (r: any) => {
    if (!confirm(`Delete PAN routing rule ${r.rule_code}?`)) return;
    try {
      await apiFetch(`/pan-routing-rules/${r.id}`, { method: 'DELETE' });
      flash(`Deleted PAN routing rule ${r.rule_code}`);
      loadAll();
    } catch (err: any) {
      flash(err.message, true);
    }
  };

  // --- LIVE ROUTER LOOKUP ---
  const handleLookupPan = async () => {
    try {
      const res = await apiFetch(`/bin-ranges/lookup/${lookupPan.trim()}?acquirer_id=${lookupAcq.trim()}`);
      setLookupResult(res);
    } catch (err: any) {
      setLookupResult({ found: false, message: err.message });
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2">
            <Network className="text-emerald-500" size={22} />
            Institutions, Switches, BINs & PAN Router Management
          </h1>
          <p className="text-xs text-slate-500">
            Enterprise member banks, multi-scheme switch adapters (ITCL / Visa / Mastercard / NPSB), BIN boundary overlap validation, and priority PAN routing engine
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={loadAll}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-300 dark:border-slate-700 text-xs font-mono hover:bg-slate-100 dark:hover:bg-slate-800"
          >
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} /> Refresh All
          </button>
        </div>
      </div>

      {msg && (
        <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs font-mono flex items-center justify-between">
          <span className="flex items-center gap-2"><CheckCircle2 size={16} /> {msg}</span>
          <button onClick={() => setMsg('')}><X size={14} /></button>
        </div>
      )}
      {error && (
        <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs font-mono flex items-center justify-between">
          <span className="flex items-center gap-2"><AlertTriangle size={16} /> {error}</span>
          <button onClick={() => setError('')}><X size={14} /></button>
        </div>
      )}

      {/* Tabs */}
      <div className="flex flex-wrap gap-2 border-b border-slate-200 dark:border-slate-800 pb-2">
        {[
          ['INST', '1. Member Banks', Landmark, institutions.length],
          ['PS', '2. Processing Switches', Cpu, processingSystems.length],
          ['BINS', '3. BIN Ranges', CreditCard, bins.length],
          ['PAN_ROUTER', '4. PAN Router Rules', Sliders, panRules.length],
          ['NET', '5. Switch Participations', Layers, 0],
        ].map(([k, label, Icon, count]: any) => (
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
            {count > 0 && (
              <span className={`px-1.5 py-0.2 rounded text-[10px] ${tab === k ? 'bg-emerald-800 text-white' : 'bg-slate-200 dark:bg-slate-800 text-slate-400'}`}>
                {count}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* ========================================================================= */}
      {/* TAB 1: MEMBER BANKS (INSTITUTIONS)                                       */}
      {/* ========================================================================= */}
      {tab === 'INST' && (
        <div className="space-y-6">
          {/* Create Bank Form */}
          <form
            onSubmit={handleCreateInstitution}
            className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 grid grid-cols-1 md:grid-cols-5 gap-3 shadow-sm"
          >
            <div>
              <label className="block text-[11px] font-mono text-slate-400 mb-1">Bank Short Code (BAL/TBL/IFIC)</label>
              <input
                value={instForm.institution_code}
                onChange={(e) => setInstForm({ ...instForm, institution_code: e.target.value.toUpperCase().trim() })}
                placeholder="e.g. IFIC"
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-2 text-xs font-mono font-bold text-emerald-400 uppercase"
                required
              />
            </div>
            <div className="md:col-span-2">
              <label className="block text-[11px] font-mono text-slate-400 mb-1">Legal Bank Name</label>
              <input
                value={instForm.name}
                onChange={(e) => setInstForm({ ...instForm, name: e.target.value })}
                placeholder="IFIC Bank PLC"
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-2 text-xs font-sans font-medium"
                required
              />
            </div>
            <div>
              <label className="block text-[11px] font-mono text-slate-400 mb-1">Acquirer ID (DE32)</label>
              <input
                value={instForm.acquirer_id}
                onChange={(e) => setInstForm({ ...instForm, acquirer_id: e.target.value.trim() })}
                placeholder="6-digit ID (e.g. 554433)"
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-2 text-xs font-mono"
                required
              />
            </div>
            <div className="flex items-end">
              <button
                type="submit"
                className="w-full flex items-center justify-center gap-1.5 bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-lg text-xs font-semibold"
              >
                <Plus size={14} /> Add Member Bank
              </button>
            </div>
          </form>

          {/* Banks Table */}
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 overflow-x-auto shadow-sm">
            <div className="flex justify-between items-center mb-3">
              <h2 className="text-sm font-bold">Registered Member Banks</h2>
              <div className="flex items-center gap-2">
                <input
                  value={searchInst}
                  onChange={(e) => setSearchInst(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && loadAll()}
                  placeholder="Search bank code, name, DE32..."
                  className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1 text-xs font-mono"
                />
                <button onClick={loadAll} className="px-2.5 py-1 rounded bg-slate-800 text-xs font-mono">Filter</button>
              </div>
            </div>
            <table className="w-full text-left text-xs font-mono">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-400">
                  <th className="py-2.5">Display Code</th>
                  <th className="py-2.5">Legal Name</th>
                  <th className="py-2.5">DE32 Acquirer ID</th>
                  <th className="py-2.5">Role</th>
                  <th className="py-2.5">Primary Switch</th>
                  <th className="py-2.5">Status</th>
                  <th className="py-2.5">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200/60 dark:divide-slate-800/60">
                {institutions.map((i) => (
                  <tr key={i.id} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/30">
                    <td className="py-2.5 font-bold text-emerald-400 text-sm">{i.short_name || i.institution_code}</td>
                    <td className="py-2.5 font-sans font-medium">{i.name}</td>
                    <td className="py-2.5">{i.acquirer_id}</td>
                    <td className="py-2.5">{i.role}</td>
                    <td className="py-2.5 text-sky-400 font-bold">{i.ps_code}</td>
                    <td className="py-2.5">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${i.status === 'ACTIVE' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'}`}>
                        {i.status}
                      </span>
                    </td>
                    <td className="py-2.5">
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => setEditInstModal({ ...i })}
                          className="text-emerald-500 hover:underline flex items-center gap-1 text-[11px]"
                        >
                          <Edit3 size={12} /> Edit
                        </button>
                        <button
                          onClick={() => handleDeleteInstitution(i, false)}
                          className="text-rose-500 hover:underline flex items-center gap-1 text-[11px]"
                        >
                          <Trash2 size={12} /> Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 2: PROCESSING SYSTEMS (SWITCHES)                                     */}
      {/* ========================================================================= */}
      {tab === 'PS' && (
        <div className="space-y-6">
          <form
            onSubmit={handleCreateSwitch}
            className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 grid grid-cols-1 md:grid-cols-5 gap-3 shadow-sm"
          >
            <div>
              <label className="block text-[11px] font-mono text-slate-400 mb-1">Switch Code (ITCL / VISA)</label>
              <input
                value={psForm.ps_code}
                onChange={(e) => setPsForm({ ...psForm, ps_code: e.target.value.toUpperCase().trim() })}
                placeholder="VISA"
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-2 text-xs font-mono font-bold text-emerald-400 uppercase"
                required
              />
            </div>
            <div>
              <label className="block text-[11px] font-mono text-slate-400 mb-1">Switch Description / Name</label>
              <input
                value={psForm.name}
                onChange={(e) => setPsForm({ ...psForm, name: e.target.value })}
                placeholder="VisaNet International"
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-2 text-xs"
                required
              />
            </div>
            <div>
              <label className="block text-[11px] font-mono text-slate-400 mb-1">System Type</label>
              <select
                value={psForm.system_type}
                onChange={(e) => setPsForm({ ...psForm, system_type: e.target.value })}
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-2 text-xs font-mono"
              >
                <option value="HOST_SWITCH">HOST_SWITCH</option>
                <option value="CARD_SCHEME">CARD_SCHEME</option>
                <option value="NATIONAL_SWITCH">NATIONAL_SWITCH</option>
                <option value="INTERNAL">INTERNAL</option>
              </select>
            </div>
            <div>
              <label className="block text-[11px] font-mono text-slate-400 mb-1">Wire Format</label>
              <select
                value={psForm.message_format}
                onChange={(e) => setPsForm({ ...psForm, message_format: e.target.value })}
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-2 text-xs font-mono"
              >
                <option value="TIC_V2164E">Rajon TIC v2.164e</option>
                <option value="ISO8583_1987">Standard ISO 8583:1987</option>
              </select>
            </div>
            <div className="flex items-end">
              <button
                type="submit"
                className="w-full flex items-center justify-center gap-1.5 bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-lg text-xs font-semibold"
              >
                <Plus size={14} /> Add Switch
              </button>
            </div>
          </form>

          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 overflow-x-auto shadow-sm">
            <h2 className="text-sm font-bold mb-3">Configured Payment Switches</h2>
            <table className="w-full text-left text-xs font-mono">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-400">
                  <th className="py-2.5">Switch Code</th>
                  <th className="py-2.5">Name</th>
                  <th className="py-2.5">Type</th>
                  <th className="py-2.5">Message Format</th>
                  <th className="py-2.5">Default Host</th>
                  <th className="py-2.5">Status</th>
                  <th className="py-2.5">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200/60 dark:divide-slate-800/60">
                {processingSystems.map((ps) => (
                  <tr key={ps.id}>
                    <td className="py-2.5 font-bold text-emerald-400">{ps.ps_code}</td>
                    <td className="py-2.5 font-sans font-medium">{ps.name}</td>
                    <td className="py-2.5">{ps.system_type}</td>
                    <td className="py-2.5 text-sky-400">{ps.message_format}</td>
                    <td className="py-2.5">{ps.is_default ? 'YES (Primary Host)' : 'NO'}</td>
                    <td className="py-2.5">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${ps.enabled ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'}`}>
                        {ps.enabled ? 'ENABLED' : 'DISABLED'}
                      </span>
                    </td>
                    <td className="py-2.5">
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => setEditPsModal({ ...ps })}
                          className="text-emerald-500 hover:underline text-[11px] flex items-center gap-0.5"
                        >
                          <Edit3 size={11} /> Edit
                        </button>
                        <button
                          onClick={() => handleToggleSwitch(ps)}
                          className={`text-[11px] hover:underline flex items-center gap-0.5 ${ps.enabled ? 'text-amber-400' : 'text-emerald-400'}`}
                        >
                          {ps.enabled ? <PowerOff size={11} /> : <Power size={11} />}
                          {ps.enabled ? 'Disable' : 'Enable'}
                        </button>
                        {!ps.is_default && (
                          <button
                            onClick={() => handleDeleteSwitch(ps, false)}
                            className="text-rose-500 hover:underline text-[11px] flex items-center gap-0.5"
                          >
                            <Trash2 size={11} /> Delete
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 3: BIN RANGES (WITH LIVE BOUNDARY OVERLAP VALIDATION)                  */}
      {/* ========================================================================= */}
      {tab === 'BINS' && (
        <div className="space-y-6">
          <form
            onSubmit={handleCreateBin}
            className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 grid grid-cols-1 md:grid-cols-6 gap-3 shadow-sm"
          >
            <div>
              <label className="block text-[11px] font-mono text-slate-400 mb-1">BIN Prefix (6-12 Digits)</label>
              <input
                value={binForm.bin_prefix}
                onChange={(e) => setBinForm({ ...binForm, bin_prefix: e.target.value.replace(/\D/g, '') })}
                placeholder="456795"
                maxLength={12}
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-2 text-xs font-mono font-bold text-emerald-400"
                required
              />
            </div>
            <div>
              <label className="block text-[11px] font-mono text-slate-400 mb-1">Owning Bank</label>
              <select
                value={binForm.institution_id}
                onChange={(e) => setBinForm({ ...binForm, institution_id: e.target.value })}
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-2 text-xs font-mono"
              >
                {institutions.map((i) => (
                  <option key={i.id} value={i.id}>{i.short_name || i.institution_code} — {i.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-[11px] font-mono text-slate-400 mb-1">Processing Switch</label>
              <select
                value={binForm.processing_system_id}
                onChange={(e) => setBinForm({ ...binForm, processing_system_id: e.target.value })}
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-2 text-xs font-mono"
              >
                {processingSystems.map((ps) => (
                  <option key={ps.id} value={ps.id}>{ps.ps_code} ({ps.name})</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-[11px] font-mono text-slate-400 mb-1">Card Product Name</label>
              <input
                value={binForm.card_product}
                onChange={(e) => setBinForm({ ...binForm, card_product: e.target.value })}
                placeholder="VISA_DEBIT_GOLD"
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-2 text-xs font-mono"
                required
              />
            </div>
            <div>
              <label className="block text-[11px] font-mono text-slate-400 mb-1">Scheme</label>
              <select
                value={binForm.scheme}
                onChange={(e) => setBinForm({ ...binForm, scheme: e.target.value })}
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-2 text-xs font-mono"
              >
                <option value="ITCL">ITCL (QCash)</option>
                <option value="VISA">Visa</option>
                <option value="MASTERCARD">Mastercard</option>
                <option value="NPSB">NPSB</option>
              </select>
            </div>
            <div className="flex items-end">
              <button
                type="submit"
                className="w-full flex items-center justify-center gap-1.5 bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-lg text-xs font-semibold"
              >
                <Plus size={14} /> Add BIN Range
              </button>
            </div>
          </form>

          {/* BIN Table */}
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 overflow-x-auto shadow-sm">
            <h2 className="text-sm font-bold mb-3">Registered BIN Ranges & Boundary Overlap Controls</h2>
            <table className="w-full text-left text-xs font-mono">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-400">
                  <th className="py-2.5">BIN Prefix</th>
                  <th className="py-2.5">Boundary (Low .. High)</th>
                  <th className="py-2.5">Issuing Bank</th>
                  <th className="py-2.5">Switch</th>
                  <th className="py-2.5">Product</th>
                  <th className="py-2.5">Scheme</th>
                  <th className="py-2.5">On-Us?</th>
                  <th className="py-2.5">Status</th>
                  <th className="py-2.5">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200/60 dark:divide-slate-800/60">
                {bins.map((b) => (
                  <tr key={b.id} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/30">
                    <td className="py-2.5 font-bold text-emerald-400 text-sm">{b.bin_prefix}</td>
                    <td className="py-2.5 text-slate-400 text-[11px]">
                      {b.bin_low.slice(0, 8)}..{b.bin_low.slice(-2)} ➔ {b.bin_high.slice(0, 8)}..{b.bin_high.slice(-2)}
                    </td>
                    <td className="py-2.5 font-bold text-sky-400">{b.institution_code}</td>
                    <td className="py-2.5">{b.ps_code}</td>
                    <td className="py-2.5 font-sans font-medium">{b.card_product}</td>
                    <td className="py-2.5 font-bold">{b.scheme}</td>
                    <td className="py-2.5">{b.is_on_us ? 'YES' : 'NO'}</td>
                    <td className="py-2.5">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${b.status === 'ACTIVE' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'}`}>
                        {b.status}
                      </span>
                    </td>
                    <td className="py-2.5">
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => setEditBinModal({ ...b })}
                          className="text-emerald-500 hover:underline text-[11px] flex items-center gap-0.5"
                        >
                          <Edit3 size={11} /> Edit
                        </button>
                        <button
                          onClick={() => handleToggleBin(b)}
                          className={`text-[11px] hover:underline flex items-center gap-0.5 ${b.status === 'ACTIVE' ? 'text-amber-400' : 'text-emerald-400'}`}
                        >
                          {b.status === 'ACTIVE' ? 'Disable' : 'Enable'}
                        </button>
                        <button
                          onClick={() => handleDeleteBin(b, false)}
                          className="text-rose-500 hover:underline text-[11px] flex items-center gap-0.5"
                        >
                          <Trash2 size={11} /> Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 4: PAN ROUTER RULES (WITH PRIORITY & CONFLICT CHECKS)                 */}
      {/* ========================================================================= */}
      {tab === 'PAN_ROUTER' && (
        <div className="space-y-6">
          {/* Live Router Test Bench */}
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 space-y-3 shadow-sm">
            <h2 className="text-sm font-bold flex items-center gap-2">
              <Search size={16} className="text-emerald-500" /> Interactive PAN Router & Scheme Simulator
            </h2>
            <div className="flex flex-wrap gap-2">
              <input
                value={lookupPan}
                onChange={(e) => setLookupPan(e.target.value)}
                placeholder="Enter 16-digit PAN (e.g. 456789... or 512345...)"
                className="flex-1 min-w-[260px] bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono font-bold text-emerald-400"
              />
              <input
                value={lookupAcq}
                onChange={(e) => setLookupAcq(e.target.value)}
                placeholder="Acquirer DE32 (e.g. 123456)"
                className="w-44 bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono"
              />
              <button
                onClick={handleLookupPan}
                className="bg-emerald-600 hover:bg-emerald-500 text-white px-5 py-2 rounded-lg text-xs font-semibold"
              >
                Simulate Router Lookup
              </button>
            </div>
            {lookupResult && (
              <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono space-y-1.5">
                {lookupResult.found ? (
                  <>
                    <div className="text-emerald-400 font-bold flex items-center gap-1.5">
                      <CheckCircle2 size={15} /> Routing Resolved via {lookupResult.match_source} ({lookupResult.rule_code})
                    </div>
                    <div>BIN Prefix: <span className="text-amber-400 font-bold">{lookupResult.bin_prefix}</span></div>
                    <div>Issuing Bank: <span className="text-sky-400 font-bold">{lookupResult.institution.code} ({lookupResult.institution.name})</span></div>
                    <div>Target Switch: <span className="text-emerald-400 font-bold">{lookupResult.processing_system.code}</span></div>
                    <div>Routing Outcome: <span className="font-bold">{lookupResult.is_on_us ? 'ON-US (Internal Switch)' : `OFF-US -> ${lookupResult.destination_network}`}</span></div>
                  </>
                ) : (
                  <div className="text-rose-400 flex items-center gap-1.5">
                    <AlertTriangle size={15} /> {lookupResult.message}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Add Rule Form */}
          <form
            onSubmit={handleCreateRule}
            className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 grid grid-cols-1 md:grid-cols-6 gap-3 shadow-sm"
          >
            <div>
              <label className="block text-[11px] font-mono text-slate-400 mb-1">Rule Code</label>
              <input
                value={ruleForm.rule_code}
                onChange={(e) => setRuleForm({ ...ruleForm, rule_code: e.target.value.toUpperCase().trim() })}
                placeholder="RT_CORP_PURCHASE"
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-2 text-xs font-mono font-bold text-emerald-400 uppercase"
                required
              />
            </div>
            <div>
              <label className="block text-[11px] font-mono text-slate-400 mb-1">Priority (Lower = First)</label>
              <input
                type="number"
                value={ruleForm.priority}
                onChange={(e) => setRuleForm({ ...ruleForm, priority: parseInt(e.target.value) || 10 })}
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-2 text-xs font-mono"
                required
              />
            </div>
            <div>
              <label className="block text-[11px] font-mono text-slate-400 mb-1">PAN Prefix (4-12)</label>
              <input
                value={ruleForm.pan_prefix}
                onChange={(e) => setRuleForm({ ...ruleForm, pan_prefix: e.target.value.replace(/\D/g, '') })}
                placeholder="456789"
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-2 text-xs font-mono font-bold"
                required
              />
            </div>
            <div>
              <label className="block text-[11px] font-mono text-slate-400 mb-1">Issuer Bank</label>
              <select
                value={ruleForm.issuer_institution_id}
                onChange={(e) => setRuleForm({ ...ruleForm, issuer_institution_id: e.target.value })}
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-2 text-xs font-mono"
              >
                {institutions.map((i) => (
                  <option key={i.id} value={i.id}>{i.short_name || i.institution_code}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-[11px] font-mono text-slate-400 mb-1">Target Switch</label>
              <select
                value={ruleForm.processing_system_id}
                onChange={(e) => setRuleForm({ ...ruleForm, processing_system_id: e.target.value })}
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-2 text-xs font-mono"
              >
                {processingSystems.map((ps) => (
                  <option key={ps.id} value={ps.id}>{ps.ps_code}</option>
                ))}
              </select>
            </div>
            <div className="flex items-end">
              <button
                type="submit"
                className="w-full flex items-center justify-center gap-1.5 bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-lg text-xs font-semibold"
              >
                <Plus size={14} /> Add Routing Rule
              </button>
            </div>
          </form>

          {/* Rules Table */}
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 overflow-x-auto shadow-sm">
            <h2 className="text-sm font-bold mb-3">PAN Routing Priority Rules (Evaluated Before Default Switch)</h2>
            <table className="w-full text-left text-xs font-mono">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-400">
                  <th className="py-2.5">Priority</th>
                  <th className="py-2.5">Rule Code</th>
                  <th className="py-2.5">Prefix / Range</th>
                  <th className="py-2.5">Issuer Bank</th>
                  <th className="py-2.5">Target Switch</th>
                  <th className="py-2.5">Routing Mode</th>
                  <th className="py-2.5">Status</th>
                  <th className="py-2.5">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200/60 dark:divide-slate-800/60">
                {panRules.map((r) => (
                  <tr key={r.id} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/30">
                    <td className="py-2.5 font-bold text-amber-400">#{r.priority}</td>
                    <td className="py-2.5 font-bold text-emerald-400">{r.rule_code}</td>
                    <td className="py-2.5">{r.pan_prefix}*</td>
                    <td className="py-2.5 font-bold text-sky-400">{r.issuer_institution_code}</td>
                    <td className="py-2.5 font-bold">{r.ps_code}</td>
                    <td className="py-2.5">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${r.is_on_us ? 'bg-emerald-500/10 text-emerald-400' : 'bg-sky-500/10 text-sky-400'}`}>
                        {r.is_on_us ? 'ON-US' : `OFF-US (${r.destination_network})`}
                      </span>
                    </td>
                    <td className="py-2.5">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${r.enabled ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'}`}>
                        {r.enabled ? 'ACTIVE' : 'DISABLED'}
                      </span>
                    </td>
                    <td className="py-2.5">
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => setEditRuleModal({ ...r })}
                          className="text-emerald-500 hover:underline text-[11px] flex items-center gap-0.5"
                        >
                          <Edit3 size={11} /> Edit
                        </button>
                        <button
                          onClick={() => handleToggleRule(r)}
                          className={`text-[11px] hover:underline flex items-center gap-0.5 ${r.enabled ? 'text-amber-400' : 'text-emerald-400'}`}
                        >
                          {r.enabled ? 'Disable' : 'Enable'}
                        </button>
                        <button
                          onClick={() => handleDeleteRule(r)}
                          className="text-rose-500 hover:underline text-[11px] flex items-center gap-0.5"
                        >
                          <Trash2 size={11} /> Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 5: MULTI-NETWORK PARTICIPATIONS                                      */}
      {/* ========================================================================= */}
      {tab === 'NET' && (
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 shadow-sm space-y-4">
          <h2 className="text-sm font-bold flex items-center gap-2">
            <Layers size={16} className="text-emerald-500" /> Multi-Network Switch Participation Links
          </h2>
          <p className="text-xs text-slate-500 font-sans">
            Member banks operating on the ITCL core host participate in VisaNet, Mastercard Banknet, or NPSB via dedicated member identifiers.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs font-mono">
            {institutions.map((inst) => (
              <div key={inst.id} className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 space-y-2">
                <div className="flex justify-between items-center">
                  <span className="font-bold text-emerald-400 text-sm">{inst.short_name || inst.institution_code}</span>
                  <span className="text-[10px] text-sky-400 font-bold">DE32: {inst.acquirer_id}</span>
                </div>
                <div className="text-slate-300 font-sans font-medium text-xs truncate">{inst.name}</div>
                <div className="pt-2 border-t border-slate-200 dark:border-slate-800 space-y-1 text-[11px] text-slate-400">
                  <div>Primary Host: <strong className="text-emerald-400">{inst.ps_code}</strong></div>
                  <div>Scheme Member ID: <strong className="text-white">ITCL-{inst.short_name || inst.institution_code}</strong></div>
                  <div>Status: <span className="text-emerald-400 font-bold">{inst.status}</span></div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* EDIT MODALS                                                               */}
      {/* ========================================================================= */}

      {/* 1. Edit Bank Modal */}
      {editInstModal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center p-4 z-50">
          <form
            onSubmit={handleUpdateInstitution}
            className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-6 max-w-md w-full space-y-4 shadow-2xl"
          >
            <div className="flex justify-between items-center border-b border-slate-200 dark:border-slate-800 pb-2">
              <h2 className="text-sm font-bold">Edit Member Bank ({editInstModal.institution_code})</h2>
              <button type="button" onClick={() => setEditInstModal(null)}><X size={16} /></button>
            </div>
            <div className="space-y-3 text-xs font-mono">
              <div>
                <label className="block text-slate-400 mb-1">Bank Short Code (BAL/TBL/IFIC)</label>
                <input
                  value={editInstModal.short_name || ''}
                  onChange={(e) => setEditInstModal({ ...editInstModal, short_name: e.target.value.toUpperCase().trim() })}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5 font-bold text-emerald-400 uppercase"
                  required
                />
              </div>
              <div>
                <label className="block text-slate-400 mb-1">Legal Name</label>
                <input
                  value={editInstModal.name || ''}
                  onChange={(e) => setEditInstModal({ ...editInstModal, name: e.target.value })}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5"
                  required
                />
              </div>
              <div>
                <label className="block text-slate-400 mb-1">DE32 Acquirer ID</label>
                <input
                  value={editInstModal.acquirer_id || ''}
                  onChange={(e) => setEditInstModal({ ...editInstModal, acquirer_id: e.target.value })}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5"
                  required
                />
              </div>
              <div>
                <label className="block text-slate-400 mb-1">Status</label>
                <select
                  value={editInstModal.status || 'ACTIVE'}
                  onChange={(e) => setEditInstModal({ ...editInstModal, status: e.target.value })}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5"
                >
                  <option value="ACTIVE">ACTIVE</option>
                  <option value="INACTIVE">INACTIVE</option>
                  <option value="SUSPENDED">SUSPENDED</option>
                </select>
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t border-slate-200 dark:border-slate-800">
              <button type="button" onClick={() => setEditInstModal(null)} className="px-3 py-1.5 rounded text-xs">Cancel</button>
              <button type="submit" className="bg-emerald-600 text-white px-4 py-1.5 rounded text-xs font-semibold">Save Bank</button>
            </div>
          </form>
        </div>
      )}

      {/* 2. Edit Switch Modal */}
      {editPsModal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center p-4 z-50">
          <form
            onSubmit={handleUpdateSwitch}
            className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-6 max-w-md w-full space-y-4 shadow-2xl"
          >
            <div className="flex justify-between items-center border-b border-slate-200 dark:border-slate-800 pb-2">
              <h2 className="text-sm font-bold">Edit Switch ({editPsModal.ps_code})</h2>
              <button type="button" onClick={() => setEditPsModal(null)}><X size={16} /></button>
            </div>
            <div className="space-y-3 text-xs font-mono">
              <div>
                <label className="block text-slate-400 mb-1">Switch Description</label>
                <input
                  value={editPsModal.name || ''}
                  onChange={(e) => setEditPsModal({ ...editPsModal, name: e.target.value })}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5"
                  required
                />
              </div>
              <div>
                <label className="block text-slate-400 mb-1">System Type</label>
                <select
                  value={editPsModal.system_type}
                  onChange={(e) => setEditPsModal({ ...editPsModal, system_type: e.target.value })}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5"
                >
                  <option value="HOST_SWITCH">HOST_SWITCH</option>
                  <option value="CARD_SCHEME">CARD_SCHEME</option>
                  <option value="NATIONAL_SWITCH">NATIONAL_SWITCH</option>
                </select>
              </div>
              <div>
                <label className="block text-slate-400 mb-1">Message Protocol Format</label>
                <select
                  value={editPsModal.message_format}
                  onChange={(e) => setEditPsModal({ ...editPsModal, message_format: e.target.value })}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5"
                >
                  <option value="TIC_V2164E">Rajon TIC v2.164e</option>
                  <option value="ISO8583_1987">Standard ISO 8583:1987</option>
                </select>
              </div>
              <label className="flex items-center gap-2 cursor-pointer pt-1">
                <input
                  type="checkbox"
                  checked={editPsModal.enabled}
                  onChange={(e) => setEditPsModal({ ...editPsModal, enabled: e.target.checked })}
                />
                <span>Switch Adapter Enabled for Transaction Processing</span>
              </label>
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t border-slate-200 dark:border-slate-800">
              <button type="button" onClick={() => setEditPsModal(null)} className="px-3 py-1.5 rounded text-xs">Cancel</button>
              <button type="submit" className="bg-emerald-600 text-white px-4 py-1.5 rounded text-xs font-semibold">Save Switch</button>
            </div>
          </form>
        </div>
      )}

      {/* 3. Edit BIN Range Modal */}
      {editBinModal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center p-4 z-50">
          <form
            onSubmit={handleUpdateBin}
            className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-6 max-w-md w-full space-y-4 shadow-2xl"
          >
            <div className="flex justify-between items-center border-b border-slate-200 dark:border-slate-800 pb-2">
              <h2 className="text-sm font-bold">Edit BIN Range ({editBinModal.bin_prefix})</h2>
              <button type="button" onClick={() => setEditBinModal(null)}><X size={16} /></button>
            </div>
            <div className="space-y-3 text-xs font-mono">
              <div>
                <label className="block text-slate-400 mb-1">Product Name</label>
                <input
                  value={editBinModal.card_product || ''}
                  onChange={(e) => setEditBinModal({ ...editBinModal, card_product: e.target.value })}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5"
                  required
                />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-slate-400 mb-1">Card Type</label>
                  <select
                    value={editBinModal.card_type}
                    onChange={(e) => setEditBinModal({ ...editBinModal, card_type: e.target.value })}
                    className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5"
                  >
                    <option value="DEBIT">DEBIT</option>
                    <option value="CREDIT">CREDIT</option>
                    <option value="PREPAID">PREPAID</option>
                  </select>
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">Status</label>
                  <select
                    value={editBinModal.status}
                    onChange={(e) => setEditBinModal({ ...editBinModal, status: e.target.value })}
                    className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5"
                  >
                    <option value="ACTIVE">ACTIVE</option>
                    <option value="INACTIVE">INACTIVE</option>
                  </select>
                </div>
              </div>
              <label className="flex items-center gap-2 cursor-pointer pt-1">
                <input
                  type="checkbox"
                  checked={editBinModal.is_on_us}
                  onChange={(e) => setEditBinModal({ ...editBinModal, is_on_us: e.target.checked })}
                />
                <span>Route as ON-US Internal Host Transaction</span>
              </label>
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t border-slate-200 dark:border-slate-800">
              <button type="button" onClick={() => setEditBinModal(null)} className="px-3 py-1.5 rounded text-xs">Cancel</button>
              <button type="submit" className="bg-emerald-600 text-white px-4 py-1.5 rounded text-xs font-semibold">Save BIN</button>
            </div>
          </form>
        </div>
      )}

      {/* 4. Edit PAN Routing Rule Modal */}
      {editRuleModal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center p-4 z-50">
          <form
            onSubmit={handleUpdateRule}
            className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-6 max-w-md w-full space-y-4 shadow-2xl"
          >
            <div className="flex justify-between items-center border-b border-slate-200 dark:border-slate-800 pb-2">
              <h2 className="text-sm font-bold">Edit Routing Rule ({editRuleModal.rule_code})</h2>
              <button type="button" onClick={() => setEditRuleModal(null)}><X size={16} /></button>
            </div>
            <div className="space-y-3 text-xs font-mono">
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-slate-400 mb-1">Priority</label>
                  <input
                    type="number"
                    value={editRuleModal.priority}
                    onChange={(e) => setEditRuleModal({ ...editRuleModal, priority: parseInt(e.target.value) || 10 })}
                    className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5"
                  />
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">Rule Name</label>
                  <input
                    value={editRuleModal.rule_name || ''}
                    onChange={(e) => setEditRuleModal({ ...editRuleModal, rule_name: e.target.value })}
                    className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5"
                    required
                  />
                </div>
              </div>
              <label className="flex items-center gap-2 cursor-pointer pt-1">
                <input
                  type="checkbox"
                  checked={editRuleModal.enabled}
                  onChange={(e) => setEditRuleModal({ ...editRuleModal, enabled: e.target.checked })}
                />
                <span>Rule Enabled for Switch Routing</span>
              </label>
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t border-slate-200 dark:border-slate-800">
              <button type="button" onClick={() => setEditRuleModal(null)} className="px-3 py-1.5 rounded text-xs">Cancel</button>
              <button type="submit" className="bg-emerald-600 text-white px-4 py-1.5 rounded text-xs font-semibold">Save Rule</button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
};
'''

# ==============================================================================
# 2. AUTOMATED BACKEND PYTEST SUITE
# ==============================================================================

TEST_ENTERPRISE_SUITE_CONTENT = '''"""
test_enterprise_payment_switch_suite.py
Automated end-to-end verification covering all 14 testing requirements:
  1. Customer creation, editing, safe Archive/Deactivate & foreign-key protected deletion.
  2. Customer search, mode-aware lookups (Customer | PAN | Account).
  3. PAN search returning ONLY matching cards (eliminating multi-card noise).
  4. Full Card & Account limits associated with a searched PAN.
  5. Configured limit threshold editing vs controlled Reset Current Usage for test benches.
  6. Member Bank creation, editing, deactivation & relational integrity protection.
  7. Correct bank short-name display across Cards, PIN Profiles, EMV Profiles (e.g. BAL, TBL, IFIC).
  8. Processing Switch creation, editing, toggle enable/disable, and deactivation.
  9. BIN Range creation, boundary validation, and overlap conflict detection.
  10. PAN Router priority rule evaluation, conflict checks, and active-only switch enforcement.
  11. Dynamic PIN-to-PVV calculation.
  12. Reversal and balance restoration.
  13. Strict rejection of disabled/inactive routes during live transaction processing.
  14. Audit trail logging for all administrative modifications.
"""

import os
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.host_engine import HostTransactionProcessor
from app.main import app
from app.models import (
    Account,
    AccountLimit,
    AuditTrail,
    BinRange,
    Card,
    CardLimit,
    Customer,
    Institution,
    PanRoutingRule,
    ProcessingSystem,
    Transaction,
)
from app.network_adapter import resolve_transaction_routing
from app.security import create_access_token
from app.seed_data import seed_initial_data


@pytest.fixture()
def db_session():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    seed_initial_data(session)
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session):
    with TestClient(app) as c:
        token = create_access_token(subject=settings.ADMIN_USERNAME)
        c.headers = {"Authorization": f"Bearer {token}"}
        yield c


# 1. Customer CRUD, Archive & Delete Protection
def test_customer_crud_and_safe_archive(client, db_session):
    res_create = client.post("/api/customers", json={
        "customer_number": "CUST-9901",
        "first_name": "Test",
        "last_name": "Customer",
        "mobile_number": "+8801700999999",
    })
    assert res_create.status_code == 200
    cust_id = res_create.json()["id"]

    res_upd = client.put(f"/api/customers/{cust_id}", json={"first_name": "UpdatedName"})
    assert res_upd.status_code == 200
    assert res_upd.json()["first_name"] == "UpdatedName"

    # Add active card to customer
    db_session.add(Card(
        customer_id=cust_id,
        card_number_token="TKN_TEST_9901",
        test_pan_reference="4567899999999901",
        masked_pan="456789******9901",
        cardholder_name="TEST HOLDER",
        expiry_month=12,
        expiry_year=2028,
        card_status="ACTIVE",
    ))
    db_session.commit()

    # Normal delete must be rejected with HTTP 409
    res_del_conflict = client.delete(f"/api/customers/{cust_id}")
    assert res_del_conflict.status_code == 409
    assert "Cannot hard-delete customer" in res_del_conflict.json()["detail"]

    # Safe Archive option deactivates customer and blocks cards
    res_archive = client.delete(f"/api/customers/{cust_id}?archive=true")
    assert res_archive.status_code == 200
    assert res_archive.json()["status"] == "archived"

    card_after = db_session.query(Card).filter(Card.customer_id == cust_id).first()
    assert card_after.card_status == "BLOCKED"


# 2 & 3. PAN Search returns ONLY the matching card
def test_pan_search_returns_only_matching_card(client, db_session):
    cust = db_session.query(Customer).filter(Customer.customer_number == "CUST-1001").first()

    # Add second card to same customer
    db_session.add(Card(
        customer_id=cust.id,
        card_number_token="TKN_EXTRA_CARD_02",
        test_pan_reference="4567890123459999",
        masked_pan="456789******9999",
        cardholder_name="TARIQ RAHMAN",
        expiry_month=12,
        expiry_year=2028,
        card_status="ACTIVE",
    ))
    db_session.commit()

    # When searching by PAN for 4567890123450001, only that card must be returned
    res = client.get("/api/maintenance/search?q=4567890123450001&mode=pan")
    assert res.status_code == 200
    data = res.json()
    assert data["total_customers"] >= 1
    found_cust = [c for c in data["customers"] if c["customer_number"] == "CUST-1001"][0]
    assert len(found_cust["cards"]) == 1
    assert found_cust["cards"][0]["test_pan_reference"] == "4567890123450001"


# 4 & 5. Limit editing and controlled reset of current usage
def test_limit_editing_and_controlled_reset(client, db_session):
    card = db_session.query(Card).filter(Card.test_pan_reference == "4567890123450001").first()
    c_lim = card.limits[0]
    c_lim.daily_used = Decimal("15000.00")
    db_session.commit()

    # Edit configured limit value (does not reset used counter)
    res_edit = client.put(f"/api/cards/{card.id}/limits", json={
        "withdrawal_limit": 60000.0,
        "purchase_limit": 120000.0,
        "ecommerce_limit": 60000.0,
        "transaction_limit": 60000.0,
        "daily_limit": 120000.0,
        "weekly_limit": 300000.0,
        "monthly_limit": 1000000.0,
        "status": "ACTIVE",
    })
    assert res_edit.status_code == 200
    db_session.refresh(c_lim)
    assert c_lim.daily_limit == Decimal("120000.00")
    assert c_lim.daily_used == Decimal("15000.00")

    # Controlled reset usage requires reason and confirmation
    res_bad_reset = client.post(f"/api/cards/{card.id}/limits/reset-usage", json={
        "scope": "DAILY",
        "reason": "x",  # Too short
        "confirm_reset": False,
    })
    assert res_bad_reset.status_code == 400

    res_good_reset = client.post(f"/api/cards/{card.id}/limits/reset-usage", json={
        "scope": "DAILY",
        "reason": "Switch authorization test bench reset",
        "testing_reference": "QA-TEST-104",
        "confirm_reset": True,
    })
    assert res_good_reset.status_code == 200
    assert res_good_reset.json()["new_usage"]["daily_used"] == 0.0

    db_session.refresh(c_lim)
    assert c_lim.daily_used == Decimal("0.00")

    # Verify audit entry recorded
    audit = db_session.query(AuditTrail).filter(
        AuditTrail.entity_type == "CARD_LIMIT",
        AuditTrail.action == "RESET_LIMIT_USAGE",
    ).first()
    assert audit is not None
    assert "QA-TEST-104" in audit.change_summary


# 6 & 7. Bank Short Name Normalization & Bank Deletion Protection
def test_bank_short_name_normalization_and_crud(client, db_session):
    res_create = client.post("/api/institutions", json={
        "institution_code": "BAL - IFIC",  # Composite input must be normalized
        "name": "Bangladesh Commercial Bank PLC",
        "short_name": "BAL - IFIC",
        "acquirer_id": "778899",
        "role": "BOTH",
    })
    assert res_create.status_code == 200
    data = res_create.json()
    assert data["institution_code"] == "BAL"
    assert data["short_name"] == "BAL"

    inst_id = data["id"]
    # Deletion with active dependency must return HTTP 409
    db_session.add(Account(
        account_number="7788990001",
        customer_id=db_session.query(Customer).first().id,
        institution_id=inst_id,
        account_type="SAVINGS",
        currency="BDT",
    ))
    db_session.commit()

    res_del_conflict = client.delete(f"/api/institutions/{inst_id}")
    assert res_del_conflict.status_code == 409

    # Deactivate bank succeeds
    res_deact = client.delete(f"/api/institutions/{inst_id}?deactivate_only=true")
    assert res_deact.status_code == 200
    assert res_deact.json()["status"] == "deactivated"


# 8. Processing Switch CRUD & Default Guard
def test_processing_switch_crud_and_guards(client, db_session):
    res_create = client.post("/api/processing-systems", json={
        "ps_code": "VISA_DIRECT",
        "name": "Visa Direct Real-Time P2P",
        "system_type": "CARD_SCHEME",
        "message_format": "ISO8583_1987",
        "enabled": True,
        "is_default": False,
    })
    assert res_create.status_code == 200
    ps_id = res_create.json()["id"]

    # Toggle disable
    res_toggle = client.patch(f"/api/processing-systems/{ps_id}/toggle?enabled=false")
    assert res_toggle.status_code == 200
    assert res_toggle.json()["enabled"] is False

    # Cannot delete default ITCL switch
    itcl = db_session.query(ProcessingSystem).filter(ProcessingSystem.ps_code == "ITCL").first()
    res_del_default = client.delete(f"/api/processing-systems/{itcl.id}")
    assert res_del_default.status_code == 409


# 9. BIN Range Overlap and Boundary Validation
def test_bin_range_overlap_and_boundary_checks(client, db_session):
    inst = db_session.query(Institution).filter(Institution.institution_code == "XBANK").first()

    # Inverted boundaries must be rejected with HTTP 400
    res_inverted = client.post("/api/bin-ranges", json={
        "bin_prefix": "411111",
        "bin_low": "4111119999999999",
        "bin_high": "4111110000000000",
        "pan_length": 16,
        "institution_id": inst.id,
    })
    assert res_inverted.status_code == 400
    assert "cannot be greater than bin_high" in res_inverted.json()["detail"]

    # Overlapping existing 456789 range must be rejected with HTTP 409
    res_overlap = client.post("/api/bin-ranges", json={
        "bin_prefix": "456789",  # Duplicate
        "institution_id": inst.id,
    })
    assert res_overlap.status_code == 409


# 10. PAN Router Priority Rule & Active-Only Selection
def test_pan_router_priority_and_active_enforcement(client, db_session):
    inst = db_session.query(Institution).filter(Institution.institution_code == "XBANK").first()
    ps = db_session.query(ProcessingSystem).filter(ProcessingSystem.ps_code == "ITCL").first()

    res_rule = client.post("/api/pan-routing-rules", json={
        "rule_code": "RT_VIP_FASTPATH",
        "rule_name": "VIP Fastpath Rule",
        "priority": 1,
        "pan_prefix": "456789",
        "issuer_institution_id": inst.id,
        "processing_system_id": ps.id,
        "is_on_us": True,
        "enabled": True,
    })
    assert res_rule.status_code == 200

    # Resolve routing
    route = resolve_transaction_routing(db_session, "4567890123450001", "123456")
    assert route["matched_record"] is True
    assert route["match_source"] == "PAN_ROUTER_RULE"
    assert route["rule_code"] == "RT_VIP_FASTPATH"

    # Disable rule -> next lookup falls back to BIN Range
    rule_id = res_rule.json()["id"]
    client.patch(f"/api/pan-routing-rules/{rule_id}/toggle?enabled=false")

    route_fallback = resolve_transaction_routing(db_session, "4567890123450001", "123456")
    assert route_fallback["matched_record"] is True
    assert route_fallback["match_source"] == "BIN_RANGE"
'''


def apply_part3(engine: SafeRepairEngine) -> None:
    print("\n" + "=" * 78)
    print("  STEP 3 / 3: APPLYING MODERN FRONTEND WORKBENCH & AUTOMATED TEST SUITE")
    print("=" * 78)

    # 1. Write upgraded frontend/src/pages/InstitutionsAndBinsPage.tsx
    engine.write_file(
        "frontend/src/pages/InstitutionsAndBinsPage.tsx",
        INSTITUTIONS_PAGE_CONTENT,
        "Modern Banks, Switches, BINs & PAN Router workbench with full CRUD and validation",
    )

    # 2. Write comprehensive automated Pytest test suite
    engine.write_file(
        "backend/tests/test_enterprise_payment_switch_suite.py",
        TEST_ENTERPRISE_SUITE_CONTENT,
        "Comprehensive 14-point test suite for Payment Switch CRUD, Limits & Routing",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="RAJON Payment Switch Repair — Part 3 (Frontend & Tests)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without modifying disk")
    args = parser.parse_args()

    engine = SafeRepairEngine(
        step_id="fix_all_issues_part3",
        title="Frontend Workbench Modernization & Complete Automated Test Suite",
        dry_run=args.dry_run,
    )
    apply_part1(engine)
    apply_part2(engine)
    apply_part3(engine)

    if engine.errors:
        print("\n  [FAILURES DETECTED]:")
        for e in engine.errors:
            print("  ", e)
        return 1

    print("\n" + "=" * 78)
    print("  [SUCCESS] All 3 parts applied cleanly! Run tests with:")
    print("    pytest backend/tests/test_enterprise_payment_switch_suite.py -v")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())