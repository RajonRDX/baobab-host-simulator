import React, { useEffect, useState } from 'react';
import { api } from '../services/api';

interface HsmAuthorityBadgeProps {
  onProviderChange?: (provider: 'INTERNAL_HSM' | 'EXTERNAL_HSM', statusData: any) => void;
}

export const HsmAuthoritySimulatorBar: React.FC<HsmAuthorityBadgeProps> = ({ onProviderChange }) => {
  const [status, setStatus] = useState<any>(null);
  const [remoteUrl, setRemoteUrl] = useState<string>('https://thales-10k-soft-hsm.onrender.com');
  const [switching, setSwitching] = useState<boolean>(false);
  const [syncMsg, setSyncMsg] = useState<string | null>(null);

  const fetchStatus = async () => {
    try {
      const res = await api.get('/api/hsm/lmk-key-management/status');
      setStatus(res.data);
      if (res.data?.remote_url) {
        setRemoteUrl(res.data.remote_url);
      }
      if (onProviderChange && res.data?.active_provider) {
        onProviderChange(res.data.active_provider, res.data);
      }
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    fetchStatus();
  }, []);

  const switchMode = async (mode: 'INTERNAL_HSM' | 'EXTERNAL_HSM') => {
    setSwitching(true);
    setSyncMsg(null);
    try {
      const res = await api.post('/api/hsm/lmk-key-management/provider', {
        provider_mode: mode,
        remote_url: remoteUrl.trim(),
      });
      setStatus(res.data);
      sessionStorage.setItem('BAOBAB_HSM_MODE', mode);
      if (mode === 'EXTERNAL_HSM') {
        try {
          const syncRes = await api.post('/api/hsm/lmk-key-management/sync-seeded');
          setSyncMsg(`Synced ${syncRes.data.count || 8} keys from External Soft-HSM`);
        } catch {
          // ignore
        }
      }
      if (onProviderChange) {
        onProviderChange(mode, res.data);
      }
    } catch (e) {
      console.error('Failed to switch HSM mode:', e);
    } finally {
      setSwitching(false);
    }
  };

  const isExternal = status?.active_provider === 'EXTERNAL_HSM';

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-3.5 mb-4 flex flex-wrap items-center justify-between gap-3 font-mono text-xs">
      <div className="flex items-center gap-3">
        <span
          className={`inline-block w-2.5 h-2.5 rounded-full ${
            status?.online !== false ? 'bg-emerald-400 animate-pulse' : 'bg-rose-500'
          }`}
        />
        <div>
          <div className="text-slate-400 text-[11px]">ACTIVE CRYPTOGRAPHIC AUTHORITY & WIRE FORMAT INDICATOR</div>
          <div className="font-bold text-white flex flex-wrap items-center gap-2 mt-0.5">
            <span>
              HSM Engine:{' '}
              <span className={isExternal ? 'text-emerald-400' : 'text-sky-400'}>
                {isExternal
                  ? 'EXTERNAL SOFT-HSM (Port Remote Soft-HSM · Thales payShield 10K Wire Format)'
                  : 'INTERNAL SIMULATOR HSM (Local In-Memory Format)'}
              </span>
            </span>
            {status?.lmk_check_value && (
              <span className="px-2 py-0.5 rounded bg-slate-800 text-amber-300 text-[10px]">
                LMK KCV: {status.lmk_check_value}
              </span>
            )}
            {syncMsg && (
              <span className="px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-700 text-[10px]">
                {syncMsg}
              </span>
            )}
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          disabled={switching}
          onClick={() => switchMode('INTERNAL_HSM')}
          className={`px-3 py-1.5 rounded font-bold transition ${
            !isExternal
              ? 'bg-sky-600 text-white shadow'
              : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
          }`}
        >
          Internal HSM Format
        </button>
        <button
          type="button"
          disabled={switching}
          onClick={() => switchMode('EXTERNAL_HSM')}
          className={`px-3 py-1.5 rounded font-bold transition ${
            isExternal
              ? 'bg-emerald-600 text-white shadow'
              : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
          }`}
        >
          External Soft-HSM (:Remote Soft-HSM)
        </button>
      </div>
    </div>
  );
};
export default HsmAuthoritySimulatorBar;
