"""
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
