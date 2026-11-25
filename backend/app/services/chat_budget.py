"""Keep each CV chat request under the model's input-token limit.

Groq rejects a request whose input is over the model's tokens-per-minute
limit (HTTP 413), so a chat whose prompt has grown past it fails on every
message. Before each call the chat estimates the request size and trims the
history to fit `CHAT_INPUT_TOKEN_BUDGET` (see `chat_service.fit_llm_messages`).

The estimate needs no tokenizer: 4 characters per token for ASCII text and 3
for anything else (Cyrillic), plus a few tokens per message. On a real chat
(English CV, Russian messages) it came out about 10% above the count Groq
reported, so it errs on the safe side.
"""

import json
from collections.abc import Mapping, Sequence
from typing import Any

from app.services.chat_guard_notes import Language

ASCII_CHARS_PER_TOKEN = 4
OTHER_CHARS_PER_TOKEN = 3
# Role markers and separators the chat template adds around each message.
MESSAGE_OVERHEAD_TOKENS = 8

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
