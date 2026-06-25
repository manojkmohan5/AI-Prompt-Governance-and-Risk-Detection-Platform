"""
Per-user anomaly detection using Z-score on rolling risk baseline.
Flags when a user's current prompt risk significantly exceeds their historical average.
Requires at least 5 previous prompts to compute a meaningful baseline.
"""
import math
from typing import Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prompt import PromptRecord
from app.models.user import User

WINDOW      = 20    # number of prior prompts used for baseline
Z_THRESHOLD = 2.0   # standard deviations above baseline to trigger flag


async def check(
    user: Optional[User],
    current_score: int,
    db: AsyncSession,
) -> Tuple[bool, Optional[float], Optional[float]]:
    """
    Returns (is_anomaly, z_score, baseline_avg).
    Returns (False, None, None) if not enough history.
    """
    if user is None:
        return False, None, None

    result = await db.execute(
        select(PromptRecord.risk_score)
        .where(PromptRecord.user_id == user.id)
        .order_by(PromptRecord.created_at.desc())
        .limit(WINDOW)
    )
    scores = [row[0] for row in result.fetchall()]

    if len(scores) < 5:
        return False, None, None

    mean     = sum(scores) / len(scores)
    variance = sum((s - mean) ** 2 for s in scores) / len(scores)
    std      = math.sqrt(variance)

    if std < 1.0:
        # Nearly zero variance — user always sends safe prompts
        # Only flag if the current score is dramatically higher
        if current_score >= 60:
            return True, round((current_score - mean) / max(std, 1.0), 2), round(mean, 1)
        return False, None, round(mean, 1)

    z = (current_score - mean) / std
    return z >= Z_THRESHOLD, round(z, 2), round(mean, 1)
