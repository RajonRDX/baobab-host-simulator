import React, { useEffect, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import {
  ShieldCheck,
  Users,
  CreditCard,
  Landmark,
  Activity,
  CheckCircle2,
  XCircle,
  RotateCcw,
  TerminalSquare,
  Cpu,
} from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from 'recharts';
import { apiFetch, setAuthSession } from '../api';

export const LoginPage: React.FC = () => {
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('AdminPassword123!');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const res = await apiFetch('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      });
      setAuthSession(res.access_token, res.username, res.hsm_mode);
      navigate('/');
    } catch (err: any) {
      setError(err.message || 'Authentication failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center p-4">
      <div className="max-w-md w-full bg-slate-900 border border-slate-800 rounded-2xl p-8 shadow-2xl space-y-6">
        <div className="flex items-center gap-3">
          <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400">
            <ShieldCheck size={28} />
          </div>
          <div>
            <h1 className="text-xl font-bold text-white tracking-tight">RAJON Private Host</h1>
            <p className="text-xs font-mono text-slate-400">Single-User Payment Switch & HSM Simulator</p>
          </div>
        </div>

        {error && (
          <div className="p-3 rounded-lg bg-rose-950/80 border border-rose-800 text-rose-300 text-xs font-mono">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-mono uppercase text-slate-400 mb-1">Operator Username</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3.5 py-2.5 text-sm text-white font-mono focus:outline-none focus:border-emerald-500"
              required
            />
          </div>
          <div>
            <label className="block text-xs font-mono uppercase text-slate-400 mb-1">Operator Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3.5 py-2.5 text-sm text-white font-mono focus:outline-none focus:border-emerald-500"
              required
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-semibold py-2.5 rounded-lg text-sm transition shadow-lg"
          >
            {loading ? 'Authenticating...' : 'Sign In to Host Console'}
          </button>
        </form>

        <div className="pt-3 border-t border-slate-800 text-[11px] font-mono text-slate-400 space-y-1">
          <div>Default Local Credentials:</div>
          <div className="text-emerald-400">User: admin | Pass: AdminPassword123!</div>
        </div>
      </div>
    </div>
  );
};

export const DashboardPage: React.FC = () => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const loadSummary = async () => {
    try {
      const res = await apiFetch('/dashboard/summary');
      setData(res);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSummary();
  }, []);

  if (loading || !data) {
    return <div className="text-sm font-mono text-slate-500">Loading Host Switch Telemetry...</div>;
  }

  const m = data.metrics;
  const pieData = [
    { name: 'Approved', value: m.approved_transactions || 0, color: '#10b981' },
    { name: 'Declined', value: m.declined_transactions || 0, color: '#f43f5e' },
    { name: 'Reversed', value: m.reversed_transactions || 0, color: '#f59e0b' },
  ];

  const barData = (data.recent_transactions || []).slice(0, 6).map((t: any) => ({
    stan: `STAN ${t.stan}`,
    amount: t.amount,
  }));

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Banking Host Executive Dashboard</h1>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Real-time authorization telemetry, ledger activity, and Soft-HSM operations
          </p>
        </div>
        <div className="flex gap-2">
          <Link
            to="/simulator"
            className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-lg text-xs font-semibold shadow-sm"
          >
            <TerminalSquare size={15} /> Launch Transaction Simulator
          </Link>
          <Link
            to="/hsm-workbench"
            className="flex items-center gap-2 bg-slate-800 hover:bg-slate-700 text-white px-4 py-2 rounded-lg text-xs font-semibold"
          >
            <Cpu size={15} /> Open HSM Workbench
          </Link>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3">
        {[
          { label: 'Customers', val: m.total_customers, icon: Users, col: 'text-sky-500' },
          { label: 'Active Cards', val: m.active_cards, icon: CreditCard, col: 'text-indigo-500' },
          { label: 'Active Accounts', val: m.active_accounts, icon: Landmark, col: 'text-teal-500' },
          { label: 'Total TXs', val: m.total_transactions, icon: Activity, col: 'text-slate-600 dark:text-slate-300' },
          { label: 'Approved', val: m.approved_transactions, icon: CheckCircle2, col: 'text-emerald-500' },
          { label: 'Declined', val: m.declined_transactions, icon: XCircle, col: 'text-rose-500' },
          { label: 'Reversed', val: m.reversed_transactions, icon: RotateCcw, col: 'text-amber-500' },
          { label: 'Approval Rate', val: `${m.approval_rate}%`, icon: CheckCircle2, col: 'text-emerald-500' },
        ].map((card, i) => {
          const Icon = card.icon;
          return (
            <div
              key={i}
              className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 shadow-sm"
            >
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-mono uppercase text-slate-400">{card.label}</span>
                <Icon size={15} className={card.col} />
              </div>
              <div className="text-xl font-bold font-mono mt-2">{card.val}</div>
            </div>
          );
        })}
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-sm font-bold">Recent Transaction Amounts (BDT)</h2>
            <span className="text-xs font-mono text-emerald-500 font-bold">
              Approved Volume: {m.transaction_volume.toLocaleString()} BDT
            </span>
          </div>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={barData}>
                <XAxis dataKey="stan" stroke="#64748b" fontSize={11} />
                <YAxis stroke="#64748b" fontSize={11} />
                <Tooltip />
                <Bar dataKey="amount" fill="#10b981" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5">
          <h2 className="text-sm font-bold mb-4">Authorization Outcome Split</h2>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={pieData} dataKey="value" nameKey="name" innerRadius={50} outerRadius={75}>
                  {pieData.map((entry, idx) => (
                    <Cell key={idx} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Recent Transactions & Recent HSM Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 overflow-x-auto">
          <div className="flex justify-between items-center mb-3">
            <h2 className="text-sm font-bold">Recent Host Transactions</h2>
            <Link to="/transactions" className="text-xs text-emerald-500 hover:underline">
              View Full Journal ➔
            </Link>
          </div>
          <table className="w-full text-left text-xs font-mono">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-400">
                <th className="py-2">RRN / STAN</th>
                <th className="py-2">Masked PAN</th>
                <th className="py-2">Amount</th>
                <th className="py-2">RC</th>
                <th className="py-2">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200/60 dark:divide-slate-800/60">
              {data.recent_transactions.map((t: any) => (
                <tr key={t.id}>
                  <td className="py-2">
                    <Link to={`/transactions/${t.id}`} className="text-sky-500 hover:underline">
                      {t.rrn} ({t.stan})
                    </Link>
                  </td>
                  <td className="py-2">{t.masked_pan}</td>
                  <td className="py-2">
                    {t.amount.toLocaleString()} {t.currency}
                  </td>
                  <td className="py-2 font-bold">{t.response_code}</td>
                  <td className="py-2">
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        t.authorization_status === 'APPROVED'
                          ? 'bg-emerald-500/10 text-emerald-500'
                          : 'bg-rose-500/10 text-rose-500'
                      }`}
                    >
                      {t.authorization_status}
                    </span>
                  </td>
                </tr>
              ))}
              {data.recent_transactions.length === 0 && (
                <tr>
                  <td colSpan={5} className="py-6 text-center text-slate-400">
                    No transactions processed yet. Open Transaction Simulator to submit one.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 overflow-x-auto">
          <div className="flex justify-between items-center mb-3">
            <h2 className="text-sm font-bold">Recent Soft-HSM Cryptographic Operations</h2>
            <Link to="/monitor" className="text-xs text-emerald-500 hover:underline">
              Live Monitor ➔
            </Link>
          </div>
          <table className="w-full text-left text-xs font-mono">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-400">
                <th className="py-2">Operation</th>
                <th className="py-2">Req Ref</th>
                <th className="py-2">Status</th>
                <th className="py-2">Time</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200/60 dark:divide-slate-800/60">
              {data.recent_hsm_operations.map((h: any) => (
                <tr key={h.id}>
                  <td className="py-2 font-semibold text-amber-500">{h.operation_type}</td>
                  <td className="py-2">{h.request_reference}</td>
                  <td className="py-2">
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        h.response_status === 'APPROVED'
                          ? 'bg-emerald-500/10 text-emerald-500'
                          : 'bg-rose-500/10 text-rose-500'
                      }`}
                    >
                      {h.response_status} (EC {h.error_code})
                    </span>
                  </td>
                  <td className="py-2">{h.duration_ms} ms</td>
                </tr>
              ))}
              {data.recent_hsm_operations.length === 0 && (
                <tr>
                  <td colSpan={4} className="py-6 text-center text-slate-400">
                    No HSM calls recorded yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
