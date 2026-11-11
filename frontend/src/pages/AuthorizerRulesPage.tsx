import React, { useEffect, useState } from 'react';
import { Sliders, ShieldCheck, Code2, Play, Plus, Trash2, CheckCircle2, AlertTriangle, RefreshCw } from 'lucide-react';
import { apiFetch } from '../api';

export const AuthorizerRulesPage: React.FC = () => {
  const [tab, setTab] = useState<'BUILTIN' | 'BUILDER' | 'CUSTOM'>('CUSTOM');
  const [rules, setRules] = useState<any[]>([]);
  const [params, setParams] = useState<any[]>([]);
  const [selectedRule, setSelectedRule] = useState<any | null>(null);
  const [testExpression, setTestExpression] = useState('trancode == "10" and amount > 50000');
  const [testContext, setTestContext] = useState(
    JSON.stringify({ trancode: "10", amount: 65000, institution: { code: "IFIC" }, card_status: "ACTIVE" }, null, 2)
  );
  const [testResult, setTestResult] = useState<any | null>(null);
  const [msg, setMsg] = useState('');

  // New rule form
  const [form, setForm] = useState({
    rule_code: 'RULE_HIGH_VAL',
    name: 'Decline Transactions Over 50,000 BDT',
    description: 'Fraud threshold rule rejecting high single-ticket debit amounts',
    priority: 50,
    rule_mode: 'SCRIPT',
    expression: 'amount > 50000',
    action: 'DECLINE',
    response_code: '61',
    message: 'High value transaction flagged by Host Authorizer Rule',
    stop_on_match: true,
    enabled: true,
  });

  const loadData = async () => {
    try {
      const [rList, pList] = await Promise.all([
        apiFetch('/authorizer-rules'),
        apiFetch('/host-parameters'),
      ]);
      setRules(rList);
      setParams(pList.filter((p: any) => p.parameter_group === 'RAJON_AUTH_RULES'));
      if (rList.length > 0 && !selectedRule) setSelectedRule(rList[0]);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleCreateRule = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await apiFetch('/authorizer-rules', {
        method: 'POST',
        body: JSON.stringify(form),
      });
      setMsg(`Successfully created rule ${form.rule_code}`);
      loadData();
    } catch (err: any) {
      setMsg(`Error: ${err.message}`);
    }
  };

  const handleDeleteRule = async (id: string) => {
    if (!confirm('Delete this authorizer rule?')) return;
    try {
      await apiFetch(`/authorizer-rules/${id}`, { method: 'DELETE' });
      setMsg('Rule deleted.');
      loadData();
    } catch (err: any) {
      alert(err.message);
    }
  };

  const handleTestExpression = async () => {
    try {
      let parsedContext = {};
      try {
        parsedContext = JSON.parse(testContext);
      } catch {
        alert('Invalid JSON in Test Context');
        return;
      }
      const res = await apiFetch('/authorizer-rules/dry-run', {
        method: 'POST',
        body: JSON.stringify({ expression: testExpression, context: parsedContext }),
      });
      setTestResult(res);
    } catch (err: any) {
      alert(err.message);
    }
  };

  const toggleParam = async (p: any) => {
    const current = p.parameter_value?.enabled ?? p.active;
    const nextVal = { ...p.parameter_value, enabled: !current };
    await apiFetch(`/host-parameters/${p.id}`, {
      method: 'PUT',
      body: JSON.stringify({ parameter_value: nextVal, active: !current }),
    });
    loadData();
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold">Host Authorizer Rules Engine</h1>
          <p className="text-xs text-slate-500">
            Define dynamic pre-auth verification and fraud checks with safe AST expression evaluation (eval/exec-free)
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono px-2.5 py-1 rounded bg-emerald-500/10 text-emerald-500 border border-emerald-500/20 font-bold">
            Execution Stage: PRE_CRYPTO
          </span>
        </div>
      </div>

      {msg && (
        <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs font-mono">
          {msg}
        </div>
      )}

      {/* Tabs */}
      <div className="flex flex-wrap gap-2 border-b border-slate-200 dark:border-slate-800 pb-2">
        {[
          ['CUSTOM', '1. Custom Expression Rules & Test Bench', Code2],
          ['BUILTIN', '2. Built-in RAJON Checks', ShieldCheck],
          ['BUILDER', '3. Visual Condition Builder', Sliders],
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

      {/* TAB 1: CUSTOM RULES & TEST BENCH */}
      {tab === 'CUSTOM' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* Rules List (Left 6 cols) */}
            <div className="lg:col-span-6 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 space-y-4">
              <h2 className="text-sm font-bold flex justify-between items-center">
                <span>Configured Authorizer Rules</span>
                <span className="text-xs font-mono text-slate-400">Total: {rules.length}</span>
              </h2>
              <div className="space-y-2 max-h-80 overflow-y-auto">
                {rules.map((r) => (
                  <div
                    key={r.id}
                    onClick={() => { setSelectedRule(r); setTestExpression(r.expression); }}
                    className={`p-3 rounded-lg border text-xs font-mono cursor-pointer transition ${
                      selectedRule?.id === r.id ? 'border-emerald-500 bg-emerald-500/10' : 'border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950'
                    }`}
                  >
                    <div className="flex justify-between items-center">
                      <span className="font-bold text-emerald-400">{r.rule_code} (Priority {r.priority})</span>
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${r.action === 'DECLINE' ? 'bg-rose-500/10 text-rose-400' : 'bg-emerald-500/10 text-emerald-400'}`}>
                        {r.action} (RC {r.response_code})
                      </span>
                    </div>
                    <div className="text-slate-300 font-sans mt-1">{r.name}</div>
                    <div className="text-[11px] text-sky-400 font-mono mt-1 truncate">Expr: {r.expression}</div>
                    <div className="flex justify-between items-center text-[10px] text-slate-500 mt-1 pt-1 border-t border-slate-800">
                      <span>Hits: <strong className="text-amber-400">{r.hit_count}</strong></span>
                      <button onClick={(e) => { e.stopPropagation(); handleDeleteRule(r.id); }} className="text-rose-500 hover:underline">Delete</button>
                    </div>
                  </div>
                ))}
                {rules.length === 0 && (
                  <div className="py-12 text-center text-slate-400 text-xs font-mono">
                    No custom rules configured yet. Create one below.
                  </div>
                )}
              </div>

              {/* Create Rule Form */}
              <form onSubmit={handleCreateRule} className="pt-3 border-t border-slate-200 dark:border-slate-800 space-y-3 text-xs font-mono">
                <div className="font-bold text-sm">Add New Custom Rule</div>
                <div className="grid grid-cols-2 gap-2">
                  <input
                    value={form.rule_code}
                    onChange={(e) => setForm({ ...form, rule_code: e.target.value })}
                    placeholder="Rule Code (e.g. RULE_BLOCK_POS)"
                    className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5"
                    required
                  />
                  <input
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                    placeholder="Rule Name"
                    className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5"
                    required
                  />
                </div>
                <textarea
                  rows={2}
                  value={form.expression}
                  onChange={(e) => setForm({ ...form, expression: e.target.value })}
                  placeholder="Safe Expression: trancode == '10' and amount > 50000"
                  className="w-full bg-slate-950 text-emerald-300 border border-slate-800 rounded p-2 text-xs font-mono"
                  required
                />
                <div className="grid grid-cols-3 gap-2">
                  <select
                    value={form.action}
                    onChange={(e) => setForm({ ...form, action: e.target.value })}
                    className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2 py-1.5"
                  >
                    <option value="DECLINE">DECLINE</option>
                    <option value="APPROVE">APPROVE</option>
                    <option value="FLAG">FLAG</option>
                  </select>
                  <input
                    value={form.response_code}
                    onChange={(e) => setForm({ ...form, response_code: e.target.value })}
                    placeholder="Response Code (e.g. 61)"
                    maxLength={2}
                    className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2 py-1.5"
                  />
                  <input
                    type="number"
                    value={form.priority}
                    onChange={(e) => setForm({ ...form, priority: parseInt(e.target.value) || 100 })}
                    placeholder="Priority (e.g. 50)"
                    className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2 py-1.5"
                  />
                </div>
                <button type="submit" className="w-full bg-emerald-600 hover:bg-emerald-500 text-white rounded py-2 font-semibold">
                  + Save Authorizer Rule
                </button>
              </form>
            </div>

            {/* Test Bench (Right 6 cols) */}
            <div className="lg:col-span-6 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 space-y-4">
              <h2 className="text-sm font-bold flex items-center gap-2">
                <Play size={15} className="text-emerald-500" /> Expression Dry-Run Test Bench
              </h2>
              <div className="space-y-3 text-xs font-mono">
                <div>
                  <label className="block text-slate-400 mb-1">Target Expression</label>
                  <input
                    value={testExpression}
                    onChange={(e) => setTestExpression(e.target.value)}
                    className="w-full bg-slate-950 text-emerald-300 border border-slate-800 rounded px-3 py-2"
                  />
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">Simulation Payload (JSON Context)</label>
                  <textarea
                    rows={6}
                    value={testContext}
                    onChange={(e) => setTestContext(e.target.value)}
                    className="w-full bg-slate-950 text-sky-300 border border-slate-800 rounded p-2.5"
                  />
                </div>
                <button
                  onClick={handleTestExpression}
                  className="bg-sky-600 hover:bg-sky-500 text-white px-4 py-2 rounded-lg font-semibold flex items-center gap-1.5"
                >
                  <Play size={13} /> Run AST Dry-Run Evaluation
                </button>

                {testResult && (
                  <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-1.5 text-xs font-mono">
                    <div className="flex justify-between items-center border-b border-slate-800 pb-1.5">
                      <span className="text-slate-400">Evaluation Result:</span>
                      <span className={`px-2 py-0.5 rounded text-[11px] font-bold ${testResult.matched ? 'bg-rose-500/10 text-rose-400' : 'bg-emerald-500/10 text-emerald-400'}`}>
                        {testResult.matched ? 'MATCHED (TRUE)' : 'NOT MATCHED (FALSE)'}
                      </span>
                    </div>
                    <div><span className="text-slate-400">AST Validation:</span> <span className="text-emerald-400 font-bold">{testResult.valid ? 'PASSED (Safe AST Whitelist)' : 'SYNTAX ERROR'}</span></div>
                    {testResult.error && <div className="text-rose-400">Error: {testResult.error}</div>}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: BUILTIN CHECKS */}
      {tab === 'BUILTIN' && (
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 space-y-4">
          <h2 className="text-sm font-bold">Core RAJON Host Authorization Checks</h2>
          <div className="space-y-2 text-xs font-mono">
            {params.map((p) => {
              const enabled = p.parameter_value?.enabled ?? p.active;
              return (
                <div key={p.id} className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 flex justify-between items-center">
                  <div>
                    <div className="font-bold text-emerald-400">{p.parameter_name}</div>
                    <div className="text-slate-400 font-sans text-[11px]">{p.description}</div>
                  </div>
                  <button
                    onClick={() => toggleParam(p)}
                    className={`px-3 py-1 rounded text-xs font-bold ${enabled ? 'bg-emerald-600 text-white' : 'bg-rose-600 text-white'}`}
                  >
                    {enabled ? 'ENABLED' : 'DISABLED'}
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* TAB 3: VISUAL BUILDER */}
      {tab === 'BUILDER' && (
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 space-y-4">
          <h2 className="text-sm font-bold">Visual Condition Rule Builder</h2>
          <p className="text-xs text-slate-500">
            Generate safe AST expressions visually by selecting parameters and conditions.
          </p>
          <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 space-y-3 text-xs font-mono">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
              <select className="bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5">
                <option value="amount">Transaction Amount (amount)</option>
                <option value="trancode">Transaction Code (trancode)</option>
                <option value="institution.code">Bank Code (institution.code)</option>
                <option value="card_status">Card Status (card_status)</option>
              </select>
              <select className="bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5">
                <option value=">">Greater than (&gt;)</option>
                <option value="<">Less than (&lt;)</option>
                <option value="==">Equals (==)</option>
                <option value="!=">Not equal (!=)</option>
              </select>
              <input placeholder="Value (e.g. 50000)" className="bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5" />
            </div>
            <div className="text-[11px] text-slate-400">
              Generated expression: <code className="text-emerald-400 font-bold">amount &gt; 50000</code>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
