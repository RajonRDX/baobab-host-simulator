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
  ChevronDown,
  Mail,
  Phone,
  MapPin,
  Calendar,
  Gauge,
  History,
  RotateCcw,
  Wallet,
  Fingerprint,
  BadgeCheck,
  Info,
  Ban,
  ShieldCheck,
  Users,
  Pencil,
} from 'lucide-react';
import { apiFetch } from '../api';

// ============================================================================
// Customer Maintenance 360  (Rajon Host Simulator)
// Search by Customer / PAN / Account  ->  profile, accounts, cards, limits, transactions
// ============================================================================

type SearchMode = 'all' | 'customer' | 'pan' | 'account';
type DetailTab = 'cards' | 'limits' | 'transactions' | 'accounts';

const MODE_TABS: { id: SearchMode; label: string; icon: React.ReactNode; hint: string }[] = [
  { id: 'all', label: 'All', icon: <Search size={14} />, hint: 'CIF, name, mobile, NID, PAN or account number' },
  { id: 'customer', label: 'Customer', icon: <User size={14} />, hint: 'Customer number / name / mobile / email / NID / passport' },
  { id: 'pan', label: 'PAN / Card', icon: <CreditCard size={14} />, hint: 'Full or partial PAN (shows card, accounts and limits)' },
  { id: 'account', label: 'Account', icon: <Landmark size={14} />, hint: 'Account number' },
];

const DETAIL_TABS: { id: DetailTab; label: string; icon: React.ReactNode }[] = [
  { id: 'cards', label: 'Cards', icon: <CreditCard size={14} /> },
  { id: 'limits', label: 'Limits', icon: <Gauge size={14} /> },
  { id: 'transactions', label: 'Transactions', icon: <History size={14} /> },
  { id: 'accounts', label: 'Accounts', icon: <Landmark size={14} /> },
];

const CARD_STATUSES = ['ACTIVE', 'BLOCKED', 'EXPIRED', 'LOST', 'STOLEN', 'CLOSED'];
const GENDERS = ['', 'MALE', 'FEMALE', 'OTHER'];
const MARITAL = ['', 'SINGLE', 'MARRIED', 'DIVORCED', 'WIDOWED'];
const KYC = ['', 'PENDING', 'VERIFIED', 'REJECTED', 'EXPIRED'];

const CUSTOMER_FORM_FIELDS = [
  'first_name', 'last_name', 'email', 'mobile_number', 'alternate_mobile', 'date_of_birth', 'gender',
  'marital_status', 'father_name', 'mother_name', 'spouse_name', 'nationality', 'place_of_birth',
  'nid_number', 'passport_number', 'passport_expiry_date', 'driving_license_number', 'tin_number',
  'occupation', 'employer_name', 'address', 'permanent_address', 'city', 'postal_code', 'country',
  'kyc_status', 'risk_category', 'customer_status', 'notes',
];
const DATE_FIELDS = ['date_of_birth', 'passport_expiry_date'];

const inputCls =
  'w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs focus:ring-2 focus:ring-emerald-500/40 focus:border-emerald-500 outline-none';
const cardCls = 'bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl';

// ---------------------------------------------------------------- helpers
const num = (v: any, digits = 2) =>
  Number(v ?? 0).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: digits });
const dash = (v: any) => (v === null || v === undefined || v === '' ? '—' : String(v));
const dateOnly = (iso?: string | null) => {
  if (!iso) return '—';
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00` : iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: '2-digit' });
};
const dateTime = (iso?: string | null) => {
  if (!iso) return '—';
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleString();
};
const ageFrom = (iso?: string | null) => {
  if (!iso) return null;
  const d = new Date(`${iso}T00:00:00`);
  if (isNaN(d.getTime())) return null;
  const now = new Date();
  let a = now.getFullYear() - d.getFullYear();
  if (now.getMonth() < d.getMonth() || (now.getMonth() === d.getMonth() && now.getDate() < d.getDate())) a -= 1;
  return a;
};
const initials = (c: any) =>
  `${(c?.first_name || '?')[0] || ''}${(c?.last_name || '')[0] || ''}`.toUpperCase();
const expiryText = (card: any) =>
  `${String(card?.expiry_month ?? '').padStart(2, '0')}/${card?.expiry_year ?? ''}`;
const isExpired = (card: any) => {
  const now = new Date();
  const y = Number(card?.expiry_year);
  const m = Number(card?.expiry_month);
  if (!y || !m) return false;
  return y < now.getFullYear() || (y === now.getFullYear() && m < now.getMonth() + 1);
};
const barColor = (pct: number | null | undefined) =>
  pct === null || pct === undefined
    ? 'bg-slate-400'
    : pct >= 90
    ? 'bg-rose-500'
    : pct >= 70
    ? 'bg-amber-500'
    : 'bg-emerald-500';
const fmtLimit = (v: any, unit?: string, currency?: string) =>
  unit === 'COUNT' ? `${num(v, 0)} txn` : `${num(v)}${currency ? ` ${currency}` : ''}`;

const StatusPill: React.FC<{ value?: string }> = ({ value }) => {
  const v = (value || '').toUpperCase();
  const ok = v === 'ACTIVE' || v === 'VERIFIED' || v === 'APPROVED';
  const warn = v === 'PENDING' || v === 'NORMAL' || v === 'SUSPENDED' || v === 'INACTIVE';
  const cls = ok
    ? 'bg-emerald-500/15 text-emerald-500 border-emerald-500/25'
    : warn
    ? 'bg-amber-500/15 text-amber-500 border-amber-500/25'
    : 'bg-rose-500/15 text-rose-500 border-rose-500/25';
  return (
    <span className={`text-[10px] px-2 py-0.5 rounded-full border font-bold tracking-wide ${cls}`}>{value || '—'}</span>
  );
};

const Modal: React.FC<{ title: React.ReactNode; onClose: () => void; wide?: boolean; children: React.ReactNode }> = ({
  title,
  onClose,
  wide,
  children,
}) => (
  <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
    <div
      className={`${cardCls} w-full ${wide ? 'max-w-3xl' : 'max-w-md'} max-h-[92vh] flex flex-col shadow-2xl`}
    >
      <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-200 dark:border-slate-800">
        <h2 className="text-sm font-bold">{title}</h2>
        <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-200">
          <X size={16} />
        </button>
      </div>
      <div className="p-5 overflow-y-auto">{children}</div>
    </div>
  </div>
);

const Field: React.FC<{ label: string; value: any; mono?: boolean; wide?: boolean }> = ({ label, value, mono, wide }) => (
  <div className={wide ? 'col-span-2 sm:col-span-3 lg:col-span-4' : ''}>
    <div className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">{label}</div>
    <div className={`text-xs mt-0.5 break-words ${mono ? 'font-mono' : ''} ${value ? '' : 'text-slate-400'}`}>
      {dash(value)}
    </div>
  </div>
);

const LabeledInput: React.FC<{
  label: string;
  value: any;
  onChange: (v: string) => void;
  type?: string;
  span?: number;
  placeholder?: string;
  children?: React.ReactNode;
}> = ({ label, value, onChange, type = 'text', span = 1, placeholder, children }) => (
  <label className={`space-y-1 block ${span === 2 ? 'col-span-2' : ''}`}>
    <span className="text-[11px] text-slate-400 font-medium">{label}</span>
    {children ? (
      children
    ) : (
      <input
        type={type}
        value={value ?? ''}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className={inputCls}
      />
    )}
  </label>
);

const ProgressBar: React.FC<{ pct: number | null | undefined }> = ({ pct }) => (
  <div className="h-2 rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden">
    <div
      className={`h-full rounded-full transition-all ${barColor(pct)}`}
      style={{ width: `${Math.min(100, Math.max(pct ?? 0, pct ? 2 : 0))}%` }}
    />
  </div>
);

// ---------------------------------------------------------------- one limit row
const LimitRow: React.FC<{
  row: any;
  onEdit: (row: any) => void;
  onReset?: (row: any) => void;
}> = ({ row, onEdit, onReset }) => {
  const hasUsage = row.used !== null && row.used !== undefined;
  return (
    <div className="grid grid-cols-12 gap-3 items-center px-4 py-3 border-t border-slate-100 dark:border-slate-800/80 hover:bg-slate-50/60 dark:hover:bg-slate-800/30">
      <div className="col-span-12 md:col-span-4 min-w-0">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs font-semibold truncate">{row.name}</span>
          {row.limit_code && (
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-500/10 text-slate-400">#{row.limit_code}</span>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-1.5 mt-1">
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-sky-500/10 text-sky-400 font-mono">{row.period}</span>
          {row.enforced === false && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-500/10 text-slate-400" title="Stored and tracked, but not blocking authorizations">
              tracked only
            </span>
          )}
          {row.override_active && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-violet-500/10 text-violet-400">override</span>
          )}
          {row.method && row.method !== 'SUM_TRANSACTION_AMOUNT' && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-400 font-mono">{row.method}</span>
          )}
        </div>
      </div>
      <div className="col-span-12 md:col-span-4">
        {hasUsage ? (
          <>
            <ProgressBar pct={row.percent} />
            <div className="flex justify-between text-[10px] text-slate-400 mt-1 font-mono">
              <span>{row.percent ?? 0}% used</span>
              {row.resets_at ? <span>resets {dateTime(row.resets_at)}</span> : <span>&nbsp;</span>}
            </div>
          </>
        ) : (
          <div className="text-[10px] text-slate-400 italic">Checked per transaction - no running usage</div>
        )}
      </div>
      <div className="col-span-7 md:col-span-2 text-right font-mono tabular-nums">
        <div className="text-xs font-bold">
          {hasUsage ? (
            <>
              {fmtLimit(row.used, row.unit)} <span className="text-slate-400 font-normal">/ {fmtLimit(row.max, row.unit)}</span>
            </>
          ) : (
            <>max {fmtLimit(row.max, row.unit)}</>
          )}
        </div>
        {hasUsage && (
          <div className="text-[10px] text-slate-400">left {fmtLimit(row.remaining, row.unit)}</div>
        )}
      </div>
      <div className="col-span-5 md:col-span-2 flex justify-end gap-1">
        {hasUsage && onReset && (
          <button
            type="button"
            onClick={() => onReset(row)}
            title="Reset usage"
            className="flex items-center gap-1 text-[11px] px-2 py-1 rounded-lg bg-amber-500/10 text-amber-500 hover:bg-amber-500/20"
          >
            <RotateCcw size={12} /> Reset
          </button>
        )}
        <button
          type="button"
          onClick={() => onEdit(row)}
          title="Edit maximum"
          className="flex items-center gap-1 text-[11px] px-2 py-1 rounded-lg bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20"
        >
          <Pencil size={12} /> Edit
        </button>
      </div>
    </div>
  );
};

const SectionHead: React.FC<{ icon: React.ReactNode; title: string; sub?: string; right?: React.ReactNode }> = ({
  icon,
  title,
  sub,
  right,
}) => (
  <div className="flex flex-wrap items-center gap-3 px-4 py-3 bg-slate-50/70 dark:bg-slate-950/40">
    <div className="text-emerald-500">{icon}</div>
    <div className="min-w-0">
      <div className="text-xs font-bold">{title}</div>
      {sub && <div className="text-[10px] text-slate-400 font-mono">{sub}</div>}
    </div>
    <div className="ml-auto flex flex-wrap gap-1.5">{right}</div>
  </div>
);

// ============================================================================
export const CustomerDataMaintenancePage: React.FC = () => {
  const [mode, setMode] = useState<SearchMode>('all');
  const [searchTerm, setSearchTerm] = useState('');
  const [loading, setLoading] = useState(false);
  const [customers, setCustomers] = useState<any[]>([]);
  const [allAccounts, setAllAccounts] = useState<any[]>([]);
  const [allCustomers, setAllCustomers] = useState<any[]>([]);
  const [selectedCustId, setSelectedCustId] = useState<string>('');
  const [selectedCardId, setSelectedCardId] = useState<string>('');
  const [tab, setTab] = useState<DetailTab>('cards');
  const [msg, setMsg] = useState('');
  const [error, setError] = useState('');
  const [stats, setStats] = useState({ total_customers: 0, total_cards: 0, total_accounts: 0 });
  const [showKyc, setShowKyc] = useState(true);

  // modals
  const [editAccountModal, setEditAccountModal] = useState<any | null>(null);
  const [pinModalCard, setPinModalCard] = useState<any | null>(null);
  const [newPin, setNewPin] = useState('1234');
  const [linkModalCard, setLinkModalCard] = useState<any | null>(null);
  const [targetAccountId, setTargetAccountId] = useState('');
  const [linkRole, setLinkRole] = useState('SECONDARY');
  const [reassignModalCard, setReassignModalCard] = useState<any | null>(null);
  const [reassignCustId, setReassignCustId] = useState('');
  const [editCustomer, setEditCustomer] = useState<Record<string, any> | null>(null);
  const [editCard, setEditCard] = useState<any | null>(null);
  const [limitEdit, setLimitEdit] = useState<{ row: any; value: string } | null>(null);
  const [resetModal, setResetModal] = useState<{ title: string; text: string; run: (reason: string) => Promise<void> } | null>(null);
  const [resetReason, setResetReason] = useState('Testing reset');
  const [busy, setBusy] = useState(false);

  // limits + transactions
  const [limitsData, setLimitsData] = useState<any | null>(null);
  const [limitsLoading, setLimitsLoading] = useState(false);
  const [limitsError, setLimitsError] = useState('');
  const [txData, setTxData] = useState<any | null>(null);
  const [txLoading, setTxLoading] = useState(false);
  const [txError, setTxError] = useState('');
  const [txCount, setTxCount] = useState(20);
  const [txScope, setTxScope] = useState<string>('card');
  const [txOpen, setTxOpen] = useState<string>('');

  const flash = (text: string, isError = false) => {
    if (isError) {
      setError(text);
      setMsg('');
    } else {
      setMsg(text);
      setError('');
    }
  };

  useEffect(() => {
    if (!msg) return;
    const t = setTimeout(() => setMsg(''), 6000);
    return () => clearTimeout(t);
  }, [msg]);

  // ---------------------------------------------------------------- load workspace
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
          const chosen = still || custList[0];
          setSelectedCustId(chosen.id);
          const cards = chosen.cards || [];
          setSelectedCardId((prev) => (cards.some((c: any) => c.id === prev) ? prev : cards[0]?.id || ''));
          // PAN search -> jump straight to the limits of the matched card
          if (activeMode === 'pan' && query.trim() && cards.length > 0) {
            setSelectedCardId(cards[0].id);
            setTab('limits');
          }
        } else {
          setSelectedCustId('');
          setSelectedCardId('');
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
  const selectedCard = useMemo(() => {
    const cards = selectedCust?.cards || [];
    return cards.find((c: any) => c.id === selectedCardId) || cards[0] || null;
  }, [selectedCust, selectedCardId]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    loadWorkspace(searchTerm, mode);
  };
  const switchMode = (m: SearchMode) => {
    setMode(m);
    loadWorkspace(searchTerm, m);
  };

  // ---------------------------------------------------------------- limits / transactions loaders
  const loadLimits = useCallback(async (cardId: string) => {
    if (!cardId) return;
    setLimitsLoading(true);
    setLimitsError('');
    try {
      setLimitsData(await apiFetch(`/maintenance/card/${cardId}/limits`));
    } catch (err: any) {
      setLimitsError(err.message || 'Could not load limits');
      setLimitsData(null);
    } finally {
      setLimitsLoading(false);
    }
  }, []);

  const loadTransactions = useCallback(
    async (scope: string, count: number, cardId: string, custId: string) => {
      const params = new URLSearchParams({ limit: String(count) });
      if (scope === 'card' && cardId) params.set('card_id', cardId);
      else if (scope.startsWith('acct:')) params.set('account_id', scope.slice(5));
      else if (custId) params.set('customer_id', custId);
      else return;
      setTxLoading(true);
      setTxError('');
      try {
        setTxData(await apiFetch(`/maintenance/transactions?${params.toString()}`));
      } catch (err: any) {
        setTxError(err.message || 'Could not load transactions');
        setTxData(null);
      } finally {
        setTxLoading(false);
      }
    },
    []
  );

  useEffect(() => {
    if (tab === 'limits' && selectedCard?.id) loadLimits(selectedCard.id);
  }, [tab, selectedCard?.id, loadLimits]);

  useEffect(() => {
    if (tab !== 'transactions' || !selectedCust) return;
    const scope = txScope === 'card' && !selectedCard ? 'customer' : txScope;
    loadTransactions(scope, txCount, selectedCard?.id || '', selectedCust.id);
  }, [tab, txScope, txCount, selectedCard?.id, selectedCust?.id, loadTransactions]);

  useEffect(() => {
    setTxScope(selectedCard ? 'card' : 'customer');
    setTxOpen('');
    setLimitsData(null);
    setTxData(null);
  }, [selectedCard?.id, selectedCust?.id]);

  // ---------------------------------------------------------------- existing actions (kept)
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
        `Account ${editAccountModal.account_number} updated - Available ${Number(
          editAccountModal.available_balance
        ).toLocaleString()} ${editAccountModal.currency}`
      );
      setEditAccountModal(null);
      await loadWorkspace(searchTerm, mode);
    } catch (err: any) {
      flash(err.message || 'Update failed', true);
    }
  };

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

  const handleChangePin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!pinModalCard) return;
    try {
      const res = await apiFetch(`/cards/${pinModalCard.id}/pin`, {
        method: 'POST',
        body: JSON.stringify({ new_pin: newPin }),
      });
      flash(`PIN updated for ${pinModalCard.masked_pan} - new PVV/Offset: ${res.new_pvv || 'OK'}`);
      setPinModalCard(null);
      setNewPin('1234');
      await loadWorkspace(searchTerm, mode);
    } catch (err: any) {
      flash(err.message, true);
    }
  };

  const handleReassignCustomer = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!reassignModalCard || !reassignCustId) return;
    try {
      const res = await apiFetch(`/cards/${reassignModalCard.id}/reassign-customer`, {
        method: 'PUT',
        body: JSON.stringify({ customer_id: reassignCustId }),
      });
      flash(`Card ${reassignModalCard.masked_pan} moved to customer ${res.new_customer_number}`);
      setReassignModalCard(null);
      setReassignCustId('');
      await loadWorkspace(searchTerm, mode);
    } catch (err: any) {
      flash(err.message, true);
    }
  };

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

  const handleUpdateCustomer = async (fields: Record<string, any>) => {
    if (!selectedCust) return;
    try {
      await apiFetch(`/customers/${selectedCust.id}`, { method: 'PUT', body: JSON.stringify(fields) });
      flash('Customer updated');
      await loadWorkspace(searchTerm, mode);
    } catch (err: any) {
      flash(err.message, true);
    }
  };

  // ---------------------------------------------------------------- new actions
  const openEditCustomer = () => {
    if (!selectedCust) return;
    const f: Record<string, any> = {};
    CUSTOMER_FORM_FIELDS.forEach((k) => {
      f[k] = selectedCust[k] ?? '';
    });
    setEditCustomer(f);
  };

  const saveCustomer = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editCustomer || !selectedCust) return;
    if (!String(editCustomer.first_name || '').trim()) {
      flash('First name is required', true);
      return;
    }
    const payload: Record<string, any> = {};
    CUSTOMER_FORM_FIELDS.forEach((k) => {
      const v = editCustomer[k];
      if (k === 'first_name') payload[k] = String(v).trim();
      else if (DATE_FIELDS.includes(k)) payload[k] = v ? v : null;
      else payload[k] = typeof v === 'string' && v.trim() === '' ? null : v;
    });
    setBusy(true);
    try {
      await apiFetch(`/customers/${selectedCust.id}`, { method: 'PUT', body: JSON.stringify(payload) });
      flash('Customer profile saved');
      setEditCustomer(null);
      await loadWorkspace(searchTerm, mode);
    } catch (err: any) {
      flash(err.message || 'Save failed', true);
    } finally {
      setBusy(false);
    }
  };

  const openEditCard = (card: any) =>
    setEditCard({
      id: card.id,
      masked_pan: card.masked_pan,
      cardholder_name: card.cardholder_name,
      expiry_month: card.expiry_month,
      expiry_year: card.expiry_year,
      card_status: card.card_status,
      card_product: card.card_product,
      card_type: card.card_type,
    });

  const expiryPreset = (kind: 'plus1' | 'plus3' | 'expired') => {
    if (!editCard) return;
    const now = new Date();
    if (kind === 'expired') {
      const d = new Date(now.getFullYear(), now.getMonth() - 1, 1);
      setEditCard({ ...editCard, expiry_month: d.getMonth() + 1, expiry_year: d.getFullYear() });
    } else {
      const years = kind === 'plus1' ? 1 : 3;
      setEditCard({ ...editCard, expiry_month: now.getMonth() + 1, expiry_year: now.getFullYear() + years });
    }
  };

  const saveCard = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editCard) return;
    setBusy(true);
    try {
      const res = await apiFetch(`/maintenance/card/${editCard.id}`, {
        method: 'PUT',
        body: JSON.stringify({
          cardholder_name: editCard.cardholder_name,
          expiry_month: Number(editCard.expiry_month),
          expiry_year: Number(editCard.expiry_year),
          card_status: editCard.card_status,
          card_product: editCard.card_product,
          card_type: editCard.card_type,
        }),
      });
      if (res.warning) flash(res.warning, true);
      else flash(`Card ${editCard.masked_pan} updated${res.cvv_regenerated ? ' - CVV recalculated for the new expiry' : ''}`);
      setEditCard(null);
      await loadWorkspace(searchTerm, mode);
    } catch (err: any) {
      flash(err.message || 'Card update failed', true);
    } finally {
      setBusy(false);
    }
  };

  const toggleCardStatus = async (card: any) => {
    const next = card.card_status === 'ACTIVE' ? 'BLOCKED' : 'ACTIVE';
    try {
      await apiFetch(`/maintenance/card/${card.id}`, { method: 'PUT', body: JSON.stringify({ card_status: next }) });
      flash(`Card ${card.masked_pan} is now ${next}`);
      await loadWorkspace(searchTerm, mode);
    } catch (err: any) {
      flash(err.message, true);
    }
  };

  // ---- limits: edit
  const openLimitEdit = (row: any) => setLimitEdit({ row, value: String(row.max ?? 0) });

  const saveLimitEdit = async (e: React.FormEvent, clearOverride = false) => {
    e.preventDefault();
    if (!limitEdit) return;
    const { row } = limitEdit;
    setBusy(true);
    try {
      if (row.source === 'PROFILE') {
        await apiFetch(`/maintenance/profile-limit/${row.assignment_id}/max`, {
          method: 'PUT',
          body: JSON.stringify({ maximum_limit: clearOverride ? null : limitEdit.value }),
        });
      } else if (row.scope === 'CARD') {
        await apiFetch(`/maintenance/card/${selectedCard.id}/legacy-limits`, {
          method: 'PATCH',
          body: JSON.stringify({ [row.key]: limitEdit.value }),
        });
      } else {
        await apiFetch(`/maintenance/account/${row.target_id}/legacy-limits`, {
          method: 'PATCH',
          body: JSON.stringify({ [row.key]: limitEdit.value }),
        });
      }
      flash(clearOverride ? `Override removed for ${row.name}` : `${row.name} maximum saved`);
      setLimitEdit(null);
      if (selectedCard) await loadLimits(selectedCard.id);
      await loadWorkspace(searchTerm, mode);
    } catch (err: any) {
      flash(err.message || 'Limit update failed', true);
    } finally {
      setBusy(false);
    }
  };

  // ---- limits: reset
  const askReset = (title: string, text: string, body: Record<string, any>) => {
    if (!selectedCard) return;
    setResetReason('Testing reset');
    setResetModal({
      title,
      text,
      run: async (reason: string) => {
        const res = await apiFetch(`/maintenance/card/${selectedCard.id}/limits/reset`, {
          method: 'POST',
          body: JSON.stringify({ ...body, reason }),
        });
        const legacyCount = (res.legacy || []).length;
        flash(`Usage reset - ${legacyCount} counter set(s), ${res.profile_records_reset || 0} profile record(s)`);
        await loadLimits(selectedCard.id);
        await loadWorkspace(searchTerm, mode);
      },
    });
  };

  const askResetRow = (row: any) => {
    if (row.source === 'PROFILE') {
      askReset(
        `Reset usage: ${row.name}`,
        `Clears the running usage of limit #${row.limit_code} for ${row.target_label}.`,
        {
          target: 'PROFILE',
          limit_definition_id: row.definition_id,
          include_card: row.scope === 'CARD',
          include_accounts: row.scope === 'ACCOUNT',
          account_id: row.scope === 'ACCOUNT' ? row.target_id : null,
        }
      );
    } else {
      askReset(
        `Reset ${row.period.toLowerCase()} usage`,
        `Sets the ${row.period.toLowerCase()} used counter of ${row.target_label} back to zero.`,
        {
          target: 'LEGACY',
          period: row.period,
          include_card: row.scope === 'CARD',
          include_accounts: row.scope === 'ACCOUNT',
          account_id: row.scope === 'ACCOUNT' ? row.target_id : null,
        }
      );
    }
  };

  const runReset = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!resetModal) return;
    setBusy(true);
    try {
      await resetModal.run(resetReason.trim() || 'Testing reset');
      setResetModal(null);
    } catch (err: any) {
      flash(err.message || 'Reset failed', true);
      setResetModal(null);
    } finally {
      setBusy(false);
    }
  };

  // account legacy limits (from the search payload) - used by the Accounts tab
  const accountLimitRows = (a: any) => {
    const l = a.limits;
    if (!l) return [];
    const mk = (key: string, name: string, period: string, usedKey: string | null, enforced: boolean) => ({
      row_id: `A:${a.id}:${key}`,
      source: 'LEGACY',
      scope: 'ACCOUNT',
      target_id: a.id,
      target_label: a.account_number,
      key,
      name,
      period,
      unit: 'AMOUNT',
      max: Number(l[key] || 0),
      used: usedKey ? Number(l[usedKey] || 0) : null,
      remaining: usedKey ? Math.max(0, Number(l[key] || 0) - Number(l[usedKey] || 0)) : null,
      percent: usedKey && Number(l[key]) ? Math.round((Number(l[usedKey] || 0) * 1000) / Number(l[key])) / 10 : null,
      enforced,
    });
    return [
      mk('per_transaction_limit', 'Per-Transaction Limit', 'PER_TRANSACTION', null, true),
      mk('daily_limit', 'Daily Limit', 'DAILY', 'daily_used', true),
      mk('weekly_limit', 'Weekly Limit', 'WEEKLY', 'weekly_used', false),
      mk('monthly_limit', 'Monthly Limit', 'MONTHLY', 'monthly_used', false),
    ];
  };

  const askResetAccountRow = (row: any) => {
    setResetReason('Testing reset');
    setResetModal({
      title: `Reset ${row.period.toLowerCase()} usage`,
      text: `Sets the ${row.period.toLowerCase()} used counter of account ${row.target_label} back to zero.`,
      run: async (reason: string) => {
        await apiFetch(`/accounts/${row.target_id}/limits/reset-usage`, {
          method: 'POST',
          body: JSON.stringify({ scope: row.period, reason, confirm_reset: true }),
        });
        flash(`Account ${row.target_label} ${row.period.toLowerCase()} usage reset`);
        await loadWorkspace(searchTerm, mode);
      },
    });
  };

  // ======================================================================== RENDER
  const legacyCard = limitsData?.legacy?.card;
  const legacyAccounts: any[] = limitsData?.legacy?.accounts || [];
  const profileRows: any[] = limitsData?.profile?.rows || [];
  const profileInfo = limitsData?.profile?.info;

  return (
    <div className="space-y-5">
      {/* ------------------------------------------------ Header */}
      <div className="relative overflow-hidden rounded-2xl border border-emerald-500/20 bg-gradient-to-br from-emerald-600/15 via-sky-500/10 to-violet-500/10 p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold tracking-tight flex items-center gap-2">
              <ShieldCheck className="text-emerald-500" size={24} />
              Customer Maintenance 360
            </h1>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 max-w-2xl">
              One workspace for a customer: profile and KYC, cards, accounts, limits with live usage, and the latest
              transactions. Search by customer, PAN or account.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-[11px] font-mono">
            <span className="px-3 py-1.5 rounded-xl bg-sky-500/10 text-sky-500 border border-sky-500/20">
              <Users size={12} className="inline mr-1 -mt-0.5" />
              {stats.total_customers} customers
            </span>
            <span className="px-3 py-1.5 rounded-xl bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">
              <CreditCard size={12} className="inline mr-1 -mt-0.5" />
              {stats.total_cards} cards
            </span>
            <span className="px-3 py-1.5 rounded-xl bg-amber-500/10 text-amber-500 border border-amber-500/20">
              <Landmark size={12} className="inline mr-1 -mt-0.5" />
              {stats.total_accounts} accounts
            </span>
          </div>
        </div>
      </div>

      {/* ------------------------------------------------ Alerts */}
      {msg && (
        <div className="flex items-center gap-2 p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-500 text-xs font-mono">
          <CheckCircle2 size={16} /> <span className="flex-1">{msg}</span>
          <button onClick={() => setMsg('')} className="opacity-60 hover:opacity-100">
            <X size={14} />
          </button>
        </div>
      )}
      {error && (
        <div className="flex items-center gap-2 p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-500 text-xs font-mono">
          <ShieldAlert size={16} /> <span className="flex-1">{error}</span>
          <button onClick={() => setError('')} className="opacity-60 hover:opacity-100">
            <X size={14} />
          </button>
        </div>
      )}

      {/* ------------------------------------------------ Search */}
      <div className={`${cardCls} p-4 shadow-sm space-y-3`}>
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
              placeholder={MODE_TABS.find((t) => t.id === mode)?.hint || 'Search...'}
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

      {/* ------------------------------------------------ Split layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 min-h-[520px]">
        {/* ---------- Left: customer list */}
        <div className={`lg:col-span-3 ${cardCls} overflow-hidden flex flex-col`}>
          <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500">Matched Customers</span>
            <span className="text-[11px] font-mono text-emerald-500">{customers.length}</span>
          </div>
          <div className="flex-1 overflow-y-auto max-h-[760px]">
            {loading && customers.length === 0 && (
              <div className="p-8 text-center text-slate-400 text-xs">
                <Loader2 className="animate-spin mx-auto mb-2" size={20} /> Searching...
              </div>
            )}
            {!loading && customers.length === 0 && (
              <div className="p-8 text-center text-slate-400 text-xs">No customers matched. Try a different mode or term.</div>
            )}
            {customers.map((c) => {
              const active = c.id === selectedCustId;
              return (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => {
                    setSelectedCustId(c.id);
                    setSelectedCardId(c.cards?.[0]?.id || '');
                  }}
                  className={`w-full text-left px-4 py-3 border-b border-slate-100 dark:border-slate-800/80 transition-colors flex items-center gap-3 ${
                    active
                      ? 'bg-emerald-500/10 border-l-2 border-l-emerald-500'
                      : 'hover:bg-slate-50 dark:hover:bg-slate-800/50 border-l-2 border-l-transparent'
                  }`}
                >
                  <div className="w-9 h-9 shrink-0 rounded-full bg-gradient-to-br from-emerald-500 to-sky-500 text-white text-xs font-bold flex items-center justify-center">
                    {initials(c)}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-[11px] font-bold text-emerald-500 truncate">{c.customer_number}</span>
                      <StatusPill value={c.customer_status} />
                    </div>
                    <div className="text-sm font-medium truncate">
                      {c.first_name} {c.last_name}
                    </div>
                    <div className="flex items-center gap-1.5 text-[10px] text-slate-400 font-mono">
                      <span className="text-sky-400">{c.institution_code || '—'}</span>·<span>{(c.cards || []).length} cards</span>·
                      <span>{(c.accounts || []).length} accts</span>
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* ---------- Right: detail workspace */}
        <div className="lg:col-span-9 space-y-4 min-w-0">
          {!selectedCust ? (
            <div className={`${cardCls} p-16 text-center text-slate-400 text-sm`}>
              Select a customer from the list, or search by PAN / account above.
            </div>
          ) : (
            <>
              {/* ===== Profile card */}
              <div className={`${cardCls} overflow-hidden`}>
                <div className="p-5 flex flex-wrap items-start justify-between gap-4 bg-gradient-to-r from-slate-50 to-transparent dark:from-slate-800/40">
                  <div className="flex items-start gap-4 min-w-0">
                    <div className="w-14 h-14 shrink-0 rounded-2xl bg-gradient-to-br from-emerald-500 via-teal-500 to-sky-500 text-white text-lg font-bold flex items-center justify-center shadow-lg shadow-emerald-500/20">
                      {initials(selectedCust)}
                    </div>
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h2 className="text-lg font-bold truncate">
                          {selectedCust.first_name} {selectedCust.last_name}
                        </h2>
                        <span className="font-mono text-xs text-emerald-500 bg-emerald-500/10 px-2 py-0.5 rounded-lg">
                          {selectedCust.customer_number}
                        </span>
                        <StatusPill value={selectedCust.customer_status} />
                        {selectedCust.kyc_status && (
                          <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full border border-sky-500/25 bg-sky-500/10 text-sky-500 font-bold">
                            <BadgeCheck size={11} /> KYC {selectedCust.kyc_status}
                          </span>
                        )}
                        <span className="text-[10px] px-2 py-0.5 rounded-full border border-slate-500/25 bg-slate-500/10 text-slate-400 font-bold">
                          RISK {selectedCust.risk_category || 'NORMAL'}
                        </span>
                      </div>
                      <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-500 dark:text-slate-300">
                        <span className="inline-flex items-center gap-1.5">
                          <Phone size={13} className="text-emerald-500" />
                          <span className="font-mono">{dash(selectedCust.mobile_number)}</span>
                        </span>
                        <span className="inline-flex items-center gap-1.5">
                          <Mail size={13} className="text-sky-500" />
                          <span className="font-mono">{dash(selectedCust.email)}</span>
                        </span>
                        <span className="inline-flex items-center gap-1.5">
                          <Landmark size={13} className="text-amber-500" />
                          <span className="font-mono text-sky-500 font-bold">{selectedCust.institution_code || '—'}</span>
                        </span>
                        {selectedCust.date_of_birth && (
                          <span className="inline-flex items-center gap-1.5">
                            <Calendar size={13} className="text-violet-500" />
                            {dateOnly(selectedCust.date_of_birth)}
                            {ageFrom(selectedCust.date_of_birth) !== null && (
                              <span className="text-slate-400">({ageFrom(selectedCust.date_of_birth)} yrs)</span>
                            )}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={openEditCustomer}
                      className="flex items-center gap-1.5 text-xs px-3.5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold shadow-md shadow-emerald-600/20"
                    >
                      <Edit3 size={13} /> Edit Customer
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        handleUpdateCustomer({
                          customer_status: selectedCust.customer_status === 'ACTIVE' ? 'BLOCKED' : 'ACTIVE',
                        })
                      }
                      className="flex items-center gap-1.5 text-xs px-3.5 py-2 rounded-xl border border-slate-300 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800"
                    >
                      {selectedCust.customer_status === 'ACTIVE' ? <Ban size={13} /> : <CheckCircle2 size={13} />}
                      {selectedCust.customer_status === 'ACTIVE' ? 'Block' : 'Activate'}
                    </button>
                  </div>
                </div>

                {/* KYC details (collapsible) */}
                <div className="border-t border-slate-200 dark:border-slate-800">
                  <button
                    type="button"
                    onClick={() => setShowKyc(!showKyc)}
                    className="w-full flex items-center gap-2 px-5 py-2.5 text-[11px] font-bold uppercase tracking-wider text-slate-500 hover:bg-slate-50 dark:hover:bg-slate-800/40"
                  >
                    <Fingerprint size={14} className="text-emerald-500" /> Personal &amp; KYC details
                    <ChevronDown size={14} className={`ml-auto transition-transform ${showKyc ? 'rotate-180' : ''}`} />
                  </button>
                  {showKyc && (
                    <div className="px-5 pb-5 pt-1 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-x-6 gap-y-3.5">
                      <Field label="Father's name" value={selectedCust.father_name} />
                      <Field label="Mother's name" value={selectedCust.mother_name} />
                      <Field label="Spouse name" value={selectedCust.spouse_name} />
                      <Field label="Gender" value={selectedCust.gender} />
                      <Field label="Date of birth" value={selectedCust.date_of_birth ? dateOnly(selectedCust.date_of_birth) : ''} />
                      <Field label="Place of birth" value={selectedCust.place_of_birth} />
                      <Field label="Marital status" value={selectedCust.marital_status} />
                      <Field label="Nationality" value={selectedCust.nationality} />
                      <Field label="NID number" value={selectedCust.nid_number} mono />
                      <Field label="Passport number" value={selectedCust.passport_number} mono />
                      <Field label="Passport expiry" value={selectedCust.passport_expiry_date ? dateOnly(selectedCust.passport_expiry_date) : ''} />
                      <Field label="Driving licence" value={selectedCust.driving_license_number} mono />
                      <Field label="TIN" value={selectedCust.tin_number} mono />
                      <Field label="Occupation" value={selectedCust.occupation} />
                      <Field label="Employer" value={selectedCust.employer_name} />
                      <Field label="Alternate mobile" value={selectedCust.alternate_mobile} mono />
                      <Field label="City / Postal code" value={[selectedCust.city, selectedCust.postal_code].filter(Boolean).join(' / ')} />
                      <Field label="Country" value={selectedCust.country} />
                      <Field label="Customer since" value={selectedCust.created_at ? dateOnly(selectedCust.created_at) : ''} />
                      <div className="col-span-2 sm:col-span-3 lg:col-span-2">
                        <div className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold flex items-center gap-1">
                          <MapPin size={10} /> Present address
                        </div>
                        <div className="text-xs mt-0.5">{dash(selectedCust.address)}</div>
                      </div>
                      <div className="col-span-2 sm:col-span-3 lg:col-span-2">
                        <div className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold flex items-center gap-1">
                          <MapPin size={10} /> Permanent address
                        </div>
                        <div className="text-xs mt-0.5">{dash(selectedCust.permanent_address)}</div>
                      </div>
                      {selectedCust.notes && <Field label="Notes" value={selectedCust.notes} wide />}
                    </div>
                  )}
                </div>
              </div>

              {/* ===== Card rail */}
              <div className={`${cardCls} p-4`}>
                <div className="flex items-center gap-2 mb-3">
                  <CreditCard size={16} className="text-sky-500" />
                  <h3 className="text-sm font-bold">Cards</h3>
                  <span className="text-[11px] font-mono text-slate-400">{(selectedCust.cards || []).length}</span>
                  <span className="text-[10px] text-slate-400 ml-2">select a card to see its details, limits and transactions</span>
                </div>
                {(selectedCust.cards || []).length === 0 ? (
                  <div className="p-4 text-xs text-slate-400 text-center">This customer has no cards.</div>
                ) : (
                  <div className="flex gap-3 overflow-x-auto pb-1">
                    {(selectedCust.cards || []).map((card: any) => {
                      const active = selectedCard?.id === card.id;
                      const expired = isExpired(card);
                      const inactive = card.card_status !== 'ACTIVE';
                      return (
                        <button
                          key={card.id}
                          type="button"
                          onClick={() => setSelectedCardId(card.id)}
                          className={`relative shrink-0 w-64 text-left rounded-2xl p-4 text-white transition-all border-2 ${
                            active ? 'border-emerald-400 shadow-xl shadow-emerald-500/20 scale-[1.02]' : 'border-transparent opacity-80 hover:opacity-100'
                          } ${
                            inactive
                              ? 'bg-gradient-to-br from-slate-600 to-slate-800'
                              : 'bg-gradient-to-br from-slate-800 via-slate-900 to-emerald-900'
                          }`}
                        >
                          <div className="flex items-center justify-between text-[10px] uppercase tracking-widest text-white/60">
                            <span>{card.card_product || card.card_type}</span>
                            <span className="font-mono">{card.institution_code || ''}</span>
                          </div>
                          <div className="mt-4 font-mono text-base tracking-widest">{card.masked_pan}</div>
                          <div className="mt-3 flex items-end justify-between">
                            <div className="min-w-0">
                              <div className="text-[9px] uppercase text-white/50">Cardholder</div>
                              <div className="text-[11px] font-semibold truncate max-w-[130px]">{card.cardholder_name}</div>
                            </div>
                            <div className="text-right">
                              <div className="text-[9px] uppercase text-white/50">Expires</div>
                              <div className={`text-[11px] font-mono font-bold ${expired ? 'text-rose-300' : ''}`}>{expiryText(card)}</div>
                            </div>
                          </div>
                          <div className="absolute top-3 right-3">
                            {inactive || expired ? (
                              <span className="text-[9px] px-1.5 py-0.5 rounded bg-rose-500/80 font-bold">
                                {expired && !inactive ? 'EXPIRED' : card.card_status}
                              </span>
                            ) : null}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* ===== Tabs */}
              <div className={`${cardCls} overflow-hidden`}>
                <div className="flex flex-wrap gap-1 p-2 border-b border-slate-200 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-950/30">
                  {DETAIL_TABS.map((t) => (
                    <button
                      key={t.id}
                      type="button"
                      onClick={() => setTab(t.id)}
                      className={`flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold transition-all ${
                        tab === t.id
                          ? 'bg-white dark:bg-slate-800 text-emerald-500 shadow-sm'
                          : 'text-slate-500 hover:text-slate-300'
                      }`}
                    >
                      {t.icon}
                      {t.label}
                    </button>
                  ))}
                  {selectedCard && (
                    <span className="ml-auto self-center text-[11px] font-mono text-slate-400 pr-2">
                      card <span className="text-sky-400 font-bold">{selectedCard.masked_pan}</span>
                    </span>
                  )}
                </div>

                {/* ================= TAB: CARDS */}
                {tab === 'cards' && (
                  <div className="p-5 space-y-4">
                    {!selectedCard ? (
                      <div className="text-xs text-slate-400 text-center py-6">No card selected.</div>
                    ) : (
                      <>
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="font-mono text-base font-bold text-sky-400">{selectedCard.masked_pan}</span>
                              <StatusPill value={selectedCard.card_status} />
                              {isExpired(selectedCard) && (
                                <span className="text-[10px] px-2 py-0.5 rounded-full bg-rose-500/15 text-rose-500 border border-rose-500/25 font-bold">
                                  EXPIRED
                                </span>
                              )}
                            </div>
                            <div className="text-[11px] text-slate-400 font-mono mt-1">
                              Ref {selectedCard.test_pan_reference} · {selectedCard.cardholder_name} · Exp {expiryText(selectedCard)} ·{' '}
                              {selectedCard.card_product}
                            </div>
                            {selectedCard.pin_profile && (
                              <div className="text-[11px] text-amber-500/90 font-mono mt-1">
                                {selectedCard.pin_profile.verification_method} · PVV/Offset{' '}
                                {selectedCard.pin_profile.pin_offset_reference} · CVV {selectedCard.pin_profile.cvv_reference || '—'} · PIN tries{' '}
                                {selectedCard.pin_profile.retry_counter}/{selectedCard.pin_profile.maximum_retry_count}
                              </div>
                            )}
                          </div>
                          <div className="flex flex-wrap gap-1.5">
                            <button
                              type="button"
                              onClick={() => openEditCard(selectedCard)}
                              className="flex items-center gap-1 text-[11px] px-2.5 py-1.5 rounded-lg bg-emerald-600/10 text-emerald-500 hover:bg-emerald-600/20"
                            >
                              <Edit3 size={12} /> Edit / Expiry
                            </button>
                            <button
                              type="button"
                              onClick={() => toggleCardStatus(selectedCard)}
                              className="flex items-center gap-1 text-[11px] px-2.5 py-1.5 rounded-lg bg-slate-500/10 text-slate-400 hover:bg-slate-500/20"
                            >
                              {selectedCard.card_status === 'ACTIVE' ? <Ban size={12} /> : <CheckCircle2 size={12} />}
                              {selectedCard.card_status === 'ACTIVE' ? 'Block' : 'Activate'}
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                setPinModalCard(selectedCard);
                                setNewPin('1234');
                              }}
                              className="flex items-center gap-1 text-[11px] px-2.5 py-1.5 rounded-lg bg-violet-600/10 text-violet-400 hover:bg-violet-600/20"
                            >
                              <KeyRound size={12} /> PIN
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                setLinkModalCard(selectedCard);
                                setTargetAccountId(allAccounts[0]?.id || '');
                                setLinkRole('SECONDARY');
                              }}
                              className="flex items-center gap-1 text-[11px] px-2.5 py-1.5 rounded-lg bg-sky-600/10 text-sky-400 hover:bg-sky-600/20"
                            >
                              <LinkIcon size={12} /> Link Acct
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                setReassignModalCard(selectedCard);
                                setReassignCustId(allCustomers[0]?.id || '');
                              }}
                              className="flex items-center gap-1 text-[11px] px-2.5 py-1.5 rounded-lg bg-amber-600/10 text-amber-500 hover:bg-amber-600/20"
                            >
                              <ArrowRightLeft size={12} /> Reassign
                            </button>
                            <button
                              type="button"
                              onClick={() => handleDeleteCard(selectedCard)}
                              className="flex items-center gap-1 text-[11px] px-2.5 py-1.5 rounded-lg bg-rose-600/10 text-rose-400 hover:bg-rose-600/20"
                            >
                              <Trash2 size={12} />
                            </button>
                          </div>
                        </div>

                        <div className="space-y-1.5">
                          <div className="text-[10px] uppercase tracking-wide text-slate-500 font-bold">Linked Accounts</div>
                          {(selectedCard.card_accounts || []).length === 0 && (
                            <div className="text-[11px] text-slate-500 italic">No linked accounts</div>
                          )}
                          {(selectedCard.card_accounts || []).map((lnk: any) => (
                            <div
                              key={lnk.id}
                              className="flex flex-wrap items-center justify-between gap-2 px-3 py-2.5 rounded-xl bg-slate-50 dark:bg-slate-950/60 border border-slate-200 dark:border-slate-800 text-xs font-mono"
                            >
                              <div className="flex flex-wrap items-center gap-2">
                                <ChevronRight size={12} className="text-slate-500" />
                                <span className="font-bold text-emerald-500">{lnk.account_number}</span>
                                <span className="text-slate-400">{lnk.account_type}</span>
                                <span
                                  className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${
                                    lnk.account_role === 'PRIMARY' ? 'bg-emerald-500/15 text-emerald-500' : 'bg-slate-500/15 text-slate-400'
                                  }`}
                                >
                                  {lnk.account_role}
                                </span>
                                <span className="text-slate-400">
                                  Avl <span className="text-slate-200 font-bold">{num(lnk.available_balance)}</span> {lnk.currency}
                                </span>
                              </div>
                              <div className="flex gap-2">
                                {lnk.account_role !== 'PRIMARY' && (
                                  <button
                                    type="button"
                                    onClick={() => handleSetPrimary(lnk.id, lnk.account_number)}
                                    className="text-[10px] text-emerald-500 hover:underline"
                                  >
                                    Make Primary
                                  </button>
                                )}
                                <button
                                  type="button"
                                  onClick={() => handleUnlink(lnk.id, lnk.account_number, selectedCard.masked_pan)}
                                  className="text-[10px] text-rose-400 hover:underline flex items-center gap-0.5"
                                >
                                  <Unlink size={10} /> Unlink
                                </button>
                              </div>
                            </div>
                          ))}
                        </div>

                        <button
                          type="button"
                          onClick={() => setTab('limits')}
                          className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl border border-dashed border-emerald-500/40 text-emerald-500 text-xs font-semibold hover:bg-emerald-500/5"
                        >
                          <Gauge size={14} /> View limits &amp; usage for this card
                        </button>
                      </>
                    )}
                  </div>
                )}

                {/* ================= TAB: LIMITS */}
                {tab === 'limits' && (
                  <div className="p-5 space-y-4">
                    {!selectedCard ? (
                      <div className="text-xs text-slate-400 text-center py-6">Select a card to see its limits.</div>
                    ) : (
                      <>
                        <div className="flex flex-wrap items-center gap-2">
                          <div className="flex items-start gap-2 text-[11px] text-slate-400 flex-1 min-w-[260px]">
                            <Info size={14} className="text-sky-500 shrink-0 mt-0.5" />
                            <span>
                              Both layers are checked during authorization: the per-card and per-account limits below, and the limits
                              of the card&apos;s Authorization Profile. Usage is the running total for the current window.
                            </span>
                          </div>
                          <button
                            type="button"
                            onClick={() => loadLimits(selectedCard.id)}
                            className="flex items-center gap-1 text-[11px] px-3 py-1.5 rounded-lg border border-slate-300 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800"
                          >
                            <RefreshCw size={12} className={limitsLoading ? 'animate-spin' : ''} /> Refresh
                          </button>
                          <button
                            type="button"
                            onClick={() =>
                              askReset(
                                'Reset ALL usage',
                                `Sets every used counter (card, linked accounts and profile limits) of ${selectedCard.masked_pan} back to zero.`,
                                { target: 'ALL', period: 'ALL' }
                              )
                            }
                            className="flex items-center gap-1 text-[11px] px-3 py-1.5 rounded-lg bg-rose-500/10 text-rose-500 hover:bg-rose-500/20 font-semibold"
                          >
                            <RotateCcw size={12} /> Reset ALL usage
                          </button>
                        </div>

                        {limitsError && (
                          <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-500 text-xs font-mono">{limitsError}</div>
                        )}
                        {limitsLoading && !limitsData && (
                          <div className="p-8 text-center text-slate-400 text-xs">
                            <Loader2 className="animate-spin mx-auto mb-2" size={20} /> Loading limits...
                          </div>
                        )}

                        {limitsData && (
                          <>
                            {/* Card limits */}
                            <div className="rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden">
                              <SectionHead
                                icon={<CreditCard size={16} />}
                                title="Card limits"
                                sub={`${selectedCard.masked_pan} · ${legacyCard?.currency || 'BDT'} · status ${legacyCard?.status}`}
                                right={
                                  <button
                                    type="button"
                                    onClick={() =>
                                      askReset('Reset card usage', `Sets daily, weekly and monthly used counters of ${selectedCard.masked_pan} back to zero.`, {
                                        target: 'LEGACY',
                                        period: 'ALL',
                                        include_card: true,
                                        include_accounts: false,
                                      })
                                    }
                                    className="flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-lg bg-amber-500/10 text-amber-500 hover:bg-amber-500/20"
                                  >
                                    <RotateCcw size={12} /> Reset card usage
                                  </button>
                                }
                              />
                              {(legacyCard?.rows || []).map((r: any) => (
                                <LimitRow key={r.row_id} row={r} onEdit={openLimitEdit} onReset={askResetRow} />
                              ))}
                            </div>

                            {/* Account limits */}
                            {legacyAccounts.length === 0 && (
                              <div className="text-[11px] text-slate-400 italic">No account is linked to this card, so there are no account limits.</div>
                            )}
                            {legacyAccounts.map((acc: any) => (
                              <div key={acc.account_id} className="rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden">
                                <SectionHead
                                  icon={<Landmark size={16} />}
                                  title={`Account limits - ${acc.account_number}`}
                                  sub={`${acc.account_type} · ${acc.account_role} · ${acc.currency} · status ${acc.status}`}
                                  right={
                                    <button
                                      type="button"
                                      onClick={() =>
                                        askReset('Reset account usage', `Sets daily, weekly and monthly used counters of account ${acc.account_number} back to zero.`, {
                                          target: 'LEGACY',
                                          period: 'ALL',
                                          include_card: false,
                                          include_accounts: true,
                                          account_id: acc.account_id,
                                        })
                                      }
                                      className="flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-lg bg-amber-500/10 text-amber-500 hover:bg-amber-500/20"
                                    >
                                      <RotateCcw size={12} /> Reset account usage
                                    </button>
                                  }
                                />
                                {(acc.rows || []).map((r: any) => (
                                  <LimitRow key={r.row_id} row={r} onEdit={openLimitEdit} onReset={askResetRow} />
                                ))}
                              </div>
                            ))}

                            {/* Profile limits */}
                            <div className="rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden">
                              <SectionHead
                                icon={<ShieldCheck size={16} />}
                                title="Authorization Profile limits"
                                sub={
                                  profileInfo?.auth_profile_code
                                    ? `${profileInfo.auth_profile_code} · card profile ${profileInfo.card_profile_code || '—'} · BIN ${profileInfo.bin_prefix || '—'}`
                                    : `card profile ${profileInfo?.card_profile_code || '—'} · BIN ${profileInfo?.bin_prefix || '—'}`
                                }
                                right={
                                  profileRows.length > 0 ? (
                                    <button
                                      type="button"
                                      onClick={() =>
                                        askReset('Reset profile limit usage', `Clears running usage of all profile limits for ${selectedCard.masked_pan} and its linked accounts.`, {
                                          target: 'PROFILE',
                                        })
                                      }
                                      className="flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-lg bg-amber-500/10 text-amber-500 hover:bg-amber-500/20"
                                    >
                                      <RotateCcw size={12} /> Reset profile usage
                                    </button>
                                  ) : undefined
                                }
                              />
                              {profileRows.length === 0 ? (
                                <div className="px-4 py-5 text-[11px] text-slate-400 italic">
                                  {profileInfo?.note || 'No profile limits apply to this card.'}
                                </div>
                              ) : (
                                profileRows.map((r: any) => (
                                  <LimitRow key={r.row_id} row={{ ...r, name: `${r.name}${r.scope === 'ACCOUNT' ? ` (${r.target_label})` : ''}` }} onEdit={openLimitEdit} onReset={askResetRow} />
                                ))
                              )}
                            </div>
                          </>
                        )}
                      </>
                    )}
                  </div>
                )}

                {/* ================= TAB: TRANSACTIONS */}
                {tab === 'transactions' && (
                  <div className="p-5 space-y-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <select
                        value={txScope}
                        onChange={(e) => setTxScope(e.target.value)}
                        className={`${inputCls} !w-auto min-w-[220px] font-mono`}
                      >
                        {selectedCard && <option value="card">Card {selectedCard.masked_pan}</option>}
                        <option value="customer">All activity of this customer</option>
                        {(selectedCust.accounts || []).map((a: any) => (
                          <option key={a.id} value={`acct:${a.id}`}>
                            Account {a.account_number}
                          </option>
                        ))}
                      </select>
                      <select
                        value={txCount}
                        onChange={(e) => setTxCount(Number(e.target.value))}
                        className={`${inputCls} !w-auto font-mono`}
                      >
                        {[10, 20, 50, 100].map((n) => (
                          <option key={n} value={n}>
                            last {n}
                          </option>
                        ))}
                      </select>
                      <button
                        type="button"
                        onClick={() => loadTransactions(txScope === 'card' && !selectedCard ? 'customer' : txScope, txCount, selectedCard?.id || '', selectedCust.id)}
                        className="flex items-center gap-1 text-[11px] px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800"
                      >
                        <RefreshCw size={12} className={txLoading ? 'animate-spin' : ''} /> Refresh
                      </button>
                      {txData && (
                        <span className="ml-auto text-[11px] font-mono text-slate-400">
                          showing {txData.returned} of {txData.total}
                        </span>
                      )}
                    </div>

                    {txError && (
                      <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-500 text-xs font-mono">{txError}</div>
                    )}
                    {txLoading && !txData && (
                      <div className="p-8 text-center text-slate-400 text-xs">
                        <Loader2 className="animate-spin mx-auto mb-2" size={20} /> Loading transactions...
                      </div>
                    )}

                    {txData && (
                      <>
                        <div className="grid grid-cols-3 gap-3">
                          <div className="rounded-xl p-3 bg-emerald-500/10 border border-emerald-500/20">
                            <div className="text-[10px] uppercase tracking-wider text-emerald-500 font-bold">Approved</div>
                            <div className="text-xl font-bold font-mono text-emerald-500">{txData.summary.approved}</div>
                          </div>
                          <div className="rounded-xl p-3 bg-rose-500/10 border border-rose-500/20">
                            <div className="text-[10px] uppercase tracking-wider text-rose-500 font-bold">Declined</div>
                            <div className="text-xl font-bold font-mono text-rose-500">{txData.summary.declined}</div>
                          </div>
                          <div className="rounded-xl p-3 bg-sky-500/10 border border-sky-500/20">
                            <div className="text-[10px] uppercase tracking-wider text-sky-500 font-bold">Approved amount</div>
                            <div className="text-xl font-bold font-mono text-sky-500">{num(txData.summary.approved_amount)}</div>
                          </div>
                        </div>

                        {txData.items.length === 0 ? (
                          <div className="p-8 text-center text-slate-400 text-xs">No transactions found for this selection.</div>
                        ) : (
                          <div className="rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden">
                            <div className="hidden md:grid grid-cols-12 gap-2 px-4 py-2 text-[10px] uppercase tracking-wider font-bold text-slate-400 bg-slate-50 dark:bg-slate-950/50">
                              <div className="col-span-3">Date / time</div>
                              <div className="col-span-3">Transaction</div>
                              <div className="col-span-2 text-right">Amount</div>
                              <div className="col-span-2">Response</div>
                              <div className="col-span-2">Channel / terminal</div>
                            </div>
                            {txData.items.map((t: any) => {
                              const open = txOpen === t.id;
                              return (
                                <div key={t.id} className="border-t border-slate-100 dark:border-slate-800/80">
                                  <button
                                    type="button"
                                    onClick={() => setTxOpen(open ? '' : t.id)}
                                    className="w-full grid grid-cols-12 gap-2 px-4 py-2.5 text-left items-center hover:bg-slate-50/70 dark:hover:bg-slate-800/30"
                                  >
                                    <div className="col-span-6 md:col-span-3 text-[11px] font-mono text-slate-400">{dateTime(t.datetime)}</div>
                                    <div className="col-span-6 md:col-span-3 min-w-0">
                                      <div className="text-xs font-semibold truncate">{t.type_name || `Code ${t.transaction_code || '—'}`}</div>
                                      <div className="text-[10px] font-mono text-slate-400">MTI {t.mti} · {t.transaction_code || '—'}</div>
                                    </div>
                                    <div className="col-span-4 md:col-span-2 text-right font-mono font-bold text-xs tabular-nums">
                                      {num(t.amount)} <span className="text-slate-400 font-normal">{t.currency}</span>
                                    </div>
                                    <div className="col-span-4 md:col-span-2">
                                      <span
                                        className={`inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full border font-bold ${
                                          t.approved
                                            ? 'bg-emerald-500/15 text-emerald-500 border-emerald-500/25'
                                            : 'bg-rose-500/15 text-rose-500 border-rose-500/25'
                                        }`}
                                      >
                                        {t.response_code} {t.approved ? 'OK' : 'DECLINED'}
                                      </span>
                                    </div>
                                    <div className="col-span-4 md:col-span-2 flex items-center justify-between gap-1 min-w-0">
                                      <div className="min-w-0">
                                        <div className="text-[11px] truncate">{t.channel}</div>
                                        <div className="text-[10px] font-mono text-slate-400 truncate">{t.terminal_id || t.merchant_name || '—'}</div>
                                      </div>
                                      <ChevronDown size={14} className={`shrink-0 text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`} />
                                    </div>
                                  </button>
                                  {open && (
                                    <div className="px-4 pb-4 pt-1 grid grid-cols-2 md:grid-cols-4 gap-x-6 gap-y-3 bg-slate-50/60 dark:bg-slate-950/40">
                                      <Field label="Reference" value={t.reference} mono />
                                      <Field label="RRN" value={t.rrn} mono />
                                      <Field label="STAN" value={t.stan} mono />
                                      <Field label="Approval code" value={t.approval_code} mono />
                                      <Field label="PAN" value={t.masked_pan} mono />
                                      <Field label="Source account" value={t.source_account} mono />
                                      <Field label="Merchant" value={[t.merchant_name, t.merchant_id].filter(Boolean).join(' · ')} />
                                      <Field label="On-us" value={t.is_on_us ? 'Yes' : 'No'} />
                                      <Field label="Response" value={t.response_message} wide />
                                      {t.decline_reason && <Field label="Decline reason" value={t.decline_reason} wide />}
                                    </div>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </>
                    )}
                  </div>
                )}

                {/* ================= TAB: ACCOUNTS */}
                {tab === 'accounts' && (
                  <div className="p-5 space-y-4">
                    {(selectedCust.accounts || []).length === 0 && (
                      <div className="p-6 text-xs text-slate-400 text-center">No accounts</div>
                    )}
                    {(selectedCust.accounts || []).map((a: any) => {
                      const rows = accountLimitRows(a);
                      return (
                        <div key={a.id} className="rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden">
                          <div className="px-4 py-3.5 flex flex-wrap items-center justify-between gap-3">
                            <div className="flex items-center gap-3">
                              <div className="w-9 h-9 rounded-xl bg-amber-500/10 text-amber-500 flex items-center justify-center">
                                <Wallet size={18} />
                              </div>
                              <div>
                                <div className="font-mono text-sm font-bold text-emerald-500">{a.account_number}</div>
                                <div className="text-[11px] text-slate-400 font-mono mt-0.5 flex items-center gap-2">
                                  {a.account_type} <StatusPill value={a.account_status} /> OD {num(a.overdraft_limit || 0)}
                                </div>
                              </div>
                            </div>
                            <div className="text-right">
                              <div className="text-sm font-bold font-mono tabular-nums">
                                {num(a.available_balance)} <span className="text-slate-400 text-xs">{a.currency}</span>
                              </div>
                              <div className="text-[11px] text-slate-400 font-mono">Ledger {num(a.ledger_balance)}</div>
                            </div>
                            <div className="flex items-center gap-1.5">
                              <button
                                type="button"
                                onClick={() => setEditAccountModal({ ...a })}
                                className="flex items-center gap-1 text-[11px] px-2.5 py-1.5 rounded-lg bg-emerald-600/10 text-emerald-500 hover:bg-emerald-600/20"
                              >
                                <Edit3 size={12} /> Balance
                              </button>
                              <button
                                type="button"
                                onClick={() => handleDeleteAccount(a)}
                                className="flex items-center gap-1 text-[11px] px-2.5 py-1.5 rounded-lg bg-rose-600/10 text-rose-400 hover:bg-rose-600/20"
                              >
                                <Trash2 size={12} />
                              </button>
                            </div>
                          </div>
                          {rows.length > 0 && (
                            <div className="border-t border-slate-100 dark:border-slate-800/80">
                              <div className="px-4 py-2 text-[10px] uppercase tracking-wider font-bold text-slate-400 bg-slate-50/70 dark:bg-slate-950/40 flex items-center gap-1.5">
                                <Gauge size={12} className="text-emerald-500" /> Account limits
                              </div>
                              {rows.map((r: any) => (
                                <LimitRow key={r.row_id} row={r} onEdit={openLimitEdit} onReset={askResetAccountRow} />
                              ))}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      {/* ======================================================== MODALS */}

      {/* Edit customer (all fields) */}
      {editCustomer && (
        <Modal title={`Edit customer ${selectedCust?.customer_number || ''}`} onClose={() => setEditCustomer(null)} wide>
          <form onSubmit={saveCustomer} className="space-y-5">
            {(() => {
              const set = (k: string) => (v: string) => setEditCustomer({ ...editCustomer, [k]: v });
              const sel = (k: string, opts: string[]) => (
                <select value={editCustomer[k] ?? ''} onChange={(e) => set(k)(e.target.value)} className={inputCls}>
                  {opts.map((o) => (
                    <option key={o} value={o}>
                      {o || '—'}
                    </option>
                  ))}
                </select>
              );
              return (
                <>
                  <div>
                    <div className="text-[11px] font-bold uppercase tracking-wider text-emerald-500 mb-2">Identity</div>
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                      <LabeledInput label="First name *" value={editCustomer.first_name} onChange={set('first_name')} />
                      <LabeledInput label="Last name" value={editCustomer.last_name} onChange={set('last_name')} />
                      <LabeledInput label="Date of birth" type="date" value={editCustomer.date_of_birth} onChange={set('date_of_birth')} />
                      <LabeledInput label="Gender" value="" onChange={() => {}}>{sel('gender', GENDERS)}</LabeledInput>
                      <LabeledInput label="Marital status" value="" onChange={() => {}}>{sel('marital_status', MARITAL)}</LabeledInput>
                      <LabeledInput label="Nationality" value={editCustomer.nationality} onChange={set('nationality')} />
                      <LabeledInput label="Father's name" value={editCustomer.father_name} onChange={set('father_name')} />
                      <LabeledInput label="Mother's name" value={editCustomer.mother_name} onChange={set('mother_name')} />
                      <LabeledInput label="Spouse name" value={editCustomer.spouse_name} onChange={set('spouse_name')} />
                      <LabeledInput label="Place of birth" value={editCustomer.place_of_birth} onChange={set('place_of_birth')} />
                      <LabeledInput label="Occupation" value={editCustomer.occupation} onChange={set('occupation')} />
                      <LabeledInput label="Employer" value={editCustomer.employer_name} onChange={set('employer_name')} />
                    </div>
                  </div>
                  <div>
                    <div className="text-[11px] font-bold uppercase tracking-wider text-sky-500 mb-2">Contact</div>
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                      <LabeledInput label="Mobile" value={editCustomer.mobile_number} onChange={set('mobile_number')} />
                      <LabeledInput label="Alternate mobile" value={editCustomer.alternate_mobile} onChange={set('alternate_mobile')} />
                      <LabeledInput label="Email" value={editCustomer.email} onChange={set('email')} />
                      <LabeledInput label="Present address" value={editCustomer.address} onChange={set('address')} span={2} />
                      <LabeledInput label="City" value={editCustomer.city} onChange={set('city')} />
                      <LabeledInput label="Permanent address" value={editCustomer.permanent_address} onChange={set('permanent_address')} span={2} />
                      <LabeledInput label="Postal code" value={editCustomer.postal_code} onChange={set('postal_code')} />
                      <LabeledInput label="Country" value={editCustomer.country} onChange={set('country')} />
                    </div>
                  </div>
                  <div>
                    <div className="text-[11px] font-bold uppercase tracking-wider text-amber-500 mb-2">Documents &amp; KYC</div>
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                      <LabeledInput label="NID number" value={editCustomer.nid_number} onChange={set('nid_number')} />
                      <LabeledInput label="Passport number" value={editCustomer.passport_number} onChange={set('passport_number')} />
                      <LabeledInput label="Passport expiry" type="date" value={editCustomer.passport_expiry_date} onChange={set('passport_expiry_date')} />
                      <LabeledInput label="Driving licence" value={editCustomer.driving_license_number} onChange={set('driving_license_number')} />
                      <LabeledInput label="TIN" value={editCustomer.tin_number} onChange={set('tin_number')} />
                      <LabeledInput label="KYC status" value="" onChange={() => {}}>{sel('kyc_status', KYC)}</LabeledInput>
                      <LabeledInput label="Risk category" value="" onChange={() => {}}>{sel('risk_category', ['NORMAL', 'VIP', 'HIGH'])}</LabeledInput>
                      <LabeledInput label="Customer status" value="" onChange={() => {}}>{sel('customer_status', ['ACTIVE', 'BLOCKED', 'CLOSED'])}</LabeledInput>
                    </div>
                  </div>
                  <LabeledInput label="Notes" value="" onChange={() => {}}>
                    <textarea
                      value={editCustomer.notes ?? ''}
                      onChange={(e) => set('notes')(e.target.value)}
                      rows={2}
                      className={inputCls}
                    />
                  </LabeledInput>
                </>
              );
            })()}
            <div className="flex justify-end gap-2 pt-3 border-t border-slate-200 dark:border-slate-800">
              <button type="button" onClick={() => setEditCustomer(null)} className="px-4 py-2 text-xs rounded-lg">
                Cancel
              </button>
              <button
                type="submit"
                disabled={busy}
                className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white px-5 py-2 rounded-lg text-xs font-semibold"
              >
                {busy ? 'Saving...' : 'Save customer'}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {/* Edit card */}
      {editCard && (
        <Modal title={`Edit card ${editCard.masked_pan}`} onClose={() => setEditCard(null)}>
          <form onSubmit={saveCard} className="space-y-4 text-xs">
            <LabeledInput label="Cardholder name" value={editCard.cardholder_name} onChange={(v) => setEditCard({ ...editCard, cardholder_name: v })} />
            <div>
              <div className="text-[11px] text-slate-400 font-medium mb-1">Expiry date (MM / YYYY)</div>
              <div className="flex gap-2">
                <select
                  value={editCard.expiry_month}
                  onChange={(e) => setEditCard({ ...editCard, expiry_month: Number(e.target.value) })}
                  className={`${inputCls} font-mono`}
                >
                  {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                    <option key={m} value={m}>
                      {String(m).padStart(2, '0')}
                    </option>
                  ))}
                </select>
                <input
                  type="number"
                  min={2000}
                  max={2099}
                  value={editCard.expiry_year}
                  onChange={(e) => setEditCard({ ...editCard, expiry_year: e.target.value })}
                  className={`${inputCls} font-mono`}
                />
              </div>
              <div className="flex flex-wrap gap-1.5 mt-2">
                <button type="button" onClick={() => expiryPreset('plus1')} className="px-2.5 py-1 rounded-lg bg-slate-500/10 text-slate-400 hover:bg-slate-500/20 text-[11px]">
                  +1 year
                </button>
                <button type="button" onClick={() => expiryPreset('plus3')} className="px-2.5 py-1 rounded-lg bg-slate-500/10 text-slate-400 hover:bg-slate-500/20 text-[11px]">
                  +3 years
                </button>
                <button type="button" onClick={() => expiryPreset('expired')} className="px-2.5 py-1 rounded-lg bg-rose-500/10 text-rose-400 hover:bg-rose-500/20 text-[11px]">
                  Make expired (test decline)
                </button>
              </div>
              <p className="text-[10px] text-slate-500 mt-2">
                The CVV depends on the expiry, so it is recalculated automatically when the expiry changes.
              </p>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <LabeledInput label="Status" value="" onChange={() => {}}>
                <select value={editCard.card_status} onChange={(e) => setEditCard({ ...editCard, card_status: e.target.value })} className={inputCls}>
                  {CARD_STATUSES.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </LabeledInput>
              <LabeledInput label="Card type" value={editCard.card_type} onChange={(v) => setEditCard({ ...editCard, card_type: v })} />
              <LabeledInput label="Card product" value={editCard.card_product} onChange={(v) => setEditCard({ ...editCard, card_product: v })} span={2} />
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t border-slate-200 dark:border-slate-800">
              <button type="button" onClick={() => setEditCard(null)} className="px-4 py-2 text-xs rounded-lg">
                Cancel
              </button>
              <button type="submit" disabled={busy} className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white px-5 py-2 rounded-lg text-xs font-semibold">
                {busy ? 'Saving...' : 'Save card'}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {/* Edit limit maximum */}
      {limitEdit && (
        <Modal title={`Edit limit: ${limitEdit.row.name}`} onClose={() => setLimitEdit(null)}>
          <form onSubmit={(e) => saveLimitEdit(e, false)} className="space-y-4 text-xs">
            <div className="text-[11px] text-slate-400 font-mono">
              {limitEdit.row.source === 'PROFILE' ? 'Authorization Profile limit' : limitEdit.row.scope === 'CARD' ? 'Card limit' : 'Account limit'} ·{' '}
              {limitEdit.row.target_label} · {limitEdit.row.period}
            </div>
            <LabeledInput label={`Maximum ${limitEdit.row.unit === 'COUNT' ? '(transactions)' : `(${limitEdit.row.currency || 'amount'})`}`} value="" onChange={() => {}}>
              <input
                type="number"
                min={0}
                step="0.01"
                value={limitEdit.value}
                onChange={(e) => setLimitEdit({ ...limitEdit, value: e.target.value })}
                className={`${inputCls} font-mono text-sm`}
                autoFocus
              />
            </LabeledInput>
            {limitEdit.row.source === 'PROFILE' ? (
              <div className="flex items-start gap-2 p-3 rounded-xl bg-amber-500/10 border border-amber-500/25 text-amber-500 text-[11px]">
                <Info size={14} className="shrink-0 mt-0.5" />
                This changes the maximum for every card that uses the same Authorization Profile, not just this card.
              </div>
            ) : (
              <p className="text-[10px] text-slate-500">Only the maximum changes; the usage counter stays as it is. Use Reset to clear usage.</p>
            )}
            <div className="flex flex-wrap justify-between gap-2 pt-2 border-t border-slate-200 dark:border-slate-800">
              <div>
                {limitEdit.row.source === 'PROFILE' && limitEdit.row.override_active && (
                  <button
                    type="button"
                    onClick={(e) => saveLimitEdit(e as any, true)}
                    className="px-3 py-2 text-[11px] rounded-lg bg-violet-500/10 text-violet-400 hover:bg-violet-500/20"
                  >
                    Remove override
                  </button>
                )}
              </div>
              <div className="flex gap-2">
                <button type="button" onClick={() => setLimitEdit(null)} className="px-4 py-2 text-xs rounded-lg">
                  Cancel
                </button>
                <button type="submit" disabled={busy} className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white px-5 py-2 rounded-lg text-xs font-semibold">
                  {busy ? 'Saving...' : 'Save maximum'}
                </button>
              </div>
            </div>
          </form>
        </Modal>
      )}

      {/* Confirm reset */}
      {resetModal && (
        <Modal title={resetModal.title} onClose={() => setResetModal(null)}>
          <form onSubmit={runReset} className="space-y-4 text-xs">
            <p className="text-slate-400">{resetModal.text}</p>
            <LabeledInput label="Reason / test reference (recorded in the audit trail)" value={resetReason} onChange={setResetReason} />
            <div className="flex justify-end gap-2 pt-2 border-t border-slate-200 dark:border-slate-800">
              <button type="button" onClick={() => setResetModal(null)} className="px-4 py-2 text-xs rounded-lg">
                Cancel
              </button>
              <button
                type="submit"
                disabled={busy || resetReason.trim().length < 3}
                className="bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-white px-5 py-2 rounded-lg text-xs font-semibold flex items-center gap-1"
              >
                <RotateCcw size={13} /> {busy ? 'Resetting...' : 'Reset usage'}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {/* Edit Account Balance */}
      {editAccountModal && (
        <Modal title={`Edit account ${editAccountModal.account_number}`} onClose={() => setEditAccountModal(null)}>
          <form onSubmit={handleSaveAccountEdit} className="space-y-4">
            <div className="grid grid-cols-2 gap-3 text-xs font-mono">
              <LabeledInput label="Available balance" value="" onChange={() => {}}>
                <input type="number" step="0.01" value={editAccountModal.available_balance} onChange={(e) => setEditAccountModal({ ...editAccountModal, available_balance: e.target.value })} className={inputCls} />
              </LabeledInput>
              <LabeledInput label="Ledger balance" value="" onChange={() => {}}>
                <input type="number" step="0.01" value={editAccountModal.ledger_balance} onChange={(e) => setEditAccountModal({ ...editAccountModal, ledger_balance: e.target.value })} className={inputCls} />
              </LabeledInput>
              <LabeledInput label="Overdraft limit" value="" onChange={() => {}}>
                <input type="number" step="0.01" value={editAccountModal.overdraft_limit || 0} onChange={(e) => setEditAccountModal({ ...editAccountModal, overdraft_limit: e.target.value })} className={inputCls} />
              </LabeledInput>
              <LabeledInput label="Status" value="" onChange={() => {}}>
                <select value={editAccountModal.account_status} onChange={(e) => setEditAccountModal({ ...editAccountModal, account_status: e.target.value })} className={inputCls}>
                  <option value="ACTIVE">ACTIVE</option>
                  <option value="BLOCKED">BLOCKED</option>
                  <option value="CLOSED">CLOSED</option>
                </select>
              </LabeledInput>
              <LabeledInput label="Account type" value="" onChange={() => {}} span={2}>
                <select value={editAccountModal.account_type} onChange={(e) => setEditAccountModal({ ...editAccountModal, account_type: e.target.value })} className={inputCls}>
                  <option value="SAVINGS">SAVINGS</option>
                  <option value="CURRENT">CURRENT</option>
                  <option value="CREDIT">CREDIT</option>
                </select>
              </LabeledInput>
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t border-slate-200 dark:border-slate-800">
              <button type="button" onClick={() => setEditAccountModal(null)} className="px-4 py-2 text-xs rounded-lg">
                Cancel
              </button>
              <button type="submit" className="bg-emerald-600 hover:bg-emerald-500 text-white px-5 py-2 rounded-lg text-xs font-semibold">
                Save Balances
              </button>
            </div>
          </form>
        </Modal>
      )}

      {/* Change PIN */}
      {pinModalCard && (
        <Modal title={`Change PIN - ${pinModalCard.masked_pan}`} onClose={() => setPinModalCard(null)}>
          <form onSubmit={handleChangePin} className="space-y-4">
            <p className="text-[11px] text-slate-400">New clear PIN will recalculate Visa PVV / IBM offset via Soft-HSM.</p>
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
              <button type="submit" className="bg-violet-600 hover:bg-violet-500 text-white px-5 py-2 rounded-lg text-xs font-semibold">
                Update PIN
              </button>
            </div>
          </form>
        </Modal>
      )}

      {/* Link Account */}
      {linkModalCard && (
        <Modal title={`Link account to ${linkModalCard.masked_pan}`} onClose={() => setLinkModalCard(null)}>
          <div className="space-y-4">
            <select value={targetAccountId} onChange={(e) => setTargetAccountId(e.target.value)} className={`${inputCls} font-mono`}>
              {allAccounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.account_number} ({a.account_type}) - {a.customer_name} - {Number(a.available_balance).toLocaleString()} {a.currency}
                </option>
              ))}
            </select>
            <select value={linkRole} onChange={(e) => setLinkRole(e.target.value)} className={`${inputCls} font-mono`}>
              <option value="PRIMARY">PRIMARY</option>
              <option value="SECONDARY">SECONDARY</option>
            </select>
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setLinkModalCard(null)} className="px-4 py-2 text-xs">
                Cancel
              </button>
              <button type="button" onClick={handleLinkAccount} className="bg-sky-600 hover:bg-sky-500 text-white px-5 py-2 rounded-lg text-xs font-semibold flex items-center gap-1">
                <Plus size={14} /> Link Account
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* Reassign Customer */}
      {reassignModalCard && (
        <Modal title={`Reassign card ${reassignModalCard.masked_pan}`} onClose={() => setReassignModalCard(null)}>
          <form onSubmit={handleReassignCustomer} className="space-y-4">
            <p className="text-[11px] text-slate-400">Move this card to a different customer CIF. Linked accounts stay with the card.</p>
            <select value={reassignCustId} onChange={(e) => setReassignCustId(e.target.value)} className={`${inputCls} font-mono`} required>
              {allCustomers.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.customer_number} - {c.name}
                </option>
              ))}
            </select>
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setReassignModalCard(null)} className="px-4 py-2 text-xs">
                Cancel
              </button>
              <button type="submit" className="bg-amber-600 hover:bg-amber-500 text-white px-5 py-2 rounded-lg text-xs font-semibold flex items-center gap-1">
                <ArrowRightLeft size={14} /> Reassign Customer
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
};
