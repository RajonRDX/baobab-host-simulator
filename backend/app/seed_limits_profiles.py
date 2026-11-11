"""
seed_limits_profiles.py — Idempotent Seeding & Data Healing for:
  - Card Profiles linked to Institutions, Processing Systems, and BIN Ranges
  - Existing Cards linked to their BIN's Card Profile if unassigned
  - Default Configurable Card Limit Definitions (100, 101, 102, 103)
  - Default Configurable Account Limit Definitions (200, 201)
  - Default Authorization Profile ("VISA_CLASSIC_STANDARD") linked to VISA_CLASSIC Card Profile
    with Allowed Transactions, Card/Account Limit Assignments, and Transaction-Code Limit Impacts.
"""

from decimal import Decimal
from sqlalchemy.orm import Session
from app.models import (
    AuthorizationProfile,
    AuthProfileLimitAssignment,
    AuthProfileTxCodePermission,
    BinRange,
    Card,
    CardProfile,
    Institution,
    LimitDefinition,
    ProcessingSystem,
    TransactionCode,
    TxCodeLimitImpact,
)


def seed_limits_and_authorization_profiles(db: Session) -> None:
    itcl_ps = db.query(ProcessingSystem).filter(ProcessingSystem.ps_code == "ITCL").first()
    xbank = db.query(Institution).filter(Institution.institution_code == "XBANK").first()

    # 1. Ensure standard Card Profiles exist and have Institution / ProcessingSystem metadata
    default_card_profiles = [
        {
            "profile_code": "VISA_CLASSIC",
            "profile_name": "VISA Classic Debit Profile",
            "description": "Standard domestic & e-commerce Visa Classic Debit profile under ITCL switch",
            "card_product": "VISA_DEBIT_CLASSIC",
            "card_type": "DEBIT",
            "currency": "BDT",
        },
        {
            "profile_code": "VISA_GOLD",
            "profile_name": "VISA Gold Priority Profile",
            "description": "High-limit Visa Gold Debit/Credit profile",
            "card_product": "VISA_GOLD",
            "card_type": "DEBIT",
            "currency": "BDT",
        },
        {
            "profile_code": "NPSB_PROPRIETARY",
            "profile_name": "NPSB / QCash Domestic Profile",
            "description": "National Payment Switch Bangladesh domestic proprietary card profile",
            "card_product": "QCASH_PROPRIETARY",
            "card_type": "DEBIT",
            "currency": "BDT",
        },
    ]

    profile_map = {}
    for cp_data in default_card_profiles:
        prof = db.query(CardProfile).filter(CardProfile.profile_code == cp_data["profile_code"]).first()
        if not prof:
            prof = CardProfile(
                profile_code=cp_data["profile_code"],
                profile_name=cp_data["profile_name"],
                description=cp_data["description"],
                institution_id=xbank.id if xbank else None,
                processing_system_id=itcl_ps.id if itcl_ps else None,
                card_type=cp_data["card_type"],
                currency=cp_data["currency"],
                card_product=cp_data["card_product"],
                domestic_enabled=True,
                international_enabled=(cp_data["profile_code"] == "VISA_GOLD"),
                ecommerce_enabled=True,
                contactless_enabled=True,
                cash_enabled=True,
                status="ACTIVE",
            )
            db.add(prof)
            db.flush()
        else:
            if not getattr(prof, "description", None):
                prof.description = cp_data["description"]
            if not getattr(prof, "institution_id", None) and xbank:
                prof.institution_id = xbank.id
            if not getattr(prof, "processing_system_id", None) and itcl_ps:
                prof.processing_system_id = itcl_ps.id
            if not getattr(prof, "card_type", None):
                prof.card_type = cp_data["card_type"]
            if not getattr(prof, "currency", None):
                prof.currency = cp_data["currency"]
        profile_map[cp_data["profile_code"]] = prof

    visa_classic_prof = profile_map["VISA_CLASSIC"]

    # 2. Link existing BIN ranges to Card Profiles only if not yet assigned
    for b in db.query(BinRange).all():
        if not getattr(b, "card_profile_id", None):
            if "GOLD" in (b.card_product or "").upper():
                b.card_profile_id = profile_map["VISA_GOLD"].id
            elif "NPSB" in (b.scheme or "").upper() or "QCASH" in (b.card_product or "").upper():
                b.card_profile_id = profile_map["NPSB_PROPRIETARY"].id
            else:
                b.card_profile_id = visa_classic_prof.id
    db.flush()

    # 3. Link existing Cards without card_profile_id to their matching BIN's card_profile_id
    all_bins = db.query(BinRange).filter(BinRange.status == "ACTIVE").all()
    for card in db.query(Card).filter(Card.card_profile_id == None).all():  # noqa: E711
        pan = card.test_pan_reference or ""
        matched_bin = None
        best_len = -1
        for br in all_bins:
            if pan.startswith(br.bin_prefix) and len(br.bin_prefix) > best_len:
                matched_bin = br
                best_len = len(br.bin_prefix)
        if matched_bin and matched_bin.card_profile_id:
            card.card_profile_id = matched_bin.card_profile_id
        else:
            card.card_profile_id = visa_classic_prof.id
    db.flush()

    # 4. Seed Default Configurable Card Limits (100 - 103) and Account Limits (200 - 201)
    default_limits = [
        {
            "limit_code": "100",
            "limit_name": "Daily Card Transaction Limit",
            "description": "Maximum cumulative daily debit amount allowed on a card across all financial channels",
            "scope": "CARD",
            "currency": "BDT",
            "maximum_limit": Decimal("100000.00"),
            "reset_interval": "DAILY",
            "calculation_method": "SUM_TRANSACTION_AMOUNT",
            "comparison_operator": ">",
            "impact_action": "DECLINE",
            "decline_response_code": "61",
        },
        {
            "limit_code": "101",
            "limit_name": "Single Card Transaction Maximum",
            "description": "Maximum amount allowed for any single card transaction",
            "scope": "CARD",
            "currency": "BDT",
            "maximum_limit": Decimal("50000.00"),
            "reset_interval": "PER_TRANSACTION",
            "calculation_method": "MAX_SINGLE_TRANSACTION",
            "comparison_operator": ">",
            "impact_action": "DECLINE",
            "decline_response_code": "61",
        },
        {
            "limit_code": "102",
            "limit_name": "Daily ATM Cash Withdrawal Limit",
            "description": "Maximum daily cumulative ATM cash withdrawal amount per card",
            "scope": "CARD",
            "currency": "BDT",
            "maximum_limit": Decimal("50000.00"),
            "reset_interval": "DAILY",
            "calculation_method": "SUM_CASH_WITHDRAWAL",
            "comparison_operator": ">",
            "impact_action": "DECLINE",
            "decline_response_code": "61",
        },
        {
            "limit_code": "103",
            "limit_name": "Daily Card Transaction Velocity Count",
            "description": "Maximum number of financial transactions permitted per card per day",
            "scope": "CARD",
            "currency": "BDT",
            "maximum_limit": Decimal("25.00"),
            "reset_interval": "DAILY",
            "calculation_method": "COUNT_TRANSACTION",
            "comparison_operator": ">",
            "impact_action": "DECLINE",
            "decline_response_code": "61",
        },
        {
            "limit_code": "200",
            "limit_name": "Daily Account Debit Limit",
            "description": "Maximum cumulative daily debit amount permitted on the linked bank account",
            "scope": "ACCOUNT",
            "currency": "BDT",
            "maximum_limit": Decimal("300000.00"),
            "reset_interval": "DAILY",
            "calculation_method": "SUM_TRANSACTION_AMOUNT",
            "comparison_operator": ">",
            "impact_action": "DECLINE",
            "decline_response_code": "61",
        },
        {
            "limit_code": "201",
            "limit_name": "Monthly Account Aggregate Limit",
            "description": "Maximum cumulative monthly debit amount permitted on the linked bank account",
            "scope": "ACCOUNT",
            "currency": "BDT",
            "maximum_limit": Decimal("3000000.00"),
            "reset_interval": "MONTHLY",
            "calculation_method": "SUM_TRANSACTION_AMOUNT",
            "comparison_operator": ">",
            "impact_action": "DECLINE",
            "decline_response_code": "61",
        },
    ]

    limit_obj_map = {}
    for l_cfg in default_limits:
        lim = db.query(LimitDefinition).filter(LimitDefinition.limit_code == l_cfg["limit_code"]).first()
        if not lim:
            lim = LimitDefinition(
                institution_id=xbank.id if xbank else None,
                status="ACTIVE",
                **l_cfg,
            )
            db.add(lim)
            db.flush()
        limit_obj_map[l_cfg["limit_code"]] = lim

    # 5. Seed Default Authorization Profiles for the Card Profiles
    auth_profiles_seed = [
        ("VISA_CLASSIC_STANDARD", "VISA Classic Standard Authorization Profile", visa_classic_prof),
        ("VISA_GOLD_EXECUTIVE", "VISA Gold Executive Authorization Profile", profile_map["VISA_GOLD"]),
        ("NPSB_DOMESTIC_STANDARD", "NPSB Domestic Standard Authorization Profile", profile_map["NPSB_PROPRIETARY"]),
    ]

    tx_codes_in_db = db.query(TransactionCode).all()

    for auth_code, auth_name, c_prof in auth_profiles_seed:
        ap = db.query(AuthorizationProfile).filter(AuthorizationProfile.auth_profile_code == auth_code).first()
        if not ap:
            ap = AuthorizationProfile(
                auth_profile_code=auth_code,
                profile_name=auth_name,
                description=f"Default authorization profile governing allowed transactions and limits for {c_prof.profile_code}",
                card_profile_id=c_prof.id,
                institution_id=xbank.id if xbank else None,
                unconfigured_tx_code_policy="REJECT",
                unconfigured_decline_rc="57",
                status="ACTIVE",
            )
            db.add(ap)
            db.flush()

            # Tab A: Populate permissions for all existing TransactionCodes
            for tc in tx_codes_in_db:
                perm = "ALLOWED" if tc.active else "DISALLOWED"
                db.add(
                    AuthProfileTxCodePermission(
                        authorization_profile_id=ap.id,
                        transaction_code_id=tc.id,
                        transaction_code=tc.transaction_code,
                        transaction_name=tc.transaction_name,
                        permission=perm,
                        decline_response_code="57",
                        description=f"Default permission for {tc.transaction_name}",
                        status="ACTIVE",
                    )
                )

            # Tab B & C: Assign Card Limits (100, 101, 102, 103) & Account Limits (200, 201)
            for prio, lcode in enumerate(["101", "100", "102", "103", "200", "201"], start=1):
                ldef = limit_obj_map[lcode]
                override_max = None
                if auth_code == "VISA_GOLD_EXECUTIVE" and ldef.scope == "CARD" and lcode in ("100", "101", "102"):
                    override_max = ldef.maximum_limit * Decimal("2")
                db.add(
                    AuthProfileLimitAssignment(
                        authorization_profile_id=ap.id,
                        limit_definition_id=ldef.id,
                        scope=ldef.scope,
                        maximum_limit_override=override_max,
                        evaluation_priority=prio * 10,
                        status="ACTIVE",
                    )
                )

            # Tab D: Seed Transaction-Code Limit Impact mappings based on actual TransactionCodes
            for tc in tx_codes_in_db:
                code_str = tc.transaction_code
                # Determine default impact type from transaction flags
                if tc.balance_inquiry_flag or not tc.financial_flag:
                    impact_type = "NO_IMPACT"
                elif tc.credit_flag and not tc.debit_flag:
                    # Deposit / refund / credit
                    impact_type = "NO_IMPACT"
                else:
                    impact_type = "INCREASE"

                for lcode in ["100", "101", "102", "103", "200", "201"]:
                    ldef = limit_obj_map[lcode]
                    basis = "TRANSACTION_COUNT" if ldef.calculation_method == "COUNT_TRANSACTION" else "TRANSACTION_AMOUNT"
                    db.add(
                        TxCodeLimitImpact(
                            authorization_profile_id=ap.id,
                            transaction_code=code_str,
                            limit_definition_id=ldef.id,
                            impact_type=impact_type,
                            calculation_basis=basis,
                            multiplier=Decimal("1.0000"),
                            description=f"{tc.transaction_name} -> {ldef.limit_name} ({impact_type})",
                            status="ACTIVE",
                        )
                    )

    db.commit()
