"""
card_crypto_service.py — Card Issuing, Luhn Validation, and Cryptographic Calculations
Interfaces with SoftHsmCryptoCore for Visa PVV, IBM 3624, CVV, and ISO PIN Blocks.
"""

import random
import re
from typing import Any, Dict, List, Optional
from app.hsm_adapter import SoftHsmCryptoCore


def validate_luhn(pan: str) -> bool:
    """Validate Primary Account Number using Luhn formula (ISO/IEC 7812)."""
    clean = re.sub(r"\D", "", pan or "")
    if len(clean) < 12:
        return False
    digits = [int(d) for d in clean]
    checksum = 0
    reverse_digits = digits[::-1]
    for i, d in enumerate(reverse_digits):
        if i % 2 == 1:
            doubled = d * 2
            checksum += doubled - 9 if doubled > 9 else doubled
        else:
            checksum += d
    return checksum % 10 == 0


def calculate_luhn_check_digit(partial_pan: str) -> str:
    """Calculate the 1-digit Luhn check digit for a partial PAN."""
    clean = re.sub(r"\D", "", partial_pan)
    digits = [int(d) for d in clean]
    checksum = 0
    # The check digit will be at an even position from right when appended
    for i, d in enumerate(digits[::-1]):
        if i % 2 == 0:
            doubled = d * 2
            checksum += doubled - 9 if doubled > 9 else doubled
        else:
            checksum += d
    remainder = checksum % 10
    return str((10 - remainder) % 10)


def generate_luhn_pan(bin_prefix: str = "456789", length: int = 16) -> str:
    """Generate a valid synthetic PAN under a given BIN prefix matching Luhn check digit."""
    clean_bin = re.sub(r"\D", "", bin_prefix)
    random_digits_needed = length - len(clean_bin) - 1
    if random_digits_needed < 1:
        raise ValueError(f"BIN prefix length ({len(clean_bin)}) exceeds or equals target PAN length ({length})")
    
    middle = "".join(str(random.randint(0, 9)) for _ in range(random_digits_needed))
    partial = f"{clean_bin}{middle}"
    check_digit = calculate_luhn_check_digit(partial)
    full_pan = f"{partial}{check_digit}"
    assert validate_luhn(full_pan)
    return full_pan


def calculate_visa_pvv_detailed(pan: str, pin: str, pvki: str = "1", pvk_id: str = "PVK_VISA_01") -> Dict[str, Any]:
    """Calculate Visa PVV with step-by-step intermediate cryptographic visibility."""
    pvk_hex = SoftHsmCryptoCore.INTERNAL_CLEAR_KEYS.get(pvk_id, "5566778899AABBCC5566778899AABBCC")
    pan11 = pan[-12:-1]  # Rightmost 11 digits excluding Luhn check digit
    tsp = f"{pan11}{pvki[0]}{pin[:4]}"
    cipher = SoftHsmCryptoCore.des3_ecb_hex(tsp, pvk_hex, decrypt=False)
    
    digits_found = [ch for ch in cipher if ch.isdigit()]
    decimalized_alphas = [str(int(ch, 16) - 10) for ch in cipher if ch in "ABCDEF"]
    combined = "".join(digits_found + decimalized_alphas)
    pvv = combined[:4]
    
    return {
        "pan": pan,
        "pin": pin,
        "pvki": pvki,
        "pvk_id": pvk_id,
        "pvk_kcv": SoftHsmCryptoCore.calculate_kcv(pvk_hex),
        "tsp_constructed": tsp,
        "3des_cipher_hex": cipher,
        "decimalized_sequence": combined,
        "calculated_pvv": pvv,
    }


def calculate_ibm_offset_detailed(pan: str, pin: str, pvk_id: str = "PVK_VISA_01") -> Dict[str, Any]:
    """Calculate IBM 3624 PIN Offset with step-by-step intermediate visibility."""
    pvk_hex = SoftHsmCryptoCore.INTERNAL_CLEAR_KEYS.get(pvk_id, "5566778899AABBCC5566778899AABBCC")
    dec_table = "0123456789012345"
    val_data = pan[-16:].zfill(16)
    enc = SoftHsmCryptoCore.des3_ecb_hex(val_data, pvk_hex, decrypt=False)
    natural_pin = "".join(dec_table[int(enc[i], 16)] for i in range(len(pin)))
    offset = "".join(str((int(pin[i]) - int(natural_pin[i]) + 10) % 10) for i in range(len(pin)))
    
    return {
        "pan": pan,
        "pin": pin,
        "pvk_id": pvk_id,
        "validation_data": val_data,
        "encrypted_validation_data": enc,
        "natural_pin": natural_pin,
        "calculated_offset": offset[:4],
    }


def calculate_cvv_detailed(pan: str, expiry_yy_mm: str, service_code: str = "101", cvk_id: str = "CVK_MAIN_01") -> Dict[str, Any]:
    """Calculate CVV1 / CVV2 / iCVV with intermediate DES blocks."""
    cvk_hex = SoftHsmCryptoCore.INTERNAL_CLEAR_KEYS.get(cvk_id, "5566778899AABBCC5566778899AABBCC")
    calculated_cvv = SoftHsmCryptoCore.calculate_cvv(pan, expiry_yy_mm, service_code, cvk_hex)
    return {
        "pan": pan,
        "expiry_yy_mm": expiry_yy_mm,
        "service_code": service_code,
        "cvk_id": cvk_id,
        "cvk_kcv": SoftHsmCryptoCore.calculate_kcv(cvk_hex),
        "calculated_cvv": calculated_cvv,
    }


def pack_pin_block_detailed(pin: str, pan: str, format_name: str = "ISO_0", awk_id: str = "AWK_ATM_01") -> Dict[str, Any]:
    """Pack clear PIN into ISO Format 0, 1, or 3 PIN block and encrypt under AWK."""
    awk_hex = SoftHsmCryptoCore.INTERNAL_CLEAR_KEYS.get(awk_id, "1A2B3C4D5E6F70811A2B3C4D5E6F7081")
    
    if format_name.upper() == "ISO_0":
        pin_part = f"0{len(pin)}{pin}".ljust(16, "F")
        pan12 = pan[-13:-1].zfill(12)
        pan_part = f"0000{pan12}"
        clear_block = SoftHsmCryptoCore.xor_hex(pin_part, pan_part)
    elif format_name.upper() == "ISO_1":
        # Format 1: 1 + L + PIN + Random Pad
        rand_pad = "".join(f"{random.randint(0, 15):X}" for _ in range(14 - len(pin)))
        clear_block = f"1{len(pin)}{pin}{rand_pad}"
    elif format_name.upper() == "ISO_3":
        # Format 3: 3 + L + PIN + Random (F-pad) XOR PAN
        rand_pad = "".join(f"{random.choice('0123456789ABCDEF')}" for _ in range(14 - len(pin)))
        pin_part = f"3{len(pin)}{pin}{rand_pad}"
        pan12 = pan[-13:-1].zfill(12)
        pan_part = f"0000{pan12}"
        clear_block = SoftHsmCryptoCore.xor_hex(pin_part, pan_part)
    else:
        raise ValueError(f"Unsupported PIN block format: {format_name}")

    encrypted_block = SoftHsmCryptoCore.des3_ecb_hex(clear_block, awk_hex, decrypt=False)
    
    return {
        "format": format_name.upper(),
        "pin": pin,
        "pan": pan,
        "awk_id": awk_id,
        "awk_kcv": SoftHsmCryptoCore.calculate_kcv(awk_hex),
        "clear_pin_block": clear_block,
        "encrypted_pin_block": encrypted_block,
    }
