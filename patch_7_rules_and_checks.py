"""
patch_7_rules_and_checks.py
Run in the project folder:   python patch_7_rules_and_checks.py     (after patches 4 and 5)
 * Fixes the 422 when saving an algo: readable messages, required-field hints, auto algo code.
 * Rules & Checks tab (replaces the confusing table): built-in check switches with explanations + simple rules you can
   add / edit / test / delete without code. Fixes: switching a built-in check OFF now really switches it off.
 * Menu 7.5 Authorizer Rules is removed (its features live in 14. Host Control Center); old links redirect.
 * Validation errors on every page are readable instead of [object Object].
Idempotent. Backups go to _backups/.
"""

PATCH_NAME = "patch7_rules"

LOCAL_HOST_ROUTER_PY = r'''"""
local_host_router.py
REST API of the Rajon Local Host control center  (prefix /api/local-host)

  GET    /meta                         banks, processing systems, transaction codes, channels, response codes ...
  GET    /overview                     KPIs for the dashboard strip
  GET    /policies                     global + per bank policy summaries
  GET    /policies/effective           merged policy of a bank (with the source of every section)
  PUT    /policies                     create / update the GLOBAL or a BANK policy
  DELETE /policies/bank/{bank_id}      remove a bank override (the bank inherits GLOBAL again)
  POST   /policies/simulate            "what would the host decide?" without posting anything

  GET    /algos                        list
  POST   /algos                        create
  GET    /algos/{id}                   read one
  PUT    /algos/{id}                   update (a new version is stored)
  DELETE /algos/{id}                   delete
  POST   /algos/{id}/toggle            enable / disable
  GET    /algos/{id}/versions          version history
  POST   /algos/{id}/rollback          restore an older version
  GET    /algos/fields                 every field / helper that can be used inside an algo
  GET    /algos/templates              ready to use examples
  GET    /algos/schema                 tables / columns usable from SQL algos
  POST   /algos/validate               syntax + safety check
  POST   /algos/test                   dry run of a (draft) algo on a real card with sample values
  GET    /algos/logs                   execution log
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.audit_service import record_audit
from app.database import Base, get_db
from app.local_host_engine import (
    ALGO_ACTIONS,
    ALGO_LANGUAGES,
    ALGO_MODES,
    ALGO_SCOPES,
    ALGO_STAGES,
    ALGO_TEMPLATES,
    CHANNELS,
    DEFAULT_POLICY,
    LocalHostEngine,
    POLICY_SECTIONS,
    build_test_context,
    effective_policy,
    field_catalog,
    sanitize_policy_config,
    sql_schema,
    validate_python,
    validate_sql,
)
from app.models import Card, CardProfile, HostParameter, Institution, ProcessingSystem, ResponseCode, TransactionCode
from app.models_local_host import HostAlgo, HostAlgoLog, HostAlgoVersion, LocalHostPolicy
from app.security import get_current_user

router = APIRouter(prefix="/api/local-host", tags=["Local Host Control Center"])


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------
def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _find_card(db: Session, card_id: Optional[str], pan: Optional[str], institution_id: Optional[str]) -> Optional[Card]:
    if card_id:
        c = db.query(Card).filter(Card.id == card_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="Card not found")
        return c
    if pan:
        c = db.query(Card).filter(Card.test_pan_reference == pan.strip()).first()
        if not c:
            raise HTTPException(status_code=404, detail="No card with that PAN")
        return c
    q = db.query(Card)
    if institution_id:
        q = q.filter(Card.institution_id == institution_id)
    return q.order_by(Card.created_at.asc()).first()


# ----------------------------------------------------------------------------
# meta / overview
# ----------------------------------------------------------------------------
@router.get("/meta")
def local_host_meta(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    banks = db.query(Institution).order_by(Institution.institution_code.asc()).all()
    systems = db.query(ProcessingSystem).order_by(ProcessingSystem.ps_code.asc()).all()
    codes = db.query(TransactionCode).filter(TransactionCode.active == True).order_by(TransactionCode.transaction_code.asc()).all()  # noqa: E712
    profiles = db.query(CardProfile).order_by(CardProfile.profile_code.asc()).all()
    rcs = db.query(ResponseCode).order_by(ResponseCode.response_code.asc()).all()
    cards = db.query(Card).order_by(Card.created_at.asc()).limit(200).all()
    return {
        "banks": [
            {"id": b.id, "code": b.institution_code, "name": b.name, "status": b.status, "country": b.country_code}
            for b in banks
        ],
        "processing_systems": [
            {"code": p.ps_code, "name": p.name, "type": p.system_type, "enabled": p.enabled} for p in systems
        ],
        "transaction_codes": [
            {"code": t.transaction_code, "name": t.transaction_name, "financial": t.financial_flag, "debit": t.debit_flag}
            for t in codes
        ],
        "card_profiles": [
            {"id": p.id, "code": p.profile_code, "name": p.profile_name, "bank_id": getattr(p, "institution_id", None)}
            for p in profiles
        ],
        "response_codes": [{"code": r.response_code, "description": r.response_description} for r in rcs],
        "cards": [
            {"id": c.id, "masked_pan": c.masked_pan, "holder": c.cardholder_name,
             "bank_code": c.institution.institution_code if c.institution else None, "status": c.card_status}
            for c in cards
        ],
        "channels": CHANNELS,
        "actions": ALGO_ACTIONS,
        "stages": ALGO_STAGES,
        "modes": ALGO_MODES,
        "scopes": ALGO_SCOPES,
        "languages": ALGO_LANGUAGES,
        "policy_sections": POLICY_SECTIONS,
        "policy_defaults": DEFAULT_POLICY,
    }


@router.get("/overview")
def local_host_overview(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    total = db.query(func.count(HostAlgo.id)).scalar() or 0
    active = db.query(func.count(HostAlgo.id)).filter(HostAlgo.enabled == True).scalar() or 0  # noqa: E712
    monitor = db.query(func.count(HostAlgo.id)).filter(HostAlgo.enabled == True, HostAlgo.mode == "MONITOR").scalar() or 0  # noqa: E712
    matches = db.query(func.count(HostAlgoLog.id)).filter(HostAlgoLog.created_at >= since, HostAlgoLog.matched == True).scalar() or 0  # noqa: E712
    blocks = (
        db.query(func.count(HostAlgoLog.id))
        .filter(HostAlgoLog.created_at >= since, HostAlgoLog.action_applied == True, HostAlgoLog.action.in_(["BLOCK_CARD", "BLOCK_CUSTOMER"]))  # noqa: E712
        .scalar()
        or 0
    )
    errors = db.query(func.count(HostAlgoLog.id)).filter(HostAlgoLog.created_at >= since, HostAlgoLog.error.isnot(None)).scalar() or 0
    bank_overrides = db.query(func.count(LocalHostPolicy.id)).filter(LocalHostPolicy.scope_type == "BANK").scalar() or 0
    top = (
        db.query(HostAlgoLog.algo_code, func.count(HostAlgoLog.id).label("n"))
        .filter(HostAlgoLog.created_at >= since, HostAlgoLog.matched == True)  # noqa: E712
        .group_by(HostAlgoLog.algo_code)
        .order_by(func.count(HostAlgoLog.id).desc())
        .limit(5)
        .all()
    )
    return {
        "algos_total": total, "algos_active": active, "algos_monitor": monitor,
        "matches_24h": matches, "blocks_24h": blocks, "errors_24h": errors,
        "bank_overrides": bank_overrides,
        "top_algos": [{"algo_code": c, "matches": n} for c, n in top],
    }


# ----------------------------------------------------------------------------
# policies
# ----------------------------------------------------------------------------
class PolicyBody(BaseModel):
    scope_type: str = Field("GLOBAL", description="GLOBAL or BANK")
    institution_id: Optional[str] = None
    name: Optional[str] = Field(None, max_length=120)
    enabled: bool = True
    config: Dict[str, Any] = Field(default_factory=dict)


@router.get("/policies")
def list_policies(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    rows = db.query(LocalHostPolicy).all()
    glob = next((r for r in rows if r.scope_type == "GLOBAL"), None)
    by_bank = {r.institution_id: r for r in rows if r.scope_type == "BANK"}
    out = [
        {
            "scope_type": "GLOBAL", "institution_id": None, "bank_code": None,
            "name": glob.name if glob else "Global Default", "exists": bool(glob),
            "enabled": glob.enabled if glob else True,
            "sections": sorted((glob.config_json or {}).keys()) if glob else [],
            "version": glob.version if glob else 0, "updated_at": _iso(glob.updated_at) if glob else None,
            "host_status": ((glob.config_json or {}).get("general") or {}).get("host_status", "ACTIVE") if glob else "ACTIVE",
        }
    ]
    for b in db.query(Institution).order_by(Institution.institution_code.asc()).all():
        p = by_bank.get(b.id)
        gen = ((p.config_json or {}).get("general") or {}) if p else {}
        out.append(
            {
                "scope_type": "BANK", "institution_id": b.id, "bank_code": b.institution_code, "name": b.name,
                "exists": bool(p), "enabled": p.enabled if p else True,
                "sections": sorted((p.config_json or {}).keys()) if p else [],
                "version": p.version if p else 0, "updated_at": _iso(p.updated_at) if p else None,
                "host_status": gen.get("host_status") or (
                    ((glob.config_json or {}).get("general") or {}).get("host_status", "ACTIVE") if glob else "ACTIVE"
                ),
                "bank_status": b.status,
            }
        )
    return out


@router.get("/policies/effective")
def get_effective_policy(
    institution_id: Optional[str] = Query(None), db: Session = Depends(get_db), _: str = Depends(get_current_user)
):
    eff = effective_policy(db, institution_id)
    glob = db.query(LocalHostPolicy).filter(LocalHostPolicy.scope_type == "GLOBAL").first()
    bank = None
    if institution_id:
        bank = db.query(LocalHostPolicy).filter(
            LocalHostPolicy.scope_type == "BANK", LocalHostPolicy.institution_id == institution_id
        ).first()
    return {
        "config": eff["config"], "sources": eff["sources"],
        "raw_global": (glob.config_json if glob else {}) or {},
        "raw_bank": (bank.config_json if bank else {}) or {},
        "global_enabled": glob.enabled if glob else True,
        "bank_enabled": bank.enabled if bank else True,
        "bank_exists": bool(bank),
    }


@router.put("/policies")
def save_policy(body: PolicyBody, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    scope = (body.scope_type or "GLOBAL").upper()
    if scope not in ("GLOBAL", "BANK"):
        raise HTTPException(status_code=400, detail="scope_type must be GLOBAL or BANK")
    inst = None
    if scope == "BANK":
        if not body.institution_id:
            raise HTTPException(status_code=400, detail="institution_id is required for a BANK policy")
        inst = db.query(Institution).filter(Institution.id == body.institution_id).first()
        if not inst:
            raise HTTPException(status_code=404, detail="Bank not found")
    q = db.query(LocalHostPolicy).filter(LocalHostPolicy.scope_type == scope)
    q = q.filter(LocalHostPolicy.institution_id == body.institution_id) if scope == "BANK" else q.filter(LocalHostPolicy.institution_id.is_(None))
    row = q.first()
    clean = sanitize_policy_config(body.config)
    before = (row.config_json if row else None)
    if row is None:
        row = LocalHostPolicy(
            scope_type=scope, institution_id=body.institution_id if scope == "BANK" else None,
            name=body.name or (f"{inst.institution_code} policy" if inst else "Global Default"),
            enabled=body.enabled, config_json=clean, version=1, updated_by=current_user,
        )
        db.add(row)
    else:
        row.config_json = clean
        row.enabled = body.enabled
        if body.name:
            row.name = body.name
        row.version = (row.version or 0) + 1
        row.updated_by = current_user
    db.flush()
    record_audit(
        db, "LOCAL_HOST_POLICY", row.id, "UPSERT", performed_by=current_user,
        before_state={"config": before} if before is not None else None, after_state={"config": clean},
        change_summary=f"{scope} local host policy saved ({', '.join(sorted(clean.keys())) or 'no sections'})"
        + (f" for {inst.institution_code}" if inst else ""),
    )
    db.commit()
    return {"status": "saved", "id": row.id, "version": row.version, "sections": sorted(clean.keys())}


@router.delete("/policies/bank/{institution_id}")
def delete_bank_policy(institution_id: str, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    row = db.query(LocalHostPolicy).filter(
        LocalHostPolicy.scope_type == "BANK", LocalHostPolicy.institution_id == institution_id
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="This bank has no override")
    record_audit(db, "LOCAL_HOST_POLICY", row.id, "DELETE", performed_by=current_user,
                 before_state={"config": row.config_json}, change_summary="Bank override removed; bank inherits GLOBAL")
    db.delete(row)
    db.commit()
    return {"status": "deleted"}


class SimulateBody(BaseModel):
    institution_id: Optional[str] = None
    card_id: Optional[str] = None
    pan: Optional[str] = None
    overrides: Dict[str, Any] = Field(default_factory=dict)


@router.post("/policies/simulate")
def simulate_policy(body: SimulateBody, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    inst = db.query(Institution).filter(Institution.id == body.institution_id).first() if body.institution_id else None
    card = _find_card(db, body.card_id, body.pan, body.institution_id)
    if card is not None and inst is None:
        inst = card.institution
    # a card of another bank would hide the bank under test: use the bank only for the policy lookup
    issuer = inst
    if card is not None and inst is not None and card.institution_id != inst.id:
        card = None
    ctx = build_test_context(db, card, body.overrides, issuer_inst=issuer)
    res = LocalHostEngine(db).evaluate_policy(ctx)
    d = ctx.data
    return {
        "allowed": res.allowed, "response_code": res.response_code, "message": res.message,
        "failed_control": res.failed_control, "policy_scope": res.scope, "checks": res.checks,
        "bank": d["bank"]["code"], "context": {
            "channel": d["tx"]["channel"], "source": d["tx"]["source"], "tran_code": d["tx"]["tran_code"],
            "amount": d["tx"]["amount"], "hour": d["tx"]["hour"], "mcc": d["terminal"]["mcc"],
            "country": d["tx"]["country"], "is_foreign": d["tx"]["is_foreign"],
        },
    }


# ----------------------------------------------------------------------------
# algos
# ----------------------------------------------------------------------------
class AlgoBody(BaseModel):
    # NOTE: no length constraints here on purpose. They are checked in _normalize() so the user
    # gets a readable message ("Algo code is required ...") instead of a raw 422 validation list.
    algo_code: str = ""
    name: str = ""
    description: Optional[str] = None
    language: str = "PYTHON"
    code: str = ""
    scope_type: str = "GLOBAL"
    institution_id: Optional[str] = None
    card_profile_id: Optional[str] = None
    stage: str = "PRE_AUTH"
    priority: int = 100
    mode: str = "ENFORCE"
    default_action: str = "DECLINE"
    default_response_code: str = "57"
    default_message: str = "Declined by risk algo"
    on_error: str = "SKIP"
    stop_on_match: bool = True
    tx_codes: List[str] = Field(default_factory=list)
    channels: List[str] = Field(default_factory=list)
    enabled: bool = True
    change_note: Optional[str] = Field(None, max_length=250)


def _check_code(language: str, code: str) -> List[str]:
    if language == "SQL":
        return validate_sql(code)[0]
    return validate_python(code)[0]


def _normalize(body: AlgoBody, db: Session) -> Dict[str, Any]:
    d = body.model_dump()
    d["algo_code"] = re.sub(r"[^A-Za-z0-9_\-]", "_", (d["algo_code"] or "").strip()).upper()
    d["name"] = (d["name"] or "").strip()
    d["default_message"] = (d["default_message"] or "").strip()[:200] or "Declined by risk algo"
    d["default_response_code"] = (d["default_response_code"] or "").strip()
    d["language"] = d["language"].upper().strip()
    d["scope_type"] = d["scope_type"].upper().strip()
    d["stage"] = d["stage"].upper().strip()
    d["mode"] = d["mode"].upper().strip()
    d["default_action"] = d["default_action"].upper().strip()
    d["on_error"] = d["on_error"].upper().strip()
    d["channels"] = [c.upper().strip() for c in d["channels"] if c.strip()]
    d["tx_codes"] = [c.strip() for c in d["tx_codes"] if c.strip()]
    errs: List[str] = []
    if len(d["algo_code"].strip("_")) < 3:
        errs.append("Algo code is required (at least 3 letters or numbers, e.g. NIGHT_ATM_LIMIT)")
    elif len(d["algo_code"]) > 60:
        errs.append("Algo code is too long (maximum 60 characters)")
    if len(d["name"]) < 2:
        errs.append("Name is required (at least 2 characters)")
    elif len(d["name"]) > 150:
        errs.append("Name is too long (maximum 150 characters)")
    try:
        if not 1 <= int(d["priority"]) <= 9999:
            errs.append("Priority must be a number between 1 and 9999")
    except (TypeError, ValueError):
        errs.append("Priority must be a number between 1 and 9999")
    if d["language"] not in ALGO_LANGUAGES:
        errs.append("language must be PYTHON or SQL")
    if d["scope_type"] not in ALGO_SCOPES:
        errs.append("scope_type must be GLOBAL, BANK or CARD_PROFILE")
    if d["stage"] not in ALGO_STAGES:
        errs.append("stage must be PRE_AUTH or POST_AUTH")
    if d["mode"] not in ALGO_MODES:
        errs.append("mode must be ENFORCE or MONITOR")
    if d["default_action"] not in ALGO_ACTIONS:
        errs.append("default_action must be one of " + ", ".join(ALGO_ACTIONS))
    if d["on_error"] not in ("SKIP", "DECLINE"):
        errs.append("on_error must be SKIP or DECLINE")
    if not re.fullmatch(r"[0-9A-Za-z]{2}", d["default_response_code"]):
        errs.append("Response code must be 2 characters (e.g. 57)")
    if d["scope_type"] == "BANK":
        if not d["institution_id"] or not db.query(Institution).filter(Institution.id == d["institution_id"]).first():
            errs.append("Choose a valid bank for a BANK scoped algo")
        d["card_profile_id"] = None
    elif d["scope_type"] == "CARD_PROFILE":
        if not d["card_profile_id"] or not db.query(CardProfile).filter(CardProfile.id == d["card_profile_id"]).first():
            errs.append("Choose a valid card profile for a CARD_PROFILE scoped algo")
        d["institution_id"] = None
    else:
        d["institution_id"] = None
        d["card_profile_id"] = None
    if not errs and d["language"] in ALGO_LANGUAGES:
        errs.extend(_check_code(d["language"], d["code"]))
    if errs:
        raise HTTPException(status_code=400, detail="; ".join(errs))
    return d


def _algo_dict(a: HostAlgo, banks: Dict[str, str], profiles: Dict[str, str], include_code: bool = True) -> Dict[str, Any]:
    out = {
        "id": a.id, "algo_code": a.algo_code, "name": a.name, "description": a.description,
        "language": a.language, "scope_type": a.scope_type, "institution_id": a.institution_id,
        "bank_code": banks.get(a.institution_id) if a.institution_id else None,
        "card_profile_id": a.card_profile_id,
        "card_profile_code": profiles.get(a.card_profile_id) if a.card_profile_id else None,
        "stage": a.stage, "priority": a.priority, "mode": a.mode, "default_action": a.default_action,
        "default_response_code": a.default_response_code, "default_message": a.default_message,
        "on_error": a.on_error, "stop_on_match": a.stop_on_match, "tx_codes": a.tx_codes_json or [],
        "channels": a.channels_json or [], "enabled": a.enabled, "version": a.version,
        "eval_count": a.eval_count, "hit_count": a.hit_count, "error_count": a.error_count,
        "last_run_at": _iso(a.last_run_at), "last_hit_at": _iso(a.last_hit_at),
        "created_at": _iso(a.created_at), "updated_at": _iso(a.updated_at), "updated_by": a.updated_by,
    }
    if include_code:
        out["code"] = a.code
    return out


def _maps(db: Session):
    banks = {b.id: b.institution_code for b in db.query(Institution).all()}
    profiles = {p.id: p.profile_code for p in db.query(CardProfile).all()}
    return banks, profiles


def _get_algo(db: Session, algo_id: str) -> HostAlgo:
    a = db.query(HostAlgo).filter(HostAlgo.id == algo_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Algo not found")
    return a


# static routes first (they must not be shadowed by /algos/{algo_id})
@router.get("/algos/fields")
def algo_fields(_: str = Depends(get_current_user)):
    return field_catalog()


@router.get("/algos/templates")
def algo_templates(_: str = Depends(get_current_user)):
    return ALGO_TEMPLATES


@router.get("/algos/schema")
def algo_schema(_: str = Depends(get_current_user)):
    return sql_schema(Base)


class ValidateBody(BaseModel):
    language: str = "PYTHON"
    code: str = ""


@router.post("/algos/validate")
def algo_validate(body: ValidateBody, _: str = Depends(get_current_user)):
    lang = body.language.upper()
    if lang == "SQL":
        errors, warnings = validate_sql(body.code)
    else:
        errors, warnings = validate_python(body.code)[0], []
    return {"valid": not errors, "errors": errors, "warnings": warnings}


class TestBody(BaseModel):
    algo_id: Optional[str] = None
    draft: Optional[Dict[str, Any]] = None
    card_id: Optional[str] = None
    pan: Optional[str] = None
    institution_id: Optional[str] = None
    overrides: Dict[str, Any] = Field(default_factory=dict)


@router.post("/algos/test")
def algo_test(body: TestBody, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    if body.draft:
        draft = dict(body.draft)
    elif body.algo_id:
        a = _get_algo(db, body.algo_id)
        draft = {
            "algo_code": a.algo_code, "name": a.name, "language": a.language, "code": a.code, "mode": a.mode,
            "default_action": a.default_action, "default_response_code": a.default_response_code,
            "default_message": a.default_message, "on_error": a.on_error, "stop_on_match": a.stop_on_match,
            "stage": a.stage,
        }
    else:
        raise HTTPException(status_code=400, detail="Send a draft or an algo_id")
    lang = str(draft.get("language") or "PYTHON").upper()
    errors = _check_code(lang, draft.get("code") or "")
    if errors:
        return {"ok": False, "errors": errors, "result": None}
    card = _find_card(db, body.card_id, body.pan, body.institution_id)
    if card is None:
        raise HTTPException(status_code=404, detail="No card available to test with")
    ctx = build_test_context(db, card, body.overrides)
    result = LocalHostEngine(db).test_draft(draft, ctx)
    db.rollback()  # a test run never keeps anything
    return {"ok": True, "errors": [], "result": result, "context": ctx.public()}


@router.get("/algos/logs")
def algo_logs(
    algo_id: Optional[str] = None,
    matched_only: bool = False,
    limit: int = Query(50, ge=1, le=300),
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    q = db.query(HostAlgoLog)
    if algo_id:
        q = q.filter(HostAlgoLog.algo_id == algo_id)
    if matched_only:
        q = q.filter(HostAlgoLog.matched == True)  # noqa: E712
    rows = q.order_by(HostAlgoLog.created_at.desc()).limit(limit).all()
    return [
        {
            "id": r.id, "algo_id": r.algo_id, "algo_code": r.algo_code, "transaction_reference": r.transaction_reference,
            "masked_pan": r.masked_pan, "stage": r.stage, "mode": r.mode, "matched": r.matched, "action": r.action,
            "action_applied": r.action_applied, "response_code": r.response_code, "message": r.message,
            "error": r.error, "duration_ms": r.duration_ms, "context": r.context_json, "created_at": _iso(r.created_at),
        }
        for r in rows
    ]


@router.get("/algos")
def list_algos(
    scope_type: Optional[str] = None,
    stage: Optional[str] = None,
    language: Optional[str] = None,
    enabled: Optional[bool] = None,
    q: Optional[str] = None,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    query = db.query(HostAlgo)
    if scope_type:
        query = query.filter(HostAlgo.scope_type == scope_type.upper())
    if stage:
        query = query.filter(HostAlgo.stage == stage.upper())
    if language:
        query = query.filter(HostAlgo.language == language.upper())
    if enabled is not None:
        query = query.filter(HostAlgo.enabled == enabled)
    if q:
        term = f"%{q.strip()}%"
        query = query.filter(HostAlgo.algo_code.ilike(term) | HostAlgo.name.ilike(term))
    banks, profiles = _maps(db)
    rows = query.order_by(HostAlgo.stage.asc(), HostAlgo.priority.asc(), HostAlgo.algo_code.asc()).all()
    return [_algo_dict(a, banks, profiles, include_code=False) for a in rows]


@router.post("/algos")
def create_algo(body: AlgoBody, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    d = _normalize(body, db)
    if db.query(HostAlgo).filter(HostAlgo.algo_code == d["algo_code"]).first():
        raise HTTPException(status_code=409, detail=f"Algo code {d['algo_code']} already exists")
    a = HostAlgo(
        algo_code=d["algo_code"], name=d["name"], description=d["description"], language=d["language"], code=d["code"],
        scope_type=d["scope_type"], institution_id=d["institution_id"], card_profile_id=d["card_profile_id"],
        stage=d["stage"], priority=d["priority"], mode=d["mode"], default_action=d["default_action"],
        default_response_code=d["default_response_code"], default_message=d["default_message"], on_error=d["on_error"],
        stop_on_match=d["stop_on_match"], tx_codes_json=d["tx_codes"], channels_json=d["channels"],
        enabled=d["enabled"], version=1, created_by=current_user, updated_by=current_user,
    )
    db.add(a)
    db.flush()
    db.add(HostAlgoVersion(algo_id=a.id, version=1, language=a.language, code=a.code,
                           change_note=d.get("change_note") or "Created", changed_by=current_user))
    record_audit(db, "HOST_ALGO", a.id, "CREATE", performed_by=current_user,
                 change_summary=f"Algo {a.algo_code} created ({a.language}, {a.scope_type}, {a.stage}, {a.mode})")
    db.commit()
    banks, profiles = _maps(db)
    return _algo_dict(a, banks, profiles)


@router.get("/algos/{algo_id}")
def read_algo(algo_id: str, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    banks, profiles = _maps(db)
    return _algo_dict(_get_algo(db, algo_id), banks, profiles)


@router.put("/algos/{algo_id}")
def update_algo(algo_id: str, body: AlgoBody, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    a = _get_algo(db, algo_id)
    d = _normalize(body, db)
    clash = db.query(HostAlgo).filter(HostAlgo.algo_code == d["algo_code"], HostAlgo.id != a.id).first()
    if clash:
        raise HTTPException(status_code=409, detail=f"Algo code {d['algo_code']} already exists")
    changed_code = (a.code != d["code"]) or (a.language != d["language"])
    a.algo_code, a.name, a.description = d["algo_code"], d["name"], d["description"]
    a.language, a.code = d["language"], d["code"]
    a.scope_type, a.institution_id, a.card_profile_id = d["scope_type"], d["institution_id"], d["card_profile_id"]
    a.stage, a.priority, a.mode = d["stage"], d["priority"], d["mode"]
    a.default_action, a.default_response_code, a.default_message = d["default_action"], d["default_response_code"], d["default_message"]
    a.on_error, a.stop_on_match = d["on_error"], d["stop_on_match"]
    a.tx_codes_json, a.channels_json, a.enabled = d["tx_codes"], d["channels"], d["enabled"]
    a.updated_by = current_user
    a.version = (a.version or 1) + 1
    db.add(HostAlgoVersion(algo_id=a.id, version=a.version, language=a.language, code=a.code,
                           change_note=d.get("change_note") or ("Code changed" if changed_code else "Settings changed"),
                           changed_by=current_user))
    record_audit(db, "HOST_ALGO", a.id, "UPDATE", performed_by=current_user,
                 change_summary=f"Algo {a.algo_code} updated to v{a.version} ({a.mode}, {'enabled' if a.enabled else 'disabled'})")
    db.commit()
    banks, profiles = _maps(db)
    return _algo_dict(a, banks, profiles)


@router.delete("/algos/{algo_id}")
def delete_algo(algo_id: str, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    a = _get_algo(db, algo_id)
    record_audit(db, "HOST_ALGO", a.id, "DELETE", performed_by=current_user, change_summary=f"Algo {a.algo_code} deleted")
    db.query(HostAlgoVersion).filter(HostAlgoVersion.algo_id == a.id).delete()
    db.delete(a)
    db.commit()
    return {"status": "deleted"}


class ToggleBody(BaseModel):
    enabled: Optional[bool] = None
    mode: Optional[str] = None


@router.post("/algos/{algo_id}/toggle")
def toggle_algo(algo_id: str, body: ToggleBody, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    a = _get_algo(db, algo_id)
    if body.enabled is not None:
        a.enabled = body.enabled
    if body.mode:
        m = body.mode.upper()
        if m not in ALGO_MODES:
            raise HTTPException(status_code=400, detail="mode must be ENFORCE or MONITOR")
        a.mode = m
    a.updated_by = current_user
    record_audit(db, "HOST_ALGO", a.id, "TOGGLE", performed_by=current_user,
                 change_summary=f"Algo {a.algo_code}: enabled={a.enabled}, mode={a.mode}")
    db.commit()
    return {"status": "ok", "enabled": a.enabled, "mode": a.mode}


@router.get("/algos/{algo_id}/versions")
def algo_versions(algo_id: str, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    _get_algo(db, algo_id)
    rows = db.query(HostAlgoVersion).filter(HostAlgoVersion.algo_id == algo_id).order_by(HostAlgoVersion.version.desc()).limit(50).all()
    return [
        {"version": v.version, "language": v.language, "code": v.code, "change_note": v.change_note,
         "changed_by": v.changed_by, "created_at": _iso(v.created_at)}
        for v in rows
    ]


class RollbackBody(BaseModel):
    version: int


@router.post("/algos/{algo_id}/rollback")
def rollback_algo(algo_id: str, body: RollbackBody, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    a = _get_algo(db, algo_id)
    v = db.query(HostAlgoVersion).filter(HostAlgoVersion.algo_id == algo_id, HostAlgoVersion.version == body.version).first()
    if not v:
        raise HTTPException(status_code=404, detail="Version not found")
    a.language, a.code = v.language, v.code
    a.version = (a.version or 1) + 1
    a.updated_by = current_user
    db.add(HostAlgoVersion(algo_id=a.id, version=a.version, language=a.language, code=a.code,
                           change_note=f"Rollback to v{body.version}", changed_by=current_user))
    record_audit(db, "HOST_ALGO", a.id, "ROLLBACK", performed_by=current_user,
                 change_summary=f"Algo {a.algo_code} rolled back to v{body.version} (now v{a.version})")
    db.commit()
    return {"status": "ok", "version": a.version}


# ============================================================================
# RULES & CHECKS tab  (built-in check switches + simple rules)
# ============================================================================
BUILTIN_CHECKS: Dict[str, Dict[str, Any]] = {
    "AUTHORIZEACCTBALANCESTRANS": {
        "title": "Account balance check", "affects_host": True, "order": 8, "decline_rc": "51",
        "what": "Declines a debit when the available balance plus the overdraft cannot cover the amount.",
        "when_off": "Customers can spend more than they have: balances can go negative.",
    },
    "CHECKCARDLIMITS": {
        "title": "Card limit check", "affects_host": True, "order": 6, "decline_rc": "61",
        "what": "Applies the per-transaction and daily limits stored on every card (menu 5. Card Limits).",
        "when_off": "The per-card limits are ignored. Authorization-profile limits still apply.",
    },
    "CHECKACCT2CARDLIMITS": {
        "title": "Account limit check", "affects_host": True, "order": 7, "decline_rc": "61",
        "what": "Applies the per-transaction and daily limits stored on the linked account (menu 6. Account Limits).",
        "when_off": "The per-account limits are ignored. Authorization-profile limits still apply.",
    },
    "DEFAULTREQUESTFUNCTION": {
        "title": "Request router", "affects_host": False,
        "what": "Name of the function that receives the incoming TIC / ISO request. Reference only.",
    },
    "DEFAULTRESPONSEFUNCTION": {
        "title": "Response builder", "affects_host": False,
        "what": "Name of the function that builds the TIC v2.164e response. Reference only.",
    },
    "POSRESPONSECONTROLFUNCTION": {
        "title": "POS response control", "affects_host": False,
        "what": "Response-code mapping and F105 balance output settings. Reference only: the engine does not read it yet.",
    },
}


def _check_enabled(p: HostParameter) -> bool:
    val = p.parameter_value
    on = bool(val.get("enabled", True)) if isinstance(val, dict) else bool(val)
    return bool(p.active) and on


@router.get("/checks")
def list_builtin_checks(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    params = db.query(HostParameter).order_by(HostParameter.parameter_group.asc(), HostParameter.parameter_name.asc()).all()
    rows = []
    for p in params:
        info = BUILTIN_CHECKS.get(p.parameter_name) if p.parameter_group == "RAJON_AUTH_RULES" else None
        rows.append(
            {
                "id": p.id, "group": p.parameter_group, "name": p.parameter_name,
                "title": info["title"] if info else p.parameter_name,
                "what": (info["what"] if info else None) or p.description or "",
                "when_off": info.get("when_off") if info else None,
                "decline_rc": info.get("decline_rc") if info else None,
                "order": info.get("order") if info else None,
                "affects_host": bool(info and info["affects_host"]),
                "known": bool(info), "enabled": _check_enabled(p), "value": p.parameter_value,
            }
        )
    rows.sort(key=lambda r: (not r["affects_host"], r["order"] or 99, r["name"]))
    return rows


class CheckToggleBody(BaseModel):
    enabled: bool


@router.post("/checks/{param_id}/toggle")
def toggle_builtin_check(param_id: str, body: CheckToggleBody, db: Session = Depends(get_db),
                         current_user: str = Depends(get_current_user)):
    p = db.query(HostParameter).filter(HostParameter.id == param_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Check not found")
    before = {"value": p.parameter_value, "active": p.active}
    val = dict(p.parameter_value) if isinstance(p.parameter_value, dict) else {}
    val["enabled"] = bool(body.enabled)
    p.parameter_value = val  # re-assigned so the JSON change is saved
    p.active = True          # the on/off state lives in parameter_value.enabled
    record_audit(db, "HOST_PARAMETER", p.id, "TOGGLE", performed_by=current_user, before_state=before,
                 after_state={"value": val, "active": True},
                 change_summary=f"Built-in check {p.parameter_name} {'enabled' if body.enabled else 'disabled'}")
    db.commit()
    return {"status": "ok", "id": p.id, "enabled": bool(body.enabled)}


RULE_FIELDS: List[Dict[str, Any]] = [
    {"name": "amount", "type": "number", "description": "Transaction amount (major units)", "example": 25000},
    {"name": "trancode", "type": "text", "description": "Transaction code: 10 cash withdrawal, 00 purchase, 31 balance inquiry", "example": "10"},
    {"name": "mti", "type": "text", "description": "Message type indicator", "example": "0200"},
    {"name": "currency", "type": "text", "description": "Currency sent in DE49", "example": "050"},
    {"name": "hour", "type": "number", "description": "Hour of the day 0-23 (from DE12 terminal time)", "example": 14},
    {"name": "mcc", "type": "text", "description": "Merchant category code (DE18)", "example": "6011"},
    {"name": "terminal_id", "type": "text", "description": "Terminal ID (DE41)", "example": "ATM0001"},
    {"name": "is_foreign", "type": "bool", "description": "True when the terminal country (DE19) is not 050", "example": False},
    {"name": "card_status", "type": "text", "description": "ACTIVE, BLOCKED, EXPIRED ...", "example": "ACTIVE"},
    {"name": "account_balance", "type": "number", "description": "Available balance of the account", "example": 150000},
    {"name": "daily_used", "type": "number", "description": "Amount the card already used today", "example": 4000},
    {"name": "institution.code", "type": "text", "description": "Issuer bank code", "example": "XBANK"},
    {"name": "institution.name", "type": "text", "description": "Issuer bank name", "example": "X Bank PLC"},
    {"name": "acquirer_bank", "type": "text", "description": "Terminal owner (acquirer) bank code", "example": "YBANK"},
    {"name": "ps_name", "type": "text", "description": "Processing system (ITCL, NPSB, VISA ...)", "example": "ITCL"},
    {"name": "bin", "type": "text", "description": "First 6 digits of the PAN", "example": "456789"},
    {"name": "pan", "type": "text", "description": "Full PAN", "example": "4567890123450001"},
    {"name": "channel", "type": "text", "description": "POS condition code (DE25). 00 normal, 08 e-commerce", "example": "00"},
]


@router.get("/rules/fields")
def rule_fields(_: str = Depends(get_current_user)):
    return RULE_FIELDS


class RuleExprBody(BaseModel):
    expression: str = ""


@router.post("/rules/validate")
def rule_validate(body: RuleExprBody, _: str = Depends(get_current_user)):
    from app.rules_evaluator import SafeAstEvaluator

    if not (body.expression or "").strip():
        return {"valid": False, "error": "The condition is empty"}
    sample: Dict[str, Any] = {}
    for f in RULE_FIELDS:
        if "." in f["name"]:
            head, tail = f["name"].split(".", 1)
            sample.setdefault(head, {})[tail] = f["example"]
        else:
            sample[f["name"]] = f["example"]
    sample["tran_code"] = "10"
    try:
        SafeAstEvaluator.evaluate(body.expression, sample)
        return {"valid": True, "error": None}
    except Exception as exc:
        return {"valid": False, "error": str(exc)}


class RuleTestBody(BaseModel):
    expression: str = ""
    card_id: Optional[str] = None
    pan: Optional[str] = None
    overrides: Dict[str, Any] = Field(default_factory=dict)


@router.post("/rules/test")
def rule_test(body: RuleTestBody, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    """Evaluate a simple-rule condition on a REAL card with sample values (nothing is saved)."""
    from app.rules_evaluator import SafeAstEvaluator, build_rule_context

    card = _find_card(db, body.card_id, body.pan, None)
    if card is None:
        raise HTTPException(status_code=404, detail="No card available to test with")
    ctx = build_test_context(db, card, body.overrides)
    r = ctx.raw
    context = build_rule_context(
        mti="0200", fields=r.fields, tx_code=str(ctx.data["tx"]["tran_code"]), tx_amount=r.amount, card=r.card,
        customer=r.cust, account=r.acct, issuer_inst=r.issuer, acquirer_inst=r.acq, ps_code=r.ps_code or "ITCL",
        card_limit=r.climit,
    )
    db.rollback()
    try:
        matched = SafeAstEvaluator.evaluate(body.expression, context)
        return {"valid": True, "matched": matched, "error": None, "context": context}
    except Exception as exc:
        return {"valid": False, "matched": False, "error": str(exc), "context": context}
'''

HC_RULES_TSX = r'''import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  Info,
  ListChecks,
  Loader2,
  Play,
  Plus,
  Save,
  ShieldCheck,
  Sparkles,
  Trash2,
  Wand2,
  XCircle,
} from 'lucide-react';
import { apiFetch } from '../../api';
import {
  Badge,
  Labeled,
  NumInput,
  RcSelect,
  SegButtons,
  Toggle,
  fmtNum,
  inputCls,
  panelCls,
  useToast,
} from './ui';

// ============================================================================
// RULES & CHECKS
//   1. Built-in checks  - the switches the host engine really reads (balance, card limits, account limits)
//   2. Simple rules     - one condition, no coding, can be added / edited / tested here
//   (scripts live in the Algo Control tab)
// ============================================================================

type Section = 'checks' | 'rules';

interface Cond {
  field: string;
  op: string;
  value: string;
}
interface RuleForm {
  id?: string;
  rule_code: string;
  name: string;
  description: string;
  mode: 'BUILDER' | 'SCRIPT';
  logic: 'AND' | 'OR';
  conditions: Cond[];
  expression: string;
  action: 'DECLINE' | 'APPROVE' | 'FLAG';
  response_code: string;
  message: string;
  priority: number;
  stop_on_match: boolean;
  enabled: boolean;
}

const blankRule = (): RuleForm => ({
  rule_code: '', name: '', description: '', mode: 'BUILDER', logic: 'AND',
  conditions: [{ field: 'amount', op: '>', value: '' }], expression: '', action: 'DECLINE',
  response_code: '61', message: 'Declined by rule', priority: 100, stop_on_match: true, enabled: true,
});

const NUM_OPS = [
  { v: '>', t: 'is greater than' }, { v: '>=', t: 'is at least' }, { v: '<', t: 'is less than' },
  { v: '<=', t: 'is at most' }, { v: '==', t: 'equals' }, { v: '!=', t: 'does not equal' },
];
const TEXT_OPS = [
  { v: '==', t: 'equals' }, { v: '!=', t: 'does not equal' }, { v: 'in', t: 'is one of (comma list)' },
  { v: 'not in', t: 'is none of (comma list)' },
];
const BOOL_OPS = [{ v: 'true', t: 'is true' }, { v: 'false', t: 'is false' }];

const ACTION_HELP: Record<string, string> = {
  DECLINE: 'Stops the transaction with the response code below.',
  APPROVE: 'Accepts at the rule layer and stops the remaining rules (PIN, limits and balance still apply).',
  FLAG: 'Only records the match and lets the transaction continue.',
};

const lit = (type: string, v: string) =>
  type === 'number' ? String(Number(v)) : `'${String(v).trim().replace(/\\/g, '\\\\').replace(/'/g, "\\'")}'`;

/** one condition -> expression text understood by the host rule engine */
export const condToExpr = (c: Cond, type: string): string => {
  if (type === 'bool') return c.op === 'false' ? `not ${c.field}` : c.field;
  if (c.op === 'in' || c.op === 'not in') {
    const items = c.value.split(',').map((x) => x.trim()).filter(Boolean);
    if (!items.length) return '';
    const parts = items.map((x) => `${c.field} ${c.op === 'in' ? '==' : '!='} ${lit(type, x)}`);
    return items.length === 1 ? parts[0] : `(${parts.join(c.op === 'in' ? ' or ' : ' and ')})`;
  }
  if (c.value.trim() === '') return '';
  if (type === 'number' && Number.isNaN(Number(c.value))) return '';
  return `${c.field} ${c.op} ${lit(type, c.value)}`;
};

interface Props {
  meta: any;
  onChanged?: () => void;
}

export const RulesAndChecksTab: React.FC<Props> = ({ meta, onChanged }) => {
  const { show, node: toastNode } = useToast();
  const [section, setSection] = useState<Section>('checks');
  return (
    <div className="space-y-5">
      {toastNode}
      <div className={`${panelCls} p-5`}>
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-xl bg-emerald-500/10 text-emerald-500 flex items-center justify-center shrink-0">
            <Info size={18} />
          </div>
          <div className="text-xs text-slate-400 leading-relaxed">
            <div className="text-sm font-bold text-slate-200 mb-1">How the host decides, from simple to advanced</div>
            <ol className="list-decimal pl-4 space-y-0.5">
              <li><strong className="text-slate-300">Built-in checks</strong>: ready-made protections you switch on or off (balance, card limits, account limits).</li>
              <li><strong className="text-slate-300">Simple rules</strong>: your own "if this, then decline / approve / flag" rules. No coding, built with dropdowns.</li>
              <li><strong className="text-slate-300">Algo Control</strong> (next tab): Python or SQL blocks for anything more complex, per bank or card profile.</li>
            </ol>
          </div>
        </div>
      </div>

      <SegButtons
        value={section}
        onChange={(v) => setSection(v as Section)}
        options={[
          { value: 'checks', label: 'Built-in checks' },
          { value: 'rules', label: 'My simple rules', tone: 'sky' },
        ]}
      />

      {section === 'checks' ? <BuiltInChecks show={show} onChanged={onChanged} /> : <SimpleRules meta={meta} show={show} onChanged={onChanged} />}
    </div>
  );
};

// ============================================================================
// 1. Built-in checks
// ============================================================================
const BuiltInChecks: React.FC<{ show: (t: string, e?: boolean) => void; onChanged?: () => void }> = ({ show, onChanged }) => {
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showRef, setShowRef] = useState(false);

  const load = useCallback(async () => {
    try {
      setRows(await apiFetch('/local-host/checks'));
    } catch (e: any) {
      show(e.message || 'Could not load the checks', true);
    } finally {
      setLoading(false);
    }
  }, [show]);
  useEffect(() => {
    load();
  }, [load]);

  const toggle = async (r: any, enabled: boolean) => {
    if (!enabled && r.affects_host && !confirm(`Switch OFF "${r.title}" for every bank?\n\n${r.when_off || ''}`)) return;
    try {
      await apiFetch(`/local-host/checks/${r.id}/toggle`, { method: 'POST', body: JSON.stringify({ enabled }) });
      setRows((list) => list.map((x) => (x.id === r.id ? { ...x, enabled } : x)));
      show(`${r.title} is now ${enabled ? 'ON' : 'OFF'}`);
      onChanged?.();
    } catch (e: any) {
      show(e.message || 'Could not change the check', true);
    }
  };

  const live = rows.filter((r) => r.affects_host);
  const ref = rows.filter((r) => !r.affects_host);

  if (loading) return <div className={`${panelCls} p-10 text-center text-xs text-slate-400`}><Loader2 className="animate-spin mx-auto mb-2" size={18} /> Loading...</div>;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {live.map((r) => (
          <div key={r.id} className={`${panelCls} p-5 flex flex-col gap-3 ${r.enabled ? '' : 'border-rose-500/30'}`}>
            <div className="flex items-start gap-3">
              <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${r.enabled ? 'bg-emerald-500/10 text-emerald-500' : 'bg-rose-500/10 text-rose-500'}`}>
                <ShieldCheck size={18} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-bold">{r.title}</div>
                <div className="text-[10px] font-mono text-slate-500">{r.name}</div>
              </div>
              <Toggle checked={r.enabled} label={`${r.title} switch`} onChange={(v) => toggle(r, v)} />
            </div>
            <p className="text-[11px] text-slate-400 leading-relaxed">{r.what}</p>
            <div className="mt-auto flex flex-wrap items-center gap-2">
              <Badge tone={r.enabled ? 'emerald' : 'rose'}>{r.enabled ? 'ON' : 'OFF'}</Badge>
              {r.decline_rc && <Badge tone="slate">declines with RC {r.decline_rc}</Badge>}
              {r.order && <Badge tone="slate">step {r.order}</Badge>}
            </div>
            {!r.enabled && r.when_off && (
              <div className="flex items-start gap-2 text-[11px] text-rose-400 bg-rose-500/10 border border-rose-500/20 rounded-lg p-2.5">
                <AlertTriangle size={13} className="mt-0.5 shrink-0" /> {r.when_off}
              </div>
            )}
          </div>
        ))}
      </div>

      {ref.length > 0 && (
        <div className={`${panelCls} overflow-hidden`}>
          <button type="button" onClick={() => setShowRef(!showRef)} className="w-full flex items-center gap-3 px-5 py-3 text-left hover:bg-slate-50 dark:hover:bg-slate-800/30">
            <Info size={15} className="text-slate-400" />
            <span className="text-xs font-bold">Reference parameters ({ref.length})</span>
            <span className="text-[11px] text-slate-400">Stored for documentation. The host engine does not read them, so they have no switch.</span>
            <ChevronDown size={14} className={`ml-auto text-slate-400 transition-transform ${showRef ? 'rotate-180' : ''}`} />
          </button>
          {showRef && (
            <div className="divide-y divide-slate-100 dark:divide-slate-800/80 border-t border-slate-200 dark:border-slate-800">
              {ref.map((r) => (
                <div key={r.id} className="px-5 py-3 grid grid-cols-12 gap-3 items-start">
                  <div className="col-span-12 md:col-span-3">
                    <div className="text-xs font-semibold">{r.title}</div>
                    <div className="text-[10px] font-mono text-slate-500">{r.group} / {r.name}</div>
                  </div>
                  <div className="col-span-12 md:col-span-5 text-[11px] text-slate-400">{r.what}</div>
                  <pre className="col-span-12 md:col-span-4 text-[10px] font-mono text-slate-400 bg-slate-950 rounded-lg p-2 overflow-x-auto">{JSON.stringify(r.value)}</pre>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// ============================================================================
// 2. Simple rules
// ============================================================================
const SimpleRules: React.FC<{ meta: any; show: (t: string, e?: boolean) => void; onChanged?: () => void }> = ({ meta, show, onChanged }) => {
  const [rules, setRules] = useState<any[]>([]);
  const [fields, setFields] = useState<any[]>([]);
  const [selected, setSelected] = useState<string>(''); // id, 'new' or ''
  const [form, setForm] = useState<RuleForm | null>(null);
  const [baseline, setBaseline] = useState('');
  const [saving, setSaving] = useState(false);
  const [check, setCheck] = useState<{ valid: boolean; error: string | null } | null>(null);
  const [showFields, setShowFields] = useState(false);
  const rcs = meta?.response_codes || [];

  const load = useCallback(async () => {
    try {
      const [r, f] = await Promise.all([apiFetch('/authorizer-rules'), apiFetch('/local-host/rules/fields')]);
      setRules(r);
      setFields(f);
    } catch (e: any) {
      show(e.message || 'Could not load the rules', true);
    }
  }, [show]);
  useEffect(() => {
    load();
  }, [load]);

  const typeOf = useCallback((name: string) => fields.find((f) => f.name === name)?.type || 'text', [fields]);

  const expression = useMemo(() => {
    if (!form) return '';
    if (form.mode === 'SCRIPT') return form.expression.trim();
    const parts = form.conditions.map((c) => condToExpr(c, typeOf(c.field))).filter(Boolean);
    return parts.join(form.logic === 'AND' ? ' and ' : ' or ');
  }, [form, typeOf]);

  const dirty = !!form && JSON.stringify(form) !== baseline;

  const summary = useMemo(() => {
    if (!form || !expression) return '';
    const verb = form.action === 'DECLINE' ? `Decline (RC ${form.response_code})` : form.action === 'APPROVE' ? 'Approve at the rule layer' : 'Flag';
    return `${verb} when ${expression.replace(/ and /g, ' AND ').replace(/ or /g, ' OR ')}`;
  }, [form, expression]);

  // live check of the condition
  useEffect(() => {
    if (!form || !expression) {
      setCheck(null);
      return;
    }
    const t = setTimeout(async () => {
      try {
        setCheck(await apiFetch('/local-host/rules/validate', { method: 'POST', body: JSON.stringify({ expression }) }));
      } catch {
        setCheck(null);
      }
    }, 450);
    return () => clearTimeout(t);
  }, [expression]); // eslint-disable-line react-hooks/exhaustive-deps

  const open = (r: any) => {
    if (dirty && !confirm('Discard your unsaved changes?')) return;
    const cj = r.conditions_json;
    const builder = r.rule_mode === 'BUILDER' && cj && Array.isArray(cj.conditions) && cj.conditions.length > 0;
    const f: RuleForm = {
      id: r.id, rule_code: r.rule_code, name: r.name, description: r.description || '', mode: builder ? 'BUILDER' : 'SCRIPT',
      logic: (cj && cj.logic) || 'AND', conditions: builder ? cj.conditions : [{ field: 'amount', op: '>', value: '' }],
      expression: r.expression, action: r.action, response_code: r.response_code, message: r.message,
      priority: r.priority, stop_on_match: r.stop_on_match, enabled: r.enabled,
    };
    setSelected(r.id);
    setForm(f);
    setBaseline(JSON.stringify(f));
  };

  const create = () => {
    if (dirty && !confirm('Discard your unsaved changes?')) return;
    const f = blankRule();
    setSelected('new');
    setForm(f);
    setBaseline(JSON.stringify(f));
  };

  const patch = (p: Partial<RuleForm>) => setForm((f) => (f ? { ...f, ...p } : f));
  const setCond = (i: number, p: Partial<Cond>) =>
    setForm((f) => {
      if (!f) return f;
      const conditions = f.conditions.map((c, idx) => {
        if (idx !== i) return c;
        const next = { ...c, ...p };
        if (p.field && p.field !== c.field) {
          const t = typeOf(p.field);
          next.op = t === 'number' ? '>' : t === 'bool' ? 'true' : '==';
          next.value = '';
        }
        return next;
      });
      return { ...f, conditions };
    });

  const problems: string[] = [];
  if (form) {
    if (form.rule_code.trim().length < 3) problems.push('Enter a rule code (3 or more characters)');
    if (form.name.trim().length < 2) problems.push('Enter a name');
    if (!expression) problems.push(form.mode === 'BUILDER' ? 'Complete at least one condition' : 'Enter the condition');
    if (check && !check.valid && expression) problems.push('Fix the condition (see the red message above)');
    if (!/^[0-9A-Za-z]{2}$/.test(form.response_code.trim()) && form.action === 'DECLINE') problems.push('Choose a response code');
  }

  const save = async () => {
    if (!form || problems.length) return;
    setSaving(true);
    try {
      const body: any = {
        rule_code: form.rule_code.trim().toUpperCase().replace(/[^A-Z0-9_\-]/g, '_'),
        name: form.name.trim(),
        description: form.description.trim() || null,
        priority: Number(form.priority) || 100,
        rule_mode: form.mode,
        conditions_json: form.mode === 'BUILDER' ? { logic: form.logic, conditions: form.conditions } : null,
        expression,
        action: form.action,
        response_code: form.response_code.trim(),
        message: form.message.trim() || 'Declined by rule',
        stop_on_match: form.stop_on_match,
        enabled: form.enabled,
      };
      let saved: any;
      if (form.id) {
        const { rule_code, ...rest } = body; // the code of an existing rule cannot change
        saved = await apiFetch(`/authorizer-rules/${form.id}`, { method: 'PUT', body: JSON.stringify(rest) });
      } else {
        saved = await apiFetch('/authorizer-rules', { method: 'POST', body: JSON.stringify(body) });
      }
      show(`Rule ${saved.rule_code} saved`);
      await load();
      open({ ...saved });
      onChanged?.();
    } catch (e: any) {
      show(e.message || 'Save failed', true);
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!form?.id || !confirm(`Delete rule ${form.rule_code}?`)) return;
    try {
      await apiFetch(`/authorizer-rules/${form.id}`, { method: 'DELETE' });
      show(`Rule ${form.rule_code} deleted`);
      setSelected('');
      setForm(null);
      await load();
    } catch (e: any) {
      show(e.message || 'Delete failed', true);
    }
  };

  const toggleRule = async (r: any, enabled: boolean) => {
    try {
      await apiFetch(`/authorizer-rules/${r.id}`, { method: 'PUT', body: JSON.stringify({ enabled }) });
      setRules((l) => l.map((x) => (x.id === r.id ? { ...x, enabled } : x)));
      if (form?.id === r.id) {
        setForm((f) => (f ? { ...f, enabled } : f));
        setBaseline((b) => (b ? JSON.stringify({ ...JSON.parse(b), enabled }) : b));
      }
      show(`${r.rule_code} ${enabled ? 'enabled' : 'disabled'}`);
    } catch (e: any) {
      show(e.message || 'Could not change the rule', true);
    }
  };

  const insertField = (name: string) => {
    if (!form) return;
    if (form.mode === 'SCRIPT') patch({ expression: `${form.expression}${form.expression && !form.expression.endsWith(' ') ? ' ' : ''}${name}` });
    else show('Pick fields from the dropdown of each condition, or switch to "Write expression".');
  };

  return (
    <div className="grid grid-cols-1 xl:grid-cols-12 gap-5">
      {/* ---------- list */}
      <aside className={`xl:col-span-4 ${panelCls} overflow-hidden self-start`}>
        <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
          <div className="text-xs font-bold uppercase tracking-wider text-slate-500">
            Simple rules <span className="text-emerald-500 font-mono">{rules.length}</span>
          </div>
          <button type="button" onClick={create} className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold shadow-md shadow-emerald-600/20">
            <Plus size={13} /> New rule
          </button>
        </div>
        <div className="max-h-[640px] overflow-y-auto">
          {rules.length === 0 && (
            <div className="p-8 text-center text-xs text-slate-400 space-y-2">
              <ListChecks className="mx-auto text-slate-500" size={26} />
              <div>No rule yet. Click <strong>New rule</strong> and build one with dropdowns.</div>
            </div>
          )}
          {rules.map((r) => (
            <div key={r.id} role="button" tabIndex={0} aria-label={`open rule ${r.rule_code}`} onClick={() => open(r)} onKeyDown={(e) => e.key === 'Enter' && open(r)}
              className={`px-4 py-3 border-b border-slate-100 dark:border-slate-800/80 cursor-pointer border-l-2 ${selected === r.id ? 'bg-emerald-500/10 border-l-emerald-500' : 'border-l-transparent hover:bg-slate-50 dark:hover:bg-slate-800/50'} ${r.enabled ? '' : 'opacity-60'}`}>
              <div className="flex items-start gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="font-mono text-[11px] font-bold text-emerald-500">{r.rule_code}</span>
                    <Badge tone={r.action === 'DECLINE' ? 'rose' : r.action === 'APPROVE' ? 'emerald' : 'amber'}>{r.action}</Badge>
                    {r.action === 'DECLINE' && <Badge tone="slate">RC {r.response_code}</Badge>}
                  </div>
                  <div className="text-xs mt-0.5 truncate">{r.name}</div>
                  <div className="text-[10px] font-mono text-sky-400 mt-1 truncate" title={r.expression}>{r.expression}</div>
                  <div className="text-[10px] text-slate-400 mt-1 font-mono">priority {r.priority} · {fmtNum(r.hit_count, 0)} hits</div>
                </div>
                <div onClick={(e) => e.stopPropagation()}>
                  <Toggle checked={r.enabled} label={`enable ${r.rule_code}`} onChange={(v) => toggleRule(r, v)} />
                </div>
              </div>
            </div>
          ))}
        </div>
      </aside>

      {/* ---------- editor */}
      <div className="xl:col-span-8 space-y-4 min-w-0">
        {!form ? (
          <div className={`${panelCls} p-14 text-center`}>
            <div className="w-16 h-16 mx-auto rounded-2xl bg-gradient-to-br from-emerald-500/20 to-sky-500/20 text-emerald-500 flex items-center justify-center mb-4"><Wand2 size={28} /></div>
            <h3 className="text-base font-bold">Make your own rule</h3>
            <p className="text-xs text-slate-400 mt-2 max-w-md mx-auto leading-relaxed">
              Example: <em>decline cash withdrawals above 50,000</em>. Choose a field, an operator and a value, then choose what the host should do.
              Rules run for every transaction, before the PIN and HSM checks, in priority order.
            </p>
            <button type="button" onClick={create} className="mt-5 inline-flex items-center gap-1.5 text-xs px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold"><Plus size={14} /> New rule</button>
          </div>
        ) : (
          <>
            <div className={`${panelCls} overflow-hidden`}>
              <div className="flex flex-wrap items-center gap-3 px-5 py-3.5 border-b border-slate-200 dark:border-slate-800 bg-gradient-to-r from-slate-50 to-transparent dark:from-slate-800/40">
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-sm font-bold">{form.id ? form.rule_code : 'New rule'}</h2>
                    {dirty && <Badge tone="amber">unsaved</Badge>}
                  </div>
                  <p className="text-[11px] text-slate-400">Rules run in priority order (1 first) before the PIN / HSM checks.</p>
                </div>
                <div className="ml-auto flex items-center gap-2">
                  <button type="button" onClick={() => setShowFields(!showFields)} className="flex items-center gap-1.5 text-[11px] px-3 py-1.5 rounded-lg bg-sky-600/10 text-sky-500 hover:bg-sky-600/20 font-semibold">
                    <Sparkles size={13} /> Available fields
                  </button>
                  {form.id && <button type="button" aria-label="delete rule" onClick={remove} className="p-2 rounded-lg text-rose-500 hover:bg-rose-500/10"><Trash2 size={14} /></button>}
                </div>
              </div>

              <div className="p-5 space-y-5">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <Labeled label="Rule code *" hint={form.id ? 'A saved rule keeps its code' : 'Letters, numbers, _ and -'}>
                    <input aria-label="rule code" disabled={!!form.id} value={form.rule_code} onChange={(e) => patch({ rule_code: e.target.value })} className={`${inputCls} font-mono`} placeholder="BLOCK_BIG_CASH" />
                  </Labeled>
                  <Labeled label="Name *" className="md:col-span-2">
                    <input aria-label="rule name" value={form.name} onChange={(e) => {
                      const v = e.target.value;
                      patch({ name: v, ...(!form.id && (form.rule_code === '' || form.rule_code === autoCode(form.name)) ? { rule_code: autoCode(v) } : {}) });
                    }} className={inputCls} placeholder="Decline cash above 50,000" />
                  </Labeled>
                </div>

                {/* WHEN */}
                <div className="rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden">
                  <div className="flex flex-wrap items-center gap-3 px-4 py-2.5 bg-slate-50 dark:bg-slate-950/50">
                    <span className="text-xs font-bold">WHEN</span>
                    <SegButtons value={form.mode} onChange={(m) => patch({ mode: m, expression: m === 'SCRIPT' && !form.expression ? expression : form.expression })}
                      options={[{ value: 'BUILDER', label: 'Build with dropdowns', tone: 'sky' }, { value: 'SCRIPT', label: 'Write expression', tone: 'sky' }]} />
                    {form.mode === 'BUILDER' && form.conditions.length > 1 && (
                      <SegButtons value={form.logic} onChange={(l) => patch({ logic: l })}
                        options={[{ value: 'AND', label: 'ALL must match' }, { value: 'OR', label: 'ANY can match', tone: 'amber' }]} />
                    )}
                  </div>
                  <div className="p-4 space-y-2.5">
                    {form.mode === 'BUILDER' ? (
                      <>
                        {form.conditions.map((c, i) => {
                          const type = typeOf(c.field);
                          const ops = type === 'number' ? NUM_OPS : type === 'bool' ? BOOL_OPS : TEXT_OPS;
                          return (
                            <div key={i} className="grid grid-cols-12 gap-2 items-center">
                              <select aria-label={`condition ${i + 1} field`} className={`${inputCls} col-span-12 md:col-span-4`} value={c.field} onChange={(e) => setCond(i, { field: e.target.value })}>
                                {fields.map((f) => <option key={f.name} value={f.name}>{f.name} - {f.description}</option>)}
                              </select>
                              <select aria-label={`condition ${i + 1} operator`} className={`${inputCls} col-span-6 md:col-span-3`} value={c.op} onChange={(e) => setCond(i, { op: e.target.value })}>
                                {ops.map((o) => <option key={o.v} value={o.v}>{o.t}</option>)}
                              </select>
                              {type === 'bool' ? <div className="col-span-5 md:col-span-4" /> : (
                                <input aria-label={`condition ${i + 1} value`} className={`${inputCls} font-mono col-span-5 md:col-span-4`} value={c.value} placeholder={type === 'number' ? 'e.g. 50000' : c.op.includes('in') ? "e.g. 10, 11" : "e.g. 6011"} onChange={(e) => setCond(i, { value: e.target.value })} />
                              )}
                              <button type="button" aria-label={`remove condition ${i + 1}`} disabled={form.conditions.length === 1} onClick={() => patch({ conditions: form.conditions.filter((_, idx) => idx !== i) })}
                                className="col-span-1 text-slate-500 hover:text-rose-500 disabled:opacity-30"><XCircle size={16} /></button>
                            </div>
                          );
                        })}
                        <button type="button" onClick={() => patch({ conditions: [...form.conditions, { field: 'amount', op: '>', value: '' }] })} className="text-[11px] text-emerald-500 hover:underline flex items-center gap-1"><Plus size={12} /> add condition</button>
                      </>
                    ) : (
                      <>
                        <textarea aria-label="rule expression" rows={3} value={form.expression} onChange={(e) => patch({ expression: e.target.value })}
                          placeholder="trancode == '10' and amount > 50000" className="w-full bg-slate-950 text-emerald-300 border border-slate-800 rounded-lg p-3 text-xs font-mono" />
                        <p className="text-[10px] text-slate-500">Use and / or / not, comparisons (== != &gt; &lt; in) and the fields from "Available fields". Example: <code className="text-emerald-400">institution.code == 'XBANK' and hour &lt; 5</code></p>
                      </>
                    )}
                    <div className="text-[11px] font-mono text-slate-400 bg-slate-950 rounded-lg px-3 py-2" data-testid="expression-preview">
                      <span className="text-slate-500">condition: </span><span className="text-emerald-300">{expression || '(incomplete)'}</span>
                    </div>
                    {check && expression && (
                      check.valid ? <div className="text-[11px] text-emerald-500 flex items-center gap-1"><CheckCircle2 size={12} /> Condition understood by the host</div>
                        : <div role="alert" className="text-[11px] text-rose-400 flex items-center gap-1"><AlertTriangle size={12} /> {check.error}</div>
                    )}
                  </div>
                </div>

                {/* THEN */}
                <div className="rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden">
                  <div className="px-4 py-2.5 bg-slate-50 dark:bg-slate-950/50 text-xs font-bold">THEN</div>
                  <div className="p-4 grid grid-cols-1 md:grid-cols-12 gap-4">
                    <div className="md:col-span-4">
                      <div className="text-[11px] text-slate-400 font-medium mb-1.5">Action</div>
                      <SegButtons value={form.action} onChange={(a) => patch({ action: a })}
                        options={[{ value: 'DECLINE', label: 'Decline', tone: 'rose' }, { value: 'APPROVE', label: 'Approve', tone: 'emerald' }, { value: 'FLAG', label: 'Flag', tone: 'amber' }]} />
                      <p className="text-[10px] text-slate-500 mt-1.5 leading-snug">{ACTION_HELP[form.action]}</p>
                    </div>
                    {form.action === 'DECLINE' && (
                      <Labeled label="Response code" className="md:col-span-4">
                        <RcSelect value={form.response_code} codes={rcs} ariaLabel="rule response code" onChange={(v) => patch({ response_code: v })} />
                      </Labeled>
                    )}
                    <Labeled label="Priority" hint="1 runs first" className="md:col-span-2">
                      <NumInput value={form.priority} ariaLabel="rule priority" placeholder="100" onChange={(v) => patch({ priority: v || 100 })} />
                    </Labeled>
                    <div className="md:col-span-2 flex items-end gap-2 pb-1">
                      <Toggle checked={form.enabled} label="rule enabled" onChange={(v) => patch({ enabled: v })} />
                      <span className="text-xs font-semibold">{form.enabled ? 'On' : 'Off'}</span>
                    </div>
                    <Labeled label="Message (shown in the transaction checks)" className="md:col-span-8">
                      <input aria-label="rule message" className={inputCls} value={form.message} onChange={(e) => patch({ message: e.target.value })} />
                    </Labeled>
                    <div className="md:col-span-4 flex items-end gap-2 pb-1">
                      <Toggle checked={form.stop_on_match} label="stop on match" onChange={(v) => patch({ stop_on_match: v })} />
                      <span className="text-[11px] text-slate-400 leading-tight">Stop checking lower-priority rules after a match</span>
                    </div>
                  </div>
                </div>

                {summary && <div className="text-xs text-slate-300 bg-emerald-500/5 border border-emerald-500/20 rounded-xl px-4 py-3" data-testid="rule-summary"><strong className="text-emerald-400">In plain words:</strong> {summary}</div>}

                {problems.length > 0 && dirty && (
                  <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 space-y-1" role="status">
                    {problems.map((p, i) => <div key={i} className="text-[11px] text-amber-400 flex gap-2"><AlertTriangle size={12} className="mt-0.5 shrink-0" /> {p}</div>)}
                  </div>
                )}

                <div className="flex flex-wrap items-center gap-3">
                  <button type="button" onClick={save} disabled={saving || !dirty || problems.length > 0}
                    className="flex items-center gap-1.5 text-xs px-5 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white font-semibold shadow-md shadow-emerald-600/20">
                    {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />} {form.id ? 'Save rule' : 'Create rule'}
                  </button>
                  <span className="text-[11px] text-slate-400">Changes apply to the next transaction.</span>
                </div>
              </div>
            </div>

            <RuleTest meta={meta} expression={expression} />
          </>
        )}

        {showFields && (
          <div className={`${panelCls} overflow-hidden`}>
            <div className="px-5 py-3 border-b border-slate-200 dark:border-slate-800 text-sm font-bold flex items-center gap-2"><Sparkles size={15} className="text-sky-500" /> Fields a simple rule can use</div>
            <div className="divide-y divide-slate-100 dark:divide-slate-800/80">
              {fields.map((f) => (
                <div key={f.name} className="grid grid-cols-12 gap-3 items-center px-5 py-2">
                  <button type="button" onClick={() => insertField(f.name)} aria-label={`field ${f.name}`} className="col-span-4 md:col-span-3 font-mono text-[11px] font-bold text-emerald-400 text-left hover:underline">{f.name}</button>
                  <div className="col-span-2 md:col-span-1"><Badge tone={f.type === 'number' ? 'violet' : f.type === 'bool' ? 'amber' : 'slate'}>{f.type}</Badge></div>
                  <div className="col-span-6 md:col-span-8 text-[11px] text-slate-400">{f.description} <span className="font-mono text-slate-500">e.g. {String(f.example)}</span></div>
                </div>
              ))}
            </div>
            <div className="px-5 py-3 text-[11px] text-slate-500 border-t border-slate-200 dark:border-slate-800">Need more fields (bank name, terminal owner, customer risk, history)? Use the <strong>Algo Control</strong> tab.</div>
          </div>
        )}
      </div>
    </div>
  );
};

const autoCode = (name: string) =>
  name.trim().toUpperCase().replace(/[^A-Z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 40);

// ---------------------------------------------------------------- test a condition on a real card
const RuleTest: React.FC<{ meta: any; expression: string }> = ({ meta, expression }) => {
  const cards: any[] = meta?.cards || [];
  const [open, setOpen] = useState(false);
  const [cardId, setCardId] = useState('');
  const [f, setF] = useState<any>({ amount: 25000, tran_code: '10', channel: 'ATM', hour: 2, mcc: '', country: '050' });
  const [res, setRes] = useState<any | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const chosen = cardId || cards[0]?.id || '';

  const run = async () => {
    setBusy(true);
    setErr('');
    try {
      const overrides: Record<string, any> = { ...f };
      Object.keys(overrides).forEach((k) => overrides[k] === '' && delete overrides[k]);
      setRes(await apiFetch('/local-host/rules/test', { method: 'POST', body: JSON.stringify({ expression, card_id: chosen || null, overrides }) }));
    } catch (e: any) {
      setErr(e.message || 'Test failed');
      setRes(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={`${panelCls} overflow-hidden`}>
      <button type="button" onClick={() => setOpen(!open)} className="w-full flex items-center gap-3 px-5 py-3 text-left hover:bg-slate-50 dark:hover:bg-slate-800/30">
        <Play size={15} className="text-violet-400" />
        <h3 className="text-sm font-bold">Test this condition</h3>
        <span className="text-[11px] text-slate-400">Try it on a real card with sample values. Nothing is saved.</span>
        <ChevronDown size={14} className={`ml-auto text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="p-5 border-t border-slate-200 dark:border-slate-800 space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Labeled label="Card" className="col-span-2">
              <select aria-label="rule test card" className={`${inputCls} font-mono`} value={chosen} onChange={(e) => setCardId(e.target.value)}>
                {cards.map((c) => <option key={c.id} value={c.id}>{c.masked_pan} · {c.bank_code}</option>)}
              </select>
            </Labeled>
            <Labeled label="Amount"><input aria-label="rule test amount" type="number" className={`${inputCls} font-mono`} value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></Labeled>
            <Labeled label="Hour (0-23)"><input aria-label="rule test hour" type="number" min={0} max={23} className={`${inputCls} font-mono`} value={f.hour} onChange={(e) => setF({ ...f, hour: e.target.value })} /></Labeled>
            <Labeled label="Channel">
              <select aria-label="rule test channel" className={inputCls} value={f.channel} onChange={(e) => setF({ ...f, channel: e.target.value })}>
                {(meta?.channels || []).map((c: string) => <option key={c}>{c}</option>)}
              </select>
            </Labeled>
            <Labeled label="Transaction code">
              <select aria-label="rule test tran code" className={inputCls} value={f.tran_code} onChange={(e) => setF({ ...f, tran_code: e.target.value })}>
                {(meta?.transaction_codes || []).map((t: any) => <option key={t.code} value={t.code}>{t.code} {t.name}</option>)}
              </select>
            </Labeled>
            <Labeled label="MCC"><input aria-label="rule test mcc" className={`${inputCls} font-mono`} placeholder="auto" value={f.mcc} onChange={(e) => setF({ ...f, mcc: e.target.value })} /></Labeled>
            <Labeled label="Country (DE19)"><input aria-label="rule test country" className={`${inputCls} font-mono`} value={f.country} onChange={(e) => setF({ ...f, country: e.target.value })} /></Labeled>
          </div>
          <div className="flex items-center gap-3">
            <button type="button" onClick={run} disabled={busy || !expression} className="flex items-center gap-1.5 text-xs px-5 py-2 rounded-lg bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white font-semibold">
              {busy ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />} Run test
            </button>
            {err && <span className="text-xs text-rose-500 font-mono">{err}</span>}
          </div>
          {res && (
            <div data-testid="rule-test-result" className={`p-4 rounded-xl border flex items-center gap-3 ${!res.valid ? 'bg-rose-500/10 border-rose-500/30' : res.matched ? 'bg-amber-500/10 border-amber-500/30' : 'bg-emerald-500/10 border-emerald-500/30'}`}>
              {!res.valid ? <AlertTriangle className="text-rose-500" size={20} /> : res.matched ? <XCircle className="text-amber-500" size={20} /> : <CheckCircle2 className="text-emerald-500" size={20} />}
              <div>
                <div className="text-sm font-bold">{!res.valid ? 'The condition has an error' : res.matched ? 'Condition MATCHES: the rule would fire' : 'Condition does not match: transaction continues'}</div>
                <div className="text-[11px] text-slate-400 font-mono">{res.error || `amount=${res.context?.amount} · trancode=${res.context?.trancode} · hour=${res.context?.hour} · mcc=${res.context?.mcc} · bank=${res.context?.institution?.code}`}</div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
'''

HC_PAGE_TSX = r'''import React, { useCallback, useEffect, useState } from 'react';
import {
  Activity,
  Cable,
  CircleDollarSign,
  CreditCard,
  Eye,
  FileCode2,
  Globe2,
  Landmark,
  Loader2,
  Network,
  ScrollText,
  Server,
  ShieldAlert,
  ShieldCheck,
  SlidersHorizontal,
} from 'lucide-react';
import { apiFetch } from '../../api';
import { RulesAndChecksTab } from './RulesAndChecksTab';
import { LocalHostTab } from './LocalHostTab';
import { AlgoControlTab } from './AlgoControlTab';
import { Badge, Toggle, fmtNum, panelCls } from './ui';

// ============================================================================
// RAJON HOST CONTROL CENTER
//   Local Host    - per bank / global transaction policy
//   Algo Control  - Python / SQL risk blocks (approve / decline / block card / block customer)
//   Rules & Checks - built-in check switches + simple rules (replaces menu 7.5 and the old parameter table)
//   CBS / External Host - planned connectors
// ============================================================================

type TabId = 'local' | 'algo' | 'rules' | 'cbs' | 'external';

const TABS: { id: TabId; label: string; icon: React.ReactNode; note?: string }[] = [
  { id: 'local', label: 'Local Host', icon: <Server size={15} /> },
  { id: 'algo', label: 'Algo Control', icon: <FileCode2 size={15} /> },
  { id: 'rules', label: 'Rules & Checks', icon: <ScrollText size={15} /> },
  { id: 'cbs', label: 'CBS', icon: <Landmark size={15} />, note: 'soon' },
  { id: 'external', label: 'External Host', icon: <Globe2 size={15} />, note: 'soon' },
];

const Kpi: React.FC<{ icon: React.ReactNode; label: string; value: React.ReactNode; tone: string; sub?: string }> = ({
  icon,
  label,
  value,
  tone,
  sub,
}) => (
  <div className={`rounded-xl px-4 py-3 border ${tone} flex items-center gap-3 min-w-[150px]`}>
    <div className="opacity-90">{icon}</div>
    <div>
      <div className="text-[10px] uppercase tracking-wider font-bold opacity-80">{label}</div>
      <div className="text-xl font-bold font-mono leading-tight">{value}</div>
      {sub && <div className="text-[10px] opacity-70 truncate max-w-[130px]">{sub}</div>}
    </div>
  </div>
);

export const HostControlCenterPage: React.FC = () => {
  const [tab, setTab] = useState<TabId>('local');
  const [meta, setMeta] = useState<any | null>(null);
  const [overview, setOverview] = useState<any | null>(null);
  const [metaError, setMetaError] = useState('');

  const loadOverview = useCallback(async () => {
    try {
      setOverview(await apiFetch('/local-host/overview'));
    } catch {
      /* the strip is optional */
    }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        setMeta(await apiFetch('/local-host/meta'));
      } catch (e: any) {
        setMetaError(e.message || 'Could not load the host control data. Is the backend updated (patch 4)?');
      }
    })();
    loadOverview();
  }, [loadOverview]);

  return (
    <div className="space-y-5">
      {/* ------------------------------------------------ banner */}
      <div className="relative overflow-hidden rounded-2xl border border-emerald-500/20 bg-gradient-to-br from-emerald-600/15 via-sky-500/10 to-violet-500/10 p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold tracking-tight flex items-center gap-2">
              <SlidersHorizontal className="text-emerald-500" size={24} />
              Host Control Center
            </h1>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 max-w-2xl">
              Decide how your host authorizes transactions: policy per bank and per source system, plus your own Python / SQL risk
              algos that can approve, decline, block a card or block a customer.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Kpi icon={<FileCode2 size={18} />} label="Active algos" value={overview ? overview.algos_active : '—'}
              sub={overview ? `${overview.algos_monitor} in monitor` : undefined} tone="bg-emerald-500/10 text-emerald-500 border-emerald-500/20" />
            <Kpi icon={<Activity size={18} />} label="Matches 24h" value={overview ? fmtNum(overview.matches_24h, 0) : '—'}
              sub={overview?.top_algos?.[0] ? `top: ${overview.top_algos[0].algo_code}` : undefined} tone="bg-sky-500/10 text-sky-500 border-sky-500/20" />
            <Kpi icon={<ShieldAlert size={18} />} label="Blocks 24h" value={overview ? fmtNum(overview.blocks_24h, 0) : '—'}
              sub={overview && overview.errors_24h ? `${overview.errors_24h} algo errors` : undefined} tone="bg-rose-500/10 text-rose-500 border-rose-500/20" />
            <Kpi icon={<Landmark size={18} />} label="Bank overrides" value={overview ? overview.bank_overrides : '—'} tone="bg-violet-500/10 text-violet-400 border-violet-500/20" />
          </div>
        </div>
      </div>

      {/* ------------------------------------------------ tabs */}
      <div className="flex flex-wrap gap-1.5 p-1.5 rounded-2xl bg-slate-100 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 w-fit max-w-full">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            aria-label={`tab ${t.label}`}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold transition-all ${
              tab === t.id
                ? 'bg-white dark:bg-slate-800 text-emerald-500 shadow-sm'
                : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
            }`}
          >
            {t.icon}
            {t.label}
            {t.note && <span className="text-[9px] px-1.5 py-0.5 rounded bg-slate-500/15 text-slate-400 uppercase">{t.note}</span>}
          </button>
        ))}
      </div>

      {metaError && (tab === 'local' || tab === 'algo' || tab === 'rules') && (
        <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-500 text-xs font-mono" role="alert">{metaError}</div>
      )}

      {/* ------------------------------------------------ content */}
      {tab === 'local' &&
        (meta ? <LocalHostTab meta={meta} onChanged={loadOverview} /> : !metaError && <Loading />)}
      {tab === 'algo' &&
        (meta ? <AlgoControlTab meta={meta} onChanged={loadOverview} /> : !metaError && <Loading />)}
      {tab === 'rules' &&
        (meta ? <RulesAndChecksTab meta={meta} onChanged={loadOverview} /> : !metaError && <Loading />)}
      {tab === 'cbs' && <CbsPlaceholder />}
      {tab === 'external' && <ExternalPlaceholder />}
    </div>
  );
};

const Loading: React.FC = () => (
  <div className={`${panelCls} p-12 text-center text-slate-400 text-xs`}>
    <Loader2 className="animate-spin mx-auto mb-2" size={20} /> Loading host control...
  </div>
);

// ---------------------------------------------------------------- placeholders (later phases)
const Roadmap: React.FC<{
  icon: React.ReactNode;
  title: string;
  lead: string;
  items: { icon: React.ReactNode; title: string; text: string }[];
  mode: string;
}> = ({ icon, title, lead, items, mode }) => (
  <div className="space-y-4">
    <div className={`${panelCls} p-8 text-center`}>
      <div className="w-16 h-16 mx-auto rounded-2xl bg-gradient-to-br from-sky-500/20 to-violet-500/20 text-sky-400 flex items-center justify-center mb-4">{icon}</div>
      <div className="flex items-center justify-center gap-2">
        <h3 className="text-base font-bold">{title}</h3>
        <Badge tone="amber">PLANNED</Badge>
      </div>
      <p className="text-xs text-slate-400 mt-2 max-w-xl mx-auto leading-relaxed">{lead}</p>
      <div className="inline-flex items-center gap-3 mt-4 px-4 py-2 rounded-xl bg-slate-100 dark:bg-slate-800">
        <span className="text-[11px] text-slate-500">Current mode</span>
        <Badge tone="emerald">{mode}</Badge>
        <Toggle checked={false} onChange={() => undefined} disabled label={`${title} connector`} />
        <span className="text-[11px] text-slate-500">connector off</span>
      </div>
    </div>
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {items.map((it) => (
        <div key={it.title} className={`${panelCls} p-5 opacity-80`}>
          <div className="w-9 h-9 rounded-xl bg-sky-500/10 text-sky-400 flex items-center justify-center mb-3">{it.icon}</div>
          <div className="text-xs font-bold">{it.title}</div>
          <p className="text-[11px] text-slate-400 mt-1 leading-relaxed">{it.text}</p>
        </div>
      ))}
    </div>
  </div>
);

const CbsPlaceholder: React.FC = () => (
  <Roadmap
    icon={<Landmark size={30} />}
    title="Core Banking System (CBS)"
    lead="Today the host posts to its own simulated ledger. This tab will connect the host to a real CBS so balances, holds and postings come from the bank."
    mode="Standalone ledger"
    items={[
      { icon: <CircleDollarSign size={18} />, title: 'Balance and hold', text: 'Real-time balance inquiry, authorization hold and release against the CBS account.' },
      { icon: <Cable size={18} />, title: 'Posting', text: 'Debit / credit posting, reversal and end-of-day reconciliation with the core.' },
      { icon: <ShieldCheck size={18} />, title: 'Stand-in', text: 'Decision rules when the CBS is slow or down (stand-in limits, advice queue).' },
    ]}
  />
);

const ExternalPlaceholder: React.FC = () => (
  <Roadmap
    icon={<Globe2 size={30} />}
    title="External Hosts: Visa, Mastercard, NPSB"
    lead="Gateways to the card schemes and the national switch. Each one will get its own connection profile, message mapping and routing rules."
    mode="Simulated schemes"
    items={[
      { icon: <CreditCard size={18} />, title: 'Visa / Mastercard', text: 'Network connections, BIN routing, key exchange and scheme specific response mapping.' },
      { icon: <Network size={18} />, title: 'NPSB', text: 'Domestic interbank switch connection, settlement files and dispute handling.' },
      { icon: <Eye size={18} />, title: 'Monitoring', text: 'Connection health, latency and stand-in when an external host is unreachable.' },
    ]}
  />
);
'''

HC_ALGO_TSX = r'''import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  Copy,
  FileCode2,
  FlaskConical,
  History,
  Loader2,
  Play,
  Plus,
  RotateCcw,
  Save,
  Search,
  ShieldOff,
  Sparkles,
  Trash2,
  XCircle,
} from 'lucide-react';
import { apiFetch } from '../../api';
import {
  Badge,
  ChipInput,
  CodeEditor,
  CodeEditorHandle,
  Labeled,
  Modal,
  NumInput,
  RcSelect,
  SegButtons,
  Toggle,
  ago,
  fmtNum,
  fmtTime,
  inputCls,
  panelCls,
  useToast,
} from './ui';

// ============================================================================
// ALGO CONTROL  - Python / SQL risk blocks
// ============================================================================

const PY_STARTER = `# Rajon Algo (Python)
# Click "Fields Reference" to see every field you can use.
# Decide with:  decline('57', 'message')   block_card('why')   block_customer('why')
#               approve('why')             flag('why')         or  return True  (default action)

if tx.channel == 'ATM' and tx.amount > 20000 and (tx.hour >= 23 or tx.hour < 5):
    decline('57', 'High value ATM cash at night')
`;
const SQL_STARTER = `-- Rajon Algo (SQL, read-only)
-- Matches when the query returns a row whose first column is true / non-zero.
-- Use :parameters from "Fields Reference", e.g. :card_id  :tx_amount  :since_15m
SELECT COUNT(*) >= 3
FROM transactions
WHERE card_id = :card_id
  AND authorization_status = 'DECLINED'
  AND transaction_datetime >= :since_15m
`;

const ACTION_TONE: Record<string, string> = {
  DECLINE: 'rose', BLOCK_CARD: 'rose', BLOCK_CUSTOMER: 'rose', APPROVE: 'emerald', FLAG: 'amber',
};

interface AlgoForm {
  id?: string;
  algo_code: string;
  name: string;
  description: string;
  language: 'PYTHON' | 'SQL';
  code: string;
  scope_type: 'GLOBAL' | 'BANK' | 'CARD_PROFILE';
  institution_id: string | null;
  card_profile_id: string | null;
  stage: 'PRE_AUTH' | 'POST_AUTH';
  priority: number;
  mode: 'ENFORCE' | 'MONITOR';
  default_action: string;
  default_response_code: string;
  default_message: string;
  on_error: 'SKIP' | 'DECLINE';
  stop_on_match: boolean;
  tx_codes: string[];
  channels: string[];
  enabled: boolean;
  version?: number;
}

const blankForm = (): AlgoForm => ({
  algo_code: '', name: '', description: '', language: 'PYTHON', code: PY_STARTER, scope_type: 'GLOBAL',
  institution_id: null, card_profile_id: null, stage: 'PRE_AUTH', priority: 100, mode: 'ENFORCE',
  default_action: 'DECLINE', default_response_code: '57', default_message: 'Declined by risk algo',
  on_error: 'SKIP', stop_on_match: true, tx_codes: [], channels: [], enabled: true,
});

const autoCode = (name: string) =>
  name.trim().toUpperCase().replace(/[^A-Z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 40);

const scopeLabel = (a: any) =>
  a.scope_type === 'BANK' ? `BANK ${a.bank_code || ''}` : a.scope_type === 'CARD_PROFILE' ? `PROFILE ${a.card_profile_code || ''}` : 'GLOBAL';

interface Props {
  meta: any;
  onChanged?: () => void;
}

export const AlgoControlTab: React.FC<Props> = ({ meta, onChanged }) => {
  const { show, node: toastNode } = useToast();
  const editorRef = useRef<CodeEditorHandle>(null);

  const [algos, setAlgos] = useState<any[]>([]);
  const [loadingList, setLoadingList] = useState(false);
  const [q, setQ] = useState('');
  const [scopeFilter, setScopeFilter] = useState<'ALL' | 'GLOBAL' | 'BANK' | 'CARD_PROFILE'>('ALL');
  const [selected, setSelected] = useState<string>(''); // algo id, 'new' or ''
  const [form, setForm] = useState<AlgoForm | null>(null);
  const [baseline, setBaseline] = useState('');
  const [saving, setSaving] = useState(false);
  const [validation, setValidation] = useState<{ valid: boolean; errors: string[] } | null>(null);

  const [catalog, setCatalog] = useState<any | null>(null);
  const [templates, setTemplates] = useState<any[]>([]);
  const [schema, setSchema] = useState<any[]>([]);
  const [showFields, setShowFields] = useState(false);
  const [showTemplates, setShowTemplates] = useState(false);
  const [showVersions, setShowVersions] = useState(false);
  const [versions, setVersions] = useState<any[]>([]);
  const [logs, setLogs] = useState<any[]>([]);
  const [showTest, setShowTest] = useState(true);

  const rcs = meta?.response_codes || [];
  const banks: any[] = meta?.banks || [];
  const profiles: any[] = meta?.card_profiles || [];

  // ---------------------------------------------------------------- loaders
  const loadList = useCallback(async () => {
    setLoadingList(true);
    try {
      setAlgos(await apiFetch('/local-host/algos'));
    } catch (e: any) {
      show(e.message || 'Could not load algos', true);
    } finally {
      setLoadingList(false);
    }
  }, [show]);

  const loadLogs = useCallback(
    async (algoId?: string) => {
      try {
        const p = new URLSearchParams({ limit: '30' });
        if (algoId) p.set('algo_id', algoId);
        setLogs(await apiFetch(`/local-host/algos/logs?${p.toString()}`));
      } catch {
        setLogs([]);
      }
    },
    []
  );

  useEffect(() => {
    loadList();
    loadLogs();
  }, [loadList, loadLogs]);

  const openAlgo = async (id: string) => {
    if (dirty && !confirm('Discard your unsaved changes?')) return;
    try {
      const a = await apiFetch(`/local-host/algos/${id}`);
      const f: AlgoForm = {
        id: a.id, algo_code: a.algo_code, name: a.name, description: a.description || '', language: a.language,
        code: a.code, scope_type: a.scope_type, institution_id: a.institution_id, card_profile_id: a.card_profile_id,
        stage: a.stage, priority: a.priority, mode: a.mode, default_action: a.default_action,
        default_response_code: a.default_response_code, default_message: a.default_message, on_error: a.on_error,
        stop_on_match: a.stop_on_match, tx_codes: a.tx_codes || [], channels: a.channels || [], enabled: a.enabled,
        version: a.version,
      };
      setSelected(id);
      setForm(f);
      setBaseline(JSON.stringify(f));
      setValidation(null);
      loadLogs(id);
    } catch (e: any) {
      show(e.message || 'Could not open the algo', true);
    }
  };

  const newAlgo = () => {
    if (dirty && !confirm('Discard your unsaved changes?')) return;
    const f = blankForm();
    setSelected('new');
    setForm(f);
    setBaseline(JSON.stringify(f));
    setValidation(null);
    loadLogs();
  };

  const dirty = useMemo(() => !!form && JSON.stringify(form) !== baseline, [form, baseline]);

  // everything the backend needs, explained in plain words (instead of a raw 422 error)
  const problems = useMemo(() => {
    const out: string[] = [];
    if (!form) return out;
    if (form.algo_code.replace(/[^A-Za-z0-9]/g, '').length < 3) out.push('Enter an Algo code: at least 3 letters or numbers, e.g. NIGHT_ATM_LIMIT');
    if (form.name.trim().length < 2) out.push('Enter a Name for the algo');
    if (form.scope_type === 'BANK' && !form.institution_id) out.push('Choose the bank this algo applies to');
    if (form.scope_type === 'CARD_PROFILE' && !form.card_profile_id) out.push('Choose the card profile this algo applies to');
    if (!form.code.trim()) out.push('The Python / SQL code block is empty');
    return out;
  }, [form]);

  // live validation (debounced)
  useEffect(() => {
    if (!form) return;
    const t = setTimeout(async () => {
      try {
        const r = await apiFetch('/local-host/algos/validate', { method: 'POST', body: JSON.stringify({ language: form.language, code: form.code }) });
        setValidation({ valid: r.valid, errors: r.errors || [] });
      } catch {
        setValidation(null);
      }
    }, 500);
    return () => clearTimeout(t);
  }, [form?.code, form?.language]); // eslint-disable-line react-hooks/exhaustive-deps

  const patch = (p: Partial<AlgoForm>) => setForm((f) => (f ? { ...f, ...p } : f));

  const switchLanguage = (lang: 'PYTHON' | 'SQL') => {
    if (!form || form.language === lang) return;
    const isStarter = form.code.trim() === '' || form.code === PY_STARTER || form.code === SQL_STARTER;
    patch({ language: lang, code: isStarter ? (lang === 'SQL' ? SQL_STARTER : PY_STARTER) : form.code });
  };

  // ---------------------------------------------------------------- save / delete / toggle
  const buildBody = (f: AlgoForm) => ({
    algo_code: f.algo_code, name: f.name, description: f.description || null, language: f.language, code: f.code,
    scope_type: f.scope_type, institution_id: f.scope_type === 'BANK' ? f.institution_id : null,
    card_profile_id: f.scope_type === 'CARD_PROFILE' ? f.card_profile_id : null, stage: f.stage,
    priority: Number(f.priority) || 100, mode: f.mode, default_action: f.default_action,
    default_response_code: f.default_response_code, default_message: f.default_message, on_error: f.on_error,
    stop_on_match: f.stop_on_match, tx_codes: f.tx_codes, channels: f.channels, enabled: f.enabled,
  });

  const save = async () => {
    if (!form) return;
    setSaving(true);
    try {
      const body = buildBody(form);
      const saved = form.id
        ? await apiFetch(`/local-host/algos/${form.id}`, { method: 'PUT', body: JSON.stringify(body) })
        : await apiFetch('/local-host/algos', { method: 'POST', body: JSON.stringify(body) });
      show(`Algo ${saved.algo_code} saved (v${saved.version})`);
      await loadList();
      await openAlgoFresh(saved.id);
      onChanged?.();
    } catch (e: any) {
      show(e.message || 'Save failed', true);
    } finally {
      setSaving(false);
    }
  };

  // open without the dirty prompt (after save / rollback)
  const openAlgoFresh = async (id: string) => {
    const a = await apiFetch(`/local-host/algos/${id}`);
    const f: AlgoForm = {
      id: a.id, algo_code: a.algo_code, name: a.name, description: a.description || '', language: a.language, code: a.code,
      scope_type: a.scope_type, institution_id: a.institution_id, card_profile_id: a.card_profile_id, stage: a.stage,
      priority: a.priority, mode: a.mode, default_action: a.default_action, default_response_code: a.default_response_code,
      default_message: a.default_message, on_error: a.on_error, stop_on_match: a.stop_on_match, tx_codes: a.tx_codes || [],
      channels: a.channels || [], enabled: a.enabled, version: a.version,
    };
    setSelected(id);
    setForm(f);
    setBaseline(JSON.stringify(f));
    loadLogs(id);
  };

  const remove = async () => {
    if (!form?.id || !confirm(`Delete algo ${form.algo_code}? This cannot be undone.`)) return;
    try {
      await apiFetch(`/local-host/algos/${form.id}`, { method: 'DELETE' });
      show(`Algo ${form.algo_code} deleted`);
      setSelected('');
      setForm(null);
      await loadList();
      loadLogs();
      onChanged?.();
    } catch (e: any) {
      show(e.message || 'Delete failed', true);
    }
  };

  const toggleListItem = async (a: any, enabled: boolean) => {
    try {
      await apiFetch(`/local-host/algos/${a.id}/toggle`, { method: 'POST', body: JSON.stringify({ enabled }) });
      setAlgos((list) => list.map((x) => (x.id === a.id ? { ...x, enabled } : x)));
      if (form?.id === a.id) {
        setForm((f) => (f ? { ...f, enabled } : f));
        setBaseline((b) => (b ? JSON.stringify({ ...JSON.parse(b), enabled }) : b));
      }
      show(`${a.algo_code} ${enabled ? 'enabled' : 'disabled'}`);
      onChanged?.();
    } catch (e: any) {
      show(e.message || 'Toggle failed', true);
    }
  };

  // ---------------------------------------------------------------- modals data
  const openFields = async () => {
    setShowFields(true);
    if (!catalog) {
      try {
        const [c, s] = await Promise.all([apiFetch('/local-host/algos/fields'), apiFetch('/local-host/algos/schema')]);
        setCatalog(c);
        setSchema(s);
      } catch (e: any) {
        show(e.message || 'Could not load the field reference', true);
      }
    }
  };

  const openTemplates = async () => {
    setShowTemplates(true);
    if (!templates.length) {
      try {
        setTemplates(await apiFetch('/local-host/algos/templates'));
      } catch (e: any) {
        show(e.message || 'Could not load templates', true);
      }
    }
  };

  const applyTemplate = (t: any) => {
    const base = form || blankForm();
    const next: AlgoForm = {
      ...base,
      algo_code: base.algo_code || String(t.key).toUpperCase(),
      name: base.name || t.title,
      description: t.description,
      language: t.language,
      code: t.code,
      stage: t.stage || 'PRE_AUTH',
      default_action: t.default_action,
      default_response_code: t.default_response_code,
      default_message: t.default_message,
    };
    if (!form) {
      setSelected('new');
      setBaseline(JSON.stringify(blankForm()));
    }
    setForm(next);
    setShowTemplates(false);
    show(`Template "${t.title}" loaded. Review it, then Save.`);
  };

  const openVersions = async () => {
    if (!form?.id) return;
    setShowVersions(true);
    try {
      setVersions(await apiFetch(`/local-host/algos/${form.id}/versions`));
    } catch (e: any) {
      show(e.message || 'Could not load versions', true);
    }
  };

  const rollback = async (v: number) => {
    if (!form?.id || !confirm(`Restore version ${v}? A new version will be created.`)) return;
    try {
      await apiFetch(`/local-host/algos/${form.id}/rollback`, { method: 'POST', body: JSON.stringify({ version: v }) });
      show(`Restored version ${v}`);
      setShowVersions(false);
      await loadList();
      await openAlgoFresh(form.id);
      onChanged?.();
    } catch (e: any) {
      show(e.message || 'Rollback failed', true);
    }
  };

  const insertField = (text: string) => editorRef.current?.insertAtCursor(text);

  const visible = algos.filter((a) => {
    if (scopeFilter !== 'ALL' && a.scope_type !== scopeFilter) return false;
    const t = q.trim().toLowerCase();
    return !t || `${a.algo_code} ${a.name}`.toLowerCase().includes(t);
  });

  // ================================================================ render
  return (
    <div className="grid grid-cols-1 xl:grid-cols-12 gap-5">
      {toastNode}

      {/* ===================== left: algo list */}
      <aside className={`xl:col-span-4 ${panelCls} overflow-hidden self-start`}>
        <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 space-y-3">
          <div className="flex items-center justify-between">
            <div className="text-xs font-bold uppercase tracking-wider text-slate-500">
              Algo blocks <span className="text-emerald-500 font-mono">{algos.length}</span>
            </div>
            <button type="button" onClick={newAlgo}
              className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold shadow-md shadow-emerald-600/20">
              <Plus size={13} /> New algo
            </button>
          </div>
          <div className="relative">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="search code or name" aria-label="search algos" className={`${inputCls} pl-8`} />
          </div>
          <div className="flex flex-wrap gap-1">
            {(['ALL', 'GLOBAL', 'BANK', 'CARD_PROFILE'] as const).map((s) => (
              <button key={s} type="button" onClick={() => setScopeFilter(s)}
                className={`text-[10px] px-2.5 py-1 rounded-lg font-semibold ${scopeFilter === s ? 'bg-emerald-600 text-white' : 'bg-slate-100 dark:bg-slate-800 text-slate-500'}`}>
                {s === 'CARD_PROFILE' ? 'PROFILE' : s}
              </button>
            ))}
          </div>
        </div>
        <div className="max-h-[720px] overflow-y-auto">
          {loadingList && algos.length === 0 && (
            <div className="p-8 text-center text-slate-400 text-xs"><Loader2 className="animate-spin mx-auto mb-2" size={18} /> Loading...</div>
          )}
          {!loadingList && visible.length === 0 && (
            <div className="p-8 text-center text-xs text-slate-400 space-y-3">
              <FileCode2 className="mx-auto text-slate-500" size={28} />
              <div>{algos.length === 0 ? 'No algo yet. Start from a ready-made template or write your own.' : 'No algo matches the filter.'}</div>
              {algos.length === 0 && (
                <button type="button" onClick={openTemplates}
                  className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-emerald-500/40 text-emerald-500 hover:bg-emerald-500/10">
                  <Sparkles size={13} /> Browse templates
                </button>
              )}
            </div>
          )}
          {visible.map((a) => {
            const active = selected === a.id;
            return (
              <div key={a.id} role="button" tabIndex={0} aria-label={`open algo ${a.algo_code}`}
                onClick={() => openAlgo(a.id)} onKeyDown={(e) => e.key === 'Enter' && openAlgo(a.id)}
                className={`px-4 py-3 border-b border-slate-100 dark:border-slate-800/80 cursor-pointer border-l-2 transition-colors ${
                  active ? 'bg-emerald-500/10 border-l-emerald-500' : 'border-l-transparent hover:bg-slate-50 dark:hover:bg-slate-800/50'
                } ${a.enabled ? '' : 'opacity-60'}`}>
                <div className="flex items-start gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="font-mono text-[11px] font-bold text-emerald-500 truncate">{a.algo_code}</span>
                      <Badge tone={a.language === 'SQL' ? 'sky' : 'violet'}>{a.language === 'SQL' ? 'SQL' : 'PY'}</Badge>
                      <Badge tone={a.mode === 'MONITOR' ? 'amber' : 'emerald'}>{a.mode}</Badge>
                    </div>
                    <div className="text-xs mt-0.5 truncate">{a.name}</div>
                    <div className="flex items-center gap-1.5 flex-wrap mt-1.5 text-[10px] text-slate-400">
                      <span className="font-mono">{scopeLabel(a)}</span>·<span>{a.stage === 'PRE_AUTH' ? 'pre-auth' : 'post-auth'}</span>·<span>prio {a.priority}</span>
                    </div>
                    <div className="flex items-center gap-2 mt-1.5">
                      <Badge tone={ACTION_TONE[a.default_action] || 'slate'}>{a.default_action}</Badge>
                      <span className="text-[10px] text-slate-400 font-mono">
                        {fmtNum(a.hit_count, 0)} hits / {fmtNum(a.eval_count, 0)} runs
                      </span>
                      {a.error_count > 0 && <Badge tone="rose">{a.error_count} err</Badge>}
                    </div>
                  </div>
                  <div onClick={(e) => e.stopPropagation()}>
                    <Toggle checked={a.enabled} label={`enable ${a.algo_code}`} onChange={(v) => toggleListItem(a, v)} />
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </aside>

      {/* ===================== right: editor */}
      <div className="xl:col-span-8 space-y-4 min-w-0">
        {!form ? (
          <div className={`${panelCls} p-14 text-center`}>
            <div className="w-16 h-16 mx-auto rounded-2xl bg-gradient-to-br from-emerald-500/20 to-sky-500/20 text-emerald-500 flex items-center justify-center mb-4">
              <FileCode2 size={30} />
            </div>
            <h3 className="text-base font-bold">Write your own transaction control</h3>
            <p className="text-xs text-slate-400 mt-2 max-w-lg mx-auto leading-relaxed">
              An algo is a small Python or SQL block that runs for every transaction of a bank or a card profile. It can
              approve, decline, block the card or block the customer. Open the Fields Reference to see every value you can use
              (amount, time, bank, terminal owner, authorization profile ...).
            </p>
            <div className="flex justify-center gap-3 mt-5">
              <button type="button" onClick={newAlgo} className="flex items-center gap-1.5 text-xs px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold">
                <Plus size={14} /> New algo
              </button>
              <button type="button" onClick={openTemplates} className="flex items-center gap-1.5 text-xs px-4 py-2 rounded-lg border border-slate-300 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800">
                <Sparkles size={14} /> Templates
              </button>
              <button type="button" onClick={openFields} className="flex items-center gap-1.5 text-xs px-4 py-2 rounded-lg border border-slate-300 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800">
                <BookOpen size={14} /> Fields Reference
              </button>
            </div>
          </div>
        ) : (
          <>
            {/* ---- header + settings */}
            <div className={`${panelCls} overflow-hidden`}>
              <div className="flex flex-wrap items-center gap-3 px-5 py-3.5 border-b border-slate-200 dark:border-slate-800 bg-gradient-to-r from-slate-50 to-transparent dark:from-slate-800/40">
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-sm font-bold">{form.id ? form.algo_code : 'New algo'}</h2>
                    {form.version && <Badge tone="slate">v{form.version}</Badge>}
                    {dirty && <Badge tone="amber">unsaved</Badge>}
                  </div>
                  <p className="text-[11px] text-slate-400">Runs {form.stage === 'PRE_AUTH' ? 'before PIN / HSM checks' : 'after balance and limit checks'} · lower priority number runs first</p>
                </div>
                <div className="ml-auto flex flex-wrap items-center gap-2">
                  <button type="button" onClick={openTemplates} className="flex items-center gap-1.5 text-[11px] px-3 py-1.5 rounded-lg border border-slate-300 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800">
                    <Sparkles size={13} /> Templates
                  </button>
                  <button type="button" onClick={openFields} className="flex items-center gap-1.5 text-[11px] px-3 py-1.5 rounded-lg bg-sky-600/10 text-sky-500 hover:bg-sky-600/20 font-semibold">
                    <BookOpen size={13} /> Fields Reference
                  </button>
                  {form.id && (
                    <button type="button" onClick={openVersions} className="flex items-center gap-1.5 text-[11px] px-3 py-1.5 rounded-lg border border-slate-300 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800">
                      <History size={13} /> History
                    </button>
                  )}
                  {form.id && (
                    <button type="button" onClick={remove} aria-label="delete algo" className="p-2 rounded-lg text-rose-500 hover:bg-rose-500/10">
                      <Trash2 size={14} />
                    </button>
                  )}
                </div>
              </div>

              <div className="p-5 space-y-5">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <Labeled label="Algo code *" hint="Letters, numbers, _ and -. Saved in upper case">
                    <input aria-label="algo code" value={form.algo_code} onChange={(e) => patch({ algo_code: e.target.value })} className={`${inputCls} font-mono`} placeholder="NIGHT_ATM_LIMIT" />
                  </Labeled>
                  <Labeled label="Name *" className="md:col-span-2">
                    <input aria-label="algo name" value={form.name} onChange={(e) => {
                      const v = e.target.value;
                      patch({ name: v, ...(!form.id && (form.algo_code === '' || form.algo_code === autoCode(form.name)) ? { algo_code: autoCode(v) } : {}) });
                    }} className={inputCls} placeholder="Block night time high value ATM cash" />
                  </Labeled>
                  <Labeled label="Description" className="md:col-span-3">
                    <input value={form.description} onChange={(e) => patch({ description: e.target.value })} className={inputCls} placeholder="What this algo protects against" />
                  </Labeled>
                </div>

                {/* scope */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 p-4 rounded-xl bg-slate-50 dark:bg-slate-950/40 border border-slate-200 dark:border-slate-800">
                  <div className="md:col-span-3 flex flex-wrap items-center gap-4">
                    <div>
                      <div className="text-[11px] text-slate-400 font-medium mb-1.5">Applies to</div>
                      <SegButtons
                        value={form.scope_type}
                        onChange={(v) => patch({ scope_type: v, institution_id: v === 'BANK' ? form.institution_id : null, card_profile_id: v === 'CARD_PROFILE' ? form.card_profile_id : null })}
                        options={[
                          { value: 'GLOBAL', label: 'Whole host' },
                          { value: 'BANK', label: 'One bank', tone: 'sky' },
                          { value: 'CARD_PROFILE', label: 'Card profile', tone: 'amber' },
                        ]}
                      />
                    </div>
                    {form.scope_type === 'BANK' && (
                      <Labeled label="Bank" className="w-64">
                        <select aria-label="algo bank" className={inputCls} value={form.institution_id || ''} onChange={(e) => patch({ institution_id: e.target.value || null })}>
                          <option value="">select a bank</option>
                          {banks.map((b) => <option key={b.id} value={b.id}>{b.code} - {b.name}</option>)}
                        </select>
                      </Labeled>
                    )}
                    {form.scope_type === 'CARD_PROFILE' && (
                      <Labeled label="Card profile" className="w-72">
                        <select aria-label="algo card profile" className={inputCls} value={form.card_profile_id || ''} onChange={(e) => patch({ card_profile_id: e.target.value || null })}>
                          <option value="">select a profile</option>
                          {profiles.map((p) => <option key={p.id} value={p.id}>{p.code} - {p.name}</option>)}
                        </select>
                      </Labeled>
                    )}
                  </div>
                  <p className="md:col-span-3 text-[11px] text-slate-400 leading-relaxed -mt-1" data-testid="scope-help">
                    {form.scope_type === 'GLOBAL' && 'Runs for every card of every bank.'}
                    {form.scope_type === 'BANK' && 'Runs for every card issued by the bank you choose.'}
                    {form.scope_type === 'CARD_PROFILE' && 'This is where you tag an algo to a card profile: choose the profile above. It then runs for every card that belongs to that profile (the profile of a card is set from its BIN / card profile assignment).'}
                  </p>
                  <Labeled label="Stage">
                    <select aria-label="algo stage" className={inputCls} value={form.stage} onChange={(e) => patch({ stage: e.target.value as any })}>
                      <option value="PRE_AUTH">PRE_AUTH - before PIN / HSM</option>
                      <option value="POST_AUTH">POST_AUTH - after balance and limits</option>
                    </select>
                  </Labeled>
                  <Labeled label="Priority" hint="1 runs first">
                    <NumInput value={form.priority} ariaLabel="algo priority" onChange={(v) => patch({ priority: v || 100 })} placeholder="100" />
                  </Labeled>
                  <div className="flex items-end gap-3 pb-1">
                    <Toggle checked={form.enabled} label="algo enabled" onChange={(v) => patch({ enabled: v })} />
                    <span className="text-xs font-semibold">{form.enabled ? 'Enabled' : 'Disabled'}</span>
                  </div>
                </div>

                {/* behaviour */}
                <div className="grid grid-cols-1 md:grid-cols-12 gap-4">
                  <div className="md:col-span-4">
                    <div className="text-[11px] text-slate-400 font-medium mb-1.5">Mode</div>
                    <SegButtons
                      value={form.mode}
                      onChange={(v) => patch({ mode: v })}
                      options={[
                        { value: 'ENFORCE', label: 'Enforce', tone: 'emerald' },
                        { value: 'MONITOR', label: 'Monitor only', tone: 'amber' },
                      ]}
                    />
                    <p className="text-[10px] text-slate-500 mt-1.5 leading-snug">
                      {form.mode === 'MONITOR' ? 'Shadow mode: logs what it WOULD do, never declines or blocks.' : 'Live: the action is applied to real transactions.'}
                    </p>
                  </div>
                  <Labeled label="When the condition is met" className="md:col-span-3">
                    <select aria-label="default action" className={inputCls} value={form.default_action} onChange={(e) => patch({ default_action: e.target.value })}>
                      {(meta?.actions || ['DECLINE', 'APPROVE', 'BLOCK_CARD', 'BLOCK_CUSTOMER', 'FLAG']).map((a: string) => <option key={a}>{a}</option>)}
                    </select>
                  </Labeled>
                  <Labeled label="Response code" className="md:col-span-5">
                    <RcSelect value={form.default_response_code} codes={rcs} ariaLabel="default response code" onChange={(v) => patch({ default_response_code: v })} />
                  </Labeled>
                  <Labeled label="Message (shown in the transaction checks)" className="md:col-span-7">
                    <input aria-label="default message" value={form.default_message} onChange={(e) => patch({ default_message: e.target.value })} className={inputCls} />
                  </Labeled>
                  <Labeled label="If the algo has an error" className="md:col-span-3">
                    <select aria-label="on error" className={inputCls} value={form.on_error} onChange={(e) => patch({ on_error: e.target.value as any })}>
                      <option value="SKIP">Ignore it (fail-open)</option>
                      <option value="DECLINE">Decline (fail-closed)</option>
                    </select>
                  </Labeled>
                  <div className="md:col-span-2 flex items-end gap-2 pb-1">
                    <Toggle checked={form.stop_on_match} label="stop on match" onChange={(v) => patch({ stop_on_match: v })} />
                    <span className="text-[11px] text-slate-400 leading-tight">Stop other algos on approve</span>
                  </div>
                  <Labeled label="Only for transaction codes (empty = all)" className="md:col-span-6">
                    <ChipInput values={form.tx_codes} onChange={(v) => patch({ tx_codes: v })}
                      suggestions={(meta?.transaction_codes || []).map((t: any) => ({ value: t.code, label: t.name }))} />
                  </Labeled>
                  <div className="md:col-span-6">
                    <div className="text-[11px] text-slate-400 font-medium mb-1.5">Only for channels (none = all)</div>
                    <div className="flex flex-wrap gap-1.5">
                      {(meta?.channels || []).map((c: string) => {
                        const on = form.channels.includes(c);
                        return (
                          <button key={c} type="button" aria-pressed={on} aria-label={`algo channel ${c}`}
                            onClick={() => patch({ channels: on ? form.channels.filter((x) => x !== c) : [...form.channels, c] })}
                            className={`text-[11px] font-mono px-2.5 py-1 rounded-md border ${on ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-500' : 'border-slate-300 dark:border-slate-700 text-slate-400'}`}>
                            {c}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* ---- code */}
            <div className={`${panelCls} overflow-hidden`}>
              <div className="flex flex-wrap items-center gap-3 px-5 py-3 border-b border-slate-200 dark:border-slate-800">
                <FileCode2 size={16} className="text-emerald-500" />
                <h3 className="text-sm font-bold">Algo code</h3>
                <SegButtons value={form.language} onChange={switchLanguage}
                  options={[{ value: 'PYTHON', label: 'Python', tone: 'sky' }, { value: 'SQL', label: 'SQL', tone: 'sky' }]} />
                <div className="ml-auto flex items-center gap-2">
                  {validation &&
                    (validation.valid ? (
                      <Badge tone="emerald"><CheckCircle2 size={11} /> valid</Badge>
                    ) : (
                      <Badge tone="rose"><XCircle size={11} /> {validation.errors.length} problem(s)</Badge>
                    ))}
                </div>
              </div>
              <div className="p-5 space-y-3">
                <CodeEditor ref={editorRef} value={form.code} onChange={(v) => patch({ code: v })} language={form.language} height={340} />
                {validation && !validation.valid && (
                  <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 space-y-1" role="alert">
                    {validation.errors.map((e, i) => (
                      <div key={i} className="text-[11px] font-mono text-rose-400 flex gap-2"><AlertTriangle size={12} className="mt-0.5 shrink-0" /> {e}</div>
                    ))}
                  </div>
                )}
                <div className="text-[11px] text-slate-400 leading-relaxed">
                  {form.language === 'PYTHON' ? (
                    <>
                      Use <code className="text-emerald-400">tx.amount</code>, <code className="text-emerald-400">card.status</code>,{' '}
                      <code className="text-emerald-400">customer.risk</code>, <code className="text-emerald-400">bank.code</code> ... Decide with{' '}
                      <code className="text-rose-300">decline()</code> <code className="text-rose-300">block_card()</code>{' '}
                      <code className="text-rose-300">block_customer()</code> <code className="text-rose-300">approve()</code>{' '}
                      <code className="text-rose-300">flag()</code>, or <code className="text-sky-300">return True</code> for the default action above. No imports, no while loops.
                    </>
                  ) : (
                    <>
                      One read-only SELECT. A first column that is true / non-zero means <strong>matched</strong>. Use{' '}
                      <code className="text-emerald-400">:card_id</code> <code className="text-emerald-400">:tx_amount</code>{' '}
                      <code className="text-emerald-400">:since_15m</code> ... or return the columns{' '}
                      <code className="text-rose-300">action, response_code, message</code> to choose the outcome from SQL.
                    </>
                  )}
                </div>
                {problems.length > 0 && (
                  <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 space-y-1" role="status" data-testid="algo-problems">
                    <div className="text-[11px] font-bold text-amber-400">To save this algo:</div>
                    {problems.map((p, i) => (
                      <div key={i} className="text-[11px] text-amber-400 flex gap-2"><AlertTriangle size={12} className="mt-0.5 shrink-0" /> {p}</div>
                    ))}
                  </div>
                )}
                <div className="flex flex-wrap items-center gap-3 pt-2">
                  <button type="button" onClick={save} disabled={saving || !dirty || problems.length > 0 || !!(validation && !validation.valid)}
                    className="flex items-center gap-1.5 text-xs px-5 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white font-semibold shadow-md shadow-emerald-600/20">
                    {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />} {form.id ? 'Save new version' : 'Create algo'}
                  </button>
                  {dirty && form.id && (
                    <button type="button" onClick={() => openAlgoFresh(form.id!)} className="text-xs px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-700">
                      <RotateCcw size={12} className="inline mr-1" /> Discard changes
                    </button>
                  )}
                  <span className="text-[11px] text-slate-400">Every save keeps a version you can restore.</span>
                </div>
              </div>
            </div>

            {/* ---- test */}
            <TestPanel meta={meta} form={form} open={showTest} onToggle={() => setShowTest(!showTest)} />
          </>
        )}

        {/* ---- logs */}
        <div className={`${panelCls} overflow-hidden`}>
          <div className="flex items-center gap-3 px-5 py-3 border-b border-slate-200 dark:border-slate-800">
            <History size={16} className="text-emerald-500" />
            <h3 className="text-sm font-bold">Execution log</h3>
            <span className="text-[11px] text-slate-400">{form?.id ? `for ${form.algo_code}` : 'all algos'} · matches and errors only</span>
            <button type="button" onClick={() => loadLogs(form?.id)} className="ml-auto text-[11px] px-3 py-1.5 rounded-lg border border-slate-300 dark:border-slate-700">Refresh</button>
          </div>
          {logs.length === 0 ? (
            <div className="p-8 text-center text-xs text-slate-400">Nothing logged yet. Entries appear when an algo matches or fails during a real transaction.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-[11px]">
                <thead>
                  <tr className="text-left text-[10px] uppercase tracking-wider text-slate-400 bg-slate-50 dark:bg-slate-950/50">
                    <th className="px-4 py-2">Time</th><th className="px-2 py-2">Algo</th><th className="px-2 py-2">Card</th>
                    <th className="px-2 py-2">Action</th><th className="px-2 py-2">RC</th><th className="px-2 py-2">Result</th><th className="px-2 py-2 text-right">ms</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map((l) => (
                    <tr key={l.id} className="border-t border-slate-100 dark:border-slate-800/80">
                      <td className="px-4 py-2 font-mono text-slate-400 whitespace-nowrap" title={fmtTime(l.created_at)}>{ago(l.created_at)}</td>
                      <td className="px-2 py-2 font-mono font-bold text-emerald-500">{l.algo_code}</td>
                      <td className="px-2 py-2 font-mono text-slate-400">{l.masked_pan || '—'}</td>
                      <td className="px-2 py-2">
                        {l.error ? <Badge tone="rose">ERROR</Badge> : <Badge tone={ACTION_TONE[l.action] || 'slate'}>{l.action}</Badge>}{' '}
                        {l.mode === 'MONITOR' ? <Badge tone="amber">MONITOR</Badge> : l.action_applied ? <Badge tone="emerald">applied</Badge> : null}
                      </td>
                      <td className="px-2 py-2 font-mono">{l.response_code || '—'}</td>
                      <td className="px-2 py-2 text-slate-400 max-w-[320px] truncate" title={l.error || l.message}>{l.error || l.message}</td>
                      <td className="px-2 py-2 text-right font-mono text-slate-400">{l.duration_ms}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* ===================== modals */}
      {showFields && (
        <FieldsModal catalog={catalog} schema={schema} language={form?.language || 'PYTHON'} hasEditor={!!form}
          onInsert={insertField} onClose={() => setShowFields(false)} onCopied={() => show('Copied')} />
      )}
      {showTemplates && (
        <Modal title={<span className="flex items-center gap-2"><Sparkles size={15} className="text-emerald-500" /> Algo templates</span>} onClose={() => setShowTemplates(false)} size="xl">
          {templates.length === 0 ? (
            <div className="p-8 text-center text-xs text-slate-400"><Loader2 className="animate-spin mx-auto mb-2" size={18} /> Loading...</div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {templates.map((t) => (
                <div key={t.key} className="rounded-xl border border-slate-200 dark:border-slate-800 p-4 flex flex-col gap-2">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs font-bold">{t.title}</span>
                    <Badge tone={t.language === 'SQL' ? 'sky' : 'violet'}>{t.language}</Badge>
                    <Badge tone={ACTION_TONE[t.default_action] || 'slate'}>{t.default_action}</Badge>
                    {t.stage === 'POST_AUTH' && <Badge tone="amber">POST_AUTH</Badge>}
                  </div>
                  <p className="text-[11px] text-slate-400">{t.description}</p>
                  <pre className="text-[10px] font-mono bg-slate-950 text-slate-300 rounded-lg p-2.5 overflow-x-auto max-h-28">{t.code}</pre>
                  <button type="button" onClick={() => applyTemplate(t)} aria-label={`use template ${t.key}`}
                    className="self-start flex items-center gap-1.5 text-[11px] px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold">
                    Use this template
                  </button>
                </div>
              ))}
            </div>
          )}
        </Modal>
      )}
      {showVersions && (
        <Modal title={`Version history - ${form?.algo_code}`} onClose={() => setShowVersions(false)} size="lg">
          <div className="space-y-3">
            {versions.map((v) => (
              <div key={v.version} className="rounded-xl border border-slate-200 dark:border-slate-800 p-3">
                <div className="flex items-center gap-2 flex-wrap">
                  <Badge tone={v.version === form?.version ? 'emerald' : 'slate'}>v{v.version}{v.version === form?.version ? ' current' : ''}</Badge>
                  <span className="text-[11px] text-slate-400">{v.change_note} · {v.changed_by} · {fmtTime(v.created_at)}</span>
                  {v.version !== form?.version && (
                    <button type="button" onClick={() => rollback(v.version)} aria-label={`restore v${v.version}`}
                      className="ml-auto text-[11px] px-3 py-1 rounded-lg bg-amber-500/10 text-amber-500 hover:bg-amber-500/20">
                      Restore
                    </button>
                  )}
                </div>
                <pre className="mt-2 text-[10px] font-mono bg-slate-950 text-slate-300 rounded-lg p-2.5 overflow-x-auto max-h-40">{v.code}</pre>
              </div>
            ))}
          </div>
        </Modal>
      )}
    </div>
  );
};

// ============================================================================
// Fields reference modal
// ============================================================================
const FieldsModal: React.FC<{
  catalog: any | null;
  schema: any[];
  language: string;
  hasEditor: boolean;
  onInsert: (text: string) => void;
  onClose: () => void;
  onCopied: () => void;
}> = ({ catalog, schema, language, hasEditor, onInsert, onClose, onCopied }) => {
  const [tab, setTab] = useState<'fields' | 'actions' | 'sql' | 'notes'>('fields');
  const [term, setTerm] = useState('');
  const [group, setGroup] = useState('ALL');
  const isSql = language === 'SQL';

  const copy = (text: string) => {
    try {
      navigator.clipboard?.writeText(text);
      onCopied();
    } catch {
      /* ignore */
    }
  };

  const groups: any[] = catalog?.groups || [];
  const t = term.trim().toLowerCase();
  const filtered = groups
    .filter((g) => group === 'ALL' || g.group === group)
    .map((g) => ({
      ...g,
      fields: g.fields.filter((f: any) => !t || `${f.python} ${f.sql} ${f.description}`.toLowerCase().includes(t)),
    }))
    .filter((g) => g.fields.length);

  return (
    <Modal title={<span className="flex items-center gap-2"><BookOpen size={15} className="text-sky-500" /> Fields Reference</span>} onClose={onClose} size="xl">
      {!catalog ? (
        <div className="p-10 text-center text-xs text-slate-400"><Loader2 className="animate-spin mx-auto mb-2" size={18} /> Loading...</div>
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            {([['fields', 'Fields'], ['actions', 'Actions & helpers'], ['sql', 'SQL tables'], ['notes', 'Notes']] as const).map(([id, label]) => (
              <button key={id} type="button" onClick={() => setTab(id)}
                className={`text-xs px-3.5 py-1.5 rounded-lg font-semibold ${tab === id ? 'bg-sky-600 text-white' : 'bg-slate-100 dark:bg-slate-800 text-slate-500'}`}>
                {label}
              </button>
            ))}
            <span className="ml-auto text-[11px] text-slate-400">
              {hasEditor ? <>Click a name to insert it into your {isSql ? 'SQL' : 'Python'} code</> : 'Open an algo to insert fields'}
            </span>
          </div>

          {tab === 'fields' && (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <div className="relative flex-1 min-w-[220px]">
                  <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
                  <input autoFocus value={term} onChange={(e) => setTerm(e.target.value)} placeholder="search: amount, hour, bank, terminal owner, balance ..." aria-label="search fields" className={`${inputCls} pl-8`} />
                </div>
                <select aria-label="field group" value={group} onChange={(e) => setGroup(e.target.value)} className={`${inputCls} !w-auto`}>
                  <option value="ALL">All groups</option>
                  {groups.map((g) => <option key={g.group} value={g.group}>{g.title}</option>)}
                </select>
              </div>
              {filtered.length === 0 && <div className="text-xs text-slate-400 p-6 text-center">No field matches "{term}".</div>}
              {filtered.map((g) => (
                <div key={g.group} className="rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden">
                  <div className="px-4 py-2 bg-slate-50 dark:bg-slate-950/50 flex items-center gap-2">
                    <span className="text-xs font-bold">{g.title}</span>
                    <span className="text-[10px] text-slate-400 font-mono">{g.hint}</span>
                  </div>
                  <div className="divide-y divide-slate-100 dark:divide-slate-800/80">
                    {g.fields.map((f: any) => (
                      <div key={f.python} className="grid grid-cols-12 gap-3 items-center px-4 py-2">
                        <div className="col-span-12 md:col-span-3">
                          <button type="button" disabled={!hasEditor || isSql} onClick={() => onInsert(f.python)} aria-label={`insert ${f.python}`}
                            className="font-mono text-[11px] font-bold text-emerald-400 hover:underline disabled:no-underline disabled:opacity-60 text-left">
                            {f.python}
                          </button>
                        </div>
                        <div className="col-span-12 md:col-span-3">
                          <button type="button" disabled={!hasEditor || !isSql} onClick={() => onInsert(f.sql)} aria-label={`insert ${f.sql}`}
                            className="font-mono text-[11px] text-sky-400 hover:underline disabled:no-underline disabled:opacity-60 text-left">
                            {f.sql}
                          </button>
                        </div>
                        <div className="col-span-3 md:col-span-1"><Badge tone={f.type === 'number' ? 'violet' : f.type === 'bool' ? 'amber' : 'slate'}>{f.type}</Badge></div>
                        <div className="col-span-9 md:col-span-4 text-[11px] text-slate-400 leading-snug">
                          {f.description} <span className="font-mono text-slate-500">e.g. {String(f.example)}</span>
                        </div>
                        <div className="hidden md:flex md:col-span-1 justify-end">
                          <button type="button" aria-label={`copy ${f.python}`} onClick={() => copy(isSql ? f.sql : f.python)} className="text-slate-500 hover:text-slate-300"><Copy size={12} /></button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </>
          )}

          {tab === 'actions' && (
            <div className="space-y-4">
              <div className="rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden">
                <div className="px-4 py-2 bg-slate-50 dark:bg-slate-950/50 text-xs font-bold">Decisions</div>
                {catalog.actions.map((a: any) => (
                  <div key={a.name} className="px-4 py-2 border-t border-slate-100 dark:border-slate-800/80 flex flex-wrap gap-3 items-start">
                    <button type="button" disabled={!hasEditor} onClick={() => onInsert(a.name.replace(/\(.*\)/, '()'))} className="font-mono text-[11px] font-bold text-rose-300 hover:underline text-left">{a.name}</button>
                    <span className="text-[11px] text-slate-400 flex-1 min-w-[240px]">{a.description}</span>
                  </div>
                ))}
              </div>
              <div className="rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden">
                <div className="px-4 py-2 bg-slate-50 dark:bg-slate-950/50 text-xs font-bold">History and helpers (Python)</div>
                {catalog.history.map((h: any) => (
                  <div key={h.name} className="px-4 py-2 border-t border-slate-100 dark:border-slate-800/80">
                    <div className="font-mono text-[11px] text-emerald-300 break-all">{h.name}</div>
                    <div className="text-[11px] text-slate-400 mt-0.5">{h.description}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {tab === 'sql' && (
            <div className="space-y-4">
              <div className="rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden">
                <div className="px-4 py-2 bg-slate-50 dark:bg-slate-950/50 text-xs font-bold">Time parameters</div>
                {catalog.time_params.map((p: any) => (
                  <div key={p.sql} className="px-4 py-2 border-t border-slate-100 dark:border-slate-800/80 flex gap-3">
                    <button type="button" disabled={!hasEditor} onClick={() => onInsert(p.sql)} className="font-mono text-[11px] font-bold text-sky-400 hover:underline w-28 text-left">{p.sql}</button>
                    <span className="text-[11px] text-slate-400">{p.description}</span>
                  </div>
                ))}
              </div>
              {schema.map((t) => (
                <div key={t.table} className="rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden">
                  <div className="px-4 py-2 bg-slate-50 dark:bg-slate-950/50 text-xs font-bold font-mono">{t.table}</div>
                  <div className="p-3 flex flex-wrap gap-1.5">
                    {t.columns.map((c: any) => (
                      <button key={c.name} type="button" disabled={!hasEditor} onClick={() => onInsert(c.name)} title={c.type}
                        className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-500/10 text-slate-300 hover:bg-slate-500/20">
                        {c.name}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}

          {tab === 'notes' && (
            <ul className="space-y-2 text-xs text-slate-300 list-disc pl-5">
              {catalog.notes.map((n: string, i: number) => <li key={i}>{n}</li>)}
            </ul>
          )}
        </div>
      )}
    </Modal>
  );
};

// ============================================================================
// Test panel (dry run on a real card, nothing is saved or blocked)
// ============================================================================
const TestPanel: React.FC<{ meta: any; form: AlgoForm; open: boolean; onToggle: () => void }> = ({ meta, form, open, onToggle }) => {
  const cards: any[] = meta?.cards || [];
  const [cardId, setCardId] = useState('');
  const [f, setF] = useState<any>({ amount: 25000, channel: 'ATM', tran_code: '10', hour: 2, mcc: '', country: '050', terminal_id: '', acquirer_code: '' });
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<any | null>(null);
  const [err, setErr] = useState('');
  const [showCtx, setShowCtx] = useState(false);
  const chosen = cardId || cards[0]?.id || '';

  const run = async () => {
    setBusy(true);
    setErr('');
    try {
      const overrides: Record<string, any> = { ...f };
      Object.keys(overrides).forEach((k) => overrides[k] === '' && delete overrides[k]);
      const draft = {
        algo_code: form.algo_code || 'DRAFT', name: form.name, language: form.language, code: form.code, mode: form.mode,
        default_action: form.default_action, default_response_code: form.default_response_code,
        default_message: form.default_message, on_error: form.on_error, stop_on_match: form.stop_on_match, stage: form.stage,
      };
      const r = await apiFetch('/local-host/algos/test', { method: 'POST', body: JSON.stringify({ draft, card_id: chosen || null, overrides }) });
      setRes(r);
      if (!r.ok) setErr((r.errors || []).join('; '));
    } catch (e: any) {
      setErr(e.message || 'Test failed');
      setRes(null);
    } finally {
      setBusy(false);
    }
  };

  const result = res?.result;
  return (
    <div className={`${panelCls} overflow-hidden`}>
      <button type="button" onClick={onToggle} className="w-full flex items-center gap-3 px-5 py-3 text-left border-b border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/30">
        <FlaskConical size={16} className="text-violet-400" />
        <h3 className="text-sm font-bold">Test run</h3>
        <span className="text-[11px] text-slate-400">Dry run on a real card with sample values. Nothing is saved, declined or blocked.</span>
        <ChevronDown size={14} className={`ml-auto text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="p-5 space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Labeled label="Card" className="col-span-2">
              <select aria-label="test card" className={`${inputCls} font-mono`} value={chosen} onChange={(e) => setCardId(e.target.value)}>
                {cards.map((c) => <option key={c.id} value={c.id}>{c.masked_pan} · {c.bank_code} · {c.holder}</option>)}
              </select>
            </Labeled>
            <Labeled label="Amount"><input aria-label="test amount" type="number" className={`${inputCls} font-mono`} value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></Labeled>
            <Labeled label="Hour (0-23)"><input aria-label="test hour" type="number" min={0} max={23} className={`${inputCls} font-mono`} value={f.hour} onChange={(e) => setF({ ...f, hour: e.target.value })} /></Labeled>
            <Labeled label="Channel">
              <select aria-label="test channel" className={inputCls} value={f.channel} onChange={(e) => setF({ ...f, channel: e.target.value })}>
                {(meta?.channels || []).map((c: string) => <option key={c}>{c}</option>)}
              </select>
            </Labeled>
            <Labeled label="Transaction code">
              <select aria-label="test tran code" className={inputCls} value={f.tran_code} onChange={(e) => setF({ ...f, tran_code: e.target.value })}>
                {(meta?.transaction_codes || []).map((t: any) => <option key={t.code} value={t.code}>{t.code} {t.name}</option>)}
              </select>
            </Labeled>
            <Labeled label="MCC"><input aria-label="test mcc" className={`${inputCls} font-mono`} placeholder="auto" value={f.mcc} onChange={(e) => setF({ ...f, mcc: e.target.value })} /></Labeled>
            <Labeled label="Country (DE19)"><input aria-label="test country" className={`${inputCls} font-mono`} value={f.country} onChange={(e) => setF({ ...f, country: e.target.value })} /></Labeled>
            <Labeled label="Terminal owner (bank)">
              <select aria-label="test terminal owner" className={inputCls} value={f.acquirer_code} onChange={(e) => setF({ ...f, acquirer_code: e.target.value })}>
                <option value="">card's own bank (ON_US)</option>
                {(meta?.banks || []).map((b: any) => <option key={b.id} value={b.code}>{b.code}</option>)}
              </select>
            </Labeled>
            <Labeled label="Terminal id"><input aria-label="test terminal" className={`${inputCls} font-mono`} placeholder="auto" value={f.terminal_id} onChange={(e) => setF({ ...f, terminal_id: e.target.value })} /></Labeled>
          </div>
          <div className="flex items-center gap-3">
            <button type="button" onClick={run} disabled={busy || !form.code.trim()}
              className="flex items-center gap-1.5 text-xs px-5 py-2 rounded-lg bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white font-semibold">
              {busy ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />} Run test
            </button>
            {err && <span className="text-xs text-rose-500 font-mono">{err}</span>}
          </div>

          {result && (
            <div className="space-y-3" data-testid="test-result">
              <div className={`flex flex-wrap items-center gap-3 p-4 rounded-xl border ${
                result.error ? 'bg-rose-500/10 border-rose-500/30' : result.matched ? 'bg-amber-500/10 border-amber-500/30' : 'bg-emerald-500/10 border-emerald-500/30'}`}>
                {result.error ? <AlertTriangle className="text-rose-500" size={22} /> : result.matched ? <ShieldOff className="text-amber-500" size={22} /> : <CheckCircle2 className="text-emerald-500" size={22} />}
                <div className="min-w-0">
                  <div className="text-sm font-bold">
                    {result.error ? 'The algo has an error' : result.matched ? <>Matched: <span className="text-amber-500">{result.action}</span>{result.response_code ? ` (RC ${result.response_code})` : ''}</> : 'Condition not met - transaction would continue'}
                  </div>
                  <div className="text-[11px] text-slate-400 break-words">
                    {result.error || result.message || ''} · {result.duration_ms} ms · mode {result.mode}
                    {result.matched && result.mode === 'MONITOR' ? ' (monitor: no effect)' : ''}
                    {result.would_block_card ? ' · would block the card' : ''}
                    {result.would_block_customer ? ' · would block the customer' : ''}
                  </div>
                </div>
              </div>
              {result.logs?.length > 0 && (
                <pre className="text-[11px] font-mono bg-slate-950 text-emerald-300 rounded-xl p-3">{result.logs.join('\n')}</pre>
              )}
              {result.rows && result.rows.length > 0 && (
                <pre className="text-[11px] font-mono bg-slate-950 text-sky-300 rounded-xl p-3 overflow-x-auto">{JSON.stringify(result.rows, null, 2)}</pre>
              )}
              <button type="button" onClick={() => setShowCtx(!showCtx)} className="text-[11px] text-slate-400 hover:text-slate-200 underline">
                {showCtx ? 'Hide' : 'Show'} the values this test used
              </button>
              {showCtx && res.context && (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  {Object.entries(res.context).map(([g, vals]: [string, any]) => (
                    <div key={g} className="rounded-xl border border-slate-200 dark:border-slate-800 p-3">
                      <div className="text-[10px] uppercase tracking-wider font-bold text-slate-400 mb-1.5">{g}</div>
                      {Object.entries(vals).map(([k, v]: [string, any]) => (
                        <div key={k} className="flex justify-between gap-2 text-[10px] font-mono py-0.5">
                          <span className="text-slate-500">{k}</span>
                          <span className="text-slate-300 truncate max-w-[140px]" title={String(v)}>{String(v)}</span>
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
'''

TEST_LOCAL_HOST_PY = r'''import os
import itertools
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.database import Base, SessionLocal, engine
from app.main import app
from app.host_engine import HostTransactionProcessor
from app.models import Account, Card, Customer, Transaction, Institution, CardProfile, HostParameter
from app.models_local_host import LocalHostPolicy, HostAlgo, HostAlgoLog, HostAlgoVersion
from app.local_host_engine import (
    validate_python, validate_sql, field_catalog, ALGO_TEMPLATES, effective_policy, build_test_context, LocalHostEngine,
    run_python_algo,
)
from app.seed_data import seed_initial_data
from app.security import create_access_token
from app.config import settings

PAN = "4567890123450001"
_seq = itertools.count(1)


@pytest.fixture()
def db_session():
    Base.metadata.create_all(bind=engine)
    # other test modules (e.g. the LMK provider switch test) leave settings.HSM_MODE on EXTERNAL: pin it for these tests
    previous_mode = settings.HSM_MODE
    settings.HSM_MODE = "SOFT_HSM_LOCAL"
    session = SessionLocal()
    seed_initial_data(session)
    yield session
    session.close()
    settings.HSM_MODE = previous_mode
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session):
    with TestClient(app) as c:
        token = create_access_token(subject=settings.ADMIN_USERNAME)
        c.headers = {"Authorization": f"Bearer {token}"}
        yield c


def tx(db, amount=2500, terminal="ATM01", tcode="10", mcc=None, country=None, hour=None, pan=PAN, **extra):
    n = next(_seq)
    fields = {"2": pan, "3": f"{int(tcode):03d}0000", "4": f"{int(amount * 100):012d}", "11": f"{n:06d}",
              "37": f"{900000000000 + n}", "41": terminal, "49": "050"}
    if mcc:
        fields["18"] = mcc
    if country:
        fields["19"] = country
    if hour is not None:
        fields["12"] = f"{hour:02d}0000"
    fields.update(extra)
    return HostTransactionProcessor(db).process_transaction(
        {"transaction_code": tcode, "mti": "0200", "test_clear_pin_helper": "1234", "fields": fields}
    )


def card_of(db):
    return db.query(Card).filter(Card.test_pan_reference == PAN).first()


def set_policy(db, config, scope="GLOBAL", inst=None, enabled=True):
    db.add(LocalHostPolicy(scope_type=scope, institution_id=inst, name="t", enabled=enabled, config_json=config))
    db.commit()


def add_algo(db, code="T_ALGO", language="PYTHON", src="", **kw):
    a = HostAlgo(algo_code=code, name=code, language=language, code=src, **kw)
    db.add(a)
    db.commit()
    return a


def check_names(res):
    return [c["check_name"] for c in res["checks"]]


# ============================================================================ baseline
def test_default_policy_does_not_change_existing_behaviour(db_session):
    res = tx(db_session)
    assert res["response_code"] == "00"
    assert any(n == "Local Host Policy" for n in check_names(res))


# ============================================================================ policy engine
def test_host_status_maintenance_declines_bank(db_session):
    bank = card_of(db_session).institution
    set_policy(db_session, {"general": {"host_status": "MAINTENANCE", "status_response_code": "91", "status_message": "Down for upgrade"}},
               scope="BANK", inst=bank.id)
    res = tx(db_session)
    assert res["response_code"] == "91"
    failed = [c for c in res["checks"] if c["check_status"] == "FAILED"][0]
    assert "Down for upgrade" in failed["message"]


def test_channel_disabled_and_amount_caps(db_session):
    set_policy(db_session, {"channels": {"ATM": {"enabled": False}}})
    assert tx(db_session)["response_code"] == "57"
    db_session.query(LocalHostPolicy).delete(); db_session.commit()
    set_policy(db_session, {"channels": {"ATM": {"enabled": True, "max_amount": 1000}}})
    assert tx(db_session, amount=2500)["response_code"] == "61"
    assert tx(db_session, amount=500)["response_code"] == "00"


def test_transaction_matrix_blocks_code_on_channel(db_session):
    set_policy(db_session, {"transactions": {"10": {"enabled": True, "channels": ["POS"]}}})
    res = tx(db_session)  # cash withdrawal on ATM terminal
    assert res["response_code"] == "57"
    set_policy_row = db_session.query(LocalHostPolicy).first()
    set_policy_row.config_json = {"transactions": {"10": {"enabled": False}}}
    db_session.commit()
    assert tx(db_session)["response_code"] == "57"


def test_source_control_on_us_and_unknown_source(db_session):
    set_policy(db_session, {"sources": {"ON_US": {"enabled": False}}})
    assert tx(db_session)["response_code"] == "57"  # seeded terminal belongs to the card's own bank -> ON_US


def test_mcc_currency_country_and_acquirer_filters(db_session):
    set_policy(db_session, {"mcc": {"blocked": ["7995"]}})
    assert tx(db_session, mcc="7995")["response_code"] == "57"
    assert tx(db_session, mcc="5411")["response_code"] == "00"
    cfg = db_session.query(LocalHostPolicy).first()
    cfg.config_json = {"cross_border": {"enabled": False}}
    db_session.commit()
    assert tx(db_session, country="840")["response_code"] == "57"
    cfg.config_json = {"general": {"allowed_currencies": ["USD"]}}
    db_session.commit()
    assert tx(db_session)["response_code"] == "57"
    card = card_of(db_session)
    cfg.config_json = {"acquirers": {"blocked": [card.institution.institution_code], "response_code": "58"}}
    db_session.commit()
    assert tx(db_session)["response_code"] == "58"          # terminal owner = the card's own bank here
    cfg.config_json = {"acquirers": {"allowed": ["SOME_OTHER_BANK"], "response_code": "58"}}
    db_session.commit()
    assert tx(db_session)["response_code"] == "58"
    cfg.config_json = {"acquirers": {"allowed": [card.institution.institution_code]}}
    db_session.commit()
    assert tx(db_session)["response_code"] == "00"


def test_business_hours_wrap_and_velocity(db_session):
    set_policy(db_session, {"general": {"business_hours": {"enabled": True, "start": "09:00", "end": "17:00"}}})
    assert tx(db_session, hour=3)["response_code"] == "57"
    assert tx(db_session, hour=10)["response_code"] == "00"
    cfg = db_session.query(LocalHostPolicy).first()
    cfg.config_json = {"velocity": {"enabled": True, "max_tx_per_minute": 2, "response_code": "65"}}
    db_session.commit()
    # earlier approved transaction(s) in this test already count; use clear numbers
    before = db_session.query(Transaction).count()
    res = None
    for _ in range(4):
        res = tx(db_session, amount=10)
        if res["response_code"] == "65":
            break
    assert res["response_code"] == "65"


def test_policy_inheritance_bank_overrides_only_its_sections(db_session):
    bank = card_of(db_session).institution
    set_policy(db_session, {"channels": {"ATM": {"enabled": False}}, "mcc": {"blocked": ["7995"]}})
    set_policy(db_session, {"channels": {"ATM": {"enabled": True}}}, scope="BANK", inst=bank.id)
    eff = effective_policy(db_session, bank.id)
    assert eff["config"]["channels"]["ATM"]["enabled"] is True            # bank override wins
    assert eff["config"]["mcc"]["blocked"] == ["7995"]                    # inherited from GLOBAL
    assert eff["sources"]["channels"] == "BANK" and eff["sources"]["mcc"] == "GLOBAL" and eff["sources"]["velocity"] == "DEFAULT"
    assert tx(db_session)["response_code"] == "00"


def test_policy_api_roundtrip_and_simulator(client, db_session):
    bank = card_of(db_session).institution
    r = client.put("/api/local-host/policies", json={"scope_type": "GLOBAL", "config": {"channels": {"ATM": {"enabled": False, "max_amount": "oops"}}, "bogus": {"x": 1}}})
    assert r.status_code == 200 and r.json()["sections"] == ["channels"]
    r = client.put("/api/local-host/policies", json={"scope_type": "BANK", "institution_id": bank.id, "config": {"mcc": {"blocked": "7995, 6012"}}})
    assert r.status_code == 200
    assert client.put("/api/local-host/policies", json={"scope_type": "BANK", "config": {}}).status_code == 400
    lst = client.get("/api/local-host/policies").json()
    assert lst[0]["scope_type"] == "GLOBAL" and any(p["bank_code"] == bank.institution_code and p["exists"] for p in lst)
    eff = client.get("/api/local-host/policies/effective", params={"institution_id": bank.id}).json()
    assert eff["config"]["mcc"]["blocked"] == ["7995", "6012"] and eff["config"]["channels"]["ATM"]["max_amount"] == 0
    sim = client.post("/api/local-host/policies/simulate", json={"institution_id": bank.id, "overrides": {"channel": "ATM", "amount": 500}}).json()
    assert sim["allowed"] is False and sim["failed_control"] == "Channel Control" and sim["response_code"] == "57"
    sim2 = client.post("/api/local-host/policies/simulate", json={"institution_id": bank.id, "overrides": {"channel": "POS", "mcc": "7995"}}).json()
    assert sim2["failed_control"] == "MCC Control"
    sim3 = client.post("/api/local-host/policies/simulate", json={"institution_id": bank.id, "overrides": {"channel": "POS", "mcc": "5411"}}).json()
    assert sim3["allowed"] is True and sim3["checks"]
    assert client.delete(f"/api/local-host/policies/bank/{bank.id}").status_code == 200
    assert client.delete(f"/api/local-host/policies/bank/{bank.id}").status_code == 404
    meta = client.get("/api/local-host/meta").json()
    assert meta["banks"] and meta["transaction_codes"] and meta["processing_systems"] and "ATM" in meta["channels"]


# ============================================================================ python sandbox
@pytest.mark.parametrize("code", [
    "import os",
    "x = ().__class__",
    "open('/etc/passwd')",
    "while True:\n    pass",
    "eval('1+1')",
    "x = tx.amount ** 9",
    "getattr(tx, 'amount')",
    "'{0.__class__}'.format(tx)",
    "def f():\n    return (i for i in []).gi_frame\nf()",
    "class A: pass",
    "try:\n    pass\nexcept:\n    pass",
    "with open('x') as f:\n    pass",
    "x = 1 << 99",
])
def test_sandbox_rejects_dangerous_code(code):
    errors, _ = validate_python(code)
    assert errors, f"should be rejected: {code!r}"


def test_sandbox_accepts_normal_code_and_blocks_memory_bombs(db_session):
    assert validate_python("if tx.amount > 5000 and tx.hour < 5:\n    decline('57', 'x')\n")[0] == []
    card = card_of(db_session)
    ctx = build_test_context(db_session, card, {"amount": 100})
    res = run_python_algo(db_session, "x = 'a' * 10**3 * 10**3\nreturn True", ctx)
    # ** is rejected at validation; plain repetition beyond the cap is blocked at run time
    assert res.error
    res = run_python_algo(db_session, "x = 'a' * 100000\nreturn True", ctx)
    assert res.error and "too large" in res.error
    res = run_python_algo(db_session, "x = 0\nfor i in range(100000):\n    x = x + i\nreturn True", ctx)
    assert res.error and "range()" in res.error
    res = run_python_algo(db_session, "tx.amount > 50", ctx)         # last expression is the result
    assert res.matched and res.action is None and not res.error
    res = run_python_algo(db_session, "decline('Night time')", ctx)  # message only
    assert res.action == "DECLINE" and res.message == "Night time" and res.rc is None
    res = run_python_algo(db_session, "decline('61', 'Too much')", ctx)
    assert res.rc == "61" and res.message == "Too much"
    res = run_python_algo(db_session, "block_card('stolen', '62')", ctx)
    assert res.action == "BLOCK_CARD" and res.rc == "62" and res.message == "stolen"
    res = run_python_algo(db_session, "block_card('only message')", ctx)
    assert res.rc is None and res.message == "only message"
    res = run_python_algo(db_session, "y = card.nothing", ctx)
    assert res.error and "AttributeError" in res.error
    res = run_python_algo(db_session, "try:\n    decline('57','in try')\nexcept Exception:\n    pass", ctx)
    assert res.action == "DECLINE"  # a script cannot swallow its own decision


# ============================================================================ python algos in the pipeline
def test_python_algo_declines_in_pipeline_and_logs(db_session):
    add_algo(db_session, "NIGHT", src="if tx.channel == 'ATM' and tx.amount > 1000 and tx.hour < 5:\n    decline('57', 'night cash')\n",
             default_action="DECLINE")
    res = tx(db_session, amount=2000, hour=2)
    assert res["response_code"] == "57"
    failed = [c for c in res["checks"] if c["check_status"] == "FAILED"][0]
    assert failed["check_name"] == "Algo NIGHT" and "night cash" in failed["message"]
    assert tx(db_session, amount=2000, hour=14)["response_code"] == "00"
    algo = db_session.query(HostAlgo).first()
    db_session.refresh(algo)
    assert algo.eval_count == 2 and algo.hit_count == 1
    logs = db_session.query(HostAlgoLog).all()
    assert len(logs) == 1 and logs[0].matched and logs[0].action_applied and logs[0].response_code == "57"
    assert "4567890123450001" not in str(logs[0].context_json)


def test_monitor_mode_never_declines_or_blocks(db_session):
    add_algo(db_session, "MON", src="return True", default_action="BLOCK_CARD", mode="MONITOR")
    res = tx(db_session)
    assert res["response_code"] == "00"
    assert any("[MONITOR] would BLOCK_CARD" in c["message"] for c in res["checks"])
    assert card_of(db_session).card_status == "ACTIVE"
    log = db_session.query(HostAlgoLog).first()
    assert log.matched and not log.action_applied


def test_block_card_blocks_for_real_and_next_tx_is_declined(db_session):
    add_algo(db_session, "BLK", src="if tx.amount > 5000:\n    block_card('suspicious', '62')\n", default_action="BLOCK_CARD", default_response_code="62")
    res = tx(db_session, amount=6000)
    assert res["response_code"] == "62"
    assert card_of(db_session).card_status == "BLOCKED"
    assert tx(db_session, amount=100)["response_code"] == "05"      # card status check now declines


def test_block_customer_blocks_customer(db_session):
    add_algo(db_session, "BLKC", src="block_customer('fraud ring')", default_action="BLOCK_CUSTOMER", default_response_code="62")
    res = tx(db_session)
    assert res["response_code"] == "62"
    cust = card_of(db_session).customer
    assert cust.customer_status == "BLOCKED"
    assert tx(db_session)["response_code"] == "05"


def test_approve_allow_list_skips_later_algos_but_not_balance(db_session):
    add_algo(db_session, "A_ALLOW", src="if tx.amount < 5000:\n    approve('allow small')", default_action="APPROVE", priority=10)
    add_algo(db_session, "B_DENY", src="return True", default_action="DECLINE", priority=20)
    assert tx(db_session, amount=100)["response_code"] == "00"
    assert tx(db_session, amount=9000)["response_code"] == "57"      # allow-list did not match -> next algo declines
    # approve() does not bypass balance checks
    acct = db_session.query(Account).filter(Account.account_number == "1001000001").first()
    acct.available_balance = Decimal("50.00"); db_session.commit()
    assert tx(db_session, amount=100)["response_code"] == "51"


def test_flag_continues_and_error_policies(db_session):
    add_algo(db_session, "FLG", src="flag('watch this card')", default_action="FLAG", priority=10)
    res = tx(db_session)
    assert res["response_code"] == "00" and any("FLAG: watch this card" in c["message"] for c in res["checks"])
    db_session.query(HostAlgo).delete(); db_session.commit()
    add_algo(db_session, "BUGSKIP", src="return 1 / 0", on_error="SKIP")
    res = tx(db_session)
    assert res["response_code"] == "00" and any(c["check_status"] == "SKIPPED" for c in res["checks"])
    assert db_session.query(HostAlgo).first().error_count >= 1
    db_session.query(HostAlgo).delete(); db_session.commit()
    add_algo(db_session, "BUGCLOSED", src="return 1 / 0", on_error="DECLINE", default_response_code="05")
    assert tx(db_session)["response_code"] == "05"


def test_scopes_and_filters(db_session):
    card = card_of(db_session)
    other = db_session.query(Institution).filter(Institution.id != card.institution_id).first()
    add_algo(db_session, "OTHERBANK", src="return True", scope_type="BANK", institution_id=other.id)
    assert tx(db_session)["response_code"] == "00"                     # other bank's algo does not apply
    add_algo(db_session, "MYBANK", src="return True", scope_type="BANK", institution_id=card.institution_id)
    assert tx(db_session)["response_code"] == "57"
    db_session.query(HostAlgo).delete(); db_session.commit()
    prof = db_session.query(CardProfile).filter(CardProfile.id != card.card_profile_id).first()
    add_algo(db_session, "OTHERPROF", src="return True", scope_type="CARD_PROFILE", card_profile_id=prof.id)
    assert tx(db_session)["response_code"] == "00"
    add_algo(db_session, "MYPROF", src="return True", scope_type="CARD_PROFILE", card_profile_id=card.card_profile_id)
    assert tx(db_session)["response_code"] == "57"
    db_session.query(HostAlgo).delete(); db_session.commit()
    add_algo(db_session, "ONLYPOS", src="return True", channels_json=["POS"])
    add_algo(db_session, "ONLYCODE00", src="return True", tx_codes_json=["00"])
    assert tx(db_session)["response_code"] == "00"                     # ATM cash (code 10): filtered out
    add_algo(db_session, "DISABLED", src="return True", enabled=False)
    assert tx(db_session)["response_code"] == "00"


def test_history_helper_velocity_and_block_after_declines(db_session):
    add_algo(db_session, "DECL3", src="if history.declines('10m', 'card') >= 2:\n    block_card('2 declines', '62')\n",
             default_action="BLOCK_CARD", default_response_code="62")
    acct = db_session.query(Account).filter(Account.account_number == "1001000001").first()
    acct.available_balance = Decimal("10.00"); db_session.commit()
    assert tx(db_session, amount=500)["response_code"] == "51"
    assert tx(db_session, amount=500)["response_code"] == "51"
    res = tx(db_session, amount=500)                                   # 2 earlier declines -> blocked
    assert res["response_code"] == "62" and card_of(db_session).card_status == "BLOCKED"


def test_post_auth_stage_sees_balance_after(db_session):
    add_algo(db_session, "POST", src="if account.balance_after < 150000:\n    decline('57', 'would leave too little')\n", stage="POST_AUTH")
    acct = db_session.query(Account).filter(Account.account_number == "1001000001").first()
    start = float(acct.available_balance)
    assert start >= 150000
    res = tx(db_session, amount=2000)                       # balance after = start - 2000 < 150000 only if start < 152000
    expected = "57" if start - 2000 < 150000 else "00"
    assert res["response_code"] == expected
    acct.available_balance = Decimal("151000.00"); db_session.commit()
    res = tx(db_session, amount=2000)                       # 149,000 left -> POST_AUTH algo declines before posting
    assert res["response_code"] == "57"
    db_session.refresh(acct)
    assert acct.available_balance == Decimal("151000.00")   # nothing was posted


# ============================================================================ SQL algos
@pytest.mark.parametrize("sql", [
    "DELETE FROM transactions",
    "SELECT 1; DROP TABLE cards",
    "UPDATE cards SET card_status='X'",
    "SELECT :not_a_field",
    "PRAGMA table_info(cards)",
    "SELECT * INTO x FROM cards",
    "INSERT INTO cards VALUES (1)",
])
def test_sql_validation_rejects_unsafe(sql):
    assert validate_sql(sql)[0], sql


def test_sql_algo_condition_and_custom_action(db_session):
    add_algo(db_session, "SQL1", language="SQL",
             src="SELECT COUNT(*) >= 2 FROM transactions WHERE card_id = :card_id AND authorization_status = 'APPROVED' AND transaction_datetime >= :since_1h",
             default_action="DECLINE", default_response_code="65")
    assert tx(db_session, amount=10)["response_code"] == "00"
    assert tx(db_session, amount=10)["response_code"] == "00"
    assert tx(db_session, amount=10)["response_code"] == "65"          # two approved earlier -> SQL matches
    db_session.query(HostAlgo).delete(); db_session.commit()
    add_algo(db_session, "SQL2", language="SQL",
             src="SELECT 'BLOCK_CARD' AS action, '62' AS response_code, 'sql says block' AS message WHERE :tx_amount > 7000")
    assert tx(db_session, amount=100)["response_code"] == "00"
    res = tx(db_session, amount=8000)
    assert res["response_code"] == "62" and card_of(db_session).card_status == "BLOCKED"
    failed = [c for c in res["checks"] if c["check_status"] == "FAILED"][0]
    assert "sql says block" in failed["message"]


# ============================================================================ algo API
def _body(**kw):
    b = {"algo_code": "api algo 1", "name": "API Algo", "language": "PYTHON", "code": "if tx.amount > 100:\n    decline('57','big')\n",
         "scope_type": "GLOBAL", "stage": "PRE_AUTH", "priority": 50, "mode": "ENFORCE", "default_action": "DECLINE",
         "default_response_code": "57", "default_message": "msg", "on_error": "SKIP", "stop_on_match": True,
         "tx_codes": [], "channels": [], "enabled": True}
    b.update(kw)
    return b


def test_algo_crud_versions_rollback_toggle_logs(client, db_session):
    r = client.post("/api/local-host/algos", json=_body())
    assert r.status_code == 200, r.text
    algo = r.json()
    assert algo["algo_code"] == "API_ALGO_1" and algo["version"] == 1
    assert client.post("/api/local-host/algos", json=_body()).status_code == 409
    assert client.post("/api/local-host/algos", json=_body(algo_code="bad code", code="import os")).status_code == 400
    assert client.post("/api/local-host/algos", json=_body(algo_code="no bank", scope_type="BANK")).status_code == 400
    assert client.post("/api/local-host/algos", json=_body(algo_code="bad sql", language="SQL", code="DELETE FROM cards")).status_code == 400
    lst = client.get("/api/local-host/algos").json()
    assert len(lst) == 1 and "code" not in lst[0]
    aid = algo["id"]
    upd = client.put(f"/api/local-host/algos/{aid}", json=_body(code="return False", change_note="no-op")).json()
    assert upd["version"] == 2 and upd["code"] == "return False"
    vers = client.get(f"/api/local-host/algos/{aid}/versions").json()
    assert [v["version"] for v in vers] == [2, 1]
    rb = client.post(f"/api/local-host/algos/{aid}/rollback", json={"version": 1}).json()
    assert rb["version"] == 3
    assert "decline" in client.get(f"/api/local-host/algos/{aid}").json()["code"]
    assert client.post(f"/api/local-host/algos/{aid}/toggle", json={"enabled": False}).json()["enabled"] is False
    assert client.post(f"/api/local-host/algos/{aid}/toggle", json={"mode": "MONITOR", "enabled": True}).json()["mode"] == "MONITOR"
    assert client.post(f"/api/local-host/algos/{aid}/toggle", json={"mode": "NOPE"}).status_code == 400
    # run a real transaction through it and read the logs / overview
    client.post(f"/api/local-host/algos/{aid}/toggle", json={"mode": "ENFORCE"})
    assert tx(db_session, amount=500)["response_code"] == "57"
    logs = client.get("/api/local-host/algos/logs", params={"algo_id": aid, "matched_only": True}).json()
    assert len(logs) == 1 and logs[0]["action"] == "DECLINE"
    ov = client.get("/api/local-host/overview").json()
    assert ov["algos_total"] == 1 and ov["matches_24h"] == 1 and ov["top_algos"][0]["algo_code"] == "API_ALGO_1"
    assert client.delete(f"/api/local-host/algos/{aid}").status_code == 200
    assert client.get(f"/api/local-host/algos/{aid}").status_code == 404


def test_algo_test_endpoint_is_side_effect_free(client, db_session):
    card = card_of(db_session)
    draft = _body(code="block_card('test block', '62')", default_action="BLOCK_CARD")
    r = client.post("/api/local-host/algos/test", json={"draft": draft, "card_id": card.id, "overrides": {"amount": 9999, "channel": "ATM", "hour": 3}}).json()
    assert r["ok"] and r["result"]["matched"] and r["result"]["action"] == "BLOCK_CARD" and r["result"]["would_block_card"]
    assert r["context"]["tx"]["amount"] == 9999 and r["context"]["tx"]["channel"] == "ATM" and r["context"]["tx"]["hour"] == 3
    assert r["context"]["card"]["pan"].startswith("456789******")   # never exposes the full PAN
    db_session.expire_all()
    assert card_of(db_session).card_status == "ACTIVE" and db_session.query(HostAlgoLog).count() == 0
    bad = client.post("/api/local-host/algos/test", json={"draft": _body(code="import os"), "card_id": card.id}).json()
    assert bad["ok"] is False and bad["errors"]
    sqlr = client.post("/api/local-host/algos/test", json={"draft": _body(language="SQL", code="SELECT 1 AS x WHERE :tx_amount > 5"), "pan": PAN, "overrides": {"amount": 50}}).json()
    assert sqlr["ok"] and sqlr["result"]["matched"] is True and sqlr["result"]["rows"] == [{"x": 1}]
    v = client.post("/api/local-host/algos/validate", json={"language": "PYTHON", "code": "while True: pass"}).json()
    assert v["valid"] is False
    assert client.post("/api/local-host/algos/validate", json={"language": "SQL", "code": "SELECT 1"}).json()["valid"] is True


def test_catalog_templates_and_schema(client, db_session):
    cat = client.get("/api/local-host/algos/fields").json()
    keys = {f["python"] for g in cat["groups"] for f in g["fields"]}
    for must in ("tx.amount", "tx.hour", "tx.channel", "bank.name", "terminal.owner", "profile.auth_name", "customer.risk",
                 "card.status", "account.balance", "limits.card_daily_used"):
        assert must in keys, must
    assert all(f["sql"].startswith(":") for g in cat["groups"] for f in g["fields"])
    assert cat["actions"] and cat["history"] and cat["time_params"]
    tpls = client.get("/api/local-host/algos/templates").json()
    assert len(tpls) == len(ALGO_TEMPLATES) >= 8
    card = card_of(db_session)
    for t in tpls:                                                      # every template is valid and runs
        v = client.post("/api/local-host/algos/validate", json={"language": t["language"], "code": t["code"]}).json()
        assert v["valid"], (t["key"], v)
        r = client.post("/api/local-host/algos/test", json={"draft": {**t, "algo_code": t["key"]}, "card_id": card.id,
                                                            "overrides": {"amount": 30000, "channel": "ATM", "hour": 2}}).json()
        assert r["ok"], (t["key"], r)
        assert not r["result"]["error"], (t["key"], r["result"]["error"])
    schema = client.get("/api/local-host/algos/schema").json()
    assert any(t["table"] == "transactions" for t in schema)
    # every SQL param in the catalog really exists in the live context
    ctx = build_test_context(db_session, card, {})
    for g in cat["groups"]:
        for f in g["fields"]:
            assert f["sql"][1:] in ctx.params


# ============================================================================ Rules & Checks tab + friendly errors
def test_algo_save_errors_are_readable_not_422(client, db_session):
    r = client.post("/api/local-host/algos", json=_body(algo_code="", name=""))
    assert r.status_code == 400
    msg = r.json()["detail"]
    assert "Algo code is required" in msg and "Name is required" in msg
    assert client.post("/api/local-host/algos", json=_body(algo_code="AB")).status_code == 400
    assert "Priority" in client.post("/api/local-host/algos", json=_body(algo_code="PRIO_X", priority=0)).json()["detail"]
    assert "Response code" in client.post("/api/local-host/algos", json=_body(algo_code="RC_X", default_response_code="5")).json()["detail"]
    ok = client.post("/api/local-host/algos", json=_body(algo_code="fine one", name="Fine"))
    assert ok.status_code == 200 and ok.json()["algo_code"] == "FINE_ONE"
    long_msg = client.post("/api/local-host/algos", json=_body(algo_code="LONGMSG", default_message="x" * 500))
    assert long_msg.status_code == 200 and len(long_msg.json()["default_message"]) == 200


def test_builtin_checks_list_toggle_and_really_switch_off(client, db_session):
    checks = client.get("/api/local-host/checks").json()
    live = [c for c in checks if c["affects_host"]]
    assert [c["name"] for c in live] == ["CHECKCARDLIMITS", "CHECKACCT2CARDLIMITS", "AUTHORIZEACCTBALANCESTRANS"]
    assert all(c["enabled"] and c["title"] and c["what"] and c["decline_rc"] for c in live)
    assert [c["name"] for c in checks if not c["affects_host"]] == ["DEFAULTREQUESTFUNCTION", "DEFAULTRESPONSEFUNCTION", "POSRESPONSECONTROLFUNCTION"]

    acct = db_session.query(Account).filter(Account.account_number == "1001000001").first()
    acct.available_balance = Decimal("10.00"); db_session.commit()
    bal = next(c for c in live if c["name"] == "AUTHORIZEACCTBALANCESTRANS")
    assert tx(db_session, amount=500)["response_code"] == "51"
    assert client.post(f"/api/local-host/checks/{bal['id']}/toggle", json={"enabled": False}).status_code == 200
    assert next(c for c in client.get("/api/local-host/checks").json() if c["id"] == bal["id"])["enabled"] is False
    assert tx(db_session, amount=500)["response_code"] == "00"          # really OFF now
    client.post(f"/api/local-host/checks/{bal['id']}/toggle", json={"enabled": True})
    assert tx(db_session, amount=500)["response_code"] == "51"          # and ON again

    # what the OLD page saved (active = false) also switches the check off now
    p = db_session.query(HostParameter).filter(HostParameter.parameter_name == "AUTHORIZEACCTBALANCESTRANS").first()
    p.active = False
    p.parameter_value = {**p.parameter_value, "enabled": False}
    db_session.commit()
    assert tx(db_session, amount=500)["response_code"] == "00"

    # parameters the engine does not know are listed as reference only
    db_session.add(HostParameter(parameter_group="MY_GROUP", parameter_name="MY_SWITCH", parameter_value={"enabled": True}, description="mine"))
    db_session.commit()
    mine = next(c for c in client.get("/api/local-host/checks").json() if c["name"] == "MY_SWITCH")
    assert mine["affects_host"] is False and mine["known"] is False and mine["title"] == "MY_SWITCH"
    assert client.post("/api/local-host/checks/nope/toggle", json={"enabled": True}).status_code == 404


def test_simple_rules_builder_roundtrip_validation_and_engine(client, db_session):
    fields = client.get("/api/local-host/rules/fields").json()
    names = {f["name"] for f in fields}
    assert {"amount", "trancode", "hour", "mcc", "institution.code", "is_foreign", "card_status", "account_balance"} <= names
    bad = client.post("/api/local-host/rules/validate", json={"expression": "ammount > 5"}).json()
    assert bad["valid"] is False and "ammount" in bad["error"]
    assert client.post("/api/local-host/rules/validate", json={"expression": "  "}).json()["valid"] is False
    for expr in ["amount > 50000", "(trancode == '10' or trancode == '11')", "not is_foreign", "institution.code == 'XBANK'",
                 "hour < 5 and amount >= 20000", "(mcc != '5411' and mcc != '5812')", "is_foreign"]:
        assert client.post("/api/local-host/rules/validate", json={"expression": expr}).json()["valid"] is True, expr

    cj = {"logic": "AND", "conditions": [{"field": "amount", "op": ">", "value": "1000"}]}
    r = client.post("/api/authorizer-rules", json={"rule_code": "BIG_CASH", "name": "Big cash", "rule_mode": "BUILDER", "conditions_json": cj,
                    "expression": "amount > 1000", "action": "DECLINE", "response_code": "61", "message": "too big", "priority": 10,
                    "stop_on_match": True, "enabled": True})
    assert r.status_code == 200, r.text
    rid = r.json()["id"]
    assert tx(db_session, amount=2000)["response_code"] == "61"
    assert tx(db_session, amount=500)["response_code"] == "00"

    cj2 = {"logic": "AND", "conditions": [{"field": "amount", "op": ">", "value": "5000"}]}
    u = client.put(f"/api/authorizer-rules/{rid}", json={"expression": "amount > 5000", "conditions_json": cj2, "rule_mode": "BUILDER"})
    assert u.status_code == 200 and u.json()["conditions_json"] == cj2 and u.json()["rule_mode"] == "BUILDER"
    assert tx(db_session, amount=2000)["response_code"] == "00"
    assert tx(db_session, amount=6000)["response_code"] == "61"
    assert client.put(f"/api/authorizer-rules/{rid}", json={"enabled": False}).status_code == 200
    assert tx(db_session, amount=6000)["response_code"] == "00"

    t = client.post("/api/local-host/rules/test", json={"expression": "amount > 1000 and hour < 5", "pan": PAN, "overrides": {"amount": 5000, "hour": 2}}).json()
    assert t["valid"] and t["matched"] and t["context"]["amount"] == 5000 and t["context"]["hour"] == 2
    t2 = client.post("/api/local-host/rules/test", json={"expression": "amount > 1000 and hour < 5", "pan": PAN, "overrides": {"amount": 5000, "hour": 14}}).json()
    assert t2["valid"] and t2["matched"] is False
    t3 = client.post("/api/local-host/rules/test", json={"expression": "nope > 1", "pan": PAN}).json()
    assert t3["valid"] is False and "nope" in t3["error"]
    assert client.post("/api/local-host/rules/test", json={"expression": "amount > 1", "pan": "0000000000000000"}).status_code == 404


def test_every_field_in_the_reference_is_usable_in_a_real_transaction(client, db_session):
    cat = client.get("/api/local-host/algos/fields").json()
    paths = [f["python"] for g in cat["groups"] for f in g["fields"]]
    params = [f["sql"] for g in cat["groups"] for f in g["fields"]]
    assert len(paths) >= 90 and "tx.currency" in paths and "tx.tran_code" in paths and "tx.is_financial" in paths

    # PYTHON: read every single field, then check that the values are the real ones of this transaction
    code = "seen = [\n" + ",\n".join(f"    {p}" for p in paths) + "\n]\n"
    code += ("if tx.currency != '050' or tx.tran_code != '10' or tx.channel != 'ATM' or tx.amount != 2500 or tx.mti != '0200':\n"
             "    decline('99', 'tx fields do not match')\n"
             "if card.status != 'ACTIVE' or card.last4 != '0001' or not bank.code or customer.status != 'ACTIVE':\n"
             "    decline('98', 'card/bank/customer fields do not match')\n"
             "if profile.auth_code == '' and profile.card_code == '':\n"
             "    decline('97', 'profile fields are empty')\n"
             "log(len(seen))\nreturn False\n")
    add_algo(db_session, "ALL_PY", src=code)
    res = tx(db_session, amount=2500)
    chk = [c for c in res["checks"] if c["check_name"] == "Algo ALL_PY"][0]
    assert chk["check_status"] == "PASSED" and chk["message"] == "Condition not met", chk
    assert res["response_code"] == "00"

    # SQL: every :parameter is bound to a value
    db_session.query(HostAlgo).delete(); db_session.commit()
    sql = "SELECT 1 WHERE " + " AND ".join(f"({p} IS NOT NULL)" for p in params)
    add_algo(db_session, "ALL_SQL", language="SQL", src=sql, mode="MONITOR")
    res = tx(db_session, amount=2500)
    chk = [c for c in res["checks"] if c["check_name"] == "Algo ALL_SQL"][0]
    assert "[MONITOR] would DECLINE" in chk["message"], chk
'''

GUIDE_MD = r'''# Rajon Host Control Center - quick guide

Menu: **14. Host Control Center**. It replaces the old *Host Configuration* table and menu *7.5 Authorizer Rules*: both are now the **Rules & Checks** tab.

## Where it sits in the authorization pipeline

```
card / customer / account checks
  -> Local Host policy            (host status, hours, source, channel, transaction matrix, currency, country, MCC, owner, velocity)
  -> Authorization profile limits (existing limit engine)
  -> Authorizer rules             (existing)
  -> Algo Control  PRE_AUTH       (your Python / SQL blocks)
  -> PIN / CVV / HSM checks
  -> balance + legacy limits
  -> Algo Control  POST_AUTH      (your Python / SQL blocks)
  -> approve + post to the ledger
```

## Local Host tab

* Left: **Global Default** plus one entry per bank. A bank inherits the Global policy section by section.
* On a bank, switch **Override** on for a section to give that bank its own values. Sections left off follow Global.
* Sections: Host status & defaults, Channel control, Source systems (ON_US, ITCL, NPSB, VISA, MASTERCARD ...),
  Transaction matrix, Cross-border, MCC, Terminal owners, Velocity.
* **Policy simulator** at the bottom evaluates a sample transaction against the saved policy.
* Changes apply to the next transaction immediately after **Save policy**. No restart needed.

Default decline codes: 57 not permitted, 61 exceeds amount, 13 below minimum, 65 velocity, 91 host unavailable, 58 terminal owner.

## Rules & Checks tab

Three layers, from simple to advanced: built-in checks, simple rules, Algo Control.

**Built-in checks** - switches for the protections the host engine really reads:

| Check | What it does | Decline |
|---|---|---|
| Account balance check | balance + overdraft must cover a debit | 51 |
| Card limit check | per-transaction and daily limits of the card (menu 5) | 61 |
| Account limit check | per-transaction and daily limits of the account (menu 6) | 61 |

Switching one OFF applies to every bank immediately. (Older versions of the page set the parameter to inactive but the engine
ignored that, so a check never really turned off. Fixed.) Request router / response builder / POS response control are stored as
reference only: the engine does not read them.

**My simple rules** - "if this, then decline / approve / flag" without code. Build the condition with dropdowns
(field, operator, value, ALL / ANY) or write the expression yourself; see the plain-words summary, test it on a real card, save.
Fields: `amount trancode currency hour mcc terminal_id is_foreign card_status account_balance daily_used institution.code
acquirer_bank ps_name bin channel` ... Rules run in priority order before the PIN / HSM checks. Anything more complex
(per bank, per card profile, history, block card / customer) belongs in Algo Control.

## Algo Control tab

An algo is a Python or SQL block with a scope (whole host, one bank, or one card profile), a stage and a mode.

| Setting | Meaning |
|---|---|
| Stage PRE_AUTH | runs before PIN / HSM checks (cheap risk checks, velocity, blocks) |
| Stage POST_AUTH | runs after balance and limits passed, just before posting (can see `account.balance_after`) |
| Mode MONITOR | shadow mode: logs what it WOULD do, never declines or blocks. Start here, then switch to ENFORCE |
| Priority | lower number runs first |
| On error | SKIP = ignore a broken algo (fail-open), DECLINE = fail-closed |

### Python

```python
if tx.channel == 'ATM' and tx.amount > 20000 and (tx.hour >= 23 or tx.hour < 5):
    decline('57', 'High value ATM cash at night')

if history.declines('10m', 'card') >= 3:
    block_card('3 declines in 10 minutes', '62')

if customer.risk == 'HIGH' and tx.is_foreign and tx.amount > 20000:
    block_customer('HIGH risk customer abroad', '62')

if customer.is_vip and tx.amount < 50000:
    approve('VIP allow-list')        # stops the other algos; PIN, balance and limits still apply

flag('just watch this one')          # logs a warning, the transaction continues
return True                          # applies the default action set in the form
```

Decisions: `approve()`, `decline(rc, msg)`, `block_card(msg, rc)`, `block_customer(msg, rc)`, `flag(msg)`, `log(text)`.
`history.count / declines / approved / sum_amount / distinct / last` and `sql("SELECT ...", **params)` are available.
History excludes the transaction being authorized.

Not allowed: imports, `while`, `class`, `**`, file / network access, names starting with `_`. `range()` is limited to 2000 items.
Each run has a 400 ms / instruction budget.

### SQL

One read-only SELECT. It matches when the first column of the first row is true / non-zero.

```sql
SELECT COUNT(*) >= 3 FROM transactions
WHERE card_id = :card_id AND authorization_status = 'DECLINED' AND transaction_datetime >= :since_15m
```

Or choose the outcome from SQL by returning the columns `action`, `response_code`, `message`:

```sql
SELECT 'BLOCK_CARD' AS action, '62' AS response_code, 'Many terminals' AS message
WHERE (SELECT COUNT(DISTINCT terminal_id) FROM transactions
       WHERE card_id = :card_id AND transaction_datetime >= :since_1h) >= 4
```

### Fields Reference button

Lists every field (Python path and SQL parameter), the helpers and the SQL tables. Click a name to insert it in the editor.
Examples: `tx.amount`, `tx.hour` (terminal time from DE12, else host clock), `tx.host_hour` (always host clock),
`tx.channel`, `terminal.owner`, `bank.name`, `profile.auth_name`, `customer.risk`, `card.status`, `account.balance`.

### Actions

| Action | Effect (ENFORCE mode) |
|---|---|
| DECLINE | declines with the response code |
| BLOCK_CARD | sets the card to BLOCKED (audit logged) and declines; later transactions decline with 05 |
| BLOCK_CUSTOMER | sets the customer to BLOCKED (audit logged) and declines |
| APPROVE | risk-layer allow-list: skips the remaining algos. It never bypasses PIN, HSM, limit or balance checks |
| FLAG | writes a warning to the system log and continues |

Every save keeps a version (History button) that you can restore. The execution log lists matches and errors.

## Operations

* Host clock offset: set the environment variable `HOST_UTC_OFFSET_HOURS` (default 6).
* A bug in an algo or in the policy engine can never take the host down: errors are logged and the transaction continues
  (unless the algo is set to fail-closed).
* Algos are written by an authenticated administrator and run inside the host process in a restricted sandbox.
  Keep the admin login private.
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


banner("PATCH 7/7  Rules & Checks tab, friendly algo errors, built-in check fix, menu 7.5 retired")

# ======================================================================== BACKEND
# 1. router: friendly validation (no more raw 422) + built-in checks + simple-rule helpers
write_new("backend/app/local_host_router.py", "backend/app/local_host_router.py (friendly errors + /checks + /rules)",
          "REST API of the Rajon Local Host control center", LOCAL_HOST_ROUTER_PY)

# 2. engine: the built-in switches really switch the check off
edit("backend/app/host_engine.py", "host_engine.py: a switched-off built-in check is really skipped", "# [PATCH rules_checks:is_rule_enabled]",
'''            .filter(
                HostParameter.parameter_group == "RAJON_AUTH_RULES",
                HostParameter.parameter_name == param_name,
                HostParameter.active == True,  # noqa: E712
            )
            .first()
        )
        if not param:
            return default
        val = param.parameter_value''',
'''            .filter(
                HostParameter.parameter_group == "RAJON_AUTH_RULES",
                HostParameter.parameter_name == param_name,
            )
            .first()
        )
        if not param:
            return default
        # [PATCH rules_checks:is_rule_enabled]
        # an inactive parameter means the check was switched OFF (the old page used to set active = false,
        # but the engine only looked at active rows, so the check silently stayed ON)
        if not param.active:
            return False
        val = param.parameter_value''')

# 3. schema: a simple rule can be edited without losing its builder conditions
edit("backend/app/schemas.py", "schemas.py: AuthorizerRuleUpdate accepts rule_mode / conditions_json", "# [PATCH rules_checks:rule_update]",
'''    stop_on_match: Optional[bool] = None
    enabled: Optional[bool] = None


class AuthorizerRuleOut(AuthorizerRuleCreate):''',
'''    stop_on_match: Optional[bool] = None
    enabled: Optional[bool] = None
    # [PATCH rules_checks:rule_update]
    rule_mode: Optional[str] = None
    conditions_json: Optional[Dict[str, Any]] = None


class AuthorizerRuleOut(AuthorizerRuleCreate):''')

# ======================================================================== FRONTEND
D = "frontend/src/pages/hostcontrol/"
write_new(D + "RulesAndChecksTab.tsx", "hostcontrol/RulesAndChecksTab.tsx (new)", "RULES & CHECKS", HC_RULES_TSX)
write_new(D + "HostControlCenterPage.tsx", "hostcontrol/HostControlCenterPage.tsx (Rules & Checks tab)", "RAJON HOST CONTROL CENTER", HC_PAGE_TSX)
write_new(D + "AlgoControlTab.tsx", "hostcontrol/AlgoControlTab.tsx (required-field hints, scope help)", "ALGO CONTROL  - Python / SQL risk blocks", HC_ALGO_TSX)

# readable error messages for every page (a 422 used to show as "[object Object]")
edit("frontend/src/api.ts", "api.ts: readable validation errors", "// [PATCH friendly_422]",
'''      errText = errData.detail || JSON.stringify(errData);
''',
'''      // [PATCH friendly_422]
      const d = errData.detail;
      if (Array.isArray(d)) {
        errText = d
          .map((x: any) => `${(x.loc || []).filter((p: any) => p !== 'body').join('.')}: ${x.msg}`)
          .join('; ');
      } else {
        errText = typeof d === 'string' ? d : d ? JSON.stringify(d) : JSON.stringify(errData);
      }
''')

# menu 7.5 is replaced by 14. Host Control Center (old bookmarks are redirected)
edit("frontend/src/components/Layout.tsx", "Layout.tsx: remove menu 7.5 Authorizer Rules", None,
     "  { to: '/authorizer-rules', label: '7.5. Authorizer Rules', icon: Sliders, group: 'SWITCH & SIMULATOR' },\n", "")
edit("frontend/src/App.tsx", "App.tsx: /authorizer-rules redirects to the Host Control Center", None,
     "              <AuthorizerRulesPage />\n",
     "              <Navigate to=\"/host-config\" replace />\n")

# ======================================================================== TESTS + GUIDE
write_new("backend/tests/test_local_host.py", "backend/tests/test_local_host.py (updated)",
          "def test_default_policy_does_not_change_existing_behaviour", TEST_LOCAL_HOST_PY)
write_new("docs/HOST_CONTROL_CENTER.md", "docs/HOST_CONTROL_CENTER.md (updated guide)",
          "Rajon Host Control Center - quick guide", GUIDE_MD)

finish([
    "Restart the backend, rebuild / restart the frontend and hard-refresh the browser.",
    "Menu 7.5 is gone: everything is in  14. Host Control Center  ->  Rules & Checks.",
])
