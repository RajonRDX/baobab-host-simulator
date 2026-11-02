"""
MODULE 2 — models.py
Normalized database models for the BAOBAB-Inspired Private Host Simulator.
Covers all 24 tables: Customers, Accounts, Ledger, Cards, Profiles, Limits,
PIN/EMV Profiles, Configurable Transaction Codes/Fields, HSM Metadata/Audits,
Transactions, Checks, Messages, Reversals, Notifications, and System Logs.
"""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ==============================================================================
# A. CUSTOMER AND ACCOUNT TABLES
# ==============================================================================

class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    customer_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[Optional[str]] = mapped_column(String(100))
    date_of_birth: Mapped[Optional[date]] = mapped_column(Date)
    email: Mapped[Optional[str]] = mapped_column(String(254))
    mobile_number: Mapped[Optional[str]] = mapped_column(String(30))
    address: Mapped[Optional[str]] = mapped_column(Text)
    customer_status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
# [PATCH step02_01:customer_inst_id]
    institution_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("institutions.id"), index=True)
    institution: Mapped[Optional["Institution"]] = relationship("Institution", foreign_keys=[institution_id])
    risk_category: Mapped[str] = mapped_column(String(20), nullable=False, default="NORMAL")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

# [PATCH fix_customer_cascade_500]
    # Safe relationships without blind delete-orphan cascade that causes HTTP 500 on ledger/tx history
    accounts: Mapped[List["Account"]] = relationship("Account", back_populates="customer")
    cards: Mapped[List["Card"]] = relationship("Card", back_populates="customer")


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    account_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(String(36), ForeignKey("customers.id"), nullable=False, index=True)
    account_type: Mapped[str] = mapped_column(String(30), nullable=False, default="CURRENT")  # SAVINGS, CURRENT, CREDIT
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BDT")
    available_balance: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal("0.00"))
    ledger_balance: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal("0.00"))
    overdraft_limit: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal("0.00"))
    account_status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    branch_code: Mapped[Optional[str]] = mapped_column(String(20), default="0001")
# [PATCH step02_01:account_inst_id]
    institution_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("institutions.id"), index=True)
    institution: Mapped[Optional["Institution"]] = relationship("Institution", foreign_keys=[institution_id])
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    customer: Mapped["Customer"] = relationship("Customer", back_populates="accounts")
    ledger_entries: Mapped[List["AccountLedger"]] = relationship("AccountLedger", back_populates="account")
    limits: Mapped[List["AccountLimit"]] = relationship("AccountLimit", back_populates="account", cascade="all, delete-orphan")


class AccountLedger(Base):
    __tablename__ = "account_ledger"
    __table_args__ = (
        UniqueConstraint("transaction_id", "account_id", "entry_type", name="uq_ledger_tx_acct_type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    account_id: Mapped[str] = mapped_column(String(36), ForeignKey("accounts.id"), nullable=False, index=True)
    transaction_id: Mapped[str] = mapped_column(String(36), ForeignKey("transactions.id"), nullable=False, index=True)
    entry_type: Mapped[str] = mapped_column(String(10), nullable=False)  # DEBIT or CREDIT
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    balance_before: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(250))
    posting_status: Mapped[str] = mapped_column(String(20), nullable=False, default="POSTED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    account: Mapped["Account"] = relationship("Account", back_populates="ledger_entries")


class AccountLimit(Base):
    __tablename__ = "account_limits"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    account_id: Mapped[str] = mapped_column(String(36), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BDT")
    per_transaction_limit: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal("100000.00"))
    daily_limit: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal("300000.00"))
    weekly_limit: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal("1000000.00"))
    monthly_limit: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal("3000000.00"))
    daily_used: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal("0.00"))
    weekly_used: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal("0.00"))
    monthly_used: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal("0.00"))
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    effective_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")

    account: Mapped["Account"] = relationship("Account", back_populates="limits")


# ==============================================================================
# B. CARD MANAGEMENT TABLES
# ==============================================================================

class CardProfile(Base):
    __tablename__ = "card_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    profile_code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    profile_name: Mapped[str] = mapped_column(String(100), nullable=False)
    card_product: Mapped[str] = mapped_column(String(60), nullable=False, default="VISA_DEBIT_CLASSIC")
    transaction_permissions: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)
    domestic_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    international_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ecommerce_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    contactless_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    cash_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")


class Card(Base):
    __tablename__ = "cards"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    customer_id: Mapped[str] = mapped_column(String(36), ForeignKey("customers.id"), nullable=False, index=True)
    card_number_token: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    test_pan_reference: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    masked_pan: Mapped[str] = mapped_column(String(25), nullable=False)
    cardholder_name: Mapped[str] = mapped_column(String(120), nullable=False)
    expiry_month: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    expiry_year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    card_type: Mapped[str] = mapped_column(String(30), nullable=False, default="DEBIT")
    card_product: Mapped[str] = mapped_column(String(60), nullable=False, default="VISA_CLASSIC")
    card_status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    issue_date: Mapped[Optional[date]] = mapped_column(Date)
    activation_date: Mapped[Optional[date]] = mapped_column(Date)
    linked_account_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("accounts.id"))
# [PATCH step02_01:card_inst_id]
    institution_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("institutions.id"), index=True)
    institution: Mapped[Optional["Institution"]] = relationship("Institution", foreign_keys=[institution_id])
    card_profile_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("card_profiles.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    customer: Mapped["Customer"] = relationship("Customer", back_populates="cards")
    card_profile: Mapped[Optional["CardProfile"]] = relationship("CardProfile")
    card_accounts: Mapped[List["CardAccount"]] = relationship("CardAccount", back_populates="card", cascade="all, delete-orphan")
    limits: Mapped[List["CardLimit"]] = relationship("CardLimit", back_populates="card", cascade="all, delete-orphan")
    pin_profile: Mapped[Optional["PinProfile"]] = relationship("PinProfile", back_populates="card", uselist=False, cascade="all, delete-orphan")
    emv_profile: Mapped[Optional["EmvProfile"]] = relationship("EmvProfile", back_populates="card", uselist=False, cascade="all, delete-orphan")


class CardAccount(Base):
    __tablename__ = "card_accounts"
    __table_args__ = (UniqueConstraint("card_id", "account_id", name="uq_card_account"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    card_id: Mapped[str] = mapped_column(String(36), ForeignKey("cards.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String(36), ForeignKey("accounts.id"), nullable=False, index=True)
    account_role: Mapped[str] = mapped_column(String(20), nullable=False, default="PRIMARY")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BDT")
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")

    card: Mapped["Card"] = relationship("Card", back_populates="card_accounts")
    account: Mapped["Account"] = relationship("Account")


class CardLimit(Base):
    __tablename__ = "card_limits"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    card_id: Mapped[str] = mapped_column(String(36), ForeignKey("cards.id", ondelete="CASCADE"), nullable=False, index=True)
    profile_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("card_profiles.id"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BDT")
    withdrawal_limit: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal("50000.00"))
    purchase_limit: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal("100000.00"))
    ecommerce_limit: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal("50000.00"))
    mail_order_limit: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal("25000.00"))
    transaction_limit: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal("50000.00"))
    daily_limit: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal("100000.00"))
    weekly_limit: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal("300000.00"))
    monthly_limit: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal("1000000.00"))
    daily_used: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal("0.00"))
    weekly_used: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal("0.00"))
    monthly_used: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal("0.00"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")

    card: Mapped["Card"] = relationship("Card", back_populates="limits")


class PinProfile(Base):
    __tablename__ = "pin_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    card_id: Mapped[str] = mapped_column(String(36), ForeignKey("cards.id", ondelete="CASCADE"), unique=True, nullable=False)
    pin_verification_method: Mapped[str] = mapped_column(String(30), nullable=False, default="VISA_PVV")  # VISA_PVV, IBM_3624
    pvk_key_reference: Mapped[str] = mapped_column(String(120), nullable=False, default="PVK_VISA_01")
    pin_offset_reference: Mapped[str] = mapped_column(String(120), nullable=False, default="7821")  # PVV or Offset (never clear PIN)
    pvki: Mapped[str] = mapped_column(String(4), nullable=False, default="1")
    cvv_reference: Mapped[str] = mapped_column(String(16), nullable=False, default="011")
    pin_block_format: Mapped[str] = mapped_column(String(30), nullable=False, default="ISO_0")
    pin_status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    retry_counter: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    maximum_retry_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=3)
    pin_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")

    card: Mapped["Card"] = relationship("Card", back_populates="pin_profile")


class EmvProfile(Base):
    __tablename__ = "emv_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    card_id: Mapped[str] = mapped_column(String(36), ForeignKey("cards.id", ondelete="CASCADE"), unique=True, nullable=False)
    application_profile: Mapped[str] = mapped_column(String(100), nullable=False, default="EMV_2000_CVN10")
    aid: Mapped[str] = mapped_column(String(64), nullable=False, default="A0000000031010")
    card_sequence_number: Mapped[str] = mapped_column(String(10), nullable=False, default="01")
    issuer_application_data_reference: Mapped[Optional[str]] = mapped_column(String(120), default="06010A03A00000")
    cryptogram_profile: Mapped[str] = mapped_column(String(100), nullable=False, default="ARPC_METHOD_1")
    master_key_reference: Mapped[str] = mapped_column(String(120), nullable=False, default="MK_AC_EMV01")
    last_atc: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")

    card: Mapped["Card"] = relationship("Card", back_populates="emv_profile")


# ==============================================================================
# C. HOST CONFIGURATION TABLES
# ==============================================================================

class TransactionCode(Base):
    __tablename__ = "transaction_codes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    transaction_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    transaction_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    transaction_category: Mapped[str] = mapped_column(String(30), nullable=False, default="FINANCIAL")
    processing_code: Mapped[str] = mapped_column(String(7), nullable=False, default="0100000")
    default_mti: Mapped[str] = mapped_column(String(4), nullable=False, default="0200")
    financial_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    balance_inquiry_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    debit_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    credit_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reversal_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    pin_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cvv_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pvv_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    emv_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mac_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    account_check_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    card_check_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    limit_check_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    fields: Mapped[List["TransactionCodeField"]] = relationship(
        "TransactionCodeField", back_populates="transaction_code_rel", cascade="all, delete-orphan"
    )


class TransactionCodeField(Base):
    __tablename__ = "transaction_code_fields"
    __table_args__ = (UniqueConstraint("transaction_code_id", "iso_field_number", name="uq_tx_code_field"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    transaction_code_id: Mapped[str] = mapped_column(String(36), ForeignKey("transaction_codes.id", ondelete="CASCADE"), nullable=False)
    iso_field_number: Mapped[int] = mapped_column(Integer, nullable=False)
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    editable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    default_value: Mapped[Optional[str]] = mapped_column(String(250))
    validation_rule: Mapped[Optional[str]] = mapped_column(String(120))
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    transaction_code_rel: Mapped["TransactionCode"] = relationship("TransactionCode", back_populates="fields")


class HostParameter(Base):
    __tablename__ = "host_parameters"
    __table_args__ = (UniqueConstraint("parameter_group", "parameter_name", name="uq_param_group_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    parameter_group: Mapped[str] = mapped_column(String(60), nullable=False)
    parameter_name: Mapped[str] = mapped_column(String(100), nullable=False)
    parameter_value: Mapped[Any] = mapped_column(JSON, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class ResponseCode(Base):
    __tablename__ = "response_codes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    response_code: Mapped[str] = mapped_column(String(5), unique=True, nullable=False)
    response_description: Mapped[str] = mapped_column(String(200), nullable=False)
    response_category: Mapped[str] = mapped_column(String(30), nullable=False, default="DECLINE")
    approved_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    retry_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


# [PATCH step11:network_profile_simulation_cols_fixed]
class NetworkProfile(Base):
    __tablename__ = "network_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    network_name: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    network_type: Mapped[str] = mapped_column(String(30), nullable=False, default="INTERNAL_SIMULATION")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    simulation_mode: Mapped[str] = mapped_column(String(30), nullable=False, default="ALWAYS_APPROVE")
    simulated_response_code: Mapped[str] = mapped_column(String(5), nullable=False, default="00")
    simulated_delay_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    configuration_json: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


# ==============================================================================
# D. HSM AND KEY REFERENCE TABLES
# ==============================================================================

class HsmKeyReference(Base):
    __tablename__ = "hsm_key_references"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    key_name: Mapped[str] = mapped_column(String(100), nullable=False)
    key_type: Mapped[str] = mapped_column(String(30), nullable=False)  # ZMK, ZPK, TMK, PVK, CVK, AWK, IWK, MK-AC, TAK
    key_usage: Mapped[str] = mapped_column(String(60), nullable=False)
    key_identifier: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    kvc: Mapped[str] = mapped_column(String(30), nullable=False)
    algorithm: Mapped[str] = mapped_column(String(40), nullable=False, default="3DES_2KEY")
    key_length: Mapped[int] = mapped_column(Integer, nullable=False, default=128)
    hsm_key_reference: Mapped[str] = mapped_column(String(200), nullable=False)  # Protected LMK cryptogram or slot ref
    key_status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
# [PATCH step10:hsm_key_ceremony_columns]
    clear_key_hex: Mapped[Optional[str]] = mapped_column(String(64))
    parent_key_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey('hsm_key_references.id'), index=True)
    parent_key: Mapped[Optional['HsmKeyReference']] = relationship('HsmKeyReference', remote_side=[id])
# [PATCH step02_01:hsm_key_inst_id]
    institution_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("institutions.id"), index=True)
    processing_system_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("processing_systems.id"), index=True)
    institution: Mapped[Optional["Institution"]] = relationship("Institution", foreign_keys=[institution_id])
    processing_system: Mapped[Optional["ProcessingSystem"]] = relationship("ProcessingSystem", foreign_keys=[processing_system_id])


# [PATCH tx_log_viewer_v1:transaction_trace_event_model]
class TransactionTraceEvent(Base):
    """
    Structured transaction-wise processing trace event recorded during actual pipeline execution
    or reconstructed from persisted TransactionCheck/HsmOperation/AccountLedger records.
    """
    __tablename__ = "transaction_trace_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    transaction_id: Mapped[str] = mapped_column(String(36), ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False, index=True)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(60), index=True)
    event_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    event_code: Mapped[str] = mapped_column(String(60), nullable=False)
    event_category: Mapped[str] = mapped_column(String(40), nullable=False, default="PIPELINE")
    event_name: Mapped[str] = mapped_column(String(120), nullable=False)
    event_status: Mapped[str] = mapped_column(String(20), nullable=False, default="COMPLETED")
    response_code: Mapped[Optional[str]] = mapped_column(String(10))
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class HsmOperation(Base):
    __tablename__ = "hsm_operations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    transaction_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    operation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    key_reference_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("hsm_key_references.id"))
    request_reference: Mapped[str] = mapped_column(String(120), nullable=False)
    sanitized_request: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    sanitized_response: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    response_status: Mapped[str] = mapped_column(String(30), nullable=False)
    error_code: Mapped[str] = mapped_column(String(60), nullable=False, default="00")
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class HsmAuditLog(Base):
    __tablename__ = "hsm_audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    operation_id: Mapped[str] = mapped_column(String(36), ForeignKey("hsm_operations.id"), nullable=False)
    operation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    key_reference_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("hsm_key_references.id"))
    actor: Mapped[str] = mapped_column(String(100), nullable=False, default="HOST_ENGINE")
    result: Mapped[str] = mapped_column(String(30), nullable=False)
    audit_reference: Mapped[str] = mapped_column(String(120), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


# ==============================================================================
# E. TRANSACTION TABLES
# ==============================================================================

class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    transaction_reference: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(120), unique=True, index=True)
    mti: Mapped[str] = mapped_column(String(4), nullable=False)
    processing_code: Mapped[str] = mapped_column(String(7), nullable=False)
    transaction_code: Mapped[Optional[str]] = mapped_column(String(20), index=True)
    stan: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    rrn: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    terminal_id: Mapped[Optional[str]] = mapped_column(String(30))
    merchant_id: Mapped[Optional[str]] = mapped_column(String(30))
    masked_pan: Mapped[Optional[str]] = mapped_column(String(25))
    card_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("cards.id"), index=True)
    customer_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("customers.id"))
    account_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("accounts.id"))
    transaction_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal("0.00"))
    billing_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal("0.00"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BDT")
    transaction_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    response_code: Mapped[str] = mapped_column(String(5), nullable=False, default="00")
    response_message: Mapped[str] = mapped_column(String(200), nullable=False, default="Approved")
    transaction_status: Mapped[str] = mapped_column(String(30), nullable=False, default="COMPLETED")
    authorization_status: Mapped[str] = mapped_column(String(30), nullable=False, default="APPROVED")
    source_channel: Mapped[str] = mapped_column(String(30), nullable=False, default="SIMULATOR")
    original_transaction_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("transactions.id"))
# [PATCH step02_01:tx_institution_attrs]
    issuer_institution_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("institutions.id"), index=True)
    acquirer_institution_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("institutions.id"), index=True)
    ps_code: Mapped[str] = mapped_column(String(30), nullable=False, default="ITCL")
    is_on_us: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    issuer_institution: Mapped[Optional["Institution"]] = relationship("Institution", foreign_keys=[issuer_institution_id])
    acquirer_institution: Mapped[Optional["Institution"]] = relationship("Institution", foreign_keys=[acquirer_institution_id])
    request_message_reference: Mapped[Optional[str]] = mapped_column(String(36))
    response_message_reference: Mapped[Optional[str]] = mapped_column(String(36))
# [PATCH tx_log_viewer_v1:transaction_extra_columns]
    correlation_id: Mapped[Optional[str]] = mapped_column(String(60), index=True)
    approval_code: Mapped[Optional[str]] = mapped_column(String(12))
    mcc: Mapped[Optional[str]] = mapped_column(String(10), index=True)
    pos_entry_mode: Mapped[Optional[str]] = mapped_column(String(10))
    pos_condition_code: Mapped[Optional[str]] = mapped_column(String(10))
    acquirer_id: Mapped[Optional[str]] = mapped_column(String(30), index=True)
    forwarding_id: Mapped[Optional[str]] = mapped_column(String(30))
    terminal_name: Mapped[Optional[str]] = mapped_column(String(120))
    terminal_owner: Mapped[Optional[str]] = mapped_column(String(120))
    merchant_name: Mapped[Optional[str]] = mapped_column(String(120))
    source_account: Mapped[Optional[str]] = mapped_column(String(40), index=True)
    destination_account: Mapped[Optional[str]] = mapped_column(String(40))
    transaction_type_name: Mapped[Optional[str]] = mapped_column(String(80))
    decline_reason: Mapped[Optional[str]] = mapped_column(String(250))
    processing_duration_ms: Mapped[Optional[int]] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    checks: Mapped[List["TransactionCheck"]] = relationship(
        "TransactionCheck", back_populates="transaction", cascade="all, delete-orphan", order_by="TransactionCheck.check_order"
    )
    messages: Mapped[List["TransactionMessage"]] = relationship(
        "TransactionMessage", back_populates="transaction", cascade="all, delete-orphan"
    )


class TransactionCheck(Base):
    __tablename__ = "transaction_checks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    transaction_id: Mapped[str] = mapped_column(String(36), ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False, index=True)
    check_name: Mapped[str] = mapped_column(String(80), nullable=False)
    check_order: Mapped[int] = mapped_column(Integer, nullable=False)
    check_status: Mapped[str] = mapped_column(String(20), nullable=False)  # PASSED, FAILED, SKIPPED
    response_code: Mapped[str] = mapped_column(String(5), nullable=False, default="00")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    transaction: Mapped["Transaction"] = relationship("Transaction", back_populates="checks")


class TransactionMessage(Base):
    __tablename__ = "transaction_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    transaction_id: Mapped[str] = mapped_column(String(36), ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False, index=True)
    message_type: Mapped[str] = mapped_column(String(20), nullable=False)  # REQUEST, RESPONSE
    mti: Mapped[str] = mapped_column(String(4), nullable=False)
    sanitized_message: Mapped[str] = mapped_column(Text, nullable=False)
    message_format: Mapped[str] = mapped_column(String(20), nullable=False, default="TIC")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    transaction: Mapped["Transaction"] = relationship("Transaction", back_populates="messages")


class TransactionReversal(Base):
    __tablename__ = "transaction_reversals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    original_transaction_id: Mapped[str] = mapped_column(String(36), ForeignKey("transactions.id"), nullable=False)
    reversal_transaction_id: Mapped[str] = mapped_column(String(36), ForeignKey("transactions.id"), unique=True, nullable=False)
    original_stan: Mapped[str] = mapped_column(String(12), nullable=False)
    original_rrn: Mapped[str] = mapped_column(String(24), nullable=False)
    reversal_reason: Mapped[str] = mapped_column(String(100), nullable=False)
    reversal_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    reversal_status: Mapped[str] = mapped_column(String(20), nullable=False, default="COMPLETED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SystemLog(Base):
    __tablename__ = "system_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    severity: Mapped[str] = mapped_column(String(15), nullable=False, index=True)
    component: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    event_name: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    transaction_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    operation_reference: Mapped[Optional[str]] = mapped_column(String(120))
    sanitized_details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    transaction_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("transactions.id"))
    notification_type: Mapped[str] = mapped_column(String(20), nullable=False, default="SMS_SIMULATED")
    recipient_masked: Mapped[str] = mapped_column(String(100), nullable=False)
    message_template: Mapped[str] = mapped_column(Text, nullable=False)
    delivery_status: Mapped[str] = mapped_column(String(30), nullable=False, default="SIMULATED_SENT")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

# [PATCH step01_01:institution_and_ps_models]
# ==============================================================================
# F. PROCESSING SYSTEMS, INSTITUTIONS (BANKS) & BIN RANGES (STEP 1)
# ==============================================================================

class ProcessingSystem(Base):
    __tablename__ = "processing_systems"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    ps_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)  # ITCL, VISA, MASTERCARD, NPSB, INTERNAL
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    system_type: Mapped[str] = mapped_column(String(40), nullable=False, default="HOST_SWITCH")  # HOST_SWITCH, CARD_SCHEME, NATIONAL_SWITCH, INTERNAL
    message_format: Mapped[str] = mapped_column(String(40), nullable=False, default="TIC_V2164E")  # TIC_V2164E, ISO8583_1987
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    configuration: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    institutions: Mapped[List["Institution"]] = relationship(
        "Institution", back_populates="primary_processing_system"
    )
    institution_links: Mapped[List["InstitutionProcessingSystem"]] = relationship(
        "InstitutionProcessingSystem", back_populates="processing_system", cascade="all, delete-orphan"
    )
    bin_ranges: Mapped[List["BinRange"]] = relationship(
        "BinRange", back_populates="processing_system"
    )


class Institution(Base):
    __tablename__ = "institutions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    institution_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)  # XBANK, YBANK, ZBANK, IFIC
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    short_name: Mapped[Optional[str]] = mapped_column(String(60))
    acquirer_id: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # DE32 Acquiring Institution ID
    forwarding_id: Mapped[Optional[str]] = mapped_column(String(20))  # DE33 Forwarding Institution ID
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="BOTH")  # ISSUER, ACQUIRER, BOTH
    processing_system_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("processing_systems.id"), nullable=False, index=True
    )
    country_code: Mapped[str] = mapped_column(String(3), nullable=False, default="050")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BDT")
    settlement_account_number: Mapped[Optional[str]] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    configuration: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    primary_processing_system: Mapped["ProcessingSystem"] = relationship(
        "ProcessingSystem", back_populates="institutions"
    )
    processing_system_links: Mapped[List["InstitutionProcessingSystem"]] = relationship(
        "InstitutionProcessingSystem", back_populates="institution", cascade="all, delete-orphan"
    )
    bin_ranges: Mapped[List["BinRange"]] = relationship(
        "BinRange", back_populates="institution", cascade="all, delete-orphan"
    )


class InstitutionProcessingSystem(Base):
    """
    Many-to-many participation table allowing an ITCL bank to also participate in
    VISA, MASTERCARD, NPSB, or future processing systems with scheme-specific IDs.
    """
    __tablename__ = "institution_processing_systems"
    __table_args__ = (
        UniqueConstraint("institution_id", "processing_system_id", name="uq_inst_proc_system"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    institution_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    processing_system_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("processing_systems.id", ondelete="CASCADE"), nullable=False, index=True
    )
    member_id: Mapped[str] = mapped_column(String(40), nullable=False)
    acquirer_id: Mapped[Optional[str]] = mapped_column(String(30))
    network_identifier: Mapped[Optional[str]] = mapped_column(String(30))
    issuer_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    acquirer_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    message_format: Mapped[str] = mapped_column(String(40), nullable=False, default="TIC_V2164E")
    routing_configuration: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    effective_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    institution: Mapped["Institution"] = relationship("Institution", back_populates="processing_system_links")
    processing_system: Mapped["ProcessingSystem"] = relationship("ProcessingSystem", back_populates="institution_links")


class BinRange(Base):
    __tablename__ = "bin_ranges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    bin_prefix: Mapped[str] = mapped_column(String(12), unique=True, nullable=False, index=True)
    bin_low: Mapped[str] = mapped_column(String(19), nullable=False, index=True)
    bin_high: Mapped[str] = mapped_column(String(19), nullable=False, index=True)
    pan_length: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=16)
    institution_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    processing_system_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("processing_systems.id"), nullable=False, index=True
    )
    card_type: Mapped[str] = mapped_column(String(30), nullable=False, default="DEBIT")  # DEBIT, CREDIT, PREPAID
    card_product: Mapped[str] = mapped_column(String(60), nullable=False, default="VISA_DEBIT_CLASSIC")
    scheme: Mapped[str] = mapped_column(String(30), nullable=False, default="ITCL")
    country_code: Mapped[str] = mapped_column(String(3), nullable=False, default="050")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BDT")
    is_on_us: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    institution: Mapped["Institution"] = relationship("Institution", back_populates="bin_ranges")
    processing_system: Mapped["ProcessingSystem"] = relationship("ProcessingSystem", back_populates="bin_ranges")


# [PATCH step03_01:audit_trail_model]

# ==============================================================================
# G. AUDIT TRAIL LOGGING (STEP 3)
# ==============================================================================

class AuditTrail(Base):
    __tablename__ = "audit_trail"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # CUSTOMER, ACCOUNT, CARD, etc.
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(20), nullable=False)  # CREATE, UPDATE, DELETE, STATUS_CHANGE
    performed_by: Mapped[str] = mapped_column(String(100), nullable=False, default="admin")
    before_state: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    after_state: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    change_summary: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


# [PATCH step07:models_api_and_crypto_logs]

# ==============================================================================
# H. OPERATIONAL API LOGS & GRANULAR CRYPTO EVENTS (STEP 7)
# ==============================================================================

class ApiAuditLog(Base):
    __tablename__ = "api_audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    correlation_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    http_method: Mapped[str] = mapped_column(String(10), nullable=False)
    path: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    client_ip: Mapped[str] = mapped_column(String(45), default="127.0.0.1")
    user_agent: Mapped[str] = mapped_column(String(250), default="Unknown")
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    user_id: Mapped[Optional[str]] = mapped_column(String(50))
    request_headers: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    request_body: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    response_body: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class CryptoEvent(Base):
    __tablename__ = "crypto_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    correlation_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    transaction_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    operation_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    step_name: Mapped[str] = mapped_column(String(80), nullable=False)
    key_id: Mapped[Optional[str]] = mapped_column(String(100))
    key_kcv: Mapped[Optional[str]] = mapped_column(String(30))
    raw_input: Mapped[Optional[str]] = mapped_column(Text)
    raw_output: Mapped[Optional[str]] = mapped_column(Text)
    expected_output: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="COMPLETED")
    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


# [PATCH step08:authorizer_rule_model]

# ==============================================================================
# I. CONFIGURABLE AUTHORIZER RULES (STEP 8)
# ==============================================================================

class AuthorizerRule(Base):
    __tablename__ = "authorizer_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    rule_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100, index=True)
    stage: Mapped[str] = mapped_column(String(30), nullable=False, default="PRE_AUTH")
    rule_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="SCRIPT")  # BUILDER, SCRIPT
    conditions_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    expression: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False, default="DECLINE")  # DECLINE, APPROVE, FLAG
    response_code: Mapped[str] = mapped_column(String(5), nullable=False, default="05")
    message: Mapped[str] = mapped_column(String(200), nullable=False, default="Declined by Authorizer Rule")
    stop_on_match: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


# [PATCH step12:models_settlement]

# ==============================================================================
# J. CLEARING, SETTLEMENT & MULTILATERAL RECONCILIATION (STEP 12)
# ==============================================================================

class SettlementBatch(Base):
    __tablename__ = "settlement_batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    batch_number: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    processing_system_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey('processing_systems.id'))
    ps_code: Mapped[str] = mapped_column(String(30), nullable=False, default='ITCL')
    cutover_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='CLOSED')  # OPEN, PROCESSING, CLOSED, RECONCILED
    total_transactions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal('0.00'))
    total_fees: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal('0.00'))
    mismatch_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    entries: Mapped[List['SettlementEntry']] = relationship('SettlementEntry', back_populates='batch', cascade='all, delete-orphan')
    positions: Mapped[List['SettlementPosition']] = relationship('SettlementPosition', back_populates='batch', cascade='all, delete-orphan')


class SettlementEntry(Base):
    __tablename__ = "settlement_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    batch_id: Mapped[str] = mapped_column(String(36), ForeignKey('settlement_batches.id', ondelete='CASCADE'), nullable=False, index=True)
    transaction_id: Mapped[str] = mapped_column(String(36), ForeignKey('transactions.id'), nullable=False, index=True)
    issuer_institution_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey('institutions.id'))
    acquirer_institution_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey('institutions.id'))
    mti: Mapped[str] = mapped_column(String(4), nullable=False)
    transaction_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    interchange_fee: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal('0.00'))
    scheme_fee: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal('0.00'))
    net_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    settlement_status: Mapped[str] = mapped_column(String(20), nullable=False, default='SETTLED')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    batch: Mapped['SettlementBatch'] = relationship('SettlementBatch', back_populates='entries')
    transaction: Mapped['Transaction'] = relationship('Transaction')


class SettlementPosition(Base):
    __tablename__ = "settlement_positions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    batch_id: Mapped[str] = mapped_column(String(36), ForeignKey('settlement_batches.id', ondelete='CASCADE'), nullable=False, index=True)
    institution_id: Mapped[str] = mapped_column(String(36), ForeignKey('institutions.id'), nullable=False, index=True)
    net_settlement_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal('0.00'))
    debit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    credit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    debit_volume: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal('0.00'))
    credit_volume: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal('0.00'))
    net_fee_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal('0.00'))
    settlement_status: Mapped[str] = mapped_column(String(20), nullable=False, default='SETTLED')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    batch: Mapped['SettlementBatch'] = relationship('SettlementBatch', back_populates='positions')
    institution: Mapped['Institution'] = relationship('Institution')


# [PATCH add_pan_routing_rule_model]

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

