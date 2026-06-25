import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.prompt import PromptRecord
from app.models.user import User
from app.schemas.prompt import PromptListResponse, PromptResponse, PromptSubmit
from app.services import prompt_service

router = APIRouter(prefix="/prompts", tags=["prompts"])


@router.post("", response_model=PromptResponse, status_code=201)
async def submit_prompt(
    body: PromptSubmit,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    record = await prompt_service.process(
        prompt_text=body.prompt,
        user=user,
        model=body.model,
        department=body.department,
        db=db,
    )
    return PromptResponse.model_validate(record)


@router.get("", response_model=PromptListResponse)
async def list_prompts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    risk_level: Optional[str] = None,
    is_blocked: Optional[bool] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = select(PromptRecord)

    # Non-admins see only their own prompts
    if user.role.value == "employee":
        q = q.where(PromptRecord.user_id == user.id)

    if risk_level:
        q = q.where(PromptRecord.risk_level == risk_level.upper())
    if is_blocked is not None:
        q = q.where(PromptRecord.is_blocked == is_blocked)
    if search:
        q = q.where(PromptRecord.prompt_text.ilike(f"%{search}%"))

    count_q = select(func.count()).select_from(q.subquery())
    total_result = await db.execute(count_q)
    total = total_result.scalar() or 0

    q = q.order_by(PromptRecord.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(q)
    items = [PromptResponse.model_validate(r) for r in result.scalars().all()]

    return PromptListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{prompt_id}", response_model=PromptResponse)
async def get_prompt(
    prompt_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from fastapi import HTTPException
    result = await db.execute(select(PromptRecord).where(PromptRecord.id == prompt_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return PromptResponse.model_validate(record)
