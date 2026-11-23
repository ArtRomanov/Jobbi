import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.exceptions import not_found
from app.models.application import Application
from app.models.user import User
from app.schemas.chat import ChangeCardRead, ChatMessageRead, ChatRequest
from app.services.application_service import get_application
from app.services.chat_card_service import (
    CardError,
    CardNotFoundError,
    accept_card,
    cards_by_message,
    reject_card,
)
from app.services.chat_service import (
    CardsReady,
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
    cards = await cards_by_message(db, application.id)
    return [
        ChatMessageRead(
            id=m.id,
            application_id=m.application_id,
            role=m.role,
            content=m.content,
            created_at=m.created_at,
            cards=[ChangeCardRead.model_validate(c) for c in cards.get(m.id, [])],
        )
        for m in messages
    ]


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
            async for item in stream_chat_response(db, application, body.content):
                if isinstance(item, CardsReady):
                    cards = [
                        ChangeCardRead.model_validate(c).model_dump(mode="json")
                        for c in item.cards
                    ]
                    yield f"event: cards\ndata: {json.dumps(cards)}\n\n"
                    continue
                data = json.dumps({"text": item})
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


async def _decide_card(
    application: Application,
    card_id: str,
    db: AsyncSession,
    *,
    accept: bool,
) -> ChangeCardRead:
    try:
        if accept:
            card = await accept_card(db, application, card_id)
        else:
            card = await reject_card(db, application, card_id)
    except CardNotFoundError:
        not_found("Card")
    except CardError as e:
        raise HTTPException(status_code=e.status_code, detail=e.code) from e
    return ChangeCardRead.model_validate(card)


@router.post(
    "/cards/{card_id}/accept",
    response_model=ChangeCardRead,
    responses={
        404: {"description": "No such application or card for this user"},
        409: {"description": "CARD_DECIDED, CARD_STALE or PASSAGE_NOT_UNIQUE"},
        422: {"description": "TOO_LONG: the CV would exceed 20 000 characters"},
    },
)
async def accept_change_card(
    application_id: str,
    card_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ChangeCardRead:
    """Apply a pending CV change card to the linked CV (bumps the CV version)."""
    application = await _get_user_application(application_id, current_user, db)
    return await _decide_card(application, card_id, db, accept=True)


@router.post(
    "/cards/{card_id}/reject",
    response_model=ChangeCardRead,
    responses={
        404: {"description": "No such application or card for this user"},
        409: {"description": "CARD_DECIDED"},
    },
)
async def reject_change_card(
    application_id: str,
    card_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ChangeCardRead:
    """Reject a pending (or stale) CV change card; the CV is not touched."""
    application = await _get_user_application(application_id, current_user, db)
    return await _decide_card(application, card_id, db, accept=False)
