"""
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
