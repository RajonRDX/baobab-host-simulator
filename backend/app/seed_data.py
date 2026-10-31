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
    Card,
    CardAccount,
    CardLimit,
    CardProfile,
    Customer,
    EmvProfile,
    HostParameter,
    HsmKeyReference,
    NetworkProfile,
    PinProfile,
    ResponseCode,
    TransactionCode,
    TransactionCodeField,
)
from app.security import mask_pan, tokenize_pan


def seed_initial_data(db: Session) -> None:
    if db.query(Customer).count() > 0:
        return

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
                hsm_key_reference=f"LMK_PROTECTED_REF::{kid}::{lmk_ref[:10]}...",
                key_status="ACTIVE",
            )
        )

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
