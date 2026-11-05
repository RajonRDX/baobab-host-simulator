#!/usr/bin/env python3
"""
install_simulator_upgrade.py
BAOBAB Private Host Simulator - Transaction Simulator workbench upgrade

HOW TO RUN
    1. Save this file in your project root (the folder that contains `backend` and `frontend`),
       for example  E:\\HOST_VSCODE\\host-simulator\\install_simulator_upgrade.py
    2. Open a terminal in that folder and run:
           python install_simulator_upgrade.py
       Optional flags:
           --dry-run        show what would change without touching any file
           --root <folder>  use a different project root

WHAT IT CHANGES (every changed file is backed up first to _backups/simulator_workbench_v2_<time>/)
    NEW   backend/app/simulator_workbench_router.py     last STAN/RRN lookup + saved cases API
    NEW   backend/tests/test_simulator_workbench.py     tests for the two features above
    EDIT  backend/app/main.py                           registers the new router (2 lines)
    EDIT  frontend/src/pages/SimulatorAndJournal.tsx    new Transaction Simulator page; the
                                                        Transaction Journal and Transaction
                                                        Details pages in that file are kept as is
    EDIT  PROGRESS.md, docs/CONTRACTS.md                (only if they exist) one entry each

The script is safe to run again: unchanged files are skipped.
After it finishes, restart the backend (it creates the new table by itself) and reload the frontend.
"""

import argparse
import re
import shutil
import sys
import py_compile
from datetime import datetime
from pathlib import Path

STEP_ID = "simulator_workbench_v2"
FALLBACK_ROOTS = [Path(r"E:\HOST_VSCODE\host-simulator")]

# ---------------------------------------------------------------------------
# Embedded file contents
# ---------------------------------------------------------------------------
ROUTER_PY = r'''"""
simulator_workbench_router.py

Backend support for the upgraded Transaction Simulator workbench:

  * GET    /api/simulator-workbench/next-ids   last STAN (DE11) / RRN (DE37) found in the
                                               transactions table and the next free values
  * GET    /api/simulator-workbench/cases      list saved simulator cases
  * GET    /api/simulator-workbench/cases/{id} read one saved case
  * POST   /api/simulator-workbench/cases      save a new case (409 if the name exists
                                               and overwrite is not requested)
  * PUT    /api/simulator-workbench/cases/{id} update a saved case
  * DELETE /api/simulator-workbench/cases/{id} delete a saved case

The saved-case table is created automatically at start-up by the existing schema
synchroniser, because this module registers its model on the shared SQLAlchemy Base
before init_db() runs.
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.database import Base, get_db
from app.models import Transaction, gen_uuid, utc_now
from app.security import get_current_user

router = APIRouter(prefix="/api/simulator-workbench", tags=["Simulator Workbench"])

DEFAULT_STAN = "100001"
DEFAULT_RRN = "000020526001"


# ==============================================================================
# MODEL
# ==============================================================================
class SimulatorSavedCase(Base):
    __tablename__ = "simulator_saved_cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    mti: Mapped[str] = mapped_column(String(4), nullable=False, default="0200")
    transaction_code: Mapped[Optional[str]] = mapped_column(String(20))
    clear_pin_helper: Mapped[Optional[str]] = mapped_column(String(32))
    fields: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    enabled_fields: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


# ==============================================================================
# SCHEMAS
# ==============================================================================
class SavedCaseIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: Optional[str] = Field(None, max_length=2000)
    mti: str = Field("0200", min_length=4, max_length=4)
    transaction_code: Optional[str] = None
    clear_pin_helper: Optional[str] = None
    fields: Dict[str, str] = Field(default_factory=dict)
    enabled_fields: Dict[str, bool] = Field(default_factory=dict)
    overwrite: bool = False


# ==============================================================================
# HELPERS
# ==============================================================================
def increment_trailing_number(value: Optional[str], default: str) -> str:
    """
    Add 1 to the trailing run of digits in `value`, keeping its width.
    '100023' -> '100024'   '000020526009' -> '000020526010'   'ABC0099' -> 'ABC0100'
    A value without digits is returned unchanged; an empty value returns `default`.
    """
    v = (value or "").strip()
    if not v:
        return default
    m = re.search(r"(\d+)$", v)
    if not m:
        return v
    digits = m.group(1)
    bumped = str(int(digits) + 1).zfill(len(digits))
    if len(bumped) > len(digits):  # overflow -> wrap, keep fixed width
        bumped = "1".zfill(len(digits))
    return v[: m.start(1)] + bumped


def _serialize_case(c: SimulatorSavedCase, include_fields: bool = True) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "id": c.id,
        "name": c.name,
        "description": c.description or "",
        "mti": c.mti,
        "transaction_code": c.transaction_code,
        "field_count": len(c.fields or {}),
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }
    if include_fields:
        data["clear_pin_helper"] = c.clear_pin_helper or ""
        data["fields"] = c.fields or {}
        data["enabled_fields"] = c.enabled_fields or {}
    return data


def _apply_payload(case: SimulatorSavedCase, payload: SavedCaseIn) -> None:
    case.name = payload.name.strip()
    case.description = (payload.description or "").strip() or None
    case.mti = payload.mti
    case.transaction_code = payload.transaction_code
    case.clear_pin_helper = payload.clear_pin_helper or None
    case.fields = dict(payload.fields)
    case.enabled_fields = dict(payload.enabled_fields)


# ==============================================================================
# LAST / NEXT STAN & RRN
# ==============================================================================
@router.get("/next-ids")
def get_next_ids(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    last = db.query(Transaction).order_by(Transaction.created_at.desc()).first()
    if not last:
        return {
            "has_history": False,
            "last_stan": None,
            "last_rrn": None,
            "next_stan": DEFAULT_STAN,
            "next_rrn": DEFAULT_RRN,
            "last_transaction": None,
        }
    next_stan = increment_trailing_number(last.stan, DEFAULT_STAN)
    if len(next_stan) == 6 and next_stan.isdigit() and int(next_stan) == 0:
        next_stan = "000001"  # DE11 must never be all zeros
    return {
        "has_history": True,
        "last_stan": last.stan,
        "last_rrn": last.rrn,
        "next_stan": next_stan,
        "next_rrn": increment_trailing_number(last.rrn, DEFAULT_RRN),
        "last_transaction": {
            "transaction_reference": last.transaction_reference,
            "mti": last.mti,
            "masked_pan": last.masked_pan,
            "response_code": last.response_code,
            "created_at": last.created_at.isoformat() if last.created_at else None,
        },
    }


# ==============================================================================
# SAVED CASES
# ==============================================================================
@router.get("/cases")
def list_cases(db: Session = Depends(get_db), _: str = Depends(get_current_user)) -> List[Dict[str, Any]]:
    rows = db.query(SimulatorSavedCase).order_by(SimulatorSavedCase.updated_at.desc()).all()
    return [_serialize_case(c, include_fields=True) for c in rows]


@router.get("/cases/{case_id}")
def get_case(case_id: str, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    case = db.query(SimulatorSavedCase).filter(SimulatorSavedCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Saved case not found")
    return _serialize_case(case)


@router.post("/cases")
def create_case(payload: SavedCaseIn, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Case name is required")
    existing = db.query(SimulatorSavedCase).filter(SimulatorSavedCase.name == name).first()
    if existing and not payload.overwrite:
        raise HTTPException(status_code=409, detail=f"A case named '{name}' already exists")
    case = existing or SimulatorSavedCase()
    _apply_payload(case, payload)
    if not existing:
        db.add(case)
    db.commit()
    db.refresh(case)
    return _serialize_case(case)


@router.put("/cases/{case_id}")
def update_case(
    case_id: str,
    payload: SavedCaseIn,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    case = db.query(SimulatorSavedCase).filter(SimulatorSavedCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Saved case not found")
    new_name = payload.name.strip()
    clash = (
        db.query(SimulatorSavedCase)
        .filter(SimulatorSavedCase.name == new_name, SimulatorSavedCase.id != case_id)
        .first()
    )
    if clash:
        raise HTTPException(status_code=409, detail=f"A case named '{new_name}' already exists")
    _apply_payload(case, payload)
    db.commit()
    db.refresh(case)
    return _serialize_case(case)


@router.delete("/cases/{case_id}")
def delete_case(case_id: str, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    case = db.query(SimulatorSavedCase).filter(SimulatorSavedCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Saved case not found")
    db.delete(case)
    db.commit()
    return {"status": "deleted", "id": case_id}
'''

TEST_PY = r'''"""
test_simulator_workbench.py - Tests for the upgraded simulator workbench:
last STAN / RRN lookup and saved simulator cases.
"""

import os

import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.host_engine import HostTransactionProcessor
from app.main import app
from app.security import create_access_token
from app.seed_data import seed_initial_data
from app.simulator_workbench_router import increment_trailing_number


@pytest.fixture()
def db_session():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    seed_initial_data(session)
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session):
    with TestClient(app) as c:
        token = create_access_token(subject=settings.ADMIN_USERNAME)
        c.headers = {"Authorization": f"Bearer {token}"}
        yield c


def _atm(rrn, stan):
    return {
        "mti": "0200",
        "transaction_code": "10",
        "test_clear_pin_helper": "1234",
        "fields": {
            "2": "4567890123450001",
            "3": "0100000",
            "4": "000000100000",
            "11": stan,
            "37": rrn,
            "41": "ATM01",
            "49": "050",
        },
    }


def test_increment_trailing_number_keeps_width():
    assert increment_trailing_number("100023", "x") == "100024"
    assert increment_trailing_number("000020526009", "x") == "000020526010"
    assert increment_trailing_number("ABC0099", "x") == "ABC0100"
    assert increment_trailing_number("ABC", "x") == "ABC"
    assert increment_trailing_number("", "fallback") == "fallback"


def test_next_ids_follow_the_last_transaction(client, db_session):
    HostTransactionProcessor(db_session).process_transaction(_atm("000088800041", "880041"))
    data = client.get("/api/simulator-workbench/next-ids").json()
    assert data["has_history"] is True
    assert data["last_stan"] == "880041"
    assert data["last_rrn"] == "000088800041"
    assert data["next_stan"] == "880042"
    assert data["next_rrn"] == "000088800042"


def test_saved_case_lifecycle(client):
    body = {
        "name": "ATM withdrawal",
        "description": "baseline",
        "mti": "0200",
        "transaction_code": "10",
        "clear_pin_helper": "1234",
        "fields": {"2": "4567890123450001", "11": "100001"},
        "enabled_fields": {"2": True, "11": True},
    }
    created = client.post("/api/simulator-workbench/cases", json=body)
    assert created.status_code == 200
    case_id = created.json()["id"]

    # same name without overwrite is rejected, with overwrite it replaces the case
    assert client.post("/api/simulator-workbench/cases", json=body).status_code == 409
    replaced = client.post("/api/simulator-workbench/cases", json=dict(body, description="v2", overwrite=True))
    assert replaced.json()["id"] == case_id and replaced.json()["description"] == "v2"

    listing = client.get("/api/simulator-workbench/cases").json()
    assert [c["name"] for c in listing] == ["ATM withdrawal"]
    assert listing[0]["fields"]["11"] == "100001"

    updated = client.put(
        f"/api/simulator-workbench/cases/{case_id}",
        json=dict(body, name="ATM withdrawal v2", fields={"2": "4567890123450001", "11": "100002"}),
    )
    assert updated.status_code == 200 and updated.json()["fields"]["11"] == "100002"

    assert client.delete(f"/api/simulator-workbench/cases/{case_id}").status_code == 200
    assert client.get(f"/api/simulator-workbench/cases/{case_id}").status_code == 404
'''

SIMULATOR_PAGE_HEAD = r'''import { HsmAuthoritySimulatorBar } from '../components/HsmAuthoritySimulatorBar';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowLeft,
  Bookmark,
  Check,
  ClipboardPaste,
  Clock,
  Code2,
  Copy,
  Database,
  FileUp,
  FolderOpen,
  ListChecks,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  Search,
  Trash2,
  X,
  Zap,
} from 'lucide-react';
import { apiFetch } from '../api';

// ============================================================================
// PAGE 8: TIC / ISO TRANSACTION SIMULATOR WORKBENCH
// ============================================================================

type Fields = Record<string, string>;
type Flags = Record<string, boolean>;
type TabKey = 'fields' | 'paste' | 'time' | 'cases';
type SplitMode = 'auto' | 'separate' | 'join';

interface NextIds {
  has_history: boolean;
  last_stan: string | null;
  last_rrn: string | null;
  next_stan: string;
  next_rrn: string;
  last_transaction: any;
}

interface SavedCase {
  id: string;
  name: string;
  description: string;
  mti: string;
  transaction_code: string | null;
  clear_pin_helper: string;
  fields: Fields;
  enabled_fields: Flags;
  field_count: number;
  created_at: string | null;
  updated_at: string | null;
}

interface LoadOpts {
  ids: boolean;
  time: boolean;
}

const STORAGE_KEY = 'BAOBAB_SIMULATOR_STATE_V2';
const MANDATORY_FIELDS = ['2', '3', '4', '11', '37', '41', '49'];
const SAMPLE_ISO =
  '02007220000008008000164567890123450001010000000000100000100001000020526001050';

// ---------------------------------------------------------------------------
// Date & time helpers (DE7 is GMT, the other time fields are local time)
// ---------------------------------------------------------------------------
const pad = (n: number, w = 2) => String(n).padStart(w, '0');
const fmtGmt = (d: Date) =>
  pad(d.getUTCMonth() + 1) + pad(d.getUTCDate()) + pad(d.getUTCHours()) + pad(d.getUTCMinutes()) + pad(d.getUTCSeconds());
const fmtLocalTime = (d: Date) => pad(d.getHours()) + pad(d.getMinutes()) + pad(d.getSeconds());
const fmtLocalDate = (d: Date) => pad(d.getMonth() + 1) + pad(d.getDate());
const toLocalInput = (d: Date) =>
  `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;

const TIME_META: Record<string, { label: string; hint: string; make: (d: Date) => string }> = {
  '7': { label: 'GMT transmission time', hint: 'MMDDhhmmss in GMT', make: fmtGmt },
  '12': { label: 'Local transaction time', hint: 'hhmmss, local time', make: fmtLocalTime },
  '13': { label: 'Local transaction date', hint: 'MMDD, local date', make: fmtLocalDate },
  '15': { label: 'Settlement date', hint: 'MMDD, local date', make: fmtLocalDate },
  '16': { label: 'Currency conversion date', hint: 'MMDD, local date', make: fmtLocalDate },
  '17': { label: 'Capture date', hint: 'MMDD, local date', make: fmtLocalDate },
};
const TIME_KEYS = Object.keys(TIME_META);
const CORE_TIME_KEYS = ['7', '12', '13'];

const buildDefaultFields = (ids?: { stan: string; rrn: string } | null): Fields => {
  const now = new Date();
  return {
    '2': '4567890123450001',
    '3': '0100000',
    '4': '000000250000',
    '7': fmtGmt(now),
    '11': ids?.stan || '100001',
    '12': fmtLocalTime(now),
    '13': fmtLocalDate(now),
    '14': '2812',
    '18': '5411',
    '22': '051',
    '25': '000',
    '32': '123456',
    '37': ids?.rrn || '000020526001',
    '41': 'ATM00001',
    '49': '050',
  };
};

const allEnabled = (f: Fields): Flags => {
  const out: Flags = {};
  Object.keys(f).forEach((k) => (out[k] = true));
  return out;
};

const isDigits = (s?: string | null) => !!s && /^\d+$/.test(s);
// True when the value already used (or is behind) the last value stored in the database.
const isStale = (current?: string, last?: string | null) => {
  if (!current || !last) return false;
  if (isDigits(current) && isDigits(last)) return Number(current) <= Number(last);
  return current === last;
};

// ---------------------------------------------------------------------------
// Raw message helpers
// ---------------------------------------------------------------------------
const splitMessages = (text: string, mode: SplitMode): string[] => {
  const lines = text
    .replace(/^\uFEFF/, '')
    .split(/\r?\n/)
    .map((l) => l.replace(/[\r\n]+$/, ''))
    .filter((l) => l.trim() !== '');
  if (!lines.length) return [];
  const extract = (l: string) => {
    const i = l.indexOf('A4M');
    return i > 0 ? l.slice(i) : l;
  };
  const looksLikeMessage = (l: string) => /A4M/.test(l) || /^\s*\d{4}[0-9A-Fa-f]{16}/.test(l);
  let effective = mode;
  if (mode === 'auto') {
    effective = lines.length > 1 && lines.every(looksLikeMessage) ? 'separate' : 'join';
  }
  return effective === 'separate' ? lines.map(extract) : [extract(lines.join(''))];
};

const decodeFileBytes = (buf: ArrayBuffer): string => {
  const latin = new TextDecoder('windows-1252').decode(buf);
  let utf8: string | null = null;
  try {
    utf8 = new TextDecoder('utf-8', { fatal: true }).decode(buf);
  } catch {
    // not valid UTF-8, so the file is a single-byte (Latin-1 / Windows-1252) file
    return latin;
  }
  // TIC separators (chr 221 and chr 179) are single bytes in a Latin-1 file, and the pair
  // 0xDD 0xB3 also happens to be valid UTF-8. A TIC message only contains characters up to
  // U+00FF, so a wider character together with those bytes means the file is Latin-1.
  const hasWideChar = Array.from(utf8).some((ch) => ch.charCodeAt(0) > 0xff);
  if (hasWideChar && /[\u00DD\u00B3]/.test(latin)) return latin;
  return utf8;
};

// ---------------------------------------------------------------------------
// Shared style tokens
// ---------------------------------------------------------------------------
const cardCls =
  'rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm';
const inputCls =
  'w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 px-3 py-2 text-xs font-mono text-slate-800 dark:text-slate-100 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500/40 focus:border-emerald-500 transition disabled:opacity-50';
const labelCls = 'block text-[11px] font-medium text-slate-500 dark:text-slate-400 mb-1';
const btnGhost =
  'inline-flex items-center gap-1.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-1.5 text-xs font-medium text-slate-700 dark:text-slate-200 hover:border-emerald-500 hover:text-emerald-600 dark:hover:text-emerald-400 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/50 transition disabled:opacity-50';
const btnPrimary =
  'inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 px-4 py-2 text-xs font-semibold text-white shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400/60 transition disabled:opacity-60';
const btnHero =
  'inline-flex items-center gap-1.5 rounded-lg border border-white/15 bg-white/10 hover:bg-white/20 px-3 py-1.5 text-xs font-medium text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-white/50 transition disabled:opacity-50';

export const TransactionSimulatorPage: React.FC = () => {
  // ---- core simulator state -------------------------------------------------
  const [catalog, setCatalog] = useState<any>(null);
  const [txCode, setTxCode] = useState('10');
  const [mti, setMti] = useState('0200');
  const [clearPinHelper, setClearPinHelper] = useState('1234');
  const [fields, setFields] = useState<Fields>(() => buildDefaultFields());
  const [enabledFields, setEnabledFields] = useState<Flags>(() => allEnabled(buildDefaultFields()));
  const [newFieldNum, setNewFieldNum] = useState('55');
  const [rawTic, setRawTic] = useState('');
  const [compactTic, setCompactTic] = useState('');
  const [decodedView, setDecodedView] = useState<any>(null);
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});
  const [txResponse, setTxResponse] = useState<any>(null);
  const [submitting, setSubmitting] = useState(false);

  // ---- workbench state ------------------------------------------------------
  const [hydrated, setHydrated] = useState(false);
  const [sessionRestored, setSessionRestored] = useState(false);
  const [activeTab, setActiveTab] = useState<TabKey>('fields');
  const [nextIds, setNextIds] = useState<NextIds | null>(null);
  const [autoAdvance, setAutoAdvance] = useState(true);
  const [flashField, setFlashField] = useState<string | null>(null);
  const [toast, setToast] = useState<{ kind: 'ok' | 'err' | 'info'; text: string } | null>(null);
  const [copied, setCopied] = useState(false);

  // ---- paste / file state ---------------------------------------------------
  const [pasteText, setPasteText] = useState('');
  const [pasteMode, setPasteMode] = useState<SplitMode>('auto');
  const [pasteIndex, setPasteIndex] = useState(0);
  const [pasteAuto, setPasteAuto] = useState(true);
  const [pasteOpts, setPasteOpts] = useState<LoadOpts>({ ids: false, time: false });
  const [pasteError, setPasteError] = useState('');
  const [pasteInfo, setPasteInfo] = useState<any>(null);
  const [pasteFileName, setPasteFileName] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ---- time tab state -------------------------------------------------------
  const [clock, setClock] = useState<Date>(new Date());
  const [pickedTime, setPickedTime] = useState(toLocalInput(new Date()));

  // ---- saved cases state ----------------------------------------------------
  const [savedCases, setSavedCases] = useState<SavedCase[]>([]);
  const [caseOpts, setCaseOpts] = useState<LoadOpts>({ ids: true, time: false });
  const [caseFilter, setCaseFilter] = useState('');
  const [currentCaseId, setCurrentCaseId] = useState<string | null>(null);
  const [currentCaseName, setCurrentCaseName] = useState('');
  const [saveOpen, setSaveOpen] = useState(false);
  const [saveName, setSaveName] = useState('');
  const [saveDesc, setSaveDesc] = useState('');
  const [saving, setSaving] = useState(false);

  const pasteMessages = useMemo(() => splitMessages(pasteText, pasteMode), [pasteText, pasteMode]);
  const pasteLineCount = useMemo(
    () => pasteText.split(/\r?\n/).filter((l) => l.trim() !== '').length,
    [pasteText]
  );

  const notify = (kind: 'ok' | 'err' | 'info', text: string) => setToast({ kind, text });

  // ==========================================================================
  // Start-up: catalog, last STAN/RRN from the database, last session / last case
  // ==========================================================================
  useEffect(() => {
    let cancelled = false;
    (async () => {
      apiFetch('/simulator/catalog')
        .then((c) => !cancelled && setCatalog(c))
        .catch(console.error);

      let ids: NextIds | null = null;
      let cases: SavedCase[] = [];
      try {
        ids = await apiFetch('/simulator-workbench/next-ids');
      } catch (e) {
        console.warn('Could not read last STAN/RRN from database', e);
      }
      try {
        cases = await apiFetch('/simulator-workbench/cases');
      } catch (e) {
        console.warn('Could not read saved simulator cases', e);
      }
      if (cancelled) return;
      setNextIds(ids);
      setSavedCases(cases);

      let stored: any = null;
      try {
        const raw = localStorage.getItem(STORAGE_KEY);
        if (raw) stored = JSON.parse(raw);
      } catch (e) {
        console.warn('Could not restore simulator state', e);
      }

      let f: Fields | null = null;
      if (stored && stored.fields && Object.keys(stored.fields).length) {
        f = { ...stored.fields };
        setEnabledFields(stored.enabledFields || allEnabled(f));
        if (stored.txCode) setTxCode(stored.txCode);
        if (stored.mti) setMti(stored.mti);
        if (typeof stored.clearPinHelper === 'string') setClearPinHelper(stored.clearPinHelper);
        if (stored.rawTic) setRawTic(stored.rawTic);
        if (stored.compactTic) setCompactTic(stored.compactTic);
        if (stored.txResponse) setTxResponse(stored.txResponse);
        if (typeof stored.autoAdvance === 'boolean') setAutoAdvance(stored.autoAdvance);
        if (stored.pasteOpts) setPasteOpts(stored.pasteOpts);
        if (stored.caseOpts) setCaseOpts(stored.caseOpts);
        if (stored.currentCaseId) setCurrentCaseId(stored.currentCaseId);
        if (stored.currentCaseName) setCurrentCaseName(stored.currentCaseName);
        if (stored.activeTab) setActiveTab(stored.activeTab);
        setSessionRestored(true);
      } else if (cases.length) {
        const latest = cases[0];
        f = { ...latest.fields };
        setEnabledFields(latest.enabled_fields && Object.keys(latest.enabled_fields).length ? latest.enabled_fields : allEnabled(f));
        setTxCode(latest.transaction_code || '10');
        setMti(latest.mti || '0200');
        setClearPinHelper(latest.clear_pin_helper || '');
        setCurrentCaseId(latest.id);
        setCurrentCaseName(latest.name);
        setSessionRestored(true);
      } else {
        f = buildDefaultFields(ids ? { stan: ids.next_stan, rrn: ids.next_rrn } : null);
        setEnabledFields(allEnabled(f));
      }

      // Never start with a STAN / RRN the database has already used
      if (ids && ids.has_history && f) {
        if ('11' in f && isStale(f['11'], ids.last_stan)) f['11'] = ids.next_stan;
        if ('37' in f && isStale(f['37'], ids.last_rrn)) f['37'] = ids.next_rrn;
      }
      if (f) setFields(f);
      setHydrated(true);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Persist the working state so the simulator re-opens exactly where it was left
  useEffect(() => {
    if (!hydrated) return;
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          fields,
          enabledFields,
          txCode,
          mti,
          clearPinHelper,
          rawTic,
          compactTic,
          txResponse,
          autoAdvance,
          pasteOpts,
          caseOpts,
          currentCaseId,
          currentCaseName,
          activeTab,
        })
      );
    } catch (e) {
      /* storage may be full or blocked */
    }
  }, [
    hydrated, fields, enabledFields, txCode, mti, clearPinHelper, rawTic, compactTic,
    txResponse, autoAdvance, pasteOpts, caseOpts, currentCaseId, currentCaseName, activeTab,
  ]);

  useEffect(() => {
    if (!toast) return;
    const t = window.setTimeout(() => setToast(null), 3800);
    return () => window.clearTimeout(t);
  }, [toast]);

  useEffect(() => {
    if (activeTab !== 'time') return;
    setClock(new Date());
    const t = window.setInterval(() => setClock(new Date()), 1000);
    return () => window.clearInterval(t);
  }, [activeTab]);

  useEffect(() => {
    if (!flashField) return;
    const t = window.setTimeout(() => setFlashField(null), 1400);
    return () => window.clearTimeout(t);
  }, [flashField]);

  useEffect(() => {
    if (pasteIndex > 0 && pasteIndex >= pasteMessages.length) setPasteIndex(0);
  }, [pasteMessages, pasteIndex]);

  // ==========================================================================
  // Helpers
  // ==========================================================================
  const getActiveFields = () => {
    const out: Fields = {};
    Object.entries(fields).forEach(([k, v]) => {
      if (enabledFields[k] !== false && v !== '') out[k] = v;
    });
    return out;
  };

  const fetchNextIds = async (): Promise<NextIds | null> => {
    try {
      const ids: NextIds = await apiFetch('/simulator-workbench/next-ids');
      setNextIds(ids);
      return ids;
    } catch (e) {
      return null;
    }
  };

  const reloadCases = async () => {
    try {
      const cases: SavedCase[] = await apiFetch('/simulator-workbench/cases');
      setSavedCases(cases);
    } catch (e) {
      console.warn(e);
    }
  };

  const useDatabaseIds = async () => {
    const ids = await fetchNextIds();
    if (!ids) {
      notify('err', 'Could not read the last STAN and RRN from the database.');
      return;
    }
    setFields((prev) => ({ ...prev, '11': ids.next_stan, '37': ids.next_rrn }));
    setEnabledFields((prev) => ({ ...prev, '11': true, '37': true }));
    notify('ok', `STAN ${ids.next_stan} and RRN ${ids.next_rrn} are ready to use.`);
  };

  const bumpStanAndRrn = () => {
    const nextStan = String((parseInt(fields['11'] || '100000', 10) + 1) % 1000000).padStart(6, '0');
    const nextRrn = String(parseInt(fields['37'] || '20526000', 10) + 1).padStart(12, '0');
    setFields({ ...fields, '11': nextStan, '37': nextRrn });
  };

  const setTimeNow = (keys: string[], date: Date = new Date()) => {
    setFields((prev) => {
      const next = { ...prev };
      keys.forEach((k) => (next[k] = TIME_META[k].make(date)));
      return next;
    });
    setEnabledFields((prev) => {
      const next = { ...prev };
      keys.forEach((k) => (next[k] = true));
      return next;
    });
  };

  const setAllTimeNow = (date: Date = new Date()) => {
    const keys = [...CORE_TIME_KEYS, ...['15', '16', '17'].filter((k) => k in fields)];
    setTimeNow(keys, date);
  };

  const applyPickedTime = () => {
    const d = new Date(pickedTime);
    if (isNaN(d.getTime())) {
      notify('err', 'Pick a valid date and time first.');
      return;
    }
    setAllTimeNow(d);
    notify('ok', 'Time fields updated from the selected date and time.');
  };

  const addFieldToEditor = (num?: string) => {
    const n = num || newFieldNum;
    if (!n) return;
    setFields((prev) => (n in prev ? prev : { ...prev, [n]: '' }));
    setEnabledFields((prev) => ({ ...prev, [n]: true }));
    setActiveTab('fields');
    setFlashField(n);
    window.setTimeout(() => {
      document.getElementById(`de-row-${n}`)?.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }, 60);
  };

  const removeField = (n: string) => {
    setFields((prev) => {
      const next = { ...prev };
      delete next[n];
      return next;
    });
    setEnabledFields((prev) => {
      const next = { ...prev };
      delete next[n];
      return next;
    });
  };

  const jumpToField = (n: number) => {
    const key = String(n);
    if (key in fields) {
      setFlashField(key);
      document.getElementById(`de-row-${key}`)?.scrollIntoView({ block: 'center', behavior: 'smooth' });
    } else if (catalog?.field_definitions?.some((d: any) => String(d.field_number) === key)) {
      addFieldToEditor(key);
    }
  };

  // Loads a message / case into the editor, optionally refreshing STAN, RRN and time
  const loadIntoEditor = async (
    data: { mti: string; txCode?: string | null; fields: Fields; enabled?: Flags; pin?: string },
    opts: LoadOpts
  ) => {
    const f: Fields = {};
    Object.entries(data.fields || {}).forEach(([k, v]) => (f[String(k)] = String(v ?? '')));
    const en: Flags =
      data.enabled && Object.keys(data.enabled).length ? { ...data.enabled } : allEnabled(f);
    Object.keys(f).forEach((k) => {
      if (!(k in en)) en[k] = true;
    });

    if (opts.ids) {
      const ids = await fetchNextIds();
      if (ids) {
        if ('11' in f) f['11'] = ids.next_stan;
        if ('37' in f) f['37'] = ids.next_rrn;
      }
    }
    if (opts.time) {
      const now = new Date();
      TIME_KEYS.forEach((k) => {
        if (k in f) f[k] = TIME_META[k].make(now);
      });
    }

    setFields(f);
    setEnabledFields(en);
    if (data.mti) setMti(data.mti);
    if (data.txCode) setTxCode(String(data.txCode));
    if (data.pin !== undefined) setClearPinHelper(data.pin);
    setValidationErrors({});
    setTxResponse(null);
    setCompactTic('');
    setDecodedView(null);
    setRawTic('');
  };

  // ==========================================================================
  // Raw message: paste, file, parse
  // ==========================================================================
  const parseMessage = async (message: string) => {
    setPasteError('');
    setPasteInfo(null);
    if (!message.trim()) {
      setPasteError('Paste a raw message or load a file first.');
      return;
    }
    try {
      const res = await apiFetch('/simulator/parse-raw', {
        method: 'POST',
        body: JSON.stringify({ raw_message: message }),
      });
      if (!res.valid) {
        setPasteError(res.error || 'The message could not be parsed.');
        return;
      }
      await loadIntoEditor(
        { mti: res.mti, txCode: res.derived_transaction_code, fields: res.fields || {} },
        pasteOpts
      );
      setRawTic(message);
      if (res.detailed_fields) setDecodedView({ detailed_fields: res.detailed_fields });
      const keys = Object.keys(res.fields || {}).sort((a, b) => Number(a) - Number(b));
      setPasteInfo({ format: res.format, mti: res.mti, keys, warnings: res.warnings || [] });
      setSessionRestored(false);
      setCurrentCaseId(null);
      setCurrentCaseName('');
      setActiveTab('fields');
      notify('ok', `Loaded ${keys.length} fields from the ${res.format === 'TIC_V2164E' ? 'TIC' : 'ISO 8583'} message.`);
    } catch (err: any) {
      setPasteError(err.message || 'The message could not be parsed.');
    }
  };

  const handlePaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    if (!pasteAuto) return;
    const text = e.clipboardData.getData('text');
    if (!text.trim()) return;
    e.preventDefault();
    setPasteText(text);
    setPasteFileName('');
    setPasteIndex(0);
    const msgs = splitMessages(text, pasteMode);
    if (msgs.length) parseMessage(msgs[0]);
  };

  const readFile = async (file: File) => {
    try {
      const text = decodeFileBytes(await file.arrayBuffer());
      setPasteText(text);
      setPasteFileName(file.name);
      setPasteIndex(0);
      setPasteError('');
      setPasteInfo(null);
      const msgs = splitMessages(text, pasteMode);
      if (!msgs.length) {
        setPasteError('The file is empty.');
        return;
      }
      if (pasteAuto) await parseMessage(msgs[0]);
      else notify('info', `Loaded ${file.name}. Press Parse and load fields to continue.`);
    } catch (err: any) {
      setPasteError(err.message || 'The file could not be read.');
    }
  };

  const onFilePicked = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) readFile(file);
    e.target.value = '';
  };

  const onDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) readFile(file);
  };

  // ==========================================================================
  // Build, decode, submit
  // ==========================================================================
  const handleBuildAndValidate = async () => {
    setValidationErrors({});
    try {
      const res = await apiFetch('/simulator/build', {
        method: 'POST',
        body: JSON.stringify({ mti, fields: getActiveFields() }),
      });
      if (!res.valid) {
        setValidationErrors(res.errors || {});
        notify('err', `${Object.keys(res.errors || {}).length} field(s) need attention.`);
      } else {
        setRawTic(res.raw_tic_message);
        setCompactTic(res.compact_tic);
        setDecodedView(res.decoded);
        notify('ok', 'Message built and validated.');
      }
    } catch (e: any) {
      notify('err', e.message);
    }
  };

  const handleDecodeRaw = async () => {
    if (!rawTic.trim()) return;
    try {
      const dec = await apiFetch('/simulator/decode', {
        method: 'POST',
        body: JSON.stringify({ raw_tic_message: rawTic }),
      });
      setDecodedView(dec);
      if (dec.valid && dec.raw_fields) {
        setMti(dec.mti || '0200');
        setFields(dec.raw_fields);
        setEnabledFields(allEnabled(dec.raw_fields));
      }
    } catch (e: any) {
      notify('err', e.message);
    }
  };

  const handleSubmitTransaction = async () => {
    setSubmitting(true);
    setValidationErrors({});
    try {
      const res = await apiFetch('/simulator/submit', {
        method: 'POST',
        body: JSON.stringify({
          transaction_code: txCode,
          mti,
          fields: getActiveFields(),
          test_clear_pin_helper: clearPinHelper || undefined,
          source_channel: 'SIMULATOR',
        }),
      });
      setTxResponse(res);
      setRawTic(res.sanitized_request_tic || rawTic);
      setCompactTic(res.compact_response_tic || '');
      if (autoAdvance) {
        const ids = await fetchNextIds();
        if (ids) {
          setFields((prev) => {
            const next = { ...prev };
            if ('11' in next) next['11'] = ids.next_stan;
            if ('37' in next) next['37'] = ids.next_rrn;
            return next;
          });
        }
      } else {
        fetchNextIds();
      }
    } catch (e: any) {
      notify('err', e.message);
    } finally {
      setSubmitting(false);
    }
  };

  const resetToDefaults = async () => {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch (e) {
      /* ignore */
    }
    const ids = await fetchNextIds();
    const f = buildDefaultFields(ids ? { stan: ids.next_stan, rrn: ids.next_rrn } : null);
    setTxCode('10');
    setMti('0200');
    setClearPinHelper('1234');
    setFields(f);
    setEnabledFields(allEnabled(f));
    setTxResponse(null);
    setRawTic('');
    setCompactTic('');
    setDecodedView(null);
    setValidationErrors({});
    setSessionRestored(false);
    setCurrentCaseId(null);
    setCurrentCaseName('');
    notify('info', 'Simulator reset. STAN and RRN continue from the database.');
  };

  const copyRaw = async () => {
    try {
      await navigator.clipboard.writeText(rawTic);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch (e) {
      notify('err', 'Copy failed. Select the text and copy it manually.');
    }
  };

  // ==========================================================================
  // Saved cases
  // ==========================================================================
  const openSaveDialog = () => {
    setSaveName(currentCaseName || '');
    setSaveDesc(savedCases.find((c) => c.id === currentCaseId)?.description || '');
    setSaveOpen(true);
  };

  const casePayload = (name: string, description: string, overwrite = false) => ({
    name: name.trim(),
    description: description.trim(),
    mti,
    transaction_code: txCode,
    clear_pin_helper: clearPinHelper || '',
    fields,
    enabled_fields: enabledFields,
    overwrite,
  });

  const saveCase = async (asNew: boolean) => {
    const name = saveName.trim();
    if (!name) {
      notify('err', 'Give the case a name first.');
      return;
    }
    setSaving(true);
    try {
      let saved: SavedCase;
      if (!asNew && currentCaseId) {
        saved = await apiFetch(`/simulator-workbench/cases/${currentCaseId}`, {
          method: 'PUT',
          body: JSON.stringify(casePayload(name, saveDesc)),
        });
      } else {
        try {
          saved = await apiFetch('/simulator-workbench/cases', {
            method: 'POST',
            body: JSON.stringify(casePayload(name, saveDesc)),
          });
        } catch (err: any) {
          if (!/already exists/i.test(err.message || '')) throw err;
          if (!window.confirm(`A case named "${name}" already exists. Replace it?`)) {
            setSaving(false);
            return;
          }
          saved = await apiFetch('/simulator-workbench/cases', {
            method: 'POST',
            body: JSON.stringify(casePayload(name, saveDesc, true)),
          });
        }
      }
      setCurrentCaseId(saved.id);
      setCurrentCaseName(saved.name);
      setSaveOpen(false);
      await reloadCases();
      notify('ok', `Saved case "${saved.name}".`);
    } catch (e: any) {
      notify('err', e.message || 'The case could not be saved.');
    } finally {
      setSaving(false);
    }
  };

  const loadCase = async (c: SavedCase) => {
    await loadIntoEditor(
      {
        mti: c.mti,
        txCode: c.transaction_code,
        fields: c.fields,
        enabled: c.enabled_fields,
        pin: c.clear_pin_helper || '',
      },
      caseOpts
    );
    setCurrentCaseId(c.id);
    setCurrentCaseName(c.name);
    setSessionRestored(false);
    setActiveTab('fields');
    notify('ok', `Loaded case "${c.name}".`);
  };

  const deleteCase = async (c: SavedCase) => {
    if (!window.confirm(`Delete the saved case "${c.name}"?`)) return;
    try {
      await apiFetch(`/simulator-workbench/cases/${c.id}`, { method: 'DELETE' });
      if (currentCaseId === c.id) {
        setCurrentCaseId(null);
        setCurrentCaseName('');
      }
      await reloadCases();
      notify('info', `Deleted "${c.name}".`);
    } catch (e: any) {
      notify('err', e.message);
    }
  };

  const filteredCases = savedCases.filter((c) => {
    const q = caseFilter.trim().toLowerCase();
    if (!q) return true;
    return c.name.toLowerCase().includes(q) || (c.description || '').toLowerCase().includes(q);
  });

  // ==========================================================================
  // Render helpers
  // ==========================================================================
  const fieldDefs: any[] = catalog?.field_definitions || [];
  const defFor = (n: string | number) => fieldDefs.find((d: any) => String(d.field_number) === String(n));

  const bitmapCell = (n: number) => {
    const key = String(n);
    const def = defFor(n);
    const present = key in fields;
    let cls = 'bg-slate-100 dark:bg-slate-900/70 cursor-default';
    if (present && enabledFields[key] === false) cls = 'bg-slate-400 dark:bg-slate-600 cursor-pointer';
    else if (present && fields[key] === '') cls = 'bg-amber-400 cursor-pointer';
    else if (present) cls = 'bg-emerald-500 cursor-pointer';
    else if (def) cls = 'bg-slate-200 dark:bg-slate-800 hover:bg-emerald-300 dark:hover:bg-emerald-800 cursor-pointer';
    return (
      <button
        key={n}
        type="button"
        onClick={() => jumpToField(n)}
        title={`DE${n}${def ? ' ' + def.name : ' (not defined)'}${present ? '' : def ? ' - click to add' : ''}`}
        aria-label={`DE${n}`}
        className={`h-3.5 rounded-[3px] transition-colors ${cls}`}
      />
    );
  };

  const tabs: { key: TabKey; label: string; icon: React.ReactNode; badge?: string }[] = [
    { key: 'fields', label: 'Field editor', icon: <ListChecks size={14} />, badge: String(Object.keys(fields).length) },
    { key: 'paste', label: 'Paste or load message', icon: <ClipboardPaste size={14} /> },
    { key: 'time', label: 'Date and time', icon: <Clock size={14} /> },
    { key: 'cases', label: 'Saved cases', icon: <Bookmark size={14} />, badge: savedCases.length ? String(savedCases.length) : undefined },
  ];

  const optionRow = (
    opts: LoadOpts,
    set: (o: LoadOpts) => void,
    idsLabel: string,
    timeLabel: string
  ) => (
    <div className="space-y-1.5 rounded-xl bg-slate-50 dark:bg-slate-950/60 border border-slate-200 dark:border-slate-800 p-3">
      <label className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-300 cursor-pointer">
        <input
          type="checkbox"
          checked={opts.ids}
          onChange={(e) => set({ ...opts, ids: e.target.checked })}
          className="accent-emerald-600"
        />
        {idsLabel}
      </label>
      <label className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-300 cursor-pointer">
        <input
          type="checkbox"
          checked={opts.time}
          onChange={(e) => set({ ...opts, time: e.target.checked })}
          className="accent-emerald-600"
        />
        {timeLabel}
      </label>
    </div>
  );

  // ==========================================================================
  // Render
  // ==========================================================================
  return (
    <div className="space-y-5">
      <HsmAuthoritySimulatorBar />

      {/* ------------------------------------------------------------------ */}
      {/* Header                                                              */}
      {/* ------------------------------------------------------------------ */}
      <div className="relative overflow-hidden rounded-2xl border border-slate-800 bg-gradient-to-br from-slate-900 via-slate-900 to-emerald-950 p-5 text-white shadow-lg">
        <div className="pointer-events-none absolute -right-16 -top-16 h-56 w-56 rounded-full bg-emerald-500/10 blur-3xl" />
        <div className="relative flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0 space-y-2">
            <h1 className="text-xl font-bold tracking-tight">Transaction simulator</h1>
            <p className="max-w-xl text-xs leading-relaxed text-slate-300">
              Build a TIC or ISO 8583 message field by field, paste a raw message to unpack it, and send it to the host.
              Your last session comes back every time you open this page.
            </p>
            <div className="flex flex-wrap items-center gap-2 pt-1">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-white/15 bg-white/10 px-2.5 py-1 text-[11px] font-mono">
                <Database size={12} className="text-emerald-300" />
                {nextIds?.has_history
                  ? `Last in database: STAN ${nextIds.last_stan}, RRN ${nextIds.last_rrn}`
                  : 'No transactions in the database yet'}
              </span>
              <button type="button" onClick={useDatabaseIds} className={btnHero} title="Fill DE11 and DE37 with the next free values">
                <RefreshCw size={12} /> Use next STAN and RRN
              </button>
              <label className="inline-flex items-center gap-1.5 text-[11px] text-slate-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={autoAdvance}
                  onChange={(e) => setAutoAdvance(e.target.checked)}
                  className="accent-emerald-500"
                />
                Move to the next STAN and RRN after each submit
              </label>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {sessionRestored && (
                <span className="inline-flex items-center gap-1 rounded-full border border-emerald-400/30 bg-emerald-400/10 px-2.5 py-0.5 text-[11px] font-medium text-emerald-300">
                  <Check size={12} /> Restored your last session
                </span>
              )}
              {currentCaseName && (
                <span className="inline-flex items-center gap-1.5 rounded-full border border-sky-400/30 bg-sky-400/10 px-2.5 py-0.5 text-[11px] font-medium text-sky-300">
                  <Bookmark size={12} /> {currentCaseName}
                  <button
                    type="button"
                    onClick={() => {
                      setCurrentCaseId(null);
                      setCurrentCaseName('');
                    }}
                    className="rounded-full hover:bg-white/20 p-0.5"
                    title="Detach from this saved case"
                    aria-label="Detach from saved case"
                  >
                    <X size={10} />
                  </button>
                </span>
              )}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button type="button" onClick={openSaveDialog} className={btnHero}>
              <Save size={14} /> Save case
            </button>
            <button type="button" onClick={() => setActiveTab('cases')} className={btnHero}>
              <FolderOpen size={14} /> Open case
            </button>
            <button type="button" onClick={resetToDefaults} className={btnHero} title="Reset the simulator to default values">
              <RotateCcw size={14} /> Reset
            </button>
            <button type="button" onClick={bumpStanAndRrn} className={btnHero} title="Add 1 to STAN and RRN">
              <Plus size={14} /> STAN and RRN
            </button>
            <button
              type="button"
              onClick={handleBuildAndValidate}
              className="inline-flex items-center gap-1.5 rounded-lg bg-sky-500 hover:bg-sky-400 px-3.5 py-1.5 text-xs font-semibold text-white transition focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-300/60"
            >
              <Code2 size={14} /> Build and validate
            </button>
            <button type="button" onClick={handleSubmitTransaction} disabled={submitting} className={btnPrimary}>
              <Play size={14} /> {submitting ? 'Processing...' : 'Submit to host'}
            </button>
          </div>
        </div>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Main grid                                                           */}
      {/* ------------------------------------------------------------------ */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        {/* ------------------------------ Left: tabbed workbench ------------------------------ */}
        <div className={`${cardCls} lg:col-span-7 p-0 overflow-hidden`}>
          <div className="flex flex-wrap gap-1 border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/50 p-2" role="tablist">
            {tabs.map((t) => (
              <button
                key={t.key}
                type="button"
                role="tab"
                aria-selected={activeTab === t.key}
                onClick={() => setActiveTab(t.key)}
                className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/50 ${
                  activeTab === t.key
                    ? 'bg-white dark:bg-slate-800 text-emerald-600 dark:text-emerald-400 shadow-sm ring-1 ring-slate-200 dark:ring-slate-700'
                    : 'text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200'
                }`}
              >
                {t.icon}
                {t.label}
                {t.badge && (
                  <span className="rounded-full bg-slate-200 dark:bg-slate-700 px-1.5 text-[10px] font-mono text-slate-600 dark:text-slate-300">
                    {t.badge}
                  </span>
                )}
              </button>
            ))}
          </div>

          <div className="p-5">
            {/* =================== TAB: FIELD EDITOR =================== */}
            {activeTab === 'fields' && (
              <div className="space-y-4">
                <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
                  <div>
                    <label className={labelCls}>Transaction code</label>
                    <select
                      value={txCode}
                      onChange={(e) => {
                        const nextCode = e.target.value;
                        setTxCode(nextCode);
                        const found = catalog?.transaction_codes?.find((c: any) => c.transaction_code === nextCode);
                        if (found) {
                          setMti(found.default_mti);
                          setFields({ ...fields, '3': found.processing_code });
                        }
                      }}
                      className={inputCls}
                    >
                      {txCode && !(catalog?.transaction_codes || []).some((c: any) => c.transaction_code === txCode) && (
                        <option value={txCode}>Code {txCode}</option>
                      )}
                      {(catalog?.transaction_codes || []).map((c: any) => (
                        <option key={c.transaction_code} value={c.transaction_code}>
                          Code {c.transaction_code}: {c.transaction_name}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className={labelCls}>MTI</label>
                    <select value={mti} onChange={(e) => setMti(e.target.value)} className={inputCls}>
                      <option value="0100">0100 Auth request</option>
                      <option value="0110">0110 Auth response</option>
                      <option value="0200">0200 Financial request</option>
                      <option value="0210">0210 Financial response</option>
                      <option value="0220">0220 Financial advice</option>
                      <option value="0400">0400 Reversal request</option>
                      <option value="0410">0410 Reversal response</option>
                      <option value="0420">0420 Reversal advice</option>
                      <option value="0430">0430 Reversal advice response</option>
                      <option value="0800">0800 Network management</option>
                      <option value="0810">0810 Network management response</option>
                      {!['0100','0110','0200','0210','0220','0400','0410','0420','0430','0800','0810'].includes(mti) && (
                        <option value={mti}>{mti}</option>
                      )}
                    </select>
                  </div>

                  <div>
                    <label className={labelCls}>Synthetic card</label>
                    <select
                      value={fields['2'] || ''}
                      onChange={(e) => setFields({ ...fields, '2': e.target.value })}
                      className={inputCls}
                    >
                      {fields['2'] && !(catalog?.test_cards || []).some((c: any) => c.test_pan_reference === fields['2']) && (
                        <option value={fields['2']}>Custom PAN from the message</option>
                      )}
                      {(catalog?.test_cards || []).map((c: any) => (
                        <option key={c.id} value={c.test_pan_reference}>
                          {c.masked_pan} ({c.card_status})
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className={labelCls}>Server PIN helper (packs DE52)</label>
                    <input
                      type="password"
                      value={clearPinHelper}
                      onChange={(e) => setClearPinHelper(e.target.value)}
                      placeholder="1234 is valid, 9999 is wrong"
                      className={inputCls}
                    />
                  </div>
                </div>

                {/* Bitmap strip */}
                <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950/50 p-3">
                  <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                    <div className="text-xs font-medium text-slate-600 dark:text-slate-300">
                      Message bitmap
                      <span className="ml-2 font-normal text-slate-400">Each square is one data element. Click a square to jump to it or add it.</span>
                    </div>
                    <div className="flex items-center gap-3 text-[10px] text-slate-500">
                      <span className="inline-flex items-center gap-1"><i className="h-2.5 w-2.5 rounded-sm bg-emerald-500" /> has a value</span>
                      <span className="inline-flex items-center gap-1"><i className="h-2.5 w-2.5 rounded-sm bg-amber-400" /> empty</span>
                      <span className="inline-flex items-center gap-1"><i className="h-2.5 w-2.5 rounded-sm bg-slate-400 dark:bg-slate-600" /> switched off</span>
                    </div>
                  </div>
                  <div className="space-y-1">
                    {[0, 1, 2, 3].map((row) => (
                      <div key={row} className="grid gap-1" style={{ gridTemplateColumns: 'repeat(32, minmax(0, 1fr))' }}>
                        {Array.from({ length: 32 }, (_, i) => row * 32 + i + 1).map(bitmapCell)}
                      </div>
                    ))}
                  </div>
                </div>

                {/* Add field */}
                <div className="flex flex-wrap items-center gap-2">
                  <select value={newFieldNum} onChange={(e) => setNewFieldNum(e.target.value)} className={`${inputCls} !w-auto min-w-[16rem] flex-1`}>
                    {fieldDefs.map((f: any) => (
                      <option key={f.field_number} value={String(f.field_number)}>
                        DE{f.field_number} {f.name} ({f.data_type}, {f.length_type}
                        {f.fixed_length ? ` ${f.fixed_length}` : ''})
                      </option>
                    ))}
                  </select>
                  <button type="button" onClick={() => addFieldToEditor()} className={btnGhost}>
                    <Plus size={14} /> Add field
                  </button>
                </div>

                {/* Field list */}
                <div className="max-h-[460px] space-y-2 overflow-y-auto pr-1">
                  {Object.keys(fields).length === 0 && (
                    <div className="rounded-xl border border-dashed border-slate-300 dark:border-slate-700 p-8 text-center text-xs text-slate-500">
                      No fields yet. Add a field above, paste a raw message, or open a saved case.
                    </div>
                  )}
                  {Object.keys(fields)
                    .sort((a, b) => Number(a) - Number(b))
                    .map((fnum) => {
                      const def = defFor(fnum);
                      const err = validationErrors[`DE${fnum}`];
                      const isMandatory = MANDATORY_FIELDS.includes(fnum);
                      const timeMeta = TIME_META[fnum];
                      const value = fields[fnum] ?? '';
                      const fixed = def && def.length_type === 'FIXED' ? def.fixed_length : null;
                      const off = enabledFields[fnum] === false;
                      return (
                        <div
                          key={fnum}
                          id={`de-row-${fnum}`}
                          className={`rounded-xl border p-2.5 text-xs transition-shadow ${
                            err
                              ? 'border-rose-400 bg-rose-500/5'
                              : 'border-slate-200 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-950/40'
                          } ${flashField === fnum ? 'ring-2 ring-emerald-500' : ''} ${off ? 'opacity-60' : ''}`}
                        >
                          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
                            <input
                              type="checkbox"
                              checked={!off}
                              onChange={(e) => setEnabledFields({ ...enabledFields, [fnum]: e.target.checked })}
                              className="accent-emerald-600"
                              aria-label={`Include DE${fnum}`}
                            />
                            <span className="w-12 font-mono font-bold text-emerald-600 dark:text-emerald-400">
                              DE{fnum}
                              {isMandatory && <span className="text-rose-500" title="Required"> *</span>}
                            </span>
                            <span className="w-44 truncate text-slate-600 dark:text-slate-300" title={def?.name}>
                              {def ? def.name : `TIC field ${fnum}`}
                            </span>
                            {def && (
                              <span className="rounded bg-slate-200 dark:bg-slate-800 px-1.5 py-0.5 font-mono text-[10px] text-slate-500">
                                {def.data_type} {def.length_type}
                                {def.fixed_length ? ` ${def.fixed_length}` : ''}
                              </span>
                            )}
                            <input
                              value={value}
                              onChange={(e) => setFields({ ...fields, [fnum]: e.target.value })}
                              disabled={off}
                              className={`${inputCls} !w-auto min-w-[10rem] flex-1`}
                            />
                            {fixed ? (
                              <span className={`w-12 text-right font-mono text-[10px] ${value.length > fixed ? 'text-rose-500' : 'text-slate-400'}`}>
                                {value.length}/{fixed}
                              </span>
                            ) : (
                              <span className="w-12 text-right font-mono text-[10px] text-slate-400">{value.length}</span>
                            )}
                            {timeMeta && (
                              <button
                                type="button"
                                onClick={() => setTimeNow([fnum])}
                                className="inline-flex items-center gap-1 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-2 py-1 text-[11px] font-semibold text-emerald-600 dark:text-emerald-400 hover:bg-emerald-500/20 transition"
                                title={`Set DE${fnum} to the current time (${timeMeta.hint})`}
                              >
                                <Clock size={11} /> Now
                              </button>
                            )}
                            {!isMandatory && (
                              <button
                                type="button"
                                onClick={() => removeField(fnum)}
                                className="rounded-lg p-1 text-slate-400 hover:bg-rose-500/10 hover:text-rose-500 transition"
                                title={`Remove DE${fnum}`}
                                aria-label={`Remove DE${fnum}`}
                              >
                                <Trash2 size={13} />
                              </button>
                            )}
                          </div>
                          {err && (
                            <div className="mt-1.5 flex items-center gap-1 pl-6 text-[11px] text-rose-500">
                              <AlertTriangle size={12} /> {err}
                            </div>
                          )}
                        </div>
                      );
                    })}
                </div>
              </div>
            )}

            {/* =================== TAB: PASTE / LOAD =================== */}
            {activeTab === 'paste' && (
              <div className="space-y-4">
                <p className="text-xs leading-relaxed text-slate-500 dark:text-slate-400">
                  Paste a raw TIC (A4M header) or ISO 8583 message, or load it from a file. Every field in the message is
                  unpacked into the field editor automatically. A file can hold one message or one message per line.
                </p>

                <div
                  onDragOver={(e) => {
                    e.preventDefault();
                    setDragOver(true);
                  }}
                  onDragLeave={() => setDragOver(false)}
                  onDrop={onDrop}
                  className={`rounded-xl border-2 border-dashed p-3 transition ${
                    dragOver
                      ? 'border-emerald-500 bg-emerald-500/5'
                      : 'border-slate-300 dark:border-slate-700 bg-slate-50/60 dark:bg-slate-950/40'
                  }`}
                >
                  <textarea
                    rows={7}
                    value={pasteText}
                    onChange={(e) => {
                      setPasteText(e.target.value);
                      setPasteFileName('');
                    }}
                    onPaste={handlePaste}
                    placeholder="Paste the raw message here (A4M0200... or 0200702004...), or drop a file on this box."
                    spellCheck={false}
                    className="w-full resize-y rounded-lg border border-slate-800 bg-slate-950 p-3 font-mono text-xs text-emerald-300 placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-emerald-500/40"
                  />
                  <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <input
                        ref={fileInputRef}
                        type="file"
                        className="hidden"
                        accept=".txt,.log,.iso,.tic,.msg,.dat,.hex,text/plain"
                        onChange={onFilePicked}
                      />
                      <button type="button" onClick={() => fileInputRef.current?.click()} className={btnGhost}>
                        <FileUp size={14} /> Load from file
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setPasteText(SAMPLE_ISO);
                          setPasteFileName('');
                          setPasteIndex(0);
                        }}
                        className="text-[11px] font-medium text-sky-600 dark:text-sky-400 hover:underline"
                      >
                        Insert a sample ISO 8583 message
                      </button>
                      {pasteFileName && (
                        <span className="rounded-full bg-slate-200 dark:bg-slate-800 px-2 py-0.5 font-mono text-[10px] text-slate-600 dark:text-slate-300">
                          {pasteFileName}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          setPasteText('');
                          setPasteFileName('');
                          setPasteError('');
                          setPasteInfo(null);
                          setPasteIndex(0);
                        }}
                        className={btnGhost}
                        disabled={!pasteText}
                      >
                        <X size={14} /> Clear
                      </button>
                      <button
                        type="button"
                        onClick={() => parseMessage(pasteMessages[Math.min(pasteIndex, Math.max(0, pasteMessages.length - 1))] || '')}
                        className={btnPrimary}
                      >
                        <Zap size={14} /> Parse and load fields
                      </button>
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                  <div className="space-y-3">
                    <label className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-300 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={pasteAuto}
                        onChange={(e) => setPasteAuto(e.target.checked)}
                        className="accent-emerald-600"
                      />
                      Load the fields as soon as I paste or open a file
                    </label>
                    {pasteLineCount > 1 && (
                      <div>
                        <label className={labelCls}>This text has {pasteLineCount} lines</label>
                        <select
                          value={pasteMode}
                          onChange={(e) => {
                            setPasteMode(e.target.value as SplitMode);
                            setPasteIndex(0);
                          }}
                          className={inputCls}
                        >
                          <option value="auto">Detect automatically</option>
                          <option value="separate">Each line is its own message</option>
                          <option value="join">All lines form one message</option>
                        </select>
                      </div>
                    )}
                    {pasteMessages.length > 1 && (
                      <div>
                        <label className={labelCls}>{pasteMessages.length} messages found. Choose one to load.</label>
                        <select
                          value={pasteIndex}
                          onChange={(e) => {
                            const i = Number(e.target.value);
                            setPasteIndex(i);
                            parseMessage(pasteMessages[i]);
                          }}
                          className={inputCls}
                        >
                          {pasteMessages.map((m, i) => (
                            <option key={i} value={i}>
                              Message {i + 1}: {m.slice(0, 34)}
                              {m.length > 34 ? '...' : ''}
                            </option>
                          ))}
                        </select>
                      </div>
                    )}
                  </div>
                  {optionRow(
                    pasteOpts,
                    setPasteOpts,
                    'Replace STAN and RRN with the next free values from the database',
                    'Set the time fields in the message to the current time'
                  )}
                </div>

                {pasteError && (
                  <div className="flex items-start gap-2 rounded-xl border border-rose-400/40 bg-rose-500/10 p-3 text-xs text-rose-600 dark:text-rose-300">
                    <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                    <div>
                      <div className="font-semibold">The message was not loaded</div>
                      <div className="mt-0.5">{pasteError}</div>
                      <div className="mt-1 text-rose-500/80">
                        Check that the message starts with A4M (TIC) or a 4-digit MTI (ISO 8583) and that it is not cut off.
                      </div>
                    </div>
                  </div>
                )}

                {pasteInfo && (
                  <div className="space-y-2 rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-3">
                    <div className="flex flex-wrap items-center gap-2 text-xs">
                      <span className="font-semibold text-emerald-600 dark:text-emerald-400">
                        {pasteInfo.keys.length} fields loaded
                      </span>
                      <span className="rounded bg-slate-200 dark:bg-slate-800 px-1.5 py-0.5 font-mono text-[10px]">
                        {pasteInfo.format === 'TIC_V2164E' ? 'TIC v2.164e' : 'ISO 8583:1987'}
                      </span>
                      <span className="rounded bg-slate-200 dark:bg-slate-800 px-1.5 py-0.5 font-mono text-[10px]">
                        MTI {pasteInfo.mti}
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {pasteInfo.keys.map((k: string) => (
                        <button
                          key={k}
                          type="button"
                          onClick={() => {
                            setActiveTab('fields');
                            window.setTimeout(() => jumpToField(Number(k)), 80);
                          }}
                          className="rounded bg-emerald-500/15 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-emerald-700 dark:text-emerald-300 hover:bg-emerald-500/30"
                          title={defFor(k)?.name}
                        >
                          DE{k}
                        </button>
                      ))}
                    </div>
                    {pasteInfo.warnings.length > 0 && (
                      <ul className="list-disc space-y-0.5 pl-5 text-[11px] text-amber-600 dark:text-amber-400">
                        {pasteInfo.warnings.map((w: string, i: number) => (
                          <li key={i}>{w}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* =================== TAB: DATE AND TIME =================== */}
            {activeTab === 'time' && (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/50 p-4">
                  <div>
                    <div className="text-[11px] text-slate-500">Local time on this computer</div>
                    <div className="font-mono text-2xl font-bold tracking-tight text-slate-800 dark:text-slate-100">
                      {pad(clock.getHours())}:{pad(clock.getMinutes())}:{pad(clock.getSeconds())}
                      <span className="ml-3 text-sm font-medium text-slate-500">
                        {clock.getFullYear()}-{pad(clock.getMonth() + 1)}-{pad(clock.getDate())}
                      </span>
                    </div>
                    <div className="mt-0.5 font-mono text-[11px] text-slate-500">
                      GMT {pad(clock.getUTCHours())}:{pad(clock.getUTCMinutes())}:{pad(clock.getUTCSeconds())}
                    </div>
                  </div>
                  <button type="button" onClick={() => { setAllTimeNow(); notify('ok', 'All time fields set to the current time.'); }} className={btnPrimary}>
                    <Clock size={14} /> Set all time fields to now
                  </button>
                </div>

                <div className="flex flex-wrap items-end gap-2">
                  <div className="min-w-[14rem] flex-1">
                    <label className={labelCls}>Use a specific date and time instead</label>
                    <input
                      type="datetime-local"
                      step={1}
                      value={pickedTime}
                      onChange={(e) => setPickedTime(e.target.value)}
                      className={inputCls}
                    />
                  </div>
                  <button type="button" onClick={() => setPickedTime(toLocalInput(new Date()))} className={btnGhost}>
                    Use current
                  </button>
                  <button type="button" onClick={applyPickedTime} className={btnGhost}>
                    Apply to time fields
                  </button>
                </div>

                <div className="space-y-2">
                  {TIME_KEYS.map((k) => {
                    const meta = TIME_META[k];
                    const present = k in fields;
                    const off = enabledFields[k] === false;
                    return (
                      <div
                        key={k}
                        className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-950/40 p-2.5 text-xs"
                      >
                        <span className="w-12 font-mono font-bold text-emerald-600 dark:text-emerald-400">DE{k}</span>
                        <div className="w-48">
                          <div className="text-slate-700 dark:text-slate-200">{meta.label}</div>
                          <div className="text-[10px] text-slate-400">{meta.hint}</div>
                        </div>
                        {present ? (
                          <input
                            value={fields[k]}
                            onChange={(e) => setFields({ ...fields, [k]: e.target.value })}
                            disabled={off}
                            className={`${inputCls} !w-auto min-w-[8rem] flex-1`}
                          />
                        ) : (
                          <span className="min-w-[8rem] flex-1 text-[11px] text-slate-400">Not in the message yet</span>
                        )}
                        <button
                          type="button"
                          onClick={() => setTimeNow([k])}
                          className="inline-flex items-center gap-1 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-2.5 py-1 text-[11px] font-semibold text-emerald-600 dark:text-emerald-400 hover:bg-emerald-500/20 transition"
                        >
                          <Clock size={11} /> {present ? 'Now' : 'Add and set to now'}
                        </button>
                      </div>
                    );
                  })}
                </div>
                <p className="text-[11px] leading-relaxed text-slate-500">
                  DE7 uses GMT. DE12, DE13, DE15, DE16 and DE17 use the local time of this computer. DE14 is the card
                  expiry date and is never changed here.
                </p>
              </div>
            )}

            {/* =================== TAB: SAVED CASES =================== */}
            {activeTab === 'cases' && (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center gap-2">
                  <div className="relative min-w-[14rem] flex-1">
                    <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                    <input
                      value={caseFilter}
                      onChange={(e) => setCaseFilter(e.target.value)}
                      placeholder="Search saved cases"
                      className={`${inputCls} !pl-8`}
                    />
                  </div>
                  <button type="button" onClick={openSaveDialog} className={btnPrimary}>
                    <Save size={14} /> Save current as case
                  </button>
                </div>

                {optionRow(
                  caseOpts,
                  setCaseOpts,
                  'Use the next free STAN and RRN from the database when I open a case',
                  'Set the time fields to the current time when I open a case'
                )}

                {filteredCases.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-slate-300 dark:border-slate-700 p-8 text-center text-xs text-slate-500">
                    {savedCases.length === 0
                      ? 'No saved cases yet. Set up a transaction, then press Save case to keep it.'
                      : 'No saved case matches your search.'}
                  </div>
                ) : (
                  <div className="max-h-[460px] space-y-2 overflow-y-auto pr-1">
                    {filteredCases.map((c) => (
                      <div
                        key={c.id}
                        className={`flex flex-wrap items-center justify-between gap-3 rounded-xl border p-3 text-xs ${
                          c.id === currentCaseId
                            ? 'border-emerald-500/60 bg-emerald-500/5'
                            : 'border-slate-200 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-950/40'
                        }`}
                      >
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="truncate text-sm font-semibold text-slate-800 dark:text-slate-100">{c.name}</span>
                            <span className="rounded bg-slate-200 dark:bg-slate-800 px-1.5 py-0.5 font-mono text-[10px]">MTI {c.mti}</span>
                            {c.transaction_code && (
                              <span className="rounded bg-slate-200 dark:bg-slate-800 px-1.5 py-0.5 font-mono text-[10px]">Code {c.transaction_code}</span>
                            )}
                            <span className="rounded bg-slate-200 dark:bg-slate-800 px-1.5 py-0.5 font-mono text-[10px]">{c.field_count} fields</span>
                          </div>
                          {c.description && <div className="mt-1 text-slate-500 dark:text-slate-400">{c.description}</div>}
                          <div className="mt-1 text-[10px] text-slate-400">
                            Saved {c.updated_at ? new Date(c.updated_at).toLocaleString() : ''}
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <button type="button" onClick={() => loadCase(c)} className={btnGhost}>
                            <FolderOpen size={13} /> Open
                          </button>
                          <button
                            type="button"
                            onClick={() => deleteCase(c)}
                            className="rounded-lg p-1.5 text-slate-400 hover:bg-rose-500/10 hover:text-rose-500 transition"
                            title="Delete this case"
                            aria-label={`Delete ${c.name}`}
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* ------------------------------ Right column ------------------------------ */}
        <div className="space-y-5 lg:col-span-5">
          {/* Raw message */}
          <div className={`${cardCls} space-y-3 p-5`}>
            <div className="flex items-center justify-between gap-2">
              <h2 className="text-sm font-bold">Wire message</h2>
              <div className="flex gap-2">
                <button type="button" onClick={handleDecodeRaw} className={btnGhost}>
                  Decode into fields
                </button>
                <button type="button" onClick={copyRaw} className={btnGhost} title="Copy the raw message" aria-label="Copy the raw message">
                  {copied ? <Check size={13} className="text-emerald-500" /> : <Copy size={13} />}
                </button>
              </div>
            </div>
            <textarea
              rows={4}
              value={rawTic}
              onChange={(e) => setRawTic(e.target.value)}
              placeholder="Build and validate to generate the TIC message, or paste one here and decode it."
              spellCheck={false}
              className="w-full resize-y rounded-lg border border-slate-800 bg-slate-950 p-3 font-mono text-xs text-emerald-300 placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-emerald-500/40"
            />
            {compactTic && (
              <div>
                <div className="mb-1 text-[11px] font-medium text-slate-500 dark:text-slate-400">
                  Compact TIC format (Ý and ³ delimiters)
                </div>
                <div className="break-all rounded-lg border border-slate-800 bg-slate-950 p-2.5 font-mono text-[11px] text-amber-300">
                  {compactTic}
                </div>
              </div>
            )}
          </div>

          {/* Host outcome */}
          {txResponse && (
            <div className={`${cardCls} space-y-4 p-5`}>
              <div className="flex items-center justify-between gap-3 border-b border-slate-200 dark:border-slate-800 pb-3">
                <div className="min-w-0">
                  <div className="truncate font-mono text-xs text-slate-400">{txResponse.transaction_reference}</div>
                  <div className="mt-0.5 font-mono text-base font-bold">
                    RC {txResponse.response_code} ({txResponse.response_tic_f39}): {txResponse.response_message}
                  </div>
                </div>
                <span
                  className={`shrink-0 rounded-full px-3 py-1 font-mono text-xs font-bold ${
                    txResponse.authorization_status === 'APPROVED'
                      ? 'border border-emerald-500/30 bg-emerald-500/15 text-emerald-500'
                      : 'border border-rose-500/30 bg-rose-500/15 text-rose-500'
                  }`}
                >
                  {txResponse.authorization_status}
                </span>
              </div>

              <div className="grid grid-cols-2 gap-2 font-mono text-xs">
                <div className="rounded-lg bg-slate-50 dark:bg-slate-950 p-2">
                  <span className="text-slate-400">Response MTI:</span> {txResponse.response_mti}
                </div>
                <div className="rounded-lg bg-slate-50 dark:bg-slate-950 p-2">
                  <span className="text-slate-400">Switch and route:</span>{' '}
                  <span className="font-bold text-emerald-500">{txResponse.ps_code || 'ITCL'}</span> ({txResponse.is_on_us ? 'ON-US' : 'OFF-US'})
                </div>
                <div className="col-span-2 rounded-lg bg-slate-50 dark:bg-slate-950 p-2">
                  <span className="text-slate-400">New balance:</span>{' '}
                  {txResponse.account_balance_after !== null && txResponse.account_balance_after !== undefined
                    ? `${txResponse.account_balance_after.toLocaleString()} ${txResponse.currency}`
                    : 'Unchanged'}
                </div>
              </div>

              <div>
                <div className="mb-2 text-xs font-medium text-slate-500 dark:text-slate-400">
                  Host execution trace ({txResponse.checks?.length || 0} steps)
                </div>
                <div className="max-h-64 space-y-1.5 overflow-y-auto">
                  {(txResponse.checks || []).map((c: any) => (
                    <div
                      key={c.check_order}
                      className="flex items-start justify-between gap-2 rounded-lg border border-slate-200/60 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 p-2 font-mono text-xs"
                    >
                      <div>
                        <span className="mr-1.5 font-bold text-slate-400">#{c.check_order}</span>
                        <span className="font-bold">{c.check_name}:</span>{' '}
                        <span className="text-slate-500 dark:text-slate-300">{c.message}</span>
                      </div>
                      <span
                        className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold ${
                          c.check_status === 'PASSED' ? 'bg-emerald-500/10 text-emerald-500' : 'bg-rose-500/10 text-rose-500'
                        }`}
                      >
                        {c.check_status} (RC {c.response_code})
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Decoded view */}
          {decodedView && (
            <div className={`${cardCls} space-y-2 p-5`}>
              <h3 className="text-xs font-medium text-slate-500 dark:text-slate-400">Decoded TIC v2.164e structure</h3>
              <pre className="max-h-60 overflow-auto rounded-lg bg-slate-950 p-3 font-mono text-[11px] text-sky-300">
                {JSON.stringify(decodedView.detailed_fields || decodedView, null, 2)}
              </pre>
            </div>
          )}
        </div>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Save dialog                                                          */}
      {/* ------------------------------------------------------------------ */}
      {saveOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
          onClick={() => !saving && setSaveOpen(false)}
          role="dialog"
          aria-modal="true"
          aria-label="Save case"
        >
          <div
            className="w-full max-w-md space-y-4 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-bold">Save case</h2>
              <button type="button" onClick={() => setSaveOpen(false)} className="rounded p-1 text-slate-400 hover:text-slate-700 dark:hover:text-white" aria-label="Close">
                <X size={16} />
              </button>
            </div>
            <div>
              <label className={labelCls}>Case name</label>
              <input
                autoFocus
                value={saveName}
                onChange={(e) => setSaveName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && saveCase(!currentCaseId)}
                placeholder="ATM withdrawal with wrong PIN"
                className={inputCls}
              />
            </div>
            <div>
              <label className={labelCls}>Notes (optional)</label>
              <textarea
                rows={3}
                value={saveDesc}
                onChange={(e) => setSaveDesc(e.target.value)}
                placeholder="What this case checks"
                className={inputCls}
              />
            </div>
            <p className="text-[11px] text-slate-500">
              Saves the message type, transaction code, PIN helper, every field and which fields are switched on or off.
            </p>
            <div className="flex flex-wrap justify-end gap-2">
              <button type="button" onClick={() => setSaveOpen(false)} className={btnGhost} disabled={saving}>
                Cancel
              </button>
              {currentCaseId && (
                <button type="button" onClick={() => saveCase(true)} className={btnGhost} disabled={saving}>
                  Save as new case
                </button>
              )}
              <button type="button" onClick={() => saveCase(!currentCaseId)} className={btnPrimary} disabled={saving}>
                <Save size={14} /> {saving ? 'Saving...' : currentCaseId ? 'Update case' : 'Save case'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Toast */}
      {toast && (
        <div
          role="status"
          className={`fixed bottom-5 right-5 z-50 flex max-w-sm items-start gap-2 rounded-xl border px-4 py-3 text-xs font-medium shadow-xl ${
            toast.kind === 'ok'
              ? 'border-emerald-500/40 bg-emerald-950 text-emerald-200'
              : toast.kind === 'err'
              ? 'border-rose-500/40 bg-rose-950 text-rose-200'
              : 'border-slate-600 bg-slate-900 text-slate-200'
          }`}
        >
          {toast.kind === 'ok' ? <Check size={14} className="mt-0.5 shrink-0" /> : toast.kind === 'err' ? <AlertTriangle size={14} className="mt-0.5 shrink-0" /> : <Zap size={14} className="mt-0.5 shrink-0" />}
          <span>{toast.text}</span>
        </div>
      )}
    </div>
  );
};

'''


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def to_lf(text):
    return text.replace("\r\n", "\n").replace("\r", "\n")


def to_crlf(text):
    return to_lf(text).replace("\n", "\r\n")


def find_root(cli_root):
    candidates = []
    if cli_root:
        candidates.append(Path(cli_root))
    here = Path(__file__).resolve().parent
    candidates += [here, here.parent, Path.cwd(), Path.cwd().parent] + FALLBACK_ROOTS
    for c in candidates:
        try:
            if (c / "backend" / "app").is_dir() and (c / "frontend" / "src").is_dir():
                return c.resolve()
        except OSError:
            continue
    return None


class Session:
    def __init__(self, root, dry_run):
        self.root = root
        self.dry_run = dry_run
        self.stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.backup_dir = root / "_backups" / ("%s_%s" % (STEP_ID, self.stamp))
        self.records = []
        self.failed = False
        self.backed_up = False

    def path(self, rel):
        return self.root / rel

    def read(self, rel):
        return self.path(rel).read_text(encoding="utf-8", errors="replace")

    def exists(self, rel):
        return self.path(rel).exists()

    def _backup(self, rel):
        src = self.path(rel)
        if not src.exists() or self.dry_run:
            return
        dest = self.backup_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        self.backed_up = True

    def write(self, rel, text, label):
        """Write `text` (converted to CRLF like the rest of the project)."""
        target = self.path(rel)
        new_text = to_crlf(text)
        action = "CREATE"
        if target.exists():
            old = to_crlf(target.read_text(encoding="utf-8", errors="replace"))
            if old == new_text:
                self.records.append((label, rel, "SKIPPED (already up to date)"))
                print("  [SKIP]    %s (already up to date)" % rel)
                return True
            action = "UPDATE"
        if self.dry_run:
            self.records.append((label, rel, "DRY-RUN " + action))
            print("  [DRY-RUN] would %s %s" % (action.lower(), rel))
            return True
        try:
            self._backup(rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "w", encoding="utf-8", newline="") as fh:
                fh.write(new_text)
            if target.suffix.lower() == ".py":
                py_compile.compile(str(target), doraise=True)
            self.records.append((label, rel, action + "D"))
            print("  [%s] %s" % (action, rel))
            return True
        except Exception as exc:  # noqa: BLE001
            self.failed = True
            self.records.append((label, rel, "FAILED: %s" % exc))
            print("  [ERROR]   %s: %s" % (rel, exc))
            return False


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------
def step_backend_files(s):
    print("\n[1/4] Backend files")
    s.write("backend/app/simulator_workbench_router.py", ROUTER_PY, "router")
    s.write("backend/tests/test_simulator_workbench.py", TEST_PY, "tests")


def step_patch_main(s):
    print("\n[2/4] Register the router in backend/app/main.py")
    rel = "backend/app/main.py"
    if not s.exists(rel):
        s.failed = True
        print("  [ERROR] %s not found" % rel)
        return
    text = to_lf(s.read(rel))
    if "simulator_workbench_router" in text:
        s.records.append(("main.py", rel, "SKIPPED (already registered)"))
        print("  [SKIP]    router already registered")
        return
    block = (
        "# [PATCH %s:main_router]\n"
        "from app.simulator_workbench_router import router as simulator_workbench_router\n"
        "app.include_router(simulator_workbench_router)\n" % STEP_ID
    )
    anchors = ["app.include_router(transaction_logs_router)\n", "app.include_router(router)\n"]
    new_text = None
    for anchor in anchors:
        if text.count(anchor) == 1:
            new_text = text.replace(anchor, anchor + block, 1)
            break
    if new_text is None:
        # no known anchor: append at the end of the module, which is valid Python
        new_text = text.rstrip("\n") + "\n\n" + block
        print("  [INFO] anchor not found, registered the router at the end of main.py")
    s.write(rel, new_text, "main.py")


def _merge_lucide_imports(head, original_text, tail):
    """Keep every lucide icon that the untouched journal/details pages still use."""
    m_orig = re.search(r"import\s*\{([^}]*)\}\s*from\s*'lucide-react';", original_text)
    m_head = re.search(r"import\s*\{([^}]*)\}\s*from\s*'lucide-react';", head)
    if not m_orig or not m_head:
        return head
    orig_names = [n.strip() for n in m_orig.group(1).split(",") if n.strip()]
    head_names = [n.strip() for n in m_head.group(1).split(",") if n.strip()]
    extra = [n for n in orig_names if n not in head_names and re.search(r"\b%s\b" % re.escape(n), tail)]
    if not extra:
        return head
    merged = sorted(set(head_names + extra))
    new_import = "import {\n" + "".join("  %s,\n" % n for n in merged) + "} from 'lucide-react';"
    print("  [INFO] kept extra icons used by the other pages: %s" % ", ".join(extra))
    return head[: m_head.start()] + new_import + head[m_head.end():]


def step_frontend_page(s):
    print("\n[3/4] Transaction Simulator page")
    rel = "frontend/src/pages/SimulatorAndJournal.tsx"
    if not s.exists(rel):
        s.failed = True
        print("  [ERROR] %s not found" % rel)
        return
    original = to_lf(s.read(rel))
    divider = re.search(r"^// =+\n// PAGE 9: TRANSACTION JOURNAL", original, re.M)
    if not divider:
        s.failed = True
        print("  [ERROR] Could not find the 'PAGE 9: TRANSACTION JOURNAL' divider in %s." % rel)
        print("          The file was left untouched.")
        return
    tail = original[divider.start():]
    head = to_lf(SIMULATOR_PAGE_HEAD).rstrip("\n") + "\n\n"
    head = _merge_lucide_imports(head, original, tail)
    new_text = "// [PATCH %s:simulator_page]\n" % STEP_ID + head + tail
    for needed in (
        "export const TransactionSimulatorPage",
        "export const TransactionJournalPage",
        "export const TransactionDetailsPage",
    ):
        if needed not in new_text:
            s.failed = True
            print("  [ERROR] Result would be missing '%s'. The file was left untouched." % needed)
            return
    s.write(rel, new_text, "simulator page")


def step_docs(s):
    print("\n[4/4] Progress log and contracts")
    entries = [
        (
            "PROGRESS.md",
            "<!-- PROGRESS:%s -->" % STEP_ID,
            "\n".join(
                [
                    "<!-- PROGRESS:%s -->" % STEP_ID,
                    "## [%s] `%s` - Simulator workbench upgrade" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), STEP_ID),
                    "- **Touched Files**: `backend/app/simulator_workbench_router.py`, `backend/app/main.py`, "
                    "`frontend/src/pages/SimulatorAndJournal.tsx`, `backend/tests/test_simulator_workbench.py`",
                    "- [x] **Completed**: Paste or load a raw TIC / ISO 8583 message (text box, drag and drop, or file) and unpack every field into the editor.",
                    "- [x] **Completed**: STAN (DE11) and RRN (DE37) start from the next free values after the last transaction in the database.",
                    "- [x] **Completed**: Time fields have Now buttons; a Date and time tab sets all of them at once.",
                    "- [x] **Completed**: Last session is restored on open; named cases can be saved, opened and deleted.",
                    "- [x] **Completed**: Removed the Load Real Backend Test Scenario bar and redesigned the page.",
                    "- **Known Issues**: None",
                    "",
                ]
            ),
        ),
        (
            "docs/CONTRACTS.md",
            "<!-- CONTRACT:%s -->" % STEP_ID,
            "\n".join(
                [
                    "<!-- CONTRACT:%s -->" % STEP_ID,
                    "## `%s` - Simulator workbench" % STEP_ID,
                    "- **Table**: `simulator_saved_cases` (id, name unique, description, mti, transaction_code, clear_pin_helper, fields JSON, enabled_fields JSON, created_at, updated_at)",
                    "- **GET /api/simulator-workbench/next-ids**: last STAN/RRN in `transactions` and the next free values",
                    "- **GET/POST /api/simulator-workbench/cases**, **GET/PUT/DELETE /api/simulator-workbench/cases/{id}**: saved simulator cases (POST returns 409 for a duplicate name unless `overwrite` is true)",
                    "- **Browser storage**: key `BAOBAB_SIMULATOR_STATE_V2` (localStorage) holds the last simulator session",
                    "",
                ]
            ),
        ),
    ]
    for rel, marker, block in entries:
        if not s.exists(rel):
            print("  [SKIP]    %s not found" % rel)
            continue
        text = to_lf(s.read(rel))
        if marker in text:
            print("  [SKIP]    %s already has this entry" % rel)
            continue
        s.write(rel, text.rstrip("\n") + "\n\n" + block, rel)


def main():
    parser = argparse.ArgumentParser(description="Install the Transaction Simulator workbench upgrade")
    parser.add_argument("--dry-run", action="store_true", help="show changes without writing any file")
    parser.add_argument("--root", help="project root (folder that contains backend and frontend)")
    args = parser.parse_args()

    root = find_root(args.root)
    if root is None:
        print("Could not find the project root (a folder that contains backend/app and frontend/src).")
        print("Put this file in your project root or run:  python install_simulator_upgrade.py --root <folder>")
        return 2

    print("=" * 78)
    print("  Simulator workbench upgrade%s" % ("  (DRY RUN)" if args.dry_run else ""))
    print("  Project root: %s" % root)
    print("=" * 78)

    s = Session(root, args.dry_run)
    step_backend_files(s)
    step_patch_main(s)
    step_frontend_page(s)
    step_docs(s)

    print("\n" + "=" * 78)
    for label, rel, status in s.records:
        print("  %-16s %-52s %s" % (label, rel, status))
    if s.backed_up and not args.dry_run:
        print("\n  Backups: %s" % s.backup_dir.relative_to(root))
    print("=" * 78)
    if s.failed:
        print("  RESULT: FAILED. See the errors above. Files that failed were not changed.")
        return 1
    print("  RESULT: SUCCESS")
    if not args.dry_run:
        print("\n  Next steps")
        print("    1. Restart the backend (python scripts/run_local.py, or your usual command).")
        print("       The saved-cases table is created automatically on start-up.")
        print("    2. Restart or rebuild the frontend (npm run dev) and hard-refresh the browser (Ctrl+F5).")
        print("    3. Optional: run the new tests  ->  cd backend && pytest tests/test_simulator_workbench.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
