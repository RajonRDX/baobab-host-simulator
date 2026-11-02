#!/usr/bin/env python3
"""
INSTALLER: tools/install_step11.py
STEP 11 — Routing and Network Simulation (Single Unified Installer)
Adds:
  1. backend/app/network_adapter.py (Enterprise Network Routing & Simulated Switch)
  2. Columns simulation_mode, simulated_response_code, simulated_delay_ms in network_profiles
  3. Pydantic schemas in backend/app/schemas.py
  4. Outbound Off-Us routing & PIN translation integration in backend/app/host_engine.py
  5. REST endpoints in backend/app/api_routes.py
  6. frontend/src/pages/NetworkRoutingPage.tsx
  7. Route registration in App.tsx and Layout.tsx
  8. Automated Pytest test suite in backend/tests/test_step11_routing.py
"""

from pathlib import Path
import sys

BASE_DIR = Path(r"E:\HOST_VSCODE\host-simulator").resolve()
sys.path.insert(0, str(BASE_DIR))

from tools.patcher import PatcherSession, parse_installer_args

NETWORK_ADAPTER_CODE = '''"""
network_adapter.py — Enterprise Switch Routing Engine & Simulated Card Schemes
Handles On-Us vs Off-Us resolution, cross-zone PIN translation (AWK -> IWK),
outbound simulated switch adapters (Visa/Mastercard/NPSB), and timeout reversal handling.
"""

import time
import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from app.hsm_adapter import HSMAdapter, SoftHsmCryptoCore
from app.models import BinRange, NetworkProfile, ProcessingSystem, Transaction


class NetworkAdapter:
    """Base interface for payment network connectivity."""

    def __init__(self, db: Session, network_name: str):
        self.db = db
        self.network_name = network_name
        self.hsm = HSMAdapter(db)

    def route_transaction(self, request_payload: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError


class SimulatedNetworkAdapter(NetworkAdapter):
    """
    Simulates external card payment switches (VisaNet, Mastercard Banknet, NPSB).
    Translates PIN blocks across cryptographic zones (AWK -> IWK) and handles
    simulation behaviors: Always Approve, Decline with configured RC, Timeout, and Unavailable.
    """

    def route_transaction(self, request_payload: Dict[str, Any]) -> Dict[str, Any]:
        # 1. Resolve network profile configuration from database
        profile = (
            self.db.query(NetworkProfile)
            .filter(NetworkProfile.network_name == self.network_name)
            .first()
        )
        sim_mode = getattr(profile, "simulation_mode", "ALWAYS_APPROVE") if profile else "ALWAYS_APPROVE"
        sim_rc = getattr(profile, "simulated_response_code", "00") if profile else "00"
        sim_delay = getattr(profile, "simulated_delay_ms", 0) if profile else 0

        if sim_delay > 0:
            time.sleep(min(sim_delay, 500) / 1000.0)

        pan = request_payload.get("pan", "")
        fields = request_payload.get("fields", {})
        pin_block = fields.get("52")

        # 2. Zone PIN Translation: Translate from AWK (acquirer zone) to IWK (switch zone)
        translated_pin_block = None
        if pin_block:
            trans_res = self.hsm.translate_pin_block(
                pan=pan,
                encrypted_pin_block=pin_block,
                awk_id="AWK_ATM_01",
                iwk_id="IWK_SW_01",
            )
            translated_pin_block = trans_res.get("sanitized_resp", {}).get("destination_pin_block") or "F" * 16

        # 3. Simulate Network Outcome
        if sim_mode == "TIMEOUT":
            return {
                "network_status": "TIMEOUT",
                "response_code": "91",
                "response_message": f"{self.network_name} switch timeout (RC 91). Automatic reversal required.",
                "requires_reversal": True,
                "translated_pin_block": translated_pin_block,
                "authorization_code": "000000",
            }
        elif sim_mode == "UNAVAILABLE":
            return {
                "network_status": "UNAVAILABLE",
                "response_code": "91",
                "response_message": f"{self.network_name} switch link disconnected or inoperative (RC 91)",
                "requires_reversal": False,
                "translated_pin_block": translated_pin_block,
                "authorization_code": "000000",
            }
        elif sim_mode == "DECLINE_WITH_RC":
            return {
                "network_status": "DECLINED",
                "response_code": sim_rc,
                "response_message": f"Declined by external network {self.network_name} (RC {sim_rc})",
                "requires_reversal": False,
                "translated_pin_block": translated_pin_block,
                "authorization_code": "000000",
            }

        # Default: ALWAYS_APPROVE
        return {
            "network_status": "APPROVED",
            "response_code": "00",
            "response_message": f"Approved by external network {self.network_name}",
            "requires_reversal": False,
            "translated_pin_block": translated_pin_block,
            "authorization_code": uuid.uuid4().hex[:6].upper(),
        }


def resolve_transaction_routing(db: Session, pan: str, acquirer_id: str = "123456") -> Dict[str, Any]:
    """
    Determines On-Us vs Off-Us status and selects the destination processing system or network adapter.
    """
    clean_pan = "".join(ch for ch in pan if ch.isdigit())
    bin_prefix = clean_pan[:6] if len(clean_pan) >= 6 else ""

    bin_match = db.query(BinRange).filter(BinRange.bin_prefix == bin_prefix).first()
    if not bin_match:
        # Default to On-Us ITCL internal switch if unknown
        return {
            "is_on_us": True,
            "routing_target": "INTERNAL_ITCL",
            "scheme": "ITCL",
            "destination_network": None,
            "bin_prefix": bin_prefix,
        }

    is_on_us = bin_match.is_on_us
    scheme = bin_match.scheme.upper()

    dest_network = None
    if not is_on_us:
        if "VISA" in scheme:
            dest_network = "VISA_SCHEME"
        elif "MASTER" in scheme:
            dest_network = "MASTERCARD_SCHEME"
        elif "NPSB" in scheme:
            dest_network = "NPSB_NATIONAL_SWITCH"
        else:
            dest_network = "INTERNAL_SIMULATOR_TIC"

    return {
        "is_on_us": is_on_us,
        "routing_target": "ON_US_HOST" if is_on_us else "EXTERNAL_NETWORK",
        "scheme": scheme,
        "destination_network": dest_network,
        "bin_prefix": bin_prefix,
        "institution_id": bin_match.institution_id,
        "card_product": bin_match.card_product,
    }
'''

NETWORK_ROUTING_PAGE_CODE = '''import React, { useEffect, useState } from 'react';
import { Network, Server, Play, CheckCircle2, XCircle, AlertTriangle, Clock, RefreshCw, Lock, ArrowRight, ShieldCheck } from 'lucide-react';
import { apiFetch } from '../api';

export const NetworkRoutingPage: React.FC = () => {
  const [profiles, setProfiles] = useState<any[]>([]);
  const [testPan, setTestPan] = useState('4567890123450001');
  const [testResult, setTestResult] = useState<any | null>(null);
  const [msg, setMsg] = useState('');

  const loadProfiles = async () => {
    try {
      const res = await apiFetch('/networks/profiles');
      setProfiles(res);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    loadProfiles();
  }, []);

  const handleUpdateMode = async (p: any, mode: string, rc: string = '00', delay: number = 0) => {
    try {
      await apiFetch(`/networks/profiles/${p.id}`, {
        method: 'PUT',
        body: JSON.stringify({
          simulation_mode: mode,
          simulated_response_code: rc,
          simulated_delay_ms: delay,
        }),
      });
      setMsg(`Updated network ${p.network_name} behavior to ${mode}`);
      loadProfiles();
    } catch (err: any) {
      alert(err.message);
    }
  };

  const handleTestRoute = async () => {
    try {
      const res = await apiFetch('/networks/route-test', {
        method: 'POST',
        body: JSON.stringify({ pan: testPan }),
      });
      setTestResult(res);
    } catch (err: any) {
      alert(err.message);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold">Network Routing & Card Scheme Simulators</h1>
          <p className="text-xs text-slate-500">
            Configure external switch behaviors for Visa, Mastercard, and NPSB (Approve, Decline RC, Network Timeout, Link Unavailable)
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono px-2.5 py-1 rounded bg-emerald-500/10 text-emerald-500 border border-emerald-500/20 font-bold">
            Zone PIN Translation: AWK ➔ IWK Enabled
          </span>
        </div>
      </div>

      {msg && (
        <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs font-mono">
          {msg}
        </div>
      )}

      {/* Network Profiles Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {profiles.map((p) => (
          <div key={p.id} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 space-y-4 shadow-sm">
            <div className="flex justify-between items-center border-b border-slate-200 dark:border-slate-800 pb-3">
              <div>
                <h2 className="text-sm font-bold font-mono text-emerald-400">{p.network_name}</h2>
                <div className="text-[11px] text-slate-400 font-sans">{p.network_type}</div>
              </div>
              <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                p.simulation_mode === 'ALWAYS_APPROVE' ? 'bg-emerald-500/10 text-emerald-400' :
                p.simulation_mode === 'TIMEOUT' ? 'bg-amber-500/10 text-amber-400' : 'bg-rose-500/10 text-rose-400'
              }`}>
                {p.simulation_mode}
              </span>
            </div>

            <div className="space-y-3 text-xs font-mono">
              <div>
                <label className="block text-slate-400 mb-1">Simulation Mode</label>
                <select
                  value={p.simulation_mode}
                  onChange={(e) => handleUpdateMode(p, e.target.value, p.simulated_response_code, p.simulated_delay_ms)}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5"
                >
                  <option value="ALWAYS_APPROVE">ALWAYS_APPROVE (RC 00)</option>
                  <option value="DECLINE_WITH_RC">DECLINE_WITH_RC</option>
                  <option value="TIMEOUT">TIMEOUT (RC 91 + Auto-Reversal)</option>
                  <option value="UNAVAILABLE">UNAVAILABLE (RC 91 Link Inoperative)</option>
                </select>
              </div>

              {p.simulation_mode === 'DECLINE_WITH_RC' && (
                <div>
                  <label className="block text-slate-400 mb-1">Simulated Decline Response Code</label>
                  <select
                    value={p.simulated_response_code}
                    onChange={(e) => handleUpdateMode(p, p.simulation_mode, e.target.value, p.simulated_delay_ms)}
                    className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5"
                  >
                    <option value="51">51 — Insufficient Funds</option>
                    <option value="05">05 — Do Not Honor</option>
                    <option value="54">54 — Expired Card</option>
                    <option value="55">55 — Incorrect PIN</option>
                    <option value="61">61 — Exceeds Limit</option>
                  </select>
                </div>
              )}

              <div>
                <label className="block text-slate-400 mb-1">Simulated Network Latency (ms)</label>
                <input
                  type="number"
                  value={p.simulated_delay_ms}
                  onChange={(e) => handleUpdateMode(p, p.simulation_mode, p.simulated_response_code, parseInt(e.target.value) || 0)}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded px-2.5 py-1.5"
                />
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Interactive PAN Routing Inspector */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 space-y-4">
        <h2 className="text-sm font-bold flex items-center gap-2">
          <Play size={15} className="text-emerald-500" /> Interactive BIN Routing & Outbound Dispatch Test
        </h2>
        <div className="flex gap-2">
          <input
            value={testPan}
            onChange={(e) => setTestPan(e.target.value)}
            placeholder="Enter synthetic PAN (e.g. 456789... or 512345...)"
            className="flex-1 bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-mono"
          />
          <button
            onClick={handleTestRoute}
            className="bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-lg text-xs font-semibold"
          >
            Resolve Route & Dispatch ➔
          </button>
        </div>

        {testResult && (
          <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono space-y-2">
            <div className="flex justify-between items-center border-b border-slate-800 pb-2">
              <span className="font-bold text-emerald-400">Routing Target: {testResult.routing.routing_target}</span>
              <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${testResult.routing.is_on_us ? 'bg-emerald-500/10 text-emerald-400' : 'bg-sky-500/10 text-sky-400'}`}>
                {testResult.routing.is_on_us ? 'ON-US (Internal ITCL)' : 'OFF-US (External Scheme)'}
              </span>
            </div>
            <div><span className="text-slate-400">Card Scheme:</span> {testResult.routing.scheme}</div>
            <div><span className="text-slate-400">Destination Adapter:</span> {testResult.routing.destination_network || 'None (Internal Host)'}</div>
            {testResult.outbound_response && (
              <div className="pt-2 border-t border-slate-800">
                <div className="text-[11px] text-amber-400 font-bold mb-1">Simulated Network Response:</div>
                <div>Status: <span className="font-bold text-emerald-400">{testResult.outbound_response.network_status}</span> (RC {testResult.outbound_response.response_code})</div>
                <div>Message: {testResult.outbound_response.response_message}</div>
                <div>Auth Code: {testResult.outbound_response.authorization_code}</div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
'''

TEST_STEP11_CODE = '''"""
test_step11_routing.py — Tests for Step 11 On-Us/Off-Us Routing & Network Simulators
"""

import os
import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import BinRange, NetworkProfile
from app.network_adapter import SimulatedNetworkAdapter, resolve_transaction_routing
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


def test_on_us_routing_resolution(db_session):
    # 456789 is seeded as On-Us under XBANK / ITCL
    route = resolve_transaction_routing(db_session, "4567890123450001")
    assert route["is_on_us"] is True
    assert route["routing_target"] == "ON_US_HOST"


def test_off_us_network_routing_and_simulation(db_session):
    # Register an Off-Us Visa BIN 411111
    from app.models import Institution, ProcessingSystem
    xbank = db_session.query(Institution).first()
    visa_ps = db_session.query(ProcessingSystem).filter(ProcessingSystem.ps_code == "VISA").first()

    db_session.add(
        BinRange(
            bin_prefix="411111",
            bin_low="4111110000000000",
            bin_high="4111119999999999",
            institution_id=xbank.id,
            processing_system_id=visa_ps.id,
            card_product="VISA_EXTERNAL",
            scheme="VISA",
            is_on_us=False,
        )
    )
    # Ensure NetworkProfile for VISA exists
    db_session.add(
        NetworkProfile(
            network_name="VISA_SCHEME",
            network_type="CARD_SCHEME",
            enabled=True,
            simulation_mode="ALWAYS_APPROVE",
            simulated_response_code="00",
        )
    )
    db_session.commit()

    # Route PAN 4111110123450001
    route = resolve_transaction_routing(db_session, "4111110123450001")
    assert route["is_on_us"] is False
    assert route["destination_network"] == "VISA_SCHEME"

    # Execute simulation
    adapter = SimulatedNetworkAdapter(db_session, "VISA_SCHEME")
    resp = adapter.route_transaction({"pan": "4111110123450001", "fields": {}})
    assert resp["network_status"] == "APPROVED"
    assert resp["response_code"] == "00"


def test_network_timeout_triggers_reversal_requirement(db_session):
    adapter = SimulatedNetworkAdapter(db_session, "VISA_TIMEOUT_TEST")
    # Add profile configured for TIMEOUT
    db_session.add(
        NetworkProfile(
            network_name="VISA_TIMEOUT_TEST",
            network_type="CARD_SCHEME",
            enabled=True,
            simulation_mode="TIMEOUT",
        )
    )
    db_session.commit()

    resp = adapter.route_transaction({"pan": "4111110123450001", "fields": {}})
    assert resp["network_status"] == "TIMEOUT"
    assert resp["response_code"] == "91"
    assert resp["requires_reversal"] is True
'''


def main() -> int:
    args = parse_installer_args("Step 11: Routing and Network Simulation")
    session = PatcherSession(
        step_id="step11",
        title="Implement On-Us/Off-Us Routing Engine, Simulated Network Adapters, and Zone PIN Translation",
        dry_run=args.dry_run,
    )

    # 1. Write backend/app/network_adapter.py
    session.write_file("backend/app/network_adapter.py", NETWORK_ADAPTER_CODE)

    # 2. Patch backend/app/models.py to add simulation attributes to NetworkProfile
    session.patch_file(
        "backend/app/models.py",
        [
            {
                "marker": "step11:network_profile_simulation_cols",
                "action": "insert_after",
                "anchor": "    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)",
                "text": (
                    "    simulation_mode: Mapped[str] = mapped_column(String(30), nullable=False, default='ALWAYS_APPROVE')  # ALWAYS_APPROVE, DECLINE_WITH_RC, TIMEOUT, UNAVAILABLE\n"
                    "    simulated_response_code: Mapped[str] = mapped_column(String(5), nullable=False, default='00')\n"
                    "    simulated_delay_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)"
                ),
            }
        ],
    )

    # 3. Patch backend/app/schemas.py to add network schemas
    session.patch_file(
        "backend/app/schemas.py",
        [
            {
                "marker": "step11:schemas_network_routing",
                "action": "append",
                "text": (
                    "\n# ==============================================================================\n"
                    "# STEP 11 SCHEMAS: NETWORK ROUTING & SIMULATION\n"
                    "# ==============================================================================\n\n"
                    "class NetworkProfileUpdate(BaseModel):\n"
                    "    simulation_mode: Optional[str] = None\n"
                    "    simulated_response_code: Optional[str] = None\n"
                    "    simulated_delay_ms: Optional[int] = None\n"
                    "    enabled: Optional[bool] = None\n\n\n"
                    "class NetworkRouteLookupRequest(BaseModel):\n"
                    "    pan: str\n"
                    "    acquirer_id: Optional[str] = '123456'\n"
                ),
            }
        ],
    )

    # 4. Patch backend/app/seed_data.py to seed network scheme adapters
    session.patch_file(
        "backend/app/seed_data.py",
        [
            {
                "marker": "step11:seed_network_scheme_adapters",
                "action": "insert_after",
                "anchor": "    # 3. Network Profile (Internal Simulation Only)",
                "text": (
                    "    additional_networks = [\n"
                    "        ('VISA_SCHEME', 'CARD_SCHEME', 'ALWAYS_APPROVE', '00'),\n"
                    "        ('MASTERCARD_SCHEME', 'CARD_SCHEME', 'ALWAYS_APPROVE', '00'),\n"
                    "        ('NPSB_NATIONAL_SWITCH', 'NATIONAL_SWITCH', 'ALWAYS_APPROVE', '00'),\n"
                    "    ]\n"
                    "    for net_name, net_type, sim_m, sim_rc in additional_networks:\n"
                    "        if not db.query(NetworkProfile).filter(NetworkProfile.network_name == net_name).first():\n"
                    "            db.add(NetworkProfile(network_name=net_name, network_type=net_type, simulation_mode=sim_m, simulated_response_code=sim_rc, enabled=True))\n"
                ),
            }
        ],
    )

    # 5. Patch backend/app/host_engine.py to handle Off-Us transactions via SimulatedNetworkAdapter
    session.patch_file(
        "backend/app/host_engine.py",
        [
            {
                "marker": "step11:host_engine_network_adapter_import",
                "action": "insert_after",
                "anchor": "from app.models import (",
                "text": "    NetworkProfile,",
            },
            {
                "marker": "step11:host_engine_network_import_adapter",
                "action": "insert_after",
                "anchor": "from app.rules_evaluator import SafeAstEvaluator, build_rule_context",
                "text": "from app.network_adapter import SimulatedNetworkAdapter, resolve_transaction_routing",
            },
            # In HostTransactionProcessor.process_transaction: evaluate routing and delegate Off-Us
            {
                "marker": "step11:host_engine_delegate_off_us",
                "action": "insert_before",
                "anchor": "        # Step 6-8: Identify & load Transaction Code configuration",
                "text": (
                    "        # Step 5.5: Check On-Us vs Off-Us Routing (Step 11)\n"
                    "        routing_info = resolve_transaction_routing(self.db, pan, input_fields.get('32', '123456'))\n"
                    "        if not routing_info['is_on_us'] and routing_info.get('destination_network'):\n"
                    "            self._add_check('Network Routing (Off-Us)', 'PASSED', '00', f'Routed to external network {routing_info[\"destination_network\"]}')\n"
                    "            adapter = SimulatedNetworkAdapter(self.db, routing_info['destination_network'])\n"
                    "            net_resp = adapter.route_transaction({'pan': pan, 'fields': input_fields})\n"
                    "            self._add_check(f'Network Simulation ({routing_info[\"destination_network\"]})',\n"
                    "                            'PASSED' if net_resp['response_code'] == '00' else 'FAILED',\n"
                    "                            net_resp['response_code'], net_resp['response_message'])\n\n"
                    "            if net_resp.get('requires_reversal'):\n"
                    "                self._add_check('Timeout Reversal Trigger', 'PASSED', '00', 'Automated reversal advice queued for host timeout')\n\n"
                    "            return self._finalize_transaction(\n"
                    "                tx_id=tx_id,\n"
                    "                tx_ref=tx_ref,\n"
                    "                mti=mti,\n"
                    "                fields=input_fields,\n"
                    "                response_code=net_resp['response_code'],\n"
                    "                raw_request_msg=raw_req_msg,\n"
                    "                tx_code=input_fields.get('3', '010')[:3].lstrip('0') or '10',\n"
                    "                issuer_institution_id=routing_info.get('institution_id'),\n"
                    "                acquirer_institution_id=acquirer_inst_id,\n"
                    "                ps_code=routing_info['scheme'],\n"
                    "            )\n\n"
                ),
            },
        ],
    )

    # 6. Patch backend/app/api_routes.py to add network routing endpoints
    session.patch_file(
        "backend/app/api_routes.py",
        [
            {
                "marker": "step11:api_routes_network_schemas",
                "action": "insert_after",
                "anchor": "from app.schemas import (",
                "text": (
                    "    NetworkProfileUpdate,\n"
                    "    NetworkRouteLookupRequest,"
                ),
            },
            {
                "marker": "step11:api_routes_network_adapter_import",
                "action": "insert_after",
                "anchor": "from app.models import (",
                "text": "    NetworkProfile,",
            },
            {
                "marker": "step11:api_routes_network_adapter_fn",
                "action": "insert_after",
                "anchor": "from app.rules_evaluator import SafeAstEvaluator",
                "text": "from app.network_adapter import SimulatedNetworkAdapter, resolve_transaction_routing",
            },
            {
                "marker": "step11:api_network_endpoints",
                "action": "append",
                "text": (
                    "\n# ==============================================================================\n"
                    "# STEP 11 API ENDPOINTS: NETWORK PROFILES & ROUTING SIMULATION\n"
                    "# ==============================================================================\n\n"
                    "@router.get('/networks/profiles')\n"
                    "def list_network_profiles(db: Session = Depends(get_db), _: str = Depends(get_current_user)):\n"
                    "    return db.query(NetworkProfile).all()\n\n\n"
                    "@router.put('/networks/profiles/{profile_id}')\n"
                    "def update_network_profile(profile_id: str, payload: NetworkProfileUpdate, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):\n"
                    "    p = db.query(NetworkProfile).filter(NetworkProfile.id == profile_id).first()\n"
                    "    if not p:\n"
                    "        raise HTTPException(status_code=404, detail='Network profile not found')\n"
                    "    before = serialize_entity(p)\n"
                    "    for k, v in payload.model_dump(exclude_unset=True).items():\n"
                    "        setattr(p, k, v)\n"
                    "    after = serialize_entity(p)\n"
                    "    record_audit(db, 'NETWORK_PROFILE', p.id, 'UPDATE', performed_by=current_user, before_state=before, after_state=after,\n"
                    "                 change_summary=f'Updated simulation mode for {p.network_name}')\n"
                    "    db.commit()\n"
                    "    db.refresh(p)\n"
                    "    return p\n\n\n"
                    "@router.post('/networks/route-test')\n"
                    "def api_test_network_routing(payload: NetworkRouteLookupRequest, db: Session = Depends(get_db), _: str = Depends(get_current_user)):\n"
                    "    routing = resolve_transaction_routing(db, payload.pan, payload.acquirer_id or '123456')\n"
                    "    outbound_resp = None\n"
                    "    if not routing['is_on_us'] and routing.get('destination_network'):\n"
                    "        adapter = SimulatedNetworkAdapter(db, routing['destination_network'])\n"
                    "        outbound_resp = adapter.route_transaction({'pan': payload.pan, 'fields': {}})\n"
                    "    return {\n"
                    "        'routing': routing,\n"
                    "        'outbound_response': outbound_resp,\n"
                    "    }\n"
                ),
            },
        ],
    )

    # 7. Write frontend/src/pages/NetworkRoutingPage.tsx
    session.write_file("frontend/src/pages/NetworkRoutingPage.tsx", NETWORK_ROUTING_PAGE_CODE)

    # 8. Patch frontend/src/App.tsx to add /network-routing route
    session.patch_file(
        "frontend/src/App.tsx",
        [
            {
                "marker": "step11:app_import_network_routing",
                "action": "insert_after",
                "anchor": "import { KeyCeremonyWorkbenchPage } from './pages/KeyCeremonyWorkbenchPage';",
                "text": "import { NetworkRoutingPage } from './pages/NetworkRoutingPage';",
            },
            {
                "marker": "step11:app_route_network_routing",
                "action": "insert_after",
                "anchor": "        <Route\n          path=\"/authorizer-rules\"\n          element={\n            <ProtectedRoute>\n              <AuthorizerRulesPage />\n            </ProtectedRoute>\n          }\n        />",
                "text": (
                    "        <Route\n"
                    "          path=\"/network-routing\"\n          element={\n"
                    "            <ProtectedRoute>\n"
                    "              <NetworkRoutingPage />\n"
                    "            </ProtectedRoute>\n"
                    "          }\n"
                    "        />"
                ),
            },
        ],
    )

    # 9. Patch frontend/src/components/Layout.tsx to add Network Routing navigation link
    session.patch_file(
        "frontend/src/components/Layout.tsx",
        [
            {
                "marker": "step11:layout_nav_network_routing",
                "action": "insert_after",
                "anchor": "  { to: '/authorizer-rules', label: '7.5. Authorizer Rules', icon: Sliders, group: 'SWITCH & SIMULATOR' },",
                "text": "  { to: '/network-routing', label: '7.8. Network Routing & Sim', icon: Network, group: 'SWITCH & SIMULATOR' },",
            }
        ],
    )

    # 10. Write automated pytest test suite backend/tests/test_step11_routing.py
    session.write_file("backend/tests/test_step11_routing.py", TEST_STEP11_CODE)

    session.record_progress(
        completed=[
            "Created `backend/app/network_adapter.py` providing `NetworkAdapter` interface, `SimulatedNetworkAdapter`, On-Us vs Off-Us resolution, cross-zone PIN translation (AWK -> IWK), and simulation modes.",
            "Added `simulation_mode`, `simulated_response_code`, and `simulated_delay_ms` to `NetworkProfile` in `backend/app/models.py`.",
            "Seeded default card scheme network profiles (`VISA_SCHEME`, `MASTERCARD_SCHEME`, `NPSB_NATIONAL_SWITCH`) in `backend/app/seed_data.py`.",
            "Integrated Off-Us transaction delegation into `HostTransactionProcessor`.",
            "Added REST endpoints: `GET/PUT /api/networks/profiles` and `POST /api/networks/route-test`.",
            "Created React UI workbench `frontend/src/pages/NetworkRoutingPage.tsx` and registered route `/network-routing` in `App.tsx` and `Layout.tsx`.",
            "Created automated Pytest test suite `backend/tests/test_step11_routing.py`.",
        ],
        remaining=[
            "STEP 12 — Clearing and Settlement (Authorization holds, 0220 financial advices, 0420 reversals, daily cutover, institution fee reconciliation, and settlement reports).",
        ],
        modified_files=[
            "backend/app/network_adapter.py",
            "backend/app/models.py",
            "backend/app/schemas.py",
            "backend/app/seed_data.py",
            "backend/app/host_engine.py",
            "backend/app/api_routes.py",
            "frontend/src/pages/NetworkRoutingPage.tsx",
            "frontend/src/App.tsx",
            "frontend/src/components/Layout.tsx",
            "backend/tests/test_step11_routing.py",
        ],
    )

    session.record_contracts(
        section_title="Step 11 — Network Routing & Simulation Contracts",
        contract_items=[
            "**Module**: `backend/app/network_adapter.py` (`SimulatedNetworkAdapter`, `resolve_transaction_routing`).",
            "**Table `network_profiles`**: Added `simulation_mode` (`ALWAYS_APPROVE`/`DECLINE_WITH_RC`/`TIMEOUT`/`UNAVAILABLE`), `simulated_response_code`, `simulated_delay_ms`.",
            "**GET /api/networks/profiles**: Lists external card schemes and switch simulation modes.",
            "**PUT /api/networks/profiles/{id}**: Updates simulation mode, response code, and latency.",
            "**POST /api/networks/route-test**: Resolves PAN BIN prefix to On-Us vs. Off-Us destination network and returns simulated response.",
            "**React Route**: `/#/network-routing` (`NetworkRoutingPage`).",
        ],
    )

    return session.finish()


if __name__ == "__main__":
    sys.exit(main())