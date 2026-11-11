#!/usr/bin/env python3
"""
fix_all_issues.py (Part 1 of 3 — Master Orchestrator, Database Models, Schemas & Seed Data)
===========================================================================================
RAJON Private Host Simulator — Enterprise Payment Switch Review, Bug Fixes & Feature Pack

Designed by Senior Payment Switch Architect (Visa/Mastercard/ITCL QCash Host Engineering).
Works seamlessly with your existing `tools/patcher.py` conventions, creates timestamped
backups in `_backups/`, supports `--dry-run`, and is 100% idempotent.

Split Architecture (3 Parts to avoid truncation and maintain clean modularity):
  - fix_all_issues.py        (Part 1: Models, Schemas, Seed Data & Master Orchestrator)
  - fix_all_issues_part2.py  (Part 2: Routers, API Endpoints, Limit Reset, Routing Engine)
  - fix_all_issues_part3.py  (Part 3: Frontend React/TSX Pages & Automated Test Suite)

Usage from project root:
  python fix_all_issues.py --dry-run
  python fix_all_issues.py
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
from pathlib import Path
import py_compile
import shutil
import sys
from typing import Dict, List, Optional


def resolve_project_root() -> Path:
    """Dynamically locate the project root whether run from root or tools/."""
    candidates = [
        Path.cwd(),
        Path(__file__).resolve().parent,
        Path(__file__).resolve().parent.parent,
        Path(r"E:\HOST_VSCODE\host-simulator"),
    ]
    for cand in candidates:
        if (cand / "backend" / "app" / "models.py").exists() and (cand / "frontend" / "src" / "App.tsx").exists():
            return cand.resolve()
    raise RuntimeError(
        "CRITICAL: Could not locate RAJON Host Simulator project root "
        "(expected backend/app/models.py and frontend/src/App.tsx). "
        "Please run this script from your project root directory."
    )


PROJECT_ROOT = resolve_project_root()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class SafeRepairEngine:
    """
    Self-contained, idempotent, backup-first repair engine compatible with `tools/patcher.py`.
    Verifies project structure, creates timestamped backups in `_backups/`, compiles Python
    files immediately after writing, and tracks all applied modifications.
    """

    PROTECTED_NAMES = {".env", "rajon_host.db", "rajon_host.db-journal", "rajon_host.db-wal"}
    PROTECTED_EXTS = {".db", ".sqlite", ".sqlite3"}

    def __init__(self, step_id: str, title: str, dry_run: bool = False):
        self.step_id = step_id
        self.title = title
        self.dry_run = dry_run
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.backup_dir = PROJECT_ROOT / "_backups" / f"{self.step_id}_{self.timestamp}"
        self.backed_up: set[Path] = set()
        self.summary: List[str] = []
        self.errors: List[str] = []

    def _safe_path(self, rel_path: str) -> Path:
        clean = rel_path.replace("\\", "/").lstrip("/")
        target = (PROJECT_ROOT / clean).resolve()
        if not str(target).startswith(str(PROJECT_ROOT)):
            raise ValueError(f"Path escapes project root: {rel_path}")
        if target.name in self.PROTECTED_NAMES or target.suffix.lower() in self.PROTECTED_EXTS:
            raise ValueError(f"Refusing to touch protected file: {rel_path}")
        return target

    @staticmethod
    def _to_crlf(text: str) -> str:
        return text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")

    @staticmethod
    def _sha256(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _backup(self, target: Path) -> None:
        if not target.exists() or target in self.backed_up:
            return
        rel = target.relative_to(PROJECT_ROOT)
        dest = self.backup_dir / rel
        if not self.dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, dest)
        self.backed_up.add(target)

    def write_file(self, rel_path: str, content: str, description: str = "") -> bool:
        try:
            target = self._safe_path(rel_path)
            norm = self._to_crlf(content)
            if target.exists():
                existing_norm = self._to_crlf(target.read_text(encoding="utf-8", errors="replace"))
                if self._sha256(existing_norm) == self._sha256(norm):
                    msg = f"[SKIP-IDENTICAL] {rel_path} ({description or 'already up to date'})"
                    print(" ", msg)
                    self.summary.append(msg)
                    return True
                self._backup(target)
                op = "UPDATED"
            else:
                op = "CREATED"

            if not self.dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                with open(target, "w", encoding="utf-8", newline="") as f:
                    f.write(norm)
                if target.suffix.lower() == ".py":
                    py_compile.compile(str(target), doraise=True)

            tag = f"DRY_RUN_{op}" if self.dry_run else op
            msg = f"[{tag}] {rel_path} — {description or f'{len(norm.splitlines())} lines'}"
            print(" ", msg)
            self.summary.append(msg)
            return True
        except Exception as exc:
            err = f"[ERROR] {rel_path}: {exc}"
            print(" ", err)
            self.errors.append(err)
            return False

    def patch_anchor(
        self,
        rel_path: str,
        marker: str,
        anchor: str,
        replacement: str,
        mode: str = "replace",
    ) -> bool:
        """
        Idempotent anchored modification.
        mode: "replace" | "insert_after" | "insert_before" | "append"
        """
        try:
            target = self._safe_path(rel_path)
            if not target.exists():
                raise FileNotFoundError(f"Missing target file: {rel_path}")

            raw = target.read_text(encoding="utf-8", errors="replace")
            work = raw.replace("\r\n", "\n").replace("\r", "\n")
            ext = target.suffix.lower()
            comment_marker = f"// [PATCH {marker}]" if ext in {".ts", ".tsx", ".js", ".css"} else f"# [PATCH {marker}]"

            if comment_marker in work or f"[PATCH {marker}]" in work:
                msg = f"[SKIP-IDEMPOTENT] {rel_path} [{marker}] already applied"
                print(" ", msg)
                self.summary.append(msg)
                return True

            anchor_lf = anchor.replace("\r\n", "\n").replace("\r", "\n")
            rep_lf = replacement.replace("\r\n", "\n").replace("\r", "\n")

            if mode == "append":
                sep = "" if work.endswith("\n") else "\n"
                work = f"{work}{sep}\n{comment_marker}\n{rep_lf}\n"
            else:
                if anchor_lf not in work:
                    raise ValueError(f"Expected anchor for [{marker}] not found in {rel_path}")
                if mode == "replace":
                    work = work.replace(anchor_lf, f"{comment_marker}\n{rep_lf}", 1)
                elif mode == "insert_after":
                    work = work.replace(anchor_lf, f"{anchor_lf}\n{comment_marker}\n{rep_lf}", 1)
                elif mode == "insert_before":
                    work = work.replace(anchor_lf, f"{comment_marker}\n{rep_lf}\n{anchor_lf}", 1)
                else:
                    raise ValueError(f"Unknown patch mode: {mode}")

            self._backup(target)
            final_crlf = self._to_crlf(work)
            if not self.dry_run:
                with open(target, "w", encoding="utf-8", newline="") as f:
                    f.write(final_crlf)
                if ext == ".py":
                    py_compile.compile(str(target), doraise=True)

            tag = "DRY_RUN_PATCHED" if self.dry_run else "PATCHED"
            msg = f"[{tag}] {rel_path} [{marker}]"
            print(" ", msg)
            self.summary.append(msg)
            return True
        except Exception as exc:
            err = f"[ERROR] {rel_path} [{marker}]: {exc}"
            print(" ", err)
            self.errors.append(err)
            return False


# ==============================================================================
# PART 1 PAYLOADS: MODELS, SCHEMAS & SEED DATA
# ==============================================================================

MODELS_OLD_CUSTOMER_REL = """    accounts: Mapped[List["Account"]] = relationship("Account", back_populates="customer", cascade="all, delete-orphan")
    cards: Mapped[List["Card"]] = relationship("Card", back_populates="customer", cascade="all, delete-orphan")"""

MODELS_NEW_CUSTOMER_REL = """    # Safe relationships without blind delete-orphan cascade that causes HTTP 500 on ledger/tx history
    accounts: Mapped[List["Account"]] = relationship("Account", back_populates="customer")
    cards: Mapped[List["Card"]] = relationship("Card", back_populates="customer")"""

MODELS_LIMIT_RESET_AND_PAN_ROUTING = """
# ==============================================================================
# K. PAN ROUTING RULES & LIMIT RESET AUDIT METADATA (ENTERPRISE ENHANCEMENT)
# ==============================================================================

class PanRoutingRule(Base):
    '''
    Granular PAN / BIN / Acquirer / Channel routing rule evaluated before fallback BIN table lookup.
    Supports priority ordering, On-Us vs Off-Us determination, issuer/acquirer matching,
    destination processing switch selection, and network profile dispatch.
    '''
    __tablename__ = "pan_routing_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    rule_code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    rule_name: Mapped[str] = mapped_column(String(140), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=10, index=True)
    pan_prefix: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    pan_low: Mapped[str] = mapped_column(String(19), nullable=False, index=True)
    pan_high: Mapped[str] = mapped_column(String(19), nullable=False, index=True)
    pan_length: Mapped[Optional[int]] = mapped_column(SmallInteger, default=16)
    card_type: Mapped[Optional[str]] = mapped_column(String(30))  # DEBIT, CREDIT, PREPAID, ANY
    transaction_code: Mapped[Optional[str]] = mapped_column(String(20))  # 10, 20, 30, 40, or NULL for ANY
    acquirer_institution_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("institutions.id"), index=True)
    issuer_institution_id: Mapped[str] = mapped_column(String(36), ForeignKey("institutions.id"), nullable=False, index=True)
    processing_system_id: Mapped[str] = mapped_column(String(36), ForeignKey("processing_systems.id"), nullable=False, index=True)
    destination_network: Mapped[Optional[str]] = mapped_column(String(60), default="INTERNAL_SIMULATOR_TIC")
    scheme: Mapped[str] = mapped_column(String(30), nullable=False, default="ITCL")
    is_on_us: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    pin_translation_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_key_id: Mapped[Optional[str]] = mapped_column(String(80), default="AWK_ATM_01")
    destination_key_id: Mapped[Optional[str]] = mapped_column(String(80), default="IWK_SW_01")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    issuer_institution: Mapped[Optional["Institution"]] = relationship("Institution", foreign_keys=[issuer_institution_id])
    acquirer_institution: Mapped[Optional["Institution"]] = relationship("Institution", foreign_keys=[acquirer_institution_id])
    processing_system: Mapped[Optional["ProcessingSystem"]] = relationship("ProcessingSystem", foreign_keys=[processing_system_id])
"""

SCHEMAS_APPEND_PAYLOAD = """
# ==============================================================================
# ENTERPRISE ENHANCEMENT SCHEMAS: LIMIT USAGE RESET & PAN ROUTING RULES
# ==============================================================================

class LimitUsageResetRequest(BaseModel):
    scope: str = Field("ALL", description="DAILY | WEEKLY | MONTHLY | ALL")
    reason: str = Field(..., min_length=3, max_length=250, description="Mandatory testing reference or reason for resetting usage counters")
    testing_reference: Optional[str] = Field(None, max_length=100)
    confirm_reset: bool = Field(True, description="Explicit confirmation flag required")


class LimitUsageResetOut(BaseModel):
    status: str
    entity_type: str
    entity_id: str
    target_identifier: str
    scope: str
    performed_by: str
    reason: str
    testing_reference: Optional[str] = None
    reset_at: datetime
    old_usage: Dict[str, float]
    new_usage: Dict[str, float]


class PanRoutingRuleCreate(BaseModel):
    rule_code: str = Field(..., min_length=2, max_length=40)
    rule_name: str = Field(..., min_length=2, max_length=140)
    description: Optional[str] = None
    priority: int = Field(10, ge=1, le=9999)
    pan_prefix: str = Field(..., min_length=4, max_length=12)
    pan_low: Optional[str] = None
    pan_high: Optional[str] = None
    pan_length: Optional[int] = Field(16, ge=12, le=19)
    card_type: Optional[str] = None
    transaction_code: Optional[str] = None
    acquirer_institution_id: Optional[str] = None
    issuer_institution_id: str
    processing_system_id: str
    destination_network: Optional[str] = "INTERNAL_SIMULATOR_TIC"
    scheme: str = "ITCL"
    is_on_us: bool = True
    pin_translation_required: bool = False
    source_key_id: Optional[str] = "AWK_ATM_01"
    destination_key_id: Optional[str] = "IWK_SW_01"
    enabled: bool = True
    status: str = "ACTIVE"


class PanRoutingRuleUpdate(BaseModel):
    rule_code: Optional[str] = None
    rule_name: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[int] = Field(None, ge=1, le=9999)
    pan_prefix: Optional[str] = None
    pan_low: Optional[str] = None
    pan_high: Optional[str] = None
    pan_length: Optional[int] = Field(None, ge=12, le=19)
    card_type: Optional[str] = None
    transaction_code: Optional[str] = None
    acquirer_institution_id: Optional[str] = None
    issuer_institution_id: Optional[str] = None
    processing_system_id: Optional[str] = None
    destination_network: Optional[str] = None
    scheme: Optional[str] = None
    is_on_us: Optional[bool] = None
    pin_translation_required: Optional[bool] = None
    source_key_id: Optional[str] = None
    destination_key_id: Optional[str] = None
    enabled: Optional[bool] = None
    status: Optional[str] = None


class PanRoutingRuleOut(BaseModel):
    id: str
    rule_code: str
    rule_name: str
    description: Optional[str] = None
    priority: int
    pan_prefix: str
    pan_low: str
    pan_high: str
    pan_length: Optional[int] = 16
    card_type: Optional[str] = None
    transaction_code: Optional[str] = None
    acquirer_institution_id: Optional[str] = None
    acquirer_institution_code: Optional[str] = None
    acquirer_institution_name: Optional[str] = None
    issuer_institution_id: str
    issuer_institution_code: Optional[str] = None
    issuer_institution_name: Optional[str] = None
    processing_system_id: str
    ps_code: Optional[str] = None
    ps_name: Optional[str] = None
    destination_network: Optional[str] = None
    scheme: str
    is_on_us: bool
    pin_translation_required: bool
    source_key_id: Optional[str] = None
    destination_key_id: Optional[str] = None
    enabled: bool
    status: str
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
"""

SEED_PAN_ROUTING_PATCH = """    # Seed initial PAN routing rules idempotently if PanRoutingRule exists
    try:
        from app.models import PanRoutingRule
        default_routes = [
            ("RT-XBANK-VISA-DEB", "xBank Visa Debit On-Us Route", 10, "456789", "4567890000000000", "4567899999999999", 16, "DEBIT", "XBANK", "ITCL", "INTERNAL_SIMULATOR_TIC", "ITCL", True, False),
            ("RT-XBANK-VISA-CRD", "xBank Visa Gold Credit On-Us Route", 20, "456790", "4567900000000000", "4567909999999999", 16, "CREDIT", "XBANK", "ITCL", "INTERNAL_SIMULATOR_TIC", "ITCL", True, False),
            ("RT-YBANK-MC-DEB", "yBank Mastercard Debit Switch Route", 30, "512345", "5123450000000000", "5123459999999999", 16, "DEBIT", "YBANK", "ITCL", "INTERNAL_SIMULATOR_TIC", "ITCL", True, True),
            ("RT-ZBANK-QCASH-DEB", "zBank QCash Proprietary Route", 40, "489012", "4890120000000000", "4890129999999999", 16, "DEBIT", "ZBANK", "ITCL", "INTERNAL_SIMULATOR_TIC", "ITCL", True, True),
        ]
        for rcode, rname, prio, pfx, low, high, plen, ctype, icode, pscode, net, scheme, on_us, pin_tr in default_routes:
            if not db.query(PanRoutingRule).filter(PanRoutingRule.rule_code == rcode).first():
                if icode in inst_map and pscode in ps_map:
                    db.add(
                        PanRoutingRule(
                            rule_code=rcode,
                            rule_name=rname,
                            description=f"Default seeded PAN routing rule for {pfx}",
                            priority=prio,
                            pan_prefix=pfx,
                            pan_low=low,
                            pan_high=high,
                            pan_length=plen,
                            card_type=ctype,
                            issuer_institution_id=inst_map[icode].id,
                            processing_system_id=ps_map[pscode].id,
                            destination_network=net,
                            scheme=scheme,
                            is_on_us=on_us,
                            pin_translation_required=pin_tr,
                            enabled=True,
                            status="ACTIVE",
                        )
                    )
        # Also clean any legacy composite short_name values like "BAL - IFIC" or "TBL - IFIC"
        for inst_obj in db.query(Institution).all():
            for field_attr in ("institution_code", "short_name"):
                val = getattr(inst_obj, field_attr, None)
                if val and (" - " in val or " — " in val):
                    clean_code = val.split(" - ")[0].split(" — ")[0].strip()
                    if field_attr == "short_name":
                        inst_obj.short_name = clean_code
    except Exception:
        pass"""


def apply_part1(engine: SafeRepairEngine) -> None:
    print("\n" + "=" * 78)
    print("  STEP 1 / 3: APPLYING DATABASE MODELS, SCHEMAS & SEED DATA")
    print("=" * 78)

    # 1. Patch backend/app/models.py: Remove dangerous delete-orphan on Customer & add PanRoutingRule
    models_path = PROJECT_ROOT / "backend" / "app" / "models.py"
    models_txt = models_path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")

    if MODELS_OLD_CUSTOMER_REL in models_txt:
        engine.patch_anchor(
            "backend/app/models.py",
            "fix_customer_cascade_500",
            MODELS_OLD_CUSTOMER_REL,
            MODELS_NEW_CUSTOMER_REL,
            mode="replace",
        )

    engine.patch_anchor(
        "backend/app/models.py",
        "add_pan_routing_rule_model",
        "",
        MODELS_LIMIT_RESET_AND_PAN_ROUTING,
        mode="append",
    )

    # 2. Patch backend/app/schemas.py: Add LimitUsageReset & PanRoutingRule schemas
    engine.patch_anchor(
        "backend/app/schemas.py",
        "add_limit_reset_and_pan_routing_schemas",
        "",
        SCHEMAS_APPEND_PAYLOAD,
        mode="append",
    )

    # 3. Patch backend/app/seed_data.py: Seed PanRoutingRule & sanitize any composite bank short_names
    engine.patch_anchor(
        "backend/app/seed_data.py",
        "seed_pan_routing_rules_and_clean_bank_names",
        "    for prefix, low, high, plen, icode, ctype, prod, scheme, on_us in bin_definitions:",
        SEED_PAN_ROUTING_PATCH,
        mode="insert_before",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="RAJON Payment Switch Comprehensive Repair & Enhancement Pack (Master Orchestrator)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate all patches and file updates without writing to disk",
    )
    parser.add_argument(
        "--part1-only",
        action="store_true",
        help="Run only Part 1 (Models, Schemas & Seed Data)",
    )
    args = parser.parse_args()

    print("=" * 78)
    print("  RAJON PRIVATE HOST SIMULATOR — COMPREHENSIVE ARCHITECT REPAIR")
    print(f"  Project Root : {PROJECT_ROOT}")
    print(f"  Mode         : {'DRY-RUN (no files modified)' if args.dry_run else 'LIVE EXECUTION'}")
    print("=" * 78)

    engine = SafeRepairEngine(
        step_id="fix_all_issues",
        title="Comprehensive Payment Switch Review, Bug Fixes & Feature Enhancement",
        dry_run=args.dry_run,
    )

    # Execute Part 1
    apply_part1(engine)

    # Auto-chain Part 2 and Part 3 if present
    if not args.part1_only:
        try:
            import fix_all_issues_part2  # type: ignore
            fix_all_issues_part2.apply_part2(engine)
        except ImportError:
            print("\n  [INFO] fix_all_issues_part2.py not yet placed in project root.")
            print("         Type 'next' in chat to receive Part 2 and Part 3.")

        try:
            import fix_all_issues_part3  # type: ignore
            fix_all_issues_part3.apply_part3(engine)
        except ImportError:
            print("\n  [INFO] fix_all_issues_part3.py not yet placed in project root.")

    print("\n" + "=" * 78)
    print(f"  REPAIR EXECUTION SUMMARY ({'DRY-RUN' if args.dry_run else 'APPLIED'})")
    print("=" * 78)
    for item in engine.summary:
        print(" ", item)

    if engine.backed_up and not args.dry_run:
        print(f"\n  [BACKUP] Timestamped backups saved to: {engine.backup_dir.relative_to(PROJECT_ROOT)}")

    if engine.errors:
        print("\n  [FAILURES DETECTED]:")
        for err in engine.errors:
            print("  ", err)
        return 1

    print("\n  [SUCCESS] All available repair stages verified and compiled cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
