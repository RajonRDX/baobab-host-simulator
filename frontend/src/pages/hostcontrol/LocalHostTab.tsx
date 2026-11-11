import React, { useCallback, useEffect, useMemo, useState } from 'react';
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
