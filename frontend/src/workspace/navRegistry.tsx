import React from 'react';
import {
  LayoutDashboard,
  Users,
  UserCheck,
  CreditCard,
  Landmark,
  Sliders,
  ShieldAlert,
  FileCode2,
  TerminalSquare,
  BookOpen,
  KeyRound,
  Cpu,
  Activity,
  Settings,
  CheckCircle2,
  ScrollText,
  Bell,
  Network,
  Layers,
  ShieldCheck,
  Database,
  Radio,
  Sparkles,
  GitBranch,
  FileSearch,
  Lock,
} from 'lucide-react';

export interface NavSubItem {
  to: string;
  code: string;
  label: string;
  shortLabel: string;
  description: string;
  icon: React.ComponentType<any>;
  badge?: string;
  accentColor: string;
}

export interface NavDomainBranch {
  id: string;
  code: string;
  title: string;
  subtitle: string;
  icon: React.ComponentType<any>;
  accent: string;
  badgeColor: string;
  items: NavSubItem[];
}

export const PAYMENT_ARCHITECTURE_TREE: NavDomainBranch[] = [
  {
    id: 'command-overview',
    code: 'DOM-01',
    title: 'Command & Telemetry',
    subtitle: 'Executive KPIs & Live Switch Health',
    icon: LayoutDashboard,
    accent: 'from-emerald-500/20 to-teal-500/10 border-emerald-500/30 text-emerald-400',
    badgeColor: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
    items: [
      {
        to: '/',
        code: '1.0',
        label: 'Executive Host Dashboard',
        shortLabel: 'Dashboard',
        description: 'Real-time TPS, approval rate telemetry, ledger volume & Soft-HSM status',
        icon: LayoutDashboard,
        badge: 'LIVE',
        accentColor: 'text-emerald-400',
      },
      {
        to: '/monitor',
        code: '13.0',
        label: 'Real-Time Execution Monitor',
        shortLabel: 'Exec Monitor',
        description: 'Live WebSocket stream of authorization stages, wire frames & HSM calls',
        icon: Activity,
        badge: 'WS',
        accentColor: 'text-teal-400',
      },
    ],
  },
  {
    id: 'card-management',
    code: 'DOM-02',
    title: 'Card & Plastic Management',
    subtitle: 'Cards, BIN Profiles, PIN/CVV Lab & Card Limits',
    icon: CreditCard,
    accent: 'from-sky-500/20 to-indigo-500/10 border-sky-500/30 text-sky-400',
    badgeColor: 'bg-sky-500/15 text-sky-400 border-sky-500/30',
    items: [
      {
        to: '/cards',
        code: '3.0',
        label: 'Issued Cards & Plastic Registry',
        shortLabel: 'Issued Cards',
        description: 'Manage test PANs, card statuses, multi-account links, PVV & EMV profiles',
        icon: CreditCard,
        badge: 'PAN',
        accentColor: 'text-sky-400',
      },
      {
        to: '/card-profiles',
        code: '1.6',
        label: 'Card Product Profiles (BIN)',
        shortLabel: 'Card Profiles',
        description: 'Configure BIN-level card products, channel permissions & default auth profiles',
        icon: Layers,
        badge: 'BIN',
        accentColor: 'text-indigo-400',
      },
      {
        to: '/card-limits',
        code: '5.0',
        label: 'Card Velocity & Channel Limits',
        shortLabel: 'Card Limits',
        description: 'Configure per-card ATM/POS/E-Com limits, reset windows & live consumption',
        icon: Sliders,
        badge: 'VELOCITY',
        accentColor: 'text-cyan-400',
      },
      {
        to: '/card-lab',
        code: '12.5',
        label: 'Synthetic Card & PIN/CVV Lab',
        shortLabel: 'PIN & Card Lab',
        description: 'Luhn PAN generator, Visa PVV, IBM 3624 offset, CVV1/CVV2 & ISO-0 PIN packer',
        icon: Sparkles,
        badge: 'LAB',
        accentColor: 'text-purple-400',
      },
    ],
  },
  {
    id: 'core-banking-cif',
    code: 'DOM-03',
    title: 'Customer, CIF & Ledger',
    subtitle: 'Customer 360, Core Accounts & Account Limits',
    icon: Landmark,
    accent: 'from-violet-500/20 to-fuchsia-500/10 border-violet-500/30 text-violet-400',
    badgeColor: 'bg-violet-500/15 text-violet-400 border-violet-500/30',
    items: [
      {
        to: '/customer-maintenance',
        code: '2.5',
        label: 'Customer Maintenance 360',
        shortLabel: 'Customer 360',
        description: 'Unified PAN / CIF / Account workbench with instant limit & balance controls',
        icon: UserCheck,
        badge: '360°',
        accentColor: 'text-violet-400',
      },
      {
        to: '/customers',
        code: '2.0',
        label: 'Customer CIF Directory',
        shortLabel: 'Customers (CIF)',
        description: 'Core banking customer profiles, KYC status, risk tiers & institution mapping',
        icon: Users,
        accentColor: 'text-fuchsia-400',
      },
      {
        to: '/accounts',
        code: '4.0',
        label: 'Core Accounts & Atomic Ledger',
        shortLabel: 'Accounts & Ledger',
        description: 'Available vs Ledger balances, overdraft rules & double-entry audit trail',
        icon: Landmark,
        badge: 'CASA',
        accentColor: 'text-purple-400',
      },
      {
        to: '/account-limits',
        code: '6.0',
        label: 'Account Velocity Limits',
        shortLabel: 'Account Limits',
        description: 'Account-scoped daily/weekly/monthly debit thresholds & usage counters',
        icon: ShieldAlert,
        accentColor: 'text-pink-400',
      },
    ],
  },
  {
    id: 'institutions-settlement',
    code: 'DOM-04',
    title: 'Institutions, Routing & Clearing',
    subtitle: 'Member Banks, Switch BINs, Off-Us Routing & Settlement',
    icon: Network,
    accent: 'from-amber-500/20 to-orange-500/10 border-amber-500/30 text-amber-400',
    badgeColor: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
    items: [
      {
        to: '/institutions',
        code: '1.5',
        label: 'Member Banks & Switch BIN Ranges',
        shortLabel: 'Banks & BINs',
        description: 'ITCL / Visa / Mastercard / NPSB processing systems, member banks & BIN routing',
        icon: Network,
        badge: 'ITCL',
        accentColor: 'text-amber-400',
      },
      {
        to: '/network-routing',
        code: '7.8',
        label: 'Network Routing & Off-Us Simulator',
        shortLabel: 'Network Routing',
        description: 'On-Us vs Off-Us BIN routing table, timeout simulation & cross-zone PIN translation',
        icon: GitBranch,
        badge: 'SWITCH',
        accentColor: 'text-orange-400',
      },
      {
        to: '/settlement',
        code: '1.8',
        label: 'Clearing, Cutover & Net Settlement',
        shortLabel: 'Clearing & Settlement',
        description: 'Daily batch cutover, 0220 clearing presentment, interchange fees & net positions',
        icon: Database,
        badge: 'EOD',
        accentColor: 'text-yellow-400',
      },
    ],
  },
  {
    id: 'authorization-policy',
    code: 'DOM-05',
    title: 'Authorization Engine & Policy',
    subtitle: 'Auth Profiles, Host Control, Tran Codes & Response Codes',
    icon: ShieldCheck,
    accent: 'from-rose-500/20 to-red-500/10 border-rose-500/30 text-rose-400',
    badgeColor: 'bg-rose-500/15 text-rose-400 border-rose-500/30',
    items: [
      {
        to: '/authorization-profiles',
        code: '7.4',
        label: 'Authorization Profiles Workbench',
        shortLabel: 'Auth Profiles',
        description: '4-Tab profile matrix: Allowed Tran Codes, Card/Acct Limits & Impact Multipliers',
        icon: CheckCircle2,
        badge: 'MATRIX',
        accentColor: 'text-rose-400',
      },
      {
        to: '/host-config',
        code: '14.0',
        label: 'Host Control Center & Risk Algos',
        shortLabel: 'Host Control Center',
        description: 'Local Host bank policies, Python/SQL Algo Control blocks & Authorization Rules',
        icon: Settings,
        badge: 'POLICY',
        accentColor: 'text-red-400',
      },
      {
        to: '/transaction-codes',
        code: '7.0',
        label: 'Transaction Code Definitions',
        shortLabel: 'Transaction Codes',
        description: 'Configure DE3 processing codes, mandatory crypto flags (PIN/CVV/EMV/MAC) & debit rules',
        icon: FileCode2,
        accentColor: 'text-orange-400',
      },
      {
        to: '/response-codes',
        code: '15.0',
        label: 'ISO / TIC Response Code Dictionary',
        shortLabel: 'Response Codes',
        description: 'Manage F39 response codes, approval flags, decline categories & retry rules',
        icon: CheckCircle2,
        accentColor: 'text-pink-400',
      },
    ],
  },
  {
    id: 'simulator-journals',
    code: 'DOM-06',
    title: 'Transaction Simulator & Journals',
    subtitle: 'ISO 8583 / TIC v2.164e Workbench & Deep Trace Logs',
    icon: TerminalSquare,
    accent: 'from-cyan-500/20 to-blue-500/10 border-cyan-500/30 text-cyan-400',
    badgeColor: 'bg-cyan-500/15 text-cyan-400 border-cyan-500/30',
    items: [
      {
        to: '/simulator',
        code: '8.0',
        label: 'TIC / ISO 8583 Transaction Simulator',
        shortLabel: 'TX Simulator',
        description: 'Build, unpack & fire raw TIC v2.164e or ISO 8583:1987 messages with live trace',
        icon: TerminalSquare,
        badge: 'FIRE',
        accentColor: 'text-cyan-400',
      },
      {
        to: '/transaction-logs',
        code: '9.5',
        label: 'Enterprise Transaction Log Inspector',
        shortLabel: 'TX Log Viewer',
        description: '20-filter enterprise investigator, 6-tab TIC wire decoder & step-by-step trace',
        icon: FileSearch,
        badge: 'DEEP',
        accentColor: 'text-blue-400',
      },
      {
        to: '/transactions',
        code: '9.0',
        label: 'Host Transaction Journal',
        shortLabel: 'TX Journal',
        description: 'Chronological switch ledger with STAN/RRN filters & reversal status',
        icon: BookOpen,
        accentColor: 'text-sky-400',
      },
    ],
  },
  {
    id: 'hsm-cryptography',
    code: 'DOM-07',
    title: 'Thales HSM & Key Management',
    subtitle: 'External Soft-HSM Keys, Command Workbench & Key Ceremony',
    icon: KeyRound,
    accent: 'from-amber-400/20 to-emerald-500/10 border-amber-400/30 text-amber-300',
    badgeColor: 'bg-amber-400/15 text-amber-300 border-amber-400/30',
    items: [
      {
        to: '/hsm-keys',
        code: '11.0',
        label: 'LMK Key Registry & External HSM',
        shortLabel: 'HSM Key Registry',
        description: 'Manage LMK-encrypted key tokens (ZMK, AWK, IWK, PVK, CVK, TAK, MK-AC) & KCVs',
        icon: KeyRound,
        badge: 'LMK',
        accentColor: 'text-amber-300',
      },
      {
        to: '/hsm-workbench',
        code: '12.0',
        label: 'Thales payShield 10K Command Workbench',
        shortLabel: 'HSM Workbench',
        description: 'Execute live DC, CA, CY, M6/M8, KQ (ARQC/ARPC) & BU commands against Soft-HSM',
        icon: Cpu,
        badge: '10K',
        accentColor: 'text-emerald-400',
      },
      {
        to: '/key-ceremony',
        code: '12.8',
        label: 'Split-Component Key Ceremony Lab',
        shortLabel: 'Key Ceremony',
        description: 'Odd-parity 3DES key generator, 2/3 custodian XOR ceremony & ZMK import/export',
        icon: Lock,
        badge: 'XOR',
        accentColor: 'text-yellow-300',
      },
    ],
  },
  {
    id: 'audit-observability',
    code: 'DOM-08',
    title: 'Observability, Audit & Alerts',
    subtitle: 'Correlation Timeline, Entity Diffs, System Logs & SMS',
    icon: ScrollText,
    accent: 'from-slate-500/20 to-zinc-500/10 border-slate-500/30 text-slate-300',
    badgeColor: 'bg-slate-500/15 text-slate-300 border-slate-500/30',
    items: [
      {
        to: '/log-portal',
        code: '13.5',
        label: 'Unified Correlation & Crypto Portal',
        shortLabel: 'Crypto Log Portal',
        description: 'End-to-end correlation ID timeline & 6-step Visa PVV cryptographic trace',
        icon: Radio,
        badge: 'TRACE',
        accentColor: 'text-emerald-400',
      },
      {
        to: '/audit-trail',
        code: '16.5',
        label: 'Regulatory Audit Trail & JSON Diffs',
        shortLabel: 'Audit Trail Diff',
        description: 'Immutable before/after entity snapshots for cards, accounts, limits & keys',
        icon: CheckCircle2,
        badge: 'AUDIT',
        accentColor: 'text-sky-400',
      },
      {
        to: '/system-logs',
        code: '16.0',
        label: 'System Event & Component Logs',
        shortLabel: 'System Logs',
        description: 'Host engine, limit engine & HSM adapter diagnostic event stream',
        icon: ScrollText,
        accentColor: 'text-slate-300',
      },
      {
        to: '/notifications',
        code: '17.0',
        label: 'Cardholder SMS Notification Simulator',
        shortLabel: 'SMS Alerts Sim',
        description: 'Outbound cardholder SMS/alert dispatch log for approved & declined transactions',
        icon: Bell,
        accentColor: 'text-amber-400',
      },
    ],
  },
];

export const ALL_NAV_ITEMS: (NavSubItem & { branchId: string; branchTitle: string })[] =
  PAYMENT_ARCHITECTURE_TREE.flatMap((branch) =>
    branch.items.map((item) => ({
      ...item,
      branchId: branch.id,
      branchTitle: branch.title,
    }))
  );

export function resolveNavMeta(path: string): {
  to: string;
  code: string;
  label: string;
  shortLabel: string;
  description: string;
  branchId: string;
  branchTitle: string;
  icon: React.ComponentType<any>;
  accentColor: string;
} {
  const clean = (path || '/').split('?')[0];
  const exact = ALL_NAV_ITEMS.find((x) => x.to === clean);
  if (exact) return exact;

  if (clean.startsWith('/transactions/')) {
    const txId = clean.replace('/transactions/', '');
    return {
      to: clean,
      code: 'TX-DTL',
      label: `Transaction Trace #${txId.slice(0, 8)}`,
      shortLabel: `TX #${txId.slice(0, 8)}`,
      description: 'Step-by-step authorization checks, wire messages, HSM calls & ledger entries',
      branchId: 'simulator-journals',
      branchTitle: 'Transaction Simulator & Journals',
      icon: FileSearch,
      accentColor: 'text-cyan-400',
    };
  }

  if (clean === '/limits') {
    const fallback = ALL_NAV_ITEMS.find((x) => x.to === '/card-limits')!;
    return { ...fallback, to: clean };
  }

  return (
    ALL_NAV_ITEMS[0] || {
      to: clean,
      code: 'HOST',
      label: clean,
      shortLabel: clean,
      description: 'Rajon Host Workbench',
      branchId: 'command-overview',
      branchTitle: 'Command & Telemetry',
      icon: Activity,
      accentColor: 'text-emerald-400',
    }
  );
}
