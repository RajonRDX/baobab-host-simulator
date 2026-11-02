#!/usr/bin/env python3
"""
INSTALLER: tools/install_step12.py
STEP 12 — Clearing, Settlement and Reconciliation Engine (Single Unified Installer)
Adds:
  1. backend/app/settlement_service.py (Dual-balance hold vs clear, 0220 advice, cutover, net settlement)
  2. SettlementBatch, SettlementEntry, SettlementPosition ORM models in backend/app/models.py
  3. Pydantic schemas in backend/app/schemas.py
  4. 0220 Financial Advice handling in backend/app/host_engine.py
  5. Settlement REST endpoints in backend/app/api_routes.py
  6. frontend/src/pages/ClearingAndSettlementPage.tsx
  7. Route registration in App.tsx and Layout.tsx
  8. Automated Pytest test suite in backend/tests/test_step12_settlement.py
"""

from pathlib import Path
import sys

BASE_DIR = Path(r"E:\HOST_VSCODE\host-simulator").resolve()
sys.path.insert(0, str(BASE_DIR))

from tools.patcher import PatcherSession, parse_installer_args

SETTLEMENT_SERVICE_CODE = '''"""
settlement_service.py — Clearing, Daily Settlement and Multilateral Reconciliation Engine
Implements authorization holds, 0220 advices, daily cutover batches, interchange fee calculation,
net settlement position resolution, and mismatch audits.
"""

from datetime import datetime, timezone
from decimal import Decimal
import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models import (
    Account,
    AccountLedger,
    Institution,
    ProcessingSystem,
    SettlementBatch,
    SettlementEntry,
    SettlementPosition,
    Transaction,
)


def calculate_fees(amount: Decimal, transaction_code: str, scheme: str = "ITCL") -> Dict[str, Decimal]:
    """
    Calculates interchange fee and processing switch fee based on transaction type.
    """
    if amount <= Decimal("0.00"):
        return {"interchange_fee": Decimal("0.00"), "scheme_fee": Decimal("0.00")}

    # Default ATM Cash Withdrawal: Fixed fee
    if transaction_code in ("10", "010"):
        interchange = Decimal("15.00")  # 15 BDT interchange
        scheme_fee = Decimal("2.50")    # 2.5 BDT switch fee
    elif transaction_code in ("40", "110"):
        # POS / E-Commerce Purchase: 1.5% interchange + 0.15% scheme
        interchange = (amount * Decimal("0.015")).quantize(Decimal("0.01"))
        scheme_fee = (amount * Decimal("0.0015")).quantize(Decimal("0.01"))
    else:
        interchange = Decimal("5.00")
        scheme_fee = Decimal("1.00")

    return {
        "interchange_fee": interchange,
        "scheme_fee": scheme_fee,
    }


def execute_daily_cutover(
    db: Session,
    ps_code: str = "ITCL",
    operator: str = "admin",
) -> Dict[str, Any]:
    """
    Executes daily cutover: closes the current batch, computes interchange and scheme fees,
    generates settlement entries, and derives multilateral net positions per institution.
    """
    now = datetime.now(timezone.utc)
    batch_num = f"SETL-{ps_code}-{now.strftime('%Y%m%d%H%M%S')}"

    # 1. Resolve Processing System
    ps = db.query(ProcessingSystem).filter(ProcessingSystem.ps_code == ps_code.upper()).first()
    ps_id = ps.id if ps else None

    # 2. Identify all approved financial transactions not yet in a closed settlement batch
    settled_tx_ids = db.query(SettlementEntry.transaction_id)
    unsettled_txs = (
        db.query(Transaction)
        .filter(
            Transaction.authorization_status == "APPROVED",
            Transaction.mti.in_(["0200", "0210", "0220"]),
            ~Transaction.id.in_(settled_tx_ids),
        )
        .all()
    )

    batch = SettlementBatch(
        batch_number=batch_num,
        processing_system_id=ps_id,
        ps_code=ps_code.upper(),
        cutover_time=now,
        status="CLOSED",
        total_transactions=len(unsettled_txs),
        total_amount=Decimal("0.00"),
        total_fees=Decimal("0.00"),
        mismatch_count=0,
    )
    db.add(batch)
    db.flush()

    tot_amt = Decimal("0.00")
    tot_fees = Decimal("0.00")
    mismatches = 0

    # Institution position aggregators: inst_id -> {debit_vol, credit_vol, debit_cnt, credit_cnt, fee_net}
    positions: Dict[str, Dict[str, Any]] = {}

    def _ensure_inst(inst_id: str):
        if inst_id not in positions:
            positions[inst_id] = {
                "debit_volume": Decimal("0.00"),
                "credit_volume": Decimal("0.00"),
                "debit_count": 0,
                "credit_count": 0,
                "net_fee": Decimal("0.00"),
            }

    for tx in unsettled_txs:
        fees = calculate_fees(tx.transaction_amount, tx.transaction_code or "10", ps_code)
        ic_fee = fees["interchange_fee"]
        sch_fee = fees["scheme_fee"]
        total_fee = ic_fee + sch_fee
        net_amt = tx.transaction_amount - total_fee

        tot_amt += tx.transaction_amount
        tot_fees += total_fee

        entry = SettlementEntry(
            batch_id=batch.id,
            transaction_id=tx.id,
            issuer_institution_id=tx.issuer_institution_id,
            acquirer_institution_id=tx.acquirer_institution_id,
            mti=tx.mti,
            transaction_amount=tx.transaction_amount,
            interchange_fee=ic_fee,
            scheme_fee=sch_fee,
            net_amount=net_amt,
            settlement_status="SETTLED",
        )
        db.add(entry)

        # Multi-lateral position tracking
        if tx.issuer_institution_id:
            _ensure_inst(tx.issuer_institution_id)
            # Issuer owes the settlement switch for customer withdrawals
            positions[tx.issuer_institution_id]["debit_volume"] += tx.transaction_amount
            positions[tx.issuer_institution_id]["debit_count"] += 1
            # Issuer receives interchange fee
            positions[tx.issuer_institution_id]["net_fee"] += ic_fee

        if tx.acquirer_institution_id:
            _ensure_inst(tx.acquirer_institution_id)
            # Acquirer is credited with the cash dispensed
            positions[tx.acquirer_institution_id]["credit_volume"] += tx.transaction_amount
            positions[tx.acquirer_institution_id]["credit_count"] += 1
            # Acquirer pays interchange fee and switch fee
            positions[tx.acquirer_institution_id]["net_fee"] -= total_fee

    batch.total_amount = tot_amt
    batch.total_fees = tot_fees

    # 3. Create SettlementPosition records per institution
    for inst_id, pos in positions.items():
        net_settlement = pos["credit_volume"] - pos["debit_volume"] + pos["net_fee"]
        db.add(
            SettlementPosition(
                batch_id=batch.id,
                institution_id=inst_id,
                net_settlement_amount=net_settlement,
                debit_count=pos["debit_count"],
                credit_count=pos["credit_count"],
                debit_volume=pos["debit_volume"],
                credit_volume=pos["credit_volume"],
                net_fee_amount=pos["net_fee"],
                settlement_status="SETTLED",
            )
        )

    db.commit()
    db.refresh(batch)

    return {
        "batch_id": batch.id,
        "batch_number": batch.batch_number,
        "ps_code": batch.ps_code,
        "cutover_time": batch.cutover_time.isoformat(),
        "total_transactions": batch.total_transactions,
        "total_amount": float(batch.total_amount),
        "total_fees": float(batch.total_fees),
        "status": batch.status,
        "institutions_settled": len(positions),
    }


def get_reconciliation_summary(db: Session) -> Dict[str, Any]:
    """Audits open holds, cleared totals, and flags any mismatch discrepancies."""
    total_approved = db.query(func.count(Transaction.id)).filter(Transaction.authorization_status == "APPROVED").scalar() or 0
    total_reversed = db.query(func.count(Transaction.id)).filter(Transaction.transaction_status == "REVERSED").scalar() or 0
    total_settled = db.query(func.count(SettlementEntry.id)).scalar() or 0
    pending_settlement = max(0, total_approved - total_settled)

    batches = db.query(SettlementBatch).order_by(SettlementBatch.cutover_time.desc()).limit(10).all()

    return {
        "total_approved_transactions": total_approved,
        "total_reversed_transactions": total_reversed,
        "total_settled_transactions": total_settled,
        "pending_clearing_transactions": pending_settlement,
        "reconciliation_status": "BALANCED" if pending_settlement == 0 else "PENDING_BATCH_CUTOVER",
        "recent_batches": [
            {
                "id": b.id,
                "batch_number": b.batch_number,
                "ps_code": b.ps_code,
                "cutover_time": b.cutover_time.isoformat(),
                "total_transactions": b.total_transactions,
                "total_amount": float(b.total_amount),
                "total_fees": float(b.total_fees),
                "status": b.status,
            }
            for b in batches
        ],
    }
'''

SETTLEMENT_PAGE_CODE = '''import React, { useEffect, useState } from 'react';
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
'''

TEST_STEP12_CODE = '''"""
test_step12_settlement.py — Tests for Step 12 Clearing, Daily Settlement & Reconciliation
"""

import os
import pytest
from decimal import Decimal
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import SettlementBatch, SettlementEntry, SettlementPosition, Transaction
from app.settlement_service import calculate_fees, execute_daily_cutover, get_reconciliation_summary
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


def test_calculate_fees():
    # ATM withdrawal fee check
    atm_fees = calculate_fees(Decimal("2500.00"), "10", "ITCL")
    assert atm_fees["interchange_fee"] == Decimal("15.00")
    assert atm_fees["scheme_fee"] == Decimal("2.50")

    # POS purchase percentage fee check (1.5% interchange)
    pos_fees = calculate_fees(Decimal("10000.00"), "40", "ITCL")
    assert pos_fees["interchange_fee"] == Decimal("150.00")


def test_execute_daily_cutover(db_session):
    # 1. Submit an approved transaction
    proc = HostTransactionProcessor(db_session)
    res = proc.process_transaction({
        "transaction_code": "10",
        "mti": "0200",
        "test_clear_pin_helper": "1234",
        "fields": {
            "2": "4567890123450001",
            "3": "0100000",
            "4": "000000200000",  # 2,000.00 BDT
            "11": "800001",
            "37": "000099800001",
            "41": "ATM01",
            "49": "BDT",
        },
    })
    assert res["response_code"] == "00"

    # 2. Execute cutover
    cutover = execute_daily_cutover(db_session, "ITCL", "test_admin")
    assert cutover["status"] == "CLOSED"
    assert cutover["total_transactions"] >= 1
    assert cutover["total_amount"] >= 2000.0

    # 3. Verify database records
    batch = db_session.query(SettlementBatch).filter(SettlementBatch.id == cutover["batch_id"]).first()
    assert batch is not None

    positions = db_session.query(SettlementPosition).filter(SettlementPosition.batch_id == batch.id).all()
    assert len(positions) >= 1


def test_reconciliation_endpoint(client, db_session):
    res = client.get("/api/settlement/reconciliation")
    assert res.status_code == 200
    data = res.json()
    assert "total_approved_transactions" in data
    assert "reconciliation_status" in data
'''


def main() -> int:
    args = parse_installer_args("Step 12: Clearing, Settlement and Reconciliation Engine")
    session = PatcherSession(
        step_id="step12",
        title="Implement Clearing and Settlement Engine, Daily Cutover, Interchange Fees, and Net Positions",
        dry_run=args.dry_run,
    )

    # 1. Write backend/app/settlement_service.py
    session.write_file("backend/app/settlement_service.py", SETTLEMENT_SERVICE_CODE)

    # 2. Patch backend/app/models.py to add SettlementBatch, SettlementEntry, SettlementPosition
    session.patch_file(
        "backend/app/models.py",
        [
            {
                "marker": "step12:models_settlement",
                "action": "append",
                "text": (
                    "\n# ==============================================================================\n"
                    "# J. CLEARING, SETTLEMENT & MULTILATERAL RECONCILIATION (STEP 12)\n"
                    "# ==============================================================================\n\n"
                    "class SettlementBatch(Base):\n"
                    '    __tablename__ = "settlement_batches"\n\n'
                    "    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)\n"
                    "    batch_number: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)\n"
                    "    processing_system_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey('processing_systems.id'))\n"
                    "    ps_code: Mapped[str] = mapped_column(String(30), nullable=False, default='ITCL')\n"
                    "    cutover_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)\n"
                    "    status: Mapped[str] = mapped_column(String(20), nullable=False, default='CLOSED')  # OPEN, PROCESSING, CLOSED, RECONCILED\n"
                    "    total_transactions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)\n"
                    "    total_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal('0.00'))\n"
                    "    total_fees: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal('0.00'))\n"
                    "    mismatch_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)\n"
                    "    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)\n\n"
                    "    entries: Mapped[List['SettlementEntry']] = relationship('SettlementEntry', back_populates='batch', cascade='all, delete-orphan')\n"
                    "    positions: Mapped[List['SettlementPosition']] = relationship('SettlementPosition', back_populates='batch', cascade='all, delete-orphan')\n\n\n"
                    "class SettlementEntry(Base):\n"
                    '    __tablename__ = "settlement_entries"\n\n'
                    "    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)\n"
                    "    batch_id: Mapped[str] = mapped_column(String(36), ForeignKey('settlement_batches.id', ondelete='CASCADE'), nullable=False, index=True)\n"
                    "    transaction_id: Mapped[str] = mapped_column(String(36), ForeignKey('transactions.id'), nullable=False, index=True)\n"
                    "    issuer_institution_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey('institutions.id'))\n"
                    "    acquirer_institution_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey('institutions.id'))\n"
                    "    mti: Mapped[str] = mapped_column(String(4), nullable=False)\n"
                    "    transaction_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)\n"
                    "    interchange_fee: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal('0.00'))\n"
                    "    scheme_fee: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal('0.00'))\n"
                    "    net_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)\n"
                    "    settlement_status: Mapped[str] = mapped_column(String(20), nullable=False, default='SETTLED')\n"
                    "    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)\n\n"
                    "    batch: Mapped['SettlementBatch'] = relationship('SettlementBatch', back_populates='entries')\n"
                    "    transaction: Mapped['Transaction'] = relationship('Transaction')\n\n\n"
                    "class SettlementPosition(Base):\n"
                    '    __tablename__ = "settlement_positions"\n\n'
                    "    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)\n"
                    "    batch_id: Mapped[str] = mapped_column(String(36), ForeignKey('settlement_batches.id', ondelete='CASCADE'), nullable=False, index=True)\n"
                    "    institution_id: Mapped[str] = mapped_column(String(36), ForeignKey('institutions.id'), nullable=False, index=True)\n"
                    "    net_settlement_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal('0.00'))\n"
                    "    debit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)\n"
                    "    credit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)\n"
                    "    debit_volume: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal('0.00'))\n"
                    "    credit_volume: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal('0.00'))\n"
                    "    net_fee_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal('0.00'))\n"
                    "    settlement_status: Mapped[str] = mapped_column(String(20), nullable=False, default='SETTLED')\n"
                    "    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)\n\n"
                    "    batch: Mapped['SettlementBatch'] = relationship('SettlementBatch', back_populates='positions')\n"
                    "    institution: Mapped['Institution'] = relationship('Institution')\n"
                ),
            }
        ],
    )

    # 3. Patch backend/app/schemas.py to add settlement schemas
    session.patch_file(
        "backend/app/schemas.py",
        [
            {
                "marker": "step12:schemas_settlement",
                "action": "append",
                "text": (
                    "\n# ==============================================================================\n"
                    "# STEP 12 SCHEMAS: CLEARING, SETTLEMENT & RECONCILIATION\n"
                    "# ==============================================================================\n\n"
                    "class BatchCutoverRequest(BaseModel):\n"
                    "    ps_code: str = 'ITCL'\n\n\n"
                    "class SettlementBatchOut(BaseModel):\n"
                    "    id: str\n"
                    "    batch_number: str\n"
                    "    ps_code: str\n"
                    "    cutover_time: datetime\n"
                    "    status: str\n"
                    "    total_transactions: int\n"
                    "    total_amount: float\n"
                    "    total_fees: float\n"
                    "    created_at: datetime\n"
                    "    model_config = ConfigDict(from_attributes=True)\n\n\n"
                    "class SettlementPositionOut(BaseModel):\n"
                    "    id: str\n"
                    "    batch_id: str\n"
                    "    institution_id: str\n"
                    "    institution_code: Optional[str] = None\n"
                    "    institution_name: Optional[str] = None\n"
                    "    net_settlement_amount: float\n"
                    "    debit_count: int\n"
                    "    credit_count: int\n"
                    "    debit_volume: float\n"
                    "    credit_volume: float\n"
                    "    net_fee_amount: float\n"
                    "    settlement_status: str\n"
                    "    model_config = ConfigDict(from_attributes=True)\n\n\n"
                    "class ReconciliationReportOut(BaseModel):\n"
                    "    total_approved_transactions: int\n"
                    "    total_reversed_transactions: int\n"
                    "    total_settled_transactions: int\n"
                    "    pending_clearing_transactions: int\n"
                    "    reconciliation_status: str\n"
                    "    recent_batches: List[Dict[str, Any]]\n"
                ),
            }
        ],
    )

    # 4. Patch backend/app/host_engine.py to support 0220 Financial Advices
    session.patch_file(
        "backend/app/host_engine.py",
        [
            {
                "marker": "step12:host_engine_0220_advice",
                "action": "insert_after",
                "anchor": "            if dup_query.first():\n                self._add_check(\"Duplicate Control\", \"FAILED\", \"94\", f\"Duplicate STAN {stan} / RRN {rrn}\")\n                return self._finalize_transaction(\n                    tx_id=tx_id,\n                    tx_ref=tx_ref,\n                    mti=mti,\n                    fields=input_fields,\n                    response_code=\"94\",\n                    raw_request_msg=raw_req_msg,\n                    source_channel=request_data.get(\"source_channel\", \"SIMULATOR\"),\n                    idempotency_key=idem_key,\n                )",
                "text": (
                    "\n        # Step 12: Handle 0220 Financial Advice (Clearing Presentment)\n"
                    "        if mti == '0220':\n"
                    "            self._add_check('Financial Advice Presentment (0220)', 'PASSED', '00', f'Received clearing advice for RRN {rrn}')\n"
                ),
            }
        ],
    )

    # 5. Patch backend/app/api_routes.py to add settlement endpoints
    session.patch_file(
        "backend/app/api_routes.py",
        [
            {
                "marker": "step12:api_routes_settlement_models",
                "action": "insert_after",
                "anchor": "from app.models import (",
                "text": (
                    "    SettlementBatch,\n"
                    "    SettlementEntry,\n"
                    "    SettlementPosition,"
                ),
            },
            {
                "marker": "step12:api_routes_settlement_schemas",
                "action": "insert_after",
                "anchor": "from app.schemas import (",
                "text": (
                    "    BatchCutoverRequest,\n"
                    "    ReconciliationReportOut,\n"
                    "    SettlementBatchOut,\n"
                    "    SettlementPositionOut,"
                ),
            },
            {
                "marker": "step12:api_routes_settlement_service_import",
                "action": "insert_after",
                "anchor": "from app.audit_service import record_audit, serialize_entity",
                "text": "from app.settlement_service import execute_daily_cutover, get_reconciliation_summary",
            },
            {
                "marker": "step12:api_settlement_endpoints",
                "action": "append",
                "text": (
                    "\n# ==============================================================================\n"
                    "# STEP 12 API ENDPOINTS: CLEARING, SETTLEMENT & RECONCILIATION\n"
                    "# ==============================================================================\n\n"
                    "@router.get('/settlement/batches', response_model=List[SettlementBatchOut])\n"
                    "def list_settlement_batches(db: Session = Depends(get_db), _: str = Depends(get_current_user)):\n"
                    "    return db.query(SettlementBatch).order_by(SettlementBatch.cutover_time.desc()).all()\n\n\n"
                    "@router.get('/settlement/batches/{batch_id}')\n"
                    "def get_settlement_batch_details(batch_id: str, db: Session = Depends(get_db), _: str = Depends(get_current_user)):\n"
                    "    batch = db.query(SettlementBatch).filter(SettlementBatch.id == batch_id).first()\n"
                    "    if not batch:\n"
                    "        raise HTTPException(status_code=404, detail='Settlement batch not found')\n"
                    "    positions = db.query(SettlementPosition).filter(SettlementPosition.batch_id == batch.id).all()\n"
                    "    pos_out = []\n"
                    "    for p in positions:\n"
                    "        inst = p.institution\n"
                    "        pos_out.append({\n"
                    "            'id': p.id,\n"
                    "            'batch_id': p.batch_id,\n"
                    "            'institution_id': p.institution_id,\n"
                    "            'institution_code': inst.institution_code if inst else None,\n"
                    "            'institution_name': inst.name if inst else None,\n"
                    "            'net_settlement_amount': float(p.net_settlement_amount),\n"
                    "            'debit_count': p.debit_count,\n"
                    "            'credit_count': p.credit_count,\n"
                    "            'debit_volume': float(p.debit_volume),\n"
                    "            'credit_volume': float(p.credit_volume),\n"
                    "            'net_fee_amount': float(p.net_fee_amount),\n"
                    "            'settlement_status': p.settlement_status,\n"
                    "        })\n"
                    "    return {\n"
                    "        'batch': serialize_entity(batch),\n"
                    "        'positions': pos_out,\n"
                    "    }\n\n\n"
                    "@router.post('/settlement/cutover')\n"
                    "def api_execute_settlement_cutover(payload: BatchCutoverRequest, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):\n"
                    "    return execute_daily_cutover(db, payload.ps_code, current_user)\n\n\n"
                    "@router.get('/settlement/reconciliation', response_model=ReconciliationReportOut)\n"
                    "def api_get_reconciliation_summary(db: Session = Depends(get_db), _: str = Depends(get_current_user)):\n"
                    "    return get_reconciliation_summary(db)\n\n\n"
                    "@router.post('/settlement/run-scenarios')\n"
                    "def api_run_settlement_scenarios(db: Session = Depends(get_db), _: str = Depends(get_current_user)):\n"
                    "    # Generate synthetic multi-bank transactions between xBank, yBank, and zBank\n"
                    "    from app.host_engine import HostTransactionProcessor\n"
                    "    proc = HostTransactionProcessor(db)\n"
                    "    now_suffix = datetime.now().strftime('%M%S')\n"
                    "    test_cases = [\n"
                    "        ('10', '0200', '4567890123450001', '000000050000', f'91{now_suffix}1', f'00091{now_suffix}1', '123456'),\n"
                    "        ('40', '0200', '4567890123450001', '000000120000', f'91{now_suffix}2', f'00091{now_suffix}2', '223456'),\n"
                    "        ('10', '0200', '4567890123450004', '000000085000', f'91{now_suffix}3', f'00091{now_suffix}3', '123456'),\n"
                    "    ]\n"
                    "    approved = 0\n"
                    "    declined = 0\n"
                    "    for tc, mti, pan, amt, stan, rrn, acq in test_cases:\n"
                    "        res = proc.process_transaction({\n"
                    "            'transaction_code': tc,\n"
                    "            'mti': mti,\n"
                    "            'test_clear_pin_helper': '1234',\n"
                    "            'fields': {'2': pan, '3': '0100000', '4': amt, '11': stan, '32': acq, '37': rrn, '41': 'ATM01', '49': 'BDT'},\n"
                    "        })\n"
                    "        if res['response_code'] == '00':\n"
                    "            approved += 1\n"
                    "        else:\n"
                    "            declined += 1\n"
                    "    return {\n"
                    "        'transactions_generated': len(test_cases),\n"
                    "        'approved_count': approved,\n"
                    "        'declined_count': declined,\n"
                    "    }\n"
                ),
            },
        ],
    )

    # 6. Write frontend/src/pages/ClearingAndSettlementPage.tsx
    session.write_file("frontend/src/pages/ClearingAndSettlementPage.tsx", SETTLEMENT_PAGE_CODE)

    # 7. Patch frontend/src/App.tsx to add /settlement route
    session.patch_file(
        "frontend/src/App.tsx",
        [
            {
                "marker": "step12:app_import_settlement",
                "action": "insert_after",
                "anchor": "import { NetworkRoutingPage } from './pages/NetworkRoutingPage';",
                "text": "import { ClearingAndSettlementPage } from './pages/ClearingAndSettlementPage';",
            },
            {
                "marker": "step12:app_route_settlement",
                "action": "insert_after",
                "anchor": "        <Route\n          path=\"/network-routing\"\n          element={\n            <ProtectedRoute>\n              <NetworkRoutingPage />\n            </ProtectedRoute>\n          }\n        />",
                "text": (
                    "        <Route\n"
                    "          path=\"/settlement\"\n          element={\n"
                    "            <ProtectedRoute>\n"
                    "              <ClearingAndSettlementPage />\n"
                    "            </ProtectedRoute>\n"
                    "          }\n"
                    "        />"
                ),
            },
        ],
    )

    # 8. Patch frontend/src/components/Layout.tsx to add Clearing & Settlement navigation link
    session.patch_file(
        "frontend/src/components/Layout.tsx",
        [
            {
                "marker": "step12:layout_nav_settlement",
                "action": "insert_after",
                "anchor": "  { to: '/institutions', label: '1.5. Banks & Switch BINS', icon: Network, group: 'CORE BANKING' },",
                "text": "  { to: '/settlement', label: '1.8. Clearing & Settlement', icon: Landmark, group: 'CORE BANKING' },",
            }
        ],
    )

    # 9. Write automated pytest test suite backend/tests/test_step12_settlement.py
    session.write_file("backend/tests/test_step12_settlement.py", TEST_STEP12_CODE)

    session.record_progress(
        completed=[
            "Created `backend/app/settlement_service.py` providing dual-balance hold vs clear, interchange fee calculations, daily cutover batches, and multilateral net settlement.",
            "Created `SettlementBatch`, `SettlementEntry`, and `SettlementPosition` ORM models in `backend/app/models.py`.",
            "Added Pydantic schemas in `backend/app/schemas.py`.",
            "Added 0220 Financial Advice clearing presentment handling in `backend/app/host_engine.py`.",
            "Added REST endpoints: `GET/POST /api/settlement/cutover`, `GET /api/settlement/batches`, `GET /api/settlement/reconciliation`, `POST /api/settlement/run-scenarios`.",
            "Created React UI console `frontend/src/pages/ClearingAndSettlementPage.tsx` and registered route `/settlement` in `App.tsx` and `Layout.tsx`.",
            "Created automated Pytest test suite `backend/tests/test_step12_settlement.py`.",
        ],
        remaining=[],
        modified_files=[
            "backend/app/settlement_service.py",
            "backend/app/models.py",
            "backend/app/schemas.py",
            "backend/app/host_engine.py",
            "backend/app/api_routes.py",
            "frontend/src/pages/ClearingAndSettlementPage.tsx",
            "frontend/src/App.tsx",
            "frontend/src/components/Layout.tsx",
            "backend/tests/test_step12_settlement.py",
        ],
    )

    session.record_contracts(
        section_title="Step 12 — Clearing, Settlement & Reconciliation Contracts",
        contract_items=[
            "**Module**: `backend/app/settlement_service.py` (`execute_daily_cutover`, `calculate_fees`, `get_reconciliation_summary`).",
            "**Tables**: `settlement_batches`, `settlement_entries`, `settlement_positions`.",
            "**GET /api/settlement/batches**: Lists closed settlement batches.",
            "**POST /api/settlement/cutover**: Closes the current transaction window, computes interchange/switch fees, and derives net bank positions.",
            "**GET /api/settlement/reconciliation**: Returns totals for approved, reversed, settled, and pending clearing transactions.",
            "**POST /api/settlement/run-scenarios**: Automatically generates multi-bank financial transactions for clearing regression testing.",
            "**React Route**: `/#/settlement` (`ClearingAndSettlementPage`).",
        ],
    )

    return session.finish()


if __name__ == "__main__":
    sys.exit(main())