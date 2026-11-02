import React, { useEffect, useState } from 'react';
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
                <div><span className="text-slate-400">3DES Ciphertext:</span> {pvvResult['3des_cipher_hex']}</div>
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
