"""
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
