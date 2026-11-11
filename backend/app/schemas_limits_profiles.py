"""
schemas_limits_profiles.py — Pydantic v2 Validation Schemas for:
  - Card & Account Limit Definitions (Module 1 & 2)
  - Card Profile Extensions & BIN-to-Card-Profile Assignments (Module 3)
  - Authorization Profiles, Allowed Transactions, Limit Assignments, and
    Transaction-Code Limit Impact Rules (Module 4)
  - Structured Limit Evaluation Results (Module 6 & 11)
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

VALID_SCOPES = {"CARD", "ACCOUNT"}
VALID_OPERATORS = {">", "<", ">=", "<=", "=", "!="}
VALID_CALC_METHODS = {
    "COUNT_TRANSACTION",
    "SUM_TRANSACTION_AMOUNT",
    "MAX_SINGLE_TRANSACTION",
    "MIN_SINGLE_TRANSACTION",
    "SUM_CASH_WITHDRAWAL",
    "SUM_PURCHASE",
    "SUM_TRANSFER",
    "CUSTOM_SUPPORTED_AGGREGATION",
}
VALID_RESET_INTERVALS = {
    "DAILY",
    "WEEKLY",
    "MONTHLY",
    "YEARLY",
    "PER_TRANSACTION",
    "CUSTOM_HOURS",
}
VALID_IMPACT_ACTIONS = {"DECLINE", "APPROVE_WITH_ALERT", "FLAG_REVIEW"}
VALID_IMPACT_TYPES = {"INCREASE", "DECREASE", "NO_IMPACT"}
VALID_CALC_BASIS = {"TRANSACTION_AMOUNT", "BILLING_AMOUNT", "TRANSACTION_COUNT", "FIXED_UNIT"}


# ------------------------------------------------------------------------------
# MODULE 1 & 2: CARD & ACCOUNT LIMIT DEFINITIONS
# ------------------------------------------------------------------------------

class LimitDefinitionBase(BaseModel):
    limit_code: str = Field(..., min_length=1, max_length=40, description="Unique configurable Limit ID, e.g. 100 or 200")
    limit_name: str = Field(..., min_length=2, max_length=120)
    description: Optional[str] = None
    scope: str = Field("CARD", description="CARD or ACCOUNT")
    currency: str = Field("BDT", min_length=3, max_length=3)
    maximum_limit: Decimal = Field(..., ge=Decimal("0.00"))
    reset_interval: str = Field("DAILY")
    reset_interval_hours: Optional[int] = Field(None, ge=1, le=8760)
    reset_anchor_time: str = Field("00:00")
    calculation_method: str = Field("SUM_TRANSACTION_AMOUNT")
    custom_aggregation_filter: Optional[Dict[str, Any]] = None
    comparison_operator: str = Field(">")
    impact_action: str = Field("DECLINE")
    decline_response_code: str = Field("61", min_length=2, max_length=5)
    institution_id: Optional[str] = None
    status: str = Field("ACTIVE")

    @field_validator("scope")
    @classmethod
    def validate_scope(cls, v: str) -> str:
        val = (v or "").upper().strip()
        if val not in VALID_SCOPES:
            raise ValueError(f"scope must be one of {sorted(VALID_SCOPES)}")
        return val

    @field_validator("comparison_operator")
    @classmethod
    def validate_operator(cls, v: str) -> str:
        val = (v or "").strip()
        if val == "==":
            val = "="
        if val not in VALID_OPERATORS:
            raise ValueError(f"comparison_operator must be one of {sorted(VALID_OPERATORS)}")
        return val

    @field_validator("calculation_method")
    @classmethod
    def validate_calc_method(cls, v: str) -> str:
        val = (v or "").upper().strip()
        if val not in VALID_CALC_METHODS:
            raise ValueError(f"calculation_method must be one of {sorted(VALID_CALC_METHODS)}")
        return val

    @field_validator("reset_interval")
    @classmethod
    def validate_reset(cls, v: str) -> str:
        val = (v or "").upper().strip()
        if val not in VALID_RESET_INTERVALS:
            raise ValueError(f"reset_interval must be one of {sorted(VALID_RESET_INTERVALS)}")
        return val

    @field_validator("impact_action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        val = (v or "").upper().strip()
        if val not in VALID_IMPACT_ACTIONS:
            raise ValueError(f"impact_action must be one of {sorted(VALID_IMPACT_ACTIONS)}")
        return val


class LimitDefinitionCreate(LimitDefinitionBase):
    pass


class LimitDefinitionUpdate(BaseModel):
    limit_name: Optional[str] = None
    description: Optional[str] = None
    currency: Optional[str] = None
    maximum_limit: Optional[Decimal] = Field(None, ge=Decimal("0.00"))
    reset_interval: Optional[str] = None
    reset_interval_hours: Optional[int] = None
    reset_anchor_time: Optional[str] = None
    calculation_method: Optional[str] = None
    custom_aggregation_filter: Optional[Dict[str, Any]] = None
    comparison_operator: Optional[str] = None
    impact_action: Optional[str] = None
    decline_response_code: Optional[str] = None
    institution_id: Optional[str] = None
    status: Optional[str] = None

    @field_validator("comparison_operator")
    @classmethod
    def validate_op_opt(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        val = v.strip()
        if val == "==":
            val = "="
        if val not in VALID_OPERATORS:
            raise ValueError(f"comparison_operator must be one of {sorted(VALID_OPERATORS)}")
        return val

    @field_validator("calculation_method")
    @classmethod
    def validate_cm_opt(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        val = v.upper().strip()
        if val not in VALID_CALC_METHODS:
            raise ValueError(f"calculation_method must be one of {sorted(VALID_CALC_METHODS)}")
        return val

    @field_validator("reset_interval")
    @classmethod
    def validate_ri_opt(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        val = v.upper().strip()
        if val not in VALID_RESET_INTERVALS:
            raise ValueError(f"reset_interval must be one of {sorted(VALID_RESET_INTERVALS)}")
        return val


class LimitDefinitionOut(LimitDefinitionBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    current_value: Decimal = Decimal("0.00")
    assigned_profiles_count: int = 0
    historical_usage_count: int = 0
    institution_code: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ------------------------------------------------------------------------------
# MODULE 3: BIN-TO-CARD-PROFILE ASSIGNMENT
# ------------------------------------------------------------------------------

class BinCardProfileAssignRequest(BaseModel):
    card_profile_id: Optional[str] = Field(
        None,
        description="Card Profile ID to associate with this BIN range (or null to unassign)",
    )


# ------------------------------------------------------------------------------
# MODULE 4: AUTHORIZATION PROFILES & TABS A, B, C, D
# ------------------------------------------------------------------------------

class AuthProfileTxPermissionCreate(BaseModel):
    transaction_code: str = Field(..., min_length=1, max_length=20)
    transaction_name: Optional[str] = None
    permission: str = Field("ALLOWED", description="ALLOWED or DISALLOWED")
    decline_response_code: str = Field("57", min_length=2, max_length=5)
    description: Optional[str] = None
    status: str = Field("ACTIVE")

    @field_validator("permission")
    @classmethod
    def validate_perm(cls, v: str) -> str:
        val = (v or "").upper().strip()
        if val not in {"ALLOWED", "DISALLOWED"}:
            raise ValueError("permission must be ALLOWED or DISALLOWED")
        return val


class AuthProfileTxPermissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    authorization_profile_id: str
    transaction_code_id: Optional[str] = None
    transaction_code: str
    transaction_name: str
    permission: str
    decline_response_code: str
    description: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None


class AuthProfileLimitAssignmentCreate(BaseModel):
    limit_definition_id: str
    scope: Optional[str] = None
    maximum_limit_override: Optional[Decimal] = Field(None, ge=Decimal("0.00"))
    calculation_method_override: Optional[str] = None
    comparison_operator_override: Optional[str] = None
    impact_action_override: Optional[str] = None
    decline_response_code_override: Optional[str] = None
    evaluation_priority: int = Field(10, ge=1, le=9999)
    status: str = Field("ACTIVE")


class AuthProfileLimitAssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    authorization_profile_id: str
    limit_definition_id: str
    limit_code: Optional[str] = None
    limit_name: Optional[str] = None
    scope: str
    effective_maximum_limit: Decimal = Decimal("0.00")
    maximum_limit_override: Optional[Decimal] = None
    effective_calculation_method: Optional[str] = None
    calculation_method_override: Optional[str] = None
    effective_comparison_operator: Optional[str] = None
    comparison_operator_override: Optional[str] = None
    effective_impact_action: Optional[str] = None
    impact_action_override: Optional[str] = None
    decline_response_code_override: Optional[str] = None
    reset_interval: Optional[str] = None
    current_value: Decimal = Decimal("0.00")
    evaluation_priority: int
    status: str
    created_at: Optional[datetime] = None


class TxCodeLimitImpactCreate(BaseModel):
    transaction_code: str = Field(..., min_length=1, max_length=20)
    limit_definition_id: str
    impact_type: str = Field("INCREASE", description="INCREASE, DECREASE, or NO_IMPACT")
    calculation_basis: str = Field("TRANSACTION_AMOUNT")
    multiplier: Decimal = Field(Decimal("1.0000"), ge=Decimal("0.0000"))
    description: Optional[str] = None
    status: str = Field("ACTIVE")

    @field_validator("impact_type")
    @classmethod
    def validate_impact_type(cls, v: str) -> str:
        val = (v or "").upper().strip()
        if val not in VALID_IMPACT_TYPES:
            raise ValueError(f"impact_type must be one of {sorted(VALID_IMPACT_TYPES)}")
        return val

    @field_validator("calculation_basis")
    @classmethod
    def validate_basis(cls, v: str) -> str:
        val = (v or "").upper().strip()
        if val not in VALID_CALC_BASIS:
            raise ValueError(f"calculation_basis must be one of {sorted(VALID_CALC_BASIS)}")
        return val


class TxCodeLimitImpactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    authorization_profile_id: Optional[str] = None
    transaction_code: str
    transaction_name: Optional[str] = None
    limit_definition_id: str
    limit_code: Optional[str] = None
    limit_name: Optional[str] = None
    limit_scope: Optional[str] = None
    impact_type: str
    calculation_basis: str
    multiplier: Decimal
    description: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None


class AuthorizationProfileCreate(BaseModel):
    auth_profile_code: str = Field(..., min_length=2, max_length=50)
    profile_name: str = Field(..., min_length=2, max_length=120)
    description: Optional[str] = None
    card_profile_id: Optional[str] = None
    institution_id: Optional[str] = None
    unconfigured_tx_code_policy: str = Field("REJECT", description="REJECT or ALLOW")
    unconfigured_decline_rc: str = Field("57", min_length=2, max_length=5)
    status: str = Field("ACTIVE")
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None


class AuthorizationProfileUpdate(BaseModel):
    profile_name: Optional[str] = None
    description: Optional[str] = None
    card_profile_id: Optional[str] = None
    institution_id: Optional[str] = None
    unconfigured_tx_code_policy: Optional[str] = None
    unconfigured_decline_rc: Optional[str] = None
    status: Optional[str] = None
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None


class AuthorizationProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    auth_profile_code: str
    profile_name: str
    description: Optional[str] = None
    card_profile_id: Optional[str] = None
    card_profile_code: Optional[str] = None
    card_profile_name: Optional[str] = None
    institution_id: Optional[str] = None
    institution_code: Optional[str] = None
    institution_name: Optional[str] = None
    unconfigured_tx_code_policy: str
    unconfigured_decline_rc: str
    status: str
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    tx_permissions: List[AuthProfileTxPermissionOut] = []
    card_limits: List[AuthProfileLimitAssignmentOut] = []
    account_limits: List[AuthProfileLimitAssignmentOut] = []
    tx_code_impacts: List[TxCodeLimitImpactOut] = []


# ------------------------------------------------------------------------------
# MODULE 6 & 11: STRUCTURED LIMIT EVALUATION RESULT
# ------------------------------------------------------------------------------

class LimitEvaluationItemResult(BaseModel):
    limit_id: str
    limit_code: str
    limit_name: str
    scope: str  # CARD | ACCOUNT
    target_entity_id: str
    reset_interval: str
    window_key: str
    calculation_method: str
    maximum_value: Decimal
    previous_usage: Decimal
    transaction_impact: Decimal
    projected_usage: Decimal
    comparison_operator: str
    condition_expression: str
    comparison_result: bool
    authorization_action: str
    final_result: str  # PASSED | DECLINED | ALERT
    response_code: str
    decline_reason: Optional[str] = None
