"""
MODULE 4 — api_routes.py
FastAPI endpoints for authentication, dashboard analytics, customers, accounts, cards,
limits, configurable transaction codes, TIC/ISO Transaction Simulator, HSM Key Management,
HSM Workbench, Host Execution Monitor (REST + WebSocket), and system logs.
"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db
from app.host_engine import HostTransactionProcessor
from app.hsm_adapter import HSMAdapter, SoftHsmCryptoCore
from app.iso_tic import build_tic_message, decode_tic_message, get_field_catalog, validate_tic_fields
# [PATCH step09:api_routes_iso_standard_codec_import]
from app.iso_standard_codec import decode_iso8583_1987, build_iso8583_1987
from app.logging_service import monitor_hub, record_system_log
# [PATCH step03_01:api_routes_audit_imports]
from app.audit_service import record_audit, serialize_entity
from app.customer_360 import customer_profile_fields
# [PATCH step12:api_routes_settlement_service_import]
from app.settlement_service import execute_daily_cutover, get_reconciliation_summary
# [PATCH step10:api_routes_ceremony_service_import]
from app.key_ceremony_service import (
    assemble_components,
    export_key_under_zmk,
    generate_random_des_key,
    import_key_under_zmk,
)
# [PATCH step08:api_routes_rules_evaluator_import]
from app.rules_evaluator import SafeAstEvaluator
# [PATCH step11:api_routes_network_adapter_fn]
from app.network_adapter import SimulatedNetworkAdapter, resolve_transaction_routing
# [PATCH step06:api_routes_crypto_service_import]
from app.card_crypto_service import (
    calculate_cvv_detailed,
    calculate_ibm_offset_detailed,
    calculate_visa_pvv_detailed,
    generate_luhn_pan,
    pack_pin_block_detailed,
)
from app.models import (
    utc_now,
# [PATCH step12:api_routes_settlement_models]
    SettlementBatch,
    SettlementEntry,
    SettlementPosition,
# [PATCH step11:api_routes_network_adapter_import]
    NetworkProfile,
# [PATCH step08:api_routes_rules_imports]
    AuthorizerRule,
# [PATCH step07:api_routes_timeline_imports]
    ApiAuditLog,
    CryptoEvent,
# [PATCH step02_01:api_routes_inst_imports]
    BinRange,
    Institution,
    ProcessingSystem,
    Account,
    AccountLedger,
    AccountLimit,
# [PATCH step03_01:api_routes_audit_model_import]
    AuditTrail,
    Card,
    CardAccount,
    CardLimit,
    CardProfile,
    Customer,
    EmvProfile,
    HostParameter,
    HsmAuditLog,
    HsmKeyReference,
    HsmOperation,
    Notification,
    PinProfile,
    ResponseCode,
    SystemLog,
    Transaction,
    TransactionCheck,
    TransactionCode,
    TransactionCodeField,
    TransactionMessage,
)
from app.schemas import (
    PaginatedResponse,
# [PATCH step12:api_routes_settlement_schemas]
    BatchCutoverRequest,
    ReconciliationReportOut,
    SettlementBatchOut,
    SettlementPositionOut,
# [PATCH step11:api_routes_network_schemas]
    NetworkProfileUpdate,
    NetworkRouteLookupRequest,
# [PATCH step10:api_routes_ceremony_schemas]
    KeyAssemblyRequest,
    KeyCeremonyResultOut,
    KeyExportUnderZmkRequest,
    KeyImportUnderZmkRequest,
    RandomKeyGenerateRequest,
# [PATCH step09:api_routes_iso_imports]
    RawMessageParseRequest,
    RawMessageParseResponse,
# [PATCH step08:api_routes_rules_schemas]
    AuthorizerRuleCreate,
    AuthorizerRuleOut,
    AuthorizerRuleUpdate,
    RuleDryRunRequest,
    RuleDryRunResponse,
# [PATCH api_routes_import_limit_reset_schemas]
# [PATCH step06:api_routes_crypto_imports]
    CardGenerateRequest,
    CardPinChangeRequest,
    CvvCalculateRequest,
    PinBlockPackRequest,
    PvvCalculateRequest,
    LimitUsageResetRequest,
    LimitUsageResetOut,
    AccountCreate,
    AccountLimitUpdate,
    AccountOut,
# [PATCH step03_01:api_routes_audit_schema_import]
    AccountUpdate,
    AuditTrailOut,
    CardUpdate,
# [PATCH step04:api_routes_schema_imports]
    CardAccountLinkCreate,
    CardAccountLinkOut,
    CardAccountLinkUpdate,
# [PATCH step03_02:api_routes_more_schemas]
    CardProfileCreate,
    CardProfileOut,
    CardProfileUpdate,
    HsmKeyReferenceUpdate,
    CustomerUpdate,
    CardCreate,
    CardLimitUpdate,
    CardOut,
    CustomerCreate,
    CustomerOut,
    HsmKeyReferenceCreate,
    HsmKeyReferenceOut,
    HsmWorkbenchRequest,
    LoginRequest,
    SimulatorBuildRequest,
    SimulatorSubmitRequest,
    TokenResponse,
    TransactionCodeCreate,
    TransactionCodeOut,
)
from app.security import (
    ADMIN_HASH,
    create_access_token,
    get_current_user,
    mask_pan,
    mask_raw_tic_message,
    tokenize_pan,
    verify_password,
)

router = APIRouter(prefix="/api")


# ==============================================================================
# 1. AUTHENTICATION & SYSTEM STATUS
# ==============================================================================

@router.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest):
    if payload.username != settings.ADMIN_USERNAME or not verify_password(payload.password, ADMIN_HASH):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_access_token(subject=payload.username)
    return TokenResponse(
        access_token=token,
        username=payload.username,
        hsm_mode=settings.HSM_MODE,
    )


@router.get("/dashboard/summary")
def get_dashboard_summary(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    total_customers = db.query(func.count(Customer.id)).scalar() or 0
    active_cards = db.query(func.count(Card.id)).filter(Card.card_status == "ACTIVE").scalar() or 0
    active_accounts = db.query(func.count(Account.id)).filter(Account.account_status == "ACTIVE").scalar() or 0
    total_tx = db.query(func.count(Transaction.id)).scalar() or 0
    approved_tx = db.query(func.count(Transaction.id)).filter(Transaction.authorization_status == "APPROVED").scalar() or 0
    declined_tx = db.query(func.count(Transaction.id)).filter(Transaction.authorization_status == "DECLINED").scalar() or 0
    reversed_tx = db.query(func.count(Transaction.id)).filter(Transaction.transaction_status == "REVERSED").scalar() or 0
    total_vol = db.query(func.sum(Transaction.transaction_amount)).filter(Transaction.authorization_status == "APPROVED").scalar() or Decimal("0.00")

    recent_tx = (
        db.query(Transaction)
        .order_by(Transaction.created_at.desc())
        .limit(8)
        .all()
    )
    recent_hsm = (
        db.query(HsmOperation)
        .order_by(HsmOperation.created_at.desc())
        .limit(6)
        .all()
    )
    recent_logs = (
        db.query(SystemLog)
        .order_by(SystemLog.created_at.desc())
        .limit(8)
        .all()
    )
# [PATCH step03_01:api_audit_trail_list]


    approval_rate = round((approved_tx / total_tx) * 100, 1) if total_tx > 0 else 100.0

    return {
        "metrics": {
            "total_customers": total_customers,
            "active_cards": active_cards,
            "active_accounts": active_accounts,
            "total_transactions": total_tx,
            "approved_transactions": approved_tx,
            "declined_transactions": declined_tx,
            "reversed_transactions": reversed_tx,
            "approval_rate": approval_rate,
            "transaction_volume": float(total_vol),
            "hsm_mode": settings.HSM_MODE,
        },
        "recent_transactions": [
            {
                "id": t.id,
                "transaction_reference": t.transaction_reference,
                "mti": t.mti,
                "transaction_code": t.transaction_code,
                "masked_pan": t.masked_pan,
                "amount": float(t.transaction_amount),
                "currency": t.currency,
                "response_code": t.response_code,
                "response_message": t.response_message,
                "authorization_status": t.authorization_status,
                "transaction_status": t.transaction_status,
                "stan": t.stan,
                "rrn": t.rrn,
                "created_at": t.created_at.isoformat(),
            }
            for t in recent_tx
        ],
        "recent_hsm_operations": [
            {
                "id": h.id,
                "operation_type": h.operation_type,
                "request_reference": h.request_reference,
                "response_status": h.response_status,
                "error_code": h.error_code,
                "duration_ms": h.duration_ms,
                "created_at": h.created_at.isoformat(),
            }
            for h in recent_hsm
        ],
        "recent_events": [
            {
                "id": l.id,
                "severity": l.severity,
                "component": l.component,
                "event_name": l.event_name,
                "message": l.message,
                "created_at": l.created_at.isoformat(),
            }
            for l in recent_logs
        ],
    }


# ==============================================================================
# 2. CUSTOMERS, ACCOUNTS, CARDS & LIMITS
# ==============================================================================

# [PATCH api_routes_customer_crud_and_safe_delete]
def _short_bank_code(inst: Optional[Institution], fallback: str = "XBANK") -> str:
    if not inst:
        return fallback
    raw = (inst.short_name or inst.institution_code or fallback).strip()
    for sep in (" - ", " — ", " – ", "/"):
        if sep in raw:
            part = raw.split(sep)[0].strip()
            if part:
                return part.upper()
    return raw.upper()


@router.get("/customers")
def list_customers(
    q: Optional[str] = Query(None),
    institution_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: Optional[int] = Query(None, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    query = db.query(Customer)
    if q:
        term = f"%{q.strip()}%"
        query = query.filter(
            (Customer.customer_number.ilike(term))
            | (Customer.first_name.ilike(term))
            | (Customer.last_name.ilike(term))
            | (Customer.email.ilike(term))
            | (Customer.mobile_number.ilike(term))
        )
    if institution_id:
        query = query.filter(Customer.institution_id == institution_id)
    if status:
        query = query.filter(Customer.customer_status == status.upper().strip())
    total = query.count()
    pg = page or 1
    custs = query.order_by(Customer.created_at.desc()).offset((pg - 1) * page_size).limit(page_size).all()
    items = []
    for c in custs:
        d = CustomerOut.model_validate(c).model_dump()
        d["institution_id"] = c.institution_id
        d["institution_code"] = _short_bank_code(c.institution, "XBANK")
        d["institution_name"] = c.institution.name if c.institution else "xBank PLC"
        d["account_count"] = db.query(Account).filter(Account.customer_id == c.id).count()
        d["card_count"] = db.query(Card).filter(Card.customer_id == c.id).count()
        items.append(d)
    total_pages = max(1, (total + page_size - 1) // page_size)
    return {"items": items, "total": total, "page": pg, "page_size": page_size, "total_pages": total_pages}


@router.get("/customers/{customer_id}")
def get_customer_details(customer_id: str, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    cust = db.query(Customer).filter(Customer.id == customer_id).first()
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    d = CustomerOut.model_validate(cust).model_dump()
    d["institution_id"] = cust.institution_id
    d["institution_code"] = _short_bank_code(cust.institution, "XBANK")
    d["institution_name"] = cust.institution.name if cust.institution else "xBank PLC"
    d["account_count"] = db.query(Account).filter(Account.customer_id == cust.id).count()
    d["card_count"] = db.query(Card).filter(Card.customer_id == cust.id).count()
    d["transaction_count"] = db.query(Transaction).filter(Transaction.customer_id == cust.id).count()
    return d


@router.post("/customers", response_model=CustomerOut)
def create_customer(
    payload: CustomerCreate,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    cnum = payload.customer_number.strip()
    if not cnum:
        raise HTTPException(status_code=400, detail="Customer number is required")
    existing = db.query(Customer).filter(Customer.customer_number == cnum).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Customer number '{cnum}' already exists")

    data = payload.model_dump()
    data["customer_number"] = cnum
    data["first_name"] = payload.first_name.strip()
    if not data.get("institution_id"):
        xbank = db.query(Institution).filter(Institution.institution_code == "XBANK").first()
        if xbank:
            data["institution_id"] = xbank.id
    cust = Customer(**data)
    db.add(cust)
    db.flush()
    record_system_log(db, "INFO", "CustomerService", "CUSTOMER_CREATED", f"Created customer {cust.customer_number}")
    record_audit(
        db,
        "CUSTOMER",
        cust.id,
        "CREATE",
        performed_by=current_user,
        after_state=serialize_entity(cust),
        change_summary=f"Created customer {cust.customer_number}",
    )
    db.commit()
    db.refresh(cust)
    cust.institution_code = _short_bank_code(cust.institution, "XBANK")
    cust.institution_name = cust.institution.name if cust.institution else "xBank PLC"
    return cust


@router.patch("/customers/{customer_id}/status")
def update_customer_status(
    customer_id: str,
    status: str,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    cust = db.query(Customer).filter(Customer.id == customer_id).first()
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    before = serialize_entity(cust)
    cust.customer_status = status.upper().strip()
    after = serialize_entity(cust)
    record_audit(
        db,
        "CUSTOMER",
        cust.id,
        "STATUS_CHANGE",
        performed_by=current_user,
        before_state=before,
        after_state=after,
        change_summary=f"Changed customer {cust.customer_number} status to {cust.customer_status}",
    )
    db.commit()
    return {"id": cust.id, "customer_status": cust.customer_status}


@router.put("/customers/{customer_id}", response_model=CustomerOut)
def update_customer(
    customer_id: str,
    payload: CustomerUpdate,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    cust = db.query(Customer).filter(Customer.id == customer_id).first()
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    before = serialize_entity(cust)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(cust, k, v)
    after = serialize_entity(cust)
    record_audit(
        db,
        "CUSTOMER",
        cust.id,
        "UPDATE",
        performed_by=current_user,
        before_state=before,
        after_state=after,
        change_summary=f"Updated customer {cust.customer_number}",
    )
    db.commit()
    db.refresh(cust)
    cust.institution_code = _short_bank_code(cust.institution, "XBANK")
    cust.institution_name = cust.institution.name if cust.institution else "xBank PLC"
    return cust


@router.delete("/customers/{customer_id}")
def delete_customer(
    customer_id: str,
    force: bool = Query(False, description="Force delete only for lab test records"),
    archive: bool = Query(False, description="Safely deactivate/archive customer and block linked cards"),
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    cust = db.query(Customer).filter(Customer.id == customer_id).first()
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")

    accts = db.query(Account).filter(Account.customer_id == cust.id).all()
    cards = db.query(Card).filter(Card.customer_id == cust.id).all()
    acct_ids = [a.id for a in accts]
    card_ids = [c.id for c in cards]

    tx_count = db.query(Transaction).filter(
        (Transaction.customer_id == cust.id)
        | (Transaction.account_id.in_(acct_ids) if acct_ids else False)
        | (Transaction.card_id.in_(card_ids) if card_ids else False)
    ).count()
    ledger_count = (
        db.query(AccountLedger).filter(AccountLedger.account_id.in_(acct_ids)).count()
        if acct_ids else 0
    )

    # Safe Archive / Deactivate workflow when customer has financial history or active relationships
    if archive:
        before = serialize_entity(cust)
        cust.customer_status = "ARCHIVED"
        for c in cards:
            c.card_status = "BLOCKED"
        for a in accts:
            if a.account_status == "ACTIVE":
                a.account_status = "INACTIVE"
        after = serialize_entity(cust)
        record_audit(
            db,
            "CUSTOMER",
            cust.id,
            "ARCHIVE",
            performed_by=current_user,
            before_state=before,
            after_state=after,
            change_summary=(
                f"Archived customer {cust.customer_number} and deactivated {len(cards)} card(s) / "
                f"{len(accts)} account(s) to preserve {tx_count} transaction(s) and {ledger_count} ledger record(s)."
            ),
        )
        db.commit()
        return {
            "status": "archived",
            "customer_id": cust.id,
            "customer_number": cust.customer_number,
            "customer_status": cust.customer_status,
            "message": (
                f"Customer {cust.customer_number} has been safely archived/deactivated to preserve "
                f"financial history ({len(accts)} accounts, {len(cards)} cards, {tx_count} transactions)."
            ),
        }

    if not force and (accts or cards or tx_count > 0 or ledger_count > 0):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot hard-delete customer {cust.customer_number} because they have "
                f"{len(accts)} account(s), {len(cards)} card(s), {tx_count} transaction(s), "
                f"and {ledger_count} ledger record(s). Choose 'Archive / Deactivate' to preserve "
                f"financial audit history, or confirm lab force-deletion."
            ),
        )

    # If force=True (or no dependencies exist), safely detach all FK references inside a single transaction
    before = serialize_entity(cust)
    db.query(Transaction).filter(Transaction.customer_id == cust.id).update(
        {"customer_id": None}, synchronize_session=False
    )
    if card_ids:
        db.query(Transaction).filter(Transaction.card_id.in_(card_ids)).update(
            {"card_id": None}, synchronize_session=False
        )
        db.query(CardAccount).filter(CardAccount.card_id.in_(card_ids)).delete(synchronize_session=False)
        db.query(CardLimit).filter(CardLimit.card_id.in_(card_ids)).delete(synchronize_session=False)
        db.query(PinProfile).filter(PinProfile.card_id.in_(card_ids)).delete(synchronize_session=False)
        db.query(EmvProfile).filter(EmvProfile.card_id.in_(card_ids)).delete(synchronize_session=False)
        db.query(Card).filter(Card.id.in_(card_ids)).delete(synchronize_session=False)

    if acct_ids:
        db.query(Card).filter(Card.linked_account_id.in_(acct_ids)).update(
            {"linked_account_id": None}, synchronize_session=False
        )
        db.query(Transaction).filter(Transaction.account_id.in_(acct_ids)).update(
            {"account_id": None}, synchronize_session=False
        )
        db.query(CardAccount).filter(CardAccount.account_id.in_(acct_ids)).delete(synchronize_session=False)
        db.query(AccountLedger).filter(AccountLedger.account_id.in_(acct_ids)).delete(synchronize_session=False)
        db.query(AccountLimit).filter(AccountLimit.account_id.in_(acct_ids)).delete(synchronize_session=False)
        db.query(Account).filter(Account.id.in_(acct_ids)).delete(synchronize_session=False)

    db.delete(cust)
    record_audit(
        db,
        "CUSTOMER",
        customer_id,
        "DELETE",
        performed_by=current_user,
        before_state=before,
        change_summary=f"Deleted customer {cust.customer_number} (Force: {force})",
    )
    db.commit()
    return {"status": "deleted", "customer_id": customer_id, "customer_number": cust.customer_number}


# [PATCH step05:api_accounts_paginated_fixed]
@router.get('/accounts')
def list_accounts(
    q: Optional[str] = Query(None, description='Search by account number or branch code'),
    account_type: Optional[str] = Query(None),
    institution_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    query = db.query(Account)
    if q:
        term = f'%{q.strip()}%'
        query = query.filter((Account.account_number.ilike(term)) | (Account.branch_code.ilike(term)))
    if account_type:
        query = query.filter(Account.account_type == account_type.upper())
    if institution_id:
        query = query.filter(Account.institution_id == institution_id)
    if status:
        query = query.filter(Account.account_status == status.upper())
    total = query.count()
    accounts = query.order_by(Account.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    out = []
    for a in accounts:
        lim = db.query(AccountLimit).filter(AccountLimit.account_id == a.id).first()
        out.append({
            'id': a.id,
            'account_number': a.account_number,
            'customer_id': a.customer_id,
            'customer_name': f"{a.customer.first_name} {a.customer.last_name or ''}".strip() if a.customer else '',
            'account_type': a.account_type,
            'currency': a.currency,
            'available_balance': float(a.available_balance),
            'ledger_balance': float(a.ledger_balance),
            'overdraft_limit': float(a.overdraft_limit),
            'account_status': a.account_status,
            'branch_code': a.branch_code,
# [PATCH api_routes_accounts_short_bank_code]
            'institution_id': a.institution_id,
            'institution_code': _short_bank_code(a.institution, 'XBANK'),
            'institution_name': a.institution.name if a.institution else None,
            'limits': {
                'id': lim.id,
                'per_transaction_limit': float(lim.per_transaction_limit),
                'daily_limit': float(lim.daily_limit),
                'weekly_limit': float(lim.weekly_limit),
                'monthly_limit': float(lim.monthly_limit),
                'daily_used': float(lim.daily_used),
                'weekly_used': float(lim.weekly_used),
                'monthly_used': float(lim.monthly_used),
            } if lim else None,
        })
    total_pages = max(1, (total + page_size - 1) // page_size)
    return {'items': out, 'total': total, 'page': page, 'page_size': page_size, 'total_pages': total_pages}


@router.post("/accounts", response_model=AccountOut)
def create_account(payload: AccountCreate, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
# [PATCH step02_01:api_account_create_inst]
    data = payload.model_dump()
    if not data.get('institution_id'):
        xbank = db.query(Institution).filter(Institution.institution_code == 'XBANK').first()
        if xbank:
            data['institution_id'] = xbank.id
    acct = Account(**data)
    db.add(acct)
    db.flush()
    db.add(AccountLimit(account_id=acct.id, currency=acct.currency))
    record_system_log(db, "INFO", "AccountService", "ACCOUNT_CREATED", f"Created account {acct.account_number}")
    db.commit()
    db.refresh(acct)
    return acct


# [PATCH api_routes_account_limit_reset_usage]
@router.put("/accounts/{account_id}/limits")
def update_account_limits(
    account_id: str,
    payload: AccountLimitUpdate,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    acct = db.query(Account).filter(Account.id == account_id).first()
    if not acct:
        raise HTTPException(status_code=404, detail="Account not found")
    lim = db.query(AccountLimit).filter(AccountLimit.account_id == account_id).first()
    if not lim:
        lim = AccountLimit(account_id=account_id, currency=acct.currency)
        db.add(lim)
        db.flush()
    before = serialize_entity(lim)
    # Ordinary limit configuration editing ONLY updates maximum thresholds & status, NEVER resetting used counters
    lim.per_transaction_limit = payload.per_transaction_limit
    lim.daily_limit = payload.daily_limit
    lim.weekly_limit = payload.weekly_limit
    lim.monthly_limit = payload.monthly_limit
    lim.status = payload.status.upper().strip()
    after = serialize_entity(lim)
    record_audit(
        db,
        "ACCOUNT_LIMIT",
        lim.id,
        "UPDATE_CONFIG",
        performed_by=current_user,
        before_state=before,
        after_state=after,
        change_summary=f"Updated configured limit thresholds for account {acct.account_number}",
    )
    db.commit()
    return {"status": "updated", "account_id": account_id, "limits": after}


@router.post("/accounts/{account_id}/limits/reset-usage", response_model=LimitUsageResetOut)
def reset_account_limit_usage(
    account_id: str,
    payload: LimitUsageResetRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    if not payload.confirm_reset:
        raise HTTPException(status_code=400, detail="Explicit confirmation is required before resetting limit usage.")
    reason_clean = (payload.reason or "").strip()
    if len(reason_clean) < 3:
        raise HTTPException(status_code=400, detail="A valid testing reason or reference is required to reset limit usage.")

    acct = db.query(Account).filter(Account.id == account_id).first()
    if not acct:
        raise HTTPException(status_code=404, detail="Account not found")
    lim = db.query(AccountLimit).filter(AccountLimit.account_id == account_id).first()
    if not lim:
        lim = AccountLimit(account_id=account_id, currency=acct.currency)
        db.add(lim)
        db.flush()

    before = serialize_entity(lim)
    old_usage = {
        "daily_used": float(lim.daily_used or 0),
        "weekly_used": float(lim.weekly_used or 0),
        "monthly_used": float(lim.monthly_used or 0),
    }

    scope = (payload.scope or "ALL").upper().strip()
    if scope in ("DAILY", "ALL"):
        lim.daily_used = Decimal("0.00")
    if scope in ("WEEKLY", "ALL"):
        lim.weekly_used = Decimal("0.00")
    if scope in ("MONTHLY", "ALL"):
        lim.monthly_used = Decimal("0.00")
    lim.effective_from = utc_now()

    new_usage = {
        "daily_used": float(lim.daily_used or 0),
        "weekly_used": float(lim.weekly_used or 0),
        "monthly_used": float(lim.monthly_used or 0),
    }
    after = serialize_entity(lim)
    after["reset_reason"] = reason_clean
    after["testing_reference"] = payload.testing_reference

    record_audit(
        db,
        "ACCOUNT_LIMIT",
        lim.id,
        "RESET_LIMIT_USAGE",
        performed_by=current_user,
        before_state=before,
        after_state=after,
        change_summary=(
            f"Reset {scope} limit usage for account {acct.account_number} to 0.00 "
            f"(Old: {old_usage} -> New: {new_usage}) | Reason: {reason_clean} "
            f"| Ref: {payload.testing_reference or 'N/A'}"
        ),
    )
    record_system_log(
        db,
        "WARNING",
        "LimitEngine",
        "ACCOUNT_LIMIT_USAGE_RESET",
        f"Operator {current_user} reset {scope} usage on account {acct.account_number} (Reason: {reason_clean})",
        details={"old_usage": old_usage, "new_usage": new_usage, "reason": reason_clean, "testing_reference": payload.testing_reference},
    )
    db.commit()
    return LimitUsageResetOut(
        status="reset",
        entity_type="ACCOUNT_LIMIT",
        entity_id=lim.id,
        target_identifier=acct.account_number,
        scope=scope,
        performed_by=current_user,
        reason=reason_clean,
        testing_reference=payload.testing_reference,
        reset_at=utc_now(),
        old_usage=old_usage,
        new_usage=new_usage,
    )
# [PATCH step03_01:api_account_put_delete]


@router.put('/accounts/{account_id}', response_model=AccountOut)
def update_account(account_id: str, payload: AccountUpdate, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    acct = db.query(Account).filter(Account.id == account_id).first()
    if not acct:
        raise HTTPException(status_code=404, detail='Account not found')
    before = serialize_entity(acct)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(acct, k, v)
    after = serialize_entity(acct)
    record_audit(db, 'ACCOUNT', acct.id, 'UPDATE', performed_by=current_user, before_state=before, after_state=after,
                 change_summary=f'Updated account {acct.account_number}')
    db.commit()
    db.refresh(acct)
    return acct


@router.delete('/accounts/{account_id}')
def delete_account(account_id: str, force: bool = Query(True), db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    acct = db.query(Account).filter(Account.id == account_id).first()
    if not acct:
        raise HTTPException(status_code=404, detail='Account not found')
    before = serialize_entity(acct)
    # Safely detach or remove all foreign key references to prevent SQLite/Postgres IntegrityError (500)
    db.query(Card).filter(Card.linked_account_id == acct.id).update({'linked_account_id': None}, synchronize_session=False)
    db.query(Transaction).filter(Transaction.account_id == acct.id).update({'account_id': None}, synchronize_session=False)
    db.query(CardAccount).filter(CardAccount.account_id == acct.id).delete(synchronize_session=False)
    db.query(AccountLedger).filter(AccountLedger.account_id == acct.id).delete(synchronize_session=False)
    db.query(AccountLimit).filter(AccountLimit.account_id == acct.id).delete(synchronize_session=False)
    db.delete(acct)
    record_audit(db, 'ACCOUNT', account_id, 'DELETE', performed_by=current_user, before_state=before,
                 change_summary=f'Deleted account {acct.account_number}')
    db.commit()
    return {'status': 'deleted', 'account_id': account_id, 'account_number': acct.account_number}

@router.get("/accounts/{account_id}/ledger")
def get_account_ledger(account_id: str, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    entries = (
        db.query(AccountLedger)
        .filter(AccountLedger.account_id == account_id)
        .order_by(AccountLedger.created_at.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "id": e.id,
            "transaction_id": e.transaction_id,
            "entry_type": e.entry_type,
            "amount": float(e.amount),
            "currency": e.currency,
            "balance_before": float(e.balance_before),
            "balance_after": float(e.balance_after),
            "description": e.description,
            "posting_status": e.posting_status,
            "created_at": e.created_at.isoformat(),
        }
        for e in entries
    ]


@router.get("/cards")
def list_cards(
    pan: Optional[str] = Query(None),
    cardholder: Optional[str] = Query(None),
    institution_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    card_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    query = db.query(Card)
    if pan:
        term = f"%{pan.strip()}%"
        query = query.filter((Card.test_pan_reference.ilike(term)) | (Card.masked_pan.ilike(term)))
    if cardholder:
        query = query.filter(Card.cardholder_name.ilike(f"%{cardholder.strip()}%"))
    if institution_id:
        query = query.filter(Card.institution_id == institution_id)
    if status:
        query = query.filter(Card.card_status == status.upper())
    if card_type:
        query = query.filter(Card.card_type == card_type.upper())
    total = query.count()
    cards = query.order_by(Card.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    out = []
    for c in cards:
        lim = db.query(CardLimit).filter(CardLimit.card_id == c.id).first()
        pin_p = db.query(PinProfile).filter(PinProfile.card_id == c.id).first()
        emv_p = db.query(EmvProfile).filter(EmvProfile.card_id == c.id).first()
        out.append({
            "id": c.id,
            "customer_id": c.customer_id,
            "card_number_token": c.card_number_token,
            "test_pan_reference": c.test_pan_reference,
            "masked_pan": c.masked_pan,
            "cardholder_name": c.cardholder_name,
            "expiry_month": c.expiry_month,
            "expiry_year": c.expiry_year,
            "card_type": c.card_type,
            "card_product": c.card_product,
            "card_status": c.card_status,
            "linked_account_id": c.linked_account_id,
# [PATCH step02_01:api_card_list_inst]
# [PATCH api_routes_cards_short_bank_code]
            "institution_id": c.institution_id,
            "institution_code": _short_bank_code(c.institution, "XBANK"),
            "institution_name": c.institution.name if c.institution else None,
            "pin_profile": {
                "verification_method": pin_p.pin_verification_method,
                "pvk_key_reference": pin_p.pvk_key_reference,
                "pin_offset_reference": pin_p.pin_offset_reference,
                "retry_counter": pin_p.retry_counter,
                "maximum_retry_count": pin_p.maximum_retry_count,
                "pin_status": pin_p.pin_status,
            } if pin_p else None,
            "emv_profile": {
                "aid": emv_p.aid,
                "application_profile": emv_p.application_profile,
                "card_sequence_number": emv_p.card_sequence_number,
                "master_key_reference": emv_p.master_key_reference,
            } if emv_p else None,
            "limits": {
                "id": lim.id,
                "withdrawal_limit": float(lim.withdrawal_limit),
                "purchase_limit": float(lim.purchase_limit),
                "ecommerce_limit": float(lim.ecommerce_limit),
                "transaction_limit": float(lim.transaction_limit),
                "daily_limit": float(lim.daily_limit),
                "weekly_limit": float(lim.weekly_limit),
                "monthly_limit": float(lim.monthly_limit),
                "daily_used": float(lim.daily_used),
                "weekly_used": float(lim.weekly_used),
                "monthly_used": float(lim.monthly_used),
            } if lim else None,
        })
    total_pages = max(1, (total + page_size - 1) // page_size)
    return {"items": out, "total": total, "page": page, "page_size": page_size, "total_pages": total_pages}


@router.post("/cards", response_model=CardOut)
def create_card(payload: CardCreate, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    inst_id = payload.institution_id
    if not inst_id:
        xbank = db.query(Institution).filter(Institution.institution_code == 'XBANK').first()
        inst_id = xbank.id if xbank else None

    hsm_adapter = HSMAdapter(db)
    raw_pin = (payload.pin or '').strip()
    if raw_pin and raw_pin.isdigit() and len(raw_pin) >= 4:
        calculated_pvv = hsm_adapter.generate_pin_pvv(payload.test_pan_reference, raw_pin, '1', 'PVK_VISA_01')
    elif payload.pvv_or_offset and payload.pvv_or_offset != '7821':
        calculated_pvv = payload.pvv_or_offset
    else:
        calculated_pvv = hsm_adapter.generate_pin_pvv(payload.test_pan_reference, '1234', '1', 'PVK_VISA_01')

    exp_yy_mm = f"{str(payload.expiry_year)[-2:]}{payload.expiry_month:02d}"
    calculated_cvv = hsm_adapter.generate_card_cvv(payload.test_pan_reference, exp_yy_mm, '101', 'CVK_MAIN_01')

    card = Card(
        customer_id=payload.customer_id,
        card_number_token=tokenize_pan(payload.test_pan_reference),
        test_pan_reference=payload.test_pan_reference,
        masked_pan=mask_pan(payload.test_pan_reference),
        cardholder_name=payload.cardholder_name.upper(),
        expiry_month=payload.expiry_month,
        expiry_year=payload.expiry_year,
        card_type=payload.card_type,
        card_product=payload.card_product,
        card_status=payload.card_status,
        linked_account_id=payload.linked_account_id,
        # [PATCH step13_03:card_inherit_bin_card_profile]
        card_profile_id=payload.card_profile_id or (
            next(
                (
                    b.card_profile_id
                    for b in sorted(
                        db.query(BinRange).filter(BinRange.status == 'ACTIVE').all(),
                        key=lambda x: len(x.bin_prefix or ''),
                        reverse=True,
                    )
                    if payload.test_pan_reference.startswith(b.bin_prefix) and getattr(b, 'card_profile_id', None)
                ),
                None,
            )
        ),
        institution_id=inst_id,
    )
    db.add(card)
    db.flush()

    if payload.linked_account_id:
        acct = db.query(Account).filter(Account.id == payload.linked_account_id).first()
        db.add(CardAccount(
            card_id=card.id,
            account_id=payload.linked_account_id,
            account_role='PRIMARY',
            currency=acct.currency if acct else 'BDT',
            priority=1,
            status='ACTIVE',
        ))
    db.add(CardLimit(card_id=card.id))
    db.add(
        PinProfile(
            card_id=card.id,
            pin_verification_method='VISA_PVV',
            pvk_key_reference='PVK_VISA_01',
            pin_offset_reference=calculated_pvv,
            pvki='1',
            cvv_reference=calculated_cvv,
        )
    )
    db.add(EmvProfile(card_id=card.id))
    record_system_log(db, 'INFO', 'CardService', 'CARD_ISSUED', f'Issued card {card.masked_pan} (PVV: {calculated_pvv})')
    record_audit(db, 'CARD', card.id, 'CREATE', performed_by=current_user, after_state=serialize_entity(card),
                 change_summary=f'Issued card {card.masked_pan} with PVV {calculated_pvv}')
    db.commit()
    db.refresh(card)
    card.institution_code = card.institution.institution_code if card.institution else None
    card.institution_name = card.institution.name if card.institution else None
    return card

@router.patch("/cards/{card_id}/status")
def update_card_status(card_id: str, card_status: str, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    card = db.query(Card).filter(Card.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    card.card_status = card_status.upper()
    db.commit()
    return {"id": card.id, "card_status": card.card_status}


# [PATCH api_routes_card_limit_reset_usage]
@router.put("/cards/{card_id}/limits")
def update_card_limits(
    card_id: str,
    payload: CardLimitUpdate,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    card = db.query(Card).filter(Card.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    lim = db.query(CardLimit).filter(CardLimit.card_id == card_id).first()
    if not lim:
        lim = CardLimit(card_id=card_id)
        db.add(lim)
        db.flush()
    before = serialize_entity(lim)
    # Ordinary limit configuration editing ONLY updates maximum thresholds & status, NEVER resetting used counters
    lim.withdrawal_limit = payload.withdrawal_limit
    lim.purchase_limit = payload.purchase_limit
    lim.ecommerce_limit = payload.ecommerce_limit
    lim.transaction_limit = payload.transaction_limit
    lim.daily_limit = payload.daily_limit
    lim.weekly_limit = payload.weekly_limit
    lim.monthly_limit = payload.monthly_limit
    lim.status = payload.status.upper().strip()
    after = serialize_entity(lim)
    record_audit(
        db,
        "CARD_LIMIT",
        lim.id,
        "UPDATE_CONFIG",
        performed_by=current_user,
        before_state=before,
        after_state=after,
        change_summary=f"Updated configured limit thresholds for card {card.masked_pan}",
    )
    db.commit()
    return {"status": "updated", "card_id": card_id, "limits": after}


@router.post("/cards/{card_id}/limits/reset-usage", response_model=LimitUsageResetOut)
def reset_card_limit_usage(
    card_id: str,
    payload: LimitUsageResetRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    if not payload.confirm_reset:
        raise HTTPException(status_code=400, detail="Explicit confirmation is required before resetting limit usage.")
    reason_clean = (payload.reason or "").strip()
    if len(reason_clean) < 3:
        raise HTTPException(status_code=400, detail="A valid testing reason or reference is required to reset limit usage.")

    card = db.query(Card).filter(Card.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    lim = db.query(CardLimit).filter(CardLimit.card_id == card_id).first()
    if not lim:
        lim = CardLimit(card_id=card_id)
        db.add(lim)
        db.flush()

    before = serialize_entity(lim)
    old_usage = {
        "daily_used": float(lim.daily_used or 0),
        "weekly_used": float(lim.weekly_used or 0),
        "monthly_used": float(lim.monthly_used or 0),
    }

    scope = (payload.scope or "ALL").upper().strip()
    if scope in ("DAILY", "ALL"):
        lim.daily_used = Decimal("0.00")
    if scope in ("WEEKLY", "ALL"):
        lim.weekly_used = Decimal("0.00")
    if scope in ("MONTHLY", "ALL"):
        lim.monthly_used = Decimal("0.00")

    new_usage = {
        "daily_used": float(lim.daily_used or 0),
        "weekly_used": float(lim.weekly_used or 0),
        "monthly_used": float(lim.monthly_used or 0),
    }
    after = serialize_entity(lim)
    after["reset_reason"] = reason_clean
    after["testing_reference"] = payload.testing_reference

    record_audit(
        db,
        "CARD_LIMIT",
        lim.id,
        "RESET_LIMIT_USAGE",
        performed_by=current_user,
        before_state=before,
        after_state=after,
        change_summary=(
            f"Reset {scope} limit usage for card {card.masked_pan} to 0.00 "
            f"(Old: {old_usage} -> New: {new_usage}) | Reason: {reason_clean} "
            f"| Ref: {payload.testing_reference or 'N/A'}"
        ),
    )
    record_system_log(
        db,
        "WARNING",
        "LimitEngine",
        "CARD_LIMIT_USAGE_RESET",
        f"Operator {current_user} reset {scope} usage on card {card.masked_pan} (Reason: {reason_clean})",
        details={"old_usage": old_usage, "new_usage": new_usage, "reason": reason_clean, "testing_reference": payload.testing_reference},
    )
    db.commit()
    return LimitUsageResetOut(
        status="reset",
        entity_type="CARD_LIMIT",
        entity_id=lim.id,
        target_identifier=card.masked_pan,
        scope=scope,
        performed_by=current_user,
        reason=reason_clean,
        testing_reference=payload.testing_reference,
        reset_at=utc_now(),
        old_usage=old_usage,
        new_usage=new_usage,
    )
# [PATCH step03_01:api_card_put_delete]


@router.put('/cards/{card_id}', response_model=CardOut)
def update_card(card_id: str, payload: CardUpdate, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    card = db.query(Card).filter(Card.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail='Card not found')
    before = serialize_entity(card)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(card, k, v)
    after = serialize_entity(card)
    record_audit(db, 'CARD', card.id, 'UPDATE', performed_by=current_user, before_state=before, after_state=after,
                 change_summary=f'Updated card {card.masked_pan}')
    db.commit()
    db.refresh(card)
    return card


@router.delete('/cards/{card_id}')
def delete_card(card_id: str, force: bool = Query(True), db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    card = db.query(Card).filter(Card.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail='Card not found')
    before = serialize_entity(card)
    db.query(Transaction).filter(Transaction.card_id == card.id).update({'card_id': None}, synchronize_session=False)
    db.query(CardAccount).filter(CardAccount.card_id == card.id).delete(synchronize_session=False)
    db.query(CardLimit).filter(CardLimit.card_id == card.id).delete(synchronize_session=False)
    db.query(PinProfile).filter(PinProfile.card_id == card.id).delete(synchronize_session=False)
    db.query(EmvProfile).filter(EmvProfile.card_id == card.id).delete(synchronize_session=False)
    db.delete(card)
    record_audit(db, 'CARD', card_id, 'DELETE', performed_by=current_user, before_state=before,
                 change_summary=f'Deleted card {card.masked_pan}')
    db.commit()
    return {'status': 'deleted', 'card_id': card_id}

# [PATCH step03_02:card_profile_endpoints]
# --- CARD PROFILES CRUD ---

@router.get('/card-profiles', response_model=List[CardProfileOut])
def list_card_profiles(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    return db.query(CardProfile).order_by(CardProfile.profile_code.asc()).all()


@router.post('/card-profiles', response_model=CardProfileOut)
def create_card_profile(payload: CardProfileCreate, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    p_code = payload.profile_code.upper().strip()
    existing = db.query(CardProfile).filter(CardProfile.profile_code == p_code).first()
    if existing:
        raise HTTPException(status_code=400, detail=f'Card profile {p_code} already exists')
    prof = CardProfile(**payload.model_dump())
    prof.profile_code = p_code
    db.add(prof)
    db.flush()
    record_audit(db, 'CARD_PROFILE', prof.id, 'CREATE', performed_by=current_user, after_state=serialize_entity(prof),
                 change_summary=f'Created card profile {prof.profile_code}')
    db.commit()
    db.refresh(prof)
    return prof


@router.put('/card-profiles/{profile_id}', response_model=CardProfileOut)
def update_card_profile(profile_id: str, payload: CardProfileUpdate, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    prof = db.query(CardProfile).filter(CardProfile.id == profile_id).first()
    if not prof:
        raise HTTPException(status_code=404, detail='Card profile not found')
    before = serialize_entity(prof)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(prof, k, v)
    after = serialize_entity(prof)
    record_audit(db, 'CARD_PROFILE', prof.id, 'UPDATE', performed_by=current_user, before_state=before, after_state=after,
                 change_summary=f'Updated card profile {prof.profile_code}')
    db.commit()
    db.refresh(prof)
    return prof


@router.delete('/card-profiles/{profile_id}')
def delete_card_profile(profile_id: str, force: bool = Query(False), db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    prof = db.query(CardProfile).filter(CardProfile.id == profile_id).first()
    if not prof:
        raise HTTPException(status_code=404, detail='Card profile not found')
    has_cards = db.query(Card).filter(Card.card_profile_id == prof.id).first() is not None
    if has_cards and not force:
        raise HTTPException(status_code=409, detail=f'Cannot delete card profile {prof.profile_code} assigned to active cards. Reassign cards first or use ?force=true')
    before = serialize_entity(prof)
    db.delete(prof)
    record_audit(db, 'CARD_PROFILE', profile_id, 'DELETE', performed_by=current_user, before_state=before,
                 change_summary=f'Deleted card profile {prof.profile_code} (Force: {force})')
    db.commit()
    return {'status': 'deleted', 'profile_id': profile_id}


# [PATCH step04:api_card_account_endpoints]
# --- CARD & ACCOUNT MULTI-LINKING (STEP 4) ---

@router.get('/cards/{card_id}/accounts', response_model=List[CardAccountLinkOut])
def list_card_accounts(card_id: str, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    card = db.query(Card).filter(Card.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail='Card not found')
    links = db.query(CardAccount).filter(CardAccount.card_id == card.id).order_by(CardAccount.priority.asc()).all()
    if not links and card.linked_account_id:
        acct_fallback = db.query(Account).filter(Account.id == card.linked_account_id).first()
        if acct_fallback:
            healed = CardAccount(card_id=card.id, account_id=acct_fallback.id, account_role='PRIMARY', currency=acct_fallback.currency, priority=1, status='ACTIVE')
            db.add(healed)
            db.commit()
            db.refresh(healed)
            links = [healed]
    out = []
    for l in links:
        acct = l.account
        out.append({
            'id': l.id,
            'card_id': l.card_id,
            'account_id': l.account_id,
            'account_number': acct.account_number if acct else None,
            'account_type': acct.account_type if acct else None,
            'currency': l.currency,
            'available_balance': float(acct.available_balance) if acct else 0.0,
            'account_role': l.account_role,
            'priority': l.priority,
            'status': l.status,
        })
    return out

@router.post('/cards/{card_id}/accounts', response_model=CardAccountLinkOut)
def link_account_to_card(card_id: str, payload: CardAccountLinkCreate, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    card = db.query(Card).filter(Card.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail='Card not found')
    acct = db.query(Account).filter(Account.id == payload.account_id).first()
    if not acct:
        raise HTTPException(status_code=404, detail='Account not found')
    existing = db.query(CardAccount).filter(CardAccount.card_id == card.id, CardAccount.account_id == acct.id).first()
    if existing:
        raise HTTPException(status_code=400, detail='Account is already linked to this card')

    if payload.account_role == 'PRIMARY':
        db.query(CardAccount).filter(CardAccount.card_id == card.id).update({'account_role': 'SECONDARY'}, synchronize_session=False)
        card.linked_account_id = acct.id

    link = CardAccount(
        card_id=card.id,
        account_id=acct.id,
        account_role=payload.account_role,
        currency=acct.currency,
        priority=payload.priority,
        status=payload.status,
    )
    db.add(link)
    db.flush()
    record_audit(db, 'CARD_ACCOUNT', link.id, 'CREATE', performed_by=current_user,
                 after_state=serialize_entity(link),
                 change_summary=f'Linked account {acct.account_number} to card {card.masked_pan} as {payload.account_role}')
    db.commit()
    db.refresh(link)
    return {
        'id': link.id,
        'card_id': link.card_id,
        'account_id': link.account_id,
        'account_number': acct.account_number,
        'account_type': acct.account_type,
        'currency': link.currency,
        'available_balance': float(acct.available_balance),
        'account_role': link.account_role,
        'priority': link.priority,
        'status': link.status,
    }


@router.put('/cards/accounts/{link_id}', response_model=CardAccountLinkOut)
def update_card_account_link(link_id: str, payload: CardAccountLinkUpdate, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    link = db.query(CardAccount).filter(CardAccount.id == link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail='Card account link not found')
    before = serialize_entity(link)
    if payload.account_role == 'PRIMARY':
        db.query(CardAccount).filter(CardAccount.card_id == link.card_id).update({'account_role': 'SECONDARY'}, synchronize_session=False)
        card = db.query(Card).filter(Card.id == link.card_id).first()
        if card:
            card.linked_account_id = link.account_id

    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(link, k, v)
    after = serialize_entity(link)
    record_audit(db, 'CARD_ACCOUNT', link.id, 'UPDATE', performed_by=current_user, before_state=before, after_state=after,
                 change_summary=f'Updated card account link {link.id}')
    db.commit()
    db.refresh(link)
    acct = link.account
    return {
        'id': link.id,
        'card_id': link.card_id,
        'account_id': link.account_id,
        'account_number': acct.account_number if acct else None,
        'account_type': acct.account_type if acct else None,
        'currency': link.currency,
        'available_balance': float(acct.available_balance) if acct else 0.0,
        'account_role': link.account_role,
        'priority': link.priority,
        'status': link.status,
    }


@router.delete('/cards/accounts/{link_id}')
def unlink_account_from_card(link_id: str, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    link = db.query(CardAccount).filter(CardAccount.id == link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail='Card account link not found')
    card = db.query(Card).filter(Card.id == link.card_id).first()
    before = serialize_entity(link)
    db.delete(link)
    db.flush()
    if card:
        next_link = db.query(CardAccount).filter(CardAccount.card_id == card.id).order_by(CardAccount.priority.asc()).first()
        if next_link:
            next_link.account_role = 'PRIMARY'
            next_link.priority = 1
            card.linked_account_id = next_link.account_id
        else:
            card.linked_account_id = None
    record_audit(db, 'CARD_ACCOUNT', link_id, 'DELETE', performed_by=current_user, before_state=before,
                 change_summary=f'Unlinked account {link.account_id} from card {link.card_id}')
    db.commit()
    return {'status': 'deleted', 'link_id': link_id}

# [PATCH step06:crypto_calculation_endpoints]
# --- CARD ISSUING & CRYPTO LAB ENDPOINTS (STEP 6) ---

@router.post('/cards/{card_id}/pin')
def change_card_pin(card_id: str, payload: CardPinChangeRequest, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    card = db.query(Card).filter(Card.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail='Card not found')
    pin_prof = db.query(PinProfile).filter(PinProfile.card_id == card.id).first()
    if not pin_prof:
        raise HTTPException(status_code=404, detail='PIN profile not found for card')

    before = serialize_entity(pin_prof)
    pvk_id = pin_prof.pvk_key_reference or 'PVK_VISA_01'
    if pin_prof.pin_verification_method == 'IBM_3624':
        calc = calculate_ibm_offset_detailed(card.test_pan_reference, payload.new_pin, pvk_id)
        new_ref = calc['calculated_offset']
    else:
        calc = calculate_visa_pvv_detailed(card.test_pan_reference, payload.new_pin, pin_prof.pvki, pvk_id)
        new_ref = calc['calculated_pvv']

    pin_prof.pin_offset_reference = new_ref
    pin_prof.retry_counter = 0
    pin_prof.pin_changed_at = utc_now()
    after = serialize_entity(pin_prof)
    record_audit(db, 'PIN_PROFILE', pin_prof.id, 'PIN_CHANGE', performed_by=current_user, before_state=before, after_state=after,
                 change_summary=f'Changed PIN and recalculated PVV/Offset for card {card.masked_pan}')
    db.commit()
    return {'status': 'updated', 'card_id': card.id, 'new_pvv': new_ref, 'method': pin_prof.pin_verification_method}


@router.post('/cards/generate-test-card')
def generate_test_card_endpoint(payload: CardGenerateRequest, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    bin_match = db.query(BinRange).filter(BinRange.bin_prefix == payload.bin_prefix).first()
    if not bin_match:
        raise HTTPException(status_code=404, detail=f'BIN range {payload.bin_prefix} not found in database')

    # Generate Luhn PAN
    pan = generate_luhn_pan(payload.bin_prefix, bin_match.pan_length)
    # Resolve customer & account
    inst_id = bin_match.institution_id
    cust = db.query(Customer).filter(Customer.institution_id == inst_id).first()
    if not cust:
        cust = db.query(Customer).first()
    acct = db.query(Account).filter(Account.customer_id == cust.id).first() if cust else None
    if not acct:
        acct = db.query(Account).first()

    # [PATCH customer_360:gen_card_expiry]
    # Expiry is chosen by the user; default = 3 years from today (no more fixed 12/2028)
    _now = datetime.now(timezone.utc)
    exp_month = payload.expiry_month or _now.month
    exp_year = payload.expiry_year or (_now.year + 3)
    exp_yymm = f"{str(exp_year)[-2:]}{int(exp_month):02d}"

    # Calculate PVV and CVV (CVV depends on the expiry)
    pvv_calc = calculate_visa_pvv_detailed(pan, payload.initial_pin, '1', 'PVK_VISA_01')
    cvv_calc = calculate_cvv_detailed(pan, exp_yymm, '101', 'CVK_MAIN_01')

    card = Card(
        customer_id=cust.id,
        card_number_token=tokenize_pan(pan),
        test_pan_reference=pan,
        masked_pan=mask_pan(pan),
        cardholder_name=payload.cardholder_name.upper(),
        expiry_month=exp_month,
        expiry_year=exp_year,
        card_type=payload.card_type,
        card_product=payload.card_product or bin_match.card_product,
        card_status='ACTIVE',
        linked_account_id=acct.id if acct else None,
        card_profile_id=getattr(bin_match, 'card_profile_id', None),
        institution_id=inst_id,
    )
    db.add(card)
    db.flush()
    if acct:
        db.add(CardAccount(card_id=card.id, account_id=acct.id, account_role='PRIMARY', priority=1, status='ACTIVE'))
    db.add(CardLimit(card_id=card.id))
    db.add(PinProfile(card_id=card.id, pin_verification_method='VISA_PVV', pvk_key_reference='PVK_VISA_01', pin_offset_reference=pvv_calc['calculated_pvv'], pvki='1', cvv_reference=cvv_calc['calculated_cvv']))
    db.add(EmvProfile(card_id=card.id))
    record_audit(db, 'CARD', card.id, 'GENERATE_TEST_CARD', performed_by=current_user, after_state=serialize_entity(card),
                 change_summary=f'Generated Luhn test card {card.masked_pan} under BIN {payload.bin_prefix}')
    db.commit()
    return {
        'id': card.id,
        'test_pan_reference': card.test_pan_reference,
        'masked_pan': card.masked_pan,
        'cardholder_name': card.cardholder_name,
        'expiry_month': card.expiry_month,
        'expiry_year': card.expiry_year,
        'pvv': pvv_calc['calculated_pvv'],
        'cvv': cvv_calc['calculated_cvv'],
        'card_product': card.card_product,
        'institution_code': bin_match.institution.institution_code if bin_match.institution else 'ITCL',
        'linked_account_number': acct.account_number if acct else 'NONE',
    }


@router.post('/crypto/calculate-pvv')
def api_calculate_pvv(payload: PvvCalculateRequest, _: str = Depends(get_current_user)):
    return calculate_visa_pvv_detailed(payload.pan, payload.pin, payload.pvki, payload.pvk_id)


@router.post('/crypto/calculate-cvv')
def api_calculate_cvv(payload: CvvCalculateRequest, _: str = Depends(get_current_user)):
    return calculate_cvv_detailed(payload.pan, payload.expiry_yy_mm, payload.service_code, payload.cvk_id)


@router.post('/crypto/pack-pin-block')
def api_pack_pin_block(payload: PinBlockPackRequest, _: str = Depends(get_current_user)):
    return pack_pin_block_detailed(payload.pin, payload.pan, payload.format, payload.awk_id)


# ==============================================================================
# 3. TRANSACTION CODES, HOST CONFIGURATION & RESPONSE CODES
# ==============================================================================

@router.get("/transaction-codes")
def list_transaction_codes(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    codes = db.query(TransactionCode).order_by(TransactionCode.transaction_code.asc()).all()
    out = []
    for tc in codes:
        fields = (
            db.query(TransactionCodeField)
            .filter(TransactionCodeField.transaction_code_id == tc.id)
            .order_by(TransactionCodeField.display_order.asc())
            .all()
        )
        d = TransactionCodeOut.model_validate(tc).model_dump()
        d["fields"] = [
            {
                "id": f.id,
                "iso_field_number": f.iso_field_number,
                "field_name": f.field_name,
                "required": f.required,
                "editable": f.editable,
                "enabled": f.enabled,
                "default_value": f.default_value,
            }
            for f in fields
        ]
        out.append(d)
    return out


@router.post("/transaction-codes", response_model=TransactionCodeOut)
def create_or_update_transaction_code(
    payload: TransactionCodeCreate,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    existing = (
        db.query(TransactionCode)
        .filter(TransactionCode.transaction_code == payload.transaction_code)
        .first()
    )
    if existing:
        for k, v in payload.model_dump().items():
            setattr(existing, k, v)
        db.commit()
        db.refresh(existing)
        return existing

    tc = TransactionCode(**payload.model_dump())
    db.add(tc)
    db.commit()
    db.refresh(tc)
    return tc
# [PATCH step03_02:delete_transaction_code]


@router.delete('/transaction-codes/{tc_id}')
def delete_transaction_code(tc_id: str, force: bool = Query(False), db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    tc = db.query(TransactionCode).filter(TransactionCode.id == tc_id).first()
    if not tc:
        raise HTTPException(status_code=404, detail='Transaction code not found')
    has_tx = db.query(Transaction).filter(Transaction.transaction_code == tc.transaction_code).first() is not None
    if has_tx and not force:
        raise HTTPException(status_code=409, detail=f'Cannot delete code {tc.transaction_code} referenced by transactions in journal. Deactivate it instead or use ?force=true')
    before = serialize_entity(tc)
    db.delete(tc)
    record_audit(db, 'TRANSACTION_CODE', tc_id, 'DELETE', performed_by=current_user, before_state=before,
                 change_summary=f'Deleted transaction code {tc.transaction_code}')
    db.commit()
    return {'status': 'deleted', 'transaction_code_id': tc_id}


@router.get("/host-parameters")
def list_host_parameters(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    params = db.query(HostParameter).order_by(HostParameter.parameter_group.asc(), HostParameter.parameter_name.asc()).all()
    return [
        {
            "id": p.id,
            "parameter_group": p.parameter_group,
            "parameter_name": p.parameter_name,
            "parameter_value": p.parameter_value,
            "description": p.description,
            "active": p.active,
        }
        for p in params
    ]


@router.put("/host-parameters/{param_id}")
def update_host_parameter(param_id: str, payload: Dict[str, Any], db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    param = db.query(HostParameter).filter(HostParameter.id == param_id).first()
    if not param:
        raise HTTPException(status_code=404, detail="Parameter not found")
    if "parameter_value" in payload:
        param.parameter_value = payload["parameter_value"]
    if "active" in payload:
        param.active = bool(payload["active"])
    if "description" in payload:
        param.description = payload["description"]
    db.commit()
    return {"status": "updated", "id": param.id}
# [PATCH step03_02:delete_host_parameter]


@router.delete('/host-parameters/{param_id}')
def delete_host_parameter(param_id: str, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    param = db.query(HostParameter).filter(HostParameter.id == param_id).first()
    if not param:
        raise HTTPException(status_code=404, detail='Parameter not found')
    before = serialize_entity(param)
    db.delete(param)
    record_audit(db, 'HOST_PARAMETER', param_id, 'DELETE', performed_by=current_user, before_state=before,
                 change_summary=f'Deleted host parameter {param.parameter_group}.{param.parameter_name}')
    db.commit()
    return {'status': 'deleted', 'id': param_id}


@router.get("/response-codes")
def list_response_codes(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    codes = db.query(ResponseCode).order_by(ResponseCode.response_code.asc()).all()
    return [
        {
            "id": c.id,
            "response_code": c.response_code,
            "response_description": c.response_description,
            "response_category": c.response_category,
            "approved_flag": c.approved_flag,
            "retry_allowed": c.retry_allowed,
            "active": c.active,
        }
        for c in codes
    ]


@router.post("/response-codes")
def upsert_response_code(payload: Dict[str, Any], db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    rc_val = str(payload.get("response_code", "")).strip()
    existing = db.query(ResponseCode).filter(ResponseCode.response_code == rc_val).first()
    if existing:
        existing.response_description = payload.get("response_description", existing.response_description)
        existing.response_category = payload.get("response_category", existing.response_category)
        existing.approved_flag = bool(payload.get("approved_flag", existing.approved_flag))
        db.commit()
        return {"status": "updated", "response_code": rc_val}
    rc = ResponseCode(
        response_code=rc_val,
        response_description=payload.get("response_description", "Custom Response"),
        response_category=payload.get("response_category", "DECLINE"),
        approved_flag=bool(payload.get("approved_flag", False)),
    )
    db.add(rc)
    db.commit()
    return {"status": "created", "response_code": rc_val}
# [PATCH step03_02:delete_response_code]


@router.delete('/response-codes/{rc_id}')
def delete_response_code(rc_id: str, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    rc = db.query(ResponseCode).filter(ResponseCode.id == rc_id).first()
    if not rc:
        raise HTTPException(status_code=404, detail='Response code not found')
    before = serialize_entity(rc)
    db.delete(rc)
    record_audit(db, 'RESPONSE_CODE', rc_id, 'DELETE', performed_by=current_user, before_state=before,
                 change_summary=f'Deleted response code {rc.response_code}')
    db.commit()
    return {'status': 'deleted', 'id': rc_id}


# ==============================================================================
# 4. TIC / ISO TRANSACTION SIMULATOR & SCENARIOS
# ==============================================================================

@router.get("/simulator/catalog")
def get_simulator_catalog(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    cards = db.query(Card).all()
    tx_codes = db.query(TransactionCode).filter(TransactionCode.active == True).all()  # noqa: E712
    return {
        "field_definitions": get_field_catalog(),
        "test_cards": [
            {
                "id": c.id,
                "test_pan_reference": c.test_pan_reference,
                "masked_pan": c.masked_pan,
                "cardholder_name": c.cardholder_name,
                "card_status": c.card_status,
                "expiry": f"{str(c.expiry_year)[-2:]}{c.expiry_month:02d}",
            }
            for c in cards
        ],
        "transaction_codes": [
            {
                "transaction_code": tc.transaction_code,
                "transaction_name": tc.transaction_name,
                "processing_code": tc.processing_code,
                "default_mti": tc.default_mti,
                "pin_required": tc.pin_required,
                "cvv_required": tc.cvv_required,
                "emv_required": tc.emv_required,
            }
            for tc in tx_codes
        ],
        "sample_scenarios": [
            {
                "key": "APPROVED_PURCHASE",
                "name": "1. Approved Purchase / Withdrawal (Code 10)",
                "transaction_code": "10",
                "mti": "0200",
                "test_clear_pin_helper": "1234",
                "fields": {
                    "2": "4567890123450001",
                    "3": "0100000",
                    "4": "000000250000",
                    "7": "1031123000",
                    "11": "100001",
                    "12": "123000",
                    "13": "1031",
                    "14": "2812",
                    "18": "5411",
                    "22": "051",
                    "25": "000",
                    "32": "123456",
                    "37": "000020526001",
                    "41": "ATM00001",
                    "49": "BDT",
                },
            },
            {
                "key": "DECLINED_INSUFFICIENT_FUNDS",
                "name": "2. Declined — Insufficient Balance (RC 51)",
                "transaction_code": "10",
                "mti": "0200",
                "test_clear_pin_helper": "1234",
                "fields": {
                    "2": "4567890123450002",
                    "3": "0100000",
                    "4": "000099900000",
                    "7": "1031123100",
                    "11": "100002",
                    "12": "123100",
                    "13": "1031",
                    "14": "2812",
                    "18": "5411",
                    "22": "051",
                    "25": "000",
                    "32": "123456",
                    "37": "000020526002",
                    "41": "POS00002",
                    "49": "BDT",
                },
            },
            {
                "key": "DECLINED_BLOCKED_CARD",
                "name": "3. Declined — Blocked Card (RC 05)",
                "transaction_code": "10",
                "mti": "0200",
                "test_clear_pin_helper": "1234",
                "fields": {
                    "2": "4567890123450003",
                    "3": "0100000",
                    "4": "000000050000",
                    "7": "1031123200",
                    "11": "100003",
                    "12": "123200",
                    "13": "1031",
                    "14": "2812",
                    "22": "051",
                    "25": "000",
                    "37": "000020526003",
                    "41": "ATM00001",
                    "49": "BDT",
                },
            },
            {
                "key": "DECLINED_EXCEEDED_LIMIT",
                "name": "4. Declined — Exceeds Card Limit (RC 61)",
                "transaction_code": "10",
                "mti": "0200",
                "test_clear_pin_helper": "1234",
                "fields": {
                    "2": "4567890123450001",
                    "3": "0100000",
                    "4": "000008500000",
                    "7": "1031123300",
                    "11": "100004",
                    "12": "123300",
                    "13": "1031",
                    "14": "2812",
                    "22": "051",
                    "25": "000",
                    "37": "000020526004",
                    "41": "ATM00001",
                    "49": "BDT",
                },
            },
            {
                "key": "DECLINED_PIN_FAILURE",
                "name": "5. Declined — PIN Verification Failure (RC 55)",
                "transaction_code": "10",
                "mti": "0200",
                "test_clear_pin_helper": "9999",
                "fields": {
                    "2": "4567890123450001",
                    "3": "0100000",
                    "4": "000000100000",
                    "7": "1031123400",
                    "11": "100005",
                    "12": "123400",
                    "13": "1031",
                    "14": "2812",
                    "22": "051",
                    "25": "000",
                    "37": "000020526005",
                    "41": "ATM00001",
                    "49": "BDT",
                },
            },
            {
                "key": "INVALID_MESSAGE_FORMAT",
                "name": "6. Declined — Invalid TIC Message Format (RC 30)",
                "transaction_code": "10",
                "mti": "0200",
                "fields": {
                    "2": "4567890123450001",
                    "3": "0100000",
                    "4": "INVALID_AMOUNT",
                    "11": "100006",
                    "37": "000020526006",
                    "49": "BDT",
                },
            },
            {
                "key": "REVERSAL_SCENARIO",
                "name": "7. Acquirer Reversal of RRN 000020526001 (MTI 0400)",
                "transaction_code": "10",
                "mti": "0400",
                "fields": {
                    "2": "4567890123450001",
                    "3": "0100000",
                    "4": "000000250000",
                    "7": "1031123500",
                    "11": "100007",
                    "37": "000020526001",
                    "41": "ATM00001",
                    "49": "BDT",
                },
            },
        ],
    }


@router.post("/simulator/build")
def simulator_build_message(payload: SimulatorBuildRequest, _: str = Depends(get_current_user)):
    validation = validate_tic_fields(payload.fields)
    if not validation["valid"]:
        return {"valid": False, "errors": validation["errors"]}
    raw_msg, compact_msg = build_tic_message(
        payload.mti,
        validation["normalized_fields"],
        h1=payload.header_h1,
        h2=payload.header_h2,
        h3=payload.header_h3,
    )
    decoded = decode_tic_message(raw_msg)
    return {
        "valid": True,
        "raw_tic_message": raw_msg,
        "sanitized_raw_tic": mask_raw_tic_message(raw_msg),
        "compact_tic": mask_raw_tic_message(compact_msg),
        "decoded": decoded,
    }


@router.post("/simulator/decode")
def simulator_decode_message(payload: Dict[str, str], _: str = Depends(get_current_user)):
    raw = payload.get("raw_tic_message", "")
    return decode_tic_message(raw)
# [PATCH step09:api_routes_parse_raw_endpoint]


@router.post('/simulator/parse-raw', response_model=RawMessageParseResponse)
def parse_raw_wire_message(payload: RawMessageParseRequest, _: str = Depends(get_current_user)):
    msg = payload.raw_message.strip()
    # Check if message is Rajon TIC/TCI (starts with A4M or contains A4M)
    if 'A4M' in msg:
        decoded = decode_tic_message(msg)
        if not decoded.get('valid'):
            return RawMessageParseResponse(
                valid=False,
                format='TIC_V2164E',
                mti=decoded.get('mti', '0200'),
                fields={},
                detailed_fields={},
                error=decoded.get('error', 'Invalid TIC message structure'),
            )
        # Derive tran code from F3 (prefix)
        raw_f = decoded.get('raw_fields', {})
        f3 = raw_f.get('3', '010')
        tc = f3[:3].lstrip('0') or '10'
        return RawMessageParseResponse(
            valid=True,
            format='TIC_V2164E',
            mti=decoded.get('mti', '0200'),
            fields=raw_f,
            detailed_fields=decoded.get('detailed_fields', {}),
            derived_transaction_code=tc,
            warnings=decoded.get('warnings', []),
        )

    # Otherwise parse as standard ISO 8583:1987 (starts with 4-digit MTI)
    iso_dec = decode_iso8583_1987(msg)
    if iso_dec.get('valid'):
        return RawMessageParseResponse(
            valid=True,
            format='ISO8583_1987',
            mti=iso_dec['mti'],
            fields=iso_dec['raw_fields'],
            detailed_fields=iso_dec['detailed_fields'],
            derived_transaction_code=iso_dec.get('derived_transaction_code', '10'),
            warnings=iso_dec.get('warnings', []),
        )

    return RawMessageParseResponse(
        valid=False,
        format='UNKNOWN',
        mti='0200',
        fields={},
        detailed_fields={},
        error='Unable to auto-detect message format (neither Rajon A4M TIC nor Standard ISO 8583)',
    )



@router.post("/simulator/submit")
def simulator_submit_transaction(
    payload: SimulatorSubmitRequest,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    processor = HostTransactionProcessor(db)
    return processor.process_transaction(payload.model_dump())


# ==============================================================================
# 5. TRANSACTION JOURNAL & DETAILS
# ==============================================================================

@router.get("/transactions")
def list_transactions(
    stan: Optional[str] = Query(None),
    rrn: Optional[str] = Query(None),
    pan: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    response_code: Optional[str] = Query(None),
    ps_code: Optional[str] = Query(None),
    min_amount: Optional[float] = Query(None),
    max_amount: Optional[float] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    q = db.query(Transaction)
    if stan:
        q = q.filter(Transaction.stan.contains(stan.strip()))
    if rrn:
        q = q.filter(Transaction.rrn.contains(rrn.strip()))
    if pan:
        q = q.filter(Transaction.masked_pan.contains(pan.strip()))
    if status:
        q = q.filter(Transaction.authorization_status == status.upper())
    if response_code:
        q = q.filter(Transaction.response_code == response_code.strip())
    if ps_code:
        q = q.filter(Transaction.ps_code == ps_code.upper().strip())
    if min_amount is not None:
        q = q.filter(Transaction.transaction_amount >= min_amount)
    if max_amount is not None:
        q = q.filter(Transaction.transaction_amount <= max_amount)
    total = q.count()
    txs = q.order_by(Transaction.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    items = [
        {
            "id": t.id,
            "transaction_reference": t.transaction_reference,
            "mti": t.mti,
            "processing_code": t.processing_code,
            "transaction_code": t.transaction_code,
            "stan": t.stan,
            "rrn": t.rrn,
            "terminal_id": t.terminal_id,
            "masked_pan": t.masked_pan,
            "transaction_amount": float(t.transaction_amount),
            "currency": t.currency,
            "response_code": t.response_code,
            "response_message": t.response_message,
            "transaction_status": t.transaction_status,
            "authorization_status": t.authorization_status,
            "source_channel": t.source_channel,
# [PATCH step02_01:api_tx_list_inst]
            "ps_code": t.ps_code,
            "is_on_us": t.is_on_us,
            "issuer_institution_id": t.issuer_institution_id,
            "issuer_code": t.issuer_institution.institution_code if t.issuer_institution else None,
            "acquirer_institution_id": t.acquirer_institution_id,
            "acquirer_code": t.acquirer_institution.institution_code if t.acquirer_institution else None,
            "created_at": t.created_at.isoformat(),
        }
        for t in txs
    ]
    total_pages = max(1, (total + page_size - 1) // page_size)
    return {"items": items, "total": total, "page": page, "page_size": page_size, "total_pages": total_pages}


@router.get("/transactions/{transaction_id}")
def get_transaction_details(transaction_id: str, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    tx = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    checks = (
        db.query(TransactionCheck)
        .filter(TransactionCheck.transaction_id == tx.id)
        .order_by(TransactionCheck.check_order.asc())
        .all()
    )
    messages = db.query(TransactionMessage).filter(TransactionMessage.transaction_id == tx.id).all()
    hsm_ops = db.query(HsmOperation).filter(HsmOperation.transaction_id == tx.id).all()
    ledger = db.query(AccountLedger).filter(AccountLedger.transaction_id == tx.id).all()

    return {
        "transaction": {
            "id": tx.id,
            "transaction_reference": tx.transaction_reference,
            "mti": tx.mti,
            "processing_code": tx.processing_code,
            "transaction_code": tx.transaction_code,
            "stan": tx.stan,
            "rrn": tx.rrn,
            "terminal_id": tx.terminal_id,
            "merchant_id": tx.merchant_id,
            "masked_pan": tx.masked_pan,
            "transaction_amount": float(tx.transaction_amount),
            "currency": tx.currency,
            "response_code": tx.response_code,
            "response_message": tx.response_message,
            "transaction_status": tx.transaction_status,
            "authorization_status": tx.authorization_status,
            "created_at": tx.created_at.isoformat(),
        },
        "checks": [
            {
                "check_order": c.check_order,
                "check_name": c.check_name,
                "check_status": c.check_status,
                "response_code": c.response_code,
                "message": c.message,
                "duration_ms": c.duration_ms,
            }
            for c in checks
        ],
        "messages": [
            {
                "message_type": m.message_type,
                "mti": m.mti,
                "sanitized_message": m.sanitized_message,
                "message_format": m.message_format,
            }
            for m in messages
        ],
        "hsm_operations": [
            {
                "operation_type": h.operation_type,
                "request_reference": h.request_reference,
                "response_status": h.response_status,
                "error_code": h.error_code,
                "duration_ms": h.duration_ms,
                "sanitized_request": h.sanitized_request,
                "sanitized_response": h.sanitized_response,
            }
            for h in hsm_ops
        ],
        "ledger_entries": [
            {
                "entry_type": l.entry_type,
                "amount": float(l.amount),
                "currency": l.currency,
                "balance_before": float(l.balance_before),
                "balance_after": float(l.balance_after),
                "description": l.description,
            }
            for l in ledger
        ],
    }


# ==============================================================================
# 6. HOST KEY MANAGEMENT & HSM WORKBENCH
# ==============================================================================

# [PATCH api_routes_hsm_keys_short_bank_code]
# [PATCH lmk_centric_key_mgmt:list_hsm_keys_safe]
@router.get("/hsm/keys")
def list_hsm_keys(
    provider_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    from app.lmk_key_management_service import LMKKeyManagementService
    q = db.query(HsmKeyReference)
    if provider_type and provider_type.upper() in ("INTERNAL_HSM", "EXTERNAL_HSM"):
        q = q.filter(HsmKeyReference.provider_type == provider_type.upper())
    keys = q.order_by(HsmKeyReference.created_at.asc()).all()
    out = []
    for k in keys:
        d = LMKKeyManagementService.serialize_key_safe(k)
        d["hsm_key_reference"] = k.hsm_key_reference
        d["institution_code"] = _short_bank_code(k.institution, "ITCL") if k.institution else "ITCL"
        out.append(d)
    return out


@router.post("/hsm/keys", response_model=HsmKeyReferenceOut)
def register_hsm_key(payload: HsmKeyReferenceCreate, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    key_rec = HsmKeyReference(**payload.model_dump())
    db.add(key_rec)
    record_system_log(db, "INFO", "HSMKeyManagement", "KEY_REGISTERED", f"Registered key reference {key_rec.key_identifier} (KVC {key_rec.kvc})")
    db.commit()
    db.refresh(key_rec)
    return key_rec
# [PATCH step03_02:hsm_key_put_and_delete]


@router.put('/hsm/keys/{key_id}', response_model=HsmKeyReferenceOut)
def update_hsm_key(key_id: str, payload: HsmKeyReferenceUpdate, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    key_rec = db.query(HsmKeyReference).filter(HsmKeyReference.id == key_id).first()
    if not key_rec:
        raise HTTPException(status_code=404, detail='HSM Key not found')
    before = serialize_entity(key_rec)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(key_rec, k, v)
    after = serialize_entity(key_rec)
    record_audit(db, 'HSM_KEY', key_rec.id, 'UPDATE', performed_by=current_user, before_state=before, after_state=after,
                 change_summary=f'Updated HSM key reference {key_rec.key_identifier}')
    db.commit()
    db.refresh(key_rec)
    return key_rec


@router.delete('/hsm/keys/{key_id}')
def delete_hsm_key(key_id: str, force: bool = Query(False), db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    key_rec = db.query(HsmKeyReference).filter(HsmKeyReference.id == key_id).first()
    if not key_rec:
        raise HTTPException(status_code=404, detail='HSM Key not found')
    has_ops = db.query(HsmOperation).filter(HsmOperation.key_reference_id == key_rec.id).first() is not None
    if has_ops and not force:
        raise HTTPException(status_code=409, detail=f'Cannot delete key {key_rec.key_identifier} referenced in HSM operation audit history. Deactivate it instead or use ?force=true')
    before = serialize_entity(key_rec)
    db.delete(key_rec)
    record_audit(db, 'HSM_KEY', key_id, 'DELETE', performed_by=current_user, before_state=before,
                 change_summary=f'Deleted HSM key reference {key_rec.key_identifier}')
    db.commit()
    return {'status': 'deleted', 'key_id': key_id}


@router.post("/hsm/workbench/execute")
def execute_hsm_workbench(
    payload: HsmWorkbenchRequest,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    adapter = HSMAdapter(db)
    op = payload.operation.upper()
    pan = payload.pan or "4567890123450001"

    pin_block = payload.pin_block
    if not pin_block and payload.clear_pin_for_test_packing:
        pin_block = adapter.pack_test_pin_block_server_side(payload.clear_pin_for_test_packing, pan)

    if op in ("PIN_VERIFY", "PVV_VERIFY"):
        res = adapter.verify_pin_pvv(
            pan=pan,
            encrypted_pin_block=pin_block or adapter.pack_test_pin_block_server_side("1234", pan),
            expected_pvv=payload.pvv_or_offset or "7821",
            pvki=payload.pvki or "1",
            pvk_id=payload.key_identifier or "PVK_VISA_01",
        )
    elif op == "PIN_TRANSLATE":
        res = adapter.translate_pin_block(
            pan=pan,
            encrypted_pin_block=pin_block or adapter.pack_test_pin_block_server_side("1234", pan),
            awk_id=payload.key_identifier or "AWK_ATM_01",
            iwk_id=payload.secondary_key_identifier or "IWK_SW_01",
        )
    elif op == "CVV_VERIFY":
        res = adapter.verify_cvv(
            pan=pan,
            expiry_yy_mm=payload.expiry_yy_mm or "2812",
            service_code=payload.service_code or "101",
            supplied_cvv=payload.cvv or "011",
            cvk_id=payload.key_identifier or "CVK_MAIN_01",
        )
    elif op in ("MAC_GENERATE", "MAC_VERIFY"):
        res = adapter.verify_or_generate_mac(
            data_hex=payload.data_hex or "48656C6C6F20576F726C64",
            supplied_mac=payload.mac_hex if op == "MAC_VERIFY" else None,
            tak_id=payload.key_identifier or "TAK_MAC_01",
        )
    elif op in ("ARQC_VERIFY", "ARPC_GENERATE", "DYNAMIC_KEY_DERIVATION"):
        default_de55 = (
            "9F02060000000050009F03060000000000009F1A02005095050000008000"
            "5F2A0200509A032610209C01009F370411223344820219809F36020045"
            "9F2608A1B2C3D4E5F601025F340101"
        )
        res = adapter.verify_emv_cryptogram(
            pan=pan,
            psn="01",
            de55_hex=payload.de55_hex or default_de55,
            arc_hex=payload.arc_hex or "3030",
            mk_ac_id=payload.key_identifier or "MK_AC_EMV01",
        )
    elif op in ("KEY_CHECK", "KVC_CHECK", "KEY_EXCHANGE"):
        res = adapter.check_key_kvc(payload.key_identifier or "ZMK_MAIN")
    else:
        res = adapter.check_key_kvc(payload.key_identifier or "ZMK_MAIN")

    db.commit()
    return res


# ==============================================================================
# 7. HOST EXECUTION MONITOR, LOGS, NOTIFICATIONS & WEBSOCKET
# ==============================================================================

@router.get("/monitor/traces")
def get_monitor_traces(
    component: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    sys_q = db.query(SystemLog)
    if component:
        sys_q = sys_q.filter(SystemLog.component == component)
    if severity:
        sys_q = sys_q.filter(SystemLog.severity == severity.upper())

    system_logs = sys_q.order_by(SystemLog.created_at.desc()).limit(100).all()
    hsm_ops = db.query(HsmOperation).order_by(HsmOperation.created_at.desc()).limit(60).all()
    tx_checks = db.query(TransactionCheck).order_by(TransactionCheck.created_at.desc()).limit(100).all()
    messages = db.query(TransactionMessage).order_by(TransactionMessage.created_at.desc()).limit(60).all()
    notifications = db.query(Notification).order_by(Notification.created_at.desc()).limit(50).all()

    return {
        "hsm_mode": settings.HSM_MODE,
        "transaction_checks": [
            {
                "id": c.id,
                "transaction_id": c.transaction_id,
                "check_order": c.check_order,
                "check_name": c.check_name,
                "check_status": c.check_status,
                "response_code": c.response_code,
                "message": c.message,
                "duration_ms": c.duration_ms,
                "created_at": c.created_at.isoformat(),
            }
            for c in tx_checks
        ],
        "hsm_traces": [
            {
                "id": h.id,
                "transaction_id": h.transaction_id,
                "operation_type": h.operation_type,
                "request_reference": h.request_reference,
                "response_status": h.response_status,
                "error_code": h.error_code,
                "duration_ms": h.duration_ms,
                "sanitized_request": h.sanitized_request,
                "sanitized_response": h.sanitized_response,
                "created_at": h.created_at.isoformat(),
            }
            for h in hsm_ops
        ],
        "system_logs": [
            {
                "id": l.id,
                "severity": l.severity,
                "component": l.component,
                "event_name": l.event_name,
                "message": l.message,
                "transaction_id": l.transaction_id,
                "sanitized_details": l.sanitized_details,
                "created_at": l.created_at.isoformat(),
            }
            for l in system_logs
        ],
        "message_traces": [
            {
                "id": m.id,
                "transaction_id": m.transaction_id,
                "message_type": m.message_type,
                "mti": m.mti,
                "sanitized_message": m.sanitized_message,
                "message_format": m.message_format,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ],
        "notifications": [
            {
                "id": n.id,
                "transaction_id": n.transaction_id,
                "notification_type": n.notification_type,
                "recipient_masked": n.recipient_masked,
                "message_template": n.message_template,
                "delivery_status": n.delivery_status,
                "created_at": n.created_at.isoformat(),
            }
            for n in notifications
        ],
    }


@router.websocket("/ws/monitor")
async def websocket_execution_monitor(websocket: WebSocket):
    await websocket.accept()
    queue = monitor_hub.subscribe()
    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        monitor_hub.unsubscribe(queue)
    except Exception:
        monitor_hub.unsubscribe(queue)

# [PATCH step03_01:api_audit_trail_endpoint]


@router.get('/audit-trail', response_model=List[AuditTrailOut])
def list_audit_trail(
    entity_type: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    q = db.query(AuditTrail)
    if entity_type:
        q = q.filter(AuditTrail.entity_type == entity_type.upper())
    if entity_id:
        q = q.filter(AuditTrail.entity_id == entity_id)
    return q.order_by(AuditTrail.created_at.desc()).limit(limit).all()


# [PATCH step07:api_routes_timeline_endpoints]

# ==============================================================================
# STEP 7 API ENDPOINTS: OPERATIONAL LOG TIMELINE & CORRELATION INSPECTION
# ==============================================================================

@router.get('/logs/timeline')
def get_unified_log_timeline(
    search: Optional[str] = Query(None),
    limit: int = Query(60, ge=1, le=200),
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    timeline = []
    # 1. Transactions
    tx_q = db.query(Transaction)
    if search:
        term = f'%{search.strip()}%'
        tx_q = tx_q.filter((Transaction.stan.ilike(term)) | (Transaction.rrn.ilike(term)) | (Transaction.masked_pan.ilike(term)))
    for t in tx_q.order_by(Transaction.created_at.desc()).limit(limit).all():
        timeline.append({
            'id': t.id,
            'correlation_id': t.transaction_reference,
            'category': 'SWITCH_TX',
            'title': f'MTI {t.mti} | Code {t.transaction_code or "N/A"}',
            'message': f'STAN {t.stan} · RRN {t.rrn} · Card {t.masked_pan} · Amount {t.transaction_amount} {t.currency}',
            'status': t.authorization_status,
            'duration_ms': 5,
            'timestamp': t.created_at.isoformat(),
        })

    # 2. API Audit Logs
    api_q = db.query(ApiAuditLog)
    if search:
        term = f'%{search.strip()}%'
        api_q = api_q.filter((ApiAuditLog.correlation_id.ilike(term)) | (ApiAuditLog.path.ilike(term)))
    for a in api_q.order_by(ApiAuditLog.created_at.desc()).limit(limit).all():
        timeline.append({
            'id': a.id,
            'correlation_id': a.correlation_id,
            'category': 'API',
            'title': f'{a.http_method} {a.path}',
            'message': f'HTTP Status {a.status_code} from {a.client_ip}',
            'status': 'OK' if a.status_code < 400 else 'ERROR',
            'duration_ms': a.duration_ms,
            'timestamp': a.created_at.isoformat(),
        })

    # 3. HSM Operations
    for h in db.query(HsmOperation).order_by(HsmOperation.created_at.desc()).limit(limit).all():
        timeline.append({
            'id': h.id,
            'correlation_id': h.request_reference,
            'category': 'HSM',
            'title': h.operation_type,
            'message': f'HSM Call Ref {h.request_reference} (EC {h.error_code})',
            'status': h.response_status,
            'duration_ms': h.duration_ms,
            'timestamp': h.created_at.isoformat(),
        })

    timeline.sort(key=lambda x: x['timestamp'], reverse=True)
    return {'events': timeline[:limit], 'total': len(timeline)}


@router.get('/logs/crypto-events')
def list_crypto_events(limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    events = db.query(CryptoEvent).order_by(CryptoEvent.created_at.desc()).limit(limit).all()
    return events


@router.get('/logs/correlation/{correlation_id}')
def get_correlation_details(correlation_id: str, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    api_log = db.query(ApiAuditLog).filter(ApiAuditLog.correlation_id == correlation_id).first()
    crypto_steps = db.query(CryptoEvent).filter(CryptoEvent.correlation_id == correlation_id).order_by(CryptoEvent.step_number.asc()).all()
    return {
        'correlation_id': correlation_id,
        'api_audit': serialize_entity(api_log) if api_log else None,
        'crypto_steps': [serialize_entity(c) for c in crypto_steps],
    }


# [PATCH step08:authorizer_rules_endpoints]

# ==============================================================================
# STEP 8 API ENDPOINTS: AUTHORIZER RULES MANAGEMENT & DRY-RUN
# ==============================================================================

@router.get('/authorizer-rules', response_model=List[AuthorizerRuleOut])
def list_authorizer_rules(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    return db.query(AuthorizerRule).order_by(AuthorizerRule.priority.asc()).all()


@router.post('/authorizer-rules', response_model=AuthorizerRuleOut)
def create_authorizer_rule(payload: AuthorizerRuleCreate, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    code = payload.rule_code.upper().strip()
    existing = db.query(AuthorizerRule).filter(AuthorizerRule.rule_code == code).first()
    if existing:
        raise HTTPException(status_code=400, detail=f'Authorizer rule {code} already exists')
    rule = AuthorizerRule(**payload.model_dump())
    rule.rule_code = code
    db.add(rule)
    db.flush()
    record_audit(db, 'AUTHORIZER_RULE', rule.id, 'CREATE', performed_by=current_user, after_state=serialize_entity(rule),
                 change_summary=f'Created authorizer rule {rule.rule_code}')
    db.commit()
    db.refresh(rule)
    return rule


@router.put('/authorizer-rules/{rule_id}', response_model=AuthorizerRuleOut)
def update_authorizer_rule(rule_id: str, payload: AuthorizerRuleUpdate, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    rule = db.query(AuthorizerRule).filter(AuthorizerRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail='Authorizer rule not found')
    before = serialize_entity(rule)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(rule, k, v)
    after = serialize_entity(rule)
    record_audit(db, 'AUTHORIZER_RULE', rule.id, 'UPDATE', performed_by=current_user, before_state=before, after_state=after,
                 change_summary=f'Updated authorizer rule {rule.rule_code}')
    db.commit()
    db.refresh(rule)
    return rule


@router.delete('/authorizer-rules/{rule_id}')
def delete_authorizer_rule(rule_id: str, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    rule = db.query(AuthorizerRule).filter(AuthorizerRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail='Authorizer rule not found')
    before = serialize_entity(rule)
    db.delete(rule)
    record_audit(db, 'AUTHORIZER_RULE', rule_id, 'DELETE', performed_by=current_user, before_state=before,
                 change_summary=f'Deleted authorizer rule {rule.rule_code}')
    db.commit()
    return {'status': 'deleted', 'rule_id': rule_id}


@router.post('/authorizer-rules/dry-run', response_model=RuleDryRunResponse)
def dry_run_authorizer_rule(payload: RuleDryRunRequest, _: str = Depends(get_current_user)):
    try:
        matched = SafeAstEvaluator.evaluate(payload.expression, payload.context)
        return RuleDryRunResponse(matched=matched, valid=True)
    except Exception as exc:
        return RuleDryRunResponse(matched=False, valid=False, error=str(exc))


# [PATCH step10:api_ceremony_endpoints]

# ==============================================================================
# STEP 10 API ENDPOINTS: SPLIT-COMPONENT KEY CEREMONY & EXCHANGE
# ==============================================================================

@router.post('/hsm/ceremony/generate-random')
def api_generate_random_key(payload: RandomKeyGenerateRequest, _: str = Depends(get_current_user)):
    return generate_random_des_key(payload.length_bits)


@router.post('/hsm/ceremony/assemble-components', response_model=KeyCeremonyResultOut)
def api_assemble_key_components(payload: KeyAssemblyRequest, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    res = assemble_components(payload.components)
    key_id = payload.key_identifier.strip()
    existing = db.query(HsmKeyReference).filter(HsmKeyReference.key_identifier == key_id).first()
    if existing:
        existing.clear_key_hex = res['assembled_key_hex']
        existing.kvc = res['kcv']
        existing.key_status = 'ACTIVE'
        db.commit()
        key_rec = existing
    else:
        key_rec = HsmKeyReference(
            key_name=payload.key_name or f'Ceremony {payload.key_type} Key',
            key_type=payload.key_type.upper(),
            key_usage=f'{payload.key_type.upper()}_OPERATIONAL',
            key_identifier=key_id,
            kvc=res['kcv'],
            algorithm='3DES_2KEY',
            key_length=res['length_bits'],
            hsm_key_reference=f'LMK_CEREMONY::{key_id}',
            clear_key_hex=res['assembled_key_hex'],
            institution_id=payload.institution_id,
            key_status='ACTIVE',
        )
        db.add(key_rec)
        db.commit()

    record_audit(db, 'HSM_KEY', key_rec.id, 'KEY_CEREMONY', performed_by=current_user,
                 change_summary=f'Assembled {key_id} from {res["components_count"]} components (KVC: {res["kcv"]})')
    db.commit()
    return KeyCeremonyResultOut(
        key_identifier=key_id,
        key_type=payload.key_type,
        kvc=res['kcv'],
        component_kcvs=res['component_kcvs'],
        status='REGISTERED',
    )


@router.post('/hsm/ceremony/export-under-zmk')
def api_export_key_under_zmk(payload: KeyExportUnderZmkRequest, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    # Resolve working key
    key_ref = db.query(HsmKeyReference).filter(HsmKeyReference.key_identifier == payload.key_identifier).first()
    wk_clear = (key_ref.clear_key_hex if (key_ref and key_ref.clear_key_hex) else SoftHsmCryptoCore.INTERNAL_CLEAR_KEYS.get(payload.key_identifier))
    if not wk_clear:
        raise HTTPException(status_code=404, detail=f'Working key {payload.key_identifier} not found')

    # Resolve ZMK
    zmk_ref = db.query(HsmKeyReference).filter(HsmKeyReference.key_identifier == payload.zmk_identifier).first()
    zmk_clear = (zmk_ref.clear_key_hex if (zmk_ref and zmk_ref.clear_key_hex) else SoftHsmCryptoCore.INTERNAL_CLEAR_KEYS.get(payload.zmk_identifier))
    if not zmk_clear:
        raise HTTPException(status_code=404, detail=f'ZMK {payload.zmk_identifier} not found')

    return export_key_under_zmk(wk_clear, zmk_clear)


@router.post('/hsm/ceremony/import-under-zmk')
def api_import_key_under_zmk(payload: KeyImportUnderZmkRequest, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    zmk_ref = db.query(HsmKeyReference).filter(HsmKeyReference.key_identifier == payload.zmk_identifier).first()
    zmk_clear = (zmk_ref.clear_key_hex if (zmk_ref and zmk_ref.clear_key_hex) else SoftHsmCryptoCore.INTERNAL_CLEAR_KEYS.get(payload.zmk_identifier))
    if not zmk_clear:
        raise HTTPException(status_code=404, detail=f'ZMK {payload.zmk_identifier} not found')

    res = import_key_under_zmk(payload.encrypted_key_hex, zmk_clear)
    key_id = payload.key_identifier.strip()
    existing = db.query(HsmKeyReference).filter(HsmKeyReference.key_identifier == key_id).first()
    if existing:
        existing.clear_key_hex = res['clear_key_hex']
        existing.kvc = res['kcv']
        db.commit()
    else:
        key_rec = HsmKeyReference(
            key_name=f'Imported {payload.key_type} Key',
            key_type=payload.key_type.upper(),
            key_usage=f'{payload.key_type.upper()}_OPERATIONAL',
            key_identifier=key_id,
            kvc=res['kcv'],
            algorithm='3DES_2KEY',
            key_length=128,
            hsm_key_reference=f'LMK_IMPORTED::{key_id}',
            clear_key_hex=res['clear_key_hex'],
            institution_id=payload.institution_id,
            key_status='ACTIVE',
        )
        db.add(key_rec)
        db.commit()

    record_audit(db, 'HSM_KEY', key_id, 'KEY_IMPORT_ZMK', performed_by=current_user,
                 change_summary=f'Imported key {key_id} under {payload.zmk_identifier} (KVC: {res["kcv"]})')
    db.commit()
    return {'key_identifier': key_id, 'kvc': res['kcv'], 'status': 'IMPORTED'}


# [PATCH step11:api_network_endpoints]

# ==============================================================================
# STEP 11 API ENDPOINTS: NETWORK PROFILES & ROUTING SIMULATION
# ==============================================================================

@router.get('/networks/profiles')
def list_network_profiles(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    return db.query(NetworkProfile).all()


@router.put('/networks/profiles/{profile_id}')
def update_network_profile(profile_id: str, payload: NetworkProfileUpdate, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    p = db.query(NetworkProfile).filter(NetworkProfile.id == profile_id).first()
    if not p:
        raise HTTPException(status_code=404, detail='Network profile not found')
    before = serialize_entity(p)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    after = serialize_entity(p)
    record_audit(db, 'NETWORK_PROFILE', p.id, 'UPDATE', performed_by=current_user, before_state=before, after_state=after,
                 change_summary=f'Updated simulation mode for {p.network_name}')
    db.commit()
    db.refresh(p)
    return p


@router.post('/networks/route-test')
def api_test_network_routing(payload: NetworkRouteLookupRequest, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    routing = resolve_transaction_routing(db, payload.pan, payload.acquirer_id or '123456')
    outbound_resp = None
    if not routing['is_on_us'] and routing.get('destination_network'):
        adapter = SimulatedNetworkAdapter(db, routing['destination_network'])
        outbound_resp = adapter.route_transaction({'pan': payload.pan, 'fields': {}})
    return {
        'routing': routing,
        'outbound_response': outbound_resp,
    }


# [PATCH step12:api_settlement_endpoints]

# ==============================================================================
# STEP 12 API ENDPOINTS: CLEARING, SETTLEMENT & RECONCILIATION
# ==============================================================================

@router.get('/settlement/batches', response_model=List[SettlementBatchOut])
def list_settlement_batches(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    return db.query(SettlementBatch).order_by(SettlementBatch.cutover_time.desc()).all()


@router.get('/settlement/batches/{batch_id}')
def get_settlement_batch_details(batch_id: str, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    batch = db.query(SettlementBatch).filter(SettlementBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail='Settlement batch not found')
    positions = db.query(SettlementPosition).filter(SettlementPosition.batch_id == batch.id).all()
    pos_out = []
    for p in positions:
        inst = p.institution
        pos_out.append({
            'id': p.id,
            'batch_id': p.batch_id,
            'institution_id': p.institution_id,
            'institution_code': inst.institution_code if inst else None,
            'institution_name': inst.name if inst else None,
            'net_settlement_amount': float(p.net_settlement_amount),
            'debit_count': p.debit_count,
            'credit_count': p.credit_count,
            'debit_volume': float(p.debit_volume),
            'credit_volume': float(p.credit_volume),
            'net_fee_amount': float(p.net_fee_amount),
            'settlement_status': p.settlement_status,
        })
    return {
        'batch': serialize_entity(batch),
        'positions': pos_out,
    }


@router.post('/settlement/cutover')
def api_execute_settlement_cutover(payload: BatchCutoverRequest, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    return execute_daily_cutover(db, payload.ps_code, current_user)


@router.get('/settlement/reconciliation', response_model=ReconciliationReportOut)
def api_get_reconciliation_summary(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    return get_reconciliation_summary(db)


@router.post('/settlement/run-scenarios')
def api_run_settlement_scenarios(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    # Generate synthetic multi-bank transactions between xBank, yBank, and zBank
    from app.host_engine import HostTransactionProcessor
    proc = HostTransactionProcessor(db)
    now_suffix = datetime.now().strftime('%M%S')
    test_cases = [
        ('10', '0200', '4567890123450001', '000000050000', f'91{now_suffix}1', f'00091{now_suffix}1', '123456'),
        ('40', '0200', '4567890123450001', '000000120000', f'91{now_suffix}2', f'00091{now_suffix}2', '223456'),
        ('10', '0200', '4567890123450004', '000000085000', f'91{now_suffix}3', f'00091{now_suffix}3', '123456'),
    ]
    approved = 0
    declined = 0
    for tc, mti, pan, amt, stan, rrn, acq in test_cases:
        res = proc.process_transaction({
            'transaction_code': tc,
            'mti': mti,
            'test_clear_pin_helper': '1234',
            'fields': {'2': pan, '3': '0100000', '4': amt, '11': stan, '32': acq, '37': rrn, '41': 'ATM01', '49': 'BDT'},
        })
        if res['response_code'] == '00':
            approved += 1
        else:
            declined += 1
    return {
        'transactions_generated': len(test_cases),
        'approved_count': approved,
        'declined_count': declined,
    }



# [PATCH api_routes_maintenance_360_strict_pan_and_limits]
# ==============================================================================
# CUSTOMER DATA MAINTENANCE 360 — PAN-BASED LIMIT MANAGEMENT & STRICT SEARCH
# ==============================================================================

def _build_card_limit_descriptors(lim: Optional[CardLimit]) -> List[Dict[str, Any]]:
    if not lim:
        return []
    d_used = float(lim.daily_used or 0)
    w_used = float(lim.weekly_used or 0)
    m_used = float(lim.monthly_used or 0)
    now_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return [
        {
            "key": "transaction_limit",
            "limit_name": "Per-Transaction Maximum Limit",
            "limit_type": "PER_TRANSACTION",
            "configured_value": float(lim.transaction_limit or 0),
            "utilized_value": None,
            "remaining_value": float(lim.transaction_limit or 0),
            "period": "PER_TX (Single Authorization)",
            "reset_info": "Evaluated per transaction",
            "status": lim.status,
            "currency": lim.currency,
        },
        {
            "key": "withdrawal_limit",
            "limit_name": "ATM Cash Withdrawal Limit",
            "limit_type": "CHANNEL_WITHDRAWAL",
            "configured_value": float(lim.withdrawal_limit or 0),
            "utilized_value": d_used,
            "remaining_value": max(0.0, float(lim.withdrawal_limit or 0) - d_used),
            "period": "DAILY (ATM Code 10)",
            "reset_info": f"Daily Cutover 23:59 UTC ({now_date})",
            "status": lim.status,
            "currency": lim.currency,
        },
        {
            "key": "purchase_limit",
            "limit_name": "POS Retail Purchase Limit",
            "limit_type": "CHANNEL_PURCHASE",
            "configured_value": float(lim.purchase_limit or 0),
            "utilized_value": d_used,
            "remaining_value": max(0.0, float(lim.purchase_limit or 0) - d_used),
            "period": "DAILY (POS Code 40/110)",
            "reset_info": f"Daily Cutover 23:59 UTC ({now_date})",
            "status": lim.status,
            "currency": lim.currency,
        },
        {
            "key": "ecommerce_limit",
            "limit_name": "E-Commerce / CNP Limit",
            "limit_type": "CHANNEL_ECOMMERCE",
            "configured_value": float(lim.ecommerce_limit or 0),
            "utilized_value": d_used,
            "remaining_value": max(0.0, float(lim.ecommerce_limit or 0) - d_used),
            "period": "DAILY (CNP POS Cond 08/81)",
            "reset_info": f"Daily Cutover 23:59 UTC ({now_date})",
            "status": lim.status,
            "currency": lim.currency,
        },
        {
            "key": "daily_limit",
            "limit_name": "Daily Aggregate Velocity Limit",
            "limit_type": "VELOCITY_DAILY",
            "configured_value": float(lim.daily_limit or 0),
            "utilized_value": d_used,
            "remaining_value": max(0.0, float(lim.daily_limit or 0) - d_used),
            "period": "DAILY (24h Window)",
            "reset_info": f"Resets at 00:00 UTC ({now_date})",
            "status": lim.status,
            "currency": lim.currency,
        },
        {
            "key": "weekly_limit",
            "limit_name": "Weekly Aggregate Velocity Limit",
            "limit_type": "VELOCITY_WEEKLY",
            "configured_value": float(lim.weekly_limit or 0),
            "utilized_value": w_used,
            "remaining_value": max(0.0, float(lim.weekly_limit or 0) - w_used),
            "period": "WEEKLY (7-Day Rolling)",
            "reset_info": "Resets Monday 00:00 UTC",
            "status": lim.status,
            "currency": lim.currency,
        },
        {
            "key": "monthly_limit",
            "limit_name": "Monthly Aggregate Velocity Limit",
            "limit_type": "VELOCITY_MONTHLY",
            "configured_value": float(lim.monthly_limit or 0),
            "utilized_value": m_used,
            "remaining_value": max(0.0, float(lim.monthly_limit or 0) - m_used),
            "period": "MONTHLY (Calendar Month)",
            "reset_info": "Resets 1st of Next Month",
            "status": lim.status,
            "currency": lim.currency,
        },
    ]


def _build_account_limit_descriptors(lim: Optional[AccountLimit]) -> List[Dict[str, Any]]:
    if not lim:
        return []
    d_used = float(lim.daily_used or 0)
    w_used = float(lim.weekly_used or 0)
    m_used = float(lim.monthly_used or 0)
    eff_from = lim.effective_from.strftime("%Y-%m-%d %H:%M UTC") if lim.effective_from else "Active"
    return [
        {
            "key": "per_transaction_limit",
            "limit_name": "Account Per-Transaction Limit",
            "limit_type": "PER_TRANSACTION",
            "configured_value": float(lim.per_transaction_limit or 0),
            "utilized_value": None,
            "remaining_value": float(lim.per_transaction_limit or 0),
            "period": "PER_TX (Single Debit)",
            "reset_info": f"Effective since {eff_from}",
            "status": lim.status,
            "currency": lim.currency,
        },
        {
            "key": "daily_limit",
            "limit_name": "Account Daily Velocity Limit",
            "limit_type": "VELOCITY_DAILY",
            "configured_value": float(lim.daily_limit or 0),
            "utilized_value": d_used,
            "remaining_value": max(0.0, float(lim.daily_limit or 0) - d_used),
            "period": "DAILY (24h Window)",
            "reset_info": f"Last Reset / Effective: {eff_from}",
            "status": lim.status,
            "currency": lim.currency,
        },
        {
            "key": "weekly_limit",
            "limit_name": "Account Weekly Velocity Limit",
            "limit_type": "VELOCITY_WEEKLY",
            "configured_value": float(lim.weekly_limit or 0),
            "utilized_value": w_used,
            "remaining_value": max(0.0, float(lim.weekly_limit or 0) - w_used),
            "period": "WEEKLY (7-Day Window)",
            "reset_info": "Resets Monday 00:00 UTC",
            "status": lim.status,
            "currency": lim.currency,
        },
        {
            "key": "monthly_limit",
            "limit_name": "Account Monthly Velocity Limit",
            "limit_type": "VELOCITY_MONTHLY",
            "configured_value": float(lim.monthly_limit or 0),
            "utilized_value": m_used,
            "remaining_value": max(0.0, float(lim.monthly_limit or 0) - m_used),
            "period": "MONTHLY (Calendar Month)",
            "reset_info": "Resets 1st of Month",
            "status": lim.status,
            "currency": lim.currency,
        },
    ]


@router.get("/maintenance/search")
def search_maintenance_data(
    q: Optional[str] = Query(None, description="Search term"),
    mode: Optional[str] = Query("customer", description="customer | pan | account | all"),
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    """
    Customer Data Maintenance 360 Search Engine.
    Supports separate search modes:
      1. customer: Search by customer number, name, mobile, email.
      2. pan: Search by full or partial PAN. Returns ONLY the matching card(s) for that PAN
              (never dumping every unrelated card of the customer), along with the owning
              customer, the accounts linked to that matching card, and full Card & Account limits.
      3. account: Search by account number.
    """
    clean_q = (q or "").strip()
    mode = (mode or "customer").lower().strip()
    if mode not in ("customer", "pan", "account", "all"):
        mode = "customer"

    matched_cust_ids_set: set[str] = set()
    matched_pan_card_ids: set[str] = set()
    matched_account_ids: set[str] = set()

    if not clean_q:
        for c in db.query(Customer).order_by(Customer.created_at.desc()).limit(40).all():
            matched_cust_ids_set.add(c.id)
    else:
        term = f"%{clean_q}%"
        exact = clean_q

        if mode in ("customer", "all"):
            for c in db.query(Customer).filter(
                (Customer.customer_number.ilike(term))
                | (Customer.first_name.ilike(term))
                | (Customer.last_name.ilike(term))
                | (Customer.mobile_number.ilike(term))
                | (Customer.email.ilike(term))
                # [PATCH customer_360:search_more_fields]
                | (Customer.nid_number.ilike(term))
                | (Customer.passport_number.ilike(term))
                | (Customer.alternate_mobile.ilike(term))
                | (Customer.father_name.ilike(term))
                | (Customer.mother_name.ilike(term))
                | (Customer.id == exact)
            ).all():
                matched_cust_ids_set.add(c.id)

        if mode in ("account", "all"):
            for a in db.query(Account).filter(
                (Account.account_number.ilike(term)) | (Account.id == exact)
            ).all():
                matched_account_ids.add(a.id)
                if a.customer_id:
                    matched_cust_ids_set.add(a.customer_id)

        if mode in ("pan", "all"):
            pan_q = db.query(Card)
            digits_only = "".join(ch for ch in clean_q if ch.isdigit())
            if len(digits_only) >= 15 and clean_q.isdigit():
                matched_cards = pan_q.filter(Card.test_pan_reference == clean_q).all()
            else:
                matched_cards = pan_q.filter(
                    (Card.test_pan_reference.ilike(term))
                    | (Card.masked_pan.ilike(term))
                    | (Card.id == exact)
                ).limit(50).all()

            for crd in matched_cards:
                matched_pan_card_ids.add(crd.id)
                if crd.customer_id:
                    matched_cust_ids_set.add(crd.customer_id)

    matched_cust_ids = list(matched_cust_ids_set)

    # All accounts (for link dropdown)
    all_accounts = db.query(Account).order_by(Account.account_number.asc()).all()
    all_accounts_out = []
    for a in all_accounts:
        all_accounts_out.append({
            "id": a.id,
            "account_number": a.account_number,
            "account_type": a.account_type,
            "currency": a.currency,
            "available_balance": float(a.available_balance or 0),
            "ledger_balance": float(a.ledger_balance or 0),
            "account_status": a.account_status,
            "customer_id": a.customer_id,
            "customer_name": (
                f"{a.customer.first_name} {a.customer.last_name or ''}".strip()
                if a.customer else ""
            ),
            "institution_code": _short_bank_code(a.institution, "XBANK"),
        })

    all_customers_mini = [
        {
            "id": c.id,
            "customer_number": c.customer_number,
            "name": f"{c.first_name} {c.last_name or ''}".strip(),
        }
        for c in db.query(Customer).order_by(Customer.customer_number.asc()).limit(200).all()
    ]

    customers_out = []
    for cid in matched_cust_ids:
        cust = db.query(Customer).filter(Customer.id == cid).first()
        if not cust:
            continue

        # Cards belonging to this customer
        raw_cards = db.query(Card).filter(Card.customer_id == cust.id).all()
        seen_card_ids: set[str] = set()
        card_list = []
        linked_acct_ids_for_matched_cards: set[str] = set()

        for card in raw_cards:
            if card.id in seen_card_ids:
                continue
            # CRITICAL PAN SEARCH REQUIREMENT:
            # When searching by PAN with a query, return ONLY the card(s) matching the searched PAN!
            if mode == "pan" and clean_q and card.id not in matched_pan_card_ids:
                continue
            seen_card_ids.add(card.id)

            # Auto-heal missing CardAccount from legacy linked_account_id
            if not card.card_accounts and card.linked_account_id:
                fallback = db.query(Account).filter(Account.id == card.linked_account_id).first()
                if fallback:
                    healed = CardAccount(
                        card_id=card.id,
                        account_id=fallback.id,
                        account_role="PRIMARY",
                        currency=fallback.currency,
                        priority=1,
                        status="ACTIVE",
                    )
                    db.add(healed)
                    db.flush()

            # Ensure CardLimit exists
            c_lim = db.query(CardLimit).filter(CardLimit.card_id == card.id).first()
            if not c_lim:
                c_lim = CardLimit(card_id=card.id, currency="BDT")
                db.add(c_lim)
                db.flush()

            ca_links = []
            for ca in sorted(card.card_accounts or [], key=lambda x: (x.priority or 99)):
                if ca.account_id:
                    linked_acct_ids_for_matched_cards.add(ca.account_id)
                acct_lim_obj = db.query(AccountLimit).filter(AccountLimit.account_id == ca.account_id).first() if ca.account_id else None
                ca_links.append({
                    "id": ca.id,
                    "account_id": ca.account_id,
                    "account_number": ca.account.account_number if ca.account else "UNKNOWN",
                    "account_type": ca.account.account_type if ca.account else "SAVINGS",
                    "available_balance": float(ca.account.available_balance) if ca.account else 0.0,
                    "ledger_balance": float(ca.account.ledger_balance) if ca.account else 0.0,
                    "account_status": ca.account.account_status if ca.account else "ACTIVE",
                    "currency": ca.currency,
                    "account_role": ca.account_role,
                    "priority": ca.priority,
                    "status": ca.status,
                    "account_limits": {
                        "id": acct_lim_obj.id,
                        "per_transaction_limit": float(acct_lim_obj.per_transaction_limit),
                        "daily_limit": float(acct_lim_obj.daily_limit),
                        "weekly_limit": float(acct_lim_obj.weekly_limit),
                        "monthly_limit": float(acct_lim_obj.monthly_limit),
                        "daily_used": float(acct_lim_obj.daily_used),
                        "weekly_used": float(acct_lim_obj.weekly_used),
                        "monthly_used": float(acct_lim_obj.monthly_used),
                        "status": acct_lim_obj.status,
                        "effective_from": acct_lim_obj.effective_from.isoformat() if acct_lim_obj.effective_from else None,
                    } if acct_lim_obj else None,
                    "account_limit_descriptors": _build_account_limit_descriptors(acct_lim_obj),
                })

            if card.linked_account_id:
                linked_acct_ids_for_matched_cards.add(card.linked_account_id)

            pin_p = card.pin_profile
            emv_p = card.emv_profile
            card_list.append({
                "id": card.id,
                "test_pan_reference": card.test_pan_reference,
                "masked_pan": card.masked_pan,
                "cardholder_name": card.cardholder_name,
                "expiry_month": card.expiry_month,
                "expiry_year": card.expiry_year,
                "card_type": card.card_type,
                "card_product": card.card_product,
                "card_status": card.card_status,
                "linked_account_id": card.linked_account_id,
                "institution_id": card.institution_id,
                "institution_code": _short_bank_code(card.institution, _short_bank_code(cust.institution, "XBANK")),
                "card_accounts": ca_links,
                "limits": {
                    "id": c_lim.id,
                    "currency": c_lim.currency,
                    "withdrawal_limit": float(c_lim.withdrawal_limit),
                    "purchase_limit": float(c_lim.purchase_limit),
                    "ecommerce_limit": float(c_lim.ecommerce_limit),
                    "transaction_limit": float(c_lim.transaction_limit),
                    "daily_limit": float(c_lim.daily_limit),
                    "weekly_limit": float(c_lim.weekly_limit),
                    "monthly_limit": float(c_lim.monthly_limit),
                    "daily_used": float(c_lim.daily_used),
                    "weekly_used": float(c_lim.weekly_used),
                    "monthly_used": float(c_lim.monthly_used),
                    "status": c_lim.status,
                },
                "limit_descriptors": _build_card_limit_descriptors(c_lim),
                "pin_profile": {
                    "pin_offset_reference": pin_p.pin_offset_reference if pin_p else None,
                    "verification_method": pin_p.pin_verification_method if pin_p else "VISA_PVV",
                    "pvk_key_reference": pin_p.pvk_key_reference if pin_p else "PVK_VISA_01",
                    "cvv_reference": pin_p.cvv_reference if pin_p else None,
                    "retry_counter": pin_p.retry_counter if pin_p else 0,
                    "maximum_retry_count": pin_p.maximum_retry_count if pin_p else 3,
                    "pin_status": pin_p.pin_status if pin_p else "ACTIVE",
                } if pin_p else None,
                "emv_profile": {
                    "aid": emv_p.aid,
                    "application_profile": emv_p.application_profile,
                    "card_sequence_number": emv_p.card_sequence_number,
                    "master_key_reference": emv_p.master_key_reference,
                } if emv_p else None,
            })

        # Accounts belonging to this customer (or linked to the matched PAN when mode=='pan')
        accts_query = db.query(Account).filter(Account.customer_id == cust.id).all()
        if mode == "pan" and clean_q and linked_acct_ids_for_matched_cards:
            # Also include any cross-customer linked account if linked to the searched PAN
            extra_accts = (
                db.query(Account)
                .filter(Account.id.in_(list(linked_acct_ids_for_matched_cards)))
                .all()
            )
            acct_map_by_id = {a.id: a for a in extra_accts}
            accts = list(acct_map_by_id.values())
        elif mode == "account" and clean_q and matched_account_ids:
            accts = [a for a in accts_query if a.id in matched_account_ids] or accts_query
        else:
            accts = accts_query

        acct_list = []
        for a in accts:
            lim = db.query(AccountLimit).filter(AccountLimit.account_id == a.id).first()
            if not lim:
                lim = AccountLimit(account_id=a.id, currency=a.currency)
                db.add(lim)
                db.flush()
            acct_list.append({
                "id": a.id,
                "account_number": a.account_number,
                "account_type": a.account_type,
                "currency": a.currency,
                "available_balance": float(a.available_balance or 0),
                "ledger_balance": float(a.ledger_balance or 0),
                "overdraft_limit": float(a.overdraft_limit or 0),
                "account_status": a.account_status,
                "branch_code": a.branch_code,
                "institution_code": _short_bank_code(a.institution, _short_bank_code(cust.institution, "XBANK")),
                "limits": {
                    "id": lim.id,
                    "currency": lim.currency,
                    "per_transaction_limit": float(lim.per_transaction_limit),
                    "daily_limit": float(lim.daily_limit),
                    "weekly_limit": float(lim.weekly_limit),
                    "monthly_limit": float(lim.monthly_limit),
                    "daily_used": float(lim.daily_used),
                    "weekly_used": float(lim.weekly_used),
                    "monthly_used": float(lim.monthly_used),
                    "status": lim.status,
                    "effective_from": lim.effective_from.isoformat() if lim.effective_from else None,
                },
                "limit_descriptors": _build_account_limit_descriptors(lim),
            })

        customers_out.append({
            "id": cust.id,
            "customer_number": cust.customer_number,
            "first_name": cust.first_name,
            "last_name": cust.last_name,
            "email": cust.email,
            "mobile_number": cust.mobile_number,
            "address": cust.address,
            **customer_profile_fields(cust),
            "customer_status": cust.customer_status,
            "risk_category": cust.risk_category,
            "institution_id": cust.institution_id,
            "institution_code": _short_bank_code(cust.institution, "XBANK"),
            "institution_name": cust.institution.name if cust.institution else None,
            "accounts": acct_list,
            "cards": card_list,
        })

    customers_out.sort(key=lambda x: x.get("customer_number") or "")

    try:
        db.commit()
    except Exception:
        db.rollback()

    return {
        "mode": mode,
        "query": clean_q,
        "customers": customers_out,
        "all_accounts": all_accounts_out,
        "all_customers": all_customers_mini,
        "total_customers": len(customers_out),
        "total_cards": sum(len(c["cards"]) for c in customers_out),
        "total_accounts": sum(len(c["accounts"]) for c in customers_out),
    }


@router.put("/cards/{card_id}/reassign-customer")
def reassign_card_customer(
    card_id: str,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Move a card to a different customer (lab maintenance)."""
    card = db.query(Card).filter(Card.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    new_cust_id = payload.get("customer_id")
    if not new_cust_id:
        raise HTTPException(status_code=400, detail="customer_id is required")
    new_cust = db.query(Customer).filter(Customer.id == new_cust_id).first()
    if not new_cust:
        raise HTTPException(status_code=404, detail="Target customer not found")

    before = serialize_entity(card)
    old_cust_id = card.customer_id
    card.customer_id = new_cust.id
    if new_cust.institution_id:
        card.institution_id = new_cust.institution_id
    after = serialize_entity(card)
    record_audit(
        db,
        "CARD",
        card.id,
        "REASSIGN_CUSTOMER",
        performed_by=current_user,
        before_state=before,
        after_state=after,
        change_summary=f"Reassigned card {card.masked_pan} from customer {old_cust_id} to {new_cust.customer_number}",
    )
    db.commit()
    db.refresh(card)
    return {
        "status": "reassigned",
        "card_id": card.id,
        "masked_pan": card.masked_pan,
        "new_customer_id": new_cust.id,
        "new_customer_number": new_cust.customer_number,
    }
