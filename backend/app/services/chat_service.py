import re
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
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
    input_budget,
    message_tokens,
    reply_tokens,
    request_tokens,
    retry_limit,
    with_margin,
)
from app.services.chat_card_service import (
    add_cards,
    card_history_note,
    cards_by_message,
    delete_application_cards,
    place_edit,
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
    PASSAGE_NOT_FOUND_NOTE,
    PROPOSE_CV_EDIT_TOOL,
    REJECTED_CALLS_NOTE,
    CallRejection,
    CvEdit,
    check_propose_cv_edit,
)
from app.services.cv_fact_guard import unsupported_names
from app.services.cv_structure import (
    Problem,
    repair_problems_text,
    structure_warning,
    unrequested_problems,
)
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
# After a newline only spaces/tabs are skipped: `\n\s*` restarted a scan of
# the whole whitespace run at every newline in it (quadratic on the model's
# reply, seconds of CPU on the event loop). The last newline of a blank-line
# run still matches, so a promise after blank lines is still found.
_PROMISE = re.compile(
    r"(?:^|[.!?:]\s+|\n[ \t]*)(?:I'll|I will|Let me|I'm going to|I am going to|"
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


_RETRY_NUDGE = (
    "Your propose_cv_edit calls above were rejected, so none of them reached "
    "the user. The error was: {error}\n"
    "Make the same edits again, one propose_cv_edit call per edit, with valid "
    'arguments: `op` is exactly "replace", "insert" or "remove". replace: '
    "`before` and `after`. remove: `before`. insert: `after` and `position`, "
    'exactly "start", "end" or "after_line" (with after_line also `anchor`). '
    "Leave out the fields an op does not use. Do not repeat your earlier text."
)


def retry_nudge(rejection: str) -> str:
    """The system message for the one retry after Groq's `tool_use_failed`."""
    return _RETRY_NUDGE.format(error=rejection)


def parse_retry_nudge(rejections: Sequence[CallRejection]) -> str:
    """The retry nudge when our parser rejected every call of the reply.

    The error names only the rule each call broke (field and error type),
    never the model's argument values.
    """
    lines = [f"call {i}: {r.summary()}" for i, r in enumerate(rejections, 1)]
    return retry_nudge("; ".join(lines))


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


def place_edits(cv: str, edits: Sequence[CvEdit]) -> tuple[list[CvEdit], int]:
    """The edits Accept can apply, quotes made exact, and how many were dropped.

    A quote that differs from the CV only in whitespace (a hard-wrapped
    paragraph quoted with spaces) is rewritten to the exact CV text, so the
    structure check and the stored card see the real passage. An edit whose
    passage is not in the CV at all is dropped (`place_edit`).
    """
    placed: list[CvEdit] = []
    for edit in edits:
        if (fixed := place_edit(cv, edit)) is not None:
            placed.append(fixed)
    return placed, len(edits) - len(placed)


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


def _validate_calls(
    calls: list[LlmToolCall],
) -> tuple[list[CvEdit], list[CallRejection]]:
    """Split the model's tool calls into usable edits and rejections.

    Each rejection is logged once, with the call's shape only (see
    `CallRejection`): never CV text or argument values.
    """
    edits: list[CvEdit] = []
    rejections: list[CallRejection] = []
    for call in calls:
        result = check_propose_cv_edit(call.name, call.arguments)
        if isinstance(result, CvEdit) and len(edits) >= MAX_CARDS_PER_REPLY:
            result = CallRejection(reason="over_card_limit")
        if isinstance(result, CvEdit):
            edits.append(result)
            continue
        _log_rejection(result)
        rejections.append(result)
    return edits, rejections


def _log_rejection(rejection: CallRejection) -> None:
    logger.warning(
        "chat_tool_call_rejected", reason=rejection.reason, **rejection.log_fields
    )


def _all_parser_rejected(calls: list[LlmToolCall]) -> list[CallRejection] | None:
    """The rejections when the reply has calls and our parser rejects them all.

    Checked without logging: the caller logs them if it acts on them.
    """
    if not calls or any(c.rejected is not None for c in calls):
        return None
    results = [check_propose_cv_edit(c.name, c.arguments) for c in calls]
    rejections = [r for r in results if isinstance(r, CallRejection)]
    return rejections if len(rejections) == len(results) else None


# Messages trimmed to fit an input budget (Python 3.11: no `type` statement).
BuildMessages = Callable[[int], list[dict[str, str]]]


@dataclass(slots=True)
class _Turn:
    """Request sizing shared by the calls of one chat turn.

    `limit` starts at `CHAT_REQUEST_TOKEN_LIMIT` and drops for the rest of the
    turn when Groq answers 413; `messages` are the first call's trimmed
    messages, which the second calls reuse.
    """

    system_prompt: str
    tools: list[dict[str, Any]] | None
    limit: int
    messages: list[dict[str, str]] = field(default_factory=list)

    def budget(self) -> int:
        """Max input estimate of a request at the current limit."""
        settings = get_settings()
        return input_budget(
            self.limit,
            min_reply=settings.CHAT_MIN_REPLY_TOKENS,
            cap=settings.CHAT_INPUT_TOKEN_BUDGET,
        )


async def _stream_sized(
    turn: _Turn,
    build: BuildMessages,
    *,
    tool_choice: Literal["auto", "required"] = "auto",
    on_sent: Callable[[list[dict[str, str]]], None] | None = None,
) -> AsyncIterator[str | LlmToolCall]:
    """One Groq call sized to `turn.limit`, retried once smaller on a 413.

    `build(budget)` returns the messages trimmed to an input estimate of at
    most `budget` (or raises `ChatUserError`). `max_tokens` takes what the
    limit leaves (`reply_tokens`). On Groq's 413 before any output the limit
    drops by Groq's overshoot (`retry_limit`), the messages are built again
    and the call is retried once; a second 413, or messages that no longer
    fit, raise `LlmRequestTooLargeError`. `on_sent` gets the messages of the
    request that went through.
    """
    settings = get_settings()
    too_large: LlmRequestTooLargeError | None = None
    for _ in range(2):
        try:
            messages = build(turn.budget())
        except ChatUserError as e:
            if too_large is None:
                raise
            logger.warning("chat_request_too_large_retry_skipped", limit=turn.limit)
            raise too_large from e
        estimated = request_tokens(turn.system_prompt, messages, turn.tools)
        max_tokens = reply_tokens(
            estimated,
            limit=turn.limit,
            max_tokens=settings.CHAT_MAX_TOKENS,
            min_reply=settings.CHAT_MIN_REPLY_TOKENS,
        )
        started = False
        try:
            async for item in stream_llm_response(
                turn.system_prompt,
                messages,
                tools=turn.tools,
                tool_choice=tool_choice,
                max_tokens=max_tokens,
                estimated_tokens=estimated,
            ):
                if not started and on_sent is not None:
                    on_sent(messages)
                started = True
                yield item
            if not started and on_sent is not None:
                on_sent(messages)
            return
        except LlmRequestTooLargeError as e:
            if too_large is not None or started:
                raise
            too_large = e
            sent = with_margin(estimated) + max_tokens
            turn.limit = min(turn.limit, retry_limit(sent, e.limit))
            logger.warning(
                "chat_request_too_large_retry",
                estimated_tokens=estimated,
                max_tokens=max_tokens,
                retry_limit=turn.limit,
            )
    raise AssertionError("unreachable")  # pragma: no cover


async def _stream_second_call(
    turn: _Turn,
    build: BuildMessages,
    *,
    has_text: bool,
    tool_choice: Literal["auto", "required"],
    calls: list[LlmToolCall],
    event: str,
) -> AsyncIterator[str]:
    """Stream a nudged second call (follow-up or retry) into the same reply.

    Its tool calls are added to `calls`. A rate limit or size error here (after
    `_stream_sized`'s one smaller retry) keeps the first reply: the second
    request comes right after the first one, in the same per-minute quota.
    """
    separator = "\n\n" if has_text else ""
    try:
        async for item in _stream_sized(turn, build, tool_choice=tool_choice):
            if isinstance(item, LlmToolCall):
                calls.append(item)
                continue
            chunk = separator + item
            separator = ""
            yield chunk
    except (LlmRateLimitError, LlmRequestTooLargeError) as e:
        logger.warning(event, error_type=type(e).__name__)


def _second_messages(
    messages: list[dict[str, str]], reply: str, nudge: str
) -> list[dict[str, str]]:
    """The trimmed messages, the reply so far (if any), then the nudge."""
    second = [*messages]
    if reply:
        second.append({"role": "assistant", "content": reply})
    second.append({"role": "system", "content": nudge})
    return second


def _second_build(
    turn: _Turn, fit: BuildMessages, reply: str, nudge: str
) -> tuple[int, BuildMessages]:
    """A second call's input estimate, and how to build its messages.

    They reuse the first call's trimmed messages. Only after a 413 (a smaller
    budget they no longer fit) is the history trimmed again, to leave room
    for the reply and the nudge.
    """
    second = _second_messages(turn.messages, reply, nudge)
    extra = sum(map(message_tokens, second[len(turn.messages) :]))
    estimate = request_tokens(turn.system_prompt, second, turn.tools)

    def build(budget: int) -> list[dict[str, str]]:
        if estimate <= budget:
            return second
        return _second_messages(fit(budget - extra), reply, nudge)

    return estimate, build


@dataclass(slots=True, kw_only=True)
class _CallOutcome:
    """The model's tool calls of one reply, sorted out."""

    edits: list[CvEdit]
    rejected: bool  # Groq rejected the calls (`tool_use_failed`)
    failed: int  # calls that are not a usable edit
    left_out: list[list[str]]  # per edit the fact guard left out: its names
    unplaced: int = 0  # edits whose quoted passage is not in the CV


def _call_outcome(
    calls: list[LlmToolCall], cv: Cv | None, *, user_texts: list[str], job_post: str
) -> _CallOutcome:
    # A rejection left after the retry (or in a follow-up) gets one clear
    # note for the whole reply instead of a malformed-call line.
    rejected = any(c.rejected is not None for c in calls)
    calls = [c for c in calls if c.rejected is None]
    if cv is not None:
        edits, rejections = _validate_calls(calls)
        failed = len(rejections)
    else:
        edits, failed = [], len(calls)
    unplaced = 0
    if cv is not None and edits:
        edits, unplaced = place_edits(cv.content, edits)
    left_out: list[list[str]] = []
    if cv is not None and edits:
        edits, left_out = drop_unsupported_edits(
            edits, cv=cv.content, user_texts=user_texts, job_post=job_post
        )
    return _CallOutcome(
        edits=edits,
        rejected=rejected,
        failed=failed,
        left_out=left_out,
        unplaced=unplaced,
    )


_REPAIR_NUDGE = (
    "Your propose_cv_edit calls above break the CV structure, and the user's "
    "latest message did not ask for that: {problems}. Propose all your edits "
    'for this request again, in this reply, keeping every "## " section, '
    'every "###" / "####" entry heading and the "# Name" line: change only '
    "the text inside them. Do not repeat your earlier text."
)


def repair_nudge(problems: Sequence[Problem]) -> str:
    """The system message for the one repair call after a structure break."""
    return _REPAIR_NUDGE.format(problems=repair_problems_text(problems))


def structure_problems(
    cv: str, edits: Sequence[CvEdit], user_message: str
) -> list[list[Problem]]:
    """Per edit, the structure losses the user's latest message did not ask for.

    Each edit is dry-run on its own on the CV the model saw: the edits of one
    reply quote that same text and must not overlap.
    """
    return [unrequested_problems(cv, edit, user_message) for edit in edits]


def with_structure_warnings(
    edits: Sequence[CvEdit], problems: Sequence[Sequence[Problem]], language: Language
) -> list[CvEdit]:
    """The edits, each with its card warning (None when it breaks nothing)."""
    return [
        replace(edit, warning=structure_warning(found, language))
        for edit, found in zip(edits, problems, strict=True)
    ]


def _rejection(calls: list[LlmToolCall]) -> str | None:
    return next((c.rejected for c in calls if c.rejected is not None), None)


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

    history = await get_chat_history(db, application.id)
    cards = await cards_by_message(db, application.id)
    tools = [PROPOSE_CV_EDIT_TOOL] if cv is not None else None
    turn = _Turn(
        system_prompt=system_prompt,
        tools=tools,
        limit=get_settings().CHAT_REQUEST_TOKEN_LIMIT,
    )

    def fit(budget: int) -> list[dict[str, str]]:
        return fit_llm_messages(
            history,
            cards,
            system_prompt=system_prompt,
            tools=tools,
            budget=budget,
            language=language,
        )

    def keep_sent(messages: list[dict[str, str]]) -> None:
        turn.messages = messages

    full_response: list[str] = []
    calls: list[LlmToolCall] = []
    # Parser-rejected first calls whose retry brought no call back.
    carried_failed = 0
    try:
        async for item in _stream_sized(turn, fit, on_sent=keep_sent):
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

    rejection = _rejection(calls) if tools else None
    if tools and rejection is not None:
        # Groq rejected the edit calls against the tool schema, failing the
        # whole generation. One retry, never more, told the exact error; it
        # reuses the trimmed messages and is skipped if it would not fit.
        calls = []
        reply = "".join(full_response).strip()
        estimate, build = _second_build(turn, fit, reply, retry_nudge(rejection))
        if estimate > (budget := turn.budget()):
            logger.info("chat_retry_skipped", estimated_tokens=estimate, budget=budget)
            calls.append(LlmToolCall(name="", arguments="", rejected=rejection))
        else:
            logger.info("chat_tool_use_retry", error=rejection)
            # The model meant to propose edits: this time a call is required.
            async for chunk in _stream_second_call(
                turn,
                build,
                has_text=bool(full_response),
                tool_choice="required",
                calls=calls,
                event="chat_retry_failed",
            ):
                full_response.append(chunk)
                yield chunk
            if not calls:
                # Rate-limited or too large (the retry kept the first reply):
                # the rejected edits still get their note.
                calls.append(LlmToolCall(name="", arguments="", rejected=rejection))
    elif tools and (parser_rejected := _all_parser_rejected(calls)):
        # Groq accepted the calls but our parser rejected every one (wrong
        # name, bad JSON, invalid arguments): no card would come of the
        # reply. One retry, never more, told only which rule each call broke;
        # it reuses the trimmed messages and is skipped if it would not fit.
        # The first calls are logged here: only the retry's calls go on.
        for rejection_found in parser_rejected:
            _log_rejection(rejection_found)
        calls = []
        reply = "".join(full_response).strip()
        nudge = parse_retry_nudge(parser_rejected)
        estimate, build = _second_build(turn, fit, reply, nudge)
        if estimate > (budget := turn.budget()):
            logger.info("chat_retry_skipped", estimated_tokens=estimate, budget=budget)
            carried_failed = len(parser_rejected)
        else:
            logger.info("chat_parse_retry", reasons=[r.reason for r in parser_rejected])
            async for chunk in _stream_second_call(
                turn,
                build,
                has_text=bool(full_response),
                tool_choice="required",
                calls=calls,
                event="chat_retry_failed",
            ):
                full_response.append(chunk)
                yield chunk
            if not calls:
                # No call came back (rate-limited, too large, or text only):
                # the first calls keep their note.
                carried_failed = len(parser_rejected)
    elif tools and needs_follow_up("".join(full_response), calls):
        # One nudge, never more: the model announced edits but made none.
        # It reuses the trimmed messages, and is skipped if it would not fit.
        reply = "".join(full_response).strip()
        estimate, build = _second_build(turn, fit, reply, FOLLOW_UP_NUDGE)
        if estimate > (budget := turn.budget()):
            logger.info(
                "chat_follow_up_skipped", estimated_tokens=estimate, budget=budget
            )
        else:
            # The reply announced edits: this time a tool call is required.
            # An empty reply announced nothing, so the model may still answer.
            async for chunk in _stream_second_call(
                turn,
                build,
                has_text=bool(full_response),
                tool_choice="required" if reply else "auto",
                calls=calls,
                event="chat_follow_up_failed",
            ):
                full_response.append(chunk)
                yield chunk

    user_texts = [m.content for m in history if m.role == "user"]
    job_post = application.notes or ""
    outcome = _call_outcome(calls, cv, user_texts=user_texts, job_post=job_post)
    outcome.failed += carried_failed
    if cv is not None and outcome.edits:
        problems = structure_problems(cv.content, outcome.edits, user_content)
        if any(problems):
            # An edit breaks the CV structure the user did not ask to change.
            # One repair call, never more, told what broke; it reuses the
            # trimmed messages and is skipped if it would not fit. Still
            # broken (or no usable edit came back): the cards keep a warning.
            reply = "".join(full_response).strip()
            found = [p for edit_problems in problems for p in edit_problems]
            estimate, build = _second_build(turn, fit, reply, repair_nudge(found))
            if estimate > (budget := turn.budget()):
                logger.info(
                    "chat_repair_skipped", estimated_tokens=estimate, budget=budget
                )
            else:
                logger.info("chat_structure_repair", problems=[p.kind for p in found])
                repair_calls: list[LlmToolCall] = []
                async for chunk in _stream_second_call(
                    turn,
                    build,
                    has_text=bool(full_response),
                    tool_choice="required",
                    calls=repair_calls,
                    event="chat_repair_failed",
                ):
                    full_response.append(chunk)
                    yield chunk
                repaired = _call_outcome(
                    repair_calls, cv, user_texts=user_texts, job_post=job_post
                )
                if repaired.edits:
                    # The repair's edits replace the first ones, but what the
                    # first reply's text already announced (left-out edits,
                    # rejected or malformed calls) keeps its note and marker.
                    left_out = [*outcome.left_out]
                    left_out += [n for n in repaired.left_out if n not in left_out]
                    outcome = _CallOutcome(
                        edits=repaired.edits,
                        rejected=outcome.rejected or repaired.rejected,
                        failed=outcome.failed + repaired.failed,
                        left_out=left_out,
                        unplaced=outcome.unplaced + repaired.unplaced,
                    )
                    problems = structure_problems(
                        cv.content, outcome.edits, user_content
                    )
            outcome.edits = with_structure_warnings(outcome.edits, problems, language)
    edits, left_out = outcome.edits, outcome.left_out
    notes = (
        [REJECTED_CALLS_NOTE[language]] * outcome.rejected
        + [MALFORMED_CALL_NOTE] * outcome.failed
        + [PASSAGE_NOT_FOUND_NOTE[language]] * outcome.unplaced
        + [unsupported_names_note(names, language) for names in left_out]
    )
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
