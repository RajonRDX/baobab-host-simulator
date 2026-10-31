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
          path="/notifications"
          element={
            <ProtectedRoute>
              <NotificationsSimulatorPage />
            </ProtectedRoute>
          }
        />
      </Routes>
    </HashRouter>
  );
};

export default App;
