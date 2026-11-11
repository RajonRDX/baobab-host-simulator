#!/usr/bin/env python3
"""
tools/install_step13_02.py — Batch 2 Installer
==============================================
Installs:
  1. backend/app/limit_engine.py (Complete Configurable Limit Calculation & Authorization Profile Engine)
  2. Updates PROGRESS.md with Batch 2 completion details.

Key capabilities implemented in `backend/app/limit_engine.py`:
  - Full hierarchy resolution:
    Institution -> Processing System -> BIN Range -> Card Profile -> Authorization Profile
  - Card-level override support with clear precedence (explicit Card.card_profile_id > BIN's Card Profile).
  - Active/effective-date validation on Authorization Profiles.
  - Transaction-code permission check (ALLOWED / DISALLOWED / unconfigured default policy).
  - All 6 comparison operators: >, <, >=, <=, =, !=
  - All 8 calculation methods:
      * COUNT_TRANSACTION
      * SUM_TRANSACTION_AMOUNT
      * MAX_SINGLE_TRANSACTION
      * MIN_SINGLE_TRANSACTION
      * SUM_CASH_WITHDRAWAL
      * SUM_PURCHASE
      * SUM_TRANSFER
      * CUSTOM_SUPPORTED_AGGREGATION
  - Reset schedules: DAILY, WEEKLY, MONTHLY, YEARLY, PER_TRANSACTION, CUSTOM_HOURS.
  - Transaction-code-wise limit impact rules (INCREASE, DECREASE, NO_IMPACT) with multiplier
    and calculation basis (TRANSACTION_AMOUNT, BILLING_AMOUNT, TRANSACTION_COUNT, FIXED_UNIT).
  - Strict separation of projected evaluation vs. committed usage:
      * Declined transactions NEVER increment usage.
      * Duplicate transactions NEVER increment usage twice (idempotent LimitTransactionConsumption).
      * Reversals (0400/0420) restore original usage once and never double-reverse.
      * Row-level locking (`with_for_update()`) prevents concurrent race-condition overruns.

Run from E:\\HOST_VSCODE\\host-simulator:
    python tools/install_step13_02.py
"""

from datetime import datetime
from pathlib import Path
import shutil
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKUP_ROOT = PROJECT_ROOT / "_backups" / f"step13_02_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


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


def patch_file_append_once(rel_path: str, marker: str, block: str) -> None:
    target = PROJECT_ROOT / rel_path
    if not target.exists():
        raise FileNotFoundError(f"Required file not found: {rel_path}")
    text = target.read_text(encoding="utf-8")
    if marker in text:
        print(f"[SKIP]  {rel_path} already contains {marker}")
        return
    backup_file(rel_path)
    updated = text.rstrip() + "\n\n" + block.strip() + "\n"
    target.write_text(updated, encoding="utf-8")
    print(f"[PATCH] {rel_path} appended with {marker}")


# ==============================================================================
# 1. backend/app/limit_engine.py
# ==============================================================================
LIMIT_ENGINE_CONTENT = '''"""
backend/app/limit_engine.py
===========================
Reusable Configurable Limit & Authorization Profile Engine for the Rajon Host Simulator.
All monetary calculations strictly use Python `Decimal` (2 decimal places, ROUND_HALF_UP).
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from app.models import (
    Account,
    AccountLimit,
    AuthorizationProfile,
    AuthProfileLimitAssignment,
    AuthProfileTxCodePermission,
    BinRange,
    Card,
    CardLimit,
    CardProfile,
    LimitDefinition,
    LimitEvaluationAudit,
    LimitTransactionConsumption,
    LimitUsageRecord,
    Transaction,
    TransactionCode,
    TxCodeLimitImpact,
)

TWO_PLACES = Decimal("0.01")
ZERO = Decimal("0.00")


def to_dec(val: Any) -> Decimal:
    if val is None:
        return ZERO
    if isinstance(val, Decimal):
        return val.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    return Decimal(str(val)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def ensure_utc(dt: Optional[datetime] = None) -> datetime:
    if dt is None:
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def compute_reset_window(
    reset_interval: str,
    tx_time: Optional[datetime] = None,
    reset_interval_hours: Optional[int] = None,
    tx_id: Optional[str] = None,
) -> Tuple[str, datetime, datetime]:
    """
    Computes a deterministic (window_key, window_start, window_end) in UTC for a limit reset interval.
    """
    now = ensure_utc(tx_time)
    interval = (reset_interval or "DAILY").upper().strip()

    if interval == "DAILY":
        start = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        key = f"DAILY:{now.strftime('%Y-%m-%d')}"
        return key, start, end

    if interval == "WEEKLY":
        # ISO week starting Monday 00:00 UTC
        monday = now - timedelta(days=now.weekday())
        start = datetime(monday.year, monday.month, monday.day, 0, 0, 0, tzinfo=timezone.utc)
        end = start + timedelta(days=7)
        iso_year, iso_week, _ = now.isocalendar()
        key = f"WEEKLY:{iso_year}-W{iso_week:02d}"
        return key, start, end

    if interval == "MONTHLY":
        start = datetime(now.year, now.month, 1, 0, 0, 0, tzinfo=timezone.utc)
        if now.month == 12:
            end = datetime(now.year + 1, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        else:
            end = datetime(now.year, now.month + 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        key = f"MONTHLY:{now.strftime('%Y-%m')}"
        return key, start, end

    if interval == "YEARLY":
        start = datetime(now.year, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(now.year + 1, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        key = f"YEARLY:{now.strftime('%Y')}"
        return key, start, end

    if interval == "CUSTOM_HOURS":
        hrs = max(1, int(reset_interval_hours or 24))
        epoch_hours = int(now.timestamp() // 3600)
        bucket = epoch_hours // hrs
        start = datetime.fromtimestamp(bucket * hrs * 3600, tz=timezone.utc)
        end = start + timedelta(hours=hrs)
        key = f"HOURS_{hrs}:{bucket}"
        return key, start, end

    # PER_TRANSACTION: isolated to the single authorization
    unique_suffix = tx_id or now.strftime("%Y%m%d%H%M%S%f")
    return f"PER_TX:{unique_suffix}", now, now + timedelta(seconds=1)


def compare_decimal_values(projected: Decimal, operator_str: str, maximum: Decimal) -> bool:
    """
    Evaluates `<projected> <operator> <maximum>` using exact Decimal arithmetic.
    Supports: >, <, >=, <=, =, !=
    """
    op = (operator_str or ">").strip()
    if op == ">":
        return projected > maximum
    if op == ">=":
        return projected >= maximum
    if op == "<":
        return projected < maximum
    if op == "<=":
        return projected <= maximum
    if op in ("=", "=="):
        return projected == maximum
    if op in ("!=", "<>"):
        return projected != maximum
    raise ValueError(f"Unsupported comparison operator: '{operator_str}'")


@dataclass
class PendingConsumptionItem:
    limit_definition_id: str
    limit_code: str
    limit_name: str
    scope: str  # CARD | ACCOUNT
    target_entity_id: str
    window_key: str
    window_start: datetime
    window_end: datetime
    transaction_code: str
    impact_type: str  # INCREASE | DECREASE | NO_IMPACT
    amount_delta: Decimal
    count_delta: int
    single_tx_amount: Decimal


@dataclass
class LimitEngineEvaluationReport:
    allowed: bool = True
    response_code: str = "00"
    decline_reason: Optional[str] = None
    failed_stage: Optional[str] = None  # TX_PERMISSION | CARD_LIMIT | ACCOUNT_LIMIT
    matched_bin: Optional[BinRange] = None
    card_profile: Optional[CardProfile] = None
    authorization_profile: Optional[AuthorizationProfile] = None
    tx_permission_status: str = "ALLOWED"
    tx_permission_message: str = "Permitted"
    evaluated_limits: List[Dict[str, Any]] = field(default_factory=list)
    pending_consumptions: List[PendingConsumptionItem] = field(default_factory=list)


class LimitCalculationEngine:
    """
    Central service for:
      1. Resolving BIN -> Card Profile -> Authorization Profile hierarchy
      2. Checking Transaction Code permissions inside the Authorization Profile
      3. Evaluating Card-level and Account-level limits with configurable operators,
         calculation methods, reset schedules, and transaction-code impact mappings
      4. Committing usage atomically ONLY when authorization succeeds
      5. Restoring usage on Reversal (0400/0420) with strict idempotency
    """

    CASH_WITHDRAWAL_CODES = {"10", "010", "115", "850"}
    PURCHASE_CODES = {"40", "110", "838", "00"}
    TRANSFER_CODES = {"40_TRF", "040", "882", "45"}
    BALANCE_INQUIRY_CODES = {"30", "030", "117", "810"}

    def __init__(self, db: Session):
        self.db = db

    # --------------------------------------------------------------------------
    # 1. HIERARCHY RESOLUTION: BIN -> CardProfile -> AuthorizationProfile
    # --------------------------------------------------------------------------
    def resolve_bin_for_pan(self, pan: str) -> Optional[BinRange]:
        clean = (pan or "").strip()
        if not clean:
            return None
        active_bins = (
            self.db.query(BinRange)
            .filter(BinRange.status == "ACTIVE")
            .all()
        )
        matched: Optional[BinRange] = None
        best_len = -1
        for b in active_bins:
            if clean.startswith(b.bin_prefix) and len(b.bin_prefix) > best_len:
                matched = b
                best_len = len(b.bin_prefix)
        return matched

    def resolve_card_profile(self, card: Optional[Card], pan: Optional[str] = None) -> Tuple[Optional[BinRange], Optional[CardProfile]]:
        """
        Precedence rule:
          1. Explicit active Card.card_profile_id override on the Card record (if active).
          2. BIN Range's associated card_profile_id based on longest BIN prefix match.
        """
        pan_str = pan or (card.test_pan_reference if card else "")
        matched_bin = self.resolve_bin_for_pan(pan_str)

        if card and card.card_profile_id:
            explicit_prof = (
                self.db.query(CardProfile)
                .filter(CardProfile.id == card.card_profile_id)
                .first()
            )
            if explicit_prof and explicit_prof.status == "ACTIVE":
                return matched_bin, explicit_prof

        if matched_bin and getattr(matched_bin, "card_profile_id", None):
            bin_prof = (
                self.db.query(CardProfile)
                .filter(CardProfile.id == matched_bin.card_profile_id)
                .first()
            )
            if bin_prof and bin_prof.status == "ACTIVE":
                return matched_bin, bin_prof

        return matched_bin, None

    def resolve_authorization_profile(
        self,
        card_profile: Optional[CardProfile],
        tx_time: Optional[datetime] = None,
    ) -> Optional[AuthorizationProfile]:
        """
        Finds the active AuthorizationProfile linked to the resolved CardProfile
        whose effective_from <= tx_time <= effective_to (if specified).
        """
        if not card_profile:
            return None
        now = ensure_utc(tx_time)
        candidates = (
            self.db.query(AuthorizationProfile)
            .filter(
                AuthorizationProfile.card_profile_id == card_profile.id,
                AuthorizationProfile.status == "ACTIVE",
            )
            .order_by(AuthorizationProfile.created_at.desc())
            .all()
        )
        for ap in candidates:
            eff_from = ensure_utc(ap.effective_from) if ap.effective_from else None
            eff_to = ensure_utc(ap.effective_to) if ap.effective_to else None
            if eff_from and now < eff_from:
                continue
            if eff_to and now > eff_to:
                continue
            return ap
        return None

    # --------------------------------------------------------------------------
    # 2. TRANSACTION CLASSIFICATION & CALCULATION ENGINE
    # --------------------------------------------------------------------------
    def _classify_transaction(
        self,
        tx_code: str,
        tx_code_cfg: Optional[TransactionCode],
        processing_code: str = "0100000",
    ) -> str:
        """
        Inspects actual TransactionCode record and processing_code to classify
        a transaction into CASH_WITHDRAWAL, PURCHASE, TRANSFER, BALANCE_INQUIRY, or OTHER.
        """
        code_norm = (str(tx_code or "")).strip()
        code_padded = code_norm.zfill(3)
        name_up = ((tx_code_cfg.transaction_name if tx_code_cfg else "") or "").upper()
        proc_prefix = (processing_code or "0100000")[:3]

        if (tx_code_cfg and tx_code_cfg.balance_inquiry_flag) or code_norm in self.BALANCE_INQUIRY_CODES or "BALANCE" in name_up:
            return "BALANCE_INQUIRY"
        if "TRANSFER" in name_up or "IBFT" in name_up or code_norm in self.TRANSFER_CODES or code_padded in ("040", "882"):
            return "TRANSFER"
        if "WITHDRAW" in name_up or "CASH" in name_up or code_norm in self.CASH_WITHDRAWAL_CODES or proc_prefix in ("010", "115"):
            return "CASH_WITHDRAWAL"
        if "PURCHASE" in name_up or "POS" in name_up or code_norm in self.PURCHASE_CODES or proc_prefix in ("110", "000"):
            return "PURCHASE"
        return "FINANCIAL_GENERIC"

    def _does_method_apply_to_transaction(
        self,
        calculation_method: str,
        tx_class: str,
        tx_code: str,
        tx_fields: Optional[Dict[str, str]],
        custom_filter: Optional[Dict[str, Any]],
    ) -> bool:
        method = (calculation_method or "SUM_TRANSACTION_AMOUNT").upper().strip()
        if method in ("SUM_TRANSACTION_AMOUNT", "COUNT_TRANSACTION", "MAX_SINGLE_TRANSACTION", "MIN_SINGLE_TRANSACTION"):
            return True
        if method == "SUM_CASH_WITHDRAWAL":
            return tx_class == "CASH_WITHDRAWAL"
        if method == "SUM_PURCHASE":
            return tx_class == "PURCHASE"
        if method == "SUM_TRANSFER":
            return tx_class == "TRANSFER"
        if method == "CUSTOM_SUPPORTED_AGGREGATION":
            if not custom_filter:
                return True
            allowed_codes = [str(c).strip() for c in custom_filter.get("transaction_codes", [])]
            if allowed_codes and str(tx_code).strip() not in allowed_codes:
                return False
            allowed_mccs = [str(m).strip() for m in custom_filter.get("mccs", [])]
            if allowed_mccs and tx_fields:
                mcc = str(tx_fields.get("18", "")).strip()
                if mcc not in allowed_mccs:
                    return False
            allowed_channels = [str(ch).upper().strip() for ch in custom_filter.get("classes", [])]
            if allowed_channels and tx_class.upper() not in allowed_channels:
                return False
            return True
        return True

    def _resolve_tx_code_impact_rule(
        self,
        auth_profile: Optional[AuthorizationProfile],
        tx_code: str,
        limit_def: LimitDefinition,
        tx_code_cfg: Optional[TransactionCode],
    ) -> Tuple[str, str, Decimal]:
        """
        Returns (impact_type, calculation_basis, multiplier) for (auth_profile, tx_code, limit_def).
        Checks profile-specific rule first, then global rule (authorization_profile_id IS NULL),
        then safe default derived from TransactionCode flags.
        """
        code_clean = str(tx_code).strip()
        code_unpadded = code_clean.lstrip("0") or "0"
        code_candidates = list({code_clean, code_unpadded, code_clean.zfill(3)})

        if auth_profile:
            prof_rule = (
                self.db.query(TxCodeLimitImpact)
                .filter(
                    TxCodeLimitImpact.authorization_profile_id == auth_profile.id,
                    TxCodeLimitImpact.limit_definition_id == limit_def.id,
                    TxCodeLimitImpact.transaction_code.in_(code_candidates),
                    TxCodeLimitImpact.status == "ACTIVE",
                )
                .first()
            )
            if prof_rule:
                return (
                    prof_rule.impact_type.upper(),
                    prof_rule.calculation_basis.upper(),
                    Decimal(str(prof_rule.multiplier or "1.0000")),
                )

        global_rule = (
            self.db.query(TxCodeLimitImpact)
            .filter(
                TxCodeLimitImpact.authorization_profile_id == None,  # noqa: E711
                TxCodeLimitImpact.limit_definition_id == limit_def.id,
                TxCodeLimitImpact.transaction_code.in_(code_candidates),
                TxCodeLimitImpact.status == "ACTIVE",
            )
            .first()
        )
        if global_rule:
            return (
                global_rule.impact_type.upper(),
                global_rule.calculation_basis.upper(),
                Decimal(str(global_rule.multiplier or "1.0000")),
            )

        # Safe fallback based on TransactionCode flags
        if tx_code_cfg:
            if tx_code_cfg.balance_inquiry_flag or not tx_code_cfg.financial_flag:
                return ("NO_IMPACT", "TRANSACTION_AMOUNT", Decimal("1.0000"))
            if tx_code_cfg.credit_flag and not tx_code_cfg.debit_flag:
                return ("NO_IMPACT", "TRANSACTION_AMOUNT", Decimal("1.0000"))

        default_basis = (
            "TRANSACTION_COUNT"
            if limit_def.calculation_method == "COUNT_TRANSACTION"
            else "TRANSACTION_AMOUNT"
        )
        return ("INCREASE", default_basis, Decimal("1.0000"))

    # --------------------------------------------------------------------------
    # 3. CURRENT USAGE QUERY (READ-ONLY OR LOCKED FOR AUTHORIZATION)
    # --------------------------------------------------------------------------
    def get_current_limit_value(
        self,
        limit_def: LimitDefinition,
        target_entity_id: Optional[str] = None,
        tx_time: Optional[datetime] = None,
        lock_row: bool = False,
    ) -> Tuple[Decimal, str, Optional[LimitUsageRecord]]:
        """
        Calculates the current consumed value for a limit definition in its active reset window.
        If target_entity_id is provided, returns that specific card/account's current window usage.
        If target_entity_id is None (e.g. summary table view), returns the aggregate active window usage.
        """
        if limit_def.reset_interval.upper() == "PER_TRANSACTION":
            win_key, _, _ = compute_reset_window("PER_TRANSACTION", tx_time)
            return ZERO, win_key, None

        win_key, _, _ = compute_reset_window(
            limit_def.reset_interval,
            tx_time=tx_time,
            reset_interval_hours=limit_def.reset_interval_hours,
        )

        q = self.db.query(LimitUsageRecord).filter(
            LimitUsageRecord.scope == limit_def.scope.upper(),
            LimitUsageRecord.limit_definition_id == limit_def.id,
            LimitUsageRecord.window_key == win_key,
        )
        if target_entity_id:
            q = q.filter(LimitUsageRecord.target_entity_id == target_entity_id)
            if lock_row:
                q = q.with_for_update()
            rec = q.first()
            if not rec:
                return ZERO, win_key, None
            if limit_def.calculation_method.upper() == "COUNT_TRANSACTION":
                return to_dec(rec.consumed_count), win_key, rec
            if limit_def.calculation_method.upper() == "MAX_SINGLE_TRANSACTION":
                return to_dec(rec.max_single_amount), win_key, rec
            if limit_def.calculation_method.upper() == "MIN_SINGLE_TRANSACTION":
                return to_dec(rec.min_single_amount or ZERO), win_key, rec
            return to_dec(rec.consumed_amount), win_key, rec

        # Aggregate across entities for overview display
        records = q.all()
        if not records:
            return ZERO, win_key, None
        if limit_def.calculation_method.upper() == "COUNT_TRANSACTION":
            return to_dec(sum(r.consumed_count for r in records)), win_key, None
        return to_dec(sum((r.consumed_amount or ZERO) for r in records)), win_key, None

    # --------------------------------------------------------------------------
    # 4. FULL TRANSACTION AUTHORIZATION EVALUATION
    # --------------------------------------------------------------------------
    def evaluate_transaction(
        self,
        card: Card,
        account: Account,
        tx_code: str,
        tx_amount: Decimal,
        tx_code_cfg: Optional[TransactionCode] = None,
        billing_amount: Optional[Decimal] = None,
        processing_code: str = "0100000",
        tx_fields: Optional[Dict[str, str]] = None,
        tx_time: Optional[datetime] = None,
        transaction_id: Optional[str] = None,
        transaction_reference: Optional[str] = None,
    ) -> LimitEngineEvaluationReport:
        """
        Executes the required 11-step authorization profile & limit evaluation pipeline:
          1. Identify card & linked account
          2. Resolve BIN & Card Profile
          3. Resolve Authorization Profile (verifying status & effective dates)
          4. Check transaction-code permission (Tab A)
          5. Load applicable Card-level & Account-level limits (Tab B & Tab C)
          6. Resolve Transaction-Code Limit Impact rule (Tab D)
          7. Calculate projected value for each applicable limit using Decimal arithmetic
          8. Apply configured comparison operator (>, <, >=, <=, =, !=)
          9. Determine authorization impact (DECLINE / APPROVE_WITH_ALERT / FLAG_REVIEW)
         10. Record LimitEvaluationAudit entries
         11. Return structured evaluation report + pending consumptions (committed ONLY on approval)
        """
        now = ensure_utc(tx_time)
        amt = to_dec(tx_amount)
        bill_amt = to_dec(billing_amount if billing_amount is not None else tx_amount)
        report = LimitEngineEvaluationReport()

        matched_bin, card_prof = self.resolve_card_profile(card, card.test_pan_reference)
        report.matched_bin = matched_bin
        report.card_profile = card_prof

        # Check if card profile has any AuthorizationProfile configured (even inactive/expired)
        if card_prof:
            all_aps_for_cp = (
                self.db.query(AuthorizationProfile)
                .filter(AuthorizationProfile.card_profile_id == card_prof.id)
                .all()
            )
            auth_prof = self.resolve_authorization_profile(card_prof, now)
            if all_aps_for_cp and not auth_prof:
                # An Authorization Profile exists for this Card Profile, but is INACTIVE or outside effective dates
                report.allowed = False
                report.failed_stage = "AUTH_PROFILE_STATUS"
                report.response_code = "05"
                report.decline_reason = (
                    f"Authorization Profile for Card Profile '{card_prof.profile_code}' is inactive or outside its effective date window"
                )
                return report
        else:
            auth_prof = None

        report.authorization_profile = auth_prof

        # Step 7: Check Transaction-Code Permission inside Authorization Profile (Tab A)
        code_clean = str(tx_code).strip()
        code_candidates = list({code_clean, code_clean.lstrip("0") or "0", code_clean.zfill(3)})

        if auth_prof:
            perms = (
                self.db.query(AuthProfileTxCodePermission)
                .filter(
                    AuthProfileTxCodePermission.authorization_profile_id == auth_prof.id,
                    AuthProfileTxCodePermission.status == "ACTIVE",
                )
                .all()
            )
            if perms:
                matched_perm = next(
                    (p for p in perms if p.transaction_code.strip() in code_candidates),
                    None,
                )
                if matched_perm:
                    if matched_perm.permission.upper() == "DISALLOWED":
                        rc = (matched_perm.decline_response_code or "57").strip()
                        reason = (
                            f"Transaction code '{code_clean}' ({matched_perm.transaction_name}) is explicitly DISALLOWED "
                            f"by Authorization Profile '{auth_prof.auth_profile_code}'"
                        )
                        report.allowed = False
                        report.failed_stage = "TX_PERMISSION"
                        report.response_code = rc
                        report.decline_reason = reason
                        report.tx_permission_status = "DISALLOWED"
                        report.tx_permission_message = reason
                        return report
                    report.tx_permission_status = "ALLOWED"
                    report.tx_permission_message = (
                        f"Transaction code '{code_clean}' permitted by profile '{auth_prof.auth_profile_code}'"
                    )
                else:
                    # Unconfigured transaction code behavior
                    policy = (auth_prof.unconfigured_tx_code_policy or "REJECT").upper().strip()
                    if policy == "REJECT":
                        rc = (auth_prof.unconfigured_decline_rc or "57").strip()
                        reason = (
                            f"Transaction code '{code_clean}' is not configured in Authorization Profile "
                            f"'{auth_prof.auth_profile_code}' (Unconfigured Policy: REJECT)"
                        )
                        report.allowed = False
                        report.failed_stage = "TX_PERMISSION"
                        report.response_code = rc
                        report.decline_reason = reason
                        report.tx_permission_status = "DISALLOWED"
                        report.tx_permission_message = reason
                        return report
                    report.tx_permission_status = "ALLOWED"
                    report.tx_permission_message = (
                        f"Transaction code '{code_clean}' allowed by default unconfigured policy"
                    )

        # Step 8 & 9: Load applicable Card Limits and Account Limits
        tx_class = self._classify_transaction(code_clean, tx_code_cfg, processing_code)

        # Collect assignments from AuthorizationProfile (avoiding duplicates via seen set)
        assignments_to_eval: List[Tuple[LimitDefinition, Optional[AuthProfileLimitAssignment]]] = []
        seen_limit_def_ids: set[str] = set()

        if auth_prof:
            active_assigns = (
                self.db.query(AuthProfileLimitAssignment)
                .filter(
                    AuthProfileLimitAssignment.authorization_profile_id == auth_prof.id,
                    AuthProfileLimitAssignment.status == "ACTIVE",
                )
                .order_by(AuthProfileLimitAssignment.evaluation_priority.asc())
                .all()
            )
            for assign in active_assigns:
                ldef = assign.limit_definition
                if not ldef or ldef.status != "ACTIVE":
                    continue
                if ldef.id in seen_limit_def_ids:
                    continue
                seen_limit_def_ids.add(ldef.id)
                assignments_to_eval.append((ldef, assign))

        # Evaluate CARD limits first, then ACCOUNT limits
        assignments_to_eval.sort(key=lambda item: (0 if item[0].scope == "CARD" else 1))

        for ldef, assign in assignments_to_eval:
            scope = ldef.scope.upper()
            target_id = card.id if scope == "CARD" else account.id

            eff_max = to_dec(
                assign.maximum_limit_override
                if (assign and assign.maximum_limit_override is not None)
                else ldef.maximum_limit
            )
            eff_method = (
                (assign.calculation_method_override if (assign and assign.calculation_method_override) else ldef.calculation_method)
                or "SUM_TRANSACTION_AMOUNT"
            ).upper().strip()
            eff_op = (
                (assign.comparison_operator_override if (assign and assign.comparison_operator_override) else ldef.comparison_operator)
                or ">"
            ).strip()
            eff_action = (
                (assign.impact_action_override if (assign and assign.impact_action_override) else ldef.impact_action)
                or "DECLINE"
            ).upper().strip()
            eff_rc = (
                (assign.decline_response_code_override if (assign and assign.decline_response_code_override) else ldef.decline_response_code)
                or "61"
            ).strip()

            # Check whether this calculation method applies to this transaction classification
            if not self._does_method_apply_to_transaction(
                eff_method,
                tx_class,
                code_clean,
                tx_fields,
                ldef.custom_aggregation_filter,
            ):
                continue

            # Resolve transaction-code limit impact (INCREASE / DECREASE / NO_IMPACT)
            impact_type, calc_basis, multiplier = self._resolve_tx_code_impact_rule(
                auth_prof, code_clean, ldef, tx_code_cfg
            )

            win_key, win_start, win_end = compute_reset_window(
                ldef.reset_interval,
                tx_time=now,
                reset_interval_hours=ldef.reset_interval_hours,
                tx_id=transaction_id,
            )

            prev_usage, _, _ = self.get_current_limit_value(
                ldef,
                target_entity_id=target_id,
                tx_time=now,
                lock_row=True,
            )

            # Determine raw basis value
            if eff_method == "COUNT_TRANSACTION" or calc_basis == "TRANSACTION_COUNT":
                raw_basis = Decimal("1.00")
            elif calc_basis == "BILLING_AMOUNT":
                raw_basis = bill_amt
            elif calc_basis == "FIXED_UNIT":
                raw_basis = Decimal("1.00")
            else:
                raw_basis = amt

            scaled_val = to_dec(raw_basis * multiplier)

            if impact_type == "NO_IMPACT":
                tx_impact = ZERO
                amount_delta = ZERO
                count_delta = 0
                projected = prev_usage
            elif impact_type == "DECREASE":
                tx_impact = -scaled_val
                amount_delta = -scaled_val if eff_method != "COUNT_TRANSACTION" else ZERO
                count_delta = -1 if eff_method == "COUNT_TRANSACTION" else 0
                projected = max(ZERO, prev_usage - scaled_val)
            else:
                # INCREASE
                tx_impact = scaled_val
                amount_delta = scaled_val if eff_method != "COUNT_TRANSACTION" else ZERO
                count_delta = 1 if eff_method == "COUNT_TRANSACTION" else 0
                if eff_method in ("MAX_SINGLE_TRANSACTION", "MIN_SINGLE_TRANSACTION"):
                    projected = scaled_val
                else:
                    projected = prev_usage + scaled_val

            # Only evaluate threshold condition when the transaction actually impacts the limit
            # or when evaluating single-transaction bounds on financial requests
            if impact_type == "NO_IMPACT":
                condition_matched = False
            else:
                condition_matched = compare_decimal_values(projected, eff_op, eff_max)

            cond_expr = f"{projected} {eff_op} {eff_max}"
            if condition_matched and eff_action == "DECLINE":
                final_res = "DECLINED"
                res_code = eff_rc
                decline_msg = (
                    f"{ldef.limit_name} ({scope} Limit ID {ldef.limit_code}): "
                    f"Previous Usage={prev_usage}, Transaction Impact={tx_impact}, "
                    f"Projected Usage={projected} {eff_op} Maximum={eff_max} -> DECLINED (RC {eff_rc})"
                )
            elif condition_matched:
                final_res = "ALERT"
                res_code = "00"
                decline_msg = (
                    f"{ldef.limit_name} ({scope} Limit ID {ldef.limit_code}): "
                    f"Condition {cond_expr} matched with action {eff_action}"
                )
            else:
                final_res = "PASSED"
                res_code = "00"
                decline_msg = None

            eval_entry = {
                "limit_id": ldef.id,
                "limit_code": ldef.limit_code,
                "limit_name": ldef.limit_name,
                "scope": scope,
                "target_entity_id": target_id,
                "reset_interval": ldef.reset_interval,
                "window_key": win_key,
                "calculation_method": eff_method,
                "maximum_value": float(eff_max),
                "previous_usage": float(prev_usage),
                "transaction_impact": float(tx_impact),
                "projected_usage": float(projected),
                "comparison_operator": eff_op,
                "condition_expression": cond_expr,
                "comparison_result": condition_matched,
                "authorization_action": eff_action,
                "final_result": final_res,
                "response_code": res_code,
                "decline_reason": decline_msg,
            }
            report.evaluated_limits.append(eval_entry)

            # Persist auditable limit evaluation record
            self.db.add(
                LimitEvaluationAudit(
                    transaction_id=transaction_id,
                    transaction_reference=transaction_reference,
                    authorization_profile_id=auth_prof.id if auth_prof else None,
                    limit_definition_id=ldef.id,
                    limit_code=ldef.limit_code,
                    limit_name=ldef.limit_name,
                    scope=scope,
                    target_entity_id=target_id,
                    transaction_code=code_clean,
                    calculation_method=eff_method,
                    reset_interval=ldef.reset_interval,
                    window_key=win_key,
                    maximum_value=eff_max,
                    previous_usage=prev_usage,
                    transaction_impact=tx_impact,
                    projected_usage=projected,
                    comparison_operator=eff_op,
                    condition_matched=condition_matched,
                    configured_action=eff_action,
                    final_result=final_res,
                    response_code=res_code,
                    decline_reason=decline_msg,
                )
            )

            if final_res == "DECLINED":
                report.allowed = False
                report.failed_stage = "CARD_LIMIT" if scope == "CARD" else "ACCOUNT_LIMIT"
                report.response_code = eff_rc
                report.decline_reason = decline_msg
                # Stop immediately on decline and clear pending consumptions so nothing is incremented
                report.pending_consumptions.clear()
                return report

            if impact_type != "NO_IMPACT" and ldef.reset_interval.upper() != "PER_TRANSACTION":
                report.pending_consumptions.append(
                    PendingConsumptionItem(
                        limit_definition_id=ldef.id,
                        limit_code=ldef.limit_code,
                        limit_name=ldef.limit_name,
                        scope=scope,
                        target_entity_id=target_id,
                        window_key=win_key,
                        window_start=win_start,
                        window_end=win_end,
                        transaction_code=code_clean,
                        impact_type=impact_type,
                        amount_delta=amount_delta,
                        count_delta=count_delta,
                        single_tx_amount=amt,
                    )
                )

        return report

    # --------------------------------------------------------------------------
    # 5. ATOMIC USAGE COMMIT (ONLY CALLED FOR APPROVED TRANSACTIONS)
    # --------------------------------------------------------------------------
    def commit_approved_usage(
        self,
        transaction_id: str,
        pending_items: List[PendingConsumptionItem],
    ) -> List[LimitTransactionConsumption]:
        """
        Atomically applies pending limit consumptions for an APPROVED transaction.
        Idempotent: if LimitTransactionConsumption already exists for (transaction_id, limit_definition_id,
        scope, target_entity_id), it will NEVER increment usage a second time.
        """
        committed: List[LimitTransactionConsumption] = []
        for item in pending_items:
            existing_cons = (
                self.db.query(LimitTransactionConsumption)
                .filter(
                    LimitTransactionConsumption.transaction_id == transaction_id,
                    LimitTransactionConsumption.limit_definition_id == item.limit_definition_id,
                    LimitTransactionConsumption.scope == item.scope,
                    LimitTransactionConsumption.target_entity_id == item.target_entity_id,
                )
                .first()
            )
            if existing_cons:
                committed.append(existing_cons)
                continue

            usage_rec = (
                self.db.query(LimitUsageRecord)
                .filter(
                    LimitUsageRecord.scope == item.scope,
                    LimitUsageRecord.target_entity_id == item.target_entity_id,
                    LimitUsageRecord.limit_definition_id == item.limit_definition_id,
                    LimitUsageRecord.window_key == item.window_key,
                )
                .with_for_update()
                .first()
            )
            if not usage_rec:
                usage_rec = LimitUsageRecord(
                    scope=item.scope,
                    target_entity_id=item.target_entity_id,
                    limit_definition_id=item.limit_definition_id,
                    window_key=item.window_key,
                    window_start=item.window_start,
                    window_end=item.window_end,
                    consumed_amount=ZERO,
                    consumed_count=0,
                    reserved_amount=ZERO,
                    max_single_amount=ZERO,
                    min_single_amount=None,
                )
                self.db.add(usage_rec)
                self.db.flush()

            new_amt = to_dec(usage_rec.consumed_amount) + item.amount_delta
            usage_rec.consumed_amount = max(ZERO, new_amt)
            usage_rec.consumed_count = max(0, (usage_rec.consumed_count or 0) + item.count_delta)
            if item.single_tx_amount > to_dec(usage_rec.max_single_amount):
                usage_rec.max_single_amount = item.single_tx_amount
            if usage_rec.min_single_amount is None or item.single_tx_amount < to_dec(usage_rec.min_single_amount):
                usage_rec.min_single_amount = item.single_tx_amount
            usage_rec.last_transaction_id = transaction_id

            cons = LimitTransactionConsumption(
                transaction_id=transaction_id,
                usage_record_id=usage_rec.id,
                limit_definition_id=item.limit_definition_id,
                scope=item.scope,
                target_entity_id=item.target_entity_id,
                window_key=item.window_key,
                transaction_code=item.transaction_code,
                impact_type=item.impact_type,
                amount_delta=item.amount_delta,
                count_delta=item.count_delta,
                reversed_flag=False,
            )
            self.db.add(cons)
            self.db.flush()
            committed.append(cons)

        return committed

    # --------------------------------------------------------------------------
    # 6. REVERSAL RESTORATION (MTI 0400 / 0420)
    # --------------------------------------------------------------------------
    def reverse_transaction_usage(
        self,
        original_transaction_id: str,
        reversal_transaction_id: str,
        card_id: Optional[str] = None,
        account_id: Optional[str] = None,
        original_amount: Optional[Decimal] = None,
    ) -> List[Dict[str, Any]]:
        """
        Reverses all limit usage consumed by `original_transaction_id`.
        Idempotent: marks each LimitTransactionConsumption as `reversed_flag=True`
        so repeated reversal attempts never subtract usage twice.
        Also restores legacy CardLimit and AccountLimit `daily_used/weekly_used/monthly_used` counters.
        """
        restored_summary: List[Dict[str, Any]] = []
        consumptions = (
            self.db.query(LimitTransactionConsumption)
            .filter(
                LimitTransactionConsumption.transaction_id == original_transaction_id,
                LimitTransactionConsumption.reversed_flag == False,  # noqa: E712
            )
            .with_for_update()
            .all()
        )

        now = ensure_utc()
        for cons in consumptions:
            usage_rec = (
                self.db.query(LimitUsageRecord)
                .filter(LimitUsageRecord.id == cons.usage_record_id)
                .with_for_update()
                .first()
            )
            if usage_rec:
                prev_amt = to_dec(usage_rec.consumed_amount)
                prev_cnt = usage_rec.consumed_count or 0
                usage_rec.consumed_amount = max(ZERO, prev_amt - to_dec(cons.amount_delta))
                usage_rec.consumed_count = max(0, prev_cnt - (cons.count_delta or 0))
            cons.reversed_flag = True
            cons.reversal_transaction_id = reversal_transaction_id
            cons.reversed_at = now

            restored_summary.append({
                "limit_definition_id": cons.limit_definition_id,
                "scope": cons.scope,
                "target_entity_id": cons.target_entity_id,
                "window_key": cons.window_key,
                "restored_amount": float(cons.amount_delta),
                "restored_count": cons.count_delta,
            })

        # Also restore legacy CardLimit / AccountLimit counters for backward compatibility
        amt = to_dec(original_amount)
        if amt > ZERO:
            if card_id:
                clim = self.db.query(CardLimit).filter(CardLimit.card_id == card_id).with_for_update().first()
                if clim:
                    clim.daily_used = max(ZERO, to_dec(clim.daily_used) - amt)
                    clim.weekly_used = max(ZERO, to_dec(clim.weekly_used) - amt)
                    clim.monthly_used = max(ZERO, to_dec(clim.monthly_used) - amt)
            if account_id:
                alim = self.db.query(AccountLimit).filter(AccountLimit.account_id == account_id).with_for_update().first()
                if alim:
                    alim.daily_used = max(ZERO, to_dec(alim.daily_used) - amt)
                    alim.weekly_used = max(ZERO, to_dec(alim.weekly_used) - amt)
                    alim.monthly_used = max(ZERO, to_dec(alim.monthly_used) - amt)

        self.db.flush()
        return restored_summary
'''


def update_progress_md() -> None:
    rel_path = "PROGRESS.md"
    marker = "<!-- PROGRESS:step13_02 -->"
    block = f"""
{marker}
## [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] `step13_02` — Batch 2: Configurable Limit Calculation & Authorization Profile Engine
- **Touched Files**: `backend/app/limit_engine.py`, `PROGRESS.md`
- [x] **Completed**: Created `LimitCalculationEngine` in `backend/app/limit_engine.py` supporting `CARD` and `ACCOUNT` scopes, all 6 comparison operators (`>`, `<`, `>=`, `<=`, `=`, `!=`), all 8 calculation methods (`COUNT_TRANSACTION`, `SUM_TRANSACTION_AMOUNT`, `MAX_SINGLE_TRANSACTION`, `MIN_SINGLE_TRANSACTION`, `SUM_CASH_WITHDRAWAL`, `SUM_PURCHASE`, `SUM_TRANSFER`, `CUSTOM_SUPPORTED_AGGREGATION`), and configurable reset windows (`DAILY`, `WEEKLY`, `MONTHLY`, `YEARLY`, `PER_TRANSACTION`, `CUSTOM_HOURS`).
- [x] **Completed**: Implemented BIN -> Card Profile -> Authorization Profile resolution, transaction-code permission checks, transaction-code limit impact rules (`INCREASE`, `DECREASE`, `NO_IMPACT`), atomic post-approval usage commits, and idempotent reversal restoration.
- [ ] **Next / Remaining**: Batch 3 (`tools/install_step13_03.py`) — REST API Router (`limits_and_profiles_router.py`) and `HostTransactionProcessor` (`host_engine.py`) integration.
"""
    patch_file_append_once(rel_path, marker, block)


def main() -> int:
    print("=" * 76)
    print("BATCH 2 INSTALLER: Limit Calculation Engine (step13_02)")
    print(f"Project Root: {PROJECT_ROOT}")
    print("=" * 76)

    write_file("backend/app/limit_engine.py", LIMIT_ENGINE_CONTENT)
    update_progress_md()

    print("-" * 76)
    print("[OK] Batch 2 installed. Verify by running:")
    print("     python -c \"import sys; sys.path.insert(0, 'backend'); from app.limit_engine import LimitCalculationEngine; print('LimitCalculationEngine OK')\"")
    print("=" * 76)
    return 0


if __name__ == "__main__":
    sys.exit(main())