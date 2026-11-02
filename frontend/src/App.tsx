import React from 'react';
import { HashRouter, Routes, Route, Navigate } from 'react-router-dom';
import { getToken } from './api';
import { Layout } from './components/Layout';
import { LoginPage, DashboardPage } from './pages/LoginAndDashboard';
import {
  CustomersPage,
  CardsPage,
  AccountsPage,
  CardLimitsPage,
  AccountLimitsPage,
} from './pages/BankingEntities';
// [PATCH step01_03:app_import_institutions]
import { InstitutionsAndBinsPage } from './pages/InstitutionsAndBinsPage';
import { CustomerDataMaintenancePage } from './pages/CustomerDataMaintenancePage';
// [PATCH step03_03:app_import_audit_page]
import { AuditTrailPage } from './pages/AuditTrailPage';
// [PATCH step06:app_import_card_lab]
import { CardCryptoLabPage } from './pages/CardCryptoLabPage';
// [PATCH step10:app_import_key_ceremony]
import { KeyCeremonyWorkbenchPage } from './pages/KeyCeremonyWorkbenchPage';
// [PATCH step11:app_import_network_routing]
import { NetworkRoutingPage } from './pages/NetworkRoutingPage';
// [PATCH step12:app_import_settlement]
import { ClearingAndSettlementPage } from './pages/ClearingAndSettlementPage';
// [PATCH step07:app_import_log_portal]
import { UnifiedLogPortalPage } from './pages/UnifiedLogPortalPage';
// [PATCH step08:app_import_rules_page]
import { AuthorizerRulesPage } from './pages/AuthorizerRulesPage';
import { TransactionLogViewerPage } from './pages/TransactionLogViewerPage';

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
// [PATCH step01_03:app_route_institutions]
        <Route
          path="/institutions"
          element={
            <ProtectedRoute>
              <InstitutionsAndBinsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/card-limits"
          element={
            <ProtectedRoute>
              <CardLimitsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/account-limits"
          element={
            <ProtectedRoute>
              <AccountLimitsPage />
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
// [PATCH step08:app_route_rules_page]
        <Route
          path="/authorizer-rules"
          element={
            <ProtectedRoute>
              <AuthorizerRulesPage />
            </ProtectedRoute>
          }
        />
// [PATCH step11:app_route_network_routing]
        <Route
          path="/network-routing"
          element={
            <ProtectedRoute>
              <NetworkRoutingPage />
            </ProtectedRoute>
          }
        />
// [PATCH step12:app_route_settlement]
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
// [PATCH step06:app_route_card_lab]
        <Route
          path="/card-lab"
          element={
            <ProtectedRoute>
              <CardCryptoLabPage />
            </ProtectedRoute>
          }
        />
// [PATCH step10:app_route_key_ceremony]
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
// [PATCH step03_03:app_route_audit_page]
        <Route
          path="/audit-trail"
          element={
            <ProtectedRoute>
              <AuditTrailPage />
            </ProtectedRoute>
          }
        />
// [PATCH step07:app_route_log_portal]
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
                <Route path="/transaction-logs" element={<TransactionLogViewerPage />} />
        </Routes>
    </HashRouter>
  );
};

export default App;
