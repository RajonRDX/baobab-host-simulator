#!/usr/bin/env python3
"""
INSTALLER: tools/install_step10.py
STEP 10 — HSM Key Management & Split-Component Ceremony (Single Unified Installer)
Adds:
  1. backend/app/key_ceremony_service.py (Parity, Component Assembly, KCV, ZMK Import/Export)
  2. Database columns clear_key_hex and parent_key_id in HsmKeyReference
  3. Pydantic schemas in backend/app/schemas.py
  4. Strict dynamic key resolution in backend/app/hsm_adapter.py
  5. REST endpoints in backend/app/api_routes.py
  6. frontend/src/pages/KeyCeremonyWorkbenchPage.tsx
  7. Route registration in App.tsx and Layout.tsx
  8. Automated Pytest test suite in backend/tests/test_step10_hsm_keys.py
"""

from pathlib import Path
import sys

BASE_DIR = Path(r"E:\HOST_VSCODE\host-simulator").resolve()
sys.path.insert(0, str(BASE_DIR))

from tools.patcher import PatcherSession, parse_installer_args

KEY_CEREMONY_SERVICE_CODE = '''"""
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
'''

KEY_CEREMONY_PAGE_CODE = '''import React, { useEffect, useState } from 'react';
import { KeyRound, ShieldCheck, Sparkles, RefreshCw, Copy, CheckCircle2, Lock, ArrowRight, Layers, Download, Upload } from 'lucide-react';
import { apiFetch } from '../api';

export const KeyCeremonyWorkbenchPage: React.FC = () => {
  const [tab, setTab] = useState<'CEREMONY' | 'RANDOM' | 'ZMK'>('CEREMONY');
  const [keys, setKeys] = useState<any[]>([]);
  const [institutions, setInstitutions] = useState<any[]>([]);
  const [msg, setMsg] = useState('');

  // 1. Ceremony State (Assembly)
  const [keyIdentifier, setKeyIdentifier] = useState('AWK_ATM_NEW_01');
  const [keyType, setKeyType] = useState('AWK');
  const [owningInstId, setOwningInstId] = useState('');
  const [comp1, setComp1] = useState('11111111111111111111111111111111');
  const [comp2, setComp2] = useState('22222222222222222222222222222222');
  const [comp3, setComp3] = useState('33333333333333333333333333333333');
  const [useThreeParts, setUseThreeParts] = useState(true);
  const [assemblyResult, setAssemblyResult] = useState<any | null>(null);

  // 2. Random Key State
  const [randomLength, setRandomLength] = useState(128);
  const [randomKeyResult, setRandomKeyResult] = useState<any | null>(null);

  // 3. ZMK Import / Export State
  const [selectedZmkId, setSelectedZmkId] = useState('ZMK_MAIN');
  const [exportKeyId, setExportKeyId] = useState('AWK_ATM_01');
  const [zmkExportResult, setZmkExportResult] = useState<any | null>(null);
  const [importEncKeyHex, setImportEncKeyHex] = useState('');
  const [importResult, setImportResult] = useState<any | null>(null);

  const loadData = async () => {
    try {
      const [kList, iList] = await Promise.all([
        apiFetch('/hsm/keys'),
        apiFetch('/institutions'),
      ]);
      setKeys(kList);
      setInstitutions(iList);
      if (iList.length > 0 && !owningInstId) setOwningInstId(iList[0].id);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleAssembleAndRegister = async () => {
    setMsg('');
    try {
      const components = useThreeParts ? [comp1, comp2, comp3] : [comp1, comp2];
      const res = await apiFetch('/hsm/ceremony/assemble-components', {
        method: 'POST',
        body: JSON.stringify({
          key_identifier: keyIdentifier,
          key_type: keyType,
          institution_id: owningInstId || null,
          components,
        }),
      });
      setAssemblyResult(res);
      setMsg(`Key Ceremony Successful: Key ${res.key_identifier} assembled (KVC: ${res.kvc}) and saved to database.`);
      loadData();
    } catch (err: any) {
      setMsg(`Error: ${err.message}`);
    }
  };

  const handleGenerateRandom = async () => {
    try {
      const res = await apiFetch('/hsm/ceremony/generate-random', {
        method: 'POST',
        body: JSON.stringify({ length_bits: randomLength }),
      });
      setRandomKeyResult(res);
    } catch (err: any) {
      alert(err.message);
    }
  };

  const handleExportUnderZmk = async () => {
    try {
      const res = await apiFetch('/hsm/ceremony/export-under-zmk', {
        method: 'POST',
        body: JSON.stringify({ key_identifier: exportKeyId, zmk_identifier: selectedZmkId }),
      });
      setZmkExportResult(res);
    } catch (err: any) {
      alert(err.message);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold">HSM Key Management & Split-Knowledge Ceremony</h1>
          <p className="text-xs text-slate-500">
            Execute 2/3 component XOR key ceremonies, odd-parity key generation, and ZMK key translation (Dual Control & Split Knowledge)
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono px-2.5 py-1 rounded bg-emerald-500/10 text-emerald-500 border border-emerald-500/20 font-bold">
            Policy: PCI-HSM Dual Control
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
          ['CEREMONY', '1. Split-Component Key Assembly Ceremony', Layers],
          ['RANDOM', '2. Parity-Verified Random Key Generator', Sparkles],
          ['ZMK', '3. ZMK Key Exchange (Import / Export)', KeyRound],
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

      {/* TAB 1: CEREMONY */}
      {tab === 'CEREMONY' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <div className="lg:col-span-7 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 space-y-4">
            <h2 className="text-sm font-bold flex justify-between items-center">
              <span>Split Knowledge Key Assembly Form</span>
              <label className="flex items-center gap-2 text-xs font-mono cursor-pointer">
                <input
                  type="checkbox"
                  checked={useThreeParts}
                  onChange={(e) => setUseThreeParts(e.target.checked)}
                />
                <span>Use 3 Custodians (3-Part XOR)</span>
              </label>
            </h2>

            <div className="grid grid-cols-2 gap-3 text-xs font-mono">
              <div>
                <label className="block text-slate-400 mb-1">New Key Identifier</label>
                <input
                  value={keyIdentifier}
                  onChange={(e) => setKeyIdentifier(e.target.value)}
                  placeholder="e.g. AWK_ATM_NEW_01"
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5 font-bold text-emerald-400"
                />
              </div>
              <div>
                <label className="block text-slate-400 mb-1">Key Type / Usage</label>
                <select
                  value={keyType}
                  onChange={(e) => setKeyType(e.target.value)}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5"
                >
                  {['AWK', 'ZPK', 'IWK', 'TMK', 'ZMK', 'PVK', 'CVK', 'TAK', 'MK-AC'].map(t => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="space-y-3 pt-2 text-xs font-mono">
              <div>
                <label className="block text-slate-400 mb-1">Custodian 1 Component (32 Hex Digits)</label>
                <input
                  value={comp1}
                  onChange={(e) => setComp1(e.target.value)}
                  maxLength={32}
                  className="w-full bg-slate-950 text-sky-300 border border-slate-800 rounded px-3 py-2 font-mono"
                />
              </div>
              <div>
                <label className="block text-slate-400 mb-1">Custodian 2 Component (32 Hex Digits)</label>
                <input
                  value={comp2}
                  onChange={(e) => setComp2(e.target.value)}
                  maxLength={32}
                  className="w-full bg-slate-950 text-amber-300 border border-slate-800 rounded px-3 py-2 font-mono"
                />
              </div>
              {useThreeParts && (
                <div>
                  <label className="block text-slate-400 mb-1">Custodian 3 Component (32 Hex Digits)</label>
                  <input
                    value={comp3}
                    onChange={(e) => setComp3(e.target.value)}
                    maxLength={32}
                    className="w-full bg-slate-950 text-indigo-300 border border-slate-800 rounded px-3 py-2 font-mono"
                  />
                </div>
              )}
            </div>

            <button
              onClick={handleAssembleAndRegister}
              className="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-semibold py-2.5 rounded-lg text-xs font-mono flex items-center justify-center gap-2"
            >
              <KeyRound size={15} /> Execute Ceremony: XOR Components & Save Key
            </button>
          </div>

          <div className="lg:col-span-5 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 space-y-4">
            <h2 className="text-sm font-bold">Ceremony Verification & KCV Breakdown</h2>
            {assemblyResult ? (
              <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono space-y-2">
                <div className="flex justify-between items-center text-emerald-400 font-bold border-b border-slate-800 pb-2">
                  <span>Assembled Key KCV:</span>
                  <span className="text-base text-amber-400 font-bold">{assemblyResult.kvc}</span>
                </div>
                <div><span className="text-slate-400">Key Identifier:</span> {assemblyResult.key_identifier}</div>
                <div><span className="text-slate-400">Type / Algorithm:</span> {assemblyResult.key_type} (3DES 128-bit)</div>
                <div><span className="text-slate-400">Odd Parity:</span> <span className="text-emerald-400 font-bold">VERIFIED</span></div>
                <div className="pt-2 border-t border-slate-800">
                  <div className="text-[11px] text-slate-400 mb-1">Custodian Component KCVs:</div>
                  {(assemblyResult.component_kcvs || []).map((kcv: string, idx: number) => (
                    <div key={idx} className="text-sky-300 text-[11px]">
                      Part #{idx + 1} KCV: <strong className="text-white">{kcv}</strong>
                    </div>
                  ))}
                </div>
                <div className="pt-2 text-[10px] text-emerald-400 font-sans">
                  ✓ Clear key saved to database. HostTransactionProcessor will dynamically use this key for all future transactions referencing {assemblyResult.key_identifier}.
                </div>
              </div>
            ) : (
              <div className="text-slate-400 text-xs font-mono py-16 text-center">
                Enter component hex values and click Execute to XOR assemble the operational key.
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 2: RANDOM KEY GENERATOR */}
      {tab === 'RANDOM' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <div className="lg:col-span-6 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 space-y-4">
            <h2 className="text-sm font-bold">Parity-Verified Key Generator</h2>
            <div className="space-y-3 text-xs font-mono">
              <div>
                <label className="block text-slate-400 mb-1">Key Length</label>
                <select
                  value={randomLength}
                  onChange={(e) => setRandomLength(parseInt(e.target.value))}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-2"
                >
                  <option value={128}>128-bit (2-Key 3DES / 32 Hex Characters)</option>
                  <option value={192}>192-bit (3-Key 3DES / 48 Hex Characters)</option>
                </select>
              </div>
            </div>
            <button
              onClick={handleGenerateRandom}
              className="bg-emerald-600 hover:bg-emerald-500 text-white font-semibold px-4 py-2 rounded-lg text-xs font-mono"
            >
              Generate Cryptographic Random Key ➔
            </button>
          </div>

          <div className="lg:col-span-6 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 space-y-4">
            <h2 className="text-sm font-bold">Generated Key Payload</h2>
            {randomKeyResult ? (
              <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono space-y-2">
                <div className="flex justify-between items-center text-emerald-400 font-bold border-b border-slate-800 pb-2">
                  <span>Computed KCV:</span>
                  <span className="text-base text-amber-400">{randomKeyResult.kcv}</span>
                </div>
                <div><span className="text-slate-400">Clear Hex Key:</span></div>
                <div className="p-2 rounded bg-slate-900 text-sky-300 break-all select-all">{randomKeyResult.key_hex}</div>
                <div><span className="text-slate-400">DES Odd Parity:</span> <span className="text-emerald-400 font-bold">ENFORCED (Mod-2 Validated)</span></div>
              </div>
            ) : (
              <div className="text-slate-400 text-xs font-mono py-12 text-center">
                Click generate to produce a high-entropy DES odd-parity key.
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 3: ZMK TRANSLATION */}
      {tab === 'ZMK' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <div className="lg:col-span-6 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 space-y-4">
            <h2 className="text-sm font-bold">Export Key Under Zone Master Key (ZMK)</h2>
            <div className="space-y-3 text-xs font-mono">
              <div>
                <label className="block text-slate-400 mb-1">Select ZMK Key</label>
                <select
                  value={selectedZmkId}
                  onChange={(e) => setSelectedZmkId(e.target.value)}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-2"
                >
                  {keys.filter(k => k.key_type === 'ZMK').map(k => (
                    <option key={k.id} value={k.key_identifier}>{k.key_identifier} ({k.key_name}) — KVC: {k.kvc}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-slate-400 mb-1">Key to Export Under ZMK</label>
                <select
                  value={exportKeyId}
                  onChange={(e) => setExportKeyId(e.target.value)}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-3 py-2"
                >
                  {keys.filter(k => k.key_type !== 'ZMK').map(k => (
                    <option key={k.id} value={k.key_identifier}>{k.key_identifier} ({k.key_type}) — KVC: {k.kvc}</option>
                  ))}
                </select>
              </div>
            </div>
            <button
              onClick={handleExportUnderZmk}
              className="bg-emerald-600 hover:bg-emerald-500 text-white font-semibold px-4 py-2 rounded-lg text-xs font-mono"
            >
              Export Under ZMK (Thales A6/A7) ➔
            </button>
          </div>

          <div className="lg:col-span-6 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 space-y-4">
            <h2 className="text-sm font-bold">Export Cryptogram Payload</h2>
            {zmkExportResult ? (
              <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono space-y-2">
                <div className="flex justify-between items-center text-emerald-400 font-bold border-b border-slate-800 pb-2">
                  <span>Export Cryptogram:</span>
                  <span className="text-amber-400">KCV: {zmkExportResult.key_kcv}</span>
                </div>
                <div className="text-slate-400">3DES Encrypted Under ZMK:</div>
                <div className="p-2.5 rounded bg-slate-900 text-amber-300 break-all select-all font-bold">
                  {zmkExportResult.encrypted_key_hex}
                </div>
                <div><span className="text-slate-400">ZMK KCV:</span> {zmkExportResult.zmk_kcv}</div>
              </div>
            ) : (
              <div className="text-slate-400 text-xs font-mono py-12 text-center">
                Select a key and ZMK to produce a transferable encrypted cryptogram.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
'''

TEST_STEP10_CODE = '''"""
test_step10_hsm_keys.py — Tests for Step 10 HSM Key Management & Key Ceremony
"""

import os
import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import HsmKeyReference
from app.key_ceremony_service import (
    assemble_components,
    enforce_des_odd_parity,
    export_key_under_zmk,
    generate_random_des_key,
    import_key_under_zmk,
    split_key_into_components,
    validate_des_parity,
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


def test_odd_parity_enforcement_and_validation():
    # Known key
    raw_key = "0123456789ABCDEF0123456789ABCDEF"
    parity_key = enforce_des_odd_parity(raw_key)
    assert validate_des_parity(parity_key) is True


def test_split_and_assemble_three_components():
    rand = generate_random_des_key(128)
    orig_key = rand["key_hex"]
    orig_kcv = rand["kcv"]

    # Split into 3 parts
    split = split_key_into_components(orig_key, 3)
    assert len(split["components"]) == 3

    # Assemble back
    comps = [c["hex"] for c in split["components"]]
    assembled = assemble_components(comps)
    assert assembled["kcv"] == orig_kcv


def test_assemble_and_register_endpoint(client, db_session):
    payload = {
        "key_identifier": "AWK_TEST_CEREMONY_01",
        "key_type": "AWK",
        "components": [
            "11111111111111111111111111111111",
            "22222222222222222222222222222222"
        ]
    }
    res = client.post("/api/hsm/ceremony/assemble-components", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["key_identifier"] == "AWK_TEST_CEREMONY_01"
    assert len(data["kvc"]) == 6

    # Verify key was persisted into the database with its clear hex
    key_db = db_session.query(HsmKeyReference).filter(HsmKeyReference.key_identifier == "AWK_TEST_CEREMONY_01").first()
    assert key_db is not None
    assert key_db.clear_key_hex is not None


def test_export_and_import_under_zmk():
    zmk = "0123456789ABCDEF0123456789ABCDEF"
    working_key = "1A2B3C4D5E6F70811A2B3C4D5E6F7081"

    exported = export_key_under_zmk(working_key, zmk)
    assert len(exported["encrypted_key_hex"]) == 32

    imported = import_key_under_zmk(exported["encrypted_key_hex"], zmk)
    assert imported["kcv"] == exported["key_kcv"]
'''


def main() -> int:
    args = parse_installer_args("Step 10: HSM Key Management & Split-Component Ceremony")
    session = PatcherSession(
        step_id="step10",
        title="Implement Split-Component Key Ceremony, Parity Enforcement, and ZMK Key Exchange",
        dry_run=args.dry_run,
    )

    # 1. Write backend/app/key_ceremony_service.py
    session.write_file("backend/app/key_ceremony_service.py", KEY_CEREMONY_SERVICE_CODE)

    # 2. Patch backend/app/models.py to add clear_key_hex and parent_key_id to HsmKeyReference
    session.patch_file(
        "backend/app/models.py",
        [
            {
                "marker": "step10:hsm_key_ceremony_columns",
                "action": "insert_after",
                "anchor": "    key_status: Mapped[str] = mapped_column(String(20), nullable=False, default=\"ACTIVE\")",
                "text": (
                    "    clear_key_hex: Mapped[Optional[str]] = mapped_column(String(64))\n"
                    "    parent_key_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey('hsm_key_references.id'), index=True)\n"
                    "    parent_key: Mapped[Optional['HsmKeyReference']] = relationship('HsmKeyReference', remote_side=[id])"
                ),
            }
        ],
    )

    # 3. Patch backend/app/schemas.py to add ceremony schemas
    session.patch_file(
        "backend/app/schemas.py",
        [
            {
                "marker": "step10:schemas_key_ceremony",
                "action": "append",
                "text": (
                    "\n# ==============================================================================\n"
                    "# STEP 10 SCHEMAS: HSM KEY CEREMONY & EXCHANGE\n"
                    "# ==============================================================================\n\n"
                    "class RandomKeyGenerateRequest(BaseModel):\n"
                    "    length_bits: int = 128\n\n\n"
                    "class KeyAssemblyRequest(BaseModel):\n"
                    "    key_identifier: str = Field(..., min_length=3, max_length=100)\n"
                    "    key_type: str = 'AWK'\n"
                    "    key_name: Optional[str] = None\n"
                    "    institution_id: Optional[str] = None\n"
                    "    components: List[str] = Field(..., min_length=2, max_length=3)\n\n\n"
                    "class KeyExportUnderZmkRequest(BaseModel):\n"
                    "    key_identifier: str\n"
                    "    zmk_identifier: str = 'ZMK_MAIN'\n\n\n"
                    "class KeyImportUnderZmkRequest(BaseModel):\n"
                    "    key_identifier: str\n"
                    "    key_type: str = 'AWK'\n"
                    "    encrypted_key_hex: str\n"
                    "    zmk_identifier: str = 'ZMK_MAIN'\n"
                    "    institution_id: Optional[str] = None\n\n\n"
                    "class KeyCeremonyResultOut(BaseModel):\n"
                    "    key_identifier: str\n"
                    "    key_type: str\n"
                    "    kvc: str\n"
                    "    component_kcvs: List[str] = Field(default_factory=list)\n"
                    "    status: str = 'REGISTERED'\n"
                ),
            }
        ],
    )

    # 4. Patch backend/app/hsm_adapter.py to strictly query clear keys from HsmKeyReference
    session.patch_file(
        "backend/app/hsm_adapter.py",
        [
            {
                "marker": "step10:hsm_adapter_strict_key_resolution",
                "action": "replace",
                "anchor": (
                    "    def _resolve_key(self, key_identifier: str) -> Tuple[Optional[HsmKeyReference], str]:\n"
                    "        key_ref = (\n"
                    "            self.db.query(HsmKeyReference)\n"
                    "            .filter(HsmKeyReference.key_identifier == key_identifier)\n"
                    "            .first()\n"
                    "        )\n"
                    "        clear_key = SoftHsmCryptoCore.INTERNAL_CLEAR_KEYS.get(\n"
                    "            key_identifier, \"0123456789ABCDEF0123456789ABCDEF\"\n"
                    "        )\n"
                    "        return key_ref, clear_key"
                ),
                "text": (
                    "    def _resolve_key(self, key_identifier: str) -> Tuple[Optional[HsmKeyReference], str]:\n"
                    "        key_ref = (\n"
                    "            self.db.query(HsmKeyReference)\n"
                    "            .filter(HsmKeyReference.key_identifier == key_identifier)\n"
                    "            .first()\n"
                    "        )\n"
                    "        # 1. Resolve from database clear_key_hex if ceremony-created\n"
                    "        if key_ref and key_ref.clear_key_hex:\n"
                    "            return key_ref, key_ref.clear_key_hex\n\n"
                    "        # 2. Resolve from internal protected key dictionary\n"
                    "        if key_identifier in SoftHsmCryptoCore.INTERNAL_CLEAR_KEYS:\n"
                    "            return key_ref, SoftHsmCryptoCore.INTERNAL_CLEAR_KEYS[key_identifier]\n\n"
                    "        # 3. Strict error if key is unknown\n"
                    "        raise ValueError(f'Unknown cryptographic key reference: {key_identifier}')"
                ),
            }
        ],
    )

    # 5. Patch backend/app/seed_data.py to populate clear_key_hex on seeded HSM keys
    session.patch_file(
        "backend/app/seed_data.py",
        [
            {
                "marker": "step10:seed_clear_key_hex",
                "action": "insert_after",
                "anchor": "                algorithm=\"3DES_2KEY\",\n                key_length=128,",
                "text": "                clear_key_hex=clear,",
            }
        ],
    )

    # 6. Patch backend/app/api_routes.py to add key ceremony endpoints
    session.patch_file(
        "backend/app/api_routes.py",
        [
            {
                "marker": "step10:api_routes_ceremony_schemas",
                "action": "insert_after",
                "anchor": "from app.schemas import (",
                "text": (
                    "    KeyAssemblyRequest,\n"
                    "    KeyCeremonyResultOut,\n"
                    "    KeyExportUnderZmkRequest,\n"
                    "    KeyImportUnderZmkRequest,\n"
                    "    RandomKeyGenerateRequest,"
                ),
            },
            {
                "marker": "step10:api_routes_ceremony_service_import",
                "action": "insert_after",
                "anchor": "from app.audit_service import record_audit, serialize_entity",
                "text": (
                    "from app.key_ceremony_service import (\n"
                    "    assemble_components,\n"
                    "    export_key_under_zmk,\n"
                    "    generate_random_des_key,\n"
                    "    import_key_under_zmk,\n"
                    ")"
                ),
            },
            {
                "marker": "step10:api_ceremony_endpoints",
                "action": "append",
                "text": (
                    "\n# ==============================================================================\n"
                    "# STEP 10 API ENDPOINTS: SPLIT-COMPONENT KEY CEREMONY & EXCHANGE\n"
                    "# ==============================================================================\n\n"
                    "@router.post('/hsm/ceremony/generate-random')\n"
                    "def api_generate_random_key(payload: RandomKeyGenerateRequest, _: str = Depends(get_current_user)):\n"
                    "    return generate_random_des_key(payload.length_bits)\n\n\n"
                    "@router.post('/hsm/ceremony/assemble-components', response_model=KeyCeremonyResultOut)\n"
                    "def api_assemble_key_components(payload: KeyAssemblyRequest, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):\n"
                    "    res = assemble_components(payload.components)\n"
                    "    key_id = payload.key_identifier.strip()\n"
                    "    existing = db.query(HsmKeyReference).filter(HsmKeyReference.key_identifier == key_id).first()\n"
                    "    if existing:\n"
                    "        existing.clear_key_hex = res['assembled_key_hex']\n"
                    "        existing.kvc = res['kcv']\n"
                    "        existing.key_status = 'ACTIVE'\n"
                    "        db.commit()\n"
                    "        key_rec = existing\n"
                    "    else:\n"
                    "        key_rec = HsmKeyReference(\n"
                    "            key_name=payload.key_name or f'Ceremony {payload.key_type} Key',\n"
                    "            key_type=payload.key_type.upper(),\n"
                    "            key_usage=f'{payload.key_type.upper()}_OPERATIONAL',\n"
                    "            key_identifier=key_id,\n"
                    "            kvc=res['kcv'],\n"
                    "            algorithm='3DES_2KEY',\n"
                    "            key_length=res['length_bits'],\n"
                    "            hsm_key_reference=f'LMK_CEREMONY::{key_id}',\n"
                    "            clear_key_hex=res['assembled_key_hex'],\n"
                    "            institution_id=payload.institution_id,\n"
                    "            key_status='ACTIVE',\n"
                    "        )\n"
                    "        db.add(key_rec)\n"
                    "        db.commit()\n\n"
                    "    record_audit(db, 'HSM_KEY', key_rec.id, 'KEY_CEREMONY', performed_by=current_user,\n"
                    "                 change_summary=f'Assembled {key_id} from {res[\"components_count\"]} components (KVC: {res[\"kcv\"]})')\n"
                    "    db.commit()\n"
                    "    return KeyCeremonyResultOut(\n"
                    "        key_identifier=key_id,\n"
                    "        key_type=payload.key_type,\n"
                    "        kvc=res['kcv'],\n"
                    "        component_kcvs=res['component_kcvs'],\n"
                    "        status='REGISTERED',\n"
                    "    )\n\n\n"
                    "@router.post('/hsm/ceremony/export-under-zmk')\n"
                    "def api_export_key_under_zmk(payload: KeyExportUnderZmkRequest, db: Session = Depends(get_db), _: str = Depends(get_current_user)):\n"
                    "    # Resolve working key\n"
                    "    key_ref = db.query(HsmKeyReference).filter(HsmKeyReference.key_identifier == payload.key_identifier).first()\n"
                    "    wk_clear = (key_ref.clear_key_hex if (key_ref and key_ref.clear_key_hex) else SoftHsmCryptoCore.INTERNAL_CLEAR_KEYS.get(payload.key_identifier))\n"
                    "    if not wk_clear:\n"
                    "        raise HTTPException(status_code=404, detail=f'Working key {payload.key_identifier} not found')\n\n"
                    "    # Resolve ZMK\n"
                    "    zmk_ref = db.query(HsmKeyReference).filter(HsmKeyReference.key_identifier == payload.zmk_identifier).first()\n"
                    "    zmk_clear = (zmk_ref.clear_key_hex if (zmk_ref and zmk_ref.clear_key_hex) else SoftHsmCryptoCore.INTERNAL_CLEAR_KEYS.get(payload.zmk_identifier))\n"
                    "    if not zmk_clear:\n"
                    "        raise HTTPException(status_code=404, detail=f'ZMK {payload.zmk_identifier} not found')\n\n"
                    "    return export_key_under_zmk(wk_clear, zmk_clear)\n\n\n"
                    "@router.post('/hsm/ceremony/import-under-zmk')\n"
                    "def api_import_key_under_zmk(payload: KeyImportUnderZmkRequest, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):\n"
                    "    zmk_ref = db.query(HsmKeyReference).filter(HsmKeyReference.key_identifier == payload.zmk_identifier).first()\n"
                    "    zmk_clear = (zmk_ref.clear_key_hex if (zmk_ref and zmk_ref.clear_key_hex) else SoftHsmCryptoCore.INTERNAL_CLEAR_KEYS.get(payload.zmk_identifier))\n"
                    "    if not zmk_clear:\n"
                    "        raise HTTPException(status_code=404, detail=f'ZMK {payload.zmk_identifier} not found')\n\n"
                    "    res = import_key_under_zmk(payload.encrypted_key_hex, zmk_clear)\n"
                    "    key_id = payload.key_identifier.strip()\n"
                    "    existing = db.query(HsmKeyReference).filter(HsmKeyReference.key_identifier == key_id).first()\n"
                    "    if existing:\n"
                    "        existing.clear_key_hex = res['clear_key_hex']\n"
                    "        existing.kvc = res['kcv']\n"
                    "        db.commit()\n"
                    "    else:\n"
                    "        key_rec = HsmKeyReference(\n"
                    "            key_name=f'Imported {payload.key_type} Key',\n"
                    "            key_type=payload.key_type.upper(),\n"
                    "            key_usage=f'{payload.key_type.upper()}_OPERATIONAL',\n"
                    "            key_identifier=key_id,\n"
                    "            kvc=res['kcv'],\n"
                    "            algorithm='3DES_2KEY',\n"
                    "            key_length=128,\n"
                    "            hsm_key_reference=f'LMK_IMPORTED::{key_id}',\n"
                    "            clear_key_hex=res['clear_key_hex'],\n"
                    "            institution_id=payload.institution_id,\n"
                    "            key_status='ACTIVE',\n"
                    "        )\n"
                    "        db.add(key_rec)\n"
                    "        db.commit()\n\n"
                    "    record_audit(db, 'HSM_KEY', key_id, 'KEY_IMPORT_ZMK', performed_by=current_user,\n"
                    "                 change_summary=f'Imported key {key_id} under {payload.zmk_identifier} (KVC: {res[\"kcv\"]})')\n"
                    "    db.commit()\n"
                    "    return {'key_identifier': key_id, 'kvc': res['kcv'], 'status': 'IMPORTED'}\n"
                ),
            },
        ],
    )

    # 7. Write frontend/src/pages/KeyCeremonyWorkbenchPage.tsx
    session.write_file("frontend/src/pages/KeyCeremonyWorkbenchPage.tsx", KEY_CEREMONY_PAGE_CODE)

    # 8. Patch frontend/src/App.tsx to add /key-ceremony route
    session.patch_file(
        "frontend/src/App.tsx",
        [
            {
                "marker": "step10:app_import_key_ceremony",
                "action": "insert_after",
                "anchor": "import { CardCryptoLabPage } from './pages/CardCryptoLabPage';",
                "text": "import { KeyCeremonyWorkbenchPage } from './pages/KeyCeremonyWorkbenchPage';",
            },
            {
                "marker": "step10:app_route_key_ceremony",
                "action": "insert_after",
                "anchor": "        <Route\n          path=\"/card-lab\"\n          element={\n            <ProtectedRoute>\n              <CardCryptoLabPage />\n            </ProtectedRoute>\n          }\n        />",
                "text": (
                    "        <Route\n"
                    "          path=\"/key-ceremony\"\n          element={\n"
                    "            <ProtectedRoute>\n"
                    "              <KeyCeremonyWorkbenchPage />\n"
                    "            </ProtectedRoute>\n"
                    "          }\n"
                    "        />"
                ),
            },
        ],
    )

    # 9. Patch frontend/src/components/Layout.tsx to add Key Ceremony navigation link
    session.patch_file(
        "frontend/src/components/Layout.tsx",
        [
            {
                "marker": "step10:layout_nav_key_ceremony",
                "action": "insert_after",
                "anchor": "  { to: '/card-lab', label: '12.5. PIN & Card Lab', icon: CreditCard, group: 'CRYPTO & HSM' },",
                "text": "  { to: '/key-ceremony', label: '12.8. Key Ceremony Lab', icon: Layers, group: 'CRYPTO & HSM' },",
            }
        ],
    )

    # 10. Write automated pytest test suite backend/tests/test_step10_hsm_keys.py
    session.write_file("backend/tests/test_step10_hsm_keys.py", TEST_STEP10_CODE)

    session.record_progress(
        completed=[
            "Created `backend/app/key_ceremony_service.py` providing DES odd-parity adjustment, 2/3 component XOR assembly, and ZMK import/export.",
            "Added `clear_key_hex` and `parent_key_id` to `HsmKeyReference` in `backend/app/models.py`.",
            "Added Pydantic schemas in `backend/app/schemas.py`.",
            "Enforced strict key resolution in `backend/app/hsm_adapter.py` without silent fallbacks.",
            "Added REST endpoints: `POST /api/hsm/ceremony/assemble-components`, `POST /api/hsm/ceremony/generate-random`, `POST /api/hsm/ceremony/export-under-zmk`, `POST /api/hsm/ceremony/import-under-zmk`.",
            "Created React UI workbench `frontend/src/pages/KeyCeremonyWorkbenchPage.tsx` and registered route `/key-ceremony` in `App.tsx` and `Layout.tsx`.",
            "Created automated Pytest test suite `backend/tests/test_step10_hsm_keys.py`.",
        ],
        remaining=[
            "STEP 11 — Routing and Network Simulation (On-Us/Off-Us routing, SimulatedNetworkAdapter, timeout handling, and cross-zone PIN translation).",
            "STEP 12 — Clearing and Settlement (Authorization holds, 0220 advices, 0420 reversals, daily cutover, institution fee reconciliation, and settlement reports).",
        ],
        modified_files=[
            "backend/app/key_ceremony_service.py",
            "backend/app/models.py",
            "backend/app/schemas.py",
            "backend/app/hsm_adapter.py",
            "backend/app/seed_data.py",
            "backend/app/api_routes.py",
            "frontend/src/pages/KeyCeremonyWorkbenchPage.tsx",
            "frontend/src/App.tsx",
            "frontend/src/components/Layout.tsx",
            "backend/tests/test_step10_hsm_keys.py",
        ],
    )

    session.record_contracts(
        section_title="Step 10 — HSM Key Ceremony & Management Contracts",
        contract_items=[
            "**Model Columns**: `hsm_key_references.clear_key_hex`, `hsm_key_references.parent_key_id`.",
            "**POST /api/hsm/ceremony/assemble-components**: Assembles 2 or 3 clear components via XOR, verifies odd parity, computes KCVs, saves key to database.",
            "**POST /api/hsm/ceremony/generate-random**: Generates 128/192-bit DES odd-parity key.",
            "**POST /api/hsm/ceremony/export-under-zmk**: Encrypts working key under ZMK for exchange.",
            "**POST /api/hsm/ceremony/import-under-zmk**: Decrypts working key under ZMK, saves key to database.",
            "**Strict Key Resolution**: `HSMAdapter._resolve_key` raises error if key identifier is missing rather than falling back to default.",
            "**React Route**: `/#/key-ceremony` (`KeyCeremonyWorkbenchPage`).",
        ],
    )

    return session.finish()


if __name__ == "__main__":
    sys.exit(main())