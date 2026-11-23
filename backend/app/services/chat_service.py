from collections.abc import AsyncIterator
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.chat_change_card import ChatChangeCard
from app.models.chat_message import ChatMessage
from app.models.cv import Cv
from app.services.chat_card_service import (
    add_cards,
    card_history_line,
    cards_by_message,
    delete_application_cards,
)
from app.services.chat_tools import (
    MALFORMED_CALL_NOTE,
    MAX_CARDS_PER_REPLY,
    PROPOSE_CV_EDIT_TOOL,
    CvEdit,
    parse_propose_cv_edit,
)
from app.services.groq_client import (
    LlmToolCall,
    build_system_prompt,
    stream_llm_response,
)


@dataclass(frozen=True, slots=True)
class CardsReady:
    """Sent once after the reply's text: the cards stored for this reply."""

    cards: list[ChatChangeCard]


async def get_chat_history(db: AsyncSession, application_id: str) -> list[ChatMessage]:
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.application_id == application_id)
        .order_by(ChatMessage.created_at.asc())
    )
    return list(result.scalars().all())


async def save_message(
    db: AsyncSession, application_id: str, role: str, content: str
) -> ChatMessage:
    message = ChatMessage(
        application_id=application_id,
        role=role,
        content=content,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message


async def clear_chat_history(db: AsyncSession, application_id: str) -> None:
    # No FK enforcement on SQLite: the cards go by hand, before their messages.
    await delete_application_cards(db, application_id)
    await db.execute(
        delete(ChatMessage).where(ChatMessage.application_id == application_id)
    )
    await db.commit()


async def get_application_context(
    db: AsyncSession, application: Application
) -> tuple[str, Application, Cv | None]:
    """Build system prompt from application + linked CV."""
    cv = None
    if application.cv_id:
        # Only the application owner's CV: a stale or forged link to another
        # user's CV must never reach the prompt.
        result = await db.execute(
            select(Cv).where(
                Cv.id == application.cv_id, Cv.user_id == application.user_id
            )
        )
        cv = result.scalar_one_or_none()

    system_prompt = build_system_prompt(application, cv)
    return system_prompt, application, cv


def build_llm_messages(
    history: list[ChatMessage], cards: dict[str, list[ChatChangeCard]]
) -> list[dict[str, str]]:
    """The chat history for the model; each card adds one line to its reply.

    Pending cards are listed too, so the model does not propose them again.
    """
    messages: list[dict[str, str]] = []
    for message in history:
        lines = [card_history_line(card) for card in cards.get(message.id, [])]
        content = "\n".join(part for part in (message.content, *lines) if part)
        if content:
            messages.append({"role": message.role, "content": content})
    return messages


def _validate_calls(calls: list[LlmToolCall]) -> tuple[list[CvEdit], int]:
    """Split the model's tool calls into usable edits and a failure count."""
    edits: list[CvEdit] = []
    failed = 0
    for call in calls:
        edit = parse_propose_cv_edit(call.name, call.arguments)
        if edit is None or len(edits) >= MAX_CARDS_PER_REPLY:
            failed += 1
        else:
            edits.append(edit)
    return edits, failed


async def stream_chat_response(
    db: AsyncSession,
    application: Application,
    user_content: str,
) -> AsyncIterator[str | CardsReady]:
    """Save the user message, stream the reply, then store its CV cards.

    Yields text chunks, then exactly one `CardsReady` (possibly empty) once the
    assistant message and its cards are saved. The model gets the
    `propose_cv_edit` tool only when the application has a CV linked (and
    owned by the same user).
    """
    await save_message(db, application.id, "user", user_content)

    system_prompt, _, cv = await get_application_context(db, application)

    history = await get_chat_history(db, application.id)
    messages = build_llm_messages(history, await cards_by_message(db, application.id))

    full_response: list[str] = []
    calls: list[LlmToolCall] = []
    tools = [PROPOSE_CV_EDIT_TOOL] if cv is not None else None
    async for item in stream_llm_response(system_prompt, messages, tools=tools):
        if isinstance(item, LlmToolCall):
            calls.append(item)
            continue
        full_response.append(item)
        yield item

    edits, failed = _validate_calls(calls) if cv is not None else ([], len(calls))
    if failed:
        # Each failed call becomes one inline line in the reply.
        separator = "\n\n" if full_response else ""
        note = separator + "\n".join([MALFORMED_CALL_NOTE] * failed)
        full_response.append(note)
        yield note

    assistant_content = "".join(full_response)
    cards: list[ChatChangeCard] = []
    if assistant_content or edits:
        message = ChatMessage(
            application_id=application.id, role="assistant", content=assistant_content
        )
        db.add(message)
        await db.flush()
        if cv is not None and edits:
            cards = add_cards(
                db,
                application_id=application.id,
                message_id=message.id,
                cv_id=cv.id,
                edits=edits,
            )
        await db.commit()
        for card in cards:
            await db.refresh(card)

    yield CardsReady(cards=cards)
