import React, { useEffect, useState } from 'react';
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
