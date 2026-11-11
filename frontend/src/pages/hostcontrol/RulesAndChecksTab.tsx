import React, { useCallback, useEffect, useMemo, useState } from 'react';
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
