#!/usr/bin/env python3
"""
restore_and_fix_frontend.py
===========================
Fixes the blank white screen by:
  1. Restoring `from '../api'` in all pages that import `apiFetch`, `getToken`,
     `setAuthSession`, or `clearAuthSession` (which were accidentally rewritten to
     `from '../services/api'`).
  2. Creating `frontend/src/api/client.ts` as a bridge re-exporting `api` from
     `../services/api` so both `../api/client` and `../services/api` resolve cleanly.
  3. Writing a clean, valid `frontend/src/App.tsx` and `frontend/src/components/Layout.tsx`
     where every `NAV_ITEMS` entry has a valid Lucide `icon` component (`Sliders`,
     `ShieldAlert`, `CreditCard`, `CheckCircle2`) and `Authorization Profiles` appears
     immediately before `Authorizer Rules`.
  4. Cleaning any stray tags at the end of `frontend/src/pages/InstitutionsAndBinsPage.tsx`.
"""

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "frontend" / "src"

if not SRC_DIR.exists():
    print("Error: Could not find frontend/src. Run this script from E:\\HOST_VSCODE\\host-simulator")
    raise SystemExit(1)

# ------------------------------------------------------------------------------
# 1. Create frontend/src/api/client.ts bridge so '../api/client' and '../services/api' both work
# ------------------------------------------------------------------------------
api_client_bridge = SRC_DIR / "api" / "client.ts"
api_client_bridge.parent.mkdir(parents=True, exist_ok=True)
api_client_bridge.write_text(
    "import { api } from '../services/api';\nexport { api };\nexport default api;\n",
    encoding="utf-8",
)
print("[OK] Created bridge frontend/src/api/client.ts -> ../services/api")

# ------------------------------------------------------------------------------
# 2. Fix all pages in frontend/src/pages/*.tsx & components/*.tsx where
#    apiFetch / setAuthSession / getToken / clearAuthSession were pointed at '../services/api'
# ------------------------------------------------------------------------------
for folder in [SRC_DIR / "pages", SRC_DIR / "components"]:
    if not folder.exists():
        continue
    for tsx in folder.glob("*.tsx"):
        text = tsx.read_text(encoding="utf-8")
        orig = text
        # Any import of apiFetch, setAuthSession, clearAuthSession, or getToken MUST come from '../api'
        text = re.sub(
            r"(import\s*\{[^}]*\b(?:apiFetch|setAuthSession|clearAuthSession|getToken)\b[^}]*\}\s*from\s*)['\"]\.\./services/api['\"]",
            r"\1'../api'",
            text,
        )
        # Any import of { api } in new pages should come from '../services/api'
        text = re.sub(
            r"(import\s*\{\s*api\s*\}\s*from\s*)['\"]\.\./api/client['\"]",
            r"\1'../services/api'",
            text,
        )
        if text != orig:
            tsx.write_text(text, encoding="utf-8")
            print(f"[FIXED IMPORTS] {tsx.relative_to(PROJECT_ROOT)}")

# ------------------------------------------------------------------------------
# 3. Clean InstitutionsAndBinsPage.tsx if corrupt trailing JSX was injected
# ------------------------------------------------------------------------------
inst_page = SRC_DIR / "pages" / "InstitutionsAndBinsPage.tsx"
if inst_page.exists():
    inst_text = inst_page.read_text(encoding="utf-8")
    # Ensure CardProfilesUnderBinTab is imported once and placed inside the main wrapper div
    inst_text = re.sub(
        r"// \[PATCH step13_04:card_profiles_tab\]\s*import \{ CardProfilesUnderBinTab \} from '\./CardProfilesUnderBinTab';\s*",
        "",
        inst_text,
    )
    inst_text = re.sub(r"\s*<CardProfilesUnderBinTab\s*/>\s*", "\n", inst_text)
    # Remove any broken trailing export lines added by earlier scripts
    inst_text = re.sub(
        r"\);\s*\};\s*export default InstitutionsAndBinsPage;\s*$",
        "  );\n};\n",
        inst_text,
    )
    # Now cleanly import CardProfilesUnderBinTab at top and render before final </div>
    inst_text = "import { CardProfilesUnderBinTab } from './CardProfilesUnderBinTab';\n" + inst_text
    last_div = inst_text.rfind("</div>")
    if last_div != -1:
        inst_text = (
            inst_text[:last_div]
            + "  <CardProfilesUnderBinTab />\n    </div>"
            + inst_text[last_div + 6 :]
        )
    inst_page.write_text(inst_text, encoding="utf-8")
    print("[OK] Repaired frontend/src/pages/InstitutionsAndBinsPage.tsx")

# ------------------------------------------------------------------------------
# 4. Write clean, complete frontend/src/components/Layout.tsx with valid icons on ALL items
# ------------------------------------------------------------------------------
CLEAN_LAYOUT_TSX = """import React, { useState } from 'react';
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
  { to: '/institutions', label: '1.5. Banks & Switch BINS', icon: Network, group: 'CORE BANKING' },
  { to: '/card-profiles', label: '1.6. Card Profiles (BIN)', icon: CreditCard, group: 'CORE BANKING' },
  { to: '/settlement', label: '1.8. Clearing & Settlement', icon: Landmark, group: 'CORE BANKING' },
  { to: '/card-limits', label: '5. Card Limits', icon: Sliders, group: 'LIMIT ENGINE' },
  { to: '/account-limits', label: '6. Account Limits', icon: ShieldAlert, group: 'LIMIT ENGINE' },
  { to: '/transaction-codes', label: '7. Transaction Codes', icon: FileCode2, group: 'SWITCH & SIMULATOR' },
  { to: '/authorization-profiles', label: '7.4. Authorization Profiles', icon: CheckCircle2, group: 'SWITCH & SIMULATOR' },
  { to: '/authorizer-rules', label: '7.5. Authorizer Rules', icon: Sliders, group: 'SWITCH & SIMULATOR' },
  { to: '/network-routing', label: '7.8. Network Routing & Sim', icon: Network, group: 'SWITCH & SIMULATOR' },
  { to: '/simulator', label: '8. Transaction Simulator', icon: TerminalSquare, group: 'SWITCH & SIMULATOR' },
  { to: '/transactions', label: '9. Transaction Journal', icon: BookOpen, group: 'SWITCH & SIMULATOR' },
  { to: '/hsm-keys', label: '11. Host Key Management', icon: KeyRound, group: 'CRYPTO & HSM' },
  { to: '/hsm-workbench', label: '12. HSM Workbench', icon: Cpu, group: 'CRYPTO & HSM' },
  { to: '/card-lab', label: '12.5. PIN & Card Lab', icon: CreditCard, group: 'CRYPTO & HSM' },
  { to: '/key-ceremony', label: '12.8. Key Ceremony Lab', icon: Layers, group: 'CRYPTO & HSM' },
  { to: '/monitor', label: '13. Execution Monitor', icon: Activity, group: 'OBSERVABILITY' },
  { to: '/log-portal', label: '13.5. Operational & Crypto Portal', icon: Activity, group: 'OBSERVABILITY' },
  { to: '/transaction-logs', label: 'Transaction Log Viewer', icon: Activity, group: 'OBSERVABILITY' },
  { to: '/host-config', label: '14. Host Configuration', icon: Settings, group: 'OBSERVABILITY' },
  { to: '/response-codes', label: '15. Response Codes', icon: CheckCircle2, group: 'OBSERVABILITY' },
  { to: '/system-logs', label: '16. System Logs', icon: ScrollText, group: 'OBSERVABILITY' },
  { to: '/audit-trail', label: '16.5. Audit Trail Diff', icon: CheckCircle2, group: 'OBSERVABILITY' },
  { to: '/notifications', label: '17. Notifications Sim', icon: Bell, group: 'OBSERVABILITY' },
];

export const Layout: React.FC<LayoutProps> = ({ children }) => {
  const [collapsed, setCollapsed] = useState(false);
  const [dark, setDark] = useState(() => document.documentElement.classList.contains('dark'));
  const navigate = useNavigate();
  const hsmMode = sessionStorage.getItem('RAJON_HSM_MODE') || 'SOFT_HSM_LOCAL';
  const username = sessionStorage.getItem('RAJON_USER') || 'admin';

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
                <div className="font-mono font-bold text-sm tracking-wider text-white">RAJON HOST</div>
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
            const Icon = item.icon || Activity;
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

      <div className="flex-1 flex flex-col overflow-hidden">
        <header className="h-14 bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 px-6 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <span className="text-xs font-mono uppercase tracking-wider px-2.5 py-1 rounded bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 font-semibold">
              Rajon TIC v2.164e
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
"""

(SRC_DIR / "components" / "Layout.tsx").write_text(CLEAN_LAYOUT_TSX, encoding="utf-8")
print("[OK] Wrote clean frontend/src/components/Layout.tsx with valid icons")

# ------------------------------------------------------------------------------
# 5. Write clean, complete frontend/src/App.tsx with all routes wrapped in ProtectedRoute
# ------------------------------------------------------------------------------
CLEAN_APP_TSX = """import React from 'react';
import { HashRouter, Routes, Route, Navigate } from 'react-router-dom';
import { getToken } from './api';
import { Layout } from './components/Layout';
import { LoginPage, DashboardPage } from './pages/LoginAndDashboard';
import {
  CustomersPage,
  CardsPage,
  AccountsPage,
} from './pages/BankingEntities';
import { InstitutionsAndBinsPage } from './pages/InstitutionsAndBinsPage';
import { CustomerDataMaintenancePage } from './pages/CustomerDataMaintenancePage';
import { AuditTrailPage } from './pages/AuditTrailPage';
import { CardCryptoLabPage } from './pages/CardCryptoLabPage';
import { KeyCeremonyWorkbenchPage } from './pages/KeyCeremonyWorkbenchPage';
import { NetworkRoutingPage } from './pages/NetworkRoutingPage';
import { ClearingAndSettlementPage } from './pages/ClearingAndSettlementPage';
import { UnifiedLogPortalPage } from './pages/UnifiedLogPortalPage';
import { AuthorizerRulesPage } from './pages/AuthorizerRulesPage';
import { TransactionLogViewerPage } from './pages/TransactionLogViewerPage';
import { LimitManagementPage } from './pages/LimitManagementPage';
import { AuthorizationProfilesPage } from './pages/AuthorizationProfilesPage';
import { CardProfilesUnderBinTab } from './pages/CardProfilesUnderBinTab';

import {
  TransactionCodesPage,
  HostConfigurationPage,
  ResponseCodesPage,
} from './pages/HostConfigPages';
import {
  TransactionSimulatorPage,
  TransactionJournalPage,
  TransactionDetailsPage,
} from './pages/SimulatorAndJournal';
import {
  HostKeyManagementPage,
  HsmWorkbenchPage,
  HostExecutionMonitorPage,
  SystemLogsPage,
  NotificationsSimulatorPage,
} from './pages/HsmAndMonitorPages';

const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  if (!getToken()) {
    return <Navigate to="/login" replace />;
  }
  return <Layout>{children}</Layout>;
};

export const App: React.FC = () => {
  return (
    <HashRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <DashboardPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/customers"
          element={
            <ProtectedRoute>
              <CustomersPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/cards"
          element={
            <ProtectedRoute>
              <CardsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/accounts"
          element={
            <ProtectedRoute>
              <AccountsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/institutions"
          element={
            <ProtectedRoute>
              <InstitutionsAndBinsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/card-profiles"
          element={
            <ProtectedRoute>
              <CardProfilesUnderBinTab />
            </ProtectedRoute>
          }
        />
        <Route
          path="/card-limits"
          element={
            <ProtectedRoute>
              <LimitManagementPage initialScope="CARD" />
            </ProtectedRoute>
          }
        />
        <Route
          path="/account-limits"
          element={
            <ProtectedRoute>
              <LimitManagementPage initialScope="ACCOUNT" />
            </ProtectedRoute>
          }
        />
        <Route
          path="/limits"
          element={
            <ProtectedRoute>
              <LimitManagementPage initialScope="CARD" />
            </ProtectedRoute>
          }
        />
        <Route
          path="/authorization-profiles"
          element={
            <ProtectedRoute>
              <AuthorizationProfilesPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/transaction-codes"
          element={
            <ProtectedRoute>
              <TransactionCodesPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/authorizer-rules"
          element={
            <ProtectedRoute>
              <AuthorizerRulesPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/network-routing"
          element={
            <ProtectedRoute>
              <NetworkRoutingPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/settlement"
          element={
            <ProtectedRoute>
              <ClearingAndSettlementPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/simulator"
          element={
            <ProtectedRoute>
              <TransactionSimulatorPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/transactions"
          element={
            <ProtectedRoute>
              <TransactionJournalPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/transactions/:id"
          element={
            <ProtectedRoute>
              <TransactionDetailsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/hsm-keys"
          element={
            <ProtectedRoute>
              <HostKeyManagementPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/hsm-workbench"
          element={
            <ProtectedRoute>
              <HsmWorkbenchPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/card-lab"
          element={
            <ProtectedRoute>
              <CardCryptoLabPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/key-ceremony"
          element={
            <ProtectedRoute>
              <KeyCeremonyWorkbenchPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/monitor"
          element={
            <ProtectedRoute>
              <HostExecutionMonitorPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/host-config"
          element={
            <ProtectedRoute>
              <HostConfigurationPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/response-codes"
          element={
            <ProtectedRoute>
              <ResponseCodesPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/system-logs"
          element={
            <ProtectedRoute>
              <SystemLogsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/audit-trail"
          element={
            <ProtectedRoute>
              <AuditTrailPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/log-portal"
          element={
            <ProtectedRoute>
              <UnifiedLogPortalPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/notifications"
          element={
            <ProtectedRoute>
              <NotificationsSimulatorPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/customer-maintenance"
          element={
            <ProtectedRoute>
              <CustomerDataMaintenancePage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/transaction-logs"
          element={
            <ProtectedRoute>
              <TransactionLogViewerPage />
            </ProtectedRoute>
          }
        />
      </Routes>
    </HashRouter>
  );
};

export default App;
"""

(SRC_DIR / "App.tsx").write_text(CLEAN_APP_TSX, encoding="utf-8")
print("[OK] Wrote clean frontend/src/App.tsx")
print("\nDone! Refresh http://localhost:5173/#/ in your browser.")