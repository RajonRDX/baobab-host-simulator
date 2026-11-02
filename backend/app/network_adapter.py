"""
network_adapter.py — Enterprise Switch Routing Engine & Simulated Card Schemes
Handles On-Us vs Off-Us resolution, priority-based PAN Router Rules, active BIN Range
validation, cross-zone PIN translation (AWK -> IWK), outbound simulated switch adapters
(Visa/Mastercard/NPSB), and timeout reversal handling.
Never selects a disabled or inactive route, BIN range, or processing switch.
"""

import time
import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from app.hsm_adapter import HSMAdapter, SoftHsmCryptoCore
from app.models import (
    BinRange,
    Card,
    Institution,
    NetworkProfile,
    PanRoutingRule,
    ProcessingSystem,
    Transaction,
)


def _clean_short_bank_code(code_or_short: Optional[str], fallback: str = "XBANK") -> str:
    raw = (code_or_short or "").strip()
    if not raw:
        return fallback
    for sep in (" - ", " — ", " – ", "/"):
        if sep in raw:
            part = raw.split(sep)[0].strip()
            if part:
                return part.upper()
    return raw.upper()


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
        profile = (
            self.db.query(NetworkProfile)
            .filter(NetworkProfile.network_name == self.network_name)
            .first()
        )
        if profile and not profile.enabled:
            return {
                "network_status": "UNAVAILABLE",
                "response_code": "91",
                "response_message": f"External network adapter {self.network_name} is disabled (RC 91)",
                "requires_reversal": False,
                "translated_pin_block": None,
                "authorization_code": "000000",
            }

        sim_mode = getattr(profile, "simulation_mode", "ALWAYS_APPROVE") if profile else "ALWAYS_APPROVE"
        sim_rc = getattr(profile, "simulated_response_code", "00") if profile else "00"
        sim_delay = getattr(profile, "simulated_delay_ms", 0) if profile else 0

        if sim_delay > 0:
            time.sleep(min(sim_delay, 500) / 1000.0)

        pan = request_payload.get("pan", "")
        fields = request_payload.get("fields", {})
        pin_block = fields.get("52")
        awk_id = request_payload.get("source_key_id") or "AWK_ATM_01"
        iwk_id = request_payload.get("destination_key_id") or "IWK_SW_01"

        translated_pin_block = None
        if pin_block:
            trans_res = self.hsm.translate_pin_block(
                pan=pan,
                encrypted_pin_block=pin_block,
                awk_id=awk_id,
                iwk_id=iwk_id,
            )
            translated_pin_block = trans_res.get("sanitized_response", {}).get("destination_pin_block") or "F" * 16

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

        return {
            "network_status": "APPROVED",
            "response_code": "00",
            "response_message": f"Approved by external network {self.network_name}",
            "requires_reversal": False,
            "translated_pin_block": translated_pin_block,
            "authorization_code": uuid.uuid4().hex[:6].upper(),
        }


def _resolve_dest_network_name(scheme: str, explicit_dest: Optional[str], is_on_us: bool) -> Optional[str]:
    if is_on_us:
        return None
    if explicit_dest and explicit_dest != "INTERNAL_SIMULATOR_TIC":
        return explicit_dest
    scheme_up = (scheme or "ITCL").upper()
    if "VISA" in scheme_up:
        return "VISA_SCHEME"
    if "MASTER" in scheme_up:
        return "MASTERCARD_SCHEME"
    if "NPSB" in scheme_up:
        return "NPSB_NATIONAL_SWITCH"
    return "INTERNAL_SIMULATOR_TIC"


def resolve_transaction_routing(
    db: Session,
    pan: str,
    acquirer_id: str = "123456",
    transaction_code: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Determines On-Us vs Off-Us status and selects the destination processing system or network adapter.
    Evaluation Order:
      1. Active PanRoutingRule records ordered by priority ASC, prefix length DESC.
         (Never selects disabled/inactive rules, inactive banks, or disabled switches.)
      2. Active BinRange records ordered by prefix length DESC (12..6) and range bounds.
         (Never selects inactive BIN ranges, inactive banks, or disabled switches.)
      3. Fallback to On-Us ITCL internal switch if no rule/BIN matches, or returns route_blocked=True
         if a matching BIN/route exists but its bank or switch is explicitly disabled.
    """
    clean_pan = "".join(ch for ch in (pan or "") if ch.isdigit())
    bin_prefix_6 = clean_pan[:6] if len(clean_pan) >= 6 else clean_pan
    pan_19 = clean_pan.ljust(19, "0")[:19]

    card_rec = db.query(Card).filter(Card.test_pan_reference == clean_pan).first() if clean_pan else None
    card_type_val = card_rec.card_type.upper() if (card_rec and card_rec.card_type) else None

    acq_inst = db.query(Institution).filter(Institution.acquirer_id == str(acquirer_id).strip()).first()

    # 1. Evaluate Active PAN Routing Rules first
    try:
        active_rules = (
            db.query(PanRoutingRule)
            .filter(PanRoutingRule.enabled == True, PanRoutingRule.status == "ACTIVE")  # noqa: E712
            .order_by(PanRoutingRule.priority.asc())
            .all()
        )
    except Exception:
        active_rules = []

    blocked_reason: Optional[str] = None

    for rule in active_rules:
        pfx = rule.pan_prefix or ""
        low_19 = (rule.pan_low or pfx).ljust(19, "0")[:19]
        high_19 = (rule.pan_high or pfx).ljust(19, "9")[:19]

        if not (clean_pan.startswith(pfx) or (low_19 <= pan_19 <= high_19)):
            continue
        if rule.pan_length and len(clean_pan) >= 12 and len(clean_pan) != rule.pan_length:
            continue
        if rule.card_type and rule.card_type != "ANY" and card_type_val and rule.card_type.upper() != card_type_val:
            continue
        if rule.transaction_code and rule.transaction_code != "ANY" and transaction_code and rule.transaction_code != str(transaction_code):
            continue
        if rule.acquirer_institution_id and acq_inst and rule.acquirer_institution_id != acq_inst.id:
            continue

        iss = rule.issuer_institution
        ps = rule.processing_system
        if (iss and iss.status != "ACTIVE") or (ps and not ps.enabled):
            blocked_reason = (
                f"Route {rule.rule_code} matched PAN {bin_prefix_6}*, but target switch "
                f"({ps.ps_code if ps else 'N/A'}) or bank ({iss.institution_code if iss else 'N/A'}) is disabled."
            )
            continue

        dest_net = _resolve_dest_network_name(rule.scheme, rule.destination_network, rule.is_on_us)
        bank_short = _clean_short_bank_code(iss.short_name or iss.institution_code if iss else "XBANK")
        return {
            "matched_record": True,
            "route_blocked": False,
            "match_source": "PAN_ROUTER_RULE",
            "rule_id": rule.id,
            "rule_code": rule.rule_code,
            "rule_name": rule.rule_name,
            "priority": rule.priority,
            "is_on_us": rule.is_on_us,
            "routing_target": "ON_US_HOST" if rule.is_on_us else "EXTERNAL_NETWORK",
            "scheme": rule.scheme.upper(),
            "ps_code": ps.ps_code if ps else rule.scheme.upper(),
            "destination_network": dest_net,
            "bin_prefix": rule.pan_prefix,
            "institution_id": rule.issuer_institution_id,
            "card_type": rule.card_type or card_type_val or "DEBIT",
            "card_product": card_rec.card_product if card_rec else f"{rule.scheme}_ROUTED_CARD",
            "pin_translation_required": rule.pin_translation_required,
            "source_key_id": rule.source_key_id or "AWK_ATM_01",
            "destination_key_id": rule.destination_key_id or "IWK_SW_01",
            "institution": {
                "id": iss.id if iss else rule.issuer_institution_id,
                "code": bank_short,
                "name": iss.name if iss else bank_short,
                "acquirer_id": iss.acquirer_id if iss else acquirer_id,
            },
            "processing_system": {
                "id": ps.id if ps else rule.processing_system_id,
                "code": ps.ps_code if ps else rule.scheme.upper(),
                "name": ps.name if ps else rule.scheme.upper(),
            },
        }

    # 2. Evaluate Active BIN Ranges (longest prefix match 12..6, then range bounds)
    all_bins = db.query(BinRange).all()
    candidate_bins: List[BinRange] = []
    for b in all_bins:
        pfx = b.bin_prefix or ""
        low_19 = (b.bin_low or pfx).ljust(19, "0")[:19]
        high_19 = (b.bin_high or pfx).ljust(19, "9")[:19]
        if clean_pan.startswith(pfx) or (low_19 <= pan_19 <= high_19):
            candidate_bins.append(b)

    candidate_bins.sort(key=lambda x: len(x.bin_prefix or ""), reverse=True)

    for b in candidate_bins:
        iss = b.institution
        ps = b.processing_system
        if b.status != "ACTIVE":
            blocked_reason = f"BIN range {b.bin_prefix} is currently {b.status}."
            continue
        if iss and iss.status != "ACTIVE":
            blocked_reason = f"Issuing bank {iss.institution_code} for BIN {b.bin_prefix} is {iss.status}."
            continue
        if ps and not ps.enabled:
            blocked_reason = f"Processing switch {ps.ps_code} for BIN {b.bin_prefix} is DISABLED."
            continue

        dest_net = _resolve_dest_network_name(b.scheme, None, b.is_on_us)
        bank_short = _clean_short_bank_code(iss.short_name or iss.institution_code if iss else "XBANK")
        return {
            "matched_record": True,
            "route_blocked": False,
            "match_source": "BIN_RANGE",
            "rule_id": None,
            "rule_code": f"BIN-{b.bin_prefix}",
            "rule_name": f"BIN {b.bin_prefix} ({b.card_product})",
            "priority": 100,
            "is_on_us": b.is_on_us,
            "routing_target": "ON_US_HOST" if b.is_on_us else "EXTERNAL_NETWORK",
            "scheme": b.scheme.upper(),
            "ps_code": ps.ps_code if ps else b.scheme.upper(),
            "destination_network": dest_net,
            "bin_prefix": b.bin_prefix,
            "institution_id": b.institution_id,
            "card_type": b.card_type,
            "card_product": b.card_product,
            "pin_translation_required": not b.is_on_us,
            "source_key_id": "AWK_ATM_01",
            "destination_key_id": "IWK_SW_01",
            "institution": {
                "id": iss.id if iss else b.institution_id,
                "code": bank_short,
                "name": iss.name if iss else bank_short,
                "acquirer_id": iss.acquirer_id if iss else acquirer_id,
            },
            "processing_system": {
                "id": ps.id if ps else b.processing_system_id,
                "code": ps.ps_code if ps else "ITCL",
                "name": ps.name if ps else "ITCL Switch",
            },
        }

    if blocked_reason:
        return {
            "matched_record": False,
            "route_blocked": True,
            "match_source": "BLOCKED_ROUTE",
            "is_on_us": False,
            "routing_target": "ROUTE_DISABLED",
            "scheme": "ITCL",
            "ps_code": "ITCL",
            "destination_network": None,
            "bin_prefix": bin_prefix_6,
            "message": blocked_reason,
        }

    return {
        "matched_record": False,
        "route_blocked": False,
        "match_source": "DEFAULT_FALLBACK",
        "is_on_us": True,
        "routing_target": "INTERNAL_ITCL",
        "scheme": "ITCL",
        "ps_code": "ITCL",
        "destination_network": None,
        "bin_prefix": bin_prefix_6,
        "message": "No explicit rule or BIN range matched. Defaulting to On-Us ITCL switch.",
    }
