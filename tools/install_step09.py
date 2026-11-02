#!/usr/bin/env python3
"""
INSTALLER: tools/install_step09.py
STEP 9 — Simulator Improvements: Persistent State & Dual-Codec Parser (Single Unified Installer)
Adds:
  1. Standard ISO 8583:1987 parser & builder in backend/app/iso_standard_codec.py
  2. Schemas in backend/app/schemas.py
  3. POST /api/simulator/parse-raw endpoint in backend/app/api_routes.py
  4. SessionStorage persistence & auto-restore in frontend/src/pages/SimulatorAndJournal.tsx
  5. Automated Pytest test suite in backend/tests/test_step09_simulator_improvements.py
"""

from pathlib import Path
import sys

BASE_DIR = Path(r"E:\HOST_VSCODE\host-simulator").resolve()
sys.path.insert(0, str(BASE_DIR))

from tools.patcher import PatcherSession, parse_installer_args

ISO_STANDARD_CODEC_CODE = '''"""
iso_standard_codec.py — Standard ISO 8583:1987 Message Codec
Supports ASCII bitmap, Hex bitmap, primary/secondary bitmaps, LLVAR/LLLVAR, and packing/unpacking.
"""

import re
from typing import Any, Dict, List, Optional, Tuple

# Standard ISO 8583:1987 field definitions
# Format: field_num: (name, data_type, length_type, fixed_length)
ISO8583_FIELDS: Dict[int, Tuple[str, str, str, Optional[int]]] = {
    2:   ("Primary Account Number (PAN)",        "N",   "LLVAR",  19),
    3:   ("Processing Code",                     "N",   "FIXED",  6),
    4:   ("Amount, Transaction",                 "N",   "FIXED",  12),
    7:   ("Transmission Date & Time",            "N",   "FIXED",  10),
    11:  ("System Trace Audit Number (STAN)",    "N",   "FIXED",  6),
    12:  ("Time, Local Transaction",             "N",   "FIXED",  6),
    13:  ("Date, Local Transaction",             "N",   "FIXED",  4),
    14:  ("Date, Expiration",                    "N",   "FIXED",  4),
    18:  ("Merchant Category Code (MCC)",        "N",   "FIXED",  4),
    22:  ("Point of Service Entry Mode",         "N",   "FIXED",  3),
    25:  ("Point of Service Condition Code",     "N",   "FIXED",  2),
    32:  ("Acquiring Institution ID",            "N",   "LLVAR",  11),
    35:  ("Track 2 Data",                        "ANS", "LLVAR",  37),
    37:  ("Retrieval Reference Number (RRN)",    "ANS", "FIXED",  12),
    38:  ("Authorization Identification Response","ANS","FIXED",  6),
    39:  ("Response Code",                       "ANS", "FIXED",  2),
    41:  ("Card Acceptor Terminal ID",           "ANS", "FIXED",  8),
    42:  ("Card Acceptor Identification Code",   "ANS", "FIXED",  15),
    43:  ("Card Acceptor Name/Location",         "ANS", "FIXED",  40),
    48:  ("Private Additional Data",             "ANS", "LLLVAR", 999),
    49:  ("Currency Code, Transaction",          "N",   "FIXED",  3),
    52:  ("Personal Identification Number Data", "HEX", "FIXED",  16),
    55:  ("ICC Related Data (EMV DE55)",         "HEX", "LLLVAR", 999),
    62:  ("Private Data, Custom",                "ANS", "LLLVAR", 999),
    64:  ("Primary MAC",                         "HEX", "FIXED",  16),
    70:  ("Network Management Information Code", "N",   "FIXED",  3),
    90:  ("Original Data Elements",              "N",   "FIXED",  42),
    102: ("Account Identification 1",            "ANS", "LLVAR",  28),
    103: ("Account Identification 2",            "ANS", "LLVAR",  28),
    128: ("Secondary MAC",                       "HEX", "FIXED",  16),
}


def decode_iso8583_1987(raw_msg: str) -> Dict[str, Any]:
    """
    Decodes a standard ISO 8583:1987 message with 16-hex or 32-hex bitmap.
    Returns parsed fields, MTI, warnings, and format metadata.
    """
    clean = raw_msg.strip().replace(" ", "").replace("\\n", "").replace("\\r", "")
    if len(clean) < 20:
        return {"valid": False, "error": "Message is too short for ISO 8583:1987", "format": "UNKNOWN"}

    mti = clean[:4]
    if not mti.isdigit():
        return {"valid": False, "error": f"Invalid ISO MTI: '{mti}'", "format": "UNKNOWN"}

    pos = 4
    # Read primary bitmap (16 hex chars = 64 bits)
    primary_hex = clean[pos : pos + 16]
    pos += 16

    try:
        bits = bin(int(primary_hex, 16))[2:].zfill(64)
    except Exception as exc:
        return {"valid": False, "error": f"Invalid primary bitmap hex: {exc}", "format": "ISO8583_1987"}

    has_secondary = bits[0] == "1"
    secondary_hex = None
    if has_secondary:
        secondary_hex = clean[pos : pos + 16]
        pos += 16
        sec_bits = bin(int(secondary_hex, 16))[2:].zfill(64)
        full_bits = bits + sec_bits
    else:
        full_bits = bits

    present_fields = [i + 1 for i, b in enumerate(full_bits) if b == "1" and i != 0]

    raw_fields: Dict[str, str] = {}
    detailed_fields: Dict[str, Any] = {}
    warnings: List[str] = []

    for fnum in present_fields:
        if fnum not in ISO8583_FIELDS:
            warnings.append(f"Field DE{fnum} present in bitmap but not defined in standard 1987 dictionary")
            break

        name, dtype, ltype, flen = ISO8583_FIELDS[fnum]
        try:
            if ltype == "FIXED":
                val = clean[pos : pos + flen]
                pos += flen
            elif ltype == "LLVAR":
                plen = int(clean[pos : pos + 2])
                pos += 2
                val = clean[pos : pos + plen]
                pos += plen
            elif ltype == "LLLVAR":
                plen = int(clean[pos : pos + 3])
                pos += 3
                val = clean[pos : pos + plen]
                pos += plen
            else:
                warnings.append(f"Unhandled length type {ltype} for DE{fnum}")
                break

            raw_fields[str(fnum)] = val
            detailed_fields[f"DE{fnum} {name}"] = val
        except Exception as exc:
            warnings.append(f"Error parsing field DE{fnum}: {exc}")
            break

    # Determine matched transaction code from DE3
    proc_code = raw_fields.get("3", "000000")
    tc_derived = proc_code[:2] if len(proc_code) >= 2 else "10"

    return {
        "valid": True,
        "format": "ISO8583_1987",
        "mti": mti,
        "bitmap": {
            "primary_hex": primary_hex,
            "secondary_hex": secondary_hex,
            "fields_present": present_fields,
        },
        "raw_fields": raw_fields,
        "detailed_fields": detailed_fields,
        "derived_transaction_code": tc_derived,
        "warnings": warnings,
    }


def build_iso8583_1987(mti: str, fields: Dict[int, str]) -> str:
    """Builds a standard ISO 8583:1987 message with hex bitmap."""
    clean_fields = {int(k): str(v) for k, v in fields.items() if v is not None and str(v) != ""}
    present_fnums = sorted(f for f in clean_fields.keys() if f != 1)
    needs_secondary = any(f > 64 for f in present_fnums)

    bits = ["0"] * (128 if needs_secondary else 64)
    if needs_secondary:
        bits[0] = "1"
    for f in present_fnums:
        if 1 <= f <= len(bits):
            bits[f - 1] = "1"

    bitmap_hex = "".join(f"{int(''.join(bits[i:i+4]), 2):X}" for i in range(0, len(bits), 4))
    body_parts = []

    for fnum in present_fnums:
        if fnum not in ISO8583_FIELDS:
            continue
        _, dtype, ltype, flen = ISO8583_FIELDS[fnum]
        val = clean_fields[fnum]

        if ltype == "FIXED" and flen is not None:
            if dtype == "N":
                val = val.zfill(flen)[:flen]
            else:
                val = val.ljust(flen)[:flen]
            body_parts.append(val)
        elif ltype == "LLVAR":
            body_parts.append(f"{len(val):02d}{val}")
        elif ltype == "LLLVAR":
            body_parts.append(f"{len(val):03d}{val}")

    return f"{mti}{bitmap_hex}{''.join(body_parts)}"
'''

TEST_STEP09_CODE = '''"""
test_step09_simulator_improvements.py — Tests for Step 9 Dual-Codec Parser & Persistent State
"""

import os
import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.database import Base, SessionLocal, engine
from app.main import app
from app.iso_standard_codec import build_iso8583_1987, decode_iso8583_1987
from app.iso_tic import build_tic_message
from app.seed_data import seed_initial_data
from app.security import create_access_token
from app.config import settings


@pytest.fixture()
def client():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    seed_initial_data(db)
    db.close()
    with TestClient(app) as c:
        token = create_access_token(subject=settings.ADMIN_USERNAME)
        c.headers = {"Authorization": f"Bearer {token}"}
        yield c
    Base.metadata.drop_all(bind=engine)


def test_standard_iso8583_pack_and_unpack():
    fields = {
        2: "4567890123450001",
        3: "010000",
        4: "000000100000",
        11: "123456",
        37: "000020526991",
        41: "ATM00001",
        49: "050"
    }
    raw = build_iso8583_1987("0200", fields)
    assert raw.startswith("0200")
    
    decoded = decode_iso8583_1987(raw)
    assert decoded["valid"] is True
    assert decoded["format"] == "ISO8583_1987"
    assert decoded["mti"] == "0200"
    assert decoded["raw_fields"]["2"] == "4567890123450001"
    assert decoded["raw_fields"]["11"] == "123456"
    assert decoded["derived_transaction_code"] == "01"


def test_parse_raw_endpoint_detects_tic_v2164e(client):
    # TIC message starts with A4M
    tic_raw, _ = build_tic_message("0200", {2: "4567890123450001", 3: "0100000", 4: "000000100000", 11: "998877", 49: "BDT"})
    res = client.post("/api/simulator/parse-raw", json={"raw_message": tic_raw})
    assert res.status_code == 200
    data = res.json()
    assert data["format"] == "TIC_V2164E"
    assert data["mti"] == "0200"
    assert data["fields"]["11"] == "998877"


def test_parse_raw_endpoint_detects_standard_iso8583(client):
    # Standard ISO message starts with 0200 + hex bitmap
    iso_raw = build_iso8583_1987("0200", {2: "4567890123450002", 3: "010000", 4: "000000250000", 11: "334455"})
    res = client.post("/api/simulator/parse-raw", json={"raw_message": iso_raw})
    assert res.status_code == 200
    data = res.json()
    assert data["format"] == "ISO8583_1987"
    assert data["mti"] == "0200"
    assert data["fields"]["2"] == "4567890123450002"
    assert data["fields"]["11"] == "334455"
'''


def main() -> int:
    args = parse_installer_args("Step 09: Simulator Improvements (Persistent State & Dual-Codec Parser)")
    session = PatcherSession(
        step_id="step09",
        title="Implement Standard ISO 8583:1987 Codec, Dual-Codec Parse-Raw Endpoint & Session Persistence",
        dry_run=args.dry_run,
    )

    # 1. Write backend/app/iso_standard_codec.py
    session.write_file("backend/app/iso_standard_codec.py", ISO_STANDARD_CODEC_CODE)

    # 2. Patch backend/app/schemas.py to add parse-raw schemas
    session.patch_file(
        "backend/app/schemas.py",
        [
            {
                "marker": "step09:schemas_parse_raw",
                "action": "append",
                "text": (
                    "\n# ==============================================================================\n"
                    "# STEP 9 SCHEMAS: DUAL-CODEC WIRE PARSER\n"
                    "# ==============================================================================\n\n"
                    "class RawMessageParseRequest(BaseModel):\n"
                    "    raw_message: str\n\n\n"
                    "class RawMessageParseResponse(BaseModel):\n"
                    "    valid: bool\n"
                    "    format: str  # TIC_V2164E, ISO8583_1987, UNKNOWN\n"
                    "    mti: str\n"
                    "    fields: Dict[str, str]\n"
                    "    detailed_fields: Dict[str, Any]\n"
                    "    derived_transaction_code: Optional[str] = None\n"
                    "    warnings: List[str] = Field(default_factory=list)\n"
                    "    error: Optional[str] = None\n"
                ),
            }
        ],
    )

    # 3. Patch backend/app/api_routes.py to add POST /api/simulator/parse-raw endpoint
    session.patch_file(
        "backend/app/api_routes.py",
        [
            {
                "marker": "step09:api_routes_iso_imports",
                "action": "insert_after",
                "anchor": "from app.schemas import (",
                "text": (
                    "    RawMessageParseRequest,\n"
                    "    RawMessageParseResponse,"
                ),
            },
            {
                "marker": "step09:api_routes_iso_standard_codec_import",
                "action": "insert_after",
                "anchor": "from app.iso_tic import build_tic_message, decode_tic_message, get_field_catalog, validate_tic_fields",
                "text": "from app.iso_standard_codec import decode_iso8583_1987, build_iso8583_1987",
            },
            {
                "marker": "step09:api_routes_parse_raw_endpoint",
                "action": "insert_after",
                "anchor": (
                    "@router.post(\"/simulator/decode\")\n"
                    "def simulator_decode_message(payload: Dict[str, str], _: str = Depends(get_current_user)):\n"
                    "    raw = payload.get(\"raw_tic_message\", \"\")\n"
                    "    return decode_tic_message(raw)"
                ),
                "text": (
                    "\n\n@router.post('/simulator/parse-raw', response_model=RawMessageParseResponse)\n"
                    "def parse_raw_wire_message(payload: RawMessageParseRequest, _: str = Depends(get_current_user)):\n"
                    "    msg = payload.raw_message.strip()\n"
                    "    # Check if message is Compass Plus TIC/TCI (starts with A4M or contains A4M)\n"
                    "    if 'A4M' in msg:\n"
                    "        decoded = decode_tic_message(msg)\n"
                    "        if not decoded.get('valid'):\n"
                    "            return RawMessageParseResponse(\n"
                    "                valid=False,\n"
                    "                format='TIC_V2164E',\n"
                    "                mti=decoded.get('mti', '0200'),\n"
                    "                fields={},\n"
                    "                detailed_fields={},\n"
                    "                error=decoded.get('error', 'Invalid TIC message structure'),\n"
                    "            )\n"
                    "        # Derive tran code from F3 (prefix)\n"
                    "        raw_f = decoded.get('raw_fields', {})\n"
                    "        f3 = raw_f.get('3', '010')\n"
                    "        tc = f3[:3].lstrip('0') or '10'\n"
                    "        return RawMessageParseResponse(\n"
                    "            valid=True,\n"
                    "            format='TIC_V2164E',\n"
                    "            mti=decoded.get('mti', '0200'),\n"
                    "            fields=raw_f,\n"
                    "            detailed_fields=decoded.get('detailed_fields', {}),\n"
                    "            derived_transaction_code=tc,\n"
                    "            warnings=decoded.get('warnings', []),\n"
                    "        )\n\n"
                    "    # Otherwise parse as standard ISO 8583:1987 (starts with 4-digit MTI)\n"
                    "    iso_dec = decode_iso8583_1987(msg)\n"
                    "    if iso_dec.get('valid'):\n"
                    "        return RawMessageParseResponse(\n"
                    "            valid=True,\n"
                    "            format='ISO8583_1987',\n"
                    "            mti=iso_dec['mti'],\n"
                    "            fields=iso_dec['raw_fields'],\n"
                    "            detailed_fields=iso_dec['detailed_fields'],\n"
                    "            derived_transaction_code=iso_dec.get('derived_transaction_code', '10'),\n"
                    "            warnings=iso_dec.get('warnings', []),\n"
                    "        )\n\n"
                    "    return RawMessageParseResponse(\n"
                    "        valid=False,\n"
                    "        format='UNKNOWN',\n"
                    "        mti='0200',\n"
                    "        fields={},\n"
                    "        detailed_fields={},\n"
                    "        error='Unable to auto-detect message format (neither Compass Plus A4M TIC nor Standard ISO 8583)',\n"
                    "    )\n"
                ),
            },
        ],
    )

    # 4. Patch frontend/src/pages/SimulatorAndJournal.tsx with sessionStorage persistence and parse-raw dialog
    session.patch_file(
        "frontend/src/pages/SimulatorAndJournal.tsx",
        [
            # Add state restored indicator & persistence hooks
            {
                "marker": "step09:simulator_persistence_state",
                "action": "insert_after",
                "anchor": "  const [submitting, setSubmitting] = useState(false);",
                "text": (
                    "  const [sessionRestored, setSessionRestored] = useState(false);\n"
                    "  const [parseModalOpen, setParseModalOpen] = useState(false);\n"
                    "  const [rawToParse, setRawToParse] = useState('');\n"
                    "  const [detectedFormat, setDetectedFormat] = useState('');"
                ),
            },
            # Load from sessionStorage on initial mount
            {
                "marker": "step09:simulator_load_session_storage",
                "action": "insert_after",
                "anchor": "  useEffect(() => {\n    apiFetch('/simulator/catalog').then(setCatalog).catch(console.error);\n  }, []);",
                "text": (
                    "\n  // Step 9: Restore persistent state from sessionStorage on mount\n"
                    "  useEffect(() => {\n"
                    "    try {\n"
                    "      const saved = sessionStorage.getItem('BAOBAB_SIMULATOR_STATE');\n"
                    "      if (saved) {\n"
                    "        const s = JSON.parse(saved);\n"
                    "        if (s.fields) setFields(s.fields);\n"
                    "        if (s.txCode) setTxCode(s.txCode);\n"
                    "        if (s.mti) setMti(s.mti);\n"
                    "        if (s.clearPinHelper) setClearPinHelper(s.clearPinHelper);\n"
                    "        if (s.enabledFields) setEnabledFields(s.enabledFields);\n"
                    "        if (s.rawTic) setRawTic(s.rawTic);\n"
                    "        if (s.compactTic) setCompactTic(s.compactTic);\n"
                    "        if (s.txResponse) setTxResponse(s.txResponse);\n"
                    "        setSessionRestored(true);\n"
                    "      }\n"
                    "    } catch (e) {\n"
                    "      console.warn('Could not restore simulator state', e);\n"
                    "    }\n"
                    "  }, []);\n\n"
                    "  // Persist simulator state to sessionStorage whenever fields/options change\n"
                    "  useEffect(() => {\n"
                    "    try {\n"
                    "      sessionStorage.setItem('BAOBAB_SIMULATOR_STATE', JSON.stringify({\n"
                    "        fields,\n"
                    "        txCode,\n"
                    "        mti,\n"
                    "        clearPinHelper,\n"
                    "        enabledFields,\n"
                    "        rawTic,\n"
                    "        compactTic,\n"
                    "        txResponse,\n"
                    "      }));\n"
                    "    } catch (e) {}\n"
                    "  }, [fields, txCode, mti, clearPinHelper, enabledFields, rawTic, compactTic, txResponse]);\n\n"
                    "  const resetToDefaults = () => {\n"
                    "    sessionStorage.removeItem('BAOBAB_SIMULATOR_STATE');\n"
                    "    setTxCode('10');\n"
                    "    setMti('0200');\n"
                    "    setClearPinHelper('1234');\n"
                    "    setFields({\n"
                    "      '2': '4567890123450001',\n"
                    "      '3': '0100000',\n"
                    "      '4': '000000250000',\n"
                    "      '7': '1031123000',\n"
                    "      '11': '100001',\n"
                    "      '12': '123000',\n"
                    "      '13': '1031',\n"
                    "      '14': '2812',\n"
                    "      '18': '5411',\n"
                    "      '22': '051',\n"
                    "      '25': '000',\n"
                    "      '32': '123456',\n"
                    "      '37': '000020526001',\n"
                    "      '41': 'ATM00001',\n"
                    "      '49': 'BDT',\n"
                    "    });\n"
                    "    setTxResponse(null);\n"
                    "    setRawTic('');\n"
                    "    setCompactTic('');\n"
                    "    setSessionRestored(false);\n"
                    "  };\n\n"
                    "  const handleParseRawWire = async () => {\n"
                    "    if (!rawToParse.trim()) return;\n"
                    "    try {\n"
                    "      const res = await apiFetch('/simulator/parse-raw', {\n"
                    "        method: 'POST',\n"
                    "        body: JSON.stringify({ raw_message: rawToParse }),\n"
                    "      });\n"
                    "      if (!res.valid) {\n"
                    "        alert(res.error || 'Failed to parse raw wire message');\n"
                    "        return;\n"
                    "      }\n"
                    "      setDetectedFormat(res.format);\n"
                    "      setMti(res.mti);\n"
                    "      if (res.derived_transaction_code) setTxCode(res.derived_transaction_code);\n"
                    "      setFields(res.fields);\n"
                    "      const en: Record<string, boolean> = {};\n"
                    "      Object.keys(res.fields).forEach((k) => (en[k] = true));\n"
                    "      setEnabledFields(en);\n"
                    "      setRawTic(rawToParse);\n"
                    "      setParseModalOpen(false);\n"
                    "    } catch (err: any) {\n"
                    "      alert(err.message);\n"
                    "    }\n"
                    "  };\n"
                ),
            },
            # Add Persistence Badge, Reset Button, and Parse Raw Button in Simulator Header
            {
                "marker": "step09:simulator_header_buttons",
                "action": "insert_before",
                "anchor": "          <button\n            onClick={bumpStanAndRrn}",
                "text": (
                    '          {sessionRestored && (\n'
                    '            <span className="flex items-center gap-1 text-[11px] font-mono px-2.5 py-1 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-bold">\n'
                    '              ✓ Session Restored\n'
                    '            </span>\n'
                    '          )}\n'
                    '          <button\n'
                    '            onClick={() => setParseModalOpen(true)}\n'
                    '            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold"\n'
                    '          >\n'
                    '            Universal Wire Parser (TIC/ISO)\n'
                    '          </button>\n'
                    '          <button\n'
                    '            onClick={resetToDefaults}\n'
                    '            className="px-2.5 py-1.5 rounded-lg bg-slate-200 dark:bg-slate-800 text-xs font-mono hover:bg-slate-300 dark:hover:bg-slate-700"\n'
                    '            title="Reset Simulator to default values"\n'
                    '          >\n'
                    '            Reset Defaults\n'
                    '          </button>\n'
                ),
            },
            # Render Parse Raw Modal in Simulator Page
            {
                "marker": "step09:simulator_render_parse_modal",
                "action": "insert_before",
                "anchor": "      {/* Sample Scenarios Bar */}",
                "text": (
                    '      {parseModalOpen && (\n'
                    '        <div className="fixed inset-0 bg-black/60 flex items-center justify-center p-4 z-50">\n'
                    '          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-6 max-w-xl w-full space-y-4 shadow-2xl">\n'
                    '            <div className="flex justify-between items-center border-b border-slate-200 dark:border-slate-800 pb-3">\n'
                    '              <h2 className="text-sm font-bold">Universal Wire Message Parser</h2>\n'
                    '              <button onClick={() => setParseModalOpen(false)} className="text-slate-400 hover:text-white text-lg">×</button>\n'
                    '            </div>\n'
                    '            <p className="text-xs text-slate-500 font-sans">\n'
                    '              Paste any raw wire string below. The host will auto-detect whether it is a Compass Plus TIC/TCI v2.164e message (A4M header) or standard ISO 8583:1987 message with hex bitmap, unpack all fields, and load them directly into your simulator editor.\n'
                    '            </p>\n'
                    '            <textarea\n'
                    '              rows={4}\n'
                    '              value={rawToParse}\n'
                    '              onChange={(e) => setRawToParse(e.target.value)}\n'
                    '              placeholder="Paste raw string here (e.g. A4M0200... or 0200702004...)"\n'
                    '              className="w-full bg-slate-950 text-emerald-300 border border-slate-800 rounded p-2.5 text-xs font-mono"\n'
                    '            />\n'
                    '            <div className="flex justify-between items-center pt-2 border-t border-slate-200 dark:border-slate-800">\n'
                    '              <div className="flex gap-2">\n'
                    '                <button\n'
                    '                  onClick={() => setRawToParse("02007220000008008000164567890123450001010000000000100000100001000020526001050")}\n'
                    '                  className="text-[11px] font-mono text-sky-400 hover:underline"\n'
                    '                >\n'
                    '                  Load Sample ISO 8583\n'
                    '                </button>\n'
                    '              </div>\n'
                    '              <div className="flex gap-2">\n'
                    '                <button onClick={() => setParseModalOpen(false)} className="px-3 py-1.5 rounded text-xs">Cancel</button>\n'
                    '                <button onClick={handleParseRawWire} className="bg-emerald-600 text-white px-4 py-1.5 rounded text-xs font-semibold">Parse & Load Fields</button>\n'
                    '              </div>\n'
                    '            </div>\n'
                    '          </div>\n'
                    '        </div>\n'
                    '      )}\n'
                ),
            },
        ],
    )

    # 5. Write automated pytest test suite backend/tests/test_step09_simulator_improvements.py
    session.write_file("backend/tests/test_step09_simulator_improvements.py", TEST_STEP09_CODE)

    session.record_progress(
        completed=[
            "Created `backend/app/iso_standard_codec.py` implementing standard ISO 8583:1987 parsing and building (ASCII/Hex primary and secondary bitmaps).",
            "Added Pydantic schemas `RawMessageParseRequest` and `RawMessageParseResponse` in `backend/app/schemas.py`.",
            "Added `POST /api/simulator/parse-raw` endpoint in `backend/app/api_routes.py` with automatic format detection between Compass Plus TIC/TCI v2.164e and Standard ISO 8583:1987.",
            "Added `sessionStorage` persistence, auto-restore indicator, and reset buttons in `frontend/src/pages/SimulatorAndJournal.tsx`.",
            "Added Universal Wire Parser modal in `frontend/src/pages/SimulatorAndJournal.tsx` to paste and unpack wire messages directly into the simulator fields.",
            "Created automated Pytest test suite `backend/tests/test_step09_simulator_improvements.py`.",
        ],
        remaining=[
            "STEP 10 — HSM Key Management (database-backed key ceremony, 2/3 component XOR key assembly, random key generation with odd parity, institution/switch ownership, and ZMK import).",
        ],
        modified_files=[
            "backend/app/iso_standard_codec.py",
            "backend/app/schemas.py",
            "backend/app/api_routes.py",
            "frontend/src/pages/SimulatorAndJournal.tsx",
            "backend/tests/test_step09_simulator_improvements.py",
        ],
    )

    session.record_contracts(
        section_title="Step 9 — Simulator Improvements & Dual-Codec Wire Parser",
        contract_items=[
            "**Module**: `backend/app/iso_standard_codec.py` (`decode_iso8583_1987`, `build_iso8583_1987`).",
            "**POST /api/simulator/parse-raw**: Accepts raw wire string, auto-detects `TIC_V2164E` (A4M) or `ISO8583_1987` (Hex bitmap), returns parsed fields and matched transaction code.",
            "**Client-Side Persistence**: Simulator fields, helper PIN, and transaction checks persist in browser `sessionStorage` (`BAOBAB_SIMULATOR_STATE`), surviving navigation and page refreshes.",
        ],
    )

    return session.finish()


if __name__ == "__main__":
    sys.exit(main())