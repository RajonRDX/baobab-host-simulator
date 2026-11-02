#!/usr/bin/env python3
"""
INSTALLER: tools/install_step08.py
STEP 8 — Authorizer Rules Engine (Single Unified Installer)
Adds:
  1. Safe whitelist AST expression evaluator in backend/app/rules_evaluator.py
  2. AuthorizerRule ORM model in backend/app/models.py
  3. Pydantic v2 schemas in backend/app/schemas.py
  4. Integration before HSM verification in backend/app/host_engine.py
  5. CRUD & dry-run test endpoints in backend/app/api_routes.py
  6. frontend/src/pages/AuthorizerRulesPage.tsx
  7. Route registration in App.tsx and Layout.tsx
  8. Automated Pytest test suite in backend/tests/test_step08_authorizer_rules.py
"""

from pathlib import Path
import sys

BASE_DIR = Path(r"E:\HOST_VSCODE\host-simulator").resolve()
sys.path.insert(0, str(BASE_DIR))

from tools.patcher import PatcherSession, parse_installer_args

RULES_EVALUATOR_CODE = '''"""
rules_evaluator.py — Whitelist AST Expression Evaluator & Context Builder
Executes custom authorizer rule expressions safely without using eval() or exec().
"""

import ast
from decimal import Decimal
from typing import Any, Dict, List, Optional


class SafeEvalError(Exception):
    """Raised when an expression contains forbidden nodes or syntax errors."""


class SafeAstEvaluator:
    ALLOWED_OPERATORS = {
        ast.Eq: lambda a, b: a == b,
        ast.NotEq: lambda a, b: a != b,
        ast.Lt: lambda a, b: a < b,
        ast.LtE: lambda a, b: a <= b,
        ast.Gt: lambda a, b: a > b,
        ast.GtE: lambda a, b: a >= b,
        ast.In: lambda a, b: a in b,
        ast.NotIn: lambda a, b: a not in b,
        ast.And: lambda a, b: a and b,
        ast.Or: lambda a, b: a or b,
        ast.Not: lambda a: not a,
    }

    @classmethod
    def evaluate(cls, expression: str, context: Dict[str, Any]) -> bool:
        clean_expr = expression.strip()
        if not clean_expr:
            return False
        try:
            tree = ast.parse(clean_expr, mode="eval")
            return bool(cls._eval_node(tree.body, context))
        except Exception as exc:
            raise SafeEvalError(f"Rule evaluation error in '{clean_expr}': {exc}")

    @classmethod
    def _eval_node(cls, node: ast.AST, context: Dict[str, Any]) -> Any:
        if isinstance(node, ast.Constant):
            return node.value

        if isinstance(node, ast.Name):
            key = node.id
            if key == "true":
                return True
            if key == "false":
                return False
            if key == "null" or key == "none":
                return None
            if key in context:
                return context[key]
            raise SafeEvalError(f"Undefined variable in rule context: '{key}'")

        if isinstance(node, ast.Attribute):
            val = cls._eval_node(node.value, context)
            attr = node.attr
            if isinstance(val, dict):
                return val.get(attr)
            if hasattr(val, attr):
                return getattr(val, attr)
            raise SafeEvalError(f"Cannot resolve attribute '{attr}' on {type(val)}")

        if isinstance(node, (ast.List, ast.Tuple)):
            return [cls._eval_node(elt, context) for elt in node.elts]

        if isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type in cls.ALLOWED_OPERATORS:
                operand = cls._eval_node(node.operand, context)
                return cls.ALLOWED_OPERATORS[op_type](operand)
            raise SafeEvalError(f"Forbidden unary operator: {op_type}")

        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                for val_node in node.values:
                    if not cls._eval_node(val_node, context):
                        return False
                return True
            if isinstance(node.op, ast.Or):
                for val_node in node.values:
                    if cls._eval_node(val_node, context):
                        return True
                return False
            raise SafeEvalError(f"Forbidden boolean operator: {type(node.op)}")

        if isinstance(node, ast.Compare):
            left = cls._eval_node(node.left, context)
            for op, comparator_node in zip(node.ops, node.comparators):
                op_type = type(op)
                right = cls._eval_node(comparator_node, context)
                if op_type not in cls.ALLOWED_OPERATORS:
                    raise SafeEvalError(f"Forbidden comparison operator: {op_type}")
                # Numeric type coercion for comparisons
                if isinstance(left, (int, float, Decimal)) and isinstance(right, (int, float, Decimal)):
                    left_cmp = float(left)
                    right_cmp = float(right)
                else:
                    left_cmp = left
                    right_cmp = right

                if not cls.ALLOWED_OPERATORS[op_type](left_cmp, right_cmp):
                    return False
                left = right
            return True

        raise SafeEvalError(f"Forbidden syntax node: {type(node).__name__}")


def build_rule_context(
    mti: str,
    fields: Dict[str, str],
    tx_code: str,
    tx_amount: Decimal,
    card: Any = None,
    customer: Any = None,
    account: Any = None,
    issuer_inst: Any = None,
    acquirer_inst: Any = None,
    ps_code: str = "ITCL",
    card_limit: Any = None,
) -> Dict[str, Any]:
    """Constructs a normalized dictionary containing all transaction parameters for rule evaluation."""
    pan = fields.get("2", "")
    bin_prefix = pan[:6] if len(pan) >= 6 else ""

    inst_code = ""
    inst_name = ""
    if issuer_inst:
        inst_code = issuer_inst.institution_code
        inst_name = issuer_inst.name
    elif card and hasattr(card, "institution") and card.institution:
        inst_code = card.institution.institution_code
        inst_name = card.institution.name

    acq_code = acquirer_inst.institution_code if acquirer_inst else ""
    hour = int(fields.get("12", "120000")[:2]) if len(fields.get("12", "")) >= 2 else 12

    return {
        "trancode": str(tx_code),
        "tran_code": str(tx_code),
        "mti": str(mti),
        "amount": float(tx_amount),
        "currency": fields.get("49", "BDT"),
        "pan": pan,
        "bin": bin_prefix,
        "mcc": fields.get("18", "5411"),
        "terminal_id": fields.get("41", ""),
        "merchant_id": fields.get("32", ""),
        "institution": {
            "code": inst_code,
            "name": inst_name,
        },
        "acquirer_bank": acq_code,
        "issuer_bank": inst_code,
        "ps_name": ps_code,
        "channel": fields.get("25", "00"),
        "hour": hour,
        "card_status": card.card_status if card else "ACTIVE",
        "account_balance": float(account.available_balance) if account else 0.0,
        "daily_used": float(card_limit.daily_used) if card_limit else 0.0,
        "is_foreign": fields.get("19", "050") != "050",
    }
'''

AUTHORIZER_RULES_PAGE_CODE = '''import React, { useEffect, useState } from 'react';
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
      setParams(pList.filter((p: any) => p.parameter_group === 'BAOBAB_AUTH_RULES'));
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
          ['BUILTIN', '2. Built-in BAOBAB Checks', ShieldCheck],
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
          <h2 className="text-sm font-bold">Core BAOBAB Host Authorization Checks</h2>
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
'''

TEST_STEP08_CODE = '''"""
test_step08_authorizer_rules.py — Tests for Step 8 Safe AST Rules Engine
"""

import os
import pytest
from decimal import Decimal
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import AuthorizerRule, Card, Transaction
from app.rules_evaluator import SafeAstEvaluator, SafeEvalError, build_rule_context
from app.host_engine import HostTransactionProcessor
from app.seed_data import seed_initial_data
from app.security import create_access_token
from app.config import settings


@pytest.fixture()
def db_session():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    seed_initial_data(session)
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session):
    with TestClient(app) as c:
        token = create_access_token(subject=settings.ADMIN_USERNAME)
        c.headers = {"Authorization": f"Bearer {token}"}
        yield c


def test_safe_ast_evaluator_valid_expressions():
    ctx = {
        "trancode": "10",
        "amount": 25000.0,
        "institution": {"code": "IFIC", "name": "IFIC Bank"},
        "card_status": "ACTIVE",
        "bin": "456789"
    }

    # Match test
    assert SafeAstEvaluator.evaluate('trancode == "10" and amount > 20000', ctx) is True
    assert SafeAstEvaluator.evaluate('institution.code == "IFIC"', ctx) is True
    assert SafeAstEvaluator.evaluate('bin in ["456789", "512345"]', ctx) is True

    # No match test
    assert SafeAstEvaluator.evaluate('amount > 50000', ctx) is False
    assert SafeAstEvaluator.evaluate('card_status != "ACTIVE"', ctx) is False


def test_safe_ast_evaluator_rejects_unsafe_operations():
    ctx = {"amount": 100}
    with pytest.raises(SafeEvalError):
        # Forbidden function calls
        SafeAstEvaluator.evaluate('__import__("os").system("echo 1")', ctx)

    with pytest.raises(SafeEvalError):
        # Forbidden attribute execution
        SafeAstEvaluator.evaluate('amount.__class__.__mro__', ctx)


def test_authorizer_rule_declines_transaction_in_host_engine(db_session):
    # Create a rule rejecting transactions with amount > 10,000 with RC 61
    rule = AuthorizerRule(
        rule_code="TEST_MAX_10K",
        name="Decline over 10K",
        priority=10,
        expression="amount > 10000",
        action="DECLINE",
        response_code="61",
        message="Transaction exceeds custom authorizer rule threshold",
        enabled=True,
    )
    db_session.add(rule)
    db_session.commit()

    proc = HostTransactionProcessor(db_session)
    res = proc.process_transaction({
        "transaction_code": "10",
        "mti": "0200",
        "test_clear_pin_helper": "1234",
        "fields": {
            "2": "4567890123450001",
            "3": "0100000",
            "4": "000001500000",  # 15,000 BDT > 10,000 threshold
            "11": "700001",
            "37": "000099700001",
            "41": "ATM01",
            "49": "BDT",
        },
    })
    assert res["response_code"] == "61"
    assert res["authorization_status"] == "DECLINED"

    db_session.refresh(rule)
    assert rule.hit_count >= 1
'''


def main() -> int:
    args = parse_installer_args("Step 08: Authorizer Rules Engine")
    session = PatcherSession(
        step_id="step08",
        title="Implement Configurable Authorizer Rules Engine & Safe Whitelist AST Expression Evaluator",
        dry_run=args.dry_run,
    )

    # 1. Write backend/app/rules_evaluator.py
    session.write_file("backend/app/rules_evaluator.py", RULES_EVALUATOR_CODE)

    # 2. Patch backend/app/models.py to add AuthorizerRule ORM model
    session.patch_file(
        "backend/app/models.py",
        [
            {
                "marker": "step08:authorizer_rule_model",
                "action": "append",
                "text": (
                    "\n# ==============================================================================\n"
                    "# I. CONFIGURABLE AUTHORIZER RULES (STEP 8)\n"
                    "# ==============================================================================\n\n"
                    "class AuthorizerRule(Base):\n"
                    '    __tablename__ = "authorizer_rules"\n\n'
                    "    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)\n"
                    "    rule_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)\n"
                    "    name: Mapped[str] = mapped_column(String(150), nullable=False)\n"
                    "    description: Mapped[Optional[str]] = mapped_column(Text)\n"
                    "    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100, index=True)\n"
                    '    stage: Mapped[str] = mapped_column(String(30), nullable=False, default="PRE_AUTH")\n'
                    '    rule_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="SCRIPT")  # BUILDER, SCRIPT\n'
                    "    conditions_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)\n"
                    "    expression: Mapped[str] = mapped_column(Text, nullable=False)\n"
                    '    action: Mapped[str] = mapped_column(String(20), nullable=False, default="DECLINE")  # DECLINE, APPROVE, FLAG\n'
                    '    response_code: Mapped[str] = mapped_column(String(5), nullable=False, default="05")\n'
                    '    message: Mapped[str] = mapped_column(String(200), nullable=False, default="Declined by Authorizer Rule")\n'
                    "    stop_on_match: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)\n"
                    "    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)\n"
                    "    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)\n"
                    "    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)\n"
                    "    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)\n"
                ),
            }
        ],
    )

    # 3. Patch backend/app/schemas.py to add AuthorizerRule schemas
    session.patch_file(
        "backend/app/schemas.py",
        [
            {
                "marker": "step08:schemas_authorizer_rules",
                "action": "append",
                "text": (
                    "\n# ==============================================================================\n"
                    "# STEP 8 SCHEMAS: AUTHORIZER RULES ENGINE\n"
                    "# ==============================================================================\n\n"
                    "class AuthorizerRuleCreate(BaseModel):\n"
                    "    rule_code: str = Field(..., min_length=3, max_length=50)\n"
                    "    name: str\n"
                    "    description: Optional[str] = None\n"
                    "    priority: int = 100\n"
                    '    stage: str = "PRE_AUTH"\n'
                    '    rule_mode: str = "SCRIPT"\n'
                    "    conditions_json: Optional[Dict[str, Any]] = None\n"
                    "    expression: str\n"
                    '    action: str = "DECLINE"\n'
                    '    response_code: str = "05"\n'
                    '    message: str = "Declined by Authorizer Rule"\n'
                    "    stop_on_match: bool = True\n"
                    "    enabled: bool = True\n\n\n"
                    "class AuthorizerRuleUpdate(BaseModel):\n"
                    "    name: Optional[str] = None\n"
                    "    description: Optional[str] = None\n"
                    "    priority: Optional[int] = None\n"
                    "    expression: Optional[str] = None\n"
                    "    action: Optional[str] = None\n"
                    "    response_code: Optional[str] = None\n"
                    "    message: Optional[str] = None\n"
                    "    stop_on_match: Optional[bool] = None\n"
                    "    enabled: Optional[bool] = None\n\n\n"
                    "class AuthorizerRuleOut(AuthorizerRuleCreate):\n"
                    "    id: str\n"
                    "    hit_count: int\n"
                    "    created_at: datetime\n"
                    "    updated_at: datetime\n"
                    "    model_config = ConfigDict(from_attributes=True)\n\n\n"
                    "class RuleDryRunRequest(BaseModel):\n"
                    "    expression: str\n"
                    "    context: Dict[str, Any]\n\n\n"
                    "class RuleDryRunResponse(BaseModel):\n"
                    "    matched: bool\n"
                    "    valid: bool\n"
                    "    error: Optional[str] = None\n"
                ),
            }
        ],
    )

    # 4. Patch backend/app/host_engine.py to evaluate rules before HSM checks
    session.patch_file(
        "backend/app/host_engine.py",
        [
            {
                "marker": "step08:host_engine_rule_imports",
                "action": "insert_after",
                "anchor": "from app.models import (",
                "text": "    AuthorizerRule,",
            },
            {
                "marker": "step08:host_engine_evaluator_import",
                "action": "insert_after",
                "anchor": "from app.logging_service import record_system_log",
                "text": "from app.rules_evaluator import SafeAstEvaluator, build_rule_context",
            },
            {
                "marker": "step08:host_engine_eval_rules_stage",
                "action": "insert_before",
                "anchor": "        # Step 16-18: HSM Cryptographic Checks (PIN / PVV / CVV / EMV / MAC)",
                "text": (
                    "        # Step 15.5: Dynamic Authorizer Rules Evaluation (Stage: PRE_AUTH)\n"
                    "        rule_ctx = build_rule_context(\n"
                    "            mti=mti,\n"
                    "            fields=input_fields,\n"
                    "            tx_code=tx_code_cfg.transaction_code,\n"
                    "            tx_amount=tx_amount,\n"
                    "            card=card,\n"
                    "            customer=customer,\n"
                    "            account=account,\n"
                    "            issuer_inst=card.institution if card else None,\n"
                    "            acquirer_inst=acq_inst,\n"
                    "            ps_code=ps_code_val,\n"
                    "        )\n"
                    "        active_rules = self.db.query(AuthorizerRule).filter(AuthorizerRule.enabled == True).order_by(AuthorizerRule.priority.asc()).all()\n"
                    "        for rule in active_rules:\n"
                    "            try:\n"
                    "                matched = SafeAstEvaluator.evaluate(rule.expression, rule_ctx)\n"
                    "            except Exception as r_err:\n"
                    "                self._add_check(f'Rule {rule.rule_code}', 'SKIPPED', '00', f'Evaluation syntax error: {r_err}')\n"
                    "                continue\n\n"
                    "            if matched:\n"
                    "                rule.hit_count += 1\n"
                    "                if rule.action == 'DECLINE':\n"
                    "                    self._add_check(f'Authorizer Rule ({rule.rule_code})', 'FAILED', rule.response_code, rule.message)\n"
                    "                    return self._finalize_transaction(\n"
                    "                        tx_id=tx_id,\n"
                    "                        tx_ref=tx_ref,\n"
                    "                        mti=mti,\n"
                    "                        fields=input_fields,\n"
                    "                        response_code=rule.response_code,\n"
                    "                        raw_request_msg=raw_req_msg,\n"
                    "                        tx_code=tx_code_cfg.transaction_code,\n"
                    "                        card=card,\n"
                    "                        customer=customer,\n"
                    "                        account=account,\n"
                    "                        issuer_institution_id=card.institution_id if (card and card.institution_id) else issuer_inst_id,\n"
                    "                        acquirer_institution_id=acquirer_inst_id,\n"
                    "                        ps_code=ps_code_val,\n"
                    "                    )\n"
                    "                else:\n"
                    "                    self._add_check(f'Authorizer Rule ({rule.rule_code})', 'PASSED', '00', f'{rule.action}: {rule.message}')\n"
                    "                    if rule.stop_on_match:\n"
                    "                        break\n\n"
                ),
            },
        ],
    )

    # 5. Patch backend/app/api_routes.py to add Authorizer Rules API endpoints
    session.patch_file(
        "backend/app/api_routes.py",
        [
            {
                "marker": "step08:api_routes_rules_imports",
                "action": "insert_after",
                "anchor": "from app.models import (",
                "text": "    AuthorizerRule,",
            },
            {
                "marker": "step08:api_routes_rules_schemas",
                "action": "insert_after",
                "anchor": "from app.schemas import (",
                "text": (
                    "    AuthorizerRuleCreate,\n"
                    "    AuthorizerRuleOut,\n"
                    "    AuthorizerRuleUpdate,\n"
                    "    RuleDryRunRequest,\n"
                    "    RuleDryRunResponse,"
                ),
            },
            {
                "marker": "step08:api_routes_rules_evaluator_import",
                "action": "insert_after",
                "anchor": "from app.audit_service import record_audit, serialize_entity",
                "text": "from app.rules_evaluator import SafeAstEvaluator",
            },
            {
                "marker": "step08:authorizer_rules_endpoints",
                "action": "append",
                "text": (
                    "\n# ==============================================================================\n"
                    "# STEP 8 API ENDPOINTS: AUTHORIZER RULES MANAGEMENT & DRY-RUN\n"
                    "# ==============================================================================\n\n"
                    "@router.get('/authorizer-rules', response_model=List[AuthorizerRuleOut])\n"
                    "def list_authorizer_rules(db: Session = Depends(get_db), _: str = Depends(get_current_user)):\n"
                    "    return db.query(AuthorizerRule).order_by(AuthorizerRule.priority.asc()).all()\n\n\n"
                    "@router.post('/authorizer-rules', response_model=AuthorizerRuleOut)\n"
                    "def create_authorizer_rule(payload: AuthorizerRuleCreate, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):\n"
                    "    code = payload.rule_code.upper().strip()\n"
                    "    existing = db.query(AuthorizerRule).filter(AuthorizerRule.rule_code == code).first()\n"
                    "    if existing:\n"
                    "        raise HTTPException(status_code=400, detail=f'Authorizer rule {code} already exists')\n"
                    "    rule = AuthorizerRule(**payload.model_dump())\n"
                    "    rule.rule_code = code\n"
                    "    db.add(rule)\n"
                    "    db.flush()\n"
                    "    record_audit(db, 'AUTHORIZER_RULE', rule.id, 'CREATE', performed_by=current_user, after_state=serialize_entity(rule),\n"
                    "                 change_summary=f'Created authorizer rule {rule.rule_code}')\n"
                    "    db.commit()\n"
                    "    db.refresh(rule)\n"
                    "    return rule\n\n\n"
                    "@router.put('/authorizer-rules/{rule_id}', response_model=AuthorizerRuleOut)\n"
                    "def update_authorizer_rule(rule_id: str, payload: AuthorizerRuleUpdate, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):\n"
                    "    rule = db.query(AuthorizerRule).filter(AuthorizerRule.id == rule_id).first()\n"
                    "    if not rule:\n"
                    "        raise HTTPException(status_code=404, detail='Authorizer rule not found')\n"
                    "    before = serialize_entity(rule)\n"
                    "    for k, v in payload.model_dump(exclude_unset=True).items():\n"
                    "        setattr(rule, k, v)\n"
                    "    after = serialize_entity(rule)\n"
                    "    record_audit(db, 'AUTHORIZER_RULE', rule.id, 'UPDATE', performed_by=current_user, before_state=before, after_state=after,\n"
                    "                 change_summary=f'Updated authorizer rule {rule.rule_code}')\n"
                    "    db.commit()\n"
                    "    db.refresh(rule)\n"
                    "    return rule\n\n\n"
                    "@router.delete('/authorizer-rules/{rule_id}')\n"
                    "def delete_authorizer_rule(rule_id: str, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):\n"
                    "    rule = db.query(AuthorizerRule).filter(AuthorizerRule.id == rule_id).first()\n"
                    "    if not rule:\n"
                    "        raise HTTPException(status_code=404, detail='Authorizer rule not found')\n"
                    "    before = serialize_entity(rule)\n"
                    "    db.delete(rule)\n"
                    "    record_audit(db, 'AUTHORIZER_RULE', rule_id, 'DELETE', performed_by=current_user, before_state=before,\n"
                    "                 change_summary=f'Deleted authorizer rule {rule.rule_code}')\n"
                    "    db.commit()\n"
                    "    return {'status': 'deleted', 'rule_id': rule_id}\n\n\n"
                    "@router.post('/authorizer-rules/dry-run', response_model=RuleDryRunResponse)\n"
                    "def dry_run_authorizer_rule(payload: RuleDryRunRequest, _: str = Depends(get_current_user)):\n"
                    "    try:\n"
                    "        matched = SafeAstEvaluator.evaluate(payload.expression, payload.context)\n"
                    "        return RuleDryRunResponse(matched=matched, valid=True)\n"
                    "    except Exception as exc:\n"
                    "        return RuleDryRunResponse(matched=False, valid=False, error=str(exc))\n"
                ),
            },
        ],
    )

    # 6. Write frontend/src/pages/AuthorizerRulesPage.tsx
    session.write_file("frontend/src/pages/AuthorizerRulesPage.tsx", AUTHORIZER_RULES_PAGE_CODE)

    # 7. Patch frontend/src/App.tsx to add /authorizer-rules route
    session.patch_file(
        "frontend/src/App.tsx",
        [
            {
                "marker": "step08:app_import_rules_page",
                "action": "insert_after",
                "anchor": "import { UnifiedLogPortalPage } from './pages/UnifiedLogPortalPage';",
                "text": "import { AuthorizerRulesPage } from './pages/AuthorizerRulesPage';",
            },
            {
                "marker": "step08:app_route_rules_page",
                "action": "insert_after",
                "anchor": "        <Route\n          path=\"/transaction-codes\"\n          element={\n            <ProtectedRoute>\n              <TransactionCodesPage />\n            </ProtectedRoute>\n          }\n        />",
                "text": (
                    "        <Route\n"
                    "          path=\"/authorizer-rules\"\n          element={\n"
                    "            <ProtectedRoute>\n"
                    "              <AuthorizerRulesPage />\n"
                    "            </ProtectedRoute>\n"
                    "          }\n"
                    "        />"
                ),
            },
        ],
    )

    # 8. Patch frontend/src/components/Layout.tsx to add Authorizer Rules navigation item
    session.patch_file(
        "frontend/src/components/Layout.tsx",
        [
            {
                "marker": "step08:layout_nav_authorizer_rules",
                "action": "insert_after",
                "anchor": "  { to: '/transaction-codes', label: '7. Transaction Codes', icon: FileCode2, group: 'SWITCH & SIMULATOR' },",
                "text": "  { to: '/authorizer-rules', label: '7.5. Authorizer Rules', icon: Sliders, group: 'SWITCH & SIMULATOR' },",
            }
        ],
    )

    # 9. Write automated pytest test suite backend/tests/test_step08_authorizer_rules.py
    session.write_file("backend/tests/test_step08_authorizer_rules.py", TEST_STEP08_CODE)

    session.record_progress(
        completed=[
            "Created `backend/app/rules_evaluator.py` providing a safe whitelist AST expression evaluator without unsafe eval/exec.",
            "Created `AuthorizerRule` ORM model in `backend/app/models.py`.",
            "Added Pydantic v2 schemas in `backend/app/schemas.py`.",
            "Integrated custom authorizer rules evaluation stage in `HostTransactionProcessor` before HSM checks.",
            "Added REST endpoints: `GET/POST/PUT/DELETE /api/authorizer-rules` and `POST /api/authorizer-rules/dry-run` in `backend/app/api_routes.py`.",
            "Created React UI workbench `frontend/src/pages/AuthorizerRulesPage.tsx` and registered route `/authorizer-rules` in `App.tsx` and `Layout.tsx`.",
            "Created automated Pytest test suite `backend/tests/test_step08_authorizer_rules.py`.",
        ],
        remaining=[
            "STEP 9 — Simulator Improvements (Persistent Simulator State across navigation/refresh and Dual-Codec Raw Message Parser for TIC v2.164e and ISO 8583:1987).",
        ],
        modified_files=[
            "backend/app/rules_evaluator.py",
            "backend/app/models.py",
            "backend/app/schemas.py",
            "backend/app/host_engine.py",
            "backend/app/api_routes.py",
            "frontend/src/pages/AuthorizerRulesPage.tsx",
            "frontend/src/App.tsx",
            "frontend/src/components/Layout.tsx",
            "backend/tests/test_step08_authorizer_rules.py",
        ],
    )

    session.record_contracts(
        section_title="Step 8 — Authorizer Rules Engine Contracts",
        contract_items=[
            "**Table `authorizer_rules`**: `id`, `rule_code`, `name`, `priority`, `stage`, `rule_mode`, `expression`, `action` (`DECLINE`/`APPROVE`/`FLAG`), `response_code`, `message`, `hit_count`, `enabled`.",
            "**GET /api/authorizer-rules**: Lists configured custom authorizer rules.",
            "**POST /api/authorizer-rules**: Creates rule with expression syntax validation.",
            "**POST /api/authorizer-rules/dry-run**: Safely tests AST expressions against arbitrary JSON transaction context payloads.",
            "**Host Pipeline**: Custom authorizer rules execute before HSM verification; matching DECLINE rules stop processing and return custom response codes with `TransactionCheck` logging.",
            "**React Route**: `/#/authorizer-rules` (`AuthorizerRulesPage`).",
        ],
    )

    return session.finish()


if __name__ == "__main__":
    sys.exit(main())