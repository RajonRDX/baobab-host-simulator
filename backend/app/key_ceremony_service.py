"""
key_ceremony_service.py — Split-Component Key Ceremony & Key Exchange Service
Implements DES odd-parity adjustment, 2/3 component XOR assembly, KCV calculation,
and key translation under Zone Master Keys (ZMK).
"""

import re
import secrets
from typing import Any, Dict, List, Optional, Tuple
from app.hsm_adapter import SoftHsmCryptoCore


def enforce_des_odd_parity(hex_key: str) -> str:
    """Adjusts the least significant bit (LSB) of each byte so that it has odd parity."""
    raw = bytes.fromhex(hex_key.replace(" ", "").upper())
    adjusted = bytearray()
    for b in raw:
        # Count bits in the top 7 bits
        bits_count = bin(b & 0xFE).count("1")
        # If even, set LSB to 1; if odd, set LSB to 0
        lsb = 1 if (bits_count % 2 == 0) else 0
        adjusted.append((b & 0xFE) | lsb)
    return adjusted.hex().upper()


def validate_des_parity(hex_key: str) -> bool:
    """Validates that every byte in the key has odd parity."""
    raw = bytes.fromhex(hex_key.replace(" ", "").upper())
    for b in raw:
        if bin(b).count("1") % 2 == 0:
            return False
    return True


def generate_random_des_key(length_bits: int = 128) -> Dict[str, Any]:
    """Generates a cryptographically secure random 2-Key (128-bit) or 3-Key (192-bit) 3DES key with odd parity."""
    num_bytes = 16 if length_bits == 128 else 24
    rand_bytes = secrets.token_bytes(num_bytes)
    adjusted_hex = enforce_des_odd_parity(rand_bytes.hex().upper())
    kcv = SoftHsmCryptoCore.calculate_kcv(adjusted_hex)
    return {
        "key_hex": adjusted_hex,
        "length_bits": length_bits,
        "kcv": kcv,
        "odd_parity": True,
    }


def split_key_into_components(key_hex: str, num_components: int = 3) -> Dict[str, Any]:
    """Splits a key into 2 or 3 random components that XOR back to the original key."""
    clean_key = key_hex.replace(" ", "").upper()
    num_bytes = len(clean_key) // 2
    components = []

    running_xor = bytes.fromhex(clean_key)
    for _ in range(num_components - 1):
        rand_comp = secrets.token_bytes(num_bytes)
        rand_hex = enforce_des_odd_parity(rand_comp.hex().upper())
        components.append({
            "component_number": len(components) + 1,
            "hex": rand_hex,
            "kcv": SoftHsmCryptoCore.calculate_kcv(rand_hex),
        })
        running_xor = bytes(a ^ b for a, b in zip(running_xor, bytes.fromhex(rand_hex)))

    # Final component is the remaining XOR
    final_hex = enforce_des_odd_parity(running_xor.hex().upper())
    components.append({
        "component_number": len(components) + 1,
        "hex": final_hex,
        "kcv": SoftHsmCryptoCore.calculate_kcv(final_hex),
    })

    return {
        "original_key_kcv": SoftHsmCryptoCore.calculate_kcv(clean_key),
        "num_components": num_components,
        "components": components,
    }


def assemble_components(components_hex: List[str]) -> Dict[str, Any]:
    """Assembles 2 or 3 clear components via XOR into the final operational key."""
    if len(components_hex) < 2:
        raise ValueError("Key assembly requires at least 2 components")

    clean_comps = [c.replace(" ", "").upper() for c in components_hex]
    key_len = len(clean_comps[0])
    for c in clean_comps:
        if len(c) != key_len:
            raise ValueError("All components must have identical length (32 or 48 hex chars)")

    running_bytes = bytes.fromhex(clean_comps[0])
    for c in clean_comps[1:]:
        comp_bytes = bytes.fromhex(c)
        running_bytes = bytes(a ^ b for a, b in zip(running_bytes, comp_bytes))

    assembled_hex = enforce_des_odd_parity(running_bytes.hex().upper())
    kcv = SoftHsmCryptoCore.calculate_kcv(assembled_hex)

    return {
        "assembled_key_hex": assembled_hex,
        "length_bits": len(assembled_hex) * 4,
        "kcv": kcv,
        "odd_parity": True,
        "components_count": len(components_hex),
        "component_kcvs": [SoftHsmCryptoCore.calculate_kcv(c) for c in clean_comps],
    }


def import_key_under_zmk(encrypted_key_hex: str, zmk_hex: str) -> Dict[str, Any]:
    """Decrypts a working key received under a ZMK and computes its clear KCV."""
    clean_enc = encrypted_key_hex.replace(" ", "").upper()
    clean_zmk = zmk_hex.replace(" ", "").upper()
    clear_key = SoftHsmCryptoCore.des3_ecb_hex(clean_enc, clean_zmk, decrypt=True)
    clear_key_parity = enforce_des_odd_parity(clear_key)
    kcv = SoftHsmCryptoCore.calculate_kcv(clear_key_parity)
    return {
        "clear_key_hex": clear_key_parity,
        "kcv": kcv,
        "zmk_kcv": SoftHsmCryptoCore.calculate_kcv(clean_zmk),
    }


def export_key_under_zmk(clear_key_hex: str, zmk_hex: str) -> Dict[str, Any]:
    """Encrypts a working key under a ZMK for secure export/exchange."""
    clean_key = clear_key_hex.replace(" ", "").upper()
    clean_zmk = zmk_hex.replace(" ", "").upper()
    encrypted_key = SoftHsmCryptoCore.des3_ecb_hex(clean_key, clean_zmk, decrypt=False)
    kcv = SoftHsmCryptoCore.calculate_kcv(clean_key)
    return {
        "encrypted_key_hex": encrypted_key,
        "key_kcv": kcv,
        "zmk_kcv": SoftHsmCryptoCore.calculate_kcv(clean_zmk),
    }
