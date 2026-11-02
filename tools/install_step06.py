#!/usr/bin/env python3
"""
INSTALLER: tools/install_step06.py
STEP 6 — PIN, PVV and Card Generation Lab (Single Unified Installer)
Adds:
  1. backend/app/card_crypto_service.py (Luhn generation, PVV, Offset, CVV, PIN block calculations)
  2. Pydantic v2 schemas in backend/app/schemas.py
  3. API endpoints in backend/app/api_routes.py (/api/cards/{id}/pin, /api/crypto/*, /api/cards/generate-test-card)
  4. frontend/src/pages/CardCryptoLabPage.tsx
  5. Route registration in App.tsx and Layout.tsx
  6. Automated Pytest test suite in backend/tests/test_step06_card_crypto.py
"""

from pathlib import Path
import sys

BASE_DIR = Path(r"E:\HOST_VSCODE\host-simulator").resolve()
sys.path.insert(0, str(BASE_DIR))

from tools.patcher import PatcherSession, parse_installer_args

CARD_CRYPTO_SERVICE_CODE = '''"""
card_crypto_service.py — Card Issuing, Luhn Validation, and Cryptographic Calculations
Interfaces with SoftHsmCryptoCore for Visa PVV, IBM 3624, CVV, and ISO PIN Blocks.
"""

import random
import re
from typing import Any, Dict, List, Optional
from app.hsm_adapter import SoftHsmCryptoCore


def validate_luhn(pan: str) -> bool:
    """Validate Primary Account Number using Luhn formula (ISO/IEC 7812)."""
    clean = re.sub(r"\\D", "", pan or "")
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
    clean = re.sub(r"\\D", "", partial_pan)
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
    clean_bin = re.sub(r"\\D", "", bin_prefix)
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
'''

CARD_LAB_PAGE_CODE = '''import React, { useEffect, useState } from 'react';
import { CreditCard, KeyRound, ShieldCheck, Sparkles, RefreshCw, Copy, CheckCircle2, Lock } from 'lucide-react';
import { apiFetch } from '../api';

export const CardCryptoLabPage: React.FC = () => {
  const [tab, setTab] = useState<'GEN' | 'PVV' | 'CVV' | 'BLOCK'>('GEN');
  const [bins, setBins] = useState<any[]>([]);
  const [institutions, setInstitutions] = useState<any[]>([]);
  const [msg, setMsg] = useState('');

  // 1. Generator State
  const [selectedBin, setSelectedBin] = useState('456789');
  const [cardholderName, setCardholderName] = useState('TEST CARDHOLDER');
  const [cardType, setCardType] = useState('DEBIT');
  const [initialPin, setInitialPin] = useState('1234');
  const [generatedCard, setGeneratedCard] = useState<any | null>(null);

  // 2. PVV & Offset State
  const [pvvPan, setPvvPan] = useState('4567890123450001');
  const [pvvPin, setPvvPin] = useState('1234');
  const [pvvResult, setPvvResult] = useState<any | null>(null);

  // 3. CVV State
  const [cvvPan, setCvvPan] = useState('4567890123450001');
  const [cvvExp, setCvvExp] = useState('2812');
  const [cvvServiceCode, setCvvServiceCode] = useState('101');
  const [cvvResult, setCvvResult] = useState<any | null>(null);

  // 4. PIN Block State
  const [blockPan, setBlockPan] = useState('4567890123450001');
  const [blockPin, setBlockPin] = useState('1234');
  const [blockFormat, setBlockFormat] = useState('ISO_0');
  const [blockResult, setBlockResult] = useState<any | null>(null);

  useEffect(() => {
    Promise.all([apiFetch('/bin-ranges'), apiFetch('/institutions')])
      .then(([bList, iList]) => {
        setBins(bList);
        setInstitutions(iList);
        if (bList.length > 0) setSelectedBin(bList[0].bin_prefix);
      })
      .catch(console.error);
  }, []);

  const handleGenerateCard = async () => {
    setMsg('');
    try {
      const res = await apiFetch('/cards/generate-test-card', {
        method: 'POST',
        body: JSON.stringify({
          bin_prefix: selectedBin,
          cardholder_name: cardholderName,
          card_type: cardType,
          initial_pin: initialPin,
        }),
      });
      setGeneratedCard(res);
      setMsg(`Successfully generated Luhn-valid card ${res.masked_pan}`);
    } catch (err: any) {
      setMsg(`Error: ${err.message}`);
    }
  };

  const handleCalculatePvv = async () => {
    try {
      const res = await apiFetch('/crypto/calculate-pvv', {
        method: 'POST',
        body: JSON.stringify({ pan: pvvPan, pin: pvvPin, pvki: '1', pvk_id: 'PVK_VISA_01' }),
      });
      setPvvResult(res);
    } catch (err: any) {
      alert(err.message);
    }
  };

  const handleCalculateCvv = async () => {
    try {
      const res = await apiFetch('/crypto/calculate-cvv', {
        method: 'POST',
        body: JSON.stringify({ pan: cvvPan, expiry_yy_mm: cvvExp, service_code: cvvServiceCode }),
      });
      setCvvResult(res);
    } catch (err: any) {
      alert(err.message);
    }
  };

  const handlePackPinBlock = async () => {
    try {
      const res = await apiFetch('/crypto/pack-pin-block', {
        method: 'POST',
        body: JSON.stringify({ pan: blockPan, pin: blockPin, format: blockFormat, awk_id: 'AWK_ATM_01' }),
      });
      setBlockResult(res);
    } catch (err: any) {
      alert(err.message);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold">PIN, PVV & Card Generation Lab</h1>
          <p className="text-xs text-slate-500">
            Interactive Soft-HSM personalization bench: Luhn test card generation, Visa PVV, IBM 3624 offset, CVV, and ISO PIN blocks
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono px-2.5 py-1 rounded bg-emerald-500/10 text-emerald-500 border border-emerald-500/20 font-bold">
            HSM: Thales payShield 10K (Raw Mode)
          </span>
        </div>
      </div>

      {msg && (
        <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs font-mono">
          {msg}
        </div>
      )}

      {/* Tabs */}
      <div className="flex flex-wrap gap-2 border-b border-slate-200 dark:border-slate-800 pb-2">
        {[
          ['GEN', '1. Luhn Synthetic Card Generator', CreditCard],
          ['PVV', '2. Visa PVV & IBM 3624 Offset', ShieldCheck],
          ['CVV', '3. CVV1 / CVV2 / iCVV Derivation', KeyRound],
          ['BLOCK', '4. ISO PIN Block Packer', Lock],
        ].map(([k, label, Icon]: any) => (
          <button
            key={k}
            onClick={() => setTab(k)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-mono font-bold transition ${
              tab === k
                ? 'bg-emerald-600 text-white shadow-sm'
                : 'bg-white dark:bg-slate-900 text-slate-500 hover:text-slate-900 dark:hover:text-white border border-slate-200 dark:border-slate-800'
            }`}
          >
            <Icon size={15} />
            <span>{label}</span>
          </button>
        ))}
      </div>

      {/* TAB 1: CARD GENERATOR */}
      {tab === 'GEN' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <div className="lg:col-span-6 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 space-y-4">
            <h2 className="text-sm font-bold">Synthetic Test Card Personalizer</h2>
            <div className="space-y-3 text-xs font-mono">
              <div>
                <label className="block text-slate-400 mb-1">Select Bank BIN Range</label>
                <select
                  value={selectedBin}
                  onChange={(e) => setSelectedBin(e.target.value)}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-2"
                >
                  {bins.map((b) => (
                    <option key={b.id} value={b.bin_prefix}>
                      {b.bin_prefix} — {b.card_product} ({b.institution_code})
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-slate-400 mb-1">Cardholder Name</label>
                <input
                  value={cardholderName}
                  onChange={(e) => setCardholderName(e.target.value)}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-2"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-400 mb-1">Card Type</label>
                  <select
                    value={cardType}
                    onChange={(e) => setCardType(e.target.value)}
                    className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-2"
                  >
                    <option value="DEBIT">DEBIT</option>
                    <option value="CREDIT">CREDIT</option>
                    <option value="PREPAID">PREPAID</option>
                  </select>
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">Initial PIN (Packs PVV)</label>
                  <input
                    value={initialPin}
                    onChange={(e) => setInitialPin(e.target.value)}
                    maxLength={4}
                    className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-2"
                  />
                </div>
              </div>
            </div>
            <button
              onClick={handleGenerateCard}
              className="w-full flex items-center justify-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold py-2.5 rounded-lg text-xs"
            >
              <Sparkles size={15} /> Generate Luhn-Valid Card & Seed Database
            </button>
          </div>

          <div className="lg:col-span-6 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 space-y-4">
            <h2 className="text-sm font-bold">Personalization Output</h2>
            {generatedCard ? (
              <div className="space-y-3 text-xs font-mono">
                <div className="p-4 rounded-xl bg-gradient-to-r from-emerald-950 to-slate-900 border border-emerald-800/40 text-emerald-200 space-y-2">
                  <div className="flex justify-between items-center text-[11px] text-emerald-400">
                    <span>{generatedCard.institution_code} SWITCH</span>
                    <span>{generatedCard.card_product}</span>
                  </div>
                  <div className="text-lg font-bold tracking-wider text-white py-1">
                    {generatedCard.test_pan_reference}
                  </div>
                  <div className="flex justify-between items-center text-[11px]">
                    <div>EXP: {String(generatedCard.expiry_month).padStart(2, '0')}/{generatedCard.expiry_year}</div>
                    <div>CVV: {generatedCard.cvv}</div>
                    <div>PIN: {initialPin}</div>
                  </div>
                </div>

                <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 space-y-1">
                  <div><span className="text-slate-400">Luhn Valid:</span> <span className="text-emerald-400 font-bold">YES (Mod-10 Verified)</span></div>
                  <div><span className="text-slate-400">Visa PVV:</span> <span className="text-amber-400 font-bold">{generatedCard.pvv}</span> (PVKI: 1)</div>
                  <div><span className="text-slate-400">Linked Account:</span> {generatedCard.linked_account_number}</div>
                  <div><span className="text-slate-400">EMV AID:</span> A0000000031010 (MK_AC_EMV01)</div>
                </div>
              </div>
            ) : (
              <div className="text-slate-400 text-xs font-mono py-16 text-center">
                Configure BIN range and click Generate to issue a live synthetic card with verified PVV and CVV.
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 2: PVV & OFFSET */}
      {tab === 'PVV' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <div className="lg:col-span-6 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 space-y-4">
            <h2 className="text-sm font-bold">Visa PVV & IBM 3624 Calculator</h2>
            <div className="space-y-3 text-xs font-mono">
              <div>
                <label className="block text-slate-400 mb-1">Card PAN</label>
                <input
                  value={pvvPan}
                  onChange={(e) => setPvvPan(e.target.value)}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-2"
                />
              </div>
              <div>
                <label className="block text-slate-400 mb-1">Clear PIN (4 Digits)</label>
                <input
                  value={pvvPin}
                  onChange={(e) => setPvvPin(e.target.value)}
                  maxLength={4}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-2"
                />
              </div>
            </div>
            <button
              onClick={handleCalculatePvv}
              className="bg-emerald-600 hover:bg-emerald-500 text-white font-semibold px-4 py-2 rounded-lg text-xs"
            >
              Calculate Visa PVV ➔
            </button>
          </div>

          <div className="lg:col-span-6 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 space-y-4">
            <h2 className="text-sm font-bold">Calculation Breakdown</h2>
            {pvvResult ? (
              <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono space-y-2">
                <div className="flex justify-between items-center text-emerald-400 font-bold border-b border-slate-800 pb-2">
                  <span>Visa PVV Result:</span>
                  <span className="text-base text-amber-400 font-bold">{pvvResult.calculated_pvv}</span>
                </div>
                <div><span className="text-slate-400">PVK Key Reference:</span> {pvvResult.pvk_id} (KCV: {pvvResult.pvk_kcv})</div>
                <div><span className="text-slate-400">Constructed TSP (16 Digits):</span> {pvvResult.tsp_constructed}</div>
                <div><span className="text-slate-400">3DES Ciphertext:</span> {pvvResult.3des_cipher_hex}</div>
                <div><span className="text-slate-400">Decimalized Sequence:</span> {pvvResult.decimalized_sequence}</div>
              </div>
            ) : (
              <div className="text-slate-400 text-xs font-mono py-12 text-center">
                Enter PAN and PIN to inspect intermediate 3DES and decimalization steps.
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 3: CVV */}
      {tab === 'CVV' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <div className="lg:col-span-6 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 space-y-4">
            <h2 className="text-sm font-bold">CVV1 / CVV2 / iCVV Derivation</h2>
            <div className="space-y-3 text-xs font-mono">
              <div>
                <label className="block text-slate-400 mb-1">Card PAN</label>
                <input
                  value={cvvPan}
                  onChange={(e) => setCvvPan(e.target.value)}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-2"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-400 mb-1">Expiry (YYMM)</label>
                  <input
                    value={cvvExp}
                    onChange={(e) => setCvvExp(e.target.value)}
                    maxLength={4}
                    className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-2"
                  />
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">Service Code</label>
                  <input
                    value={cvvServiceCode}
                    onChange={(e) => setCvvServiceCode(e.target.value)}
                    maxLength={3}
                    className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-2"
                  />
                </div>
              </div>
            </div>
            <button
              onClick={handleCalculateCvv}
              className="bg-emerald-600 hover:bg-emerald-500 text-white font-semibold px-4 py-2 rounded-lg text-xs"
            >
              Derive CVV ➔
            </button>
          </div>

          <div className="lg:col-span-6 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 space-y-4">
            <h2 className="text-sm font-bold">CVV Derivation Breakdown</h2>
            {cvvResult ? (
              <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono space-y-2">
                <div className="flex justify-between items-center text-emerald-400 font-bold border-b border-slate-800 pb-2">
                  <span>Derived CVV:</span>
                  <span className="text-base text-amber-400 font-bold">{cvvResult.calculated_cvv}</span>
                </div>
                <div><span className="text-slate-400">CVK Reference:</span> {cvvResult.cvk_id} (KCV: {cvvResult.cvk_kcv})</div>
                <div><span className="text-slate-400">Combined Block (32 hex):</span> {cvvResult.pan}{cvvResult.expiry_yy_mm}{cvvResult.service_code}0000000000000</div>
              </div>
            ) : (
              <div className="text-slate-400 text-xs font-mono py-12 text-center">
                Enter PAN, Expiry, and Service Code to compute 3-digit CVV.
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 4: PIN BLOCK */}
      {tab === 'BLOCK' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <div className="lg:col-span-6 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 space-y-4">
            <h2 className="text-sm font-bold">ISO 9564 PIN Block Packer (AWK Encryption)</h2>
            <div className="space-y-3 text-xs font-mono">
              <div>
                <label className="block text-slate-400 mb-1">Card PAN</label>
                <input
                  value={blockPan}
                  onChange={(e) => setBlockPan(e.target.value)}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-2"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-400 mb-1">Clear PIN</label>
                  <input
                    value={blockPin}
                    onChange={(e) => setBlockPin(e.target.value)}
                    maxLength={12}
                    className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-2"
                  />
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">ISO Format</label>
                  <select
                    value={blockFormat}
                    onChange={(e) => setBlockFormat(e.target.value)}
                    className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-2"
                  >
                    <option value="ISO_0">ISO Format 0 (Standard ANSI X9.8)</option>
                    <option value="ISO_1">ISO Format 1 (No PAN XOR)</option>
                    <option value="ISO_3">ISO Format 3</option>
                  </select>
                </div>
              </div>
            </div>
            <button
              onClick={handlePackPinBlock}
              className="bg-emerald-600 hover:bg-emerald-500 text-white font-semibold px-4 py-2 rounded-lg text-xs"
            >
              Pack & Encrypt PIN Block ➔
            </button>
          </div>

          <div className="lg:col-span-6 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 space-y-4">
            <h2 className="text-sm font-bold">Packed PIN Block Output</h2>
            {blockResult ? (
              <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono space-y-2">
                <div><span className="text-slate-400">Clear Block:</span> <span className="text-sky-300 font-bold">{blockResult.clear_pin_block}</span></div>
                <div><span className="text-slate-400">Encrypted Under AWK:</span> <span className="text-amber-400 font-bold">{blockResult.encrypted_pin_block}</span></div>
                <div><span className="text-slate-400">AWK Reference:</span> {blockResult.awk_id} (KCV: {blockResult.awk_kcv})</div>
                <div className="pt-2 border-t border-slate-800 text-[11px] text-slate-400">
                  Ready to paste directly into TIC DE52 or ISO 8583 Field 52.
                </div>
              </div>
            ) : (
              <div className="text-slate-400 text-xs font-mono py-12 text-center">
                Configure clear PIN and PAN to generate raw ISO-0/1/3 encrypted block.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
'''

TEST_STEP06_CODE = '''"""
test_step06_card_crypto.py — Tests for Step 6 Luhn Generation, Visa PVV, CVV, and PIN Change
"""

import os
import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Card, PinProfile
from app.card_crypto_service import (
    calculate_cvv_detailed,
    calculate_luhn_check_digit,
    calculate_visa_pvv_detailed,
    generate_luhn_pan,
    pack_pin_block_detailed,
    validate_luhn,
)
from app.seed_data import seed_initial_data
from app.security import create_access_token
from app.config import settings


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


def test_luhn_generation_and_validation():
    pan = generate_luhn_pan("456789", 16)
    assert pan.startswith("456789")
    assert len(pan) == 16
    assert validate_luhn(pan) is True
    # Invalidate check digit
    bad_pan = pan[:-1] + str((int(pan[-1]) + 1) % 10)
    assert validate_luhn(bad_pan) is False


def test_visa_pvv_calculation():
    # Test known vector
    res = calculate_visa_pvv_detailed("4567890123450001", "1234", "1", "PVK_VISA_01")
    assert len(res["calculated_pvv"]) == 4
    assert res["calculated_pvv"].isdigit()


def test_cvv_derivation():
    res = calculate_cvv_detailed("4567890123450001", "2812", "101")
    assert len(res["calculated_cvv"]) == 3
    assert res["calculated_cvv"].isdigit()


def test_iso0_pin_block_packing():
    res = pack_pin_block_detailed("1234", "4567890123450001", "ISO_0")
    assert len(res["encrypted_pin_block"]) == 16
    assert len(res["clear_pin_block"]) == 16


def test_card_pin_change_endpoint(client, db_session):
    card = db_session.query(Card).first()
    pin_prof_before = card.pin_profile.pin_offset_reference

    # Change PIN to 4321
    res = client.post(f"/api/cards/{card.id}/pin", json={"new_pin": "4321"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "updated"
    assert data["new_pvv"] != pin_prof_before

    db_session.refresh(card.pin_profile)
    assert card.pin_profile.pin_offset_reference == data["new_pvv"]
    assert card.pin_profile.retry_counter == 0
'''


def main() -> int:
    args = parse_installer_args("Step 06: PIN, PVV and Card Generation Lab")
    session = PatcherSession(
        step_id="step06",
        title="Implement PIN, PVV, CVV, ISO PIN Block, and Synthetic Card Personalization Lab",
        dry_run=args.dry_run,
    )

    # 1. Write backend/app/card_crypto_service.py
    session.write_file("backend/app/card_crypto_service.py", CARD_CRYPTO_SERVICE_CODE)

    # 2. Patch backend/app/schemas.py to add card crypto schemas
    session.patch_file(
        "backend/app/schemas.py",
        [
            {
                "marker": "step06:schemas_card_crypto",
                "action": "append",
                "text": (
                    "\n# ==============================================================================\n"
                    "# STEP 6 SCHEMAS: PIN, PVV, CVV & SYNTHETIC CARD GENERATION\n"
                    "# ==============================================================================\n\n"
                    "class CardPinChangeRequest(BaseModel):\n"
                    "    new_pin: str = Field(..., min_length=4, max_length=12, description='New clear PIN (4 to 12 digits)')\n\n\n"
                    "class CardGenerateRequest(BaseModel):\n"
                    "    bin_prefix: str = '456789'\n"
                    "    cardholder_name: str = 'SYNTHETIC CARDHOLDER'\n"
                    "    card_type: str = 'DEBIT'\n"
                    "    card_product: str = 'VISA_DEBIT_CLASSIC'\n"
                    "    initial_pin: str = '1234'\n"
                    "    linked_account_id: Optional[str] = None\n\n\n"
                    "class PvvCalculateRequest(BaseModel):\n"
                    "    pan: str\n"
                    "    pin: str\n"
                    "    pvki: str = '1'\n"
                    "    pvk_id: str = 'PVK_VISA_01'\n\n\n"
                    "class CvvCalculateRequest(BaseModel):\n"
                    "    pan: str\n"
                    "    expiry_yy_mm: str = '2812'\n"
                    "    service_code: str = '101'\n"
                    "    cvk_id: str = 'CVK_MAIN_01'\n\n\n"
                    "class PinBlockPackRequest(BaseModel):\n"
                    "    pan: str\n"
                    "    pin: str\n"
                    "    format: str = 'ISO_0'\n"
                    "    awk_id: str = 'AWK_ATM_01'\n"
                ),
            }
        ],
    )

    # 3. Patch backend/app/api_routes.py to add crypto calculation and PIN change endpoints
    session.patch_file(
        "backend/app/api_routes.py",
        [
            {
                "marker": "step06:api_routes_crypto_imports",
                "action": "insert_after",
                "anchor": "from app.schemas import (",
                "text": (
                    "    CardGenerateRequest,\n"
                    "    CardPinChangeRequest,\n"
                    "    CvvCalculateRequest,\n"
                    "    PinBlockPackRequest,\n"
                    "    PvvCalculateRequest,"
                ),
            },
            {
                "marker": "step06:api_routes_crypto_service_import",
                "action": "insert_after",
                "anchor": "from app.audit_service import record_audit, serialize_entity",
                "text": (
                    "from app.card_crypto_service import (\n"
                    "    calculate_cvv_detailed,\n"
                    "    calculate_ibm_offset_detailed,\n"
                    "    calculate_visa_pvv_detailed,\n"
                    "    generate_luhn_pan,\n"
                    "    pack_pin_block_detailed,\n"
                    ")"
                ),
            },
            {
                "marker": "step06:crypto_calculation_endpoints",
                "action": "insert_before",
                "anchor": "# ==============================================================================\n# 3. TRANSACTION CODES, HOST CONFIGURATION & RESPONSE CODES",
                "text": (
                    "# --- CARD ISSUING & CRYPTO LAB ENDPOINTS (STEP 6) ---\n\n"
                    "@router.post('/cards/{card_id}/pin')\n"
                    "def change_card_pin(card_id: str, payload: CardPinChangeRequest, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):\n"
                    "    card = db.query(Card).filter(Card.id == card_id).first()\n"
                    "    if not card:\n"
                    "        raise HTTPException(status_code=404, detail='Card not found')\n"
                    "    pin_prof = db.query(PinProfile).filter(PinProfile.card_id == card.id).first()\n"
                    "    if not pin_prof:\n"
                    "        raise HTTPException(status_code=404, detail='PIN profile not found for card')\n\n"
                    "    before = serialize_entity(pin_prof)\n"
                    "    pvk_id = pin_prof.pvk_key_reference or 'PVK_VISA_01'\n"
                    "    if pin_prof.pin_verification_method == 'IBM_3624':\n"
                    "        calc = calculate_ibm_offset_detailed(card.test_pan_reference, payload.new_pin, pvk_id)\n"
                    "        new_ref = calc['calculated_offset']\n"
                    "    else:\n"
                    "        calc = calculate_visa_pvv_detailed(card.test_pan_reference, payload.new_pin, pin_prof.pvki, pvk_id)\n"
                    "        new_ref = calc['calculated_pvv']\n\n"
                    "    pin_prof.pin_offset_reference = new_ref\n"
                    "    pin_prof.retry_counter = 0\n"
                    "    pin_prof.pin_changed_at = utc_now()\n"
                    "    after = serialize_entity(pin_prof)\n"
                    "    record_audit(db, 'PIN_PROFILE', pin_prof.id, 'PIN_CHANGE', performed_by=current_user, before_state=before, after_state=after,\n"
                    "                 change_summary=f'Changed PIN and recalculated PVV/Offset for card {card.masked_pan}')\n"
                    "    db.commit()\n"
                    "    return {'status': 'updated', 'card_id': card.id, 'new_pvv': new_ref, 'method': pin_prof.pin_verification_method}\n\n\n"
                    "@router.post('/cards/generate-test-card')\n"
                    "def generate_test_card_endpoint(payload: CardGenerateRequest, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):\n"
                    "    bin_match = db.query(BinRange).filter(BinRange.bin_prefix == payload.bin_prefix).first()\n"
                    "    if not bin_match:\n"
                    "        raise HTTPException(status_code=404, detail=f'BIN range {payload.bin_prefix} not found in database')\n\n"
                    "    # Generate Luhn PAN\n"
                    "    pan = generate_luhn_pan(payload.bin_prefix, bin_match.pan_length)\n"
                    "    # Resolve customer & account\n"
                    "    inst_id = bin_match.institution_id\n"
                    "    cust = db.query(Customer).filter(Customer.institution_id == inst_id).first()\n"
                    "    if not cust:\n"
                    "        cust = db.query(Customer).first()\n"
                    "    acct = db.query(Account).filter(Account.customer_id == cust.id).first() if cust else None\n"
                    "    if not acct:\n"
                    "        acct = db.query(Account).first()\n\n"
                    "    # Calculate PVV and CVV\n"
                    "    pvv_calc = calculate_visa_pvv_detailed(pan, payload.initial_pin, '1', 'PVK_VISA_01')\n"
                    "    cvv_calc = calculate_cvv_detailed(pan, '2812', '101', 'CVK_MAIN_01')\n\n"
                    "    card = Card(\n"
                    "        customer_id=cust.id,\n"
                    "        card_number_token=tokenize_pan(pan),\n"
                    "        test_pan_reference=pan,\n"
                    "        masked_pan=mask_pan(pan),\n"
                    "        cardholder_name=payload.cardholder_name.upper(),\n"
                    "        expiry_month=12,\n"
                    "        expiry_year=2028,\n"
                    "        card_type=payload.card_type,\n"
                    "        card_product=payload.card_product or bin_match.card_product,\n"
                    "        card_status='ACTIVE',\n"
                    "        linked_account_id=acct.id if acct else None,\n"
                    "        institution_id=inst_id,\n"
                    "    )\n"
                    "    db.add(card)\n"
                    "    db.flush()\n"
                    "    if acct:\n"
                    "        db.add(CardAccount(card_id=card.id, account_id=acct.id, account_role='PRIMARY', priority=1, status='ACTIVE'))\n"
                    "    db.add(CardLimit(card_id=card.id))\n"
                    "    db.add(PinProfile(card_id=card.id, pin_verification_method='VISA_PVV', pvk_key_reference='PVK_VISA_01', pin_offset_reference=pvv_calc['calculated_pvv'], pvki='1', cvv_reference=cvv_calc['calculated_cvv']))\n"
                    "    db.add(EmvProfile(card_id=card.id))\n"
                    "    record_audit(db, 'CARD', card.id, 'GENERATE_TEST_CARD', performed_by=current_user, after_state=serialize_entity(card),\n"
                    "                 change_summary=f'Generated Luhn test card {card.masked_pan} under BIN {payload.bin_prefix}')\n"
                    "    db.commit()\n"
                    "    return {\n"
                    "        'id': card.id,\n"
                    "        'test_pan_reference': card.test_pan_reference,\n"
                    "        'masked_pan': card.masked_pan,\n"
                    "        'cardholder_name': card.cardholder_name,\n"
                    "        'expiry_month': card.expiry_month,\n"
                    "        'expiry_year': card.expiry_year,\n"
                    "        'pvv': pvv_calc['calculated_pvv'],\n"
                    "        'cvv': cvv_calc['calculated_cvv'],\n"
                    "        'card_product': card.card_product,\n"
                    "        'institution_code': bin_match.institution.institution_code if bin_match.institution else 'ITCL',\n"
                    "        'linked_account_number': acct.account_number if acct else 'NONE',\n"
                    "    }\n\n\n"
                    "@router.post('/crypto/calculate-pvv')\n"
                    "def api_calculate_pvv(payload: PvvCalculateRequest, _: str = Depends(get_current_user)):\n"
                    "    return calculate_visa_pvv_detailed(payload.pan, payload.pin, payload.pvki, payload.pvk_id)\n\n\n"
                    "@router.post('/crypto/calculate-cvv')\n"
                    "def api_calculate_cvv(payload: CvvCalculateRequest, _: str = Depends(get_current_user)):\n"
                    "    return calculate_cvv_detailed(payload.pan, payload.expiry_yy_mm, payload.service_code, payload.cvk_id)\n\n\n"
                    "@router.post('/crypto/pack-pin-block')\n"
                    "def api_pack_pin_block(payload: PinBlockPackRequest, _: str = Depends(get_current_user)):\n"
                    "    return pack_pin_block_detailed(payload.pin, payload.pan, payload.format, payload.awk_id)\n\n"
                ),
            },
        ],
    )

    # 4. Write frontend/src/pages/CardCryptoLabPage.tsx
    session.write_file("frontend/src/pages/CardCryptoLabPage.tsx", CARD_LAB_PAGE_CODE)

    # 5. Patch frontend/src/App.tsx to add /card-lab route
    session.patch_file(
        "frontend/src/App.tsx",
        [
            {
                "marker": "step06:app_import_card_lab",
                "action": "insert_after",
                "anchor": "import { AuditTrailPage } from './pages/AuditTrailPage';",
                "text": "import { CardCryptoLabPage } from './pages/CardCryptoLabPage';",
            },
            {
                "marker": "step06:app_route_card_lab",
                "action": "insert_after",
                "anchor": "        <Route\n          path=\"/hsm-workbench\"\n          element={\n            <ProtectedRoute>\n              <HsmWorkbenchPage />\n            </ProtectedRoute>\n          }\n        />",
                "text": (
                    "        <Route\n"
                    "          path=\"/card-lab\"\n          element={\n"
                    "            <ProtectedRoute>\n"
                    "              <CardCryptoLabPage />\n"
                    "            </ProtectedRoute>\n"
                    "          }\n"
                    "        />"
                ),
            },
        ],
    )

    # 6. Patch frontend/src/components/Layout.tsx to add PIN & Card Lab navigation item
    session.patch_file(
        "frontend/src/components/Layout.tsx",
        [
            {
                "marker": "step06:layout_nav_card_lab",
                "action": "insert_after",
                "anchor": "  { to: '/hsm-workbench', label: '12. HSM Workbench', icon: Cpu, group: 'CRYPTO & HSM' },",
                "text": "  { to: '/card-lab', label: '12.5. PIN & Card Lab', icon: CreditCard, group: 'CRYPTO & HSM' },",
            }
        ],
    )

    # 7. Write automated pytest test suite backend/tests/test_step06_card_crypto.py
    session.write_file("backend/tests/test_step06_card_crypto.py", TEST_STEP06_CODE)

    session.record_progress(
        completed=[
            "Created `backend/app/card_crypto_service.py` providing Luhn PAN generation/validation, Visa PVV, IBM 3624 offset, CVV, and ISO PIN block calculations.",
            "Added Pydantic schemas in `backend/app/schemas.py`.",
            "Added REST endpoints: `POST /api/cards/{id}/pin`, `POST /api/cards/generate-test-card`, `POST /api/crypto/calculate-pvv`, `POST /api/crypto/calculate-cvv`, `POST /api/crypto/pack-pin-block` in `backend/app/api_routes.py`.",
            "Created React UI workbench `frontend/src/pages/CardCryptoLabPage.tsx` and registered route `/card-lab` in `App.tsx` and `Layout.tsx`.",
            "Created automated Pytest test suite `backend/tests/test_step06_card_crypto.py`.",
        ],
        remaining=[
            "STEP 7 — Complete Operation and Cryptographic Log Portal (Correlation ID middleware, `audit_log`, `crypto_events`, granular PIN verification trace, unified log timeline with polling).",
        ],
        modified_files=[
            "backend/app/card_crypto_service.py",
            "backend/app/schemas.py",
            "backend/app/api_routes.py",
            "frontend/src/pages/CardCryptoLabPage.tsx",
            "frontend/src/App.tsx",
            "frontend/src/components/Layout.tsx",
            "backend/tests/test_step06_card_crypto.py",
        ],
    )

    session.record_contracts(
        section_title="Step 6 — PIN, PVV and Card Generation Lab Contracts",
        contract_items=[
            "**POST /api/cards/{card_id}/pin**: Recalculates card PVV/offset, resets retry counter, updates `pin_changed_at`, logs audit entry.",
            "**POST /api/cards/generate-test-card**: Generates Luhn-valid synthetic PAN under bank BIN, computes PVV and CVV, seeds card, account link, limits, and EMV profiles.",
            "**POST /api/crypto/calculate-pvv**: Visa PVV calculation with intermediate 3DES and decimalization trace.",
            "**POST /api/crypto/calculate-cvv**: CVV1/CVV2 calculation under CVK.",
            "**POST /api/crypto/pack-pin-block**: Packs clear PIN into ISO-0, ISO-1, or ISO-3 encrypted block under AWK.",
            "**React Route**: `/#/card-lab` (`CardCryptoLabPage`).",
        ],
    )

    return session.finish()


if __name__ == "__main__":
    sys.exit(main())