import json
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.exceptions import not_found
from app.models.user import User
from app.schemas.chat import ChatMessageRead, ChatRequest
from app.services.application_service import get_application
from app.services.chat_service import (
    clear_chat_history,
    get_chat_history,
    stream_chat_response,
)

router = APIRouter(prefix="/applications/{application_id}/chat", tags=["chat"])


async def _get_user_application(
    application_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Dependency that verifies the user owns the application."""
    application = await get_application(db, current_user.id, application_id)
    if application is None:
        not_found("Application")
    return application


@router.get("", response_model=list[ChatMessageRead])
async def get_history(
    application_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ChatMessageRead]:
    application = await _get_user_application(application_id, current_user, db)
    messages = await get_chat_history(db, application.id)
    return [ChatMessageRead.model_validate(m) for m in messages]


@router.post("")
async def send_message(
    application_id: str,
    body: ChatRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    application = await _get_user_application(application_id, current_user, db)

    async def event_stream():
        try:
            async for chunk in stream_chat_response(db, application, body.content):
                data = json.dumps({"text": chunk})
                yield f"event: token\ndata: {data}\n\n"

            yield f"event: done\ndata: {json.dumps({'status': 'complete'})}\n\n"
        except Exception as e:
            error_data = json.dumps({"detail": str(e)})
            yield f"event: error\ndata: {error_data}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.delete("")
async def clear_history(
    application_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    application = await _get_user_application(application_id, current_user, db)
    await clear_chat_history(db, application.id)
    return {"message": "Chat history cleared."}
