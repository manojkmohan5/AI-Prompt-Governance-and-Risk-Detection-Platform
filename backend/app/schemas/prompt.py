from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.governance.policy_engine import POLICY_FLAGS
from app.models.policy_rule import ActionType, ConditionType


class PromptSubmit(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=10000)
    model: str = "llama-3.3-70b-versatile"
    department: Optional[str] = None


class PromptResponse(BaseModel):
    model_config = {"protected_namespaces": (), "from_attributes": True}

    id: UUID
    prompt_text: str
    redacted_prompt: Optional[str]
    response_text: Optional[str]
    model_used: str
    department: Optional[str]
    username: Optional[str]
    risk_score: int
    risk_level: str
    flags: Optional[List[str]]
    policy_action: str
    is_blocked: bool
    tokens_used: Optional[int]
    latency_ms: Optional[int]
    knowledge_shield_score: Optional[float]
    ml_risk_category: Optional[str]
    ml_confidence: Optional[float]
    compliance_tags: Optional[List[str]]
    anomaly_detected: Optional[bool]
    anomaly_z_score: Optional[float]
    created_at: datetime


class PromptListResponse(BaseModel):
    items: List[PromptResponse]
    total: int
    page: int
    page_size: int


class PolicyRuleOut(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    condition_type: str
    condition_value: str
    action: str
    priority: int
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class PolicyRuleCreate(BaseModel):
    """
    A new policy rule, validated before it can reach the database.

    These were plain strings. A rule saved with a typo ("BLCOK") could not be
    loaded back: the policy engine reads every active rule on every prompt, so
    one bad rule failed every prompt, and GET /policies failed too - leaving no
    way to remove it from the UI.
    """
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    condition_type: ConditionType
    condition_value: str = ""
    action: ActionType
    priority: int = Field(0, ge=0, le=1000)
    is_active: bool = True

    @model_validator(mode="after")
    def _value_fits_the_condition(self):
        value = self.condition_value.strip()
        if self.condition_type == ConditionType.FLAG_CONTAINS:
            if value not in POLICY_FLAGS:
                raise ValueError(
                    f"'{value}' is not a flag a rule can match. Use one of: "
                    f"{', '.join(sorted(POLICY_FLAGS))}."
                )
        elif self.condition_type == ConditionType.RISK_SCORE_ABOVE:
            if not value.isdigit() or not 0 <= int(value) <= 100:
                raise ValueError("A risk-score rule needs a whole number from 0 to 100.")
        elif self.condition_type == ConditionType.DEPARTMENT_IS:
            if not value:
                raise ValueError("A department rule needs a department name.")
        self.condition_value = value
        return self


class AuditLogOut(BaseModel):
    id: UUID
    prompt_id: Optional[UUID]
    user_id: Optional[UUID]
    event_type: str
    event_data: Optional[dict]
    username: Optional[str]
    department: Optional[str]
    ip_address: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class ConfidentialDocCreate(BaseModel):
    name: str
    content: str
    category: str = "general"


class ConfidentialDocOut(BaseModel):
    id: UUID
    name: str
    category: str
    created_at: datetime

    model_config = {"from_attributes": True}
