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
    institution_id: Optional[str] = None


# [PATCH step02_01:schema_customer_out_inst_fixed]
class CustomerOut(CustomerCreate):
    id: str
    institution_code: Optional[str] = None
    institution_name: Optional[str] = None
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
    institution_id: Optional[str] = None


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
    card_product: str = "VISA_DEBIT_CLASSIC"
    card_status: str = "ACTIVE"
    linked_account_id: Optional[str] = None
    card_profile_id: Optional[str] = None
    pin: Optional[str] = Field("1234", description="Clear 4-12 digit PIN to auto-derive Visa PVV")
    pvv_or_offset: Optional[str] = None
    cvv_value: str = "011"
    institution_id: Optional[str] = None

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
    institution_id: Optional[str] = None
    institution_code: Optional[str] = None
    institution_name: Optional[str] = None
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

# [PATCH step01_01:institution_and_ps_schemas]
# ==============================================================================
# STEP 1 SCHEMAS: PROCESSING SYSTEMS, INSTITUTIONS & BIN RANGES
# ==============================================================================

class ProcessingSystemCreate(BaseModel):
    ps_code: str = Field(..., description="Unique processing system code, e.g. ITCL, VISA, MASTERCARD, NPSB")
    name: str
    system_type: str = "HOST_SWITCH"
    message_format: str = "TIC_V2164E"
    enabled: bool = True
    is_default: bool = False
    configuration: Dict[str, Any] = Field(default_factory=dict)


class ProcessingSystemUpdate(BaseModel):
    name: Optional[str] = None
    system_type: Optional[str] = None
    message_format: Optional[str] = None
    enabled: Optional[bool] = None
    is_default: Optional[bool] = None
    configuration: Optional[Dict[str, Any]] = None


class ProcessingSystemOut(ProcessingSystemCreate):
    id: str
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class InstitutionCreate(BaseModel):
    institution_code: str = Field(..., description="Unique bank code, e.g. XBANK, YBANK, ZBANK, IFIC")
    name: str
    short_name: Optional[str] = None
    acquirer_id: str = Field(..., description="DE32 Acquiring Institution Identification Code")
    forwarding_id: Optional[str] = None
    role: str = "BOTH"  # ISSUER, ACQUIRER, BOTH
    processing_system_id: Optional[str] = Field(
        None,
        description="Primary processing system ID. Defaults to ITCL if omitted.",
    )
    ps_code: Optional[str] = Field(
        "ITCL",
        description="Fallback processing system code if processing_system_id is not supplied (defaults to ITCL).",
    )
    country_code: str = "050"
    currency: str = "BDT"
    settlement_account_number: Optional[str] = None
    status: str = "ACTIVE"
    configuration: Dict[str, Any] = Field(default_factory=dict)


class InstitutionUpdate(BaseModel):
    name: Optional[str] = None
    short_name: Optional[str] = None
    acquirer_id: Optional[str] = None
    forwarding_id: Optional[str] = None
    role: Optional[str] = None
    processing_system_id: Optional[str] = None
    country_code: Optional[str] = None
    currency: Optional[str] = None
    settlement_account_number: Optional[str] = None
    status: Optional[str] = None
    configuration: Optional[Dict[str, Any]] = None


class InstitutionOut(BaseModel):
    id: str
    institution_code: str
    name: str
    short_name: Optional[str] = None
    acquirer_id: str
    forwarding_id: Optional[str] = None
    role: str
    processing_system_id: str
    ps_code: Optional[str] = None
    ps_name: Optional[str] = None
    country_code: str
    currency: str
    settlement_account_number: Optional[str] = None
    status: str
    configuration: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class InstitutionProcessingSystemCreate(BaseModel):
    institution_id: Optional[str] = None
    processing_system_id: str
    member_id: str
    acquirer_id: Optional[str] = None
    network_identifier: Optional[str] = None
    issuer_enabled: bool = True
    acquirer_enabled: bool = True
    message_format: str = "TIC_V2164E"
    routing_configuration: Dict[str, Any] = Field(default_factory=dict)
    status: str = "ACTIVE"


class InstitutionProcessingSystemOut(BaseModel):
    id: str
    institution_id: str
    institution_code: Optional[str] = None
    institution_name: Optional[str] = None
    processing_system_id: str
    ps_code: Optional[str] = None
    ps_name: Optional[str] = None
    member_id: str
    acquirer_id: Optional[str] = None
    network_identifier: Optional[str] = None
    issuer_enabled: bool
    acquirer_enabled: bool
    message_format: str
    routing_configuration: Dict[str, Any]
    status: str
    effective_from: datetime
    effective_to: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class BinRangeCreate(BaseModel):
    bin_prefix: str = Field(..., min_length=6, max_length=12, description="6 to 12 digit BIN prefix")
    bin_low: Optional[str] = None
    bin_high: Optional[str] = None
    pan_length: int = 16
    institution_id: str
    processing_system_id: Optional[str] = None
    card_type: str = "DEBIT"
    card_product: str = "VISA_DEBIT_CLASSIC"
    scheme: str = "ITCL"
    country_code: str = "050"
    currency: str = "BDT"
    is_on_us: bool = True
    status: str = "ACTIVE"


class BinRangeUpdate(BaseModel):
    bin_prefix: Optional[str] = None
    bin_low: Optional[str] = None
    bin_high: Optional[str] = None
    pan_length: Optional[int] = None
    institution_id: Optional[str] = None
    processing_system_id: Optional[str] = None
    card_type: Optional[str] = None
    card_product: Optional[str] = None
    scheme: Optional[str] = None
    country_code: Optional[str] = None
    currency: Optional[str] = None
    is_on_us: Optional[bool] = None
    status: Optional[str] = None


class BinRangeOut(BaseModel):
    id: str
    bin_prefix: str
    bin_low: str
    bin_high: str
    pan_length: int
    institution_id: str
    institution_code: Optional[str] = None
    institution_name: Optional[str] = None
    processing_system_id: str
    ps_code: Optional[str] = None
    ps_name: Optional[str] = None
    card_type: str
    card_product: str
    scheme: str
    country_code: str
    currency: str
    is_on_us: bool
    status: str
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# [PATCH step03_01:schemas_update_and_audit]

# ==============================================================================
# STEP 3 SCHEMAS: FULL CRUD UPDATES & AUDIT TRAIL
# ==============================================================================

class CustomerUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    email: Optional[str] = None
    mobile_number: Optional[str] = None
    address: Optional[str] = None
    customer_status: Optional[str] = None
    risk_category: Optional[str] = None
    institution_id: Optional[str] = None


class AccountUpdate(BaseModel):
    account_type: Optional[str] = None
    currency: Optional[str] = None
    available_balance: Optional[Decimal] = None
    ledger_balance: Optional[Decimal] = None
    overdraft_limit: Optional[Decimal] = None
    account_status: Optional[str] = None
    branch_code: Optional[str] = None
    institution_id: Optional[str] = None

# [PATCH fix_modern_maintenance:card_update_customer_id]
class CardUpdate(BaseModel):
    cardholder_name: Optional[str] = None
    expiry_month: Optional[int] = Field(None, ge=1, le=12)
    expiry_year: Optional[int] = Field(None, ge=2024, le=2040)
    card_status: Optional[str] = None
    card_product: Optional[str] = None
    linked_account_id: Optional[str] = None
    card_profile_id: Optional[str] = None
    institution_id: Optional[str] = None
    customer_id: Optional[str] = None


class AuditTrailOut(BaseModel):
    id: str
    entity_type: str
    entity_id: str
    action: str
    performed_by: str
    before_state: Optional[Dict[str, Any]] = None
    after_state: Optional[Dict[str, Any]] = None
    change_summary: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# [PATCH step03_02:schemas_card_profile_and_key_updates]

# ==============================================================================
# CARD PROFILE, KEY & RESPONSE CODE UPDATE SCHEMAS (STEP 3.2)
# ==============================================================================

class CardProfileCreate(BaseModel):
    profile_code: str
    profile_name: str
    card_product: str = "VISA_DEBIT_CLASSIC"
    transaction_permissions: Dict[str, Any] = Field(default_factory=dict)
    domestic_enabled: bool = True
    international_enabled: bool = False
    ecommerce_enabled: bool = True
    contactless_enabled: bool = True
    cash_enabled: bool = True
    status: str = "ACTIVE"


class CardProfileUpdate(BaseModel):
    profile_name: Optional[str] = None
    card_product: Optional[str] = None
    transaction_permissions: Optional[Dict[str, Any]] = None
    domestic_enabled: Optional[bool] = None
    international_enabled: Optional[bool] = None
    ecommerce_enabled: Optional[bool] = None
    contactless_enabled: Optional[bool] = None
    cash_enabled: Optional[bool] = None
    status: Optional[str] = None


class CardProfileOut(CardProfileCreate):
    id: str
    model_config = ConfigDict(from_attributes=True)


class HsmKeyReferenceUpdate(BaseModel):
    key_name: Optional[str] = None
    key_usage: Optional[str] = None
    kvc: Optional[str] = None
    key_status: Optional[str] = None
    institution_id: Optional[str] = None
    processing_system_id: Optional[str] = None


class ResponseCodeUpdate(BaseModel):
    response_description: Optional[str] = None
    response_category: Optional[str] = None
    approved_flag: Optional[bool] = None
    retry_allowed: Optional[bool] = None
    active: Optional[bool] = None


# [PATCH step04:schemas_card_account_links]

# ==============================================================================
# STEP 4 SCHEMAS: CARD & ACCOUNT MULTI-LINKING
# ==============================================================================

class CardAccountLinkCreate(BaseModel):
    account_id: str
    account_role: str = "SECONDARY"  # PRIMARY, SECONDARY
    priority: int = 2
    status: str = "ACTIVE"


class CardAccountLinkUpdate(BaseModel):
    account_role: Optional[str] = None
    priority: Optional[int] = None
    status: Optional[str] = None


class CardAccountLinkOut(BaseModel):
    id: str
    card_id: str
    account_id: str
    account_number: Optional[str] = None
    account_type: Optional[str] = None
    currency: str
    available_balance: Optional[float] = None
    account_role: str
    priority: int
    status: str
    model_config = ConfigDict(from_attributes=True)


# [PATCH step05:schema_paginated_response]

# ==============================================================================
# STEP 5 SCHEMAS: PAGINATED RESPONSE ENVELOPE
# ==============================================================================

from typing import Generic, TypeVar

T = TypeVar('T')

class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    page_size: int
    total_pages: int


# [PATCH step06:schemas_card_crypto]

# ==============================================================================
# STEP 6 SCHEMAS: PIN, PVV, CVV & SYNTHETIC CARD GENERATION
# ==============================================================================

class CardPinChangeRequest(BaseModel):
    new_pin: str = Field(..., min_length=4, max_length=12, description='New clear PIN (4 to 12 digits)')


class CardGenerateRequest(BaseModel):
    bin_prefix: str = '456789'
    cardholder_name: str = 'SYNTHETIC CARDHOLDER'
    card_type: str = 'DEBIT'
    card_product: str = 'VISA_DEBIT_CLASSIC'
    initial_pin: str = '1234'
    linked_account_id: Optional[str] = None


class PvvCalculateRequest(BaseModel):
    pan: str
    pin: str
    pvki: str = '1'
    pvk_id: str = 'PVK_VISA_01'


class CvvCalculateRequest(BaseModel):
    pan: str
    expiry_yy_mm: str = '2812'
    service_code: str = '101'
    cvk_id: str = 'CVK_MAIN_01'


class PinBlockPackRequest(BaseModel):
    pan: str
    pin: str
    format: str = 'ISO_0'
    awk_id: str = 'AWK_ATM_01'


# [PATCH step07:schemas_log_portal]

# ==============================================================================
# STEP 7 SCHEMAS: API AUDIT LOGS & CRYPTO EVENTS
# ==============================================================================

class ApiAuditLogOut(BaseModel):
    id: str
    correlation_id: str
    http_method: str
    path: str
    status_code: int
    duration_ms: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class CryptoEventOut(BaseModel):
    id: str
    correlation_id: str
    operation_type: str
    step_number: int
    step_name: str
    key_id: Optional[str] = None
    key_kcv: Optional[str] = None
    raw_input: Optional[str] = None
    raw_output: Optional[str] = None
    expected_output: Optional[str] = None
    status: str
    duration_ms: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class UnifiedLogTimelineOut(BaseModel):
    events: List[Dict[str, Any]]
    total: int


# [PATCH step08:schemas_authorizer_rules]

# ==============================================================================
# STEP 8 SCHEMAS: AUTHORIZER RULES ENGINE
# ==============================================================================

class AuthorizerRuleCreate(BaseModel):
    rule_code: str = Field(..., min_length=3, max_length=50)
    name: str
    description: Optional[str] = None
    priority: int = 100
    stage: str = "PRE_AUTH"
    rule_mode: str = "SCRIPT"
    conditions_json: Optional[Dict[str, Any]] = None
    expression: str
    action: str = "DECLINE"
    response_code: str = "05"
    message: str = "Declined by Authorizer Rule"
    stop_on_match: bool = True
    enabled: bool = True


class AuthorizerRuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[int] = None
    expression: Optional[str] = None
    action: Optional[str] = None
    response_code: Optional[str] = None
    message: Optional[str] = None
    stop_on_match: Optional[bool] = None
    enabled: Optional[bool] = None


class AuthorizerRuleOut(AuthorizerRuleCreate):
    id: str
    hit_count: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class RuleDryRunRequest(BaseModel):
    expression: str
    context: Dict[str, Any]


class RuleDryRunResponse(BaseModel):
    matched: bool
    valid: bool
    error: Optional[str] = None


# [PATCH step09:schemas_parse_raw]

# ==============================================================================
# STEP 9 SCHEMAS: DUAL-CODEC WIRE PARSER
# ==============================================================================

class RawMessageParseRequest(BaseModel):
    raw_message: str


class RawMessageParseResponse(BaseModel):
    valid: bool
    format: str  # TIC_V2164E, ISO8583_1987, UNKNOWN
    mti: str
    fields: Dict[str, str]
    detailed_fields: Dict[str, Any]
    derived_transaction_code: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
    error: Optional[str] = None


# [PATCH step10:schemas_key_ceremony]

# ==============================================================================
# STEP 10 SCHEMAS: HSM KEY CEREMONY & EXCHANGE
# ==============================================================================

class RandomKeyGenerateRequest(BaseModel):
    length_bits: int = 128


class KeyAssemblyRequest(BaseModel):
    key_identifier: str = Field(..., min_length=3, max_length=100)
    key_type: str = 'AWK'
    key_name: Optional[str] = None
    institution_id: Optional[str] = None
    components: List[str] = Field(..., min_length=2, max_length=3)


class KeyExportUnderZmkRequest(BaseModel):
    key_identifier: str
    zmk_identifier: str = 'ZMK_MAIN'


class KeyImportUnderZmkRequest(BaseModel):
    key_identifier: str
    key_type: str = 'AWK'
    encrypted_key_hex: str
    zmk_identifier: str = 'ZMK_MAIN'
    institution_id: Optional[str] = None


class KeyCeremonyResultOut(BaseModel):
    key_identifier: str
    key_type: str
    kvc: str
    component_kcvs: List[str] = Field(default_factory=list)
    status: str = 'REGISTERED'


# [PATCH step11:schemas_network_routing]

# ==============================================================================
# STEP 11 SCHEMAS: NETWORK ROUTING & SIMULATION
# ==============================================================================

class NetworkProfileUpdate(BaseModel):
    simulation_mode: Optional[str] = None
    simulated_response_code: Optional[str] = None
    simulated_delay_ms: Optional[int] = None
    enabled: Optional[bool] = None


class NetworkRouteLookupRequest(BaseModel):
    pan: str
    acquirer_id: Optional[str] = '123456'


# [PATCH step12:schemas_settlement]

# ==============================================================================
# STEP 12 SCHEMAS: CLEARING, SETTLEMENT & RECONCILIATION
# ==============================================================================

class BatchCutoverRequest(BaseModel):
    ps_code: str = 'ITCL'


class SettlementBatchOut(BaseModel):
    id: str
    batch_number: str
    ps_code: str
    cutover_time: datetime
    status: str
    total_transactions: int
    total_amount: float
    total_fees: float
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class SettlementPositionOut(BaseModel):
    id: str
    batch_id: str
    institution_id: str
    institution_code: Optional[str] = None
    institution_name: Optional[str] = None
    net_settlement_amount: float
    debit_count: int
    credit_count: int
    debit_volume: float
    credit_volume: float
    net_fee_amount: float
    settlement_status: str
    model_config = ConfigDict(from_attributes=True)


class ReconciliationReportOut(BaseModel):
    total_approved_transactions: int
    total_reversed_transactions: int
    total_settled_transactions: int
    pending_clearing_transactions: int
    reconciliation_status: str
    recent_batches: List[Dict[str, Any]]


# [PATCH add_limit_reset_and_pan_routing_schemas]

# ==============================================================================
# ENTERPRISE ENHANCEMENT SCHEMAS: LIMIT USAGE RESET & PAN ROUTING RULES
# ==============================================================================

class LimitUsageResetRequest(BaseModel):
    scope: str = Field("ALL", description="DAILY | WEEKLY | MONTHLY | ALL")
    reason: str = Field(..., min_length=3, max_length=250, description="Mandatory testing reference or reason for resetting usage counters")
    testing_reference: Optional[str] = Field(None, max_length=100)
    confirm_reset: bool = Field(True, description="Explicit confirmation flag required")


class LimitUsageResetOut(BaseModel):
    status: str
    entity_type: str
    entity_id: str
    target_identifier: str
    scope: str
    performed_by: str
    reason: str
    testing_reference: Optional[str] = None
    reset_at: datetime
    old_usage: Dict[str, float]
    new_usage: Dict[str, float]


class PanRoutingRuleCreate(BaseModel):
    rule_code: str = Field(..., min_length=2, max_length=40)
    rule_name: str = Field(..., min_length=2, max_length=140)
    description: Optional[str] = None
    priority: int = Field(10, ge=1, le=9999)
    pan_prefix: str = Field(..., min_length=4, max_length=12)
    pan_low: Optional[str] = None
    pan_high: Optional[str] = None
    pan_length: Optional[int] = Field(16, ge=12, le=19)
    card_type: Optional[str] = None
    transaction_code: Optional[str] = None
    acquirer_institution_id: Optional[str] = None
    issuer_institution_id: str
    processing_system_id: str
    destination_network: Optional[str] = "INTERNAL_SIMULATOR_TIC"
    scheme: str = "ITCL"
    is_on_us: bool = True
    pin_translation_required: bool = False
    source_key_id: Optional[str] = "AWK_ATM_01"
    destination_key_id: Optional[str] = "IWK_SW_01"
    enabled: bool = True
    status: str = "ACTIVE"


class PanRoutingRuleUpdate(BaseModel):
    rule_code: Optional[str] = None
    rule_name: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[int] = Field(None, ge=1, le=9999)
    pan_prefix: Optional[str] = None
    pan_low: Optional[str] = None
    pan_high: Optional[str] = None
    pan_length: Optional[int] = Field(None, ge=12, le=19)
    card_type: Optional[str] = None
    transaction_code: Optional[str] = None
    acquirer_institution_id: Optional[str] = None
    issuer_institution_id: Optional[str] = None
    processing_system_id: Optional[str] = None
    destination_network: Optional[str] = None
    scheme: Optional[str] = None
    is_on_us: Optional[bool] = None
    pin_translation_required: Optional[bool] = None
    source_key_id: Optional[str] = None
    destination_key_id: Optional[str] = None
    enabled: Optional[bool] = None
    status: Optional[str] = None


class PanRoutingRuleOut(BaseModel):
    id: str
    rule_code: str
    rule_name: str
    description: Optional[str] = None
    priority: int
    pan_prefix: str
    pan_low: str
    pan_high: str
    pan_length: Optional[int] = 16
    card_type: Optional[str] = None
    transaction_code: Optional[str] = None
    acquirer_institution_id: Optional[str] = None
    acquirer_institution_code: Optional[str] = None
    acquirer_institution_name: Optional[str] = None
    issuer_institution_id: str
    issuer_institution_code: Optional[str] = None
    issuer_institution_name: Optional[str] = None
    processing_system_id: str
    ps_code: Optional[str] = None
    ps_name: Optional[str] = None
    destination_network: Optional[str] = None
    scheme: str
    is_on_us: bool
    pin_translation_required: bool
    source_key_id: Optional[str] = None
    destination_key_id: Optional[str] = None
    enabled: bool
    status: str
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)

