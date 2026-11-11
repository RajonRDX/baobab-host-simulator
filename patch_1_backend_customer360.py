"""
patch_1_backend_customer360.py
Run in the project folder (or pass the folder):   python patch_1_backend_customer360.py
Adds: extra customer fields (father, mother, NID, passport ...), Customer 360 endpoints (limits with
max/usage, reset, edit, last transactions, edit card incl. expiry) and a free card expiry date.
Idempotent: running it twice is safe. Backups go to _backups/.
"""

PATCH_NAME = "patch1_backend"

CUSTOMER_360_PY = r'''"""
customer_360.py
Customer Maintenance 360 - backend extensions for the Rajon Host Simulator.

Adds (without touching any existing endpoint):
  GET  /api/maintenance/card/{card_id}/limits            max + usage of every limit that affects a card
  POST /api/maintenance/card/{card_id}/limits/reset      reset usage (legacy counters and/or profile limits)
  PATCH /api/maintenance/card/{card_id}/legacy-limits    edit per-card thresholds (partial update)
  PATCH /api/maintenance/account/{account_id}/legacy-limits   edit per-account thresholds (partial update)
  PUT  /api/maintenance/profile-limit/{assignment_id}/max     edit the maximum of a profile limit
  PUT  /api/maintenance/card/{card_id}                   edit card (name, expiry, status, product)
  GET  /api/maintenance/transactions                     last N transactions of a card / account / customer

Two limit systems exist in the host and BOTH are enforced during authorization:
  * LEGACY   card_limits / account_limits    (per-transaction + daily check; weekly / monthly are tracked)
  * PROFILE  limit_definitions + limit_usage_records, resolved BIN -> Card Profile -> Authorization Profile
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.audit_service import record_audit, serialize_entity
from app.database import get_db
from app.limit_engine import LimitCalculationEngine, compute_reset_window
from app.models import (
    Account,
    AccountLimit,
    Card,
    CardLimit,
    Customer,
    PinProfile,
    Transaction,
)
from app.models_limits_profiles import (
    AuthProfileLimitAssignment,
    LimitUsageRecord,
)
from app.security import get_current_user

logger = logging.getLogger("rajon.customer360")

router = APIRouter(prefix="/api/maintenance", tags=["Customer Maintenance 360"])

# ----------------------------------------------------------------------------
# Customer profile fields (used by /maintenance/search and the Customers page)
# ----------------------------------------------------------------------------
CUSTOMER_EXTRA_TEXT_FIELDS: Tuple[str, ...] = (
    "father_name",
    "mother_name",
    "spouse_name",
    "gender",
    "marital_status",
    "nationality",
    "place_of_birth",
    "nid_number",
    "passport_number",
    "driving_license_number",
    "tin_number",
    "occupation",
    "employer_name",
    "alternate_mobile",
    "permanent_address",
    "city",
    "postal_code",
    "country",
    "kyc_status",
    "notes",
)


def customer_profile_fields(cust: Any) -> Dict[str, Any]:
    """Extra identity fields of a customer as JSON-safe values (safe even on old rows)."""
    out: Dict[str, Any] = {}
    dob = getattr(cust, "date_of_birth", None)
    out["date_of_birth"] = dob.isoformat() if dob else None
    pexp = getattr(cust, "passport_expiry_date", None)
    out["passport_expiry_date"] = pexp.isoformat() if pexp else None
    for name in CUSTOMER_EXTRA_TEXT_FIELDS:
        out[name] = getattr(cust, name, None)
    created = getattr(cust, "created_at", None)
    out["created_at"] = created.isoformat() if created else None
    return out


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------
def _f(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _pct(used: Optional[float], maximum: float) -> Optional[float]:
    if used is None or not maximum:
        return None
    return round(min(999.0, used * 100.0 / maximum), 1)


def _dec(value: Any, field: str) -> Decimal:
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise HTTPException(status_code=400, detail=f"{field} must be a number")
    if d < 0:
        raise HTTPException(status_code=400, detail=f"{field} cannot be negative")
    return d.quantize(Decimal("0.01"))


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _linked_accounts(db: Session, card: Card) -> List[Tuple[Account, str, int]]:
    """Accounts linked to a card, primary first. Falls back to the legacy linked_account_id."""
    seen: set = set()
    result: List[Tuple[Account, str, int]] = []
    links = sorted(card.card_accounts or [], key=lambda x: (x.priority or 99))
    for ca in links:
        if ca.account_id in seen:
            continue
        acct = db.query(Account).filter(Account.id == ca.account_id).first()
        if acct:
            seen.add(acct.id)
            result.append((acct, ca.account_role or "PRIMARY", ca.priority or 1))
    if not result and card.linked_account_id:
        acct = db.query(Account).filter(Account.id == card.linked_account_id).first()
        if acct:
            result.append((acct, "PRIMARY", 1))
    return result


def _get_card(db: Session, card_id: str) -> Card:
    card = db.query(Card).filter(Card.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    return card


def _ensure_card_limit(db: Session, card: Card) -> CardLimit:
    lim = db.query(CardLimit).filter(CardLimit.card_id == card.id).first()
    if not lim:
        lim = CardLimit(card_id=card.id, currency="BDT")
        db.add(lim)
        db.flush()
    return lim


def _ensure_account_limit(db: Session, acct: Account) -> AccountLimit:
    lim = db.query(AccountLimit).filter(AccountLimit.account_id == acct.id).first()
    if not lim:
        lim = AccountLimit(account_id=acct.id, currency=acct.currency)
        db.add(lim)
        db.flush()
    return lim


# ----------------------------------------------------------------------------
# LEGACY limit rows
# ----------------------------------------------------------------------------
# (field, label, period, used_field, enforced_by_host_engine)
_CARD_LEGACY_DEF = [
    ("transaction_limit", "Per-Transaction Limit", "PER_TRANSACTION", None, True),
    ("daily_limit", "Daily Limit", "DAILY", "daily_used", True),
    ("weekly_limit", "Weekly Limit", "WEEKLY", "weekly_used", False),
    ("monthly_limit", "Monthly Limit", "MONTHLY", "monthly_used", False),
    ("withdrawal_limit", "ATM Withdrawal Cap", "CHANNEL", None, False),
    ("purchase_limit", "POS Purchase Cap", "CHANNEL", None, False),
    ("ecommerce_limit", "E-Commerce Cap", "CHANNEL", None, False),
]
_ACCOUNT_LEGACY_DEF = [
    ("per_transaction_limit", "Per-Transaction Limit", "PER_TRANSACTION", None, True),
    ("daily_limit", "Daily Limit", "DAILY", "daily_used", True),
    ("weekly_limit", "Weekly Limit", "WEEKLY", "weekly_used", False),
    ("monthly_limit", "Monthly Limit", "MONTHLY", "monthly_used", False),
]


def _legacy_rows(lim: Any, definition: list, scope: str, target_id: str, label: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for field, name, period, used_field, enforced in definition:
        maximum = _f(getattr(lim, field, 0))
        used = _f(getattr(lim, used_field, 0)) if used_field else None
        rows.append(
            {
                "row_id": f"LEGACY:{scope}:{target_id}:{field}",
                "source": "LEGACY",
                "scope": scope,
                "target_id": target_id,
                "target_label": label,
                "key": field,
                "name": name,
                "period": period,
                "unit": "AMOUNT",
                "currency": getattr(lim, "currency", "BDT"),
                "max": maximum,
                "used": used,
                "remaining": max(0.0, maximum - used) if used is not None else None,
                "percent": _pct(used, maximum),
                "enforced": enforced,
                "status": getattr(lim, "status", "ACTIVE"),
                "editable": True,
            }
        )
    return rows


# ----------------------------------------------------------------------------
# PROFILE (limit engine) rows
# ----------------------------------------------------------------------------
def _usage_value(rec: Optional[LimitUsageRecord], method: str) -> float:
    if rec is None:
        return 0.0
    m = (method or "").upper()
    if m == "COUNT_TRANSACTION":
        return _f(rec.consumed_count)
    if m == "MAX_SINGLE_TRANSACTION":
        return _f(rec.max_single_amount)
    if m == "MIN_SINGLE_TRANSACTION":
        return _f(rec.min_single_amount)
    return _f(rec.consumed_amount)


def _profile_rows(
    db: Session, card: Card, accounts: List[Tuple[Account, str, int]]
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    engine = LimitCalculationEngine(db)
    bin_row, card_profile = engine.resolve_card_profile(card)
    auth = engine.resolve_authorization_profile(card_profile) if card_profile else None

    info: Dict[str, Any] = {
        "bin_prefix": getattr(bin_row, "bin_prefix", None),
        "card_profile_code": getattr(card_profile, "profile_code", None),
        "card_profile_name": getattr(card_profile, "profile_name", None),
        "auth_profile_code": getattr(auth, "auth_profile_code", None),
        "auth_profile_name": getattr(auth, "profile_name", None),
        "note": None,
    }
    rows: List[Dict[str, Any]] = []
    if not card_profile:
        info["note"] = "No active Card Profile resolved for this card (check the BIN or card profile assignment)."
        return info, rows
    if not auth:
        info["note"] = "No active Authorization Profile is linked to the card profile, so no profile limits apply."
        return info, rows

    assigns = (
        db.query(AuthProfileLimitAssignment)
        .filter(
            AuthProfileLimitAssignment.authorization_profile_id == auth.id,
            AuthProfileLimitAssignment.status == "ACTIVE",
        )
        .order_by(AuthProfileLimitAssignment.evaluation_priority.asc())
        .all()
    )
    seen: set = set()
    for a in assigns:
        ldef = a.limit_definition
        if not ldef or ldef.status != "ACTIVE" or ldef.id in seen:
            continue
        seen.add(ldef.id)
        scope = (ldef.scope or "CARD").upper()
        method = (a.calculation_method_override or ldef.calculation_method or "SUM_TRANSACTION_AMOUNT").upper()
        eff_max = a.maximum_limit_override if a.maximum_limit_override is not None else ldef.maximum_limit
        interval = (ldef.reset_interval or "DAILY").upper()
        unit = "COUNT" if method == "COUNT_TRANSACTION" else "AMOUNT"

        if scope == "CARD":
            targets = [(card.id, card.masked_pan)]
        else:
            targets = [(acct.id, acct.account_number) for acct, _, _ in accounts]

        for target_id, label in targets:
            win_key, win_start, win_end = compute_reset_window(
                interval, reset_interval_hours=ldef.reset_interval_hours
            )
            used: Optional[float]
            if interval == "PER_TRANSACTION":
                used = None
            else:
                rec = (
                    db.query(LimitUsageRecord)
                    .filter(
                        LimitUsageRecord.scope == scope,
                        LimitUsageRecord.target_entity_id == target_id,
                        LimitUsageRecord.limit_definition_id == ldef.id,
                        LimitUsageRecord.window_key == win_key,
                    )
                    .first()
                )
                used = _usage_value(rec, method)
            maximum = _f(eff_max)
            rows.append(
                {
                    "row_id": f"PROFILE:{scope}:{target_id}:{ldef.id}",
                    "source": "PROFILE",
                    "scope": scope,
                    "target_id": target_id,
                    "target_label": label,
                    "key": ldef.limit_code,
                    "name": ldef.limit_name,
                    "limit_code": ldef.limit_code,
                    "period": interval,
                    "unit": unit,
                    "currency": ldef.currency,
                    "max": maximum,
                    "used": used,
                    "remaining": max(0.0, maximum - used) if used is not None else None,
                    "percent": _pct(used, maximum),
                    "window_key": win_key if interval != "PER_TRANSACTION" else None,
                    "resets_at": _iso(win_end) if interval != "PER_TRANSACTION" else None,
                    "method": method,
                    "operator": a.comparison_operator_override or ldef.comparison_operator,
                    "impact_action": a.impact_action_override or ldef.impact_action,
                    "decline_rc": a.decline_response_code_override or ldef.decline_response_code,
                    "override_active": a.maximum_limit_override is not None,
                    "definition_id": ldef.id,
                    "assignment_id": a.id,
                    "enforced": True,
                    "status": ldef.status,
                    "editable": True,
                }
            )
    return info, rows


# ----------------------------------------------------------------------------
# GET limits
# ----------------------------------------------------------------------------
@router.get("/card/{card_id}/limits")
def card_limits_360(
    card_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    card = _get_card(db, card_id)
    accounts = _linked_accounts(db, card)

    c_lim = _ensure_card_limit(db, card)
    legacy_card = {
        "limit_id": c_lim.id,
        "status": c_lim.status,
        "currency": c_lim.currency,
        "rows": _legacy_rows(c_lim, _CARD_LEGACY_DEF, "CARD", card.id, card.masked_pan),
    }
    legacy_accounts = []
    for acct, role, priority in accounts:
        a_lim = _ensure_account_limit(db, acct)
        legacy_accounts.append(
            {
                "account_id": acct.id,
                "account_number": acct.account_number,
                "account_type": acct.account_type,
                "account_role": role,
                "currency": acct.currency,
                "limit_id": a_lim.id,
                "status": a_lim.status,
                "rows": _legacy_rows(a_lim, _ACCOUNT_LEGACY_DEF, "ACCOUNT", acct.id, acct.account_number),
            }
        )
    info, profile_rows = _profile_rows(db, card, accounts)
    db.commit()
    return {
        "card": {"id": card.id, "masked_pan": card.masked_pan, "card_status": card.card_status},
        "legacy": {"card": legacy_card, "accounts": legacy_accounts},
        "profile": {"info": info, "rows": profile_rows},
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ----------------------------------------------------------------------------
# RESET usage
# ----------------------------------------------------------------------------
class LimitResetBody(BaseModel):
    target: str = Field("ALL", description="ALL | LEGACY | PROFILE")
    period: str = Field("ALL", description="Legacy counters: DAILY | WEEKLY | MONTHLY | ALL")
    limit_definition_id: Optional[str] = Field(None, description="Profile limits: reset only this definition")
    account_id: Optional[str] = Field(None, description="Restrict the reset to one linked account")
    include_card: bool = True
    reason: str = Field("Customer 360 manual reset", min_length=3, max_length=250)


def _zero_legacy(lim: Any, period: str) -> Dict[str, Any]:
    old = {
        "daily_used": _f(lim.daily_used),
        "weekly_used": _f(lim.weekly_used),
        "monthly_used": _f(lim.monthly_used),
    }
    if period in ("DAILY", "ALL"):
        lim.daily_used = Decimal("0.00")
    if period in ("WEEKLY", "ALL"):
        lim.weekly_used = Decimal("0.00")
    if period in ("MONTHLY", "ALL"):
        lim.monthly_used = Decimal("0.00")
    new = {
        "daily_used": _f(lim.daily_used),
        "weekly_used": _f(lim.weekly_used),
        "monthly_used": _f(lim.monthly_used),
    }
    return {"old": old, "new": new}


@router.post("/card/{card_id}/limits/reset")
def reset_card_limits_360(
    card_id: str,
    body: LimitResetBody,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    target = (body.target or "ALL").upper().strip()
    period = (body.period or "ALL").upper().strip()
    if target not in ("ALL", "LEGACY", "PROFILE"):
        raise HTTPException(status_code=400, detail="target must be ALL, LEGACY or PROFILE")
    if period not in ("ALL", "DAILY", "WEEKLY", "MONTHLY"):
        raise HTTPException(status_code=400, detail="period must be ALL, DAILY, WEEKLY or MONTHLY")
    reason = (body.reason or "").strip()
    if len(reason) < 3:
        raise HTTPException(status_code=400, detail="A reason of at least 3 characters is required")

    card = _get_card(db, card_id)
    accounts = _linked_accounts(db, card)
    if body.account_id:
        accounts = [t for t in accounts if t[0].id == body.account_id]
        if not accounts:
            raise HTTPException(status_code=404, detail="Account is not linked to this card")

    summary: Dict[str, Any] = {"legacy": [], "profile_records_reset": 0}

    if target in ("ALL", "LEGACY"):
        if body.include_card:
            c_lim = _ensure_card_limit(db, card)
            before = serialize_entity(c_lim)
            res = _zero_legacy(c_lim, period)
            record_audit(
                db, "CARD_LIMIT", c_lim.id, "RESET_USAGE", performed_by=current_user,
                before_state=before, after_state=serialize_entity(c_lim),
                change_summary=f"Customer 360 reset ({period}) of card {card.masked_pan}: {reason}",
            )
            summary["legacy"].append({"entity": "CARD", "label": card.masked_pan, **res})
        for acct, _, _ in accounts:
            a_lim = _ensure_account_limit(db, acct)
            before = serialize_entity(a_lim)
            res = _zero_legacy(a_lim, period)
            record_audit(
                db, "ACCOUNT_LIMIT", a_lim.id, "RESET_USAGE", performed_by=current_user,
                before_state=before, after_state=serialize_entity(a_lim),
                change_summary=f"Customer 360 reset ({period}) of account {acct.account_number}: {reason}",
            )
            summary["legacy"].append({"entity": "ACCOUNT", "label": acct.account_number, **res})

    if target in ("ALL", "PROFILE"):
        targets: List[Tuple[str, str]] = []
        if body.include_card:
            targets.append(("CARD", card.id))
        targets.extend(("ACCOUNT", acct.id) for acct, _, _ in accounts)
        count = 0
        for scope, tid in targets:
            q = db.query(LimitUsageRecord).filter(
                LimitUsageRecord.scope == scope, LimitUsageRecord.target_entity_id == tid
            )
            if body.limit_definition_id:
                q = q.filter(LimitUsageRecord.limit_definition_id == body.limit_definition_id)
            for r in q.all():
                r.consumed_amount = Decimal("0.00")
                r.consumed_count = 0
                r.reserved_amount = Decimal("0.00")
                r.max_single_amount = Decimal("0.00")
                r.min_single_amount = None
                count += 1
        summary["profile_records_reset"] = count
        record_audit(
            db, "CARD", card.id, "RESET_PROFILE_LIMIT_USAGE", performed_by=current_user,
            change_summary=f"Customer 360 reset {count} profile limit usage record(s) for card {card.masked_pan}: {reason}",
        )

    db.commit()
    return {"status": "reset", "target": target, "period": period, "reason": reason, **summary}


# ----------------------------------------------------------------------------
# EDIT legacy limits (partial update)
# ----------------------------------------------------------------------------
class CardLegacyLimitPatch(BaseModel):
    transaction_limit: Optional[Decimal] = None
    daily_limit: Optional[Decimal] = None
    weekly_limit: Optional[Decimal] = None
    monthly_limit: Optional[Decimal] = None
    withdrawal_limit: Optional[Decimal] = None
    purchase_limit: Optional[Decimal] = None
    ecommerce_limit: Optional[Decimal] = None
    status: Optional[str] = None


class AccountLegacyLimitPatch(BaseModel):
    per_transaction_limit: Optional[Decimal] = None
    daily_limit: Optional[Decimal] = None
    weekly_limit: Optional[Decimal] = None
    monthly_limit: Optional[Decimal] = None
    status: Optional[str] = None


def _apply_patch(lim: Any, patch: BaseModel) -> None:
    for key, value in patch.model_dump(exclude_unset=True).items():
        if value is None:
            continue
        if key == "status":
            status = str(value).upper().strip()
            if status not in ("ACTIVE", "INACTIVE", "SUSPENDED"):
                raise HTTPException(status_code=400, detail="status must be ACTIVE, INACTIVE or SUSPENDED")
            lim.status = status
        else:
            setattr(lim, key, _dec(value, key))


@router.patch("/card/{card_id}/legacy-limits")
def patch_card_legacy_limits(
    card_id: str,
    body: CardLegacyLimitPatch,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    card = _get_card(db, card_id)
    lim = _ensure_card_limit(db, card)
    before = serialize_entity(lim)
    _apply_patch(lim, body)
    record_audit(
        db, "CARD_LIMIT", lim.id, "UPDATE_CONFIG", performed_by=current_user,
        before_state=before, after_state=serialize_entity(lim),
        change_summary=f"Customer 360 edited limit thresholds of card {card.masked_pan}",
    )
    db.commit()
    return {"status": "updated", "card_id": card.id, "limits": serialize_entity(lim)}


@router.patch("/account/{account_id}/legacy-limits")
def patch_account_legacy_limits(
    account_id: str,
    body: AccountLegacyLimitPatch,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    acct = db.query(Account).filter(Account.id == account_id).first()
    if not acct:
        raise HTTPException(status_code=404, detail="Account not found")
    lim = _ensure_account_limit(db, acct)
    before = serialize_entity(lim)
    _apply_patch(lim, body)
    record_audit(
        db, "ACCOUNT_LIMIT", lim.id, "UPDATE_CONFIG", performed_by=current_user,
        before_state=before, after_state=serialize_entity(lim),
        change_summary=f"Customer 360 edited limit thresholds of account {acct.account_number}",
    )
    db.commit()
    return {"status": "updated", "account_id": acct.id, "limits": serialize_entity(lim)}


class ProfileLimitMaxBody(BaseModel):
    maximum_limit: Optional[Decimal] = Field(None, description="New maximum, or null to remove the override")


@router.put("/profile-limit/{assignment_id}/max")
def edit_profile_limit_max(
    assignment_id: str,
    body: ProfileLimitMaxBody,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Edits the maximum override of a limit assigned to an Authorization Profile.
    NOTE: it applies to every card that uses that Authorization Profile."""
    a = db.query(AuthProfileLimitAssignment).filter(AuthProfileLimitAssignment.id == assignment_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Limit assignment not found")
    before = serialize_entity(a)
    a.maximum_limit_override = None if body.maximum_limit is None else _dec(body.maximum_limit, "maximum_limit")
    code = a.limit_definition.limit_code if a.limit_definition else a.limit_definition_id
    record_audit(
        db, "AUTH_PROFILE_LIMIT", a.id, "UPDATE_MAX", performed_by=current_user,
        before_state=before, after_state=serialize_entity(a),
        change_summary=f"Customer 360 changed maximum of profile limit {code} to {a.maximum_limit_override}",
    )
    db.commit()
    return {
        "status": "updated",
        "assignment_id": a.id,
        "maximum_limit_override": _f(a.maximum_limit_override) if a.maximum_limit_override is not None else None,
    }


# ----------------------------------------------------------------------------
# EDIT card (expiry aware)
# ----------------------------------------------------------------------------
class CardEditBody(BaseModel):
    cardholder_name: Optional[str] = Field(None, max_length=120)
    expiry_month: Optional[int] = Field(None, ge=1, le=12)
    expiry_year: Optional[int] = Field(None, ge=2000, le=2099)
    card_status: Optional[str] = None
    card_product: Optional[str] = Field(None, max_length=60)
    card_type: Optional[str] = Field(None, max_length=30)


@router.put("/card/{card_id}")
def edit_card_360(
    card_id: str,
    body: CardEditBody,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    card = _get_card(db, card_id)
    before = serialize_entity(card)
    data = body.model_dump(exclude_unset=True)
    old_expiry = (card.expiry_year, card.expiry_month)

    if "cardholder_name" in data and data["cardholder_name"] is not None:
        name = data["cardholder_name"].strip().upper()
        if not name:
            raise HTTPException(status_code=400, detail="Cardholder name cannot be empty")
        card.cardholder_name = name
    for key in ("card_product", "card_type"):
        if data.get(key):
            setattr(card, key, data[key].strip())
    if data.get("card_status"):
        card.card_status = data["card_status"].upper().strip()
    if data.get("expiry_month") is not None:
        card.expiry_month = int(data["expiry_month"])
    if data.get("expiry_year") is not None:
        card.expiry_year = int(data["expiry_year"])

    warning: Optional[str] = None
    cvv_regenerated = False
    if (card.expiry_year, card.expiry_month) != old_expiry:
        # The CVV is derived from PAN + expiry, so it must be recalculated for the new expiry.
        try:
            from app.hsm_adapter import HSMAdapter

            yymm = f"{str(card.expiry_year)[-2:]}{int(card.expiry_month):02d}"
            new_cvv = HSMAdapter(db).generate_card_cvv(card.test_pan_reference, yymm, "101", "CVK_MAIN_01")
            pin_prof = db.query(PinProfile).filter(PinProfile.card_id == card.id).first()
            if pin_prof and new_cvv:
                pin_prof.cvv_reference = new_cvv
                cvv_regenerated = True
        except Exception as exc:  # HSM offline / key missing: keep the edit but tell the user
            logger.warning("CVV regeneration failed for card %s: %s", card.id, exc)
            warning = f"Expiry saved, but the CVV could not be recalculated ({exc}). Recalculate it in the PIN & Card Lab."

    record_audit(
        db, "CARD", card.id, "UPDATE", performed_by=current_user,
        before_state=before, after_state=serialize_entity(card),
        change_summary=f"Customer 360 edited card {card.masked_pan}"
        + (" (expiry changed, CVV recalculated)" if cvv_regenerated else ""),
    )
    db.commit()
    return {
        "status": "updated",
        "card_id": card.id,
        "expiry_month": card.expiry_month,
        "expiry_year": card.expiry_year,
        "cvv_regenerated": cvv_regenerated,
        "warning": warning,
    }


# ----------------------------------------------------------------------------
# TRANSACTIONS
# ----------------------------------------------------------------------------
@router.get("/transactions")
def maintenance_transactions(
    card_id: Optional[str] = Query(None),
    account_id: Optional[str] = Query(None),
    customer_id: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    q = db.query(Transaction)
    scope_label = ""
    if card_id:
        card = _get_card(db, card_id)
        q = q.filter(or_(Transaction.card_id == card.id, Transaction.masked_pan == card.masked_pan))
        scope_label = card.masked_pan
    elif account_id:
        acct = db.query(Account).filter(Account.id == account_id).first()
        if not acct:
            raise HTTPException(status_code=404, detail="Account not found")
        q = q.filter(
            or_(
                Transaction.account_id == acct.id,
                Transaction.source_account == acct.account_number,
                Transaction.destination_account == acct.account_number,
            )
        )
        scope_label = acct.account_number
    elif customer_id:
        cust = db.query(Customer).filter(Customer.id == customer_id).first()
        if not cust:
            raise HTTPException(status_code=404, detail="Customer not found")
        q = q.filter(Transaction.customer_id == cust.id)
        scope_label = cust.customer_number
    else:
        raise HTTPException(status_code=400, detail="Provide card_id, account_id or customer_id")

    total = q.count()
    rows = (
        q.order_by(Transaction.transaction_datetime.desc(), Transaction.created_at.desc())
        .limit(limit)
        .all()
    )
    items: List[Dict[str, Any]] = []
    approved = declined = 0
    approved_amount = 0.0
    for t in rows:
        ok = (t.response_code or "") in ("00", "0", "000") or (t.authorization_status or "").upper() == "APPROVED"
        if ok:
            approved += 1
            approved_amount += _f(t.transaction_amount)
        else:
            declined += 1
        items.append(
            {
                "id": t.id,
                "reference": t.transaction_reference,
                "datetime": _iso(t.transaction_datetime),
                "mti": t.mti,
                "transaction_code": t.transaction_code,
                "type_name": t.transaction_type_name,
                "amount": _f(t.transaction_amount),
                "currency": t.currency,
                "response_code": t.response_code,
                "response_message": t.response_message,
                "status": t.transaction_status,
                "authorization_status": t.authorization_status,
                "approved": ok,
                "decline_reason": t.decline_reason,
                "channel": t.source_channel,
                "terminal_id": t.terminal_id,
                "merchant_name": t.merchant_name,
                "merchant_id": t.merchant_id,
                "rrn": t.rrn,
                "stan": t.stan,
                "approval_code": t.approval_code,
                "masked_pan": t.masked_pan,
                "source_account": t.source_account,
                "destination_account": t.destination_account,
                "is_on_us": t.is_on_us,
            }
        )
    return {
        "scope": scope_label,
        "total": total,
        "returned": len(items),
        "summary": {"approved": approved, "declined": declined, "approved_amount": round(approved_amount, 2)},
        "items": items,
    }
'''

import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------- locate the project
def find_root():
    if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        return Path(sys.argv[1])
    cwd = Path.cwd()
    if (cwd / "backend" / "app").exists():
        return cwd
    here = Path(__file__).resolve().parent
    if (here / "backend" / "app").exists():
        return here
    return Path(r"E:\HOST_VSCODE\host-simulator-github-prod")


ROOT = find_root()
BACKUP = ROOT / "_backups" / f"{PATCH_NAME}_{datetime.now():%Y%m%d_%H%M%S}"
problems = []


def load(path):
    raw = path.read_bytes().decode("utf-8")
    return raw.replace("\r\n", "\n"), ("\r\n" in raw)


def save(path, text, crlf):
    if crlf:
        text = text.replace("\n", "\r\n")
    path.write_bytes(text.encode("utf-8"))


def backup(path):
    if not path.exists():
        return
    dest = BACKUP / path.relative_to(ROOT)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)


def check_syntax(path, text):
    if path.suffix == ".py":
        try:
            compile(text, str(path), "exec")
        except SyntaxError as exc:
            return f"syntax error: {exc}"
    return None


def edit(rel, label, marker, old, new, count=1):
    """Replace `old` by `new` in file `rel` (exactly `count` occurrences). Idempotent via `marker`."""
    path = ROOT / rel
    if not path.exists():
        print(f"[NOT FOUND] {rel} (file missing)  - {label}")
        problems.append(label)
        return
    text, crlf = load(path)
    if (marker and marker in text) or (old not in text and new in text):
        print(f"[ALREADY DONE] {label}")
        return
    found = text.count(old)
    if found != count:
        print(f"[NOT FOUND] {label}  ({rel}: expected {count} match, found {found})")
        problems.append(label)
        return
    new_text = text.replace(old, new)
    err = check_syntax(path, new_text)
    if err:
        print(f"[FAILED] {label}: {err}; file NOT changed")
        problems.append(label)
        return
    backup(path)
    save(path, new_text, crlf)
    print(f"[APPLIED] {label}")


def write_new(rel, label, marker, content):
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing, _ = load(path)
        if marker in existing:
            if existing.strip() == content.strip():
                print(f"[ALREADY DONE] {label}")
                return
        backup(path)
    err = check_syntax(path, content)
    if err:
        print(f"[FAILED] {label}: {err}")
        problems.append(label)
        return
    path.write_bytes(content.encode("utf-8"))
    print(f"[APPLIED] {label}")


def banner(title):
    print("=" * 72)
    print(f" {title}")
    print(f" Project folder: {ROOT}")
    print("=" * 72)
    if not (ROOT / "backend" / "app").exists():
        print("[STOP] backend/app not found here. Run from the project folder or pass the folder as argument.")
        sys.exit(2)


def finish(next_steps):
    print("=" * 72)
    if problems:
        print(f" FINISHED WITH {len(problems)} PROBLEM(S): " + "; ".join(problems))
        print(" Nothing else was touched for the failed edits. Send me this output if you need help.")
        sys.exit(1)
    print(f" Done. Backups: {BACKUP}")
    for s in next_steps:
        print(" " + s)
    print("=" * 72)


banner("PATCH 1/3  Backend: customer profile fields, limits 360, transactions, card expiry")

# ---------------------------------------------------------------- 1. new module
write_new("backend/app/customer_360.py", "new module backend/app/customer_360.py",
          "Customer Maintenance 360 - backend extensions", CUSTOMER_360_PY)

# ---------------------------------------------------------------- 2. models.py (new nullable columns; auto-added at startup)
edit("backend/app/models.py", "models.py: extra Customer columns", "[PATCH customer_360:profile_fields]",
'''    address: Mapped[Optional[str]] = mapped_column(Text)
    customer_status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
''',
'''    address: Mapped[Optional[str]] = mapped_column(Text)
    customer_status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    # [PATCH customer_360:profile_fields]
    father_name: Mapped[Optional[str]] = mapped_column(String(120))
    mother_name: Mapped[Optional[str]] = mapped_column(String(120))
    spouse_name: Mapped[Optional[str]] = mapped_column(String(120))
    gender: Mapped[Optional[str]] = mapped_column(String(20))
    marital_status: Mapped[Optional[str]] = mapped_column(String(20))
    nationality: Mapped[Optional[str]] = mapped_column(String(60))
    place_of_birth: Mapped[Optional[str]] = mapped_column(String(100))
    nid_number: Mapped[Optional[str]] = mapped_column(String(30))
    passport_number: Mapped[Optional[str]] = mapped_column(String(30))
    passport_expiry_date: Mapped[Optional[date]] = mapped_column(Date)
    driving_license_number: Mapped[Optional[str]] = mapped_column(String(40))
    tin_number: Mapped[Optional[str]] = mapped_column(String(30))
    occupation: Mapped[Optional[str]] = mapped_column(String(100))
    employer_name: Mapped[Optional[str]] = mapped_column(String(120))
    alternate_mobile: Mapped[Optional[str]] = mapped_column(String(30))
    permanent_address: Mapped[Optional[str]] = mapped_column(Text)
    city: Mapped[Optional[str]] = mapped_column(String(80))
    postal_code: Mapped[Optional[str]] = mapped_column(String(20))
    country: Mapped[Optional[str]] = mapped_column(String(60))
    kyc_status: Mapped[Optional[str]] = mapped_column(String(20))
    notes: Mapped[Optional[str]] = mapped_column(Text)
''')

# ---------------------------------------------------------------- 3. schemas.py
edit("backend/app/schemas.py", "schemas.py: CustomerCreate extra fields", "# [PATCH customer_360:schema_create]",
'''    customer_status: str = "ACTIVE"
    risk_category: str = "NORMAL"
    institution_id: Optional[str] = None


# [PATCH step02_01:schema_customer_out_inst_fixed]''',
'''    customer_status: str = "ACTIVE"
    risk_category: str = "NORMAL"
    institution_id: Optional[str] = None
    # [PATCH customer_360:schema_create]
    father_name: Optional[str] = None
    mother_name: Optional[str] = None
    spouse_name: Optional[str] = None
    gender: Optional[str] = None
    marital_status: Optional[str] = None
    nationality: Optional[str] = None
    place_of_birth: Optional[str] = None
    nid_number: Optional[str] = None
    passport_number: Optional[str] = None
    passport_expiry_date: Optional[date] = None
    driving_license_number: Optional[str] = None
    tin_number: Optional[str] = None
    occupation: Optional[str] = None
    employer_name: Optional[str] = None
    alternate_mobile: Optional[str] = None
    permanent_address: Optional[str] = None
    city: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    kyc_status: Optional[str] = None
    notes: Optional[str] = None


# [PATCH step02_01:schema_customer_out_inst_fixed]''')

edit("backend/app/schemas.py", "schemas.py: CustomerUpdate extra fields", "# [PATCH customer_360:schema_update]",
'''    customer_status: Optional[str] = None
    risk_category: Optional[str] = None
    institution_id: Optional[str] = None


class AccountUpdate(BaseModel):''',
'''    customer_status: Optional[str] = None
    risk_category: Optional[str] = None
    institution_id: Optional[str] = None
    # [PATCH customer_360:schema_update]
    father_name: Optional[str] = None
    mother_name: Optional[str] = None
    spouse_name: Optional[str] = None
    gender: Optional[str] = None
    marital_status: Optional[str] = None
    nationality: Optional[str] = None
    place_of_birth: Optional[str] = None
    nid_number: Optional[str] = None
    passport_number: Optional[str] = None
    passport_expiry_date: Optional[date] = None
    driving_license_number: Optional[str] = None
    tin_number: Optional[str] = None
    occupation: Optional[str] = None
    employer_name: Optional[str] = None
    alternate_mobile: Optional[str] = None
    permanent_address: Optional[str] = None
    city: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    kyc_status: Optional[str] = None
    notes: Optional[str] = None


class AccountUpdate(BaseModel):''')

# card expiry: allow any realistic year (also past years, to test EXPIRED CARD declines)
edit("backend/app/schemas.py", "schemas.py: CardCreate expiry year range 2000-2099", None,
     "    expiry_year: int = Field(..., ge=2024, le=2040)",
     "    expiry_year: int = Field(..., ge=2000, le=2099)")
edit("backend/app/schemas.py", "schemas.py: CardUpdate expiry year range 2000-2099", None,
     "    expiry_year: Optional[int] = Field(None, ge=2024, le=2040)",
     "    expiry_year: Optional[int] = Field(None, ge=2000, le=2099)")

edit("backend/app/schemas.py", "schemas.py: CardGenerateRequest expiry month/year", "# [PATCH customer_360:gen_expiry]",
'''    initial_pin: str = '1234'
    linked_account_id: Optional[str] = None
''',
'''    initial_pin: str = '1234'
    linked_account_id: Optional[str] = None
    # [PATCH customer_360:gen_expiry]
    expiry_month: Optional[int] = Field(None, ge=1, le=12)
    expiry_year: Optional[int] = Field(None, ge=2000, le=2099)
''')

# ---------------------------------------------------------------- 4. api_routes.py
edit("backend/app/api_routes.py", "api_routes.py: import customer_profile_fields", "from app.customer_360 import customer_profile_fields",
     "from app.audit_service import record_audit, serialize_entity\n",
     "from app.audit_service import record_audit, serialize_entity\nfrom app.customer_360 import customer_profile_fields\n")

edit("backend/app/api_routes.py", "api_routes.py: maintenance search also matches NID / passport / parents", "# [PATCH customer_360:search_more_fields]",
'''                | (Customer.mobile_number.ilike(term))
                | (Customer.email.ilike(term))
                | (Customer.id == exact)''',
'''                | (Customer.mobile_number.ilike(term))
                | (Customer.email.ilike(term))
                # [PATCH customer_360:search_more_fields]
                | (Customer.nid_number.ilike(term))
                | (Customer.passport_number.ilike(term))
                | (Customer.alternate_mobile.ilike(term))
                | (Customer.father_name.ilike(term))
                | (Customer.mother_name.ilike(term))
                | (Customer.id == exact)''')

edit("backend/app/api_routes.py", "api_routes.py: maintenance search returns all customer fields", "**customer_profile_fields(cust),",
'''            "address": cust.address,
            "customer_status": cust.customer_status,
            "risk_category": cust.risk_category,''',
'''            "address": cust.address,
            **customer_profile_fields(cust),
            "customer_status": cust.customer_status,
            "risk_category": cust.risk_category,''')

edit("backend/app/api_routes.py", "api_routes.py: generate-test-card CVV uses the real expiry", "# [PATCH customer_360:gen_card_expiry]",
'''    # Calculate PVV and CVV
    pvv_calc = calculate_visa_pvv_detailed(pan, payload.initial_pin, '1', 'PVK_VISA_01')
    cvv_calc = calculate_cvv_detailed(pan, '2812', '101', 'CVK_MAIN_01')
''',
'''    # [PATCH customer_360:gen_card_expiry]
    # Expiry is chosen by the user; default = 3 years from today (no more fixed 12/2028)
    _now = datetime.now(timezone.utc)
    exp_month = payload.expiry_month or _now.month
    exp_year = payload.expiry_year or (_now.year + 3)
    exp_yymm = f"{str(exp_year)[-2:]}{int(exp_month):02d}"

    # Calculate PVV and CVV (CVV depends on the expiry)
    pvv_calc = calculate_visa_pvv_detailed(pan, payload.initial_pin, '1', 'PVK_VISA_01')
    cvv_calc = calculate_cvv_detailed(pan, exp_yymm, '101', 'CVK_MAIN_01')
''')

edit("backend/app/api_routes.py", "api_routes.py: generate-test-card stores the chosen expiry", None,
'''        cardholder_name=payload.cardholder_name.upper(),
        expiry_month=12,
        expiry_year=2028,
        card_type=payload.card_type,''',
'''        cardholder_name=payload.cardholder_name.upper(),
        expiry_month=exp_month,
        expiry_year=exp_year,
        card_type=payload.card_type,''')

# ---------------------------------------------------------------- 5. main.py
edit("backend/app/main.py", "main.py: register customer_360 router", "# [PATCH customer_360:router]",
     "app.include_router(simulator_workbench_router)\n",
     "app.include_router(simulator_workbench_router)\n"
     "# [PATCH customer_360:router]\n"
     "from app.customer_360 import router as customer_360_router\n"
     "app.include_router(customer_360_router)\n")

finish([
    "Restart the backend (uvicorn). New customer columns are added to the database automatically at startup.",
    "Next: run PATCH 2/3 (frontend pages) and PATCH 3/3 (new Customer Maintenance 360 page).",
])
