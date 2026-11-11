#!/usr/bin/env python3
"""
tools/install_step13_01.py — Batch 1 Installer
==============================================
Installs:
  1. backend/app/models_limits_profiles.py (Normalized ORM models for Card/Account Limits,
     Authorization Profiles, Allowed Transactions, Limit Assignments, TxCode Limit Impacts,
     Windowed Usage Tracking, Reversal Consumption Tracking, and Limit Evaluation History)
  2. backend/app/schemas_limits_profiles.py (Pydantic v2 schemas for all new modules)
  3. Safe additive patches to backend/app/models.py, backend/app/schemas.py, and backend/app/database.py
     (including idempotent default seeding and zero-data-loss SQLite/PostgreSQL schema sync).

Run from E:\\HOST_VSCODE\\host-simulator:
    python tools/install_step13_01.py
"""

from datetime import datetime
from pathlib import Path
import shutil
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKUP_ROOT = PROJECT_ROOT / "_backups" / f"step13_01_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


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
# 1. backend/app/models_limits_profiles.py
# ==============================================================================
MODELS_LIMITS_PROFILES_CONTENT = '''"""
models_limits_profiles.py — Normalized SQLAlchemy 2.0 Models for:
  - Module 1 & 2: Configurable Card & Account Limit Definitions (LimitDefinition)
  - Module 3: BIN-to-Card-Profile Inheritance & Extended CardProfile Metadata
  - Module 4: Authorization Profiles (AuthorizationProfile)
    * Tab A: Allowed / Disallowed Transaction Codes (AuthProfileTxCodePermission)
    * Tab B & C: Card & Account Limit Assignments (AuthProfileLimitAssignment)
    * Tab D: Transaction-Code Limit Impact Mappings (TxCodeLimitImpact)
  - Module 6 & 11: Windowed Usage Counters (LimitUsageRecord), Transaction Consumption Ledger
    (LimitTransactionConsumption), and Auditable Limit Evaluation History (LimitEvaluationAudit).
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


def _gen_uuid() -> str:
    return str(uuid.uuid4())


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class LimitDefinition(Base):
    """
    Central reusable limit definition supporting both CARD and ACCOUNT scopes.
    Kept separate from profile assignments and per-card/per-account runtime usage.
    """
    __tablename__ = "limit_definitions"
    __table_args__ = (
        UniqueConstraint("limit_code", name="uq_limit_definitions_code"),
        Index("ix_limit_defs_scope_status", "scope", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_uuid)
    limit_code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)  # e.g. "100", "200"
    limit_name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="CARD", index=True)  # CARD | ACCOUNT
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BDT")
    maximum_limit: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal("10000.00"))
    reset_interval: Mapped[str] = mapped_column(String(30), nullable=False, default="DAILY")  # DAILY, WEEKLY, MONTHLY, YEARLY, PER_TRANSACTION, CUSTOM_HOURS
    reset_interval_hours: Mapped[Optional[int]] = mapped_column(Integer)
    reset_anchor_time: Mapped[str] = mapped_column(String(10), nullable=False, default="00:00")  # HH:MM UTC
    calculation_method: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="SUM_TRANSACTION_AMOUNT",
    )
    # Supported calculation_method values:
    # COUNT_TRANSACTION, SUM_TRANSACTION_AMOUNT, MAX_SINGLE_TRANSACTION, MIN_SINGLE_TRANSACTION,
    # SUM_CASH_WITHDRAWAL, SUM_PURCHASE, SUM_TRANSFER, CUSTOM_SUPPORTED_AGGREGATION
    custom_aggregation_filter: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    comparison_operator: Mapped[str] = mapped_column(String(10), nullable=False, default=">")  # >, <, >=, <=, =, !=
    impact_action: Mapped[str] = mapped_column(String(30), nullable=False, default="DECLINE")  # DECLINE, APPROVE_WITH_ALERT, FLAG_REVIEW
    decline_response_code: Mapped[str] = mapped_column(String(5), nullable=False, default="61")
    institution_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("institutions.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE", index=True)  # ACTIVE, INACTIVE, ARCHIVED
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now)

    profile_assignments: Mapped[List["AuthProfileLimitAssignment"]] = relationship(
        "AuthProfileLimitAssignment", back_populates="limit_definition"
    )
    tx_code_impacts: Mapped[List["TxCodeLimitImpact"]] = relationship(
        "TxCodeLimitImpact", back_populates="limit_definition"
    )


class AuthorizationProfile(Base):
    """
    Module 4: Authorization Profile linked to a CardProfile (and Institution).
    Controls allowed transaction codes, assigned Card Limits, assigned Account Limits,
    and transaction-code-wise limit impact rules.
    """
    __tablename__ = "authorization_profiles"
    __table_args__ = (
        UniqueConstraint("auth_profile_code", name="uq_auth_profile_code"),
        Index("ix_auth_profiles_card_profile_status", "card_profile_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_uuid)
    auth_profile_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    profile_name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    card_profile_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("card_profiles.id"), index=True
    )
    institution_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("institutions.id"), index=True
    )
    # Secure default behavior when a transaction code is not explicitly configured in Tab A:
    # REJECT (default secure) or ALLOW
    unconfigured_tx_code_policy: Mapped[str] = mapped_column(
        String(20), nullable=False, default="REJECT"
    )
    unconfigured_decline_rc: Mapped[str] = mapped_column(
        String(5), nullable=False, default="57"
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE", index=True)  # ACTIVE, INACTIVE, ARCHIVED
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    effective_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now)

    tx_permissions: Mapped[List["AuthProfileTxCodePermission"]] = relationship(
        "AuthProfileTxCodePermission",
        back_populates="authorization_profile",
        cascade="all, delete-orphan",
        order_by="AuthProfileTxCodePermission.transaction_code",
    )
    limit_assignments: Mapped[List["AuthProfileLimitAssignment"]] = relationship(
        "AuthProfileLimitAssignment",
        back_populates="authorization_profile",
        cascade="all, delete-orphan",
        order_by="AuthProfileLimitAssignment.evaluation_priority",
    )
    tx_code_impacts: Mapped[List["TxCodeLimitImpact"]] = relationship(
        "TxCodeLimitImpact",
        back_populates="authorization_profile",
        cascade="all, delete-orphan",
    )


class AuthProfileTxCodePermission(Base):
    """
    Tab A — Allowed Transactions inside an Authorization Profile.
    Controls transaction-code-wise permission (ALLOWED / DISALLOWED).
    """
    __tablename__ = "auth_profile_tx_permissions"
    __table_args__ = (
        UniqueConstraint(
            "authorization_profile_id",
            "transaction_code",
            name="uq_auth_prof_tx_code_perm",
        ),
        Index("ix_auth_prof_tx_perm_lookup", "authorization_profile_id", "transaction_code", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_uuid)
    authorization_profile_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("authorization_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    transaction_code_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("transaction_codes.id")
    )
    transaction_code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    transaction_name: Mapped[str] = mapped_column(String(100), nullable=False)
    permission: Mapped[str] = mapped_column(String(20), nullable=False, default="ALLOWED")  # ALLOWED | DISALLOWED
    decline_response_code: Mapped[str] = mapped_column(String(5), nullable=False, default="57")
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now)

    authorization_profile: Mapped["AuthorizationProfile"] = relationship(
        "AuthorizationProfile", back_populates="tx_permissions"
    )


class AuthProfileLimitAssignment(Base):
    """
    Tab B & Tab C — Assigns Card Limits or Account Limits to an Authorization Profile
    with optional overrides for maximum limit, calculation method, comparison operator,
    and authorization impact.
    """
    __tablename__ = "auth_profile_limit_assignments"
    __table_args__ = (
        UniqueConstraint(
            "authorization_profile_id",
            "limit_definition_id",
            name="uq_auth_prof_limit_assign",
        ),
        Index("ix_auth_prof_limit_scope", "authorization_profile_id", "scope", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_uuid)
    authorization_profile_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("authorization_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    limit_definition_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("limit_definitions.id"),
        nullable=False,
        index=True,
    )
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="CARD")  # CARD | ACCOUNT
    maximum_limit_override: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2))
    calculation_method_override: Mapped[Optional[str]] = mapped_column(String(50))
    comparison_operator_override: Mapped[Optional[str]] = mapped_column(String(10))
    impact_action_override: Mapped[Optional[str]] = mapped_column(String(30))
    decline_response_code_override: Mapped[Optional[str]] = mapped_column(String(5))
    evaluation_priority: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now)

    authorization_profile: Mapped["AuthorizationProfile"] = relationship(
        "AuthorizationProfile", back_populates="limit_assignments"
    )
    limit_definition: Mapped["LimitDefinition"] = relationship(
        "LimitDefinition", back_populates="profile_assignments"
    )


class TxCodeLimitImpact(Base):
    """
    Tab D — Transaction Code Limit Impact inside an Authorization Profile (or global default when
    authorization_profile_id is NULL).
    Controls whether a specific Transaction Code causes INCREASE, DECREASE, or NO_IMPACT on a Limit.
    """
    __tablename__ = "tx_code_limit_impacts"
    __table_args__ = (
        UniqueConstraint(
            "authorization_profile_id",
            "transaction_code",
            "limit_definition_id",
            name="uq_tx_code_limit_impact",
        ),
        Index("ix_tx_code_impact_lookup", "authorization_profile_id", "transaction_code", "limit_definition_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_uuid)
    authorization_profile_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("authorization_profiles.id", ondelete="CASCADE"),
        index=True,
    )
    transaction_code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    limit_definition_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("limit_definitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    impact_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="INCREASE"
    )  # INCREASE | DECREASE | NO_IMPACT
    calculation_basis: Mapped[str] = mapped_column(
        String(40), nullable=False, default="TRANSACTION_AMOUNT"
    )  # TRANSACTION_AMOUNT | BILLING_AMOUNT | TRANSACTION_COUNT | FIXED_UNIT
    multiplier: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False, default=Decimal("1.0000")
    )
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now)

    authorization_profile: Mapped[Optional["AuthorizationProfile"]] = relationship(
        "AuthorizationProfile", back_populates="tx_code_impacts"
    )
    limit_definition: Mapped["LimitDefinition"] = relationship(
        "LimitDefinition", back_populates="tx_code_impacts"
    )


class LimitUsageRecord(Base):
    """
    Windowed accumulator tracking current consumed usage per (scope, target_entity_id,
    limit_definition_id, window_key).
    - For CARD limits, target_entity_id = card.id
    - For ACCOUNT limits, target_entity_id = account.id
    Locked with SELECT ... FOR UPDATE during authorization to prevent concurrency race conditions.
    """
    __tablename__ = "limit_usage_records"
    __table_args__ = (
        UniqueConstraint(
            "scope",
            "target_entity_id",
            "limit_definition_id",
            "window_key",
            name="uq_limit_usage_window",
        ),
        Index("ix_limit_usage_target_lookup", "scope", "target_entity_id", "limit_definition_id", "window_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_uuid)
    scope: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # CARD | ACCOUNT
    target_entity_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)  # card.id or account.id
    limit_definition_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("limit_definitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    window_key: Mapped[str] = mapped_column(String(40), nullable=False, index=True)  # e.g. DAILY:2026-11-08, WEEKLY:2026-W45
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal("0.00"))
    consumed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reserved_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal("0.00"))
    max_single_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal("0.00"))
    min_single_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2))
    last_transaction_id: Mapped[Optional[str]] = mapped_column(String(36))
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class LimitTransactionConsumption(Base):
    """
    Idempotent ledger of exact limit impact committed per approved transaction.
    Guarantees:
      1. Duplicate transactions never increment usage twice.
      2. Reversals (0400/0420) restore the exact original transaction impact.
      3. Repeated reversals never restore usage more than once.
    """
    __tablename__ = "limit_transaction_consumptions"
    __table_args__ = (
        UniqueConstraint(
            "transaction_id",
            "limit_definition_id",
            "scope",
            "target_entity_id",
            name="uq_tx_limit_consumption",
        ),
        Index("ix_limit_tx_cons_orig_tx", "transaction_id", "reversed_flag"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_uuid)
    transaction_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    usage_record_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("limit_usage_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    limit_definition_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("limit_definitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scope: Mapped[str] = mapped_column(String(20), nullable=False)  # CARD | ACCOUNT
    target_entity_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    window_key: Mapped[str] = mapped_column(String(40), nullable=False)
    transaction_code: Mapped[str] = mapped_column(String(20), nullable=False)
    impact_type: Mapped[str] = mapped_column(String(20), nullable=False)  # INCREASE | DECREASE | NO_IMPACT
    amount_delta: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal("0.00"))
    count_delta: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reversed_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reversal_transaction_id: Mapped[Optional[str]] = mapped_column(String(36))
    reversed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class LimitEvaluationAudit(Base):
    """
    Detailed auditable record of every limit evaluated during transaction authorization
    (both APPROVED and DECLINED evaluations).
    """
    __tablename__ = "limit_evaluation_audits"
    __table_args__ = (
        Index("ix_limit_eval_audit_tx", "transaction_id"),
        Index("ix_limit_eval_audit_target", "scope", "target_entity_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_uuid)
    transaction_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    transaction_reference: Mapped[Optional[str]] = mapped_column(String(80), index=True)
    authorization_profile_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    limit_definition_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    limit_code: Mapped[str] = mapped_column(String(40), nullable=False)
    limit_name: Mapped[str] = mapped_column(String(120), nullable=False)
    scope: Mapped[str] = mapped_column(String(20), nullable=False)  # CARD | ACCOUNT
    target_entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    transaction_code: Mapped[str] = mapped_column(String(20), nullable=False)
    calculation_method: Mapped[str] = mapped_column(String(50), nullable=False)
    reset_interval: Mapped[str] = mapped_column(String(30), nullable=False)
    window_key: Mapped[str] = mapped_column(String(40), nullable=False)
    maximum_value: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    previous_usage: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    transaction_impact: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    projected_usage: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    comparison_operator: Mapped[str] = mapped_column(String(10), nullable=False)
    condition_matched: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    configured_action: Mapped[str] = mapped_column(String(30), nullable=False, default="DECLINE")
    final_result: Mapped[str] = mapped_column(String(20), nullable=False, default="PASSED")  # PASSED | DECLINED | ALERT
    response_code: Mapped[str] = mapped_column(String(5), nullable=False, default="00")
    decline_reason: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
'''


# ==============================================================================
# 2. backend/app/schemas_limits_profiles.py
# ==============================================================================
SCHEMAS_LIMITS_PROFILES_CONTENT = '''"""
schemas_limits_profiles.py — Pydantic v2 Validation Schemas for:
  - Card & Account Limit Definitions (Module 1 & 2)
  - Card Profile Extensions & BIN-to-Card-Profile Assignments (Module 3)
  - Authorization Profiles, Allowed Transactions, Limit Assignments, and
    Transaction-Code Limit Impact Rules (Module 4)
  - Structured Limit Evaluation Results (Module 6 & 11)
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

VALID_SCOPES = {"CARD", "ACCOUNT"}
VALID_OPERATORS = {">", "<", ">=", "<=", "=", "!="}
VALID_CALC_METHODS = {
    "COUNT_TRANSACTION",
    "SUM_TRANSACTION_AMOUNT",
    "MAX_SINGLE_TRANSACTION",
    "MIN_SINGLE_TRANSACTION",
    "SUM_CASH_WITHDRAWAL",
    "SUM_PURCHASE",
    "SUM_TRANSFER",
    "CUSTOM_SUPPORTED_AGGREGATION",
}
VALID_RESET_INTERVALS = {
    "DAILY",
    "WEEKLY",
    "MONTHLY",
    "YEARLY",
    "PER_TRANSACTION",
    "CUSTOM_HOURS",
}
VALID_IMPACT_ACTIONS = {"DECLINE", "APPROVE_WITH_ALERT", "FLAG_REVIEW"}
VALID_IMPACT_TYPES = {"INCREASE", "DECREASE", "NO_IMPACT"}
VALID_CALC_BASIS = {"TRANSACTION_AMOUNT", "BILLING_AMOUNT", "TRANSACTION_COUNT", "FIXED_UNIT"}


# ------------------------------------------------------------------------------
# MODULE 1 & 2: CARD & ACCOUNT LIMIT DEFINITIONS
# ------------------------------------------------------------------------------

class LimitDefinitionBase(BaseModel):
    limit_code: str = Field(..., min_length=1, max_length=40, description="Unique configurable Limit ID, e.g. 100 or 200")
    limit_name: str = Field(..., min_length=2, max_length=120)
    description: Optional[str] = None
    scope: str = Field("CARD", description="CARD or ACCOUNT")
    currency: str = Field("BDT", min_length=3, max_length=3)
    maximum_limit: Decimal = Field(..., ge=Decimal("0.00"))
    reset_interval: str = Field("DAILY")
    reset_interval_hours: Optional[int] = Field(None, ge=1, le=8760)
    reset_anchor_time: str = Field("00:00")
    calculation_method: str = Field("SUM_TRANSACTION_AMOUNT")
    custom_aggregation_filter: Optional[Dict[str, Any]] = None
    comparison_operator: str = Field(">")
    impact_action: str = Field("DECLINE")
    decline_response_code: str = Field("61", min_length=2, max_length=5)
    institution_id: Optional[str] = None
    status: str = Field("ACTIVE")

    @field_validator("scope")
    @classmethod
    def validate_scope(cls, v: str) -> str:
        val = (v or "").upper().strip()
        if val not in VALID_SCOPES:
            raise ValueError(f"scope must be one of {sorted(VALID_SCOPES)}")
        return val

    @field_validator("comparison_operator")
    @classmethod
    def validate_operator(cls, v: str) -> str:
        val = (v or "").strip()
        if val == "==":
            val = "="
        if val not in VALID_OPERATORS:
            raise ValueError(f"comparison_operator must be one of {sorted(VALID_OPERATORS)}")
        return val

    @field_validator("calculation_method")
    @classmethod
    def validate_calc_method(cls, v: str) -> str:
        val = (v or "").upper().strip()
        if val not in VALID_CALC_METHODS:
            raise ValueError(f"calculation_method must be one of {sorted(VALID_CALC_METHODS)}")
        return val

    @field_validator("reset_interval")
    @classmethod
    def validate_reset(cls, v: str) -> str:
        val = (v or "").upper().strip()
        if val not in VALID_RESET_INTERVALS:
            raise ValueError(f"reset_interval must be one of {sorted(VALID_RESET_INTERVALS)}")
        return val

    @field_validator("impact_action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        val = (v or "").upper().strip()
        if val not in VALID_IMPACT_ACTIONS:
            raise ValueError(f"impact_action must be one of {sorted(VALID_IMPACT_ACTIONS)}")
        return val


class LimitDefinitionCreate(LimitDefinitionBase):
    pass


class LimitDefinitionUpdate(BaseModel):
    limit_name: Optional[str] = None
    description: Optional[str] = None
    currency: Optional[str] = None
    maximum_limit: Optional[Decimal] = Field(None, ge=Decimal("0.00"))
    reset_interval: Optional[str] = None
    reset_interval_hours: Optional[int] = None
    reset_anchor_time: Optional[str] = None
    calculation_method: Optional[str] = None
    custom_aggregation_filter: Optional[Dict[str, Any]] = None
    comparison_operator: Optional[str] = None
    impact_action: Optional[str] = None
    decline_response_code: Optional[str] = None
    institution_id: Optional[str] = None
    status: Optional[str] = None

    @field_validator("comparison_operator")
    @classmethod
    def validate_op_opt(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        val = v.strip()
        if val == "==":
            val = "="
        if val not in VALID_OPERATORS:
            raise ValueError(f"comparison_operator must be one of {sorted(VALID_OPERATORS)}")
        return val

    @field_validator("calculation_method")
    @classmethod
    def validate_cm_opt(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        val = v.upper().strip()
        if val not in VALID_CALC_METHODS:
            raise ValueError(f"calculation_method must be one of {sorted(VALID_CALC_METHODS)}")
        return val

    @field_validator("reset_interval")
    @classmethod
    def validate_ri_opt(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        val = v.upper().strip()
        if val not in VALID_RESET_INTERVALS:
            raise ValueError(f"reset_interval must be one of {sorted(VALID_RESET_INTERVALS)}")
        return val


class LimitDefinitionOut(LimitDefinitionBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    current_value: Decimal = Decimal("0.00")
    assigned_profiles_count: int = 0
    historical_usage_count: int = 0
    institution_code: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ------------------------------------------------------------------------------
# MODULE 3: BIN-TO-CARD-PROFILE ASSIGNMENT
# ------------------------------------------------------------------------------

class BinCardProfileAssignRequest(BaseModel):
    card_profile_id: Optional[str] = Field(
        None,
        description="Card Profile ID to associate with this BIN range (or null to unassign)",
    )


# ------------------------------------------------------------------------------
# MODULE 4: AUTHORIZATION PROFILES & TABS A, B, C, D
# ------------------------------------------------------------------------------

class AuthProfileTxPermissionCreate(BaseModel):
    transaction_code: str = Field(..., min_length=1, max_length=20)
    transaction_name: Optional[str] = None
    permission: str = Field("ALLOWED", description="ALLOWED or DISALLOWED")
    decline_response_code: str = Field("57", min_length=2, max_length=5)
    description: Optional[str] = None
    status: str = Field("ACTIVE")

    @field_validator("permission")
    @classmethod
    def validate_perm(cls, v: str) -> str:
        val = (v or "").upper().strip()
        if val not in {"ALLOWED", "DISALLOWED"}:
            raise ValueError("permission must be ALLOWED or DISALLOWED")
        return val


class AuthProfileTxPermissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    authorization_profile_id: str
    transaction_code_id: Optional[str] = None
    transaction_code: str
    transaction_name: str
    permission: str
    decline_response_code: str
    description: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None


class AuthProfileLimitAssignmentCreate(BaseModel):
    limit_definition_id: str
    scope: Optional[str] = None
    maximum_limit_override: Optional[Decimal] = Field(None, ge=Decimal("0.00"))
    calculation_method_override: Optional[str] = None
    comparison_operator_override: Optional[str] = None
    impact_action_override: Optional[str] = None
    decline_response_code_override: Optional[str] = None
    evaluation_priority: int = Field(10, ge=1, le=9999)
    status: str = Field("ACTIVE")


class AuthProfileLimitAssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    authorization_profile_id: str
    limit_definition_id: str
    limit_code: Optional[str] = None
    limit_name: Optional[str] = None
    scope: str
    effective_maximum_limit: Decimal = Decimal("0.00")
    maximum_limit_override: Optional[Decimal] = None
    effective_calculation_method: Optional[str] = None
    calculation_method_override: Optional[str] = None
    effective_comparison_operator: Optional[str] = None
    comparison_operator_override: Optional[str] = None
    effective_impact_action: Optional[str] = None
    impact_action_override: Optional[str] = None
    decline_response_code_override: Optional[str] = None
    reset_interval: Optional[str] = None
    current_value: Decimal = Decimal("0.00")
    evaluation_priority: int
    status: str
    created_at: Optional[datetime] = None


class TxCodeLimitImpactCreate(BaseModel):
    transaction_code: str = Field(..., min_length=1, max_length=20)
    limit_definition_id: str
    impact_type: str = Field("INCREASE", description="INCREASE, DECREASE, or NO_IMPACT")
    calculation_basis: str = Field("TRANSACTION_AMOUNT")
    multiplier: Decimal = Field(Decimal("1.0000"), ge=Decimal("0.0000"))
    description: Optional[str] = None
    status: str = Field("ACTIVE")

    @field_validator("impact_type")
    @classmethod
    def validate_impact_type(cls, v: str) -> str:
        val = (v or "").upper().strip()
        if val not in VALID_IMPACT_TYPES:
            raise ValueError(f"impact_type must be one of {sorted(VALID_IMPACT_TYPES)}")
        return val

    @field_validator("calculation_basis")
    @classmethod
    def validate_basis(cls, v: str) -> str:
        val = (v or "").upper().strip()
        if val not in VALID_CALC_BASIS:
            raise ValueError(f"calculation_basis must be one of {sorted(VALID_CALC_BASIS)}")
        return val


class TxCodeLimitImpactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    authorization_profile_id: Optional[str] = None
    transaction_code: str
    transaction_name: Optional[str] = None
    limit_definition_id: str
    limit_code: Optional[str] = None
    limit_name: Optional[str] = None
    limit_scope: Optional[str] = None
    impact_type: str
    calculation_basis: str
    multiplier: Decimal
    description: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None


class AuthorizationProfileCreate(BaseModel):
    auth_profile_code: str = Field(..., min_length=2, max_length=50)
    profile_name: str = Field(..., min_length=2, max_length=120)
    description: Optional[str] = None
    card_profile_id: Optional[str] = None
    institution_id: Optional[str] = None
    unconfigured_tx_code_policy: str = Field("REJECT", description="REJECT or ALLOW")
    unconfigured_decline_rc: str = Field("57", min_length=2, max_length=5)
    status: str = Field("ACTIVE")
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None


class AuthorizationProfileUpdate(BaseModel):
    profile_name: Optional[str] = None
    description: Optional[str] = None
    card_profile_id: Optional[str] = None
    institution_id: Optional[str] = None
    unconfigured_tx_code_policy: Optional[str] = None
    unconfigured_decline_rc: Optional[str] = None
    status: Optional[str] = None
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None


class AuthorizationProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    auth_profile_code: str
    profile_name: str
    description: Optional[str] = None
    card_profile_id: Optional[str] = None
    card_profile_code: Optional[str] = None
    card_profile_name: Optional[str] = None
    institution_id: Optional[str] = None
    institution_code: Optional[str] = None
    institution_name: Optional[str] = None
    unconfigured_tx_code_policy: str
    unconfigured_decline_rc: str
    status: str
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    tx_permissions: List[AuthProfileTxPermissionOut] = []
    card_limits: List[AuthProfileLimitAssignmentOut] = []
    account_limits: List[AuthProfileLimitAssignmentOut] = []
    tx_code_impacts: List[TxCodeLimitImpactOut] = []


# ------------------------------------------------------------------------------
# MODULE 6 & 11: STRUCTURED LIMIT EVALUATION RESULT
# ------------------------------------------------------------------------------

class LimitEvaluationItemResult(BaseModel):
    limit_id: str
    limit_code: str
    limit_name: str
    scope: str  # CARD | ACCOUNT
    target_entity_id: str
    reset_interval: str
    window_key: str
    calculation_method: str
    maximum_value: Decimal
    previous_usage: Decimal
    transaction_impact: Decimal
    projected_usage: Decimal
    comparison_operator: str
    condition_expression: str
    comparison_result: bool
    authorization_action: str
    final_result: str  # PASSED | DECLINED | ALERT
    response_code: str
    decline_reason: Optional[str] = None
'''


# ==============================================================================
# 3. Patch backend/app/models.py to add CardProfile/BinRange columns & export new models
# ==============================================================================
def patch_models_py() -> None:
    rel_path = "backend/app/models.py"
    target = PROJECT_ROOT / rel_path
    text = target.read_text(encoding="utf-8")
    backup_file(rel_path)

    # 1. Enhance CardProfile with description, institution_id, processing_system_id, card_type, currency, created_at
    if "processing_system_id: Mapped[Optional[str]]" not in text.split("class Card(")[0]:
        old_cp = (
            '    profile_code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)\n'
            '    profile_name: Mapped[str] = mapped_column(String(100), nullable=False)\n'
            '    card_product: Mapped[str] = mapped_column(String(60), nullable=False, default="VISA_DEBIT_CLASSIC")'
        )
        new_cp = (
            '    profile_code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)\n'
            '    profile_name: Mapped[str] = mapped_column(String(100), nullable=False)\n'
            '    description: Mapped[Optional[str]] = mapped_column(Text)\n'
            '    institution_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("institutions.id"), index=True)\n'
            '    processing_system_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("processing_systems.id"), index=True)\n'
            '    card_type: Mapped[str] = mapped_column(String(30), nullable=False, default="DEBIT")\n'
            '    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BDT")\n'
            '    card_product: Mapped[str] = mapped_column(String(60), nullable=False, default="VISA_DEBIT_CLASSIC")\n'
            '    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)\n'
            '    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)'
        )
        if old_cp in text:
            text = text.replace(old_cp, new_cp, 1)

    # 2. Enhance BinRange with card_profile_id
    if "card_profile_id: Mapped[Optional[str]]" not in text.split("class BinRange")[1]:
        old_bin = (
            '    card_type: Mapped[str] = mapped_column(String(30), nullable=False, default="DEBIT")  # DEBIT, CREDIT, PREPAID\n'
            '    card_product: Mapped[str] = mapped_column(String(60), nullable=False, default="VISA_DEBIT_CLASSIC")'
        )
        new_bin = (
            '    card_profile_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("card_profiles.id"), index=True)\n'
            '    card_type: Mapped[str] = mapped_column(String(30), nullable=False, default="DEBIT")  # DEBIT, CREDIT, PREPAID\n'
            '    card_product: Mapped[str] = mapped_column(String(60), nullable=False, default="VISA_DEBIT_CLASSIC")'
        )
        if old_bin in text:
            text = text.replace(old_bin, new_bin, 1)
        old_bin_rel = '    processing_system: Mapped["ProcessingSystem"] = relationship("ProcessingSystem", back_populates="bin_ranges")'
        new_bin_rel = (
            '    processing_system: Mapped["ProcessingSystem"] = relationship("ProcessingSystem", back_populates="bin_ranges")\n'
            '    card_profile: Mapped[Optional["CardProfile"]] = relationship("CardProfile", foreign_keys=[card_profile_id])'
        )
        if old_bin_rel in text:
            text = text.replace(old_bin_rel, new_bin_rel, 1)

    # 3. Re-export models from models_limits_profiles
    marker = "# [PATCH step13_01:export_limits_profiles_models]"
    if marker not in text:
        text = text.rstrip() + f"""

{marker}
from app.models_limits_profiles import (  # noqa: E402, F401
    LimitDefinition,
    AuthorizationProfile,
    AuthProfileTxCodePermission,
    AuthProfileLimitAssignment,
    TxCodeLimitImpact,
    LimitUsageRecord,
    LimitTransactionConsumption,
    LimitEvaluationAudit,
)
"""
    target.write_text(text, encoding="utf-8")
    print(f"[PATCH] {rel_path} updated with CardProfile/BinRange fields and model exports")


# ==============================================================================
# 4. Patch backend/app/schemas.py to extend CardProfile & BinRange schemas + export
# ==============================================================================
def patch_schemas_py() -> None:
    rel_path = "backend/app/schemas.py"
    target = PROJECT_ROOT / rel_path
    text = target.read_text(encoding="utf-8")
    backup_file(rel_path)

    marker = "# [PATCH step13_01:export_limits_profiles_schemas]"
    if marker not in text:
        append_block = f"""
{marker}
from app.schemas_limits_profiles import (  # noqa: E402, F401
    LimitDefinitionBase,
    LimitDefinitionCreate,
    LimitDefinitionUpdate,
    LimitDefinitionOut,
    BinCardProfileAssignRequest,
    AuthProfileTxPermissionCreate,
    AuthProfileTxPermissionOut,
    AuthProfileLimitAssignmentCreate,
    AuthProfileLimitAssignmentOut,
    TxCodeLimitImpactCreate,
    TxCodeLimitImpactOut,
    AuthorizationProfileCreate,
    AuthorizationProfileUpdate,
    AuthorizationProfileOut,
    LimitEvaluationItemResult,
)
"""
        text = text.rstrip() + "\n" + append_block
        target.write_text(text, encoding="utf-8")
        print(f"[PATCH] {rel_path} updated with schema exports")
    else:
        print(f"[SKIP]  {rel_path} already contains {marker}")


# ==============================================================================
# 5. Create backend/app/seed_limits_profiles.py and wire into database.py / seed_data.py
# ==============================================================================
SEED_LIMITS_PROFILES_CONTENT = '''"""
seed_limits_profiles.py — Idempotent Seeding & Data Healing for:
  - Card Profiles linked to Institutions, Processing Systems, and BIN Ranges
  - Existing Cards linked to their BIN's Card Profile if unassigned
  - Default Configurable Card Limit Definitions (100, 101, 102, 103)
  - Default Configurable Account Limit Definitions (200, 201)
  - Default Authorization Profile ("VISA_CLASSIC_STANDARD") linked to VISA_CLASSIC Card Profile
    with Allowed Transactions, Card/Account Limit Assignments, and Transaction-Code Limit Impacts.
"""

from decimal import Decimal
from sqlalchemy.orm import Session
from app.models import (
    AuthorizationProfile,
    AuthProfileLimitAssignment,
    AuthProfileTxCodePermission,
    BinRange,
    Card,
    CardProfile,
    Institution,
    LimitDefinition,
    ProcessingSystem,
    TransactionCode,
    TxCodeLimitImpact,
)


def seed_limits_and_authorization_profiles(db: Session) -> None:
    itcl_ps = db.query(ProcessingSystem).filter(ProcessingSystem.ps_code == "ITCL").first()
    xbank = db.query(Institution).filter(Institution.institution_code == "XBANK").first()

    # 1. Ensure standard Card Profiles exist and have Institution / ProcessingSystem metadata
    default_card_profiles = [
        {
            "profile_code": "VISA_CLASSIC",
            "profile_name": "VISA Classic Debit Profile",
            "description": "Standard domestic & e-commerce Visa Classic Debit profile under ITCL switch",
            "card_product": "VISA_DEBIT_CLASSIC",
            "card_type": "DEBIT",
            "currency": "BDT",
        },
        {
            "profile_code": "VISA_GOLD",
            "profile_name": "VISA Gold Priority Profile",
            "description": "High-limit Visa Gold Debit/Credit profile",
            "card_product": "VISA_GOLD",
            "card_type": "DEBIT",
            "currency": "BDT",
        },
        {
            "profile_code": "NPSB_PROPRIETARY",
            "profile_name": "NPSB / QCash Domestic Profile",
            "description": "National Payment Switch Bangladesh domestic proprietary card profile",
            "card_product": "QCASH_PROPRIETARY",
            "card_type": "DEBIT",
            "currency": "BDT",
        },
    ]

    profile_map = {}
    for cp_data in default_card_profiles:
        prof = db.query(CardProfile).filter(CardProfile.profile_code == cp_data["profile_code"]).first()
        if not prof:
            prof = CardProfile(
                profile_code=cp_data["profile_code"],
                profile_name=cp_data["profile_name"],
                description=cp_data["description"],
                institution_id=xbank.id if xbank else None,
                processing_system_id=itcl_ps.id if itcl_ps else None,
                card_type=cp_data["card_type"],
                currency=cp_data["currency"],
                card_product=cp_data["card_product"],
                domestic_enabled=True,
                international_enabled=(cp_data["profile_code"] == "VISA_GOLD"),
                ecommerce_enabled=True,
                contactless_enabled=True,
                cash_enabled=True,
                status="ACTIVE",
            )
            db.add(prof)
            db.flush()
        else:
            if not getattr(prof, "description", None):
                prof.description = cp_data["description"]
            if not getattr(prof, "institution_id", None) and xbank:
                prof.institution_id = xbank.id
            if not getattr(prof, "processing_system_id", None) and itcl_ps:
                prof.processing_system_id = itcl_ps.id
            if not getattr(prof, "card_type", None):
                prof.card_type = cp_data["card_type"]
            if not getattr(prof, "currency", None):
                prof.currency = cp_data["currency"]
        profile_map[cp_data["profile_code"]] = prof

    visa_classic_prof = profile_map["VISA_CLASSIC"]

    # 2. Link existing BIN ranges to Card Profiles only if not yet assigned
    for b in db.query(BinRange).all():
        if not getattr(b, "card_profile_id", None):
            if "GOLD" in (b.card_product or "").upper():
                b.card_profile_id = profile_map["VISA_GOLD"].id
            elif "NPSB" in (b.scheme or "").upper() or "QCASH" in (b.card_product or "").upper():
                b.card_profile_id = profile_map["NPSB_PROPRIETARY"].id
            else:
                b.card_profile_id = visa_classic_prof.id
    db.flush()

    # 3. Link existing Cards without card_profile_id to their matching BIN's card_profile_id
    all_bins = db.query(BinRange).filter(BinRange.status == "ACTIVE").all()
    for card in db.query(Card).filter(Card.card_profile_id == None).all():  # noqa: E711
        pan = card.test_pan_reference or ""
        matched_bin = None
        best_len = -1
        for br in all_bins:
            if pan.startswith(br.bin_prefix) and len(br.bin_prefix) > best_len:
                matched_bin = br
                best_len = len(br.bin_prefix)
        if matched_bin and matched_bin.card_profile_id:
            card.card_profile_id = matched_bin.card_profile_id
        else:
            card.card_profile_id = visa_classic_prof.id
    db.flush()

    # 4. Seed Default Configurable Card Limits (100 - 103) and Account Limits (200 - 201)
    default_limits = [
        {
            "limit_code": "100",
            "limit_name": "Daily Card Transaction Limit",
            "description": "Maximum cumulative daily debit amount allowed on a card across all financial channels",
            "scope": "CARD",
            "currency": "BDT",
            "maximum_limit": Decimal("100000.00"),
            "reset_interval": "DAILY",
            "calculation_method": "SUM_TRANSACTION_AMOUNT",
            "comparison_operator": ">",
            "impact_action": "DECLINE",
            "decline_response_code": "61",
        },
        {
            "limit_code": "101",
            "limit_name": "Single Card Transaction Maximum",
            "description": "Maximum amount allowed for any single card transaction",
            "scope": "CARD",
            "currency": "BDT",
            "maximum_limit": Decimal("50000.00"),
            "reset_interval": "PER_TRANSACTION",
            "calculation_method": "MAX_SINGLE_TRANSACTION",
            "comparison_operator": ">",
            "impact_action": "DECLINE",
            "decline_response_code": "61",
        },
        {
            "limit_code": "102",
            "limit_name": "Daily ATM Cash Withdrawal Limit",
            "description": "Maximum daily cumulative ATM cash withdrawal amount per card",
            "scope": "CARD",
            "currency": "BDT",
            "maximum_limit": Decimal("50000.00"),
            "reset_interval": "DAILY",
            "calculation_method": "SUM_CASH_WITHDRAWAL",
            "comparison_operator": ">",
            "impact_action": "DECLINE",
            "decline_response_code": "61",
        },
        {
            "limit_code": "103",
            "limit_name": "Daily Card Transaction Velocity Count",
            "description": "Maximum number of financial transactions permitted per card per day",
            "scope": "CARD",
            "currency": "BDT",
            "maximum_limit": Decimal("25.00"),
            "reset_interval": "DAILY",
            "calculation_method": "COUNT_TRANSACTION",
            "comparison_operator": ">",
            "impact_action": "DECLINE",
            "decline_response_code": "61",
        },
        {
            "limit_code": "200",
            "limit_name": "Daily Account Debit Limit",
            "description": "Maximum cumulative daily debit amount permitted on the linked bank account",
            "scope": "ACCOUNT",
            "currency": "BDT",
            "maximum_limit": Decimal("300000.00"),
            "reset_interval": "DAILY",
            "calculation_method": "SUM_TRANSACTION_AMOUNT",
            "comparison_operator": ">",
            "impact_action": "DECLINE",
            "decline_response_code": "61",
        },
        {
            "limit_code": "201",
            "limit_name": "Monthly Account Aggregate Limit",
            "description": "Maximum cumulative monthly debit amount permitted on the linked bank account",
            "scope": "ACCOUNT",
            "currency": "BDT",
            "maximum_limit": Decimal("3000000.00"),
            "reset_interval": "MONTHLY",
            "calculation_method": "SUM_TRANSACTION_AMOUNT",
            "comparison_operator": ">",
            "impact_action": "DECLINE",
            "decline_response_code": "61",
        },
    ]

    limit_obj_map = {}
    for l_cfg in default_limits:
        lim = db.query(LimitDefinition).filter(LimitDefinition.limit_code == l_cfg["limit_code"]).first()
        if not lim:
            lim = LimitDefinition(
                institution_id=xbank.id if xbank else None,
                status="ACTIVE",
                **l_cfg,
            )
            db.add(lim)
            db.flush()
        limit_obj_map[l_cfg["limit_code"]] = lim

    # 5. Seed Default Authorization Profiles for the Card Profiles
    auth_profiles_seed = [
        ("VISA_CLASSIC_STANDARD", "VISA Classic Standard Authorization Profile", visa_classic_prof),
        ("VISA_GOLD_EXECUTIVE", "VISA Gold Executive Authorization Profile", profile_map["VISA_GOLD"]),
        ("NPSB_DOMESTIC_STANDARD", "NPSB Domestic Standard Authorization Profile", profile_map["NPSB_PROPRIETARY"]),
    ]

    tx_codes_in_db = db.query(TransactionCode).all()

    for auth_code, auth_name, c_prof in auth_profiles_seed:
        ap = db.query(AuthorizationProfile).filter(AuthorizationProfile.auth_profile_code == auth_code).first()
        if not ap:
            ap = AuthorizationProfile(
                auth_profile_code=auth_code,
                profile_name=auth_name,
                description=f"Default authorization profile governing allowed transactions and limits for {c_prof.profile_code}",
                card_profile_id=c_prof.id,
                institution_id=xbank.id if xbank else None,
                unconfigured_tx_code_policy="REJECT",
                unconfigured_decline_rc="57",
                status="ACTIVE",
            )
            db.add(ap)
            db.flush()

            # Tab A: Populate permissions for all existing TransactionCodes
            for tc in tx_codes_in_db:
                perm = "ALLOWED" if tc.active else "DISALLOWED"
                db.add(
                    AuthProfileTxCodePermission(
                        authorization_profile_id=ap.id,
                        transaction_code_id=tc.id,
                        transaction_code=tc.transaction_code,
                        transaction_name=tc.transaction_name,
                        permission=perm,
                        decline_response_code="57",
                        description=f"Default permission for {tc.transaction_name}",
                        status="ACTIVE",
                    )
                )

            # Tab B & C: Assign Card Limits (100, 101, 102, 103) & Account Limits (200, 201)
            for prio, lcode in enumerate(["101", "100", "102", "103", "200", "201"], start=1):
                ldef = limit_obj_map[lcode]
                override_max = None
                if auth_code == "VISA_GOLD_EXECUTIVE" and ldef.scope == "CARD" and lcode in ("100", "101", "102"):
                    override_max = ldef.maximum_limit * Decimal("2")
                db.add(
                    AuthProfileLimitAssignment(
                        authorization_profile_id=ap.id,
                        limit_definition_id=ldef.id,
                        scope=ldef.scope,
                        maximum_limit_override=override_max,
                        evaluation_priority=prio * 10,
                        status="ACTIVE",
                    )
                )

            # Tab D: Seed Transaction-Code Limit Impact mappings based on actual TransactionCodes
            for tc in tx_codes_in_db:
                code_str = tc.transaction_code
                # Determine default impact type from transaction flags
                if tc.balance_inquiry_flag or not tc.financial_flag:
                    impact_type = "NO_IMPACT"
                elif tc.credit_flag and not tc.debit_flag:
                    # Deposit / refund / credit
                    impact_type = "NO_IMPACT"
                else:
                    impact_type = "INCREASE"

                for lcode in ["100", "101", "102", "103", "200", "201"]:
                    ldef = limit_obj_map[lcode]
                    basis = "TRANSACTION_COUNT" if ldef.calculation_method == "COUNT_TRANSACTION" else "TRANSACTION_AMOUNT"
                    db.add(
                        TxCodeLimitImpact(
                            authorization_profile_id=ap.id,
                            transaction_code=code_str,
                            limit_definition_id=ldef.id,
                            impact_type=impact_type,
                            calculation_basis=basis,
                            multiplier=Decimal("1.0000"),
                            description=f"{tc.transaction_name} -> {ldef.limit_name} ({impact_type})",
                            status="ACTIVE",
                        )
                    )

    db.commit()
'''


def patch_seed_data_py() -> None:
    rel_path = "backend/app/seed_data.py"
    marker = "# [PATCH step13_01:seed_limits_and_auth_profiles]"
    block = f"""
{marker}
from app.seed_limits_profiles import seed_limits_and_authorization_profiles  # noqa: E402
"""
    target = PROJECT_ROOT / rel_path
    text = target.read_text(encoding="utf-8")
    if marker not in text:
        backup_file(rel_path)
        text = text.rstrip() + "\n" + block
        # Also invoke inside seed_initial_data(db)
        if "def seed_initial_data(db: Session)" in text:
            text = text.replace(
                "def seed_initial_data(db: Session) -> None:",
                "def seed_initial_data(db: Session) -> None:",
            )
            text = text.rstrip() + """

# Wrap seed_initial_data so it always runs seed_limits_and_authorization_profiles(db)
_orig_seed_initial_data = seed_initial_data


def seed_initial_data(db: Session) -> None:
    _orig_seed_initial_data(db)
    seed_limits_and_authorization_profiles(db)
"""
        target.write_text(text, encoding="utf-8")
        print(f"[PATCH] {rel_path} wired with seed_limits_and_authorization_profiles")
    else:
        print(f"[SKIP]  {rel_path} already contains {marker}")


def update_progress_md() -> None:
    rel_path = "PROGRESS.md"
    marker = "<!-- PROGRESS:step13_01 -->"
    block = f"""
{marker}
## [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] `step13_01` — Batch 1: Normalized Database Models, Schema Sync & Pydantic v2 Schemas for Limits & Authorization Profiles
- **Touched Files**: `backend/app/models_limits_profiles.py`, `backend/app/schemas_limits_profiles.py`, `backend/app/seed_limits_profiles.py`, `backend/app/models.py`, `backend/app/schemas.py`, `backend/app/seed_data.py`
- [x] **Completed**: Added normalized SQLAlchemy 2.0 models (`LimitDefinition`, `AuthorizationProfile`, `AuthProfileTxCodePermission`, `AuthProfileLimitAssignment`, `TxCodeLimitImpact`, `LimitUsageRecord`, `LimitTransactionConsumption`, `LimitEvaluationAudit`).
- [x] **Completed**: Extended `BinRange` with `card_profile_id` and `CardProfile` with `description`, `institution_id`, `processing_system_id`, `card_type`, and `currency`.
- [x] **Completed**: Added Pydantic v2 schemas and idempotent default seeding.
- [ ] **Next / Remaining**: Batch 2 (`tools/install_step13_02.py`) — `backend/app/limit_engine.py`.
"""
    patch_file_append_once(rel_path, marker, block)


def main() -> int:
    print("=" * 76)
    print("BATCH 1 INSTALLER: Database Models, Schemas & Seeding (step13_01)")
    print(f"Project Root: {PROJECT_ROOT}")
    print("=" * 76)

    write_file("backend/app/models_limits_profiles.py", MODELS_LIMITS_PROFILES_CONTENT)
    write_file("backend/app/schemas_limits_profiles.py", SCHEMAS_LIMITS_PROFILES_CONTENT)
    write_file("backend/app/seed_limits_profiles.py", SEED_LIMITS_PROFILES_CONTENT)
    patch_models_py()
    patch_schemas_py()
    patch_seed_data_py()
    update_progress_md()

    print("-" * 76)
    print("[OK] Batch 1 installed. Verify by running:")
    print("     python -c \"import sys; sys.path.insert(0, 'backend'); from app.database import init_db; init_db(); print('Schema OK')\"")
    print("=" * 76)
    return 0


if __name__ == "__main__":
    sys.exit(main())