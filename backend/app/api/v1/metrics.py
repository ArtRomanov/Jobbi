from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.metrics import MetricsResponse
from app.services.metrics_service import get_metrics

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("", response_model=MetricsResponse)
async def get_user_metrics(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    range: Literal["7d", "30d", "90d", "all"] = Query(default="30d"),
) -> MetricsResponse:
    data = await get_metrics(db, current_user.id, range)
    return MetricsResponse(**data)
