import json
from collections.abc import AsyncIterator
from typing import Annotated, Any

import structlog
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
    ReplyText,
    clear_chat_history,
    get_chat_history,
    stream_chat_response,
)

logger = structlog.get_logger()

STREAM_ERROR_DETAIL = "Something went wrong. Please try again."


def _cards_json(ready: CardsReady) -> list[dict[str, Any]]:
    """The cards as JSON, or [] if they cannot be serialized.

    They are already saved, so the client still gets them from the history
    reload that follows `done`.
    """
    try:
        return [
            ChangeCardRead.model_validate(c).model_dump(mode="json")
            for c in ready.cards
        ]
    # Broad on purpose: a saved reply must still end with `cards` + `done`.
    except Exception as e:  # noqa: BLE001 - logged by type; reply is saved
        logger.error("chat_cards_serialize_failed", error_type=type(e).__name__)
        return []


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

    async def event_stream() -> AsyncIterator[str]:
        try:
            async for item in stream_chat_response(db, application, body.content):
                if isinstance(item, CardsReady):
                    # The reply and its cards are committed by now: from here
                    # on the stream must end with `done`, never `error`.
                    yield f"event: cards\ndata: {json.dumps(_cards_json(item))}\n\n"
                    continue
                if isinstance(item, ReplyText):
                    # The whole reply as saved: replaces the text streamed so far.
                    data = json.dumps({"text": item.text})
                    yield f"event: reply\ndata: {data}\n\n"
                    continue
                data = json.dumps({"text": item})
                yield f"event: token\ndata: {data}\n\n"

            yield f"event: done\ndata: {json.dumps({'status': 'complete'})}\n\n"
        # Broad on purpose: any failure must end the stream with a frame the
        # client understands, and its text must not reach the client.
        except Exception as e:  # noqa: BLE001 - logged by type, never sent
            logger.error("chat_stream_failed", error_type=type(e).__name__)
            error_data = json.dumps({"detail": STREAM_ERROR_DETAIL})
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
        409: {
            "description": (
                "CARD_DECIDED, CARD_STALE, CARD_OUTDATED, PASSAGE_NOT_UNIQUE or CV_BUSY"
            )
        },
        422: {"description": "TOO_LONG: the CV would exceed 20 000 characters"},
    },
)
async def accept_change_card(
    application_id: str,
    card_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ChangeCardRead:
    """Apply a pending CV change card to the linked CV (bumps the CV version).

    409 codes: CARD_DECIDED (already accepted or rejected); CARD_STALE (the card
    is already stale, or the passage / CV is gone and the change cannot be
    re-aimed at the current text, and the card becomes stale);
    PASSAGE_NOT_UNIQUE (card stays pending); CV_BUSY (the CV kept changing
    during the Accept, card stays pending, try again); CARD_OUTDATED (a newer
    chat message exists: only the newest reply's cards can be decided).
    """
    application = await _get_user_application(application_id, current_user, db)
    return await _decide_card(application, card_id, db, accept=True)


@router.post(
    "/cards/{card_id}/reject",
    response_model=ChangeCardRead,
    responses={
        404: {"description": "No such application or card for this user"},
        409: {"description": "CARD_DECIDED or CARD_OUTDATED"},
    },
)
async def reject_change_card(
    application_id: str,
    card_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ChangeCardRead:
    """Reject a pending (or stale) CV change card; the CV is not touched.

    409 codes: CARD_DECIDED; CARD_OUTDATED (a newer chat message exists).
    """
    application = await _get_user_application(application_id, current_user, db)
    return await _decide_card(application, card_id, db, accept=False)
