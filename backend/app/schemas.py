"""
MODULE 3 — schemas.py
Pydantic v2 request and response validation schemas for the Private Host Simulator.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    hsm_mode: str


class CustomerCreate(BaseModel):
    customer_number: str
    first_name: str
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    email: Optional[str] = None
    mobile_number: Optional[str] = None
    address: Optional[str] = None
    customer_status: str = "ACTIVE"
    risk_category: str = "NORMAL"


class CustomerOut(CustomerCreate):
    id: str
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class AccountCreate(BaseModel):
    account_number: str
    customer_id: str
    account_type: str = "CURRENT"
    currency: str = "BDT"
    available_balance: Decimal = Decimal("0.00")
    ledger_balance: Decimal = Decimal("0.00")
    overdraft_limit: Decimal = Decimal("0.00")
    account_status: str = "ACTIVE"
    branch_code: str = "0001"


class AccountOut(AccountCreate):
    id: str
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class CardCreate(BaseModel):
    customer_id: str
    test_pan_reference: str = Field(..., description="Synthetic 16-digit test PAN")
    cardholder_name: str
    expiry_month: int = Field(..., ge=1, le=12)
    expiry_year: int = Field(..., ge=2024, le=2040)
    card_type: str = "DEBIT"
    card_product: str = "VISA_CLASSIC"
    card_status: str = "ACTIVE"
    linked_account_id: str
    card_profile_id: Optional[str] = None
    pvv_or_offset: str = "7821"
    cvv_value: str = "011"


class CardOut(BaseModel):
    id: str
    customer_id: str
    card_number_token: str
    test_pan_reference: str
    masked_pan: str
    cardholder_name: str
    expiry_month: int
    expiry_year: int
    card_type: str
    card_product: str
    card_status: str
    linked_account_id: Optional[str]
    card_profile_id: Optional[str]
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class CardLimitUpdate(BaseModel):
    withdrawal_limit: Decimal
    purchase_limit: Decimal
    ecommerce_limit: Decimal
    transaction_limit: Decimal
    daily_limit: Decimal
    weekly_limit: Decimal
    monthly_limit: Decimal
    status: str = "ACTIVE"


class AccountLimitUpdate(BaseModel):
    per_transaction_limit: Decimal
    daily_limit: Decimal
    weekly_limit: Decimal
    monthly_limit: Decimal
    status: str = "ACTIVE"


class TransactionCodeFieldSchema(BaseModel):
    iso_field_number: int
    field_name: str
    required: bool = False
    editable: bool = True
    enabled: bool = True
    default_value: Optional[str] = None
    validation_rule: Optional[str] = None
    display_order: int = 0


class TransactionCodeCreate(BaseModel):
    transaction_code: str
    transaction_name: str
    description: Optional[str] = None
    transaction_category: str = "FINANCIAL"
    processing_code: str = "0100000"
    default_mti: str = "0200"
    financial_flag: bool = True
    balance_inquiry_flag: bool = False
    debit_flag: bool = True
    credit_flag: bool = False
    reversal_allowed: bool = True
    pin_required: bool = False
    cvv_required: bool = False
    pvv_required: bool = False
    emv_required: bool = False
    mac_required: bool = False
    account_check_required: bool = True
    card_check_required: bool = True
    limit_check_required: bool = True
    active: bool = True


class TransactionCodeOut(TransactionCodeCreate):
    id: str
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class HsmKeyReferenceCreate(BaseModel):
    key_name: str
    key_type: str
    key_usage: str
    key_identifier: str
    kvc: str
    algorithm: str = "3DES_2KEY"
    key_length: int = 128
    hsm_key_reference: str
    key_status: str = "ACTIVE"


class HsmKeyReferenceOut(HsmKeyReferenceCreate):
    id: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class HsmWorkbenchRequest(BaseModel):
    operation: str  # PIN_VERIFY, PIN_TRANSLATE, PVV_VERIFY, CVV_VERIFY, MAC_GENERATE, MAC_VERIFY, ARQC_VERIFY, ARPC_GENERATE, KEY_CHECK, RAW_COMMAND
    key_identifier: Optional[str] = None
    secondary_key_identifier: Optional[str] = None
    pan: Optional[str] = "4567890123456789"
    pin_block: Optional[str] = None
    clear_pin_for_test_packing: Optional[str] = None
    pvv_or_offset: Optional[str] = "7821"
    pvki: Optional[str] = "1"
    expiry_yy_mm: Optional[str] = "2812"
    service_code: Optional[str] = "101"
    cvv: Optional[str] = "011"
    data_hex: Optional[str] = "48656C6C6F20576F726C64"
    mac_hex: Optional[str] = None
    de55_hex: Optional[str] = None
    arc_hex: Optional[str] = "3030"
    raw_thales_command: Optional[str] = None


class SimulatorBuildRequest(BaseModel):
    mti: str = "0200"
    header_h1: str = "A4M"
    header_h2: str = "02"
    header_h3: str = "000"
    fields: Dict[str, str]


class SimulatorSubmitRequest(BaseModel):
    transaction_code: Optional[str] = None
    mti: str = "0200"
    fields: Dict[str, str] = Field(default_factory=dict)
    raw_tic_message: Optional[str] = None
    source_channel: str = "SIMULATOR"
    idempotency_key: Optional[str] = None
    test_clear_pin_helper: Optional[str] = Field(
        None,
        description="Optional test helper: packs an encrypted ISO-0 PIN block under AWK on the server before submitting",
    )
