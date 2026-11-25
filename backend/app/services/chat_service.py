import re
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

import structlog
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.application import Application
from app.models.chat_change_card import ChatChangeCard
from app.models.chat_message import ChatMessage
from app.models.cv import Cv
from app.services.chat_budget import (
    HISTORY_TRIMMED_NOTE,
    PROMPT_TOO_LARGE_DETAIL,
    RATE_LIMITED_DETAIL,
    ChatUserError,
    fixed_tokens,
    message_tokens,
    request_tokens,
)
from app.services.chat_card_service import (
    add_cards,
    card_history_note,
    cards_by_message,
    delete_application_cards,
)
from app.services.chat_guard_notes import (
    Language,
    mark_left_out_items,
    reply_language,
    unsupported_names_note,
)
from app.services.chat_tools import (
    MALFORMED_CALL_NOTE,
    MAX_CARDS_PER_REPLY,
    PROPOSE_CV_EDIT_TOOL,
    CvEdit,
    parse_propose_cv_edit,
)
from app.services.cv_fact_guard import unsupported_names
from app.services.groq_client import (
    LlmRateLimitError,
    LlmRequestTooLargeError,
    LlmToolCall,
    build_system_prompt,
    stream_llm_response,
)

logger = structlog.get_logger()


@dataclass(frozen=True, slots=True)
class CardsReady:
    """Sent once after the reply's text: the cards stored for this reply."""

    cards: list[ChatChangeCard]


@dataclass(frozen=True, slots=True)
class ReplyText:
    """Sent before `CardsReady` when the text already streamed was changed.

    `text` is the whole reply as saved; it replaces everything streamed so far.
    """

    text: str


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


def _latest_with_cards(
    history: Sequence[ChatMessage], cards: Mapping[str, list[ChatChangeCard]]
) -> str | None:
    return next((m.id for m in reversed(history) if cards.get(m.id)), None)


def _message_entries(
    message: ChatMessage, cards: Sequence[ChatChangeCard], *, quote_removed: bool
) -> list[dict[str, str]]:
    """One stored message as model messages: its text, then its card note."""
    entries: list[dict[str, str]] = []
    if message.content:
        entries.append({"role": message.role, "content": message.content})
    if cards:
        note = card_history_note(cards, quote_removed=quote_removed)
        entries.append({"role": "system", "content": note})
    return entries


def build_llm_messages(
    history: list[ChatMessage], cards: dict[str, list[ChatChangeCard]]
) -> list[dict[str, str]]:
    """The chat history for the model.

    A reply's cards go into a separate system note right after that reply,
    one line per card, so the model does not copy them into its own replies.
    Pending cards are listed too, so the model does not propose them again.
    The latest reply with cards also quotes, in full, the text its accepted
    cards took out, so the model can put it back on request.
    """
    latest = _latest_with_cards(history, cards)
    messages: list[dict[str, str]] = []
    for message in history:
        messages += _message_entries(
            message, cards.get(message.id, []), quote_removed=message.id == latest
        )
    return messages


def _kept_ids(history: Sequence[ChatMessage]) -> set[str]:
    """The messages the budget never drops: the latest user message and the
    last assistant reply (with its card notes)."""
    kept: set[str] = set()
    if history and history[-1].role == "user":
        kept.add(history[-1].id)
    if last_reply := next(
        (m for m in reversed(history) if m.role == "assistant"), None
    ):
        kept.add(last_reply.id)
    return kept


def fit_llm_messages(
    history: list[ChatMessage],
    cards: dict[str, list[ChatChangeCard]],
    *,
    system_prompt: str,
    tools: Sequence[dict[str, Any]] | None,
    budget: int,
    language: Language,
) -> list[dict[str, str]]:
    """`build_llm_messages`, trimmed so the whole request fits `budget` tokens.

    Over budget, it first leaves out the oldest messages (never the latest
    user message or the last assistant reply), then shortens the full quote of
    the latest reply's accepted cards to the one-line form. Raises
    `ChatUserError` if the request is still too large: the CV, the vacancy and
    the kept messages alone do not fit.
    """
    latest = _latest_with_cards(history, cards)
    entries = {
        m.id: _message_entries(m, cards.get(m.id, []), quote_removed=m.id == latest)
        for m in history
    }
    sizes = {m_id: sum(map(message_tokens, e)) for m_id, e in entries.items()}
    total = fixed_tokens(system_prompt, tools) + sum(sizes.values())
    kept = _kept_ids(history)
    dropped: set[str] = set()
    trim_note = {"role": "system", "content": HISTORY_TRIMMED_NOTE}
    for message in history:
        if total <= budget:
            break
        if message.id in kept:
            continue
        if not dropped:
            total += message_tokens(trim_note)
        dropped.add(message.id)
        total -= sizes[message.id]

    if total > budget and latest is not None and latest not in dropped:
        reply = next(m for m in history if m.id == latest)
        entries[latest] = _message_entries(reply, cards[latest], quote_removed=False)
        total += sum(map(message_tokens, entries[latest])) - sizes[latest]

    if total > budget:
        raise ChatUserError(
            PROMPT_TOO_LARGE_DETAIL[language], reason="prompt_over_budget"
        )
    if dropped:
        logger.info(
            "chat_history_trimmed",
            dropped_messages=len(dropped),
            estimated_tokens=total,
            budget=budget,
        )
    messages = [trim_note] if dropped else []
    for message in history:
        if message.id not in dropped:
            messages += entries[message.id]
    return messages


# A reply that "fetches" the CV, opens a sentence with a promise ("I'll
# shorten it…") or ends on a colon announced edits it never made: the model
# stopped after the text, with no tool call. A conditional promise ("Once you
# share the dates, I'll add it") does not open its sentence, so it is not one.
_IMAGINED_ACTION = re.compile(
    r"\b(?:fetch\w*|re-?pull\w*|re-?read\w*|re-?load\w*)\b|"
    r"\b(?:pull|load|check)(?:ing)? (?:up )?the (?:current |latest )?cv\b",
    re.IGNORECASE,
)
_PROMISE = re.compile(
    r"(?:^|[.!?:]\s+|\n\s*)(?:I'll|I will|Let me|I'm going to|I am going to|"
    r"Сейчас|Я сейчас)\b",
    re.IGNORECASE,
)
FOLLOW_UP_NUDGE = (
    "Your reply above proposed no CV edit. The CV block in the first system "
    "message is the current CV; you have no other tool and nothing to fetch. "
    "Now call propose_cv_edit once for each change the user asked for in "
    "their latest message, all in this reply. If no change was asked for, or "
    "a change cannot be made, say so in one sentence instead. Do not repeat "
    "your earlier text."
)


def drop_unsupported_edits(
    edits: list[CvEdit], *, cv: str, user_texts: list[str], job_post: str
) -> tuple[list[CvEdit], list[list[str]]]:
    """Leave out edits that add names the candidate never claimed.

    Returns the edits to keep and, per edit left out, its unsupported names.
    A name is supported when the CV or one of the user's messages mentions it
    (see `cv_fact_guard`).
    """
    kept: list[CvEdit] = []
    left_out: list[list[str]] = []
    for edit in edits:
        names = unsupported_names(
            edit.after_text, cv=cv, user_texts=user_texts, job_post=job_post
        )
        if names:
            left_out.append(names)
        else:
            kept.append(edit)
    return kept, left_out


def needs_follow_up(reply: str, calls: list[LlmToolCall]) -> bool:
    """The model ended its turn without the edits it announced.

    True when it made no tool call and its reply is empty, imagines a CV
    fetch, opens a sentence with a promise, or ends on a colon ("Here are the
    changes:").
    """
    if calls:
        return False
    text = reply.strip()
    return (
        not text
        or text.endswith(":")
        or bool(_IMAGINED_ACTION.search(text) or _PROMISE.search(text))
    )


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


async def _stream_follow_up(
    system_prompt: str,
    follow_up: list[dict[str, str]],
    tools: list[dict[str, Any]],
    reply: str,
    has_text: bool,
    calls: list[LlmToolCall],
) -> AsyncIterator[str]:
    """Stream the nudged second call; its tool calls are added to `calls`.

    A rate limit or size error here keeps the first reply: the follow-up
    request comes right after the first one, in the same per-minute quota.
    """
    separator = "\n\n" if has_text else ""
    # The reply announced edits: this time a tool call is required. An
    # empty reply announced nothing, so the model may still just answer.
    tool_choice: Literal["auto", "required"] = "required" if reply else "auto"
    try:
        async for item in stream_llm_response(
            system_prompt, follow_up, tools=tools, tool_choice=tool_choice
        ):
            if isinstance(item, LlmToolCall):
                calls.append(item)
                continue
            chunk = separator + item
            separator = ""
            yield chunk
    except (LlmRateLimitError, LlmRequestTooLargeError) as e:
        logger.warning("chat_follow_up_failed", error_type=type(e).__name__)


async def stream_chat_response(
    db: AsyncSession,
    application: Application,
    user_content: str,
) -> AsyncIterator[str | ReplyText | CardsReady]:
    """Save the user message, stream the reply, then store its CV cards.

    Yields text chunks, at most one `ReplyText` (the fact guard marked an item
    of the text already streamed), then exactly one `CardsReady` (possibly
    empty) once the assistant message and its cards are saved. The model gets the
    `propose_cv_edit` tool only when the application has a CV linked (and
    owned by the same user).

    If anything fails before the reply is stored, the user message is deleted
    again and the error re-raised: a failed send leaves no trace in the
    history (the client puts the text back into its input box).
    """
    user_message = await save_message(db, application.id, "user", user_content)
    user_message_id = user_message.id
    reply_stored = False
    try:
        async for item in _stream_reply(db, application, user_content):
            # `CardsReady` comes only after the reply's commit.
            reply_stored = reply_stored or isinstance(item, CardsReady)
            yield item
    except Exception:
        if not reply_stored:
            await _discard_user_message(db, user_message_id)
        raise


async def _discard_user_message(db: AsyncSession, message_id: str) -> None:
    """Delete the user message of a failed send; never raises over the cause."""
    try:
        await db.rollback()
        await db.execute(delete(ChatMessage).where(ChatMessage.id == message_id))
        await db.commit()
    except SQLAlchemyError as e:
        logger.error("chat_user_message_discard_failed", error_type=type(e).__name__)


async def _stream_reply(
    db: AsyncSession,
    application: Application,
    user_content: str,
) -> AsyncIterator[str | ReplyText | CardsReady]:
    """The part of `stream_chat_response` after the user message is saved.

    Any exception it raises comes before the assistant reply is committed: the
    commit is its last step before the final `CardsReady`.
    """
    system_prompt, _, cv = await get_application_context(db, application)
    language = reply_language(user_content)
    budget = get_settings().CHAT_INPUT_TOKEN_BUDGET

    history = await get_chat_history(db, application.id)
    tools = [PROPOSE_CV_EDIT_TOOL] if cv is not None else None
    messages = fit_llm_messages(
        history,
        await cards_by_message(db, application.id),
        system_prompt=system_prompt,
        tools=tools,
        budget=budget,
        language=language,
    )

    full_response: list[str] = []
    calls: list[LlmToolCall] = []
    try:
        async for item in stream_llm_response(system_prompt, messages, tools=tools):
            if isinstance(item, LlmToolCall):
                calls.append(item)
                continue
            full_response.append(item)
            yield item
    except LlmRequestTooLargeError as e:
        # The estimate let through a request Groq still found too large.
        raise ChatUserError(
            PROMPT_TOO_LARGE_DETAIL[language], reason="groq_request_too_large"
        ) from e
    except LlmRateLimitError as e:
        raise ChatUserError(
            RATE_LIMITED_DETAIL[language], reason="groq_rate_limit"
        ) from e

    if tools and needs_follow_up("".join(full_response), calls):
        # One nudge, never more: the model announced edits but made none.
        # It reuses the trimmed messages, and is skipped if it would not fit.
        follow_up = [*messages]
        if reply := "".join(full_response).strip():
            follow_up.append({"role": "assistant", "content": reply})
        follow_up.append({"role": "system", "content": FOLLOW_UP_NUDGE})
        estimate = request_tokens(system_prompt, follow_up, tools)
        if estimate > budget:
            logger.info(
                "chat_follow_up_skipped", estimated_tokens=estimate, budget=budget
            )
        else:
            async for chunk in _stream_follow_up(
                system_prompt, follow_up, tools, reply, bool(full_response), calls
            ):
                full_response.append(chunk)
                yield chunk

    edits, failed = _validate_calls(calls) if cv is not None else ([], len(calls))
    left_out: list[list[str]] = []
    if cv is not None and edits:
        edits, left_out = drop_unsupported_edits(
            edits,
            cv=cv.content,
            user_texts=[m.content for m in history if m.role == "user"],
            job_post=application.notes or "",
        )
    notes = [MALFORMED_CALL_NOTE] * failed + [
        unsupported_names_note(names, language) for names in left_out
    ]
    streamed = "".join(full_response)
    marked = mark_left_out_items(streamed, left_out, language)
    note = ""
    if notes:
        # Each failed or left-out call becomes one line under the reply.
        note = ("\n\n" if streamed else "") + "\n".join(notes)
    if marked != streamed:
        # The text on screen announced a left-out edit: replace it as a whole.
        yield ReplyText(text=marked + note)
    elif note:
        yield note

    assistant_content = marked + note
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
        # Every card field is set in Python (id at flush), so the cards are
        # sent as they are: no refresh after the commit that could fail and
        # turn a saved reply into a stream error.
        await db.commit()

    yield CardsReady(cards=cards)
