"""
backend/app/routers/limits_and_profiles_router.py
=================================================
Authenticated REST endpoints for:
  - Module 1: Configurable Card Limit Management
  - Module 2: Configurable Account Limit Management
  - Module 3: Card Profile Management under BIN Management & BIN-to-Profile association
  - Module 4: Authorization Profile Management (Tabs A, B, C, D)
  - Limit Usage & Evaluation Audit Inspection
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.audit_service import record_audit, serialize_entity
from app.database import get_db
from app.limit_engine import LimitCalculationEngine, compute_reset_window, to_dec
from app.logging_service import record_system_log
from app.models import (
    Account,
    AuthorizationProfile,
    AuthProfileLimitAssignment,
    AuthProfileTxCodePermission,
    BinRange,
    Card,
    CardProfile,
    Institution,
    LimitDefinition,
    LimitEvaluationAudit,
    LimitTransactionConsumption,
    LimitUsageRecord,
    ProcessingSystem,
    TransactionCode,
    TxCodeLimitImpact,
)
from app.schemas import (
    AuthorizationProfileCreate,
    AuthorizationProfileOut,
    AuthorizationProfileUpdate,
    AuthProfileLimitAssignmentCreate,
    AuthProfileLimitAssignmentOut,
    AuthProfileTxPermissionCreate,
    AuthProfileTxPermissionOut,
    BinCardProfileAssignRequest,
    LimitDefinitionCreate,
    LimitDefinitionOut,
    LimitDefinitionUpdate,
    TxCodeLimitImpactCreate,
    TxCodeLimitImpactOut,
)
from app.security import get_current_user

router = APIRouter(prefix="/api", tags=["Limits & Authorization Profiles"])


def _serialize_limit_definition(
    db: Session,
    engine: LimitCalculationEngine,
    ldef: LimitDefinition,
    target_entity_id: Optional[str] = None,
) -> Dict[str, Any]:
    curr_val, win_key, _ = engine.get_current_limit_value(
        ldef, target_entity_id=target_entity_id
    )
    assigned_count = (
        db.query(AuthProfileLimitAssignment)
        .filter(AuthProfileLimitAssignment.limit_definition_id == ldef.id)
        .count()
    )
    usage_count = (
        db.query(LimitUsageRecord)
        .filter(LimitUsageRecord.limit_definition_id == ldef.id)
        .count()
    )
    eval_count = (
        db.query(LimitEvaluationAudit)
        .filter(LimitEvaluationAudit.limit_definition_id == ldef.id)
        .count()
    )
    inst = (
        db.query(Institution).filter(Institution.id == ldef.institution_id).first()
        if ldef.institution_id
        else None
    )
    return {
        "id": ldef.id,
        "limit_code": ldef.limit_code,
        "limit_name": ldef.limit_name,
        "description": ldef.description,
        "scope": ldef.scope,
        "currency": ldef.currency,
        "maximum_limit": float(to_dec(ldef.maximum_limit)),
        "current_value": float(curr_val),
        "active_window_key": win_key,
        "reset_interval": ldef.reset_interval,
        "reset_interval_hours": ldef.reset_interval_hours,
        "reset_anchor_time": ldef.reset_anchor_time,
        "calculation_method": ldef.calculation_method,
        "custom_aggregation_filter": ldef.custom_aggregation_filter,
        "comparison_operator": ldef.comparison_operator,
        "impact_action": ldef.impact_action,
        "decline_response_code": ldef.decline_response_code,
        "institution_id": ldef.institution_id,
        "institution_code": inst.institution_code if inst else "ALL",
        "status": ldef.status,
        "assigned_profiles_count": assigned_count,
        "historical_usage_count": usage_count + eval_count,
        "created_at": ldef.created_at.isoformat() if ldef.created_at else None,
        "updated_at": ldef.updated_at.isoformat() if ldef.updated_at else None,
    }


def _serialize_authorization_profile(
    db: Session,
    engine: LimitCalculationEngine,
    ap: AuthorizationProfile,
    target_card_id: Optional[str] = None,
    target_account_id: Optional[str] = None,
) -> Dict[str, Any]:
    cp = (
        db.query(CardProfile).filter(CardProfile.id == ap.card_profile_id).first()
        if ap.card_profile_id
        else None
    )
    inst = (
        db.query(Institution).filter(Institution.id == ap.institution_id).first()
        if ap.institution_id
        else None
    )
    tx_code_map = {
        tc.transaction_code: tc.transaction_name
        for tc in db.query(TransactionCode).all()
    }

    # Tab A: Allowed Transactions
    perms_out = []
    for p in ap.tx_permissions:
        perms_out.append({
            "id": p.id,
            "authorization_profile_id": p.authorization_profile_id,
            "transaction_code_id": p.transaction_code_id,
            "transaction_code": p.transaction_code,
            "transaction_name": p.transaction_name or tx_code_map.get(p.transaction_code, f"Code {p.transaction_code}"),
            "permission": p.permission,
            "decline_response_code": p.decline_response_code,
            "description": p.description,
            "status": p.status,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        })

    # Tab B & Tab C: Assigned Card Limits and Account Limits
    card_limits_out = []
    account_limits_out = []
    for assign in ap.limit_assignments:
        ldef = assign.limit_definition
        if not ldef:
            continue
        scope = (assign.scope or ldef.scope).upper()
        target_id = target_card_id if scope == "CARD" else target_account_id
        curr_val, win_key, _ = engine.get_current_limit_value(ldef, target_entity_id=target_id)
        eff_max = to_dec(
            assign.maximum_limit_override
            if assign.maximum_limit_override is not None
            else ldef.maximum_limit
        )
        eff_method = assign.calculation_method_override or ldef.calculation_method
        eff_op = assign.comparison_operator_override or ldef.comparison_operator
        eff_act = assign.impact_action_override or ldef.impact_action
        eff_rc = assign.decline_response_code_override or ldef.decline_response_code
        item = {
            "id": assign.id,
            "authorization_profile_id": assign.authorization_profile_id,
            "limit_definition_id": ldef.id,
            "limit_code": ldef.limit_code,
            "limit_name": ldef.limit_name,
            "description": ldef.description,
            "scope": scope,
            "currency": ldef.currency,
            "effective_maximum_limit": float(eff_max),
            "maximum_limit_override": float(assign.maximum_limit_override) if assign.maximum_limit_override is not None else None,
            "default_maximum_limit": float(to_dec(ldef.maximum_limit)),
            "effective_calculation_method": eff_method,
            "calculation_method_override": assign.calculation_method_override,
            "effective_comparison_operator": eff_op,
            "comparison_operator_override": assign.comparison_operator_override,
            "effective_impact_action": eff_act,
            "impact_action_override": assign.impact_action_override,
            "decline_response_code_override": eff_rc,
            "reset_interval": ldef.reset_interval,
            "current_value": float(curr_val),
            "active_window_key": win_key,
            "evaluation_priority": assign.evaluation_priority,
            "status": assign.status,
            "limit_status": ldef.status,
            "created_at": assign.created_at.isoformat() if assign.created_at else None,
        }
        if scope == "CARD":
            card_limits_out.append(item)
        else:
            account_limits_out.append(item)

    # Tab D: Transaction Code Limit Impacts
    impacts_out = []
    for imp in ap.tx_code_impacts:
        ldef = imp.limit_definition
        impacts_out.append({
            "id": imp.id,
            "authorization_profile_id": imp.authorization_profile_id,
            "transaction_code": imp.transaction_code,
            "transaction_name": tx_code_map.get(imp.transaction_code, f"Code {imp.transaction_code}"),
            "limit_definition_id": imp.limit_definition_id,
            "limit_code": ldef.limit_code if ldef else None,
            "limit_name": ldef.limit_name if ldef else None,
            "limit_scope": ldef.scope if ldef else None,
            "impact_type": imp.impact_type,
            "calculation_basis": imp.calculation_basis,
            "multiplier": float(to_dec(imp.multiplier)),
            "description": imp.description,
            "status": imp.status,
            "created_at": imp.created_at.isoformat() if imp.created_at else None,
        })

    # Associated BIN ranges via Card Profile
    bins_linked = []
    if cp:
        for b in db.query(BinRange).filter(BinRange.card_profile_id == cp.id).all():
            bins_linked.append({
                "id": b.id,
                "bin_prefix": b.bin_prefix,
                "card_product": b.card_product,
                "scheme": b.scheme,
                "status": b.status,
            })

    return {
        "id": ap.id,
        "auth_profile_code": ap.auth_profile_code,
        "profile_name": ap.profile_name,
        "description": ap.description,
        "card_profile_id": ap.card_profile_id,
        "card_profile_code": cp.profile_code if cp else None,
        "card_profile_name": cp.profile_name if cp else None,
        "institution_id": ap.institution_id,
        "institution_code": inst.institution_code if inst else (cp.institution.institution_code if (cp and cp.institution) else "XBANK"),
        "institution_name": inst.name if inst else (cp.institution.name if (cp and cp.institution) else "xBank PLC"),
        "unconfigured_tx_code_policy": ap.unconfigured_tx_code_policy,
        "unconfigured_decline_rc": ap.unconfigured_decline_rc,
        "status": ap.status,
        "effective_from": ap.effective_from.isoformat() if ap.effective_from else None,
        "effective_to": ap.effective_to.isoformat() if ap.effective_to else None,
        "created_at": ap.created_at.isoformat() if ap.created_at else None,
        "updated_at": ap.updated_at.isoformat() if ap.updated_at else None,
        "tx_permissions": perms_out,
        "card_limits": card_limits_out,
        "account_limits": account_limits_out,
        "tx_code_impacts": impacts_out,
        "linked_bins": bins_linked,
    }


# ==============================================================================
# MODULE 1 & 2: CARD & ACCOUNT LIMIT DEFINITIONS ENDPOINTS
# ==============================================================================

@router.get("/limit-definitions")
def list_limit_definitions(
    scope: Optional[str] = Query(None, description="CARD or ACCOUNT"),
    status: Optional[str] = Query(None, description="ACTIVE, INACTIVE, ARCHIVED"),
    q: Optional[str] = Query(None, description="Search by limit_code or limit_name"),
    target_entity_id: Optional[str] = Query(None, description="Optional card_id or account_id to compute entity-specific current usage"),
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    query = db.query(LimitDefinition)
    if scope:
        query = query.filter(LimitDefinition.scope == scope.upper().strip())
    if status:
        query = query.filter(LimitDefinition.status == status.upper().strip())
    if q:
        term = f"%{q.strip()}%"
        query = query.filter(
            (LimitDefinition.limit_code.ilike(term))
            | (LimitDefinition.limit_name.ilike(term))
            | (LimitDefinition.description.ilike(term))
        )
    defs = query.order_by(LimitDefinition.scope.asc(), LimitDefinition.limit_code.asc()).all()
    engine = LimitCalculationEngine(db)
    return [_serialize_limit_definition(db, engine, d, target_entity_id=target_entity_id) for d in defs]


@router.get("/limit-definitions/{limit_id}")
def get_limit_definition(
    limit_id: str,
    target_entity_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    ldef = (
        db.query(LimitDefinition)
        .filter((LimitDefinition.id == limit_id) | (LimitDefinition.limit_code == limit_id))
        .first()
    )
    if not ldef:
        raise HTTPException(status_code=404, detail="Limit definition not found")
    engine = LimitCalculationEngine(db)
    data = _serialize_limit_definition(db, engine, ldef, target_entity_id=target_entity_id)

    # Include recent usage records & evaluation audits
    usage_rows = (
        db.query(LimitUsageRecord)
        .filter(LimitUsageRecord.limit_definition_id == ldef.id)
        .order_by(LimitUsageRecord.last_updated_at.desc())
        .limit(25)
        .all()
    )
    data["usage_records"] = [
        {
            "id": u.id,
            "scope": u.scope,
            "target_entity_id": u.target_entity_id,
            "window_key": u.window_key,
            "consumed_amount": float(to_dec(u.consumed_amount)),
            "consumed_count": u.consumed_count,
            "max_single_amount": float(to_dec(u.max_single_amount)),
            "last_updated_at": u.last_updated_at.isoformat() if u.last_updated_at else None,
        }
        for u in usage_rows
    ]
    return data


@router.post("/limit-definitions")
def create_limit_definition(
    payload: LimitDefinitionCreate,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    code_clean = payload.limit_code.strip().upper()
    existing = db.query(LimitDefinition).filter(LimitDefinition.limit_code == code_clean).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Limit ID '{code_clean}' already exists ({existing.limit_name})",
        )
    data = payload.model_dump()
    data["limit_code"] = code_clean
    ldef = LimitDefinition(**data)
    db.add(ldef)
    db.flush()

    record_audit(
        db,
        f"{ldef.scope}_LIMIT_DEFINITION",
        ldef.id,
        "CREATE",
        performed_by=current_user,
        after_state=serialize_entity(ldef),
        change_summary=f"Created {ldef.scope} limit '{ldef.limit_code}' ({ldef.limit_name}) Max={ldef.maximum_limit} Op='{ldef.comparison_operator}'",
    )
    record_system_log(
        db,
        "INFO",
        "LimitManagement",
        "LIMIT_DEFINITION_CREATED",
        f"Created {ldef.scope} Limit {ldef.limit_code} ({ldef.limit_name})",
    )
    db.commit()
    db.refresh(ldef)
    engine = LimitCalculationEngine(db)
    return _serialize_limit_definition(db, engine, ldef)


@router.put("/limit-definitions/{limit_id}")
def update_limit_definition(
    limit_id: str,
    payload: LimitDefinitionUpdate,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    ldef = db.query(LimitDefinition).filter(LimitDefinition.id == limit_id).first()
    if not ldef:
        raise HTTPException(status_code=404, detail="Limit definition not found")
    before = serialize_entity(ldef)
    for k, v in payload.model_dump(exclude_unset=True).items():
        if k == "status" and v:
            v = v.upper().strip()
        setattr(ldef, k, v)
    after = serialize_entity(ldef)
    record_audit(
        db,
        f"{ldef.scope}_LIMIT_DEFINITION",
        ldef.id,
        "UPDATE",
        performed_by=current_user,
        before_state=before,
        after_state=after,
        change_summary=f"Updated {ldef.scope} limit '{ldef.limit_code}' ({ldef.limit_name})",
    )
    db.commit()
    db.refresh(ldef)
    engine = LimitCalculationEngine(db)
    return _serialize_limit_definition(db, engine, ldef)


@router.patch("/limit-definitions/{limit_id}/status")
def toggle_limit_definition_status(
    limit_id: str,
    status: str = Query(..., description="ACTIVE, INACTIVE, or ARCHIVED"),
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    ldef = db.query(LimitDefinition).filter(LimitDefinition.id == limit_id).first()
    if not ldef:
        raise HTTPException(status_code=404, detail="Limit definition not found")
    new_status = status.upper().strip()
    if new_status not in {"ACTIVE", "INACTIVE", "ARCHIVED"}:
        raise HTTPException(status_code=400, detail="status must be ACTIVE, INACTIVE, or ARCHIVED")
    before = serialize_entity(ldef)
    ldef.status = new_status
    after = serialize_entity(ldef)
    record_audit(
        db,
        f"{ldef.scope}_LIMIT_DEFINITION",
        ldef.id,
        "STATUS_CHANGE",
        performed_by=current_user,
        before_state=before,
        after_state=after,
        change_summary=f"Changed {ldef.scope} limit '{ldef.limit_code}' status to {new_status}",
    )
    db.commit()
    engine = LimitCalculationEngine(db)
    return _serialize_limit_definition(db, engine, ldef)


@router.delete("/limit-definitions/{limit_id}")
def delete_limit_definition(
    limit_id: str,
    archive_if_in_use: bool = Query(False, description="Deactivate/archive instead of hard deleting when referenced"),
    force: bool = Query(False, description="Force delete lab record and detach references"),
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    ldef = db.query(LimitDefinition).filter(LimitDefinition.id == limit_id).first()
    if not ldef:
        raise HTTPException(status_code=404, detail="Limit definition not found")

    active_assigns = (
        db.query(AuthProfileLimitAssignment)
        .filter(AuthProfileLimitAssignment.limit_definition_id == ldef.id)
        .count()
    )
    usage_count = (
        db.query(LimitUsageRecord)
        .filter(LimitUsageRecord.limit_definition_id == ldef.id)
        .count()
    )
    eval_count = (
        db.query(LimitEvaluationAudit)
        .filter(LimitEvaluationAudit.limit_definition_id == ldef.id)
        .count()
    )

    if (active_assigns > 0 or usage_count > 0 or eval_count > 0) and not force:
        if archive_if_in_use:
            before = serialize_entity(ldef)
            ldef.status = "INACTIVE"
            after = serialize_entity(ldef)
            record_audit(
                db,
                f"{ldef.scope}_LIMIT_DEFINITION",
                ldef.id,
                "DEACTIVATE_PROTECTED",
                performed_by=current_user,
                before_state=before,
                after_state=after,
                change_summary=(
                    f"Deactivated {ldef.scope} limit '{ldef.limit_code}' to preserve "
                    f"{active_assigns} profile assignment(s) and {usage_count + eval_count} historical usage record(s)"
                ),
            )
            db.commit()
            return {
                "status": "deactivated",
                "limit_id": ldef.id,
                "limit_code": ldef.limit_code,
                "message": (
                    f"Limit {ldef.limit_code} is assigned to {active_assigns} authorization profile(s) or has "
                    f"{usage_count + eval_count} historical usage record(s); safely deactivated instead of hard deletion."
                ),
            }
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot hard-delete {ldef.scope} Limit '{ldef.limit_code}' ({ldef.limit_name}) because it is "
                f"assigned to {active_assigns} Authorization Profile(s) and has {usage_count + eval_count} "
                f"historical usage/evaluation record(s). Deactivate it instead, or pass ?archive_if_in_use=true."
            ),
        )

    before = serialize_entity(ldef)
    db.query(AuthProfileLimitAssignment).filter(
        AuthProfileLimitAssignment.limit_definition_id == ldef.id
    ).delete(synchronize_session=False)
    db.query(TxCodeLimitImpact).filter(
        TxCodeLimitImpact.limit_definition_id == ldef.id
    ).delete(synchronize_session=False)
    db.query(LimitTransactionConsumption).filter(
        LimitTransactionConsumption.limit_definition_id == ldef.id
    ).delete(synchronize_session=False)
    db.query(LimitUsageRecord).filter(
        LimitUsageRecord.limit_definition_id == ldef.id
    ).delete(synchronize_session=False)
    db.delete(ldef)

    record_audit(
        db,
        f"{ldef.scope}_LIMIT_DEFINITION",
        limit_id,
        "DELETE",
        performed_by=current_user,
        before_state=before,
        change_summary=f"Deleted {ldef.scope} limit '{ldef.limit_code}' ({ldef.limit_name})",
    )
    db.commit()
    return {"status": "deleted", "limit_id": limit_id, "limit_code": ldef.limit_code}


@router.post("/limit-definitions/{limit_id}/reset-usage")
def reset_limit_definition_usage(
    limit_id: str,
    target_entity_id: Optional[str] = Query(None, description="Specific card_id or account_id to reset, or omit for all"),
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    ldef = db.query(LimitDefinition).filter(LimitDefinition.id == limit_id).first()
    if not ldef:
        raise HTTPException(status_code=404, detail="Limit definition not found")

    q = db.query(LimitUsageRecord).filter(LimitUsageRecord.limit_definition_id == ldef.id)
    if target_entity_id:
        q = q.filter(LimitUsageRecord.target_entity_id == target_entity_id)

    rows = q.all()
    reset_count = 0
    for r in rows:
        r.consumed_amount = Decimal("0.00")
        r.consumed_count = 0
        r.reserved_amount = Decimal("0.00")
        r.max_single_amount = Decimal("0.00")
        r.min_single_amount = None
        reset_count += 1

    record_audit(
        db,
        f"{ldef.scope}_LIMIT_DEFINITION",
        ldef.id,
        "RESET_USAGE",
        performed_by=current_user,
        change_summary=f"Reset {reset_count} usage window record(s) for limit {ldef.limit_code}",
    )
    db.commit()
    return {"status": "reset", "limit_id": ldef.id, "limit_code": ldef.limit_code, "records_reset": reset_count}


# ==============================================================================
# MODULE 3: CARD PROFILES & BIN-TO-CARD-PROFILE ASSOCIATION ENDPOINTS
# ==============================================================================

@router.get("/card-profiles-v2")
def list_card_profiles_detailed(
    institution_id: Optional[str] = Query(None),
    processing_system_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    q = db.query(CardProfile)
    if institution_id:
        q = q.filter(CardProfile.institution_id == institution_id)
    if processing_system_id:
        q = q.filter(CardProfile.processing_system_id == processing_system_id)
    if status:
        q = q.filter(CardProfile.status == status.upper().strip())

    profiles = q.order_by(CardProfile.profile_code.asc()).all()
    out = []
    for cp in profiles:
        inst = db.query(Institution).filter(Institution.id == cp.institution_id).first() if getattr(cp, "institution_id", None) else None
        ps = db.query(ProcessingSystem).filter(ProcessingSystem.id == cp.processing_system_id).first() if getattr(cp, "processing_system_id", None) else None
        bins = db.query(BinRange).filter(BinRange.card_profile_id == cp.id).all()
        auth_profs = db.query(AuthorizationProfile).filter(AuthorizationProfile.card_profile_id == cp.id).all()
        card_count = db.query(Card).filter(Card.card_profile_id == cp.id).count()
        out.append({
            "id": cp.id,
            "profile_code": cp.profile_code,
            "profile_name": cp.profile_name,
            "description": getattr(cp, "description", None),
            "institution_id": getattr(cp, "institution_id", None),
            "institution_code": inst.institution_code if inst else "XBANK",
            "institution_name": inst.name if inst else "xBank PLC",
            "processing_system_id": getattr(cp, "processing_system_id", None),
            "ps_code": ps.ps_code if ps else "ITCL",
            "ps_name": ps.name if ps else "ITCL Host Switch",
            "card_type": getattr(cp, "card_type", "DEBIT"),
            "currency": getattr(cp, "currency", "BDT"),
            "card_product": cp.card_product,
            "domestic_enabled": cp.domestic_enabled,
            "international_enabled": cp.international_enabled,
            "ecommerce_enabled": cp.ecommerce_enabled,
            "contactless_enabled": cp.contactless_enabled,
            "cash_enabled": cp.cash_enabled,
            "status": cp.status,
            "created_at": cp.created_at.isoformat() if getattr(cp, "created_at", None) else None,
            "card_count": card_count,
            "associated_bins": [
                {
                    "id": b.id,
                    "bin_prefix": b.bin_prefix,
                    "bin_low": b.bin_low,
                    "bin_high": b.bin_high,
                    "card_type": b.card_type,
                    "card_product": b.card_product,
                    "scheme": b.scheme,
                    "status": b.status,
                }
                for b in bins
            ],
            "authorization_profiles": [
                {
                    "id": ap.id,
                    "auth_profile_code": ap.auth_profile_code,
                    "profile_name": ap.profile_name,
                    "status": ap.status,
                }
                for ap in auth_profs
            ],
        })
    return out


@router.post("/card-profiles-v2")
def create_card_profile_v2(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    code = (payload.get("profile_code") or "").upper().strip()
    if not code:
        raise HTTPException(status_code=400, detail="profile_code is required")
    existing = db.query(CardProfile).filter(CardProfile.profile_code == code).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Card Profile '{code}' already exists")

    raw_inst = payload.get("institution_id")
    inst_id = None if raw_inst in (None, "", "ALL", "SHARED") else raw_inst
    ps_id = payload.get("processing_system_id") or None
    if not ps_id:
        itcl = db.query(ProcessingSystem).filter(ProcessingSystem.ps_code == "ITCL").first()
        ps_id = itcl.id if itcl else None
    if not ps_id:
        itcl = db.query(ProcessingSystem).filter(ProcessingSystem.ps_code == "ITCL").first()
        ps_id = itcl.id if itcl else None

    prof = CardProfile(
        profile_code=code,
        profile_name=(payload.get("profile_name") or code).strip(),
        description=payload.get("description"),
        institution_id=inst_id,
        processing_system_id=ps_id,
        card_type=(payload.get("card_type") or "DEBIT").upper().strip(),
        currency=(payload.get("currency") or "BDT").upper().strip(),
        card_product=(payload.get("card_product") or "VISA_DEBIT_CLASSIC").strip(),
        domestic_enabled=bool(payload.get("domestic_enabled", True)),
        international_enabled=bool(payload.get("international_enabled", False)),
        ecommerce_enabled=bool(payload.get("ecommerce_enabled", True)),
        contactless_enabled=bool(payload.get("contactless_enabled", True)),
        cash_enabled=bool(payload.get("cash_enabled", True)),
        status=(payload.get("status") or "ACTIVE").upper().strip(),
    )
    db.add(prof)
    db.flush()

    # Optional BIN range IDs to associate with this new Card Profile
    bin_ids = payload.get("bin_ids") or []
    for bid in bin_ids:
        b = db.query(BinRange).filter(BinRange.id == bid).first()
        if b:
            b.card_profile_id = prof.id

    record_audit(
        db,
        "CARD_PROFILE",
        prof.id,
        "CREATE",
        performed_by=current_user,
        after_state=serialize_entity(prof),
        change_summary=f"Created Card Profile '{prof.profile_code}' ({prof.profile_name})",
    )
    db.commit()
    db.refresh(prof)
    return list_card_profiles_detailed(db=db, _=current_user)


@router.put("/card-profiles-v2/{profile_id}")
def update_card_profile_v2(
    profile_id: str,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    prof = db.query(CardProfile).filter(CardProfile.id == profile_id).first()
    if not prof:
        raise HTTPException(status_code=404, detail="Card Profile not found")

    before = serialize_entity(prof)
    editable_fields = [
        "profile_name",
        "description",
        "institution_id",
        "processing_system_id",
        "card_type",
        "currency",
        "card_product",
        "domestic_enabled",
        "international_enabled",
        "ecommerce_enabled",
        "contactless_enabled",
        "cash_enabled",
        "status",
    ]
    for f in editable_fields:
        if f in payload and payload[f] is not None:
            setattr(prof, f, payload[f])

    after = serialize_entity(prof)
    if "institution_id" in payload and payload["institution_id"] in ("", "ALL", "SHARED", None):
        prof.institution_id = None

    if "bin_ids" in payload and isinstance(payload["bin_ids"], list):
        target_bin_ids = set(str(x) for x in payload["bin_ids"] if x)
        # Unassign BINs previously linked to this profile that are no longer in target_bin_ids
        for b in db.query(BinRange).filter(BinRange.card_profile_id == prof.id).all():
            if b.id not in target_bin_ids:
                b.card_profile_id = None
        # Assign selected BINs to this profile
        for bid in target_bin_ids:
            b = db.query(BinRange).filter(BinRange.id == bid).first()
            if b:
                b.card_profile_id = prof.id

    record_audit(
        db,
        "CARD_PROFILE",
        prof.id,
        "UPDATE",
        performed_by=current_user,
        before_state=before,
        after_state=after,
        change_summary=f"Updated Card Profile '{prof.profile_code}'",
    )
    db.commit()
    return {"status": "updated", "id": prof.id, "profile_code": prof.profile_code}


@router.put("/bins/{bin_id}/assign-card-profile")
def assign_card_profile_to_bin(
    bin_id: str,
    payload: BinCardProfileAssignRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    Associates or unassigns a Card Profile on a BIN Range.
    Validates institution/switch consistency and NEVER silently mutates existing cards' profile assignments.
    """
    b = db.query(BinRange).filter(BinRange.id == bin_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="BIN Range not found")

    before = serialize_entity(b)
    if payload.card_profile_id:
        cp = db.query(CardProfile).filter(CardProfile.id == payload.card_profile_id).first()
        if not cp:
            raise HTTPException(status_code=404, detail="Target Card Profile not found")
        if cp.status != "ACTIVE":
            raise HTTPException(
                status_code=400,
                detail=f"Cannot assign inactive Card Profile '{cp.profile_code}' to BIN '{b.bin_prefix}'",
            )
        # Allow assigning any active Card Profile across member bank BIN ranges
        b.card_profile_id = cp.id
        summary = f"Assigned Card Profile '{cp.profile_code}' to BIN '{b.bin_prefix}'"
    else:
        b.card_profile_id = None
        summary = f"Removed Card Profile assignment from BIN '{b.bin_prefix}'"

    after = serialize_entity(b)
    record_audit(
        db,
        "BIN_RANGE",
        b.id,
        "ASSIGN_CARD_PROFILE",
        performed_by=current_user,
        before_state=before,
        after_state=after,
        change_summary=summary,
    )
    db.commit()
    db.refresh(b)
    return {
        "status": "updated",
        "bin_id": b.id,
        "bin_prefix": b.bin_prefix,
        "card_profile_id": b.card_profile_id,
        "card_profile_code": b.card_profile.profile_code if b.card_profile else None,
        "card_profile_name": b.card_profile.profile_name if b.card_profile else None,
    }


# ==============================================================================
# MODULE 4: AUTHORIZATION PROFILES & TABS A, B, C, D ENDPOINTS
# ==============================================================================

@router.get("/authorization-profiles")
def list_authorization_profiles(
    card_profile_id: Optional[str] = Query(None),
    institution_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    target_card_id: Optional[str] = Query(None),
    target_account_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    q = db.query(AuthorizationProfile)
    if card_profile_id:
        q = q.filter(AuthorizationProfile.card_profile_id == card_profile_id)
    if institution_id:
        q = q.filter(AuthorizationProfile.institution_id == institution_id)
    if status:
        q = q.filter(AuthorizationProfile.status == status.upper().strip())

    profiles = q.order_by(AuthorizationProfile.auth_profile_code.asc()).all()
    engine = LimitCalculationEngine(db)
    return [
        _serialize_authorization_profile(
            db,
            engine,
            ap,
            target_card_id=target_card_id,
            target_account_id=target_account_id,
        )
        for ap in profiles
    ]


@router.get("/authorization-profiles/{auth_profile_id}")
def get_authorization_profile(
    auth_profile_id: str,
    target_card_id: Optional[str] = Query(None),
    target_account_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    ap = (
        db.query(AuthorizationProfile)
        .filter(
            (AuthorizationProfile.id == auth_profile_id)
            | (AuthorizationProfile.auth_profile_code == auth_profile_id)
        )
        .first()
    )
    if not ap:
        raise HTTPException(status_code=404, detail="Authorization Profile not found")
    engine = LimitCalculationEngine(db)
    return _serialize_authorization_profile(
        db,
        engine,
        ap,
        target_card_id=target_card_id,
        target_account_id=target_account_id,
    )


@router.post("/authorization-profiles")
def create_authorization_profile(
    payload: AuthorizationProfileCreate,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    code = payload.auth_profile_code.upper().strip()
    existing = (
        db.query(AuthorizationProfile)
        .filter(AuthorizationProfile.auth_profile_code == code)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Authorization Profile '{code}' already exists",
        )

    inst_id = payload.institution_id
    if not inst_id and payload.card_profile_id:
        cp = db.query(CardProfile).filter(CardProfile.id == payload.card_profile_id).first()
        if cp and getattr(cp, "institution_id", None):
            inst_id = cp.institution_id
    if not inst_id:
        xbank = db.query(Institution).filter(Institution.institution_code == "XBANK").first()
        inst_id = xbank.id if xbank else None

    ap = AuthorizationProfile(
        auth_profile_code=code,
        profile_name=payload.profile_name.strip(),
        description=payload.description,
        card_profile_id=payload.card_profile_id,
        institution_id=inst_id,
        unconfigured_tx_code_policy=(payload.unconfigured_tx_code_policy or "REJECT").upper().strip(),
        unconfigured_decline_rc=(payload.unconfigured_decline_rc or "57").strip(),
        status=(payload.status or "ACTIVE").upper().strip(),
        effective_from=payload.effective_from or datetime.now(timezone.utc),
        effective_to=payload.effective_to,
    )
    db.add(ap)
    db.flush()

    # Pre-seed Tab A with configured TransactionCodes so the administrator immediately sees all codes
    for tc in db.query(TransactionCode).order_by(TransactionCode.transaction_code.asc()).all():
        db.add(
            AuthProfileTxCodePermission(
                authorization_profile_id=ap.id,
                transaction_code_id=tc.id,
                transaction_code=tc.transaction_code,
                transaction_name=tc.transaction_name,
                permission="ALLOWED" if tc.active else "DISALLOWED",
                decline_response_code="57",
                description=f"Default permission for {tc.transaction_name}",
                status="ACTIVE",
            )
        )

    record_audit(
        db,
        "AUTHORIZATION_PROFILE",
        ap.id,
        "CREATE",
        performed_by=current_user,
        after_state=serialize_entity(ap),
        change_summary=f"Created Authorization Profile '{ap.auth_profile_code}' ({ap.profile_name})",
    )
    db.commit()
    db.refresh(ap)
    engine = LimitCalculationEngine(db)
    return _serialize_authorization_profile(db, engine, ap)


@router.put("/authorization-profiles/{auth_profile_id}")
def update_authorization_profile(
    auth_profile_id: str,
    payload: AuthorizationProfileUpdate,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    ap = db.query(AuthorizationProfile).filter(AuthorizationProfile.id == auth_profile_id).first()
    if not ap:
        raise HTTPException(status_code=404, detail="Authorization Profile not found")
    before = serialize_entity(ap)
    for k, v in payload.model_dump(exclude_unset=True).items():
        if k in ("status", "unconfigured_tx_code_policy") and v:
            v = v.upper().strip()
        setattr(ap, k, v)
    after = serialize_entity(ap)
    record_audit(
        db,
        "AUTHORIZATION_PROFILE",
        ap.id,
        "UPDATE",
        performed_by=current_user,
        before_state=before,
        after_state=after,
        change_summary=f"Updated Authorization Profile '{ap.auth_profile_code}'",
    )
    db.commit()
    db.refresh(ap)
    engine = LimitCalculationEngine(db)
    return _serialize_authorization_profile(db, engine, ap)


@router.delete("/authorization-profiles/{auth_profile_id}")
def delete_authorization_profile(
    auth_profile_id: str,
    force: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    ap = db.query(AuthorizationProfile).filter(AuthorizationProfile.id == auth_profile_id).first()
    if not ap:
        raise HTTPException(status_code=404, detail="Authorization Profile not found")

    eval_count = (
        db.query(LimitEvaluationAudit)
        .filter(LimitEvaluationAudit.authorization_profile_id == ap.id)
        .count()
    )
    cards_using = (
        db.query(Card).filter(Card.card_profile_id == ap.card_profile_id).count()
        if ap.card_profile_id
        else 0
    )

    if (eval_count > 0 or cards_using > 0) and not force:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot hard-delete Authorization Profile '{ap.auth_profile_code}' because it governs "
                f"{cards_using} card(s) under its Card Profile and has {eval_count} historical limit evaluation(s). "
                f"Deactivate it instead or pass ?force=true."
            ),
        )

    before = serialize_entity(ap)
    db.delete(ap)
    record_audit(
        db,
        "AUTHORIZATION_PROFILE",
        auth_profile_id,
        "DELETE",
        performed_by=current_user,
        before_state=before,
        change_summary=f"Deleted Authorization Profile '{ap.auth_profile_code}'",
    )
    db.commit()
    return {"status": "deleted", "auth_profile_id": auth_profile_id}


# --- TAB A: ALLOWED TRANSACTIONS ---

@router.post("/authorization-profiles/{auth_profile_id}/permissions")
def upsert_auth_profile_tx_permission(
    auth_profile_id: str,
    payload: AuthProfileTxPermissionCreate,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    ap = db.query(AuthorizationProfile).filter(AuthorizationProfile.id == auth_profile_id).first()
    if not ap:
        raise HTTPException(status_code=404, detail="Authorization Profile not found")

    code_clean = payload.transaction_code.strip()
    tc = db.query(TransactionCode).filter(TransactionCode.transaction_code == code_clean).first()
    tx_name = payload.transaction_name or (tc.transaction_name if tc else f"Transaction {code_clean}")

    existing = (
        db.query(AuthProfileTxCodePermission)
        .filter(
            AuthProfileTxCodePermission.authorization_profile_id == ap.id,
            AuthProfileTxCodePermission.transaction_code == code_clean,
        )
        .first()
    )
    if existing:
        before = serialize_entity(existing)
        existing.transaction_name = tx_name
        existing.permission = payload.permission.upper().strip()
        existing.decline_response_code = payload.decline_response_code.strip()
        existing.description = payload.description
        existing.status = payload.status.upper().strip()
        after = serialize_entity(existing)
        record_audit(
            db,
            "AUTH_PROFILE_TX_PERMISSION",
            existing.id,
            "UPDATE",
            performed_by=current_user,
            before_state=before,
            after_state=after,
            change_summary=f"Set TxCode {code_clean} to {existing.permission} on {ap.auth_profile_code}",
        )
        db.commit()
        db.refresh(existing)
        return existing

    perm = AuthProfileTxCodePermission(
        authorization_profile_id=ap.id,
        transaction_code_id=tc.id if tc else None,
        transaction_code=code_clean,
        transaction_name=tx_name,
        permission=payload.permission.upper().strip(),
        decline_response_code=payload.decline_response_code.strip(),
        description=payload.description,
        status=payload.status.upper().strip(),
    )
    db.add(perm)
    db.flush()
    record_audit(
        db,
        "AUTH_PROFILE_TX_PERMISSION",
        perm.id,
        "CREATE",
        performed_by=current_user,
        after_state=serialize_entity(perm),
        change_summary=f"Added TxCode {code_clean} ({perm.permission}) to {ap.auth_profile_code}",
    )
    db.commit()
    db.refresh(perm)
    return perm


@router.delete("/authorization-profiles/{auth_profile_id}/permissions/{permission_id}")
def delete_auth_profile_tx_permission(
    auth_profile_id: str,
    permission_id: str,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    perm = (
        db.query(AuthProfileTxCodePermission)
        .filter(
            AuthProfileTxCodePermission.id == permission_id,
            AuthProfileTxCodePermission.authorization_profile_id == auth_profile_id,
        )
        .first()
    )
    if not perm:
        raise HTTPException(status_code=404, detail="Transaction permission not found")
    before = serialize_entity(perm)
    db.delete(perm)
    record_audit(
        db,
        "AUTH_PROFILE_TX_PERMISSION",
        permission_id,
        "DELETE",
        performed_by=current_user,
        before_state=before,
        change_summary=f"Removed TxCode {perm.transaction_code} permission from profile {auth_profile_id}",
    )
    db.commit()
    return {"status": "deleted", "permission_id": permission_id}


# --- TAB B & C: CARD & ACCOUNT LIMIT ASSIGNMENTS ---

@router.post("/authorization-profiles/{auth_profile_id}/limits")
def assign_limit_to_authorization_profile(
    auth_profile_id: str,
    payload: AuthProfileLimitAssignmentCreate,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    ap = db.query(AuthorizationProfile).filter(AuthorizationProfile.id == auth_profile_id).first()
    if not ap:
        raise HTTPException(status_code=404, detail="Authorization Profile not found")

    ldef = (
        db.query(LimitDefinition)
        .filter(
            (LimitDefinition.id == payload.limit_definition_id)
            | (LimitDefinition.limit_code == payload.limit_definition_id)
        )
        .first()
    )
    if not ldef:
        raise HTTPException(status_code=404, detail="Limit Definition not found")

    if payload.scope and payload.scope.upper().strip() != ldef.scope.upper():
        raise HTTPException(
            status_code=400,
            detail=(
                f"Scope mismatch: Limit '{ldef.limit_code}' has scope '{ldef.scope}', "
                f"cannot assign to '{payload.scope}' tab"
            ),
        )

    existing = (
        db.query(AuthProfileLimitAssignment)
        .filter(
            AuthProfileLimitAssignment.authorization_profile_id == ap.id,
            AuthProfileLimitAssignment.limit_definition_id == ldef.id,
        )
        .first()
    )
    if existing:
        before = serialize_entity(existing)
        existing.maximum_limit_override = payload.maximum_limit_override
        existing.calculation_method_override = payload.calculation_method_override
        existing.comparison_operator_override = payload.comparison_operator_override
        existing.impact_action_override = payload.impact_action_override
        existing.decline_response_code_override = payload.decline_response_code_override
        existing.evaluation_priority = payload.evaluation_priority
        existing.status = payload.status.upper().strip()
        after = serialize_entity(existing)
        record_audit(
            db,
            "AUTH_PROFILE_LIMIT_ASSIGNMENT",
            existing.id,
            "UPDATE",
            performed_by=current_user,
            before_state=before,
            after_state=after,
            change_summary=f"Updated {ldef.scope} Limit '{ldef.limit_code}' assignment on {ap.auth_profile_code}",
        )
        db.commit()
        engine = LimitCalculationEngine(db)
        return _serialize_authorization_profile(db, engine, ap)

    assign = AuthProfileLimitAssignment(
        authorization_profile_id=ap.id,
        limit_definition_id=ldef.id,
        scope=ldef.scope,
        maximum_limit_override=payload.maximum_limit_override,
        calculation_method_override=payload.calculation_method_override,
        comparison_operator_override=payload.comparison_operator_override,
        impact_action_override=payload.impact_action_override,
        decline_response_code_override=payload.decline_response_code_override,
        evaluation_priority=payload.evaluation_priority,
        status=payload.status.upper().strip(),
    )
    db.add(assign)
    db.flush()
    record_audit(
        db,
        "AUTH_PROFILE_LIMIT_ASSIGNMENT",
        assign.id,
        "CREATE",
        performed_by=current_user,
        after_state=serialize_entity(assign),
        change_summary=f"Assigned {ldef.scope} Limit '{ldef.limit_code}' ({ldef.limit_name}) to {ap.auth_profile_code}",
    )
    db.commit()
    engine = LimitCalculationEngine(db)
    return _serialize_authorization_profile(db, engine, ap)


@router.delete("/authorization-profiles/{auth_profile_id}/limits/{assignment_id}")
def remove_limit_from_authorization_profile(
    auth_profile_id: str,
    assignment_id: str,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    assign = (
        db.query(AuthProfileLimitAssignment)
        .filter(
            AuthProfileLimitAssignment.id == assignment_id,
            AuthProfileLimitAssignment.authorization_profile_id == auth_profile_id,
        )
        .first()
    )
    if not assign:
        raise HTTPException(status_code=404, detail="Limit assignment not found")
    before = serialize_entity(assign)
    db.delete(assign)
    record_audit(
        db,
        "AUTH_PROFILE_LIMIT_ASSIGNMENT",
        assignment_id,
        "DELETE",
        performed_by=current_user,
        before_state=before,
        change_summary=f"Unassigned limit {assign.limit_definition_id} from profile {auth_profile_id}",
    )
    db.commit()
    return {"status": "deleted", "assignment_id": assignment_id}


# --- TAB D: TRANSACTION CODE LIMIT IMPACT MAPPINGS ---

@router.post("/authorization-profiles/{auth_profile_id}/impacts")
def upsert_tx_code_limit_impact(
    auth_profile_id: str,
    payload: TxCodeLimitImpactCreate,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    ap = db.query(AuthorizationProfile).filter(AuthorizationProfile.id == auth_profile_id).first()
    if not ap:
        raise HTTPException(status_code=404, detail="Authorization Profile not found")

    ldef = (
        db.query(LimitDefinition)
        .filter(
            (LimitDefinition.id == payload.limit_definition_id)
            | (LimitDefinition.limit_code == payload.limit_definition_id)
        )
        .first()
    )
    if not ldef:
        raise HTTPException(status_code=404, detail="Limit Definition not found")

    code_clean = payload.transaction_code.strip()
    existing = (
        db.query(TxCodeLimitImpact)
        .filter(
            TxCodeLimitImpact.authorization_profile_id == ap.id,
            TxCodeLimitImpact.transaction_code == code_clean,
            TxCodeLimitImpact.limit_definition_id == ldef.id,
        )
        .first()
    )
    if existing:
        before = serialize_entity(existing)
        existing.impact_type = payload.impact_type.upper().strip()
        existing.calculation_basis = payload.calculation_basis.upper().strip()
        existing.multiplier = payload.multiplier
        existing.description = payload.description
        existing.status = payload.status.upper().strip()
        after = serialize_entity(existing)
        record_audit(
            db,
            "TX_CODE_LIMIT_IMPACT",
            existing.id,
            "UPDATE",
            performed_by=current_user,
            before_state=before,
            after_state=after,
            change_summary=f"Updated TxCode {code_clean} -> Limit {ldef.limit_code} impact to {existing.impact_type}",
        )
        db.commit()
        engine = LimitCalculationEngine(db)
        return _serialize_authorization_profile(db, engine, ap)

    imp = TxCodeLimitImpact(
        authorization_profile_id=ap.id,
        transaction_code=code_clean,
        limit_definition_id=ldef.id,
        impact_type=payload.impact_type.upper().strip(),
        calculation_basis=payload.calculation_basis.upper().strip(),
        multiplier=payload.multiplier,
        description=payload.description,
        status=payload.status.upper().strip(),
    )
    db.add(imp)
    db.flush()
    record_audit(
        db,
        "TX_CODE_LIMIT_IMPACT",
        imp.id,
        "CREATE",
        performed_by=current_user,
        after_state=serialize_entity(imp),
        change_summary=f"Created TxCode {code_clean} -> Limit {ldef.limit_code} impact ({imp.impact_type})",
    )
    db.commit()
    engine = LimitCalculationEngine(db)
    return _serialize_authorization_profile(db, engine, ap)


@router.delete("/authorization-profiles/{auth_profile_id}/impacts/{impact_id}")
def delete_tx_code_limit_impact(
    auth_profile_id: str,
    impact_id: str,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    imp = (
        db.query(TxCodeLimitImpact)
        .filter(
            TxCodeLimitImpact.id == impact_id,
            TxCodeLimitImpact.authorization_profile_id == auth_profile_id,
        )
        .first()
    )
    if not imp:
        raise HTTPException(status_code=404, detail="Transaction code limit impact not found")
    before = serialize_entity(imp)
    db.delete(imp)
    record_audit(
        db,
        "TX_CODE_LIMIT_IMPACT",
        impact_id,
        "DELETE",
        performed_by=current_user,
        before_state=before,
        change_summary=f"Deleted TxCode {imp.transaction_code} limit impact {impact_id}",
    )
    db.commit()
    return {"status": "deleted", "impact_id": impact_id}


# --- EVALUATION AUDIT HISTORY ---

@router.get("/limit-evaluations")
def list_limit_evaluation_audits(
    transaction_id: Optional[str] = Query(None),
    scope: Optional[str] = Query(None),
    limit_code: Optional[str] = Query(None),
    target_entity_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    q = db.query(LimitEvaluationAudit)
    if transaction_id:
        q = q.filter(LimitEvaluationAudit.transaction_id == transaction_id)
    if scope:
        q = q.filter(LimitEvaluationAudit.scope == scope.upper().strip())
    if limit_code:
        q = q.filter(LimitEvaluationAudit.limit_code == limit_code.strip())
    if target_entity_id:
        q = q.filter(LimitEvaluationAudit.target_entity_id == target_entity_id)

    rows = q.order_by(LimitEvaluationAudit.created_at.desc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "transaction_id": r.transaction_id,
            "transaction_reference": r.transaction_reference,
            "authorization_profile_id": r.authorization_profile_id,
            "limit_definition_id": r.limit_definition_id,
            "limit_code": r.limit_code,
            "limit_name": r.limit_name,
            "scope": r.scope,
            "target_entity_id": r.target_entity_id,
            "transaction_code": r.transaction_code,
            "calculation_method": r.calculation_method,
            "reset_interval": r.reset_interval,
            "window_key": r.window_key,
            "maximum_value": float(to_dec(r.maximum_value)),
            "previous_usage": float(to_dec(r.previous_usage)),
            "transaction_impact": float(to_dec(r.transaction_impact)),
            "projected_usage": float(to_dec(r.projected_usage)),
            "comparison_operator": r.comparison_operator,
            "condition_matched": r.condition_matched,
            "configured_action": r.configured_action,
            "final_result": r.final_result,
            "response_code": r.response_code,
            "decline_reason": r.decline_reason,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]

# [PATCH step13_06:card_profile_dynamic_endpoints]
@router.put("/bin-ranges/{bin_id}/assign-card-profile")
def assign_card_profile_to_bin_range_alias(
    bin_id: str,
    payload: BinCardProfileAssignRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    return assign_card_profile_to_bin(bin_id=bin_id, payload=payload, db=db, current_user=current_user)


@router.post("/card-profiles-v2/{profile_id}/assign-bins")
def bulk_assign_bins_to_card_profile(
    profile_id: str,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    Assigns a list of BIN Range IDs (`bin_ids`) to a Card Profile in one atomic operation.
    Any BIN previously assigned to this Card Profile that is not in `bin_ids` is unassigned
    (unless `append_only=True`).
    """
    prof = db.query(CardProfile).filter(CardProfile.id == profile_id).first()
    if not prof:
        raise HTTPException(status_code=404, detail="Card Profile not found")
    if prof.status != "ACTIVE":
        raise HTTPException(status_code=400, detail=f"Card Profile '{prof.profile_code}' is not ACTIVE")

    bin_ids = [str(x) for x in (payload.get("bin_ids") or []) if x]
    append_only = bool(payload.get("append_only", False))
    target_set = set(bin_ids)

    if not append_only:
        for existing_bin in db.query(BinRange).filter(BinRange.card_profile_id == prof.id).all():
            if existing_bin.id not in target_set:
                existing_bin.card_profile_id = None

    assigned_prefixes: List[str] = []
    for bid in target_set:
        b = db.query(BinRange).filter(BinRange.id == bid).first()
        if b:
            b.card_profile_id = prof.id
            assigned_prefixes.append(b.bin_prefix)

    record_audit(
        db,
        "CARD_PROFILE",
        prof.id,
        "BULK_ASSIGN_BINS",
        performed_by=current_user,
        change_summary=f"Assigned {len(assigned_prefixes)} BIN range(s) ({', '.join(assigned_prefixes) or 'none'}) to Card Profile '{prof.profile_code}'",
    )
    db.commit()
    return {
        "status": "updated",
        "card_profile_id": prof.id,
        "profile_code": prof.profile_code,
        "assigned_bin_prefixes": assigned_prefixes,
        "assigned_count": len(assigned_prefixes),
    }


@router.patch("/card-profiles-v2/{profile_id}/status")
def toggle_card_profile_v2_status(
    profile_id: str,
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    prof = db.query(CardProfile).filter(CardProfile.id == profile_id).first()
    if not prof:
        raise HTTPException(status_code=404, detail="Card Profile not found")
    before = serialize_entity(prof)
    next_status = status.upper().strip() if status else ("INACTIVE" if prof.status == "ACTIVE" else "ACTIVE")
    prof.status = next_status
    after = serialize_entity(prof)
    record_audit(
        db,
        "CARD_PROFILE",
        prof.id,
        "STATUS_CHANGE",
        performed_by=current_user,
        before_state=before,
        after_state=after,
        change_summary=f"Changed Card Profile '{prof.profile_code}' status to {next_status}",
    )
    db.commit()
    return {"status": "updated", "id": prof.id, "profile_code": prof.profile_code, "new_status": prof.status}


@router.post("/card-profiles-v2/{profile_id}/sync-cards")
def sync_cards_under_profile_bins(
    profile_id: str,
    overwrite_existing: bool = Query(False, description="If true, updates all cards under linked BINs; otherwise only unassigned cards"),
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    Explicit operator action to synchronize issued cards whose PAN matches the BIN ranges
    assigned to this Card Profile.
    """
    prof = db.query(CardProfile).filter(CardProfile.id == profile_id).first()
    if not prof:
        raise HTTPException(status_code=404, detail="Card Profile not found")

    linked_bins = db.query(BinRange).filter(BinRange.card_profile_id == prof.id).all()
    if not linked_bins:
        return {"status": "no_bins", "updated_cards": 0, "message": f"No BIN ranges are linked to {prof.profile_code}"}

    cards = db.query(Card).all()
    updated_count = 0
    for c in cards:
        if not overwrite_existing and c.card_profile_id:
            continue
        pan = c.test_pan_reference or ""
        if any(pan.startswith(b.bin_prefix) for b in linked_bins):
            c.card_profile_id = prof.id
            updated_count += 1

    record_audit(
        db,
        "CARD_PROFILE",
        prof.id,
        "SYNC_CARDS",
        performed_by=current_user,
        change_summary=f"Synchronized {updated_count} card(s) under BINs of Card Profile '{prof.profile_code}'",
    )
    db.commit()
    return {
        "status": "synced",
        "card_profile_id": prof.id,
        "profile_code": prof.profile_code,
        "updated_cards": updated_count,
    }


@router.delete("/card-profiles-v2/{profile_id}")
def delete_card_profile_v2(
    profile_id: str,
    deactivate_only: bool = Query(False),
    force: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    prof = db.query(CardProfile).filter(CardProfile.id == profile_id).first()
    if not prof:
        raise HTTPException(status_code=404, detail="Card Profile not found")

    bin_count = db.query(BinRange).filter(BinRange.card_profile_id == prof.id).count()
    card_count = db.query(Card).filter(Card.card_profile_id == prof.id).count()
    auth_count = db.query(AuthorizationProfile).filter(AuthorizationProfile.card_profile_id == prof.id).count()

    if deactivate_only:
        before = serialize_entity(prof)
        prof.status = "INACTIVE"
        record_audit(
            db,
            "CARD_PROFILE",
            prof.id,
            "DEACTIVATE",
            performed_by=current_user,
            before_state=before,
            after_state=serialize_entity(prof),
            change_summary=f"Deactivated Card Profile '{prof.profile_code}' (linked to {bin_count} BINs, {card_count} cards, {auth_count} auth profiles)",
        )
        db.commit()
        return {
            "status": "deactivated",
            "id": prof.id,
            "profile_code": prof.profile_code,
            "message": f"Card Profile '{prof.profile_code}' has been safely deactivated.",
        }

    if (bin_count > 0 or card_count > 0 or auth_count > 0) and not force:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot hard-delete Card Profile '{prof.profile_code}' because it is linked to "
                f"{bin_count} BIN range(s), {card_count} card(s), and {auth_count} Authorization Profile(s). "
                f"Deactivate it instead or use Force Delete to detach references."
            ),
        )

    before = serialize_entity(prof)
    db.query(BinRange).filter(BinRange.card_profile_id == prof.id).update({"card_profile_id": None}, synchronize_session=False)
    db.query(Card).filter(Card.card_profile_id == prof.id).update({"card_profile_id": None}, synchronize_session=False)
    db.query(AuthorizationProfile).filter(AuthorizationProfile.card_profile_id == prof.id).update({"card_profile_id": None}, synchronize_session=False)
    db.delete(prof)
    record_audit(
        db,
        "CARD_PROFILE",
        profile_id,
        "DELETE",
        performed_by=current_user,
        before_state=before,
        change_summary=f"Deleted Card Profile '{prof.profile_code}' (Force={force})",
    )
    db.commit()
    return {"status": "deleted", "id": profile_id, "profile_code": prof.profile_code}

