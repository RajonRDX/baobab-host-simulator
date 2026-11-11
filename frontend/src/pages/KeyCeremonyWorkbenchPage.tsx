import React, { useEffect, useState } from 'react';
import { api } from '../services/api';

interface KeyRecord {
  id: string;
  key_identifier: string;
  key_name: string;
  key_type: string;
  thales_key_type_code: string;
  key_usage: string;
  key_scheme: string;
  key_version: number;
  key_status: string;
  kvc: string;
  algorithm: string;
  key_length: number;
  provider_type: 'INTERNAL_HSM' | 'EXTERNAL_HSM';
  lmk_id: string;
  lmk_check_value: string | null;
  encrypted_key_block: string;
  masked_key_block: string;
  institution_code?: string;
  created_at?: string;
}

export const KeyCeremonyWorkbenchPage: React.FC = () => {
  const [lmkStatus, setLmkStatus] = useState<any>(null);
  const [auditReport, setAuditReport] = useState<any>(null);
  const [keys, setKeys] = useState<KeyRecord[]>([]);
  const [providerFilter, setProviderFilter] = useState<string>('ACTIVE_PROVIDER');
  const [remoteUrlInput, setRemoteUrlInput] = useState<string>('https://thales-10k-soft-hsm.onrender.com');
  const [loading, setLoading] = useState<boolean>(false);
  const [banner, setBanner] = useState<{ type: 'ok' | 'err' | 'warn'; msg: string } | null>(null);
  const [activeTab, setActiveTab] = useState<'inventory' | 'a0_generate' | 'a6_import' | 'a8_export' | 'audit'>('inventory');

  // A0 Key Generation Form State
  const [a0Alias, setA0Alias] = useState('ZPK_EXT_ISS_01');
  const [a0Name, setA0Name] = useState('External Interchange ZPK');
  const [a0Type, setA0Type] = useState('ZPK');
  const [a0Scheme, setA0Scheme] = useState('U');
  const [a0Mode, setA0Mode] = useState('0');
  const [a0ZmkAlias, setA0ZmkAlias] = useState('ZMK_MAIN');
  const [a0Result, setA0Result] = useState<any>(null);

  // A6 Key Import Form State
  const [a6Alias, setA6Alias] = useState('ZPK_PARTNER_IMP_01');
  const [a6Name, setA6Name] = useState('Imported Partner ZPK');
  const [a6Type, setA6Type] = useState('ZPK');
  const [a6ZmkAlias, setA6ZmkAlias] = useState('ZMK_MAIN');
  const [a6EncKey, setA6EncKey] = useState('');
  const [a6Scheme, setA6Scheme] = useState('U');
  const [a6Result, setA6Result] = useState<any>(null);

  // A8 Key Export Form State
  const [a8KeyAlias, setA8KeyAlias] = useState('AWK_ATM_01');
  const [a8ZmkAlias, setA8ZmkAlias] = useState('ZMK_MAIN');
  const [a8Scheme, setA8Scheme] = useState('U');
  const [a8Result, setA8Result] = useState<any>(null);

  const loadAll = async (filterOverride?: string) => {
    setLoading(true);
    try {
      const statusRes = await api.get('/api/hsm/lmk-key-management/status');
      setLmkStatus(statusRes.data);
      if (statusRes.data?.remote_url) {
        setRemoteUrlInput(statusRes.data.remote_url);
      }
      const effFilter = filterOverride || providerFilter;
      const qParam = effFilter === 'ACTIVE_PROVIDER' ? statusRes.data.active_provider : effFilter;
      const keysRes = await api.get(`/api/hsm/lmk-key-management/keys?provider_type=${qParam}&include_superseded=true`);
      setKeys(keysRes.data.keys || []);
    } catch (e: any) {
      setBanner({ type: 'err', msg: e?.response?.data?.detail || e.message || 'Failed to load HSM key status' });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAll();
  }, []);

  const handleSwitchProvider = async (mode: 'INTERNAL_HSM' | 'EXTERNAL_HSM') => {
    setBanner(null);
    try {
      const res = await api.post('/api/hsm/lmk-key-management/provider', {
        provider_mode: mode,
        remote_url: remoteUrlInput.trim(),
      });
      setLmkStatus(res.data);
      setBanner({
        type: res.data.online ? 'ok' : 'warn',
        msg: `Switched Cryptographic Authority to ${res.data.active_provider} (LMK KCV: ${res.data.lmk_check_value})`,
      });
      await loadAll(mode);
    } catch (e: any) {
      setBanner({ type: 'err', msg: e?.response?.data?.detail || 'Provider switch failed' });
    }
  };

  const handleSyncExternalKeys = async () => {
    setBanner(null);
    try {
      const res = await api.post('/api/hsm/lmk-key-management/sync-seeded');
      setBanner({
        type: 'ok',
        msg: `Synchronized & BU-verified ${res.data.count} LMK-encrypted keys from External Soft-HSM (Domain ${res.data.lmk_check_value})`,
      });
      await loadAll('EXTERNAL_HSM');
    } catch (e: any) {
      setBanner({ type: 'err', msg: e?.response?.data?.detail || 'Failed to sync keys from External Soft-HSM' });
    }
  };

  const handleGenerateA0 = async () => {
    setBanner(null);
    setA0Result(null);
    try {
      const res = await api.post('/api/hsm/lmk-key-management/generate', {
        key_identifier: a0Alias,
        key_name: a0Name,
        key_type: a0Type,
        key_scheme: a0Scheme,
        mode: a0Mode,
        export_zmk_key_identifier: a0Mode === '1' ? a0ZmkAlias : undefined,
      });
      setA0Result(res.data);
      setBanner({
        type: 'ok',
        msg: `Soft-HSM Command A0 (A100) succeeded. Stored LMK key block for '${res.data.key.key_identifier}' (KCV: ${res.data.key.kvc})`,
      });
      await loadAll();
    } catch (e: any) {
      setBanner({ type: 'err', msg: e?.response?.data?.detail || 'Soft-HSM A0 key generation failed' });
    }
  };

  const handleImportA6 = async () => {
    setBanner(null);
    setA6Result(null);
    try {
      const res = await api.post('/api/hsm/lmk-key-management/import', {
        key_identifier: a6Alias,
        key_name: a6Name,
        key_type: a6Type,
        zmk_key_identifier: a6ZmkAlias,
        encrypted_key_under_zmk: a6EncKey,
        key_scheme_lmk: a6Scheme,
      });
      setA6Result(res.data);
      setBanner({
        type: 'ok',
        msg: `Soft-HSM Command A6 (A700) succeeded. Imported '${res.data.key.key_identifier}' under LMK (KCV: ${res.data.key.kvc})`,
      });
      await loadAll();
    } catch (e: any) {
      setBanner({ type: 'err', msg: e?.response?.data?.detail || 'Soft-HSM A6 key import failed' });
    }
  };

  const handleExportA8 = async () => {
    setBanner(null);
    setA8Result(null);
    try {
      const res = await api.post('/api/hsm/lmk-key-management/export', {
        key_identifier: a8KeyAlias,
        zmk_key_identifier: a8ZmkAlias,
        export_scheme: a8Scheme,
      });
      setA8Result(res.data);
      setBanner({
        type: 'ok',
        msg: `Soft-HSM Command A8 (A900) succeeded. Exported '${a8KeyAlias}' under '${a8ZmkAlias}' (KCV: ${res.data.kcv})`,
      });
    } catch (e: any) {
      setBanner({ type: 'err', msg: e?.response?.data?.detail || 'Soft-HSM A8 key export failed' });
    }
  };

  const handleVerifyBu = async (alias: string) => {
    setBanner(null);
    try {
      const res = await api.post(`/api/hsm/lmk-key-management/verify-kcv/${alias}`);
      setBanner({
        type: res.data.kcv_matched ? 'ok' : 'warn',
        msg: `Soft-HSM BU (BV00) check for '${alias}': Calculated KCV ${res.data.calculated_kvc} (Stored: ${res.data.stored_kvc}) | Raw: ${res.data.raw_response}`,
      });
    } catch (e: any) {
      setBanner({ type: 'err', msg: e?.response?.data?.detail || `BU check failed for ${alias}` });
    }
  };

  const handleRotateKey = async (alias: string) => {
    setBanner(null);
    try {
      const res = await api.post('/api/hsm/lmk-key-management/rotate', { key_identifier: alias });
      setBanner({
        type: 'ok',
        msg: `Rotated '${alias}' via Soft-HSM A0: v${res.data.previous_version} to v${res.data.new_version} (New KCV: ${res.data.key.kvc})`,
      });
      await loadAll();
    } catch (e: any) {
      setBanner({ type: 'err', msg: e?.response?.data?.detail || `Rotation failed for ${alias}` });
    }
  };

  const handleDeleteKey = async (id: string, alias: string) => {
    setBanner(null);
    try {
      await api.delete(`/api/hsm/keys/${id}?force=true`);
      setBanner({ type: 'ok', msg: `Deleted key record '${alias}' from Host inventory` });
      await loadAll();
    } catch (e: any) {
      setBanner({ type: 'err', msg: e?.response?.data?.detail || 'Delete failed' });
    }
  };

  const loadAuditDeliverable = async () => {
    setActiveTab('audit');
    try {
      const res = await api.get('/api/hsm/lmk-key-management/audit-report');
      setAuditReport(res.data);
    } catch (e: any) {
      setBanner({ type: 'err', msg: 'Failed to load audit report' });
    }
  };

  const isExternal = lmkStatus?.active_provider === 'EXTERNAL_HSM';

  return (
    <div className="space-y-6">
      {/* Header & Active Cryptographic Authority Banner */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
        <div className="flex flex-wrap justify-between items-center gap-4">
          <div>
            <h1 className="text-xl font-bold text-white font-mono">
              LMK-Centric Key Management & Cryptographic Ownership
            </h1>
            <p className="text-xs text-slate-400 mt-1">
              Thales payShield 10K LMK Domain Isolation · Zero Clear Key Storage · Live A0 / A6 / A8 / BU / NC Execution
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => handleSwitchProvider('INTERNAL_HSM')}
              className={`px-3 py-1.5 rounded text-xs font-mono font-bold transition ${
                !isExternal ? 'bg-sky-600 text-white' : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
              }`}
            >
              Internal Simulator HSM
            </button>
            <button
              onClick={() => handleSwitchProvider('EXTERNAL_HSM')}
              className={`px-3 py-1.5 rounded text-xs font-mono font-bold transition ${
                isExternal ? 'bg-emerald-600 text-white' : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
              }`}
            >
              External Soft-HSM Authority
            </button>
          </div>
        </div>

        {/* LMK Domain Status Grid */}
        {lmkStatus && (
          <div className="grid grid-cols-1 md:grid-cols-5 gap-3 pt-2 border-t border-slate-800 text-xs font-mono">
            <div className="bg-slate-950 border border-slate-800 p-3 rounded">
              <div className="text-slate-400">Active Authority</div>
              <div className={`font-bold mt-1 ${isExternal ? 'text-emerald-400' : 'text-sky-400'}`}>
                {lmkStatus.active_provider} ({lmkStatus.online ? 'ONLINE' : 'OFFLINE'})
              </div>
            </div>
            <div className="bg-slate-950 border border-slate-800 p-3 rounded">
              <div className="text-slate-400">LMK Domain Check Value (NC)</div>
              <div className="font-bold text-amber-400 mt-1">
                Slot %{lmkStatus.lmk_id || '00'} · {lmkStatus.lmk_check_value}
              </div>
            </div>
            <div className="bg-slate-950 border border-slate-800 p-3 rounded">
              <div className="text-slate-400">HSM State & Firmware</div>
              <div className="font-bold text-slate-200 mt-1">
                {lmkStatus.hsm_state} ({lmkStatus.firmware})
              </div>
            </div>
            <div className="bg-slate-950 border border-slate-800 p-3 rounded md:col-span-2">
              <div className="text-slate-400 mb-1">External Soft-HSM Endpoint & Seeded LMK Sync</div>
              <div className="flex gap-2">
                <input
                  value={remoteUrlInput}
                  onChange={(e) => setRemoteUrlInput(e.target.value)}
                  className="flex-1 bg-slate-900 border border-slate-700 rounded px-2 py-1 text-emerald-300 text-xs"
                  placeholder="https://thales-10k-soft-hsm.onrender.com"
                />
                <button
                  onClick={handleSyncExternalKeys}
                  className="bg-emerald-700 hover:bg-emerald-600 px-3 py-1 rounded text-white font-bold whitespace-nowrap"
                >
                  Sync LMK Keys
                </button>
              </div>
            </div>
          </div>
        )}

        {lmkStatus?.persistence_audit?.ephemeral_risk && (
          <div className="bg-amber-950/50 border border-amber-700/60 rounded p-2.5 text-xs font-mono text-amber-200">
            <strong>LMK Persistence Notice:</strong> {lmkStatus.persistence_audit.ephemeral_risk}
          </div>
        )}

        {banner && (
          <div
            className={`p-3 rounded text-xs font-mono border ${
              banner.type === 'ok'
                ? 'bg-emerald-950/70 border-emerald-700 text-emerald-200'
                : banner.type === 'warn'
                ? 'bg-amber-950/70 border-amber-700 text-amber-200'
                : 'bg-rose-950/70 border-rose-700 text-rose-200'
            }`}
          >
            {banner.msg}
          </div>
        )}
      </div>

      {/* Navigation Tabs */}
      <div className="flex flex-wrap gap-2 border-b border-slate-800 pb-2 font-mono text-xs">
        {[
          { id: 'inventory', label: '1. Key Inventory & LMK Domains' },
          { id: 'a0_generate', label: '2. Generate Key (Soft-HSM A0)' },
          { id: 'a6_import', label: '3. Import Key (Soft-HSM A6)' },
          { id: 'a8_export', label: '4. Export / Translate Key (Soft-HSM A8)' },
          { id: 'audit', label: '5. Mandatory LMK Audit Deliverable (Part G)' },
        ].map((t) => (
          <button
            key={t.id}
            onClick={() => (t.id === 'audit' ? loadAuditDeliverable() : setActiveTab(t.id as any))}
            className={`px-3.5 py-2 rounded font-bold transition ${
              activeTab === t.id ? 'bg-emerald-600 text-white' : 'bg-slate-900 text-slate-300 hover:bg-slate-800'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* TAB 1: KEY INVENTORY */}
      {activeTab === 'inventory' && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
          <div className="flex flex-wrap justify-between items-center gap-3">
            <h2 className="text-sm font-bold font-mono text-emerald-400">
              Cryptographic Key Inventory (Sensitive Key Material Strictly Hidden)
            </h2>
            <div className="flex items-center gap-2 text-xs font-mono">
              <span className="text-slate-400">Filter Provider:</span>
              {['ACTIVE_PROVIDER', 'EXTERNAL_HSM', 'INTERNAL_HSM', 'ALL'].map((pf) => (
                <button
                  key={pf}
                  onClick={() => {
                    setProviderFilter(pf);
                    loadAll(pf);
                  }}
                  className={`px-2.5 py-1 rounded ${
                    providerFilter === pf ? 'bg-emerald-600 text-white font-bold' : 'bg-slate-800 text-slate-300'
                  }`}
                >
                  {pf}
                </button>
              ))}
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left font-mono text-xs border-collapse">
              <thead>
                <tr className="border-b border-slate-800 text-slate-400">
                  <th className="py-2 px-2">Key Alias</th>
                  <th className="py-2 px-2">Provider</th>
                  <th className="py-2 px-2">Type (Thales)</th>
                  <th className="py-2 px-2">Usage</th>
                  <th className="py-2 px-2">Scheme</th>
                  <th className="py-2 px-2">Ver</th>
                  <th className="py-2 px-2">KCV</th>
                  <th className="py-2 px-2">LMK Domain</th>
                  <th className="py-2 px-2">LMK-Encrypted Block (Masked)</th>
                  <th className="py-2 px-2">Status</th>
                  <th className="py-2 px-2">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {keys.map((k) => (
                  <tr key={k.id} className="hover:bg-slate-800/40">
                    <td className="py-2 px-2 font-bold text-emerald-400">
                      <div>{k.key_identifier}</div>
                      <div className="text-[10px] text-slate-400 font-normal">{k.key_name}</div>
                    </td>
                    <td className="py-2 px-2">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          k.provider_type === 'EXTERNAL_HSM'
                            ? 'bg-emerald-950 text-emerald-300 border border-emerald-700'
                            : 'bg-sky-950 text-sky-300 border border-sky-700'
                        }`}
                      >
                        {k.provider_type}
                      </span>
                    </td>
                    <td className="py-2 px-2 text-slate-200">
                      {k.key_type} <span className="text-slate-400">({k.thales_key_type_code})</span>
                    </td>
                    <td className="py-2 px-2 text-slate-300">{k.key_usage}</td>
                    <td className="py-2 px-2 text-amber-300 font-bold">{k.key_scheme}</td>
                    <td className="py-2 px-2 text-slate-300">v{k.key_version}</td>
                    <td className="py-2 px-2 font-bold text-amber-400">{k.kvc}</td>
                    <td className="py-2 px-2 text-sky-300">
                      {k.lmk_check_value ? `${k.lmk_check_value.slice(0, 6)} (%${k.lmk_id})` : 'INTERNAL'}
                    </td>
                    <td className="py-2 px-2 text-slate-400" title="Clear keys are never stored or displayed">
                      {k.masked_key_block}
                    </td>
                    <td className="py-2 px-2">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          k.key_status === 'ACTIVE'
                            ? 'bg-emerald-950 text-emerald-300'
                            : 'bg-slate-800 text-slate-400'
                        }`}
                      >
                        {k.key_status}
                      </span>
                    </td>
                    <td className="py-2 px-2 space-x-2 whitespace-nowrap">
                      {k.provider_type === 'EXTERNAL_HSM' && k.key_status === 'ACTIVE' && (
                        <>
                          <button
                            onClick={() => handleVerifyBu(k.key_identifier)}
                            className="text-sky-400 hover:underline"
                          >
                            Verify (BU)
                          </button>
                          <button
                            onClick={() => handleRotateKey(k.key_identifier)}
                            className="text-amber-400 hover:underline"
                          >
                            Rotate (A0)
                          </button>
                        </>
                      )}
                      <button
                        onClick={() => handleDeleteKey(k.id, k.key_identifier)}
                        className="text-rose-400 hover:underline"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* TAB 2: A0 KEY GENERATION */}
      {activeTab === 'a0_generate' && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4 font-mono text-xs">
          <h2 className="text-sm font-bold text-emerald-400">
            Generate Cryptographic Key on External Soft-HSM (Thales Command A0 / Response A1)
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-slate-400 mb-1">Key Alias (Host Identifier)</label>
              <input
                value={a0Alias}
                onChange={(e) => setA0Alias(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded px-3 py-2 text-emerald-300"
              />
            </div>
            <div>
              <label className="block text-slate-400 mb-1">Key Label / Description</label>
              <input
                value={a0Name}
                onChange={(e) => setA0Name(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded px-3 py-2 text-slate-200"
              />
            </div>
            <div>
              <label className="block text-slate-400 mb-1">Key Type (Maps to Thales LMK Variant)</label>
              <select
                value={a0Type}
                onChange={(e) => setA0Type(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded px-3 py-2 text-slate-200"
              >
                <option value="ZMK">ZMK (000 - LMK 04-05)</option>
                <option value="ZPK">ZPK / AWK / IWK (001 - LMK 06-07)</option>
                <option value="TMK">TMK (002 - LMK 14-15)</option>
                <option value="TPK">TPK (002 - LMK 14-15)</option>
                <option value="PVK">PVK (002 - LMK 14-15)</option>
                <option value="CVK">CVK (402 - LMK 14-15 Var 4)</option>
                <option value="TAK">TAK (003 - LMK 16-17)</option>
                <option value="ZAK">ZAK (008 - LMK 26-27)</option>
                <option value="BDK">BDK (009 - LMK 28-29)</option>
                <option value="MK-AC">MK-AC (109 - LMK 28-29)</option>
                <option value="ZEK">ZEK (00A - LMK 30-31)</option>
                <option value="DEK">DEK (00B - LMK 32-33)</option>
              </select>
            </div>
            <div>
              <label className="block text-slate-400 mb-1">Key Scheme (LMK)</label>
              <select
                value={a0Scheme}
                onChange={(e) => setA0Scheme(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded px-3 py-2 text-slate-200"
              >
                <option value="U">U - Variant Double-Length 3DES (128-bit)</option>
                <option value="T">T - Variant Triple-Length 3DES (192-bit)</option>
                <option value="S">S - Thales Key Block Header + MAC</option>
              </select>
            </div>
            <div>
              <label className="block text-slate-400 mb-1">A0 Generation Mode</label>
              <select
                value={a0Mode}
                onChange={(e) => setA0Mode(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded px-3 py-2 text-slate-200"
              >
                <option value="0">Mode 0 - Generate Under LMK Only</option>
                <option value="1">Mode 1 - Generate Under LMK + Export Under ZMK</option>
              </select>
            </div>
            {a0Mode === '1' && (
              <div>
                <label className="block text-slate-400 mb-1">Export ZMK Alias</label>
                <input
                  value={a0ZmkAlias}
                  onChange={(e) => setA0ZmkAlias(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded px-3 py-2 text-sky-300"
                />
              </div>
            )}
          </div>
          <button
            onClick={handleGenerateA0}
            className="bg-emerald-600 hover:bg-emerald-500 px-5 py-2.5 rounded text-white font-bold"
          >
            Execute Thales A0 on External Soft-HSM
          </button>

          {a0Result && (
            <pre className="bg-slate-950 border border-slate-800 p-4 rounded text-emerald-300 overflow-x-auto">
{`RAW REQUEST         : ${a0Result.raw_request}
RAW RESPONSE        : ${a0Result.raw_response}
KEY ALIAS           : ${a0Result.key.key_identifier} (v${a0Result.key.key_version})
FORMAT INSPECTION   : ${a0Result.token_inspection.representation} (${a0Result.token_inspection.key_length_bits}-bit)
MASKED LMK BLOCK    : ${a0Result.key.masked_key_block}
KEY CHECK VALUE     : ${a0Result.key.kvc}
LMK DOMAIN KCV      : ${a0Result.key.lmk_check_value}
EXPORTED UNDER ZMK  : ${a0Result.exported_key_under_zmk || 'N/A (Mode 0)'}`}
            </pre>
          )}
        </div>
      )}

      {/* TAB 3: A6 KEY IMPORT */}
      {activeTab === 'a6_import' && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4 font-mono text-xs">
          <h2 className="text-sm font-bold text-sky-400">
            Import Working Key Encrypted Under ZMK into Soft-HSM LMK (Thales Command A6 / Response A7)
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-slate-400 mb-1">Imported Key Alias</label>
              <input
                value={a6Alias}
                onChange={(e) => setA6Alias(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded px-3 py-2 text-sky-300"
              />
            </div>
            <div>
              <label className="block text-slate-400 mb-1">Key Type</label>
              <select
                value={a6Type}
                onChange={(e) => setA6Type(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded px-3 py-2 text-slate-200"
              >
                <option value="ZPK">ZPK (001)</option>
                <option value="TPK">TPK / TMK / PVK (002)</option>
                <option value="TAK">TAK (003)</option>
                <option value="CVK">CVK (402)</option>
                <option value="MK-AC">MK-AC (109)</option>
              </select>
            </div>
            <div>
              <label className="block text-slate-400 mb-1">Wrapping ZMK Alias (in Host DB)</label>
              <input
                value={a6ZmkAlias}
                onChange={(e) => setA6ZmkAlias(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded px-3 py-2 text-amber-300"
              />
            </div>
            <div className="md:col-span-2">
              <label className="block text-slate-400 mb-1">Key Encrypted Under ZMK (e.g. U + 32H from A8 Export)</label>
              <input
                value={a6EncKey}
                onChange={(e) => setA6EncKey(e.target.value)}
                placeholder="U06071111222233334444555566667777"
                className="w-full bg-slate-950 border border-slate-700 rounded px-3 py-2 text-emerald-300"
              />
            </div>
            <div>
              <label className="block text-slate-400 mb-1">Target LMK Scheme</label>
              <select
                value={a6Scheme}
                onChange={(e) => setA6Scheme(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded px-3 py-2 text-slate-200"
              >
                <option value="U">U - Variant Double-Length</option>
                <option value="S">S - Thales Key Block</option>
              </select>
            </div>
          </div>
          <button
            onClick={handleImportA6}
            className="bg-sky-600 hover:bg-sky-500 px-5 py-2.5 rounded text-white font-bold"
          >
            Execute Thales A6 Import on External Soft-HSM
          </button>
          {a6Result && (
            <pre className="bg-slate-950 border border-slate-800 p-4 rounded text-sky-300 overflow-x-auto">
{`RAW REQUEST         : ${a6Result.raw_request}
RAW RESPONSE        : ${a6Result.raw_response}
IMPORTED ALIAS      : ${a6Result.key.key_identifier}
MASKED LMK BLOCK    : ${a6Result.key.masked_key_block}
KEY CHECK VALUE     : ${a6Result.key.kvc}`}
            </pre>
          )}
        </div>
      )}

      {/* TAB 4: A8 KEY EXPORT */}
      {activeTab === 'a8_export' && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4 font-mono text-xs">
          <h2 className="text-sm font-bold text-amber-400">
            Export Working Key from LMK to ZMK Encryption (Thales Command A8 / Response A9)
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-slate-400 mb-1">Working Key Alias (Under LMK)</label>
              <input
                value={a8KeyAlias}
                onChange={(e) => setA8KeyAlias(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded px-3 py-2 text-emerald-300"
              />
            </div>
            <div>
              <label className="block text-slate-400 mb-1">Transport ZMK Alias (Under LMK)</label>
              <input
                value={a8ZmkAlias}
                onChange={(e) => setA8ZmkAlias(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded px-3 py-2 text-amber-300"
              />
            </div>
            <div>
              <label className="block text-slate-400 mb-1">Output ZMK Scheme</label>
              <select
                value={a8Scheme}
                onChange={(e) => setA8Scheme(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded px-3 py-2 text-slate-200"
              >
                <option value="U">U - Variant 32H</option>
                <option value="X">X - ANSI X9.17 32H</option>
              </select>
            </div>
          </div>
          <button
            onClick={handleExportA8}
            className="bg-amber-600 hover:bg-amber-500 px-5 py-2.5 rounded text-white font-bold"
          >
            Execute Thales A8 Export on External Soft-HSM
          </button>
          {a8Result && (
            <pre className="bg-slate-950 border border-slate-800 p-4 rounded text-amber-300 overflow-x-auto">
{`RAW REQUEST         : ${a8Result.raw_request}
RAW RESPONSE        : ${a8Result.raw_response}
KEY UNDER ZMK       : ${a8Result.key_under_zmk}
KEY CHECK VALUE     : ${a8Result.kcv}`}
            </pre>
          )}
        </div>
      )}

      {/* TAB 5: PART G AUDIT DELIVERABLE */}
      {activeTab === 'audit' && auditReport && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-3 font-mono text-xs">
          <h2 className="text-sm font-bold text-emerald-400">
            Part G: Verified Soft-HSM LMK & Key-Management Audit Deliverable
          </h2>
          <pre className="bg-slate-950 border border-slate-800 p-4 rounded text-slate-200 overflow-x-auto whitespace-pre-wrap">
            {JSON.stringify(auditReport, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
};
export default KeyCeremonyWorkbenchPage;