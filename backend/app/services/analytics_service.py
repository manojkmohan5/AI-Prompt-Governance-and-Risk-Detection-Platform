"""
Analytics Service – aggregates governance metrics for the dashboard.
"""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import List

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prompt import PolicyAction, PromptRecord, RiskLevel
from app.schemas.analytics import (
    AnalyticsOverview,
    FlagCount,
    ModelUsage,
    RiskDistribution,
    TimeSeriesPoint,
    TopRiskyUser,
)


async def get_overview(db: AsyncSession, days: int = 30) -> AnalyticsOverview:
    since = datetime.now(timezone.utc) - timedelta(days=days)

    result = await db.execute(
        select(PromptRecord).where(PromptRecord.created_at >= since)
    )
    prompts: List[PromptRecord] = list(result.scalars().all())

    total = len(prompts)
    blocked = sum(1 for p in prompts if p.is_blocked)
    warned = sum(1 for p in prompts if p.policy_action == PolicyAction.WARN.value)
    high_risk = sum(1 for p in prompts if p.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL))
    avg_risk = round(sum(p.risk_score for p in prompts) / total, 1) if total else 0.0

    compliance_score = round(((total - blocked) / total * 100) if total else 100.0, 1)
    governance_score = round(max(0, 100 - avg_risk), 1)

    # Risk distribution
    risk_dist = RiskDistribution()
    for p in prompts:
        setattr(risk_dist, p.risk_level.value, getattr(risk_dist, p.risk_level.value) + 1)

    # Time series (last `days` days)
    daily: dict = defaultdict(lambda: {"total": 0, "blocked": 0, "high_risk": 0})
    for p in prompts:
        day = p.created_at.strftime("%Y-%m-%d")
        daily[day]["total"] += 1
        if p.is_blocked:
            daily[day]["blocked"] += 1
        if p.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            daily[day]["high_risk"] += 1

    time_series = []
    for i in range(days):
        d = (datetime.now(timezone.utc) - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
        entry = daily.get(d, {"total": 0, "blocked": 0, "high_risk": 0})
        time_series.append(TimeSeriesPoint(date=d, **entry))

    # Top flags
    flag_counter: Counter = Counter()
    for p in prompts:
        for flag in (p.flags or []):
            flag_counter[flag] += 1
    top_flags = [FlagCount(flag=f, count=c) for f, c in flag_counter.most_common(10)]

    # Model distribution
    model_counter: Counter = Counter(p.model_used for p in prompts)
    model_dist = [ModelUsage(model=m, count=c) for m, c in model_counter.most_common()]

    # Top risky users
    user_stats: dict = defaultdict(lambda: {"count": 0, "total_risk": 0, "blocked": 0, "dept": ""})
    for p in prompts:
        u = p.username or "anonymous"
        user_stats[u]["count"] += 1
        user_stats[u]["total_risk"] += p.risk_score
        user_stats[u]["blocked"] += int(p.is_blocked)
        user_stats[u]["dept"] = p.department or ""

    top_users = sorted(user_stats.items(), key=lambda x: x[1]["total_risk"] / max(x[1]["count"], 1), reverse=True)[:5]
    top_risky = [
        TopRiskyUser(
            username=u,
            department=stats["dept"],
            prompt_count=stats["count"],
            avg_risk_score=round(stats["total_risk"] / stats["count"], 1),
            blocked_count=stats["blocked"],
        )
        for u, stats in top_users
    ]

    return AnalyticsOverview(
        total_prompts=total,
        blocked_prompts=blocked,
        warned_prompts=warned,
        high_risk_prompts=high_risk,
        avg_risk_score=avg_risk,
        compliance_score=compliance_score,
        governance_score=governance_score,
        risk_distribution=risk_dist,
        prompts_over_time=time_series,
        top_flags=top_flags,
        model_distribution=model_dist,
        top_risky_users=top_risky,
    )
