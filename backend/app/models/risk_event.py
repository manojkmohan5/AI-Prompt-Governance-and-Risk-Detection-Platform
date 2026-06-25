import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RiskEventSeverity(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskEvent(Base):
    __tablename__ = "risk_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    prompt_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("prompts.id", ondelete="SET NULL"), nullable=True
    )

    risk_type: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[RiskEventSeverity] = mapped_column(Enum(RiskEventSeverity, native_enum=False), nullable=False)
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
