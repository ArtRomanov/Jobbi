"""Keep each CV chat request under the model's per-request token limit.

Groq rejects a request that is over the model's tokens-per-minute limit
(HTTP 413) and counts the input *plus the requested `max_tokens`* against it
(gpt-oss-20b free tier: 8000). Before each call the chat estimates the input,
trims the history to fit `input_budget` and sizes `max_tokens` with
`reply_tokens`, so that input (with a safety margin) + `max_tokens` stays
within `CHAT_REQUEST_TOKEN_LIMIT` (see `chat_service`).

The estimate needs no tokenizer: 4 characters per token for ASCII text and 3
for anything else (Cyrillic), plus a few tokens per message. Against the
o200k_base tokenizer (gpt-oss) it ran 0.87-1.09x the real count: low on
Russian CV text (spaces and digits between Cyrillic words count as ASCII),
high on English prose. `with_margin` adds 15% to cover the low end.
"""

import json
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from app.services.chat_guard_notes import Language

ASCII_CHARS_PER_TOKEN = 4
OTHER_CHARS_PER_TOKEN = 3
# Role markers and separators the chat template adds around each message.
MESSAGE_OVERHEAD_TOKENS = 8
# Added to an input estimate before it is set against the request limit.
ESTIMATE_MARGIN_PERCENT = 15
# A retry after Groq's 413 goes this far below the size Groq would accept.
RETRY_MARGIN_TOKENS = 200
# Shrink of a retry when Groq's 413 names no numbers.
UNKNOWN_OVERSHOOT_PERCENT = 15

HISTORY_TRIMMED_NOTE = (
    "Context note: the earliest messages of this chat were left out to fit the "
    "model's input limit."
)

PROMPT_TOO_LARGE_DETAIL: dict[Language, str] = {
    "en": (
        "Your CV and this vacancy are too long for the AI model's limit. "
        "Shorten them (or your message), or clear the chat history and try again."
    ),
    "ru": (
        "CV и вакансия слишком длинные для лимита AI-модели. Сократите их "
        "(или ваше сообщение) либо очистите историю чата и попробуйте снова."
    ),
}
RATE_LIMITED_DETAIL: dict[Language, str] = {
    "en": "The AI model's per-minute limit is used up. Wait a minute and try again.",
    "ru": "Минутный лимит AI-модели исчерпан. Подождите минуту и попробуйте снова.",
}


class GroqLimitLike(Protocol):
    """The numbers of a Groq limit error (`groq_client.GroqLimit`)."""

    @property
    def limit(self) -> int | None: ...

    @property
    def requested(self) -> int | None: ...


class ChatUserError(Exception):
    """A chat failure the user can act on; `detail` is shown to them as is."""

    def __init__(self, detail: str, *, reason: str) -> None:
        super().__init__(reason)
        self.detail = detail
        self.reason = reason


def estimate_tokens(text: str) -> int:
    """An upper-leaning estimate of the model's token count for `text`."""
    other = sum(1 for char in text if not char.isascii())
    ascii_chars = len(text) - other
    # Ceiling division, so even a one-character text counts.
    return -(-ascii_chars // ASCII_CHARS_PER_TOKEN) - (-other // OTHER_CHARS_PER_TOKEN)


def message_tokens(message: Mapping[str, str]) -> int:
    return estimate_tokens(message["content"]) + MESSAGE_OVERHEAD_TOKENS


def fixed_tokens(system_prompt: str, tools: Sequence[dict[str, Any]] | None) -> int:
    """The part of every request that the history trim cannot shrink."""
    total = message_tokens({"content": system_prompt})
    if tools:
        total += estimate_tokens(json.dumps(list(tools)))
    return total


def request_tokens(
    system_prompt: str,
    messages: Sequence[Mapping[str, str]],
    tools: Sequence[dict[str, Any]] | None,
) -> int:
    """Estimated input tokens of one chat completion request."""
    return fixed_tokens(system_prompt, tools) + sum(message_tokens(m) for m in messages)


def with_margin(estimated: int) -> int:
    """`estimated` plus the safety margin for the estimate's undercount."""
    return estimated - (-estimated * ESTIMATE_MARGIN_PERCENT // 100)


def input_budget(limit: int, *, min_reply: int, cap: int) -> int:
    """The largest input estimate that still leaves `min_reply` reply tokens.

    `cap` (`CHAT_INPUT_TOKEN_BUDGET`) bounds it further; 0 when even an empty
    input would not leave the reply its minimum.
    """
    room = limit - min_reply
    if room <= 0:
        return 0
    budget = room * 100 // (100 + ESTIMATE_MARGIN_PERCENT)
    while budget > 0 and with_margin(budget) > room:
        budget -= 1
    return min(cap, budget)


def reply_tokens(estimated: int, *, limit: int, max_tokens: int, min_reply: int) -> int:
    """`max_tokens` for a request whose input is estimated at `estimated`.

    What is left under `limit`, capped at `CHAT_MAX_TOKENS`. Never under
    `min_reply` (callers trim the input to `input_budget` first): gpt-oss
    spends part of it on reasoning, and a reply cut short is worse than a 413
    that the chat retries.
    """
    room = limit - with_margin(estimated)
    return min(max_tokens, max(room, min_reply))


def retry_limit(sent: int, groq_limit: GroqLimitLike) -> int:
    """The request limit for the one retry after Groq's 413.

    `sent` is what the failed request was sized to (input with margin +
    `max_tokens`). Groq's message says by how much it was over ("Limit 8000,
    Requested 9500"); without numbers the retry is 15% smaller. Either way it
    goes `RETRY_MARGIN_TOKENS` further down.
    """
    limit, requested = groq_limit.limit, groq_limit.requested
    if limit is not None and requested is not None and requested > limit:
        overshoot = requested - limit
    else:
        overshoot = sent * UNKNOWN_OVERSHOOT_PERCENT // 100
    return sent - overshoot - RETRY_MARGIN_TOKENS
