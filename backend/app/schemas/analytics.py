from typing import Dict, List

from pydantic import BaseModel


class RiskDistribution(BaseModel):
    LOW: int = 0
    MEDIUM: int = 0
    HIGH: int = 0
    CRITICAL: int = 0


class TimeSeriesPoint(BaseModel):
    date: str
    total: int
    blocked: int
    high_risk: int


class FlagCount(BaseModel):
    flag: str
    count: int


class ModelUsage(BaseModel):
    model: str
    count: int


class TopRiskyUser(BaseModel):
    username: str
    department: str
    prompt_count: int
    avg_risk_score: float
    blocked_count: int


class AnalyticsOverview(BaseModel):
    model_config = {"protected_namespaces": ()}

    total_prompts: int
    blocked_prompts: int
    warned_prompts: int
    high_risk_prompts: int
    avg_risk_score: float
    compliance_score: float
    governance_score: float
    risk_distribution: RiskDistribution
    prompts_over_time: List[TimeSeriesPoint]
    top_flags: List[FlagCount]
    model_distribution: List[ModelUsage]
    top_risky_users: List[TopRiskyUser]
