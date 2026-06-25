import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.core.database import get_db
from app.models.policy_rule import PolicyRule
from app.schemas.prompt import PolicyRuleCreate, PolicyRuleOut

router = APIRouter(prefix="/policies", tags=["policies"])


@router.get("", response_model=list[PolicyRuleOut])
async def list_policies(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    result = await db.execute(select(PolicyRule).order_by(PolicyRule.priority.desc()))
    return [PolicyRuleOut.model_validate(r) for r in result.scalars().all()]


@router.post("", response_model=PolicyRuleOut, status_code=201)
async def create_policy(
    body: PolicyRuleCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    rule = PolicyRule(**body.model_dump())
    db.add(rule)
    await db.flush()
    return PolicyRuleOut.model_validate(rule)


@router.patch("/{policy_id}/toggle", response_model=PolicyRuleOut)
async def toggle_policy(
    policy_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    result = await db.execute(select(PolicyRule).where(PolicyRule.id == policy_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Policy not found")
    rule.is_active = not rule.is_active
    await db.flush()
    return PolicyRuleOut.model_validate(rule)


@router.delete("/{policy_id}", status_code=204)
async def delete_policy(
    policy_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    result = await db.execute(select(PolicyRule).where(PolicyRule.id == policy_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Policy not found")
    await db.delete(rule)
