import React, { useEffect, useMemo, useState } from 'react';
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
