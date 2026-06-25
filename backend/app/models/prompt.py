import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RiskLevel(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class PolicyAction(str, enum.Enum):
    ALLOW = "ALLOW"
    WARN = "WARN"
    REDACT = "REDACT"
    BLOCK = "BLOCK"


class PromptRecord(Base):
    __tablename__ = "prompts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    redacted_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    response_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    model_used: Mapped[str] = mapped_column(String(100), default="llama-3.3-70b-versatile")
    department: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    risk_level: Mapped[RiskLevel] = mapped_column(Enum(RiskLevel, native_enum=False), default=RiskLevel.LOW)
    flags: Mapped[Optional[list]] = mapped_column(JSON, default=list)

    policy_action: Mapped[PolicyAction] = mapped_column(Enum(PolicyAction, native_enum=False), default=PolicyAction.ALLOW)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)

    tokens_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    knowledge_shield_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # ML classification
    ml_risk_category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    ml_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Compliance framework tags derived from flags
    compliance_tags: Mapped[Optional[list]] = mapped_column(JSON, default=list)

    # Anomaly detection
    anomaly_detected: Mapped[bool] = mapped_column(Boolean, default=False)
    anomaly_z_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
