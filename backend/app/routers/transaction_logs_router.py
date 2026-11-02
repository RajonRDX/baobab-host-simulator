"""
transaction_logs_router.py — Enterprise Transaction Log Viewer & Investigation API
Implements:
  - GET  /api/transaction-logs
  - GET  /api/transaction-logs/summary
  - GET  /api/transaction-logs/export
  - GET  /api/transaction-logs/{transaction_id}
  - GET  /api/transaction-logs/{transaction_id}/authorization
  - GET  /api/transaction-logs/{transaction_id}/messages
  - GET  /api/transaction-logs/{transaction_id}/messages/{message_id}/parsed
  - GET  /api/transaction-logs/{transaction_id}/messages/{message_id}/export-excel
  - GET  /api/transaction-logs/{transaction_id}/crypto
  - GET  /api/transaction-logs/{transaction_id}/trace
  - POST /api/transaction-logs/{transaction_id}/trace/generate
  - GET  /api/transaction-logs/{transaction_id}/trace/export
  - GET  /api/transaction-logs/{transaction_id}/related
  - GET  /api/transaction-logs/{transaction_id}/package
"""

import csv
import io
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import asc, desc, func, or_
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.database import get_db
from app.models import (
    Account,
    AccountLedger,
    AccountLimit,
    BinRange,
    Card,
    CardLimit,
    CryptoEvent,
    Customer,
    HsmAuditLog,
    HsmKeyReference,
    HsmOperation,
    Institution,
    ProcessingSystem,
    Transaction,
    TransactionCheck,
    TransactionCode,
    TransactionMessage,
    TransactionReversal,
    TransactionTraceEvent,
)
from app.security import get_current_user, mask_pan, sanitize_dict
from app.tic_decoder_engine import (
    strict_mask_pan,
    TRAN_CODES,
    compare_request_and_response,
    decode_full_tic_or_iso_message,
    export_decoded_message_excel_bytes,
    extract_metadata_from_tic,
    mask_sensitive_wire_string,
)

router = APIRouter(prefix="/api/transaction-logs", tags=["Transaction Log Viewer"])


def _short_inst_code(inst: Optional[Institution], default: str = "ITCL") -> str:
    if not inst:
        return default
    raw = (inst.short_name or inst.institution_code or default).strip()
    for sep in (" - ", " — ", " – ", "/"):
        if sep in raw:
            return raw.split(sep)[0].strip().upper()
    return raw.upper()


def _resolve_display_status(tx: Transaction) -> str:
    if (tx.transaction_status or "").upper() == "REVERSED":
        return "REVERSED"
    if (tx.transaction_status or "").upper() == "PENDING":
        return "PENDING"
    return (tx.authorization_status or "DECLINED").upper()


def backfill_historical_transaction_metadata(db: Session) -> None:
    """
    Safe, idempotent startup backfill so any pre-existing transactions created before
    the Transaction Log Viewer upgrade have populated metadata columns (approval_code,
    mcc, terminal_owner, transaction_type_name, etc.) from their stored TIC messages.
    """
    missing_txs = (
        db.query(Transaction)
        .filter(Transaction.transaction_type_name.is_(None))
        .limit(500)
        .all()
    )
    if not missing_txs:
        return

    for tx in missing_txs:
        f3_prefix = (tx.processing_code or "0100000")[:3]
        tx.transaction_type_name = TRAN_CODES.get(f3_prefix) or (
            "Acquirer Reversal" if (tx.mti or "").startswith("04") else f"Code {tx.transaction_code or f3_prefix}"
        )
        tx.correlation_id = tx.correlation_id or tx.transaction_reference

        msgs = db.query(TransactionMessage).filter(TransactionMessage.transaction_id == tx.id).all()
        req_m = next((m for m in msgs if m.message_type == "REQUEST"), None)
        resp_m = next((m for m in msgs if m.message_type == "RESPONSE"), None)

        if req_m and req_m.sanitized_message:
            meta = extract_metadata_from_tic(req_m.sanitized_message)
            tx.mcc = tx.mcc or meta.get("mcc") or "6011"
            tx.pos_entry_mode = tx.pos_entry_mode or meta.get("pos_entry_mode") or "051"
            tx.pos_condition_code = tx.pos_condition_code or meta.get("pos_condition_code") or "000"
            tx.acquirer_id = tx.acquirer_id or meta.get("acquirer_id") or tx.merchant_id or "123456"
            tx.forwarding_id = tx.forwarding_id or meta.get("forwarding_id")
            tx.terminal_name = tx.terminal_name or meta.get("terminal_name") or tx.terminal_id
            tx.terminal_owner = tx.terminal_owner or meta.get("terminal_owner") or "ITCL Member Bank"
            tx.merchant_name = tx.merchant_name or meta.get("merchant_name") or tx.merchant_id
            tx.source_account = tx.source_account or meta.get("source_account")
            tx.destination_account = tx.destination_account or meta.get("destination_account")

        if resp_m and resp_m.sanitized_message:
            resp_meta = extract_metadata_from_tic(resp_m.sanitized_message)
            tx.approval_code = tx.approval_code or resp_meta.get("approval_code")
        if not tx.approval_code:
            tx.approval_code = tx.rrn[-6:] if (tx.authorization_status == "APPROVED" and tx.rrn) else "000000"

        if not tx.source_account and tx.account_id:
            acct = db.query(Account).filter(Account.id == tx.account_id).first()
            if acct:
                tx.source_account = acct.account_number

        checks = db.query(TransactionCheck).filter(TransactionCheck.transaction_id == tx.id).all()
        dur_sum = sum(c.duration_ms or 1 for c in checks)
        tx.processing_duration_ms = max(2, dur_sum)
        if tx.authorization_status != "APPROVED":
            failed = next((c for c in checks if c.check_status == "FAILED"), None)
            tx.decline_reason = failed.message if failed else tx.response_message

    db.commit()


def _apply_transaction_filters(
    query,
    db: Session,
    transaction_id: Optional[str] = None,
    rrn: Optional[str] = None,
    stan: Optional[str] = None,
    pan: Optional[str] = None,
    account_number: Optional[str] = None,
    customer: Optional[str] = None,
    terminal_id: Optional[str] = None,
    terminal_name: Optional[str] = None,
    merchant_id: Optional[str] = None,
    merchant_name: Optional[str] = None,
    mcc: Optional[str] = None,
    issuer: Optional[str] = None,
    acquirer: Optional[str] = None,
    ps_code: Optional[str] = None,
    mti: Optional[str] = None,
    response_code: Optional[str] = None,
    status: Optional[str] = None,
    transaction_type: Optional[str] = None,
    currency: Optional[str] = None,
    amount_from: Optional[float] = None,
    amount_to: Optional[float] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    correlation_id: Optional[str] = None,
):
    if transaction_id:
        t_clean = transaction_id.strip()
        term = f"%{t_clean}%"
        query = query.filter(
            or_(
                Transaction.id.ilike(term),
                Transaction.transaction_reference.ilike(term),
                Transaction.correlation_id.ilike(term),
            )
        )
    if correlation_id:
        c_term = f"%{correlation_id.strip()}%"
        query = query.filter(
            or_(
                Transaction.correlation_id.ilike(c_term),
                Transaction.transaction_reference.ilike(c_term),
            )
        )
    if rrn:
        query = query.filter(Transaction.rrn.ilike(f"%{rrn.strip()}%"))
    if stan:
        query = query.filter(Transaction.stan.ilike(f"%{stan.strip()}%"))
    if pan:
        p_clean = pan.strip()
        p_term = f"%{p_clean}%"
        matching_card_ids = [
            c.id for c in db.query(Card.id).filter(
                or_(Card.test_pan_reference.ilike(p_term), Card.masked_pan.ilike(p_term))
            ).all()
        ]
        if matching_card_ids:
            query = query.filter(
                or_(Transaction.masked_pan.ilike(p_term), Transaction.card_id.in_(matching_card_ids))
            )
        else:
            query = query.filter(Transaction.masked_pan.ilike(p_term))
    if account_number:
        a_term = f"%{account_number.strip()}%"
        acct_ids = [a.id for a in db.query(Account.id).filter(Account.account_number.ilike(a_term)).all()]
        query = query.filter(
            or_(
                Transaction.source_account.ilike(a_term),
                Transaction.destination_account.ilike(a_term),
                Transaction.account_id.in_(acct_ids) if acct_ids else False,
            )
        )
    if customer:
        c_term = f"%{customer.strip()}%"
        cust_ids = [
            c.id for c in db.query(Customer.id).filter(
                or_(
                    Customer.customer_number.ilike(c_term),
                    Customer.first_name.ilike(c_term),
                    Customer.last_name.ilike(c_term),
                )
            ).all()
        ]
        query = query.filter(Transaction.customer_id.in_(cust_ids) if cust_ids else Transaction.customer_id == "__NONE__")
    if terminal_id:
        query = query.filter(Transaction.terminal_id.ilike(f"%{terminal_id.strip()}%"))
    if terminal_name:
        tn = f"%{terminal_name.strip()}%"
        query = query.filter(or_(Transaction.terminal_name.ilike(tn), Transaction.terminal_owner.ilike(tn)))
    if merchant_id:
        query = query.filter(Transaction.merchant_id.ilike(f"%{merchant_id.strip()}%"))
    if merchant_name:
        query = query.filter(Transaction.merchant_name.ilike(f"%{merchant_name.strip()}%"))
    if mcc:
        query = query.filter(Transaction.mcc.ilike(f"%{mcc.strip()}%"))
    if issuer:
        iss_term = f"%{issuer.strip()}%"
        iss_ids = [
            i.id for i in db.query(Institution.id).filter(
                or_(
                    Institution.id == issuer.strip(),
                    Institution.institution_code.ilike(iss_term),
                    Institution.short_name.ilike(iss_term),
                    Institution.name.ilike(iss_term),
                )
            ).all()
        ]
        query = query.filter(Transaction.issuer_institution_id.in_(iss_ids) if iss_ids else Transaction.issuer_institution_id == "__NONE__")
    if acquirer:
        acq_term = f"%{acquirer.strip()}%"
        acq_ids = [
            i.id for i in db.query(Institution.id).filter(
                or_(
                    Institution.id == acquirer.strip(),
                    Institution.institution_code.ilike(acq_term),
                    Institution.short_name.ilike(acq_term),
                    Institution.name.ilike(acq_term),
                    Institution.acquirer_id.ilike(acq_term),
                )
            ).all()
        ]
        query = query.filter(
            or_(
                Transaction.acquirer_institution_id.in_(acq_ids) if acq_ids else False,
                Transaction.acquirer_id.ilike(acq_term),
            )
        )
    if ps_code:
        query = query.filter(Transaction.ps_code == ps_code.strip().upper())
    if mti:
        query = query.filter(Transaction.mti == mti.strip())
    if response_code:
        query = query.filter(Transaction.response_code == response_code.strip())
    if status:
        st_up = status.strip().upper()
        if st_up == "REVERSED":
            query = query.filter(Transaction.transaction_status == "REVERSED")
        elif st_up == "PENDING":
            query = query.filter(Transaction.transaction_status == "PENDING")
        elif st_up == "APPROVED":
            query = query.filter(Transaction.authorization_status == "APPROVED", Transaction.transaction_status != "REVERSED")
        elif st_up == "DECLINED":
            query = query.filter(Transaction.authorization_status == "DECLINED")
    if transaction_type:
        tt = f"%{transaction_type.strip()}%"
        query = query.filter(
            or_(
                Transaction.transaction_type_name.ilike(tt),
                Transaction.transaction_code == transaction_type.strip(),
                Transaction.processing_code.ilike(tt),
            )
        )
    if currency:
        query = query.filter(Transaction.currency == currency.strip().upper())
    if amount_from is not None:
        query = query.filter(Transaction.transaction_amount >= Decimal(str(amount_from)))
    if amount_to is not None:
        query = query.filter(Transaction.transaction_amount <= Decimal(str(amount_to)))
    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from.replace("Z", "+00:00"))
            query = query.filter(Transaction.created_at >= dt_from)
        except Exception:
            pass
    if date_to:
        try:
            raw_to = date_to.strip()
            if len(raw_to) == 10:
                dt_to = datetime.fromisoformat(raw_to + "T23:59:59+00:00")
            else:
                dt_to = datetime.fromisoformat(raw_to.replace("Z", "+00:00"))
            query = query.filter(Transaction.created_at <= dt_to)
        except Exception:
            pass
    return query


def _serialize_tx_list_row(tx: Transaction) -> Dict[str, Any]:
    created_dt = tx.created_at or datetime.now(timezone.utc)
    iss_code = _short_inst_code(tx.issuer_institution, "XBANK")
    acq_code = _short_inst_code(tx.acquirer_institution, "XBANK")
    f3_prefix = (tx.processing_code or "0100000")[:3]
    tx_type = tx.transaction_type_name or TRAN_CODES.get(f3_prefix) or (
        "Acquirer Reversal" if (tx.mti or "").startswith("04") else f"Code {tx.transaction_code or f3_prefix}"
    )
    return {
        "id": tx.id,
        "transaction_reference": tx.transaction_reference,
        "correlation_id": tx.correlation_id or tx.transaction_reference,
        "date": created_dt.strftime("%Y-%m-%d"),
        "time": created_dt.strftime("%H:%M:%S.%f")[:-3],
        "created_at": created_dt.isoformat(),
        "mti": tx.mti,
        "processing_code": tx.processing_code,
        "transaction_code": tx.transaction_code,
        "transaction_type": tx_type,
        "mcc": tx.mcc or "6011",
        "terminal_id": tx.terminal_id or "TERM0001",
        "terminal_name": tx.terminal_name or tx.terminal_id or "ATM Terminal",
        "terminal_owner": tx.terminal_owner or acq_code,
        "merchant_id": tx.merchant_id or "123456",
        "merchant_name": tx.merchant_name or f"{acq_code} Merchant",
        "issuer_code": iss_code,
        "issuer_name": tx.issuer_institution.name if tx.issuer_institution else iss_code,
        "acquirer_code": acq_code,
        "acquirer_name": tx.acquirer_institution.name if tx.acquirer_institution else acq_code,
        "ps_code": tx.ps_code or "ITCL",
        "is_on_us": bool(tx.is_on_us),
        "masked_pan": strict_mask_pan(tx.masked_pan),
        "source_account": tx.source_account,
        "amount": float(tx.transaction_amount or 0),
        "billing_amount": float(tx.billing_amount or tx.transaction_amount or 0),
        "currency": tx.currency or "BDT",
        "response_code": tx.response_code,
        "response_description": tx.response_message,
        "approval_code": tx.approval_code or ("000000" if tx.response_code != "00" else (tx.rrn[-6:] if tx.rrn else "AUTH00")),
        "rrn": tx.rrn,
        "stan": tx.stan,
        "status": _resolve_display_status(tx),
        "authorization_status": tx.authorization_status,
        "transaction_status": tx.transaction_status,
        "processing_duration_ms": tx.processing_duration_ms or 2,
        "source_channel": tx.source_channel,
    }


def _compute_summary_from_query(filtered_query) -> Dict[str, Any]:
    total = filtered_query.count()
    approved = filtered_query.filter(
        Transaction.authorization_status == "APPROVED",
        Transaction.transaction_status != "REVERSED",
    ).count()
    declined = filtered_query.filter(Transaction.authorization_status == "DECLINED").count()
    reversed_cnt = filtered_query.filter(Transaction.transaction_status == "REVERSED").count()
    pending_cnt = filtered_query.filter(Transaction.transaction_status == "PENDING").count()
    total_approved_ever = approved + reversed_cnt
    rate = round((total_approved_ever / total) * 100, 1) if total > 0 else 0.0
    vol = (
        filtered_query.filter(Transaction.authorization_status == "APPROVED")
        .with_entities(func.sum(Transaction.transaction_amount))
        .scalar()
        or Decimal("0.00")
    )
    return {
        "total_transactions": total,
        "approved_transactions": approved,
        "declined_transactions": declined,
        "reversed_transactions": reversed_cnt,
        "pending_transactions": pending_cnt,
        "approval_rate": rate,
        "approved_volume": float(vol),
    }


@router.get("")
def list_transaction_logs(
    transaction_id: Optional[str] = Query(None),
    correlation_id: Optional[str] = Query(None),
    rrn: Optional[str] = Query(None),
    stan: Optional[str] = Query(None),
    pan: Optional[str] = Query(None),
    account_number: Optional[str] = Query(None),
    customer: Optional[str] = Query(None),
    terminal_id: Optional[str] = Query(None),
    terminal_name: Optional[str] = Query(None),
    merchant_id: Optional[str] = Query(None),
    merchant_name: Optional[str] = Query(None),
    mcc: Optional[str] = Query(None),
    issuer: Optional[str] = Query(None),
    acquirer: Optional[str] = Query(None),
    ps_code: Optional[str] = Query(None),
    mti: Optional[str] = Query(None),
    response_code: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    transaction_type: Optional[str] = Query(None),
    currency: Optional[str] = Query(None),
    amount_from: Optional[float] = Query(None),
    amount_to: Optional[float] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    sort_by: str = Query("created_at"),
    sort_dir: str = Query("desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    """
    Lightweight, server-side paginated transaction log list.
    Never loads raw ISO messages per row, preventing N+1 queries and keeping auto-refresh fast.
    """
    base_q = db.query(Transaction).options(
        joinedload(Transaction.issuer_institution),
        joinedload(Transaction.acquirer_institution),
    )
    filtered_q = _apply_transaction_filters(
        base_q, db,
        transaction_id=transaction_id, correlation_id=correlation_id, rrn=rrn, stan=stan,
        pan=pan, account_number=account_number, customer=customer, terminal_id=terminal_id,
        terminal_name=terminal_name, merchant_id=merchant_id, merchant_name=merchant_name,
        mcc=mcc, issuer=issuer, acquirer=acquirer, ps_code=ps_code, mti=mti,
        response_code=response_code, status=status, transaction_type=transaction_type,
        currency=currency, amount_from=amount_from, amount_to=amount_to,
        date_from=date_from, date_to=date_to,
    )

    summary = _compute_summary_from_query(
        _apply_transaction_filters(
            db.query(Transaction), db,
            transaction_id=transaction_id, correlation_id=correlation_id, rrn=rrn, stan=stan,
            pan=pan, account_number=account_number, customer=customer, terminal_id=terminal_id,
            terminal_name=terminal_name, merchant_id=merchant_id, merchant_name=merchant_name,
            mcc=mcc, issuer=issuer, acquirer=acquirer, ps_code=ps_code, mti=mti,
            response_code=response_code, status=status, transaction_type=transaction_type,
            currency=currency, amount_from=amount_from, amount_to=amount_to,
            date_from=date_from, date_to=date_to,
        )
    )

    sort_col_map = {
        "created_at": Transaction.created_at,
        "transaction_reference": Transaction.transaction_reference,
        "amount": Transaction.transaction_amount,
        "mti": Transaction.mti,
        "rrn": Transaction.rrn,
        "stan": Transaction.stan,
        "response_code": Transaction.response_code,
        "status": Transaction.authorization_status,
    }
    sort_col = sort_col_map.get(sort_by, Transaction.created_at)
    order_expr = asc(sort_col) if sort_dir.lower() == "asc" else desc(sort_col)

    total = summary["total_transactions"]
    total_pages = max(1, (total + page_size - 1) // page_size)
    safe_page = min(page, total_pages)

    rows = (
        filtered_q.order_by(order_expr)
        .offset((safe_page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "items": [_serialize_tx_list_row(t) for t in rows],
        "total": total,
        "page": safe_page,
        "page_size": page_size,
        "total_pages": total_pages,
        "summary": summary,
        "server_timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/summary")
def get_transaction_logs_summary(
    transaction_id: Optional[str] = Query(None),
    rrn: Optional[str] = Query(None),
    stan: Optional[str] = Query(None),
    pan: Optional[str] = Query(None),
    issuer: Optional[str] = Query(None),
    acquirer: Optional[str] = Query(None),
    ps_code: Optional[str] = Query(None),
    mti: Optional[str] = Query(None),
    response_code: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    filtered_q = _apply_transaction_filters(
        db.query(Transaction), db,
        transaction_id=transaction_id, rrn=rrn, stan=stan, pan=pan,
        issuer=issuer, acquirer=acquirer, ps_code=ps_code, mti=mti,
        response_code=response_code, status=status, date_from=date_from, date_to=date_to,
    )
    return _compute_summary_from_query(filtered_q)


@router.get("/export")
def export_transaction_logs_csv(
    transaction_id: Optional[str] = Query(None),
    rrn: Optional[str] = Query(None),
    stan: Optional[str] = Query(None),
    pan: Optional[str] = Query(None),
    issuer: Optional[str] = Query(None),
    acquirer: Optional[str] = Query(None),
    ps_code: Optional[str] = Query(None),
    mti: Optional[str] = Query(None),
    response_code: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    transaction_type: Optional[str] = Query(None),
    currency: Optional[str] = Query(None),
    amount_from: Optional[float] = Query(None),
    amount_to: Optional[float] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    base_q = db.query(Transaction).options(
        joinedload(Transaction.issuer_institution),
        joinedload(Transaction.acquirer_institution),
    )
    filtered_q = _apply_transaction_filters(
        base_q, db,
        transaction_id=transaction_id, rrn=rrn, stan=stan, pan=pan,
        issuer=issuer, acquirer=acquirer, ps_code=ps_code, mti=mti,
        response_code=response_code, status=status, transaction_type=transaction_type,
        currency=currency, amount_from=amount_from, amount_to=amount_to,
        date_from=date_from, date_to=date_to,
    )
    rows = filtered_q.order_by(Transaction.created_at.desc()).limit(2000).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Txn Reference", "Date", "Time", "MTI", "Transaction Type", "Processing System",
        "Issuer", "Acquirer", "Masked PAN", "Source Account", "Amount", "Currency",
        "Response Code", "Response Description", "Approval Code", "RRN", "STAN",
        "Terminal ID", "Terminal Owner", "MCC", "Status", "Duration (ms)"
    ])
    for t in rows:
        s = _serialize_tx_list_row(t)
        writer.writerow([
            s["transaction_reference"], s["date"], s["time"], s["mti"], s["transaction_type"],
            s["ps_code"], s["issuer_code"], s["acquirer_code"], s["masked_pan"],
            s["source_account"] or "", f"{s['amount']:.2f}", s["currency"],
            s["response_code"], s["response_description"], s["approval_code"],
            s["rrn"], s["stan"], s["terminal_id"], s["terminal_owner"], s["mcc"],
            s["status"], s["processing_duration_ms"],
        ])

    csv_bytes = output.getvalue().encode("utf-8-sig")
    fname = f"baobab_transaction_logs_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


def _get_tx_or_404(db: Session, transaction_id: str) -> Transaction:
    tx = (
        db.query(Transaction)
        .options(
            joinedload(Transaction.issuer_institution),
            joinedload(Transaction.acquirer_institution),
        )
        .filter(
            or_(
                Transaction.id == transaction_id,
                Transaction.transaction_reference == transaction_id,
            )
        )
        .first()
    )
    if not tx:
        raise HTTPException(status_code=404, detail=f"Transaction '{transaction_id}' not found")
    return tx


@router.get("/{transaction_id}")
def get_transaction_general_detail(
    transaction_id: str,
    reveal_pan: bool = Query(False, description="Explicit simulator-only full PAN reveal"),
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    """TAB 1 — GENERAL: Complete Transaction, Card, Account, Merchant/Terminal, Financial & Network Reference info."""
    tx = _get_tx_or_404(db, transaction_id)
    card = db.query(Card).filter(Card.id == tx.card_id).first() if tx.card_id else None
    cust = db.query(Customer).filter(Customer.id == tx.customer_id).first() if tx.customer_id else None
    acct = db.query(Account).filter(Account.id == tx.account_id).first() if tx.account_id else None

    # Decode request message for any additional terminal/location attributes
    req_msg = (
        db.query(TransactionMessage)
        .filter(TransactionMessage.transaction_id == tx.id, TransactionMessage.message_type == "REQUEST")
        .first()
    )
    f43_location = None
    if req_msg and req_msg.sanitized_message:
        dec = decode_full_tic_or_iso_message(req_msg.sanitized_message)
        for pf in dec.get("parsed_fields", []):
            if pf["field_number"] == 43:
                f43_location = pf["display_value"]

    allow_full = bool(reveal_pan and getattr(settings, "LOG_RAW_DATA", True))
    raw_pan_val = (card.test_pan_reference if card else tx.masked_pan) or ""
    pan_display = raw_pan_val if allow_full else strict_mask_pan(raw_pan_val)
    bin_prefix = (card.test_pan_reference[:6] if card and card.test_pan_reference else (tx.masked_pan[:6] if tx.masked_pan else "N/A"))

    row_summary = _serialize_tx_list_row(tx)
    return {
        "summary": row_summary,
        "transaction_info": {
            "transaction_id": tx.id,
            "transaction_reference": tx.transaction_reference,
            "transaction_date": row_summary["date"],
            "transaction_time": row_summary["time"],
            "transaction_type": row_summary["transaction_type"],
            "mti": tx.mti,
            "processing_code": tx.processing_code,
            "transaction_code": tx.transaction_code,
            "processing_system": tx.ps_code or "ITCL",
            "transaction_status": row_summary["status"],
            "authorization_status": tx.authorization_status,
            "transaction_channel": tx.source_channel,
            "source_application": "BAOBAB Host Switch Engine",
            "correlation_id": tx.correlation_id or tx.transaction_reference,
            "is_on_us": tx.is_on_us,
        },
        "card_info": {
            "pan": pan_display,
            "masked_pan": strict_mask_pan(raw_pan_val),
            "full_pan_available": bool(card and getattr(settings, "LOG_RAW_DATA", True)),
            "card_type": card.card_type if card else "N/A",
            "card_product": card.card_product if card else "N/A",
            "bin": bin_prefix,
            "expiry_date": f"{card.expiry_month:02d}/{card.expiry_year}" if card else "••/••••",
            "card_status": card.card_status if card else "N/A",
            "cardholder_name": card.cardholder_name if card else None,
            "customer_name": f"{cust.first_name} {cust.last_name or ''}".strip() if cust else None,
            "customer_id": cust.customer_number if cust else None,
        },
        "account_info": {
            "source_account": acct.account_number if acct else tx.source_account,
            "destination_account": tx.destination_account,
            "account_type": acct.account_type if acct else None,
            "account_currency": acct.currency if acct else tx.currency,
            "account_status": acct.account_status if acct else None,
            "branch_code": acct.branch_code if acct else None,
        },
        "merchant_terminal_info": {
            "merchant_id": tx.merchant_id,
            "merchant_name": row_summary["merchant_name"],
            "mcc": row_summary["mcc"],
            "pos_entry_mode": tx.pos_entry_mode or "051",
            "pos_condition_code": tx.pos_condition_code or "000",
            "terminal_id": tx.terminal_id,
            "terminal_name": row_summary["terminal_name"],
            "terminal_owner": row_summary["terminal_owner"],
            "terminal_location": f43_location or row_summary["terminal_name"],
            "acquirer": f"{row_summary['acquirer_code']} — {row_summary['acquirer_name']}",
            "issuer": f"{row_summary['issuer_code']} — {row_summary['issuer_name']}",
        },
        "financial_info": {
            "transaction_amount": float(tx.transaction_amount or 0),
            "billing_amount": float(tx.billing_amount or tx.transaction_amount or 0),
            "transaction_currency": tx.currency,
            "billing_currency": acct.currency if acct else tx.currency,
            "exchange_rate": "1.000000",
            "fee": 0.0,
        },
        "network_reference_info": {
            "rrn": tx.rrn,
            "stan": tx.stan,
            "approval_code": row_summary["approval_code"],
            "acquirer_reference": tx.acquirer_id or (tx.acquirer_institution.acquirer_id if tx.acquirer_institution else "123456"),
            "forwarding_reference": tx.forwarding_id,
            "network_transaction_reference": tx.transaction_reference,
        },
    }


@router.get("/{transaction_id}/authorization")
def get_transaction_authorization_detail(
    transaction_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    """TAB 2 — AUTHORIZER RESPONSE: Explains why the transaction was approved or declined using actual checks & ledger."""
    tx = _get_tx_or_404(db, transaction_id)
    checks = (
        db.query(TransactionCheck)
        .filter(TransactionCheck.transaction_id == tx.id)
        .order_by(TransactionCheck.check_order.asc())
        .all()
    )
    ledger = (
        db.query(AccountLedger)
        .filter(AccountLedger.transaction_id == tx.id)
        .order_by(AccountLedger.created_at.asc())
        .all()
    )
    card = db.query(Card).filter(Card.id == tx.card_id).first() if tx.card_id else None
    acct = db.query(Account).filter(Account.id == tx.account_id).first() if tx.account_id else None
    card_lim = db.query(CardLimit).filter(CardLimit.card_id == card.id).first() if card else None
    acct_lim = db.query(AccountLimit).filter(AccountLimit.account_id == acct.id).first() if acct else None

    failed_check = next((c for c in checks if c.check_status == "FAILED"), None)
    rule_checks = [c for c in checks if "Rule" in c.check_name or "Permissions" in c.check_name]
    limit_checks = [c for c in checks if "Limit" in c.check_name]
    bin_checks = [c for c in checks if "Routing" in c.check_name or "BIN" in c.check_name or "Lookup" in c.check_name]
    card_status_chk = next((c for c in checks if "Card Status" in c.check_name), None)
    acct_status_chk = next((c for c in checks if "Account Status" in c.check_name), None)
    bal_chk = next((c for c in checks if "Balance Authorization" in c.check_name), None)

    recorded_balance_before = float(ledger[0].balance_before) if ledger else None
    recorded_balance_after = float(ledger[-1].balance_after) if ledger else (float(acct.available_balance) if acct else None)

    total_dur = sum(c.duration_ms or 1 for c in checks) or tx.processing_duration_ms or 1

    return {
        "authorization_status": tx.authorization_status,
        "transaction_status": tx.transaction_status,
        "display_status": _resolve_display_status(tx),
        "response_code": tx.response_code,
        "response_tic_f39": f"000{tx.response_code}",
        "response_description": tx.response_message,
        "decline_reason": (
            failed_check.message
            if failed_check
            else (tx.decline_reason if tx.authorization_status != "APPROVED" else "None — All authorization checks passed")
        ),
        "failed_stage": failed_check.check_name if failed_check else None,
        "authorization_decision": (
            f"APPROVED (Auth Code {tx.approval_code or '000000'})"
            if tx.authorization_status == "APPROVED"
            else f"DECLINED at stage '{failed_check.check_name if failed_check else 'Host Validation'}' (RC {tx.response_code})"
        ),
        "applicable_rules": [
            {"name": c.check_name, "status": c.check_status, "rc": c.response_code, "message": c.message}
            for c in rule_checks
        ],
        "card_status_at_auth": (
            card_status_chk.message if card_status_chk else (card.card_status if card else "Not evaluated")
        ),
        "account_status_at_auth": (
            acct_status_chk.message if acct_status_chk else (acct.account_status if acct else "Not evaluated")
        ),
        "balance_snapshot": {
            "balance_check_message": bal_chk.message if bal_chk else None,
            "balance_before": recorded_balance_before,
            "balance_after": recorded_balance_after,
            "currency": tx.currency,
        },
        "limits_evaluation": {
            "card_per_tx_limit": float(card_lim.transaction_limit) if card_lim else None,
            "card_daily_limit": float(card_lim.daily_limit) if card_lim else None,
            "account_per_tx_limit": float(acct_lim.per_transaction_limit) if acct_lim else None,
            "account_daily_limit": float(acct_lim.daily_limit) if acct_lim else None,
            "limit_validation_result": (
                " | ".join(f"{c.check_name}: {c.status if hasattr(c, 'status') else c.check_status} ({c.message})" for c in limit_checks)
                if limit_checks
                else "Not required / Not reached"
            ),
        },
        "validation_results": {
            "terminal_validation": f"Terminal {tx.terminal_id or 'TERM0001'} accepted",
            "bin_validation": (
                " | ".join(f"{c.check_name}: {c.check_status} ({c.message})" for c in bin_checks)
                if bin_checks
                else f"On-Us {tx.ps_code} routing validated"
            ),
            "processing_system_validation": f"Switch {tx.ps_code or 'ITCL'} ({'On-Us' if tx.is_on_us else 'Off-Us'})",
        },
        "timestamps": {
            "authorization_timestamp": tx.created_at.isoformat() if tx.created_at else None,
            "response_timestamp": (tx.completed_at or tx.created_at).isoformat() if (tx.completed_at or tx.created_at) else None,
            "processing_duration_ms": total_dur,
        },
        "checks": [
            {
                "check_order": c.check_order,
                "check_name": c.check_name,
                "check_status": c.check_status,
                "response_code": c.response_code,
                "message": c.message,
                "duration_ms": c.duration_ms,
                "timestamp": c.created_at.isoformat() if c.created_at else None,
            }
            for c in checks
        ],
        "ledger_entries": [
            {
                "id": l.id,
                "entry_type": l.entry_type,
                "amount": float(l.amount),
                "currency": l.currency,
                "balance_before": float(l.balance_before),
                "balance_after": float(l.balance_after),
                "description": l.description,
                "posting_status": l.posting_status,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in ledger
        ],
    }


@router.get("/{transaction_id}/messages")
def get_transaction_iso_messages(
    transaction_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    """TAB 3 — ISO DETAILS: Returns all stored messages for the transaction, decoded with `tic_decoder.py` + side-by-side diff."""
    tx = _get_tx_or_404(db, transaction_id)
    msgs = (
        db.query(TransactionMessage)
        .filter(TransactionMessage.transaction_id == tx.id)
        .order_by(TransactionMessage.created_at.asc())
        .all()
    )

    req_raw = None
    resp_raw = None
    out_msgs = []
    for m in msgs:
        if m.message_type == "REQUEST" and not req_raw:
            req_raw = m.sanitized_message
        elif m.message_type == "RESPONSE" and not resp_raw:
            resp_raw = m.sanitized_message

        decoded = decode_full_tic_or_iso_message(m.sanitized_message, allow_full_pan=False)
        out_msgs.append({
            "id": m.id,
            "transaction_id": tx.id,
            "direction": m.message_type,
            "mti": m.mti,
            "message_format": m.message_format,
            "timestamp": m.created_at.isoformat() if m.created_at else tx.created_at.isoformat(),
            "raw_message": mask_sensitive_wire_string(m.sanitized_message),
            "decoded": decoded,
        })

    comparison = compare_request_and_response(req_raw, resp_raw)
    return {
        "transaction_id": tx.id,
        "transaction_reference": tx.transaction_reference,
        "rrn": tx.rrn,
        "stan": tx.stan,
        "messages": out_msgs,
        "comparison": comparison,
    }


@router.get("/{transaction_id}/messages/{message_id}/parsed")
def get_single_parsed_iso_message(
    transaction_id: str,
    message_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    tx = _get_tx_or_404(db, transaction_id)
    msg = (
        db.query(TransactionMessage)
        .filter(TransactionMessage.id == message_id, TransactionMessage.transaction_id == tx.id)
        .first()
    )
    if not msg:
        raise HTTPException(status_code=404, detail="Transaction message not found")
    decoded = decode_full_tic_or_iso_message(msg.sanitized_message, allow_full_pan=False)
    return {
        "id": msg.id,
        "direction": msg.message_type,
        "mti": msg.mti,
        "message_format": msg.message_format,
        "timestamp": msg.created_at.isoformat() if msg.created_at else None,
        "raw_message": mask_sensitive_wire_string(msg.sanitized_message),
        "decoded": decoded,
    }


@router.get("/{transaction_id}/messages/{message_id}/export-excel")
def export_parsed_message_excel(
    transaction_id: str,
    message_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    tx = _get_tx_or_404(db, transaction_id)
    msg = (
        db.query(TransactionMessage)
        .filter(TransactionMessage.id == message_id, TransactionMessage.transaction_id == tx.id)
        .first()
    )
    if not msg:
        raise HTTPException(status_code=404, detail="Transaction message not found")
    decoded = decode_full_tic_or_iso_message(msg.sanitized_message, allow_full_pan=False)
    xlsx_bytes = export_decoded_message_excel_bytes(decoded, rrn=f"{tx.rrn}_{msg.mti}")
    if not xlsx_bytes:
        # CSV fallback if openpyxl is unavailable
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["Field", "Field Name", "Subfield / Key", "Value"])
        for row in decoded.get("flat_rows", []):
            writer.writerow([row["field_tag"], row["field_name"], row["subfield_key"], row["value"]])
        return Response(
            content=buf.getvalue().encode("utf-8-sig"),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{tx.rrn}_{msg.mti}_decoded.csv"'},
        )
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{tx.rrn}_{msg.mti}_decoded.xlsx"'},
    )


def _mask_crypto_dict(d: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not d:
        return {}
    out: Dict[str, Any] = {}
    for k, v in d.items():
        kl = k.lower()
        if any(s in kl for s in ("pin_block", "clear_key", "clear_pin", "cvv", "track", "pvv", "offset", "secret")):
            if kl in ("pvv_matched", "cvv_matched", "arqc_verified", "mac_matched", "destination_pin_block_generated"):
                out[k] = v
            else:
                out[k] = "***MASKED_SENSITIVE***"
        else:
            out[k] = v
    return out


@router.get("/{transaction_id}/crypto")
def get_transaction_crypto_detail(
    transaction_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    """TAB 4 — KEYS & CRYPTO: Returns sanitized HSM operations, key references (never clear key material), and audit refs."""
    tx = _get_tx_or_404(db, transaction_id)
    hsm_ops = (
        db.query(HsmOperation)
        .filter(HsmOperation.transaction_id == tx.id)
        .order_by(HsmOperation.created_at.asc())
        .all()
    )

    operations_out = []
    for op in hsm_ops:
        key_rec = db.query(HsmKeyReference).filter(HsmKeyReference.id == op.key_reference_id).first() if op.key_reference_id else None
        audit_rec = db.query(HsmAuditLog).filter(HsmAuditLog.operation_id == op.id).first()
        op_up = op.operation_type.upper()
        op_category = "CRYPTO_OPERATION"
        if "PVV" in op_up or "PIN_VERIFY" in op_up:
            op_category = "PIN Verification (Visa PVV / IBM 3624)"
        elif "TRANSLATE" in op_up:
            op_category = "PIN Block Translation (AWK -> IWK)"
        elif "CVV" in op_up:
            op_category = "CVV / CVV2 Verification"
        elif "ARQC" in op_up or "EMV" in op_up:
            op_category = "EMV ARQC Verification & ARPC Generation"
        elif "MAC" in op_up:
            op_category = "Retail MAC ISO 9797-1 Alg 3"

        operations_out.append({
            "operation_id": op.id,
            "hsm_provider": "Thales payShield 10K Soft-HSM",
            "hsm_connection": f"{settings.HSM_MODE} (Host LMK Slot Table)",
            "hsm_operation": op.operation_type,
            "operation_category": op_category,
            "request_reference": op.request_reference,
            "audit_reference": audit_rec.audit_reference if audit_rec else None,
            "key_type": key_rec.key_type if key_rec else "SLOT_KEY",
            "key_alias": key_rec.key_identifier if key_rec else "DEFAULT_SLOT",
            "key_name": key_rec.key_name if key_rec else "Internal HSM Operational Key",
            "key_version": "v1 (Active)",
            "key_scheme": key_rec.algorithm if key_rec else "3DES_2KEY (Variant LMK)",
            "key_usage": key_rec.key_usage if key_rec else "OPERATIONAL",
            "kvc": key_rec.kvc if key_rec else "N/A",
            "hsm_key_reference": key_rec.hsm_key_reference if key_rec else "LMK_PROTECTED",
            "cryptographic_result": op.response_status,
            "hsm_response_code": op.error_code,
            "hsm_processing_status": "COMPLETED" if op.error_code == "00" else "DECLINED_OR_ERROR",
            "request_timestamp": op.created_at.isoformat() if op.created_at else None,
            "response_timestamp": op.created_at.isoformat() if op.created_at else None,
            "duration_ms": op.duration_ms,
            "sanitized_request": _mask_crypto_dict(op.sanitized_request),
            "sanitized_response": _mask_crypto_dict(op.sanitized_response),
        })

    return {
        "transaction_id": tx.id,
        "transaction_reference": tx.transaction_reference,
        "hsm_provider": "Thales payShield 10K Soft-HSM",
        "hsm_mode": settings.HSM_MODE,
        "operations_count": len(operations_out),
        "operations": operations_out,
    }


def _build_or_load_trace_events(db: Session, tx: Transaction, persist_if_missing: bool = False) -> List[Dict[str, Any]]:
    """
    Retrieves actual recorded TransactionTraceEvent records for `tx`.
    If `tx` was created before `TransactionTraceEvent` existed, reconstructs the trace strictly
    from the transaction's actual persisted `TransactionCheck`, `HsmOperation`, and `AccountLedger`
    rows — NEVER re-executing authorization, HSM, or ledger processing, and NEVER fabricating stages
    that did not run.
    """
    stored_events = (
        db.query(TransactionTraceEvent)
        .filter(TransactionTraceEvent.transaction_id == tx.id)
        .order_by(TransactionTraceEvent.event_order.asc())
        .all()
    )
    if stored_events:
        return [
            {
                "event_id": ev.id,
                "transaction_id": ev.transaction_id,
                "correlation_id": ev.correlation_id or tx.transaction_reference,
                "event_order": ev.event_order,
                "event_code": ev.event_code,
                "event_category": ev.event_category,
                "event_name": ev.event_name,
                "event_status": ev.event_status,
                "response_code": ev.response_code,
                "duration_ms": ev.duration_ms,
                "message": ev.message,
                "event_timestamp": ev.event_timestamp.isoformat() if ev.event_timestamp else tx.created_at.isoformat(),
            }
            for ev in stored_events
        ]

    # Reconstruct strictly from actual persisted TransactionCheck rows
    checks = (
        db.query(TransactionCheck)
        .filter(TransactionCheck.transaction_id == tx.id)
        .order_by(TransactionCheck.check_order.asc())
        .all()
    )
    base_ts = tx.created_at or datetime.now(timezone.utc)
    elapsed_ms = 0
    reconstructed: List[Dict[str, Any]] = []

    def _add_ev(order: int, code: str, cat: str, name: str, status: str, rc: str, dur: int, msg: str):
        nonlocal elapsed_ms
        ev_ts = base_ts + timedelta(milliseconds=elapsed_ms)
        elapsed_ms += max(1, dur)
        reconstructed.append({
            "event_id": f"TRC-{tx.id[:8]}-{order:02d}",
            "transaction_id": tx.id,
            "correlation_id": tx.correlation_id or tx.transaction_reference,
            "event_order": order,
            "event_code": code,
            "event_category": cat,
            "event_name": name,
            "event_status": status,
            "response_code": rc,
            "duration_ms": max(1, dur),
            "message": msg,
            "event_timestamp": ev_ts.isoformat(),
        })

    order_idx = 1
    _add_ev(
        order_idx,
        "TRANSACTION_RECEIVED",
        "INGRESS",
        "TRANSACTION RECEIVED",
        "PASSED",
        "00",
        1,
        f"Incoming MTI {tx.mti} transaction {tx.transaction_reference} received from {tx.source_channel}.",
    )

    for c in checks:
        order_idx += 1
        cname_up = c.check_name.upper()
        cat = "VALIDATION"
        if "MESSAGE" in cname_up:
            cat = "PARSING"
        elif "ROUTING" in cname_up or "NETWORK" in cname_up:
            cat = "ROUTING"
        elif "HSM" in cname_up or "PIN" in cname_up or "CVV" in cname_up or "EMV" in cname_up or "MAC" in cname_up:
            cat = "HSM_CRYPTO"
        elif "LIMIT" in cname_up:
            cat = "LIMITS"
        elif "RULE" in cname_up:
            cat = "RISK_RULE"
        elif "BALANCE" in cname_up or "DECISION" in cname_up:
            cat = "AUTHORIZATION"
        elif "LEDGER" in cname_up:
            cat = "LEDGER"

        _add_ev(
            order_idx,
            cname_up.replace(" ", "_")[:50],
            cat,
            cname_up,
            c.check_status,
            c.response_code,
            c.duration_ms or 1,
            c.message,
        )

    order_idx += 1
    _add_ev(
        order_idx,
        "RESPONSE_GENERATION",
        "EGRESS",
        "RESPONSE GENERATION",
        "PASSED",
        tx.response_code,
        1,
        f"ISO 8583 / TIC response generated (RC={tx.response_code}: {tx.response_message}).",
    )
    order_idx += 1
    _add_ev(
        order_idx,
        "TRANSACTION_COMPLETED",
        "COMPLETION",
        "TRANSACTION COMPLETED",
        _resolve_display_status(tx),
        tx.response_code,
        1,
        f"Final response delivered ({_resolve_display_status(tx)}).",
    )

    if persist_if_missing:
        for item in reconstructed:
            db.add(
                TransactionTraceEvent(
                    transaction_id=tx.id,
                    correlation_id=item["correlation_id"],
                    event_order=item["event_order"],
                    event_code=item["event_code"],
                    event_category=item["event_category"],
                    event_name=item["event_name"],
                    event_status=item["event_status"],
                    response_code=item["response_code"],
                    duration_ms=item["duration_ms"],
                    message=item["message"],
                    event_timestamp=datetime.fromisoformat(item["event_timestamp"]),
                )
            )
        db.commit()

    return reconstructed


def _format_switch_trace_text(tx: Transaction, events: List[Dict[str, Any]]) -> str:
    total_ms = sum(e.get("duration_ms", 1) for e in events)
    final_status = _resolve_display_status(tx)
    lines = [
        "=" * 60,
        "TRANSACTION PROCESSING TRACE",
        "=" * 60,
        "",
        f"Transaction ID : {tx.transaction_reference}",
        f"Internal UUID  : {tx.id}",
        f"Correlation ID : {tx.correlation_id or tx.transaction_reference}",
        f"MTI            : {tx.mti}",
        f"STAN           : {tx.stan}",
        f"RRN            : {tx.rrn}",
        f"Masked PAN     : {strict_mask_pan(tx.masked_pan)}",
        f"Amount         : {tx.transaction_amount:.2f} {tx.currency}",
        f"Switch / Route : {tx.ps_code} ({'ON-US' if tx.is_on_us else 'OFF-US'})",
        "",
    ]
    for ev in events:
        try:
            dt = datetime.fromisoformat(ev["event_timestamp"].replace("Z", "+00:00"))
            ts_str = dt.strftime("%H:%M:%S.%f")[:-3]
        except Exception:
            ts_str = ev["event_timestamp"]
        lines.append("-" * 60)
        lines.append(f"{ts_str} | {ev['event_name']} [{ev['event_status']}] ({ev['duration_ms']} ms)")
        lines.append("-" * 60)
        lines.append(f"{ev['message']}")
        lines.append("")

    lines.extend([
        "=" * 60,
        f"FINAL STATUS: {final_status} (RC {tx.response_code} — {tx.response_message})",
        f"TOTAL PROCESSING TIME: {total_ms} MS",
        "=" * 60,
    ])
    return "\n".join(lines)


@router.get("/{transaction_id}/trace")
def get_transaction_trace(
    transaction_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    """TAB 5 — PROCESSING TRACE (Read-only retrieval of recorded trace events)."""
    tx = _get_tx_or_404(db, transaction_id)
    events = _build_or_load_trace_events(db, tx, persist_if_missing=False)
    formatted_text = _format_switch_trace_text(tx, events)
    total_ms = sum(e.get("duration_ms", 1) for e in events)
    return {
        "transaction_id": tx.id,
        "transaction_reference": tx.transaction_reference,
        "correlation_id": tx.correlation_id or tx.transaction_reference,
        "mti": tx.mti,
        "stan": tx.stan,
        "rrn": tx.rrn,
        "final_status": _resolve_display_status(tx),
        "response_code": tx.response_code,
        "response_message": tx.response_message,
        "total_duration_ms": total_ms,
        "events": events,
        "formatted_trace": formatted_text,
    }


@router.post("/{transaction_id}/trace/generate")
def generate_or_load_transaction_trace(
    transaction_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    """
    Explicit [ Generate / Load Transaction Trace ] button action.
    Loads actual recorded events (and persists reconstructed events from TransactionCheck if legacy),
    NEVER re-executing authorization, HSM, or ledger posting.
    """
    tx = _get_tx_or_404(db, transaction_id)
    events = _build_or_load_trace_events(db, tx, persist_if_missing=True)
    formatted_text = _format_switch_trace_text(tx, events)
    total_ms = sum(e.get("duration_ms", 1) for e in events)
    return {
        "transaction_id": tx.id,
        "transaction_reference": tx.transaction_reference,
        "correlation_id": tx.correlation_id or tx.transaction_reference,
        "mti": tx.mti,
        "stan": tx.stan,
        "rrn": tx.rrn,
        "final_status": _resolve_display_status(tx),
        "response_code": tx.response_code,
        "response_message": tx.response_message,
        "total_duration_ms": total_ms,
        "events": events,
        "formatted_trace": formatted_text,
    }


@router.get("/{transaction_id}/trace/export")
def export_transaction_trace_txt(
    transaction_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    tx = _get_tx_or_404(db, transaction_id)
    events = _build_or_load_trace_events(db, tx, persist_if_missing=False)
    formatted_text = _format_switch_trace_text(tx, events)
    fname = f"trace_{tx.transaction_reference}_{tx.rrn}.txt"
    return Response(
        content=formatted_text.encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/{transaction_id}/related")
def get_related_transactions(
    transaction_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    """
    TAB 6 — RELATED TRANSACTIONS:
    Links Original Authorizations, Reversals (0400/0420), Financial Advices (0220),
    and Duplicate Transmissions using reliable keys (original_transaction_id, TransactionReversal,
    RRN, STAN+RRN, and Correlation ID) — never linking by equal amount alone.
    """
    tx = _get_tx_or_404(db, transaction_id)
    related_map: Dict[str, Dict[str, Any]] = {}

    def _register(rel_tx: Optional[Transaction], relationship_type: str, link_basis: str):
        if not rel_tx or rel_tx.id == tx.id:
            return
        if rel_tx.id not in related_map:
            row = _serialize_tx_list_row(rel_tx)
            row["relationship_type"] = relationship_type
            row["link_basis"] = link_basis
            related_map[rel_tx.id] = row

    # 1. Explicit original_transaction_id parent
    if tx.original_transaction_id:
        orig = db.query(Transaction).filter(Transaction.id == tx.original_transaction_id).first()
        _register(orig, "ORIGINAL_AUTHORIZATION", "Explicit original_transaction_id FK")

    # 2. Explicit child transactions pointing to this transaction as original
    children = db.query(Transaction).filter(Transaction.original_transaction_id == tx.id).all()
    for ch in children:
        rel_label = "REVERSAL" if (ch.mti or "").startswith("04") else "LINKED_FOLLOW_UP"
        _register(ch, rel_label, "Explicit original_transaction_id FK")

    # 3. TransactionReversal table links
    rev_links = (
        db.query(TransactionReversal)
        .filter(
            or_(
                TransactionReversal.original_transaction_id == tx.id,
                TransactionReversal.reversal_transaction_id == tx.id,
            )
        )
        .all()
    )
    for rl in rev_links:
        if rl.original_transaction_id != tx.id:
            o_tx = db.query(Transaction).filter(Transaction.id == rl.original_transaction_id).first()
            _register(o_tx, "ORIGINAL_AUTHORIZATION", f"Reversal Registry (RRN {rl.original_rrn})")
        if rl.reversal_transaction_id != tx.id:
            r_tx = db.query(Transaction).filter(Transaction.id == rl.reversal_transaction_id).first()
            _register(r_tx, "REVERSAL", f"Reversal Registry ({rl.reversal_reason})")

    # 4. Same RRN (Advices 0220, Reversals 0400/0420, Duplicate Transmissions RC 94)
    if tx.rrn:
        same_rrn = db.query(Transaction).filter(Transaction.rrn == tx.rrn, Transaction.id != tx.id).all()
        for sr in same_rrn:
            if sr.response_code == "94":
                r_type = "DUPLICATE_TRANSMISSION"
                basis = f"Identical STAN {sr.stan} / RRN {sr.rrn} (RC 94)"
            elif (sr.mti or "").startswith("04"):
                r_type = "REVERSAL"
                basis = f"Matching RRN {sr.rrn}"
            elif sr.mti == "0220":
                r_type = "CLEARING_ADVICE_0220"
                basis = f"Matching RRN {sr.rrn}"
            elif sr.mti in ("0100", "0200"):
                r_type = "ORIGINAL_AUTHORIZATION"
                basis = f"Matching RRN {sr.rrn}"
            else:
                r_type = "RELATED_BY_RRN"
                basis = f"Matching RRN {sr.rrn}"
            _register(sr, r_type, basis)

    # 5. Same Correlation ID (if shared across multi-leg switch operations)
    if tx.correlation_id:
        same_corr = (
            db.query(Transaction)
            .filter(Transaction.correlation_id == tx.correlation_id, Transaction.id != tx.id)
            .all()
        )
        for sc in same_corr:
            _register(sc, "CORRELATED_LEG", f"Correlation ID {tx.correlation_id}")

    related_list = sorted(related_map.values(), key=lambda x: x["created_at"])
    return {
        "transaction_id": tx.id,
        "transaction_reference": tx.transaction_reference,
        "rrn": tx.rrn,
        "stan": tx.stan,
        "related_count": len(related_list),
        "related_transactions": related_list,
    }


@router.get("/{transaction_id}/package")
def download_investigation_package(
    transaction_id: str,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Downloads a complete, sanitized JSON investigation dossier for support teams."""
    general = get_transaction_general_detail(transaction_id, reveal_pan=False, db=db, _=current_user)
    auth = get_transaction_authorization_detail(transaction_id, db=db, _=current_user)
    iso = get_transaction_iso_messages(transaction_id, db=db, _=current_user)
    crypto = get_transaction_crypto_detail(transaction_id, db=db, _=current_user)
    trace = get_transaction_trace(transaction_id, db=db, _=current_user)
    related = get_related_transactions(transaction_id, db=db, _=current_user)

    dossier = {
        "package_metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generated_by": current_user,
            "application": settings.APP_NAME,
            "security_policy": "PCI-DSS Sanitized (PAN Masked, PIN/CVV/Keys Redacted)",
        },
        "general": general,
        "authorizer_response": auth,
        "iso_messages_and_comparison": iso,
        "keys_and_crypto": crypto,
        "processing_trace": trace,
        "related_transactions": related,
    }
    ref = general["summary"]["transaction_reference"]
    content = json.dumps(dossier, indent=2, default=str).encode("utf-8")
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="investigation_{ref}.json"'},
    )


# [PATCH tx_log_viewer_v3:column_preferences_and_incremental_poll]
DEFAULT_TX_LOG_COLUMNS = [
    "transaction_reference",
    "date",
    "time",
    "mti",
    "transaction_type",
    "mcc",
    "terminal_id",
    "terminal_name",
    "terminal_owner",
    "issuer_code",
    "acquirer_code",
    "ps_code",
    "masked_pan",
    "amount",
    "currency",
    "response_code",
    "response_description",
    "approval_code",
    "rrn",
    "stan",
    "status",
]


@router.get("/preferences/columns")
def get_user_column_preferences(
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    from app.models import HostParameter
    param_name = f"TX_LOG_VIEWER_COLUMNS_{current_user.upper()}"
    param = (
        db.query(HostParameter)
        .filter(
            HostParameter.parameter_group == "UI_PREFERENCES",
            HostParameter.parameter_name == param_name,
        )
        .first()
    )
    if param and isinstance(param.parameter_value, dict) and "columns" in param.parameter_value:
        return {"columns": param.parameter_value["columns"], "default_columns": DEFAULT_TX_LOG_COLUMNS}
    return {"columns": DEFAULT_TX_LOG_COLUMNS, "default_columns": DEFAULT_TX_LOG_COLUMNS}


@router.put("/preferences/columns")
def save_user_column_preferences(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    from app.models import HostParameter
    cols = payload.get("columns")
    if not isinstance(cols, list) or len(cols) == 0:
        raise HTTPException(status_code=400, detail="At least one column must be selected")
    param_name = f"TX_LOG_VIEWER_COLUMNS_{current_user.upper()}"
    param = (
        db.query(HostParameter)
        .filter(
            HostParameter.parameter_group == "UI_PREFERENCES",
            HostParameter.parameter_name == param_name,
        )
        .first()
    )
    if param:
        param.parameter_value = {"columns": cols, "updated_at": datetime.now(timezone.utc).isoformat()}
    else:
        param = HostParameter(
            parameter_group="UI_PREFERENCES",
            parameter_name=param_name,
            parameter_value={"columns": cols, "updated_at": datetime.now(timezone.utc).isoformat()},
            description=f"Saved Transaction Log Viewer column preferences for {current_user}",
            active=True,
        )
        db.add(param)
    db.commit()
    return {"status": "saved", "columns": cols}
