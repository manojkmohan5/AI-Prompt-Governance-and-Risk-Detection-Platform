from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


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
    name: str
    description: Optional[str] = None
    condition_type: str
    condition_value: str
    action: str
    priority: int = 0
    is_active: bool = True


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
