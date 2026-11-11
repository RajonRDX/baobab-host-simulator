#!/usr/bin/env python3
"""
fix_router_nesting_crash.py
===========================
Fixes the React Router v6 runtime invariant crash:
  "You cannot render a <Router> inside another <Router>."

Root Cause:
  `IsolatedRouteViewport` in `frontend/src/workspace/RouteRenderer.tsx` rendered a
  `<MemoryRouter>` inside the main `<HashRouter>`, which React Router v6 forbids.

Fix:
  1. Replaces `<MemoryRouter>` in `IsolatedRouteViewport` with `<Routes location={virtualLocation}>`
     plus an interactive click interceptor for internal `<a href="#/...">` links so pop-out
     windows and side-by-side split panes can render any route and navigate internally
     without ever instantiating a second `<Router>`!
  2. Also ensures `Layout.tsx` and `App.tsx` (Part 3) are cleanly installed so the entire
     3-part UI upgrade works out-of-the-box in a single command.

Run from your project root (E:\HOST_VSCODE\host-simulator):
    python fix_router_nesting_crash.py
"""

from datetime import datetime
from pathlib import Path
import shutil


def resolve_project_root() -> Path:
    here = Path(__file__).resolve().parent
    if (here / "frontend" / "src").exists():
        return here
    if (here.parent / "frontend" / "src").exists():
        return here.parent
    cwd = Path.cwd()
    if (cwd / "frontend" / "src").exists():
        return cwd
    raise RuntimeError("Could not locate 'frontend/src'. Please run this script from the project root folder.")


PROJECT_ROOT = resolve_project_root()
BACKUP_ROOT = PROJECT_ROOT / "_backups" / f"fix_router_crash_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def write_project_file(rel_path: str, content: str) -> None:
    target = PROJECT_ROOT / rel_path
    if target.exists():
        bkp = BACKUP_ROOT / rel_path
        bkp.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, bkp)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    print(f"  [OK] Wrote {rel_path} ({len(content):,} bytes)")


ROUTE_RENDERER_TSX_FIXED = r"""import React, { useEffect, useMemo, useState } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';

import { DashboardPage } from '../pages/LoginAndDashboard';
import { CustomersPage, CardsPage, AccountsPage } from '../pages/BankingEntities';
import { InstitutionsAndBinsPage } from '../pages/InstitutionsAndBinsPage';
import { CustomerDataMaintenancePage } from '../pages/CustomerDataMaintenancePage';
import { AuditTrailPage } from '../pages/AuditTrailPage';
import { CardCryptoLabPage } from '../pages/CardCryptoLabPage';
import { KeyCeremonyWorkbenchPage } from '../pages/KeyCeremonyWorkbenchPage';
import { NetworkRoutingPage } from '../pages/NetworkRoutingPage';
import { ClearingAndSettlementPage } from '../pages/ClearingAndSettlementPage';
import { UnifiedLogPortalPage } from '../pages/UnifiedLogPortalPage';
import { TransactionLogViewerPage } from '../pages/TransactionLogViewerPage';
import { LimitManagementPage } from '../pages/LimitManagementPage';
import { AuthorizationProfilesPage } from '../pages/AuthorizationProfilesPage';
import { CardProfilesUnderBinTab } from '../pages/CardProfilesUnderBinTab';
import { HostControlCenterPage } from '../pages/hostcontrol/HostControlCenterPage';
import { TransactionCodesPage, ResponseCodesPage } from '../pages/HostConfigPages';
import {
  TransactionSimulatorPage,
  TransactionJournalPage,
  TransactionDetailsPage,
} from '../pages/SimulatorAndJournal';
import {
  HostKeyManagementPage,
  HsmWorkbenchPage,
  HostExecutionMonitorPage,
  SystemLogsPage,
  NotificationsSimulatorPage,
} from '../pages/HsmAndMonitorPages';

export const HostRoutesSwitch: React.FC<{ customLocation?: any }> = ({ customLocation }) => {
  return (
    <Routes location={customLocation}>
      <Route path="/" element={<DashboardPage />} />
      <Route path="/customers" element={<CustomersPage />} />
      <Route path="/cards" element={<CardsPage />} />
      <Route path="/accounts" element={<AccountsPage />} />
      <Route path="/institutions" element={<InstitutionsAndBinsPage />} />
      <Route path="/card-profiles" element={<CardProfilesUnderBinTab />} />
      <Route path="/card-limits" element={<LimitManagementPage initialScope="CARD" />} />
      <Route path="/account-limits" element={<LimitManagementPage initialScope="ACCOUNT" />} />
      <Route path="/limits" element={<LimitManagementPage initialScope="CARD" />} />
      <Route path="/authorization-profiles" element={<AuthorizationProfilesPage />} />
      <Route path="/transaction-codes" element={<TransactionCodesPage />} />
      <Route path="/authorizer-rules" element={<Navigate to="/host-config" replace />} />
      <Route path="/network-routing" element={<NetworkRoutingPage />} />
      <Route path="/settlement" element={<ClearingAndSettlementPage />} />
      <Route path="/simulator" element={<TransactionSimulatorPage />} />
      <Route path="/transactions" element={<TransactionJournalPage />} />
      <Route path="/transactions/:id" element={<TransactionDetailsPage />} />
      <Route path="/hsm-keys" element={<HostKeyManagementPage />} />
      <Route path="/hsm-workbench" element={<HsmWorkbenchPage />} />
      <Route path="/card-lab" element={<CardCryptoLabPage />} />
      <Route path="/key-ceremony" element={<KeyCeremonyWorkbenchPage />} />
      <Route path="/monitor" element={<HostExecutionMonitorPage />} />
      <Route path="/host-config" element={<HostControlCenterPage />} />
      <Route path="/response-codes" element={<ResponseCodesPage />} />
      <Route path="/system-logs" element={<SystemLogsPage />} />
      <Route path="/audit-trail" element={<AuditTrailPage />} />
      <Route path="/log-portal" element={<UnifiedLogPortalPage />} />
      <Route path="/notifications" element={<NotificationsSimulatorPage />} />
      <Route path="/customer-maintenance" element={<CustomerDataMaintenancePage />} />
      <Route path="/transaction-logs" element={<TransactionLogViewerPage />} />
      <Route path="*" element={<DashboardPage />} />
    </Routes>
  );
};

/**
 * IsolatedRouteViewport renders any route path inside a Pop-Out Window or Side-by-Side Split
 * WITHOUT creating a nested <Router> (which React Router v6 forbids).
 * Instead, it passes a virtual location object to <Routes location={virtualLocation}> and
 * intercepts internal <Link to="..."> clicks so navigation stays inside the pop-out/split pane!
 */
export const IsolatedRouteViewport: React.FC<{ initialPath: string }> = ({ initialPath }) => {
  const [internalPath, setInternalPath] = useState<string>(initialPath || '/');

  useEffect(() => {
    setInternalPath(initialPath || '/');
  }, [initialPath]);

  const virtualLocation = useMemo(() => {
    const raw = internalPath || '/';
    const [pathname, searchPart] = raw.split('?');
    return {
      pathname: pathname.startsWith('/') ? pathname : `/${pathname}`,
      search: searchPart ? `?${searchPart}` : '',
      hash: '',
      state: null,
      key: `isolated-${raw}`,
    };
  }, [internalPath]);

  const handleContainerClickCapture = (e: React.MouseEvent<HTMLDivElement>) => {
    const anchor = (e.target as HTMLElement)?.closest('a');
    if (!anchor) return;
    const href = anchor.getAttribute('href') || '';
    if (href.startsWith('#/')) {
      e.preventDefault();
      e.stopPropagation();
      setInternalPath(href.slice(1));
    } else if (href.startsWith('/') && !href.startsWith('//')) {
      e.preventDefault();
      e.stopPropagation();
      setInternalPath(href);
    }
  };

  return (
    <div onClickCapture={handleContainerClickCapture} className="w-full h-full">
      <HostRoutesSwitch customLocation={virtualLocation} />
    </div>
  );
};
"""


LAYOUT_TSX_CONTENT = r"""import React, { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  LogOut,
  Moon,
  Sun,
  Layers,
  Columns,
  Maximize2,
  Search,
  X,
  ExternalLink,
  PanelLeftClose,
  FolderTree,
  TerminalSquare,
  CreditCard,
  Cpu,
} from 'lucide-react';
import { clearAuthSession, ensureSilentAuthSession } from '../api';
import {
  PAYMENT_ARCHITECTURE_TREE,
  ALL_NAV_ITEMS,
  resolveNavMeta,
  NavDomainBranch,
  NavSubItem,
} from '../workspace/navRegistry';
import { useWorkspace } from '../workspace/WorkspaceContext';
import { FloatingWindowManager } from '../workspace/FloatingWindowManager';
import { IsolatedRouteViewport } from '../workspace/RouteRenderer';

interface LayoutProps {
  children: React.ReactNode;
}

export const Layout: React.FC<LayoutProps> = ({ children }) => {
  const location = useLocation();
  const navigate = useNavigate();

  const {
    windows,
    splitPath,
    splitWidthPercent,
    subTreeMode,
    clickBehavior,
    commandPaletteOpen,
    setSubTreeMode,
    setClickBehavior,
    setCommandPaletteOpen,
    setSplitWidthPercent,
    openPopoutWindow,
    openSideBySideSplit,
    closeSideBySideSplit,
  } = useWorkspace();

  const [collapsed, setCollapsed] = useState(false);
  const [dark, setDark] = useState(() => document.documentElement.classList.contains('dark'));

  const activeMeta = useMemo(() => resolveNavMeta(location.pathname), [location.pathname]);

  const [selectedBranchId, setSelectedBranchId] = useState<string | null>(null);
  const [expandedBranches, setExpandedBranches] = useState<Record<string, boolean>>(() => ({
    [activeMeta.branchId]: true,
    'card-management': true,
    'simulator-journals': true,
  }));

  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    ensureSilentAuthSession();
  }, []);

  useEffect(() => {
    setExpandedBranches((prev) => ({ ...prev, [activeMeta.branchId]: true }));
  }, [activeMeta.branchId]);

  const hsmMode =
    localStorage.getItem('RAJON_HSM_MODE') ||
    sessionStorage.getItem('RAJON_HSM_MODE') ||
    'SOFT_HSM_REMOTE';
  const username =
    localStorage.getItem('RAJON_USER') ||
    sessionStorage.getItem('RAJON_USER') ||
    'admin';

  const toggleDark = () => {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle('dark', next);
  };

  const handleLogout = () => {
    clearAuthSession();
    navigate('/login');
  };

  const handleBranchClick = (branch: NavDomainBranch) => {
    if (subTreeMode === 'SIDE_FLYOUT') {
      setSelectedBranchId((prev) => (prev === branch.id ? null : branch.id));
    } else {
      setExpandedBranches((prev) => ({
        ...prev,
        [branch.id]: !prev[branch.id],
      }));
    }
  };

  const handleSubItemClick = (item: NavSubItem, forceMainCanvas = false) => {
    if (subTreeMode === 'SIDE_FLYOUT') {
      setSelectedBranchId(null);
    }
    if (forceMainCanvas || clickBehavior === 'MAIN_CANVAS' || item.to === location.pathname) {
      navigate(item.to);
    } else {
      openPopoutWindow(item.to, 'LG');
    }
  };

  const activeFlyoutBranch = useMemo(
    () => PAYMENT_ARCHITECTURE_TREE.find((b) => b.id === selectedBranchId) || null,
    [selectedBranchId]
  );

  const filteredSearchItems = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return ALL_NAV_ITEMS;
    return ALL_NAV_ITEMS.filter(
      (item) =>
        item.label.toLowerCase().includes(q) ||
        item.shortLabel.toLowerCase().includes(q) ||
        item.code.toLowerCase().includes(q) ||
        item.description.toLowerCase().includes(q) ||
        item.branchTitle.toLowerCase().includes(q)
    );
  }, [searchQuery]);

  const splitMeta = useMemo(
    () => (splitPath ? resolveNavMeta(splitPath) : null),
    [splitPath]
  );

  return (
    <div className="flex h-screen overflow-hidden bg-slate-100 dark:bg-slate-950 text-slate-900 dark:text-slate-100">
      {/* LEFT DOMAIN TREE SIDEBAR */}
      <aside
        className={`${
          collapsed ? 'w-16' : 'w-72'
        } bg-slate-950 text-slate-200 flex flex-col border-r border-slate-800/90 transition-all duration-200 select-none z-30 shrink-0`}
      >
        <div className="h-14 flex items-center justify-between px-3.5 border-b border-slate-800/90 bg-slate-900/60">
          {!collapsed && (
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="h-3 w-3 rounded-full bg-emerald-400 animate-pulse shadow-[0_0_12px_#10b981]" />
              <div className="truncate">
                <div className="font-mono font-bold text-xs tracking-wider text-white">
                  RAJON PAYMENT SWITCH
                </div>
                <div className="text-[10px] font-mono text-emerald-400 truncate">
                  ARCHITECT WORKBENCH v2.0
                </div>
              </div>
            </div>
          )}
          <button
            type="button"
            onClick={() => {
              setCollapsed(!collapsed);
              setSelectedBranchId(null);
            }}
            className="p-1.5 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white transition"
            title={collapsed ? 'Expand Sidebar' : 'Collapse Sidebar'}
          >
            {collapsed ? <ChevronRight size={17} /> : <ChevronLeft size={17} />}
          </button>
        </div>

        {!collapsed && (
          <div className="p-2.5 border-b border-slate-800/80 bg-slate-900/30 space-y-2">
            <div className="flex items-center justify-between gap-1 bg-slate-900 p-1 rounded-xl border border-slate-800">
              <button
                type="button"
                onClick={() => setSubTreeMode('SIDE_FLYOUT')}
                className={`flex-1 flex items-center justify-center gap-1.5 py-1 px-2 rounded-lg text-[10px] font-mono font-bold transition ${
                  subTreeMode === 'SIDE_FLYOUT'
                    ? 'bg-emerald-600 text-white shadow'
                    : 'text-slate-400 hover:text-white'
                }`}
                title="Open sub-tree side-by-side when clicking a main branch"
              >
                <Columns size={12} />
                <span>Side Sub-Tree</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  setSubTreeMode('ACCORDION');
                  setSelectedBranchId(null);
                }}
                className={`flex-1 flex items-center justify-center gap-1.5 py-1 px-2 rounded-lg text-[10px] font-mono font-bold transition ${
                  subTreeMode === 'ACCORDION'
                    ? 'bg-emerald-600 text-white shadow'
                    : 'text-slate-400 hover:text-white'
                }`}
                title="Expand sub-tree inline inside the sidebar"
              >
                <FolderTree size={12} />
                <span>Inline Tree</span>
              </button>
            </div>

            <button
              type="button"
              onClick={() => setCommandPaletteOpen(true)}
              className="w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800/90 border border-slate-800 text-xs text-slate-400 hover:text-slate-200 transition"
            >
              <span className="flex items-center gap-2 font-mono text-[11px]">
                <Search size={13} className="text-emerald-400" />
                <span>Jump / Pop-out module...</span>
              </span>
              <kbd className="px-1.5 py-0.5 text-[9px] font-mono bg-slate-950 text-slate-400 rounded border border-slate-800">
                Ctrl+K
              </kbd>
            </button>
          </div>
        )}

        <nav className="flex-1 overflow-y-auto py-2.5 px-2 space-y-1.5">
          {PAYMENT_ARCHITECTURE_TREE.map((branch) => {
            const BranchIcon = branch.icon;
            const hasActiveRoute = branch.items.some((i) => i.to === location.pathname);
            const isFlyoutSelected =
              subTreeMode === 'SIDE_FLYOUT' && selectedBranchId === branch.id;
            const isAccordionExpanded =
              subTreeMode === 'ACCORDION' && !!expandedBranches[branch.id];

            return (
              <div key={branch.id} className="space-y-1">
                <button
                  type="button"
                  onClick={() => handleBranchClick(branch)}
                  title={collapsed ? `${branch.title} (${branch.subtitle})` : undefined}
                  className={`w-full flex items-center justify-between px-2.5 py-2.5 rounded-xl text-left transition-all border ${
                    isFlyoutSelected
                      ? `bg-gradient-to-r ${branch.accent} shadow-md`
                      : hasActiveRoute
                      ? 'bg-slate-900/95 border-emerald-500/40 text-white'
                      : 'bg-slate-900/40 hover:bg-slate-900 border-slate-800/60 text-slate-300 hover:text-white'
                  }`}
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <div
                      className={`p-1.5 rounded-lg border shrink-0 ${
                        hasActiveRoute || isFlyoutSelected
                          ? branch.badgeColor
                          : 'bg-slate-900 border-slate-800 text-slate-400'
                      }`}
                    >
                      <BranchIcon size={16} />
                    </div>
                    {!collapsed && (
                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5">
                          <span className="text-xs font-bold tracking-tight truncate">
                            {branch.title}
                          </span>
                          {hasActiveRoute && (
                            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 shrink-0" />
                          )}
                        </div>
                        <div className="text-[10px] text-slate-400 truncate">
                          {branch.subtitle}
                        </div>
                      </div>
                    )}
                  </div>

                  {!collapsed && (
                    <div className="flex items-center gap-1 shrink-0 ml-1">
                      <span className="px-1.5 py-0.5 rounded-md bg-slate-950/80 border border-slate-800 text-[10px] font-mono text-slate-400">
                        {branch.items.length}
                      </span>
                      {subTreeMode === 'SIDE_FLYOUT' ? (
                        <ChevronRight
                          size={14}
                          className={`transition-transform ${
                            isFlyoutSelected ? 'translate-x-0.5 text-emerald-400' : 'text-slate-500'
                          }`}
                        />
                      ) : (
                        <ChevronDown
                          size={14}
                          className={`transition-transform ${
                            isAccordionExpanded ? 'rotate-180 text-emerald-400' : 'text-slate-500'
                          }`}
                        />
                      )}
                    </div>
                  )}
                </button>

                {!collapsed && subTreeMode === 'ACCORDION' && isAccordionExpanded && (
                  <div className="ml-3.5 pl-2.5 border-l-2 border-slate-800 space-y-1 py-1">
                    {branch.items.map((sub) => {
                      const SubIcon = sub.icon;
                      const isCurrentMain = location.pathname === sub.to;
                      const isPoppedOut = windows.some((w) => w.path === sub.to);

                      return (
                        <div
                          key={sub.to}
                          className={`group flex items-center justify-between rounded-lg px-2.5 py-1.5 text-xs transition ${
                            isCurrentMain
                              ? 'bg-emerald-600/20 border border-emerald-500/40 text-emerald-300 font-semibold'
                              : 'text-slate-300 hover:bg-slate-900 hover:text-white border border-transparent'
                          }`}
                        >
                          <button
                            type="button"
                            onClick={() => handleSubItemClick(sub)}
                            className="flex items-center gap-2 min-w-0 flex-1 text-left"
                          >
                            <SubIcon size={14} className={sub.accentColor} />
                            <span className="font-mono text-[10px] text-slate-500 shrink-0">
                              {sub.code}
                            </span>
                            <span className="truncate">{sub.shortLabel}</span>
                            {isPoppedOut && (
                              <span className="px-1 py-0.2 rounded bg-sky-500/20 text-sky-300 font-mono text-[9px]">
                                WIN
                              </span>
                            )}
                          </button>

                          <div className="hidden group-hover:flex items-center gap-1 shrink-0 ml-1">
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                openPopoutWindow(sub.to, 'LG');
                              }}
                              title="Pop-out in Floating Window"
                              className="p-1 rounded hover:bg-slate-800 text-slate-400 hover:text-emerald-400"
                            >
                              <ExternalLink size={12} />
                            </button>
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                openSideBySideSplit(sub.to);
                              }}
                              title="Open Side-by-Side (Split Screen)"
                              className="p-1 rounded hover:bg-slate-800 text-slate-400 hover:text-sky-400"
                            >
                              <Columns size={12} />
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </nav>

        <div className="p-2.5 border-t border-slate-800/90 bg-slate-900/40 space-y-2">
          {!collapsed && (
            <div className="px-2.5 py-2 rounded-xl bg-slate-950 border border-slate-800/90 text-[11px] font-mono flex items-center justify-between">
              <div>
                <div className="text-[10px] text-slate-400">EXTERNAL HSM LINK</div>
                <div className="text-emerald-400 font-bold truncate">{hsmMode}</div>
              </div>
              <span className="px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 text-[9px] font-bold">
                ONLINE
              </span>
            </div>
          )}
          <button
            type="button"
            onClick={handleLogout}
            className="w-full flex items-center justify-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium bg-rose-950/40 text-rose-300 hover:bg-rose-900/60 border border-rose-800/40 transition"
          >
            <LogOut size={14} />
            {!collapsed && <span>Lock Console ({username})</span>}
          </button>
        </div>
      </aside>

      {/* SIDE-BY-SIDE SUB-TREE FLYOUT DRAWER */}
      {subTreeMode === 'SIDE_FLYOUT' && activeFlyoutBranch && (
        <>
          <div
            className="fixed inset-0 z-20 bg-black/20 backdrop-blur-[1px]"
            onClick={() => setSelectedBranchId(null)}
          />
          <div className="w-88 bg-slate-900/98 backdrop-blur-xl text-slate-100 border-r border-slate-700/80 shadow-[20px_0_50px_rgba(0,0,0,0.65)] z-30 flex flex-col shrink-0">
            <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/60">
              <div className="flex items-center gap-2.5 min-w-0">
                <div className={`p-2 rounded-xl border ${activeFlyoutBranch.badgeColor}`}>
                  <activeFlyoutBranch.icon size={18} />
                </div>
                <div className="min-w-0">
                  <div className="text-[10px] font-mono uppercase tracking-wider text-emerald-400">
                    {activeFlyoutBranch.code} · SUB-TREE MODULES
                  </div>
                  <h3 className="text-sm font-bold text-white truncate">
                    {activeFlyoutBranch.title}
                  </h3>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setSelectedBranchId(null)}
                className="p-1.5 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white"
                title="Close Sub-Tree Drawer"
              >
                <PanelLeftClose size={16} />
              </button>
            </div>

            <div className="px-4 py-2 bg-slate-950/90 border-b border-slate-800/80 flex items-center justify-between text-[10px] font-mono text-slate-400">
              <span>
                Click mode:{' '}
                <strong className="text-emerald-400">
                  {clickBehavior === 'POPOUT' ? 'POP-OUT WINDOW' : 'MAIN VIEW'}
                </strong>
              </span>
              <span>{activeFlyoutBranch.items.length} workbenches</span>
            </div>

            <div className="flex-1 overflow-y-auto p-3 space-y-2.5">
              {activeFlyoutBranch.items.map((sub) => {
                const SubIcon = sub.icon;
                const isCurrentMain = location.pathname === sub.to;
                const isPoppedOut = windows.some((w) => w.path === sub.to);
                const isSplit = splitPath === sub.to;

                return (
                  <div
                    key={sub.to}
                    onClick={() => handleSubItemClick(sub)}
                    className={`group rounded-xl p-3 border transition cursor-pointer ${
                      isCurrentMain
                        ? 'bg-emerald-950/40 border-emerald-500/60 shadow-sm'
                        : 'bg-slate-950/70 hover:bg-slate-800/90 border-slate-800 hover:border-slate-700'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2.5 min-w-0">
                        <div className="p-2 rounded-lg bg-slate-900 border border-slate-800 shrink-0">
                          <SubIcon size={16} className={sub.accentColor} />
                        </div>
                        <div className="min-w-0">
                          <div className="flex items-center gap-1.5">
                            <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-slate-900 border border-slate-700 text-slate-300 font-bold">
                              {sub.code}
                            </span>
                            <span className="text-xs font-bold text-white truncate">
                              {sub.label}
                            </span>
                          </div>
                          <p className="text-[11px] text-slate-400 mt-1 line-clamp-2 leading-relaxed">
                            {sub.description}
                          </p>
                        </div>
                      </div>
                    </div>

                    <div className="mt-3 pt-2 border-t border-slate-800/80 flex items-center justify-between gap-1.5">
                      <div className="flex items-center gap-1">
                        {isCurrentMain && (
                          <span className="px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 font-mono text-[9px] font-bold">
                            ACTIVE MAIN
                          </span>
                        )}
                        {isPoppedOut && (
                          <span className="px-1.5 py-0.5 rounded bg-sky-500/20 text-sky-300 font-mono text-[9px] font-bold">
                            POPPED OUT
                          </span>
                        )}
                        {isSplit && (
                          <span className="px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-300 font-mono text-[9px] font-bold">
                            SPLIT PANE
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-1.5 ml-auto">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            openPopoutWindow(sub.to, 'LG');
                            setSelectedBranchId(null);
                          }}
                          className="flex items-center gap-1 px-2 py-1 rounded-md bg-emerald-600/20 hover:bg-emerald-600 text-emerald-300 hover:text-white border border-emerald-500/30 text-[10px] font-mono font-semibold transition"
                          title="Open as resizable Pop-Out Window over current page"
                        >
                          <ExternalLink size={11} />
                          <span>Pop-Out</span>
                        </button>

                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            openSideBySideSplit(sub.to);
                            setSelectedBranchId(null);
                          }}
                          className="flex items-center gap-1 px-2 py-1 rounded-md bg-sky-600/20 hover:bg-sky-600 text-sky-300 hover:text-white border border-sky-500/30 text-[10px] font-mono font-semibold transition"
                          title="Dock Side-by-Side on the right half of screen"
                        >
                          <Columns size={11} />
                          <span>Side-by-Side</span>
                        </button>

                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleSubItemClick(sub, true);
                          }}
                          className="px-2 py-1 rounded-md bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white text-[10px] font-mono transition"
                          title="Replace primary background canvas"
                        >
                          Main
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </>
      )}

      {/* MAIN WORKSPACE COLUMN */}
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        <header className="h-14 bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 px-4 lg:px-6 flex items-center justify-between gap-3 shrink-0 z-10">
          <div className="flex items-center gap-2.5 min-w-0">
            <span className="px-2 py-0.5 rounded-md bg-emerald-500/10 border border-emerald-500/30 text-emerald-600 dark:text-emerald-400 font-mono text-xs font-bold shrink-0">
              {activeMeta.code}
            </span>
            <div className="truncate">
              <div className="flex items-center gap-1.5 text-xs font-bold tracking-tight truncate">
                <span className="text-slate-400 font-normal hidden sm:inline">
                  {activeMeta.branchTitle} /
                </span>
                <span>{activeMeta.label}</span>
              </div>
              <div className="text-[10px] text-slate-400 truncate hidden md:block">
                {activeMeta.description}
              </div>
            </div>
          </div>

          <div className="hidden xl:flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => openPopoutWindow('/simulator', 'LG')}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 border border-emerald-500/25 text-xs font-mono font-semibold transition"
              title="Pop out Transaction Simulator"
            >
              <TerminalSquare size={13} />
              <span>+ Simulator</span>
            </button>
            <button
              type="button"
              onClick={() => openSideBySideSplit('/transaction-logs')}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-sky-500/10 hover:bg-sky-500/20 text-sky-600 dark:text-sky-400 border border-sky-500/25 text-xs font-mono font-semibold transition"
              title="Open Transaction Log Inspector Side-by-Side"
            >
              <Columns size={13} />
              <span>Split TX Logs</span>
            </button>
            <button
              type="button"
              onClick={() => openPopoutWindow('/customer-maintenance', 'XL')}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-violet-500/10 hover:bg-violet-500/20 text-violet-600 dark:text-violet-400 border border-violet-500/25 text-xs font-mono font-semibold transition"
              title="Pop out Customer 360 Maintenance"
            >
              <CreditCard size={13} />
              <span>+ Customer 360</span>
            </button>
            <button
              type="button"
              onClick={() => openPopoutWindow('/hsm-workbench', 'MD')}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-amber-500/10 hover:bg-amber-500/20 text-amber-600 dark:text-amber-400 border border-amber-500/25 text-xs font-mono font-semibold transition"
              title="Pop out Thales 10K HSM Workbench"
            >
              <Cpu size={13} />
              <span>+ HSM 10K</span>
            </button>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <div
              className="flex items-center bg-slate-100 dark:bg-slate-950 p-1 rounded-xl border border-slate-200 dark:border-slate-800"
              title="Choose what happens when you click a tab in the sidebar"
            >
              <button
                type="button"
                onClick={() => setClickBehavior('POPOUT')}
                className={`flex items-center gap-1 px-2.5 py-1 rounded-lg text-[10px] font-mono font-bold transition ${
                  clickBehavior === 'POPOUT'
                    ? 'bg-emerald-600 text-white shadow'
                    : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
                }`}
              >
                <Layers size={12} />
                <span>Pop-Out Mode</span>
              </button>
              <button
                type="button"
                onClick={() => setClickBehavior('MAIN_CANVAS')}
                className={`flex items-center gap-1 px-2.5 py-1 rounded-lg text-[10px] font-mono font-bold transition ${
                  clickBehavior === 'MAIN_CANVAS'
                    ? 'bg-slate-800 text-white shadow'
                    : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
                }`}
              >
                <Maximize2 size={12} />
                <span>Page Mode</span>
              </button>
            </div>

            <button
              type="button"
              onClick={() => openPopoutWindow(location.pathname, 'LG')}
              className="p-2 rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300"
              title="Pop out current page into a floating window"
            >
              <ExternalLink size={15} />
            </button>

            <button
              type="button"
              onClick={toggleDark}
              className="p-2 rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300"
              title="Toggle Light / Dark Theme"
            >
              {dark ? <Sun size={15} /> : <Moon size={15} />}
            </button>
          </div>
        </header>

        <div className="flex-1 flex overflow-hidden relative">
          <main
            style={{
              width: splitPath ? `${100 - splitWidthPercent}%` : '100%',
            }}
            className="h-full overflow-y-auto p-6 transition-all duration-150"
          >
            {children}
          </main>

          {splitPath && splitMeta && (
            <div
              style={{ width: `${splitWidthPercent}%` }}
              className="h-full border-l-2 border-emerald-500/40 bg-slate-50 dark:bg-slate-950 flex flex-col overflow-hidden shadow-2xl"
            >
              <div className="h-10 px-4 bg-slate-900 text-white border-b border-slate-800 flex items-center justify-between shrink-0">
                <div className="flex items-center gap-2 min-w-0">
                  <Columns size={14} className="text-sky-400 shrink-0" />
                  <span className="px-1.5 py-0.5 rounded bg-sky-500/20 text-sky-300 font-mono text-[10px] font-bold">
                    SIDE-BY-SIDE
                  </span>
                  <span className="text-xs font-bold truncate">{splitMeta.label}</span>
                </div>

                <div className="flex items-center gap-1.5">
                  {[35, 50, 60].map((pct) => (
                    <button
                      key={pct}
                      type="button"
                      onClick={() => setSplitWidthPercent(pct)}
                      className={`px-1.5 py-0.5 rounded text-[10px] font-mono ${
                        splitWidthPercent === pct
                          ? 'bg-sky-600 text-white font-bold'
                          : 'bg-slate-800 text-slate-400 hover:text-white'
                      }`}
                      title={`Set split width to ${pct}%`}
                    >
                      {pct}%
                    </button>
                  ))}
                  <button
                    type="button"
                    onClick={() => {
                      openPopoutWindow(splitPath, 'LG');
                      closeSideBySideSplit();
                    }}
                    className="p-1 rounded hover:bg-slate-800 text-slate-400 hover:text-emerald-400"
                    title="Undock into Floating Pop-out Window"
                  >
                    <ExternalLink size={13} />
                  </button>
                  <button
                    type="button"
                    onClick={closeSideBySideSplit}
                    className="p-1 rounded hover:bg-rose-900/60 text-slate-400 hover:text-rose-300"
                    title="Close Split View (ESC)"
                  >
                    <X size={14} />
                  </button>
                </div>
              </div>

              <div className="flex-1 overflow-y-auto p-5">
                <IsolatedRouteViewport key={splitPath} initialPath={splitPath} />
              </div>
            </div>
          )}
        </div>
      </div>

      <FloatingWindowManager />

      {commandPaletteOpen && (
        <div
          className="fixed inset-0 z-[1000] bg-black/60 backdrop-blur-sm flex items-start justify-center pt-20 p-4"
          onClick={() => setCommandPaletteOpen(false)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-2xl bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl overflow-hidden text-slate-100"
          >
            <div className="p-3.5 border-b border-slate-800 flex items-center gap-3 bg-slate-950">
              <Search size={18} className="text-emerald-400 shrink-0" />
              <input
                type="text"
                autoFocus
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search any host workbench, BIN, HSM tool, limit engine, or journal..."
                className="w-full bg-transparent text-sm text-white focus:outline-none font-mono"
              />
              <button
                type="button"
                onClick={() => setCommandPaletteOpen(false)}
                className="px-2 py-0.5 rounded bg-slate-800 text-slate-400 text-[10px] font-mono"
              >
                ESC
              </button>
            </div>

            <div className="max-h-96 overflow-y-auto p-2 divide-y divide-slate-800/60">
              {filteredSearchItems.map((item) => {
                const ItemIcon = item.icon;
                return (
                  <div
                    key={item.to}
                    className="p-2.5 hover:bg-slate-800/80 rounded-xl flex items-center justify-between gap-3 transition"
                  >
                    <div
                      onClick={() => {
                        openPopoutWindow(item.to, 'LG');
                        setCommandPaletteOpen(false);
                      }}
                      className="flex items-center gap-3 min-w-0 flex-1 cursor-pointer"
                    >
                      <div className="p-2 rounded-lg bg-slate-950 border border-slate-800">
                        <ItemIcon size={16} className={item.accentColor} />
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-[10px] text-emerald-400 font-bold">
                            {item.code}
                          </span>
                          <span className="text-xs font-bold text-white truncate">
                            {item.label}
                          </span>
                          <span className="text-[10px] font-mono text-slate-500">
                            ({item.branchTitle})
                          </span>
                        </div>
                        <div className="text-[11px] text-slate-400 truncate">
                          {item.description}
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-1.5 shrink-0">
                      <button
                        type="button"
                        onClick={() => {
                          openPopoutWindow(item.to, 'LG');
                          setCommandPaletteOpen(false);
                        }}
                        className="px-2.5 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-[10px] font-mono font-bold"
                      >
                        Pop-Out
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          openSideBySideSplit(item.to);
                          setCommandPaletteOpen(false);
                        }}
                        className="px-2.5 py-1 rounded-lg bg-sky-600/30 hover:bg-sky-600 text-sky-300 hover:text-white border border-sky-500/40 text-[10px] font-mono font-bold"
                      >
                        Split
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          navigate(item.to);
                          setCommandPaletteOpen(false);
                        }}
                        className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-[10px] font-mono"
                      >
                        Main
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
"""


APP_TSX_CONTENT = r"""import React, { useEffect, useState } from 'react';
import { HashRouter, Routes, Route } from 'react-router-dom';
import { getToken, ensureSilentAuthSession } from './api';
import { Layout } from './components/Layout';
import { LoginPage } from './pages/LoginAndDashboard';
import { WorkspaceProvider } from './workspace/WorkspaceContext';
import { HostRoutesSwitch } from './workspace/RouteRenderer';

const ProtectedWorkspaceShell: React.FC = () => {
  const [ready, setReady] = useState<boolean>(() => Boolean(getToken()));

  useEffect(() => {
    if (!getToken()) {
      ensureSilentAuthSession().finally(() => setReady(true));
    } else {
      setReady(true);
    }
  }, []);

  if (!ready) {
    return (
      <div className="min-h-screen bg-slate-950 text-emerald-400 flex items-center justify-center font-mono text-xs">
        Initializing Rajon Payment Switch & External Soft-HSM Session...
      </div>
    );
  }

  return (
    <WorkspaceProvider>
      <Layout>
        <HostRoutesSwitch />
      </Layout>
    </WorkspaceProvider>
  );
};

export const App: React.FC = () => {
  return (
    <HashRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/*" element={<ProtectedWorkspaceShell />} />
      </Routes>
    </HashRouter>
  );
};

export default App;
"""


def main() -> None:
    print("=" * 76)
    print("FIXING REACT ROUTER NESTED <Router> INVARIANT CRASH")
    print("=" * 76)
    write_project_file("frontend/src/workspace/RouteRenderer.tsx", ROUTE_RENDERER_TSX_FIXED)
    write_project_file("frontend/src/components/Layout.tsx", LAYOUT_TSX_CONTENT)
    write_project_file("frontend/src/App.tsx", APP_TSX_CONTENT)
    print("-" * 76)
    print("FIXED! Refresh your browser (http://localhost:5173) — pop-outs & split panes now work cleanly.")


if __name__ == "__main__":
    main()
