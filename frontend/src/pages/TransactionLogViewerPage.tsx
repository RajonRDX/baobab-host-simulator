import { HsmAuthoritySimulatorBar } from '../components/HsmAuthoritySimulatorBar';
import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import {
  Activity,
  RefreshCw,
  Pause,
  Play,
  Search,
  Filter,
  SlidersHorizontal,
  Download,
  Eye,
  X,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Clock,
  RotateCcw,
  Copy,
  Check,
  FileText,
  FileSpreadsheet,
  Shield,
  Key,
  Terminal,
  GitBranch,
  Layers,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  ExternalLink,
  Sparkles,
  Lock,
  Unlock,
} from 'lucide-react';

// -----------------------------------------------------------------------------
// TYPES & INTERFACES
// -----------------------------------------------------------------------------

interface TxSummaryMetrics {
  total_transactions: number;
  approved_transactions: number;
  declined_transactions: number;
  reversed_transactions: number;
  pending_transactions: number;
  approval_rate: number;
  approved_volume: number;
}

interface TxLogRow {
  id: string;
  transaction_reference: string;
  correlation_id: string;
  date: string;
  time: string;
  created_at: string;
  mti: string;
  processing_code: string;
  transaction_code: string;
  transaction_type: string;
  mcc: string;
  terminal_id: string;
  terminal_name: string;
  terminal_owner: string;
  merchant_id: string;
  merchant_name: string;
  issuer_code: string;
  issuer_name: string;
  acquirer_code: string;
  acquirer_name: string;
  ps_code: string;
  is_on_us: boolean;
  masked_pan: string;
  source_account?: string;
  amount: number;
  billing_amount: number;
  currency: string;
  response_code: string;
  response_description: string;
  approval_code: string;
  rrn: string;
  stan: string;
  status: 'APPROVED' | 'DECLINED' | 'REVERSED' | 'PENDING' | string;
  authorization_status: string;
  transaction_status: string;
  processing_duration_ms: number;
  source_channel: string;
}

interface ColumnDef {
  key: string;
  label: string;
  sortable?: boolean;
  sortKey?: string;
  defaultVisible: boolean;
  align?: 'left' | 'right' | 'center';
}

const ALL_COLUMNS: ColumnDef[] = [
  { key: 'transaction_reference', label: 'Txn ID', sortable: true, sortKey: 'transaction_reference', defaultVisible: true },
  { key: 'date', label: 'Date', sortable: true, sortKey: 'created_at', defaultVisible: true },
  { key: 'time', label: 'Time', sortable: true, sortKey: 'created_at', defaultVisible: true },
  { key: 'mti', label: 'MTI', sortable: true, sortKey: 'mti', defaultVisible: true, align: 'center' },
  { key: 'transaction_type', label: 'Transaction Type', defaultVisible: true },
  { key: 'mcc', label: 'MCC', defaultVisible: false, align: 'center' },
  { key: 'terminal_id', label: 'Terminal ID', defaultVisible: true },
  { key: 'terminal_name', label: 'Terminal Name', defaultVisible: false },
  { key: 'terminal_owner', label: 'Terminal Owner', defaultVisible: false },
  { key: 'issuer_code', label: 'Issuer', defaultVisible: true, align: 'center' },
  { key: 'acquirer_code', label: 'Acquirer', defaultVisible: true, align: 'center' },
  { key: 'ps_code', label: 'Switch', defaultVisible: true, align: 'center' },
  { key: 'masked_pan', label: 'PAN', defaultVisible: true },
  { key: 'source_account', label: 'Account', defaultVisible: false },
  { key: 'amount', label: 'Amount', sortable: true, sortKey: 'amount', defaultVisible: true, align: 'right' },
  { key: 'currency', label: 'Curr', defaultVisible: true, align: 'center' },
  { key: 'response_code', label: 'RC', sortable: true, sortKey: 'response_code', defaultVisible: true, align: 'center' },
  { key: 'response_description', label: 'Response Description', defaultVisible: true },
  { key: 'approval_code', label: 'Approval Code', defaultVisible: false, align: 'center' },
  { key: 'rrn', label: 'RRN', sortable: true, sortKey: 'rrn', defaultVisible: true },
  { key: 'stan', label: 'STAN', sortable: true, sortKey: 'stan', defaultVisible: true },
  { key: 'status', label: 'Status', sortable: true, sortKey: 'status', defaultVisible: true, align: 'center' },
];

const DEFAULT_VISIBLE_KEYS = ALL_COLUMNS.filter((c) => c.defaultVisible).map((c) => c.key);
const STORAGE_KEY_COLS = 'baobab_tx_log_viewer_columns_v1';
const STORAGE_KEY_REFRESH = 'baobab_tx_log_viewer_refresh_v1';

interface FilterState {
  transaction_id: string;
  correlation_id: string;
  rrn: string;
  stan: string;
  pan: string;
  account_number: string;
  customer: string;
  terminal_id: string;
  terminal_name: string;
  merchant_id: string;
  merchant_name: string;
  mcc: string;
  issuer: string;
  acquirer: string;
  ps_code: string;
  mti: string;
  response_code: string;
  status: string;
  transaction_type: string;
  currency: string;
  amount_from: string;
  amount_to: string;
  date_from: string;
  date_to: string;
}

const EMPTY_FILTERS: FilterState = {
  transaction_id: '',
  correlation_id: '',
  rrn: '',
  stan: '',
  pan: '',
  account_number: '',
  customer: '',
  terminal_id: '',
  terminal_name: '',
  merchant_id: '',
  merchant_name: '',
  mcc: '',
  issuer: '',
  acquirer: '',
  ps_code: '',
  mti: '',
  response_code: '',
  status: '',
  transaction_type: '',
  currency: '',
  amount_from: '',
  amount_to: '',
  date_from: '',
  date_to: '',
};

function findStoredJwtToken(): string {
  const candidateKeys = [
    'baobab_auth_token',
    'baobab_token',
    'host_token',
    'auth_token',
    'token',
    'access_token',
    'jwt',
  ];
  for (const k of candidateKeys) {
    const v = localStorage.getItem(k) || sessionStorage.getItem(k);
    if (v && v.trim()) {
      const clean = v.trim().replace(/^"|"$/g, '');
      if (clean.startsWith('eyJ')) return clean;
    }
  }
  // Scan all localStorage & sessionStorage entries for any JWT or JSON containing access_token
  for (const store of [localStorage, sessionStorage]) {
    for (let i = 0; i < store.length; i++) {
      const key = store.key(i);
      if (!key) continue;
      const raw = store.getItem(key) || '';
      const trimmed = raw.trim().replace(/^"|"$/g, '');
      if (trimmed.startsWith('eyJ') && trimmed.split('.').length === 3) {
        return trimmed;
      }
      if (trimmed.startsWith('{')) {
        try {
          const parsed = JSON.parse(trimmed);
          const tok = parsed?.access_token || parsed?.token || parsed?.state?.token;
          if (typeof tok === 'string' && tok.startsWith('eyJ')) {
            return tok;
          }
        } catch {
          // ignore
        }
      }
    }
  }
  return '';
}

function getAuthHeaders(): Record<string, string> {
  const token = findStoredJwtToken();
  return token
    ? { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
    : { 'Content-Type': 'application/json' };
}

let autoLoginPromise: Promise<string | null> | null = null;

async function ensureSimulatorToken(): Promise<string | null> {
  if (autoLoginPromise) return autoLoginPromise;
  autoLoginPromise = (async () => {
    try {
      const resp = await window.fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: 'admin', password: 'AdminPassword123!' }),
      });
      if (!resp.ok) return null;
      const data = await resp.json();
      if (data?.access_token) {
        localStorage.setItem('baobab_token', data.access_token);
        localStorage.setItem('token', data.access_token);
        localStorage.setItem('access_token', data.access_token);
        return data.access_token as string;
      }
      return null;
    } catch {
      return null;
    } finally {
      autoLoginPromise = null;
    }
  })();
  return autoLoginPromise;
}

async function apiFetch(input: string, init?: RequestInit): Promise<Response> {
  const headers = new Headers(init?.headers || {});
  const existingToken = findStoredJwtToken();
  if (existingToken && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${existingToken}`);
  }
  if (!headers.has('Content-Type') && init?.body) {
    headers.set('Content-Type', 'application/json');
  }

  let resp = await window.fetch(input, { ...init, headers });
  if (resp.status === 401) {
    const freshToken = await ensureSimulatorToken();
    if (freshToken) {
      headers.set('Authorization', `Bearer ${freshToken}`);
      resp = await window.fetch(input, { ...init, headers });
    }
  }
  return resp;
}

function StatusBadge({ status }: { status: string }) {
  const s = (status || '').toUpperCase();
  if (s === 'APPROVED') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
        <CheckCircle2 className="w-3 h-3" /> APPROVED
      </span>
    );
  }
  if (s === 'REVERSED') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-amber-500/15 text-amber-400 border border-amber-500/30">
        <RotateCcw className="w-3 h-3" /> REVERSED
      </span>
    );
  }
  if (s === 'PENDING') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-sky-500/15 text-sky-400 border border-sky-500/30">
        <Clock className="w-3 h-3" /> PENDING
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-rose-500/15 text-rose-400 border border-rose-500/30">
      <XCircle className="w-3 h-3" /> {s || 'DECLINED'}
    </span>
  );
}

// -----------------------------------------------------------------------------
// MAIN COMPONENT
// -----------------------------------------------------------------------------

export const TransactionLogViewerPage: React.FC = () => {
  // Data state
  const [rows, setRows] = useState<TxLogRow[]>([]);
  const [summary, setSummary] = useState<TxSummaryMetrics>({
    total_transactions: 0,
    approved_transactions: 0,
    declined_transactions: 0,
    reversed_transactions: 0,
    pending_transactions: 0,
    approval_rate: 0,
    approved_volume: 0,
  });
  const [total, setTotal] = useState<number>(0);
  const [page, setPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(25);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [sortBy, setSortBy] = useState<string>('created_at');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  // Loading & Error
  const [initialLoading, setInitialLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string>('—');

  // Auto-refresh timer state
  const [autoRefresh, setAutoRefresh] = useState<boolean>(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY_REFRESH) || '{}');
      return saved.autoRefresh ?? true;
    } catch {
      return true;
    }
  });
  const [ isPaused, setIsPaused ] = useState<boolean>(false);
  const [refreshIntervalSec, setRefreshIntervalSec] = useState<number>(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY_REFRESH) || '{}');
      return Number(saved.intervalSec) || 5;
    } catch {
      return 5;
    }
  });
  const [customIntervalInput, setCustomIntervalInput] = useState<string>('');
  const [showCustomInterval, setShowCustomInterval] = useState<boolean>(false);
  const [countdown, setCountdown] = useState<number>(refreshIntervalSec);

  // Filters state (draft vs applied)
  const [draftFilters, setDraftFilters] = useState<FilterState>(EMPTY_FILTERS);
  const [appliedFilters, setAppliedFilters] = useState<FilterState>(EMPTY_FILTERS);
  const [showAdvancedFilters, setShowAdvancedFilters] = useState<boolean>(false);

  // Column customization state
  const [visibleColumns, setVisibleColumns] = useState<string[]>(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY_COLS);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed) && parsed.length > 0) return parsed;
      }
    } catch {
      // ignore
    }
    return DEFAULT_VISIBLE_KEYS;
  });
  const [showColModal, setShowColModal] = useState<boolean>(false);
  const [draftColumns, setDraftColumns] = useState<string[]>(visibleColumns);

  // Selected Transaction for Detail Modal/Drawer
  const [selectedTxId, setSelectedTxId] = useState<string | null>(null);
  const [activeDetailTab, setActiveDetailTab] = useState<
    'GENERAL' | 'AUTHORIZATION' | 'ISO_DETAILS' | 'CRYPTO' | 'TRACE' | 'RELATED'
  >('GENERAL');

  // Concurrency & cleanup refs
  const inFlightRef = useRef<boolean>(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Persist auto-refresh settings
  useEffect(() => {
    try {
      localStorage.setItem(
        STORAGE_KEY_REFRESH,
        JSON.stringify({ autoRefresh, intervalSec: refreshIntervalSec })
      );
    } catch {
      // ignore
    }
  }, [autoRefresh, refreshIntervalSec]);

  // Load saved column preferences from backend on mount
  useEffect(() => {
    let mounted = true;
    apiFetch('/api/transaction-logs/preferences/columns', { headers: getAuthHeaders() })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (mounted && data && Array.isArray(data.columns) && data.columns.length > 0) {
          // Only overwrite if user hasn't customized locally yet
          if (!localStorage.getItem(STORAGE_KEY_COLS)) {
            setVisibleColumns(data.columns);
            setDraftColumns(data.columns);
          }
        }
      })
      .catch(() => {});
    return () => {
      mounted = false;
    };
  }, []);

  // Build query string from appliedFilters, page, pageSize, sortBy, sortDir
  const buildQueryParams = useCallback(
    (overridePage?: number) => {
      const params = new URLSearchParams();
      params.set('page', String(overridePage ?? page));
      params.set('page_size', String(pageSize));
      params.set('sort_by', sortBy);
      params.set('sort_dir', sortDir);
      Object.entries(appliedFilters).forEach(([k, v]) => {
        if (v !== undefined && v !== null && String(v).trim() !== '') {
          params.set(k, String(v).trim());
        }
      });
      return params.toString();
    },
    [appliedFilters, page, pageSize, sortBy, sortDir]
  );

  // Core fetch function (non-overlapping, preserves scroll and selection)
  const fetchTransactions = useCallback(
    async (isBackgroundRefresh = false, overridePage?: number) => {
      if (inFlightRef.current) {
        return; // Prevent overlapping refresh requests
      }
      inFlightRef.current = true;
      if (!isBackgroundRefresh) {
        setRefreshing(true);
      } else {
        setRefreshing(true);
      }

      const controller = new AbortController();
      abortControllerRef.current = controller;

      try {
        const qs = buildQueryParams(overridePage);
        const resp = await apiFetch(`/api/transaction-logs?${qs}`, {
          headers: getAuthHeaders(),
          signal: controller.signal,
        });
        if (!resp.ok) {
          const errBody = await resp.json().catch(() => ({}));
          throw new Error(errBody.detail || `Database query failed (HTTP ${resp.status})`);
        }
        const data = await resp.json();
        setRows(Array.isArray(data.items) ? data.items : []);
        setTotal(Number(data.total ?? 0));
        setTotalPages(Number(data.total_pages ?? 1));
        if (data.summary) {
          setSummary(data.summary);
        }
        setLastUpdated(new Date().toLocaleTimeString());
        setErrorMsg(null);
      } catch (err: any) {
        if (err?.name !== 'AbortError') {
          setErrorMsg(err?.message || 'Unable to retrieve transaction logs from database.');
        }
      } finally {
        inFlightRef.current = false;
        setInitialLoading(false);
        setRefreshing(false);
      }
    },
    [buildQueryParams]
  );

  // 1.1 Automatic initial loading & whenever appliedFilters / page / pageSize / sort change
  useEffect(() => {
    fetchTransactions(false);
    setCountdown(refreshIntervalSec);
  }, [fetchTransactions, refreshIntervalSec]);

  // Cleanup any in-flight request when leaving the page
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  // 1.2 Automatic refresh countdown timer
  useEffect(() => {
    if (!autoRefresh || isPaused) {
      return;
    }
    const timer = window.setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          if (!inFlightRef.current) {
            fetchTransactions(true);
          }
          return refreshIntervalSec;
        }
        return prev - 1;
      });
    }, 1000);

    return () => window.clearInterval(timer);
  }, [autoRefresh, isPaused, refreshIntervalSec, fetchTransactions]);

  // Handlers
  const handleManualRefresh = () => {
    setCountdown(refreshIntervalSec);
    fetchTransactions(false);
  };

  const handleApplyFilters = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setPage(1);
    setAppliedFilters({ ...draftFilters });
  };

  const handleClearFilters = () => {
    setDraftFilters(EMPTY_FILTERS);
    setAppliedFilters(EMPTY_FILTERS);
    setPage(1);
  };

  const handleSort = (col: ColumnDef) => {
    if (!col.sortable || !col.sortKey) return;
    if (sortBy === col.sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortBy(col.sortKey);
      setSortDir('desc');
    }
  };

  const handleExportCsv = async () => {
    try {
      const qs = buildQueryParams(1);
      const resp = await apiFetch(`/api/transaction-logs/export?${qs}`, {
        headers: getAuthHeaders(),
      });
      if (!resp.ok) throw new Error('Failed to export CSV');
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `baobab_transactions_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '_')}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err: any) {
      alert(err?.message || 'CSV Export failed');
    }
  };

  const handleSaveColumns = async () => {
    if (draftColumns.length === 0) {
      alert('Please select at least one column.');
      return;
    }
    setVisibleColumns(draftColumns);
    localStorage.setItem(STORAGE_KEY_COLS, JSON.stringify(draftColumns));
    setShowColModal(false);
    try {
      await apiFetch('/api/transaction-logs/preferences/columns', {
        method: 'PUT',
        headers: getAuthHeaders(),
        body: JSON.stringify({ columns: draftColumns }),
      });
    } catch {
      // localStorage already saved
    }
  };

  const activeColumns = useMemo(
    () => ALL_COLUMNS.filter((c) => visibleColumns.includes(c.key)),
    [visibleColumns]
  );

  const activeFilterCount = useMemo(
    () => Object.values(appliedFilters).filter((v) => String(v).trim() !== '').length,
    [appliedFilters]
  );

  const startRecord = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const endRecord = Math.min(total, page * pageSize);

  return (
    <div className="space-y-4 text-slate-100">
      <HsmAuthoritySimulatorBar />
      {/* HEADER BAR */}
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3 bg-slate-900/90 border border-slate-800 rounded-xl p-4 shadow-lg">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-indigo-500/15 border border-indigo-500/30 text-indigo-400">
              <Activity className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-lg font-bold tracking-tight text-white">
                TRANSACTION LOG VIEWER
              </h1>
              <p className="text-xs text-slate-400">
                Real-Time Host Switch Transaction Monitoring, TIC v2.164e ISO Inspector &amp; Pipeline Trace Investigator
              </p>
            </div>
          </div>
        </div>

        {/* AUTO-REFRESH CONTROL BAR */}
        <div className="flex flex-wrap items-center gap-2.5 bg-slate-950/80 border border-slate-800 rounded-lg px-3 py-2 text-xs">
          <div className="flex items-center gap-1.5 pr-2 border-r border-slate-800">
            <span className="text-slate-400">Last Updated:</span>
            <span className="font-mono font-semibold text-emerald-400">{lastUpdated}</span>
            {refreshing && (
              <RefreshCw className="w-3.5 h-3.5 text-indigo-400 animate-spin ml-1" title="Querying database..." />
            )}
          </div>

          <div className="flex items-center gap-1.5 pr-2 border-r border-slate-800">
            <span className="text-slate-400">Auto Refresh:</span>
            <button
              type="button"
              onClick={() => {
                setAutoRefresh((v) => !v);
                setIsPaused(false);
                setCountdown(refreshIntervalSec);
              }}
              className={`px-2 py-0.5 rounded font-bold transition ${
                autoRefresh
                  ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                  : 'bg-slate-800 text-slate-400 border border-slate-700'
              }`}
            >
              {autoRefresh ? 'ON' : 'OFF'}
            </button>
          </div>

          <div className="flex items-center gap-1.5 pr-2 border-r border-slate-800">
            <span className="text-slate-400">Interval:</span>
            <select
              value={showCustomInterval ? 'CUSTOM' : String(refreshIntervalSec)}
              onChange={(e) => {
                const val = e.target.value;
                if (val === 'CUSTOM') {
                  setShowCustomInterval(true);
                  setCustomIntervalInput(String(refreshIntervalSec));
                } else {
                  setShowCustomInterval(false);
                  const sec = Number(val);
                  setRefreshIntervalSec(sec);
                  setCountdown(sec);
                }
              }}
              className="bg-slate-900 border border-slate-700 rounded px-2 py-0.5 text-slate-200 font-mono focus:outline-none focus:border-indigo-500"
            >
              {[2, 5, 10, 15, 30, 60].map((s) => (
                <option key={s} value={String(s)}>
                  {s}s
                </option>
              ))}
              <option value="CUSTOM">Custom...</option>
            </select>

            {showCustomInterval && (
              <div className="flex items-center gap-1">
                <input
                  type="number"
                  min={1}
                  max={300}
                  value={customIntervalInput}
                  onChange={(e) => setCustomIntervalInput(e.target.value)}
                  className="w-14 bg-slate-900 border border-slate-700 rounded px-1.5 py-0.5 font-mono text-slate-200"
                  placeholder="Sec"
                />
                <button
                  type="button"
                  onClick={() => {
                    const parsed = Math.max(1, Math.min(300, Number(customIntervalInput) || 5));
                    setRefreshIntervalSec(parsed);
                    setCountdown(parsed);
                  }}
                  className="px-1.5 py-0.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded font-medium"
                >
                  Set
                </button>
              </div>
            )}
          </div>

          {autoRefresh && (
            <div className="flex items-center gap-1.5 pr-2 border-r border-slate-800">
              <span className="text-slate-400">Next Refresh In:</span>
              <span
                className={`font-mono font-bold px-1.5 py-0.2 rounded ${
                  isPaused ? 'text-amber-400 bg-amber-500/10' : 'text-indigo-300 bg-indigo-500/15'
                }`}
              >
                {isPaused ? 'PAUSED' : `${String(countdown).padStart(2, '0')}s`}
              </span>
            </div>
          )}

          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={handleManualRefresh}
              disabled={refreshing}
              className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-medium transition"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
              Refresh Now
            </button>

            {autoRefresh && (
              <button
                type="button"
                onClick={() => setIsPaused((p) => !p)}
                className={`inline-flex items-center gap-1 px-2.5 py-1 rounded border font-medium transition ${
                  isPaused
                    ? 'bg-emerald-600/20 border-emerald-500/40 text-emerald-300 hover:bg-emerald-600/30'
                    : 'bg-amber-500/15 border-amber-500/30 text-amber-300 hover:bg-amber-500/25'
                }`}
              >
                {isPaused ? (
                  <>
                    <Play className="w-3.5 h-3.5" /> Resume
                  </>
                ) : (
                  <>
                    <Pause className="w-3.5 h-3.5" /> Pause
                  </>
                )}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* ERROR BANNER */}
      {errorMsg && (
        <div className="flex items-center justify-between bg-rose-950/70 border border-rose-500/40 text-rose-200 px-4 py-2.5 rounded-lg text-xs">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
            <span>{errorMsg}</span>
          </div>
          <button
            type="button"
            onClick={handleManualRefresh}
            className="px-2.5 py-1 bg-rose-600 hover:bg-rose-500 text-white rounded font-semibold"
          >
            Retry Query
          </button>
        </div>
      )}

      {/* 2.1 SUMMARY CARDS */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-3">
          <div className="text-[11px] font-medium uppercase tracking-wider text-slate-400">
            Total Transactions
          </div>
          <div className="mt-1 text-2xl font-bold font-mono text-white">
            {summary.total_transactions.toLocaleString()}
          </div>
          <div className="text-[11px] text-slate-500 mt-0.5">Matching active filter context</div>
        </div>

        <div className="bg-slate-900/90 border border-emerald-500/25 rounded-xl p-3">
          <div className="text-[11px] font-medium uppercase tracking-wider text-emerald-400">
            Approved
          </div>
          <div className="mt-1 text-2xl font-bold font-mono text-emerald-400">
            {summary.approved_transactions.toLocaleString()}
          </div>
          <div className="text-[11px] text-slate-400 mt-0.5 font-mono">
            Vol: {summary.approved_volume.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
        </div>

        <div className="bg-slate-900/90 border border-rose-500/25 rounded-xl p-3">
          <div className="text-[11px] font-medium uppercase tracking-wider text-rose-400">
            Declined
          </div>
          <div className="mt-1 text-2xl font-bold font-mono text-rose-400">
            {summary.declined_transactions.toLocaleString()}
          </div>
          <div className="text-[11px] text-slate-500 mt-0.5">Host / HSM / Rule declines</div>
        </div>

        <div className="bg-slate-900/90 border border-amber-500/25 rounded-xl p-3">
          <div className="text-[11px] font-medium uppercase tracking-wider text-amber-400">
            Reversed
          </div>
          <div className="mt-1 text-2xl font-bold font-mono text-amber-400">
            {summary.reversed_transactions.toLocaleString()}
          </div>
          <div className="text-[11px] text-slate-500 mt-0.5">MTI 0400 / 0420 reversals</div>
        </div>

        <div className="bg-slate-900/90 border border-sky-500/25 rounded-xl p-3">
          <div className="text-[11px] font-medium uppercase tracking-wider text-sky-400">
            Pending
          </div>
          <div className="mt-1 text-2xl font-bold font-mono text-sky-400">
            {summary.pending_transactions.toLocaleString()}
          </div>
          <div className="text-[11px] text-slate-500 mt-0.5">In-flight / awaiting advice</div>
        </div>

        <div className="bg-slate-900/90 border border-indigo-500/25 rounded-xl p-3">
          <div className="text-[11px] font-medium uppercase tracking-wider text-indigo-400">
            Approval Rate
          </div>
          <div className="mt-1 text-2xl font-bold font-mono text-indigo-300">
            {summary.approval_rate.toFixed(1)}%
          </div>
          <div className="w-full bg-slate-800 h-1.5 rounded-full mt-2 overflow-hidden">
            <div
              className="bg-indigo-500 h-full rounded-full transition-all"
              style={{ width: `${Math.min(100, Math.max(0, summary.approval_rate))}%` }}
            />
          </div>
        </div>
      </div>

      {/* 2.2 SERVER-SIDE TRANSACTION FILTERS */}
      <form
        onSubmit={handleApplyFilters}
        className="bg-slate-900/90 border border-slate-800 rounded-xl p-3.5 space-y-3"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-300">
            <Filter className="w-4 h-4 text-indigo-400" />
            <span>SERVER-SIDE TRANSACTION FILTERS</span>
            {activeFilterCount > 0 && (
              <span className="px-2 py-0.5 rounded-full text-[11px] bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                {activeFilterCount} Active
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setShowAdvancedFilters((s) => !s)}
              className="text-xs text-indigo-400 hover:text-indigo-300 font-medium"
            >
              {showAdvancedFilters ? 'Hide Extended Filters ▲' : 'Show All 20 Filters ▼'}
            </button>
          </div>
        </div>

        {/* Primary Filter Row */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5 text-xs">
          <div>
            <label className="block text-[11px] text-slate-400 mb-1">Txn ID / Reference</label>
            <input
              type="text"
              value={draftFilters.transaction_id}
              onChange={(e) => setDraftFilters({ ...draftFilters, transaction_id: e.target.value })}
              placeholder="TX-... or UUID"
              className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200 font-mono focus:border-indigo-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-[11px] text-slate-400 mb-1">RRN (F37)</label>
            <input
              type="text"
              value={draftFilters.rrn}
              onChange={(e) => setDraftFilters({ ...draftFilters, rrn: e.target.value })}
              placeholder="e.g. 000020526001"
              className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200 font-mono focus:border-indigo-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-[11px] text-slate-400 mb-1">STAN (F11)</label>
            <input
              type="text"
              value={draftFilters.stan}
              onChange={(e) => setDraftFilters({ ...draftFilters, stan: e.target.value })}
              placeholder="e.g. 100001"
              className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200 font-mono focus:border-indigo-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-[11px] text-slate-400 mb-1">PAN (Full or Last 4)</label>
            <input
              type="text"
              value={draftFilters.pan}
              onChange={(e) => setDraftFilters({ ...draftFilters, pan: e.target.value })}
              placeholder="456789... or 0001"
              className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200 font-mono focus:border-indigo-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-[11px] text-slate-400 mb-1">Status</label>
            <select
              value={draftFilters.status}
              onChange={(e) => setDraftFilters({ ...draftFilters, status: e.target.value })}
              className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200 focus:border-indigo-500 focus:outline-none"
            >
              <option value="">All Statuses</option>
              <option value="APPROVED">APPROVED</option>
              <option value="DECLINED">DECLINED</option>
              <option value="REVERSED">REVERSED</option>
              <option value="PENDING">PENDING</option>
            </select>
          </div>
          <div>
            <label className="block text-[11px] text-slate-400 mb-1">Response Code (F39)</label>
            <input
              type="text"
              value={draftFilters.response_code}
              onChange={(e) => setDraftFilters({ ...draftFilters, response_code: e.target.value })}
              placeholder="00, 05, 51, 55, 61..."
              className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200 font-mono focus:border-indigo-500 focus:outline-none"
            />
          </div>
        </div>

        {/* Extended 20-Filter Grid */}
        {showAdvancedFilters && (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5 pt-2 border-t border-slate-800/80 text-xs">
            <div>
              <label className="block text-[11px] text-slate-400 mb-1">MTI</label>
              <select
                value={draftFilters.mti}
                onChange={(e) => setDraftFilters({ ...draftFilters, mti: e.target.value })}
                className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200 font-mono"
              >
                <option value="">All MTIs</option>
                <option value="0100">0100 (Auth Req)</option>
                <option value="0200">0200 (Financial Req)</option>
                <option value="0220">0220 (Clearing Advice)</option>
                <option value="0400">0400 (Reversal Req)</option>
                <option value="0420">0420 (Reversal Advice)</option>
              </select>
            </div>
            <div>
              <label className="block text-[11px] text-slate-400 mb-1">Processing System</label>
              <select
                value={draftFilters.ps_code}
                onChange={(e) => setDraftFilters({ ...draftFilters, ps_code: e.target.value })}
                className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200"
              >
                <option value="">All Switches</option>
                <option value="ITCL">ITCL (QCash)</option>
                <option value="VISA">VISA</option>
                <option value="MASTERCARD">MASTERCARD</option>
                <option value="NPSB">NPSB</option>
              </select>
            </div>
            <div>
              <label className="block text-[11px] text-slate-400 mb-1">Issuer Bank</label>
              <input
                type="text"
                value={draftFilters.issuer}
                onChange={(e) => setDraftFilters({ ...draftFilters, issuer: e.target.value })}
                placeholder="XBANK, YBANK, ZBANK..."
                className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200"
              />
            </div>
            <div>
              <label className="block text-[11px] text-slate-400 mb-1">Acquirer Bank / ID</label>
              <input
                type="text"
                value={draftFilters.acquirer}
                onChange={(e) => setDraftFilters({ ...draftFilters, acquirer: e.target.value })}
                placeholder="XBANK or 123456"
                className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200"
              />
            </div>
            <div>
              <label className="block text-[11px] text-slate-400 mb-1">Transaction Type / Code</label>
              <input
                type="text"
                value={draftFilters.transaction_type}
                onChange={(e) => setDraftFilters({ ...draftFilters, transaction_type: e.target.value })}
                placeholder="Withdrawal, Purchase, 10..."
                className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200"
              />
            </div>
            <div>
              <label className="block text-[11px] text-slate-400 mb-1">Account Number</label>
              <input
                type="text"
                value={draftFilters.account_number}
                onChange={(e) => setDraftFilters({ ...draftFilters, account_number: e.target.value })}
                placeholder="ACCT-..."
                className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200 font-mono"
              />
            </div>
            <div>
              <label className="block text-[11px] text-slate-400 mb-1">Customer Name / CIF</label>
              <input
                type="text"
                value={draftFilters.customer}
                onChange={(e) => setDraftFilters({ ...draftFilters, customer: e.target.value })}
                placeholder="CIF or Customer Name"
                className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200"
              />
            </div>
            <div>
              <label className="block text-[11px] text-slate-400 mb-1">Terminal ID (F41)</label>
              <input
                type="text"
                value={draftFilters.terminal_id}
                onChange={(e) => setDraftFilters({ ...draftFilters, terminal_id: e.target.value })}
                placeholder="ATM00001 / POS00002"
                className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200 font-mono"
              />
            </div>
            <div>
              <label className="block text-[11px] text-slate-400 mb-1">Terminal Name / Owner</label>
              <input
                type="text"
                value={draftFilters.terminal_name}
                onChange={(e) => setDraftFilters({ ...draftFilters, terminal_name: e.target.value })}
                placeholder="Owner or Location"
                className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200"
              />
            </div>
            <div>
              <label className="block text-[11px] text-slate-400 mb-1">Merchant ID / Name</label>
              <input
                type="text"
                value={draftFilters.merchant_id}
                onChange={(e) => setDraftFilters({ ...draftFilters, merchant_id: e.target.value })}
                placeholder="Merchant ID"
                className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200 font-mono"
              />
            </div>
            <div>
              <label className="block text-[11px] text-slate-400 mb-1">MCC (F18)</label>
              <input
                type="text"
                value={draftFilters.mcc}
                onChange={(e) => setDraftFilters({ ...draftFilters, mcc: e.target.value })}
                placeholder="6011, 5411..."
                className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200 font-mono"
              />
            </div>
            <div>
              <label className="block text-[11px] text-slate-400 mb-1">Correlation ID</label>
              <input
                type="text"
                value={draftFilters.correlation_id}
                onChange={(e) => setDraftFilters({ ...draftFilters, correlation_id: e.target.value })}
                placeholder="CORR-..."
                className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200 font-mono"
              />
            </div>
            <div>
              <label className="block text-[11px] text-slate-400 mb-1">Currency (F49)</label>
              <input
                type="text"
                value={draftFilters.currency}
                onChange={(e) => setDraftFilters({ ...draftFilters, currency: e.target.value })}
                placeholder="BDT, USD..."
                className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200 font-mono"
              />
            </div>
            <div>
              <label className="block text-[11px] text-slate-400 mb-1">Amount From</label>
              <input
                type="number"
                step="0.01"
                value={draftFilters.amount_from}
                onChange={(e) => setDraftFilters({ ...draftFilters, amount_from: e.target.value })}
                placeholder="Min Amount"
                className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200 font-mono"
              />
            </div>
            <div>
              <label className="block text-[11px] text-slate-400 mb-1">Amount To</label>
              <input
                type="number"
                step="0.01"
                value={draftFilters.amount_to}
                onChange={(e) => setDraftFilters({ ...draftFilters, amount_to: e.target.value })}
                placeholder="Max Amount"
                className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200 font-mono"
              />
            </div>
            <div>
              <label className="block text-[11px] text-slate-400 mb-1">Date From</label>
              <input
                type="date"
                value={draftFilters.date_from}
                onChange={(e) => setDraftFilters({ ...draftFilters, date_from: e.target.value })}
                className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200 font-mono"
              />
            </div>
            <div>
              <label className="block text-[11px] text-slate-400 mb-1">Date To</label>
              <input
                type="date"
                value={draftFilters.date_to}
                onChange={(e) => setDraftFilters({ ...draftFilters, date_to: e.target.value })}
                className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200 font-mono"
              />
            </div>
          </div>
        )}

        {/* Filter Action Buttons */}
        <div className="flex items-center justify-end gap-2 pt-1">
          <button
            type="button"
            onClick={handleClearFilters}
            className="px-3 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium transition"
          >
            Clear Filters
          </button>
          <button
            type="submit"
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold transition shadow"
          >
            <Search className="w-3.5 h-3.5" />
            Apply Filters
          </button>
        </div>
      </form>

      {/* 2.3 MAIN TRANSACTION TABLE CONTAINER */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl overflow-hidden shadow-lg">
        {/* Table Toolbar */}
        <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 border-b border-slate-800 bg-slate-950/50">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
              Transaction Log Stream
            </span>
            <span className="text-xs text-slate-500">
              (Double-click any row or click Investigate for full 6-tab switch forensics)
            </span>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => {
                setDraftColumns(visibleColumns);
                setShowColModal(true);
              }}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium border border-slate-700 transition"
            >
              <SlidersHorizontal className="w-3.5 h-3.5 text-indigo-400" />
              Columns ({visibleColumns.length}/{ALL_COLUMNS.length})
            </button>

            <button
              type="button"
              onClick={handleExportCsv}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border border-emerald-500/30 text-xs font-medium transition"
            >
              <Download className="w-3.5 h-3.5" />
              Export CSV
            </button>
          </div>
        </div>

        {/* Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="bg-slate-950/90 border-b border-slate-800 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                {activeColumns.map((col) => {
                  const isSorted = col.sortable && col.sortKey === sortBy;
                  return (
                    <th
                      key={col.key}
                      onClick={() => handleSort(col)}
                      className={`py-2.5 px-3 whitespace-nowrap select-none ${
                        col.sortable ? 'cursor-pointer hover:text-white' : ''
                      } ${
                        col.align === 'right'
                          ? 'text-right'
                          : col.align === 'center'
                          ? 'text-center'
                          : 'text-left'
                      }`}
                    >
                      <div
                        className={`inline-flex items-center gap-1 ${
                          col.align === 'right' ? 'justify-end' : col.align === 'center' ? 'justify-center' : ''
                        }`}
                      >
                        <span>{col.label}</span>
                        {col.sortable && (
                          <span>
                            {isSorted ? (
                              sortDir === 'asc' ? (
                                <ArrowUp className="w-3 h-3 text-indigo-400" />
                              ) : (
                                <ArrowDown className="w-3 h-3 text-indigo-400" />
                              )
                            ) : (
                              <ArrowUpDown className="w-3 h-3 text-slate-600" />
                            )}
                          </span>
                        )}
                      </div>
                    </th>
                  );
                })}
                <th className="py-2.5 px-3 text-right whitespace-nowrap">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/70 font-mono">
              {initialLoading ? (
                <tr>
                  <td colSpan={activeColumns.length + 1} className="py-12 text-center text-slate-400 font-sans">
                    <RefreshCw className="w-6 h-6 text-indigo-400 animate-spin mx-auto mb-2" />
                    Loading latest transactions from BAOBAB host database...
                  </td>
                </tr>
              ) : rows.length === 0 ? (
                <tr>
                  <td colSpan={activeColumns.length + 1} className="py-12 text-center text-slate-400 font-sans">
                    No transaction records match the active filter criteria.
                  </td>
                </tr>
              ) : (
                rows.map((row) => {
                  const isSelected = selectedTxId === row.id;
                  return (
                    <tr
                      key={row.id}
                      onDoubleClick={() => {
                        setSelectedTxId(row.id);
                        setActiveDetailTab('GENERAL');
                      }}
                      className={`transition cursor-pointer ${
                        isSelected
                          ? 'bg-indigo-950/60 hover:bg-indigo-950/80'
                          : 'hover:bg-slate-800/60'
                      }`}
                    >
                      {activeColumns.map((col) => {
                        const val = (row as any)[col.key];
                        if (col.key === 'status') {
                          return (
                            <td key={col.key} className="py-2 px-3 text-center whitespace-nowrap font-sans">
                              <StatusBadge status={row.status} />
                            </td>
                          );
                        }
                        if (col.key === 'amount') {
                          return (
                            <td key={col.key} className="py-2 px-3 text-right whitespace-nowrap font-semibold text-white">
                              {Number(row.amount || 0).toLocaleString(undefined, {
                                minimumFractionDigits: 2,
                                maximumFractionDigits: 2,
                              })}
                            </td>
                          );
                        }
                        if (col.key === 'response_code') {
                          const isOk = row.response_code === '00';
                          return (
                            <td key={col.key} className="py-2 px-3 text-center whitespace-nowrap">
                              <span
                                className={`px-1.5 py-0.5 rounded text-[11px] font-bold ${
                                  isOk
                                    ? 'bg-emerald-500/15 text-emerald-300'
                                    : 'bg-rose-500/15 text-rose-300'
                                }`}
                              >
                                {row.response_code}
                              </span>
                            </td>
                          );
                        }
                        if (col.key === 'mti') {
                          return (
                            <td key={col.key} className="py-2 px-3 text-center whitespace-nowrap text-indigo-300 font-semibold">
                              {row.mti}
                            </td>
                          );
                        }
                        if (col.key === 'transaction_type' || col.key === 'response_description' || col.key === 'terminal_name') {
                          return (
                            <td key={col.key} className="py-2 px-3 whitespace-nowrap font-sans text-slate-200">
                              {val || '—'}
                            </td>
                          );
                        }
                        return (
                          <td
                            key={col.key}
                            className={`py-2 px-3 whitespace-nowrap text-slate-300 ${
                              col.align === 'right'
                                ? 'text-right'
                                : col.align === 'center'
                                ? 'text-center'
                                : 'text-left'
                            }`}
                          >
                            {val ?? '—'}
                          </td>
                        );
                      })}
                      <td className="py-2 px-3 text-right whitespace-nowrap font-sans">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedTxId(row.id);
                            setActiveDetailTab('GENERAL');
                          }}
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-indigo-600/20 hover:bg-indigo-600/40 text-indigo-300 border border-indigo-500/30 text-[11px] font-semibold transition"
                        >
                          <Eye className="w-3 h-3" /> Details
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* 2.5 SERVER-SIDE PAGINATION FOOTER */}
        <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 border-t border-slate-800 bg-slate-950/60 text-xs">
          <div className="flex items-center gap-3 text-slate-400">
            <span>
              Showing <strong className="text-white font-mono">{startRecord}</strong>–
              <strong className="text-white font-mono">{endRecord}</strong> of{' '}
              <strong className="text-white font-mono">{total.toLocaleString()}</strong> records
            </span>

            <div className="flex items-center gap-1.5">
              <span>Page Size:</span>
              <select
                value={pageSize}
                onChange={(e) => {
                  setPageSize(Number(e.target.value));
                  setPage(1);
                }}
                className="bg-slate-900 border border-slate-700 rounded px-2 py-0.5 text-slate-200 font-mono"
              >
                {[25, 50, 100, 200].map((sz) => (
                  <option key={sz} value={sz}>
                    {sz}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="flex items-center gap-1.5">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => setPage(1)}
              className="p-1.5 rounded bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-slate-300"
              title="First Page"
            >
              <ChevronsLeft className="w-4 h-4" />
            </button>
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-slate-300 font-medium inline-flex items-center gap-1"
            >
              <ChevronLeft className="w-3.5 h-3.5" /> Previous
            </button>
            <span className="px-3 py-1 font-mono text-slate-300">
              Page <strong className="text-white">{page}</strong> / {totalPages}
            </span>
            <button
              type="button"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-slate-300 font-medium inline-flex items-center gap-1"
            >
              Next <ChevronRight className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              disabled={page >= totalPages}
              onClick={() => setPage(totalPages)}
              className="p-1.5 rounded bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-slate-300"
              title="Last Page"
            >
              <ChevronsRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* 2.4 COLUMN CUSTOMIZATION MODAL */}
      {showColModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-xl max-w-lg w-full p-5 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <SlidersHorizontal className="w-4 h-4 text-indigo-400" />
                <h3 className="text-sm font-bold text-white">Customize Transaction Table Columns</h3>
              </div>
              <button
                type="button"
                onClick={() => setShowColModal(false)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="flex items-center gap-2 text-xs">
              <button
                type="button"
                onClick={() => setDraftColumns(ALL_COLUMNS.map((c) => c.key))}
                className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200"
              >
                Select All
              </button>
              <button
                type="button"
                onClick={() => setDraftColumns(['transaction_reference'])}
                className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200"
              >
                Deselect All
              </button>
              <button
                type="button"
                onClick={() => setDraftColumns(DEFAULT_VISIBLE_KEYS)}
                className="px-2.5 py-1 rounded bg-indigo-500/20 hover:bg-indigo-500/30 text-indigo-300"
              >
                Reset to Default
              </button>
            </div>

            <div className="grid grid-cols-2 gap-2 max-h-72 overflow-y-auto p-1 text-xs">
              {ALL_COLUMNS.map((col) => {
                const checked = draftColumns.includes(col.key);
                return (
                  <label
                    key={col.key}
                    className={`flex items-center gap-2 p-2 rounded border cursor-pointer transition ${
                      checked
                        ? 'bg-indigo-950/40 border-indigo-500/40 text-white'
                        : 'bg-slate-950/60 border-slate-800 text-slate-400'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setDraftColumns([...draftColumns, col.key]);
                        } else {
                          setDraftColumns(draftColumns.filter((k) => k !== col.key));
                        }
                      }}
                      className="rounded border-slate-600 text-indigo-600 focus:ring-indigo-500"
                    />
                    <span>{col.label}</span>
                  </label>
                );
              })}
            </div>

            <div className="flex items-center justify-end gap-2 border-t border-slate-800 pt-3 text-xs">
              <button
                type="button"
                onClick={() => setShowColModal(false)}
                className="px-3 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSaveColumns}
                className="px-4 py-1.5 rounded bg-indigo-600 hover:bg-indigo-500 text-white font-semibold"
              >
                Apply &amp; Save Preference
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 3. TRANSACTION DETAIL INVESTIGATION MODAL */}
      {selectedTxId && (
        <TransactionInvestigationModal
          transactionId={selectedTxId}
          activeTab={activeDetailTab}
          onChangeTab={setActiveDetailTab}
          onSelectRelatedTx={(newId) => {
            setSelectedTxId(newId);
            setActiveDetailTab('GENERAL');
          }}
          onClose={() => setSelectedTxId(null)}
        />
      )}
    </div>
  );
};

// -----------------------------------------------------------------------------
// TRANSACTION DETAIL INVESTIGATION MODAL (6 LAZY-LOADED TABS)
// -----------------------------------------------------------------------------

interface InvestigationModalProps {
  transactionId: string;
  activeTab: 'GENERAL' | 'AUTHORIZATION' | 'ISO_DETAILS' | 'CRYPTO' | 'TRACE' | 'RELATED';
  onChangeTab: (tab: 'GENERAL' | 'AUTHORIZATION' | 'ISO_DETAILS' | 'CRYPTO' | 'TRACE' | 'RELATED') => void;
  onSelectRelatedTx: (txId: string) => void;
  onClose: () => void;
}

const TransactionInvestigationModal: React.FC<InvestigationModalProps> = ({
  transactionId,
  activeTab,
  onChangeTab,
  onSelectRelatedTx,
  onClose,
}) => {
  const [generalData, setGeneralData] = useState<any>(null);
  const [revealPan, setRevealPan] = useState<boolean>(false);
  const [authData, setAuthData] = useState<any>(null);
  const [isoData, setIsoData] = useState<any>(null);
  const [cryptoData, setCryptoData] = useState<any>(null);
  const [traceData, setTraceData] = useState<any>(null);
  const [relatedData, setRelatedData] = useState<any>(null);
  const [tabLoading, setTabLoading] = useState<boolean>(false);
  const [tabError, setTabError] = useState<string | null>(null);

  // ISO Details sub-state
  const [selectedMsgIdx, setSelectedMsgIdx] = useState<number>(0);
  const [isoViewMode, setIsoViewMode] = useState<'PARSED' | 'RAW' | 'COMPARE'>('PARSED');
  const [isoFieldSearch, setIsoFieldSearch] = useState<string>('');
  const [expandedFields, setExpandedFields] = useState<Record<number, boolean>>({});
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  // Reset cached tab payloads when transactionId changes
  useEffect(() => {
    setGeneralData(null);
    setAuthData(null);
    setIsoData(null);
    setCryptoData(null);
    setTraceData(null);
    setRelatedData(null);
    setRevealPan(false);
    setSelectedMsgIdx(0);
    setIsoViewMode('PARSED');
  }, [transactionId]);

  // Lazy load active tab data (Note: TRACE tab waits for explicit user button click per Requirement 8)
  useEffect(() => {
    let mounted = true;
    const loadTab = async () => {
      setTabError(null);
      try {
        if (activeTab === 'GENERAL') {
          setTabLoading(true);
          const r = await fetch(
            `/api/transaction-logs/${transactionId}?reveal_pan=${revealPan ? 'true' : 'false'}`,
            { headers: getAuthHeaders() }
          );
          if (!r.ok) throw new Error(`Failed to load General tab (${r.status})`);
          const d = await r.json();
          if (mounted) setGeneralData(d);
        } else if (activeTab === 'AUTHORIZATION' && !authData) {
          setTabLoading(true);
          const r = await apiFetch(`/api/transaction-logs/${transactionId}/authorization`, {
            headers: getAuthHeaders(),
          });
          if (!r.ok) throw new Error(`Failed to load Authorizer Response (${r.status})`);
          const d = await r.json();
          if (mounted) setAuthData(d);
        } else if (activeTab === 'ISO_DETAILS' && !isoData) {
          setTabLoading(true);
          const r = await apiFetch(`/api/transaction-logs/${transactionId}/messages`, {
            headers: getAuthHeaders(),
          });
          if (!r.ok) throw new Error(`Failed to load ISO messages (${r.status})`);
          const d = await r.json();
          if (mounted) setIsoData(d);
        } else if (activeTab === 'CRYPTO' && !cryptoData) {
          setTabLoading(true);
          const r = await apiFetch(`/api/transaction-logs/${transactionId}/crypto`, {
            headers: getAuthHeaders(),
          });
          if (!r.ok) throw new Error(`Failed to load Keys & Crypto (${r.status})`);
          const d = await r.json();
          if (mounted) setCryptoData(d);
        } else if (activeTab === 'RELATED' && !relatedData) {
          setTabLoading(true);
          const r = await apiFetch(`/api/transaction-logs/${transactionId}/related`, {
            headers: getAuthHeaders(),
          });
          if (!r.ok) throw new Error(`Failed to load Related Transactions (${r.status})`);
          const d = await r.json();
          if (mounted) setRelatedData(d);
        }
      } catch (err: any) {
        if (mounted) setTabError(err?.message || 'Error loading tab details');
      } finally {
        if (mounted) setTabLoading(false);
      }
    };
    loadTab();
    return () => {
      mounted = false;
    };
  }, [transactionId, activeTab, revealPan, authData, isoData, cryptoData, relatedData]);

  // Explicit Trace Generation/Loading Handler (Requirement 8)
  const handleGenerateOrLoadTrace = async () => {
    setTabLoading(true);
    setTabError(null);
    try {
      const r = await apiFetch(`/api/transaction-logs/${transactionId}/trace/generate`, {
        method: 'POST',
        headers: getAuthHeaders(),
      });
      if (!r.ok) throw new Error(`Failed to generate/load trace (${r.status})`);
      const d = await r.json();
      setTraceData(d);
    } catch (err: any) {
      setTabError(err?.message || 'Trace retrieval failed');
    } finally {
      setTabLoading(false);
    }
  };

  const handleDownloadTraceTxt = async () => {
    const resp = await apiFetch(`/api/transaction-logs/${transactionId}/trace/export`, {
      headers: getAuthHeaders(),
    });
    if (!resp.ok) return;
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `trace_${transactionId}.txt`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  const handleDownloadPackage = async () => {
    const resp = await apiFetch(`/api/transaction-logs/${transactionId}/package`, {
      headers: getAuthHeaders(),
    });
    if (!resp.ok) return;
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `investigation_${transactionId}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  const handleExportDecodedExcel = async (msgId: string, mti: string) => {
    const resp = await fetch(
      `/api/transaction-logs/${transactionId}/messages/${msgId}/export-excel`,
      { headers: getAuthHeaders() }
    );
    if (!resp.ok) return;
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `tic_decoded_${mti}_${transactionId.slice(0, 8)}.xlsx`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  const copyText = (key: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 1500);
  };

  const summaryHeader = generalData?.summary;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-3 sm:p-6">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-6xl h-[90vh] flex flex-col overflow-hidden shadow-2xl">
        {/* TOP HEADER */}
        <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-3.5 bg-slate-950 border-b border-slate-800">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-indigo-500/15 border border-indigo-500/30 text-indigo-400">
              <Layers className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2.5">
                <h2 className="text-sm font-bold text-white font-mono">
                  {summaryHeader?.transaction_reference || transactionId}
                </h2>
                {summaryHeader && <StatusBadge status={summaryHeader.status} />}
                {summaryHeader && (
                  <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono text-xs">
                    MTI {summaryHeader.mti} · RC {summaryHeader.response_code}
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-400 mt-0.5 font-mono">
                RRN: {summaryHeader?.rrn || '—'} · STAN: {summaryHeader?.stan || '—'} · Amount:{' '}
                {summaryHeader
                  ? `${Number(summaryHeader.amount).toLocaleString(undefined, { minimumFractionDigits: 2 })} ${summaryHeader.currency}`
                  : '—'}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleDownloadPackage}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 border border-indigo-500/30 text-xs font-semibold transition"
              title="Download sanitized JSON investigation package"
            >
              <Download className="w-3.5 h-3.5" /> Investigation Package
            </button>
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* 6 INVESTIGATION TABS BAR */}
        <div className="flex items-center gap-1 px-5 pt-2 bg-slate-950/70 border-b border-slate-800 overflow-x-auto text-xs">
          {[
            { id: 'GENERAL', label: '1. General', icon: FileText },
            { id: 'AUTHORIZATION', label: '2. Authorizer Response', icon: Shield },
            { id: 'ISO_DETAILS', label: '3. ISO Details (TIC Decoder)', icon: Layers },
            { id: 'CRYPTO', label: '4. Keys & Crypto', icon: Key },
            { id: 'TRACE', label: '5. Processing Trace', icon: Terminal },
            { id: 'RELATED', label: '6. Related Transactions', icon: GitBranch },
          ].map((t) => {
            const Icon = t.icon;
            const isActive = activeTab === t.id;
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => onChangeTab(t.id as any)}
                className={`inline-flex items-center gap-1.5 px-3.5 py-2.5 border-b-2 font-semibold whitespace-nowrap transition ${
                  isActive
                    ? 'border-indigo-500 text-indigo-400 bg-indigo-500/10'
                    : 'border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-900/50'
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                {t.label}
              </button>
            );
          })}
        </div>

        {/* TAB BODY */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4 text-xs">
          {tabError && (
            <div className="bg-rose-950/60 border border-rose-500/40 text-rose-200 p-3 rounded-lg">
              {tabError}
            </div>
          )}

          {tabLoading && (
            <div className="py-16 text-center text-slate-400">
              <RefreshCw className="w-6 h-6 text-indigo-400 animate-spin mx-auto mb-2" />
              Loading investigation telemetry...
            </div>
          )}

          {/* TAB 1: GENERAL */}
          {!tabLoading && activeTab === 'GENERAL' && generalData && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              <DetailSection title="Transaction Information">
                <KVRow label="Transaction ID" value={generalData.transaction_info.transaction_reference} mono />
                <KVRow label="Internal UUID" value={generalData.transaction_info.transaction_id} mono />
                <KVRow label="Date & Time" value={`${generalData.transaction_info.transaction_date} ${generalData.transaction_info.transaction_time}`} mono />
                <KVRow label="Transaction Type" value={generalData.transaction_info.transaction_type} />
                <KVRow label="MTI / Proc Code" value={`${generalData.transaction_info.mti} / ${generalData.transaction_info.processing_code}`} mono />
                <KVRow label="Processing System" value={`${generalData.transaction_info.processing_system} (${generalData.transaction_info.is_on_us ? 'On-Us' : 'Off-Us'})`} />
                <KVRow label="Transaction Status" value={generalData.transaction_info.transaction_status} />
                <KVRow label="Channel" value={generalData.transaction_info.transaction_channel} />
                <KVRow label="Source Application" value={generalData.transaction_info.source_application} />
                <KVRow label="Correlation ID" value={generalData.transaction_info.correlation_id} mono />
              </DetailSection>

              <DetailSection
                title="Card Information"
                action={
                  generalData.card_info.full_pan_available && (
                    <button
                      type="button"
                      onClick={() => setRevealPan((v) => !v)}
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-[11px] text-indigo-300"
                    >
                      {revealPan ? <Lock className="w-3 h-3" /> : <Unlock className="w-3 h-3" />}
                      {revealPan ? 'Mask PAN' : 'Simulator Reveal PAN'}
                    </button>
                  )
                }
              >
                <KVRow label="PAN" value={generalData.card_info.pan} mono />
                <KVRow label="BIN (First 6)" value={generalData.card_info.bin} mono />
                <KVRow label="Card Type" value={generalData.card_info.card_type} />
                <KVRow label="Card Product" value={generalData.card_info.card_product} />
                <KVRow label="Expiry Date" value={generalData.card_info.expiry_date} mono />
                <KVRow label="Card Status" value={generalData.card_info.card_status} />
                <KVRow label="Cardholder Name" value={generalData.card_info.cardholder_name || '—'} />
                <KVRow label="Customer Name" value={generalData.card_info.customer_name || '—'} />
                <KVRow label="Customer ID (CIF)" value={generalData.card_info.customer_id || '—'} mono />
              </DetailSection>

              <DetailSection title="Account Information">
                <KVRow label="Source Account" value={generalData.account_info.source_account || '—'} mono />
                <KVRow label="Destination Account" value={generalData.account_info.destination_account || '—'} mono />
                <KVRow label="Account Type" value={generalData.account_info.account_type || '—'} />
                <KVRow label="Account Currency" value={generalData.account_info.account_currency || '—'} mono />
                <KVRow label="Account Status" value={generalData.account_info.account_status || '—'} />
                <KVRow label="Branch Code" value={generalData.account_info.branch_code || '—'} mono />
              </DetailSection>

              <DetailSection title="Merchant & Terminal Information">
                <KVRow label="Merchant ID (F32)" value={generalData.merchant_terminal_info.merchant_id || '—'} mono />
                <KVRow label="Merchant Name" value={generalData.merchant_terminal_info.merchant_name || '—'} />
                <KVRow label="MCC (F18)" value={generalData.merchant_terminal_info.mcc || '—'} mono />
                <KVRow label="POS Entry / Cond" value={`${generalData.merchant_terminal_info.pos_entry_mode} / ${generalData.merchant_terminal_info.pos_condition_code}`} mono />
                <KVRow label="Terminal ID (F41)" value={generalData.merchant_terminal_info.terminal_id || '—'} mono />
                <KVRow label="Terminal Name" value={generalData.merchant_terminal_info.terminal_name || '—'} />
                <KVRow label="Terminal Owner" value={generalData.merchant_terminal_info.terminal_owner || '—'} />
                <KVRow label="Acquirer" value={generalData.merchant_terminal_info.acquirer} />
                <KVRow label="Issuer" value={generalData.merchant_terminal_info.issuer} />
              </DetailSection>

              <DetailSection title="Financial Information">
                <KVRow
                  label="Transaction Amount"
                  value={`${Number(generalData.financial_info.transaction_amount).toLocaleString(undefined, { minimumFractionDigits: 2 })} ${generalData.financial_info.transaction_currency}`}
                  mono
                />
                <KVRow
                  label="Billing Amount"
                  value={`${Number(generalData.financial_info.billing_amount).toLocaleString(undefined, { minimumFractionDigits: 2 })} ${generalData.financial_info.billing_currency}`}
                  mono
                />
                <KVRow label="Transaction Currency" value={generalData.financial_info.transaction_currency} mono />
                <KVRow label="Billing Currency" value={generalData.financial_info.billing_currency} mono />
                <KVRow label="Exchange Rate" value={generalData.financial_info.exchange_rate} mono />
                <KVRow label="Fee Amount" value={String(generalData.financial_info.fee)} mono />
              </DetailSection>

              <DetailSection title="Network Reference Information">
                <KVRow label="RRN (F37)" value={generalData.network_reference_info.rrn} mono />
                <KVRow label="STAN (F11)" value={generalData.network_reference_info.stan} mono />
                <KVRow label="Approval Code (F38)" value={generalData.network_reference_info.approval_code} mono />
                <KVRow label="Acquirer Ref (F32)" value={generalData.network_reference_info.acquirer_reference} mono />
                <KVRow label="Forwarding Ref (F33)" value={generalData.network_reference_info.forwarding_reference || '—'} mono />
                <KVRow label="Switch Reference" value={generalData.network_reference_info.network_transaction_reference} mono />
              </DetailSection>
            </div>
          )}

          {/* TAB 2: AUTHORIZER RESPONSE */}
          {!tabLoading && activeTab === 'AUTHORIZATION' && authData && (
            <div className="space-y-4">
              <div
                className={`p-4 rounded-xl border ${
                  authData.authorization_status === 'APPROVED'
                    ? 'bg-emerald-950/30 border-emerald-500/40'
                    : 'bg-rose-950/30 border-rose-500/40'
                }`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <div className="text-[11px] uppercase tracking-wider text-slate-400">
                      Authorization Decision
                    </div>
                    <div className="text-base font-bold text-white mt-0.5">
                      {authData.authorization_decision}
                    </div>
                    <div className="text-xs text-slate-300 mt-1">
                      <strong>Reason / Explanation:</strong> {authData.decline_reason}
                    </div>
                  </div>
                  <div className="text-right font-mono">
                    <div className="text-xs text-slate-400">
                      RC: <strong className="text-white">{authData.response_code}</strong> (TIC F39:{' '}
                      {authData.response_tic_f39})
                    </div>
                    <div className="text-xs text-slate-400 mt-0.5">
                      Duration: <strong className="text-indigo-300">{authData.timestamps.processing_duration_ms} ms</strong>
                    </div>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <DetailSection title="Status & Balance at Authorization">
                  <KVRow label="Card Status Check" value={authData.card_status_at_auth} />
                  <KVRow label="Account Status Check" value={authData.account_status_at_auth} />
                  <KVRow
                    label="Balance Before"
                    value={
                      authData.balance_snapshot.balance_before !== null && authData.balance_snapshot.balance_before !== undefined
                        ? `${Number(authData.balance_snapshot.balance_before).toLocaleString(undefined, { minimumFractionDigits: 2 })} ${authData.balance_snapshot.currency}`
                        : 'Not modified'
                    }
                    mono
                  />
                  <KVRow
                    label="Balance After"
                    value={
                      authData.balance_snapshot.balance_after !== null && authData.balance_snapshot.balance_after !== undefined
                        ? `${Number(authData.balance_snapshot.balance_after).toLocaleString(undefined, { minimumFractionDigits: 2 })} ${authData.balance_snapshot.currency}`
                        : '—'
                    }
                    mono
                  />
                </DetailSection>

                <DetailSection title="Limits & Velocity Evaluation">
                  <KVRow
                    label="Card Per-Tx Limit"
                    value={authData.limits_evaluation.card_per_tx_limit ? Number(authData.limits_evaluation.card_per_tx_limit).toLocaleString() : '—'}
                    mono
                  />
                  <KVRow
                    label="Card Daily Limit"
                    value={authData.limits_evaluation.card_daily_limit ? Number(authData.limits_evaluation.card_daily_limit).toLocaleString() : '—'}
                    mono
                  />
                  <KVRow
                    label="Account Daily Limit"
                    value={authData.limits_evaluation.account_daily_limit ? Number(authData.limits_evaluation.account_daily_limit).toLocaleString() : '—'}
                    mono
                  />
                  <KVRow label="Limit Validation" value={authData.limits_evaluation.limit_validation_result} />
                </DetailSection>

                <DetailSection title="Routing & Timestamps">
                  <KVRow label="BIN Validation" value={authData.validation_results.bin_validation} />
                  <KVRow label="Switch Validation" value={authData.validation_results.processing_system_validation} />
                  <KVRow label="Auth Timestamp" value={authData.timestamps.authorization_timestamp || '—'} mono />
                  <KVRow label="Response Timestamp" value={authData.timestamps.response_timestamp || '—'} mono />
                </DetailSection>
              </div>

              {/* Ordered Pipeline Check Table */}
              <div className="bg-slate-950/70 border border-slate-800 rounded-xl overflow-hidden">
                <div className="px-4 py-2.5 border-b border-slate-800 font-semibold text-slate-200">
                  Executed Authorization Pipeline Checks ({authData.checks?.length || 0})
                </div>
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="bg-slate-900 text-slate-400 border-b border-slate-800">
                      <th className="py-2 px-3 w-12">#</th>
                      <th className="py-2 px-3">Check / Rule Stage</th>
                      <th className="py-2 px-3 text-center">Status</th>
                      <th className="py-2 px-3 text-center">RC</th>
                      <th className="py-2 px-3">Result Details</th>
                      <th className="py-2 px-3 text-right">Duration</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60">
                    {(authData.checks || []).map((c: any) => (
                      <tr key={c.check_order}>
                        <td className="py-2 px-3 font-mono text-slate-400">{c.check_order}</td>
                        <td className="py-2 px-3 font-semibold text-white">{c.check_name}</td>
                        <td className="py-2 px-3 text-center">
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                              c.check_status === 'PASSED'
                                ? 'bg-emerald-500/15 text-emerald-400'
                                : 'bg-rose-500/20 text-rose-400'
                            }`}
                          >
                            {c.check_status}
                          </span>
                        </td>
                        <td className="py-2 px-3 text-center font-mono">{c.response_code}</td>
                        <td className="py-2 px-3 text-slate-300">{c.message}</td>
                        <td className="py-2 px-3 text-right font-mono text-slate-400">{c.duration_ms} ms</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* TAB 3: ISO DETAILS (TIC DECODER) */}
          {!tabLoading && activeTab === 'ISO_DETAILS' && isoData && (
            <div className="space-y-4">
              {/* Message Selector & View Mode Toggle */}
              <div className="flex flex-wrap items-center justify-between gap-3 bg-slate-950/80 border border-slate-800 p-3 rounded-xl">
                <div className="flex items-center gap-2">
                  {(isoData.messages || []).map((m: any, idx: number) => (
                    <button
                      key={m.id}
                      type="button"
                      onClick={() => {
                        setSelectedMsgIdx(idx);
                        if (isoViewMode === 'COMPARE') setIsoViewMode('PARSED');
                      }}
                      className={`px-3 py-1.5 rounded-lg font-mono text-xs font-semibold transition ${
                        selectedMsgIdx === idx && isoViewMode !== 'COMPARE'
                          ? 'bg-indigo-600 text-white'
                          : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
                      }`}
                    >
                      {m.direction} (MTI {m.mti})
                    </button>
                  ))}
                  <button
                    type="button"
                    onClick={() => setIsoViewMode('COMPARE')}
                    className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
                      isoViewMode === 'COMPARE'
                        ? 'bg-amber-500 text-slate-950'
                        : 'bg-slate-800 text-amber-300 hover:bg-slate-700'
                    }`}
                  >
                    Request vs Response Comparison ({isoData.comparison?.length || 0} Fields)
                  </button>
                </div>

                {isoViewMode !== 'COMPARE' && isoData.messages?.[selectedMsgIdx] && (
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setIsoViewMode(isoViewMode === 'RAW' ? 'PARSED' : 'RAW')}
                      className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 font-medium"
                    >
                      {isoViewMode === 'RAW' ? 'Switch to Parsed Table' : 'Switch to Raw Wire View'}
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        copyText(
                          'FULL_MSG',
                          JSON.stringify(isoData.messages[selectedMsgIdx].decoded, null, 2)
                        )
                      }
                      className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200"
                    >
                      {copiedKey === 'FULL_MSG' ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                      Copy Parsed JSON
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        handleExportDecodedExcel(
                          isoData.messages[selectedMsgIdx].id,
                          isoData.messages[selectedMsgIdx].mti
                        )
                      }
                      className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border border-emerald-500/30 font-medium"
                    >
                      <FileSpreadsheet className="w-3.5 h-3.5" /> Export Excel/CSV
                    </button>
                  </div>
                )}
              </div>

              {/* SIDE-BY-SIDE COMPARISON VIEW */}
              {isoViewMode === 'COMPARE' ? (
                <div className="bg-slate-950/80 border border-slate-800 rounded-xl overflow-hidden">
                  <div className="px-4 py-2.5 border-b border-slate-800 font-semibold text-slate-200">
                    Side-by-Side ISO 8583 / TIC Request vs Response Field Comparison
                  </div>
                  <table className="w-full text-left border-collapse text-xs">
                    <thead>
                      <tr className="bg-slate-900 text-slate-400 border-b border-slate-800">
                        <th className="py-2 px-3 w-20">Field</th>
                        <th className="py-2 px-3 w-52">Field Name</th>
                        <th className="py-2 px-3">Request Value</th>
                        <th className="py-2 px-3">Response Value</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60 font-mono">
                      {(isoData.comparison || []).map((c: any) => (
                        <tr
                          key={c.field_number}
                          className={c.differs ? 'bg-amber-500/10' : ''}
                        >
                          <td className="py-2 px-3 font-bold text-indigo-300">{c.field_tag}</td>
                          <td className="py-2 px-3 font-sans text-slate-200">{c.field_name}</td>
                          <td className="py-2 px-3 text-slate-300 break-all">
                            {c.request_value ?? <span className="text-slate-600">N/A</span>}
                          </td>
                          <td className="py-2 px-3 text-emerald-300 break-all">
                            {c.response_value ?? <span className="text-slate-600">N/A</span>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                isoData.messages?.[selectedMsgIdx] && (() => {
                  const activeMsg = isoData.messages[selectedMsgIdx];
                  const dec = activeMsg.decoded || {};
                  const filteredFields = (dec.parsed_fields || []).filter((f: any) => {
                    if (!isoFieldSearch.trim()) return true;
                    const q = isoFieldSearch.toLowerCase();
                    return (
                      f.field_tag.toLowerCase().includes(q) ||
                      f.field_name.toLowerCase().includes(q) ||
                      String(f.display_value).toLowerCase().includes(q)
                    );
                  });

                  return (
                    <div className="space-y-3">
                      {/* Header & Bitmap Summary */}
                      <div className="grid grid-cols-1 md:grid-cols-4 gap-3 bg-slate-950/60 border border-slate-800 rounded-xl p-3 font-mono">
                        <div>
                          <div className="text-[10px] uppercase text-slate-400 font-sans">Header & Format</div>
                          <div className="text-xs text-white mt-0.5">
                            {dec.format} · H1={dec.header?.['H1 Start Indicator'] || 'A4M'} H2={dec.header?.['H2 Protocol Version'] || '02'} H3={dec.header?.['H3 Reject Status'] || '000'}
                          </div>
                        </div>
                        <div>
                          <div className="text-[10px] uppercase text-slate-400 font-sans">MTI</div>
                          <div className="text-xs text-indigo-300 font-bold mt-0.5">
                            {dec.mti} — {dec.mti_description}
                          </div>
                        </div>
                        <div>
                          <div className="text-[10px] uppercase text-slate-400 font-sans">Primary Bitmap (Hex)</div>
                          <div className="text-xs text-emerald-300 mt-0.5">{dec.primary_bitmap || '—'}</div>
                        </div>
                        <div>
                          <div className="text-[10px] uppercase text-slate-400 font-sans">Secondary Bitmap (F1)</div>
                          <div className="text-xs text-amber-300 mt-0.5">
                            {dec.secondary_bitmap || '— Not present'}
                          </div>
                        </div>
                      </div>

                      {/* Warnings / Parse Errors */}
                      {(dec.warnings?.length > 0 || Object.keys(dec.parse_errors || {}).length > 0) && (
                        <div className="bg-amber-950/40 border border-amber-500/40 rounded-lg p-3 text-amber-200 space-y-1">
                          {(dec.warnings || []).map((w: string, i: number) => (
                            <div key={i}>⚠ {w}</div>
                          ))}
                          {Object.entries(dec.parse_errors || {}).map(([k, v]) => (
                            <div key={k} className="text-rose-300">
                              🔴 Parse Error ({k}): {String(v)}
                            </div>
                          ))}
                        </div>
                      )}

                      {isoViewMode === 'RAW' ? (
                        <div className="space-y-3">
                          <div className="bg-slate-950 border border-slate-800 rounded-xl p-4">
                            <div className="text-[11px] font-semibold uppercase text-slate-400 mb-1.5">
                              Sanitized Raw Wire Frame
                            </div>
                            <pre className="font-mono text-xs text-emerald-300 whitespace-pre-wrap break-all">
                              {activeMsg.raw_message}
                            </pre>
                          </div>
                          {dec.compact_tic && (
                            <div className="bg-slate-950 border border-amber-500/30 rounded-xl p-4">
                              <div className="text-[11px] font-semibold uppercase text-amber-400 mb-1.5">
                                Compass Plus TIC Compact Format (Ý / ³ Delimiters)
                              </div>
                              <pre className="font-mono text-xs text-amber-200 whitespace-pre-wrap break-all">
                                {dec.compact_tic}
                              </pre>
                            </div>
                          )}
                        </div>
                      ) : (
                        <div className="bg-slate-950/80 border border-slate-800 rounded-xl overflow-hidden">
                          <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5 border-b border-slate-800">
                            <span className="font-semibold text-slate-200">
                              Parsed Fields (Ascending Numeric Order · {filteredFields.length} Fields)
                            </span>
                            <input
                              type="text"
                              value={isoFieldSearch}
                              onChange={(e) => setIsoFieldSearch(e.target.value)}
                              placeholder="Search field number, name, or value..."
                              className="w-64 bg-slate-900 border border-slate-700 rounded px-2.5 py-1 text-xs text-slate-200"
                            />
                          </div>
                          <table className="w-full text-left border-collapse text-xs">
                            <thead>
                              <tr className="bg-slate-900 text-slate-400 border-b border-slate-800">
                                <th className="py-2 px-3 w-20">Field</th>
                                <th className="py-2 px-3 w-56">Field Name</th>
                                <th className="py-2 px-3 w-56">Subfield / Key</th>
                                <th className="py-2 px-3">Decoded Value</th>
                                <th className="py-2 px-3 w-20 text-right">Copy</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-800/60 font-mono">
                              {filteredFields.map((f: any) => {
                                const subs = f.subfields || [{ key: f.field_name, value: f.display_value }];
                                const isMulti = subs.length > 1;
                                const isExp = expandedFields[f.field_number] ?? true;
                                return (
                                  <React.Fragment key={f.field_number}>
                                    {subs.map((sub: any, sIdx: number) => {
                                      if (sIdx > 0 && !isExp) return null;
                                      return (
                                        <tr key={`${f.field_number}-${sIdx}`} className="hover:bg-slate-900/50">
                                          <td className="py-2 px-3 font-bold text-indigo-300">
                                            {sIdx === 0 ? (
                                              <div className="flex items-center gap-1">
                                                <span>{f.field_tag}</span>
                                                {isMulti && (
                                                  <button
                                                    type="button"
                                                    onClick={() =>
                                                      setExpandedFields({
                                                        ...expandedFields,
                                                        [f.field_number]: !isExp,
                                                      })
                                                    }
                                                    className="text-[10px] px-1 rounded bg-slate-800 text-slate-400"
                                                  >
                                                    {isExp ? '−' : `+${subs.length}`}
                                                  </button>
                                                )}
                                              </div>
                                            ) : (
                                              ''
                                            )}
                                          </td>
                                          <td className="py-2 px-3 font-sans font-semibold text-slate-200">
                                            {sIdx === 0 ? f.field_name : ''}
                                          </td>
                                          <td className="py-2 px-3 font-sans text-slate-400">{sub.key}</td>
                                          <td className="py-2 px-3 text-emerald-300 break-all">{sub.value}</td>
                                          <td className="py-2 px-3 text-right">
                                            <button
                                              type="button"
                                              onClick={() => copyText(`${f.field_number}-${sIdx}`, String(sub.value))}
                                              className="p-1 rounded hover:bg-slate-800 text-slate-400 hover:text-white"
                                              title="Copy field value"
                                            >
                                              {copiedKey === `${f.field_number}-${sIdx}` ? (
                                                <Check className="w-3.5 h-3.5 text-emerald-400" />
                                              ) : (
                                                <Copy className="w-3.5 h-3.5" />
                                              )}
                                            </button>
                                          </td>
                                        </tr>
                                      );
                                    })}
                                  </React.Fragment>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>
                  );
                })()
              )}
            </div>
          )}

          {/* TAB 4: KEYS & CRYPTO */}
          {!tabLoading && activeTab === 'CRYPTO' && cryptoData && (
            <div className="space-y-4">
              <div className="flex items-center justify-between bg-slate-950/80 border border-slate-800 rounded-xl p-3">
                <div>
                  <div className="text-xs font-bold text-white">
                    HSM Provider: {cryptoData.hsm_provider} ({cryptoData.hsm_mode})
                  </div>
                  <div className="text-[11px] text-slate-400">
                    All clear keys, PIN blocks, PVV/offsets, and CVVs are masked per PCI-DSS host security policy.
                  </div>
                </div>
                <span className="px-2.5 py-1 rounded bg-indigo-500/15 text-indigo-300 font-mono text-xs font-semibold">
                  {cryptoData.operations_count} Cryptographic Operation(s)
                </span>
              </div>

              {cryptoData.operations_count === 0 ? (
                <div className="bg-slate-950/60 border border-slate-800 rounded-xl p-8 text-center text-slate-400">
                  No HSM cryptographic operations were required or executed for this transaction.
                </div>
              ) : (
                <div className="space-y-3">
                  {(cryptoData.operations || []).map((op: any) => (
                    <div
                      key={op.operation_id}
                      className="bg-slate-950/80 border border-slate-800 rounded-xl p-4 space-y-3"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-2.5">
                        <div className="flex items-center gap-2">
                          <Key className="w-4 h-4 text-amber-400" />
                          <span className="font-bold text-white">{op.hsm_operation}</span>
                          <span className="text-slate-400">({op.operation_category})</span>
                        </div>
                        <div className="flex items-center gap-2 font-mono">
                          <span
                            className={`px-2 py-0.5 rounded text-[11px] font-bold ${
                              op.cryptographic_result === 'APPROVED'
                                ? 'bg-emerald-500/15 text-emerald-400'
                                : 'bg-rose-500/20 text-rose-400'
                            }`}
                          >
                            {op.cryptographic_result} (HSM RC {op.hsm_response_code})
                          </span>
                          <span className="text-slate-400">{op.duration_ms} ms</span>
                        </div>
                      </div>

                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                        <KVRow label="Key Alias / Ref" value={op.key_alias} mono />
                        <KVRow label="Key Type & Usage" value={`${op.key_type} · ${op.key_usage}`} />
                        <KVRow label="Key Scheme & KVC" value={`${op.key_scheme} (KVC ${op.kvc})`} mono />
                        <KVRow label="LMK Reference" value={op.hsm_key_reference} mono />
                        <KVRow label="Request Ref" value={op.request_reference} mono />
                        <KVRow label="Audit Ref" value={op.audit_reference || '—'} mono />
                        <KVRow label="HSM Device" value={op.hsm_connection} />
                        <KVRow label="Timestamp" value={op.request_timestamp || '—'} mono />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* TAB 5: PROCESSING TRACE */}
          {activeTab === 'TRACE' && (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-2 bg-slate-950/80 border border-slate-800 rounded-xl p-3.5">
                <div>
                  <div className="text-xs font-bold text-white">
                    Switch Pipeline Transaction Processing Trace
                  </div>
                  <div className="text-[11px] text-slate-400">
                    Loads actual recorded pipeline stage events from the host database without re-executing authorization or HSM calls.
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={handleGenerateOrLoadTrace}
                    disabled={tabLoading}
                    className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded bg-indigo-600 hover:bg-indigo-500 text-white font-semibold transition shadow"
                  >
                    <Sparkles className="w-3.5 h-3.5" />
                    {traceData ? 'Refresh Trace' : 'Generate / Load Transaction Trace'}
                  </button>

                  {traceData && (
                    <>
                      <button
                        type="button"
                        onClick={() => copyText('TRACE_TXT', traceData.formatted_trace)}
                        className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-200"
                      >
                        {copiedKey === 'TRACE_TXT' ? (
                          <Check className="w-3.5 h-3.5 text-emerald-400" />
                        ) : (
                          <Copy className="w-3.5 h-3.5" />
                        )}
                        Copy Trace
                      </button>
                      <button
                        type="button"
                        onClick={handleDownloadTraceTxt}
                        className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border border-emerald-500/30"
                      >
                        <Download className="w-3.5 h-3.5" /> Download TXT
                      </button>
                      <button
                        type="button"
                        onClick={() => setTraceData(null)}
                        className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-400"
                      >
                        Clear Display
                      </button>
                    </>
                  )}
                </div>
              </div>

              {!traceData && !tabLoading && (
                <div className="bg-slate-950/60 border border-dashed border-slate-800 rounded-xl py-14 text-center space-y-3">
                  <Terminal className="w-8 h-8 text-indigo-400 mx-auto" />
                  <div className="text-sm font-semibold text-slate-200">
                    Click [ Generate / Load Transaction Trace ] above to inspect the stage-by-stage execution log
                  </div>
                  <p className="text-xs text-slate-500 max-w-md mx-auto">
                    Displays exact timestamps, stage durations, and validation outcomes recorded during the transaction lifecycle.
                  </p>
                </div>
              )}

              {traceData && (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  {/* Formatted Switch Log Output */}
                  <div className="bg-slate-950 border border-slate-800 rounded-xl p-4 overflow-x-auto">
                    <div className="text-[11px] font-semibold uppercase tracking-wider text-indigo-400 mb-2">
                      Switch Investigation Trace Output
                    </div>
                    <pre className="font-mono text-xs text-emerald-300 leading-relaxed whitespace-pre-wrap">
                      {traceData.formatted_trace}
                    </pre>
                  </div>

                  {/* Structured Timeline Cards */}
                  <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-4 space-y-2.5">
                    <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-300 mb-2">
                      Structured Stage Timeline ({traceData.events?.length || 0} Stages · Total {traceData.total_duration_ms} ms)
                    </div>
                    {(traceData.events || []).map((ev: any) => (
                      <div
                        key={ev.event_order}
                        className="p-2.5 rounded-lg bg-slate-900/90 border border-slate-800 flex items-start justify-between gap-2"
                      >
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-[11px] text-indigo-400 font-bold">
                              #{ev.event_order}
                            </span>
                            <span className="font-bold text-white">{ev.event_name}</span>
                            <span className="text-[10px] px-1.5 py-0.2 rounded bg-slate-800 text-slate-400 font-mono">
                              {ev.event_category}
                            </span>
                          </div>
                          <div className="text-slate-300 mt-1">{ev.message}</div>
                        </div>
                        <div className="text-right font-mono shrink-0">
                          <span
                            className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                              ev.event_status === 'PASSED' || ev.event_status === 'APPROVED'
                                ? 'bg-emerald-500/15 text-emerald-400'
                                : 'bg-rose-500/20 text-rose-400'
                            }`}
                          >
                            {ev.event_status}
                          </span>
                          <div className="text-[11px] text-slate-500 mt-1">{ev.duration_ms} ms</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* TAB 6: RELATED TRANSACTIONS */}
          {!tabLoading && activeTab === 'RELATED' && relatedData && (
            <div className="space-y-3">
              <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-3 flex items-center justify-between">
                <div>
                  <div className="text-xs font-bold text-white">
                    Linked Lifecycle &amp; Related Transactions (RRN {relatedData.rrn} / STAN {relatedData.stan})
                  </div>
                  <div className="text-[11px] text-slate-400">
                    Linked strictly by Original Transaction FK, Reversal Registry, RRN/STAN, or Correlation ID.
                  </div>
                </div>
                <span className="px-2.5 py-1 rounded bg-indigo-500/15 text-indigo-300 font-mono text-xs font-semibold">
                  {relatedData.related_count} Linked Record(s)
                </span>
              </div>

              {relatedData.related_count === 0 ? (
                <div className="bg-slate-950/60 border border-slate-800 rounded-xl p-8 text-center text-slate-400">
                  No reversals, clearing advices, or duplicate transmissions are linked to this transaction.
                </div>
              ) : (
                <div className="bg-slate-950/80 border border-slate-800 rounded-xl overflow-hidden">
                  <table className="w-full text-left border-collapse text-xs">
                    <thead>
                      <tr className="bg-slate-900 text-slate-400 border-b border-slate-800">
                        <th className="py-2.5 px-3">Relationship</th>
                        <th className="py-2.5 px-3">Txn ID</th>
                        <th className="py-2.5 px-3">Date / Time</th>
                        <th className="py-2.5 px-3 text-center">MTI</th>
                        <th className="py-2.5 px-3">Type</th>
                        <th className="py-2.5 px-3">RRN / STAN</th>
                        <th className="py-2.5 px-3 text-right">Amount</th>
                        <th className="py-2.5 px-3 text-center">Status</th>
                        <th className="py-2.5 px-3">Link Basis</th>
                        <th className="py-2.5 px-3 text-right">Open</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60 font-mono">
                      {(relatedData.related_transactions || []).map((rt: any) => (
                        <tr key={rt.id} className="hover:bg-slate-900/60">
                          <td className="py-2 px-3 font-sans">
                            <span className="px-2 py-0.5 rounded bg-indigo-500/15 text-indigo-300 font-semibold text-[11px]">
                              {rt.relationship_type}
                            </span>
                          </td>
                          <td className="py-2 px-3 text-white font-semibold">{rt.transaction_reference}</td>
                          <td className="py-2 px-3 text-slate-300">
                            {rt.date} {rt.time}
                          </td>
                          <td className="py-2 px-3 text-center text-indigo-300">{rt.mti}</td>
                          <td className="py-2 px-3 font-sans text-slate-200">{rt.transaction_type}</td>
                          <td className="py-2 px-3 text-slate-300">
                            {rt.rrn} / {rt.stan}
                          </td>
                          <td className="py-2 px-3 text-right text-white font-semibold">
                            {Number(rt.amount).toLocaleString(undefined, { minimumFractionDigits: 2 })} {rt.currency}
                          </td>
                          <td className="py-2 px-3 text-center font-sans">
                            <StatusBadge status={rt.status} />
                          </td>
                          <td className="py-2 px-3 font-sans text-slate-400">{rt.link_basis}</td>
                          <td className="py-2 px-3 text-right font-sans">
                            <button
                              type="button"
                              onClick={() => onSelectRelatedTx(rt.id)}
                              className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-indigo-600 hover:bg-indigo-500 text-white text-[11px] font-semibold"
                            >
                              Open <ExternalLink className="w-3 h-3" />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

// Helper UI Subcomponents
const DetailSection: React.FC<{
  title: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}> = ({ title, action, children }) => (
  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5 space-y-2">
    <div className="flex items-center justify-between border-b border-slate-800/80 pb-2">
      <h4 className="text-xs font-bold uppercase tracking-wider text-indigo-400">{title}</h4>
      {action}
    </div>
    <div className="space-y-1.5">{children}</div>
  </div>
);

const KVRow: React.FC<{ label: string; value: React.ReactNode; mono?: boolean }> = ({
  label,
  value,
  mono,
}) => (
  <div className="flex items-start justify-between gap-2 text-xs">
    <span className="text-slate-400 shrink-0">{label}:</span>
    <span className={`text-right text-slate-200 break-all ${mono ? 'font-mono font-medium' : ''}`}>
      {value ?? '—'}
    </span>
  </div>
);

export default TransactionLogViewerPage;
