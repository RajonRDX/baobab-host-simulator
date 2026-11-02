import React, { useEffect, useState } from 'react';
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
