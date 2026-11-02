"""
tic_decoder_engine.py — Integrated Compass Plus TW TIC/TCI v2.164e & ISO 8583:1987 Decoder
Reuses the complete field definitions, lookup tables, subfield parsers (_pf3.._pf126, UAMP F123-F125),
and Excel/Text report formatters from `tic_decoder.py`, while enforcing strict payment-switch
security masking (PAN, PIN blocks, CVV/CVV2, Track 1/2, and secret keys).
"""

import io
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from app.iso_standard_codec import ISO8583_FIELDS, decode_iso8583_1987
from app.security import mask_pan

def strict_strict_mask_pan(pan: Optional[str]) -> str:
    """Always masks PAN as 123456******1234 by default, even when LOG_RAW_DATA=True."""
    if not pan:
        return "****"
    clean = "".join(ch for ch in str(pan) if ch.isdigit())
    if len(clean) >= 10:
        return f"{clean[:6]}{'*' * (len(clean) - 10)}{clean[-4:]}"
    if "*" in str(pan):
        return str(pan)
    return "****"


def strict_strict_strict_mask_pan(pan: Optional[str]) -> str:
    """Always masks PAN as 123456******1234 by default, even when LOG_RAW_DATA=True."""
    if not pan:
        return "****"
    clean = "".join(ch for ch in str(pan) if ch.isdigit())
    if len(clean) >= 10:
        return f"{clean[:6]}{'*' * (len(clean) - 10)}{clean[-4:]}"
    if "*" in str(pan):
        return str(pan)
    return "****"


try:
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

FIELD_DEFS: Dict[int, Tuple[str, str, str, Optional[int]]] = {
    2:   ("PAN",                           "N",   "LLVAR",     None),
    3:   ("Processing Code",               "N",   "FIXED",     7),
    4:   ("Transaction Amount",            "N",   "FIXED",     12),
    5:   ("Settlement Amount",             "N",   "FIXED",     12),
    6:   ("Cardholder Billing Amount",     "N",   "FIXED",     12),
    7:   ("GMT Transmission Time",         "N",   "FIXED",     10),
    8:   ("Billing Fee Amount",            "N",   "FIXED",     8),
    9:   ("Settlement Conv Rate",          "N",   "FIXED",     8),
    10:  ("Cardholder Billing Conv Rate",  "N",   "FIXED",     8),
    11:  ("STAN",                          "N",   "FIXED",     6),
    12:  ("Local Transaction Time",        "N",   "FIXED",     6),
    13:  ("Local Transaction Date",        "N",   "FIXED",     4),
    14:  ("Expiration Date",               "N",   "FIXED",     4),
    15:  ("Settlement Date",               "N",   "FIXED",     4),
    16:  ("Currency Conv Date",            "N",   "FIXED",     4),
    17:  ("Capture Date",                  "N",   "FIXED",     4),
    18:  ("MCC / SIC",                     "N",   "FIXED",     4),
    19:  ("Acquiring Country Code",        "N",   "FIXED",     3),
    20:  ("PAN Country Code",              "N",   "FIXED",     3),
    21:  ("Forwarding Country Code",       "N",   "FIXED",     3),
    22:  ("POS Entry Mode",                "N",   "FIXED",     3),
    23:  ("MBR (Card Seq No)",             "N",   "FIXED",     3),
    24:  ("Network Int Identifier",        "N",   "FIXED",     3),
    25:  ("POS Condition Code",            "N",   "FIXED",     3),
    26:  ("Message Reason Code",           "N",   "FIXED",     4),
    28:  ("Fee Amount",                    "ANS", "FIXED",     9),
    32:  ("Acquiring Institution ID",      "N",   "LLVAR",     None),
    33:  ("Forwarding Institution ID",     "N",   "LLVAR",     None),
    35:  ("Track 2 Data",                  "ANS", "LLVAR",     None),
    37:  ("RRN",                           "ANS", "FIXED",     12),
    38:  ("Approval Code",                 "ANS", "FIXED",     6),
    39:  ("Response Code",                 "N",   "FIXED",     5),
    41:  ("Terminal ID",                   "ANS", "LLVAR",     None),
    43:  ("Terminal Name/Location",        "ANS", "FIXED",     222),
    44:  ("PIN/CVV Verification Result",   "ANS", "FIXED",     2),
    45:  ("Track 1 Data",                  "ANS", "LLVAR",     None),
    48:  ("Reference to Other Tran",       "ANS", "FIXED",     31),
    49:  ("Transaction Currency",          "N",   "FIXED",     3),
    51:  ("Cardholder Billing Currency",   "N",   "FIXED",     3),
    52:  ("PIN",                           "HEX", "FIXED",     16),
    53:  ("Security Control Info",         "b",   "FIXED",     48),
    54:  ("Adjustment Amount",             "N",   "FIXED",     12),
    55:  ("ICC System Related Data",       "b",   "LLLVAR",    None),
    61:  ("Card Issuer Data",              "ANS", "FIXED",     14),
    62:  ("External Tran Attributes",      "ANS", "LLLVAR",    None),
    63:  ("New PIN",                       "HEX", "FIXED",     16),
    64:  ("MAC",                           "HEX", "FIXED",     16),
    70:  ("Network Mgmt Info Code",        "N",   "FIXED",     3),
    95:  ("Replacement Amounts",           "N",   "FIXED",     24),
    100: ("Receiving Institution ID",      "N",   "LLVAR",     None),
    102: ("Account ID 1 (FROM)",           "ANS", "LLVAR",     None),
    103: ("Account ID 2 (TO)",             "ANS", "LLVAR",     None),
    104: ("Host Net Identification",       "ANS", "FIXED",     4),
    105: ("Account Balance Data",          "N",   "FIXED",     25),
    106: ("Multi Currency Data",           "N",   "FIXED",     46),
    107: ("Final RRN",                     "ANS", "FIXED",     12),
    108: ("Regional Listing / String Msg", "ANS", "LLLVAR",    None),
    109: ("Multi Account Data",            "ANS", "LLLVAR",    None),
    110: ("Numeric Message",               "N",   "LVAR",      None),
    111: ("Account Identification 2",      "ANS", "LLVAR",     None),
    114: ("Mini-Statement Data",           "ANS", "LLLVAR",    None),
    115: ("Statement Data",                "ANS", "PLLLLLVAR", None),
    116: ("Billing Data",                  "ANS", "LLLLLVAR",  None),
    121: ("Additional POS Data",           "ANS", "FIXED",     47),
    122: ("3D-Secure Data",                "ANS", "FIXED",     48),
    123: ("Misc Tran Attributes",          "ANS", "LLLVAR",    None),
    124: ("Misc Tran Attributes 2",        "ANS", "LLLLLVAR",  None),
    125: ("Administrative Tran Data",      "ANS", "LLLLLVAR",  None),
    126: ("Pre-auth Parameters",           "ANS", "FIXED",     34),
    127: ("Additional Information",        "ANS", "LLLLLVAR",  None),
    128: ("Secondary MAC",                 "HEX", "FIXED",     16),
}

TRAN_CODES = {
    "010":"ATM Withdrawal","020":"ATM Deposit","022":"ATM Change EC Status",
    "026":"ATM Get Account","027":"ATM Cheque Deposit","030":"ATM Balance Inquiry",
    "031":"ATM Transfer Data Inquiry","040":"ATM Transfer","041":"ATM Transfer Pass",
    "042":"ATM Transfer Debit","043":"ATM Transfer Credit","046":"ATM P2P Pass",
    "050":"ATM Payment","051":"ATM Payment Pass","052":"ATM Payment Debit",
    "053":"ATM Payment Credit","054":"ATM Cash Payment","055":"ATM Bills Request",
    "058":"ATM Payment Return","059":"ATM Cash Payment Pass","060":"ATM Message to FI",
    "062":"ATM PrepaidCode","063":"ATM P2P Debit","064":"ATM P2P Credit",
    "065":"ATM P2P Transfer","066":"ATM Precheck","067":"ATM Confirmation",
    "068":"ATM Payment Request","070":"ATM Statement Print","071":"ATM Mini-Statement Print",
    "072":"ATM Card Statement","081":"ATM PIN Change","082":"ATM Internet PIN Change",
    "083":"ATM Link Auth Card to Telebank Customer","084":"ATM Link Card to Telebank Customer",
    "085":"ATM Create Virtual Card","086":"ATM Telebank PIN Change","087":"ATM PIN Unblock",
    "089":"ATM Create Telebank Customer","090":"ATM Check PIN for Admin Card",
    "108":"ATM Service Auto Payment","420":"ATM Cardless Message",
    "110":"POS Purchase","111":"POS Pre-purchase","112":"POS Pre-purchase Complete",
    "113":"POS Mail/Phone Order","114":"POS Merchandise Return","115":"POS Cash Advance",
    "116":"POS Card Verification","117":"POS Balance Inquiry","118":"POS Purchase with Cashback",
    "121":"POS Purchase Adjustment","122":"POS Merchandise Return Adjustment",
    "123":"POS Cash Advance Adjustment","124":"POS Pre-purchase Increment",
    "125":"POS Purchase Cancellation","126":"POS Message to FI",
    "127":"POS Cardless Cash Advance","130":"POS Quasi-Cash","131":"POS PrepaidCode",
    "132":"POS P2P Debit","133":"POS P2P Credit","134":"POS P2P Calculate Fee",
    "135":"POS P2P Pass","136":"POS Installment Details","137":"POS Transfer",
    "138":"POS Mini-Statement Print","139":"POS PIN Change","140":"POS Deposit",
    "141":"POS Deposit Adjustment","142":"POS Payment","143":"POS Precheck",
    "144":"POS Confirmation","145":"POS Payment Request","147":"POS Transfer Debit",
    "148":"POS Transfer Credit","149":"POS Transfer Pass","162":"POS Close Day",
    "171":"POS Prepaid Pass","172":"POS Prepaid Debit","173":"POS Prepaid Credit",
    "175":"POS Payment Pass","176":"POS Payment Debit","177":"POS Payment Credit",
    "178":"POS Tokenization","179":"POS Send Dynamic Password",
    "180":"POS Transfer Data Inquiry","181":"POS Accumulate Bonus","182":"POS Redeem Bonus",
    "183":"POS Cash Payment","184":"POS Cash Payment Pass","185":"POS Calculate Fee",
    "188":"POS Tokenization Completion","189":"POS Tokenization Event",
    "192":"POS Transaction Confirmation","194":"POS Exchange Rate Inquiry",
    "196":"POS TC Advice","198":"POS Get Card by Alias","199":"POS Alias Action",
    "801":"POS Alias Action Pass","827":"POS ATC Update","832":"POS QR Purchase",
    "833":"POS QR Refund","834":"POS Get PIN","836":"POS C2C Pull Check",
    "837":"POS C2C Pull","838":"POS QR Purchase Debit","839":"POS QR Purchase Credit",
    "840":"POS QR Purchase Pass","841":"POS QR Actions","856":"POS EC Purchase",
    "857":"POS EC Refund",
    "201":"Debit Adjustment","202":"Credit Adjustment",
    "219":"Clearing Fund Balance Inquiry","220":"Add Card to Stoplist",
    "221":"Delete Card from Stoplist","222":"Modify Stoplist","223":"Inquiry Stoplist",
    "234":"PAR Inquiry","236":"Token Inquiry","237":"Update Card Metadata for Tokens",
    "303":"Telebank Operation History","336":"Telebank Create Virtual Card",
    "347":"Telebank Get BackOffice Info","351":"Telebank Transfer","352":"Telebank Payment",
    "353":"Telebank Prepaid Code","354":"Telebank Outside Transfer",
    "355":"Telebank P2P Debit","356":"Telebank P2P Credit","357":"Telebank Precheck",
    "358":"Telebank Confirmation","359":"Telebank Payment Request",
    "363":"Telebank Card Statement","368":"Telebank Transfer Pass",
    "369":"Telebank Transfer Debit","370":"Telebank Transfer Credit",
    "381":"Telebank P2P Pass","382":"Telebank Payment Pass","383":"Telebank Payment Debit",
    "384":"Telebank Payment Credit","385":"Telebank Prepaid Pass",
    "386":"Telebank Prepaid Debit","387":"Telebank Prepaid Credit",
    "601":"3DS Verify Enrollment","602":"3DS Payer Authentication",
    "603":"3DS Check Proxy PAN","604":"3DS Get Enrolled",
    "605":"3DS Get Dynamic Auth Address List","606":"3DS Add Abonent",
    "607":"3DS Update Abonent","611":"3DS Change Authentication Data",
    "621":"3DS Generate Dynamic Password","622":"3DS Change EC Status",
    "623":"3DS Prepare Authorization","624":"3DS Process Authorization",
    "625":"3DS Request External Authentication","626":"3DS Check External Authentication",
    "441":"Admin Receive Prepaid Code","443":"Admin Change EC Status",
    "591":"FIMI Get BackOffice Info","800":"FIMI Balance Inquiry",
    "701":"CMS Payment","703":"CMS Customer Messaging","751":"CMS Payment Debit",
    "752":"CMS Payment Credit","753":"CMS Payment Precheck","754":"CMS Payment Confirmation",
    "758":"CMS Payment Request","882":"IBFT / Internet Banking Fund Transfer",
    "999":"Extended (see S-123.ETC)",
}

ACCT_TYPES = {"00":"Unknown","01":"Checking","11":"Savings","31":"Credit","91":"Bonus"}

POS_ENTRY_MODES = {
    "00":"Unknown / no terminal","01":"Manual key entry",
    "02":"Mag stripe – CVV not reliable","03":"Consumer-presented QR",
    "04":"Optical character reader","05":"ICC chip – CVV reliable",
    "07":"Contactless EMV","09":"eCommerce Chip",
    "90":"Mag stripe – CVV reliable","91":"Contactless mag stripe","95":"ICC – CVV unreliable",
}

PIN_CAP = {"0":"Unknown","1":"Can accept PIN","2":"Cannot accept PIN","8":"PIN pad down"}

POS_CONDITION_CODES = {
    "0":"Normal","1":"Customer not present","2":"Unattended CAT","3":"Merchant suspicious",
    "5":"Customer present – card not present","8":"Mail/phone order",
    "10":"Customer identity verified","11":"Normal – with Bonuses","13":"Representment",
    "17":"Chargeback","51":"Verification only","52":"Recurring payment",
    "53":"Installment payment","54":"Chargeback reversal","59":"VSEC public network",
    "60":"Recurring – Secure Attempt","61":"Recurring – Secure VSEC",
    "62":"Recurring – Non-secure VSEC","63":"Recurring – EMV chip",
    "64":"Installment – Secure Attempt","65":"Installment – Secure VSEC",
    "66":"Installment – Non-secure VSEC","67":"Installment – EMV chip",
    "71":"Referral","72":"Hardware Crypto Customer Auth","73":"Software Crypto Customer Auth",
    "78":"Merchant Risk Based Decisioning","79":"Issuer Risk Based Decisioning",
    "81":"3DS Supported by acquirer only","82":"3DS","83":"Non-auth SET chip cryptogram",
    "84":"Secure SET chip cryptogram","85":"Secure SET with certificate",
    "86":"Non-auth SET without certificate","87":"Channel encrypted VSEC",
    "88":"Non-secure VSEC","89":"Channel encrypted VSEC chip cryptogram",
    "91":"EMV chip transaction","92":"EMV chip – with Bonuses",
}

TERM_CLASS = {"001":"ATM","002":"POS","003":"CRT","004":"TELEBANK"}

RESPONSE_CODES = {
    "00":"Approved","01":"Approved","02":"Partially approved","03":"Purchase only approved",
    "04":"Postponed","05":"Do not honor","06":"Strong customer authentication required",
    "10":"Should select account number","11":"Should change PVV","12":"Invalid transaction",
    "13":"Invalid amount / Select bill","14":"Invalid card number / Customer confirmation",
    "15":"Original transaction not found","22":"Acquirer limit exceeded","29":"Closed account",
    "30":"Format error / Blocked","40":"Lost card","41":"Stolen card",
    "49":"Ineligible vendor account","50":"Unauthorized usage","51":"Insufficient funds / Expired card",
    "52":"Invalid card","53":"Invalid PIN","54":"Expired card / System error",
    "55":"Incorrect PIN / Ineligible transaction","56":"Ineligible account",
    "57":"Transaction not permitted","58":"Restricted card","59":"Insufficient funds",
    "60":"Uses limit exceeded","61":"Exceeds withdrawal/transaction limit",
    "62":"PIN tries limit reached","63":"Withdrawal limit already reached",
    "64":"Credit amount limit","65":"No statement info","66":"Statement not available",
    "67":"Invalid amount","68":"External decline","69":"No sharing",
    "71":"Contact card issuer","72":"Destination not available","73":"Routing error",
    "74":"Format error","75":"External decline special","80":"Bad CVV","81":"Bad CVV2",
    "82":"Invalid transaction","83":"PIN tries was exceeded","84":"Bad CAVV",
    "85":"Bad ARQC","91":"Issuer or switch inoperative","94":"Duplicate transmission",
    "96":"Approved frictionless","97":"Inquiry only","98":"Invalid merchant",
}

RETAIN_CARD = {
    "0":"Normal","1":"Retain card","2":"Honour with identification","3":"TC advice requested"
}

MTI_NAMES = {
    "0100":"Authorization Request","0110":"Authorization Response",
    "0103":"Balance / Preauthorization Request","0113":"Balance / Preauthorization Response",
    "0104":"Postauthorization Request","0114":"Postauthorization Response",
    "0200":"Financial Transaction Request","0203":"Financial Preauthorization Request",
    "0204":"Financial Postauthorization Request",
    "0210":"Financial Transaction Response","0213":"Financial Preauthorization Response",
    "0214":"Financial Postauthorization Response",
    "0120":"Authorization Advice","0130":"Authorization Advice Response",
    "0220":"Financial Advice / Representment / Adjustment Advice",
    "0230":"Financial Advice Response",
    "0320":"Batch Upload Advice","0330":"Batch Upload Advice Response",
    "0400":"Acquirer Reversal Request","0410":"Acquirer Reversal Response",
    "0420":"Acquirer Reversal Advice","0430":"Acquirer Reversal Advice Response",
    "0422":"Stoplist / Change Token Status / Chargeback",
    "0432":"Stoplist / Change Token Status / Chargeback Response",
    "0600":"Administrative Request","0610":"Administrative Response",
    "0620":"Administrative Advice","0630":"Administrative Advice Response",
    "0800":"Network Management Request","0810":"Network Management Response",
}

NETWORK_MGMT_CODES = {
    "001":"Logon","002":"Logoff","003":"Cutover offline (TCI)",
    "004":"Inquiry mode (TCI)","101":"PIN Working Key Change","301":"Echo test",
}

HOST_NET_IDS = {"VISA":"Visa","EP":"Mastercard Europe","MC":"Mastercard Global",
                "AMEX":"American Express","UPI":"UPI"}

UAMP_F123_NAMES = {
    "CR":"CAVV Verification Result","MP":"Terminal Max PIN Number",
    "TC":"Terminal Entry Capabilities","CC":"Terminal Contactless Capable",
    "SPA":"Terminal Support Partial Auth","TD":"To Date","FD":"From Date",
    "IF":"Issuer Fee","AF":"Actual Fee","AIF":"Actual Issuer Fee",
    "AA":"Actual Amount in Account Currency","ICO":"ICC Card Auth Result",
    "IC":"Issuer Country Code","IB":"Issuer Card Brand",
    "SA":"Settlement Amount","SC":"Settlement Currency","SD":"Settlement Date",
    "P2":"Another PAN","CM2":"Another Card Member No","RC":"ICC Response Code",
    "TL":"Terminal Language","TLC":"Terminal Language Alpha2","PD":"P2P Sender Data",
    "ER":"External PS RRN","ET":"External Transaction Number","DR":"Debit RRN",
    "ERN":"External Retailer Name","BAI":"Business Application Identifier",
    "ETC":"Extended Transaction Code","TID":"Transaction ID / Trace ID",
    "TCE":"Terminal Entry Caps Extended","ERR":"Error Code",
    "NP":"New PVV for PIN Change","PVT":"PIN Verification Type",
    "CBA":"Cashback Amount","TIPA":"Tip Amount","FPI":"Fee Program Indicator",
    "DF":"DCC Fee","FPTTI":"Funding/Payment Transaction Type Indicator",
    "ETCD":"External Transaction Code","ETCS":"External Terminal Class",
}

UAMP_F124_NAMES = {
    "DR":"Decline Reason","ART":"Authorizer Response Text",
    "EPS":"External Payment System Fields","ERC":"External Response Code",
    "TA2":"Account Identification 2","PC":"Prepaid Code","AL":"Account List",
    "CA":"Customer Address","AVR":"Address Verification Result",
    "DA":"Detail Addenda","AB":"Additional Balances","PF":"External Payment Gateway Fields",
    "IPS":"Incoming Payment System Fields","ID":"Transaction ID",
    "PRCNT":"Processing Count","DAE":"Detail Addenda Ext","IND":"Installment Data",
    "NII":"Network International Identifier","MPI":"Mobile POS Indicator",
    "PST":"POS Sender Type","EC":"3DS E-Commerce Data","OFPRL":"OFP Risk Level",
    "TAD":"Terminal Additional Data","AVID":"Avatar ID","AVDA":"Avatar Data",
    "AVIN":"Avatar Info","SME":"String Message Extended","ED":"External Description",
    "MD":"Merchant Data","TKN":"Token Data","HDI":"Host Data Internal",
    "DRC":"Detailed Response Code","C3DS":"3DS Transaction Conditions",
    "IFL":"Issuer Fee List","MVR":"Misc Verification Result","ADE":"Auth Data Ext",
    "DD":"Dispute Data","DCCREQ":"DCC Request","DCCRES":"DCC Response",
    "DCCCS":"DCC Conversion System","CPI":"Card Product ID","AP":"Auto Payment Data",
    "APH":"Auto Payment History","DTD":"Debit Transaction Data","UD":"User Data",
    "MTC":"Message to Cardholder","AED":"Additional Ecommerce Data","AD":"Alias Data",
    "EIS":"External Interface State","DI":"Device Information","CL":"Card List",
    "AA":"Additional Amounts","ITA":"Incoming Transaction Attributes",
    "TAXID":"Card Acceptor Tax ID","OTL":"Original Transaction List","QRD":"QR-code Data",
    "AR3DS":"3DS Authentication Rules","CD":"Conversion Date","QRIMAGE":"QR-code Image",
    "OFPRD":"OFP Response Data","DCCREQID":"DCC Inquiry Identifier","PD":"P2P Sender Data",
    "FC":"Fee Calculated","GT":"Generation Time","TLCTN":"Terminal Location",
    "TBCI":"Telebank Card Info","SN":"POS Transaction Sequence Number",
    "ExtPAN":"External PAN","NW":"Network","RCC":"Response Code Category",
    "RD":"Recurring Data","RPK":"Remote PIN Key","EAMT":"Extra Large Amount",
    "EAMTACCT":"Extra Large Cardholder Billing Amount","AF":"Additional Fields",
    "RQRList":"QR Code List","MW":"Merchant Wallet Data","CCC":"Terminal Contactless Capable",
    "CAT":"CAT Level",
}

UAMP_F125_NAMES = {
    "TI":"Administrative Transaction Initiator","AH":"ATM Hoppers",
    "AC":"ATM Coins","ADV":"ATM Deposit Value","ACV":"ATM Cash Value",
}

SEP = chr(221)   # Ý
SSEP = chr(179)  # ³


def _unescape(s: str) -> str:
    return re.sub(r"\\x([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), s)


def _decode_bitmap(hex_str: str) -> Tuple[List[int], str]:
    bits = bin(int(hex_str, 16))[2:].zfill(len(hex_str) * 4)
    return [i + 1 for i, b in enumerate(bits) if b == "1"], bits


def _read_bitmap(msg: str, pos: int) -> Tuple[List[int], str, Optional[str], str, int]:
    ph = msg[pos : pos + 16]
    pos += 16
    if bin(int(ph, 16))[2:].zfill(64)[0] == "1":
        sh = msg[pos : pos + 16]
        pos += 16
        fh = ph + sh
    else:
        sh = None
        fh = ph
    fields, bits = _decode_bitmap(fh)
    # Field 1 is secondary bitmap indicator, never returned as a regular data field
    fields = [f for f in fields if f != 1]
    return fields, ph, sh, bits, pos


def _read_field(msg: str, pos: int, fnum: int) -> Tuple[str, int]:
    if fnum not in FIELD_DEFS:
        raise ValueError(f"Unsupported TIC field number: F{fnum}")
    _, _, lt, fl = FIELD_DEFS[fnum]
    if lt == "FIXED":
        if pos + fl > len(msg):
            raise ValueError(f"Field F{fnum} truncated (expected {fl} chars, got {len(msg) - pos})")
        return msg[pos : pos + fl], pos + fl
    if lt == "LVAR":
        l = int(msg[pos : pos + 1]); pos += 1; return msg[pos : pos + l], pos + l
    if lt == "LLVAR":
        l = int(msg[pos : pos + 2]); pos += 2; return msg[pos : pos + l], pos + l
    if lt == "LLLVAR":
        l = int(msg[pos : pos + 3]); pos += 3; return msg[pos : pos + l], pos + l
    if lt == "LLLLLVAR":
        l = int(msg[pos : pos + 5]); pos += 5; return msg[pos : pos + l], pos + l
    if lt == "PLLLLLVAR":
        l = int(msg[pos + 1 : pos + 5]) if msg[pos : pos + 1] == "0" else int(msg[pos : pos + 5])
        pos += 5
        return msg[pos : pos + l], pos + l
    raise ValueError(f"Unhandled length type {lt}")


def _pf3(v: str):
    tc = v[0:3]; fa = v[3:5]; ta = v[5:7]
    detail = {
        "F3.1 Transaction Code":  f"{tc} — {TRAN_CODES.get(tc, 'Configurable / Custom')}",
        "F3.2 From Account Type": f"{fa} — {ACCT_TYPES.get(fa, 'Unknown')}",
        "F3.3 To Account Type":   f"{ta} — {ACCT_TYPES.get(ta, 'Unknown')}",
    }
    return detail, {"F3.1": tc, "F3.2": fa, "F3.3": ta}


def _pf22(v: str):
    ce = v[0:2]; pc = v[2:3] if len(v) >= 3 else "?"
    detail = {
        "F22.1 Card Entry Mode": f"{ce} — {POS_ENTRY_MODES.get(ce, 'Unknown')}",
        "F22.2 PIN Capability":  f"{pc} — {PIN_CAP.get(pc, 'Unknown')}",
    }
    return detail, {"F22": v}


def _pf25(v: str):
    code = v.strip().lstrip("0") or "0"
    return {"F25.1 POS Condition": f"{v} — {POS_CONDITION_CODES.get(code, 'Unknown')}"}, {"F25": v}


def _pf28(v: str):
    dir_map = {"D": "Debit", "C": "Credit"}
    detail = {
        "F28.1 Direction": f"{v[0]} — {dir_map.get(v[0], '?')}",
        "F28.2 Amount": v[1:],
    }
    return detail, {"F28": v[1:]}


def _pf39(v: str):
    if len(v) == 5:
        retain = v[2]; rc = v[3:5]
        detail = {
            "F39.1 Retain Card Indicator": f"{retain} — {RETAIN_CARD.get(retain, 'Unknown')}",
            "F39.2 Response Code":         f"{rc} — {RESPONSE_CODES.get(rc, 'Unknown')}",
        }
        return detail, {"F39": v}
    rc = v.strip()[:2]
    return {"F39 Response Code": f"{rc} — {RESPONSE_CODES.get(rc, 'Unknown')}"}, {"F39": v}


def _pf43(v: str):
    subs = [
        ("F43.1", 30), ("F43.2", 30), ("F43.3", 3), ("F43.4", 3), ("F43.5", 30),
        ("F43.6", 30), ("F43.7", 30), ("F43.8", 3), ("F43.9", 8), ("F43.10", 10),
        ("F43.11", 4), ("F43.12", 25), ("F43.13", 3), ("F43.14", 9), ("F43.15", 4),
    ]
    labels = [
        "Terminal Owner", "Terminal City", "Terminal State", "Terminal Country",
        "Terminal Address", "Terminal Branch", "Terminal Region", "Terminal Class",
        "Terminal Date", "Terminal PS Name", "Terminal FI Name",
        "Terminal Retailer Name", "Terminal County", "Terminal ZIP Code",
        "Terminal Time Offset",
    ]
    detail = {}; compact = {}; ptr = 0
    for (key, w), label in zip(subs, labels):
        chunk = v[ptr : ptr + w]
        stripped = chunk.strip()
        if key == "F43.8" and stripped:
            detail[f"{key} {label}"] = f"{stripped} — {TERM_CLASS.get(stripped.zfill(3), 'Unknown')}"
        elif stripped:
            detail[f"{key} {label}"] = stripped
        compact[key] = chunk
        ptr += w
    if not detail:
        detail["Terminal Name/Location"] = v.strip()
    return detail, compact


def _pf44(v: str):
    vm = {"1": "OK", "0": "Failed", " ": "Not performed"}
    detail = {
        "F44.1 PIN Verification": f"{v[0:1]!r} — {vm.get(v[0:1], '?')}",
        "F44.2 CVV Verification": f"{v[1:2]!r} — {vm.get(v[1:2], '?')}",
    }
    return detail, {"F44": v}


def _pf48(v: str):
    other_pan = v[12:31].strip()
    detail = {
        "F48.1 Other RRN": v[0:12].strip(),
        "F48.2 Other PAN": strict_strict_mask_pan(other_pan) if other_pan else "",
    }
    return detail, {"F48": v[0:12] + (strict_strict_mask_pan(other_pan) if other_pan else "")}


def _pf61(v: str):
    detail = {"F61.1 Auth FI Name": v[0:4].strip(), "F61.2 Auth PS Name": v[4:14].strip()}
    return detail, {"F61.1": v[0:4], "F61.2": v[4:14]}


def _pf95(v: str):
    detail = {"S95.1 Replacement Amount": v[0:12], "S95.2 Replacement Original": v[12:24]}
    return detail, {"F95": v}


def _pf105(v: str):
    cm = {"1": "Account currency", "0": "Transaction currency"}
    led_raw = v[0:12]
    avl_raw = v[12:24]
    led_fmt = f"{int(led_raw)/100:,.2f}" if led_raw.isdigit() else led_raw
    avl_fmt = f"{int(avl_raw)/100:,.2f}" if avl_raw.isdigit() else avl_raw
    detail = {
        "S105.1 Ledger Balance": f"{led_raw} ({led_fmt})",
        "S105.2 Available Balance": f"{avl_raw} ({avl_fmt})",
        "S105.3 Balance Currency": f"{v[24:25]} — {cm.get(v[24:25], '?')}",
    }
    return detail, {"F105": v}


def _pf106(v: str):
    detail = {
        "S106.1 TO Account Currency": v[0:3],
        "S106.2 Original Currency": v[3:6],
        "S106.3 TO Account Amount": v[6:18],
        "S106.4 Original Amount": v[18:30],
        "S106.5 FROM Acct Exchange Rate": v[30:38],
        "S106.6 TO Acct Exchange Rate": v[38:46],
    }
    return detail, {"F106": v}


def _pf121(v: str):
    dc = {
        "0": "Wait terminal confirm", "1": "Reason to debit", "2": "ForcePost",
        "3": "VISA Fast Funds", "4": "Verification Only", "6": "UPOP with OTP",
        "8": "Discontinuous P2P",
    }
    # Security requirement: Never expose CVV2
    detail = {
        "S121.1 Transaction Category": v[0:2].strip(),
        "S121.2 Draft Capture":        f"{v[2:3].strip()} — {dc.get(v[2:3].strip(), 'Unknown')}",
        "S121.3 CVV2":                 "***MASKED_CVV2***",
        "S121.4 Clerk ID":             v[6:22].strip(),
        "S121.5 Invoice Number":       v[22:38].strip(),
        "S121.6 Batch/Shift Data":     v[38:47].strip(),
    }
    compact = {
        "F121.1": v[0:2], "F121.2": v[2:3], "F121.3": "***",
        "F121.4": v[6:22], "F121.5": v[22:38], "F121.6": v[38:47],
    }
    return detail, compact


def _pf122(v: str):
    arc = {
        "0": "Auth Successful", "5": "Cannot Perform", "7": "Non-participating issuer attempt",
        "8": "Acquirer attempt ACS unavail", "9": "Auth Failed",
    }
    detail = {
        "S122.1 CAVV": "***MASKED_CAVV***",
        "S122.2 Auth Result Code": f"{v[3:4]} — {arc.get(v[3:4], '?')}",
        "S122.3 Unpredictable Number": v[4:8],
        "S122.4 Merchant Tran ID": v[8:48].strip(),
    }
    return detail, {"F122": "***" + v[3:]}


def _pf126(v: str):
    detail = {
        "S126.1 Original Invoice No": v[0:16],
        "S126.2 Original Seq No": v[16:25],
        "S126.3 Preauth Hold (min)": v[25:34],
    }
    return detail, {"F126": v}


def _parse_uamp(raw: str) -> Dict[str, str]:
    text = raw.replace(chr(13), "")
    parts = text.split(chr(16))
    result: Dict[str, str] = {}
    for p in parts:
        p = p.strip(chr(19)).strip()
        if "=" in p:
            k, v = p.split("=", 1)
            k_clean = k.strip()
            v_clean = v.strip()
            if k_clean in ("NP", "RPK"):
                v_clean = "***MASKED_SECRET***"
            elif k_clean in ("P2", "ExtPAN") and v_clean:
                v_clean = strict_strict_mask_pan(v_clean)
            result[k_clean] = v_clean
        elif p:
            result[p] = ""
    return result


def _apply_names(d: Dict[str, str], nm: Dict[str, str]) -> Dict[str, str]:
    return {f"{k} ({nm[k]})" if k in nm else k: v for k, v in d.items()}


def _uamp_compact(raw: str) -> str:
    d = _parse_uamp(raw)
    return "".join(f"{k}={v}" for k, v in d.items())


def _build_compact(mti: str, header: Dict[str, str], fields_compact: List[Tuple[int, str, Any]]) -> str:
    short_mti = mti[1:] if len(mti) == 4 else mti
    parts = [f"{short_mti}:", f"H1){header['H1']}{SEP}H2){header['H2']}{SEP}H3){header['H3']}{SEP}"]
    for fnum, raw, compact in fields_compact:
        if isinstance(compact, dict) and len(compact) > 1:
            sub_parts = [f"{k}){v}" for k, v in compact.items()]
            parts.append(SSEP.join(sub_parts) + SSEP + SEP)
        elif isinstance(compact, dict) and len(compact) == 1:
            k, v = next(iter(compact.items()))
            parts.append(f"{k}){v}{SEP}")
        else:
            parts.append(f"F{fnum}){raw}{SEP}")
    return "".join(parts)


def mask_sensitive_wire_string(raw_msg: str) -> str:
    """Mask PAN and PIN blocks in raw TIC or ISO wire strings before returning to UI."""
    if not raw_msg:
        return ""
    out = re.sub(
        r"(A4M\d{5}\d{4}[0-9A-Fa-f]{16,32})(\d{2})(\d{12,19})",
        lambda m: f"{m.group(1)}{m.group(2)}{strict_strict_mask_pan(m.group(3))}",
        raw_msg,
    )
    out = re.sub(
        r"(F2\))(\d{12,19})",
        lambda m: f"{m.group(1)}{strict_strict_mask_pan(m.group(2))}",
        out,
    )
    out = re.sub(r"(F52\))[0-9A-Fa-f]{16}", r"\1****************", out)
    out = re.sub(r"(F35\))[^Ý]+", r"\1***MASKED_TRACK2***", out)
    out = re.sub(r"(F45\))[^Ý]+", r"\1***MASKED_TRACK1***", out)
    return out


def decode_full_tic_or_iso_message(raw_msg: str, allow_full_pan: bool = False) -> Dict[str, Any]:
    """
    Master decoder entry point reusing `tic_decoder.py` logic for TIC/TCI v2.164e
    and falling back to `iso_standard_codec.py` if an ISO 8583:1987 message is supplied.
    Always returns ascending numeric field order, flat rows for UI tables, subfields,
    warnings, errors, and masked sensitive fields.
    """
    if not raw_msg or not raw_msg.strip():
        return {
            "valid": False,
            "format": "EMPTY",
            "header": {},
            "mti": "",
            "mti_description": "",
            "primary_bitmap": "",
            "secondary_bitmap": None,
            "fields_present": [],
            "parsed_fields": [],
            "flat_rows": [],
            "warnings": [],
            "parse_errors": {"message": "Empty message content"},
            "compact_tic": "",
            "sanitized_raw": "",
        }

    msg = _unescape(raw_msg.replace("\n", "").replace("\r", "").strip())
    a4m_idx = msg.find("A4M")

    # Standard ISO 8583:1987 fallback if not TIC
    if a4m_idx == -1:
        iso_res = decode_iso8583_1987(msg)
        if not iso_res.get("valid"):
            return {
                "valid": False,
                "format": "UNKNOWN",
                "header": {},
                "mti": iso_res.get("mti", ""),
                "mti_description": "Unknown / Invalid Format",
                "primary_bitmap": "",
                "secondary_bitmap": None,
                "fields_present": [],
                "parsed_fields": [],
                "flat_rows": [],
                "warnings": iso_res.get("warnings", []),
                "parse_errors": {"format": iso_res.get("error", "Missing A4M header")},
                "compact_tic": "",
                "sanitized_raw": mask_sensitive_wire_string(msg),
            }
        bmap = iso_res.get("bitmap", {})
        raw_f = iso_res.get("raw_fields", {})
        parsed_fields = []
        flat_rows = []
        for fnum in sorted(int(k) for k in raw_f.keys() if str(k).isdigit()):
            if fnum == 1:
                continue
            val = raw_f[str(fnum)]
            fname, dtype, ltype, flen = ISO8583_FIELDS.get(fnum, ("Unknown", "ANS", "LLVAR", None))
            if fnum == 2:
                safe_val = val if allow_full_pan else strict_strict_mask_pan(val)
            elif fnum in (35, 45, 52, 53, 63):
                safe_val = f"***MASKED_F{fnum}***"
            else:
                safe_val = val
            parsed_fields.append({
                "field_number": fnum,
                "field_tag": f"F{fnum}",
                "field_name": fname,
                "data_type": dtype,
                "length_type": ltype,
                "raw_value": safe_val,
                "display_value": safe_val,
                "subfields": [{"key": "value", "value": safe_val}],
            })
            flat_rows.append({
                "field_number": fnum,
                "field_tag": f"F{fnum}",
                "field_name": fname,
                "subfield_key": fname,
                "value": safe_val,
            })
        mti_val = iso_res["mti"]
        return {
            "valid": True,
            "format": "ISO8583_1987",
            "header": {"Protocol": "ISO 8583:1987"},
            "mti": mti_val,
            "mti_description": MTI_NAMES.get(mti_val, "ISO 8583 Message"),
            "primary_bitmap": bmap.get("primary_hex", ""),
            "secondary_bitmap": bmap.get("secondary_hex"),
            "fields_present": sorted(f for f in bmap.get("fields_present", []) if f != 1),
            "parsed_fields": parsed_fields,
            "flat_rows": flat_rows,
            "warnings": iso_res.get("warnings", []),
            "parse_errors": {},
            "compact_tic": "",
            "sanitized_raw": mask_sensitive_wire_string(msg),
        }

    if a4m_idx > 0:
        msg = msg[a4m_idx:]

    if len(msg) < 28:
        return {
            "valid": False,
            "format": "TIC_V2164E",
            "header": {},
            "mti": "",
            "mti_description": "",
            "primary_bitmap": "",
            "secondary_bitmap": None,
            "fields_present": [],
            "parsed_fields": [],
            "flat_rows": [],
            "warnings": [],
            "parse_errors": {"header": "TIC/TCI message is too short (< 28 chars)"},
            "compact_tic": "",
            "sanitized_raw": mask_sensitive_wire_string(msg),
        }

    h1, h2, h3 = msg[0:3], msg[3:5], msg[5:8]
    header_info = {
        "H1 Start Indicator": h1,
        "H2 Protocol Version": h2,
        "H3 Reject Status": h3,
    }
    header_for_compact = {"H1": h1, "H2": h2, "H3": h3}
    warnings: List[str] = []

    if h1 != "A4M":
        warnings.append(f"Unexpected start indicator: '{h1}' (expected 'A4M')")
    if h3 != "000":
        rmap = {"001": "Not a TIC/TCI message", "197": "Invalid MAC"}
        warnings.append(f"Reject H3={h3}: {rmap.get(h3, 'Bad field #' + h3)}")

    pos = 8
    mti = msg[pos : pos + 4]
    pos += 4
    if mti.startswith("9"):
        orig = "0" + mti[1:]
        mti_name = f"REJECT of {MTI_NAMES.get(orig, 'Unknown')} ({orig})"
        warnings.append(f"Reject message (MTI={mti})")
    else:
        mti_name = MTI_NAMES.get(mti, "Unknown MTI")

    try:
        present, ph, sh, _, pos = _read_bitmap(msg, pos)
    except Exception as exc:
        return {
            "valid": False,
            "format": "TIC_V2164E",
            "header": header_info,
            "mti": mti,
            "mti_description": mti_name,
            "primary_bitmap": "",
            "secondary_bitmap": None,
            "fields_present": [],
            "parsed_fields": [],
            "flat_rows": [],
            "warnings": warnings,
            "parse_errors": {"bitmap": str(exc)},
            "compact_tic": "",
            "sanitized_raw": mask_sensitive_wire_string(msg),
        }

    parsed_fields: List[Dict[str, Any]] = []
    flat_rows: List[Dict[str, Any]] = []
    parse_errors: Dict[str, str] = {}
    compact_fields: List[Tuple[int, str, Any]] = []

    # Strictly ascending numeric order, never treating Field 1 as a data field
    for fnum in sorted(f for f in present if f != 1):
        try:
            raw_val, pos = _read_field(msg, pos, fnum)
            fname, dtype, ltype, _ = FIELD_DEFS.get(fnum, ("Unknown", "ANS", "LLVAR", None))

            detail: Dict[str, Any] = {}
            compact: Any = None
            safe_raw = raw_val

            if fnum == 2:
                safe_raw = raw_val if allow_full_pan else strict_strict_mask_pan(raw_val)
                detail = {
                    "PAN": safe_raw,
                    "BIN (First 6)": raw_val[:6] if len(raw_val) >= 6 else raw_val,
                    "Length": str(len(raw_val)),
                }
                compact = {"F2": safe_raw}
            elif fnum == 3:
                if len(raw_val) >= 7:
                    detail, compact = _pf3(raw_val)
                else:
                    detail = {"Processing Code": raw_val}
                    compact = {"F3": raw_val}
            elif fnum in (4, 5, 6, 54):
                amt_fmt = f"{int(raw_val)/100:,.2f}" if raw_val.isdigit() else raw_val
                detail = {"Raw Minor Units": raw_val, "Formatted Amount": amt_fmt}
                compact = {f"F{fnum}": raw_val}
            elif fnum == 22:
                detail, compact = _pf22(raw_val)
            elif fnum == 25:
                detail, compact = _pf25(raw_val)
            elif fnum == 28:
                detail, compact = _pf28(raw_val)
            elif fnum in (35, 45):
                safe_raw = f"***MASKED_TRACK_{'2' if fnum == 35 else '1'}_DATA***"
                detail = {"Track Data": safe_raw}
                compact = {f"F{fnum}": safe_raw}
            elif fnum == 39:
                detail, compact = _pf39(raw_val)
            elif fnum == 43:
                detail, compact = _pf43(raw_val)
            elif fnum == 44:
                detail, compact = _pf44(raw_val)
            elif fnum == 48:
                detail, compact = _pf48(raw_val)
            elif fnum in (52, 53, 63):
                safe_raw = f"***MASKED_{fname.upper().replace(' ', '_')}***"
                detail = {fname: safe_raw}
                compact = {f"F{fnum}": "****************"}
            elif fnum == 61:
                detail, compact = _pf61(raw_val)
            elif fnum == 70:
                code = raw_val.strip().lstrip("0") or "0"
                detail = {"F70 Network Mgmt Code": f"{raw_val.strip()} — {NETWORK_MGMT_CODES.get(code, 'Unknown')}"}
                compact = {"F70": raw_val.strip()}
            elif fnum == 95:
                detail, compact = _pf95(raw_val)
            elif fnum == 104:
                net = raw_val.strip()
                detail = {"Host Network ID": f"{net} — {HOST_NET_IDS.get(net, 'Other')}"}
                compact = {"F104": net}
            elif fnum == 105:
                detail, compact = _pf105(raw_val)
            elif fnum == 106:
                detail, compact = _pf106(raw_val)
            elif fnum == 121:
                safe_raw = raw_val[:3] + "***" + raw_val[6:] if len(raw_val) >= 6 else "***"
                detail, compact = _pf121(raw_val)
            elif fnum == 122:
                safe_raw = "***" + raw_val[3:]
                detail, compact = _pf122(raw_val)
            elif fnum == 123:
                uamp = _parse_uamp(raw_val)
                detail = _apply_names(uamp, UAMP_F123_NAMES)
                compact = {"F123": _uamp_compact(raw_val)}
            elif fnum == 124:
                uamp = _parse_uamp(raw_val)
                detail = _apply_names(uamp, UAMP_F124_NAMES)
                compact = {"F124": _uamp_compact(raw_val)}
            elif fnum == 125:
                uamp = _parse_uamp(raw_val)
                detail = _apply_names(uamp, UAMP_F125_NAMES)
                compact = {"F125": _uamp_compact(raw_val)}
            elif fnum == 126:
                detail, compact = _pf126(raw_val)
            else:
                detail = {fname: raw_val.strip()}
                compact = {f"F{fnum}": raw_val}

            sub_list = [{"key": k, "value": str(v)} for k, v in detail.items() if v is not None and str(v) != ""]
            if not sub_list:
                sub_list = [{"key": fname, "value": safe_raw.strip()}]

            summary_val = (
                " | ".join(f"{s['key']}: {s['value']}" for s in sub_list)
                if len(sub_list) > 1
                else sub_list[0]["value"]
            )

            parsed_fields.append({
                "field_number": fnum,
                "field_tag": f"F{fnum}",
                "field_name": fname,
                "data_type": dtype,
                "length_type": ltype,
                "raw_value": safe_raw,
                "display_value": summary_val,
                "subfields": sub_list,
            })

            for idx, s in enumerate(sub_list):
                flat_rows.append({
                    "field_number": fnum,
                    "field_tag": f"F{fnum}" if idx == 0 else "",
                    "field_name": fname if idx == 0 else "",
                    "subfield_key": s["key"],
                    "value": s["value"],
                })

            compact_fields.append((fnum, safe_raw, compact))
        except Exception as exc:
            parse_errors[f"F{fnum}"] = str(exc)
            warnings.append(f"Error reading F{fnum}: {exc}")
            break

    remaining = msg[pos:]
    if remaining:
        warnings.append(f"{len(remaining)} unparsed trailing character(s)")

    compact_line = _build_compact(mti, header_for_compact, compact_fields)
    return {
        "valid": len(parse_errors) == 0,
        "format": "TIC_V2164E",
        "header": header_info,
        "mti": mti,
        "mti_description": mti_name,
        "primary_bitmap": ph,
        "secondary_bitmap": sh if sh else None,
        "fields_present": sorted(f for f in present if f != 1),
        "parsed_fields": parsed_fields,
        "flat_rows": flat_rows,
        "warnings": warnings,
        "parse_errors": parse_errors,
        "compact_tic": compact_line,
        "sanitized_raw": mask_sensitive_wire_string(msg),
    }


def extract_metadata_from_tic(raw_msg: str) -> Dict[str, Any]:
    """Extracts structured transaction columns from a raw TIC message for DB persistence & backfill."""
    dec = decode_full_tic_or_iso_message(raw_msg, allow_full_pan=False)
    fmap = {f["field_number"]: f for f in dec.get("parsed_fields", [])}

    def _raw(fnum: int) -> Optional[str]:
        return fmap[fnum]["raw_value"].strip() if fnum in fmap and fmap[fnum].get("raw_value") else None

    f43_subs = {s["key"]: s["value"] for s in fmap.get(43, {}).get("subfields", [])}
    term_owner = next((v for k, v in f43_subs.items() if "F43.1 " in k), None)
    term_city = next((v for k, v in f43_subs.items() if "F43.2 " in k), None)
    term_addr = next((v for k, v in f43_subs.items() if "F43.5 " in k), None)
    merch_name = next((v for k, v in f43_subs.items() if "F43.12" in k), None) or term_owner

    f3_raw = _raw(3) or ""
    tc_prefix = f3_raw[:3] if len(f3_raw) >= 3 else ""
    tx_type_name = TRAN_CODES.get(tc_prefix)

    return {
        "mcc": _raw(18),
        "pos_entry_mode": _raw(22),
        "pos_condition_code": _raw(25),
        "acquirer_id": _raw(32),
        "forwarding_id": _raw(33),
        "approval_code": _raw(38),
        "terminal_id": _raw(41),
        "terminal_owner": term_owner,
        "terminal_name": term_addr or term_city or _raw(41),
        "merchant_name": merch_name,
        "source_account": _raw(102),
        "destination_account": _raw(103),
        "transaction_type_name": tx_type_name,
    }


def compare_request_and_response(req_raw: Optional[str], resp_raw: Optional[str]) -> List[Dict[str, Any]]:
    """Builds a side-by-side comparison of Request vs Response ISO/TIC fields in ascending numeric order."""
    req_dec = decode_full_tic_or_iso_message(req_raw or "") if req_raw else {"parsed_fields": []}
    resp_dec = decode_full_tic_or_iso_message(resp_raw or "") if resp_raw else {"parsed_fields": []}

    req_map = {f["field_number"]: f for f in req_dec.get("parsed_fields", [])}
    resp_map = {f["field_number"]: f for f in resp_dec.get("parsed_fields", [])}

    all_fnums = sorted(set(req_map.keys()) | set(resp_map.keys()))
    comparison: List[Dict[str, Any]] = []
    for fnum in all_fnums:
        if fnum == 1:
            continue
        rf = req_map.get(fnum)
        spf = resp_map.get(fnum)
        fname = (rf or spf or {}).get("field_name") or FIELD_DEFS.get(fnum, ("Unknown",))[0]
        req_val = rf["display_value"] if rf else None
        resp_val = spf["display_value"] if spf else None
        comparison.append({
            "field_number": fnum,
            "field_tag": f"F{fnum}",
            "field_name": fname,
            "in_request": rf is not None,
            "in_response": spf is not None,
            "request_value": req_val,
            "response_value": resp_val,
            "differs": (req_val or "") != (resp_val or ""),
        })
    return comparison


def export_decoded_message_excel_bytes(decoded: Dict[str, Any], rrn: str = "TX") -> Optional[bytes]:
    """Generates an in-memory `.xlsx` report using the styling from `tic_decoder.py`."""
    if not HAS_OPENPYXL:
        return None
    wb = openpyxl.Workbook()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    C_NAVY = "1B2A4A"
    C_TEAL = "0D6E6E"
    C_STEEL = "2E5F8A"
    C_ICE = "E8F4FD"
    C_LTGRAY = "F5F5F5"
    C_GOLD = "D4AF37"
    C_BORDER = "B0BEC5"

    def _fill(c): return PatternFill("solid", fgColor=c)
    def _font(b=False, c="000000", s=10, it=False): return Font(bold=b, color=c, size=s, italic=it, name="Calibri")
    def _border(st="thin", c=C_BORDER):
        sd = Side(style=st, color=c)
        return Border(left=sd, right=sd, top=sd, bottom=sd)
    def _align(h="left", v="center", w=False): return Alignment(horizontal=h, vertical=v, wrap_text=w)

    ws1 = wb.active
    ws1.title = "Summary"
    ws1.column_dimensions["A"].width = 28
    ws1.column_dimensions["B"].width = 65

    c = ws1.cell(row=1, column=1, value="TIC / TCI ISO 8583 · Decoded Message Report")
    c.fill = _fill(C_NAVY); c.font = _font(True, "FFFFFF", 13); c.alignment = _align("center")
    ws1.merge_cells("A1:B1")

    c2 = ws1.cell(row=2, column=1, value=f"Reference (RRN): {rrn} | Generated: {ts}")
    c2.fill = _fill(C_NAVY); c2.font = _font(False, "D0D0D0", 10, True); c2.alignment = _align("center")
    ws1.merge_cells("A2:B2")

    overview = [
        ("Format", decoded.get("format", "TIC_V2164E")),
        ("MTI", f"{decoded.get('mti', '')} — {decoded.get('mti_description', '')}"),
        ("Primary Bitmap", decoded.get("primary_bitmap", "")),
        ("Secondary Bitmap", decoded.get("secondary_bitmap") or "— not present"),
        ("Fields Present", str(decoded.get("fields_present", []))),
    ]
    for k, v in (decoded.get("header") or {}).items():
        overview.append((k, str(v)))

    r = 4
    for idx, (k, v) in enumerate(overview):
        bg = C_ICE if idx % 2 == 0 else C_LTGRAY
        ca = ws1.cell(row=r, column=1, value=k)
        cb = ws1.cell(row=r, column=2, value=v)
        ca.fill = _fill(bg); ca.font = _font(True); ca.border = _border()
        cb.fill = _fill(bg); cb.font = _font(False); cb.border = _border()
        r += 1

    r += 1
    ct = ws1.cell(row=r, column=1, value="COMPACT TIC-FORMAT OUTPUT")
    ct.fill = _fill(C_TEAL); ct.font = _font(True, "FFFFFF", 11)
    ws1.merge_cells(start_row=r, start_column=1, end_row=r, end_column=2)
    r += 1
    cc = ws1.cell(row=r, column=1, value=decoded.get("compact_tic", ""))
    cc.fill = _fill("FFF8E1"); cc.font = _font(False, "5D4037", 9, True)
    cc.alignment = _align("left", "center", True); cc.border = _border("medium", C_GOLD)
    ws1.merge_cells(start_row=r, start_column=1, end_row=r, end_column=2)

    ws2 = wb.create_sheet("Fields Detail")
    ws2.column_dimensions["A"].width = 10
    ws2.column_dimensions["B"].width = 34
    ws2.column_dimensions["C"].width = 38
    ws2.column_dimensions["D"].width = 55

    headers = ["Field", "Field Name", "Subfield / Key", "Value"]
    for ci, h in enumerate(headers, 1):
        hc = ws2.cell(row=1, column=ci, value=h)
        hc.fill = _fill(C_STEEL); hc.font = _font(True, "FFFFFF", 10); hc.alignment = _align("center")

    for idx, row_item in enumerate(decoded.get("flat_rows", []), start=2):
        bg = C_ICE if idx % 2 == 0 else C_LTGRAY
        ws2.cell(row=idx, column=1, value=row_item["field_tag"]).fill = _fill(bg)
        ws2.cell(row=idx, column=2, value=row_item["field_name"]).fill = _fill(bg)
        ws2.cell(row=idx, column=3, value=row_item["subfield_key"]).fill = _fill(bg)
        ws2.cell(row=idx, column=4, value=row_item["value"]).fill = _fill(bg)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def strict_mask_pan(pan) -> str:
    """Always masks PAN as 123456******1234 by default, even when LOG_RAW_DATA=True."""
    if not pan:
        return "****"
    clean = "".join(ch for ch in str(pan) if ch.isdigit())
    if len(clean) >= 10:
        return f"{clean[:6]}{'*' * (len(clean) - 10)}{clean[-4:]}"
    if "*" in str(pan):
        return str(pan)
    return "****"
