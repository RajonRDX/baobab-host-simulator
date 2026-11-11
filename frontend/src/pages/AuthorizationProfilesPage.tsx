import React, { useEffect, useState } from 'react';
import { api } from '../services/api';

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
