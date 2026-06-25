from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.core.database import get_db
from app.models.audit_log import AuditLog
from app.schemas.prompt import AuditLogOut

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=dict)
async def list_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    event_type: Optional[str] = None,
    username: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    q = select(AuditLog)

    if event_type:
        q = q.where(AuditLog.event_type == event_type)
    if username:
        q = q.where(AuditLog.username.ilike(f"%{username}%"))

    count_result = await db.execute(select(func.count()).select_from(q.subquery()))
    total = count_result.scalar() or 0

    q = q.order_by(AuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(q)
    items = [AuditLogOut.model_validate(r) for r in result.scalars().all()]

    return {"items": items, "total": total, "page": page, "page_size": page_size}
