import React, { useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
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
  ChevronLeft,
  ChevronRight,
  LogOut,
  Moon,
  Sun,
  Network,
  Layers,
} from 'lucide-react';
import { clearAuthSession } from '../api';

interface LayoutProps {
  children: React.ReactNode;
}

const NAV_ITEMS = [
  { to: '/', label: '1. Dashboard', icon: LayoutDashboard, group: 'OVERVIEW' },
  { to: '/customers', label: '2. Customers', icon: Users, group: 'CORE BANKING' },
  { to: '/customer-maintenance', label: '2.5. Customer Maintenance 360', icon: UserCheck, group: 'CORE BANKING' },
  { to: '/cards', label: '3. Cards & Profiles', icon: CreditCard, group: 'CORE BANKING' },
  { to: '/accounts', label: '4. Accounts & Ledger', icon: Landmark, group: 'CORE BANKING' },
// [PATCH step01_03:layout_nav_institutions]
  { to: '/institutions', label: '1.5. Banks & Switch BINS', icon: Network, group: 'CORE BANKING' },
// [PATCH step12:layout_nav_settlement]
  { to: '/settlement', label: '1.8. Clearing & Settlement', icon: Landmark, group: 'CORE BANKING' },
  { to: '/card-limits', label: '5. Card Limits', icon: Sliders, group: 'LIMIT ENGINE' },
  { to: '/account-limits', label: '6. Account Limits', icon: ShieldAlert, group: 'LIMIT ENGINE' },
  { to: '/transaction-codes', label: '7. Transaction Codes', icon: FileCode2, group: 'SWITCH & SIMULATOR' },
// [PATCH step08:layout_nav_authorizer_rules]
  { to: '/authorizer-rules', label: '7.5. Authorizer Rules', icon: Sliders, group: 'SWITCH & SIMULATOR' },
// [PATCH step11:layout_nav_network_routing]
  { to: '/network-routing', label: '7.8. Network Routing & Sim', icon: Network, group: 'SWITCH & SIMULATOR' },
  { to: '/simulator', label: '8. Transaction Simulator', icon: TerminalSquare, group: 'SWITCH & SIMULATOR' },
  { to: '/transactions', label: '9. Transaction Journal', icon: BookOpen, group: 'SWITCH & SIMULATOR' },
  { to: '/hsm-keys', label: '11. Host Key Management', icon: KeyRound, group: 'CRYPTO & HSM' },
  { to: '/hsm-workbench', label: '12. HSM Workbench', icon: Cpu, group: 'CRYPTO & HSM' },
// [PATCH step06:layout_nav_card_lab]
  { to: '/card-lab', label: '12.5. PIN & Card Lab', icon: CreditCard, group: 'CRYPTO & HSM' },
// [PATCH step10:layout_nav_key_ceremony]
  { to: '/key-ceremony', label: '12.8. Key Ceremony Lab', icon: Layers, group: 'CRYPTO & HSM' },
  { to: '/monitor', label: '13. Execution Monitor', icon: Activity, group: 'OBSERVABILITY' },
// [PATCH step07:layout_nav_log_portal]
  { to: '/log-portal', label: '13.5. Operational & Crypto Portal', icon: Activity, group: 'OBSERVABILITY' },
  { to: '/transaction-logs', label: 'Transaction Log Viewer', icon: Activity, group: 'OBSERVABILITY' },
  { to: '/host-config', label: '14. Host Configuration', icon: Settings, group: 'OBSERVABILITY' },
  { to: '/response-codes', label: '15. Response Codes', icon: CheckCircle2, group: 'OBSERVABILITY' },
  { to: '/system-logs', label: '16. System Logs', icon: ScrollText, group: 'OBSERVABILITY' },
// [PATCH step03_03:layout_nav_audit_trail]
  { to: '/audit-trail', label: '16.5. Audit Trail Diff', icon: CheckCircle2, group: 'OBSERVABILITY' },
  { to: '/notifications', label: '17. Notifications Sim', icon: Bell, group: 'OBSERVABILITY' },
];

export const Layout: React.FC<LayoutProps> = ({ children }) => {
  const [collapsed, setCollapsed] = useState(false);
  const [dark, setDark] = useState(() => document.documentElement.classList.contains('dark'));
  const navigate = useNavigate();
  const hsmMode = sessionStorage.getItem('BAOBAB_HSM_MODE') || 'SOFT_HSM_LOCAL';
  const username = sessionStorage.getItem('BAOBAB_USER') || 'admin';

  const toggleDark = () => {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle('dark', next);
  };

  const handleLogout = () => {
    clearAuthSession();
    navigate('/login');
  };

  return (
    <div className="flex h-screen overflow-hidden bg-slate-100 dark:bg-slate-950">
      {/* Dark Navy Sidebar */}
      <aside
        className={`${
          collapsed ? 'w-16' : 'w-64'
        } bg-slate-900 text-slate-200 flex flex-col border-r border-slate-800 transition-all duration-200 select-none`}
      >
        <div className="h-16 flex items-center justify-between px-4 border-b border-slate-800">
          {!collapsed && (
            <div className="flex items-center gap-2.5">
              <div className="h-3 w-3 rounded-full bg-emerald-400 animate-pulse" />
              <div>
                <div className="font-mono font-bold text-sm tracking-wider text-white">BAOBAB HOST</div>
                <div className="text-[10px] font-mono text-emerald-400">SWITCH SIMULATOR v1.0</div>
              </div>
            </div>
          )}
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="p-1.5 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white"
            title="Toggle Sidebar"
          >
            {collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-1">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3 py-2 rounded-lg text-xs font-medium transition-colors ${
                    isActive
                      ? 'bg-emerald-600 text-white shadow-sm'
                      : 'text-slate-300 hover:bg-slate-800/80 hover:text-white'
                  }`
                }
                title={collapsed ? item.label : undefined}
              >
                <Icon size={16} className="shrink-0" />
                {!collapsed && <span className="truncate">{item.label}</span>}
              </NavLink>
            );
          })}
        </nav>

        <div className="p-3 border-t border-slate-800 space-y-2">
          {!collapsed && (
            <div className="px-2 py-1.5 rounded bg-slate-950/90 border border-slate-800 text-[11px] font-mono">
              <div className="text-slate-400">HSM ADAPTER MODE:</div>
              <div className="text-emerald-400 font-bold truncate">{hsmMode}</div>
            </div>
          )}
          <button
            onClick={handleLogout}
            className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-xs font-medium bg-rose-950/50 text-rose-300 hover:bg-rose-900/60 border border-rose-800/40"
          >
            <LogOut size={15} />
            {!collapsed && <span>Sign Out ({username})</span>}
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <header className="h-14 bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 px-6 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <span className="text-xs font-mono uppercase tracking-wider px-2.5 py-1 rounded bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 font-semibold">
              Compass Plus TW TIC v2.164e
            </span>
            <span className="text-xs font-mono px-2.5 py-1 rounded bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 font-semibold">
              Thales payShield 10K Soft-HSM Connected
            </span>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={toggleDark}
              className="p-2 rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300"
              title="Toggle Light/Dark Mode"
            >
              {dark ? <Sun size={16} /> : <Moon size={16} />}
            </button>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
  );
};
