"""
local_host_engine.py
Rajon Local Host control center - decision engines used by the host pipeline.

  1. LocalHostEngine.evaluate_policy()  per-bank / global transaction policy
       (host status, business hours, source systems, channels, transaction matrix, currency,
        cross border, MCC, acquirers / terminal owners, velocity)
  2. LocalHostEngine.run_algos()        user written Python / SQL risk blocks
       actions: APPROVE, DECLINE, BLOCK_CARD, BLOCK_CUSTOMER, FLAG   (modes: ENFORCE / MONITOR)

Python algos run in a restricted sandbox (AST whitelist, no imports, no file/network access,
instruction + time budget). SQL algos are read-only SELECT statements with named parameters.
"""
from __future__ import annotations

import ast
import hashlib
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.audit_service import record_audit
from app.logging_service import record_system_log
from app.models import (
    Account,
    AccountLimit,
    Card,
    CardLimit,
    CardProfile,
    Customer,
    Institution,
    Transaction,
)
from app.models_local_host import HostAlgo, HostAlgoLog, LocalHostPolicy

logger = logging.getLogger("rajon.localhost")

HOST_UTC_OFFSET_HOURS = float(os.getenv("HOST_UTC_OFFSET_HOURS", "6"))  # Bangladesh = UTC+6

CHANNELS = ["ATM", "POS", "ECOM", "MOBILE", "INTERNET", "OTHER"]
ALGO_ACTIONS = ["DECLINE", "APPROVE", "BLOCK_CARD", "BLOCK_CUSTOMER", "FLAG"]
ALGO_STAGES = ["PRE_AUTH", "POST_AUTH"]
ALGO_MODES = ["ENFORCE", "MONITOR"]
ALGO_SCOPES = ["GLOBAL", "BANK", "CARD_PROFILE"]
ALGO_LANGUAGES = ["PYTHON", "SQL"]

# ============================================================================
# Policy defaults
# ============================================================================
DEFAULT_POLICY: Dict[str, Any] = {
    "general": {
        "host_status": "ACTIVE",  # ACTIVE | MAINTENANCE | DECLINE_ALL
        "status_response_code": "91",
        "status_message": "Host is not available",
        "decline_response_code": "57",
        "min_amount": 0,
        "max_amount": 0,  # 0 = no limit
        "allowed_currencies": [],  # empty = all
        "business_hours": {"enabled": False, "start": "00:00", "end": "23:59"},
    },
    "channels": {c: {"enabled": True, "min_amount": 0, "max_amount": 0} for c in CHANNELS},
    "sources": {"ON_US": {"enabled": True, "max_amount": 0, "allowed_tx_codes": []}},
    "transactions": {},  # tx_code -> {enabled, channels[], min_amount, max_amount}
    "cross_border": {
        "enabled": True,
        "allowed_countries": [],
        "blocked_countries": [],
        "response_code": "57",
    },
    "mcc": {"allowed": [], "blocked": [], "response_code": "57"},
    "acquirers": {"allowed": [], "blocked": [], "response_code": "58"},
    "velocity": {
        "enabled": False,
        "max_tx_per_minute": 0,
        "max_tx_per_hour": 0,
        "max_declines_per_day": 0,
        "response_code": "65",
    },
}
DICT_OF_DICT_SECTIONS = ("channels", "sources", "transactions")
POLICY_SECTIONS = list(DEFAULT_POLICY.keys())


def _merge_section(name: str, *layers: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for layer in layers:
        if not isinstance(layer, dict):
            continue
        if name in DICT_OF_DICT_SECTIONS:
            for k, v in layer.items():
                base = out.get(k, {})
                out[k] = {**base, **v} if isinstance(v, dict) else v
        else:
            for k, v in layer.items():
                if isinstance(v, dict) and isinstance(out.get(k), dict):
                    out[k] = {**out[k], **v}
                else:
                    out[k] = v
    return out


def effective_policy(db: Session, institution_id: Optional[str]) -> Dict[str, Any]:
    """Merge built-in defaults <- GLOBAL policy <- BANK policy (section level inheritance)."""
    glob = (
        db.query(LocalHostPolicy)
        .filter(LocalHostPolicy.scope_type == "GLOBAL", LocalHostPolicy.enabled == True)  # noqa: E712
        .first()
    )
    bank = None
    if institution_id:
        bank = (
            db.query(LocalHostPolicy)
            .filter(
                LocalHostPolicy.scope_type == "BANK",
                LocalHostPolicy.institution_id == institution_id,
                LocalHostPolicy.enabled == True,  # noqa: E712
            )
            .first()
        )
    g_cfg = (glob.config_json if glob else None) or {}
    b_cfg = (bank.config_json if bank else None) or {}
    result: Dict[str, Any] = {}
    sources: Dict[str, str] = {}
    for sec in POLICY_SECTIONS:
        result[sec] = _merge_section(sec, DEFAULT_POLICY[sec], g_cfg.get(sec), b_cfg.get(sec))
        sources[sec] = "BANK" if sec in b_cfg else ("GLOBAL" if sec in g_cfg else "DEFAULT")
    return {"config": result, "sources": sources, "global_id": glob.id if glob else None, "bank_id": bank.id if bank else None}


def sanitize_policy_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only known sections; coerce types so a bad payload can never break the host."""
    clean: Dict[str, Any] = {}
    if not isinstance(cfg, dict):
        return clean

    def num(v: Any) -> float:
        try:
            return max(0.0, float(v or 0))
        except (TypeError, ValueError):
            return 0.0

    def lst(v: Any) -> List[str]:
        if isinstance(v, str):
            v = [x for x in re.split(r"[,\s]+", v) if x]
        return [str(x).strip() for x in (v or []) if str(x).strip()]

    def rc(v: Any, default: str) -> str:
        s = str(v or "").strip()
        return s if re.fullmatch(r"[0-9A-Za-z]{2}", s) else default

    if "general" in cfg and isinstance(cfg["general"], dict):
        g = cfg["general"]
        bh = g.get("business_hours") or {}
        clean["general"] = {
            "host_status": g.get("host_status") if g.get("host_status") in ("ACTIVE", "MAINTENANCE", "DECLINE_ALL") else "ACTIVE",
            "status_response_code": rc(g.get("status_response_code"), "91"),
            "status_message": str(g.get("status_message") or "Host is not available")[:150],
            "decline_response_code": rc(g.get("decline_response_code"), "57"),
            "min_amount": num(g.get("min_amount")),
            "max_amount": num(g.get("max_amount")),
            "allowed_currencies": lst(g.get("allowed_currencies")),
            "business_hours": {
                "enabled": bool(bh.get("enabled", False)),
                "start": str(bh.get("start") or "00:00")[:5],
                "end": str(bh.get("end") or "23:59")[:5],
            },
        }
    if "channels" in cfg and isinstance(cfg["channels"], dict):
        clean["channels"] = {
            str(k).upper(): {
                "enabled": bool(v.get("enabled", True)),
                "min_amount": num(v.get("min_amount")),
                "max_amount": num(v.get("max_amount")),
            }
            for k, v in cfg["channels"].items()
            if isinstance(v, dict)
        }
    if "sources" in cfg and isinstance(cfg["sources"], dict):
        clean["sources"] = {
            str(k).upper(): {
                "enabled": bool(v.get("enabled", True)),
                "max_amount": num(v.get("max_amount")),
                "allowed_tx_codes": lst(v.get("allowed_tx_codes")),
            }
            for k, v in cfg["sources"].items()
            if isinstance(v, dict)
        }
    if "transactions" in cfg and isinstance(cfg["transactions"], dict):
        clean["transactions"] = {
            str(k): {
                "enabled": bool(v.get("enabled", True)),
                "channels": [c.upper() for c in lst(v.get("channels"))],
                "min_amount": num(v.get("min_amount")),
                "max_amount": num(v.get("max_amount")),
            }
            for k, v in cfg["transactions"].items()
            if isinstance(v, dict)
        }
    if "cross_border" in cfg and isinstance(cfg["cross_border"], dict):
        c = cfg["cross_border"]
        clean["cross_border"] = {
            "enabled": bool(c.get("enabled", True)),
            "allowed_countries": lst(c.get("allowed_countries")),
            "blocked_countries": lst(c.get("blocked_countries")),
            "response_code": rc(c.get("response_code"), "57"),
        }
    for sec, dflt in (("mcc", "57"), ("acquirers", "58")):
        if sec in cfg and isinstance(cfg[sec], dict):
            clean[sec] = {
                "allowed": lst(cfg[sec].get("allowed")),
                "blocked": lst(cfg[sec].get("blocked")),
                "response_code": rc(cfg[sec].get("response_code"), dflt),
            }
    if "velocity" in cfg and isinstance(cfg["velocity"], dict):
        v = cfg["velocity"]
        clean["velocity"] = {
            "enabled": bool(v.get("enabled", False)),
            "max_tx_per_minute": int(num(v.get("max_tx_per_minute"))),
            "max_tx_per_hour": int(num(v.get("max_tx_per_hour"))),
            "max_declines_per_day": int(num(v.get("max_declines_per_day"))),
            "response_code": rc(v.get("response_code"), "65"),
        }
    return clean


# ============================================================================
# Transaction context (shared by policy, algo, field catalog and the test panels)
# ============================================================================
def derive_channel(fields: Dict[str, str], request_data: Dict[str, Any]) -> str:
    explicit = str((request_data or {}).get("source_channel") or "").upper()
    if explicit in CHANNELS and explicit != "OTHER":
        return explicit
    mcc = str(fields.get("18", ""))
    term = str(fields.get("41", "")).upper()
    pos_cond = str(fields.get("25", ""))
    entry = str(fields.get("22", ""))
    if mcc == "6011" or term.startswith("ATM"):
        return "ATM"
    if pos_cond in ("08", "81", "82") or entry.startswith("81"):
        return "ECOM"
    if explicit in ("MOBILE", "INTERNET"):
        return explicit
    if term or pos_cond or entry:
        return "POS"
    return "OTHER"


def _g(obj: Any, attr: str, default: Any = "") -> Any:
    if obj is None:
        return default
    v = getattr(obj, attr, default)
    return default if v is None else v


def _num(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _days_since(dt: Optional[datetime], now: datetime) -> int:
    if not dt:
        return 0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0, (now - dt).days)


def _age(dob: Any, now: datetime) -> int:
    if not dob:
        return 0
    try:
        a = now.year - dob.year
        if (now.month, now.day) < (dob.month, dob.day):
            a -= 1
        return max(0, a)
    except Exception:
        return 0


# (group, key, type, description, example, getter(r))
FIELD_SPEC: List[Tuple[str, str, str, str, Any, Callable[[SimpleNamespace], Any]]] = [
    # ---- transaction
    ("tx", "amount", "number", "Transaction amount in major units (2500.00 = BDT 2,500)", 2500.0, lambda r: float(r.amount)),
    ("tx", "currency", "text", "Currency sent in DE49 (e.g. 050 or BDT)", "050", lambda r: r.fields.get("49", "BDT")),
    ("tx", "tran_code", "text", "Transaction code (10 = cash withdrawal, 00 = purchase, 31 = balance inquiry ...)", "10", lambda r: str(_g(r.tx_cfg, "transaction_code", ""))),
    ("tx", "tran_name", "text", "Transaction code name", "Cash Withdrawal", lambda r: str(_g(r.tx_cfg, "transaction_name", ""))),
    ("tx", "mti", "text", "Message type indicator", "0200", lambda r: str(r.mti)),
    ("tx", "processing_code", "text", "DE3 processing code (7 digits)", "0100000", lambda r: r.fields.get("3", "")),
    ("tx", "is_financial", "bool", "True when the transaction moves money", True, lambda r: bool(_g(r.tx_cfg, "financial_flag", True))),
    ("tx", "is_debit", "bool", "True when the transaction debits the account", True, lambda r: bool(_g(r.tx_cfg, "debit_flag", True))),
    ("tx", "channel", "text", "ATM, POS, ECOM, MOBILE, INTERNET or OTHER", "ATM", lambda r: r.channel),
    ("tx", "source", "text", "Where the request came from: ON_US or the processing system code (ITCL, NPSB, VISA, MASTERCARD ...)", "ON_US", lambda r: r.source),
    ("tx", "source_channel", "text", "Raw source_channel sent by the caller (SIMULATOR, NPSB ...)", "SIMULATOR", lambda r: str((r.req or {}).get("source_channel", "SIMULATOR"))),
    ("tx", "is_on_us", "bool", "True when the terminal owner (acquirer) bank is also the card issuer", True, lambda r: r.is_on_us),
    ("tx", "is_foreign", "bool", "True when the terminal country (DE19) differs from the issuer bank country", False, lambda r: r.is_foreign),
    ("tx", "country", "text", "Terminal / acquirer country code (DE19, 050 = Bangladesh)", "050", lambda r: r.country),
    ("tx", "pos_entry_mode", "text", "POS entry mode (DE22)", "051", lambda r: r.fields.get("22", "")),
    ("tx", "pos_condition_code", "text", "POS condition code (DE25)", "00", lambda r: r.fields.get("25", "")),
    ("tx", "pin_entered", "bool", "True when a PIN block (DE52) is present", True, lambda r: bool(r.fields.get("52"))),
    ("tx", "emv", "bool", "True when EMV data (DE55) is present", False, lambda r: bool(r.fields.get("55"))),
    ("tx", "hour", "number", "Hour of the day 0-23 (DE12 local terminal time if sent, otherwise the host clock)", 14, lambda r: r.hour),
    ("tx", "minute", "number", "Minute 0-59", 30, lambda r: r.minute),
    ("tx", "host_hour", "number", "Hour of the day on the HOST clock (UTC+6), ignores DE12 sent by the terminal", 14, lambda r: r.now_local.hour),
    ("tx", "weekday", "number", "Day of week: 0 = Monday ... 6 = Sunday", 2, lambda r: r.weekday),
    ("tx", "is_weekend", "bool", "True on Saturday or Sunday", False, lambda r: r.weekday >= 5),
    ("tx", "is_night", "bool", "True between 22:00 and 06:00", False, lambda r: r.hour >= 22 or r.hour < 6),
    ("tx", "time", "text", "HH:MM text, handy for comparisons", "14:30", lambda r: f"{r.hour:02d}:{r.minute:02d}"),
    ("tx", "date", "text", "YYYY-MM-DD (host local date)", "2026-11-09", lambda r: r.now_local.strftime("%Y-%m-%d")),
    ("tx", "stan", "text", "System trace audit number (DE11)", "000123", lambda r: r.fields.get("11", "")),
    ("tx", "rrn", "text", "Retrieval reference number (DE37)", "000000000123", lambda r: r.fields.get("37", "")),
    ("tx", "reference", "text", "Host transaction reference", "TX-20261109-ABC123", lambda r: r.tx_ref),
    # ---- terminal / acquirer
    ("terminal", "id", "text", "Terminal ID (DE41)", "ATM0001", lambda r: r.fields.get("41", "")),
    ("terminal", "owner", "text", "Terminal owner = acquiring bank name", "X Bank PLC", lambda r: str(_g(r.acq, "name", ""))),
    ("terminal", "owner_code", "text", "Terminal owner = acquiring bank code", "XBANK", lambda r: str(_g(r.acq, "institution_code", ""))),
    ("terminal", "acquirer_id", "text", "Acquiring institution id (DE32)", "123456", lambda r: r.fields.get("32", "")),
    ("terminal", "merchant_id", "text", "Merchant / card acceptor id (DE42)", "MERCH001", lambda r: r.fields.get("42", "")),
    ("terminal", "merchant_name", "text", "Merchant name / location (DE43)", "SUPER SHOP DHAKA", lambda r: r.fields.get("43", "")),
    ("terminal", "mcc", "text", "Merchant category code (DE18). 6011 = ATM, 5411 = grocery", "6011", lambda r: r.fields.get("18", "")),
    # ---- card
    ("card", "id", "text", "Card id (internal)", "7f0e...", lambda r: str(_g(r.card, "id", ""))),
    ("card", "masked_pan", "text", "Masked PAN", "456789******0001", lambda r: str(_g(r.card, "masked_pan", ""))),
    ("card", "pan", "text", "Full PAN (never written to the algo log)", "4567890123450001", lambda r: str(_g(r.card, "test_pan_reference", ""))),
    ("card", "bin", "text", "First 6 digits of the PAN", "456789", lambda r: str(_g(r.card, "test_pan_reference", ""))[:6]),
    ("card", "last4", "text", "Last 4 digits of the PAN", "0001", lambda r: str(_g(r.card, "test_pan_reference", ""))[-4:]),
    ("card", "holder", "text", "Cardholder name", "RAJON ALI", lambda r: str(_g(r.card, "cardholder_name", ""))),
    ("card", "status", "text", "ACTIVE, BLOCKED, EXPIRED, LOST, STOLEN ...", "ACTIVE", lambda r: str(_g(r.card, "card_status", ""))),
    ("card", "product", "text", "Card product", "VISA_DEBIT_CLASSIC", lambda r: str(_g(r.card, "card_product", ""))),
    ("card", "type", "text", "DEBIT / CREDIT / PREPAID", "DEBIT", lambda r: str(_g(r.card, "card_type", ""))),
    ("card", "expiry_month", "number", "Expiry month 1-12", 12, lambda r: int(_g(r.card, "expiry_month", 0) or 0)),
    ("card", "expiry_year", "number", "Expiry year", 2030, lambda r: int(_g(r.card, "expiry_year", 0) or 0)),
    ("card", "expiry", "text", "Expiry as YYYY-MM", "2030-12", lambda r: f"{int(_g(r.card, 'expiry_year', 0) or 0):04d}-{int(_g(r.card, 'expiry_month', 0) or 0):02d}"),
    ("card", "is_expired", "bool", "True when the card is past its expiry month", False, lambda r: r.card_expired),
    ("card", "days_to_expiry", "number", "Days until the end of the expiry month (negative = expired)", 400, lambda r: r.days_to_expiry),
    ("card", "age_days", "number", "Days since the card was created", 120, lambda r: _days_since(_g(r.card, "created_at", None), r.now_utc)),
    ("card", "pin_retries", "number", "Wrong PIN attempts since the last good PIN", 0, lambda r: int(_g(r.pin_profile, "retry_counter", 0) or 0)),
    ("card", "pin_max_retries", "number", "Maximum PIN attempts", 3, lambda r: int(_g(r.pin_profile, "maximum_retry_count", 3) or 3)),
    # ---- customer
    ("customer", "id", "text", "Customer id (internal)", "c1f2...", lambda r: str(_g(r.cust, "id", ""))),
    ("customer", "number", "text", "Customer number (CIF)", "CUST-1001", lambda r: str(_g(r.cust, "customer_number", ""))),
    ("customer", "name", "text", "Full name", "Rajon Ali", lambda r: f"{_g(r.cust, 'first_name', '')} {_g(r.cust, 'last_name', '')}".strip()),
    ("customer", "first_name", "text", "First name", "Rajon", lambda r: str(_g(r.cust, "first_name", ""))),
    ("customer", "last_name", "text", "Last name", "Ali", lambda r: str(_g(r.cust, "last_name", ""))),
    ("customer", "status", "text", "ACTIVE / BLOCKED / CLOSED", "ACTIVE", lambda r: str(_g(r.cust, "customer_status", ""))),
    ("customer", "risk", "text", "Risk category: NORMAL, VIP, HIGH", "NORMAL", lambda r: str(_g(r.cust, "risk_category", ""))),
    ("customer", "is_vip", "bool", "True when risk category is VIP", False, lambda r: str(_g(r.cust, "risk_category", "")).upper() == "VIP"),
    ("customer", "kyc_status", "text", "KYC status (PENDING / VERIFIED ...)", "VERIFIED", lambda r: str(_g(r.cust, "kyc_status", ""))),
    ("customer", "age", "number", "Age in years (0 when date of birth is unknown)", 34, lambda r: _age(_g(r.cust, "date_of_birth", None), r.now_utc)),
    ("customer", "gender", "text", "Gender", "MALE", lambda r: str(_g(r.cust, "gender", ""))),
    ("customer", "nationality", "text", "Nationality", "Bangladeshi", lambda r: str(_g(r.cust, "nationality", ""))),
    ("customer", "city", "text", "City", "Dhaka", lambda r: str(_g(r.cust, "city", ""))),
    ("customer", "country", "text", "Country", "Bangladesh", lambda r: str(_g(r.cust, "country", ""))),
    ("customer", "mobile", "text", "Mobile number", "+8801700000001", lambda r: str(_g(r.cust, "mobile_number", ""))),
    ("customer", "email", "text", "Email", "rajon@example.com", lambda r: str(_g(r.cust, "email", ""))),
    ("customer", "since_days", "number", "Days since the customer was created", 900, lambda r: _days_since(_g(r.cust, "created_at", None), r.now_utc)),
    # ---- account
    ("account", "id", "text", "Account id (internal)", "a91c...", lambda r: str(_g(r.acct, "id", ""))),
    ("account", "number", "text", "Account number", "2001000111", lambda r: str(_g(r.acct, "account_number", ""))),
    ("account", "type", "text", "SAVINGS / CURRENT / CREDIT", "SAVINGS", lambda r: str(_g(r.acct, "account_type", ""))),
    ("account", "currency", "text", "Account currency", "BDT", lambda r: str(_g(r.acct, "currency", ""))),
    ("account", "status", "text", "ACTIVE / BLOCKED / CLOSED", "ACTIVE", lambda r: str(_g(r.acct, "account_status", ""))),
    ("account", "balance", "number", "Available balance", 150000.0, lambda r: _num(_g(r.acct, "available_balance", 0))),
    ("account", "ledger_balance", "number", "Ledger balance", 150000.0, lambda r: _num(_g(r.acct, "ledger_balance", 0))),
    ("account", "overdraft", "number", "Overdraft limit", 0.0, lambda r: _num(_g(r.acct, "overdraft_limit", 0))),
    ("account", "spendable", "number", "Available balance + overdraft", 150000.0, lambda r: _num(_g(r.acct, "available_balance", 0)) + _num(_g(r.acct, "overdraft_limit", 0))),
    ("account", "balance_after", "number", "Available balance after this transaction (debits only)", 147500.0, lambda r: _num(_g(r.acct, "available_balance", 0)) - (float(r.amount) if bool(_g(r.tx_cfg, "debit_flag", True)) and bool(_g(r.tx_cfg, "financial_flag", True)) else 0.0)),
    # ---- issuer bank / acquirer bank
    ("bank", "id", "text", "Issuer bank id (the bank of the card)", "b7e1...", lambda r: str(_g(r.issuer, "id", ""))),
    ("bank", "code", "text", "Issuer bank code", "XBANK", lambda r: str(_g(r.issuer, "institution_code", ""))),
    ("bank", "name", "text", "Issuer bank name", "X Bank PLC", lambda r: str(_g(r.issuer, "name", ""))),
    ("bank", "short_name", "text", "Issuer bank short name", "XBL", lambda r: str(_g(r.issuer, "short_name", ""))),
    ("bank", "country", "text", "Issuer bank country code", "050", lambda r: str(_g(r.issuer, "country_code", "050"))),
    ("bank", "status", "text", "Issuer bank status", "ACTIVE", lambda r: str(_g(r.issuer, "status", ""))),
    ("acquirer", "id", "text", "Acquirer bank id", "b7e2...", lambda r: str(_g(r.acq, "id", ""))),
    ("acquirer", "code", "text", "Acquirer bank code", "YBANK", lambda r: str(_g(r.acq, "institution_code", ""))),
    ("acquirer", "name", "text", "Acquirer bank name", "Y Bank PLC", lambda r: str(_g(r.acq, "name", ""))),
    ("acquirer", "country", "text", "Acquirer bank country code", "050", lambda r: str(_g(r.acq, "country_code", "050"))),
    ("acquirer", "is_own", "bool", "True when acquirer and issuer are the same bank", True, lambda r: r.is_on_us),
    ("acquirer", "ps_code", "text", "Processing system of the transaction (ITCL, NPSB, VISA ...)", "ITCL", lambda r: str(r.ps_code or "")),
    # ---- profiles
    ("profile", "card_code", "text", "Card profile code", "VISA_CLASSIC", lambda r: str(_g(r.card_profile, "profile_code", ""))),
    ("profile", "card_name", "text", "Card profile name", "Visa Classic", lambda r: str(_g(r.card_profile, "profile_name", ""))),
    ("profile", "auth_code", "text", "Authorization profile code (resolved by the limit engine)", "VISA_CLASSIC_STANDARD", lambda r: str(r.auth_code or "")),
    ("profile", "auth_name", "text", "Authorization profile name", "Visa Classic Standard", lambda r: str(r.auth_name or "")),
    # ---- limit usage (legacy per-card / per-account counters)
    ("limits", "card_daily_used", "number", "Card amount used today", 4000.0, lambda r: _num(_g(r.climit, "daily_used", 0))),
    ("limits", "card_daily_limit", "number", "Card daily limit", 100000.0, lambda r: _num(_g(r.climit, "daily_limit", 0))),
    ("limits", "card_daily_remaining", "number", "Card daily limit still available", 96000.0, lambda r: max(0.0, _num(_g(r.climit, "daily_limit", 0)) - _num(_g(r.climit, "daily_used", 0)))),
    ("limits", "card_weekly_used", "number", "Card amount used this week", 9000.0, lambda r: _num(_g(r.climit, "weekly_used", 0))),
    ("limits", "card_monthly_used", "number", "Card amount used this month", 30000.0, lambda r: _num(_g(r.climit, "monthly_used", 0))),
    ("limits", "card_per_tx_limit", "number", "Card per-transaction limit", 50000.0, lambda r: _num(_g(r.climit, "transaction_limit", 0))),
    ("limits", "account_daily_used", "number", "Account amount used today", 2500.0, lambda r: _num(_g(r.alimit, "daily_used", 0))),
    ("limits", "account_daily_limit", "number", "Account daily limit", 300000.0, lambda r: _num(_g(r.alimit, "daily_limit", 0))),
    ("limits", "account_per_tx_limit", "number", "Account per-transaction limit", 100000.0, lambda r: _num(_g(r.alimit, "per_transaction_limit", 0))),
]

TIME_PARAMS = [
    ("now", "Current UTC time"),
    ("since_1m", "UTC time 1 minute ago"),
    ("since_5m", "UTC time 5 minutes ago"),
    ("since_15m", "UTC time 15 minutes ago"),
    ("since_1h", "UTC time 1 hour ago"),
    ("since_24h", "UTC time 24 hours ago"),
    ("since_7d", "UTC time 7 days ago"),
    ("today_start", "UTC start of today (host local midnight converted to UTC)"),
]


class DotDict(dict):
    """dict with attribute access: tx.amount  (underscore attributes are not exposed)."""

    def __getattr__(self, item: str) -> Any:
        if item.startswith("_"):
            raise AttributeError(item)
        try:
            return self[item]
        except KeyError:
            raise AttributeError(f"no field '{item}'")


class TxContext:
    def __init__(self, data: Dict[str, DotDict], params: Dict[str, Any], raw: SimpleNamespace):
        self.data = data
        self.params = params
        self.raw = raw

    def public(self, mask_pan: bool = True) -> Dict[str, Any]:
        out = {g: dict(v) for g, v in self.data.items()}
        if mask_pan and "card" in out:
            out["card"]["pan"] = out["card"].get("masked_pan", "")
        return out


def build_context(
    db: Session,
    *,
    mti: str,
    fields: Dict[str, str],
    request_data: Optional[Dict[str, Any]],
    tx_code_cfg: Any,
    tx_amount: Any,
    card: Optional[Card],
    customer: Optional[Customer],
    account: Optional[Account],
    acq_inst: Optional[Institution],
    ps_code: Optional[str],
    tx_id: str = "",
    tx_ref: str = "",
    auth_profile_code: Optional[str] = None,
    auth_profile_name: Optional[str] = None,
    now: Optional[datetime] = None,
    issuer_inst: Optional[Institution] = None,
) -> TxContext:
    now_utc = now or datetime.now(timezone.utc)
    now_local = now_utc + timedelta(hours=HOST_UTC_OFFSET_HOURS)
    issuer = card.institution if (card is not None and getattr(card, "institution", None)) else issuer_inst

    f12 = str(fields.get("12", ""))
    hour = int(f12[:2]) if len(f12) >= 4 and f12[:2].isdigit() and int(f12[:2]) < 24 else now_local.hour
    minute = int(f12[2:4]) if len(f12) >= 4 and f12[2:4].isdigit() and int(f12[2:4]) < 60 else now_local.minute

    country = str(fields.get("19") or "050")
    bank_country = str(_g(issuer, "country_code", "050") or "050")
    is_foreign = country != bank_country
    is_on_us = bool(acq_inst is not None and issuer is not None and acq_inst.id == issuer.id)

    # Source: ON_US, otherwise the processing system code of the request
    source = "ON_US" if is_on_us else str(ps_code or "UNKNOWN")

    climit = alimit = pin_profile = card_profile = None
    if card is not None:
        climit = db.query(CardLimit).filter(CardLimit.card_id == card.id).first()
        card_profile = getattr(card, "card_profile", None)
        try:
            from app.models import PinProfile

            pin_profile = db.query(PinProfile).filter(PinProfile.card_id == card.id).first()
        except Exception:
            pin_profile = None
    if account is not None:
        alimit = db.query(AccountLimit).filter(AccountLimit.account_id == account.id).first()

    card_expired = False
    days_to_expiry = 0
    if card is not None and card.expiry_year and card.expiry_month:
        y, m = int(card.expiry_year), int(card.expiry_month)
        nxt = datetime(y + (1 if m == 12 else 0), 1 if m == 12 else m + 1, 1, tzinfo=timezone.utc)
        days_to_expiry = (nxt - now_utc).days
        card_expired = (y, m) < (now_utc.year, now_utc.month)

    r = SimpleNamespace(
        fields=fields, req=request_data or {}, tx_cfg=tx_code_cfg, amount=Decimal(str(tx_amount)), mti=mti,
        card=card, cust=customer, acct=account, issuer=issuer, acq=acq_inst, ps_code=ps_code,
        tx_id=tx_id, tx_ref=tx_ref, now_utc=now_utc, now_local=now_local, hour=hour, minute=minute,
        weekday=now_local.weekday(), channel=derive_channel(fields, request_data or {}), source=source,
        is_on_us=is_on_us, is_foreign=is_foreign, country=country, card_expired=card_expired,
        days_to_expiry=days_to_expiry, climit=climit, alimit=alimit, pin_profile=pin_profile,
        card_profile=card_profile, auth_code=auth_profile_code, auth_name=auth_profile_name,
    )

    data: Dict[str, DotDict] = {}
    params: Dict[str, Any] = {}
    for group, key, _t, _d, _e, getter in FIELD_SPEC:
        try:
            value = getter(r)
        except Exception:  # never let a missing optional value break the host
            value = "" if _t == "text" else (False if _t == "bool" else 0)
        data.setdefault(group, DotDict())[key] = value
        params[f"{group}_{key}"] = value

    today_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    naive_utc = now_utc.replace(tzinfo=None)
    params.update(
        {
            "now": naive_utc,
            "since_1m": naive_utc - timedelta(minutes=1),
            "since_5m": naive_utc - timedelta(minutes=5),
            "since_15m": naive_utc - timedelta(minutes=15),
            "since_1h": naive_utc - timedelta(hours=1),
            "since_24h": naive_utc - timedelta(hours=24),
            "since_7d": naive_utc - timedelta(days=7),
            "today_start": (today_local - timedelta(hours=HOST_UTC_OFFSET_HOURS)).replace(tzinfo=None),
        }
    )
    return TxContext(data, params, r)


# ============================================================================
# Policy engine
# ============================================================================
def _window_minutes(window: Any) -> float:
    if isinstance(window, (int, float)):
        return float(window)
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([smhdSMHD]?)\s*", str(window))
    if not m:
        raise ValueError(f"bad window '{window}' (use 30s, 5m, 1h, 24h, 7d)")
    n, unit = float(m.group(1)), (m.group(2) or "m").lower()
    return n * {"s": 1 / 60, "m": 1, "h": 60, "d": 1440}[unit]


class History:
    """Transaction history helper (python algos: history.count(...)). Excludes the current transaction."""

    WHO = {"card": "card_id", "customer": "customer_id", "account": "account_id"}
    DISTINCT = {"terminal": "terminal_id", "merchant": "merchant_id", "mcc": "mcc", "acquirer": "acquirer_id"}

    def __init__(self, db: Session, ctx: TxContext):
        self._db = db
        self._ctx = ctx

    def _query(self, window: Any, who: str, status: Optional[str], tx_code: Optional[str],
               min_amount: Optional[float], response_code: Optional[str]):
        raw = self._ctx.raw
        since = raw.now_utc - timedelta(minutes=_window_minutes(window))
        q = self._db.query(Transaction).filter(Transaction.transaction_datetime >= since)
        who = (who or "card").lower()
        if who in self.WHO:
            value = {"card": _g(raw.card, "id", None), "customer": _g(raw.cust, "id", None), "account": _g(raw.acct, "id", None)}[who]
            if not value:
                return q.filter(Transaction.id == "__none__")
            q = q.filter(getattr(Transaction, self.WHO[who]) == value)
        elif who == "terminal":
            q = q.filter(Transaction.terminal_id == self._ctx.data["terminal"]["id"])
        elif who == "bank":
            q = q.filter(Transaction.issuer_institution_id == _g(raw.issuer, "id", None))
        elif who != "all":
            raise ValueError("who must be card, customer, account, terminal, bank or all")
        if status:
            q = q.filter(Transaction.authorization_status == str(status).upper())
        if tx_code:
            q = q.filter(Transaction.transaction_code == str(tx_code))
        if response_code:
            q = q.filter(Transaction.response_code == str(response_code))
        if min_amount is not None:
            q = q.filter(Transaction.transaction_amount >= Decimal(str(min_amount)))
        return q

    def count(self, window: Any = "1h", who: str = "card", status: Optional[str] = None,
              tx_code: Optional[str] = None, min_amount: Optional[float] = None,
              response_code: Optional[str] = None) -> int:
        return int(self._query(window, who, status, tx_code, min_amount, response_code).count())

    def declines(self, window: Any = "1h", who: str = "card") -> int:
        return self.count(window, who, status="DECLINED")

    def approved(self, window: Any = "1h", who: str = "card") -> int:
        return self.count(window, who, status="APPROVED")

    def sum_amount(self, window: Any = "24h", who: str = "card", status: Optional[str] = "APPROVED",
                   tx_code: Optional[str] = None) -> float:
        rows = self._query(window, who, status, tx_code, None, None).limit(1000).all()
        return float(sum((t.transaction_amount or 0) for t in rows))

    def distinct(self, field: str = "terminal", window: Any = "24h", who: str = "card") -> int:
        col = self.DISTINCT.get(field)
        if not col:
            raise ValueError("field must be terminal, merchant, mcc or acquirer")
        rows = self._query(window, who, None, None, None, None).limit(1000).all()
        return len({getattr(t, col) for t in rows if getattr(t, col)})

    def last(self, n: int = 5, who: str = "card", window: Any = "7d") -> List[Dict[str, Any]]:
        n = max(1, min(int(n), 50))
        rows = self._query(window, who, None, None, None, None).order_by(Transaction.transaction_datetime.desc()).limit(n).all()
        return [
            {
                "amount": float(t.transaction_amount or 0),
                "response_code": t.response_code,
                "status": t.authorization_status,
                "terminal": t.terminal_id,
                "mcc": t.mcc,
                "tran_code": t.transaction_code,
                "time": t.transaction_datetime.isoformat() if t.transaction_datetime else None,
            }
            for t in rows
        ]


class PolicyResult:
    def __init__(self) -> None:
        self.allowed = True
        self.response_code = "00"
        self.message = ""
        self.checks: List[Dict[str, Any]] = []
        self.scope = "DEFAULT"
        self.failed_control: Optional[str] = None

    def add(self, name: str, status: str, rc: str, message: str) -> None:
        self.checks.append({"name": name, "status": status, "rc": rc, "message": message})

    def fail(self, control: str, rc: str, message: str) -> "PolicyResult":
        self.allowed = False
        self.response_code = rc
        self.message = message
        self.failed_control = control
        self.add(f"Local Host: {control}", "FAILED", rc, message)
        return self


def _norm_ccy(v: str) -> str:
    v = str(v or "").strip().upper()
    return "BDT" if v in ("050", "BDT") else v


def _hhmm(v: str) -> int:
    try:
        h, m = str(v).split(":")[:2]
        return int(h) * 60 + int(m)
    except Exception:
        return 0


# ============================================================================
# Python sandbox
# ============================================================================
class _AlgoStop(BaseException):
    """Raised by approve()/decline()/block_*() to end the script (BaseException: scripts cannot swallow it)."""


class _AlgoTimeout(BaseException):
    pass


_FORBIDDEN_NAMES = {
    "eval", "exec", "compile", "open", "__import__", "globals", "locals", "vars", "dir", "getattr", "setattr",
    "delattr", "input", "breakpoint", "type", "object", "super", "memoryview", "bytearray", "bytes", "property",
    "classmethod", "staticmethod", "help", "exit", "quit", "id", "hash", "iter", "next", "callable", "format",
    "print", "os", "sys", "subprocess", "importlib", "builtins",
}
_BLOCKED_ATTRS = {"format", "format_map", "mro", "load_module", "system", "popen"}
_BLOCKED_ATTR_PREFIXES = ("gi_", "cr_", "ag_", "f_", "tb_", "co_", "func_")

_ALLOWED_NODES: Tuple[type, ...] = (
    ast.Module, ast.Expr, ast.Assign, ast.AugAssign, ast.AnnAssign, ast.If, ast.For, ast.Break, ast.Continue,
    ast.Pass, ast.Return, ast.FunctionDef, ast.arguments, ast.arg, ast.Lambda, ast.Try, ast.ExceptHandler,
    ast.BoolOp, ast.BinOp, ast.UnaryOp, ast.Compare, ast.IfExp, ast.Call, ast.keyword, ast.Attribute,
    ast.Subscript, ast.Slice, ast.List, ast.Tuple, ast.Dict, ast.Set, ast.ListComp, ast.SetComp, ast.DictComp,
    ast.GeneratorExp, ast.comprehension, ast.Name, ast.Constant, ast.JoinedStr, ast.FormattedValue, ast.Starred,
    ast.Load, ast.Store, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.And, ast.Or, ast.Not,
    ast.USub, ast.UAdd, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn, ast.Is, ast.IsNot,
)

MAX_RANGE = 2000
MAX_SEQ = 10000
MAX_EVENTS = 300_000
DEFAULT_TIMEOUT_MS = 400


def _safe_range(*args: int) -> range:
    r = range(*args)
    if len(r) > MAX_RANGE:
        raise ValueError(f"range() is limited to {MAX_RANGE} items inside an algo")
    return r


def _safe_mul(a: Any, b: Any) -> Any:
    for x, y in ((a, b), (b, a)):
        if isinstance(x, (str, list, tuple)) and isinstance(y, int) and len(x) * max(y, 0) > MAX_SEQ:
            raise ValueError("sequence repetition is too large")
    return a * b


SAFE_BUILTINS: Dict[str, Any] = {
    "abs": abs, "all": all, "any": any, "bool": bool, "dict": dict, "divmod": divmod, "enumerate": enumerate,
    "float": float, "int": int, "len": len, "list": list, "max": max, "min": min, "range": _safe_range,
    "reversed": reversed, "round": round, "set": set, "sorted": sorted, "str": str, "sum": sum, "tuple": tuple,
    "zip": zip, "isinstance": isinstance, "True": True, "False": False, "None": None,
    "Exception": Exception, "ValueError": ValueError, "KeyError": KeyError, "TypeError": TypeError,
    "ZeroDivisionError": ZeroDivisionError, "AttributeError": AttributeError, "IndexError": IndexError,
}


def validate_python(code: str) -> Tuple[List[str], Optional[ast.Module]]:
    errors: List[str] = []
    if not (code or "").strip():
        return ["The algo code is empty"], None
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        return [f"Syntax error on line {exc.lineno}: {exc.msg}"], None
    for node in ast.walk(tree):
        line = getattr(node, "lineno", "?")
        if not isinstance(node, _ALLOWED_NODES):
            errors.append(f"line {line}: '{type(node).__name__}' is not allowed in an algo")
            continue
        if isinstance(node, ast.Name):
            if node.id in _FORBIDDEN_NAMES or node.id.startswith("__"):
                errors.append(f"line {line}: name '{node.id}' is not allowed")
        elif isinstance(node, ast.Attribute):
            a = node.attr
            if a.startswith("_") or a in _BLOCKED_ATTRS or a.startswith(_BLOCKED_ATTR_PREFIXES):
                errors.append(f"line {line}: attribute '{a}' is not allowed")
        elif isinstance(node, ast.ExceptHandler):
            if node.type is None:
                errors.append(f"line {line}: use 'except Exception:' instead of a bare 'except:'")
        elif isinstance(node, ast.FunctionDef):
            if node.decorator_list:
                errors.append(f"line {line}: decorators are not allowed")
        elif isinstance(node, ast.AugAssign):
            if isinstance(node.op, ast.Mult) and not isinstance(node.target, ast.Name):
                errors.append(f"line {line}: write 'x = x * y' instead of '*=' on this target")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in _FORBIDDEN_NAMES:
                errors.append(f"line {line}: '{node.func.id}()' is not allowed")
    return errors, tree


class _Guard(ast.NodeTransformer):
    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        self.generic_visit(node)
        if isinstance(node.op, ast.Mult):
            return ast.copy_location(
                ast.Call(func=ast.Name(id="_safe_mul", ctx=ast.Load()), args=[node.left, node.right], keywords=[]), node
            )
        return node

    def visit_AugAssign(self, node: ast.AugAssign) -> ast.AST:
        self.generic_visit(node)
        if isinstance(node.op, ast.Mult) and isinstance(node.target, ast.Name):
            call = ast.Call(
                func=ast.Name(id="_safe_mul", ctx=ast.Load()),
                args=[ast.Name(id=node.target.id, ctx=ast.Load()), node.value],
                keywords=[],
            )
            return ast.copy_location(
                ast.Assign(targets=[ast.Name(id=node.target.id, ctx=ast.Store())], value=call), node
            )
        return node


_COMPILED: Dict[str, Any] = {}


def _compile_python(code: str) -> Any:
    key = hashlib.sha1(code.encode("utf-8")).hexdigest()
    cached = _COMPILED.get(key)
    if cached is not None:
        return cached
    errors, tree = validate_python(code)
    if errors or tree is None:
        raise ValueError("; ".join(errors))
    tree = _Guard().visit(tree)
    body = list(tree.body) or [ast.Pass()]
    if isinstance(body[-1], ast.Expr):  # a final expression is the result:  tx.amount > 5000
        body[-1] = ast.copy_location(ast.Return(value=body[-1].value), body[-1])
    kwargs: Dict[str, Any] = {}
    if sys.version_info >= (3, 12):
        kwargs["type_params"] = []
    func = ast.FunctionDef(
        name="__algo__",
        args=ast.arguments(posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[], defaults=[]),
        body=body, decorator_list=[], returns=None, type_comment=None, **kwargs,
    )
    module = ast.Module(body=[func], type_ignores=[])
    ast.fix_missing_locations(module)
    compiled = compile(module, "<algo>", "exec")
    if len(_COMPILED) > 300:
        _COMPILED.clear()
    _COMPILED[key] = compiled
    return compiled


_RC_RE = re.compile(r"^[0-9A-Za-z]{2}$")


class Recorder:
    def __init__(self) -> None:
        self.stop: Optional[Dict[str, Any]] = None
        self.flags: List[str] = []
        self.logs: List[str] = []

    @staticmethod
    def _split(a: Any, b: Any) -> Tuple[Optional[str], Optional[str]]:
        if a is not None and _RC_RE.match(str(a)) and not (b is None and len(str(a)) != 2):
            return str(a), (None if b is None else str(b))
        return (None if b is None else str(b)), (None if a is None else str(a))

    def approve(self, message: Optional[str] = None) -> None:
        self.stop = {"action": "APPROVE", "rc": "00", "message": message}
        raise _AlgoStop()

    def decline(self, rc: Optional[str] = None, message: Optional[str] = None) -> None:
        r, m = self._split(rc, message)
        self.stop = {"action": "DECLINE", "rc": r, "message": m}
        raise _AlgoStop()

    def block_card(self, message: Optional[str] = None, rc: Optional[str] = None) -> None:
        r, m = self._split(rc, message) if (rc is not None and _RC_RE.match(str(rc))) else (rc, message)
        self.stop = {"action": "BLOCK_CARD", "rc": r, "message": m}
        raise _AlgoStop()

    def block_customer(self, message: Optional[str] = None, rc: Optional[str] = None) -> None:
        r, m = self._split(rc, message) if (rc is not None and _RC_RE.match(str(rc))) else (rc, message)
        self.stop = {"action": "BLOCK_CUSTOMER", "rc": r, "message": m}
        raise _AlgoStop()

    def flag(self, message: Optional[str] = None) -> None:
        self.flags.append(str(message or "flagged"))

    def log(self, *args: Any) -> None:
        if len(self.logs) < 50:
            self.logs.append(" ".join(str(a) for a in args)[:300])


def _jsonable(v: Any) -> Any:
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, set)):
        return [_jsonable(x) for x in v]
    return v


# ============================================================================
# SQL algos
# ============================================================================
_SQL_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|attach|detach|pragma|vacuum|grant|revoke|commit|"
    r"rollback|savepoint|release|load_extension|copy|call|exec|execute|merge|into|pg_sleep|dblink|lo_import|lo_export)\b",
    re.IGNORECASE,
)


def _strip_sql(code: str) -> str:
    s = re.sub(r"--[^\n]*", " ", code)
    s = re.sub(r"/\*.*?\*/", " ", s, flags=re.S)
    s = re.sub(r"'(?:[^']|'')*'", "''", s)
    s = re.sub(r'"(?:[^"]|"")*"', '""', s)
    return s


def known_param_names() -> List[str]:
    return [f"{g}_{k}" for g, k, *_ in FIELD_SPEC] + [n for n, _ in TIME_PARAMS]


def validate_sql(code: str) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []
    if not (code or "").strip():
        return ["The SQL is empty"], warnings
    s = _strip_sql(code).strip().rstrip(";").strip()
    if ";" in s:
        errors.append("Only one SQL statement is allowed")
    if not re.match(r"^(select|with)\b", s, re.IGNORECASE):
        errors.append("The SQL must start with SELECT (or WITH ... SELECT)")
    bad = _SQL_FORBIDDEN.search(s)
    if bad:
        errors.append(f"'{bad.group(1).upper()}' is not allowed: algo SQL is read-only")
    names = set(re.findall(r"(?<!:):([A-Za-z_]\w*)", s))
    unknown = sorted(n for n in names if n not in set(known_param_names()))
    if unknown:
        errors.append("Unknown parameter(s): " + ", ".join(":" + n for n in unknown) + "  (open Fields Reference)")
    return errors, warnings


def run_sql(db: Session, code: str, params: Dict[str, Any], limit: int = 50) -> List[Dict[str, Any]]:
    errors, _ = validate_sql(code)
    if errors:
        raise ValueError("; ".join(errors))
    s = _strip_sql(code)
    names = set(re.findall(r"(?<!:):([A-Za-z_]\w*)", s))
    bind = {k: params[k] for k in names if k in params}
    result = db.execute(text(code.strip().rstrip(";")), bind)
    return [{k: _jsonable(v) for k, v in dict(row).items()} for row in result.mappings().fetchmany(limit)]


# ============================================================================
# Algo execution
# ============================================================================
class ExecResult:
    def __init__(self) -> None:
        self.matched = False
        self.action: Optional[str] = None
        self.rc: Optional[str] = None
        self.message: Optional[str] = None
        self.explicit = False
        self.logs: List[str] = []
        self.error: Optional[str] = None
        self.duration_ms = 0
        self.value: Any = None
        self.rows: Optional[List[Dict[str, Any]]] = None


def run_python_algo(db: Session, code: str, ctx: TxContext, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> ExecResult:
    res = ExecResult()
    t0 = time.perf_counter()
    rec = Recorder()
    try:
        compiled = _compile_python(code)

        def sql_fn(query: str, **extra: Any) -> List[Dict[str, Any]]:
            return run_sql(db, query, {**ctx.params, **extra}, limit=200)

        env: Dict[str, Any] = {"__builtins__": SAFE_BUILTINS, "_safe_mul": _safe_mul}
        env.update(ctx.data)
        env.update(
            history=History(db, ctx), sql=sql_fn, approve=rec.approve, decline=rec.decline,
            block_card=rec.block_card, block_customer=rec.block_customer, flag=rec.flag, log=rec.log,
            now=lambda: ctx.raw.now_local,
        )
        exec(compiled, env)  # defines __algo__ (no user code runs here)
        fn = env["__algo__"]

        deadline = t0 + timeout_ms / 1000.0
        counter = [0]

        def tracer(frame: Any, event: str, arg: Any) -> Optional[Callable]:
            if frame.f_code.co_filename != "<algo>":
                return None
            counter[0] += 1
            if counter[0] > MAX_EVENTS or time.perf_counter() > deadline:
                raise _AlgoTimeout()
            return tracer

        previous = sys.gettrace()
        sys.settrace(tracer)
        try:
            res.value = fn()
        finally:
            sys.settrace(previous)
    except _AlgoStop:
        pass
    except _AlgoTimeout:
        res.error = f"Algo exceeded its time/instruction budget ({timeout_ms} ms)"
    except Exception as exc:  # script bug: reported, never crashes the host
        res.error = f"{type(exc).__name__}: {exc}"
    res.logs = rec.logs
    if rec.stop:
        res.matched, res.explicit = True, True
        res.action, res.rc, res.message = rec.stop["action"], rec.stop["rc"], rec.stop["message"]
    elif rec.flags:
        res.matched, res.explicit = True, True
        res.action, res.message = "FLAG", " | ".join(rec.flags)[:300]
    elif not res.error and res.value:
        res.matched = True  # truthy return -> the algo's default action
    res.duration_ms = int((time.perf_counter() - t0) * 1000)
    return res


def run_sql_algo(db: Session, code: str, ctx: TxContext) -> ExecResult:
    res = ExecResult()
    t0 = time.perf_counter()
    try:
        rows = run_sql(db, code, ctx.params)
        res.rows = rows
        if rows:
            first = rows[0]
            keys = {k.lower(): k for k in first.keys()}
            act = first.get(keys["action"]) if "action" in keys else first.get(keys["decision"]) if "decision" in keys else None
            if act is not None:
                a = str(act).upper().strip()
                if a in ALGO_ACTIONS:
                    res.matched, res.explicit, res.action = True, True, a
                elif a in ("NONE", "PASS", ""):
                    res.matched = False
                else:
                    res.error = f"Unknown action '{act}' returned by the SQL (use {', '.join(ALGO_ACTIONS)} or NONE)"
                rc_key = keys.get("response_code") or keys.get("rc")
                if rc_key and first.get(rc_key) not in (None, ""):
                    res.rc = str(first[rc_key])
                if "message" in keys and first.get(keys["message"]) not in (None, ""):
                    res.message = str(first[keys["message"]])[:300]
            else:
                value = next(iter(first.values()))
                res.matched = bool(value) and str(value).strip() not in ("0", "False", "false")
    except Exception as exc:
        res.error = f"{type(exc).__name__}: {exc}"
    res.duration_ms = int((time.perf_counter() - t0) * 1000)
    return res


class AlgoOutcome:
    def __init__(self) -> None:
        self.decline: Optional[Dict[str, Any]] = None
        self.checks: List[Dict[str, Any]] = []
        self.results: List[Dict[str, Any]] = []
        self.approved_by: Optional[str] = None

    def add(self, name: str, status: str, rc: str, message: str) -> None:
        self.checks.append({"name": name, "status": status, "rc": rc, "message": message})


def _compact_context(ctx: TxContext) -> Dict[str, Any]:
    d = ctx.data
    return {
        "amount": d["tx"]["amount"], "channel": d["tx"]["channel"], "source": d["tx"]["source"],
        "tran_code": d["tx"]["tran_code"], "hour": d["tx"]["hour"], "mcc": d["terminal"]["mcc"],
        "country": d["tx"]["country"], "terminal": d["terminal"]["id"], "card": d["card"]["masked_pan"],
        "customer": d["customer"]["number"], "bank": d["bank"]["code"], "balance": d["account"]["balance"],
    }


class LocalHostEngine:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ policy
    def evaluate_policy(self, ctx: TxContext) -> PolicyResult:
        res = PolicyResult()
        d = ctx.data
        tx, term = d["tx"], d["terminal"]
        issuer_id = _g(ctx.raw.issuer, "id", None)
        eff = effective_policy(self.db, issuer_id)
        cfg = eff["config"]
        res.scope = "BANK" if eff["bank_id"] else ("GLOBAL" if eff["global_id"] else "DEFAULT")
        gen = cfg["general"]
        default_rc = gen.get("decline_response_code", "57")
        amount = float(tx["amount"])
        financial = bool(tx["is_financial"]) and amount > 0
        evaluated = 0

        # 1. host status
        status = gen.get("host_status", "ACTIVE")
        if status in ("MAINTENANCE", "DECLINE_ALL"):
            return res.fail("Host Status", gen.get("status_response_code", "91"),
                            f"{gen.get('status_message') or 'Host is not available'} (status {status})")
        evaluated += 1

        # 2. business hours
        bh = gen.get("business_hours") or {}
        if bh.get("enabled"):
            now_m = int(tx["hour"]) * 60 + int(tx["minute"])
            s, e = _hhmm(bh.get("start", "00:00")), _hhmm(bh.get("end", "23:59"))
            inside = (s <= now_m <= e) if s <= e else (now_m >= s or now_m <= e)
            if not inside:
                return res.fail("Business Hours", default_rc, f"{tx['time']} is outside {bh.get('start')}-{bh.get('end')}")
            res.add("Local Host: Business Hours", "PASSED", "00", f"{tx['time']} inside {bh.get('start')}-{bh.get('end')}")
            evaluated += 1

        # 3. source / external system control
        src_cfg = cfg["sources"].get(str(tx["source"]).upper()) or cfg["sources"].get("UNKNOWN")
        if src_cfg is not None:
            if not src_cfg.get("enabled", True):
                return res.fail("Source Control", default_rc, f"Transactions from source {tx['source']} are disabled")
            allowed = [str(x) for x in src_cfg.get("allowed_tx_codes") or []]
            if allowed and str(tx["tran_code"]) not in allowed:
                return res.fail("Source Control", default_rc, f"Transaction code {tx['tran_code']} is not allowed from {tx['source']}")
            mx = float(src_cfg.get("max_amount") or 0)
            if financial and mx and amount > mx:
                return res.fail("Source Control", "61", f"Amount {amount:,.2f} exceeds the {tx['source']} maximum {mx:,.2f}")
            res.add("Local Host: Source Control", "PASSED", "00", f"Source {tx['source']} permitted")
            evaluated += 1

        # 4. channel control
        ch_cfg = cfg["channels"].get(str(tx["channel"]).upper())
        if ch_cfg is not None:
            if not ch_cfg.get("enabled", True):
                return res.fail("Channel Control", default_rc, f"Channel {tx['channel']} is disabled")
            mn, mx = float(ch_cfg.get("min_amount") or 0), float(ch_cfg.get("max_amount") or 0)
            if financial and mn and amount < mn:
                return res.fail("Channel Control", "13", f"Amount {amount:,.2f} is below the {tx['channel']} minimum {mn:,.2f}")
            if financial and mx and amount > mx:
                return res.fail("Channel Control", "61", f"Amount {amount:,.2f} exceeds the {tx['channel']} maximum {mx:,.2f}")
            res.add("Local Host: Channel Control", "PASSED", "00", f"Channel {tx['channel']} permitted")
            evaluated += 1

        # 5. transaction matrix
        t_cfg = cfg["transactions"].get(str(tx["tran_code"]))
        if t_cfg is not None:
            if not t_cfg.get("enabled", True):
                return res.fail("Transaction Matrix", default_rc, f"Transaction code {tx['tran_code']} is disabled by the host")
            chans = [c.upper() for c in t_cfg.get("channels") or []]
            if chans and str(tx["channel"]).upper() not in chans:
                return res.fail("Transaction Matrix", default_rc, f"Transaction {tx['tran_code']} is not allowed on channel {tx['channel']}")
            mn, mx = float(t_cfg.get("min_amount") or 0), float(t_cfg.get("max_amount") or 0)
            if financial and mn and amount < mn:
                return res.fail("Transaction Matrix", "13", f"Amount {amount:,.2f} is below the minimum {mn:,.2f} for code {tx['tran_code']}")
            if financial and mx and amount > mx:
                return res.fail("Transaction Matrix", "61", f"Amount {amount:,.2f} exceeds the maximum {mx:,.2f} for code {tx['tran_code']}")
            res.add("Local Host: Transaction Matrix", "PASSED", "00", f"Code {tx['tran_code']} permitted on {tx['channel']}")
            evaluated += 1

        # 6. general amount and currency
        if financial:
            mn, mx = float(gen.get("min_amount") or 0), float(gen.get("max_amount") or 0)
            if mn and amount < mn:
                return res.fail("Amount Control", "13", f"Amount {amount:,.2f} is below the host minimum {mn:,.2f}")
            if mx and amount > mx:
                return res.fail("Amount Control", "61", f"Amount {amount:,.2f} exceeds the host maximum {mx:,.2f}")
            evaluated += 1
        ccys = [_norm_ccy(c) for c in gen.get("allowed_currencies") or []]
        if ccys:
            if _norm_ccy(tx["currency"]) not in ccys:
                return res.fail("Currency Control", default_rc, f"Currency {tx['currency']} is not allowed")
            res.add("Local Host: Currency Control", "PASSED", "00", f"Currency {tx['currency']} allowed")
            evaluated += 1

        # 7. cross border
        cb = cfg["cross_border"]
        blocked_c = [str(c) for c in cb.get("blocked_countries") or []]
        allowed_c = [str(c) for c in cb.get("allowed_countries") or []]
        if tx["is_foreign"] and not cb.get("enabled", True):
            return res.fail("Cross-border", cb.get("response_code", "57"), f"Foreign transactions are disabled (country {tx['country']})")
        if str(tx["country"]) in blocked_c:
            return res.fail("Cross-border", cb.get("response_code", "57"), f"Country {tx['country']} is blocked")
        if allowed_c and tx["is_foreign"] and str(tx["country"]) not in allowed_c:
            return res.fail("Cross-border", cb.get("response_code", "57"), f"Country {tx['country']} is not in the allowed list")
        if tx["is_foreign"] or blocked_c or allowed_c:
            res.add("Local Host: Cross-border", "PASSED", "00", f"Country {tx['country']} permitted")
            evaluated += 1

        # 8. MCC
        mcc_cfg = cfg["mcc"]
        mcc = str(term["mcc"])
        if mcc and mcc in [str(x) for x in mcc_cfg.get("blocked") or []]:
            return res.fail("MCC Control", mcc_cfg.get("response_code", "57"), f"Merchant category {mcc} is blocked")
        allowed_m = [str(x) for x in mcc_cfg.get("allowed") or []]
        if allowed_m and mcc not in allowed_m:
            return res.fail("MCC Control", mcc_cfg.get("response_code", "57"), f"Merchant category {mcc} is not in the allowed list")
        if mcc_cfg.get("blocked") or allowed_m:
            res.add("Local Host: MCC Control", "PASSED", "00", f"MCC {mcc} permitted")
            evaluated += 1

        # 9. acquirer / terminal owner
        aq = cfg["acquirers"]
        ids = {str(term["acquirer_id"]), str(term["owner_code"]), str(d["acquirer"]["code"])} - {""}
        if ids & {str(x) for x in aq.get("blocked") or []}:
            return res.fail("Terminal Owner", aq.get("response_code", "58"), f"Terminal owner {term['owner_code'] or term['acquirer_id']} is blocked")
        allowed_a = {str(x) for x in aq.get("allowed") or []}
        if allowed_a and not (ids & allowed_a):
            return res.fail("Terminal Owner", aq.get("response_code", "58"), f"Terminal owner {term['owner_code'] or term['acquirer_id']} is not in the allowed list")
        if aq.get("blocked") or allowed_a:
            res.add("Local Host: Terminal Owner", "PASSED", "00", f"Terminal owner {term['owner_code'] or term['acquirer_id']} permitted")
            evaluated += 1

        # 10. velocity (per card)
        vel = cfg["velocity"]
        if vel.get("enabled") and _g(ctx.raw.card, "id", None):
            h = History(self.db, ctx)
            if vel.get("max_tx_per_minute") and h.count("1m", "card") >= int(vel["max_tx_per_minute"]):
                return res.fail("Velocity", vel.get("response_code", "65"), f"More than {vel['max_tx_per_minute']} transactions in 1 minute")
            if vel.get("max_tx_per_hour") and h.count("1h", "card") >= int(vel["max_tx_per_hour"]):
                return res.fail("Velocity", vel.get("response_code", "65"), f"More than {vel['max_tx_per_hour']} transactions in 1 hour")
            if vel.get("max_declines_per_day") and h.declines("24h", "card") >= int(vel["max_declines_per_day"]):
                return res.fail("Velocity", vel.get("response_code", "65"), f"{vel['max_declines_per_day']} or more declines in 24 hours")
            res.add("Local Host: Velocity", "PASSED", "00", "Within velocity controls")
            evaluated += 1

        res.add("Local Host Policy", "PASSED", "00", f"{evaluated} control(s) evaluated ({res.scope} policy)")
        return res

    # ------------------------------------------------------------------ algos
    def _candidates(self, stage: str, ctx: TxContext) -> List[HostAlgo]:
        q = (
            self.db.query(HostAlgo)
            .filter(HostAlgo.enabled == True, HostAlgo.stage == stage)  # noqa: E712
            .order_by(HostAlgo.priority.asc(), HostAlgo.created_at.asc())
        )
        issuer_id = _g(ctx.raw.issuer, "id", None)
        profile_id = _g(ctx.raw.card, "card_profile_id", None)
        tran_code, channel = str(ctx.data["tx"]["tran_code"]), str(ctx.data["tx"]["channel"]).upper()
        out: List[HostAlgo] = []
        for a in q.all():
            if a.scope_type == "BANK" and a.institution_id != issuer_id:
                continue
            if a.scope_type == "CARD_PROFILE" and a.card_profile_id != profile_id:
                continue
            if a.tx_codes_json and tran_code not in [str(x) for x in a.tx_codes_json]:
                continue
            if a.channels_json and channel not in [str(x).upper() for x in a.channels_json]:
                continue
            out.append(a)
        return out

    def execute(self, language: str, code: str, ctx: TxContext) -> ExecResult:
        if (language or "PYTHON").upper() == "SQL":
            return run_sql_algo(self.db, code, ctx)
        return run_python_algo(self.db, code, ctx)

    def _apply_block(self, kind: str, algo_code: str, ctx: TxContext, message: str) -> None:
        raw = ctx.raw
        if kind == "BLOCK_CARD" and raw.card is not None:
            before = raw.card.card_status
            raw.card.card_status = "BLOCKED"
            record_audit(self.db, "CARD", raw.card.id, "ALGO_BLOCK_CARD", performed_by=f"ALGO:{algo_code}",
                         change_summary=f"Card blocked by algo {algo_code} (was {before}): {message}")
        elif kind == "BLOCK_CUSTOMER" and raw.cust is not None:
            before = raw.cust.customer_status
            raw.cust.customer_status = "BLOCKED"
            record_audit(self.db, "CUSTOMER", raw.cust.id, "ALGO_BLOCK_CUSTOMER", performed_by=f"ALGO:{algo_code}",
                         change_summary=f"Customer blocked by algo {algo_code} (was {before}): {message}")

    def run_algos(self, stage: str, ctx: TxContext) -> AlgoOutcome:
        outcome = AlgoOutcome()
        for algo in self._candidates(stage, ctx):
            res = self.execute(algo.language, algo.code, ctx)
            self._finish_one(algo, res, ctx, outcome, simulate=False)
            if outcome.decline or (outcome.approved_by and algo.stop_on_match and res.matched and (res.action or algo.default_action) == "APPROVE"):
                break
        return outcome

    def _finish_one(self, algo: Any, res: ExecResult, ctx: TxContext, outcome: AlgoOutcome, simulate: bool) -> Dict[str, Any]:
        action = (res.action or algo.default_action) if res.matched else None
        rc = res.rc or algo.default_response_code
        message = res.message or algo.default_message
        label = f"Algo {algo.algo_code}"
        applied = False
        info = {
            "algo_code": algo.algo_code, "name": algo.name, "matched": res.matched, "action": action,
            "response_code": rc if res.matched else None, "message": message if res.matched else None,
            "error": res.error, "duration_ms": res.duration_ms, "logs": res.logs, "mode": algo.mode,
            "applied": False,
        }
        if res.error:
            if algo.on_error == "DECLINE" and algo.mode == "ENFORCE" and not simulate:
                outcome.decline = {"rc": algo.default_response_code, "message": f"Algo error: {res.error}"[:200], "algo": algo.algo_code}
                outcome.add(label, "FAILED", algo.default_response_code, f"Algo error (fail-closed): {res.error}"[:300])
                applied = True
            else:
                outcome.add(label, "SKIPPED", "00", f"Algo error ignored (fail-open): {res.error}"[:300])
        elif not res.matched:
            outcome.add(label, "PASSED", "00", "Condition not met")
        elif algo.mode == "MONITOR":
            outcome.add(label, "PASSED", "00", f"[MONITOR] would {action}: {message}")
        else:
            if action == "APPROVE":
                outcome.approved_by = algo.algo_code
                outcome.add(label, "PASSED", "00", f"APPROVE (algo allow): {message}")
                applied = True
            elif action == "FLAG":
                outcome.add(label, "PASSED", "00", f"FLAG: {message}")
                if not simulate:
                    record_system_log(self.db, "WARNING", "HostAlgo", "ALGO_FLAG", f"{algo.algo_code}: {message}",
                                      details={"algo": algo.algo_code})
                applied = True
            else:  # DECLINE / BLOCK_CARD / BLOCK_CUSTOMER
                outcome.decline = {"rc": rc, "message": message, "algo": algo.algo_code, "action": action}
                outcome.add(label, "FAILED", rc, f"{action}: {message}")
                if action in ("BLOCK_CARD", "BLOCK_CUSTOMER") and not simulate:
                    self._apply_block(action, algo.algo_code, ctx, message)
                applied = True
        info["applied"] = applied and not simulate
        outcome.results.append(info)

        if not simulate and getattr(algo, "id", None):
            now = datetime.now(timezone.utc)
            algo.eval_count = (algo.eval_count or 0) + 1
            algo.last_run_at = now
            if res.matched:
                algo.hit_count = (algo.hit_count or 0) + 1
                algo.last_hit_at = now
            if res.error:
                algo.error_count = (algo.error_count or 0) + 1
            if res.matched or res.error:
                self.db.add(HostAlgoLog(
                    algo_id=algo.id, algo_code=algo.algo_code, transaction_id=ctx.raw.tx_id or None,
                    transaction_reference=ctx.raw.tx_ref or None, masked_pan=ctx.data["card"]["masked_pan"],
                    stage=algo.stage, mode=algo.mode, matched=bool(res.matched), action=action,
                    action_applied=bool(info["applied"] and algo.mode == "ENFORCE"),
                    response_code=rc if res.matched else None, message=(message if res.matched else None),
                    error=res.error, duration_ms=res.duration_ms, context_json=_compact_context(ctx),
                ))
        return info

    # ------------------------------------------------------------------ test / draft runs (no side effects)
    def test_draft(self, draft: Dict[str, Any], ctx: TxContext) -> Dict[str, Any]:
        algo = SimpleNamespace(
            id=None, algo_code=str(draft.get("algo_code") or "DRAFT"), name=draft.get("name") or "Draft",
            language=(draft.get("language") or "PYTHON").upper(), code=draft.get("code") or "",
            mode=(draft.get("mode") or "ENFORCE").upper(), default_action=(draft.get("default_action") or "DECLINE").upper(),
            default_response_code=str(draft.get("default_response_code") or "57"),
            default_message=draft.get("default_message") or "Declined by risk algo",
            on_error=(draft.get("on_error") or "SKIP").upper(), stop_on_match=bool(draft.get("stop_on_match", True)),
            stage=draft.get("stage") or "PRE_AUTH",
        )
        res = self.execute(algo.language, algo.code, ctx)
        outcome = AlgoOutcome()
        info = self._finish_one(algo, res, ctx, outcome, simulate=True)
        info["rows"] = res.rows
        info["would_block_card"] = bool(res.matched and info["action"] == "BLOCK_CARD")
        info["would_block_customer"] = bool(res.matched and info["action"] == "BLOCK_CUSTOMER")
        return info


def build_test_context(db: Session, card: Optional[Card], overrides: Dict[str, Any],
                       issuer_inst: Optional[Institution] = None) -> TxContext:
    """Create a realistic context for the Test / Simulate panels from a card and a few overrides."""
    o = overrides or {}
    channel = str(o.get("channel") or "POS").upper()
    mcc = str(o.get("mcc") or ("6011" if channel == "ATM" else "5411"))
    hour = o.get("hour")
    now = datetime.now(timezone.utc)
    hh = int(hour) if hour not in (None, "") else (now + timedelta(hours=HOST_UTC_OFFSET_HOURS)).hour
    amount = Decimal(str(o.get("amount") or "1000"))
    tran_code = str(o.get("tran_code") or ("10" if channel == "ATM" else "00"))
    from app.models import TransactionCode

    tx_cfg = db.query(TransactionCode).filter(TransactionCode.transaction_code == tran_code).first()
    acq = None
    acq_key = str(o.get("acquirer_code") or "")
    issuer = card.institution if card is not None else issuer_inst
    if acq_key:
        acq = db.query(Institution).filter(Institution.institution_code == acq_key).first()
    if acq is None:
        acq = issuer
    fields = {
        "2": _g(card, "test_pan_reference", ""),
        "3": f"{int(tran_code):03d}0000" if tran_code.isdigit() else "0100000",
        "4": f"{int(amount * 100):012d}",
        "12": f"{hh:02d}0000",
        "18": mcc,
        "19": str(o.get("country") or "050"),
        "25": "08" if channel == "ECOM" else "00",
        "32": _g(acq, "acquirer_id", "123456"),
        "41": str(o.get("terminal_id") or ("ATM0001" if channel == "ATM" else "POS0001")),
        "49": str(o.get("currency") or "050"),
    }
    customer = card.customer if card is not None else None
    account = None
    if card is not None:
        link = next(iter(sorted(card.card_accounts or [], key=lambda x: x.priority or 99)), None)
        account = link.account if link is not None and link.account is not None else (
            db.query(Account).filter(Account.id == card.linked_account_id).first() if card.linked_account_id else None
        )
    ps_code = o.get("source") if o.get("source") and o.get("source") != "ON_US" else (
        acq.primary_processing_system.ps_code if (acq is not None and acq.primary_processing_system) else "ITCL"
    )
    return build_context(
        db, mti="0200", fields=fields, request_data={"source_channel": channel}, tx_code_cfg=tx_cfg,
        tx_amount=amount, card=card, customer=customer, account=account, acq_inst=acq, ps_code=ps_code,
        tx_id="TEST", tx_ref="TEST", issuer_inst=issuer_inst,
    )


# ============================================================================
# Field catalog, templates, SQL schema (served to the UI "Fields Reference" button)
# ============================================================================
GROUP_TITLES = {
    "tx": ("Transaction", "tx.amount  ·  SQL :tx_amount"),
    "terminal": ("Terminal / Acquirer", "terminal.owner  ·  SQL :terminal_owner"),
    "card": ("Card", "card.status  ·  SQL :card_status"),
    "customer": ("Customer", "customer.risk  ·  SQL :customer_risk"),
    "account": ("Account", "account.balance  ·  SQL :account_balance"),
    "bank": ("Issuer Bank", "bank.code  ·  SQL :bank_code"),
    "acquirer": ("Acquirer Bank", "acquirer.code  ·  SQL :acquirer_code"),
    "profile": ("Profiles", "profile.auth_name  ·  SQL :profile_auth_name"),
    "limits": ("Limit usage", "limits.card_daily_used  ·  SQL :limits_card_daily_used"),
}


def field_catalog() -> Dict[str, Any]:
    groups: Dict[str, Dict[str, Any]] = {}
    for group, key, typ, desc, example, _g_ in FIELD_SPEC:
        title, hint = GROUP_TITLES.get(group, (group.title(), ""))
        g = groups.setdefault(group, {"group": group, "title": title, "hint": hint, "fields": []})
        g["fields"].append({"key": key, "python": f"{group}.{key}", "sql": f":{group}_{key}", "type": typ,
                            "description": desc, "example": example})
    return {
        "groups": list(groups.values()),
        "time_params": [{"sql": f":{n}", "description": d} for n, d in TIME_PARAMS],
        "actions": [
            {"name": "approve(message)", "description": "Allow-list: accept at the risk layer and stop the remaining algos. PIN, HSM, limit and balance checks still run."},
            {"name": "decline(rc, message)", "description": "Decline with a response code, e.g. decline('57', 'Night time')."},
            {"name": "block_card(message, rc)", "description": "Set the card status to BLOCKED and decline (default RC 62)."},
            {"name": "block_customer(message, rc)", "description": "Set the customer status to BLOCKED and decline (default RC 62)."},
            {"name": "flag(message)", "description": "Record a warning for follow up and let the transaction continue."},
            {"name": "log(text)", "description": "Write a line to the test output / algo log."},
            {"name": "return True", "description": "Apply the algo's default action (set in the form). A last-line expression such as  tx.amount > 5000  does the same."},
        ],
        "history": [
            {"name": "history.count(window='1h', who='card', status=None, tx_code=None, min_amount=None, response_code=None)", "description": "Number of earlier transactions. window: 30s, 5m, 1h, 24h, 7d. who: card, customer, account, terminal, bank, all. status: APPROVED / DECLINED."},
            {"name": "history.declines(window='1h', who='card')", "description": "Number of earlier declined transactions."},
            {"name": "history.approved(window='1h', who='card')", "description": "Number of earlier approved transactions."},
            {"name": "history.sum_amount(window='24h', who='card', status='APPROVED', tx_code=None)", "description": "Total amount of earlier transactions."},
            {"name": "history.distinct(field='terminal', window='24h', who='card')", "description": "Number of different terminals / merchants / mcc / acquirer used."},
            {"name": "history.last(n=5, who='card')", "description": "List of the last n transactions (amount, response_code, status, terminal, mcc, time)."},
            {"name": "sql('SELECT ... WHERE card_id = :card_id', **extra)", "description": "Run a read-only SELECT from Python and get a list of rows (max 200)."},
            {"name": "now()", "description": "Host local date and time (UTC+6 by default)."},
        ],
        "notes": [
            "History counts exclude the transaction that is being authorized right now.",
            "Python: no imports, no while loops, no file or network access. range() is limited to 2000 items.",
            "SQL: one read-only SELECT. If it returns a row whose first column is truthy, the algo matches. "
            "Return columns action / response_code / message to control the outcome from SQL.",
            "Stage PRE_AUTH runs before PIN/HSM checks. Stage POST_AUTH runs after balance and limit checks, just before posting.",
        ],
    }


ALGO_TEMPLATES: List[Dict[str, Any]] = [
    {
        "key": "night_atm", "title": "Night-time high value ATM", "language": "PYTHON",
        "description": "Decline ATM cash above 20,000 between 23:00 and 05:00.",
        "default_action": "DECLINE", "default_response_code": "57", "default_message": "High value ATM cash at night",
        "code": "# Decline big ATM withdrawals at night\nif tx.channel == 'ATM' and tx.amount > 20000 and (tx.hour >= 23 or tx.hour < 5):\n    decline('57', 'High value ATM cash at night')\n",
    },
    {
        "key": "velocity_2m", "title": "Velocity: 5 transactions in 2 minutes", "language": "PYTHON",
        "description": "Decline when the card already made 5 or more transactions in the last 2 minutes.",
        "default_action": "DECLINE", "default_response_code": "65", "default_message": "Too many transactions",
        "code": "# history excludes the current transaction\nif history.count('2m', 'card') >= 5:\n    decline('65', 'More than 5 transactions in 2 minutes')\n",
    },
    {
        "key": "block_after_declines", "title": "Block card after 3 declines in 10 minutes", "language": "PYTHON",
        "description": "Protects against PIN guessing and testing of stolen cards.",
        "default_action": "BLOCK_CARD", "default_response_code": "62", "default_message": "Card blocked by risk algo",
        "code": "if history.declines('10m', 'card') >= 3:\n    block_card('3 declines in 10 minutes', '62')\n",
    },
    {
        "key": "block_high_risk_foreign", "title": "Block customer: HIGH risk + foreign + big amount", "language": "PYTHON",
        "description": "Blocks the whole customer when a HIGH risk customer makes a large foreign transaction.",
        "default_action": "BLOCK_CUSTOMER", "default_response_code": "62", "default_message": "Customer blocked by risk algo",
        "code": "if customer.risk == 'HIGH' and tx.is_foreign and tx.amount > 20000:\n    block_customer('HIGH risk customer, large foreign transaction', '62')\n",
    },
    {
        "key": "daily_atm_cash", "title": "Daily ATM cash cap (all ATM withdrawals)", "language": "PYTHON",
        "description": "Declines when today's approved ATM cash plus this amount would pass 100,000.",
        "default_action": "DECLINE", "default_response_code": "61", "default_message": "Daily ATM cash cap exceeded",
        "code": "used = history.sum_amount('24h', 'card', 'APPROVED', tx_code='10')\nif tx.tran_code == '10' and used + tx.amount > 100000:\n    decline('61', 'Daily ATM cash cap exceeded (used %s)' % used)\n",
    },
    {
        "key": "impossible_travel", "title": "Two acquirers within 5 minutes", "language": "PYTHON",
        "description": "Flags a card used at different acquirers within 5 minutes (possible cloned card).",
        "default_action": "FLAG", "default_response_code": "00", "default_message": "Possible cloned card",
        "code": "if history.distinct('acquirer', '5m', 'card') >= 2:\n    flag('Card used at 2+ acquirers in 5 minutes')\n",
    },
    {
        "key": "vip_allow", "title": "VIP allow-list (small amounts)", "language": "PYTHON",
        "description": "Approves VIP customers below 50,000 at the risk layer and skips the other algos.",
        "default_action": "APPROVE", "default_response_code": "00", "default_message": "VIP allow-list",
        "code": "if customer.is_vip and tx.amount < 50000:\n    approve('VIP allow-list')\n",
    },
    {
        "key": "low_balance_flag", "title": "Balance would drop below 500 (POST_AUTH)", "language": "PYTHON",
        "description": "Flags purchases that leave less than 500 in the account.",
        "default_action": "FLAG", "default_response_code": "00", "default_message": "Low balance after transaction",
        "code": "if tx.is_debit and account.balance_after < 500:\n    flag('Balance after transaction: %s' % account.balance_after)\n",
        "stage": "POST_AUTH",
    },
    {
        "key": "sql_repeat_declines", "title": "SQL: 3+ declines on this card in 15 minutes", "language": "SQL",
        "description": "Matches when the card has 3 or more declined transactions in the last 15 minutes.",
        "default_action": "DECLINE", "default_response_code": "05", "default_message": "Repeated declines",
        "code": "SELECT COUNT(*) >= 3\nFROM transactions\nWHERE card_id = :card_id\n  AND authorization_status = 'DECLINED'\n  AND transaction_datetime >= :since_15m\n",
    },
    {
        "key": "sql_custom_action", "title": "SQL: choose action from the query", "language": "SQL",
        "description": "Returns action / response_code / message columns, so SQL decides what happens.",
        "default_action": "DECLINE", "default_response_code": "57", "default_message": "Risk rule",
        "code": "SELECT 'BLOCK_CARD' AS action, '62' AS response_code, 'Many terminals in 1 hour' AS message\nWHERE (SELECT COUNT(DISTINCT terminal_id) FROM transactions\n       WHERE card_id = :card_id AND transaction_datetime >= :since_1h) >= 4\n",
    },
]


def sql_schema(Base: Any) -> List[Dict[str, Any]]:
    wanted = ["transactions", "cards", "customers", "accounts", "institutions", "card_limits", "account_limits",
              "card_accounts", "host_algo_logs"]
    out = []
    for name in wanted:
        t = Base.metadata.tables.get(name)
        if t is not None:
            out.append({"table": name, "columns": [{"name": c.name, "type": str(c.type)} for c in t.columns]})
    return out
