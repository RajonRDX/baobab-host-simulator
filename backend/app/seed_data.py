import logging
logger = logging.getLogger(__name__)
"""
seed_data.py
Seeds the local development database with synthetic records:
- 5 Customers
- 5 Accounts & Account Limits
- 5 Synthetic Cards, Card Profiles, Card Limits, PIN Profiles, and EMV Profiles
- Configurable Transaction Codes 10, 20, 30, 40 (administrator editable)
- Response Codes & BAOBAB-inspired Host Parameters (AUTHORIZEACCTBALANCESTRANS, CHECKCARDLIMITS, etc.)
- HSM Key References (metadata & KVCs only, never clear production keys)
"""

from datetime import date
from decimal import Decimal
from sqlalchemy.orm import Session
from app.hsm_adapter import SoftHsmCryptoCore
from app.models import (
    Account,
    AccountLimit,
    BinRange,
    Card,
    CardAccount,
    CardLimit,
    CardProfile,
    Customer,
    EmvProfile,
    HostParameter,
    HsmKeyReference,
    Institution,
    InstitutionProcessingSystem,
    NetworkProfile,
    PinProfile,
    ProcessingSystem,
    ResponseCode,
    TransactionCode,
    TransactionCodeField,
)
from app.security import mask_pan, tokenize_pan


# [PATCH step01_01:seed_early_call]
def seed_initial_data(db: Session) -> None:
    seed_processing_systems_and_institutions(db)
    if db.query(Customer).count() > 0:
        return

    xbank = db.query(Institution).filter(Institution.institution_code == 'XBANK').first()
    xbank_id = xbank.id if xbank else None
    itcl_ps = db.query(ProcessingSystem).filter(ProcessingSystem.ps_code == 'ITCL').first()
    itcl_id = itcl_ps.id if itcl_ps else None

    # 1. Response Codes
    response_codes = [
        ("00", "Approved", "APPROVAL", True),
        ("05", "Do not honor / Blocked status", "DECLINE", False),
        ("12", "Invalid transaction", "DECLINE", False),
        ("13", "Invalid amount", "DECLINE", False),
        ("14", "Invalid card number", "DECLINE", False),
        ("15", "Original transaction not found", "DECLINE", False),
        ("30", "Format error", "ERROR", False),
        ("51", "Insufficient funds", "DECLINE", False),
        ("54", "Expired card", "DECLINE", False),
        ("55", "Incorrect PIN", "DECLINE", False),
        ("57", "Transaction not permitted to cardholder", "DECLINE", False),
        ("61", "Exceeds withdrawal or transaction limit", "DECLINE", False),
        ("62", "PIN tries limit reached", "DECLINE", False),
        ("80", "Bad CVV", "DECLINE", False),
        ("85", "Bad ARQC cryptogram", "DECLINE", False),
        ("91", "Issuer or switch inoperative", "ERROR", False),
        ("94", "Duplicate transmission", "DECLINE", False),
    ]
    for code, desc, cat, app in response_codes:
        db.add(ResponseCode(response_code=code, response_description=desc, response_category=cat, approved_flag=app))

    # 2. BAOBAB-inspired Host Parameters
    host_params = [
        ("BAOBAB_AUTH_RULES", "AUTHORIZEACCTBALANCESTRANS", {"enabled": True, "order": 8}, "Verify available account balance & overdraft during financial debit authorization"),
        ("BAOBAB_AUTH_RULES", "CHECKCARDLIMITS", {"enabled": True, "order": 6}, "Evaluate ATH_CARDLIMIT per-transaction, daily, weekly, and monthly card limits"),
        ("BAOBAB_AUTH_RULES", "CHECKACCT2CARDLIMITS", {"enabled": True, "order": 7}, "Evaluate account-level transaction and velocity limits"),
        ("BAOBAB_AUTH_RULES", "DEFAULTREQUESTFUNCTION", {"enabled": True, "function": "HostTransactionProcessor.process_transaction"}, "Default incoming TIC/ISO authorization router"),
        ("BAOBAB_AUTH_RULES", "DEFAULTRESPONSEFUNCTION", {"enabled": True, "function": "build_tic_message"}, "Default TIC v2.164e response builder"),
        ("BAOBAB_AUTH_RULES", "POSRESPONSECONTROLFUNCTION", {"enabled": True, "include_f105_balance": True}, "Controls response code mapping and F105 balance output"),
    ]
    for grp, name, val, desc in host_params:
        db.add(HostParameter(parameter_group=grp, parameter_name=name, parameter_value=val, description=desc))

    # 3. Network Profile (Internal Simulation Only)
# [PATCH step11:seed_network_scheme_adapters]
    additional_networks = [
        ('VISA_SCHEME', 'CARD_SCHEME', 'ALWAYS_APPROVE', '00'),
        ('MASTERCARD_SCHEME', 'CARD_SCHEME', 'ALWAYS_APPROVE', '00'),
        ('NPSB_NATIONAL_SWITCH', 'NATIONAL_SWITCH', 'ALWAYS_APPROVE', '00'),
    ]
    for net_name, net_type, sim_m, sim_rc in additional_networks:
        if not db.query(NetworkProfile).filter(NetworkProfile.network_name == net_name).first():
            db.add(NetworkProfile(network_name=net_name, network_type=net_type, simulation_mode=sim_m, simulated_response_code=sim_rc, enabled=True))

    db.add(
        NetworkProfile(
            network_name="INTERNAL_SIMULATOR_TIC",
            network_type="INTERNAL_SIMULATION",
            enabled=True,
            configuration_json={"protocol": "Compass Plus TW TIC/TCI v2.164e", "live_external_connections": False},
        )
    )

    # 4. HSM Key References (Metadata & KVC only)
    hsm_keys = [
        ("Interchange ZMK", "ZMK", "ZONE_MASTER_KEY", "ZMK_MAIN", "000", "U0123456789ABCDEF0123456789ABCDEF"),
        ("POS Terminal Master Key", "TMK", "TERMINAL_MASTER_KEY", "TMK_POS_01", "002", "UFEDCBA9876543210FEDCBA9876543210"),
        ("Acquirer Working Key (ZPK/TPK)", "AWK", "PIN_ENCRYPTION_ACQUIRER", "AWK_ATM_01", "001", "U1A2B3C4D5E6F70811A2B3C4D5E6F7081"),
        ("Issuer Working Key (Outward ZPK)", "IWK", "PIN_ENCRYPTION_ISSUER", "IWK_SW_01", "001", "U89ABCDEF0123456789ABCDEF01234567"),
        ("Issuer PIN Verification Key", "PVK", "VISA_PVV_IBM3624", "PVK_VISA_01", "008", "U5566778899AABBCC5566778899AABBCC"),
        ("Card Verification Key", "CVK", "CVV1_CVV2_ICVV", "CVK_MAIN_01", "008", "U5566778899AABBCC5566778899AABBCC"),
        ("Terminal Auth MAC Key", "TAK", "RETAIL_MAC_ISO9797", "TAK_MAC_01", "003", "U8899AABBCCDDEEFF8899AABBCCDDEEFF"),
        ("EMV Master Key AC", "MK-AC", "EMV_ARQC_ARPC", "MK_AC_EMV01", "109", "UAABBCCDDEEFF00112233445566778899"),
    ]
    for kname, ktype, kusage, kid, _, lmk_ref in hsm_keys:
        clear = SoftHsmCryptoCore.INTERNAL_CLEAR_KEYS[kid]
        kvc = SoftHsmCryptoCore.calculate_kcv(clear)
        db.add(
            HsmKeyReference(
                key_name=kname,
                key_type=ktype,
                key_usage=kusage,
                key_identifier=kid,
                kvc=kvc,
                algorithm="3DES_2KEY",
                key_length=128,
# [PATCH step10:seed_clear_key_hex]
                clear_key_hex=clear,
                hsm_key_reference=f"LMK_PROTECTED_REF::{kid}::{lmk_ref[:10]}...",
                key_status="ACTIVE",
# [PATCH step02_01:seed_hsm_key_inst_arg]
                institution_id=xbank_id,
                processing_system_id=itcl_id,
            )
        )

# [PATCH step02_01:seed_backfill_existing]
    # Backfill Step 2 institution links on pre-existing records
    xbank_rec = db.query(Institution).filter(Institution.institution_code == 'XBANK').first()
    itcl_rec = db.query(ProcessingSystem).filter(ProcessingSystem.ps_code == 'ITCL').first()
    if xbank_rec:
        db.query(Customer).filter(Customer.institution_id.is_(None)).update({'institution_id': xbank_rec.id}, synchronize_session=False)
        db.query(Account).filter(Account.institution_id.is_(None)).update({'institution_id': xbank_rec.id}, synchronize_session=False)
        db.query(Card).filter(Card.institution_id.is_(None)).update({'institution_id': xbank_rec.id}, synchronize_session=False)
        if itcl_rec:
            db.query(HsmKeyReference).filter(HsmKeyReference.institution_id.is_(None)).update({'institution_id': xbank_rec.id, 'processing_system_id': itcl_rec.id}, synchronize_session=False)
        db.commit()

    # 5. Configurable Transaction Codes (10, 20, 30, 40)
    tx_codes = [
        ("10", "Configurable Transaction 10 (Default Debit/Withdrawal)", "Operator-configurable financial debit rule set", "FINANCIAL", "0100000", "0200", True, False, True, False, True, True),
        ("20", "Configurable Transaction 20 (Default Credit/Deposit)", "Operator-configurable financial credit rule set", "FINANCIAL", "0200000", "0200", True, False, False, True, False, False),
        ("30", "Configurable Transaction 30 (Default Balance Inquiry)", "Operator-configurable non-financial inquiry rule set", "INQUIRY", "0300000", "0100", False, True, False, False, True, True),
        ("40", "Configurable Transaction 40 (Default Transfer/POS)", "Operator-configurable transfer or purchase rule set", "FINANCIAL", "0400000", "0200", True, False, True, False, True, True),
    ]
    default_fields = [
        (2, "PAN", True, 1),
        (3, "Processing Code", True, 2),
        (4, "Transaction Amount", True, 3),
        (7, "GMT Transmission Time", False, 4),
        (11, "STAN", True, 5),
        (12, "Local Transaction Time", False, 6),
        (13, "Local Transaction Date", False, 7),
        (14, "Expiration Date", False, 8),
        (18, "MCC / SIC", False, 9),
        (22, "POS Entry Mode", False, 10),
        (25, "POS Condition Code", False, 11),
        (32, "Acquiring Institution ID", False, 12),
        (37, "RRN", True, 13),
        (41, "Terminal ID", True, 14),
        (49, "Transaction Currency", True, 15),
        (52, "PIN Data", False, 16),
        (55, "ICC/EMV Data", False, 17),
        (64, "MAC", False, 18),
    ]
    for code, name, desc, cat, pcode, mti, fin, bal, deb, cred, pin_req, pvv_req in tx_codes:
        tc = TransactionCode(
            transaction_code=code,
            transaction_name=name,
            description=desc,
            transaction_category=cat,
            processing_code=pcode,
            default_mti=mti,
            financial_flag=fin,
            balance_inquiry_flag=bal,
            debit_flag=deb,
            credit_flag=cred,
            pin_required=pin_req,
            pvv_required=pvv_req,
        )
        db.add(tc)
        db.flush()
        for fnum, fname, req, order in default_fields:
            db.add(
                TransactionCodeField(
                    transaction_code_id=tc.id,
                    iso_field_number=fnum,
                    field_name=fname,
                    required=req,
                    editable=True,
                    enabled=True,
                    display_order=order,
                )
            )

    # 6. Card Profiles
    prof_std = CardProfile(
        profile_code="PROF_DOM_STD",
        profile_name="Domestic Standard Debit Profile",
        card_product="VISA_DEBIT_CLASSIC",
        domestic_enabled=True,
        international_enabled=False,
        ecommerce_enabled=True,
        contactless_enabled=True,
        cash_enabled=True,
    )
    prof_vip = CardProfile(
        profile_code="PROF_INTL_GOLD",
        profile_name="International Gold Multi-Channel Profile",
        card_product="VISA_GOLD",
        domestic_enabled=True,
        international_enabled=True,
        ecommerce_enabled=True,
        contactless_enabled=True,
        cash_enabled=True,
    )
    db.add_all([prof_std, prof_vip])
    db.flush()

    # 7. 5 Customers, 5 Accounts, 5 Synthetic Cards
    synthetic_customers = [
        ("CUST-1001", "Tariq", "Rahman", "tariq.r@example.test", "+8801700000001", "ACTIVE", "1001000001", Decimal("150000.00"), "4567890123450001", "ACTIVE", prof_std.id),
        ("CUST-1002", "Nusrat", "Jahan", "nusrat.j@example.test", "+8801700000002", "ACTIVE", "1001000002", Decimal("4500.00"), "4567890123450002", "ACTIVE", prof_std.id),
        ("CUST-1003", "Tanvir", "Ahmed", "tanvir.a@example.test", "+8801700000003", "ACTIVE", "1001000003", Decimal("85000.00"), "4567890123450003", "BLOCKED", prof_std.id),
        ("CUST-1004", "Farhana", "Karim", "farhana.k@example.test", "+8801700000004", "ACTIVE", "1001000004", Decimal("520000.00"), "4567890123450004", "ACTIVE", prof_vip.id),
        ("CUST-1005", "Sajid", "Hossain", "sajid.h@example.test", "+8801700000005", "ACTIVE", "1001000005", Decimal("62000.00"), "4567890123450005", "ACTIVE", prof_std.id),
    ]

    _, pvk_clear = ("PVK_VISA_01", SoftHsmCryptoCore.INTERNAL_CLEAR_KEYS["PVK_VISA_01"])
# [PATCH step02_01:seed_link_existing_entities]
    xbank = db.query(Institution).filter(Institution.institution_code == 'XBANK').first()
    xbank_id = xbank.id if xbank else None
    itcl_ps = db.query(ProcessingSystem).filter(ProcessingSystem.ps_code == 'ITCL').first()
    itcl_id = itcl_ps.id if itcl_ps else None

    for c_num, fname, lname, email, mob, c_stat, a_num, bal, pan, card_stat, prof_id in synthetic_customers:
        cust = Customer(
            customer_number=c_num,
            first_name=fname,
            last_name=lname,
            date_of_birth=date(1992, 5, 15),
            email=email,
            mobile_number=mob,
            address="Dhaka, Bangladesh (Synthetic Test Record)",
            customer_status=c_stat,
# [PATCH step02_01:seed_customer_inst_arg]
            institution_id=xbank_id,
        )
        db.add(cust)
        db.flush()

        acct = Account(
            account_number=a_num,
            customer_id=cust.id,
            account_type="SAVINGS",
            currency="BDT",
            available_balance=bal,
            ledger_balance=bal,
            overdraft_limit=Decimal("0.00"),
            account_status="ACTIVE",
# [PATCH step02_01:seed_account_inst_arg]
            institution_id=xbank_id,
        )
        db.add(acct)
        db.flush()

        db.add(AccountLimit(account_id=acct.id, currency="BDT"))

        card = Card(
            customer_id=cust.id,
            card_number_token=tokenize_pan(pan),
            test_pan_reference=pan,
            masked_pan=mask_pan(pan),
            cardholder_name=f"{fname} {lname}".upper(),
            expiry_month=12,
            expiry_year=2028,
            card_type="DEBIT",
            card_product="VISA_DEBIT_CLASSIC",
            card_status=card_stat,
            issue_date=date(2025, 1, 1),
            activation_date=date(2025, 1, 2),
            linked_account_id=acct.id,
            card_profile_id=prof_id,
# [PATCH step02_01:seed_card_inst_arg]
            institution_id=xbank_id,
        )
        db.add(card)
        db.flush()

        db.add(CardAccount(card_id=card.id, account_id=acct.id, account_role="PRIMARY", currency="BDT", priority=1))
        db.add(CardLimit(card_id=card.id, profile_id=prof_id, currency="BDT"))

        # Calculate exact Visa PVV for test PIN "1234" so HSM verification is 100% real
        pvv_for_1234 = SoftHsmCryptoCore.calculate_visa_pvv(pan, "1234", "1", pvk_clear)
        db.add(
            PinProfile(
                card_id=card.id,
                pin_verification_method="VISA_PVV",
                pvk_key_reference="PVK_VISA_01",
                pin_offset_reference=pvv_for_1234,
                pvki="1",
                cvv_reference="011",
                pin_block_format="ISO_0",
            )
        )
        db.add(
            EmvProfile(
                card_id=card.id,
                application_profile="EMV_2000_CVN10",
                aid="A0000000031010",
                card_sequence_number="01",
                cryptogram_profile="ARPC_METHOD_1",
                master_key_reference="MK_AC_EMV01",
            )
        )

    db.commit()
    try:
        from app.lmk_key_management_service import LMKKeyManagementService
        LMKKeyManagementService(db).seed_fallback_external_keys()
    except Exception:
        logger.exception("Failed to seed fallback external HSM keys at startup")

# [PATCH step01_01:seed_ps_and_institutions_fn]
def seed_processing_systems_and_institutions(db: Session) -> None:
    """
    Idempotently seeds:
      1. Processing Systems: ITCL (default), VISA, MASTERCARD, NPSB, INTERNAL
      2. Initial Banks (all assigned to ITCL): xBank, yBank, zBank
      3. Institution-to-Processing-System participation records (all initial banks -> ITCL)
      4. Sample BIN Ranges mapped to xBank, yBank, zBank under ITCL
    Safe to run on every startup, including existing databases.
    """
    from app.models import (
        BinRange,
        Institution,
        InstitutionProcessingSystem,
        ProcessingSystem,
    )

    ps_definitions = [
        (
            "ITCL",
            "Information Technology Consultants Ltd (QCash Host Switch)",
            "HOST_SWITCH",
            "TIC_V2164E",
            True,
            True,
            {
                "protocol": "Compass Plus TW TIC/TCI v2.164e",
                "country": "BD",
                "default_currency": "BDT",
                "header_h1": "A4M",
                "settlement_cutover": "23:59",
            },
        ),
        (
            "VISA",
            "VisaNet / Visa Clearing Exchange (VCX)",
            "CARD_SCHEME",
            "ISO8583_1987",
            True,
            False,
            {
                "protocol": "ISO 8583:1987 VIP",
                "default_currency": "USD",
                "network_id": "0002",
            },
        ),
        (
            "MASTERCARD",
            "Mastercard Banknet / MDS",
            "CARD_SCHEME",
            "ISO8583_1987",
            True,
            False,
            {
                "protocol": "ISO 8583:1987 CIS/MDS",
                "default_currency": "USD",
                "network_id": "0003",
            },
        ),
        (
            "NPSB",
            "National Payment Switch Bangladesh (Bangladesh Bank)",
            "NATIONAL_SWITCH",
            "ISO8583_1987",
            True,
            False,
            {
                "protocol": "ISO 8583:1987 NPSB",
                "country": "BD",
                "default_currency": "BDT",
                "network_id": "0050",
            },
        ),
        (
            "INTERNAL",
            "BAOBAB Internal Host Loopback",
            "INTERNAL",
            "TIC_V2164E",
            True,
            False,
            {
                "protocol": "INTERNAL_LOOPBACK",
                "default_currency": "BDT",
            },
        ),
    ]

    ps_map = {}
    for code, name, stype, fmt, enabled, is_def, cfg in ps_definitions:
        existing_ps = db.query(ProcessingSystem).filter(ProcessingSystem.ps_code == code).first()
        if not existing_ps:
            existing_ps = ProcessingSystem(
                ps_code=code,
                name=name,
                system_type=stype,
                message_format=fmt,
                enabled=enabled,
                is_default=is_def,
                configuration=cfg,
            )
            db.add(existing_ps)
            db.flush()
        ps_map[code] = existing_ps

    itcl_ps = ps_map["ITCL"]

    # Seed initial banks (xBank, yBank, zBank) — all strictly assigned to ITCL
    bank_definitions = [
        ("XBANK", "xBank PLC", "xBank", "123456", "123456", "BOTH", "SETL-XBANK-001"),
        ("YBANK", "yBank Limited", "yBank", "223456", "223456", "BOTH", "SETL-YBANK-002"),
        ("ZBANK", "zBank Commercial PLC", "zBank", "323456", "323456", "BOTH", "SETL-ZBANK-003"),
    ]

    inst_map = {}
    for icode, iname, short, acq_id, fwd_id, role, setl_acct in bank_definitions:
        inst = db.query(Institution).filter(Institution.institution_code == icode).first()
        if not inst:
            inst = Institution(
                institution_code=icode,
                name=iname,
                short_name=short,
                acquirer_id=acq_id,
                forwarding_id=fwd_id,
                role=role,
                processing_system_id=itcl_ps.id,
                country_code="050",
                currency="BDT",
                settlement_account_number=setl_acct,
                status="ACTIVE",
                configuration={"on_us_host": "ITCL", "stand_in_enabled": True},
            )
            db.add(inst)
            db.flush()
        inst_map[icode] = inst

        # Ensure primary ITCL participation link exists in institution_processing_systems
        link = (
            db.query(InstitutionProcessingSystem)
            .filter(
                InstitutionProcessingSystem.institution_id == inst.id,
                InstitutionProcessingSystem.processing_system_id == itcl_ps.id,
            )
            .first()
        )
        if not link:
            db.add(
                InstitutionProcessingSystem(
                    institution_id=inst.id,
                    processing_system_id=itcl_ps.id,
                    member_id=f"ITCL-{icode}",
                    acquirer_id=acq_id,
                    network_identifier="ITCL_QCSH",
                    issuer_enabled=True,
                    acquirer_enabled=True,
                    message_format="TIC_V2164E",
                    routing_configuration={"priority": 1, "is_primary_host": True},
                    status="ACTIVE",
                )
            )
            db.flush()

    # Seed sample BIN ranges under ITCL
    # Note: 456789 matches existing seeded cards (4567890123450001..0005)
    bin_definitions = [
        ("456789", "4567890000000000", "4567899999999999", 16, "XBANK", "DEBIT", "VISA_DEBIT_CLASSIC", "ITCL", True),
        ("456790", "4567900000000000", "4567909999999999", 16, "XBANK", "CREDIT", "VISA_GOLD_CREDIT", "ITCL", True),
        ("512345", "5123450000000000", "5123459999999999", 16, "YBANK", "DEBIT", "MC_DEBIT_STANDARD", "ITCL", True),
        ("489012", "4890120000000000", "4890129999999999", 16, "ZBANK", "DEBIT", "QCASH_PROPRIETARY_DEBIT", "ITCL", True),
    ]

# [PATCH seed_pan_routing_rules_and_clean_bank_names]
    # Seed initial PAN routing rules idempotently if PanRoutingRule exists
    try:
        from app.models import PanRoutingRule
        default_routes = [
            ("RT-XBANK-VISA-DEB", "xBank Visa Debit On-Us Route", 10, "456789", "4567890000000000", "4567899999999999", 16, "DEBIT", "XBANK", "ITCL", "INTERNAL_SIMULATOR_TIC", "ITCL", True, False),
            ("RT-XBANK-VISA-CRD", "xBank Visa Gold Credit On-Us Route", 20, "456790", "4567900000000000", "4567909999999999", 16, "CREDIT", "XBANK", "ITCL", "INTERNAL_SIMULATOR_TIC", "ITCL", True, False),
            ("RT-YBANK-MC-DEB", "yBank Mastercard Debit Switch Route", 30, "512345", "5123450000000000", "5123459999999999", 16, "DEBIT", "YBANK", "ITCL", "INTERNAL_SIMULATOR_TIC", "ITCL", True, True),
            ("RT-ZBANK-QCASH-DEB", "zBank QCash Proprietary Route", 40, "489012", "4890120000000000", "4890129999999999", 16, "DEBIT", "ZBANK", "ITCL", "INTERNAL_SIMULATOR_TIC", "ITCL", True, True),
        ]
        for rcode, rname, prio, pfx, low, high, plen, ctype, icode, pscode, net, scheme, on_us, pin_tr in default_routes:
            if not db.query(PanRoutingRule).filter(PanRoutingRule.rule_code == rcode).first():
                if icode in inst_map and pscode in ps_map:
                    db.add(
                        PanRoutingRule(
                            rule_code=rcode,
                            rule_name=rname,
                            description=f"Default seeded PAN routing rule for {pfx}",
                            priority=prio,
                            pan_prefix=pfx,
                            pan_low=low,
                            pan_high=high,
                            pan_length=plen,
                            card_type=ctype,
                            issuer_institution_id=inst_map[icode].id,
                            processing_system_id=ps_map[pscode].id,
                            destination_network=net,
                            scheme=scheme,
                            is_on_us=on_us,
                            pin_translation_required=pin_tr,
                            enabled=True,
                            status="ACTIVE",
                        )
                    )
        # Also clean any legacy composite short_name values like "BAL - IFIC" or "TBL - IFIC"
        for inst_obj in db.query(Institution).all():
            for field_attr in ("institution_code", "short_name"):
                val = getattr(inst_obj, field_attr, None)
                if val and (" - " in val or " — " in val):
                    clean_code = val.split(" - ")[0].split(" — ")[0].strip()
                    if field_attr == "short_name":
                        inst_obj.short_name = clean_code
    except Exception:
        pass
    for prefix, low, high, plen, icode, ctype, prod, scheme, on_us in bin_definitions:
        existing_bin = db.query(BinRange).filter(BinRange.bin_prefix == prefix).first()
        if not existing_bin and icode in inst_map:
            db.add(
                BinRange(
                    bin_prefix=prefix,
                    bin_low=low,
                    bin_high=high,
                    pan_length=plen,
                    institution_id=inst_map[icode].id,
                    processing_system_id=itcl_ps.id,
                    card_type=ctype,
                    card_product=prod,
                    scheme=scheme,
                    country_code="050",
                    currency="BDT",
                    is_on_us=on_us,
                    status="ACTIVE",
                )
            )

    db.commit()

