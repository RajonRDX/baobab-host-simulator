"""
INSTITUTIONS ROUTER — Processing Systems, Member Banks, Network Links, BIN Ranges & PAN Router
Enterprise-grade validation, overlap detection, relational integrity checks, and audit trail logging.
"""

import re
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.audit_service import record_audit, serialize_entity
from app.database import get_db
from app.models import (
    Account,
    BinRange,
    Card,
    Customer,
    HsmKeyReference,
    Institution,
    InstitutionProcessingSystem,
    PanRoutingRule,
    ProcessingSystem,
    Transaction,
)
from app.schemas import (
    BinRangeCreate,
    BinRangeOut,
    BinRangeUpdate,
    InstitutionCreate,
    InstitutionOut,
    InstitutionProcessingSystemCreate,
    InstitutionProcessingSystemOut,
    InstitutionUpdate,
    PanRoutingRuleCreate,
    PanRoutingRuleOut,
    PanRoutingRuleUpdate,
    ProcessingSystemCreate,
    ProcessingSystemOut,
    ProcessingSystemUpdate,
)
from app.security import get_current_user

router = APIRouter(prefix="/api", tags=["Institutions, Switches, BINs & PAN Router"])


def clean_bank_short_code(code_or_short: Optional[str], fallback: str = "XBANK") -> str:
    """
    Returns the clean bank short-code (e.g. BAL, TBL, IFIC, XBANK) without composite
    suffixes like 'BAL - IFIC' or 'TBL - IFIC'. Never alters the stored legal name.
    """
    raw = (code_or_short or "").strip()
    if not raw:
        return fallback
    for sep in (" - ", " — ", " – ", "/"):
        if sep in raw:
            part = raw.split(sep)[0].strip()
            if part:
                return part.upper()
    return raw.upper()


# ==============================================================================
# 1. PROCESSING SYSTEMS (SWITCHES)
# ==============================================================================

@router.get("/processing-systems", response_model=List[ProcessingSystemOut])
def list_processing_systems(
    q: Optional[str] = Query(None, description="Search by PS code, name, type, or format"),
    system_type: Optional[str] = Query(None),
    enabled: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    query = db.query(ProcessingSystem)
    if q:
        term = f"%{q.strip()}%"
        query = query.filter(
            (ProcessingSystem.ps_code.ilike(term))
            | (ProcessingSystem.name.ilike(term))
            | (ProcessingSystem.system_type.ilike(term))
            | (ProcessingSystem.message_format.ilike(term))
        )
    if system_type:
        query = query.filter(ProcessingSystem.system_type == system_type.upper().strip())
    if enabled is not None:
        query = query.filter(ProcessingSystem.enabled == enabled)
    return query.order_by(ProcessingSystem.ps_code.asc()).all()


@router.get("/processing-systems/{ps_id}", response_model=ProcessingSystemOut)
def get_processing_system(ps_id: str, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    ps = db.query(ProcessingSystem).filter(ProcessingSystem.id == ps_id).first()
    if not ps:
        raise HTTPException(status_code=404, detail="Processing system not found")
    return ps


@router.post("/processing-systems", response_model=ProcessingSystemOut)
def create_processing_system(
    payload: ProcessingSystemCreate,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    ps_code = payload.ps_code.strip().upper()
    if not re.fullmatch(r"[A-Z0-9_\-]{2,30}", ps_code):
        raise HTTPException(status_code=400, detail="Processing switch code must be 2-30 alphanumeric characters")

    existing = db.query(ProcessingSystem).filter(ProcessingSystem.ps_code == ps_code).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Processing system '{ps_code}' already exists")

    if payload.is_default:
        db.query(ProcessingSystem).update({"is_default": False}, synchronize_session=False)

    ps = ProcessingSystem(
        ps_code=ps_code,
        name=payload.name.strip(),
        system_type=payload.system_type.strip().upper(),
        message_format=payload.message_format.strip().upper(),
        enabled=payload.enabled,
        is_default=payload.is_default,
        configuration=payload.configuration or {},
    )
    db.add(ps)
    db.flush()
    record_audit(
        db,
        "PROCESSING_SYSTEM",
        ps.id,
        "CREATE",
        performed_by=current_user,
        after_state=serialize_entity(ps),
        change_summary=f"Created processing switch {ps.ps_code} ({ps.name})",
    )
    db.commit()
    db.refresh(ps)
    return ps


@router.put("/processing-systems/{ps_id}", response_model=ProcessingSystemOut)
def update_processing_system(
    ps_id: str,
    payload: ProcessingSystemUpdate,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    ps = db.query(ProcessingSystem).filter(ProcessingSystem.id == ps_id).first()
    if not ps:
        raise HTTPException(status_code=404, detail="Processing system not found")

    before = serialize_entity(ps)
    data = payload.model_dump(exclude_unset=True)

    if data.get("enabled") is False and ps.is_default:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot disable the primary default switch ({ps.ps_code}). Promote another switch to default first.",
        )

    if data.get("is_default") is True:
        db.query(ProcessingSystem).filter(ProcessingSystem.id != ps.id).update(
            {"is_default": False}, synchronize_session=False
        )

    for k, v in data.items():
        if isinstance(v, str) and k in ("system_type", "message_format"):
            setattr(ps, k, v.strip().upper())
        elif isinstance(v, str) and k == "name":
            setattr(ps, k, v.strip())
        else:
            setattr(ps, k, v)

    after = serialize_entity(ps)
    record_audit(
        db,
        "PROCESSING_SYSTEM",
        ps.id,
        "UPDATE",
        performed_by=current_user,
        before_state=before,
        after_state=after,
        change_summary=f"Updated processing switch {ps.ps_code}",
    )
    db.commit()
    db.refresh(ps)
    return ps


@router.patch("/processing-systems/{ps_id}/toggle", response_model=ProcessingSystemOut)
def toggle_processing_system(
    ps_id: str,
    enabled: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    ps = db.query(ProcessingSystem).filter(ProcessingSystem.id == ps_id).first()
    if not ps:
        raise HTTPException(status_code=404, detail="Processing system not found")

    next_state = (not ps.enabled) if enabled is None else bool(enabled)
    if not next_state and ps.is_default:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot disable primary default processing switch ({ps.ps_code}).",
        )

    before = serialize_entity(ps)
    ps.enabled = next_state
    after = serialize_entity(ps)
    record_audit(
        db,
        "PROCESSING_SYSTEM",
        ps.id,
        "STATUS_CHANGE",
        performed_by=current_user,
        before_state=before,
        after_state=after,
        change_summary=f"{'Enabled' if next_state else 'Disabled'} processing switch {ps.ps_code}",
    )
    db.commit()
    db.refresh(ps)
    return ps


@router.delete("/processing-systems/{ps_id}")
def delete_processing_system(
    ps_id: str,
    deactivate_only: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    ps = db.query(ProcessingSystem).filter(ProcessingSystem.id == ps_id).first()
    if not ps:
        raise HTTPException(status_code=404, detail="Processing system not found")

    if ps.is_default:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete or deactivate the primary default processing switch ({ps.ps_code}).",
        )

    inst_count = db.query(Institution).filter(Institution.processing_system_id == ps.id).count()
    bin_count = db.query(BinRange).filter(BinRange.processing_system_id == ps.id).count()
    route_count = db.query(PanRoutingRule).filter(PanRoutingRule.processing_system_id == ps.id).count()
    tx_count = db.query(Transaction).filter(Transaction.ps_code == ps.ps_code).count()

    if deactivate_only:
        before = serialize_entity(ps)
        ps.enabled = False
        record_audit(
            db,
            "PROCESSING_SYSTEM",
            ps.id,
            "DEACTIVATE",
            performed_by=current_user,
            before_state=before,
            after_state=serialize_entity(ps),
            change_summary=f"Deactivated processing switch {ps.ps_code}",
        )
        db.commit()
        return {
            "status": "deactivated",
            "ps_id": ps.id,
            "ps_code": ps.ps_code,
            "message": f"Processing switch {ps.ps_code} has been safely disabled.",
        }

    if inst_count > 0 or bin_count > 0 or route_count > 0 or tx_count > 0:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot hard-delete processing switch '{ps.ps_code}' because it is referenced by "
                f"{inst_count} bank(s), {bin_count} BIN range(s), {route_count} PAN routing rule(s), "
                f"and {tx_count} historical transaction(s). Disable/deactivate the switch instead."
            ),
        )

    before = serialize_entity(ps)
    db.delete(ps)
    record_audit(
        db,
        "PROCESSING_SYSTEM",
        ps_id,
        "DELETE",
        performed_by=current_user,
        before_state=before,
        change_summary=f"Deleted processing switch {ps.ps_code}",
    )
    db.commit()
    return {"status": "deleted", "ps_id": ps_id, "ps_code": ps.ps_code}


# ==============================================================================
# 2. INSTITUTIONS (MEMBER BANKS)
# ==============================================================================

def _serialize_institution(inst: Institution) -> Dict[str, Any]:
    short_clean = clean_bank_short_code(inst.short_name or inst.institution_code, inst.institution_code)
    code_clean = clean_bank_short_code(inst.institution_code, inst.institution_code)
    return {
        "id": inst.id,
        "institution_code": code_clean,
        "name": inst.name,
        "short_name": short_clean,
        "display_code": short_clean,
        "acquirer_id": inst.acquirer_id,
        "forwarding_id": inst.forwarding_id,
        "role": inst.role,
        "processing_system_id": inst.processing_system_id,
        "ps_code": inst.primary_processing_system.ps_code if inst.primary_processing_system else "ITCL",
        "ps_name": inst.primary_processing_system.name if inst.primary_processing_system else "ITCL Switch",
        "country_code": inst.country_code,
        "currency": inst.currency,
        "settlement_account_number": inst.settlement_account_number,
        "status": inst.status,
        "configuration": inst.configuration or {},
        "created_at": inst.created_at,
        "updated_at": inst.updated_at,
    }


@router.get("/institutions", response_model=List[InstitutionOut])
def list_institutions(
    q: Optional[str] = Query(None, description="Search by bank code, short name, legal name, or DE32 acquirer ID"),
    status: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    ps_code: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    query = db.query(Institution)
    if q:
        term = f"%{q.strip()}%"
        query = query.filter(
            (Institution.institution_code.ilike(term))
            | (Institution.short_name.ilike(term))
            | (Institution.name.ilike(term))
            | (Institution.acquirer_id.ilike(term))
        )
    if status:
        query = query.filter(Institution.status == status.upper().strip())
    if role:
        query = query.filter(Institution.role == role.upper().strip())
    if ps_code:
        ps_obj = db.query(ProcessingSystem).filter(ProcessingSystem.ps_code == ps_code.upper().strip()).first()
        if ps_obj:
            query = query.filter(Institution.processing_system_id == ps_obj.id)

    insts = query.order_by(Institution.institution_code.asc()).all()
    return [_serialize_institution(i) for i in insts]


@router.get("/institutions/{inst_id}", response_model=InstitutionOut)
def get_institution(inst_id: str, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    inst = db.query(Institution).filter(Institution.id == inst_id).first()
    if not inst:
        raise HTTPException(status_code=404, detail="Institution not found")
    return _serialize_institution(inst)


@router.post("/institutions", response_model=InstitutionOut)
def create_institution(
    payload: InstitutionCreate,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    icode = clean_bank_short_code(payload.institution_code)
    if not icode:
        raise HTTPException(status_code=400, detail="Institution code is required")

    existing = db.query(Institution).filter(Institution.institution_code == icode).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Institution '{icode}' already exists")

    ps_id = payload.processing_system_id
    if not ps_id:
        ps_code_target = (payload.ps_code or "ITCL").upper()
        ps = db.query(ProcessingSystem).filter(ProcessingSystem.ps_code == ps_code_target).first()
        if not ps:
            ps = db.query(ProcessingSystem).filter(ProcessingSystem.ps_code == "ITCL").first()
        if not ps:
            raise HTTPException(status_code=500, detail="Default ITCL processing system not found in database")
        ps_id = ps.id
    else:
        ps = db.query(ProcessingSystem).filter(ProcessingSystem.id == ps_id).first()
        if not ps:
            raise HTTPException(status_code=404, detail="Specified processing system not found")

    short_val = clean_bank_short_code(payload.short_name or icode, icode)

    inst = Institution(
        institution_code=icode,
        name=payload.name.strip(),
        short_name=short_val,
        acquirer_id=payload.acquirer_id.strip(),
        forwarding_id=(payload.forwarding_id or payload.acquirer_id).strip(),
        role=payload.role.upper().strip(),
        processing_system_id=ps_id,
        country_code=payload.country_code.strip(),
        currency=payload.currency.upper().strip(),
        settlement_account_number=payload.settlement_account_number,
        status=payload.status.upper().strip(),
        configuration=payload.configuration or {},
    )
    db.add(inst)
    db.flush()

    link = InstitutionProcessingSystem(
        institution_id=inst.id,
        processing_system_id=ps.id,
        card_profile_id=getattr(payload, 'card_profile_id', None) or None,
        member_id=f"{ps.ps_code}-{icode}",
        acquirer_id=inst.acquirer_id,
        network_identifier=f"{ps.ps_code}_HOST",
        issuer_enabled=True,
        acquirer_enabled=True,
        message_format=ps.message_format,
        routing_configuration={"is_primary_host": True},
        status="ACTIVE",
    )
    db.add(link)
    record_audit(
        db,
        "INSTITUTION",
        inst.id,
        "CREATE",
        performed_by=current_user,
        after_state=serialize_entity(inst),
        change_summary=f"Created bank {inst.institution_code} ({inst.name})",
    )
    db.commit()
    db.refresh(inst)
    return _serialize_institution(inst)


@router.put("/institutions/{inst_id}", response_model=InstitutionOut)
def update_institution(
    inst_id: str,
    payload: InstitutionUpdate,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    inst = db.query(Institution).filter(Institution.id == inst_id).first()
    if not inst:
        raise HTTPException(status_code=404, detail="Institution not found")

    before = serialize_entity(inst)
    data = payload.model_dump(exclude_unset=True)

    if "processing_system_id" in data and data["processing_system_id"]:
        ps = db.query(ProcessingSystem).filter(ProcessingSystem.id == data["processing_system_id"]).first()
        if not ps:
            raise HTTPException(status_code=404, detail="Target processing switch not found")

    if "short_name" in data and data["short_name"] is not None:
        data["short_name"] = clean_bank_short_code(data["short_name"], inst.institution_code)

    for k, v in data.items():
        setattr(inst, k, v)

    after = serialize_entity(inst)
    record_audit(
        db,
        "INSTITUTION",
        inst.id,
        "UPDATE",
        performed_by=current_user,
        before_state=before,
        after_state=after,
        change_summary=f"Updated bank {inst.institution_code} ({inst.name})",
    )
    db.commit()
    db.refresh(inst)
    return _serialize_institution(inst)


@router.patch("/institutions/{inst_id}/status", response_model=InstitutionOut)
def update_institution_status(
    inst_id: str,
    status: str = Query(..., description="ACTIVE | INACTIVE | SUSPENDED"),
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    inst = db.query(Institution).filter(Institution.id == inst_id).first()
    if not inst:
        raise HTTPException(status_code=404, detail="Institution not found")
    before = serialize_entity(inst)
    inst.status = status.upper().strip()
    after = serialize_entity(inst)
    record_audit(
        db,
        "INSTITUTION",
        inst.id,
        "STATUS_CHANGE",
        performed_by=current_user,
        before_state=before,
        after_state=after,
        change_summary=f"Changed bank {inst.institution_code} status to {inst.status}",
    )
    db.commit()
    db.refresh(inst)
    return _serialize_institution(inst)


@router.delete("/institutions/{inst_id}")
def delete_institution(
    inst_id: str,
    deactivate_only: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    inst = db.query(Institution).filter(Institution.id == inst_id).first()
    if not inst:
        raise HTTPException(status_code=404, detail="Institution not found")

    cust_count = db.query(Customer).filter(Customer.institution_id == inst.id).count()
    acct_count = db.query(Account).filter(Account.institution_id == inst.id).count()
    card_count = db.query(Card).filter(Card.institution_id == inst.id).count()
    bin_count = db.query(BinRange).filter(BinRange.institution_id == inst.id).count()
    route_count = db.query(PanRoutingRule).filter(
        (PanRoutingRule.issuer_institution_id == inst.id)
        | (PanRoutingRule.acquirer_institution_id == inst.id)
    ).count()
    tx_count = db.query(Transaction).filter(
        (Transaction.issuer_institution_id == inst.id)
        | (Transaction.acquirer_institution_id == inst.id)
    ).count()

    if deactivate_only:
        before = serialize_entity(inst)
        inst.status = "INACTIVE"
        record_audit(
            db,
            "INSTITUTION",
            inst.id,
            "DEACTIVATE",
            performed_by=current_user,
            before_state=before,
            after_state=serialize_entity(inst),
            change_summary=f"Deactivated bank {inst.institution_code} to preserve relational history",
        )
        db.commit()
        return {
            "status": "deactivated",
            "institution_id": inst.id,
            "institution_code": inst.institution_code,
            "message": f"Bank {inst.institution_code} deactivated safely.",
        }

    if any(cnt > 0 for cnt in (cust_count, acct_count, card_count, bin_count, route_count, tx_count)):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot hard-delete bank '{inst.institution_code}' because it has active/historical dependencies: "
                f"{cust_count} customer(s), {acct_count} account(s), {card_count} card(s), "
                f"{bin_count} BIN range(s), {route_count} PAN routing rule(s), and {tx_count} transaction(s). "
                f"Deactivate the bank instead to preserve historical and relational integrity."
            ),
        )

    before = serialize_entity(inst)
    db.delete(inst)
    record_audit(
        db,
        "INSTITUTION",
        inst_id,
        "DELETE",
        performed_by=current_user,
        before_state=before,
        change_summary=f"Deleted bank {inst.institution_code}",
    )
    db.commit()
    return {"status": "deleted", "institution_id": inst_id, "institution_code": inst.institution_code}


# ==============================================================================
# 3. INSTITUTION PROCESSING SYSTEM LINKS (MULTI-NETWORK MEMBERSHIPS)
# ==============================================================================

@router.get("/institutions/{inst_id}/networks", response_model=List[InstitutionProcessingSystemOut])
def list_institution_networks(inst_id: str, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    links = (
        db.query(InstitutionProcessingSystem)
        .filter(InstitutionProcessingSystem.institution_id == inst_id)
        .all()
    )
    out = []
    for l in links:
        icode = clean_bank_short_code(l.institution.short_name or l.institution.institution_code) if l.institution else None
        out.append({
            "id": l.id,
            "institution_id": l.institution_id,
            "institution_code": icode,
            "institution_name": l.institution.name if l.institution else None,
            "processing_system_id": l.processing_system_id,
            "ps_code": l.processing_system.ps_code if l.processing_system else None,
            "ps_name": l.processing_system.name if l.processing_system else None,
            "member_id": l.member_id,
            "acquirer_id": l.acquirer_id,
            "network_identifier": l.network_identifier,
            "issuer_enabled": l.issuer_enabled,
            "acquirer_enabled": l.acquirer_enabled,
            "message_format": l.message_format,
            "routing_configuration": l.routing_configuration or {},
            "status": l.status,
            "effective_from": l.effective_from,
            "effective_to": l.effective_to,
            "created_at": l.created_at,
            "updated_at": l.updated_at,
        })
    return out


@router.post("/institutions/{inst_id}/networks", response_model=InstitutionProcessingSystemOut)
def add_institution_network(
    inst_id: str,
    payload: InstitutionProcessingSystemCreate,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    inst = db.query(Institution).filter(Institution.id == inst_id).first()
    if not inst:
        raise HTTPException(status_code=404, detail="Institution not found")
    ps = db.query(ProcessingSystem).filter(ProcessingSystem.id == payload.processing_system_id).first()
    if not ps:
        raise HTTPException(status_code=404, detail="Processing system not found")

    existing = (
        db.query(InstitutionProcessingSystem)
        .filter(
            InstitutionProcessingSystem.institution_id == inst_id,
            InstitutionProcessingSystem.processing_system_id == payload.processing_system_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Institution is already linked to this processing system")

    link = InstitutionProcessingSystem(
        institution_id=inst_id,
        processing_system_id=payload.processing_system_id,
        member_id=payload.member_id,
        acquirer_id=payload.acquirer_id,
        network_identifier=payload.network_identifier,
        issuer_enabled=payload.issuer_enabled,
        acquirer_enabled=payload.acquirer_enabled,
        message_format=payload.message_format or ps.message_format,
        routing_configuration=payload.routing_configuration,
        status=payload.status,
    )
    db.add(link)
    db.flush()
    record_audit(
        db,
        "INSTITUTION_NETWORK",
        link.id,
        "CREATE",
        performed_by=current_user,
        after_state=serialize_entity(link),
        change_summary=f"Linked bank {inst.institution_code} to switch {ps.ps_code}",
    )
    db.commit()
    db.refresh(link)
    return {
        "id": link.id,
        "institution_id": link.institution_id,
        "institution_code": clean_bank_short_code(inst.short_name or inst.institution_code),
        "institution_name": inst.name,
        "processing_system_id": link.processing_system_id,
        "ps_code": ps.ps_code,
        "ps_name": ps.name,
        "member_id": link.member_id,
        "acquirer_id": link.acquirer_id,
        "network_identifier": link.network_identifier,
        "issuer_enabled": link.issuer_enabled,
        "acquirer_enabled": link.acquirer_enabled,
        "message_format": link.message_format,
        "routing_configuration": link.routing_configuration,
        "status": link.status,
        "effective_from": link.effective_from,
        "effective_to": link.effective_to,
        "created_at": link.created_at,
        "updated_at": link.updated_at,
    }


@router.delete("/institutions/networks/{link_id}")
def remove_institution_network(link_id: str, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    link = db.query(InstitutionProcessingSystem).filter(InstitutionProcessingSystem.id == link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Network link not found")
    before = serialize_entity(link)
    db.delete(link)
    record_audit(
        db,
        "INSTITUTION_NETWORK",
        link_id,
        "DELETE",
        performed_by=current_user,
        before_state=before,
        change_summary=f"Removed institution network membership {link.member_id}",
    )
    db.commit()
    return {"status": "deleted", "link_id": link_id}


# ==============================================================================
# 4. BIN RANGES (WITH BOUNDARY & OVERLAP VALIDATION)
# ==============================================================================

def _normalize_range_bounds(prefix: str, low_in: Optional[str], high_in: Optional[str], pan_len: int = 16) -> tuple[str, str]:
    clean_pfx = re.sub(r"\D", "", prefix or "")
    if len(clean_pfx) < 6 or len(clean_pfx) > 12:
        raise HTTPException(status_code=400, detail="BIN/IIN prefix must be between 6 and 12 numeric digits")
    if pan_len < 12 or pan_len > 19:
        raise HTTPException(status_code=400, detail="PAN length must be between 12 and 19 digits")

    low_raw = re.sub(r"\D", "", low_in) if low_in else clean_pfx.ljust(pan_len, "0")
    high_raw = re.sub(r"\D", "", high_in) if high_in else clean_pfx.ljust(pan_len, "9")

    low_norm = low_raw.ljust(19, "0")[:19]
    high_norm = high_raw.ljust(19, "9")[:19]

    if low_norm > high_norm:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid BIN range boundaries: bin_low ({low_raw}) cannot be greater than bin_high ({high_raw})",
        )
    return low_raw, high_raw


def _check_bin_overlap(
    db: Session,
    prefix: str,
    low_raw: str,
    high_raw: str,
    exclude_bin_id: Optional[str] = None,
) -> None:
    low_19 = low_raw.ljust(19, "0")[:19]
    high_19 = high_raw.ljust(19, "9")[:19]

    query = db.query(BinRange)
    if exclude_bin_id:
        query = query.filter(BinRange.id != exclude_bin_id)

    for existing in query.all():
        if existing.bin_prefix == prefix:
            raise HTTPException(
                status_code=409,
                detail=f"Duplicate BIN prefix '{prefix}' already exists (assigned to {existing.institution.institution_code if existing.institution else 'another bank'}).",
            )
        ex_low = (existing.bin_low or existing.bin_prefix).ljust(19, "0")[:19]
        ex_high = (existing.bin_high or existing.bin_prefix).ljust(19, "9")[:19]
        if not (high_19 < ex_low or low_19 > ex_high):
            bank_label = clean_bank_short_code(
                existing.institution.short_name or existing.institution.institution_code
                if existing.institution else "UNKNOWN"
            )
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Overlapping BIN range detected: [{low_raw} .. {high_raw}] conflicts with existing "
                    f"BIN {existing.bin_prefix} [{existing.bin_low} .. {existing.bin_high}] owned by {bank_label}."
                ),
            )


def _serialize_bin(b: BinRange) -> Dict[str, Any]:
    bank_short = clean_bank_short_code(
        b.institution.short_name or b.institution.institution_code if b.institution else None,
        "XBANK",
    )
    return {
        "id": b.id,
        "bin_prefix": b.bin_prefix,
        "bin_low": b.bin_low,
        "bin_high": b.bin_high,
        "pan_length": b.pan_length,
        "institution_id": b.institution_id,
        "institution_code": bank_short,
        "institution_name": b.institution.name if b.institution else None,
        "processing_system_id": b.processing_system_id,
        "ps_code": b.processing_system.ps_code if b.processing_system else None,
        "ps_name": b.processing_system.name if b.processing_system else None,
        "card_type": b.card_type,
        "card_product": b.card_product,
        "scheme": b.scheme,
        "country_code": b.country_code,
        "currency": b.currency,
        # [PATCH step13_03:bins_include_card_profile]
        "card_profile_id": getattr(b, "card_profile_id", None),
        "card_profile_code": b.card_profile.profile_code if getattr(b, "card_profile", None) else None,
        "card_profile_name": b.card_profile.profile_name if getattr(b, "card_profile", None) else None,
        "is_on_us": b.is_on_us,
        "status": b.status,
        "created_at": b.created_at,
        "updated_at": b.updated_at,
    }


@router.get("/bin-ranges", response_model=List[BinRangeOut])
def list_bin_ranges(
    q: Optional[str] = Query(None, description="Search by BIN prefix, product, bank, or scheme"),
    institution_id: Optional[str] = Query(None),
    card_type: Optional[str] = Query(None),
    scheme: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    query = db.query(BinRange)
    if institution_id:
        query = query.filter(BinRange.institution_id == institution_id)
    if card_type:
        query = query.filter(BinRange.card_type == card_type.upper().strip())
    if scheme:
        query = query.filter(BinRange.scheme == scheme.upper().strip())
    if status:
        query = query.filter(BinRange.status == status.upper().strip())

    bins = query.order_by(BinRange.bin_prefix.asc()).all()
    serialized = [_serialize_bin(b) for b in bins]
    if q:
        term = q.strip().lower()
        serialized = [
            item for item in serialized
            if term in (item["bin_prefix"] or "").lower()
            or term in (item["card_product"] or "").lower()
            or term in (item["institution_code"] or "").lower()
            or term in (item["institution_name"] or "").lower()
            or term in (item["scheme"] or "").lower()
            or term in (item["ps_code"] or "").lower()
        ]
    return serialized


@router.get("/bin-ranges/lookup/{pan}")
def lookup_bin_for_pan(
    pan: str,
    acquirer_id: Optional[str] = Query("123456"),
    transaction_code: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    from app.network_adapter import resolve_transaction_routing

    clean_pan = "".join(ch for ch in pan if ch.isdigit())
    if len(clean_pan) < 6:
        raise HTTPException(status_code=400, detail="PAN is too short for BIN lookup (minimum 6 numeric digits)")

    routing = resolve_transaction_routing(db, clean_pan, acquirer_id or "123456", transaction_code=transaction_code)
    if not routing.get("matched_record"):
        return {
            "found": False,
            "pan_masked": clean_pan[:6] + "*" * max(0, len(clean_pan) - 10) + clean_pan[-4:] if len(clean_pan) >= 10 else "****",
            "message": routing.get("message") or "No active BIN range or PAN routing rule matched. Defaulting to On-Us ITCL switch.",
            "routing": routing,
        }

    return {
        "found": True,
        "match_source": routing.get("match_source", "BIN_RANGE"),
        "rule_code": routing.get("rule_code"),
        "bin_prefix": routing["bin_prefix"],
        "institution": routing["institution"],
        "processing_system": routing["processing_system"],
        "card_product": routing["card_product"],
        "card_type": routing.get("card_type", "DEBIT"),
        "scheme": routing["scheme"],
        "is_on_us": routing["is_on_us"],
        "destination_network": routing.get("destination_network"),
        "routing": routing,
    }


@router.post("/bin-ranges", response_model=BinRangeOut)
def create_bin_range(
    payload: BinRangeCreate,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    prefix = re.sub(r"\D", "", payload.bin_prefix.strip())
    low_raw, high_raw = _normalize_range_bounds(prefix, payload.bin_low, payload.bin_high, payload.pan_length)

    inst = db.query(Institution).filter(Institution.id == payload.institution_id).first()
    if not inst:
        raise HTTPException(status_code=404, detail="Owning institution (bank) not found")

    ps_id = payload.processing_system_id or inst.processing_system_id
    ps = db.query(ProcessingSystem).filter(ProcessingSystem.id == ps_id).first()
    if not ps:
        raise HTTPException(status_code=404, detail="Processing switch not found")

    _check_bin_overlap(db, prefix, low_raw, high_raw)

    b = BinRange(
        bin_prefix=prefix,
        bin_low=low_raw,
        bin_high=high_raw,
        pan_length=payload.pan_length,
        institution_id=inst.id,
        processing_system_id=ps.id,
        card_type=payload.card_type.upper().strip(),
        card_product=payload.card_product.strip(),
        scheme=payload.scheme.upper().strip(),
        country_code=payload.country_code.strip(),
        currency=payload.currency.upper().strip(),
        is_on_us=payload.is_on_us,
        status=payload.status.upper().strip(),
    )
    db.add(b)
    db.flush()
    record_audit(
        db,
        "BIN_RANGE",
        b.id,
        "CREATE",
        performed_by=current_user,
        after_state=serialize_entity(b),
        change_summary=f"Created BIN range {b.bin_prefix} for {inst.institution_code}",
    )
    db.commit()
    db.refresh(b)
    return _serialize_bin(b)


@router.put("/bin-ranges/{bin_id}", response_model=BinRangeOut)
def update_bin_range(
    bin_id: str,
    payload: BinRangeUpdate,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    b = db.query(BinRange).filter(BinRange.id == bin_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="BIN range not found")

    before = serialize_entity(b)
    data = payload.model_dump(exclude_unset=True)

    new_prefix = re.sub(r"\D", "", data.get("bin_prefix", b.bin_prefix))
    new_len = int(data.get("pan_length", b.pan_length))
    new_low_in = data.get("bin_low", b.bin_low if "bin_prefix" not in data else None)
    new_high_in = data.get("bin_high", b.bin_high if "bin_prefix" not in data else None)

    low_raw, high_raw = _normalize_range_bounds(new_prefix, new_low_in, new_high_in, new_len)
    _check_bin_overlap(db, new_prefix, low_raw, high_raw, exclude_bin_id=b.id)

    if "institution_id" in data and data["institution_id"]:
        inst = db.query(Institution).filter(Institution.id == data["institution_id"]).first()
        if not inst:
            raise HTTPException(status_code=404, detail="Referenced institution not found")

    if "processing_system_id" in data and data["processing_system_id"]:
        ps = db.query(ProcessingSystem).filter(ProcessingSystem.id == data["processing_system_id"]).first()
        if not ps:
            raise HTTPException(status_code=404, detail="Referenced processing system not found")

    b.bin_prefix = new_prefix
    b.bin_low = low_raw
    b.bin_high = high_raw
    b.pan_length = new_len

    if "card_profile_id" in data:
        b.card_profile_id = data["card_profile_id"] or None

    for k in ("institution_id", "processing_system_id", "card_type", "card_product", "scheme", "country_code", "currency", "is_on_us", "status"):
        if k in data and data[k] is not None:
            val = data[k]
            if isinstance(val, str) and k in ("card_type", "scheme", "currency", "status"):
                val = val.upper().strip()
            setattr(b, k, val)

    after = serialize_entity(b)
    record_audit(
        db,
        "BIN_RANGE",
        b.id,
        "UPDATE",
        performed_by=current_user,
        before_state=before,
        after_state=after,
        change_summary=f"Updated BIN range {b.bin_prefix}",
    )
    db.commit()
    db.refresh(b)
    return _serialize_bin(b)


@router.patch("/bin-ranges/{bin_id}/status", response_model=BinRangeOut)
def toggle_bin_range_status(
    bin_id: str,
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    b = db.query(BinRange).filter(BinRange.id == bin_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="BIN range not found")
    before = serialize_entity(b)
    next_status = status.upper().strip() if status else ("INACTIVE" if b.status == "ACTIVE" else "ACTIVE")
    b.status = next_status
    after = serialize_entity(b)
    record_audit(
        db,
        "BIN_RANGE",
        b.id,
        "STATUS_CHANGE",
        performed_by=current_user,
        before_state=before,
        after_state=after,
        change_summary=f"Changed BIN range {b.bin_prefix} status to {b.status}",
    )
    db.commit()
    db.refresh(b)
    return _serialize_bin(b)


@router.delete("/bin-ranges/{bin_id}")
def delete_bin_range(
    bin_id: str,
    deactivate_only: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    b = db.query(BinRange).filter(BinRange.id == bin_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="BIN range not found")

    matching_cards = db.query(Card).filter(Card.test_pan_reference.startswith(b.bin_prefix)).count()
    if deactivate_only:
        before = serialize_entity(b)
        b.status = "INACTIVE"
        record_audit(
            db,
            "BIN_RANGE",
            b.id,
            "DEACTIVATE",
            performed_by=current_user,
            before_state=before,
            after_state=serialize_entity(b),
            change_summary=f"Deactivated BIN range {b.bin_prefix}",
        )
        db.commit()
        return {"status": "deactivated", "bin_id": b.id, "bin_prefix": b.bin_prefix}

    if matching_cards > 0:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot hard-delete BIN range '{b.bin_prefix}' because {matching_cards} issued card(s) "
                f"belong to this BIN prefix. Disable/deactivate the BIN range instead."
            ),
        )

    before = serialize_entity(b)
    db.delete(b)
    record_audit(
        db,
        "BIN_RANGE",
        bin_id,
        "DELETE",
        performed_by=current_user,
        before_state=before,
        change_summary=f"Deleted BIN range {b.bin_prefix}",
    )
    db.commit()
    return {"status": "deleted", "bin_id": bin_id, "bin_prefix": b.bin_prefix}


# ==============================================================================
# 5. PAN ROUTER RULES MANAGEMENT (WITH PRIORITY & CONFLICT VALIDATION)
# ==============================================================================

def _serialize_pan_rule(r: PanRoutingRule) -> Dict[str, Any]:
    iss_code = clean_bank_short_code(
        r.issuer_institution.short_name or r.issuer_institution.institution_code
        if r.issuer_institution else None,
        "XBANK",
    )
    acq_code = clean_bank_short_code(
        r.acquirer_institution.short_name or r.acquirer_institution.institution_code
        if r.acquirer_institution else None,
        "",
    ) if r.acquirer_institution else None
    return {
        "id": r.id,
        "rule_code": r.rule_code,
        "rule_name": r.rule_name,
        "description": r.description,
        "priority": r.priority,
        "pan_prefix": r.pan_prefix,
        "pan_low": r.pan_low,
        "pan_high": r.pan_high,
        "pan_length": r.pan_length,
        "card_type": r.card_type,
        "transaction_code": r.transaction_code,
        "acquirer_institution_id": r.acquirer_institution_id,
        "acquirer_institution_code": acq_code,
        "acquirer_institution_name": r.acquirer_institution.name if r.acquirer_institution else None,
        "issuer_institution_id": r.issuer_institution_id,
        "issuer_institution_code": iss_code,
        "issuer_institution_name": r.issuer_institution.name if r.issuer_institution else None,
        "processing_system_id": r.processing_system_id,
        "ps_code": r.processing_system.ps_code if r.processing_system else None,
        "ps_name": r.processing_system.name if r.processing_system else None,
        "destination_network": r.destination_network,
        "scheme": r.scheme,
        "is_on_us": r.is_on_us,
        "pin_translation_required": r.pin_translation_required,
        "source_key_id": r.source_key_id,
        "destination_key_id": r.destination_key_id,
        "enabled": r.enabled,
        "status": r.status,
        "created_at": r.created_at,
        "updated_at": r.updated_at,
    }


def _validate_pan_routing_conflicts(
    db: Session,
    rule_code: str,
    prefix: str,
    low_raw: str,
    high_raw: str,
    priority: int,
    card_type: Optional[str],
    tx_code: Optional[str],
    acq_id: Optional[str],
    exclude_id: Optional[str] = None,
) -> None:
    clean_pfx = re.sub(r"\D", "", prefix or "")
    if len(clean_pfx) < 4 or len(clean_pfx) > 12:
        raise HTTPException(status_code=400, detail="PAN routing prefix must be 4 to 12 numeric digits")

    low_19 = low_raw.ljust(19, "0")[:19]
    high_19 = high_raw.ljust(19, "9")[:19]
    if low_19 > high_19:
        raise HTTPException(status_code=400, detail=f"Invalid PAN range: pan_low ({low_raw}) > pan_high ({high_raw})")

    query = db.query(PanRoutingRule)
    if exclude_id:
        query = query.filter(PanRoutingRule.id != exclude_id)

    for ex in query.all():
        if ex.rule_code.upper() == rule_code.upper():
            raise HTTPException(status_code=409, detail=f"PAN routing rule code '{rule_code}' already exists")

        ex_low = (ex.pan_low or ex.pan_prefix).ljust(19, "0")[:19]
        ex_high = (ex.pan_high or ex.pan_prefix).ljust(19, "9")[:19]
        ranges_overlap = not (high_19 < ex_low or low_19 > ex_high)

        same_conditions = (
            (ex.card_type or "ANY") == (card_type or "ANY")
            and (ex.transaction_code or "ANY") == (tx_code or "ANY")
            and (ex.acquirer_institution_id or "ANY") == (acq_id or "ANY")
        )
        if ranges_overlap and same_conditions and ex.priority == priority:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Routing conflict: Rule '{ex.rule_code}' already covers overlapping PAN range "
                    f"[{ex.pan_low}..{ex.pan_high}] with identical priority {priority} and conditions."
                ),
            )


@router.get("/pan-routing-rules", response_model=List[PanRoutingRuleOut])
def list_pan_routing_rules(
    q: Optional[str] = Query(None),
    issuer_institution_id: Optional[str] = Query(None),
    processing_system_id: Optional[str] = Query(None),
    scheme: Optional[str] = Query(None),
    enabled: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    query = db.query(PanRoutingRule)
    if issuer_institution_id:
        query = query.filter(PanRoutingRule.issuer_institution_id == issuer_institution_id)
    if processing_system_id:
        query = query.filter(PanRoutingRule.processing_system_id == processing_system_id)
    if scheme:
        query = query.filter(PanRoutingRule.scheme == scheme.upper().strip())
    if enabled is not None:
        query = query.filter(PanRoutingRule.enabled == enabled)

    rules = query.order_by(PanRoutingRule.priority.asc(), PanRoutingRule.pan_prefix.asc()).all()
    out = [_serialize_pan_rule(r) for r in rules]
    if q:
        term = q.strip().lower()
        out = [
            r for r in out
            if term in (r["rule_code"] or "").lower()
            or term in (r["rule_name"] or "").lower()
            or term in (r["pan_prefix"] or "").lower()
            or term in (r["issuer_institution_code"] or "").lower()
            or term in (r["ps_code"] or "").lower()
            or term in (r["scheme"] or "").lower()
        ]
    return out


@router.post("/pan-routing-rules", response_model=PanRoutingRuleOut)
def create_pan_routing_rule(
    payload: PanRoutingRuleCreate,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    rcode = payload.rule_code.strip().upper()
    prefix = re.sub(r"\D", "", payload.pan_prefix.strip())
    plen = payload.pan_length or 16
    low_raw = re.sub(r"\D", "", payload.pan_low) if payload.pan_low else prefix.ljust(plen, "0")
    high_raw = re.sub(r"\D", "", payload.pan_high) if payload.pan_high else prefix.ljust(plen, "9")

    issuer = db.query(Institution).filter(Institution.id == payload.issuer_institution_id).first()
    if not issuer:
        raise HTTPException(status_code=404, detail="Issuer institution not found")

    if payload.acquirer_institution_id:
        acq = db.query(Institution).filter(Institution.id == payload.acquirer_institution_id).first()
        if not acq:
            raise HTTPException(status_code=404, detail="Acquirer institution not found")

    ps = db.query(ProcessingSystem).filter(ProcessingSystem.id == payload.processing_system_id).first()
    if not ps:
        raise HTTPException(status_code=404, detail="Processing switch not found")

    ctype = payload.card_type.upper().strip() if payload.card_type else None
    tx_code = payload.transaction_code.strip() if payload.transaction_code else None

    _validate_pan_routing_conflicts(
        db,
        rule_code=rcode,
        prefix=prefix,
        low_raw=low_raw,
        high_raw=high_raw,
        priority=payload.priority,
        card_type=ctype,
        tx_code=tx_code,
        acq_id=payload.acquirer_institution_id,
    )

    rule = PanRoutingRule(
        rule_code=rcode,
        rule_name=payload.rule_name.strip(),
        description=payload.description,
        priority=payload.priority,
        pan_prefix=prefix,
        pan_low=low_raw,
        pan_high=high_raw,
        pan_length=plen,
        card_type=ctype,
        transaction_code=tx_code,
        acquirer_institution_id=payload.acquirer_institution_id or None,
        issuer_institution_id=issuer.id,
        processing_system_id=ps.id,
        destination_network=payload.destination_network or ("INTERNAL_SIMULATOR_TIC" if payload.is_on_us else f"{payload.scheme.upper()}_SCHEME"),
        scheme=payload.scheme.upper().strip(),
        is_on_us=payload.is_on_us,
        pin_translation_required=payload.pin_translation_required,
        source_key_id=payload.source_key_id or "AWK_ATM_01",
        destination_key_id=payload.destination_key_id or "IWK_SW_01",
        enabled=payload.enabled,
        status=payload.status.upper().strip(),
    )
    db.add(rule)
    db.flush()
    record_audit(
        db,
        "PAN_ROUTING_RULE",
        rule.id,
        "CREATE",
        performed_by=current_user,
        after_state=serialize_entity(rule),
        change_summary=f"Created PAN routing rule {rule.rule_code} (prefix {rule.pan_prefix} -> {ps.ps_code})",
    )
    db.commit()
    db.refresh(rule)
    return _serialize_pan_rule(rule)


@router.put("/pan-routing-rules/{rule_id}", response_model=PanRoutingRuleOut)
def update_pan_routing_rule(
    rule_id: str,
    payload: PanRoutingRuleUpdate,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    rule = db.query(PanRoutingRule).filter(PanRoutingRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="PAN routing rule not found")

    before = serialize_entity(rule)
    data = payload.model_dump(exclude_unset=True)

    new_code = (data.get("rule_code") or rule.rule_code).strip().upper()
    new_prefix = re.sub(r"\D", "", data.get("pan_prefix") or rule.pan_prefix)
    new_plen = int(data.get("pan_length") or rule.pan_length or 16)
    new_low = re.sub(r"\D", "", data["pan_low"]) if data.get("pan_low") else (
        new_prefix.ljust(new_plen, "0") if "pan_prefix" in data and "pan_low" not in data else rule.pan_low
    )
    new_high = re.sub(r"\D", "", data["pan_high"]) if data.get("pan_high") else (
        new_prefix.ljust(new_plen, "9") if "pan_prefix" in data and "pan_high" not in data else rule.pan_high
    )
    new_prio = int(data.get("priority", rule.priority))
    new_ctype = data.get("card_type", rule.card_type)
    if isinstance(new_ctype, str):
        new_ctype = new_ctype.upper().strip() or None
    new_tx_code = data.get("transaction_code", rule.transaction_code)
    if isinstance(new_tx_code, str):
        new_tx_code = new_tx_code.strip() or None
    new_acq_id = data.get("acquirer_institution_id", rule.acquirer_institution_id) or None

    _validate_pan_routing_conflicts(
        db,
        rule_code=new_code,
        prefix=new_prefix,
        low_raw=new_low,
        high_raw=new_high,
        priority=new_prio,
        card_type=new_ctype,
        tx_code=new_tx_code,
        acq_id=new_acq_id,
        exclude_id=rule.id,
    )

    if "issuer_institution_id" in data and data["issuer_institution_id"]:
        if not db.query(Institution).filter(Institution.id == data["issuer_institution_id"]).first():
            raise HTTPException(status_code=404, detail="Issuer institution not found")

    if "processing_system_id" in data and data["processing_system_id"]:
        if not db.query(ProcessingSystem).filter(ProcessingSystem.id == data["processing_system_id"]).first():
            raise HTTPException(status_code=404, detail="Processing switch not found")

    rule.rule_code = new_code
    rule.pan_prefix = new_prefix
    rule.pan_low = new_low
    rule.pan_high = new_high
    rule.pan_length = new_plen
    rule.priority = new_prio
    rule.card_type = new_ctype
    rule.transaction_code = new_tx_code
    rule.acquirer_institution_id = new_acq_id

    for k in (
        "rule_name",
        "description",
        "issuer_institution_id",
        "processing_system_id",
        "destination_network",
        "scheme",
        "is_on_us",
        "pin_translation_required",
        "source_key_id",
        "destination_key_id",
        "enabled",
        "status",
    ):
        if k in data and data[k] is not None:
            val = data[k]
            if isinstance(val, str) and k in ("scheme", "status"):
                val = val.upper().strip()
            setattr(rule, k, val)

    if "enabled" in data:
        rule.status = "ACTIVE" if rule.enabled else "INACTIVE"
    elif "status" in data:
        rule.enabled = rule.status == "ACTIVE"

    after = serialize_entity(rule)
    record_audit(
        db,
        "PAN_ROUTING_RULE",
        rule.id,
        "UPDATE",
        performed_by=current_user,
        before_state=before,
        after_state=after,
        change_summary=f"Updated PAN routing rule {rule.rule_code}",
    )
    db.commit()
    db.refresh(rule)
    return _serialize_pan_rule(rule)


@router.patch("/pan-routing-rules/{rule_id}/toggle", response_model=PanRoutingRuleOut)
def toggle_pan_routing_rule(
    rule_id: str,
    enabled: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    rule = db.query(PanRoutingRule).filter(PanRoutingRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="PAN routing rule not found")
    before = serialize_entity(rule)
    next_enabled = (not rule.enabled) if enabled is None else bool(enabled)
    rule.enabled = next_enabled
    rule.status = "ACTIVE" if next_enabled else "INACTIVE"
    after = serialize_entity(rule)
    record_audit(
        db,
        "PAN_ROUTING_RULE",
        rule.id,
        "STATUS_CHANGE",
        performed_by=current_user,
        before_state=before,
        after_state=after,
        change_summary=f"{'Enabled' if next_enabled else 'Disabled'} PAN routing rule {rule.rule_code}",
    )
    db.commit()
    db.refresh(rule)
    return _serialize_pan_rule(rule)


@router.delete("/pan-routing-rules/{rule_id}")
def delete_pan_routing_rule(
    rule_id: str,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    rule = db.query(PanRoutingRule).filter(PanRoutingRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="PAN routing rule not found")
    before = serialize_entity(rule)
    code = rule.rule_code
    db.delete(rule)
    record_audit(
        db,
        "PAN_ROUTING_RULE",
        rule_id,
        "DELETE",
        performed_by=current_user,
        before_state=before,
        change_summary=f"Deleted PAN routing rule {code}",
    )
    db.commit()
    return {"status": "deleted", "rule_id": rule_id, "rule_code": code}

# [PATCH step13_06:bins_alias_route]
@router.get("/bins", response_model=List[BinRangeOut])
def list_bins_alias(
    q: Optional[str] = Query(None),
    institution_id: Optional[str] = Query(None),
    card_type: Optional[str] = Query(None),
    scheme: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    return list_bin_ranges(
        q=q,
        institution_id=institution_id,
        card_type=card_type,
        scheme=scheme,
        status=status,
        db=db,
        _=current_user,
    )

