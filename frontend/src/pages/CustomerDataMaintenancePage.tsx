import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Search,
  User,
  CreditCard,
  Landmark,
  Trash2,
  Link as LinkIcon,
  Unlink,
  RefreshCw,
  Edit3,
  KeyRound,
  Plus,
  CheckCircle2,
  ShieldAlert,
  ArrowRightLeft,
  Loader2,
  X,
  ChevronRight,
} from 'lucide-react';
import { apiFetch } from '../api';

type SearchMode = 'all' | 'customer' | 'pan' | 'account';

const MODE_TABS: { id: SearchMode; label: string; icon: React.ReactNode; hint: string }[] = [
  { id: 'all', label: 'All', icon: <Search size={14} />, hint: 'CIF, name, PAN or account' },
  { id: 'customer', label: 'Customer', icon: <User size={14} />, hint: 'Customer number / name / mobile' },
  { id: 'pan', label: 'PAN / Card', icon: <CreditCard size={14} />, hint: 'Full or partial PAN' },
  { id: 'account', label: 'Account', icon: <Landmark size={14} />, hint: 'Account number' },
];

export const CustomerDataMaintenancePage: React.FC = () => {
  const [mode, setMode] = useState<SearchMode>('all');
  const [searchTerm, setSearchTerm] = useState('');
  const [loading, setLoading] = useState(false);
  const [customers, setCustomers] = useState<any[]>([]);
  const [allAccounts, setAllAccounts] = useState<any[]>([]);
  const [allCustomers, setAllCustomers] = useState<any[]>([]);
  const [selectedCustId, setSelectedCustId] = useState<string>('');
  const [msg, setMsg] = useState('');
  const [error, setError] = useState('');
  const [stats, setStats] = useState({ total_customers: 0, total_cards: 0, total_accounts: 0 });

  // Modals
  const [editAccountModal, setEditAccountModal] = useState<any | null>(null);
  const [pinModalCard, setPinModalCard] = useState<any | null>(null);
  const [newPin, setNewPin] = useState('1234');
  const [linkModalCard, setLinkModalCard] = useState<any | null>(null);
  const [targetAccountId, setTargetAccountId] = useState('');
  const [linkRole, setLinkRole] = useState('SECONDARY');
  const [reassignModalCard, setReassignModalCard] = useState<any | null>(null);
  const [reassignCustId, setReassignCustId] = useState('');

  const loadWorkspace = useCallback(
    async (query: string = searchTerm, activeMode: SearchMode = mode) => {
      setLoading(true);
      setError('');
      try {
        const params = new URLSearchParams();
        if (query.trim()) params.set('q', query.trim());
        params.set('mode', activeMode);
        const res = await apiFetch(`/maintenance/search?${params.toString()}`);
        const custList = res.customers || [];
        setCustomers(custList);
        setAllAccounts(res.all_accounts || []);
        setAllCustomers(res.all_customers || []);
        setStats({
          total_customers: res.total_customers ?? custList.length,
          total_cards: res.total_cards ?? 0,
          total_accounts: res.total_accounts ?? 0,
        });
        if (custList.length > 0) {
          const still = custList.find((c: any) => c.id === selectedCustId);
          setSelectedCustId(still ? still.id : custList[0].id);
        } else {
          setSelectedCustId('');
        }
      } catch (err: any) {
        setError(err.message || 'Search failed');
        setCustomers([]);
      } finally {
        setLoading(false);
      }
    },
    [searchTerm, mode, selectedCustId]
  );

  useEffect(() => {
    loadWorkspace('', 'all');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectedCust = useMemo(
    () => customers.find((c) => c.id === selectedCustId) || null,
    [customers, selectedCustId]
  );

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    loadWorkspace(searchTerm, mode);
  };

  const switchMode = (m: SearchMode) => {
    setMode(m);
    loadWorkspace(searchTerm, m);
  };

  const flash = (text: string, isError = false) => {
    if (isError) {
      setError(text);
      setMsg('');
    } else {
      setMsg(text);
      setError('');
    }
  };

  // ---------- Account balance edit ----------
  const handleSaveAccountEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editAccountModal) return;
    try {
      await apiFetch(`/accounts/${editAccountModal.id}`, {
        method: 'PUT',
        body: JSON.stringify({
          account_type: editAccountModal.account_type,
          available_balance: Number(editAccountModal.available_balance),
          ledger_balance: Number(editAccountModal.ledger_balance),
          overdraft_limit: Number(editAccountModal.overdraft_limit || 0),
          account_status: editAccountModal.account_status,
        }),
      });
      flash(
        `Account ${editAccountModal.account_number} updated — Available ${Number(
          editAccountModal.available_balance
        ).toLocaleString()} ${editAccountModal.currency}`
      );
      setEditAccountModal(null);
      await loadWorkspace(searchTerm, mode);
    } catch (err: any) {
      flash(err.message || 'Update failed', true);
    }
  };

  // ---------- Delete account ----------
  const handleDeleteAccount = async (acct: any) => {
    if (!confirm(`Delete account ${acct.account_number}? Cards will be detached.`)) return;
    try {
      await apiFetch(`/accounts/${acct.id}?force=true`, { method: 'DELETE' });
      flash(`Account ${acct.account_number} deleted`);
      await loadWorkspace(searchTerm, mode);
    } catch (err: any) {
      flash(err.message, true);
    }
  };

  // ---------- Link / Unlink / Promote ----------
  const handleLinkAccount = async () => {
    if (!linkModalCard || !targetAccountId) return;
    try {
      await apiFetch(`/cards/${linkModalCard.id}/accounts`, {
        method: 'POST',
        body: JSON.stringify({
          account_id: targetAccountId,
          account_role: linkRole,
          priority: (linkModalCard.card_accounts?.length || 0) + 1,
        }),
      });
      flash(`Linked account to ${linkModalCard.masked_pan} as ${linkRole}`);
      setLinkModalCard(null);
      await loadWorkspace(searchTerm, mode);
    } catch (err: any) {
      flash(err.message, true);
    }
  };

  const handleUnlink = async (linkId: string, acctNum: string, maskedPan: string) => {
    if (!confirm(`Unlink ${acctNum} from ${maskedPan}?`)) return;
    try {
      await apiFetch(`/cards/accounts/${linkId}`, { method: 'DELETE' });
      flash(`Unlinked ${acctNum}`);
      await loadWorkspace(searchTerm, mode);
    } catch (err: any) {
      flash(err.message, true);
    }
  };

  const handleSetPrimary = async (linkId: string, acctNum: string) => {
    try {
      await apiFetch(`/cards/accounts/${linkId}`, {
        method: 'PUT',
        body: JSON.stringify({ account_role: 'PRIMARY', priority: 1 }),
      });
      flash(`${acctNum} is now PRIMARY`);
      await loadWorkspace(searchTerm, mode);
    } catch (err: any) {
      flash(err.message, true);
    }
  };

  // ---------- PIN change ----------
  const handleChangePin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!pinModalCard) return;
    try {
      const res = await apiFetch(`/cards/${pinModalCard.id}/pin`, {
        method: 'POST',
        body: JSON.stringify({ new_pin: newPin }),
      });
      flash(`PIN updated for ${pinModalCard.masked_pan} — new PVV/Offset: ${res.new_pvv || 'OK'}`);
      setPinModalCard(null);
      setNewPin('1234');
      await loadWorkspace(searchTerm, mode);
    } catch (err: any) {
      flash(err.message, true);
    }
  };

  // ---------- Reassign card to another customer ----------
  const handleReassignCustomer = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!reassignModalCard || !reassignCustId) return;
    try {
      const res = await apiFetch(`/cards/${reassignModalCard.id}/reassign-customer`, {
        method: 'PUT',
        body: JSON.stringify({ customer_id: reassignCustId }),
      });
      flash(
        `Card ${reassignModalCard.masked_pan} moved to customer ${res.new_customer_number}`
      );
      setReassignModalCard(null);
      setReassignCustId('');
      await loadWorkspace(searchTerm, mode);
    } catch (err: any) {
      flash(err.message, true);
    }
  };

  // ---------- Delete card ----------
  const handleDeleteCard = async (card: any) => {
    if (!confirm(`Delete card ${card.masked_pan}?`)) return;
    try {
      await apiFetch(`/cards/${card.id}?force=true`, { method: 'DELETE' });
      flash(`Card ${card.masked_pan} deleted`);
      await loadWorkspace(searchTerm, mode);
    } catch (err: any) {
      flash(err.message, true);
    }
  };

  // ---------- Update customer basics ----------
  const handleUpdateCustomer = async (fields: Record<string, any>) => {
    if (!selectedCust) return;
    try {
      await apiFetch(`/customers/${selectedCust.id}`, {
        method: 'PUT',
        body: JSON.stringify(fields),
      });
      flash('Customer updated');
      await loadWorkspace(searchTerm, mode);
    } catch (err: any) {
      flash(err.message, true);
    }
  };

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight flex items-center gap-2">
            <ShieldAlert className="text-emerald-500" size={22} />
            Customer Data Maintenance 360
          </h1>
          <p className="text-xs text-slate-500 mt-1 max-w-2xl">
            Search by Customer, PAN or Account. Inspect relationships, edit balances, re-link
            accounts, change PIN, reassign cards, and delete entities — all in one modern workspace.
          </p>
        </div>
        <div className="flex items-center gap-2 text-[11px] font-mono">
          <span className="px-2.5 py-1 rounded-full bg-sky-500/10 text-sky-400 border border-sky-500/20">
            {stats.total_customers} customers
          </span>
          <span className="px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            {stats.total_cards} cards
          </span>
          <span className="px-2.5 py-1 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20">
            {stats.total_accounts} accounts
          </span>
        </div>
      </div>

      {/* Alerts */}
      {msg && (
        <div className="flex items-center gap-2 p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs font-mono">
          <CheckCircle2 size={16} /> {msg}
          <button onClick={() => setMsg('')} className="ml-auto opacity-60 hover:opacity-100">
            <X size={14} />
          </button>
        </div>
      )}
      {error && (
        <div className="flex items-center gap-2 p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs font-mono">
          <ShieldAlert size={16} /> {error}
          <button onClick={() => setError('')} className="ml-auto opacity-60 hover:opacity-100">
            <X size={14} />
          </button>
        </div>
      )}

      {/* Search mode tabs + bar */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-4 shadow-sm space-y-3">
        <div className="flex flex-wrap gap-1.5">
          {MODE_TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => switchMode(t.id)}
              className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                mode === t.id
                  ? 'bg-emerald-600 text-white shadow-md shadow-emerald-600/25'
                  : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700'
              }`}
            >
              {t.icon}
              {t.label}
            </button>
          ))}
        </div>

        <form onSubmit={handleSearchSubmit} className="flex flex-wrap gap-2">
          <div className="relative flex-1 min-w-[240px]">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder={MODE_TABS.find((t) => t.id === mode)?.hint || 'Search…'}
              className="w-full pl-9 pr-3 py-2.5 rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 text-sm font-mono focus:ring-2 focus:ring-emerald-500/40 focus:border-emerald-500 outline-none"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="flex items-center gap-1.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white px-5 py-2.5 rounded-xl text-xs font-semibold shadow-md shadow-emerald-600/20"
          >
            {loading ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />}
            Search
          </button>
          <button
            type="button"
            onClick={() => {
              setSearchTerm('');
              loadWorkspace('', mode);
            }}
            className="flex items-center gap-1.5 px-3 py-2.5 rounded-xl border border-slate-300 dark:border-slate-700 text-xs font-medium hover:bg-slate-50 dark:hover:bg-slate-800"
          >
            <RefreshCw size={14} /> Reset
          </button>
        </form>
      </div>

      {/* Main split layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 min-h-[520px]">
        {/* Left: customer list */}
        <div className="lg:col-span-4 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl overflow-hidden flex flex-col">
          <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
              Matched Customers
            </span>
            <span className="text-[11px] font-mono text-emerald-500">{customers.length}</span>
          </div>
          <div className="flex-1 overflow-y-auto max-h-[640px]">
            {loading && customers.length === 0 && (
              <div className="p-8 text-center text-slate-400 text-xs">
                <Loader2 className="animate-spin mx-auto mb-2" size={20} /> Searching…
              </div>
            )}
            {!loading && customers.length === 0 && (
              <div className="p-8 text-center text-slate-400 text-xs">
                No customers matched. Try a different mode or term.
              </div>
            )}
            {customers.map((c) => {
              const active = c.id === selectedCustId;
              return (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => setSelectedCustId(c.id)}
                  className={`w-full text-left px-4 py-3 border-b border-slate-100 dark:border-slate-800/80 transition-colors ${
                    active
                      ? 'bg-emerald-500/10 border-l-2 border-l-emerald-500'
                      : 'hover:bg-slate-50 dark:hover:bg-slate-800/50 border-l-2 border-l-transparent'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-xs font-bold text-emerald-500">
                      {c.customer_number}
                    </span>
                    <span
                      className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${
                        c.customer_status === 'ACTIVE'
                          ? 'bg-emerald-500/15 text-emerald-400'
                          : 'bg-rose-500/15 text-rose-400'
                      }`}
                    >
                      {c.customer_status}
                    </span>
                  </div>
                  <div className="text-sm font-medium mt-0.5 truncate">
                    {c.first_name} {c.last_name}
                  </div>
                  <div className="flex items-center gap-2 mt-1 text-[11px] text-slate-400 font-mono">
                    <span className="text-sky-400">{c.institution_code || '—'}</span>
                    <span>·</span>
                    <span>{(c.cards || []).length} cards</span>
                    <span>·</span>
                    <span>{(c.accounts || []).length} accts</span>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Right: detail workspace */}
        <div className="lg:col-span-8 space-y-4">
          {!selectedCust ? (
            <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-16 text-center text-slate-400 text-sm">
              Select a customer from the left list or search by PAN / Account above.
            </div>
          ) : (
            <>
              {/* Customer header card */}
              <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <div className="flex items-center gap-2">
                      <User size={18} className="text-emerald-500" />
                      <h2 className="text-lg font-bold">
                        {selectedCust.first_name} {selectedCust.last_name}
                      </h2>
                      <span className="font-mono text-xs text-emerald-500 bg-emerald-500/10 px-2 py-0.5 rounded">
                        {selectedCust.customer_number}
                      </span>
                    </div>
                    <div className="mt-2 grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-mono text-slate-400">
                      <div>
                        <div className="text-[10px] uppercase tracking-wide">Bank</div>
                        <div className="text-sky-400 font-bold">
                          {selectedCust.institution_code || '—'}
                        </div>
                      </div>
                      <div>
                        <div className="text-[10px] uppercase tracking-wide">Mobile</div>
                        <div className="text-slate-200">{selectedCust.mobile_number || '—'}</div>
                      </div>
                      <div>
                        <div className="text-[10px] uppercase tracking-wide">Risk</div>
                        <div>{selectedCust.risk_category || 'NORMAL'}</div>
                      </div>
                      <div>
                        <div className="text-[10px] uppercase tracking-wide">Status</div>
                        <div
                          className={
                            selectedCust.customer_status === 'ACTIVE'
                              ? 'text-emerald-400 font-bold'
                              : 'text-rose-400 font-bold'
                          }
                        >
                          {selectedCust.customer_status}
                        </div>
                      </div>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() =>
                        handleUpdateCustomer({
                          customer_status:
                            selectedCust.customer_status === 'ACTIVE' ? 'BLOCKED' : 'ACTIVE',
                        })
                      }
                      className="text-xs px-3 py-1.5 rounded-lg border border-slate-300 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800"
                    >
                      {selectedCust.customer_status === 'ACTIVE' ? 'Block' : 'Activate'}
                    </button>
                  </div>
                </div>
              </div>

              {/* Accounts section */}
              <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl overflow-hidden">
                <div className="px-5 py-3 border-b border-slate-200 dark:border-slate-800 flex items-center gap-2">
                  <Landmark size={16} className="text-amber-500" />
                  <h3 className="text-sm font-bold">Accounts</h3>
                  <span className="text-[11px] font-mono text-slate-400 ml-auto">
                    {(selectedCust.accounts || []).length}
                  </span>
                </div>
                <div className="divide-y divide-slate-100 dark:divide-slate-800">
                  {(selectedCust.accounts || []).length === 0 && (
                    <div className="p-6 text-xs text-slate-400 text-center">No accounts</div>
                  )}
                  {(selectedCust.accounts || []).map((a: any) => (
                    <div
                      key={a.id}
                      className="px-5 py-3.5 flex flex-wrap items-center justify-between gap-3 hover:bg-slate-50/50 dark:hover:bg-slate-800/30"
                    >
                      <div>
                        <div className="font-mono text-sm font-bold text-emerald-500">
                          {a.account_number}
                        </div>
                        <div className="text-[11px] text-slate-400 font-mono mt-0.5">
                          {a.account_type} · {a.account_status} · OD {Number(a.overdraft_limit || 0).toLocaleString()}
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-sm font-bold font-mono">
                          {Number(a.available_balance).toLocaleString()}{' '}
                          <span className="text-slate-400 text-xs">{a.currency}</span>
                        </div>
                        <div className="text-[11px] text-slate-400 font-mono">
                          Ledger {Number(a.ledger_balance).toLocaleString()}
                        </div>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <button
                          type="button"
                          onClick={() => setEditAccountModal({ ...a })}
                          className="flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-lg bg-emerald-600/10 text-emerald-400 hover:bg-emerald-600/20"
                        >
                          <Edit3 size={12} /> Balance
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDeleteAccount(a)}
                          className="flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-lg bg-rose-600/10 text-rose-400 hover:bg-rose-600/20"
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Cards section */}
              <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl overflow-hidden">
                <div className="px-5 py-3 border-b border-slate-200 dark:border-slate-800 flex items-center gap-2">
                  <CreditCard size={16} className="text-sky-500" />
                  <h3 className="text-sm font-bold">Cards</h3>
                  <span className="text-[11px] font-mono text-slate-400 ml-auto">
                    {(selectedCust.cards || []).length}
                  </span>
                </div>
                <div className="p-4 space-y-4">
                  {(selectedCust.cards || []).length === 0 && (
                    <div className="p-4 text-xs text-slate-400 text-center">No cards</div>
                  )}
                  {(selectedCust.cards || []).map((card: any) => (
                    <div
                      key={card.id}
                      className="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/50 p-4 space-y-3"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-base font-bold text-sky-400">
                              {card.masked_pan}
                            </span>
                            <span
                              className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${
                                card.card_status === 'ACTIVE'
                                  ? 'bg-emerald-500/15 text-emerald-400'
                                  : 'bg-rose-500/15 text-rose-400'
                              }`}
                            >
                              {card.card_status}
                            </span>
                          </div>
                          <div className="text-[11px] text-slate-400 font-mono mt-1">
                            Ref {card.test_pan_reference} · {card.cardholder_name} · Exp{' '}
                            {String(card.expiry_month).padStart(2, '0')}/{card.expiry_year} ·{' '}
                            {card.card_product}
                          </div>
                          {card.pin_profile && (
                            <div className="text-[11px] text-amber-400/90 font-mono mt-1">
                              {card.pin_profile.verification_method} · PVV/Offset{' '}
                              {card.pin_profile.pin_offset_reference} · CVV{' '}
                              {card.pin_profile.cvv_reference || '—'}
                            </div>
                          )}
                        </div>
                        <div className="flex flex-wrap gap-1.5">
                          <button
                            type="button"
                            onClick={() => {
                              setPinModalCard(card);
                              setNewPin('1234');
                            }}
                            className="flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-lg bg-violet-600/10 text-violet-400 hover:bg-violet-600/20"
                          >
                            <KeyRound size={12} /> PIN
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              setLinkModalCard(card);
                              setTargetAccountId(allAccounts[0]?.id || '');
                              setLinkRole('SECONDARY');
                            }}
                            className="flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-lg bg-sky-600/10 text-sky-400 hover:bg-sky-600/20"
                          >
                            <LinkIcon size={12} /> Link Acct
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              setReassignModalCard(card);
                              setReassignCustId(allCustomers[0]?.id || '');
                            }}
                            className="flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-lg bg-amber-600/10 text-amber-400 hover:bg-amber-600/20"
                          >
                            <ArrowRightLeft size={12} /> Reassign
                          </button>
                          <button
                            type="button"
                            onClick={() => handleDeleteCard(card)}
                            className="flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-lg bg-rose-600/10 text-rose-400 hover:bg-rose-600/20"
                          >
                            <Trash2 size={12} />
                          </button>
                        </div>
                      </div>

                      {/* Linked accounts */}
                      <div className="space-y-1.5">
                        <div className="text-[10px] uppercase tracking-wide text-slate-500 font-bold">
                          Linked Accounts
                        </div>
                        {(card.card_accounts || []).length === 0 && (
                          <div className="text-[11px] text-slate-500 italic">No linked accounts</div>
                        )}
                        {(card.card_accounts || []).map((lnk: any) => (
                          <div
                            key={lnk.id}
                            className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-xs font-mono"
                          >
                            <div className="flex items-center gap-2">
                              <ChevronRight size={12} className="text-slate-500" />
                              <span className="font-bold text-emerald-500">{lnk.account_number}</span>
                              <span className="text-slate-400">{lnk.account_type}</span>
                              <span
                                className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${
                                  lnk.account_role === 'PRIMARY'
                                    ? 'bg-emerald-500/15 text-emerald-400'
                                    : 'bg-slate-500/15 text-slate-400'
                                }`}
                              >
                                {lnk.account_role}
                              </span>
                              <span className="text-slate-400">
                                Avl {Number(lnk.available_balance).toLocaleString()} {lnk.currency}
                              </span>
                            </div>
                            <div className="flex gap-1.5">
                              {lnk.account_role !== 'PRIMARY' && (
                                <button
                                  type="button"
                                  onClick={() => handleSetPrimary(lnk.id, lnk.account_number)}
                                  className="text-[10px] text-emerald-400 hover:underline"
                                >
                                  Make Primary
                                </button>
                              )}
                              <button
                                type="button"
                                onClick={() =>
                                  handleUnlink(lnk.id, lnk.account_number, card.masked_pan)
                                }
                                className="text-[10px] text-rose-400 hover:underline flex items-center gap-0.5"
                              >
                                <Unlink size={10} /> Unlink
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {/* ========== MODALS ========== */}

      {/* Edit Account Balance */}
      {editAccountModal && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <form
            onSubmit={handleSaveAccountEdit}
            className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 w-full max-w-md space-y-4 shadow-2xl"
          >
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-bold font-mono text-emerald-400">
                Edit Account {editAccountModal.account_number}
              </h2>
              <button type="button" onClick={() => setEditAccountModal(null)}>
                <X size={16} className="text-slate-400" />
              </button>
            </div>
            <div className="grid grid-cols-2 gap-3 text-xs font-mono">
              <label className="space-y-1">
                <span className="text-slate-400">Available Balance</span>
                <input
                  type="number"
                  step="0.01"
                  value={editAccountModal.available_balance}
                  onChange={(e) =>
                    setEditAccountModal({
                      ...editAccountModal,
                      available_balance: e.target.value,
                    })
                  }
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2"
                />
              </label>
              <label className="space-y-1">
                <span className="text-slate-400">Ledger Balance</span>
                <input
                  type="number"
                  step="0.01"
                  value={editAccountModal.ledger_balance}
                  onChange={(e) =>
                    setEditAccountModal({
                      ...editAccountModal,
                      ledger_balance: e.target.value,
                    })
                  }
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2"
                />
              </label>
              <label className="space-y-1">
                <span className="text-slate-400">Overdraft Limit</span>
                <input
                  type="number"
                  step="0.01"
                  value={editAccountModal.overdraft_limit || 0}
                  onChange={(e) =>
                    setEditAccountModal({
                      ...editAccountModal,
                      overdraft_limit: e.target.value,
                    })
                  }
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2"
                />
              </label>
              <label className="space-y-1">
                <span className="text-slate-400">Status</span>
                <select
                  value={editAccountModal.account_status}
                  onChange={(e) =>
                    setEditAccountModal({
                      ...editAccountModal,
                      account_status: e.target.value,
                    })
                  }
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2"
                >
                  <option value="ACTIVE">ACTIVE</option>
                  <option value="BLOCKED">BLOCKED</option>
                  <option value="CLOSED">CLOSED</option>
                </select>
              </label>
              <label className="space-y-1 col-span-2">
                <span className="text-slate-400">Account Type</span>
                <select
                  value={editAccountModal.account_type}
                  onChange={(e) =>
                    setEditAccountModal({
                      ...editAccountModal,
                      account_type: e.target.value,
                    })
                  }
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2"
                >
                  <option value="SAVINGS">SAVINGS</option>
                  <option value="CURRENT">CURRENT</option>
                  <option value="CREDIT">CREDIT</option>
                </select>
              </label>
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t border-slate-200 dark:border-slate-800">
              <button
                type="button"
                onClick={() => setEditAccountModal(null)}
                className="px-4 py-2 text-xs rounded-lg"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="bg-emerald-600 hover:bg-emerald-500 text-white px-5 py-2 rounded-lg text-xs font-semibold"
              >
                Save Balances
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Change PIN */}
      {pinModalCard && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <form
            onSubmit={handleChangePin}
            className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 w-full max-w-sm space-y-4 shadow-2xl"
          >
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-bold">Change PIN — {pinModalCard.masked_pan}</h2>
              <button type="button" onClick={() => setPinModalCard(null)}>
                <X size={16} className="text-slate-400" />
              </button>
            </div>
            <p className="text-[11px] text-slate-400">
              New clear PIN will recalculate Visa PVV / IBM offset via Soft-HSM.
            </p>
            <input
              type="password"
              inputMode="numeric"
              pattern="[0-9]*"
              minLength={4}
              maxLength={12}
              value={newPin}
              onChange={(e) => setNewPin(e.target.value)}
              className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2.5 font-mono text-center text-lg tracking-widest"
              required
            />
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setPinModalCard(null)} className="px-4 py-2 text-xs">
                Cancel
              </button>
              <button
                type="submit"
                className="bg-violet-600 hover:bg-violet-500 text-white px-5 py-2 rounded-lg text-xs font-semibold"
              >
                Update PIN
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Link Account */}
      {linkModalCard && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 w-full max-w-md space-y-4 shadow-2xl">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-bold">Link Account → {linkModalCard.masked_pan}</h2>
              <button type="button" onClick={() => setLinkModalCard(null)}>
                <X size={16} className="text-slate-400" />
              </button>
            </div>
            <select
              value={targetAccountId}
              onChange={(e) => setTargetAccountId(e.target.value)}
              className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono"
            >
              {allAccounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.account_number} ({a.account_type}) — {a.customer_name} —{' '}
                  {Number(a.available_balance).toLocaleString()} {a.currency}
                </option>
              ))}
            </select>
            <select
              value={linkRole}
              onChange={(e) => setLinkRole(e.target.value)}
              className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono"
            >
              <option value="PRIMARY">PRIMARY</option>
              <option value="SECONDARY">SECONDARY</option>
            </select>
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setLinkModalCard(null)} className="px-4 py-2 text-xs">
                Cancel
              </button>
              <button
                type="button"
                onClick={handleLinkAccount}
                className="bg-sky-600 hover:bg-sky-500 text-white px-5 py-2 rounded-lg text-xs font-semibold flex items-center gap-1"
              >
                <Plus size={14} /> Link Account
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Reassign Customer */}
      {reassignModalCard && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <form
            onSubmit={handleReassignCustomer}
            className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 w-full max-w-md space-y-4 shadow-2xl"
          >
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-bold">
                Reassign Card {reassignModalCard.masked_pan}
              </h2>
              <button type="button" onClick={() => setReassignModalCard(null)}>
                <X size={16} className="text-slate-400" />
              </button>
            </div>
            <p className="text-[11px] text-slate-400">
              Move this card to a different customer CIF. Linked accounts stay with the card.
            </p>
            <select
              value={reassignCustId}
              onChange={(e) => setReassignCustId(e.target.value)}
              className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono"
              required
            >
              {allCustomers.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.customer_number} — {c.name}
                </option>
              ))}
            </select>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setReassignModalCard(null)}
                className="px-4 py-2 text-xs"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="bg-amber-600 hover:bg-amber-500 text-white px-5 py-2 rounded-lg text-xs font-semibold flex items-center gap-1"
              >
                <ArrowRightLeft size={14} /> Reassign Customer
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
};
