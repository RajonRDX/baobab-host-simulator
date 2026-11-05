"""
simulator_workbench_router.py

Backend support for the upgraded Transaction Simulator workbench:

  * GET    /api/simulator-workbench/next-ids   last STAN (DE11) / RRN (DE37) found in the
                                               transactions table and the next free values
  * GET    /api/simulator-workbench/cases      list saved simulator cases
  * GET    /api/simulator-workbench/cases/{id} read one saved case
  * POST   /api/simulator-workbench/cases      save a new case (409 if the name exists
                                               and overwrite is not requested)
  * PUT    /api/simulator-workbench/cases/{id} update a saved case
  * DELETE /api/simulator-workbench/cases/{id} delete a saved case

The saved-case table is created automatically at start-up by the existing schema
synchroniser, because this module registers its model on the shared SQLAlchemy Base
before init_db() runs.
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.database import Base, get_db
from app.models import Transaction, gen_uuid, utc_now
from app.security import get_current_user

router = APIRouter(prefix="/api/simulator-workbench", tags=["Simulator Workbench"])

DEFAULT_STAN = "100001"
DEFAULT_RRN = "000020526001"


# ==============================================================================
# MODEL
# ==============================================================================
class SimulatorSavedCase(Base):
    __tablename__ = "simulator_saved_cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    mti: Mapped[str] = mapped_column(String(4), nullable=False, default="0200")
    transaction_code: Mapped[Optional[str]] = mapped_column(String(20))
    clear_pin_helper: Mapped[Optional[str]] = mapped_column(String(32))
    fields: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    enabled_fields: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


# ==============================================================================
# SCHEMAS
# ==============================================================================
class SavedCaseIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: Optional[str] = Field(None, max_length=2000)
    mti: str = Field("0200", min_length=4, max_length=4)
    transaction_code: Optional[str] = None
    clear_pin_helper: Optional[str] = None
    fields: Dict[str, str] = Field(default_factory=dict)
    enabled_fields: Dict[str, bool] = Field(default_factory=dict)
    overwrite: bool = False


# ==============================================================================
# HELPERS
# ==============================================================================
def increment_trailing_number(value: Optional[str], default: str) -> str:
    """
    Add 1 to the trailing run of digits in `value`, keeping its width.
    '100023' -> '100024'   '000020526009' -> '000020526010'   'ABC0099' -> 'ABC0100'
    A value without digits is returned unchanged; an empty value returns `default`.
    """
    v = (value or "").strip()
    if not v:
        return default
    m = re.search(r"(\d+)$", v)
    if not m:
        return v
    digits = m.group(1)
    bumped = str(int(digits) + 1).zfill(len(digits))
    if len(bumped) > len(digits):  # overflow -> wrap, keep fixed width
        bumped = "1".zfill(len(digits))
    return v[: m.start(1)] + bumped


def _serialize_case(c: SimulatorSavedCase, include_fields: bool = True) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "id": c.id,
        "name": c.name,
        "description": c.description or "",
        "mti": c.mti,
        "transaction_code": c.transaction_code,
        "field_count": len(c.fields or {}),
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }
    if include_fields:
        data["clear_pin_helper"] = c.clear_pin_helper or ""
        data["fields"] = c.fields or {}
        data["enabled_fields"] = c.enabled_fields or {}
    return data


def _apply_payload(case: SimulatorSavedCase, payload: SavedCaseIn) -> None:
    case.name = payload.name.strip()
    case.description = (payload.description or "").strip() or None
    case.mti = payload.mti
    case.transaction_code = payload.transaction_code
    case.clear_pin_helper = payload.clear_pin_helper or None
    case.fields = dict(payload.fields)
    case.enabled_fields = dict(payload.enabled_fields)


# ==============================================================================
# LAST / NEXT STAN & RRN
# ==============================================================================
@router.get("/next-ids")
def get_next_ids(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    last = db.query(Transaction).order_by(Transaction.created_at.desc()).first()
    if not last:
        return {
            "has_history": False,
            "last_stan": None,
            "last_rrn": None,
            "next_stan": DEFAULT_STAN,
            "next_rrn": DEFAULT_RRN,
            "last_transaction": None,
        }
    next_stan = increment_trailing_number(last.stan, DEFAULT_STAN)
    if len(next_stan) == 6 and next_stan.isdigit() and int(next_stan) == 0:
        next_stan = "000001"  # DE11 must never be all zeros
    return {
        "has_history": True,
        "last_stan": last.stan,
        "last_rrn": last.rrn,
        "next_stan": next_stan,
        "next_rrn": increment_trailing_number(last.rrn, DEFAULT_RRN),
        "last_transaction": {
            "transaction_reference": last.transaction_reference,
            "mti": last.mti,
            "masked_pan": last.masked_pan,
            "response_code": last.response_code,
            "created_at": last.created_at.isoformat() if last.created_at else None,
        },
    }


# ==============================================================================
# SAVED CASES
# ==============================================================================
@router.get("/cases")
def list_cases(db: Session = Depends(get_db), _: str = Depends(get_current_user)) -> List[Dict[str, Any]]:
    rows = db.query(SimulatorSavedCase).order_by(SimulatorSavedCase.updated_at.desc()).all()
    return [_serialize_case(c, include_fields=True) for c in rows]


@router.get("/cases/{case_id}")
def get_case(case_id: str, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    case = db.query(SimulatorSavedCase).filter(SimulatorSavedCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Saved case not found")
    return _serialize_case(case)


@router.post("/cases")
def create_case(payload: SavedCaseIn, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Case name is required")
    existing = db.query(SimulatorSavedCase).filter(SimulatorSavedCase.name == name).first()
    if existing and not payload.overwrite:
        raise HTTPException(status_code=409, detail=f"A case named '{name}' already exists")
    case = existing or SimulatorSavedCase()
    _apply_payload(case, payload)
    if not existing:
        db.add(case)
    db.commit()
    db.refresh(case)
    return _serialize_case(case)


@router.put("/cases/{case_id}")
def update_case(
    case_id: str,
    payload: SavedCaseIn,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    case = db.query(SimulatorSavedCase).filter(SimulatorSavedCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Saved case not found")
    new_name = payload.name.strip()
    clash = (
        db.query(SimulatorSavedCase)
        .filter(SimulatorSavedCase.name == new_name, SimulatorSavedCase.id != case_id)
        .first()
    )
    if clash:
        raise HTTPException(status_code=409, detail=f"A case named '{new_name}' already exists")
    _apply_payload(case, payload)
    db.commit()
    db.refresh(case)
    return _serialize_case(case)


@router.delete("/cases/{case_id}")
def delete_case(case_id: str, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    case = db.query(SimulatorSavedCase).filter(SimulatorSavedCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Saved case not found")
    db.delete(case)
    db.commit()
    return {"status": "deleted", "id": case_id}
