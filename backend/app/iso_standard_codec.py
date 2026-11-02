"""
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
    clean = raw_msg.strip().replace(" ", "").replace("\n", "").replace("\r", "")
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
