"""
models_local_host.py
Models for the Rajon Local Host control center:

  * LocalHostPolicy    - transaction policy of the host. One GLOBAL row plus optional per-BANK overrides.
  * HostAlgo           - user written Python / SQL risk block (scope: GLOBAL, BANK or CARD_PROFILE).
  * HostAlgoVersion    - every saved version of an algo (audit + rollback).
  * HostAlgoLog        - execution log of algos (matches, blocks, errors).
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import Boolean, DateTime, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class LocalHostPolicy(Base):
    __tablename__ = "local_host_policies"
    __table_args__ = (UniqueConstraint("scope_type", "institution_id", name="uq_local_host_policy_scope"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    scope_type: Mapped[str] = mapped_column(String(10), nullable=False, default="GLOBAL", index=True)  # GLOBAL | BANK
    institution_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, default="Global Default")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Sparse configuration. Sections that are missing are inherited (BANK -> GLOBAL -> built-in defaults).
    config_json: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_by: Mapped[Optional[str]] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class HostAlgo(Base):
    __tablename__ = "host_algos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    algo_code: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="PYTHON")  # PYTHON | SQL
    code: Mapped[str] = mapped_column(Text, nullable=False, default="")
    scope_type: Mapped[str] = mapped_column(String(15), nullable=False, default="GLOBAL", index=True)  # GLOBAL | BANK | CARD_PROFILE
    institution_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    card_profile_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    stage: Mapped[str] = mapped_column(String(15), nullable=False, default="PRE_AUTH", index=True)  # PRE_AUTH | POST_AUTH
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100, index=True)
    mode: Mapped[str] = mapped_column(String(10), nullable=False, default="ENFORCE")  # ENFORCE | MONITOR
    default_action: Mapped[str] = mapped_column(String(20), nullable=False, default="DECLINE")
    default_response_code: Mapped[str] = mapped_column(String(5), nullable=False, default="57")
    default_message: Mapped[str] = mapped_column(String(200), nullable=False, default="Declined by risk algo")
    on_error: Mapped[str] = mapped_column(String(10), nullable=False, default="SKIP")  # SKIP | DECLINE
    stop_on_match: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    tx_codes_json: Mapped[Optional[Any]] = mapped_column(JSON)  # list of transaction codes, empty = all
    channels_json: Mapped[Optional[Any]] = mapped_column(JSON)  # list of channels, empty = all
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    eval_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_hit_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[Optional[str]] = mapped_column(String(80))
    updated_by: Mapped[Optional[str]] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class HostAlgoVersion(Base):
    __tablename__ = "host_algo_versions"
    __table_args__ = (Index("ix_host_algo_versions_algo", "algo_id", "version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    algo_id: Mapped[str] = mapped_column(String(36), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    change_note: Mapped[Optional[str]] = mapped_column(String(250))
    changed_by: Mapped[Optional[str]] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class HostAlgoLog(Base):
    __tablename__ = "host_algo_logs"
    __table_args__ = (Index("ix_host_algo_logs_algo_time", "algo_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    algo_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    algo_code: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    transaction_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    transaction_reference: Mapped[Optional[str]] = mapped_column(String(60))
    masked_pan: Mapped[Optional[str]] = mapped_column(String(30))
    stage: Mapped[str] = mapped_column(String(15), nullable=False, default="PRE_AUTH")
    mode: Mapped[str] = mapped_column(String(10), nullable=False, default="ENFORCE")
    matched: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    action: Mapped[Optional[str]] = mapped_column(String(20))
    action_applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    response_code: Mapped[Optional[str]] = mapped_column(String(5))
    message: Mapped[Optional[str]] = mapped_column(String(300))
    error: Mapped[Optional[str]] = mapped_column(Text)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    context_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
