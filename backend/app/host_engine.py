"""
MODULE 5 — host_engine.py
Central HostTransactionProcessor and configurable Rajon Authorization Engine.
All transaction entry methods (Transaction Simulator, pasted raw TIC messages, sample scenarios,
and future NetworkAdapter requests) pass through this single service.
"""

import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from app.hsm_adapter import HSMAdapter
from app.iso_tic import RESPONSE_MTI_MAP, build_tic_message, decode_tic_message, validate_tic_fields
from app.logging_service import record_system_log
# [PATCH step08:host_engine_evaluator_import]
from app.rules_evaluator import SafeAstEvaluator, build_rule_context
# [PATCH step13_03:limit_engine_integration]
from app.limit_engine import LimitCalculationEngine
# [PATCH step11:host_engine_network_import_adapter]
from app.network_adapter import SimulatedNetworkAdapter, resolve_transaction_routing
from app.models import (
    BinRange,
    Institution,
    ProcessingSystem,
# [PATCH step11:host_engine_network_adapter_import]
    NetworkProfile,
# [PATCH step08:host_engine_rule_imports]
    AuthorizerRule,
    Account,
    AccountLedger,
    AccountLimit,
    Card,
    CardAccount,
    CardLimit,
    Customer,
    EmvProfile,
    HostParameter,
    Notification,
    PinProfile,
    ResponseCode,
    Transaction,
    TransactionCheck,
    TransactionCode,
    TransactionMessage,
    TransactionReversal,
)
from app.security import mask_pan, mask_raw_tic_message
# [PATCH tx_log_viewer_v1:host_engine_imports]
from app.context_trace import get_correlation_id
from app.tic_decoder_engine import extract_metadata_from_tic, TRAN_CODES
from app.models import TransactionTraceEvent


class NetworkAdapter:
    """
    Clean interface placeholder for Phase 2 network connectivity (Visa, Mastercard, NPSB).
    Live external connections are intentionally disabled in Phase 1.
    """

    network_name: str = "INTERNAL_SIMULATOR"

    def to_internal_request(self, external_payload: Any) -> Dict[str, Any]:
        raise NotImplementedError("Live network adapters are disabled in Phase 1.")


class HostTransactionProcessor:
    """
    Executes the 32-step transaction-processing pipeline with atomic database ledger posting,
    configurable Rajon rule ordering, HSM cryptographic verification, and full trace logging.
    """

    def __init__(self, db: Session):
        self.db = db
        self.hsm = HSMAdapter(db)
        self.limit_engine = LimitCalculationEngine(db)
        self.limit_eval_results: List[Dict[str, Any]] = []
        self.pending_limit_consumptions: List[Any] = []
        self.resolved_auth_profile_code: Optional[str] = None
        self.checks_log: List[Dict[str, Any]] = []
        self.check_counter: int = 0
# [PATCH tx_log_viewer_v1:host_engine_start_timer]
        self.pipeline_t0: float = time.perf_counter()

    def _add_check(
        self,
        check_name: str,
        status: str,
        response_code: str,
        message: str,
        duration_ms: int = 1,
    ) -> None:
        self.check_counter += 1
        self.checks_log.append({
            "check_name": check_name,
            "check_order": self.check_counter,
            "check_status": status,
            "response_code": response_code,
            "message": message,
            "duration_ms": max(1, duration_ms),
        })

    def _get_response_description(self, code: str) -> str:
        rc = self.db.query(ResponseCode).filter(ResponseCode.response_code == code).first()
        if rc:
            return rc.response_description
        fallback = {
            "00": "Approved",
            "05": "Do not honor",
            "12": "Invalid transaction",
            "13": "Invalid amount",
            "14": "Invalid card number",
            "15": "Original transaction not found",
            "30": "Format error",
            "51": "Insufficient funds",
            "54": "Expired card",
            "55": "Incorrect PIN",
            "57": "Transaction not permitted to cardholder",
            "61": "Exceeds withdrawal/transaction limit",
            "62": "PIN tries limit reached",
            "80": "Bad CVV",
            "85": "Bad ARQC",
            "91": "Issuer or switch inoperative",
            "94": "Duplicate transmission",
        }
        return fallback.get(code, "Declined")

    def _is_rule_enabled(self, param_name: str, default: bool = True) -> bool:
        param = (
            self.db.query(HostParameter)
            .filter(
                HostParameter.parameter_group == "RAJON_AUTH_RULES",
                HostParameter.parameter_name == param_name,
            )
            .first()
        )
        if not param:
            return default
        # [PATCH rules_checks:is_rule_enabled]
        # an inactive parameter means the check was switched OFF (the old page used to set active = false,
        # but the engine only looked at active rows, so the check silently stayed ON)
        if not param.active:
            return False
        val = param.parameter_value
        if isinstance(val, dict):
            return bool(val.get("enabled", default))
        return bool(val)

    def process_transaction(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        tx_id = str(uuid.uuid4())
        tx_ref = f"TX-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"

        record_system_log(
            self.db,
            "INFO",
            "HostTransactionProcessor",
            "TRANSACTION_RECEIVED",
            f"Received transaction {tx_ref} from {request_data.get('source_channel', 'SIMULATOR')}",
            transaction_id=tx_id,
        )

        # Step 1-4: Identify & decode TIC message or build from fields
        t0 = time.perf_counter()
        raw_tic_input = request_data.get("raw_tic_message")
        input_fields: Dict[str, str] = {
            str(k).upper().replace("DE", "").replace("F", ""): str(v)
            for k, v in (request_data.get("fields") or {}).items()
            if v is not None and str(v) != ""
        }
        mti = request_data.get("mti") or "0200"

        if raw_tic_input:
            decoded = decode_tic_message(raw_tic_input)
            if not decoded.get("valid"):
                self._add_check("Message Validation", "FAILED", "30", decoded.get("error", "Format error"))
                return self._finalize_transaction(
                    tx_id=tx_id,
                    tx_ref=tx_ref,
                    mti=mti,
                    fields=input_fields,
                    response_code="30",
                    raw_request_msg=raw_tic_input,
                    source_channel=request_data.get("source_channel", "SIMULATOR"),
                    idempotency_key=request_data.get("idempotency_key"),
                )
            mti = decoded["mti"]
            input_fields = decoded["raw_fields"]

        # Optional test helper: pack clear PIN into ISO-0 encrypted block under AWK on server
        if request_data.get("test_clear_pin_helper") and input_fields.get("2"):
            input_fields["52"] = self.hsm.pack_test_pin_block_server_side(
                request_data["test_clear_pin_helper"], input_fields["2"]
            )

        # Normalize DE3 to 7 digits for TIC v2.164e (3-digit tran code + 2-digit from acct + 2-digit to acct)
        proc_code = input_fields.get("3", "0100000")
        if len(proc_code) == 6:
            proc_code = "0" + proc_code
            input_fields["3"] = proc_code

        # Step 5: Validate TIC message structure
        val_res = validate_tic_fields(input_fields)
        if not val_res["valid"]:
            err_summary = "; ".join(f"{k}: {v}" for k, v in val_res["errors"].items())
            self._add_check("Message Validation", "FAILED", "30", err_summary)
            raw_req, _ = build_tic_message(mti, {int(k): v for k, v in input_fields.items() if k.isdigit()})
            return self._finalize_transaction(
                tx_id=tx_id,
                tx_ref=tx_ref,
                mti=mti,
                fields=input_fields,
                response_code="30",
                raw_request_msg=raw_req,
                source_channel=request_data.get("source_channel", "SIMULATOR"),
                idempotency_key=request_data.get("idempotency_key"),
            )

        raw_req_msg, _ = build_tic_message(mti, val_res["normalized_fields"])
        self._add_check(
            "Message Validation",
            "PASSED",
            "00",
            f"Valid TIC v2.164e message (MTI {mti}, {len(val_res['normalized_fields'])} fields)",
            int((time.perf_counter() - t0) * 1000),
        )

        stan = input_fields.get("11", "000001")
        rrn = input_fields.get("37", "000000000001")
        pan = input_fields.get("2", "")
        raw_amt = input_fields.get("4", "000000000000")
        tx_amount = (Decimal(raw_amt) / Decimal("100")).quantize(Decimal("0.01"))
        currency = input_fields.get("49", "BDT")

        # Duplicate STAN/RRN & Idempotency check
        idem_key = request_data.get("idempotency_key")
        if mti in ("0100", "0200"):
            dup_query = self.db.query(Transaction).filter(
                Transaction.stan == stan,
                Transaction.rrn == rrn,
                Transaction.mti == mti,
                Transaction.authorization_status == "APPROVED",
            )
            if dup_query.first():
                self._add_check("Duplicate Control", "FAILED", "94", f"Duplicate STAN {stan} / RRN {rrn}")
                return self._finalize_transaction(
                    tx_id=tx_id,
                    tx_ref=tx_ref,
                    mti=mti,
                    fields=input_fields,
                    response_code="94",
                    raw_request_msg=raw_req_msg,
                    source_channel=request_data.get("source_channel", "SIMULATOR"),
                    idempotency_key=idem_key,
                )
# [PATCH step12:host_engine_0220_advice]

        # Step 12: Handle 0220 Financial Advice (Clearing Presentment)
        if mti == '0220':
            self._add_check('Financial Advice Presentment (0220)', 'PASSED', '00', f'Received clearing advice for RRN {rrn}')


        # Handle Reversal (MTI 0400 / 0420)
        if mti in ("0400", "0420"):
            return self._process_reversal(
                tx_id=tx_id,
                tx_ref=tx_ref,
                mti=mti,
                fields=input_fields,
                stan=stan,
                rrn=rrn,
                tx_amount=tx_amount,
                raw_req_msg=raw_req_msg,
                source_channel=request_data.get("source_channel", "SIMULATOR"),
            )

# [PATCH step11:host_engine_delegate_off_us]
        # Resolve Acquirer & Default Issuer Institution Context
        acq_code_de32 = input_fields.get('32', '123456')
        acq_inst = self.db.query(Institution).filter(Institution.acquirer_id == acq_code_de32).first()
        if not acq_inst:
            acq_inst = self.db.query(Institution).filter(Institution.institution_code == 'XBANK').first()
        acquirer_inst_id = acq_inst.id if acq_inst else None
        issuer_inst_id = acquirer_inst_id
        ps_code_val = 'ITCL'

# [PATCH host_engine_pan_router_and_active_check]
        # Step 5.5: Check PAN Router Rules, BIN Range Status & On-Us vs Off-Us Routing
        derived_tx_code = request_data.get('transaction_code') or (proc_code[:3].lstrip('0') or '10')
        routing_info = resolve_transaction_routing(
            self.db,
            pan,
            input_fields.get('32', '123456'),
            transaction_code=str(derived_tx_code),
        )
        if routing_info.get('route_blocked'):
            self._add_check(
                'PAN / BIN Routing Check',
                'FAILED',
                '91',
                routing_info.get('message', 'Target BIN range, bank, or processing switch is disabled'),
            )
            return self._finalize_transaction(
                tx_id=tx_id,
                tx_ref=tx_ref,
                mti=mti,
                fields=input_fields,
                response_code='91',
                raw_request_msg=raw_req_msg,
                tx_code=str(derived_tx_code),
                issuer_institution_id=routing_info.get('institution_id'),
                acquirer_institution_id=acquirer_inst_id,
                ps_code=routing_info.get('ps_code', 'ITCL'),
            )

        if routing_info.get('institution_id'):
            issuer_inst_id = routing_info['institution_id']
        if routing_info.get('ps_code'):
            ps_code_val = routing_info['ps_code']

        if not routing_info['is_on_us'] and routing_info.get('destination_network'):
            self._add_check(
                'Network Routing (Off-Us)',
                'PASSED',
                '00',
                f"Routed via {routing_info.get('match_source', 'BIN_RANGE')} ({routing_info.get('rule_code', '')}) to {routing_info['destination_network']}",
            )
            adapter = SimulatedNetworkAdapter(self.db, routing_info['destination_network'])
            net_resp = adapter.route_transaction({
                'pan': pan,
                'fields': input_fields,
                'source_key_id': routing_info.get('source_key_id', 'AWK_ATM_01'),
                'destination_key_id': routing_info.get('destination_key_id', 'IWK_SW_01'),
            })
            self._add_check(
                f'Network Simulation ({routing_info["destination_network"]})',
                'PASSED' if net_resp['response_code'] == '00' else 'FAILED',
                net_resp['response_code'],
                net_resp['response_message'],
            )

            if net_resp.get('requires_reversal'):
                self._add_check('Timeout Reversal Trigger', 'PASSED', '00', 'Automated reversal advice queued for host timeout')

            return self._finalize_transaction(
                tx_id=tx_id,
                tx_ref=tx_ref,
                mti=mti,
                fields=input_fields,
                response_code=net_resp['response_code'],
                raw_request_msg=raw_req_msg,
                tx_code=str(derived_tx_code),
                issuer_institution_id=routing_info.get('institution_id'),
                acquirer_institution_id=acquirer_inst_id,
                ps_code=routing_info['scheme'],
            )


        # Step 6-8: Identify & load Transaction Code configuration
        req_tx_code = request_data.get("transaction_code")
        if not req_tx_code:
            # Derive from F3.1 (e.g. "010" -> "10")
            f3_prefix = proc_code[:3].lstrip("0") or "10"
            req_tx_code = f3_prefix

        tx_code_cfg = (
            self.db.query(TransactionCode)
            .filter(TransactionCode.transaction_code == str(req_tx_code))
            .first()
        )
        if not tx_code_cfg or not tx_code_cfg.active:
            self._add_check("Transaction Code Lookup", "FAILED", "12", f"Transaction code '{req_tx_code}' inactive or undefined")
            return self._finalize_transaction(
                tx_id=tx_id,
                tx_ref=tx_ref,
                mti=mti,
                fields=input_fields,
                response_code="12",
                raw_request_msg=raw_req_msg,
                tx_code=str(req_tx_code),
            )
        self._add_check(
            "Transaction Code Lookup",
            "PASSED",
            "00",
            f"Loaded configurable code {tx_code_cfg.transaction_code} ({tx_code_cfg.transaction_name})",
        )

        # Step 9-11: Identify Card, Check Card Status & Expiry
        card = self.db.query(Card).filter(Card.test_pan_reference == pan).first()
        if card and card.institution_id:
            issuer_inst_id = card.institution_id
        if not card:
            self._add_check("Card Lookup", "FAILED", "14", f"Card {mask_pan(pan)} not found in host database")
            return self._finalize_transaction(
                tx_id=tx_id,
                tx_ref=tx_ref,
                mti=mti,
                fields=input_fields,
                response_code="14",
                raw_request_msg=raw_req_msg,
                tx_code=tx_code_cfg.transaction_code,
            )

        if tx_code_cfg.card_check_required:
            if card.card_status != "ACTIVE":
                self._add_check("Card Status Check", "FAILED", "05", f"Card status is {card.card_status}")
                return self._finalize_transaction(
                    tx_id=tx_id,
                    tx_ref=tx_ref,
                    mti=mti,
                    fields=input_fields,
                    response_code="05",
                    raw_request_msg=raw_req_msg,
                    tx_code=tx_code_cfg.transaction_code,
                    card=card,
                )
            self._add_check("Card Status Check", "PASSED", "00", f"Card {card.masked_pan} is ACTIVE")

            now = datetime.now(timezone.utc)
            if (card.expiry_year < now.year) or (card.expiry_year == now.year and card.expiry_month < now.month):
                self._add_check("Card Expiry Check", "FAILED", "54", f"Card expired {card.expiry_month:02d}/{card.expiry_year}")
                return self._finalize_transaction(
                    tx_id=tx_id,
                    tx_ref=tx_ref,
                    mti=mti,
                    fields=input_fields,
                    response_code="54",
                    raw_request_msg=raw_req_msg,
                    tx_code=tx_code_cfg.transaction_code,
                    card=card,
                )
            self._add_check("Card Expiry Check", "PASSED", "00", f"Expiry {card.expiry_month:02d}/{card.expiry_year} valid")

        # Step 12-14: Identify Customer & Select Linked Account
        customer = self.db.query(Customer).filter(Customer.id == card.customer_id).first()
        if customer and customer.customer_status != "ACTIVE":
            self._add_check("Customer Status Check", "FAILED", "05", f"Customer status is {customer.customer_status}")
            return self._finalize_transaction(
                tx_id=tx_id,
                tx_ref=tx_ref,
                mti=mti,
                fields=input_fields,
                response_code="05",
                raw_request_msg=raw_req_msg,
                tx_code=tx_code_cfg.transaction_code,
                card=card,
                customer=customer,
            )

# [PATCH step04:host_engine_de3_account_selection]
        # Step 4: Multi-Account Resolution via DE3 Processing Code (Digits 3-4 = From Account Type)
        # 01 = Checking / Current, 11 = Savings, 31 = Credit, 00 = Default Primary
        from_acct_type = proc_code[3:5] if len(proc_code) >= 5 else '00'
        acct_type_target = None
        if from_acct_type in ('01', '02', '20'):
            acct_type_target = 'CURRENT'
        elif from_acct_type in ('10', '11'):
            acct_type_target = 'SAVINGS'
        elif from_acct_type in ('30', '31'):
            acct_type_target = 'CREDIT'

        active_card_accts = (
            self.db.query(CardAccount)
            .filter(CardAccount.card_id == card.id, CardAccount.status == 'ACTIVE')
            .order_by(CardAccount.priority.asc())
            .all()
        )

        selected_card_acct = None
        if acct_type_target and active_card_accts:
            for ca in active_card_accts:
                if ca.account and ca.account.account_type == acct_type_target:
                    selected_card_acct = ca
                    break

        if not selected_card_acct and active_card_accts:
            selected_card_acct = active_card_accts[0]

        account_id = selected_card_acct.account_id if selected_card_acct else card.linked_account_id
        # Lock account row during financial authorization
        account = (
            self.db.query(Account)
            .filter(Account.id == account_id)
            .with_for_update()
            .first()
        )
        if not account:
            self._add_check("Account Selection", "FAILED", "12", "No linked account found for card")
            return self._finalize_transaction(
                tx_id=tx_id,
                tx_ref=tx_ref,
                mti=mti,
                fields=input_fields,
                response_code="12",
                raw_request_msg=raw_req_msg,
                tx_code=tx_code_cfg.transaction_code,
                card=card,
                customer=customer,
            )

        if tx_code_cfg.account_check_required:
            if account.account_status != "ACTIVE":
                self._add_check("Account Status Check", "FAILED", "05", f"Account {account.account_number} is {account.account_status}")
                return self._finalize_transaction(
                    tx_id=tx_id,
                    tx_ref=tx_ref,
                    mti=mti,
                    fields=input_fields,
                    response_code="05",
                    raw_request_msg=raw_req_msg,
                    tx_code=tx_code_cfg.transaction_code,
                    card=card,
                    customer=customer,
                    account=account,
                )
            self._add_check("Account Status Check", "PASSED", "00", f"Account {account.account_number} ({account.currency}) is ACTIVE")

        # Step 15: Check Card Profile Transaction Permissions
        if card.card_profile:
            prof = card.card_profile
            pos_cond = input_fields.get("25", "00")
            if pos_cond in ("08", "81", "82") and not prof.ecommerce_enabled:
                self._add_check("Transaction Permissions", "FAILED", "57", "E-Commerce disabled on card profile")
                return self._finalize_transaction(
                    tx_id=tx_id,
                    tx_ref=tx_ref,
                    mti=mti,
                    fields=input_fields,
                    response_code="57",
                    raw_request_msg=raw_req_msg,
                    tx_code=tx_code_cfg.transaction_code,
                    card=card,
                    customer=customer,
                    account=account,
                )
            self._add_check("Transaction Permissions", "PASSED", "00", f"Permitted by profile {prof.profile_code}")

# [PATCH local_host:policy_stage]
        # Step 15.1: Rajon Local Host policy (host status, source system, channel, transaction matrix, risk filters)
        self._lh_engine = None
        self._lh_ctx = None
        _lh_policy = None
        try:
            from app.local_host_engine import LocalHostEngine, build_context as _lh_build_context
            self._lh_engine = LocalHostEngine(self.db)
            self._lh_ctx = _lh_build_context(
                self.db, mti=mti, fields=input_fields, request_data=request_data, tx_code_cfg=tx_code_cfg,
                tx_amount=tx_amount, card=card, customer=customer, account=account, acq_inst=acq_inst,
                ps_code=ps_code_val, tx_id=tx_id, tx_ref=tx_ref,
            )
            _lh_policy = self._lh_engine.evaluate_policy(self._lh_ctx)
            for _c in _lh_policy.checks:
                self._add_check(_c["name"], _c["status"], _c["rc"], _c["message"])
        except Exception as _lh_err:  # a bug in the control center must never take the host down
            _lh_policy = None
            self._lh_engine = None
            self._add_check("Local Host Policy", "SKIPPED", "00", f"Policy engine error ignored: {_lh_err}")
        if _lh_policy is not None and not _lh_policy.allowed:
            return self._finalize_transaction(
                tx_id=tx_id,
                tx_ref=tx_ref,
                mti=mti,
                fields=input_fields,
                response_code=_lh_policy.response_code,
                raw_request_msg=raw_req_msg,
                tx_code=tx_code_cfg.transaction_code,
                card=card,
                customer=customer,
                account=account,
                source_channel=request_data.get("source_channel", "SIMULATOR"),
                issuer_institution_id=card.institution_id if (card and card.institution_id) else issuer_inst_id,
                acquirer_institution_id=acquirer_inst_id,
                ps_code=ps_code_val,
            )

# [PATCH step08:host_engine_eval_rules_stage]
        # [PATCH step13_03:auth_profile_and_limit_engine_stage]
        # Step 15.2: Resolve BIN -> Card Profile -> Authorization Profile, Check Tx Permission & Evaluate Configurable Card/Account Limits
        limit_eval_report = self.limit_engine.evaluate_transaction(
            card=card,
            account=account,
            tx_code=tx_code_cfg.transaction_code,
            tx_amount=tx_amount,
            tx_code_cfg=tx_code_cfg,
            billing_amount=tx_amount,
            processing_code=proc_code,
            tx_fields=input_fields,
            transaction_id=tx_id,
            transaction_reference=tx_ref,
        )
        self.limit_eval_results = limit_eval_report.evaluated_limits
        if limit_eval_report.authorization_profile:
            self.resolved_auth_profile_code = limit_eval_report.authorization_profile.auth_profile_code
            self._add_check(
                "Authorization Profile Resolution",
                "PASSED",
                "00",
                f"Resolved Authorization Profile {limit_eval_report.authorization_profile.auth_profile_code} via Card Profile {limit_eval_report.card_profile.profile_code if limit_eval_report.card_profile else 'DEFAULT'}",
            )

        if not limit_eval_report.allowed:
            if limit_eval_report.failed_stage == "AUTH_PROFILE_STATUS":
                self._add_check(
                    "Authorization Profile Check",
                    "FAILED",
                    limit_eval_report.response_code,
                    limit_eval_report.decline_reason or "Authorization profile inactive",
                )
            elif limit_eval_report.failed_stage == "TX_PERMISSION":
                self._add_check(
                    "Profile Transaction Permission",
                    "FAILED",
                    limit_eval_report.response_code,
                    limit_eval_report.decline_reason or "Transaction code disallowed by profile",
                )
            else:
                # Record passed limits up to the failed limit
                for ev in limit_eval_report.evaluated_limits:
                    chk_label = f"{ev['scope'].title()} Limit {ev['limit_code']} ({ev['limit_name']})"
                    if ev["final_result"] == "DECLINED":
                        self._add_check(chk_label, "FAILED", ev["response_code"], ev["decline_reason"] or "Limit exceeded")
                    else:
                        self._add_check(
                            chk_label,
                            "PASSED",
                            "00",
                            f"Projected {ev['projected_usage']} vs Max {ev['maximum_value']} (Op {ev['comparison_operator']}) -> {ev['final_result']}",
                        )
            return self._finalize_transaction(
                tx_id=tx_id,
                tx_ref=tx_ref,
                mti=mti,
                fields=input_fields,
                response_code=limit_eval_report.response_code,
                raw_request_msg=raw_req_msg,
                tx_code=tx_code_cfg.transaction_code,
                card=card,
                customer=customer,
                account=account,
                issuer_institution_id=card.institution_id if (card and card.institution_id) else issuer_inst_id,
                acquirer_institution_id=acquirer_inst_id,
                ps_code=ps_code_val,
            )
        else:
            if limit_eval_report.authorization_profile:
                self._add_check(
                    "Profile Transaction Permission",
                    "PASSED",
                    "00",
                    limit_eval_report.tx_permission_message,
                )
            for ev in limit_eval_report.evaluated_limits:
                chk_label = f"{ev['scope'].title()} Limit {ev['limit_code']} ({ev['limit_name']})"
                self._add_check(
                    chk_label,
                    "PASSED",
                    "00",
                    f"Prev={ev['previous_usage']}, Impact={ev['transaction_impact']}, Projected={ev['projected_usage']} (Op '{ev['comparison_operator']}' Max {ev['maximum_value']})",
                )

        # Step 15.5: Dynamic Authorizer Rules Evaluation (Stage: PRE_AUTH)
        rule_ctx = build_rule_context(
            mti=mti,
            fields=input_fields,
            tx_code=tx_code_cfg.transaction_code,
            tx_amount=tx_amount,
            card=card,
            customer=customer,
            account=account,
            issuer_inst=card.institution if card else None,
            acquirer_inst=acq_inst,
            ps_code=ps_code_val,
        )
        active_rules = self.db.query(AuthorizerRule).filter(AuthorizerRule.enabled == True).order_by(AuthorizerRule.priority.asc()).all()
        for rule in active_rules:
            try:
                matched = SafeAstEvaluator.evaluate(rule.expression, rule_ctx)
            except Exception as r_err:
                self._add_check(f'Rule {rule.rule_code}', 'SKIPPED', '00', f'Evaluation syntax error: {r_err}')
                continue

            if matched:
                rule.hit_count += 1
                if rule.action == 'DECLINE':
                    self._add_check(f'Authorizer Rule ({rule.rule_code})', 'FAILED', rule.response_code, rule.message)
                    return self._finalize_transaction(
                        tx_id=tx_id,
                        tx_ref=tx_ref,
                        mti=mti,
                        fields=input_fields,
                        response_code=rule.response_code,
                        raw_request_msg=raw_req_msg,
                        tx_code=tx_code_cfg.transaction_code,
                        card=card,
                        customer=customer,
                        account=account,
                        issuer_institution_id=card.institution_id if (card and card.institution_id) else issuer_inst_id,
                        acquirer_institution_id=acquirer_inst_id,
                        ps_code=ps_code_val,
                    )
                else:
                    self._add_check(f'Authorizer Rule ({rule.rule_code})', 'PASSED', '00', f'{rule.action}: {rule.message}')
                    if rule.stop_on_match:
                        break


# [PATCH local_host:algo_pre_auth]
        # Step 15.6: Algo Control blocks (Python / SQL risk algos, stage PRE_AUTH)
        _lh_algo = None
        if getattr(self, "_lh_engine", None) is not None:
            try:
                from app.local_host_engine import build_context as _lh_build_context
                _ap = limit_eval_report.authorization_profile if limit_eval_report else None
                self._lh_ctx = _lh_build_context(
                    self.db, mti=mti, fields=input_fields, request_data=request_data, tx_code_cfg=tx_code_cfg,
                    tx_amount=tx_amount, card=card, customer=customer, account=account, acq_inst=acq_inst,
                    ps_code=ps_code_val, tx_id=tx_id, tx_ref=tx_ref,
                    auth_profile_code=getattr(_ap, "auth_profile_code", None),
                    auth_profile_name=getattr(_ap, "profile_name", None),
                )
                _lh_algo = self._lh_engine.run_algos("PRE_AUTH", self._lh_ctx)
                for _c in _lh_algo.checks:
                    self._add_check(_c["name"], _c["status"], _c["rc"], _c["message"])
            except Exception as _lh_err:
                _lh_algo = None
                self._add_check("Risk Algos (PRE_AUTH)", "SKIPPED", "00", f"Algo engine error ignored: {_lh_err}")
        if _lh_algo is not None and _lh_algo.decline:
            return self._finalize_transaction(
                tx_id=tx_id,
                tx_ref=tx_ref,
                mti=mti,
                fields=input_fields,
                response_code=_lh_algo.decline["rc"],
                raw_request_msg=raw_req_msg,
                tx_code=tx_code_cfg.transaction_code,
                card=card,
                customer=customer,
                account=account,
                source_channel=request_data.get("source_channel", "SIMULATOR"),
                issuer_institution_id=card.institution_id if (card and card.institution_id) else issuer_inst_id,
                acquirer_institution_id=acquirer_inst_id,
                ps_code=ps_code_val,
            )

        # Step 16-18: HSM Cryptographic Checks (PIN / PVV / CVV / EMV / MAC)
        pin_prof = self.db.query(PinProfile).filter(PinProfile.card_id == card.id).first()
        if tx_code_cfg.pin_required or tx_code_cfg.pvv_required or "52" in input_fields:
            if pin_prof and pin_prof.retry_counter >= pin_prof.maximum_retry_count:
                self._add_check("PIN Retry Counter Check", "FAILED", "62", "Maximum PIN tries exceeded")
                return self._finalize_transaction(
                    tx_id=tx_id,
                    tx_ref=tx_ref,
                    mti=mti,
                    fields=input_fields,
                    response_code="62",
                    raw_request_msg=raw_req_msg,
                    tx_code=tx_code_cfg.transaction_code,
                    card=card,
                    customer=customer,
                    account=account,
                )

            pin_block = input_fields.get("52")
            if not pin_block:
                self._add_check("PIN Verification", "FAILED", "55", "PIN required by transaction code but DE52 is absent")
                return self._finalize_transaction(
                    tx_id=tx_id,
                    tx_ref=tx_ref,
                    mti=mti,
                    fields=input_fields,
                    response_code="55",
                    raw_request_msg=raw_req_msg,
                    tx_code=tx_code_cfg.transaction_code,
                    card=card,
                    customer=customer,
                    account=account,
                )

            hsm_pin_res = self.hsm.verify_pin_pvv(
                pan=pan,
                encrypted_pin_block=pin_block,
                expected_pvv=pin_prof.pin_offset_reference if pin_prof else "7821",
                pvki=pin_prof.pvki if pin_prof else "1",
                pvk_id=pin_prof.pvk_key_reference if pin_prof else "PVK_VISA_01",
                transaction_id=tx_id,
            )
            if hsm_pin_res["status"] != "APPROVED":
                if pin_prof:
                    pin_prof.retry_counter += 1
                self._add_check(
                    "HSM PIN/PVV Verification",
                    "FAILED",
                    "55",
                    f"HSM declined PIN (Audit {hsm_pin_res['audit_reference']})",
                    hsm_pin_res["duration_ms"],
                )
                return self._finalize_transaction(
                    tx_id=tx_id,
                    tx_ref=tx_ref,
                    mti=mti,
                    fields=input_fields,
                    response_code="55",
                    raw_request_msg=raw_req_msg,
                    tx_code=tx_code_cfg.transaction_code,
                    card=card,
                    customer=customer,
                    account=account,
                )
            if pin_prof:
                pin_prof.retry_counter = 0
            self._add_check(
                "HSM PIN/PVV Verification",
                "PASSED",
                "00",
                f"Verified via {hsm_pin_res['mode']} (Audit {hsm_pin_res['audit_reference']})",
                hsm_pin_res["duration_ms"],
            )

        if tx_code_cfg.cvv_required:
            f121 = input_fields.get("121", "")
            supplied_cvv = f121[3:6].strip() if len(f121) >= 6 else "011"
            exp_yy_mm = f"{str(card.expiry_year)[-2:]}{card.expiry_month:02d}"
            cvv_res = self.hsm.verify_cvv(
                pan=pan,
                expiry_yy_mm=exp_yy_mm,
                service_code="101",
                supplied_cvv=supplied_cvv,
                transaction_id=tx_id,
            )
            if cvv_res["status"] != "APPROVED":
                self._add_check("HSM CVV Verification", "FAILED", "80", "CVV verification failed", cvv_res["duration_ms"])
                return self._finalize_transaction(
                    tx_id=tx_id,
                    tx_ref=tx_ref,
                    mti=mti,
                    fields=input_fields,
                    response_code="80",
                    raw_request_msg=raw_req_msg,
                    tx_code=tx_code_cfg.transaction_code,
                    card=card,
                    customer=customer,
                    account=account,
                )
            self._add_check("HSM CVV Verification", "PASSED", "00", "CVV verified by HSM", cvv_res["duration_ms"])

        if tx_code_cfg.emv_required or "55" in input_fields:
            de55 = input_fields.get("55", "")
            if de55:
                emv_prof = self.db.query(EmvProfile).filter(EmvProfile.card_id == card.id).first()
                emv_res = self.hsm.verify_emv_cryptogram(
                    pan=pan,
                    psn=emv_prof.card_sequence_number if emv_prof else "01",
                    de55_hex=de55,
                    mk_ac_id=emv_prof.master_key_reference if emv_prof else "MK_AC_EMV01",
                    transaction_id=tx_id,
                )
                if emv_res["status"] != "APPROVED":
                    self._add_check("HSM EMV ARQC Check", "FAILED", "85", "ARQC cryptogram mismatch", emv_res["duration_ms"])
                    return self._finalize_transaction(
                        tx_id=tx_id,
                        tx_ref=tx_ref,
                        mti=mti,
                        fields=input_fields,
                        response_code="85",
                        raw_request_msg=raw_req_msg,
                        tx_code=tx_code_cfg.transaction_code,
                        card=card,
                        customer=customer,
                        account=account,
                    )
                self._add_check(
                    "HSM EMV ARQC Check",
                    "PASSED",
                    "00",
                    f"ARQC verified, ARPC generated ({emv_res['sanitized_response'].get('arpc_generated')})",
                    emv_res["duration_ms"],
                )

        if tx_code_cfg.mac_required or "64" in input_fields:
            mac_val = input_fields.get("64")
            mac_res = self.hsm.verify_or_generate_mac(
                data_hex=stan.encode("utf-8").hex().upper(),
                supplied_mac=mac_val,
                transaction_id=tx_id,
            )
            if mac_res["status"] != "APPROVED":
                self._add_check("HSM MAC Verification", "FAILED", "30", "MAC verification failed", mac_res["duration_ms"])
                return self._finalize_transaction(
                    tx_id=tx_id,
                    tx_ref=tx_ref,
                    mti=mti,
                    fields=input_fields,
                    response_code="30",
                    raw_request_msg=raw_req_msg,
                    tx_code=tx_code_cfg.transaction_code,
                    card=card,
                    customer=customer,
                    account=account,
                )
            self._add_check("HSM MAC Verification", "PASSED", "00", "MAC verified by HSM", mac_res["duration_ms"])

        # Step 19-20: Check Card Limits & Account Limits (RAJON CHECKCARDLIMITS & CHECKACCT2CARDLIMITS)
        card_limit = self.db.query(CardLimit).filter(CardLimit.card_id == card.id, CardLimit.status == "ACTIVE").first()
        acct_limit = self.db.query(AccountLimit).filter(AccountLimit.account_id == account.id, AccountLimit.status == "ACTIVE").first()

        if tx_code_cfg.limit_check_required and tx_code_cfg.financial_flag and tx_code_cfg.debit_flag:
            if self._is_rule_enabled("CHECKCARDLIMITS", True) and card_limit:
                if tx_amount > card_limit.transaction_limit:
                    self._add_check(
                        "Card Limit Check (CHECKCARDLIMITS)",
                        "FAILED",
                        "61",
                        f"Amount {tx_amount} exceeds card per-tx limit {card_limit.transaction_limit}",
                    )
                    return self._finalize_transaction(
                        tx_id=tx_id,
                        tx_ref=tx_ref,
                        mti=mti,
                        fields=input_fields,
                        response_code="61",
                        raw_request_msg=raw_req_msg,
                        tx_code=tx_code_cfg.transaction_code,
                        card=card,
                        customer=customer,
                        account=account,
                    )
                if (card_limit.daily_used + tx_amount) > card_limit.daily_limit:
                    self._add_check(
                        "Card Limit Check (CHECKCARDLIMITS)",
                        "FAILED",
                        "61",
                        f"Daily card limit {card_limit.daily_limit} would be exceeded",
                    )
                    return self._finalize_transaction(
                        tx_id=tx_id,
                        tx_ref=tx_ref,
                        mti=mti,
                        fields=input_fields,
                        response_code="61",
                        raw_request_msg=raw_req_msg,
                        tx_code=tx_code_cfg.transaction_code,
                        card=card,
                        customer=customer,
                        account=account,
                    )
                self._add_check(
                    "Card Limit Check (CHECKCARDLIMITS)",
                    "PASSED",
                    "00",
                    f"Within card limits (Daily used: {card_limit.daily_used + tx_amount}/{card_limit.daily_limit})",
                )

            if self._is_rule_enabled("CHECKACCT2CARDLIMITS", True) and acct_limit:
                if tx_amount > acct_limit.per_transaction_limit or (acct_limit.daily_used + tx_amount) > acct_limit.daily_limit:
                    self._add_check(
                        "Account Limit Check (CHECKACCT2CARDLIMITS)",
                        "FAILED",
                        "61",
                        f"Amount {tx_amount} exceeds account limit",
                    )
                    return self._finalize_transaction(
                        tx_id=tx_id,
                        tx_ref=tx_ref,
                        mti=mti,
                        fields=input_fields,
                        response_code="61",
                        raw_request_msg=raw_req_msg,
                        tx_code=tx_code_cfg.transaction_code,
                        card=card,
                        customer=customer,
                        account=account,
                    )
                self._add_check(
                    "Account Limit Check (CHECKACCT2CARDLIMITS)",
                    "PASSED",
                    "00",
                    f"Within account limits (Daily used: {acct_limit.daily_used + tx_amount}/{acct_limit.daily_limit})",
                )

        # Step 21: Check Account Balance / Overdraft (AUTHORIZEACCTBALANCESTRANS)
        if tx_code_cfg.financial_flag and tx_code_cfg.debit_flag and self._is_rule_enabled("AUTHORIZEACCTBALANCESTRANS", True):
            max_spendable = account.available_balance + account.overdraft_limit
            if tx_amount > max_spendable:
                self._add_check(
                    "Balance Authorization (AUTHORIZEACCTBALANCESTRANS)",
                    "FAILED",
                    "51",
                    f"Insufficient funds: Required {tx_amount}, Spendable {max_spendable}",
                )
                return self._finalize_transaction(
                    tx_id=tx_id,
                    tx_ref=tx_ref,
                    mti=mti,
                    fields=input_fields,
                    response_code="51",
                    raw_request_msg=raw_req_msg,
                    tx_code=tx_code_cfg.transaction_code,
                    card=card,
                    customer=customer,
                    account=account,
                )
            self._add_check(
                "Balance Authorization (AUTHORIZEACCTBALANCESTRANS)",
                "PASSED",
                "00",
                f"Sufficient balance ({account.available_balance} {account.currency})",
            )

# [PATCH local_host:algo_post_auth]
        # Step 22.5: Algo Control blocks (stage POST_AUTH: balance and limits already passed)
        _lh_post = None
        if getattr(self, "_lh_engine", None) is not None:
            try:
                _lh_post = self._lh_engine.run_algos("POST_AUTH", self._lh_ctx)
                for _c in _lh_post.checks:
                    self._add_check(_c["name"], _c["status"], _c["rc"], _c["message"])
            except Exception as _lh_err:
                _lh_post = None
                self._add_check("Risk Algos (POST_AUTH)", "SKIPPED", "00", f"Algo engine error ignored: {_lh_err}")
        if _lh_post is not None and _lh_post.decline:
            return self._finalize_transaction(
                tx_id=tx_id,
                tx_ref=tx_ref,
                mti=mti,
                fields=input_fields,
                response_code=_lh_post.decline["rc"],
                raw_request_msg=raw_req_msg,
                tx_code=tx_code_cfg.transaction_code,
                card=card,
                customer=customer,
                account=account,
                source_channel=request_data.get("source_channel", "SIMULATOR"),
                issuer_institution_id=card.institution_id if (card and card.institution_id) else issuer_inst_id,
                acquirer_institution_id=acquirer_inst_id,
                ps_code=ps_code_val,
            )

        # Step 23-25: Approve, Post Atomic Ledger Entry, and Update Limit Counters
        self._add_check("Authorization Decision", "PASSED", "00", "Transaction APPROVED by Host Engine")
        # Queue pending LimitCalculationEngine usage to be flushed right after Transaction row is inserted
        if limit_eval_report and limit_eval_report.pending_consumptions:
            self.pending_limit_consumptions = list(limit_eval_report.pending_consumptions)

        if tx_code_cfg.financial_flag and tx_amount > Decimal("0.00"):
            bal_before = account.available_balance
            if tx_code_cfg.debit_flag:
                account.available_balance -= tx_amount
                account.ledger_balance -= tx_amount
                entry_type = "DEBIT"
            else:
                account.available_balance += tx_amount
                account.ledger_balance += tx_amount
                entry_type = "CREDIT"
            bal_after = account.available_balance

            if entry_type == "DEBIT":
                if card_limit:
                    card_limit.daily_used += tx_amount
                    card_limit.weekly_used += tx_amount
                    card_limit.monthly_used += tx_amount
                if acct_limit:
                    acct_limit.daily_used += tx_amount
                    acct_limit.weekly_used += tx_amount
                    acct_limit.monthly_used += tx_amount

            ledger_info = {
                "entry_type": entry_type,
                "amount": tx_amount,
                "currency": account.currency,
                "balance_before": bal_before,
                "balance_after": bal_after,
                "description": f"{tx_code_cfg.transaction_name} (RRN {rrn})",
            }
            self._add_check(
                "Atomic Ledger Posting",
                "PASSED",
                "00",
                f"Posted {entry_type} of {tx_amount} {account.currency} (New Bal: {bal_after})",
            )
        else:
            ledger_info = None

        return self._finalize_transaction(
            tx_id=tx_id,
            tx_ref=tx_ref,
            mti=mti,
            fields=input_fields,
            response_code="00",
            raw_request_msg=raw_req_msg,
            tx_code=tx_code_cfg.transaction_code,
            card=card,
            customer=customer,
            account=account,
            ledger_info=ledger_info,
            source_channel=request_data.get("source_channel", "SIMULATOR"),
            idempotency_key=idem_key,
            issuer_institution_id=issuer_inst_id,
            acquirer_institution_id=acquirer_inst_id,
            ps_code=ps_code_val,
        )

    def _process_reversal(
        self,
        tx_id: str,
        tx_ref: str,
        mti: str,
        fields: Dict[str, str],
        stan: str,
        rrn: str,
        tx_amount: Decimal,
        raw_req_msg: str,
        source_channel: str,
    ) -> Dict[str, Any]:
        orig_tx = (
            self.db.query(Transaction)
            .filter(
                Transaction.rrn == rrn,
                Transaction.mti.in_(["0100", "0200"]),
                Transaction.authorization_status == "APPROVED",
            )
            .order_by(Transaction.created_at.desc())
            .first()
        )
        if not orig_tx:
            self._add_check("Original Transaction Lookup", "FAILED", "15", f"Original transaction with RRN {rrn} not found")
            return self._finalize_transaction(
                tx_id=tx_id,
                tx_ref=tx_ref,
                mti=mti,
                fields=fields,
                response_code="15",
                raw_request_msg=raw_req_msg,
                source_channel=source_channel,
            )

        if orig_tx.transaction_status == "REVERSED":
            self._add_check("Reversal Idempotency Check", "FAILED", "94", f"Transaction {orig_tx.transaction_reference} already reversed")
            return self._finalize_transaction(
                tx_id=tx_id,
                tx_ref=tx_ref,
                mti=mti,
                fields=fields,
                response_code="94",
                raw_request_msg=raw_req_msg,
                source_channel=source_channel,
            )

        account = self.db.query(Account).filter(Account.id == orig_tx.account_id).with_for_update().first()
        card = self.db.query(Card).filter(Card.id == orig_tx.card_id).first()
        customer = self.db.query(Customer).filter(Customer.id == orig_tx.customer_id).first()

        ledger_info = None
        if account and orig_tx.transaction_amount > Decimal("0.00"):
            bal_before = account.available_balance
            account.available_balance += orig_tx.transaction_amount
            account.ledger_balance += orig_tx.transaction_amount
            bal_after = account.available_balance
            ledger_info = {
                "entry_type": "CREDIT",
                "amount": orig_tx.transaction_amount,
                "currency": account.currency,
                "balance_before": bal_before,
                "balance_after": bal_after,
                "description": f"Reversal of RRN {rrn}",
            }

        orig_tx.transaction_status = "REVERSED"
        self.limit_engine.reverse_transaction_usage(
            original_transaction_id=orig_tx.id,
            reversal_transaction_id=tx_id,
            card_id=orig_tx.card_id,
            account_id=orig_tx.account_id,
            original_amount=orig_tx.transaction_amount,
        )
        self._add_check(
            "Reversal Processing",
            "PASSED",
            "00",
            f"Reversed original transaction {orig_tx.transaction_reference} and restored {orig_tx.transaction_amount}",
        )

        return self._finalize_transaction(
            tx_id=tx_id,
            tx_ref=tx_ref,
            mti=mti,
            fields=fields,
            response_code="00",
            raw_request_msg=raw_req_msg,
            tx_code=orig_tx.transaction_code,
            card=card,
            customer=customer,
            account=account,
            ledger_info=ledger_info,
            original_tx=orig_tx,
            source_channel=source_channel,
        )

    def _finalize_transaction(
        self,
        tx_id: str,
        tx_ref: str,
        mti: str,
        fields: Dict[str, str],
        response_code: str,
        raw_request_msg: str,
        tx_code: Optional[str] = None,
        card: Optional[Card] = None,
        customer: Optional[Customer] = None,
        account: Optional[Account] = None,
        ledger_info: Optional[Dict[str, Any]] = None,
        original_tx: Optional[Transaction] = None,
        source_channel: str = "SIMULATOR",
        idempotency_key: Optional[str] = None,
        issuer_institution_id: Optional[str] = None,
        acquirer_institution_id: Optional[str] = None,
        ps_code: str = "ITCL",
    ) -> Dict[str, Any]:
        resp_mti = RESPONSE_MTI_MAP.get(mti, "0210")
        resp_desc = self._get_response_description(response_code)
        approved = response_code == "00"

        resp_fields: Dict[int, str] = {}
        for k, v in fields.items():
            if k.isdigit() and int(k) not in (52, 55):
                resp_fields[int(k)] = v
        resp_fields[38] = uuid.uuid4().hex[:6].upper() if approved else "000000"
        resp_fields[39] = f"000{response_code}"

        if account and approved:
            # Populate F105 Account Balance Data (12-digit ledger + 12-digit available + '1')
            led_cents = int(account.ledger_balance * 100)
            avl_cents = int(account.available_balance * 100)
            resp_fields[105] = f"{max(0, led_cents):012d}{max(0, avl_cents):012d}1"

        raw_resp_msg, compact_resp = build_tic_message(resp_mti, resp_fields)
        raw_amt = fields.get("4", "000000000000")
        tx_amount = (Decimal(raw_amt) / Decimal("100")).quantize(Decimal("0.01")) if raw_amt.isdigit() else Decimal("0.00")

        tx = Transaction(
            id=tx_id,
            transaction_reference=tx_ref,
            idempotency_key=idempotency_key,
            mti=mti,
            processing_code=fields.get("3", "0100000"),
            transaction_code=tx_code,
            stan=fields.get("11", "000001"),
            rrn=fields.get("37", "000000000001"),
            terminal_id=fields.get("41", "TERM0001"),
            merchant_id=fields.get("32", "MERCH001"),
            masked_pan=card.masked_pan if card else mask_pan(fields.get("2", "")),
            card_id=card.id if card else None,
            customer_id=customer.id if customer else None,
            account_id=account.id if account else None,
            transaction_amount=tx_amount,
            billing_amount=tx_amount,
            currency=account.currency if account else fields.get("49", "BDT"),
            response_code=response_code,
            response_message=resp_desc,
            transaction_status="REVERSED" if original_tx else "COMPLETED",
# [PATCH step02_01:tx_model_assign_inst_fixed]
            authorization_status="APPROVED" if approved else "DECLINED",
            source_channel=source_channel,
            issuer_institution_id=issuer_institution_id or (card.institution_id if card else None),
            acquirer_institution_id=acquirer_institution_id,
            ps_code=ps_code,
            is_on_us=(issuer_institution_id == acquirer_institution_id) if (issuer_institution_id and acquirer_institution_id) else True,
            original_transaction_id=original_tx.id if original_tx else None,
            completed_at=datetime.now(timezone.utc),
        )
# [PATCH tx_log_viewer_v1:populate_tx_metadata_and_trace]
        tic_meta = extract_metadata_from_tic(raw_request_msg)
        f3_code = (fields.get("3", "0100000") or "0100000")[:3]
        tx.correlation_id = get_correlation_id() or tx_ref
        tx.approval_code = resp_fields.get(38)
        tx.mcc = fields.get("18") or tic_meta.get("mcc")
        tx.pos_entry_mode = fields.get("22") or tic_meta.get("pos_entry_mode")
        tx.pos_condition_code = fields.get("25") or tic_meta.get("pos_condition_code")
        tx.acquirer_id = fields.get("32") or tic_meta.get("acquirer_id")
        tx.forwarding_id = fields.get("33") or tic_meta.get("forwarding_id")
        tx.terminal_name = tic_meta.get("terminal_name") or fields.get("41", "TERM0001")
        tx.terminal_owner = tic_meta.get("terminal_owner") or (tx.acquirer_institution.short_name if tx.acquirer_institution else "ITCL")
        tx.merchant_name = tic_meta.get("merchant_name") or fields.get("32", "MERCH001")
        tx.source_account = account.account_number if account else (fields.get("102") or tic_meta.get("source_account"))
        tx.destination_account = fields.get("103") or tic_meta.get("destination_account")
        tx.transaction_type_name = TRAN_CODES.get(f3_code) or ("Acquirer Reversal" if mti.startswith("04") else f"Tran Code {tx_code or f3_code}")
        tx.processing_duration_ms = max(1, int((time.perf_counter() - getattr(self, "pipeline_t0", time.perf_counter())) * 1000))
        failed_chk = next((c for c in self.checks_log if c["check_status"] == "FAILED"), None)
        tx.decline_reason = failed_chk["message"] if (not approved and failed_chk) else (None if approved else resp_desc)

        self.db.add(tx)
        self.db.flush()

        # [PATCH step13_07:commit_limit_usage_after_tx_flush]
        if approved and getattr(self, 'pending_limit_consumptions', None):
            self.limit_engine.commit_approved_usage(tx.id, self.pending_limit_consumptions)
            self.pending_limit_consumptions = []

        # Persist structured TransactionTraceEvent records for actual executed stages
        trace_order = 1
        self.db.add(TransactionTraceEvent(
            transaction_id=tx.id,
            correlation_id=tx.correlation_id,
            event_order=trace_order,
            event_code="TRANSACTION_RECEIVED",
            event_category="INGRESS",
            event_name="TRANSACTION RECEIVED",
            event_status="PASSED",
            response_code="00",
            duration_ms=1,
            message=f"Incoming {mti} transaction {tx_ref} received via {source_channel} (STAN {tx.stan}, RRN {tx.rrn}).",
        ))
        for chk in self.checks_log:
            trace_order += 1
            cname_up = chk["check_name"].upper()
            cat = "VALIDATION"
            if "MESSAGE" in cname_up:
                cat = "PARSING"
            elif "ROUTING" in cname_up or "NETWORK" in cname_up:
                cat = "ROUTING"
            elif "HSM" in cname_up or "PIN" in cname_up or "CVV" in cname_up or "EMV" in cname_up or "MAC" in cname_up:
                cat = "HSM_CRYPTO"
            elif "LIMIT" in cname_up:
                cat = "LIMITS"
            elif "RULE" in cname_up:
                cat = "RISK_RULE"
            elif "BALANCE" in cname_up or "DECISION" in cname_up:
                cat = "AUTHORIZATION"
            elif "LEDGER" in cname_up:
                cat = "LEDGER"
            self.db.add(TransactionTraceEvent(
                transaction_id=tx.id,
                correlation_id=tx.correlation_id,
                event_order=trace_order,
                event_code=cname_up.replace(" ", "_")[:50],
                event_category=cat,
                event_name=chk["check_name"].upper(),
                event_status=chk["check_status"],
                response_code=chk["response_code"],
                duration_ms=chk["duration_ms"],
                message=chk["message"],
            ))
        trace_order += 1
        self.db.add(TransactionTraceEvent(
            transaction_id=tx.id,
            correlation_id=tx.correlation_id,
            event_order=trace_order,
            event_code="RESPONSE_GENERATION",
            event_category="EGRESS",
            event_name="RESPONSE GENERATION",
            event_status="PASSED",
            response_code=response_code,
            duration_ms=1,
            message=f"ISO 8583 / TIC {resp_mti} response generated (F39=000{response_code}, Approval={tx.approval_code}).",
        ))
        trace_order += 1
        self.db.add(TransactionTraceEvent(
            transaction_id=tx.id,
            correlation_id=tx.correlation_id,
            event_order=trace_order,
            event_code="TRANSACTION_COMPLETED",
            event_category="COMPLETION",
            event_name="TRANSACTION COMPLETED",
            event_status=tx.authorization_status,
            response_code=response_code,
            duration_ms=tx.processing_duration_ms,
            message=f"Final response delivered ({tx.authorization_status} — RC {response_code}: {resp_desc}).",
        ))

        for chk in self.checks_log:
            self.db.add(TransactionCheck(transaction_id=tx.id, **chk))

        req_msg_rec = TransactionMessage(
            transaction_id=tx.id,
            message_type="REQUEST",
            mti=mti,
            sanitized_message=mask_raw_tic_message(raw_request_msg),
            message_format="TIC",
        )
        resp_msg_rec = TransactionMessage(
            transaction_id=tx.id,
            message_type="RESPONSE",
            mti=resp_mti,
            sanitized_message=mask_raw_tic_message(raw_resp_msg),
            message_format="TIC",
        )
        self.db.add_all([req_msg_rec, resp_msg_rec])
        self.db.flush()

        tx.request_message_reference = req_msg_rec.id
        tx.response_message_reference = resp_msg_rec.id

        if ledger_info and account:
            self.db.add(
                AccountLedger(
                    account_id=account.id,
                    transaction_id=tx.id,
                    **ledger_info,
                )
            )

        if original_tx:
            self.db.add(
                TransactionReversal(
                    original_transaction_id=original_tx.id,
                    reversal_transaction_id=tx.id,
                    original_stan=original_tx.stan,
                    original_rrn=original_tx.rrn,
                    reversal_reason="Acquirer Reversal 0400",
                    reversal_amount=orig_tx.transaction_amount if (orig_tx := original_tx) else tx_amount,
                    reversal_status="COMPLETED",
                )
            )

        if customer and customer.mobile_number:
            self.db.add(
                Notification(
                    transaction_id=tx.id,
                    notification_type="SMS_SIMULATED",
                    recipient_masked=f"***{customer.mobile_number[-4:]}",
                    message_template=(
                        f"[RAJON HOST] Card {tx.masked_pan} TX {tx_amount} {tx.currency} "
                        f"Status: {tx.authorization_status} (RC {response_code}). Avl Bal: "
                        f"{account.available_balance if account else 'N/A'}"
                    ),
                    delivery_status="SIMULATED_SENT",
                )
            )

        record_system_log(
            self.db,
            "INFO" if approved else "WARNING",
            "HostTransactionProcessor",
            "TRANSACTION_COMPLETED",
            f"Transaction {tx_ref} finished with RC={response_code} ({resp_desc})",
            transaction_id=tx.id,
            details={
                "transaction_reference": tx_ref,
                "mti": mti,
                "response_mti": resp_mti,
                "stan": tx.stan,
                "rrn": tx.rrn,
                "masked_pan": tx.masked_pan,
                "amount": str(tx_amount),
                "response_code": response_code,
                "authorization_status": tx.authorization_status,
            },
        )

        self.db.commit()

        return {
            "transaction_id": tx.id,
            "transaction_reference": tx.transaction_reference,
            "mti": mti,
            "response_mti": resp_mti,
            "stan": tx.stan,
            "rrn": tx.rrn,
            "masked_pan": tx.masked_pan,
            "amount": float(tx_amount),
            "currency": tx.currency,
            "response_code": response_code,
            "response_tic_f39": f"000{response_code}",
            "response_message": resp_desc,
            "authorization_status": tx.authorization_status,
            "ps_code": tx.ps_code,
            "is_on_us": tx.is_on_us,
            "issuer_institution_id": tx.issuer_institution_id,
            "acquirer_institution_id": tx.acquirer_institution_id,
            "account_balance_after": float(account.available_balance) if account else None,
            "sanitized_request_tic": mask_raw_tic_message(raw_request_msg),
            "sanitized_response_tic": mask_raw_tic_message(raw_resp_msg),
            "compact_response_tic": mask_raw_tic_message(compact_resp),
            "checks": self.checks_log,
            "authorization_profile_code": self.resolved_auth_profile_code,
            "limit_evaluations": self.limit_eval_results,
        }
