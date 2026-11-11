import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
