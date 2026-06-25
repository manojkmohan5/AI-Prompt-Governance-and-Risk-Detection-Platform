import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ConditionType(str, enum.Enum):
    RISK_SCORE_ABOVE = "risk_score_above"
    FLAG_CONTAINS = "flag_contains"
    DEPARTMENT_IS = "department_is"
    ALWAYS = "always"


class ActionType(str, enum.Enum):
    ALLOW = "ALLOW"
    WARN = "WARN"
    REDACT = "REDACT"
    BLOCK = "BLOCK"


class PolicyRule(Base):
    __tablename__ = "policy_rules"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    condition_type: Mapped[ConditionType] = mapped_column(Enum(ConditionType, native_enum=False), nullable=False)
    condition_value: Mapped[str] = mapped_column(String(500), nullable=False)

    action: Mapped[ActionType] = mapped_column(Enum(ActionType, native_enum=False), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
