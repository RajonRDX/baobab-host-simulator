import React, { useCallback, useEffect, useState } from 'react';
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
