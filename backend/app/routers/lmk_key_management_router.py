"""
lmk_key_management_router.py — REST API for LMK-Centric Key Management & Key Ownership
======================================================================================
Provides endpoints for:
  - GET  /api/hsm/lmk-key-management/audit-report (Part G mandatory audit deliverable)
  - GET  /api/hsm/lmk-key-management/status (Live LMK check value, domain & provider status)
  - POST /api/hsm/lmk-key-management/provider (Switch between INTERNAL_HSM and EXTERNAL_HSM)
  - GET  /api/hsm/lmk-key-management/keys (Provider-isolated key inventory, zero clear keys)
  - POST /api/hsm/lmk-key-management/sync-seeded (Sync Soft-HSM default LMK keys via BU)
  - POST /api/hsm/lmk-key-management/generate (Generate key via Soft-HSM Command A0)
  - POST /api/hsm/lmk-key-management/import (Import key under ZMK/TMK via Soft-HSM Command A6)
  - POST /api/hsm/lmk-key-management/export (Export key under ZMK/TMK via Soft-HSM Command A8)
  - POST /api/hsm/lmk-key-management/verify-kcv/{key_identifier} (Verify KCV via Soft-HSM Command BU)
  - POST /api/hsm/lmk-key-management/rotate (Rotate key version via Soft-HSM Command A0)
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.lmk_key_management_service import LMKKeyManagementService, THALES_KEY_TYPE_MAP
from app.models import HsmKeyReference
from app.schemas import (
    ExternalKeyExportRequest,
    ExternalKeyGenerateRequest,
    ExternalKeyImportRequest,
    ExternalKeyRotateRequest,
    HsmProviderSwitchRequest,
)
from app.security import get_current_user

router = APIRouter(prefix="/api/hsm/lmk-key-management", tags=["LMK-Centric Key Management"])


@router.get("/audit-report")
def get_key_management_audit_deliverable(
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    """
    Part G: Required Key-Management Audit Deliverable verified against the actual
    Soft-HSM codebase and Thales payShield 10K manuals (PUGD0537-004, PUGD0538-003, PUGD0539-003).
    """
    svc = LMKKeyManagementService(db)
    svc.seed_fallback_external_keys()
    live_status = svc.get_lmk_and_provider_status()
    return {
        "1_lmk_generation_mechanism": (
            "ThalesLMKManager (backend/lmk_manager.py) initializes a deterministic 12-pair Variant LMK table "
            "(DEFAULT_LMK_TABLE pairs 04_05 through 36_37) with Thales variant masks 0..9. "
            "Master LMK check value is computed by encrypting 8 zero bytes under LMK pair 04_05 -> D3B82A0000000000."
        ),
        "2_lmk_storage_location": "Soft-HSM process memory (self.lmk_table in ThalesLMKManager, backend/main.py).",
        "3_lmk_survives_restarts": (
            "Default LMK (D3B82A0000000000) survives restarts because DEFAULT_LMK_TABLE is compiled in source code. "
            "Runtime LMK modifications via POST /api/lmk are held in RAM only and do NOT survive restarts."
        ),
        "4_lmk_survives_render_redeployment": (
            "Default LMK (D3B82A0000000000) survives Render redeployments. Custom LMK overrides do NOT."
        ),
        "5_key_database_storage_mechanism": (
            "Soft-HSM seeds 8 default keys in RAM (HSMStorageManager.keys) and optionally syncs to PostgreSQL if DATABASE_URL is set. "
            "Host Simulator persists key records in `hsm_key_references` with provider_type and lmk_check_value isolation."
        ),
        "6_key_representation_format": (
            "Soft-HSM commands operate statelessly on LMK-encrypted key tokens passed in the command payload: "
            "Variant tokens ('U' + 32H, 'T' + 48H, 'Z' + 16H) and Thales Key Blocks ('S10064<Usage>TN0000<32H_Enc><8H_MAC>'). "
            "Clear keys are never stored in the Host DB for EXTERNAL_HSM records."
        ),
        "7_supported_key_generation_commands": ["A0 (Generate Key under LMK and optionally export under ZMK/TMK -> A1)"],
        "8_supported_key_import_export_commands": [
            "A6 (Import Key encrypted under ZMK/TMK into LMK -> A7)",
            "A8 (Export Key from LMK to ZMK/TMK -> A9)",
            "KI (Derive & Export EMV Card UDK under KEK -> KJ)",
        ],
        "9_supported_key_translation_commands": [
            "A6 / A8 (ZMK/TMK <-> LMK working key translation)",
            "CA / CC / G0 (PIN block translation across TPK/ZPK/BDK)",
            "M4 (Data block translation across TEK/ZEK/DEK)",
            "Note: Old-to-New LMK migration (BW) and scheme translation (B0) are not in Soft-HSM COMMAND_REGISTRY (return ER68).",
        ],
        "10_key_aliases_and_references": (
            "Soft-HSM does not implement LA/LE User Storage 'Kxxx' index pointers. "
            "Instead, the Host Simulator maps human-readable key aliases (`key_identifier`) to their "
            "LMK-encrypted key block (`encrypted_key_block`) and injects the LMK token into raw Thales commands."
        ),
        "11_host_storage_and_reference_model": (
            "Host stores alias, key_type, thales_key_type_code, key_usage, key_scheme, key_version, key_status, "
            "kvc, lmk_id, lmk_check_value, provider_type='EXTERNAL_HSM', and encrypted_key_block. clear_key_hex is NULL."
        ),
        "12_lmk_compatibility_and_persistence_limitations": (
            "Render Free uses an ephemeral filesystem. Storing self-contained LMK-encrypted key blocks in the Host DB "
            "ensures keys survive Soft-HSM restarts/redeploys under the deterministic Default LMK (D3B82A0000000000). "
            "Cross-LMK or cross-provider usage is blocked by strict LMK check value verification."
        ),
        "live_status": live_status,
        "supported_thales_key_types": THALES_KEY_TYPE_MAP,
    }


@router.get("/status")
def get_lmk_status(
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    svc = LMKKeyManagementService(db)
    svc.seed_fallback_external_keys()
    return svc.get_lmk_and_provider_status()


@router.post("/provider")
def switch_hsm_provider(
    payload: HsmProviderSwitchRequest,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    return _execute_safe_provider_switch(
        {"provider_mode": payload.provider_mode, "remote_url": payload.remote_url}, db
    )


@router.get("/keys")
def list_provider_keys(
    provider_type: Optional[str] = Query(None, description="INTERNAL_HSM | EXTERNAL_HSM | ALL"),
    include_superseded: bool = Query(False),
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    svc = LMKKeyManagementService(db)
    svc.seed_fallback_external_keys()
    active_prov = svc.active_provider_type()
    target_prov = (provider_type or active_prov).upper().strip()

    q = db.query(HsmKeyReference)
    if target_prov in ("INTERNAL_HSM", "EXTERNAL_HSM"):
        q = q.filter(HsmKeyReference.provider_type == target_prov)
    if not include_superseded:
        q = q.filter(HsmKeyReference.key_status != "SUPERSEDED")

    keys = q.order_by(HsmKeyReference.key_identifier.asc()).all()
    return {
        "active_provider": active_prov,
        "filtered_provider": target_prov,
        "count": len(keys),
        "keys": [svc.serialize_key_safe(k) for k in keys],
    }


@router.post("/sync-seeded")
def sync_seeded_external_keys(
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    svc = LMKKeyManagementService(db)
    svc.seed_fallback_external_keys()
    try:
        return svc.sync_default_external_keys(current_user=current_user)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/generate")
def generate_external_key_a0(
    payload: ExternalKeyGenerateRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    svc = LMKKeyManagementService(db)
    svc.seed_fallback_external_keys()
    try:
        return svc.generate_key_via_soft_hsm_a0(payload.model_dump(), current_user=current_user)
    except ConnectionError as ce:
        raise HTTPException(status_code=502, detail=str(ce))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


@router.post("/import")
def import_external_key_a6(
    payload: ExternalKeyImportRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    svc = LMKKeyManagementService(db)
    svc.seed_fallback_external_keys()
    try:
        return svc.import_key_via_soft_hsm_a6(payload.model_dump(), current_user=current_user)
    except ConnectionError as ce:
        raise HTTPException(status_code=502, detail=str(ce))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


@router.post("/export")
def export_external_key_a8(
    payload: ExternalKeyExportRequest,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    svc = LMKKeyManagementService(db)
    svc.seed_fallback_external_keys()
    try:
        return svc.export_key_via_soft_hsm_a8(payload.model_dump())
    except ConnectionError as ce:
        raise HTTPException(status_code=502, detail=str(ce))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


@router.post("/verify-kcv/{key_identifier}")
def verify_external_key_kcv_bu(
    key_identifier: str,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    svc = LMKKeyManagementService(db)
    svc.seed_fallback_external_keys()
    try:
        return svc.verify_key_kcv_via_soft_hsm_bu(key_identifier)
    except ConnectionError as ce:
        raise HTTPException(status_code=502, detail=str(ce))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


@router.post("/rotate")
def rotate_external_key_a0(
    payload: ExternalKeyRotateRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    svc = LMKKeyManagementService(db)
    svc.seed_fallback_external_keys()
    try:
        return svc.rotate_external_key(
            key_identifier=payload.key_identifier,
            new_scheme=payload.new_key_scheme,
            export_zmk_key_identifier=payload.export_zmk_key_identifier,
            current_user=current_user,
        )
    except ConnectionError as ce:
        raise HTTPException(status_code=502, detail=str(ce))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


# [PATCH provider_switch_fast]
def _execute_safe_provider_switch(payload: Dict[str, Any], db: Session) -> Dict[str, Any]:
    """
    Fast, always-answering provider switch used by /provider and the universal routes.
    No long remote chains: local seed + one short probe of the Soft-HSM (which also wakes Render).
    """
    import json as _json
    import logging as _logging
    import urllib.request as _urlreq

    log = _logging.getLogger("baobab.host")
    raw_target = (
        payload.get("provider_mode")
        or payload.get("provider_type")
        or payload.get("provider")
        or payload.get("hsm_mode")
        or payload.get("mode")
        or payload.get("target_provider")
        or ""
    )
    target = str(raw_target).upper().strip()
    if any(k in target for k in ("EXT", "REMOTE", "THALES", "CLOUD")):
        settings.HSM_MODE = "SOFT_HSM_REMOTE"
        active_provider = "EXTERNAL_HSM"
    elif any(k in target for k in ("INT", "LOCAL")):
        settings.HSM_MODE = "SOFT_HSM_LOCAL"
        active_provider = "INTERNAL_HSM"
    else:
        raise HTTPException(status_code=400, detail="provider_mode must be 'INTERNAL_HSM' or 'EXTERNAL_HSM'")

    remote_url = payload.get("remote_url")
    if remote_url:
        settings.HSM_REMOTE_URL = str(remote_url).strip()

    svc = LMKKeyManagementService(db)
    try:
        svc.seed_fallback_external_keys()  # local only, never overwrites real tokens
    except Exception:
        db.rollback()
        log.exception("seed_fallback_external_keys failed during provider switch")

    counts = {"internal_keys": 0, "external_keys": 0}
    try:
        counts["internal_keys"] = db.query(HsmKeyReference).filter(HsmKeyReference.provider_type == "INTERNAL_HSM").count()
        counts["external_keys"] = db.query(HsmKeyReference).filter(HsmKeyReference.provider_type == "EXTERNAL_HSM").count()
    except Exception:
        db.rollback()

    if active_provider == "INTERNAL_HSM":
        status_info = svc.get_lmk_and_provider_status()  # no network in internal mode
    else:
        online, remote, warning = False, {}, None
        try:
            req = _urlreq.Request(
                svc.bridge.status_url,
                headers={"Accept": "application/json", "User-Agent": "BAOBAB-Host-Simulator/1.0"},
                method="GET",
            )
            with _urlreq.urlopen(req, timeout=8) as resp:
                remote = _json.loads(resp.read().decode("utf-8"))
                online = True
        except Exception as exc:
            warning = f"External Soft-HSM did not answer in 8s (Render may be waking up): {exc}"
            log.warning(warning)
        lmk_cv = remote.get("lmk_check_value") or ("D3B82A0000000000" if online else "UNREACHABLE")
        status_info = {
            "active_provider": "EXTERNAL_HSM",
            "hsm_mode": settings.HSM_MODE,
            "online": online,
            "hsm_state": remote.get("hsm_state", "AUTHORIZED_ONLINE" if online else "OFFLINE_UNREACHABLE"),
            "lmk_id": "00",
            "lmk_check_value": lmk_cv,
            "lmk_kcv_short": lmk_cv[:6],
            "firmware": remote.get("firmware", "N/A"),
            "remote_url": svc.bridge.execute_url,
            "key_counts": counts,
        }
        if warning:
            status_info["warning"] = warning

    status_info["active_provider"] = active_provider
    status_info["hsm_mode"] = settings.HSM_MODE
    return {
        "status": "OK",
        "switched": True,
        "provider_type": active_provider,
        **status_info,
    }


