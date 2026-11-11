"""
patch_5_frontend_host_control.py
Run in the project folder:   python patch_5_frontend_host_control.py
Adds the Host Control Center (menu 14): Local Host policy per bank, Algo Control (Python / SQL blocks with a
Fields Reference button, templates, test run, versions, execution log), the old Host Configuration table as the
"Authorization Rules" tab, and CBS / External Host placeholders. Needs patch 4 (backend) first.
Idempotent. Backups go to _backups/.
"""

PATCH_NAME = "patch5_hostcontrol"

HC_UI_TSX = r'''import React, { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react';
import { X } from 'lucide-react';

// ============================================================================
// Shared UI for the Rajon Host Control Center
// ============================================================================

export const inputCls =
  'w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs focus:ring-2 focus:ring-emerald-500/40 focus:border-emerald-500 outline-none disabled:opacity-50';
export const panelCls = 'bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl';

export const fmtNum = (v: any, d = 2) =>
  Number(v ?? 0).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: d });
export const fmtTime = (iso?: string | null) => {
  if (!iso) return '—';
  const d = new Date(iso);
  return isNaN(d.getTime()) ? String(iso) : d.toLocaleString();
};
export const ago = (iso?: string | null) => {
  if (!iso) return 'never';
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return `${Math.floor(s)}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
};

// ---------------------------------------------------------------- Toggle
export const Toggle: React.FC<{
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
  label?: string;
  title?: string;
}> = ({ checked, onChange, disabled, label, title }) => (
  <button
    type="button"
    role="switch"
    aria-checked={checked}
    aria-label={label || title || 'toggle'}
    title={title}
    disabled={disabled}
    onClick={() => onChange(!checked)}
    className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors ${
      checked ? 'bg-emerald-500' : 'bg-slate-300 dark:bg-slate-700'
    } ${disabled ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer'}`}
  >
    <span
      className={`inline-block h-4 w-4 rounded-full bg-white shadow transition-transform ${
        checked ? 'translate-x-[18px]' : 'translate-x-0.5'
      }`}
    />
  </button>
);

// ---------------------------------------------------------------- Badge
const TONES: Record<string, string> = {
  emerald: 'bg-emerald-500/15 text-emerald-500 border-emerald-500/25',
  rose: 'bg-rose-500/15 text-rose-500 border-rose-500/25',
  amber: 'bg-amber-500/15 text-amber-500 border-amber-500/25',
  sky: 'bg-sky-500/15 text-sky-500 border-sky-500/25',
  violet: 'bg-violet-500/15 text-violet-400 border-violet-500/25',
  slate: 'bg-slate-500/15 text-slate-400 border-slate-500/25',
};
export const Badge: React.FC<{ tone?: keyof typeof TONES | string; children: React.ReactNode; title?: string }> = ({
  tone = 'slate',
  children,
  title,
}) => (
  <span
    title={title}
    className={`inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full border font-bold tracking-wide ${
      TONES[tone] || TONES.slate
    }`}
  >
    {children}
  </span>
);

// ---------------------------------------------------------------- segmented buttons
export function SegButtons<T extends string>({
  options,
  value,
  onChange,
  disabled,
}: {
  options: { value: T; label: string; tone?: 'emerald' | 'amber' | 'rose' | 'sky' }[];
  value: T;
  onChange: (v: T) => void;
  disabled?: boolean;
}) {
  const active: Record<string, string> = {
    emerald: 'bg-emerald-600 text-white shadow shadow-emerald-600/30',
    amber: 'bg-amber-500 text-white shadow shadow-amber-500/30',
    rose: 'bg-rose-600 text-white shadow shadow-rose-600/30',
    sky: 'bg-sky-600 text-white shadow shadow-sky-600/30',
  };
  return (
    <div className={`inline-flex p-1 rounded-xl bg-slate-100 dark:bg-slate-800 gap-1 ${disabled ? 'opacity-50' : ''}`}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          disabled={disabled}
          onClick={() => onChange(o.value)}
          className={`px-3 py-1.5 rounded-lg text-[11px] font-semibold transition-all ${
            value === o.value
              ? active[o.tone || 'emerald']
              : 'text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- chip input
export const ChipInput: React.FC<{
  values: string[];
  onChange: (v: string[]) => void;
  placeholder?: string;
  disabled?: boolean;
  suggestions?: { value: string; label?: string }[];
  tone?: string;
}> = ({ values, onChange, placeholder, disabled, suggestions, tone = 'sky' }) => {
  const [text, setText] = useState('');
  const add = (raw: string) => {
    const parts = raw
      .split(/[,\s]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (!parts.length) return;
    const next = [...values];
    parts.forEach((p) => {
      if (!next.includes(p)) next.push(p);
    });
    onChange(next);
    setText('');
  };
  const free = (suggestions || []).filter((s) => !values.includes(s.value)).slice(0, 6);
  return (
    <div>
      <div
        className={`flex flex-wrap items-center gap-1.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-950 px-2 py-1.5 min-h-[34px] ${
          disabled ? 'opacity-50' : ''
        }`}
      >
        {values.map((v) => (
          <span
            key={v}
            className={`inline-flex items-center gap-1 text-[11px] font-mono px-2 py-0.5 rounded-md ${TONES[tone] || TONES.sky} border`}
          >
            {v}
            {!disabled && (
              <button
                type="button"
                aria-label={`remove ${v}`}
                onClick={() => onChange(values.filter((x) => x !== v))}
                className="opacity-60 hover:opacity-100"
              >
                <X size={11} />
              </button>
            )}
          </span>
        ))}
        {!disabled && (
          <input
            value={text}
            placeholder={values.length ? '' : placeholder || 'type and press Enter'}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ',') {
                e.preventDefault();
                add(text);
              } else if (e.key === 'Backspace' && !text && values.length) {
                onChange(values.slice(0, -1));
              }
            }}
            onBlur={() => add(text)}
            className="flex-1 min-w-[80px] bg-transparent outline-none text-xs font-mono"
          />
        )}
      </div>
      {!disabled && free.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-1.5">
          {free.map((s) => (
            <button
              key={s.value}
              type="button"
              onClick={() => add(s.value)}
              title={s.label}
              className="text-[10px] px-1.5 py-0.5 rounded bg-slate-500/10 text-slate-400 hover:bg-slate-500/20 font-mono"
            >
              + {s.value}
              {s.label ? ` ${s.label}` : ''}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

// ---------------------------------------------------------------- form bits
export const Labeled: React.FC<{ label: string; hint?: string; className?: string; children: React.ReactNode }> = ({
  label,
  hint,
  className,
  children,
}) => (
  <label className={`block space-y-1 ${className || ''}`}>
    <span className="text-[11px] text-slate-400 font-medium">{label}</span>
    {children}
    {hint && <span className="block text-[10px] text-slate-500">{hint}</span>}
  </label>
);

export const NumInput: React.FC<{
  value: any;
  onChange: (v: number) => void;
  disabled?: boolean;
  placeholder?: string;
  ariaLabel?: string;
}> = ({ value, onChange, disabled, placeholder, ariaLabel }) => (
  <input
    type="number"
    min={0}
    step="any"
    aria-label={ariaLabel}
    disabled={disabled}
    placeholder={placeholder ?? '0 = no limit'}
    value={value === 0 || value === undefined || value === null ? '' : value}
    onChange={(e) => onChange(e.target.value === '' ? 0 : Math.max(0, Number(e.target.value)))}
    className={`${inputCls} font-mono`}
  />
);

export const RcSelect: React.FC<{
  value: string;
  onChange: (v: string) => void;
  codes: { code: string; description: string }[];
  disabled?: boolean;
  ariaLabel?: string;
}> = ({ value, onChange, codes, disabled, ariaLabel }) => {
  const list = useMemo(() => {
    const has = codes.some((c) => c.code === value);
    return has || !value ? codes : [{ code: value, description: '' }, ...codes];
  }, [codes, value]);
  return (
    <select
      aria-label={ariaLabel}
      disabled={disabled}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={`${inputCls} font-mono`}
    >
      {list.map((c) => (
        <option key={c.code} value={c.code}>
          {c.code}
          {c.description ? ` - ${c.description}` : ''}
        </option>
      ))}
    </select>
  );
};

// ---------------------------------------------------------------- card section
export const SectionCard: React.FC<{
  icon: React.ReactNode;
  title: string;
  subtitle?: string;
  right?: React.ReactNode;
  dim?: boolean;
  children: React.ReactNode;
}> = ({ icon, title, subtitle, right, dim, children }) => (
  <section className={`${panelCls} overflow-hidden ${dim ? 'opacity-90' : ''}`}>
    <header className="flex flex-wrap items-center gap-3 px-5 py-3.5 border-b border-slate-200 dark:border-slate-800 bg-gradient-to-r from-slate-50 to-transparent dark:from-slate-800/40">
      <div className="w-8 h-8 rounded-xl bg-emerald-500/10 text-emerald-500 flex items-center justify-center shrink-0">{icon}</div>
      <div className="min-w-0">
        <h3 className="text-sm font-bold">{title}</h3>
        {subtitle && <p className="text-[11px] text-slate-400 leading-snug">{subtitle}</p>}
      </div>
      <div className="ml-auto flex items-center gap-2">{right}</div>
    </header>
    <div className={`p-5 ${dim ? 'pointer-events-none select-none opacity-60' : ''}`}>{children}</div>
  </section>
);

// ---------------------------------------------------------------- modal
export const Modal: React.FC<{
  title: React.ReactNode;
  onClose: () => void;
  size?: 'md' | 'lg' | 'xl';
  children: React.ReactNode;
}> = ({ title, onClose, size = 'md', children }) => (
  <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
    <div
      role="dialog"
      className={`${panelCls} w-full ${size === 'xl' ? 'max-w-5xl' : size === 'lg' ? 'max-w-3xl' : 'max-w-md'} max-h-[92vh] flex flex-col shadow-2xl`}
    >
      <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-200 dark:border-slate-800">
        <h2 className="text-sm font-bold">{title}</h2>
        <button type="button" aria-label="close" onClick={onClose} className="text-slate-400 hover:text-slate-200">
          <X size={16} />
        </button>
      </div>
      <div className="p-5 overflow-y-auto">{children}</div>
    </div>
  </div>
);

// ---------------------------------------------------------------- toast
export function useToast() {
  const [toast, setToast] = useState<{ text: string; error: boolean } | null>(null);
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), toast.error ? 9000 : 5000);
    return () => clearTimeout(t);
  }, [toast]);
  const show = useCallback((text: string, error = false) => setToast({ text, error }), []);
  const node = toast ? (
    <div
      role="status"
      className={`fixed bottom-5 right-5 z-[60] max-w-md flex items-start gap-2 px-4 py-3 rounded-xl shadow-2xl border text-xs font-mono ${
        toast.error
          ? 'bg-rose-950/95 border-rose-500/40 text-rose-200'
          : 'bg-emerald-950/95 border-emerald-500/40 text-emerald-200'
      }`}
    >
      <span className="flex-1 break-words">{toast.text}</span>
      <button type="button" aria-label="dismiss" onClick={() => setToast(null)} className="opacity-60 hover:opacity-100">
        <X size={13} />
      </button>
    </div>
  ) : null;
  return { show, node };
}

// ============================================================================
// Code editor with line numbers and light syntax colouring (Python / SQL)
// ============================================================================
export interface CodeEditorHandle {
  insertAtCursor: (text: string) => void;
  focus: () => void;
}

const PY_KW = new Set([
  'if', 'elif', 'else', 'for', 'in', 'not', 'and', 'or', 'return', 'True', 'False', 'None', 'def', 'lambda', 'try',
  'except', 'pass', 'break', 'continue', 'is',
]);
const PY_FN = new Set(['approve', 'decline', 'block_card', 'block_customer', 'flag', 'log', 'history', 'sql', 'now']);
const GROUPS = new Set(['tx', 'terminal', 'card', 'customer', 'account', 'bank', 'acquirer', 'profile', 'limits']);
const SQL_KW = new Set([
  'SELECT', 'FROM', 'WHERE', 'AND', 'OR', 'NOT', 'GROUP', 'BY', 'HAVING', 'ORDER', 'LIMIT', 'COUNT', 'DISTINCT', 'AS',
  'IN', 'IS', 'NULL', 'JOIN', 'LEFT', 'INNER', 'ON', 'WITH', 'CASE', 'WHEN', 'THEN', 'ELSE', 'END', 'SUM', 'MAX', 'MIN',
  'AVG', 'LIKE', 'BETWEEN', 'EXISTS', 'UNION', 'ALL', 'DESC', 'ASC', 'COALESCE',
]);

const TOKEN_RE = /(#[^\n]*|--[^\n]*)|('(?:[^'\\\n]|\\.)*'|"(?:[^"\\\n]|\\.)*")|(\b\d+(?:\.\d+)?\b)|(:[A-Za-z_]\w*)|([A-Za-z_]\w*)|(\s+)|([\s\S])/g;

export function highlightCode(code: string, language: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  const isSql = language === 'SQL';
  let i = 0;
  let m: RegExpExecArray | null;
  TOKEN_RE.lastIndex = 0;
  while ((m = TOKEN_RE.exec(code)) !== null) {
    const [tok, comment, str, numTok, param, ident] = m;
    let cls = '';
    if (comment) {
      const isComment = isSql ? comment.startsWith('--') : comment.startsWith('#');
      cls = isComment ? 'text-slate-500 italic' : '';
    } else if (str) cls = 'text-amber-300';
    else if (numTok) cls = 'text-violet-300';
    else if (param) cls = isSql ? 'text-emerald-300' : '';
    else if (ident) {
      const after = code[m.index + tok.length];
      if (isSql) {
        if (SQL_KW.has(ident.toUpperCase())) cls = 'text-sky-300 font-semibold';
      } else if (PY_KW.has(ident)) cls = 'text-sky-300 font-semibold';
      else if (PY_FN.has(ident)) cls = 'text-rose-300 font-semibold';
      else if (GROUPS.has(ident) && after === '.') cls = 'text-emerald-300';
    }
    out.push(
      cls ? (
        <span key={i++} className={cls}>
          {tok}
        </span>
      ) : (
        <React.Fragment key={i++}>{tok}</React.Fragment>
      )
    );
    if (tok.length === 0) TOKEN_RE.lastIndex++;
  }
  return out;
}

const LINE_H = 20; // px, shared by gutter, highlight layer and textarea

export const CodeEditor = forwardRef<
  CodeEditorHandle,
  {
    value: string;
    onChange: (v: string) => void;
    language: 'PYTHON' | 'SQL' | string;
    height?: number;
    readOnly?: boolean;
    placeholder?: string;
  }
>(({ value, onChange, language, height = 340, readOnly, placeholder }, ref) => {
  const taRef = useRef<HTMLTextAreaElement>(null);
  const [scroll, setScroll] = useState({ top: 0, left: 0 });
  const lines = Math.max(1, value.split('\n').length);

  useImperativeHandle(ref, () => ({
    focus: () => taRef.current?.focus(),
    insertAtCursor: (text: string) => {
      const ta = taRef.current;
      if (!ta) {
        onChange(value + text);
        return;
      }
      const s = ta.selectionStart ?? value.length;
      const e = ta.selectionEnd ?? value.length;
      onChange(value.slice(0, s) + text + value.slice(e));
      setTimeout(() => {
        ta.focus();
        ta.selectionStart = ta.selectionEnd = s + text.length;
      }, 0);
    },
  }));

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    const ta = e.currentTarget;
    if (e.key === 'Tab') {
      e.preventDefault();
      const s = ta.selectionStart;
      const en = ta.selectionEnd;
      onChange(value.slice(0, s) + '    ' + value.slice(en));
      setTimeout(() => {
        ta.selectionStart = ta.selectionEnd = s + 4;
      }, 0);
    } else if (e.key === 'Enter' && language !== 'SQL') {
      const s = ta.selectionStart;
      const lineStart = value.lastIndexOf('\n', s - 1) + 1;
      const line = value.slice(lineStart, s);
      const indent = (line.match(/^\s*/) || [''])[0];
      const extra = line.trimEnd().endsWith(':') ? '    ' : '';
      if (indent || extra) {
        e.preventDefault();
        const ins = '\n' + indent + extra;
        onChange(value.slice(0, s) + ins + value.slice(ta.selectionEnd));
        setTimeout(() => {
          ta.selectionStart = ta.selectionEnd = s + ins.length;
        }, 0);
      }
    }
  };

  const shared: React.CSSProperties = {
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
    fontSize: 12,
    lineHeight: `${LINE_H}px`,
    padding: '10px 12px',
    tabSize: 4,
    whiteSpace: 'pre',
  };

  return (
    <div
      className="relative flex rounded-xl border border-slate-700 bg-slate-950 overflow-hidden"
      style={{ height }}
      data-testid="code-editor"
    >
      <div
        aria-hidden
        className="select-none text-right text-slate-600 bg-slate-900/70 border-r border-slate-800 overflow-hidden shrink-0"
        style={{ width: 44, ...shared, whiteSpace: 'pre', padding: '10px 8px' }}
      >
        <div style={{ transform: `translateY(${-scroll.top}px)` }}>
          {Array.from({ length: lines }, (_, i) => (
            <div key={i}>{i + 1}</div>
          ))}
        </div>
      </div>
      <div className="relative flex-1 overflow-hidden">
        <pre
          aria-hidden
          className="absolute inset-0 m-0 text-slate-200 pointer-events-none overflow-hidden"
          style={shared}
        >
          <div style={{ transform: `translate(${-scroll.left}px, ${-scroll.top}px)` }}>
            {highlightCode(value, language)}
            {'\n '}
          </div>
        </pre>
        <textarea
          ref={taRef}
          aria-label="algo source code"
          spellCheck={false}
          readOnly={readOnly}
          value={value}
          placeholder={placeholder}
          wrap="off"
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKeyDown}
          onScroll={(e) => setScroll({ top: e.currentTarget.scrollTop, left: e.currentTarget.scrollLeft })}
          className="absolute inset-0 w-full h-full bg-transparent text-transparent caret-emerald-400 outline-none resize-none overflow-auto selection:bg-emerald-500/30"
          style={shared}
        />
      </div>
    </div>
  );
});
CodeEditor.displayName = 'CodeEditor';
'''

HC_LOCAL_TSX = r'''import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Banknote,
  Building2,
  CheckCircle2,
  Clock,
  Globe,
  Layers,
  ListChecks,
  Loader2,
  Monitor,
  Network,
  Plane,
  Play,
  Power,
  RotateCcw,
  Save,
  Search,
  ShieldAlert,
  Smartphone,
  Store,
  Tag,
  Timer,
  XCircle,
  Zap,
} from 'lucide-react';
import { apiFetch } from '../../api';
import {
  Badge,
  ChipInput,
  Labeled,
  NumInput,
  RcSelect,
  SectionCard,
  SegButtons,
  Toggle,
  fmtTime,
  inputCls,
  panelCls,
  useToast,
} from './ui';

// ============================================================================
// LOCAL HOST  - per bank transaction policy
// ============================================================================

const SECTION_ORDER = ['general', 'channels', 'sources', 'transactions', 'cross_border', 'mcc', 'acquirers', 'velocity'];

const CH_ICON: Record<string, React.ReactNode> = {
  ATM: <Banknote size={14} />,
  POS: <Store size={14} />,
  ECOM: <Globe size={14} />,
  MOBILE: <Smartphone size={14} />,
  INTERNET: <Monitor size={14} />,
  OTHER: <Layers size={14} />,
};
const CH_DESC: Record<string, string> = {
  ATM: 'Cash machines (MCC 6011 / ATM terminals)',
  POS: 'Physical card present terminals',
  ECOM: 'Card-not-present / online payments',
  MOBILE: 'Mobile banking and wallets',
  INTERNET: 'Internet banking',
  OTHER: 'Anything that is not recognised',
};
const COUNTRY_HINTS = [
  { value: '050', label: 'BD' }, { value: '356', label: 'IN' }, { value: '586', label: 'PK' }, { value: '840', label: 'US' },
  { value: '826', label: 'UK' }, { value: '784', label: 'AE' }, { value: '702', label: 'SG' }, { value: '458', label: 'MY' },
  { value: '156', label: 'CN' }, { value: '643', label: 'RU' },
];
const MCC_HINTS = [
  { value: '6011', label: 'ATM' }, { value: '7995', label: 'betting' }, { value: '4829', label: 'money transfer' },
  { value: '6051', label: 'crypto/quasi-cash' }, { value: '5967', label: 'adult direct mkt' }, { value: '5411', label: 'grocery' },
  { value: '5812', label: 'restaurants' }, { value: '4511', label: 'airlines' },
];

const STATUS_TONE: Record<string, string> = { ACTIVE: 'emerald', MAINTENANCE: 'amber', DECLINE_ALL: 'rose' };

const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v));

const DEFAULT_CH = { enabled: true, min_amount: 0, max_amount: 0 };
const DEFAULT_SRC = { enabled: true, max_amount: 0, allowed_tx_codes: [] as string[] };
const DEFAULT_TX = { enabled: true, channels: [] as string[], min_amount: 0, max_amount: 0 };

interface Props {
  meta: any;
  onChanged?: () => void;
}

export const LocalHostTab: React.FC<Props> = ({ meta, onChanged }) => {
  const { show, node: toastNode } = useToast();
  const [policies, setPolicies] = useState<any[]>([]);
  const [scope, setScope] = useState<string>('GLOBAL'); // 'GLOBAL' or bank id
  const [filter, setFilter] = useState('');
  const [eff, setEff] = useState<any | null>(null);
  const [globalEff, setGlobalEff] = useState<any | null>(null);
  const [draft, setDraft] = useState<Record<string, any>>({});
  const [ovr, setOvr] = useState<Record<string, boolean>>({});
  const [policyEnabled, setPolicyEnabled] = useState(true);
  const [snapshot, setSnapshot] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const isGlobal = scope === 'GLOBAL';
  const bank = (meta?.banks || []).find((b: any) => b.id === scope);
  const policyRow = policies.find((p) => (isGlobal ? p.scope_type === 'GLOBAL' : p.institution_id === scope));
  const rcs: { code: string; description: string }[] = meta?.response_codes || [];

  const loadPolicies = useCallback(async () => {
    try {
      setPolicies(await apiFetch('/local-host/policies'));
    } catch (e: any) {
      show(e.message || 'Could not load policies', true);
    }
  }, [show]);

  const loadScope = useCallback(
    async (key: string) => {
      setLoading(true);
      try {
        const g = await apiFetch('/local-host/policies/effective');
        setGlobalEff(g);
        const e = key === 'GLOBAL' ? g : await apiFetch(`/local-host/policies/effective?institution_id=${key}`);
        setEff(e);
        const d = clone(e.config);
        const o: Record<string, boolean> = {};
        SECTION_ORDER.forEach((s) => {
          o[s] = key === 'GLOBAL' ? true : Object.prototype.hasOwnProperty.call(e.raw_bank || {}, s);
        });
        const enabled = key === 'GLOBAL' ? e.global_enabled : e.bank_enabled;
        setDraft(d);
        setOvr(o);
        setPolicyEnabled(enabled !== false);
        setSnapshot(JSON.stringify({ d, o, enabled: enabled !== false }));
      } catch (err: any) {
        show(err.message || 'Could not load the policy', true);
      } finally {
        setLoading(false);
      }
    },
    [show]
  );

  useEffect(() => {
    loadPolicies();
  }, [loadPolicies]);
  useEffect(() => {
    loadScope(scope);
  }, [scope, loadScope]);

  const dirty = useMemo(
    () => !!snapshot && JSON.stringify({ d: draft, o: ovr, enabled: policyEnabled }) !== snapshot,
    [draft, ovr, policyEnabled, snapshot]
  );

  const setSec = (name: string, value: any) => setDraft((d) => ({ ...d, [name]: value }));
  const toggleOverride = (name: string, on: boolean) => {
    setOvr((o) => ({ ...o, [name]: on }));
    if (!on && globalEff) setSec(name, clone(globalEff.config[name]));
  };

  const save = async () => {
    setSaving(true);
    try {
      const config: Record<string, any> = {};
      SECTION_ORDER.forEach((s) => {
        if (ovr[s]) config[s] = tidy(s, draft[s]);
      });
      const res = await apiFetch('/local-host/policies', {
        method: 'PUT',
        body: JSON.stringify({
          scope_type: isGlobal ? 'GLOBAL' : 'BANK',
          institution_id: isGlobal ? null : scope,
          enabled: policyEnabled,
          config,
        }),
      });
      show(`${isGlobal ? 'Global policy' : `${bank?.code} policy`} saved (v${res.version})`);
      await Promise.all([loadPolicies(), loadScope(scope)]);
      onChanged?.();
    } catch (err: any) {
      show(err.message || 'Save failed', true);
    } finally {
      setSaving(false);
    }
  };

  const removeOverride = async () => {
    if (isGlobal || !confirm(`Remove all overrides of ${bank?.code}? The bank will inherit the Global policy.`)) return;
    try {
      await apiFetch(`/local-host/policies/bank/${scope}`, { method: 'DELETE' });
      show(`${bank?.code} now inherits the Global policy`);
      await Promise.all([loadPolicies(), loadScope(scope)]);
      onChanged?.();
    } catch (err: any) {
      show(err.message || 'Could not remove', true);
    }
  };

  // keep configuration tidy: store only what differs from the defaults
  const tidy = (name: string, v: any) => {
    if (name === 'transactions') {
      const out: Record<string, any> = {};
      Object.entries(v || {}).forEach(([k, t]: [string, any]) => {
        if (JSON.stringify(t) !== JSON.stringify(DEFAULT_TX)) out[k] = t;
      });
      return out;
    }
    return v;
  };

  const banks: any[] = meta?.banks || [];
  const rail = [{ id: 'GLOBAL', code: 'GLOBAL', name: 'Global Default', status: 'ACTIVE' }, ...banks].filter((b) => {
    const t = filter.trim().toLowerCase();
    return !t || `${b.code} ${b.name}`.toLowerCase().includes(t);
  });
  const rowFor = (id: string) => policies.find((p) => (id === 'GLOBAL' ? p.scope_type === 'GLOBAL' : p.institution_id === id));

  const gen = draft.general || {};
  const hostStatus = gen.host_status || 'ACTIVE';

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
      {toastNode}

      {/* ===================== left rail */}
      <aside className={`lg:col-span-3 ${panelCls} overflow-hidden flex flex-col self-start`}>
        <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800">
          <div className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">Host scope</div>
          <div className="relative">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="find a bank"
              className={`${inputCls} pl-8`}
              aria-label="find a bank"
            />
          </div>
        </div>
        <div className="max-h-[640px] overflow-y-auto">
          {rail.map((b) => {
            const row = rowFor(b.id);
            const active = scope === b.id;
            const st = row?.host_status || 'ACTIVE';
            return (
              <button
                key={b.id}
                type="button"
                onClick={() => setScope(b.id)}
                aria-label={`scope ${b.code}`}
                className={`w-full text-left px-4 py-3 border-b border-slate-100 dark:border-slate-800/80 flex items-center gap-3 border-l-2 transition-colors ${
                  active ? 'bg-emerald-500/10 border-l-emerald-500' : 'border-l-transparent hover:bg-slate-50 dark:hover:bg-slate-800/50'
                }`}
              >
                <div
                  className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 text-white text-[11px] font-bold ${
                    b.id === 'GLOBAL' ? 'bg-gradient-to-br from-violet-500 to-sky-500' : 'bg-gradient-to-br from-emerald-500 to-teal-600'
                  }`}
                >
                  {b.id === 'GLOBAL' ? <Network size={16} /> : <Building2 size={16} />}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <span className="font-mono text-[11px] font-bold text-emerald-500 truncate">{b.code}</span>
                    <span className={`w-1.5 h-1.5 rounded-full ${st === 'ACTIVE' ? 'bg-emerald-500' : st === 'MAINTENANCE' ? 'bg-amber-500' : 'bg-rose-500'}`} />
                  </div>
                  <div className="text-xs truncate">{b.name}</div>
                  <div className="text-[10px] text-slate-400 mt-0.5">
                    {b.id === 'GLOBAL'
                      ? row?.exists
                        ? `${row.sections.length} sections saved`
                        : 'built-in defaults'
                      : row?.exists
                      ? `${row.sections.length} override${row.sections.length === 1 ? '' : 's'}`
                      : 'inherits Global'}
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </aside>

      {/* ===================== right pane */}
      <div className="lg:col-span-9 space-y-4 min-w-0">
        {/* scope header */}
        <div className="rounded-2xl border border-emerald-500/20 bg-gradient-to-r from-emerald-600/10 via-sky-500/5 to-transparent p-5">
          <div className="flex flex-wrap items-center gap-3">
            <div className="min-w-0">
              <h2 className="text-lg font-bold flex items-center gap-2">
                {isGlobal ? <Network className="text-violet-400" size={20} /> : <Building2 className="text-emerald-500" size={20} />}
                {isGlobal ? 'Global Default policy' : `${bank?.code} - ${bank?.name}`}
              </h2>
              <p className="text-[11px] text-slate-400 mt-1 max-w-2xl">
                {isGlobal
                  ? 'Applies to every bank that does not override a section. Built-in defaults are used for sections that were never saved.'
                  : 'Turn on "Override" on a section to give this bank its own rules. Sections left off inherit the Global policy.'}
              </p>
            </div>
            <div className="ml-auto flex flex-wrap items-center gap-2">
              <Badge tone={STATUS_TONE[hostStatus] || 'slate'}>HOST {hostStatus.replace('_', ' ')}</Badge>
              {!isGlobal && <Badge tone="sky">{Object.values(ovr).filter(Boolean).length} override(s)</Badge>}
              {policyRow?.exists && <Badge tone="slate">v{policyRow.version}</Badge>}
              {policyRow?.updated_at && <span className="text-[10px] text-slate-400">saved {fmtTime(policyRow.updated_at)}</span>}
              <div className="flex items-center gap-2 pl-2 border-l border-slate-300/40">
                <span className="text-[11px] text-slate-400">Policy active</span>
                <Toggle checked={policyEnabled} onChange={setPolicyEnabled} label="policy active" />
              </div>
            </div>
          </div>
        </div>

        {loading && !eff ? (
          <div className={`${panelCls} p-12 text-center text-slate-400 text-xs`}>
            <Loader2 className="animate-spin mx-auto mb-2" size={20} /> Loading policy...
          </div>
        ) : (
          <>
            {/* ---------- general */}
            <SectionCard
              icon={<Power size={16} />}
              title="Host status & defaults"
              subtitle="Open or close the host, set the default decline code, amount range, currencies and business hours"
              right={<SectionHead name="general" isGlobal={isGlobal} ovr={ovr} eff={eff} onToggle={toggleOverride} />}
              dim={!isGlobal && !ovr.general}
            >
              <div className="space-y-5">
                <div className="flex flex-wrap items-center gap-4">
                  <div>
                    <div className="text-[11px] text-slate-400 font-medium mb-1.5">Host status</div>
                    <SegButtons
                      value={hostStatus}
                      onChange={(v) => setSec('general', { ...gen, host_status: v })}
                      options={[
                        { value: 'ACTIVE', label: 'Active', tone: 'emerald' },
                        { value: 'MAINTENANCE', label: 'Maintenance', tone: 'amber' },
                        { value: 'DECLINE_ALL', label: 'Decline all', tone: 'rose' },
                      ]}
                    />
                  </div>
                  {hostStatus !== 'ACTIVE' && (
                    <>
                      <Labeled label="Response code" className="w-56">
                        <RcSelect value={gen.status_response_code || '91'} codes={rcs} ariaLabel="status response code"
                          onChange={(v) => setSec('general', { ...gen, status_response_code: v })} />
                      </Labeled>
                      <Labeled label="Message" className="flex-1 min-w-[200px]">
                        <input value={gen.status_message || ''} className={inputCls}
                          onChange={(e) => setSec('general', { ...gen, status_message: e.target.value })} />
                      </Labeled>
                    </>
                  )}
                </div>
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                  <Labeled label="Default decline code" hint="Used when a control below declines">
                    <RcSelect value={gen.decline_response_code || '57'} codes={rcs} ariaLabel="default decline code"
                      onChange={(v) => setSec('general', { ...gen, decline_response_code: v })} />
                  </Labeled>
                  <Labeled label="Min amount per transaction">
                    <NumInput value={gen.min_amount} ariaLabel="host min amount" onChange={(v) => setSec('general', { ...gen, min_amount: v })} />
                  </Labeled>
                  <Labeled label="Max amount per transaction">
                    <NumInput value={gen.max_amount} ariaLabel="host max amount" onChange={(v) => setSec('general', { ...gen, max_amount: v })} />
                  </Labeled>
                  <Labeled label="Allowed currencies" hint="Empty = all. BDT = 050">
                    <ChipInput values={gen.allowed_currencies || []} placeholder="BDT, USD"
                      onChange={(v) => setSec('general', { ...gen, allowed_currencies: v })}
                      suggestions={[{ value: 'BDT' }, { value: 'USD' }, { value: 'EUR' }, { value: 'INR' }]} />
                  </Labeled>
                </div>
                <div className="flex flex-wrap items-center gap-4 p-3 rounded-xl bg-slate-50 dark:bg-slate-950/50 border border-slate-200 dark:border-slate-800">
                  <Clock size={16} className="text-sky-500" />
                  <div className="text-xs font-semibold">Business hours</div>
                  <Toggle
                    checked={!!gen.business_hours?.enabled}
                    label="business hours"
                    onChange={(v) => setSec('general', { ...gen, business_hours: { ...(gen.business_hours || {}), enabled: v } })}
                  />
                  <span className="text-[11px] text-slate-400">Decline outside the window (supports overnight, e.g. 22:00 to 06:00)</span>
                  {gen.business_hours?.enabled && (
                    <div className="flex items-center gap-2 ml-auto">
                      <input type="time" aria-label="hours start" value={gen.business_hours.start || '00:00'} className={`${inputCls} w-28`}
                        onChange={(e) => setSec('general', { ...gen, business_hours: { ...gen.business_hours, start: e.target.value } })} />
                      <span className="text-slate-400 text-xs">to</span>
                      <input type="time" aria-label="hours end" value={gen.business_hours.end || '23:59'} className={`${inputCls} w-28`}
                        onChange={(e) => setSec('general', { ...gen, business_hours: { ...gen.business_hours, end: e.target.value } })} />
                    </div>
                  )}
                </div>
              </div>
            </SectionCard>

            {/* ---------- channels */}
            <SectionCard
              icon={<Layers size={16} />}
              title="Channel control"
              subtitle="Allow or stop a channel and limit the amount per transaction"
              right={<SectionHead name="channels" isGlobal={isGlobal} ovr={ovr} eff={eff} onToggle={toggleOverride} />}
              dim={!isGlobal && !ovr.channels}
            >
              <div className="rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden">
                <div className="hidden md:grid grid-cols-12 gap-3 px-4 py-2 text-[10px] uppercase tracking-wider font-bold text-slate-400 bg-slate-50 dark:bg-slate-950/50">
                  <div className="col-span-5">Channel</div>
                  <div className="col-span-1">On</div>
                  <div className="col-span-3">Min amount</div>
                  <div className="col-span-3">Max amount</div>
                </div>
                {(meta?.channels || []).map((ch: string) => {
                  const v = { ...DEFAULT_CH, ...(draft.channels?.[ch] || {}) };
                  const upd = (patch: any) => setSec('channels', { ...(draft.channels || {}), [ch]: { ...v, ...patch } });
                  return (
                    <div key={ch} className="grid grid-cols-12 gap-3 items-center px-4 py-3 border-t border-slate-100 dark:border-slate-800/80">
                      <div className="col-span-12 md:col-span-5 flex items-center gap-3">
                        <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${v.enabled ? 'bg-emerald-500/10 text-emerald-500' : 'bg-rose-500/10 text-rose-500'}`}>
                          {CH_ICON[ch]}
                        </div>
                        <div>
                          <div className="text-xs font-bold font-mono">{ch}</div>
                          <div className="text-[10px] text-slate-400">{CH_DESC[ch]}</div>
                        </div>
                      </div>
                      <div className="col-span-3 md:col-span-1">
                        <Toggle checked={v.enabled} label={`${ch} enabled`} onChange={(x) => upd({ enabled: x })} />
                      </div>
                      <div className="col-span-4 md:col-span-3">
                        <NumInput value={v.min_amount} ariaLabel={`${ch} min`} onChange={(x) => upd({ min_amount: x })} disabled={!v.enabled} placeholder="no minimum" />
                      </div>
                      <div className="col-span-5 md:col-span-3">
                        <NumInput value={v.max_amount} ariaLabel={`${ch} max`} onChange={(x) => upd({ max_amount: x })} disabled={!v.enabled} placeholder="no maximum" />
                      </div>
                    </div>
                  );
                })}
              </div>
            </SectionCard>

            {/* ---------- sources */}
            <SectionCard
              icon={<Network size={16} />}
              title="Source systems (internal and external)"
              subtitle="Who is sending the request: your own banks (ON_US) or a processing system such as NPSB, VISA or MASTERCARD"
              right={<SectionHead name="sources" isGlobal={isGlobal} ovr={ovr} eff={eff} onToggle={toggleOverride} />}
              dim={!isGlobal && !ovr.sources}
            >
              <SourcesTable meta={meta} value={draft.sources || {}} onChange={(v) => setSec('sources', v)} />
            </SectionCard>

            {/* ---------- transactions */}
            <SectionCard
              icon={<ListChecks size={16} />}
              title="Transaction matrix"
              subtitle="Per transaction code: allow it, choose the channels it may use, and set an amount range. Empty channels = all"
              right={<SectionHead name="transactions" isGlobal={isGlobal} ovr={ovr} eff={eff} onToggle={toggleOverride} />}
              dim={!isGlobal && !ovr.transactions}
            >
              <TxMatrix meta={meta} value={draft.transactions || {}} onChange={(v) => setSec('transactions', v)} />
            </SectionCard>

            {/* ---------- cross border */}
            <SectionCard
              icon={<Plane size={16} />}
              title="Cross-border"
              subtitle="Control transactions made outside the bank's country (DE19 terminal country, 050 = Bangladesh)"
              right={<SectionHead name="cross_border" isGlobal={isGlobal} ovr={ovr} eff={eff} onToggle={toggleOverride} />}
              dim={!isGlobal && !ovr.cross_border}
            >
              {(() => {
                const v = draft.cross_border || {};
                const upd = (p: any) => setSec('cross_border', { ...v, ...p });
                return (
                  <div className="space-y-4">
                    <div className="flex items-center gap-3">
                      <Toggle checked={v.enabled !== false} label="allow foreign transactions" onChange={(x) => upd({ enabled: x })} />
                      <span className="text-xs font-semibold">Allow foreign transactions</span>
                      <span className="text-[11px] text-slate-400">Off = every transaction outside the home country is declined</span>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      <Labeled label="Allowed countries (when foreign is on)" hint="Empty = all countries">
                        <ChipInput values={v.allowed_countries || []} onChange={(x) => upd({ allowed_countries: x })} suggestions={COUNTRY_HINTS} tone="emerald" />
                      </Labeled>
                      <Labeled label="Blocked countries">
                        <ChipInput values={v.blocked_countries || []} onChange={(x) => upd({ blocked_countries: x })} suggestions={COUNTRY_HINTS} tone="rose" />
                      </Labeled>
                      <Labeled label="Decline code">
                        <RcSelect value={v.response_code || '57'} codes={rcs} ariaLabel="cross border code" onChange={(x) => upd({ response_code: x })} />
                      </Labeled>
                    </div>
                  </div>
                );
              })()}
            </SectionCard>

            {/* ---------- mcc + acquirers */}
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
              <SectionCard
                icon={<Tag size={16} />}
                title="Merchant category (MCC)"
                subtitle="Block risky categories or allow only a list"
                right={<SectionHead name="mcc" isGlobal={isGlobal} ovr={ovr} eff={eff} onToggle={toggleOverride} />}
                dim={!isGlobal && !ovr.mcc}
              >
                {(() => {
                  const v = draft.mcc || {};
                  const upd = (p: any) => setSec('mcc', { ...v, ...p });
                  return (
                    <div className="space-y-3">
                      <Labeled label="Blocked MCC">
                        <ChipInput values={v.blocked || []} onChange={(x) => upd({ blocked: x })} suggestions={MCC_HINTS} tone="rose" />
                      </Labeled>
                      <Labeled label="Allowed MCC only" hint="Empty = every MCC that is not blocked">
                        <ChipInput values={v.allowed || []} onChange={(x) => upd({ allowed: x })} suggestions={MCC_HINTS} tone="emerald" />
                      </Labeled>
                      <Labeled label="Decline code">
                        <RcSelect value={v.response_code || '57'} codes={rcs} ariaLabel="mcc code" onChange={(x) => upd({ response_code: x })} />
                      </Labeled>
                    </div>
                  );
                })()}
              </SectionCard>

              <SectionCard
                icon={<Building2 size={16} />}
                title="Terminal owners (acquirers)"
                subtitle="Block or allow by acquiring bank code or institution id (DE32)"
                right={<SectionHead name="acquirers" isGlobal={isGlobal} ovr={ovr} eff={eff} onToggle={toggleOverride} />}
                dim={!isGlobal && !ovr.acquirers}
              >
                {(() => {
                  const v = draft.acquirers || {};
                  const upd = (p: any) => setSec('acquirers', { ...v, ...p });
                  const hints = banks.map((b: any) => ({ value: b.code }));
                  return (
                    <div className="space-y-3">
                      <Labeled label="Blocked terminal owners">
                        <ChipInput values={v.blocked || []} onChange={(x) => upd({ blocked: x })} suggestions={hints} tone="rose" />
                      </Labeled>
                      <Labeled label="Allowed terminal owners only" hint="Empty = all owners that are not blocked">
                        <ChipInput values={v.allowed || []} onChange={(x) => upd({ allowed: x })} suggestions={hints} tone="emerald" />
                      </Labeled>
                      <Labeled label="Decline code">
                        <RcSelect value={v.response_code || '58'} codes={rcs} ariaLabel="acquirer code" onChange={(x) => upd({ response_code: x })} />
                      </Labeled>
                    </div>
                  );
                })()}
              </SectionCard>
            </div>

            {/* ---------- velocity */}
            <SectionCard
              icon={<Zap size={16} />}
              title="Velocity controls"
              subtitle="Stop card testing and burst fraud. Counted per card from earlier transactions"
              right={<SectionHead name="velocity" isGlobal={isGlobal} ovr={ovr} eff={eff} onToggle={toggleOverride} />}
              dim={!isGlobal && !ovr.velocity}
            >
              {(() => {
                const v = draft.velocity || {};
                const upd = (p: any) => setSec('velocity', { ...v, ...p });
                return (
                  <div className="space-y-4">
                    <div className="flex items-center gap-3">
                      <Toggle checked={!!v.enabled} label="velocity enabled" onChange={(x) => upd({ enabled: x })} />
                      <span className="text-xs font-semibold">Enable velocity controls</span>
                    </div>
                    <div className={`grid grid-cols-1 md:grid-cols-4 gap-4 ${v.enabled ? '' : 'opacity-50'}`}>
                      <Labeled label="Max transactions per minute">
                        <NumInput value={v.max_tx_per_minute} ariaLabel="max per minute" onChange={(x) => upd({ max_tx_per_minute: x })} disabled={!v.enabled} />
                      </Labeled>
                      <Labeled label="Max transactions per hour">
                        <NumInput value={v.max_tx_per_hour} ariaLabel="max per hour" onChange={(x) => upd({ max_tx_per_hour: x })} disabled={!v.enabled} />
                      </Labeled>
                      <Labeled label="Max declines per 24 hours">
                        <NumInput value={v.max_declines_per_day} ariaLabel="max declines" onChange={(x) => upd({ max_declines_per_day: x })} disabled={!v.enabled} />
                      </Labeled>
                      <Labeled label="Decline code">
                        <RcSelect value={v.response_code || '65'} codes={rcs} ariaLabel="velocity code" onChange={(x) => upd({ response_code: x })} disabled={!v.enabled} />
                      </Labeled>
                    </div>
                  </div>
                );
              })()}
            </SectionCard>

            {/* ---------- simulator */}
            <PolicySimulator meta={meta} scope={scope} bank={bank} dirty={dirty} />

            {/* ---------- sticky save bar */}
            <div className="sticky bottom-3 z-20">
              <div className={`${panelCls} shadow-xl px-4 py-3 flex flex-wrap items-center gap-3 ${dirty ? 'border-amber-500/50' : ''}`}>
                {dirty ? (
                  <span className="flex items-center gap-2 text-xs text-amber-500 font-semibold">
                    <ShieldAlert size={14} /> Unsaved changes
                  </span>
                ) : (
                  <span className="flex items-center gap-2 text-xs text-emerald-500 font-semibold">
                    <CheckCircle2 size={14} /> Saved
                  </span>
                )}
                <span className="text-[11px] text-slate-400">Changes apply to new transactions immediately after saving.</span>
                <div className="ml-auto flex items-center gap-2">
                  {!isGlobal && policyRow?.exists && (
                    <button type="button" onClick={removeOverride}
                      className="flex items-center gap-1.5 text-xs px-3 py-2 rounded-lg border border-rose-500/30 text-rose-500 hover:bg-rose-500/10">
                      <RotateCcw size={13} /> Inherit Global
                    </button>
                  )}
                  <button type="button" disabled={!dirty} onClick={() => loadScope(scope)}
                    className="text-xs px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-700 disabled:opacity-40">
                    Discard
                  </button>
                  <button type="button" disabled={!dirty || saving} onClick={save}
                    className="flex items-center gap-1.5 text-xs px-5 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white font-semibold shadow-md shadow-emerald-600/20">
                    {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />} Save policy
                  </button>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------- section header: source + override switch
const SectionHead: React.FC<{
  name: string;
  isGlobal: boolean;
  ovr: Record<string, boolean>;
  eff: any;
  onToggle: (name: string, on: boolean) => void;
}> = ({ name, isGlobal, ovr, eff, onToggle }) => {
  const src = eff?.sources?.[name] || 'DEFAULT';
  if (isGlobal) return <Badge tone={src === 'DEFAULT' ? 'slate' : 'violet'}>{src === 'DEFAULT' ? 'DEFAULTS' : 'SAVED'}</Badge>;
  return (
    <div className="flex items-center gap-2">
      <Badge tone={ovr[name] ? 'emerald' : 'slate'}>{ovr[name] ? 'BANK OVERRIDE' : `INHERITS ${src === 'DEFAULT' ? 'DEFAULTS' : 'GLOBAL'}`}</Badge>
      <span className="text-[11px] text-slate-400">Override</span>
      <Toggle checked={!!ovr[name]} onChange={(v) => onToggle(name, v)} label={`override ${name}`} />
    </div>
  );
};

// ---------------------------------------------------------------- sources table
const SourcesTable: React.FC<{ meta: any; value: Record<string, any>; onChange: (v: Record<string, any>) => void }> = ({
  meta,
  value,
  onChange,
}) => {
  const systems: any[] = meta?.processing_systems || [];
  const keys = ['ON_US', ...systems.map((s) => s.code).filter((c: string) => c !== 'ON_US'), 'UNKNOWN'];
  const label = (k: string) =>
    k === 'ON_US'
      ? { name: 'Own banks (ON_US)', note: 'Terminal owner and card issuer are the same bank' }
      : k === 'UNKNOWN'
      ? { name: 'Unknown source', note: 'Any system that is not listed' }
      : { name: systems.find((s) => s.code === k)?.name || k, note: systems.find((s) => s.code === k)?.type || '' };
  const txSug = (meta?.transaction_codes || []).map((t: any) => ({ value: t.code, label: t.name }));
  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden">
      {keys.map((k) => {
        const v = { ...DEFAULT_SRC, ...(value[k] || {}) };
        const upd = (p: any) => onChange({ ...value, [k]: { ...v, ...p } });
        const l = label(k);
        return (
          <div key={k} className="grid grid-cols-12 gap-3 items-start px-4 py-3 border-t first:border-t-0 border-slate-100 dark:border-slate-800/80">
            <div className="col-span-12 md:col-span-3 flex items-start gap-3">
              <Toggle checked={v.enabled} label={`${k} enabled`} onChange={(x) => upd({ enabled: x })} />
              <div>
                <div className="text-xs font-bold font-mono">{k}</div>
                <div className="text-[10px] text-slate-400">{l.name}</div>
                {l.note && <div className="text-[10px] text-slate-500">{l.note}</div>}
              </div>
            </div>
            <div className="col-span-12 md:col-span-3">
              <div className="text-[10px] text-slate-400 mb-1">Max amount</div>
              <NumInput value={v.max_amount} ariaLabel={`${k} max`} onChange={(x) => upd({ max_amount: x })} disabled={!v.enabled} placeholder="no maximum" />
            </div>
            <div className="col-span-12 md:col-span-6">
              <div className="text-[10px] text-slate-400 mb-1">Allowed transaction codes (empty = all)</div>
              <ChipInput values={v.allowed_tx_codes || []} onChange={(x) => upd({ allowed_tx_codes: x })} disabled={!v.enabled} suggestions={txSug} />
            </div>
          </div>
        );
      })}
    </div>
  );
};

// ---------------------------------------------------------------- transaction matrix
const TxMatrix: React.FC<{ meta: any; value: Record<string, any>; onChange: (v: Record<string, any>) => void }> = ({
  meta,
  value,
  onChange,
}) => {
  const codes: any[] = meta?.transaction_codes || [];
  const channels: string[] = meta?.channels || [];
  if (!codes.length) return <div className="text-xs text-slate-400">No transaction codes are configured yet.</div>;
  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden">
      <div className="hidden md:grid grid-cols-12 gap-3 px-4 py-2 text-[10px] uppercase tracking-wider font-bold text-slate-400 bg-slate-50 dark:bg-slate-950/50">
        <div className="col-span-3">Transaction</div>
        <div className="col-span-1">Allow</div>
        <div className="col-span-4">Channels (none = all)</div>
        <div className="col-span-2">Min</div>
        <div className="col-span-2">Max</div>
      </div>
      {codes.map((t) => {
        const v = { ...DEFAULT_TX, ...(value[t.code] || {}) };
        const upd = (p: any) => onChange({ ...value, [t.code]: { ...v, ...p } });
        return (
          <div key={t.code} className="grid grid-cols-12 gap-3 items-center px-4 py-2.5 border-t border-slate-100 dark:border-slate-800/80">
            <div className="col-span-12 md:col-span-3">
              <div className="text-xs font-semibold">
                <span className="font-mono text-emerald-500">{t.code}</span> {t.name}
              </div>
              <div className="flex gap-1 mt-0.5">
                {t.financial && <Badge tone="sky">financial</Badge>}
                {t.financial && (t.debit ? <Badge tone="amber">debit</Badge> : <Badge tone="emerald">credit</Badge>)}
              </div>
            </div>
            <div className="col-span-3 md:col-span-1">
              <Toggle checked={v.enabled} label={`tx ${t.code} allowed`} onChange={(x) => upd({ enabled: x })} />
            </div>
            <div className="col-span-9 md:col-span-4 flex flex-wrap gap-1">
              {channels.map((ch) => {
                const on = (v.channels || []).includes(ch);
                return (
                  <button
                    key={ch}
                    type="button"
                    disabled={!v.enabled}
                    aria-pressed={on}
                    aria-label={`tx ${t.code} channel ${ch}`}
                    onClick={() => upd({ channels: on ? v.channels.filter((c: string) => c !== ch) : [...(v.channels || []), ch] })}
                    className={`text-[10px] font-mono px-2 py-0.5 rounded-md border transition-colors ${
                      on ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-500' : 'border-slate-300 dark:border-slate-700 text-slate-400 hover:border-slate-400'
                    } ${!v.enabled ? 'opacity-40' : ''}`}
                  >
                    {ch}
                  </button>
                );
              })}
            </div>
            <div className="col-span-6 md:col-span-2">
              <NumInput value={v.min_amount} ariaLabel={`tx ${t.code} min`} onChange={(x) => upd({ min_amount: x })} disabled={!v.enabled || !t.financial} placeholder="-" />
            </div>
            <div className="col-span-6 md:col-span-2">
              <NumInput value={v.max_amount} ariaLabel={`tx ${t.code} max`} onChange={(x) => upd({ max_amount: x })} disabled={!v.enabled || !t.financial} placeholder="-" />
            </div>
          </div>
        );
      })}
    </div>
  );
};

// ---------------------------------------------------------------- policy simulator
const PolicySimulator: React.FC<{ meta: any; scope: string; bank: any; dirty: boolean }> = ({ meta, scope, bank, dirty }) => {
  const [bankId, setBankId] = useState<string>('');
  const [f, setF] = useState<any>({ channel: 'ATM', tran_code: '10', amount: 5000, mcc: '', currency: '050', source: 'ON_US', hour: '', country: '050' });
  const [res, setRes] = useState<any | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const effectiveBank = scope !== 'GLOBAL' ? scope : bankId || meta?.banks?.[0]?.id || '';

  const run = async () => {
    setBusy(true);
    setErr('');
    try {
      const overrides: Record<string, any> = { ...f };
      Object.keys(overrides).forEach((k) => overrides[k] === '' && delete overrides[k]);
      setRes(await apiFetch('/local-host/policies/simulate', { method: 'POST', body: JSON.stringify({ institution_id: effectiveBank || null, overrides }) }));
    } catch (e: any) {
      setErr(e.message || 'Simulation failed');
      setRes(null);
    } finally {
      setBusy(false);
    }
  };

  const sources = ['ON_US', ...(meta?.processing_systems || []).map((s: any) => s.code)];
  return (
    <SectionCard
      icon={<Play size={16} />}
      title="Policy simulator"
      subtitle="Try a transaction against the SAVED policy. Only the policy layer is simulated (limits, PIN and balance are checked later)"
      right={dirty ? <Badge tone="amber">save first to test your edits</Badge> : undefined}
    >
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {scope === 'GLOBAL' && (
          <Labeled label="Bank">
            <select aria-label="simulator bank" className={inputCls} value={effectiveBank} onChange={(e) => setBankId(e.target.value)}>
              {(meta?.banks || []).map((b: any) => (
                <option key={b.id} value={b.id}>{b.code}</option>
              ))}
            </select>
          </Labeled>
        )}
        <Labeled label="Channel">
          <select aria-label="simulator channel" className={inputCls} value={f.channel} onChange={(e) => setF({ ...f, channel: e.target.value })}>
            {(meta?.channels || []).map((c: string) => <option key={c}>{c}</option>)}
          </select>
        </Labeled>
        <Labeled label="Transaction code">
          <select aria-label="simulator tran code" className={inputCls} value={f.tran_code} onChange={(e) => setF({ ...f, tran_code: e.target.value })}>
            {(meta?.transaction_codes || []).map((t: any) => <option key={t.code} value={t.code}>{t.code} {t.name}</option>)}
          </select>
        </Labeled>
        <Labeled label="Amount">
          <input aria-label="simulator amount" type="number" className={`${inputCls} font-mono`} value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} />
        </Labeled>
        <Labeled label="Source">
          <select aria-label="simulator source" className={inputCls} value={f.source} onChange={(e) => setF({ ...f, source: e.target.value })}>
            {sources.map((s: string) => <option key={s}>{s}</option>)}
          </select>
        </Labeled>
        <Labeled label="MCC">
          <input aria-label="simulator mcc" className={`${inputCls} font-mono`} placeholder="auto" value={f.mcc} onChange={(e) => setF({ ...f, mcc: e.target.value })} />
        </Labeled>
        <Labeled label="Country (DE19)">
          <input aria-label="simulator country" className={`${inputCls} font-mono`} value={f.country} onChange={(e) => setF({ ...f, country: e.target.value })} />
        </Labeled>
        <Labeled label="Hour (0-23)">
          <input aria-label="simulator hour" type="number" min={0} max={23} className={`${inputCls} font-mono`} placeholder="now" value={f.hour} onChange={(e) => setF({ ...f, hour: e.target.value })} />
        </Labeled>
      </div>
      <div className="flex items-center gap-3 mt-4">
        <button type="button" onClick={run} disabled={busy}
          className="flex items-center gap-1.5 text-xs px-5 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white font-semibold">
          {busy ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />} Evaluate
        </button>
        {err && <span className="text-xs text-rose-500 font-mono">{err}</span>}
      </div>
      {res && (
        <div className="mt-4 space-y-3">
          <div className={`flex flex-wrap items-center gap-3 p-4 rounded-xl border ${res.allowed ? 'bg-emerald-500/10 border-emerald-500/30' : 'bg-rose-500/10 border-rose-500/30'}`}>
            {res.allowed ? <CheckCircle2 className="text-emerald-500" size={22} /> : <XCircle className="text-rose-500" size={22} />}
            <div>
              <div className={`text-sm font-bold ${res.allowed ? 'text-emerald-500' : 'text-rose-500'}`}>
                {res.allowed ? 'Policy allows this transaction' : `Declined by ${res.failed_control}  (RC ${res.response_code})`}
              </div>
              <div className="text-[11px] text-slate-400">
                {res.allowed ? 'Continues to limits, PIN, balance and algos.' : res.message} · {res.policy_scope} policy · bank {res.bank} · channel {res.context?.channel} · source {res.context?.source}
              </div>
            </div>
          </div>
          <div className="rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden">
            {(res.checks || []).map((c: any, i: number) => (
              <div key={i} className="flex items-start gap-2 px-4 py-2 text-[11px] border-t first:border-t-0 border-slate-100 dark:border-slate-800/80">
                {c.status === 'PASSED' ? <CheckCircle2 size={13} className="text-emerald-500 mt-0.5" /> : <XCircle size={13} className="text-rose-500 mt-0.5" />}
                <span className="font-semibold w-52 shrink-0">{c.name}</span>
                <span className="text-slate-400">{c.message}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </SectionCard>
  );
};
'''

HC_ALGO_TSX = r'''import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  Copy,
  FileCode2,
  FlaskConical,
  History,
  Loader2,
  Play,
  Plus,
  RotateCcw,
  Save,
  Search,
  ShieldOff,
  Sparkles,
  Trash2,
  XCircle,
} from 'lucide-react';
import { apiFetch } from '../../api';
import {
  Badge,
  ChipInput,
  CodeEditor,
  CodeEditorHandle,
  Labeled,
  Modal,
  NumInput,
  RcSelect,
  SegButtons,
  Toggle,
  ago,
  fmtNum,
  fmtTime,
  inputCls,
  panelCls,
  useToast,
} from './ui';

// ============================================================================
// ALGO CONTROL  - Python / SQL risk blocks
// ============================================================================

const PY_STARTER = `# Rajon Algo (Python)
# Click "Fields Reference" to see every field you can use.
# Decide with:  decline('57', 'message')   block_card('why')   block_customer('why')
#               approve('why')             flag('why')         or  return True  (default action)

if tx.channel == 'ATM' and tx.amount > 20000 and (tx.hour >= 23 or tx.hour < 5):
    decline('57', 'High value ATM cash at night')
`;
const SQL_STARTER = `-- Rajon Algo (SQL, read-only)
-- Matches when the query returns a row whose first column is true / non-zero.
-- Use :parameters from "Fields Reference", e.g. :card_id  :tx_amount  :since_15m
SELECT COUNT(*) >= 3
FROM transactions
WHERE card_id = :card_id
  AND authorization_status = 'DECLINED'
  AND transaction_datetime >= :since_15m
`;

const ACTION_TONE: Record<string, string> = {
  DECLINE: 'rose', BLOCK_CARD: 'rose', BLOCK_CUSTOMER: 'rose', APPROVE: 'emerald', FLAG: 'amber',
};

interface AlgoForm {
  id?: string;
  algo_code: string;
  name: string;
  description: string;
  language: 'PYTHON' | 'SQL';
  code: string;
  scope_type: 'GLOBAL' | 'BANK' | 'CARD_PROFILE';
  institution_id: string | null;
  card_profile_id: string | null;
  stage: 'PRE_AUTH' | 'POST_AUTH';
  priority: number;
  mode: 'ENFORCE' | 'MONITOR';
  default_action: string;
  default_response_code: string;
  default_message: string;
  on_error: 'SKIP' | 'DECLINE';
  stop_on_match: boolean;
  tx_codes: string[];
  channels: string[];
  enabled: boolean;
  version?: number;
}

const blankForm = (): AlgoForm => ({
  algo_code: '', name: '', description: '', language: 'PYTHON', code: PY_STARTER, scope_type: 'GLOBAL',
  institution_id: null, card_profile_id: null, stage: 'PRE_AUTH', priority: 100, mode: 'ENFORCE',
  default_action: 'DECLINE', default_response_code: '57', default_message: 'Declined by risk algo',
  on_error: 'SKIP', stop_on_match: true, tx_codes: [], channels: [], enabled: true,
});

const autoCode = (name: string) =>
  name.trim().toUpperCase().replace(/[^A-Z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 40);

const scopeLabel = (a: any) =>
  a.scope_type === 'BANK' ? `BANK ${a.bank_code || ''}` : a.scope_type === 'CARD_PROFILE' ? `PROFILE ${a.card_profile_code || ''}` : 'GLOBAL';

interface Props {
  meta: any;
  onChanged?: () => void;
}

export const AlgoControlTab: React.FC<Props> = ({ meta, onChanged }) => {
  const { show, node: toastNode } = useToast();
  const editorRef = useRef<CodeEditorHandle>(null);

  const [algos, setAlgos] = useState<any[]>([]);
  const [loadingList, setLoadingList] = useState(false);
  const [q, setQ] = useState('');
  const [scopeFilter, setScopeFilter] = useState<'ALL' | 'GLOBAL' | 'BANK' | 'CARD_PROFILE'>('ALL');
  const [selected, setSelected] = useState<string>(''); // algo id, 'new' or ''
  const [form, setForm] = useState<AlgoForm | null>(null);
  const [baseline, setBaseline] = useState('');
  const [saving, setSaving] = useState(false);
  const [validation, setValidation] = useState<{ valid: boolean; errors: string[] } | null>(null);

  const [catalog, setCatalog] = useState<any | null>(null);
  const [templates, setTemplates] = useState<any[]>([]);
  const [schema, setSchema] = useState<any[]>([]);
  const [showFields, setShowFields] = useState(false);
  const [showTemplates, setShowTemplates] = useState(false);
  const [showVersions, setShowVersions] = useState(false);
  const [versions, setVersions] = useState<any[]>([]);
  const [logs, setLogs] = useState<any[]>([]);
  const [showTest, setShowTest] = useState(true);

  const rcs = meta?.response_codes || [];
  const banks: any[] = meta?.banks || [];
  const profiles: any[] = meta?.card_profiles || [];

  // ---------------------------------------------------------------- loaders
  const loadList = useCallback(async () => {
    setLoadingList(true);
    try {
      setAlgos(await apiFetch('/local-host/algos'));
    } catch (e: any) {
      show(e.message || 'Could not load algos', true);
    } finally {
      setLoadingList(false);
    }
  }, [show]);

  const loadLogs = useCallback(
    async (algoId?: string) => {
      try {
        const p = new URLSearchParams({ limit: '30' });
        if (algoId) p.set('algo_id', algoId);
        setLogs(await apiFetch(`/local-host/algos/logs?${p.toString()}`));
      } catch {
        setLogs([]);
      }
    },
    []
  );

  useEffect(() => {
    loadList();
    loadLogs();
  }, [loadList, loadLogs]);

  const openAlgo = async (id: string) => {
    if (dirty && !confirm('Discard your unsaved changes?')) return;
    try {
      const a = await apiFetch(`/local-host/algos/${id}`);
      const f: AlgoForm = {
        id: a.id, algo_code: a.algo_code, name: a.name, description: a.description || '', language: a.language,
        code: a.code, scope_type: a.scope_type, institution_id: a.institution_id, card_profile_id: a.card_profile_id,
        stage: a.stage, priority: a.priority, mode: a.mode, default_action: a.default_action,
        default_response_code: a.default_response_code, default_message: a.default_message, on_error: a.on_error,
        stop_on_match: a.stop_on_match, tx_codes: a.tx_codes || [], channels: a.channels || [], enabled: a.enabled,
        version: a.version,
      };
      setSelected(id);
      setForm(f);
      setBaseline(JSON.stringify(f));
      setValidation(null);
      loadLogs(id);
    } catch (e: any) {
      show(e.message || 'Could not open the algo', true);
    }
  };

  const newAlgo = () => {
    if (dirty && !confirm('Discard your unsaved changes?')) return;
    const f = blankForm();
    setSelected('new');
    setForm(f);
    setBaseline(JSON.stringify(f));
    setValidation(null);
    loadLogs();
  };

  const dirty = useMemo(() => !!form && JSON.stringify(form) !== baseline, [form, baseline]);

  // everything the backend needs, explained in plain words (instead of a raw 422 error)
  const problems = useMemo(() => {
    const out: string[] = [];
    if (!form) return out;
    if (form.algo_code.replace(/[^A-Za-z0-9]/g, '').length < 3) out.push('Enter an Algo code: at least 3 letters or numbers, e.g. NIGHT_ATM_LIMIT');
    if (form.name.trim().length < 2) out.push('Enter a Name for the algo');
    if (form.scope_type === 'BANK' && !form.institution_id) out.push('Choose the bank this algo applies to');
    if (form.scope_type === 'CARD_PROFILE' && !form.card_profile_id) out.push('Choose the card profile this algo applies to');
    if (!form.code.trim()) out.push('The Python / SQL code block is empty');
    return out;
  }, [form]);

  // live validation (debounced)
  useEffect(() => {
    if (!form) return;
    const t = setTimeout(async () => {
      try {
        const r = await apiFetch('/local-host/algos/validate', { method: 'POST', body: JSON.stringify({ language: form.language, code: form.code }) });
        setValidation({ valid: r.valid, errors: r.errors || [] });
      } catch {
        setValidation(null);
      }
    }, 500);
    return () => clearTimeout(t);
  }, [form?.code, form?.language]); // eslint-disable-line react-hooks/exhaustive-deps

  const patch = (p: Partial<AlgoForm>) => setForm((f) => (f ? { ...f, ...p } : f));

  const switchLanguage = (lang: 'PYTHON' | 'SQL') => {
    if (!form || form.language === lang) return;
    const isStarter = form.code.trim() === '' || form.code === PY_STARTER || form.code === SQL_STARTER;
    patch({ language: lang, code: isStarter ? (lang === 'SQL' ? SQL_STARTER : PY_STARTER) : form.code });
  };

  // ---------------------------------------------------------------- save / delete / toggle
  const buildBody = (f: AlgoForm) => ({
    algo_code: f.algo_code, name: f.name, description: f.description || null, language: f.language, code: f.code,
    scope_type: f.scope_type, institution_id: f.scope_type === 'BANK' ? f.institution_id : null,
    card_profile_id: f.scope_type === 'CARD_PROFILE' ? f.card_profile_id : null, stage: f.stage,
    priority: Number(f.priority) || 100, mode: f.mode, default_action: f.default_action,
    default_response_code: f.default_response_code, default_message: f.default_message, on_error: f.on_error,
    stop_on_match: f.stop_on_match, tx_codes: f.tx_codes, channels: f.channels, enabled: f.enabled,
  });

  const save = async () => {
    if (!form) return;
    setSaving(true);
    try {
      const body = buildBody(form);
      const saved = form.id
        ? await apiFetch(`/local-host/algos/${form.id}`, { method: 'PUT', body: JSON.stringify(body) })
        : await apiFetch('/local-host/algos', { method: 'POST', body: JSON.stringify(body) });
      show(`Algo ${saved.algo_code} saved (v${saved.version})`);
      await loadList();
      await openAlgoFresh(saved.id);
      onChanged?.();
    } catch (e: any) {
      show(e.message || 'Save failed', true);
    } finally {
      setSaving(false);
    }
  };

  // open without the dirty prompt (after save / rollback)
  const openAlgoFresh = async (id: string) => {
    const a = await apiFetch(`/local-host/algos/${id}`);
    const f: AlgoForm = {
      id: a.id, algo_code: a.algo_code, name: a.name, description: a.description || '', language: a.language, code: a.code,
      scope_type: a.scope_type, institution_id: a.institution_id, card_profile_id: a.card_profile_id, stage: a.stage,
      priority: a.priority, mode: a.mode, default_action: a.default_action, default_response_code: a.default_response_code,
      default_message: a.default_message, on_error: a.on_error, stop_on_match: a.stop_on_match, tx_codes: a.tx_codes || [],
      channels: a.channels || [], enabled: a.enabled, version: a.version,
    };
    setSelected(id);
    setForm(f);
    setBaseline(JSON.stringify(f));
    loadLogs(id);
  };

  const remove = async () => {
    if (!form?.id || !confirm(`Delete algo ${form.algo_code}? This cannot be undone.`)) return;
    try {
      await apiFetch(`/local-host/algos/${form.id}`, { method: 'DELETE' });
      show(`Algo ${form.algo_code} deleted`);
      setSelected('');
      setForm(null);
      await loadList();
      loadLogs();
      onChanged?.();
    } catch (e: any) {
      show(e.message || 'Delete failed', true);
    }
  };

  const toggleListItem = async (a: any, enabled: boolean) => {
    try {
      await apiFetch(`/local-host/algos/${a.id}/toggle`, { method: 'POST', body: JSON.stringify({ enabled }) });
      setAlgos((list) => list.map((x) => (x.id === a.id ? { ...x, enabled } : x)));
      if (form?.id === a.id) {
        setForm((f) => (f ? { ...f, enabled } : f));
        setBaseline((b) => (b ? JSON.stringify({ ...JSON.parse(b), enabled }) : b));
      }
      show(`${a.algo_code} ${enabled ? 'enabled' : 'disabled'}`);
      onChanged?.();
    } catch (e: any) {
      show(e.message || 'Toggle failed', true);
    }
  };

  // ---------------------------------------------------------------- modals data
  const openFields = async () => {
    setShowFields(true);
    if (!catalog) {
      try {
        const [c, s] = await Promise.all([apiFetch('/local-host/algos/fields'), apiFetch('/local-host/algos/schema')]);
        setCatalog(c);
        setSchema(s);
      } catch (e: any) {
        show(e.message || 'Could not load the field reference', true);
      }
    }
  };

  const openTemplates = async () => {
    setShowTemplates(true);
    if (!templates.length) {
      try {
        setTemplates(await apiFetch('/local-host/algos/templates'));
      } catch (e: any) {
        show(e.message || 'Could not load templates', true);
      }
    }
  };

  const applyTemplate = (t: any) => {
    const base = form || blankForm();
    const next: AlgoForm = {
      ...base,
      algo_code: base.algo_code || String(t.key).toUpperCase(),
      name: base.name || t.title,
      description: t.description,
      language: t.language,
      code: t.code,
      stage: t.stage || 'PRE_AUTH',
      default_action: t.default_action,
      default_response_code: t.default_response_code,
      default_message: t.default_message,
    };
    if (!form) {
      setSelected('new');
      setBaseline(JSON.stringify(blankForm()));
    }
    setForm(next);
    setShowTemplates(false);
    show(`Template "${t.title}" loaded. Review it, then Save.`);
  };

  const openVersions = async () => {
    if (!form?.id) return;
    setShowVersions(true);
    try {
      setVersions(await apiFetch(`/local-host/algos/${form.id}/versions`));
    } catch (e: any) {
      show(e.message || 'Could not load versions', true);
    }
  };

  const rollback = async (v: number) => {
    if (!form?.id || !confirm(`Restore version ${v}? A new version will be created.`)) return;
    try {
      await apiFetch(`/local-host/algos/${form.id}/rollback`, { method: 'POST', body: JSON.stringify({ version: v }) });
      show(`Restored version ${v}`);
      setShowVersions(false);
      await loadList();
      await openAlgoFresh(form.id);
      onChanged?.();
    } catch (e: any) {
      show(e.message || 'Rollback failed', true);
    }
  };

  const insertField = (text: string) => editorRef.current?.insertAtCursor(text);

  const visible = algos.filter((a) => {
    if (scopeFilter !== 'ALL' && a.scope_type !== scopeFilter) return false;
    const t = q.trim().toLowerCase();
    return !t || `${a.algo_code} ${a.name}`.toLowerCase().includes(t);
  });

  // ================================================================ render
  return (
    <div className="grid grid-cols-1 xl:grid-cols-12 gap-5">
      {toastNode}

      {/* ===================== left: algo list */}
      <aside className={`xl:col-span-4 ${panelCls} overflow-hidden self-start`}>
        <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 space-y-3">
          <div className="flex items-center justify-between">
            <div className="text-xs font-bold uppercase tracking-wider text-slate-500">
              Algo blocks <span className="text-emerald-500 font-mono">{algos.length}</span>
            </div>
            <button type="button" onClick={newAlgo}
              className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold shadow-md shadow-emerald-600/20">
              <Plus size={13} /> New algo
            </button>
          </div>
          <div className="relative">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="search code or name" aria-label="search algos" className={`${inputCls} pl-8`} />
          </div>
          <div className="flex flex-wrap gap-1">
            {(['ALL', 'GLOBAL', 'BANK', 'CARD_PROFILE'] as const).map((s) => (
              <button key={s} type="button" onClick={() => setScopeFilter(s)}
                className={`text-[10px] px-2.5 py-1 rounded-lg font-semibold ${scopeFilter === s ? 'bg-emerald-600 text-white' : 'bg-slate-100 dark:bg-slate-800 text-slate-500'}`}>
                {s === 'CARD_PROFILE' ? 'PROFILE' : s}
              </button>
            ))}
          </div>
        </div>
        <div className="max-h-[720px] overflow-y-auto">
          {loadingList && algos.length === 0 && (
            <div className="p-8 text-center text-slate-400 text-xs"><Loader2 className="animate-spin mx-auto mb-2" size={18} /> Loading...</div>
          )}
          {!loadingList && visible.length === 0 && (
            <div className="p-8 text-center text-xs text-slate-400 space-y-3">
              <FileCode2 className="mx-auto text-slate-500" size={28} />
              <div>{algos.length === 0 ? 'No algo yet. Start from a ready-made template or write your own.' : 'No algo matches the filter.'}</div>
              {algos.length === 0 && (
                <button type="button" onClick={openTemplates}
                  className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-emerald-500/40 text-emerald-500 hover:bg-emerald-500/10">
                  <Sparkles size={13} /> Browse templates
                </button>
              )}
            </div>
          )}
          {visible.map((a) => {
            const active = selected === a.id;
            return (
              <div key={a.id} role="button" tabIndex={0} aria-label={`open algo ${a.algo_code}`}
                onClick={() => openAlgo(a.id)} onKeyDown={(e) => e.key === 'Enter' && openAlgo(a.id)}
                className={`px-4 py-3 border-b border-slate-100 dark:border-slate-800/80 cursor-pointer border-l-2 transition-colors ${
                  active ? 'bg-emerald-500/10 border-l-emerald-500' : 'border-l-transparent hover:bg-slate-50 dark:hover:bg-slate-800/50'
                } ${a.enabled ? '' : 'opacity-60'}`}>
                <div className="flex items-start gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="font-mono text-[11px] font-bold text-emerald-500 truncate">{a.algo_code}</span>
                      <Badge tone={a.language === 'SQL' ? 'sky' : 'violet'}>{a.language === 'SQL' ? 'SQL' : 'PY'}</Badge>
                      <Badge tone={a.mode === 'MONITOR' ? 'amber' : 'emerald'}>{a.mode}</Badge>
                    </div>
                    <div className="text-xs mt-0.5 truncate">{a.name}</div>
                    <div className="flex items-center gap-1.5 flex-wrap mt-1.5 text-[10px] text-slate-400">
                      <span className="font-mono">{scopeLabel(a)}</span>·<span>{a.stage === 'PRE_AUTH' ? 'pre-auth' : 'post-auth'}</span>·<span>prio {a.priority}</span>
                    </div>
                    <div className="flex items-center gap-2 mt-1.5">
                      <Badge tone={ACTION_TONE[a.default_action] || 'slate'}>{a.default_action}</Badge>
                      <span className="text-[10px] text-slate-400 font-mono">
                        {fmtNum(a.hit_count, 0)} hits / {fmtNum(a.eval_count, 0)} runs
                      </span>
                      {a.error_count > 0 && <Badge tone="rose">{a.error_count} err</Badge>}
                    </div>
                  </div>
                  <div onClick={(e) => e.stopPropagation()}>
                    <Toggle checked={a.enabled} label={`enable ${a.algo_code}`} onChange={(v) => toggleListItem(a, v)} />
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </aside>

      {/* ===================== right: editor */}
      <div className="xl:col-span-8 space-y-4 min-w-0">
        {!form ? (
          <div className={`${panelCls} p-14 text-center`}>
            <div className="w-16 h-16 mx-auto rounded-2xl bg-gradient-to-br from-emerald-500/20 to-sky-500/20 text-emerald-500 flex items-center justify-center mb-4">
              <FileCode2 size={30} />
            </div>
            <h3 className="text-base font-bold">Write your own transaction control</h3>
            <p className="text-xs text-slate-400 mt-2 max-w-lg mx-auto leading-relaxed">
              An algo is a small Python or SQL block that runs for every transaction of a bank or a card profile. It can
              approve, decline, block the card or block the customer. Open the Fields Reference to see every value you can use
              (amount, time, bank, terminal owner, authorization profile ...).
            </p>
            <div className="flex justify-center gap-3 mt-5">
              <button type="button" onClick={newAlgo} className="flex items-center gap-1.5 text-xs px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold">
                <Plus size={14} /> New algo
              </button>
              <button type="button" onClick={openTemplates} className="flex items-center gap-1.5 text-xs px-4 py-2 rounded-lg border border-slate-300 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800">
                <Sparkles size={14} /> Templates
              </button>
              <button type="button" onClick={openFields} className="flex items-center gap-1.5 text-xs px-4 py-2 rounded-lg border border-slate-300 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800">
                <BookOpen size={14} /> Fields Reference
              </button>
            </div>
          </div>
        ) : (
          <>
            {/* ---- header + settings */}
            <div className={`${panelCls} overflow-hidden`}>
              <div className="flex flex-wrap items-center gap-3 px-5 py-3.5 border-b border-slate-200 dark:border-slate-800 bg-gradient-to-r from-slate-50 to-transparent dark:from-slate-800/40">
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-sm font-bold">{form.id ? form.algo_code : 'New algo'}</h2>
                    {form.version && <Badge tone="slate">v{form.version}</Badge>}
                    {dirty && <Badge tone="amber">unsaved</Badge>}
                  </div>
                  <p className="text-[11px] text-slate-400">Runs {form.stage === 'PRE_AUTH' ? 'before PIN / HSM checks' : 'after balance and limit checks'} · lower priority number runs first</p>
                </div>
                <div className="ml-auto flex flex-wrap items-center gap-2">
                  <button type="button" onClick={openTemplates} className="flex items-center gap-1.5 text-[11px] px-3 py-1.5 rounded-lg border border-slate-300 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800">
                    <Sparkles size={13} /> Templates
                  </button>
                  <button type="button" onClick={openFields} className="flex items-center gap-1.5 text-[11px] px-3 py-1.5 rounded-lg bg-sky-600/10 text-sky-500 hover:bg-sky-600/20 font-semibold">
                    <BookOpen size={13} /> Fields Reference
                  </button>
                  {form.id && (
                    <button type="button" onClick={openVersions} className="flex items-center gap-1.5 text-[11px] px-3 py-1.5 rounded-lg border border-slate-300 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800">
                      <History size={13} /> History
                    </button>
                  )}
                  {form.id && (
                    <button type="button" onClick={remove} aria-label="delete algo" className="p-2 rounded-lg text-rose-500 hover:bg-rose-500/10">
                      <Trash2 size={14} />
                    </button>
                  )}
                </div>
              </div>

              <div className="p-5 space-y-5">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <Labeled label="Algo code *" hint="Letters, numbers, _ and -. Saved in upper case">
                    <input aria-label="algo code" value={form.algo_code} onChange={(e) => patch({ algo_code: e.target.value })} className={`${inputCls} font-mono`} placeholder="NIGHT_ATM_LIMIT" />
                  </Labeled>
                  <Labeled label="Name *" className="md:col-span-2">
                    <input aria-label="algo name" value={form.name} onChange={(e) => {
                      const v = e.target.value;
                      patch({ name: v, ...(!form.id && (form.algo_code === '' || form.algo_code === autoCode(form.name)) ? { algo_code: autoCode(v) } : {}) });
                    }} className={inputCls} placeholder="Block night time high value ATM cash" />
                  </Labeled>
                  <Labeled label="Description" className="md:col-span-3">
                    <input value={form.description} onChange={(e) => patch({ description: e.target.value })} className={inputCls} placeholder="What this algo protects against" />
                  </Labeled>
                </div>

                {/* scope */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 p-4 rounded-xl bg-slate-50 dark:bg-slate-950/40 border border-slate-200 dark:border-slate-800">
                  <div className="md:col-span-3 flex flex-wrap items-center gap-4">
                    <div>
                      <div className="text-[11px] text-slate-400 font-medium mb-1.5">Applies to</div>
                      <SegButtons
                        value={form.scope_type}
                        onChange={(v) => patch({ scope_type: v, institution_id: v === 'BANK' ? form.institution_id : null, card_profile_id: v === 'CARD_PROFILE' ? form.card_profile_id : null })}
                        options={[
                          { value: 'GLOBAL', label: 'Whole host' },
                          { value: 'BANK', label: 'One bank', tone: 'sky' },
                          { value: 'CARD_PROFILE', label: 'Card profile', tone: 'amber' },
                        ]}
                      />
                    </div>
                    {form.scope_type === 'BANK' && (
                      <Labeled label="Bank" className="w-64">
                        <select aria-label="algo bank" className={inputCls} value={form.institution_id || ''} onChange={(e) => patch({ institution_id: e.target.value || null })}>
                          <option value="">select a bank</option>
                          {banks.map((b) => <option key={b.id} value={b.id}>{b.code} - {b.name}</option>)}
                        </select>
                      </Labeled>
                    )}
                    {form.scope_type === 'CARD_PROFILE' && (
                      <Labeled label="Card profile" className="w-72">
                        <select aria-label="algo card profile" className={inputCls} value={form.card_profile_id || ''} onChange={(e) => patch({ card_profile_id: e.target.value || null })}>
                          <option value="">select a profile</option>
                          {profiles.map((p) => <option key={p.id} value={p.id}>{p.code} - {p.name}</option>)}
                        </select>
                      </Labeled>
                    )}
                  </div>
                  <p className="md:col-span-3 text-[11px] text-slate-400 leading-relaxed -mt-1" data-testid="scope-help">
                    {form.scope_type === 'GLOBAL' && 'Runs for every card of every bank.'}
                    {form.scope_type === 'BANK' && 'Runs for every card issued by the bank you choose.'}
                    {form.scope_type === 'CARD_PROFILE' && 'This is where you tag an algo to a card profile: choose the profile above. It then runs for every card that belongs to that profile (the profile of a card is set from its BIN / card profile assignment).'}
                  </p>
                  <Labeled label="Stage">
                    <select aria-label="algo stage" className={inputCls} value={form.stage} onChange={(e) => patch({ stage: e.target.value as any })}>
                      <option value="PRE_AUTH">PRE_AUTH - before PIN / HSM</option>
                      <option value="POST_AUTH">POST_AUTH - after balance and limits</option>
                    </select>
                  </Labeled>
                  <Labeled label="Priority" hint="1 runs first">
                    <NumInput value={form.priority} ariaLabel="algo priority" onChange={(v) => patch({ priority: v || 100 })} placeholder="100" />
                  </Labeled>
                  <div className="flex items-end gap-3 pb-1">
                    <Toggle checked={form.enabled} label="algo enabled" onChange={(v) => patch({ enabled: v })} />
                    <span className="text-xs font-semibold">{form.enabled ? 'Enabled' : 'Disabled'}</span>
                  </div>
                </div>

                {/* behaviour */}
                <div className="grid grid-cols-1 md:grid-cols-12 gap-4">
                  <div className="md:col-span-4">
                    <div className="text-[11px] text-slate-400 font-medium mb-1.5">Mode</div>
                    <SegButtons
                      value={form.mode}
                      onChange={(v) => patch({ mode: v })}
                      options={[
                        { value: 'ENFORCE', label: 'Enforce', tone: 'emerald' },
                        { value: 'MONITOR', label: 'Monitor only', tone: 'amber' },
                      ]}
                    />
                    <p className="text-[10px] text-slate-500 mt-1.5 leading-snug">
                      {form.mode === 'MONITOR' ? 'Shadow mode: logs what it WOULD do, never declines or blocks.' : 'Live: the action is applied to real transactions.'}
                    </p>
                  </div>
                  <Labeled label="When the condition is met" className="md:col-span-3">
                    <select aria-label="default action" className={inputCls} value={form.default_action} onChange={(e) => patch({ default_action: e.target.value })}>
                      {(meta?.actions || ['DECLINE', 'APPROVE', 'BLOCK_CARD', 'BLOCK_CUSTOMER', 'FLAG']).map((a: string) => <option key={a}>{a}</option>)}
                    </select>
                  </Labeled>
                  <Labeled label="Response code" className="md:col-span-5">
                    <RcSelect value={form.default_response_code} codes={rcs} ariaLabel="default response code" onChange={(v) => patch({ default_response_code: v })} />
                  </Labeled>
                  <Labeled label="Message (shown in the transaction checks)" className="md:col-span-7">
                    <input aria-label="default message" value={form.default_message} onChange={(e) => patch({ default_message: e.target.value })} className={inputCls} />
                  </Labeled>
                  <Labeled label="If the algo has an error" className="md:col-span-3">
                    <select aria-label="on error" className={inputCls} value={form.on_error} onChange={(e) => patch({ on_error: e.target.value as any })}>
                      <option value="SKIP">Ignore it (fail-open)</option>
                      <option value="DECLINE">Decline (fail-closed)</option>
                    </select>
                  </Labeled>
                  <div className="md:col-span-2 flex items-end gap-2 pb-1">
                    <Toggle checked={form.stop_on_match} label="stop on match" onChange={(v) => patch({ stop_on_match: v })} />
                    <span className="text-[11px] text-slate-400 leading-tight">Stop other algos on approve</span>
                  </div>
                  <Labeled label="Only for transaction codes (empty = all)" className="md:col-span-6">
                    <ChipInput values={form.tx_codes} onChange={(v) => patch({ tx_codes: v })}
                      suggestions={(meta?.transaction_codes || []).map((t: any) => ({ value: t.code, label: t.name }))} />
                  </Labeled>
                  <div className="md:col-span-6">
                    <div className="text-[11px] text-slate-400 font-medium mb-1.5">Only for channels (none = all)</div>
                    <div className="flex flex-wrap gap-1.5">
                      {(meta?.channels || []).map((c: string) => {
                        const on = form.channels.includes(c);
                        return (
                          <button key={c} type="button" aria-pressed={on} aria-label={`algo channel ${c}`}
                            onClick={() => patch({ channels: on ? form.channels.filter((x) => x !== c) : [...form.channels, c] })}
                            className={`text-[11px] font-mono px-2.5 py-1 rounded-md border ${on ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-500' : 'border-slate-300 dark:border-slate-700 text-slate-400'}`}>
                            {c}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* ---- code */}
            <div className={`${panelCls} overflow-hidden`}>
              <div className="flex flex-wrap items-center gap-3 px-5 py-3 border-b border-slate-200 dark:border-slate-800">
                <FileCode2 size={16} className="text-emerald-500" />
                <h3 className="text-sm font-bold">Algo code</h3>
                <SegButtons value={form.language} onChange={switchLanguage}
                  options={[{ value: 'PYTHON', label: 'Python', tone: 'sky' }, { value: 'SQL', label: 'SQL', tone: 'sky' }]} />
                <div className="ml-auto flex items-center gap-2">
                  {validation &&
                    (validation.valid ? (
                      <Badge tone="emerald"><CheckCircle2 size={11} /> valid</Badge>
                    ) : (
                      <Badge tone="rose"><XCircle size={11} /> {validation.errors.length} problem(s)</Badge>
                    ))}
                </div>
              </div>
              <div className="p-5 space-y-3">
                <CodeEditor ref={editorRef} value={form.code} onChange={(v) => patch({ code: v })} language={form.language} height={340} />
                {validation && !validation.valid && (
                  <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 space-y-1" role="alert">
                    {validation.errors.map((e, i) => (
                      <div key={i} className="text-[11px] font-mono text-rose-400 flex gap-2"><AlertTriangle size={12} className="mt-0.5 shrink-0" /> {e}</div>
                    ))}
                  </div>
                )}
                <div className="text-[11px] text-slate-400 leading-relaxed">
                  {form.language === 'PYTHON' ? (
                    <>
                      Use <code className="text-emerald-400">tx.amount</code>, <code className="text-emerald-400">card.status</code>,{' '}
                      <code className="text-emerald-400">customer.risk</code>, <code className="text-emerald-400">bank.code</code> ... Decide with{' '}
                      <code className="text-rose-300">decline()</code> <code className="text-rose-300">block_card()</code>{' '}
                      <code className="text-rose-300">block_customer()</code> <code className="text-rose-300">approve()</code>{' '}
                      <code className="text-rose-300">flag()</code>, or <code className="text-sky-300">return True</code> for the default action above. No imports, no while loops.
                    </>
                  ) : (
                    <>
                      One read-only SELECT. A first column that is true / non-zero means <strong>matched</strong>. Use{' '}
                      <code className="text-emerald-400">:card_id</code> <code className="text-emerald-400">:tx_amount</code>{' '}
                      <code className="text-emerald-400">:since_15m</code> ... or return the columns{' '}
                      <code className="text-rose-300">action, response_code, message</code> to choose the outcome from SQL.
                    </>
                  )}
                </div>
                {problems.length > 0 && (
                  <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 space-y-1" role="status" data-testid="algo-problems">
                    <div className="text-[11px] font-bold text-amber-400">To save this algo:</div>
                    {problems.map((p, i) => (
                      <div key={i} className="text-[11px] text-amber-400 flex gap-2"><AlertTriangle size={12} className="mt-0.5 shrink-0" /> {p}</div>
                    ))}
                  </div>
                )}
                <div className="flex flex-wrap items-center gap-3 pt-2">
                  <button type="button" onClick={save} disabled={saving || !dirty || problems.length > 0 || !!(validation && !validation.valid)}
                    className="flex items-center gap-1.5 text-xs px-5 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white font-semibold shadow-md shadow-emerald-600/20">
                    {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />} {form.id ? 'Save new version' : 'Create algo'}
                  </button>
                  {dirty && form.id && (
                    <button type="button" onClick={() => openAlgoFresh(form.id!)} className="text-xs px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-700">
                      <RotateCcw size={12} className="inline mr-1" /> Discard changes
                    </button>
                  )}
                  <span className="text-[11px] text-slate-400">Every save keeps a version you can restore.</span>
                </div>
              </div>
            </div>

            {/* ---- test */}
            <TestPanel meta={meta} form={form} open={showTest} onToggle={() => setShowTest(!showTest)} />
          </>
        )}

        {/* ---- logs */}
        <div className={`${panelCls} overflow-hidden`}>
          <div className="flex items-center gap-3 px-5 py-3 border-b border-slate-200 dark:border-slate-800">
            <History size={16} className="text-emerald-500" />
            <h3 className="text-sm font-bold">Execution log</h3>
            <span className="text-[11px] text-slate-400">{form?.id ? `for ${form.algo_code}` : 'all algos'} · matches and errors only</span>
            <button type="button" onClick={() => loadLogs(form?.id)} className="ml-auto text-[11px] px-3 py-1.5 rounded-lg border border-slate-300 dark:border-slate-700">Refresh</button>
          </div>
          {logs.length === 0 ? (
            <div className="p-8 text-center text-xs text-slate-400">Nothing logged yet. Entries appear when an algo matches or fails during a real transaction.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-[11px]">
                <thead>
                  <tr className="text-left text-[10px] uppercase tracking-wider text-slate-400 bg-slate-50 dark:bg-slate-950/50">
                    <th className="px-4 py-2">Time</th><th className="px-2 py-2">Algo</th><th className="px-2 py-2">Card</th>
                    <th className="px-2 py-2">Action</th><th className="px-2 py-2">RC</th><th className="px-2 py-2">Result</th><th className="px-2 py-2 text-right">ms</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map((l) => (
                    <tr key={l.id} className="border-t border-slate-100 dark:border-slate-800/80">
                      <td className="px-4 py-2 font-mono text-slate-400 whitespace-nowrap" title={fmtTime(l.created_at)}>{ago(l.created_at)}</td>
                      <td className="px-2 py-2 font-mono font-bold text-emerald-500">{l.algo_code}</td>
                      <td className="px-2 py-2 font-mono text-slate-400">{l.masked_pan || '—'}</td>
                      <td className="px-2 py-2">
                        {l.error ? <Badge tone="rose">ERROR</Badge> : <Badge tone={ACTION_TONE[l.action] || 'slate'}>{l.action}</Badge>}{' '}
                        {l.mode === 'MONITOR' ? <Badge tone="amber">MONITOR</Badge> : l.action_applied ? <Badge tone="emerald">applied</Badge> : null}
                      </td>
                      <td className="px-2 py-2 font-mono">{l.response_code || '—'}</td>
                      <td className="px-2 py-2 text-slate-400 max-w-[320px] truncate" title={l.error || l.message}>{l.error || l.message}</td>
                      <td className="px-2 py-2 text-right font-mono text-slate-400">{l.duration_ms}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* ===================== modals */}
      {showFields && (
        <FieldsModal catalog={catalog} schema={schema} language={form?.language || 'PYTHON'} hasEditor={!!form}
          onInsert={insertField} onClose={() => setShowFields(false)} onCopied={() => show('Copied')} />
      )}
      {showTemplates && (
        <Modal title={<span className="flex items-center gap-2"><Sparkles size={15} className="text-emerald-500" /> Algo templates</span>} onClose={() => setShowTemplates(false)} size="xl">
          {templates.length === 0 ? (
            <div className="p-8 text-center text-xs text-slate-400"><Loader2 className="animate-spin mx-auto mb-2" size={18} /> Loading...</div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {templates.map((t) => (
                <div key={t.key} className="rounded-xl border border-slate-200 dark:border-slate-800 p-4 flex flex-col gap-2">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs font-bold">{t.title}</span>
                    <Badge tone={t.language === 'SQL' ? 'sky' : 'violet'}>{t.language}</Badge>
                    <Badge tone={ACTION_TONE[t.default_action] || 'slate'}>{t.default_action}</Badge>
                    {t.stage === 'POST_AUTH' && <Badge tone="amber">POST_AUTH</Badge>}
                  </div>
                  <p className="text-[11px] text-slate-400">{t.description}</p>
                  <pre className="text-[10px] font-mono bg-slate-950 text-slate-300 rounded-lg p-2.5 overflow-x-auto max-h-28">{t.code}</pre>
                  <button type="button" onClick={() => applyTemplate(t)} aria-label={`use template ${t.key}`}
                    className="self-start flex items-center gap-1.5 text-[11px] px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold">
                    Use this template
                  </button>
                </div>
              ))}
            </div>
          )}
        </Modal>
      )}
      {showVersions && (
        <Modal title={`Version history - ${form?.algo_code}`} onClose={() => setShowVersions(false)} size="lg">
          <div className="space-y-3">
            {versions.map((v) => (
              <div key={v.version} className="rounded-xl border border-slate-200 dark:border-slate-800 p-3">
                <div className="flex items-center gap-2 flex-wrap">
                  <Badge tone={v.version === form?.version ? 'emerald' : 'slate'}>v{v.version}{v.version === form?.version ? ' current' : ''}</Badge>
                  <span className="text-[11px] text-slate-400">{v.change_note} · {v.changed_by} · {fmtTime(v.created_at)}</span>
                  {v.version !== form?.version && (
                    <button type="button" onClick={() => rollback(v.version)} aria-label={`restore v${v.version}`}
                      className="ml-auto text-[11px] px-3 py-1 rounded-lg bg-amber-500/10 text-amber-500 hover:bg-amber-500/20">
                      Restore
                    </button>
                  )}
                </div>
                <pre className="mt-2 text-[10px] font-mono bg-slate-950 text-slate-300 rounded-lg p-2.5 overflow-x-auto max-h-40">{v.code}</pre>
              </div>
            ))}
          </div>
        </Modal>
      )}
    </div>
  );
};

// ============================================================================
// Fields reference modal
// ============================================================================
const FieldsModal: React.FC<{
  catalog: any | null;
  schema: any[];
  language: string;
  hasEditor: boolean;
  onInsert: (text: string) => void;
  onClose: () => void;
  onCopied: () => void;
}> = ({ catalog, schema, language, hasEditor, onInsert, onClose, onCopied }) => {
  const [tab, setTab] = useState<'fields' | 'actions' | 'sql' | 'notes'>('fields');
  const [term, setTerm] = useState('');
  const [group, setGroup] = useState('ALL');
  const isSql = language === 'SQL';

  const copy = (text: string) => {
    try {
      navigator.clipboard?.writeText(text);
      onCopied();
    } catch {
      /* ignore */
    }
  };

  const groups: any[] = catalog?.groups || [];
  const t = term.trim().toLowerCase();
  const filtered = groups
    .filter((g) => group === 'ALL' || g.group === group)
    .map((g) => ({
      ...g,
      fields: g.fields.filter((f: any) => !t || `${f.python} ${f.sql} ${f.description}`.toLowerCase().includes(t)),
    }))
    .filter((g) => g.fields.length);

  return (
    <Modal title={<span className="flex items-center gap-2"><BookOpen size={15} className="text-sky-500" /> Fields Reference</span>} onClose={onClose} size="xl">
      {!catalog ? (
        <div className="p-10 text-center text-xs text-slate-400"><Loader2 className="animate-spin mx-auto mb-2" size={18} /> Loading...</div>
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            {([['fields', 'Fields'], ['actions', 'Actions & helpers'], ['sql', 'SQL tables'], ['notes', 'Notes']] as const).map(([id, label]) => (
              <button key={id} type="button" onClick={() => setTab(id)}
                className={`text-xs px-3.5 py-1.5 rounded-lg font-semibold ${tab === id ? 'bg-sky-600 text-white' : 'bg-slate-100 dark:bg-slate-800 text-slate-500'}`}>
                {label}
              </button>
            ))}
            <span className="ml-auto text-[11px] text-slate-400">
              {hasEditor ? <>Click a name to insert it into your {isSql ? 'SQL' : 'Python'} code</> : 'Open an algo to insert fields'}
            </span>
          </div>

          {tab === 'fields' && (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <div className="relative flex-1 min-w-[220px]">
                  <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
                  <input autoFocus value={term} onChange={(e) => setTerm(e.target.value)} placeholder="search: amount, hour, bank, terminal owner, balance ..." aria-label="search fields" className={`${inputCls} pl-8`} />
                </div>
                <select aria-label="field group" value={group} onChange={(e) => setGroup(e.target.value)} className={`${inputCls} !w-auto`}>
                  <option value="ALL">All groups</option>
                  {groups.map((g) => <option key={g.group} value={g.group}>{g.title}</option>)}
                </select>
              </div>
              {filtered.length === 0 && <div className="text-xs text-slate-400 p-6 text-center">No field matches "{term}".</div>}
              {filtered.map((g) => (
                <div key={g.group} className="rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden">
                  <div className="px-4 py-2 bg-slate-50 dark:bg-slate-950/50 flex items-center gap-2">
                    <span className="text-xs font-bold">{g.title}</span>
                    <span className="text-[10px] text-slate-400 font-mono">{g.hint}</span>
                  </div>
                  <div className="divide-y divide-slate-100 dark:divide-slate-800/80">
                    {g.fields.map((f: any) => (
                      <div key={f.python} className="grid grid-cols-12 gap-3 items-center px-4 py-2">
                        <div className="col-span-12 md:col-span-3">
                          <button type="button" disabled={!hasEditor || isSql} onClick={() => onInsert(f.python)} aria-label={`insert ${f.python}`}
                            className="font-mono text-[11px] font-bold text-emerald-400 hover:underline disabled:no-underline disabled:opacity-60 text-left">
                            {f.python}
                          </button>
                        </div>
                        <div className="col-span-12 md:col-span-3">
                          <button type="button" disabled={!hasEditor || !isSql} onClick={() => onInsert(f.sql)} aria-label={`insert ${f.sql}`}
                            className="font-mono text-[11px] text-sky-400 hover:underline disabled:no-underline disabled:opacity-60 text-left">
                            {f.sql}
                          </button>
                        </div>
                        <div className="col-span-3 md:col-span-1"><Badge tone={f.type === 'number' ? 'violet' : f.type === 'bool' ? 'amber' : 'slate'}>{f.type}</Badge></div>
                        <div className="col-span-9 md:col-span-4 text-[11px] text-slate-400 leading-snug">
                          {f.description} <span className="font-mono text-slate-500">e.g. {String(f.example)}</span>
                        </div>
                        <div className="hidden md:flex md:col-span-1 justify-end">
                          <button type="button" aria-label={`copy ${f.python}`} onClick={() => copy(isSql ? f.sql : f.python)} className="text-slate-500 hover:text-slate-300"><Copy size={12} /></button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </>
          )}

          {tab === 'actions' && (
            <div className="space-y-4">
              <div className="rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden">
                <div className="px-4 py-2 bg-slate-50 dark:bg-slate-950/50 text-xs font-bold">Decisions</div>
                {catalog.actions.map((a: any) => (
                  <div key={a.name} className="px-4 py-2 border-t border-slate-100 dark:border-slate-800/80 flex flex-wrap gap-3 items-start">
                    <button type="button" disabled={!hasEditor} onClick={() => onInsert(a.name.replace(/\(.*\)/, '()'))} className="font-mono text-[11px] font-bold text-rose-300 hover:underline text-left">{a.name}</button>
                    <span className="text-[11px] text-slate-400 flex-1 min-w-[240px]">{a.description}</span>
                  </div>
                ))}
              </div>
              <div className="rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden">
                <div className="px-4 py-2 bg-slate-50 dark:bg-slate-950/50 text-xs font-bold">History and helpers (Python)</div>
                {catalog.history.map((h: any) => (
                  <div key={h.name} className="px-4 py-2 border-t border-slate-100 dark:border-slate-800/80">
                    <div className="font-mono text-[11px] text-emerald-300 break-all">{h.name}</div>
                    <div className="text-[11px] text-slate-400 mt-0.5">{h.description}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {tab === 'sql' && (
            <div className="space-y-4">
              <div className="rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden">
                <div className="px-4 py-2 bg-slate-50 dark:bg-slate-950/50 text-xs font-bold">Time parameters</div>
                {catalog.time_params.map((p: any) => (
                  <div key={p.sql} className="px-4 py-2 border-t border-slate-100 dark:border-slate-800/80 flex gap-3">
                    <button type="button" disabled={!hasEditor} onClick={() => onInsert(p.sql)} className="font-mono text-[11px] font-bold text-sky-400 hover:underline w-28 text-left">{p.sql}</button>
                    <span className="text-[11px] text-slate-400">{p.description}</span>
                  </div>
                ))}
              </div>
              {schema.map((t) => (
                <div key={t.table} className="rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden">
                  <div className="px-4 py-2 bg-slate-50 dark:bg-slate-950/50 text-xs font-bold font-mono">{t.table}</div>
                  <div className="p-3 flex flex-wrap gap-1.5">
                    {t.columns.map((c: any) => (
                      <button key={c.name} type="button" disabled={!hasEditor} onClick={() => onInsert(c.name)} title={c.type}
                        className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-500/10 text-slate-300 hover:bg-slate-500/20">
                        {c.name}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}

          {tab === 'notes' && (
            <ul className="space-y-2 text-xs text-slate-300 list-disc pl-5">
              {catalog.notes.map((n: string, i: number) => <li key={i}>{n}</li>)}
            </ul>
          )}
        </div>
      )}
    </Modal>
  );
};

// ============================================================================
// Test panel (dry run on a real card, nothing is saved or blocked)
// ============================================================================
const TestPanel: React.FC<{ meta: any; form: AlgoForm; open: boolean; onToggle: () => void }> = ({ meta, form, open, onToggle }) => {
  const cards: any[] = meta?.cards || [];
  const [cardId, setCardId] = useState('');
  const [f, setF] = useState<any>({ amount: 25000, channel: 'ATM', tran_code: '10', hour: 2, mcc: '', country: '050', terminal_id: '', acquirer_code: '' });
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<any | null>(null);
  const [err, setErr] = useState('');
  const [showCtx, setShowCtx] = useState(false);
  const chosen = cardId || cards[0]?.id || '';

  const run = async () => {
    setBusy(true);
    setErr('');
    try {
      const overrides: Record<string, any> = { ...f };
      Object.keys(overrides).forEach((k) => overrides[k] === '' && delete overrides[k]);
      const draft = {
        algo_code: form.algo_code || 'DRAFT', name: form.name, language: form.language, code: form.code, mode: form.mode,
        default_action: form.default_action, default_response_code: form.default_response_code,
        default_message: form.default_message, on_error: form.on_error, stop_on_match: form.stop_on_match, stage: form.stage,
      };
      const r = await apiFetch('/local-host/algos/test', { method: 'POST', body: JSON.stringify({ draft, card_id: chosen || null, overrides }) });
      setRes(r);
      if (!r.ok) setErr((r.errors || []).join('; '));
    } catch (e: any) {
      setErr(e.message || 'Test failed');
      setRes(null);
    } finally {
      setBusy(false);
    }
  };

  const result = res?.result;
  return (
    <div className={`${panelCls} overflow-hidden`}>
      <button type="button" onClick={onToggle} className="w-full flex items-center gap-3 px-5 py-3 text-left border-b border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/30">
        <FlaskConical size={16} className="text-violet-400" />
        <h3 className="text-sm font-bold">Test run</h3>
        <span className="text-[11px] text-slate-400">Dry run on a real card with sample values. Nothing is saved, declined or blocked.</span>
        <ChevronDown size={14} className={`ml-auto text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="p-5 space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Labeled label="Card" className="col-span-2">
              <select aria-label="test card" className={`${inputCls} font-mono`} value={chosen} onChange={(e) => setCardId(e.target.value)}>
                {cards.map((c) => <option key={c.id} value={c.id}>{c.masked_pan} · {c.bank_code} · {c.holder}</option>)}
              </select>
            </Labeled>
            <Labeled label="Amount"><input aria-label="test amount" type="number" className={`${inputCls} font-mono`} value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></Labeled>
            <Labeled label="Hour (0-23)"><input aria-label="test hour" type="number" min={0} max={23} className={`${inputCls} font-mono`} value={f.hour} onChange={(e) => setF({ ...f, hour: e.target.value })} /></Labeled>
            <Labeled label="Channel">
              <select aria-label="test channel" className={inputCls} value={f.channel} onChange={(e) => setF({ ...f, channel: e.target.value })}>
                {(meta?.channels || []).map((c: string) => <option key={c}>{c}</option>)}
              </select>
            </Labeled>
            <Labeled label="Transaction code">
              <select aria-label="test tran code" className={inputCls} value={f.tran_code} onChange={(e) => setF({ ...f, tran_code: e.target.value })}>
                {(meta?.transaction_codes || []).map((t: any) => <option key={t.code} value={t.code}>{t.code} {t.name}</option>)}
              </select>
            </Labeled>
            <Labeled label="MCC"><input aria-label="test mcc" className={`${inputCls} font-mono`} placeholder="auto" value={f.mcc} onChange={(e) => setF({ ...f, mcc: e.target.value })} /></Labeled>
            <Labeled label="Country (DE19)"><input aria-label="test country" className={`${inputCls} font-mono`} value={f.country} onChange={(e) => setF({ ...f, country: e.target.value })} /></Labeled>
            <Labeled label="Terminal owner (bank)">
              <select aria-label="test terminal owner" className={inputCls} value={f.acquirer_code} onChange={(e) => setF({ ...f, acquirer_code: e.target.value })}>
                <option value="">card's own bank (ON_US)</option>
                {(meta?.banks || []).map((b: any) => <option key={b.id} value={b.code}>{b.code}</option>)}
              </select>
            </Labeled>
            <Labeled label="Terminal id"><input aria-label="test terminal" className={`${inputCls} font-mono`} placeholder="auto" value={f.terminal_id} onChange={(e) => setF({ ...f, terminal_id: e.target.value })} /></Labeled>
          </div>
          <div className="flex items-center gap-3">
            <button type="button" onClick={run} disabled={busy || !form.code.trim()}
              className="flex items-center gap-1.5 text-xs px-5 py-2 rounded-lg bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white font-semibold">
              {busy ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />} Run test
            </button>
            {err && <span className="text-xs text-rose-500 font-mono">{err}</span>}
          </div>

          {result && (
            <div className="space-y-3" data-testid="test-result">
              <div className={`flex flex-wrap items-center gap-3 p-4 rounded-xl border ${
                result.error ? 'bg-rose-500/10 border-rose-500/30' : result.matched ? 'bg-amber-500/10 border-amber-500/30' : 'bg-emerald-500/10 border-emerald-500/30'}`}>
                {result.error ? <AlertTriangle className="text-rose-500" size={22} /> : result.matched ? <ShieldOff className="text-amber-500" size={22} /> : <CheckCircle2 className="text-emerald-500" size={22} />}
                <div className="min-w-0">
                  <div className="text-sm font-bold">
                    {result.error ? 'The algo has an error' : result.matched ? <>Matched: <span className="text-amber-500">{result.action}</span>{result.response_code ? ` (RC ${result.response_code})` : ''}</> : 'Condition not met - transaction would continue'}
                  </div>
                  <div className="text-[11px] text-slate-400 break-words">
                    {result.error || result.message || ''} · {result.duration_ms} ms · mode {result.mode}
                    {result.matched && result.mode === 'MONITOR' ? ' (monitor: no effect)' : ''}
                    {result.would_block_card ? ' · would block the card' : ''}
                    {result.would_block_customer ? ' · would block the customer' : ''}
                  </div>
                </div>
              </div>
              {result.logs?.length > 0 && (
                <pre className="text-[11px] font-mono bg-slate-950 text-emerald-300 rounded-xl p-3">{result.logs.join('\n')}</pre>
              )}
              {result.rows && result.rows.length > 0 && (
                <pre className="text-[11px] font-mono bg-slate-950 text-sky-300 rounded-xl p-3 overflow-x-auto">{JSON.stringify(result.rows, null, 2)}</pre>
              )}
              <button type="button" onClick={() => setShowCtx(!showCtx)} className="text-[11px] text-slate-400 hover:text-slate-200 underline">
                {showCtx ? 'Hide' : 'Show'} the values this test used
              </button>
              {showCtx && res.context && (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  {Object.entries(res.context).map(([g, vals]: [string, any]) => (
                    <div key={g} className="rounded-xl border border-slate-200 dark:border-slate-800 p-3">
                      <div className="text-[10px] uppercase tracking-wider font-bold text-slate-400 mb-1.5">{g}</div>
                      {Object.entries(vals).map(([k, v]: [string, any]) => (
                        <div key={k} className="flex justify-between gap-2 text-[10px] font-mono py-0.5">
                          <span className="text-slate-500">{k}</span>
                          <span className="text-slate-300 truncate max-w-[140px]" title={String(v)}>{String(v)}</span>
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
'''

HC_PAGE_TSX = r'''import React, { useCallback, useEffect, useState } from 'react';
import {
  Activity,
  Cable,
  CircleDollarSign,
  CreditCard,
  Eye,
  FileCode2,
  Globe2,
  Landmark,
  Loader2,
  Network,
  ScrollText,
  Server,
  ShieldAlert,
  ShieldCheck,
  SlidersHorizontal,
} from 'lucide-react';
import { apiFetch } from '../../api';
import { RulesAndChecksTab } from './RulesAndChecksTab';
import { LocalHostTab } from './LocalHostTab';
import { AlgoControlTab } from './AlgoControlTab';
import { Badge, Toggle, fmtNum, panelCls } from './ui';

// ============================================================================
// RAJON HOST CONTROL CENTER
//   Local Host    - per bank / global transaction policy
//   Algo Control  - Python / SQL risk blocks (approve / decline / block card / block customer)
//   Rules & Checks - built-in check switches + simple rules (replaces menu 7.5 and the old parameter table)
//   CBS / External Host - planned connectors
// ============================================================================

type TabId = 'local' | 'algo' | 'rules' | 'cbs' | 'external';

const TABS: { id: TabId; label: string; icon: React.ReactNode; note?: string }[] = [
  { id: 'local', label: 'Local Host', icon: <Server size={15} /> },
  { id: 'algo', label: 'Algo Control', icon: <FileCode2 size={15} /> },
  { id: 'rules', label: 'Rules & Checks', icon: <ScrollText size={15} /> },
  { id: 'cbs', label: 'CBS', icon: <Landmark size={15} />, note: 'soon' },
  { id: 'external', label: 'External Host', icon: <Globe2 size={15} />, note: 'soon' },
];

const Kpi: React.FC<{ icon: React.ReactNode; label: string; value: React.ReactNode; tone: string; sub?: string }> = ({
  icon,
  label,
  value,
  tone,
  sub,
}) => (
  <div className={`rounded-xl px-4 py-3 border ${tone} flex items-center gap-3 min-w-[150px]`}>
    <div className="opacity-90">{icon}</div>
    <div>
      <div className="text-[10px] uppercase tracking-wider font-bold opacity-80">{label}</div>
      <div className="text-xl font-bold font-mono leading-tight">{value}</div>
      {sub && <div className="text-[10px] opacity-70 truncate max-w-[130px]">{sub}</div>}
    </div>
  </div>
);

export const HostControlCenterPage: React.FC = () => {
  const [tab, setTab] = useState<TabId>('local');
  const [meta, setMeta] = useState<any | null>(null);
  const [overview, setOverview] = useState<any | null>(null);
  const [metaError, setMetaError] = useState('');

  const loadOverview = useCallback(async () => {
    try {
      setOverview(await apiFetch('/local-host/overview'));
    } catch {
      /* the strip is optional */
    }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        setMeta(await apiFetch('/local-host/meta'));
      } catch (e: any) {
        setMetaError(e.message || 'Could not load the host control data. Is the backend updated (patch 4)?');
      }
    })();
    loadOverview();
  }, [loadOverview]);

  return (
    <div className="space-y-5">
      {/* ------------------------------------------------ banner */}
      <div className="relative overflow-hidden rounded-2xl border border-emerald-500/20 bg-gradient-to-br from-emerald-600/15 via-sky-500/10 to-violet-500/10 p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold tracking-tight flex items-center gap-2">
              <SlidersHorizontal className="text-emerald-500" size={24} />
              Host Control Center
            </h1>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 max-w-2xl">
              Decide how your host authorizes transactions: policy per bank and per source system, plus your own Python / SQL risk
              algos that can approve, decline, block a card or block a customer.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Kpi icon={<FileCode2 size={18} />} label="Active algos" value={overview ? overview.algos_active : '—'}
              sub={overview ? `${overview.algos_monitor} in monitor` : undefined} tone="bg-emerald-500/10 text-emerald-500 border-emerald-500/20" />
            <Kpi icon={<Activity size={18} />} label="Matches 24h" value={overview ? fmtNum(overview.matches_24h, 0) : '—'}
              sub={overview?.top_algos?.[0] ? `top: ${overview.top_algos[0].algo_code}` : undefined} tone="bg-sky-500/10 text-sky-500 border-sky-500/20" />
            <Kpi icon={<ShieldAlert size={18} />} label="Blocks 24h" value={overview ? fmtNum(overview.blocks_24h, 0) : '—'}
              sub={overview && overview.errors_24h ? `${overview.errors_24h} algo errors` : undefined} tone="bg-rose-500/10 text-rose-500 border-rose-500/20" />
            <Kpi icon={<Landmark size={18} />} label="Bank overrides" value={overview ? overview.bank_overrides : '—'} tone="bg-violet-500/10 text-violet-400 border-violet-500/20" />
          </div>
        </div>
      </div>

      {/* ------------------------------------------------ tabs */}
      <div className="flex flex-wrap gap-1.5 p-1.5 rounded-2xl bg-slate-100 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 w-fit max-w-full">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            aria-label={`tab ${t.label}`}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold transition-all ${
              tab === t.id
                ? 'bg-white dark:bg-slate-800 text-emerald-500 shadow-sm'
                : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
            }`}
          >
            {t.icon}
            {t.label}
            {t.note && <span className="text-[9px] px-1.5 py-0.5 rounded bg-slate-500/15 text-slate-400 uppercase">{t.note}</span>}
          </button>
        ))}
      </div>

      {metaError && (tab === 'local' || tab === 'algo' || tab === 'rules') && (
        <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-500 text-xs font-mono" role="alert">{metaError}</div>
      )}

      {/* ------------------------------------------------ content */}
      {tab === 'local' &&
        (meta ? <LocalHostTab meta={meta} onChanged={loadOverview} /> : !metaError && <Loading />)}
      {tab === 'algo' &&
        (meta ? <AlgoControlTab meta={meta} onChanged={loadOverview} /> : !metaError && <Loading />)}
      {tab === 'rules' &&
        (meta ? <RulesAndChecksTab meta={meta} onChanged={loadOverview} /> : !metaError && <Loading />)}
      {tab === 'cbs' && <CbsPlaceholder />}
      {tab === 'external' && <ExternalPlaceholder />}
    </div>
  );
};

const Loading: React.FC = () => (
  <div className={`${panelCls} p-12 text-center text-slate-400 text-xs`}>
    <Loader2 className="animate-spin mx-auto mb-2" size={20} /> Loading host control...
  </div>
);

// ---------------------------------------------------------------- placeholders (later phases)
const Roadmap: React.FC<{
  icon: React.ReactNode;
  title: string;
  lead: string;
  items: { icon: React.ReactNode; title: string; text: string }[];
  mode: string;
}> = ({ icon, title, lead, items, mode }) => (
  <div className="space-y-4">
    <div className={`${panelCls} p-8 text-center`}>
      <div className="w-16 h-16 mx-auto rounded-2xl bg-gradient-to-br from-sky-500/20 to-violet-500/20 text-sky-400 flex items-center justify-center mb-4">{icon}</div>
      <div className="flex items-center justify-center gap-2">
        <h3 className="text-base font-bold">{title}</h3>
        <Badge tone="amber">PLANNED</Badge>
      </div>
      <p className="text-xs text-slate-400 mt-2 max-w-xl mx-auto leading-relaxed">{lead}</p>
      <div className="inline-flex items-center gap-3 mt-4 px-4 py-2 rounded-xl bg-slate-100 dark:bg-slate-800">
        <span className="text-[11px] text-slate-500">Current mode</span>
        <Badge tone="emerald">{mode}</Badge>
        <Toggle checked={false} onChange={() => undefined} disabled label={`${title} connector`} />
        <span className="text-[11px] text-slate-500">connector off</span>
      </div>
    </div>
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {items.map((it) => (
        <div key={it.title} className={`${panelCls} p-5 opacity-80`}>
          <div className="w-9 h-9 rounded-xl bg-sky-500/10 text-sky-400 flex items-center justify-center mb-3">{it.icon}</div>
          <div className="text-xs font-bold">{it.title}</div>
          <p className="text-[11px] text-slate-400 mt-1 leading-relaxed">{it.text}</p>
        </div>
      ))}
    </div>
  </div>
);

const CbsPlaceholder: React.FC = () => (
  <Roadmap
    icon={<Landmark size={30} />}
    title="Core Banking System (CBS)"
    lead="Today the host posts to its own simulated ledger. This tab will connect the host to a real CBS so balances, holds and postings come from the bank."
    mode="Standalone ledger"
    items={[
      { icon: <CircleDollarSign size={18} />, title: 'Balance and hold', text: 'Real-time balance inquiry, authorization hold and release against the CBS account.' },
      { icon: <Cable size={18} />, title: 'Posting', text: 'Debit / credit posting, reversal and end-of-day reconciliation with the core.' },
      { icon: <ShieldCheck size={18} />, title: 'Stand-in', text: 'Decision rules when the CBS is slow or down (stand-in limits, advice queue).' },
    ]}
  />
);

const ExternalPlaceholder: React.FC = () => (
  <Roadmap
    icon={<Globe2 size={30} />}
    title="External Hosts: Visa, Mastercard, NPSB"
    lead="Gateways to the card schemes and the national switch. Each one will get its own connection profile, message mapping and routing rules."
    mode="Simulated schemes"
    items={[
      { icon: <CreditCard size={18} />, title: 'Visa / Mastercard', text: 'Network connections, BIN routing, key exchange and scheme specific response mapping.' },
      { icon: <Network size={18} />, title: 'NPSB', text: 'Domestic interbank switch connection, settlement files and dispute handling.' },
      { icon: <Eye size={18} />, title: 'Monitoring', text: 'Connection health, latency and stand-in when an external host is unreachable.' },
    ]}
  />
);
'''

HC_RULES_TSX = r'''import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  Info,
  ListChecks,
  Loader2,
  Play,
  Plus,
  Save,
  ShieldCheck,
  Sparkles,
  Trash2,
  Wand2,
  XCircle,
} from 'lucide-react';
import { apiFetch } from '../../api';
import {
  Badge,
  Labeled,
  NumInput,
  RcSelect,
  SegButtons,
  Toggle,
  fmtNum,
  inputCls,
  panelCls,
  useToast,
} from './ui';

// ============================================================================
// RULES & CHECKS
//   1. Built-in checks  - the switches the host engine really reads (balance, card limits, account limits)
//   2. Simple rules     - one condition, no coding, can be added / edited / tested here
//   (scripts live in the Algo Control tab)
// ============================================================================

type Section = 'checks' | 'rules';

interface Cond {
  field: string;
  op: string;
  value: string;
}
interface RuleForm {
  id?: string;
  rule_code: string;
  name: string;
  description: string;
  mode: 'BUILDER' | 'SCRIPT';
  logic: 'AND' | 'OR';
  conditions: Cond[];
  expression: string;
  action: 'DECLINE' | 'APPROVE' | 'FLAG';
  response_code: string;
  message: string;
  priority: number;
  stop_on_match: boolean;
  enabled: boolean;
}

const blankRule = (): RuleForm => ({
  rule_code: '', name: '', description: '', mode: 'BUILDER', logic: 'AND',
  conditions: [{ field: 'amount', op: '>', value: '' }], expression: '', action: 'DECLINE',
  response_code: '61', message: 'Declined by rule', priority: 100, stop_on_match: true, enabled: true,
});

const NUM_OPS = [
  { v: '>', t: 'is greater than' }, { v: '>=', t: 'is at least' }, { v: '<', t: 'is less than' },
  { v: '<=', t: 'is at most' }, { v: '==', t: 'equals' }, { v: '!=', t: 'does not equal' },
];
const TEXT_OPS = [
  { v: '==', t: 'equals' }, { v: '!=', t: 'does not equal' }, { v: 'in', t: 'is one of (comma list)' },
  { v: 'not in', t: 'is none of (comma list)' },
];
const BOOL_OPS = [{ v: 'true', t: 'is true' }, { v: 'false', t: 'is false' }];

const ACTION_HELP: Record<string, string> = {
  DECLINE: 'Stops the transaction with the response code below.',
  APPROVE: 'Accepts at the rule layer and stops the remaining rules (PIN, limits and balance still apply).',
  FLAG: 'Only records the match and lets the transaction continue.',
};

const lit = (type: string, v: string) =>
  type === 'number' ? String(Number(v)) : `'${String(v).trim().replace(/\\/g, '\\\\').replace(/'/g, "\\'")}'`;

/** one condition -> expression text understood by the host rule engine */
export const condToExpr = (c: Cond, type: string): string => {
  if (type === 'bool') return c.op === 'false' ? `not ${c.field}` : c.field;
  if (c.op === 'in' || c.op === 'not in') {
    const items = c.value.split(',').map((x) => x.trim()).filter(Boolean);
    if (!items.length) return '';
    const parts = items.map((x) => `${c.field} ${c.op === 'in' ? '==' : '!='} ${lit(type, x)}`);
    return items.length === 1 ? parts[0] : `(${parts.join(c.op === 'in' ? ' or ' : ' and ')})`;
  }
  if (c.value.trim() === '') return '';
  if (type === 'number' && Number.isNaN(Number(c.value))) return '';
  return `${c.field} ${c.op} ${lit(type, c.value)}`;
};

interface Props {
  meta: any;
  onChanged?: () => void;
}

export const RulesAndChecksTab: React.FC<Props> = ({ meta, onChanged }) => {
  const { show, node: toastNode } = useToast();
  const [section, setSection] = useState<Section>('checks');
  return (
    <div className="space-y-5">
      {toastNode}
      <div className={`${panelCls} p-5`}>
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-xl bg-emerald-500/10 text-emerald-500 flex items-center justify-center shrink-0">
            <Info size={18} />
          </div>
          <div className="text-xs text-slate-400 leading-relaxed">
            <div className="text-sm font-bold text-slate-200 mb-1">How the host decides, from simple to advanced</div>
            <ol className="list-decimal pl-4 space-y-0.5">
              <li><strong className="text-slate-300">Built-in checks</strong>: ready-made protections you switch on or off (balance, card limits, account limits).</li>
              <li><strong className="text-slate-300">Simple rules</strong>: your own "if this, then decline / approve / flag" rules. No coding, built with dropdowns.</li>
              <li><strong className="text-slate-300">Algo Control</strong> (next tab): Python or SQL blocks for anything more complex, per bank or card profile.</li>
            </ol>
          </div>
        </div>
      </div>

      <SegButtons
        value={section}
        onChange={(v) => setSection(v as Section)}
        options={[
          { value: 'checks', label: 'Built-in checks' },
          { value: 'rules', label: 'My simple rules', tone: 'sky' },
        ]}
      />

      {section === 'checks' ? <BuiltInChecks show={show} onChanged={onChanged} /> : <SimpleRules meta={meta} show={show} onChanged={onChanged} />}
    </div>
  );
};

// ============================================================================
// 1. Built-in checks
// ============================================================================
const BuiltInChecks: React.FC<{ show: (t: string, e?: boolean) => void; onChanged?: () => void }> = ({ show, onChanged }) => {
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showRef, setShowRef] = useState(false);

  const load = useCallback(async () => {
    try {
      setRows(await apiFetch('/local-host/checks'));
    } catch (e: any) {
      show(e.message || 'Could not load the checks', true);
    } finally {
      setLoading(false);
    }
  }, [show]);
  useEffect(() => {
    load();
  }, [load]);

  const toggle = async (r: any, enabled: boolean) => {
    if (!enabled && r.affects_host && !confirm(`Switch OFF "${r.title}" for every bank?\n\n${r.when_off || ''}`)) return;
    try {
      await apiFetch(`/local-host/checks/${r.id}/toggle`, { method: 'POST', body: JSON.stringify({ enabled }) });
      setRows((list) => list.map((x) => (x.id === r.id ? { ...x, enabled } : x)));
      show(`${r.title} is now ${enabled ? 'ON' : 'OFF'}`);
      onChanged?.();
    } catch (e: any) {
      show(e.message || 'Could not change the check', true);
    }
  };

  const live = rows.filter((r) => r.affects_host);
  const ref = rows.filter((r) => !r.affects_host);

  if (loading) return <div className={`${panelCls} p-10 text-center text-xs text-slate-400`}><Loader2 className="animate-spin mx-auto mb-2" size={18} /> Loading...</div>;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {live.map((r) => (
          <div key={r.id} className={`${panelCls} p-5 flex flex-col gap-3 ${r.enabled ? '' : 'border-rose-500/30'}`}>
            <div className="flex items-start gap-3">
              <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${r.enabled ? 'bg-emerald-500/10 text-emerald-500' : 'bg-rose-500/10 text-rose-500'}`}>
                <ShieldCheck size={18} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-bold">{r.title}</div>
                <div className="text-[10px] font-mono text-slate-500">{r.name}</div>
              </div>
              <Toggle checked={r.enabled} label={`${r.title} switch`} onChange={(v) => toggle(r, v)} />
            </div>
            <p className="text-[11px] text-slate-400 leading-relaxed">{r.what}</p>
            <div className="mt-auto flex flex-wrap items-center gap-2">
              <Badge tone={r.enabled ? 'emerald' : 'rose'}>{r.enabled ? 'ON' : 'OFF'}</Badge>
              {r.decline_rc && <Badge tone="slate">declines with RC {r.decline_rc}</Badge>}
              {r.order && <Badge tone="slate">step {r.order}</Badge>}
            </div>
            {!r.enabled && r.when_off && (
              <div className="flex items-start gap-2 text-[11px] text-rose-400 bg-rose-500/10 border border-rose-500/20 rounded-lg p-2.5">
                <AlertTriangle size={13} className="mt-0.5 shrink-0" /> {r.when_off}
              </div>
            )}
          </div>
        ))}
      </div>

      {ref.length > 0 && (
        <div className={`${panelCls} overflow-hidden`}>
          <button type="button" onClick={() => setShowRef(!showRef)} className="w-full flex items-center gap-3 px-5 py-3 text-left hover:bg-slate-50 dark:hover:bg-slate-800/30">
            <Info size={15} className="text-slate-400" />
            <span className="text-xs font-bold">Reference parameters ({ref.length})</span>
            <span className="text-[11px] text-slate-400">Stored for documentation. The host engine does not read them, so they have no switch.</span>
            <ChevronDown size={14} className={`ml-auto text-slate-400 transition-transform ${showRef ? 'rotate-180' : ''}`} />
          </button>
          {showRef && (
            <div className="divide-y divide-slate-100 dark:divide-slate-800/80 border-t border-slate-200 dark:border-slate-800">
              {ref.map((r) => (
                <div key={r.id} className="px-5 py-3 grid grid-cols-12 gap-3 items-start">
                  <div className="col-span-12 md:col-span-3">
                    <div className="text-xs font-semibold">{r.title}</div>
                    <div className="text-[10px] font-mono text-slate-500">{r.group} / {r.name}</div>
                  </div>
                  <div className="col-span-12 md:col-span-5 text-[11px] text-slate-400">{r.what}</div>
                  <pre className="col-span-12 md:col-span-4 text-[10px] font-mono text-slate-400 bg-slate-950 rounded-lg p-2 overflow-x-auto">{JSON.stringify(r.value)}</pre>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// ============================================================================
// 2. Simple rules
// ============================================================================
const SimpleRules: React.FC<{ meta: any; show: (t: string, e?: boolean) => void; onChanged?: () => void }> = ({ meta, show, onChanged }) => {
  const [rules, setRules] = useState<any[]>([]);
  const [fields, setFields] = useState<any[]>([]);
  const [selected, setSelected] = useState<string>(''); // id, 'new' or ''
  const [form, setForm] = useState<RuleForm | null>(null);
  const [baseline, setBaseline] = useState('');
  const [saving, setSaving] = useState(false);
  const [check, setCheck] = useState<{ valid: boolean; error: string | null } | null>(null);
  const [showFields, setShowFields] = useState(false);
  const rcs = meta?.response_codes || [];

  const load = useCallback(async () => {
    try {
      const [r, f] = await Promise.all([apiFetch('/authorizer-rules'), apiFetch('/local-host/rules/fields')]);
      setRules(r);
      setFields(f);
    } catch (e: any) {
      show(e.message || 'Could not load the rules', true);
    }
  }, [show]);
  useEffect(() => {
    load();
  }, [load]);

  const typeOf = useCallback((name: string) => fields.find((f) => f.name === name)?.type || 'text', [fields]);

  const expression = useMemo(() => {
    if (!form) return '';
    if (form.mode === 'SCRIPT') return form.expression.trim();
    const parts = form.conditions.map((c) => condToExpr(c, typeOf(c.field))).filter(Boolean);
    return parts.join(form.logic === 'AND' ? ' and ' : ' or ');
  }, [form, typeOf]);

  const dirty = !!form && JSON.stringify(form) !== baseline;

  const summary = useMemo(() => {
    if (!form || !expression) return '';
    const verb = form.action === 'DECLINE' ? `Decline (RC ${form.response_code})` : form.action === 'APPROVE' ? 'Approve at the rule layer' : 'Flag';
    return `${verb} when ${expression.replace(/ and /g, ' AND ').replace(/ or /g, ' OR ')}`;
  }, [form, expression]);

  // live check of the condition
  useEffect(() => {
    if (!form || !expression) {
      setCheck(null);
      return;
    }
    const t = setTimeout(async () => {
      try {
        setCheck(await apiFetch('/local-host/rules/validate', { method: 'POST', body: JSON.stringify({ expression }) }));
      } catch {
        setCheck(null);
      }
    }, 450);
    return () => clearTimeout(t);
  }, [expression]); // eslint-disable-line react-hooks/exhaustive-deps

  const open = (r: any) => {
    if (dirty && !confirm('Discard your unsaved changes?')) return;
    const cj = r.conditions_json;
    const builder = r.rule_mode === 'BUILDER' && cj && Array.isArray(cj.conditions) && cj.conditions.length > 0;
    const f: RuleForm = {
      id: r.id, rule_code: r.rule_code, name: r.name, description: r.description || '', mode: builder ? 'BUILDER' : 'SCRIPT',
      logic: (cj && cj.logic) || 'AND', conditions: builder ? cj.conditions : [{ field: 'amount', op: '>', value: '' }],
      expression: r.expression, action: r.action, response_code: r.response_code, message: r.message,
      priority: r.priority, stop_on_match: r.stop_on_match, enabled: r.enabled,
    };
    setSelected(r.id);
    setForm(f);
    setBaseline(JSON.stringify(f));
  };

  const create = () => {
    if (dirty && !confirm('Discard your unsaved changes?')) return;
    const f = blankRule();
    setSelected('new');
    setForm(f);
    setBaseline(JSON.stringify(f));
  };

  const patch = (p: Partial<RuleForm>) => setForm((f) => (f ? { ...f, ...p } : f));
  const setCond = (i: number, p: Partial<Cond>) =>
    setForm((f) => {
      if (!f) return f;
      const conditions = f.conditions.map((c, idx) => {
        if (idx !== i) return c;
        const next = { ...c, ...p };
        if (p.field && p.field !== c.field) {
          const t = typeOf(p.field);
          next.op = t === 'number' ? '>' : t === 'bool' ? 'true' : '==';
          next.value = '';
        }
        return next;
      });
      return { ...f, conditions };
    });

  const problems: string[] = [];
  if (form) {
    if (form.rule_code.trim().length < 3) problems.push('Enter a rule code (3 or more characters)');
    if (form.name.trim().length < 2) problems.push('Enter a name');
    if (!expression) problems.push(form.mode === 'BUILDER' ? 'Complete at least one condition' : 'Enter the condition');
    if (check && !check.valid && expression) problems.push('Fix the condition (see the red message above)');
    if (!/^[0-9A-Za-z]{2}$/.test(form.response_code.trim()) && form.action === 'DECLINE') problems.push('Choose a response code');
  }

  const save = async () => {
    if (!form || problems.length) return;
    setSaving(true);
    try {
      const body: any = {
        rule_code: form.rule_code.trim().toUpperCase().replace(/[^A-Z0-9_\-]/g, '_'),
        name: form.name.trim(),
        description: form.description.trim() || null,
        priority: Number(form.priority) || 100,
        rule_mode: form.mode,
        conditions_json: form.mode === 'BUILDER' ? { logic: form.logic, conditions: form.conditions } : null,
        expression,
        action: form.action,
        response_code: form.response_code.trim(),
        message: form.message.trim() || 'Declined by rule',
        stop_on_match: form.stop_on_match,
        enabled: form.enabled,
      };
      let saved: any;
      if (form.id) {
        const { rule_code, ...rest } = body; // the code of an existing rule cannot change
        saved = await apiFetch(`/authorizer-rules/${form.id}`, { method: 'PUT', body: JSON.stringify(rest) });
      } else {
        saved = await apiFetch('/authorizer-rules', { method: 'POST', body: JSON.stringify(body) });
      }
      show(`Rule ${saved.rule_code} saved`);
      await load();
      open({ ...saved });
      onChanged?.();
    } catch (e: any) {
      show(e.message || 'Save failed', true);
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!form?.id || !confirm(`Delete rule ${form.rule_code}?`)) return;
    try {
      await apiFetch(`/authorizer-rules/${form.id}`, { method: 'DELETE' });
      show(`Rule ${form.rule_code} deleted`);
      setSelected('');
      setForm(null);
      await load();
    } catch (e: any) {
      show(e.message || 'Delete failed', true);
    }
  };

  const toggleRule = async (r: any, enabled: boolean) => {
    try {
      await apiFetch(`/authorizer-rules/${r.id}`, { method: 'PUT', body: JSON.stringify({ enabled }) });
      setRules((l) => l.map((x) => (x.id === r.id ? { ...x, enabled } : x)));
      if (form?.id === r.id) {
        setForm((f) => (f ? { ...f, enabled } : f));
        setBaseline((b) => (b ? JSON.stringify({ ...JSON.parse(b), enabled }) : b));
      }
      show(`${r.rule_code} ${enabled ? 'enabled' : 'disabled'}`);
    } catch (e: any) {
      show(e.message || 'Could not change the rule', true);
    }
  };

  const insertField = (name: string) => {
    if (!form) return;
    if (form.mode === 'SCRIPT') patch({ expression: `${form.expression}${form.expression && !form.expression.endsWith(' ') ? ' ' : ''}${name}` });
    else show('Pick fields from the dropdown of each condition, or switch to "Write expression".');
  };

  return (
    <div className="grid grid-cols-1 xl:grid-cols-12 gap-5">
      {/* ---------- list */}
      <aside className={`xl:col-span-4 ${panelCls} overflow-hidden self-start`}>
        <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
          <div className="text-xs font-bold uppercase tracking-wider text-slate-500">
            Simple rules <span className="text-emerald-500 font-mono">{rules.length}</span>
          </div>
          <button type="button" onClick={create} className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold shadow-md shadow-emerald-600/20">
            <Plus size={13} /> New rule
          </button>
        </div>
        <div className="max-h-[640px] overflow-y-auto">
          {rules.length === 0 && (
            <div className="p-8 text-center text-xs text-slate-400 space-y-2">
              <ListChecks className="mx-auto text-slate-500" size={26} />
              <div>No rule yet. Click <strong>New rule</strong> and build one with dropdowns.</div>
            </div>
          )}
          {rules.map((r) => (
            <div key={r.id} role="button" tabIndex={0} aria-label={`open rule ${r.rule_code}`} onClick={() => open(r)} onKeyDown={(e) => e.key === 'Enter' && open(r)}
              className={`px-4 py-3 border-b border-slate-100 dark:border-slate-800/80 cursor-pointer border-l-2 ${selected === r.id ? 'bg-emerald-500/10 border-l-emerald-500' : 'border-l-transparent hover:bg-slate-50 dark:hover:bg-slate-800/50'} ${r.enabled ? '' : 'opacity-60'}`}>
              <div className="flex items-start gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="font-mono text-[11px] font-bold text-emerald-500">{r.rule_code}</span>
                    <Badge tone={r.action === 'DECLINE' ? 'rose' : r.action === 'APPROVE' ? 'emerald' : 'amber'}>{r.action}</Badge>
                    {r.action === 'DECLINE' && <Badge tone="slate">RC {r.response_code}</Badge>}
                  </div>
                  <div className="text-xs mt-0.5 truncate">{r.name}</div>
                  <div className="text-[10px] font-mono text-sky-400 mt-1 truncate" title={r.expression}>{r.expression}</div>
                  <div className="text-[10px] text-slate-400 mt-1 font-mono">priority {r.priority} · {fmtNum(r.hit_count, 0)} hits</div>
                </div>
                <div onClick={(e) => e.stopPropagation()}>
                  <Toggle checked={r.enabled} label={`enable ${r.rule_code}`} onChange={(v) => toggleRule(r, v)} />
                </div>
              </div>
            </div>
          ))}
        </div>
      </aside>

      {/* ---------- editor */}
      <div className="xl:col-span-8 space-y-4 min-w-0">
        {!form ? (
          <div className={`${panelCls} p-14 text-center`}>
            <div className="w-16 h-16 mx-auto rounded-2xl bg-gradient-to-br from-emerald-500/20 to-sky-500/20 text-emerald-500 flex items-center justify-center mb-4"><Wand2 size={28} /></div>
            <h3 className="text-base font-bold">Make your own rule</h3>
            <p className="text-xs text-slate-400 mt-2 max-w-md mx-auto leading-relaxed">
              Example: <em>decline cash withdrawals above 50,000</em>. Choose a field, an operator and a value, then choose what the host should do.
              Rules run for every transaction, before the PIN and HSM checks, in priority order.
            </p>
            <button type="button" onClick={create} className="mt-5 inline-flex items-center gap-1.5 text-xs px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold"><Plus size={14} /> New rule</button>
          </div>
        ) : (
          <>
            <div className={`${panelCls} overflow-hidden`}>
              <div className="flex flex-wrap items-center gap-3 px-5 py-3.5 border-b border-slate-200 dark:border-slate-800 bg-gradient-to-r from-slate-50 to-transparent dark:from-slate-800/40">
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-sm font-bold">{form.id ? form.rule_code : 'New rule'}</h2>
                    {dirty && <Badge tone="amber">unsaved</Badge>}
                  </div>
                  <p className="text-[11px] text-slate-400">Rules run in priority order (1 first) before the PIN / HSM checks.</p>
                </div>
                <div className="ml-auto flex items-center gap-2">
                  <button type="button" onClick={() => setShowFields(!showFields)} className="flex items-center gap-1.5 text-[11px] px-3 py-1.5 rounded-lg bg-sky-600/10 text-sky-500 hover:bg-sky-600/20 font-semibold">
                    <Sparkles size={13} /> Available fields
                  </button>
                  {form.id && <button type="button" aria-label="delete rule" onClick={remove} className="p-2 rounded-lg text-rose-500 hover:bg-rose-500/10"><Trash2 size={14} /></button>}
                </div>
              </div>

              <div className="p-5 space-y-5">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <Labeled label="Rule code *" hint={form.id ? 'A saved rule keeps its code' : 'Letters, numbers, _ and -'}>
                    <input aria-label="rule code" disabled={!!form.id} value={form.rule_code} onChange={(e) => patch({ rule_code: e.target.value })} className={`${inputCls} font-mono`} placeholder="BLOCK_BIG_CASH" />
                  </Labeled>
                  <Labeled label="Name *" className="md:col-span-2">
                    <input aria-label="rule name" value={form.name} onChange={(e) => {
                      const v = e.target.value;
                      patch({ name: v, ...(!form.id && (form.rule_code === '' || form.rule_code === autoCode(form.name)) ? { rule_code: autoCode(v) } : {}) });
                    }} className={inputCls} placeholder="Decline cash above 50,000" />
                  </Labeled>
                </div>

                {/* WHEN */}
                <div className="rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden">
                  <div className="flex flex-wrap items-center gap-3 px-4 py-2.5 bg-slate-50 dark:bg-slate-950/50">
                    <span className="text-xs font-bold">WHEN</span>
                    <SegButtons value={form.mode} onChange={(m) => patch({ mode: m, expression: m === 'SCRIPT' && !form.expression ? expression : form.expression })}
                      options={[{ value: 'BUILDER', label: 'Build with dropdowns', tone: 'sky' }, { value: 'SCRIPT', label: 'Write expression', tone: 'sky' }]} />
                    {form.mode === 'BUILDER' && form.conditions.length > 1 && (
                      <SegButtons value={form.logic} onChange={(l) => patch({ logic: l })}
                        options={[{ value: 'AND', label: 'ALL must match' }, { value: 'OR', label: 'ANY can match', tone: 'amber' }]} />
                    )}
                  </div>
                  <div className="p-4 space-y-2.5">
                    {form.mode === 'BUILDER' ? (
                      <>
                        {form.conditions.map((c, i) => {
                          const type = typeOf(c.field);
                          const ops = type === 'number' ? NUM_OPS : type === 'bool' ? BOOL_OPS : TEXT_OPS;
                          return (
                            <div key={i} className="grid grid-cols-12 gap-2 items-center">
                              <select aria-label={`condition ${i + 1} field`} className={`${inputCls} col-span-12 md:col-span-4`} value={c.field} onChange={(e) => setCond(i, { field: e.target.value })}>
                                {fields.map((f) => <option key={f.name} value={f.name}>{f.name} - {f.description}</option>)}
                              </select>
                              <select aria-label={`condition ${i + 1} operator`} className={`${inputCls} col-span-6 md:col-span-3`} value={c.op} onChange={(e) => setCond(i, { op: e.target.value })}>
                                {ops.map((o) => <option key={o.v} value={o.v}>{o.t}</option>)}
                              </select>
                              {type === 'bool' ? <div className="col-span-5 md:col-span-4" /> : (
                                <input aria-label={`condition ${i + 1} value`} className={`${inputCls} font-mono col-span-5 md:col-span-4`} value={c.value} placeholder={type === 'number' ? 'e.g. 50000' : c.op.includes('in') ? "e.g. 10, 11" : "e.g. 6011"} onChange={(e) => setCond(i, { value: e.target.value })} />
                              )}
                              <button type="button" aria-label={`remove condition ${i + 1}`} disabled={form.conditions.length === 1} onClick={() => patch({ conditions: form.conditions.filter((_, idx) => idx !== i) })}
                                className="col-span-1 text-slate-500 hover:text-rose-500 disabled:opacity-30"><XCircle size={16} /></button>
                            </div>
                          );
                        })}
                        <button type="button" onClick={() => patch({ conditions: [...form.conditions, { field: 'amount', op: '>', value: '' }] })} className="text-[11px] text-emerald-500 hover:underline flex items-center gap-1"><Plus size={12} /> add condition</button>
                      </>
                    ) : (
                      <>
                        <textarea aria-label="rule expression" rows={3} value={form.expression} onChange={(e) => patch({ expression: e.target.value })}
                          placeholder="trancode == '10' and amount > 50000" className="w-full bg-slate-950 text-emerald-300 border border-slate-800 rounded-lg p-3 text-xs font-mono" />
                        <p className="text-[10px] text-slate-500">Use and / or / not, comparisons (== != &gt; &lt; in) and the fields from "Available fields". Example: <code className="text-emerald-400">institution.code == 'XBANK' and hour &lt; 5</code></p>
                      </>
                    )}
                    <div className="text-[11px] font-mono text-slate-400 bg-slate-950 rounded-lg px-3 py-2" data-testid="expression-preview">
                      <span className="text-slate-500">condition: </span><span className="text-emerald-300">{expression || '(incomplete)'}</span>
                    </div>
                    {check && expression && (
                      check.valid ? <div className="text-[11px] text-emerald-500 flex items-center gap-1"><CheckCircle2 size={12} /> Condition understood by the host</div>
                        : <div role="alert" className="text-[11px] text-rose-400 flex items-center gap-1"><AlertTriangle size={12} /> {check.error}</div>
                    )}
                  </div>
                </div>

                {/* THEN */}
                <div className="rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden">
                  <div className="px-4 py-2.5 bg-slate-50 dark:bg-slate-950/50 text-xs font-bold">THEN</div>
                  <div className="p-4 grid grid-cols-1 md:grid-cols-12 gap-4">
                    <div className="md:col-span-4">
                      <div className="text-[11px] text-slate-400 font-medium mb-1.5">Action</div>
                      <SegButtons value={form.action} onChange={(a) => patch({ action: a })}
                        options={[{ value: 'DECLINE', label: 'Decline', tone: 'rose' }, { value: 'APPROVE', label: 'Approve', tone: 'emerald' }, { value: 'FLAG', label: 'Flag', tone: 'amber' }]} />
                      <p className="text-[10px] text-slate-500 mt-1.5 leading-snug">{ACTION_HELP[form.action]}</p>
                    </div>
                    {form.action === 'DECLINE' && (
                      <Labeled label="Response code" className="md:col-span-4">
                        <RcSelect value={form.response_code} codes={rcs} ariaLabel="rule response code" onChange={(v) => patch({ response_code: v })} />
                      </Labeled>
                    )}
                    <Labeled label="Priority" hint="1 runs first" className="md:col-span-2">
                      <NumInput value={form.priority} ariaLabel="rule priority" placeholder="100" onChange={(v) => patch({ priority: v || 100 })} />
                    </Labeled>
                    <div className="md:col-span-2 flex items-end gap-2 pb-1">
                      <Toggle checked={form.enabled} label="rule enabled" onChange={(v) => patch({ enabled: v })} />
                      <span className="text-xs font-semibold">{form.enabled ? 'On' : 'Off'}</span>
                    </div>
                    <Labeled label="Message (shown in the transaction checks)" className="md:col-span-8">
                      <input aria-label="rule message" className={inputCls} value={form.message} onChange={(e) => patch({ message: e.target.value })} />
                    </Labeled>
                    <div className="md:col-span-4 flex items-end gap-2 pb-1">
                      <Toggle checked={form.stop_on_match} label="stop on match" onChange={(v) => patch({ stop_on_match: v })} />
                      <span className="text-[11px] text-slate-400 leading-tight">Stop checking lower-priority rules after a match</span>
                    </div>
                  </div>
                </div>

                {summary && <div className="text-xs text-slate-300 bg-emerald-500/5 border border-emerald-500/20 rounded-xl px-4 py-3" data-testid="rule-summary"><strong className="text-emerald-400">In plain words:</strong> {summary}</div>}

                {problems.length > 0 && dirty && (
                  <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 space-y-1" role="status">
                    {problems.map((p, i) => <div key={i} className="text-[11px] text-amber-400 flex gap-2"><AlertTriangle size={12} className="mt-0.5 shrink-0" /> {p}</div>)}
                  </div>
                )}

                <div className="flex flex-wrap items-center gap-3">
                  <button type="button" onClick={save} disabled={saving || !dirty || problems.length > 0}
                    className="flex items-center gap-1.5 text-xs px-5 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white font-semibold shadow-md shadow-emerald-600/20">
                    {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />} {form.id ? 'Save rule' : 'Create rule'}
                  </button>
                  <span className="text-[11px] text-slate-400">Changes apply to the next transaction.</span>
                </div>
              </div>
            </div>

            <RuleTest meta={meta} expression={expression} />
          </>
        )}

        {showFields && (
          <div className={`${panelCls} overflow-hidden`}>
            <div className="px-5 py-3 border-b border-slate-200 dark:border-slate-800 text-sm font-bold flex items-center gap-2"><Sparkles size={15} className="text-sky-500" /> Fields a simple rule can use</div>
            <div className="divide-y divide-slate-100 dark:divide-slate-800/80">
              {fields.map((f) => (
                <div key={f.name} className="grid grid-cols-12 gap-3 items-center px-5 py-2">
                  <button type="button" onClick={() => insertField(f.name)} aria-label={`field ${f.name}`} className="col-span-4 md:col-span-3 font-mono text-[11px] font-bold text-emerald-400 text-left hover:underline">{f.name}</button>
                  <div className="col-span-2 md:col-span-1"><Badge tone={f.type === 'number' ? 'violet' : f.type === 'bool' ? 'amber' : 'slate'}>{f.type}</Badge></div>
                  <div className="col-span-6 md:col-span-8 text-[11px] text-slate-400">{f.description} <span className="font-mono text-slate-500">e.g. {String(f.example)}</span></div>
                </div>
              ))}
            </div>
            <div className="px-5 py-3 text-[11px] text-slate-500 border-t border-slate-200 dark:border-slate-800">Need more fields (bank name, terminal owner, customer risk, history)? Use the <strong>Algo Control</strong> tab.</div>
          </div>
        )}
      </div>
    </div>
  );
};

const autoCode = (name: string) =>
  name.trim().toUpperCase().replace(/[^A-Z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 40);

// ---------------------------------------------------------------- test a condition on a real card
const RuleTest: React.FC<{ meta: any; expression: string }> = ({ meta, expression }) => {
  const cards: any[] = meta?.cards || [];
  const [open, setOpen] = useState(false);
  const [cardId, setCardId] = useState('');
  const [f, setF] = useState<any>({ amount: 25000, tran_code: '10', channel: 'ATM', hour: 2, mcc: '', country: '050' });
  const [res, setRes] = useState<any | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const chosen = cardId || cards[0]?.id || '';

  const run = async () => {
    setBusy(true);
    setErr('');
    try {
      const overrides: Record<string, any> = { ...f };
      Object.keys(overrides).forEach((k) => overrides[k] === '' && delete overrides[k]);
      setRes(await apiFetch('/local-host/rules/test', { method: 'POST', body: JSON.stringify({ expression, card_id: chosen || null, overrides }) }));
    } catch (e: any) {
      setErr(e.message || 'Test failed');
      setRes(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={`${panelCls} overflow-hidden`}>
      <button type="button" onClick={() => setOpen(!open)} className="w-full flex items-center gap-3 px-5 py-3 text-left hover:bg-slate-50 dark:hover:bg-slate-800/30">
        <Play size={15} className="text-violet-400" />
        <h3 className="text-sm font-bold">Test this condition</h3>
        <span className="text-[11px] text-slate-400">Try it on a real card with sample values. Nothing is saved.</span>
        <ChevronDown size={14} className={`ml-auto text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="p-5 border-t border-slate-200 dark:border-slate-800 space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Labeled label="Card" className="col-span-2">
              <select aria-label="rule test card" className={`${inputCls} font-mono`} value={chosen} onChange={(e) => setCardId(e.target.value)}>
                {cards.map((c) => <option key={c.id} value={c.id}>{c.masked_pan} · {c.bank_code}</option>)}
              </select>
            </Labeled>
            <Labeled label="Amount"><input aria-label="rule test amount" type="number" className={`${inputCls} font-mono`} value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></Labeled>
            <Labeled label="Hour (0-23)"><input aria-label="rule test hour" type="number" min={0} max={23} className={`${inputCls} font-mono`} value={f.hour} onChange={(e) => setF({ ...f, hour: e.target.value })} /></Labeled>
            <Labeled label="Channel">
              <select aria-label="rule test channel" className={inputCls} value={f.channel} onChange={(e) => setF({ ...f, channel: e.target.value })}>
                {(meta?.channels || []).map((c: string) => <option key={c}>{c}</option>)}
              </select>
            </Labeled>
            <Labeled label="Transaction code">
              <select aria-label="rule test tran code" className={inputCls} value={f.tran_code} onChange={(e) => setF({ ...f, tran_code: e.target.value })}>
                {(meta?.transaction_codes || []).map((t: any) => <option key={t.code} value={t.code}>{t.code} {t.name}</option>)}
              </select>
            </Labeled>
            <Labeled label="MCC"><input aria-label="rule test mcc" className={`${inputCls} font-mono`} placeholder="auto" value={f.mcc} onChange={(e) => setF({ ...f, mcc: e.target.value })} /></Labeled>
            <Labeled label="Country (DE19)"><input aria-label="rule test country" className={`${inputCls} font-mono`} value={f.country} onChange={(e) => setF({ ...f, country: e.target.value })} /></Labeled>
          </div>
          <div className="flex items-center gap-3">
            <button type="button" onClick={run} disabled={busy || !expression} className="flex items-center gap-1.5 text-xs px-5 py-2 rounded-lg bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white font-semibold">
              {busy ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />} Run test
            </button>
            {err && <span className="text-xs text-rose-500 font-mono">{err}</span>}
          </div>
          {res && (
            <div data-testid="rule-test-result" className={`p-4 rounded-xl border flex items-center gap-3 ${!res.valid ? 'bg-rose-500/10 border-rose-500/30' : res.matched ? 'bg-amber-500/10 border-amber-500/30' : 'bg-emerald-500/10 border-emerald-500/30'}`}>
              {!res.valid ? <AlertTriangle className="text-rose-500" size={20} /> : res.matched ? <XCircle className="text-amber-500" size={20} /> : <CheckCircle2 className="text-emerald-500" size={20} />}
              <div>
                <div className="text-sm font-bold">{!res.valid ? 'The condition has an error' : res.matched ? 'Condition MATCHES: the rule would fire' : 'Condition does not match: transaction continues'}</div>
                <div className="text-[11px] text-slate-400 font-mono">{res.error || `amount=${res.context?.amount} · trancode=${res.context?.trancode} · hour=${res.context?.hour} · mcc=${res.context?.mcc} · bank=${res.context?.institution?.code}`}</div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
'''

import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------- locate the project
def find_root():
    if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        return Path(sys.argv[1])
    cwd = Path.cwd()
    if (cwd / "backend" / "app").exists():
        return cwd
    here = Path(__file__).resolve().parent
    if (here / "backend" / "app").exists():
        return here
    return Path(r"E:\HOST_VSCODE\host-simulator-github-prod")


ROOT = find_root()
BACKUP = ROOT / "_backups" / f"{PATCH_NAME}_{datetime.now():%Y%m%d_%H%M%S}"
problems = []


def load(path):
    raw = path.read_bytes().decode("utf-8")
    return raw.replace("\r\n", "\n"), ("\r\n" in raw)


def save(path, text, crlf):
    if crlf:
        text = text.replace("\n", "\r\n")
    path.write_bytes(text.encode("utf-8"))


def backup(path):
    if not path.exists():
        return
    dest = BACKUP / path.relative_to(ROOT)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)


def check_syntax(path, text):
    if path.suffix == ".py":
        try:
            compile(text, str(path), "exec")
        except SyntaxError as exc:
            return f"syntax error: {exc}"
    return None


def edit(rel, label, marker, old, new, count=1):
    """Replace `old` by `new` in file `rel` (exactly `count` occurrences). Idempotent via `marker`."""
    path = ROOT / rel
    if not path.exists():
        print(f"[NOT FOUND] {rel} (file missing)  - {label}")
        problems.append(label)
        return
    text, crlf = load(path)
    if (marker and marker in text) or (old not in text and new in text):
        print(f"[ALREADY DONE] {label}")
        return
    found = text.count(old)
    if found != count:
        print(f"[NOT FOUND] {label}  ({rel}: expected {count} match, found {found})")
        problems.append(label)
        return
    new_text = text.replace(old, new)
    err = check_syntax(path, new_text)
    if err:
        print(f"[FAILED] {label}: {err}; file NOT changed")
        problems.append(label)
        return
    backup(path)
    save(path, new_text, crlf)
    print(f"[APPLIED] {label}")


def write_new(rel, label, marker, content):
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing, _ = load(path)
        if marker in existing:
            if existing.strip() == content.strip():
                print(f"[ALREADY DONE] {label}")
                return
        backup(path)
    err = check_syntax(path, content)
    if err:
        print(f"[FAILED] {label}: {err}")
        problems.append(label)
        return
    path.write_bytes(content.encode("utf-8"))
    print(f"[APPLIED] {label}")


def banner(title):
    print("=" * 72)
    print(f" {title}")
    print(f" Project folder: {ROOT}")
    print("=" * 72)
    if not (ROOT / "backend" / "app").exists():
        print("[STOP] backend/app not found here. Run from the project folder or pass the folder as argument.")
        sys.exit(2)


def finish(next_steps):
    print("=" * 72)
    if problems:
        print(f" FINISHED WITH {len(problems)} PROBLEM(S): " + "; ".join(problems))
        print(" Nothing else was touched for the failed edits. Send me this output if you need help.")
        sys.exit(1)
    print(f" Done. Backups: {BACKUP}")
    for s in next_steps:
        print(" " + s)
    print("=" * 72)


banner("PATCH 5/6  Frontend: Host Control Center (Local Host + Algo Control)")

D = "frontend/src/pages/hostcontrol/"
write_new(D + "ui.tsx", "hostcontrol/ui.tsx (shared components + code editor)", "Shared UI for the Rajon Host Control Center", HC_UI_TSX)
write_new(D + "LocalHostTab.tsx", "hostcontrol/LocalHostTab.tsx", "LOCAL HOST  - per bank transaction policy", HC_LOCAL_TSX)
write_new(D + "AlgoControlTab.tsx", "hostcontrol/AlgoControlTab.tsx", "ALGO CONTROL  - Python / SQL risk blocks", HC_ALGO_TSX)
write_new(D + "RulesAndChecksTab.tsx", "hostcontrol/RulesAndChecksTab.tsx", "RULES & CHECKS", HC_RULES_TSX)
write_new(D + "HostControlCenterPage.tsx", "hostcontrol/HostControlCenterPage.tsx", "RAJON HOST CONTROL CENTER", HC_PAGE_TSX)

# the existing "14. Host Configuration" route now opens the Control Center
# (its old table of authorization rules is kept as the "Authorization Rules" tab)
edit("frontend/src/App.tsx", "App.tsx: import the Host Control Center", "HostControlCenterPage } from './pages/hostcontrol/HostControlCenterPage'",
     "import { CardProfilesUnderBinTab } from './pages/CardProfilesUnderBinTab';\n",
     "import { CardProfilesUnderBinTab } from './pages/CardProfilesUnderBinTab';\n"
     "import { HostControlCenterPage } from './pages/hostcontrol/HostControlCenterPage';\n")

edit("frontend/src/App.tsx", "App.tsx: /host-config opens the Host Control Center", None,
     "              <HostConfigurationPage />\n",
     "              <HostControlCenterPage />\n")

edit("frontend/src/components/Layout.tsx", "Layout.tsx: menu label", None,
     "label: '14. Host Configuration'", "label: '14. Host Control Center'")

finish([
    "Rebuild / restart the frontend (npm run dev or npm run build) and hard-refresh the browser (Ctrl+Shift+F5).",
    "Menu: 14. Host Control Center  ->  Local Host | Algo Control | Authorization Rules | CBS | External Host",
])
