#!/usr/bin/env python3
"""
tools/install_step13_06_card_profiles_dynamic.py
================================================
Fixes & upgrades Card Profile and BIN-to-Card-Profile Management across Backend & Frontend:
  1. Backend Schema Fixes (`backend/app/schemas.py`):
     - Adds `card_profile_id`, `card_profile_code`, and `card_profile_name` to `BinRangeCreate`,
       `BinRangeUpdate`, and `BinRangeOut` so FastAPI never strips Card Profile associations.
  2. Backend Router Upgrades (`backend/app/routers/institutions_router.py` & `limits_and_profiles_router.py`):
     - Exposes both `/api/bin-ranges` and `/api/bins` aliases.
     - Persists `card_profile_id` when creating or updating a BIN range in `/api/bin-ranges`.
     - Removes the rigid institution mismatch block in `assign_card_profile_to_bin` so any active
       Card Profile (bank-specific or shared multi-bank) can be assigned to any bank's BIN range.
     - Adds bulk BIN assignment (`POST /api/card-profiles-v2/{profile_id}/assign-bins`),
       status toggle (`PATCH /api/card-profiles-v2/{profile_id}/status`),
       safe delete/archive (`DELETE /api/card-profiles-v2/{profile_id}`), and
       on-demand card inheritance sync (`POST /api/card-profiles-v2/{profile_id}/sync-cards`).
  3. Dynamic Frontend Workbench (`frontend/src/pages/CardProfilesUnderBinTab.tsx` & `InstitutionsAndBinsPage.tsx`):
     - Uses resilient `Promise.allSettled` with `apiFetch` from `'../api'` so Institutions,
       Processing Systems, BIN Ranges, Card Profiles, and Auth Profiles always load reliably.
     - Supports Create, Edit, Activate/Deactivate, Delete/Archive, Multi-BIN checkbox assignment,
       Channel Permission flags (Domestic, International, E-Commerce, Contactless, ATM Cash),
       inline BIN-to-Card-Profile assignment for any bank, and Quick BIN Creation with Card Profile.
     - Integrates `3.5. Card Profiles` directly into the main tab bar of `InstitutionsAndBinsPage.tsx`.

Run from E:\\HOST_VSCODE\\host-simulator:
    python tools/install_step13_06_card_profiles_dynamic.py
"""

from datetime import datetime
from pathlib import Path
import re
import shutil
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKUP_ROOT = PROJECT_ROOT / "_backups" / f"step13_06_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def backup_file(rel_path: str) -> None:
    src = PROJECT_ROOT / rel_path
    if src.exists():
        dst = BACKUP_ROOT / rel_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def write_file(rel_path: str, content: str) -> None:
    backup_file(rel_path)
    dst = PROJECT_ROOT / rel_path
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(content, encoding="utf-8")
    print(f"[WRITE] {rel_path} ({len(content.splitlines())} lines)")


# ==============================================================================
# 1. Patch backend/app/schemas.py so BinRangeCreate/Update/Out include card_profile_id
# ==============================================================================
def patch_schemas_py() -> None:
    rel_path = "backend/app/schemas.py"
    target = PROJECT_ROOT / rel_path
    text = target.read_text(encoding="utf-8")
    backup_file(rel_path)

    marker = "# [PATCH step13_06:bin_range_card_profile_schemas]"
    if marker not in text:
        override_block = f"""
{marker}
# Override BinRangeCreate, BinRangeUpdate, and BinRangeOut to include card_profile_id & metadata
class BinRangeCreate(BaseModel):
    bin_prefix: str = Field(..., min_length=6, max_length=12, description="6 to 12 digit BIN prefix")
    bin_low: Optional[str] = None
    bin_high: Optional[str] = None
    pan_length: int = 16
    institution_id: str
    processing_system_id: Optional[str] = None
    card_profile_id: Optional[str] = None
    card_type: str = "DEBIT"
    card_product: str = "VISA_DEBIT_CLASSIC"
    scheme: str = "ITCL"
    country_code: str = "050"
    currency: str = "BDT"
    is_on_us: bool = True
    status: str = "ACTIVE"


class BinRangeUpdate(BaseModel):
    bin_prefix: Optional[str] = None
    bin_low: Optional[str] = None
    bin_high: Optional[str] = None
    pan_length: Optional[int] = None
    institution_id: Optional[str] = None
    processing_system_id: Optional[str] = None
    card_profile_id: Optional[str] = None
    card_type: Optional[str] = None
    card_product: Optional[str] = None
    scheme: Optional[str] = None
    country_code: Optional[str] = None
    currency: Optional[str] = None
    is_on_us: Optional[bool] = None
    status: Optional[str] = None


class BinRangeOut(BaseModel):
    id: str
    bin_prefix: str
    bin_low: str
    bin_high: str
    pan_length: int
    institution_id: str
    institution_code: Optional[str] = None
    institution_name: Optional[str] = None
    processing_system_id: str
    ps_code: Optional[str] = None
    ps_name: Optional[str] = None
    card_profile_id: Optional[str] = None
    card_profile_code: Optional[str] = None
    card_profile_name: Optional[str] = None
    card_type: str
    card_product: str
    scheme: str
    country_code: str
    currency: str
    is_on_us: bool
    status: str
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
"""
        text = text.rstrip() + "\n" + override_block + "\n"
        target.write_text(text, encoding="utf-8")
        print(f"[PATCH] {rel_path} updated with card_profile_id on BinRangeCreate/Update/Out")
    else:
        print(f"[SKIP]  {rel_path} already contains {marker}")


# ==============================================================================
# 2. Patch backend/app/routers/institutions_router.py to support card_profile_id on BIN CRUD & /api/bins alias
# ==============================================================================
def patch_institutions_router_py() -> None:
    rel_path = "backend/app/routers/institutions_router.py"
    target = PROJECT_ROOT / rel_path
    if not target.exists():
        return
    text = target.read_text(encoding="utf-8")
    backup_file(rel_path)

    # Ensure create_bin_range saves card_profile_id if provided
    if "card_profile_id=getattr(payload, 'card_profile_id', None)" not in text:
        text = text.replace(
            "        institution_id=inst.id,\n        processing_system_id=ps.id,",
            "        institution_id=inst.id,\n        processing_system_id=ps.id,\n        card_profile_id=getattr(payload, 'card_profile_id', None) or None,",
            1,
        )

    # Ensure update_bin_range updates card_profile_id if present in payload
    old_loop = 'for k in ("institution_id", "processing_system_id", "card_type", "card_product", "scheme", "country_code", "currency", "is_on_us", "status"):'
    new_loop = (
        'if "card_profile_id" in data:\n'
        '        b.card_profile_id = data["card_profile_id"] or None\n\n'
        '    for k in ("institution_id", "processing_system_id", "card_type", "card_product", "scheme", "country_code", "currency", "is_on_us", "status"):'
    )
    if old_loop in text and 'if "card_profile_id" in data:' not in text:
        text = text.replace(old_loop, new_loop, 1)

    # Add /api/bins GET alias if not present
    marker = "# [PATCH step13_06:bins_alias_route]"
    if marker not in text:
        alias_block = f"""
{marker}
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
"""
        text = text.rstrip() + "\n" + alias_block + "\n"

    target.write_text(text, encoding="utf-8")
    print(f"[PATCH] {rel_path} updated with card_profile_id persistence and /api/bins alias")


# ==============================================================================
# 3. Update backend/app/routers/limits_and_profiles_router.py with full dynamic Card Profile & BIN endpoints
# ==============================================================================
def patch_limits_and_profiles_router_py() -> None:
    rel_path = "backend/app/routers/limits_and_profiles_router.py"
    target = PROJECT_ROOT / rel_path
    if not target.exists():
        raise FileNotFoundError(f"Missing {rel_path}. Run Batch 3 first.")

    text = target.read_text(encoding="utf-8")
    backup_file(rel_path)

    # 1. Remove the restrictive 400 institution mismatch check in assign_card_profile_to_bin
    bad_check = '''        if getattr(cp, "institution_id", None) and b.institution_id and cp.institution_id != b.institution_id:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Institution mismatch: BIN '{b.bin_prefix}' belongs to institution '{b.institution_id}', "
                    f"while Card Profile '{cp.profile_code}' belongs to '{cp.institution_id}'"
                ),
            )'''
    if bad_check in text:
        text = text.replace(bad_check, "        # Allow assigning any active Card Profile across member bank BIN ranges", 1)

    # 2. In create_card_profile_v2, allow institution_id to be None (Shared Multi-Bank Switch Profile) or specific bank
    old_inst_fallback = '''    inst_id = payload.get("institution_id")
    ps_id = payload.get("processing_system_id")
    if not inst_id:
        xbank = db.query(Institution).filter(Institution.institution_code == "XBANK").first()
        inst_id = xbank.id if xbank else None'''
    new_inst_fallback = '''    raw_inst = payload.get("institution_id")
    inst_id = None if raw_inst in (None, "", "ALL", "SHARED") else raw_inst
    ps_id = payload.get("processing_system_id") or None
    if not ps_id:
        itcl = db.query(ProcessingSystem).filter(ProcessingSystem.ps_code == "ITCL").first()
        ps_id = itcl.id if itcl else None'''
    if old_inst_fallback in text:
        text = text.replace(old_inst_fallback, new_inst_fallback, 1)

    # 3. In update_card_profile_v2, also allow updating bin_ids if passed in payload
    old_update_commit = '''    record_audit(
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
    return {"status": "updated", "id": prof.id, "profile_code": prof.profile_code}'''

    new_update_commit = '''    if "institution_id" in payload and payload["institution_id"] in ("", "ALL", "SHARED", None):
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
    return {"status": "updated", "id": prof.id, "profile_code": prof.profile_code}'''
    if old_update_commit in text:
        text = text.replace(old_update_commit, new_update_commit, 1)

    # 4. Append dynamic Card Profile management endpoints (bulk BIN assignment, status toggle, delete/archive, sync-cards, /bin-ranges alias)
    marker = "# [PATCH step13_06:card_profile_dynamic_endpoints]"
    if marker not in text:
        dynamic_endpoints = f"""
{marker}
@router.put("/bin-ranges/{{bin_id}}/assign-card-profile")
def assign_card_profile_to_bin_range_alias(
    bin_id: str,
    payload: BinCardProfileAssignRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    return assign_card_profile_to_bin(bin_id=bin_id, payload=payload, db=db, current_user=current_user)


@router.post("/card-profiles-v2/{{profile_id}}/assign-bins")
def bulk_assign_bins_to_card_profile(
    profile_id: str,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    \"\"\"
    Assigns a list of BIN Range IDs (`bin_ids`) to a Card Profile in one atomic operation.
    Any BIN previously assigned to this Card Profile that is not in `bin_ids` is unassigned
    (unless `append_only=True`).
    \"\"\"
    prof = db.query(CardProfile).filter(CardProfile.id == profile_id).first()
    if not prof:
        raise HTTPException(status_code=404, detail="Card Profile not found")
    if prof.status != "ACTIVE":
        raise HTTPException(status_code=400, detail=f"Card Profile '{{prof.profile_code}}' is not ACTIVE")

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
        change_summary=f"Assigned {{len(assigned_prefixes)}} BIN range(s) ({{', '.join(assigned_prefixes) or 'none'}}) to Card Profile '{{prof.profile_code}}'",
    )
    db.commit()
    return {{
        "status": "updated",
        "card_profile_id": prof.id,
        "profile_code": prof.profile_code,
        "assigned_bin_prefixes": assigned_prefixes,
        "assigned_count": len(assigned_prefixes),
    }}


@router.patch("/card-profiles-v2/{{profile_id}}/status")
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
        change_summary=f"Changed Card Profile '{{prof.profile_code}}' status to {{next_status}}",
    )
    db.commit()
    return {{"status": "updated", "id": prof.id, "profile_code": prof.profile_code, "new_status": prof.status}}


@router.post("/card-profiles-v2/{{profile_id}}/sync-cards")
def sync_cards_under_profile_bins(
    profile_id: str,
    overwrite_existing: bool = Query(False, description="If true, updates all cards under linked BINs; otherwise only unassigned cards"),
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    \"\"\"
    Explicit operator action to synchronize issued cards whose PAN matches the BIN ranges
    assigned to this Card Profile.
    \"\"\"
    prof = db.query(CardProfile).filter(CardProfile.id == profile_id).first()
    if not prof:
        raise HTTPException(status_code=404, detail="Card Profile not found")

    linked_bins = db.query(BinRange).filter(BinRange.card_profile_id == prof.id).all()
    if not linked_bins:
        return {{"status": "no_bins", "updated_cards": 0, "message": f"No BIN ranges are linked to {{prof.profile_code}}"}}

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
        change_summary=f"Synchronized {{updated_count}} card(s) under BINs of Card Profile '{{prof.profile_code}}'",
    )
    db.commit()
    return {{
        "status": "synced",
        "card_profile_id": prof.id,
        "profile_code": prof.profile_code,
        "updated_cards": updated_count,
    }}


@router.delete("/card-profiles-v2/{{profile_id}}")
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
            change_summary=f"Deactivated Card Profile '{{prof.profile_code}}' (linked to {{bin_count}} BINs, {{card_count}} cards, {{auth_count}} auth profiles)",
        )
        db.commit()
        return {{
            "status": "deactivated",
            "id": prof.id,
            "profile_code": prof.profile_code,
            "message": f"Card Profile '{{prof.profile_code}}' has been safely deactivated.",
        }}

    if (bin_count > 0 or card_count > 0 or auth_count > 0) and not force:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot hard-delete Card Profile '{{prof.profile_code}}' because it is linked to "
                f"{{bin_count}} BIN range(s), {{card_count}} card(s), and {{auth_count}} Authorization Profile(s). "
                f"Deactivate it instead or use Force Delete to detach references."
            ),
        )

    before = serialize_entity(prof)
    db.query(BinRange).filter(BinRange.card_profile_id == prof.id).update({{"card_profile_id": None}}, synchronize_session=False)
    db.query(Card).filter(Card.card_profile_id == prof.id).update({{"card_profile_id": None}}, synchronize_session=False)
    db.query(AuthorizationProfile).filter(AuthorizationProfile.card_profile_id == prof.id).update({{"card_profile_id": None}}, synchronize_session=False)
    db.delete(prof)
    record_audit(
        db,
        "CARD_PROFILE",
        profile_id,
        "DELETE",
        performed_by=current_user,
        before_state=before,
        change_summary=f"Deleted Card Profile '{{prof.profile_code}}' (Force={{force}})",
    )
    db.commit()
    return {{"status": "deleted", "id": profile_id, "profile_code": prof.profile_code}}
"""
        text = text.rstrip() + "\n" + dynamic_endpoints + "\n"

    target.write_text(text, encoding="utf-8")
    print(f"[PATCH] {rel_path} upgraded with dynamic Card Profile & BIN endpoints")


# ==============================================================================
# 4. Write Dynamic frontend/src/pages/CardProfilesUnderBinTab.tsx
# ==============================================================================
DYNAMIC_CARD_PROFILES_TSX = '''import React, { useEffect, useMemo, useState } from 'react';
import {
  CreditCard,
  Plus,
  Edit3,
  Trash2,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  Link2,
  Layers,
  Search,
  Power,
  ShieldCheck,
  X,
  ArrowRight,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { apiFetch } from '../api';

interface AssociatedBin {
  id: string;
  bin_prefix: string;
  bin_low: string;
  bin_high: string;
  card_type: string;
  card_product: string;
  scheme: string;
  status: string;
}

interface CardProfileItem {
  id: string;
  profile_code: string;
  profile_name: string;
  description?: string | null;
  institution_id?: string | null;
  institution_code?: string;
  institution_name?: string;
  processing_system_id?: string | null;
  ps_code?: string;
  ps_name?: string;
  card_type: string;
  currency: string;
  card_product: string;
  domestic_enabled: boolean;
  international_enabled: boolean;
  ecommerce_enabled: boolean;
  contactless_enabled: boolean;
  cash_enabled: boolean;
  status: string;
  created_at?: string | null;
  card_count: number;
  associated_bins: AssociatedBin[];
  authorization_profiles: {
    id: string;
    auth_profile_code: string;
    profile_name: string;
    status: string;
  }[];
}

export const CardProfilesUnderBinTab: React.FC = () => {
  const [profiles, setProfiles] = useState<CardProfileItem[]>([]);
  const [bins, setBins] = useState<any[]>([]);
  const [institutions, setInstitutions] = useState<any[]>([]);
  const [systems, setSystems] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [banner, setBanner] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Filters for Card Profiles table
  const [searchQuery, setSearchQuery] = useState('');
  const [filterBank, setFilterBank] = useState('');
  const [filterSwitch, setFilterSwitch] = useState('');
  const [filterType, setFilterType] = useState('');
  const [filterStatus, setFilterStatus] = useState('');

  // Filters for BIN-to-Profile Matrix
  const [binSearch, setBinSearch] = useState('');
  const [binBankFilter, setBinBankFilter] = useState('');
  const [binAssignFilter, setBinAssignFilter] = useState<'ALL' | 'ASSIGNED' | 'UNASSIGNED'>('ALL');

  // Create / Edit Card Profile Modal
  const [showProfileModal, setShowProfileModal] = useState(false);
  const [editingProfile, setEditingProfile] = useState<CardProfileItem | null>(null);
  const [binPickerFilter, setBinPickerFilter] = useState('');
  const [form, setForm] = useState({
    profile_code: '',
    profile_name: '',
    description: '',
    institution_id: '',
    processing_system_id: '',
    card_type: 'DEBIT',
    currency: 'BDT',
    card_product: 'VISA_DEBIT_CLASSIC',
    domestic_enabled: true,
    international_enabled: false,
    ecommerce_enabled: true,
    contactless_enabled: true,
    cash_enabled: true,
    status: 'ACTIVE',
    bin_ids: [] as string[],
  });

  // Manage BINs Modal for a specific Card Profile
  const [manageBinsProfile, setManageBinsProfile] = useState<CardProfileItem | null>(null);
  const [selectedBinIds, setSelectedBinIds] = useState<string[]>([]);

  // Delete Confirmation Modal
  const [deleteTarget, setDeleteTarget] = useState<CardProfileItem | null>(null);

  // Quick Create BIN Modal
  const [showQuickBinModal, setShowQuickBinModal] = useState(false);
  const [quickBinForm, setQuickBinForm] = useState({
    bin_prefix: '456798',
    pan_length: 16,
    institution_id: '',
    processing_system_id: '',
    card_profile_id: '',
    card_type: 'DEBIT',
    card_product: 'VISA_DEBIT_CLASSIC',
    scheme: 'ITCL',
    currency: 'BDT',
    is_on_us: true,
    status: 'ACTIVE',
  });

  const loadAll = async () => {
    setLoading(true);
    try {
      const [cpRes, binRes, instRes, psRes] = await Promise.allSettled([
        apiFetch('/card-profiles-v2'),
        apiFetch('/bin-ranges'),
        apiFetch('/institutions'),
        apiFetch('/processing-systems'),
      ]);

      const cpList = cpRes.status === 'fulfilled' && Array.isArray(cpRes.value) ? cpRes.value : [];
      const binList = binRes.status === 'fulfilled' && Array.isArray(binRes.value) ? binRes.value : [];
      const instList = instRes.status === 'fulfilled' && Array.isArray(instRes.value) ? instRes.value : [];
      const psList = psRes.status === 'fulfilled' && Array.isArray(psRes.value) ? psRes.value : [];

      setProfiles(cpList);
      setBins(binList);
      setInstitutions(instList);
      setSystems(psList);
    } catch (err: any) {
      setBanner({ type: 'error', text: err?.message || 'Failed to load Card Profiles data' });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAll();
  }, []);

  // Filtered Card Profiles
  const filteredProfiles = useMemo(() => {
    return profiles.filter((cp) => {
      if (filterBank === 'SHARED' && cp.institution_id) return false;
      if (filterBank && filterBank !== 'SHARED' && cp.institution_id !== filterBank) return false;
      if (filterSwitch && cp.processing_system_id !== filterSwitch) return false;
      if (filterType && cp.card_type !== filterType) return false;
      if (filterStatus && cp.status !== filterStatus) return false;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const inCode = (cp.profile_code || '').toLowerCase().includes(q);
        const inName = (cp.profile_name || '').toLowerCase().includes(q);
        const inProd = (cp.card_product || '').toLowerCase().includes(q);
        const inBank = (cp.institution_code || '').toLowerCase().includes(q);
        const inBins = (cp.associated_bins || []).some((b) => b.bin_prefix.includes(q));
        if (!inCode && !inName && !inProd && !inBank && !inBins) return false;
      }
      return true;
    });
  }, [profiles, filterBank, filterSwitch, filterType, filterStatus, searchQuery]);

  // Filtered BINs for Matrix
  const filteredBins = useMemo(() => {
    return bins.filter((b) => {
      if (binBankFilter && b.institution_id !== binBankFilter) return false;
      if (binAssignFilter === 'ASSIGNED' && !b.card_profile_id) return false;
      if (binAssignFilter === 'UNASSIGNED' && b.card_profile_id) return false;
      if (binSearch.trim()) {
        const q = binSearch.toLowerCase();
        const matchPrefix = (b.bin_prefix || '').toLowerCase().includes(q);
        const matchBank = (b.institution_code || '').toLowerCase().includes(q);
        const matchProf = (b.card_profile_code || '').toLowerCase().includes(q);
        const matchProd = (b.card_product || '').toLowerCase().includes(q);
        if (!matchPrefix && !matchBank && !matchProf && !matchProd) return false;
      }
      return true;
    });
  }, [bins, binBankFilter, binAssignFilter, binSearch]);

  // Summary Metrics
  const metrics = useMemo(() => {
    const activeProfiles = profiles.filter((p) => p.status === 'ACTIVE').length;
    const assignedBins = bins.filter((b) => !!b.card_profile_id).length;
    const unassignedBins = bins.length - assignedBins;
    const totalCardsLinked = profiles.reduce((acc, p) => acc + (p.card_count || 0), 0);
    const totalAuthProfiles = profiles.reduce(
      (acc, p) => acc + (p.authorization_profiles ? p.authorization_profiles.length : 0),
      0
    );
    return {
      totalProfiles: profiles.length,
      activeProfiles,
      assignedBins,
      unassignedBins,
      totalCardsLinked,
      totalAuthProfiles,
    };
  }, [profiles, bins]);

  // Open Create Card Profile Modal
  const openCreateModal = () => {
    setEditingProfile(null);
    setBinPickerFilter('');
    setForm({
      profile_code: `VISA_PROF_${Math.floor(100 + Math.random() * 900)}`,
      profile_name: 'VISA Custom Debit Profile',
      description: 'Configurable card profile governing BIN routing and authorization limits',
      institution_id: institutions[0]?.id || '',
      processing_system_id: systems[0]?.id || '',
      card_type: 'DEBIT',
      currency: 'BDT',
      card_product: 'VISA_DEBIT_CLASSIC',
      domestic_enabled: true,
      international_enabled: false,
      ecommerce_enabled: true,
      contactless_enabled: true,
      cash_enabled: true,
      status: 'ACTIVE',
      bin_ids: [],
    });
    setShowProfileModal(true);
  };

  // Open Edit Card Profile Modal
  const openEditModal = (cp: CardProfileItem) => {
    setEditingProfile(cp);
    setBinPickerFilter('');
    setForm({
      profile_code: cp.profile_code,
      profile_name: cp.profile_name,
      description: cp.description || '',
      institution_id: cp.institution_id || '',
      processing_system_id: cp.processing_system_id || systems[0]?.id || '',
      card_type: cp.card_type || 'DEBIT',
      currency: cp.currency || 'BDT',
      card_product: cp.card_product || 'VISA_DEBIT_CLASSIC',
      domestic_enabled: cp.domestic_enabled ?? true,
      international_enabled: cp.international_enabled ?? false,
      ecommerce_enabled: cp.ecommerce_enabled ?? true,
      contactless_enabled: cp.contactless_enabled ?? true,
      cash_enabled: cp.cash_enabled ?? true,
      status: cp.status || 'ACTIVE',
      bin_ids: (cp.associated_bins || []).map((b) => b.id),
    });
    setShowProfileModal(true);
  };

  const toggleBinInForm = (binId: string) => {
    setForm((prev) => {
      const exists = prev.bin_ids.includes(binId);
      return {
        ...prev,
        bin_ids: exists ? prev.bin_ids.filter((id) => id !== binId) : [...prev.bin_ids, binId],
      };
    });
  };

  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setBanner(null);
    try {
      const payload = {
        ...form,
        profile_code: form.profile_code.trim().toUpperCase(),
        profile_name: form.profile_name.trim(),
        institution_id: form.institution_id || null,
        processing_system_id: form.processing_system_id || null,
      };
      if (editingProfile) {
        await apiFetch(`/card-profiles-v2/${editingProfile.id}`, {
          method: 'PUT',
          body: JSON.stringify(payload),
        });
        setBanner({
          type: 'success',
          text: `Updated Card Profile '${payload.profile_code}' and synchronized ${form.bin_ids.length} BIN association(s).`,
        });
      } else {
        await apiFetch('/card-profiles-v2', {
          method: 'POST',
          body: JSON.stringify(payload),
        });
        setBanner({
          type: 'success',
          text: `Created Card Profile '${payload.profile_code}' (${payload.profile_name}) with ${form.bin_ids.length} associated BIN(s).`,
        });
      }
      setShowProfileModal(false);
      await loadAll();
    } catch (err: any) {
      setBanner({ type: 'error', text: err?.message || 'Failed to save Card Profile' });
    }
  };

  const handleToggleProfileStatus = async (cp: CardProfileItem) => {
    try {
      const res = await apiFetch(`/card-profiles-v2/${cp.id}/status`, { method: 'PATCH' });
      setBanner({
        type: 'success',
        text: `Card Profile '${cp.profile_code}' is now ${res.new_status}`,
      });
      await loadAll();
    } catch (err: any) {
      setBanner({ type: 'error', text: err?.message || 'Failed to toggle status' });
    }
  };

  const handleSyncCards = async (cp: CardProfileItem) => {
    try {
      const res = await apiFetch(`/card-profiles-v2/${cp.id}/sync-cards?overwrite_existing=true`, {
        method: 'POST',
      });
      setBanner({
        type: 'success',
        text: `Synchronized ${res.updated_cards ?? 0} card(s) under BIN ranges linked to '${cp.profile_code}'.`,
      });
      await loadAll();
    } catch (err: any) {
      setBanner({ type: 'error', text: err?.message || 'Failed to synchronize cards' });
    }
  };

  const handleConfirmDeleteProfile = async (deactivateOnly: boolean, force: boolean) => {
    if (!deleteTarget) return;
    try {
      const res = await apiFetch(
        `/card-profiles-v2/${deleteTarget.id}?deactivate_only=${deactivateOnly}&force=${force}`,
        { method: 'DELETE' }
      );
      setBanner({
        type: 'success',
        text: res.message || `Card Profile '${deleteTarget.profile_code}' ${res.status}`,
      });
      setDeleteTarget(null);
      await loadAll();
    } catch (err: any) {
      setBanner({ type: 'error', text: err?.message || 'Delete failed' });
    }
  };

  // Manage BINs Modal Handlers
  const openManageBinsModal = (cp: CardProfileItem) => {
    setManageBinsProfile(cp);
    setSelectedBinIds((cp.associated_bins || []).map((b) => b.id));
  };

  const handleSaveManagedBins = async () => {
    if (!manageBinsProfile) return;
    try {
      const res = await apiFetch(`/card-profiles-v2/${manageBinsProfile.id}/assign-bins`, {
        method: 'POST',
        body: JSON.stringify({ bin_ids: selectedBinIds, append_only: false }),
      });
      setBanner({
        type: 'success',
        text: `Updated BIN assignments for '${manageBinsProfile.profile_code}' (${res.assigned_count} BIN range(s) linked).`,
      });
      setManageBinsProfile(null);
      await loadAll();
    } catch (err: any) {
      setBanner({ type: 'error', text: err?.message || 'Failed to update BIN assignments' });
    }
  };

  // Inline BIN-to-Profile Assignment in Matrix
  const handleAssignBinProfile = async (binId: string, cardProfileId: string) => {
    try {
      const res = await apiFetch(`/bins/${binId}/assign-card-profile`, {
        method: 'PUT',
        body: JSON.stringify({ card_profile_id: cardProfileId || null }),
      });
      setBanner({
        type: 'success',
        text: cardProfileId
          ? `Assigned Card Profile '${res.card_profile_code}' to BIN ${res.bin_prefix}`
          : `Unassigned Card Profile from BIN ${res.bin_prefix}`,
      });
      await loadAll();
    } catch (err: any) {
      setBanner({ type: 'error', text: err?.message || 'Failed to assign Card Profile to BIN' });
    }
  };

  // Quick Create BIN with Card Profile
  const openQuickBinModal = () => {
    setQuickBinForm({
      bin_prefix: `4567${Math.floor(10 + Math.random() * 89)}`,
      pan_length: 16,
      institution_id: institutions[0]?.id || '',
      processing_system_id: systems[0]?.id || '',
      card_profile_id: profiles.find((p) => p.status === 'ACTIVE')?.id || '',
      card_type: 'DEBIT',
      card_product: 'VISA_DEBIT_CLASSIC',
      scheme: 'ITCL',
      currency: 'BDT',
      is_on_us: true,
      status: 'ACTIVE',
    });
    setShowQuickBinModal(true);
  };

  const handleQuickCreateBin = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await apiFetch('/bin-ranges', {
        method: 'POST',
        body: JSON.stringify({
          ...quickBinForm,
          card_profile_id: quickBinForm.card_profile_id || null,
        }),
      });
      setBanner({
        type: 'success',
        text: `Created BIN ${res.bin_prefix} for ${res.institution_code} ${
          res.card_profile_code ? `linked to Card Profile '${res.card_profile_code}'` : ''
        }`,
      });
      setShowQuickBinModal(false);
      await loadAll();
    } catch (err: any) {
      setBanner({ type: 'error', text: err?.message || 'Failed to create BIN range' });
    }
  };

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 bg-slate-900/90 border border-slate-800 rounded-xl p-5">
        <div>
          <div className="flex items-center gap-2">
            <span className="px-2.5 py-0.5 text-[11px] font-mono uppercase rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
              MODULE 3 · BIN &rarr; CARD PROFILE &rarr; AUTH PROFILE
            </span>
          </div>
          <h2 className="text-xl font-bold text-white mt-1 flex items-center gap-2">
            <CreditCard className="text-emerald-400" size={22} />
            Card Profile &amp; BIN Range Association Workbench
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Create bank-specific or multi-bank Card Profiles, configure channel permissions, and dynamically bind them to any bank&apos;s BIN ranges.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={loadAll}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-mono text-slate-200 border border-slate-700"
          >
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
          <button
            onClick={openQuickBinModal}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow"
          >
            <Plus size={14} /> + New BIN with Profile
          </button>
          <button
            onClick={openCreateModal}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold shadow"
          >
            <Plus size={14} /> + Create Card Profile
          </button>
        </div>
      </div>

      {/* KPI Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
        <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-3.5">
          <div className="text-[11px] font-mono text-slate-400 uppercase">Total Profiles</div>
          <div className="text-xl font-bold text-white font-mono mt-1">{metrics.totalProfiles}</div>
        </div>
        <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-3.5">
          <div className="text-[11px] font-mono text-slate-400 uppercase">Active Profiles</div>
          <div className="text-xl font-bold text-emerald-400 font-mono mt-1">{metrics.activeProfiles}</div>
        </div>
        <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-3.5">
          <div className="text-[11px] font-mono text-slate-400 uppercase">Linked BINs</div>
          <div className="text-xl font-bold text-indigo-400 font-mono mt-1">{metrics.assignedBins}</div>
        </div>
        <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-3.5">
          <div className="text-[11px] font-mono text-slate-400 uppercase">Unassigned BINs</div>
          <div className="text-xl font-bold text-amber-400 font-mono mt-1">{metrics.unassignedBins}</div>
        </div>
        <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-3.5">
          <div className="text-[11px] font-mono text-slate-400 uppercase">Auth Profiles</div>
          <div className="text-xl font-bold text-sky-400 font-mono mt-1">{metrics.totalAuthProfiles}</div>
        </div>
        <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-3.5">
          <div className="text-[11px] font-mono text-slate-400 uppercase">Cards Using Profiles</div>
          <div className="text-xl font-bold text-purple-400 font-mono mt-1">{metrics.totalCardsLinked}</div>
        </div>
      </div>

      {banner && (
        <div
          className={`p-3.5 rounded-xl border text-xs font-mono flex items-center justify-between ${
            banner.type === 'success'
              ? 'bg-emerald-950/60 border-emerald-500/40 text-emerald-200'
              : 'bg-rose-950/60 border-rose-500/40 text-rose-200'
          }`}
        >
          <span className="flex items-center gap-2">
            {banner.type === 'success' ? <CheckCircle2 size={15} /> : <AlertTriangle size={15} />}
            {banner.text}
          </span>
          <button onClick={() => setBanner(null)} className="underline ml-4">
            Dismiss
          </button>
        </div>
      )}

      {/* Filter Bar for Card Profiles */}
      <div className="grid grid-cols-1 md:grid-cols-6 gap-3 bg-slate-900/70 border border-slate-800 rounded-xl p-4">
        <div className="md:col-span-2 relative">
          <Search size={14} className="absolute left-3 top-2.5 text-slate-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search profile code, name, product, bank, or BIN..."
            className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-8 pr-3 py-1.5 text-xs text-white"
          />
        </div>
        <select
          value={filterBank}
          onChange={(e) => setFilterBank(e.target.value)}
          className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-200"
        >
          <option value="">All Member Banks</option>
          <option value="SHARED">Shared / Multi-Bank Profiles</option>
          {institutions.map((i) => (
            <option key={i.id} value={i.id}>
              {i.short_name || i.institution_code} — {i.name}
            </option>
          ))}
        </select>
        <select
          value={filterSwitch}
          onChange={(e) => setFilterSwitch(e.target.value)}
          className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-200"
        >
          <option value="">All Processing Switches</option>
          {systems.map((s) => (
            <option key={s.id} value={s.id}>
              {s.ps_code} — {s.name}
            </option>
          ))}
        </select>
        <select
          value={filterType}
          onChange={(e) => setFilterType(e.target.value)}
          className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-200"
        >
          <option value="">All Card Types</option>
          <option value="DEBIT">DEBIT</option>
          <option value="CREDIT">CREDIT</option>
          <option value="PREPAID">PREPAID</option>
        </select>
        <select
          value={filterStatus}
          onChange={(e) => setFilterStatus(e.target.value)}
          className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-200"
        >
          <option value="">All Statuses</option>
          <option value="ACTIVE">ACTIVE</option>
          <option value="INACTIVE">INACTIVE</option>
        </select>
      </div>

      {/* Card Profiles Table */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl overflow-hidden">
        <div className="px-5 py-3.5 border-b border-slate-800 flex items-center justify-between">
          <span className="text-sm font-bold text-slate-200">
            Configured Card Profiles ({filteredProfiles.length})
          </span>
          <span className="text-xs text-slate-400">
            Click <strong className="text-indigo-300">Manage BINs</strong> on any row to bind/unbind BIN ranges across any bank
          </span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-800 bg-slate-950/60 text-[11px] uppercase text-slate-400 font-mono">
                <th className="py-3 px-4">Card Profile ID</th>
                <th className="py-3 px-4">Profile Name &amp; Channels</th>
                <th className="py-3 px-4">Bank / Switch</th>
                <th className="py-3 px-4">Type / Currency</th>
                <th className="py-3 px-4">Associated BIN Ranges</th>
                <th className="py-3 px-4">Auth Profile</th>
                <th className="py-3 px-4 text-center">Cards</th>
                <th className="py-3 px-4 text-center">Status</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {filteredProfiles.length === 0 ? (
                <tr>
                  <td colSpan={9} className="py-8 text-center text-slate-500 text-xs">
                    No Card Profiles match the current filter. Click &quot;+ Create Card Profile&quot; to add one.
                  </td>
                </tr>
              ) : (
                filteredProfiles.map((cp) => (
                  <tr key={cp.id} className="hover:bg-slate-800/35 transition">
                    <td className="py-3.5 px-4 font-mono font-bold text-indigo-300">
                      {cp.profile_code}
                      <div className="text-[10px] text-slate-500 font-normal mt-0.5">
                        {cp.card_product}
                      </div>
                    </td>
                    <td className="py-3.5 px-4">
                      <div className="font-semibold text-white">{cp.profile_name}</div>
                      <div className="text-xs text-slate-400 line-clamp-1">
                        {cp.description || 'Standard card profile'}
                      </div>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {cp.domestic_enabled && (
                          <span className="px-1.5 py-0.2 text-[10px] font-mono rounded bg-slate-800 text-emerald-300">
                            DOM
                          </span>
                        )}
                        {cp.international_enabled && (
                          <span className="px-1.5 py-0.2 text-[10px] font-mono rounded bg-slate-800 text-sky-300">
                            INTL
                          </span>
                        )}
                        {cp.ecommerce_enabled && (
                          <span className="px-1.5 py-0.2 text-[10px] font-mono rounded bg-slate-800 text-indigo-300">
                            ECOM
                          </span>
                        )}
                        {cp.contactless_enabled && (
                          <span className="px-1.5 py-0.2 text-[10px] font-mono rounded bg-slate-800 text-amber-300">
                            NFC
                          </span>
                        )}
                        {cp.cash_enabled && (
                          <span className="px-1.5 py-0.2 text-[10px] font-mono rounded bg-slate-800 text-purple-300">
                            ATM
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="py-3.5 px-4 text-xs font-mono">
                      <span className="text-sky-300 font-bold">
                        {cp.institution_id ? cp.institution_code : 'ALL BANKS (SHARED)'}
                      </span>
                      <div className="text-amber-300 text-[11px]">{cp.ps_code || 'ITCL'}</div>
                    </td>
                    <td className="py-3.5 px-4 font-mono text-xs text-slate-200">
                      <span className="px-2 py-0.5 rounded bg-slate-800 border border-slate-700">
                        {cp.card_type}
                      </span>{' '}
                      · {cp.currency}
                    </td>
                    <td className="py-3.5 px-4">
                      <div className="flex flex-wrap items-center gap-1">
                        {cp.associated_bins && cp.associated_bins.length > 0 ? (
                          cp.associated_bins.map((b) => (
                            <span
                              key={b.id}
                              className="px-2 py-0.5 text-xs font-mono font-bold rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30"
                              title={`${b.bin_low} .. ${b.bin_high} (${b.scheme})`}
                            >
                              {b.bin_prefix}
                            </span>
                          ))
                        ) : (
                          <span className="text-xs text-slate-500 italic">No BINs linked</span>
                        )}
                        <button
                          onClick={() => openManageBinsModal(cp)}
                          className="ml-1 px-2 py-0.5 text-[11px] font-mono rounded bg-slate-800 hover:bg-indigo-600 text-slate-300 hover:text-white border border-slate-700 transition"
                        >
                          + Manage BINs
                        </button>
                      </div>
                    </td>
                    <td className="py-3.5 px-4">
                      {cp.authorization_profiles && cp.authorization_profiles.length > 0 ? (
                        <div className="space-y-1">
                          {cp.authorization_profiles.map((ap) => (
                            <Link
                              key={ap.id}
                              to="/authorization-profiles"
                              className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-mono rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 hover:bg-emerald-500/30"
                            >
                              {ap.auth_profile_code} <ArrowRight size={11} />
                            </Link>
                          ))}
                        </div>
                      ) : (
                        <Link
                          to="/authorization-profiles"
                          className="text-xs text-amber-400 hover:underline font-mono"
                        >
                          + Link Auth Profile
                        </Link>
                      )}
                    </td>
                    <td className="py-3.5 px-4 text-center font-mono text-xs text-slate-200">
                      <div>{cp.card_count || 0}</div>
                      {cp.associated_bins && cp.associated_bins.length > 0 && (
                        <button
                          onClick={() => handleSyncCards(cp)}
                          className="text-[10px] text-indigo-400 hover:underline"
                          title="Sync cards under associated BINs to use this Card Profile"
                        >
                          Sync Cards
                        </button>
                      )}
                    </td>
                    <td className="py-3.5 px-4 text-center">
                      <button
                        onClick={() => handleToggleProfileStatus(cp)}
                        className={`px-2.5 py-0.5 text-xs font-semibold rounded border transition ${
                          cp.status === 'ACTIVE'
                            ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                            : 'bg-slate-800 text-slate-400 border-slate-700'
                        }`}
                      >
                        {cp.status}
                      </button>
                    </td>
                    <td className="py-3.5 px-4 text-right space-x-1.5 whitespace-nowrap">
                      <button
                        onClick={() => openEditModal(cp)}
                        className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-xs text-slate-200"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => setDeleteTarget(cp)}
                        className="px-2.5 py-1 rounded bg-rose-950/70 hover:bg-rose-900/80 text-xs text-rose-300 border border-rose-500/30"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Dynamic BIN-to-Card-Profile Association Matrix */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl overflow-hidden">
        <div className="p-4 border-b border-slate-800 flex flex-col md:flex-row md:items-center md:justify-between gap-3">
          <div>
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <Link2 size={16} className="text-indigo-400" />
              Dynamic BIN-to-Card-Profile Assignment Matrix ({filteredBins.length} of {bins.length} BIN Ranges)
            </h3>
            <p className="text-xs text-slate-400">
              Select any active Card Profile from the dropdown to immediately associate or change the profile for any bank&apos;s BIN range.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <input
              type="text"
              value={binSearch}
              onChange={(e) => setBinSearch(e.target.value)}
              placeholder="Filter BIN prefix or bank..."
              className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-white font-mono"
            />
            <select
              value={binBankFilter}
              onChange={(e) => setBinBankFilter(e.target.value)}
              className="bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200"
            >
              <option value="">All Banks</option>
              {institutions.map((i) => (
                <option key={i.id} value={i.id}>
                  {i.short_name || i.institution_code}
                </option>
              ))}
            </select>
            <select
              value={binAssignFilter}
              onChange={(e) => setBinAssignFilter(e.target.value as any)}
              className="bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200"
            >
              <option value="ALL">All BINs</option>
              <option value="ASSIGNED">Assigned Only</option>
              <option value="UNASSIGNED">Unassigned Only</option>
            </select>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-800 bg-slate-950/60 text-[11px] uppercase text-slate-400 font-mono">
                <th className="py-2.5 px-4">BIN Prefix</th>
                <th className="py-2.5 px-4">PAN Range (Low &rarr; High)</th>
                <th className="py-2.5 px-4">Owning Bank &amp; Switch</th>
                <th className="py-2.5 px-4">Product &amp; Type</th>
                <th className="py-2.5 px-4">Current Card Profile</th>
                <th className="py-2.5 px-4">Assign / Change Card Profile</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {filteredBins.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-6 text-center text-slate-500 text-xs">
                    No BIN ranges match the filter.
                  </td>
                </tr>
              ) : (
                filteredBins.map((b) => (
                  <tr key={b.id} className="hover:bg-slate-800/30">
                    <td className="py-3 px-4 font-mono font-bold text-amber-300 text-sm">
                      {b.bin_prefix}
                    </td>
                    <td className="py-3 px-4 font-mono text-xs text-slate-400">
                      {b.bin_low} &rarr; {b.bin_high}
                    </td>
                    <td className="py-3 px-4 text-xs font-mono">
                      <span className="font-bold text-sky-400">{b.institution_code}</span> /{' '}
                      <span className="text-slate-300">{b.ps_code}</span>
                    </td>
                    <td className="py-3 px-4 text-xs">
                      <span className="text-white font-medium">{b.card_product}</span>{' '}
                      <span className="font-mono text-slate-400">({b.card_type})</span>
                    </td>
                    <td className="py-3 px-4 font-mono text-xs">
                      {b.card_profile_code ? (
                        <span className="px-2.5 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 font-bold">
                          {b.card_profile_code}
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">
                          UNASSIGNED
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-4">
                      <select
                        value={b.card_profile_id || ''}
                        onChange={(e) => handleAssignBinProfile(b.id, e.target.value)}
                        className="bg-slate-950 border border-slate-700 hover:border-indigo-500 rounded-lg px-3 py-1.5 text-xs text-white font-mono transition"
                      >
                        <option value="">-- Unassigned --</option>
                        {profiles
                          .filter((cp) => cp.status === 'ACTIVE' || cp.id === b.card_profile_id)
                          .map((cp) => (
                            <option key={cp.id} value={cp.id}>
                              {cp.profile_code} — {cp.profile_name} (
                              {cp.institution_id ? cp.institution_code : 'SHARED'})
                            </option>
                          ))}
                      </select>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Create / Edit Card Profile Modal */}
      {showProfileModal && (
        <div className="fixed inset-0 z-50 bg-black/75 flex items-center justify-center p-4 overflow-y-auto">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-3xl w-full p-6 space-y-4 shadow-2xl my-8">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-lg font-bold text-white">
                {editingProfile
                  ? `Edit Card Profile: ${editingProfile.profile_code}`
                  : 'Create New Card Profile'}
              </h3>
              <button
                onClick={() => setShowProfileModal(false)}
                className="text-slate-400 hover:text-white"
              >
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleSaveProfile} className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div>
                  <label className="block text-xs text-slate-400 mb-1">
                    Card Profile ID (Code)
                  </label>
                  <input
                    type="text"
                    required
                    disabled={!!editingProfile}
                    value={form.profile_code}
                    onChange={(e) =>
                      setForm({ ...form, profile_code: e.target.value.toUpperCase() })
                    }
                    placeholder="e.g. VISA_PLATINUM"
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white font-mono disabled:opacity-60"
                  />
                </div>
                <div className="md:col-span-2">
                  <label className="block text-xs text-slate-400 mb-1">Profile Name</label>
                  <input
                    type="text"
                    required
                    value={form.profile_name}
                    onChange={(e) => setForm({ ...form, profile_name: e.target.value })}
                    placeholder="e.g. VISA Platinum Debit Profile"
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs text-slate-400 mb-1">Description</label>
                <input
                  type="text"
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                  placeholder="Optional description of the card profile"
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white"
                />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-slate-400 mb-1">
                    Institution / Bank Ownership
                  </label>
                  <select
                    value={form.institution_id}
                    onChange={(e) => setForm({ ...form, institution_id: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white"
                  >
                    <option value="">🌐 All Member Banks (Shared Switch Profile)</option>
                    {institutions.map((i) => (
                      <option key={i.id} value={i.id}>
                        {i.short_name || i.institution_code} — {i.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">
                    Processing System / Switch
                  </label>
                  <select
                    value={form.processing_system_id}
                    onChange={(e) =>
                      setForm({ ...form, processing_system_id: e.target.value })
                    }
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white"
                  >
                    {systems.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.ps_code} — {s.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Card Type</label>
                  <select
                    value={form.card_type}
                    onChange={(e) => setForm({ ...form, card_type: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white font-mono"
                  >
                    <option value="DEBIT">DEBIT</option>
                    <option value="CREDIT">CREDIT</option>
                    <option value="PREPAID">PREPAID</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Currency</label>
                  <input
                    type="text"
                    maxLength={3}
                    value={form.currency}
                    onChange={(e) =>
                      setForm({ ...form, currency: e.target.value.toUpperCase() })
                    }
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white font-mono"
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Card Product</label>
                  <input
                    type="text"
                    value={form.card_product}
                    onChange={(e) => setForm({ ...form, card_product: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white font-mono"
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Status</label>
                  <select
                    value={form.status}
                    onChange={(e) => setForm({ ...form, status: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white"
                  >
                    <option value="ACTIVE">ACTIVE</option>
                    <option value="INACTIVE">INACTIVE</option>
                  </select>
                </div>
              </div>

              {/* Channel Permissions */}
              <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
                <div className="text-xs font-semibold text-slate-300 mb-2">
                  Channel &amp; Transaction Feature Permissions
                </div>
                <div className="grid grid-cols-2 md:grid-cols-5 gap-2 text-xs">
                  {[
                    ['domestic_enabled', 'Domestic TX'],
                    ['international_enabled', 'International TX'],
                    ['ecommerce_enabled', 'E-Commerce / CNP'],
                    ['contactless_enabled', 'Contactless / NFC'],
                    ['cash_enabled', 'ATM Cash Withdrawal'],
                  ].map(([key, label]) => (
                    <label
                      key={key}
                      className="flex items-center gap-2 p-2 rounded bg-slate-900 border border-slate-800 cursor-pointer"
                    >
                      <input
                        type="checkbox"
                        checked={Boolean((form as any)[key])}
                        onChange={(e) =>
                          setForm({ ...form, [key]: e.target.checked } as any)
                        }
                      />
                      <span className="text-slate-200">{label}</span>
                    </label>
                  ))}
                </div>
              </div>

              {/* Interactive BIN Range Association Picker */}
              <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5 space-y-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <div className="text-xs font-semibold text-slate-200">
                      Associate BIN Ranges with this Card Profile ({form.bin_ids.length} selected)
                    </div>
                    <div className="text-[11px] text-slate-400">
                      You can select BIN ranges from any member bank to inherit this Card Profile.
                    </div>
                  </div>
                  <input
                    type="text"
                    value={binPickerFilter}
                    onChange={(e) => setBinPickerFilter(e.target.value)}
                    placeholder="Filter BINs by prefix or bank..."
                    className="bg-slate-900 border border-slate-700 rounded px-2.5 py-1 text-xs text-white font-mono"
                  />
                </div>
                <div className="max-h-44 overflow-y-auto grid grid-cols-1 md:grid-cols-2 gap-2 pt-1">
                  {bins
                    .filter((b) => {
                      if (!binPickerFilter.trim()) return true;
                      const q = binPickerFilter.toLowerCase();
                      return (
                        (b.bin_prefix || '').toLowerCase().includes(q) ||
                        (b.institution_code || '').toLowerCase().includes(q) ||
                        (b.card_product || '').toLowerCase().includes(q)
                      );
                    })
                    .map((b) => {
                      const checked = form.bin_ids.includes(b.id);
                      return (
                        <label
                          key={b.id}
                          className={`flex items-center justify-between p-2 rounded-lg border text-xs cursor-pointer transition ${
                            checked
                              ? 'bg-indigo-950/60 border-indigo-500 text-white'
                              : 'bg-slate-900 border-slate-800 text-slate-300 hover:border-slate-700'
                          }`}
                        >
                          <div className="flex items-center gap-2">
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={() => toggleBinInForm(b.id)}
                            />
                            <span className="font-mono font-bold text-amber-300">
                              {b.bin_prefix}
                            </span>
                            <span className="font-bold text-sky-400">
                              [{b.institution_code}]
                            </span>
                            <span className="text-slate-400 truncate max-w-[130px]">
                              {b.card_product}
                            </span>
                          </div>
                          {b.card_profile_code && (
                            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">
                              {b.card_profile_code}
                            </span>
                          )}
                        </label>
                      );
                    })}
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowProfileModal(false)}
                  className="px-4 py-2 rounded-lg bg-slate-800 text-slate-300 text-xs font-semibold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold"
                >
                  {editingProfile ? 'Save Profile & BIN Links' : 'Create Card Profile'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Manage BINs Quick Modal */}
      {manageBinsProfile && (
        <div className="fixed inset-0 z-50 bg-black/75 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-xl w-full p-6 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div>
                <h3 className="text-base font-bold text-white">
                  Manage BIN Ranges for {manageBinsProfile.profile_code}
                </h3>
                <p className="text-xs text-slate-400">
                  Check or uncheck any bank&apos;s BIN range to associate with this Card Profile.
                </p>
              </div>
              <button
                onClick={() => setManageBinsProfile(null)}
                className="text-slate-400 hover:text-white"
              >
                <X size={18} />
              </button>
            </div>

            <div className="max-h-72 overflow-y-auto space-y-2">
              {bins.map((b) => {
                const isChecked = selectedBinIds.includes(b.id);
                return (
                  <label
                    key={b.id}
                    className={`flex items-center justify-between p-3 rounded-xl border text-xs cursor-pointer ${
                      isChecked
                        ? 'bg-indigo-950/60 border-indigo-500 text-white'
                        : 'bg-slate-950 border-slate-800 text-slate-300'
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={() =>
                          setSelectedBinIds((prev) =>
                            prev.includes(b.id)
                              ? prev.filter((id) => id !== b.id)
                              : [...prev, b.id]
                          )
                        }
                      />
                      <div>
                        <span className="font-mono font-bold text-amber-300 text-sm">
                          {b.bin_prefix}
                        </span>{' '}
                        <span className="font-mono text-sky-400 font-bold">
                          ({b.institution_code} / {b.ps_code})
                        </span>
                        <div className="text-[11px] text-slate-400">
                          {b.card_product} · {b.bin_low} .. {b.bin_high}
                        </div>
                      </div>
                    </div>
                    <span className="font-mono text-[11px] text-slate-400">
                      Current: {b.card_profile_code || 'NONE'}
                    </span>
                  </label>
                );
              })}
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setManageBinsProfile(null)}
                className="px-4 py-2 rounded-lg bg-slate-800 text-slate-300 text-xs font-semibold"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveManagedBins}
                className="px-5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold"
              >
                Save BIN Associations ({selectedBinIds.length})
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Quick Create BIN with Card Profile Modal */}
      {showQuickBinModal && (
        <div className="fixed inset-0 z-50 bg-black/75 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-lg w-full p-6 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-base font-bold text-white">
                Create New BIN Range &amp; Link Card Profile
              </h3>
              <button
                onClick={() => setShowQuickBinModal(false)}
                className="text-slate-400 hover:text-white"
              >
                <X size={18} />
              </button>
            </div>
            <form onSubmit={handleQuickCreateBin} className="space-y-3 text-xs">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-400 mb-1">BIN Prefix (6-12 digits)</label>
                  <input
                    type="text"
                    required
                    maxLength={12}
                    value={quickBinForm.bin_prefix}
                    onChange={(e) =>
                      setQuickBinForm({
                        ...quickBinForm,
                        bin_prefix: e.target.value.replace(/\D/g, ''),
                      })
                    }
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-white font-mono"
                  />
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">Associated Card Profile</label>
                  <select
                    value={quickBinForm.card_profile_id}
                    onChange={(e) =>
                      setQuickBinForm({ ...quickBinForm, card_profile_id: e.target.value })
                    }
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-indigo-300 font-mono"
                  >
                    <option value="">-- Optional: Select Card Profile --</option>
                    {profiles
                      .filter((p) => p.status === 'ACTIVE')
                      .map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.profile_code} — {p.profile_name}
                        </option>
                      ))}
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-400 mb-1">Owning Bank</label>
                  <select
                    value={quickBinForm.institution_id}
                    onChange={(e) =>
                      setQuickBinForm({ ...quickBinForm, institution_id: e.target.value })
                    }
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-white"
                  >
                    {institutions.map((i) => (
                      <option key={i.id} value={i.id}>
                        {i.short_name || i.institution_code} — {i.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">Processing Switch</label>
                  <select
                    value={quickBinForm.processing_system_id}
                    onChange={(e) =>
                      setQuickBinForm({
                        ...quickBinForm,
                        processing_system_id: e.target.value,
                      })
                    }
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-white"
                  >
                    {systems.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.ps_code} — {s.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-400 mb-1">Card Product</label>
                  <input
                    type="text"
                    value={quickBinForm.card_product}
                    onChange={(e) =>
                      setQuickBinForm({ ...quickBinForm, card_product: e.target.value })
                    }
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-white font-mono"
                  />
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">Scheme</label>
                  <select
                    value={quickBinForm.scheme}
                    onChange={(e) =>
                      setQuickBinForm({ ...quickBinForm, scheme: e.target.value })
                    }
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-white font-mono"
                  >
                    <option value="ITCL">ITCL</option>
                    <option value="VISA">VISA</option>
                    <option value="MASTERCARD">MASTERCARD</option>
                    <option value="NPSB">NPSB</option>
                  </select>
                </div>
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowQuickBinModal(false)}
                  className="px-4 py-2 rounded-lg bg-slate-800 text-slate-300 font-semibold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 rounded-lg bg-emerald-600 text-white font-semibold"
                >
                  Create BIN Range
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete / Archive Confirmation Modal */}
      {deleteTarget && (
        <div className="fixed inset-0 z-50 bg-black/75 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-lg w-full p-6 space-y-4">
            <h3 className="text-lg font-bold text-white">
              Delete Card Profile &apos;{deleteTarget.profile_code}&apos;?
            </h3>
            <p className="text-xs text-slate-300">
              Associated BINs: <strong>{deleteTarget.associated_bins?.length || 0}</strong> ·
              Linked Cards: <strong>{deleteTarget.card_count || 0}</strong> · Linked Auth Profiles:{' '}
              <strong>{deleteTarget.authorization_profiles?.length || 0}</strong>
            </p>
            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setDeleteTarget(null)}
                className="px-3.5 py-2 rounded-lg bg-slate-800 text-slate-300 text-xs font-semibold"
              >
                Cancel
              </button>
              <button
                onClick={() => handleConfirmDeleteProfile(true, false)}
                className="px-3.5 py-2 rounded-lg bg-amber-600 hover:bg-amber-500 text-white text-xs font-semibold"
              >
                Safely Deactivate
              </button>
              <button
                onClick={() => handleConfirmDeleteProfile(false, true)}
                className="px-3.5 py-2 rounded-lg bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold"
              >
                Force Delete &amp; Detach
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default CardProfilesUnderBinTab;
'''


# ==============================================================================
# 5. Patch frontend/src/pages/InstitutionsAndBinsPage.tsx so Card Profiles is a first-class tab
# ==============================================================================
def patch_institutions_and_bins_page_tabs() -> None:
    rel_path = "frontend/src/pages/InstitutionsAndBinsPage.tsx"
    target = PROJECT_ROOT / rel_path
    if not target.exists():
        return
    text = target.read_text(encoding="utf-8")
    backup_file(rel_path)

    # 1. Remove the always-rendered bottom <CardProfilesUnderBinTab /> if present and render it inside its own tab
    text = re.sub(r"\s*<CardProfilesUnderBinTab\s*/>\s*(?=</div>\s*\);\s*\};)", "\n", text)

    # 2. Ensure CardProfilesUnderBinTab is imported once at top
    if "import { CardProfilesUnderBinTab } from './CardProfilesUnderBinTab';" not in text:
        text = "import { CardProfilesUnderBinTab } from './CardProfilesUnderBinTab';\n" + text

    # 3. Add 'CARD_PROFILES' to the tab state union and tab bar buttons
    text = text.replace(
        "useState<'INST' | 'PS' | 'BINS' | 'PAN_ROUTER' | 'NET'>('INST')",
        "useState<'INST' | 'PS' | 'BINS' | 'CARD_PROFILES' | 'PAN_ROUTER' | 'NET'>('INST')",
    )

    old_tab_entry = "['BINS', '3. BIN Ranges', CreditCard, bins.length],"
    new_tab_entry = (
        "['BINS', '3. BIN Ranges', CreditCard, bins.length],\n"
        "          ['CARD_PROFILES', '3.5. Card Profiles', CreditCard, 0],"
    )
    if old_tab_entry in text and "'CARD_PROFILES'" not in text:
        text = text.replace(old_tab_entry, new_tab_entry, 1)

    # 4. Render {tab === 'CARD_PROFILES' && <CardProfilesUnderBinTab />} right before TAB 4: PAN ROUTER
    pan_router_anchor = "{tab === 'PAN_ROUTER' && ("
    if pan_router_anchor in text and "tab === 'CARD_PROFILES'" not in text:
        text = text.replace(
            pan_router_anchor,
            "{tab === 'CARD_PROFILES' && <CardProfilesUnderBinTab />}\n\n      " + pan_router_anchor,
            1,
        )

    target.write_text(text, encoding="utf-8")
    print(f"[PATCH] {rel_path} updated with '3.5. Card Profiles' tab")


def main() -> int:
    print("=" * 76)
    print("STEP 13_06 INSTALLER: Dynamic Card Profiles & BIN Association Fix")
    print(f"Project Root: {PROJECT_ROOT}")
    print("=" * 76)

    patch_schemas_py()
    patch_institutions_router_py()
    patch_limits_and_profiles_router_py()
    write_file("frontend/src/pages/CardProfilesUnderBinTab.tsx", DYNAMIC_CARD_PROFILES_TSX)
    patch_institutions_and_bins_page_tabs()

    print("-" * 76)
    print("[OK] All Card Profile & BIN association fixes installed!")
    print("Restart your backend (if not using --reload) and refresh http://localhost:5173/#/card-profiles")
    print("=" * 76)
    return 0


if __name__ == "__main__":
    sys.exit(main())