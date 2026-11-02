#!/usr/bin/env python3
"""
INSTALLER: tools/install_step01_02.py
STEP 1 — Bank, Processing System & BIN Management — Script 2 of 3
Creates:
  1. backend/app/routers/institutions_router.py
  2. backend/tests/test_step01_institutions.py
Modifies:
  - backend/app/main.py (includes institutions router)
"""

from pathlib import Path
import sys

BASE_DIR = Path(r"E:\HOST_VSCODE\host-simulator").resolve()
sys.path.insert(0, str(BASE_DIR))

from tools.patcher import PatcherSession, parse_installer_args

INSTITUTIONS_ROUTER_CODE = '''"""
INSTITUTIONS ROUTER — Processing Systems, Member Banks, Network Links & BIN Ranges
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import (
    BinRange,
    Institution,
    InstitutionProcessingSystem,
    ProcessingSystem,
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
    ProcessingSystemCreate,
    ProcessingSystemOut,
    ProcessingSystemUpdate,
)
from app.security import get_current_user

router = APIRouter(prefix="/api", tags=["Institutions & Processing Systems"])


# ==============================================================================
# 1. PROCESSING SYSTEMS
# ==============================================================================

@router.get("/processing-systems", response_model=List[ProcessingSystemOut])
def list_processing_systems(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    return db.query(ProcessingSystem).order_by(ProcessingSystem.ps_code.asc()).all()


@router.post("/processing-systems", response_model=ProcessingSystemOut)
def create_processing_system(payload: ProcessingSystemCreate, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    existing = db.query(ProcessingSystem).filter(ProcessingSystem.ps_code == payload.ps_code.upper()).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Processing system '{payload.ps_code}' already exists")
    ps = ProcessingSystem(
        ps_code=payload.ps_code.upper(),
        name=payload.name,
        system_type=payload.system_type,
        message_format=payload.message_format,
        enabled=payload.enabled,
        is_default=payload.is_default,
        configuration=payload.configuration,
    )
    db.add(ps)
    db.commit()
    db.refresh(ps)
    return ps


@router.put("/processing-systems/{ps_id}", response_model=ProcessingSystemOut)
def update_processing_system(ps_id: str, payload: ProcessingSystemUpdate, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    ps = db.query(ProcessingSystem).filter(ProcessingSystem.id == ps_id).first()
    if not ps:
        raise HTTPException(status_code=404, detail="Processing system not found")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(ps, k, v)
    db.commit()
    db.refresh(ps)
    return ps


# ==============================================================================
# 2. INSTITUTIONS (BANKS)
# ==============================================================================

def _serialize_institution(inst: Institution) -> Dict[str, Any]:
    return {
        "id": inst.id,
        "institution_code": inst.institution_code,
        "name": inst.name,
        "short_name": inst.short_name,
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
def list_institutions(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    insts = db.query(Institution).order_by(Institution.institution_code.asc()).all()
    return [_serialize_institution(i) for i in insts]


@router.post("/institutions", response_model=InstitutionOut)
def create_institution(payload: InstitutionCreate, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    icode = payload.institution_code.upper()
    existing = db.query(Institution).filter(Institution.institution_code == icode).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Institution '{icode}' already exists")

    # Resolve processing system (default to ITCL if not supplied)
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

    inst = Institution(
        institution_code=icode,
        name=payload.name,
        short_name=payload.short_name or payload.name,
        acquirer_id=payload.acquirer_id,
        forwarding_id=payload.forwarding_id,
        role=payload.role,
        processing_system_id=ps_id,
        country_code=payload.country_code,
        currency=payload.currency,
        settlement_account_number=payload.settlement_account_number,
        status=payload.status,
        configuration=payload.configuration,
    )
    db.add(inst)
    db.flush()

    # Automatically create primary participation link in institution_processing_systems
    link = InstitutionProcessingSystem(
        institution_id=inst.id,
        processing_system_id=ps.id,
        member_id=f"{ps.ps_code}-{icode}",
        acquirer_id=payload.acquirer_id,
        network_identifier=f"{ps.ps_code}_HOST",
        issuer_enabled=True,
        acquirer_enabled=True,
        message_format=ps.message_format,
        routing_configuration={"is_primary_host": True},
        status="ACTIVE",
    )
    db.add(link)
    db.commit()
    db.refresh(inst)
    return _serialize_institution(inst)


@router.put("/institutions/{inst_id}", response_model=InstitutionOut)
def update_institution(inst_id: str, payload: InstitutionUpdate, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    inst = db.query(Institution).filter(Institution.id == inst_id).first()
    if not inst:
        raise HTTPException(status_code=404, detail="Institution not found")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(inst, k, v)
    db.commit()
    db.refresh(inst)
    return _serialize_institution(inst)


@router.delete("/institutions/{inst_id}")
def delete_institution(inst_id: str, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    inst = db.query(Institution).filter(Institution.id == inst_id).first()
    if not inst:
        raise HTTPException(status_code=404, detail="Institution not found")
    if inst.cards or inst.accounts:
        raise HTTPException(status_code=409, detail="Cannot delete institution with active cards or accounts. Soft close instead.")
    db.delete(inst)
    db.commit()
    return {"status": "deleted", "institution_id": inst_id}


# ==============================================================================
# 3. INSTITUTION PROCESSING SYSTEM LINKS (MULTI-NETWORK MEMBERSHIPS)
# ==============================================================================

@router.get("/institutions/{inst_id}/networks", response_model=List[InstitutionProcessingSystemOut])
def list_institution_networks(inst_id: str, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    links = db.query(InstitutionProcessingSystem).filter(InstitutionProcessingSystem.institution_id == inst_id).all()
    out = []
    for l in links:
        out.append({
            "id": l.id,
            "institution_id": l.institution_id,
            "institution_code": l.institution.institution_code if l.institution else None,
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
def add_institution_network(inst_id: str, payload: InstitutionProcessingSystemCreate, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    inst = db.query(Institution).filter(Institution.id == inst_id).first()
    if not inst:
        raise HTTPException(status_code=404, detail="Institution not found")
    ps = db.query(ProcessingSystem).filter(ProcessingSystem.id == payload.processing_system_id).first()
    if not ps:
        raise HTTPException(status_code=404, detail="Processing system not found")

    existing = db.query(InstitutionProcessingSystem).filter(
        InstitutionProcessingSystem.institution_id == inst_id,
        InstitutionProcessingSystem.processing_system_id == payload.processing_system_id,
    ).first()
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
    db.commit()
    db.refresh(link)
    return {
        "id": link.id,
        "institution_id": link.institution_id,
        "institution_code": inst.institution_code,
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
def remove_institution_network(link_id: str, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    link = db.query(InstitutionProcessingSystem).filter(InstitutionProcessingSystem.id == link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Network link not found")
    db.delete(link)
    db.commit()
    return {"status": "deleted", "link_id": link_id}


# ==============================================================================
# 4. BIN RANGES
# ==============================================================================

def _serialize_bin(b: BinRange) -> Dict[str, Any]:
    return {
        "id": b.id,
        "bin_prefix": b.bin_prefix,
        "bin_low": b.bin_low,
        "bin_high": b.bin_high,
        "pan_length": b.pan_length,
        "institution_id": b.institution_id,
        "institution_code": b.institution.institution_code if b.institution else None,
        "institution_name": b.institution.name if b.institution else None,
        "processing_system_id": b.processing_system_id,
        "ps_code": b.processing_system.ps_code if b.processing_system else None,
        "ps_name": b.processing_system.name if b.processing_system else None,
        "card_type": b.card_type,
        "card_product": b.card_product,
        "scheme": b.scheme,
        "country_code": b.country_code,
        "currency": b.currency,
        "is_on_us": b.is_on_us,
        "status": b.status,
        "created_at": b.created_at,
        "updated_at": b.updated_at,
    }


@router.get("/bin-ranges", response_model=List[BinRangeOut])
def list_bin_ranges(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    bins = db.query(BinRange).order_by(BinRange.bin_prefix.asc()).all()
    return [_serialize_bin(b) for b in bins]


@router.post("/bin-ranges", response_model=BinRangeOut)
def create_bin_range(payload: BinRangeCreate, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    prefix = payload.bin_prefix.strip()
    existing = db.query(BinRange).filter(BinRange.bin_prefix == prefix).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"BIN prefix '{prefix}' already exists")

    inst = db.query(Institution).filter(Institution.id == payload.institution_id).first()
    if not inst:
        raise HTTPException(status_code=404, detail="Institution not found")

    ps_id = payload.processing_system_id or inst.processing_system_id

    bin_low = payload.bin_low or f"{prefix}".ljust(19, "0")
    bin_high = payload.bin_high or f"{prefix}".ljust(19, "9")

    b = BinRange(
        bin_prefix=prefix,
        bin_low=bin_low,
        bin_high=bin_high,
        pan_length=payload.pan_length,
        institution_id=payload.institution_id,
        processing_system_id=ps_id,
        card_type=payload.card_type,
        card_product=payload.card_product,
        scheme=payload.scheme,
        country_code=payload.country_code,
        currency=payload.currency,
        is_on_us=payload.is_on_us,
        status=payload.status,
    )
    db.add(b)
    db.commit()
    db.refresh(b)
    return _serialize_bin(b)


@router.put("/bin-ranges/{bin_id}", response_model=BinRangeOut)
def update_bin_range(bin_id: str, payload: BinRangeUpdate, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    b = db.query(BinRange).filter(BinRange.id == bin_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="BIN range not found")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(b, k, v)
    db.commit()
    db.refresh(b)
    return _serialize_bin(b)


@router.delete("/bin-ranges/{bin_id}")
def delete_bin_range(bin_id: str, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    b = db.query(BinRange).filter(BinRange.id == bin_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="BIN range not found")
    db.delete(b)
    db.commit()
    return {"status": "deleted", "bin_id": bin_id}


@router.get("/bin-ranges/lookup/{pan}")
def lookup_bin_for_pan(pan: str, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    clean_pan = "".join(ch for ch in pan if ch.isdigit())
    if len(clean_pan) < 6:
        raise HTTPException(status_code=400, detail="PAN is too short for BIN lookup (minimum 6 digits)")

    # Check 6, 8, 10, 12 digit prefixes
    matched = None
    for length in (12, 10, 8, 6):
        if len(clean_pan) >= length:
            prefix = clean_pan[:length]
            matched = db.query(BinRange).filter(BinRange.bin_prefix == prefix).first()
            if matched:
                break

    if not matched:
        # Fallback to general range check
        all_bins = db.query(BinRange).all()
        for b in all_bins:
            if b.bin_low and b.bin_high:
                if b.bin_low.ljust(19, '0') <= clean_pan.ljust(19, '0') <= b.bin_high.ljust(19, '9'):
                    matched = b
                    break

    if not matched:
        return {"found": False, "pan_masked": pan[:6] + "*" * (len(pan) - 10) + pan[-4:] if len(pan) >= 10 else "****", "message": "No matching BIN range found. Defaulting to On-Us ITCL switch."}

    return {
        "found": True,
        "bin_prefix": matched.bin_prefix,
        "institution": {
            "id": matched.institution.id,
            "code": matched.institution.institution_code,
            "name": matched.institution.name,
            "acquirer_id": matched.institution.acquirer_id,
        },
        "processing_system": {
            "id": matched.processing_system.id,
            "code": matched.processing_system.ps_code,
            "name": matched.processing_system.name,
        },
        "card_product": matched.card_product,
        "scheme": matched.scheme,
        "is_on_us": matched.is_on_us,
    }
'''

TEST_INSTITUTIONS_CODE = '''"""
test_step01_institutions.py — Tests for Step 1 Processing Systems, Institutions & BINs
"""

import os
import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Institution, ProcessingSystem
from app.seed_data import seed_initial_data
from app.security import create_access_token
from app.config import settings


@pytest.fixture()
def client():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    seed_initial_data(db)
    db.close()
    
    with TestClient(app) as c:
        token = create_access_token(subject=settings.ADMIN_USERNAME)
        c.headers = {"Authorization": f"Bearer {token}"}
        yield c
    Base.metadata.drop_all(bind=engine)


def test_list_processing_systems(client):
    res = client.get("/api/processing-systems")
    assert res.status_code == 200
    data = res.json()
    codes = [p["ps_code"] for p in data]
    assert "ITCL" in codes
    assert "VISA" in codes
    assert "MASTERCARD" in codes
    assert "NPSB" in codes


def test_list_institutions_default_itcl(client):
    res = client.get("/api/institutions")
    assert res.status_code == 200
    data = res.json()
    codes = [i["institution_code"] for i in data]
    assert "XBANK" in codes
    assert "YBANK" in codes
    assert "ZBANK" in codes
    for inst in data:
        assert inst["ps_code"] == "ITCL"


def test_create_institution_defaults_to_itcl(client):
    payload = {
        "institution_code": "IFIC",
        "name": "IFIC Bank PLC",
        "acquirer_id": "443322",
        "role": "BOTH"
    }
    res = client.post("/api/institutions", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["institution_code"] == "IFIC"
    assert data["ps_code"] == "ITCL"


def test_bin_lookup_for_pan(client):
    # 4567890123450001 belongs to XBANK under ITCL
    res = client.get("/api/bin-ranges/lookup/4567890123450001")
    assert res.status_code == 200
    data = res.json()
    assert data["found"] is True
    assert data["institution"]["code"] == "XBANK"
    assert data["processing_system"]["code"] == "ITCL"
'''


def main() -> int:
    args = parse_installer_args("Step 01_02: FastAPI Router for Processing Systems, Institutions & BINs + Tests")
    session = PatcherSession(
        step_id="step01_02",
        title="Implement Institutions & Processing Systems API Router and Pytest Suite",
        dry_run=args.dry_run,
    )

    # 1. Write backend/app/routers/institutions_router.py
    session.write_file("backend/app/routers/institutions_router.py", INSTITUTIONS_ROUTER_CODE)

    # 2. Write backend/tests/test_step01_institutions.py
    session.write_file("backend/tests/test_step01_institutions.py", TEST_INSTITUTIONS_CODE)

    # 3. Patch backend/app/main.py to include institutions_router
    session.patch_file(
        "backend/app/main.py",
        [
            {
                "marker": "step01_02:include_institutions_router",
                "action": "insert_after",
                "anchor": "from app.api_routes import router",
                "text": "from app.routers.institutions_router import router as institutions_router",
            },
            {
                "marker": "step01_02:app_include_router_inst",
                "action": "insert_after",
                "anchor": "app.include_router(router)",
                "text": "app.include_router(institutions_router)",
            },
        ],
    )

    session.record_progress(
        completed=[
            "Created `backend/app/routers/institutions_router.py` with endpoints for processing systems, institutions, multi-network links, and BIN range prefix lookups.",
            "Wired `institutions_router` into `backend/app/main.py`.",
            "Created automated test suite `backend/tests/test_step01_institutions.py`.",
        ],
        remaining=[
            "Step 1 Script 3 of 3 (`tools/install_step01_03.py`): Create React UI page `InstitutionsAndBinsPage.tsx` and wire navigation in `App.tsx` and `Layout.tsx`.",
        ],
        modified_files=[
            "backend/app/routers/institutions_router.py",
            "backend/app/main.py",
            "backend/tests/test_step01_institutions.py",
        ],
    )

    session.record_contracts(
        section_title="Step 1.2 — Processing Systems & Institutions API Contracts",
        contract_items=[
            "**GET /api/processing-systems**: Returns all active processing switches.",
            "**POST /api/processing-systems**: Registers a new processing system.",
            "**GET /api/institutions**: Returns all member banks with their primary processing system code.",
            "**POST /api/institutions**: Creates a new bank (defaults to **ITCL** if `processing_system_id` is omitted).",
            "**GET /api/institutions/{inst_id}/networks**: Lists secondary network participations.",
            "**POST /api/institutions/{inst_id}/networks**: Links a bank to VISA, Mastercard, or NPSB.",
            "**GET /api/bin-ranges**: Lists BIN prefixes.",
            "**GET /api/bin-ranges/lookup/{pan}**: Resolves a PAN to its issuing bank and processing system.",
        ],
    )

    return session.finish()


if __name__ == "__main__":
    sys.exit(main())