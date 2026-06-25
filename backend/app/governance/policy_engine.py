"""
Policy Enforcement Engine
Evaluates active policy rules and returns the strictest applicable action.
"""
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.policy_rule import ActionType, ConditionType, PolicyRule

# Action precedence (higher index = stricter)
_ACTION_RANK = {
    ActionType.ALLOW: 0,
    ActionType.WARN: 1,
    ActionType.REDACT: 2,
    ActionType.BLOCK: 3,
}


async def determine_action(
    risk_score: int,
    flags: List[str],
    department: str | None,
    db: AsyncSession,
) -> str:
    result = await db.execute(
        select(PolicyRule).where(PolicyRule.is_active == True).order_by(PolicyRule.priority.desc())
    )
    rules: List[PolicyRule] = list(result.scalars().all())

    chosen = ActionType.ALLOW

    for rule in rules:
        matched = False

        if rule.condition_type == ConditionType.ALWAYS:
            matched = True

        elif rule.condition_type == ConditionType.RISK_SCORE_ABOVE:
            try:
                threshold = int(rule.condition_value)
                matched = risk_score > threshold
            except ValueError:
                pass

        elif rule.condition_type == ConditionType.FLAG_CONTAINS:
            matched = rule.condition_value in flags

        elif rule.condition_type == ConditionType.DEPARTMENT_IS:
            matched = department == rule.condition_value

        if matched:
            candidate = ActionType(rule.action)
            if _ACTION_RANK[candidate] > _ACTION_RANK[chosen]:
                chosen = candidate

    return chosen.value
