import React, { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react';
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
