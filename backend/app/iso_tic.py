"""
MODULE 7 — iso_tic.py
TIC / TCI ISO 8583 Message Decoder, Validator, Builder, and Response Formatter.
Directly preserves the Compass Plus TW International Interconnection Protocol (spec v.2.164e)
field definitions, lengths, encodings, and subfield parsers from `tic_decoder (1).py`.
"""

import re
from typing import Any, Dict, List, Optional, Tuple
from app.security import mask_pan, mask_raw_tic_message

# Exact field definitions from Compass Plus TW TIC/TCI Spec v.2.164e
FIELD_DEFS: Dict[int, Tuple[str, str, str, Optional[int]]] = {
    2:   ("PAN",                           "N",   "LLVAR",     None),
    3:   ("Processing Code",               "N",   "FIXED",     7),
    4:   ("Transaction Amount",            "N",   "FIXED",     12),
    5:   ("Settlement Amount",             "N",   "FIXED",     12),
    6:   ("Cardholder Billing Amount",     "N",   "FIXED",     12),
    7:   ("GMT Transmission Time",         "N",   "FIXED",     10),
    8:   ("Billing Fee Amount",            "N",   "FIXED",     8),
    9:   ("Settlement Conv Rate",          "N",   "FIXED",     8),
    10:  ("Cardholder Billing Conv Rate",  "N",   "FIXED",     8),
    11:  ("STAN",                          "N",   "FIXED",     6),
    12:  ("Local Transaction Time",        "N",   "FIXED",     6),
    13:  ("Local Transaction Date",        "N",   "FIXED",     4),
    14:  ("Expiration Date",               "N",   "FIXED",     4),
    15:  ("Settlement Date",               "N",   "FIXED",     4),
    16:  ("Currency Conv Date",            "N",   "FIXED",     4),
    17:  ("Capture Date",                  "N",   "FIXED",     4),
    18:  ("MCC / SIC",                     "N",   "FIXED",     4),
    19:  ("Acquiring Country Code",        "N",   "FIXED",     3),
    20:  ("PAN Country Code",              "N",   "FIXED",     3),
    21:  ("Forwarding Country Code",       "N",   "FIXED",     3),
    22:  ("POS Entry Mode",                "N",   "FIXED",     3),
    23:  ("MBR (Card Seq No)",             "N",   "FIXED",     3),
    24:  ("Network Int Identifier",        "N",   "FIXED",     3),
    25:  ("POS Condition Code",            "N",   "FIXED",     3),
    26:  ("Message Reason Code",           "N",   "FIXED",     4),
    28:  ("Fee Amount",                    "ANS", "FIXED",     9),
    32:  ("Acquiring Institution ID",      "N",   "LLVAR",     None),
    33:  ("Forwarding Institution ID",     "N",   "LLVAR",     None),
    35:  ("Track 2 Data",                  "ANS", "LLVAR",     None),
    37:  ("RRN",                           "ANS", "FIXED",     12),
    38:  ("Approval Code",                 "ANS", "FIXED",     6),
    39:  ("Response Code",                 "N",   "FIXED",     5),
    41:  ("Terminal ID",                   "ANS", "LLVAR",     None),
    43:  ("Terminal Name/Location",        "ANS", "FIXED",     222),
    44:  ("PIN/CVV Verification Result",   "ANS", "FIXED",     2),
    45:  ("Track 1 Data",                  "ANS", "LLVAR",     None),
    48:  ("Reference to Other Tran",       "ANS", "FIXED",     31),
    49:  ("Transaction Currency",          "N",   "FIXED",     3),
    51:  ("Cardholder Billing Currency",   "N",   "FIXED",     3),
    52:  ("PIN",                           "HEX", "FIXED",     16),
    53:  ("Security Control Info",         "b",   "FIXED",     48),
    54:  ("Adjustment Amount",             "N",   "FIXED",     12),
    55:  ("ICC System Related Data",       "b",   "LLLVAR",    None),
    61:  ("Card Issuer Data",              "ANS", "FIXED",     14),
    62:  ("External Tran Attributes",      "ANS", "LLLVAR",    None),
    63:  ("New PIN",                       "HEX", "FIXED",     16),
    64:  ("MAC",                           "HEX", "FIXED",     16),
    70:  ("Network Mgmt Info Code",        "N",   "FIXED",     3),
    95:  ("Replacement Amounts",           "N",   "FIXED",     24),
    100: ("Receiving Institution ID",      "N",   "LLVAR",     None),
    102: ("Account ID 1 (FROM)",           "ANS", "LLVAR",     None),
    103: ("Account ID 2 (TO)",             "ANS", "LLVAR",     None),
    104: ("Host Net Identification",       "ANS", "FIXED",     4),
    105: ("Account Balance Data",          "N",   "FIXED",     25),
    106: ("Multi Currency Data",           "N",   "FIXED",     46),
    107: ("Final RRN",                     "ANS", "FIXED",     12),
    108: ("Regional Listing / String Msg", "ANS", "LLLVAR",    None),
    109: ("Multi Account Data",            "ANS", "LLLVAR",    None),
    110: ("Numeric Message",               "N",   "LVAR",      None),
    111: ("Account Identification 2",      "ANS", "LLVAR",     None),
    114: ("Mini-Statement Data",           "ANS", "LLLVAR",    None),
    115: ("Statement Data",                "ANS", "PLLLLLVAR", None),
    116: ("Billing Data",                  "ANS", "LLLLLVAR",  None),
    121: ("Additional POS Data",           "ANS", "FIXED",     47),
    122: ("3D-Secure Data",                "ANS", "FIXED",     48),
    123: ("Misc Tran Attributes",          "ANS", "LLLVAR",    None),
    124: ("Misc Tran Attributes 2",        "ANS", "LLLLLVAR",  None),
    125: ("Administrative Tran Data",      "ANS", "LLLLLVAR",  None),
    126: ("Pre-auth Parameters",           "ANS", "FIXED",     34),
    127: ("Additional Information",        "ANS", "LLLLLVAR",  None),
    128: ("Secondary MAC",                 "HEX", "FIXED",     16),
}

TRAN_CODES = {
    "010": "ATM Withdrawal", "020": "ATM Deposit", "030": "ATM Balance Inquiry",
    "040": "ATM Transfer", "110": "POS Purchase", "114": "POS Merchandise Return",
    "115": "POS Cash Advance", "117": "POS Balance Inquiry", "882": "IBFT Fund Transfer",
}

ACCT_TYPES = {"00": "Unknown", "01": "Checking", "11": "Savings", "31": "Credit", "91": "Bonus"}

MTI_NAMES = {
    "0100": "Authorization Request", "0110": "Authorization Response",
    "0200": "Financial Transaction Request", "0210": "Financial Transaction Response",
    "0400": "Acquirer Reversal Request", "0410": "Acquirer Reversal Response",
    "0420": "Acquirer Reversal Advice", "0430": "Acquirer Reversal Advice Response",
    "0800": "Network Management Request", "0810": "Network Management Response",
}

RESPONSE_MTI_MAP = {
    "0100": "0110",
    "0200": "0210",
    "0400": "0410",
    "0420": "0430",
    "0800": "0810",
}

SEP = chr(221)   # Ý
SSEP = chr(179)  # ³


def get_field_catalog() -> List[Dict[str, Any]]:
    catalog = []
    for fnum, (name, dtype, ltype, flen) in sorted(FIELD_DEFS.items()):
        catalog.append({
            "field_number": fnum,
            "field_key": f"DE{fnum}",
            "name": name,
            "data_type": dtype,
            "length_type": ltype,
            "fixed_length": flen,
        })
    return catalog


def _unescape(s: str) -> str:
    return re.sub(r"\x([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), s)


def _decode_bitmap(hex_str: str) -> Tuple[List[int], str]:
    bits = bin(int(hex_str, 16))[2:].zfill(len(hex_str) * 4)
    return [i + 1 for i, b in enumerate(bits) if b == "1"], bits


def _read_bitmap(msg: str, pos: int) -> Tuple[List[int], str, Optional[str], str, int]:
    ph = msg[pos : pos + 16]
    pos += 16
    if bin(int(ph, 16))[2:].zfill(64)[0] == "1":
        sh = msg[pos : pos + 16]
        pos += 16
        fh = ph + sh
    else:
        sh = None
        fh = ph
    fields, bits = _decode_bitmap(fh)
    fields = [f for f in fields if f != 1]
    return fields, ph, sh, bits, pos


def _read_field(msg: str, pos: int, fnum: int) -> Tuple[str, int]:
    if fnum not in FIELD_DEFS:
        raise ValueError(f"Unsupported TIC field number: {fnum}")
    _, _, lt, fl = FIELD_DEFS[fnum]
    if lt == "FIXED":
        if pos + fl > len(msg):
            raise ValueError(f"Field F{fnum} truncated (expected {fl} chars)")
        return msg[pos : pos + fl], pos + fl
    prefix_map = {"LVAR": 1, "LLVAR": 2, "LLLVAR": 3, "LLLLLVAR": 5}
    if lt in prefix_map:
        plen = prefix_map[lt]
        l_str = msg[pos : pos + plen]
        if not l_str.isdigit():
            raise ValueError(f"Invalid length prefix '{l_str}' for F{fnum}")
        length = int(l_str)
        pos += plen
        return msg[pos : pos + length], pos + length
    if lt == "PLLLLLVAR":
        l_str = msg[pos + 1 : pos + 5] if msg[pos : pos + 1] == "0" else msg[pos : pos + 5]
        length = int(l_str)
        pos += 5
        return msg[pos : pos + length], pos + length
    raise ValueError(f"Unhandled length type {lt}")


def build_tic_message(
    mti: str,
    fields: Dict[int, str],
    h1: str = "A4M",
    h2: str = "02",
    h3: str = "000",
) -> Tuple[str, str]:
    """
    Build a raw Compass Plus TW TIC/TCI message from MTI and field dictionary.
    Returns (raw_tic_message, compact_tic_line).
    """
    clean_fields = {int(k): str(v) for k, v in fields.items() if v is not None and str(v) != ""}
    present_fnums = sorted(f for f in clean_fields.keys() if f != 1)
    needs_secondary = any(f > 64 for f in present_fnums)

    bits = ["0"] * (128 if needs_secondary else 64)
    if needs_secondary:
        bits[0] = "1"
    for f in present_fnums:
        if 1 <= f <= len(bits):
            bits[f - 1] = "1"

    bitmap_hex = "".join(
        f"{int(''.join(bits[i:i+4]), 2):X}" for i in range(0, len(bits), 4)
    )

    body_parts: List[str] = []
    compact_parts: List[str] = [f"{mti[1:]}:", f"H1){h1}{SEP}H2){h2}{SEP}H3){h3}{SEP}"]

    for fnum in present_fnums:
        if fnum not in FIELD_DEFS:
            continue
        _, dtype, ltype, flen = FIELD_DEFS[fnum]
        val = clean_fields[fnum]

        if ltype == "FIXED" and flen is not None:
            if fnum == 39 and len(val) == 2:
                # TIC F39 is 5 chars: 00 + retain_indicator(0) + 2-char response code
                val = f"000{val}"
            elif dtype == "N":
                val = val.zfill(flen)[:flen]
            else:
                val = val.ljust(flen)[:flen]
            body_parts.append(val)
        elif ltype == "LVAR":
            body_parts.append(f"{len(val):01d}{val}")
        elif ltype == "LLVAR":
            body_parts.append(f"{len(val):02d}{val}")
        elif ltype == "LLLVAR":
            body_parts.append(f"{len(val):03d}{val}")
        elif ltype in ("LLLLLVAR", "PLLLLLVAR"):
            body_parts.append(f"{len(val):05d}{val}")

        if fnum == 3 and len(val) == 7:
            compact_parts.append(f"F3.1){val[0:3]}{SSEP}F3.2){val[3:5]}{SSEP}F3.3){val[5:7]}{SSEP}{SEP}")
        else:
            compact_parts.append(f"F{fnum}){val}{SEP}")

    raw_msg = f"{h1}{h2}{h3}{mti}{bitmap_hex}{''.join(body_parts)}"
    return raw_msg, "".join(compact_parts)


def decode_tic_message(raw_msg: str) -> Dict[str, Any]:
    """Decode a raw TIC/TCI message into structured fields, subfields, warnings, and compact representation."""
    msg = raw_msg.replace("\n", "").replace("\r", "").strip()
    msg = _unescape(msg)

    a4m_idx = msg.find("A4M")
    if a4m_idx > 0:
        msg = msg[a4m_idx:]
    elif a4m_idx == -1:
        return {"valid": False, "error": "No valid TIC/TCI message found (missing A4M header)"}

    if len(msg) < 28:
        return {"valid": False, "error": "TIC/TCI message is too short"}

    h1, h2, h3 = msg[0:3], msg[3:5], msg[5:8]
    mti = msg[8:12]
    warnings: List[str] = []

    if h1 != "A4M":
        warnings.append(f"Unexpected H1 start indicator '{h1}'")
    if h3 != "000":
        warnings.append(f"Non-zero H3 reject status '{h3}'")

    try:
        present, ph, sh, _, pos = _read_bitmap(msg, 12)
    except Exception as exc:
        return {"valid": False, "error": f"Bitmap parse error: {exc}"}

    raw_fields: Dict[str, str] = {}
    detailed_fields: Dict[str, Any] = {}
    parse_errors: Dict[str, str] = {}
    compact_parts = [f"{mti[1:]}:", f"H1){h1}{SEP}H2){h2}{SEP}H3){h3}{SEP}"]

    for fnum in sorted(present):
        try:
            val, pos = _read_field(msg, pos, fnum)
            raw_fields[str(fnum)] = val
            fname = FIELD_DEFS.get(fnum, ("Unknown",))[0]

            if fnum == 2:
                detailed_fields[f"F{fnum} {fname}"] = {"masked_pan": mask_pan(val), "length": len(val)}
                compact_parts.append(f"F2){mask_pan(val)}{SEP}")
            elif fnum == 3 and len(val) == 7:
                tc, fa, ta = val[0:3], val[3:5], val[5:7]
                detailed_fields[f"F{fnum} {fname}"] = {
                    "raw": val,
                    "F3.1 Transaction Code": f"{tc} — {TRAN_CODES.get(tc, 'Configurable')}",
                    "F3.2 From Account Type": f"{fa} — {ACCT_TYPES.get(fa, 'Unknown')}",
                    "F3.3 To Account Type": f"{ta} — {ACCT_TYPES.get(ta, 'Unknown')}",
                }
                compact_parts.append(f"F3.1){tc}{SSEP}F3.2){fa}{SSEP}F3.3){ta}{SSEP}{SEP}")
            elif fnum == 39 and len(val) == 5:
                detailed_fields[f"F{fnum} {fname}"] = {
                    "raw": val,
                    "F39.1 Retain Card": val[2],
                    "F39.2 Response Code": val[3:5],
                }
                compact_parts.append(f"F39){val}{SEP}")
            elif fnum == 52:
                detailed_fields[f"F{fnum} {fname}"] = {"value": "***ENCRYPTED_PIN_BLOCK***"}
                compact_parts.append(f"F52)****************{SEP}")
            else:
                detailed_fields[f"F{fnum} {fname}"] = {"value": val.strip()}
                compact_parts.append(f"F{fnum}){val}{SEP}")
        except Exception as exc:
            parse_errors[f"F{fnum}"] = str(exc)
            warnings.append(f"Error reading F{fnum}: {exc}")
            break

    return {
        "valid": len(parse_errors) == 0,
        "header": {"H1": h1, "H2": h2, "H3": h3},
        "mti": mti,
        "mti_description": MTI_NAMES.get(mti, "Unknown MTI"),
        "bitmap": {
            "primary_hex": ph,
            "secondary_hex": sh,
            "fields_present": sorted(present),
        },
        "raw_fields": raw_fields,
        "detailed_fields": detailed_fields,
        "parse_errors": parse_errors,
        "warnings": warnings,
        "compact_tic": "".join(compact_parts),
        "sanitized_raw": mask_raw_tic_message(msg),
    }


def validate_tic_fields(
    fields: Dict[str, str],
    configured_rules: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Validate individual ISO/TIC field values against FIELD_DEFS and transaction code rules."""
    errors: Dict[str, str] = {}
    normalized: Dict[int, str] = {}

    for k, v in fields.items():
        if v is None or str(v) == "":
            continue
        fnum = int(str(k).upper().replace("DE", "").replace("F", ""))
        val = str(v)
        normalized[fnum] = val

        if fnum not in FIELD_DEFS:
            errors[f"DE{fnum}"] = f"Field DE{fnum} is not defined in TIC v2.164e specification"
            continue

        name, dtype, ltype, flen = FIELD_DEFS[fnum]
        if dtype == "N" and not val.isdigit():
            errors[f"DE{fnum}"] = f"{name} (DE{fnum}) must be numeric ('N')"
        elif dtype == "HEX" and not re.fullmatch(r"[0-9A-Fa-f]+", val):
            errors[f"DE{fnum}"] = f"{name} (DE{fnum}) must be hexadecimal"

        if ltype == "FIXED" and flen is not None:
            # Allow DE39 to be entered as 2 chars (auto-padded to 5 chars in TIC) or 5 chars
            if fnum == 39 and len(val) in (2, 5):
                pass
            # Allow DE3 to be 6 or 7 digits (auto-normalized to 7-digit TIC format)
            elif fnum == 3 and len(val) in (6, 7):
                pass
            elif dtype != "N" and len(val) > flen:
                errors[f"DE{fnum}"] = f"{name} (DE{fnum}) exceeds fixed length of {flen}"
            elif dtype == "HEX" and len(val) != flen:
                errors[f"DE{fnum}"] = f"{name} (DE{fnum}) must be exactly {flen} hex characters"

    if configured_rules:
        for rule in configured_rules:
            fnum = int(rule["iso_field_number"])
            if rule.get("required") and fnum not in normalized:
                errors[f"DE{fnum}"] = f"Mandatory field DE{fnum} ({rule.get('field_name')}) is missing"

    return {"valid": len(errors) == 0, "errors": errors, "normalized_fields": normalized}
