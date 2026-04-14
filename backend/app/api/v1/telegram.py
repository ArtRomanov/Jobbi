from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.telegram import ConnectionCodeResponse, TelegramStatus
from app.services.telegram_service import (
    create_connection_code,
    delete_user_link,
    get_user_link,
)

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.post(
    "/connection-code",
    response_model=ConnectionCodeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_connection_code(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConnectionCodeResponse:
    record = await create_connection_code(db, current_user.id)
    return ConnectionCodeResponse(code=record.code, expires_at=record.expires_at)


@router.get("/status", response_model=TelegramStatus)
async def get_status(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TelegramStatus:
    link = await get_user_link(db, current_user.id)
    if link is None:
        return TelegramStatus(connected=False)
    return TelegramStatus(
        connected=True,
        telegram_username=link.telegram_username,
        linked_at=link.linked_at,
    )


@router.delete("/link")
async def disconnect_telegram(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    await delete_user_link(db, current_user.id)
    return {"message": "Disconnected."}
