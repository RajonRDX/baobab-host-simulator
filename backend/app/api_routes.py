"""
MODULE 4 — api_routes.py
FastAPI endpoints for authentication, dashboard analytics, customers, accounts, cards,
limits, configurable transaction codes, TIC/ISO Transaction Simulator, HSM Key Management,
HSM Workbench, Host Execution Monitor (REST + WebSocket), and system logs.
"""

import asyncio
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
from app.logging_service import monitor_hub, record_system_log
from app.models import (
    Account,
    AccountLedger,
    AccountLimit,
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
    AccountCreate,
    AccountLimitUpdate,
    AccountOut,
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

@router.get("/customers", response_model=List[CustomerOut])
def list_customers(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    return db.query(Customer).order_by(Customer.created_at.desc()).all()


@router.post("/customers", response_model=CustomerOut)
def create_customer(payload: CustomerCreate, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    cust = Customer(**payload.model_dump())
    db.add(cust)
    record_system_log(db, "INFO", "CustomerService", "CUSTOMER_CREATED", f"Created customer {cust.customer_number}")
    db.commit()
    db.refresh(cust)
    return cust


@router.patch("/customers/{customer_id}/status")
def update_customer_status(customer_id: str, status: str, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    cust = db.query(Customer).filter(Customer.id == customer_id).first()
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    cust.customer_status = status.upper()
    db.commit()
    return {"id": cust.id, "customer_status": cust.customer_status}


@router.get("/accounts")
def list_accounts(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    accounts = db.query(Account).order_by(Account.created_at.desc()).all()
    out = []
    for a in accounts:
        lim = db.query(AccountLimit).filter(AccountLimit.account_id == a.id).first()
        out.append({
            "id": a.id,
            "account_number": a.account_number,
            "customer_id": a.customer_id,
            "customer_name": f"{a.customer.first_name} {a.customer.last_name or ''}".strip() if a.customer else "",
            "account_type": a.account_type,
            "currency": a.currency,
            "available_balance": float(a.available_balance),
            "ledger_balance": float(a.ledger_balance),
            "overdraft_limit": float(a.overdraft_limit),
            "account_status": a.account_status,
            "branch_code": a.branch_code,
            "limits": {
                "id": lim.id,
                "per_transaction_limit": float(lim.per_transaction_limit),
                "daily_limit": float(lim.daily_limit),
                "weekly_limit": float(lim.weekly_limit),
                "monthly_limit": float(lim.monthly_limit),
                "daily_used": float(lim.daily_used),
                "weekly_used": float(lim.weekly_used),
                "monthly_used": float(lim.monthly_used),
            } if lim else None,
        })
    return out


@router.post("/accounts", response_model=AccountOut)
def create_account(payload: AccountCreate, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    acct = Account(**payload.model_dump())
    db.add(acct)
    db.flush()
    db.add(AccountLimit(account_id=acct.id, currency=acct.currency))
    record_system_log(db, "INFO", "AccountService", "ACCOUNT_CREATED", f"Created account {acct.account_number}")
    db.commit()
    db.refresh(acct)
    return acct


@router.put("/accounts/{account_id}/limits")
def update_account_limits(account_id: str, payload: AccountLimitUpdate, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    lim = db.query(AccountLimit).filter(AccountLimit.account_id == account_id).first()
    if not lim:
        lim = AccountLimit(account_id=account_id)
        db.add(lim)
    for k, v in payload.model_dump().items():
        setattr(lim, k, v)
    db.commit()
    return {"status": "updated", "account_id": account_id}


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
def list_cards(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    cards = db.query(Card).order_by(Card.created_at.desc()).all()
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
    return out


@router.post("/cards", response_model=CardOut)
def create_card(payload: CardCreate, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    card = Card(
        customer_id=payload.customer_id,
        card_number_token=tokenize_pan(payload.test_pan_reference),
        test_pan_reference=payload.test_pan_reference,
        masked_pan=mask_pan(payload.test_pan_reference),
        cardholder_name=payload.cardholder_name,
        expiry_month=payload.expiry_month,
        expiry_year=payload.expiry_year,
        card_type=payload.card_type,
        card_product=payload.card_product,
        card_status=payload.card_status,
        linked_account_id=payload.linked_account_id,
        card_profile_id=payload.card_profile_id,
    )
    db.add(card)
    db.flush()

    db.add(CardAccount(card_id=card.id, account_id=payload.linked_account_id, account_role="PRIMARY", priority=1))
    db.add(CardLimit(card_id=card.id))
    db.add(
        PinProfile(
            card_id=card.id,
            pin_offset_reference=payload.pvv_or_offset,
            cvv_reference=payload.cvv_value,
        )
    )
    db.add(EmvProfile(card_id=card.id))
    record_system_log(db, "INFO", "CardService", "CARD_ISSUED", f"Issued card {card.masked_pan}")
    db.commit()
    db.refresh(card)
    return card


@router.patch("/cards/{card_id}/status")
def update_card_status(card_id: str, card_status: str, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    card = db.query(Card).filter(Card.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    card.card_status = card_status.upper()
    db.commit()
    return {"id": card.id, "card_status": card.card_status}


@router.put("/cards/{card_id}/limits")
def update_card_limits(card_id: str, payload: CardLimitUpdate, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    lim = db.query(CardLimit).filter(CardLimit.card_id == card_id).first()
    if not lim:
        lim = CardLimit(card_id=card_id)
        db.add(lim)
    for k, v in payload.model_dump().items():
        setattr(lim, k, v)
    db.commit()
    return {"status": "updated", "card_id": card_id}


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
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    q = db.query(Transaction)
    if stan:
        q = q.filter(Transaction.stan.contains(stan))
    if rrn:
        q = q.filter(Transaction.rrn.contains(rrn))
    if status:
        q = q.filter(Transaction.authorization_status == status.upper())
    txs = q.order_by(Transaction.created_at.desc()).limit(100).all()
    return [
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
            "created_at": t.created_at.isoformat(),
        }
        for t in txs
    ]


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

@router.get("/hsm/keys", response_model=List[HsmKeyReferenceOut])
def list_hsm_keys(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    return db.query(HsmKeyReference).order_by(HsmKeyReference.created_at.asc()).all()


@router.post("/hsm/keys", response_model=HsmKeyReferenceOut)
def register_hsm_key(payload: HsmKeyReferenceCreate, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    key_rec = HsmKeyReference(**payload.model_dump())
    db.add(key_rec)
    record_system_log(db, "INFO", "HSMKeyManagement", "KEY_REGISTERED", f"Registered key reference {key_rec.key_identifier} (KVC {key_rec.kvc})")
    db.commit()
    db.refresh(key_rec)
    return key_rec


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
