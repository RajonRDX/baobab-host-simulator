import React, { useEffect, useState } from 'react';
import { Landmark, ArrowRightLeft, Clock, CheckCircle2, AlertTriangle, RefreshCw, FileText, Play, Layers, DollarSign } from 'lucide-react';
import { apiFetch } from '../api';

export const ClearingAndSettlementPage: React.FC = () => {
  const [tab, setTab] = useState<'BATCHES' | 'POSITIONS' | 'RECON' | 'SCENARIOS'>('BATCHES');
  const [recon, setRecon] = useState<any | null>(null);
  const [batches, setBatches] = useState<any[]>([]);
  const [selectedBatch, setSelectedBatch] = useState<any | null>(null);
  const [positions, setPositions] = useState<any[]>([]);
  const [cutoverMsg, setCutoverMsg] = useState('');
  const [scenarioResult, setScenarioResult] = useState<any | null>(null);

  const loadData = async () => {
    try {
      const [rData, bData] = await Promise.all([
        apiFetch('/settlement/reconciliation'),
        apiFetch('/settlement/batches'),
      ]);
      setRecon(rData);
      setBatches(bData);
      if (bData.length > 0 && !selectedBatch) {
        inspectBatch(bData[0].id);
      }
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const inspectBatch = async (batchId: string) => {
    try {
      const data = await apiFetch(`/settlement/batches/${batchId}`);
      setSelectedBatch(data.batch);
      setPositions(data.positions || []);
    } catch (err: any) {
      alert(err.message);
    }
  };

  const handleExecuteCutover = async () => {
    setCutoverMsg('');
    try {
      const res = await apiFetch('/settlement/cutover', {
        method: 'POST',
        body: JSON.stringify({ ps_code: 'ITCL' }),
      });
      setCutoverMsg(`Cutover Batch ${res.batch_number} executed: Settled ${res.total_transactions} transactions (${res.total_amount.toLocaleString()} BDT) across ${res.institutions_settled} banks.`);
      loadData();
      inspectBatch(res.batch_id);
    } catch (err: any) {
      setCutoverMsg(`Error: ${err.message}`);
    }
  };

  const handleRunScenarios = async () => {
    try {
      const res = await apiFetch('/settlement/run-scenarios', { method: 'POST' });
      setScenarioResult(res);
      loadData();
    } catch (err: any) {
      alert(err.message);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold">Clearing, Daily Settlement & Multilateral Reconciliation</h1>
          <p className="text-xs text-slate-500">
            Dual-balance holds vs ledger clearing, interchange fee calculation, daily cutover batches, and bank settlement positions
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleExecuteCutover}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold shadow"
          >
            <Clock size={14} /> Execute Daily Settlement Cutover
          </button>
        </div>
      </div>

      {cutoverMsg && (
        <div className="p-3.5 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs font-mono">
          {cutoverMsg}
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 shadow-sm">
          <div className="text-[11px] font-mono text-slate-400">TOTAL APPROVED TXS</div>
          <div className="text-2xl font-bold font-mono text-emerald-400 mt-1">
            {recon?.total_approved_transactions || 0}
          </div>
        </div>
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 shadow-sm">
          <div className="text-[11px] font-mono text-slate-400">TOTAL CLEARED / SETTLED</div>
          <div className="text-2xl font-bold font-mono text-sky-400 mt-1">
            {recon?.total_settled_transactions || 0}
          </div>
        </div>
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 shadow-sm">
          <div className="text-[11px] font-mono text-slate-400">PENDING BATCH CLEARING</div>
          <div className="text-2xl font-bold font-mono text-amber-400 mt-1">
            {recon?.pending_clearing_transactions || 0}
          </div>
        </div>
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 shadow-sm">
          <div className="text-[11px] font-mono text-slate-400">SWITCH RECONCILIATION</div>
          <div className="text-sm font-bold font-mono text-emerald-400 mt-2">
            {recon?.reconciliation_status || 'BALANCED'}
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex flex-wrap gap-2 border-b border-slate-200 dark:border-slate-800 pb-2">
        {[
          ['BATCHES', '1. Settlement Batches', Clock],
          ['POSITIONS', '2. Bank Net Positions', Landmark],
          ['SCENARIOS', '3. Scenario Test Runner', Play],
        ].map(([k, label, Icon]: any) => (
          <button
            key={k}
            onClick={() => setTab(k)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-mono font-bold transition ${
              tab === k
                ? 'bg-emerald-600 text-white shadow-sm'
                : 'bg-white dark:bg-slate-900 text-slate-500 hover:text-slate-900 dark:hover:text-white border border-slate-200 dark:border-slate-800'
            }`}
          >
            <Icon size={15} />
            <span>{label}</span>
          </button>
        ))}
      </div>

      {/* TAB 1: BATCHES */}
      {tab === 'BATCHES' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <div className="lg:col-span-7 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 overflow-x-auto">
            <h2 className="text-sm font-bold mb-3">Settlement Cutover Batches</h2>
            <table className="w-full text-left text-xs font-mono">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-400">
                  <th className="py-2.5">Batch Number</th>
                  <th className="py-2.5">Scheme</th>
                  <th className="py-2.5">Cutover Time</th>
                  <th className="py-2.5">Transactions</th>
                  <th className="py-2.5">Volume (BDT)</th>
                  <th className="py-2.5">Fees</th>
                  <th className="py-2.5">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200/60 dark:divide-slate-800/60">
                {batches.map((b) => (
                  <tr
                    key={b.id}
                    onClick={() => inspectBatch(b.id)}
                    className={`cursor-pointer transition ${selectedBatch?.id === b.id ? 'bg-emerald-500/10' : 'hover:bg-slate-50 dark:hover:bg-slate-800/50'}`}
                  >
                    <td className="py-2.5 font-bold text-sky-400">{b.batch_number}</td>
                    <td className="py-2.5 text-emerald-400 font-bold">{b.ps_code}</td>
                    <td className="py-2.5 text-slate-400">{new Date(b.cutover_time).toLocaleTimeString()}</td>
                    <td className="py-2.5 font-bold">{b.total_transactions}</td>
                    <td className="py-2.5">{b.total_amount.toLocaleString()}</td>
                    <td className="py-2.5 text-amber-400">{b.total_fees.toLocaleString()}</td>
                    <td className="py-2.5">
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/10 text-emerald-400">
                        {b.status}
                      </span>
                    </td>
                  </tr>
                ))}
                {batches.length === 0 && (
                  <tr>
                    <td colSpan={7} className="py-8 text-center text-slate-400">
                      No settlement batches closed yet. Click "Execute Daily Settlement Cutover" to clear current transactions.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="lg:col-span-5 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 space-y-4">
            <h2 className="text-sm font-bold flex items-center gap-2">
              <Landmark size={16} className="text-emerald-500" /> Multilateral Net Settlement Positions
            </h2>
            {selectedBatch ? (
              <div className="space-y-3 text-xs font-mono">
                <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 space-y-1">
                  <div>Batch: <span className="text-sky-400 font-bold">{selectedBatch.batch_number}</span></div>
                  <div>Scheme: {selectedBatch.ps_code} Switch · Total Settled: {selectedBatch.total_amount.toLocaleString()} BDT</div>
                </div>

                <div className="space-y-2 max-h-72 overflow-y-auto">
                  {positions.map((pos) => {
                    const isCreditor = pos.net_settlement_amount >= 0;
                    return (
                      <div key={pos.id} className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 flex justify-between items-center">
                        <div>
                          <div className="font-bold text-emerald-400">{pos.institution_name} ({pos.institution_code})</div>
                          <div className="text-[11px] text-slate-400">
                            Debits: {pos.debit_count} ({pos.debit_volume.toLocaleString()}) · Credits: {pos.credit_count} ({pos.credit_volume.toLocaleString()})
                          </div>
                          <div className="text-[10px] text-amber-400">Net Fee Share: {pos.net_fee_amount.toLocaleString()} BDT</div>
                        </div>
                        <div className="text-right">
                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${isCreditor ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'}`}>
                            {isCreditor ? 'NET CREDITOR (Receives)' : 'NET DEBTOR (Pays)'}
                          </span>
                          <div className={`text-sm font-bold mt-1 ${isCreditor ? 'text-emerald-400' : 'text-rose-400'}`}>
                            {pos.net_settlement_amount.toLocaleString()} BDT
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : (
              <div className="text-slate-400 text-xs font-mono py-16 text-center">
                Select a batch on the left to inspect its bank-by-bank net clearing positions.
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 2: BANK POSITIONS */}
      {tab === 'POSITIONS' && (
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 overflow-x-auto">
          <h2 className="text-sm font-bold mb-3">Latest Multilateral Clearing Positions (Per Member Bank)</h2>
          <table className="w-full text-left text-xs font-mono">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-400">
                <th className="py-2.5">Bank</th>
                <th className="py-2.5">Debit Volume (Dispensed to Cardholders)</th>
                <th className="py-2.5">Credit Volume (Acquired from Others)</th>
                <th className="py-2.5">Net Fee Amount</th>
                <th className="py-2.5">Net Settlement Position</th>
                <th className="py-2.5">Obligation Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200/60 dark:divide-slate-800/60">
              {positions.map((pos) => {
                const isCreditor = pos.net_settlement_amount >= 0;
                return (
                  <tr key={pos.id}>
                    <td className="py-2.5 font-bold text-emerald-400">{pos.institution_name} ({pos.institution_code})</td>
                    <td className="py-2.5 text-rose-400">{pos.debit_volume.toLocaleString()} BDT</td>
                    <td className="py-2.5 text-emerald-400">{pos.credit_volume.toLocaleString()} BDT</td>
                    <td className="py-2.5 text-amber-400">{pos.net_fee_amount.toLocaleString()} BDT</td>
                    <td className={`py-2.5 font-bold ${isCreditor ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {pos.net_settlement_amount.toLocaleString()} BDT
                    </td>
                    <td className="py-2.5">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${isCreditor ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'}`}>
                        {isCreditor ? 'RECEIVES FROM SWITCH' : 'MUST PAY SWITCH'}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* TAB 3: SCENARIOS */}
      {tab === 'SCENARIOS' && (
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 space-y-4">
          <div className="flex justify-between items-center">
            <div>
              <h2 className="text-sm font-bold">Automated Clearing Regression Test Suite</h2>
              <p className="text-xs text-slate-500">
                Dispatches a batch of multi-bank transactions across xBank, yBank, and zBank to test clearing, interchange fee splits, and reconciliation
              </p>
            </div>
            <button
              onClick={handleRunScenarios}
              className="flex items-center gap-1.5 bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-lg text-xs font-semibold"
            >
              <Play size={14} /> Run Multi-Bank Settlement Batch
            </button>
          </div>

          {scenarioResult && (
            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono space-y-2">
              <div className="text-emerald-400 font-bold flex items-center gap-1.5">
                <CheckCircle2 size={16} /> Batch Scenario Execution Completed
              </div>
              <div>Dispatched: <strong className="text-white">{scenarioResult.transactions_generated} transactions</strong></div>
              <div>Approved: <strong className="text-emerald-400">{scenarioResult.approved_count}</strong> · Declined: <strong className="text-rose-400">{scenarioResult.declined_count}</strong></div>
              <div className="text-slate-400 pt-1 border-t border-slate-800">
                Transactions generated across multiple banks. Now click "Execute Daily Settlement Cutover" above to clear them.
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
