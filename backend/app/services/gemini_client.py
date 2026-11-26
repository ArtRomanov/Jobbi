"""The CV chat on Google Gemini, through its OpenAI-compatible endpoint.

Used when `CHAT_PROVIDER=gemini`. Yields the same items as
`groq_client.stream_llm_response` (text chunks, then one `LlmToolCall` per
call) and raises the same `LlmRateLimitError` / `LlmRequestTooLargeError`.
Groq-only parts stay out: no gpt-oss `reasoning_effort` values, no
`tool_use_failed`, no `parallel_tool_calls` (undocumented on this layer;
Gemini calls several functions per turn on its own).
"""

import re
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any

import openai
import structlog

from app.core.config import get_settings
from app.services.llm_stream import (
    NO_LIMIT_NUMBERS,
    CallAssembler,
    LlmLimit,
    LlmRateLimitError,
    LlmRequestTooLargeError,
    LlmToolCall,
    ToolChoice,
    tool_kwargs,
)

logger = structlog.get_logger()

# Mid-chat system messages (card notes, retry nudges) go as user messages:
# the OpenAI layer folds every system message into Gemini's one system
# instruction, which would move a nudge away from the end of the chat.
APP_NOTE_PREFIX = "[Note from the Jobbi app, not typed by the user]\n"

# Gemini's 400 for an over-long input: "The input token count (1048577)
# exceeds the maximum number of tokens allowed (1048576)."
# Possessive and atomic parts: no backtracking, linear on a long message.
_TOO_LONG = re.compile(
    r"input token count\D*+(\d++)(?>.*?allowed)\D*+(\d++)", re.IGNORECASE
)
_TOO_LONG_HINT = re.compile(r"token count|exceeds the maximum|too long", re.IGNORECASE)


class ChatProviderNotConfiguredError(RuntimeError):
    """CHAT_PROVIDER=gemini without GEMINI_API_KEY."""


def _get_client() -> openai.AsyncOpenAI:
    settings = get_settings()
    if not settings.GEMINI_API_KEY:
        raise ChatProviderNotConfiguredError("GEMINI_API_KEY is not set")
    return openai.AsyncOpenAI(
        api_key=settings.GEMINI_API_KEY, base_url=settings.GEMINI_BASE_URL
    )


def gemini_messages(
    system_prompt: str, messages: Sequence[Mapping[str, str]]
) -> list[dict[str, str]]:
    """The system prompt first; later system messages as marked user notes."""
    full = [{"role": "system", "content": system_prompt}]
    for message in messages:
        if message["role"] == "system":
            full.append(
                {"role": "user", "content": APP_NOTE_PREFIX + message["content"]}
            )
        else:
            full.append({"role": message["role"], "content": message["content"]})
    return full


def _error_message(body: object) -> str | None:
    """`error.message` of an OpenAI-layer error body.

    Gemini may wrap it in a list (`[{"error": {...}}]`).
    """
    if isinstance(body, list) and body:
        body = body[0]
    error = body.get("error", body) if isinstance(body, Mapping) else None
    message = error.get("message") if isinstance(error, Mapping) else None
    return message if isinstance(message, str) else None


def _error_status(body: object) -> str | None:
    """Gemini's status word (e.g. RESOURCE_EXHAUSTED), if the body has one."""
    if isinstance(body, list) and body:
        body = body[0]
    error = body.get("error", body) if isinstance(body, Mapping) else None
    status = error.get("status") if isinstance(error, Mapping) else None
    return status if isinstance(status, str) and status.isupper() else None


def parse_too_long(body: object) -> LlmLimit | None:
    """The numbers of Gemini's "input too long" error; None for another error."""
    message = _error_message(body)
    if message is None or not _TOO_LONG_HINT.search(message):
        return None
    found = _TOO_LONG.search(message)
    if found is None:
        return NO_LIMIT_NUMBERS
    return LlmLimit(
        kind="input", limit=int(found.group(2)), requested=int(found.group(1))
    )


def _log_error(
    event: str,
    error: openai.APIStatusError,
    *,
    max_tokens: int,
    estimated_tokens: int | None,
) -> None:
    """Status and kind only: Gemini's messages can name the project or key."""
    logger.error(
        event,
        status_code=error.status_code,
        kind=_error_status(error.body),
        estimated_tokens=estimated_tokens,
        max_tokens=max_tokens,
        model=get_settings().GEMINI_CHAT_MODEL,
    )


async def stream_gemini_response(
    system_prompt: str,
    messages: list[dict[str, str]],
    tools: list[dict[str, Any]] | None = None,
    *,
    tool_choice: ToolChoice = "auto",
    max_tokens: int | None = None,
    estimated_tokens: int | None = None,
) -> AsyncIterator[str | LlmToolCall]:
    """Stream Gemini's response; the contract of `stream_llm_response`.

    `tool_choice="required"` goes out as "auto" unless
    `GEMINI_TOOL_CHOICE_REQUIRED` is on. Raises
    `ChatProviderNotConfiguredError` without `GEMINI_API_KEY`.
    """
    settings = get_settings()
    client = _get_client()
    reply_cap = settings.GEMINI_CHAT_MAX_TOKENS if max_tokens is None else max_tokens
    if tool_choice == "required" and not settings.GEMINI_TOOL_CHOICE_REQUIRED:
        tool_choice = "auto"
    reasoning: dict[str, str] = (
        {"reasoning_effort": settings.GEMINI_REASONING_EFFORT}
        if settings.GEMINI_REASONING_EFFORT
        else {}
    )
    assembler = CallAssembler()

    try:
        stream = await client.chat.completions.create(
            model=settings.GEMINI_CHAT_MODEL,
            # Gemini 3 thinks inside this cap (thinking cannot be turned off).
            max_tokens=reply_cap,
            messages=gemini_messages(system_prompt, messages),  # type: ignore[arg-type]
            stream=True,
            **reasoning,
            **tool_kwargs(tools, tool_choice, parallel_tool_calls=False),
        )
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content
            assembler.add_delta(delta)
    except openai.AuthenticationError as e:
        _log_error("gemini_auth_error", e, max_tokens=reply_cap, estimated_tokens=None)
        raise RuntimeError(
            "AI service authentication failed. Please contact the operator."
        ) from e
    except openai.RateLimitError as e:
        _log_error(
            "gemini_rate_limited",
            e,
            max_tokens=reply_cap,
            estimated_tokens=estimated_tokens,
        )
        raise LlmRateLimitError(
            "Rate limit reached. Please try again in a moment.",
            limit=NO_LIMIT_NUMBERS,
        ) from e
    except openai.APIConnectionError as e:
        logger.error("gemini_connection_error", error_type=type(e).__name__)
        raise RuntimeError("Couldn't reach the AI service. Please try again.") from e
    except openai.APIStatusError as e:
        too_long = parse_too_long(e.body) if e.status_code in (400, 413) else None
        if e.status_code == 413 and too_long is None:
            too_long = NO_LIMIT_NUMBERS
        if too_long is not None:
            _log_error(
                "gemini_request_too_large",
                e,
                max_tokens=reply_cap,
                estimated_tokens=estimated_tokens,
            )
            raise LlmRequestTooLargeError(
                "The request is over the model's input limit.", limit=too_long
            ) from e
        _log_error(
            "gemini_api_error",
            e,
            max_tokens=reply_cap,
            estimated_tokens=estimated_tokens,
        )
        raise RuntimeError("The AI service returned an error.") from e
    except openai.APIError as e:
        # E.g. an error event inside the stream: no status code.
        logger.error("gemini_api_error", error_type=type(e).__name__)
        raise RuntimeError("The AI service returned an error.") from e

    for call in assembler.tool_calls():
        yield call
