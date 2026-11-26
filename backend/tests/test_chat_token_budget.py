"""The CV chat keeps each request under the model's input limit. Fake Groq only."""

from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

import groq
import httpx
import pytest

from app.core.config import get_settings
from app.models.chat_change_card import ChatChangeCard
from app.models.chat_message import ChatMessage
from app.services.chat_budget import (
    HISTORY_TRIMMED_NOTE,
    PROMPT_TOO_LARGE_DETAIL,
    RATE_LIMITED_DETAIL,
    ChatUserError,
    estimate_tokens,
    request_tokens,
)
from app.services.chat_card_service import REMOVED_TEXT_LABEL, card_history_note
from app.services.chat_service import (
    FOLLOW_UP_NUDGE,
    build_llm_messages,
    fit_llm_messages,
)
from app.services.chat_tools import PROPOSE_CV_EDIT_TOOL
from app.services.groq_client import LlmRequestTooLargeError, stream_llm_response
from tests.test_chat_cards import APPS, _chunk, _h
from tests.test_chat_follows_requests import _send_seq, _SequenceGroq, setup

__all__ = ["setup"]  # the fixture, re-used

SYSTEM = "You are a CV assistant."
TOOLS = [PROPOSE_CV_EDIT_TOOL]


def _msg(i: int, role: str, content: str) -> ChatMessage:
    return ChatMessage(id=f"m{i:02d}", application_id="a", role=role, content=content)


def _chat(*turns: tuple[str, str]) -> list[ChatMessage]:
    return [_msg(i, role, text) for i, (role, text) in enumerate(turns)]


def _card(message_id: str, before: str) -> ChatChangeCard:
    return ChatChangeCard(
        id=f"c-{message_id}",
        message_id=message_id,
        op="replace",
        state="accepted",
        before_text=before,
        after_text="new",
        anchor_text=None,
        position=None,
    )


def _fit(
    history: list[ChatMessage],
    budget: int,
    cards: dict[str, list[ChatChangeCard]] | None = None,
    system: str = SYSTEM,
) -> list[dict[str, str]]:
    return fit_llm_messages(
        history,
        cards or {},
        system_prompt=system,
        tools=TOOLS,
        budget=budget,
        language="en",
    )


def _size(messages: list[dict[str, str]], system: str = SYSTEM) -> int:
    return request_tokens(system, messages, TOOLS)


LONG = "word " * 400  # ~500 tokens


# ---------------------------------------------------------------------------
# Estimate
# ---------------------------------------------------------------------------


def test_estimate_counts_cyrillic_denser_than_ascii() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("a") == 1
    assert estimate_tokens("abcd" * 10) == 10
    assert estimate_tokens("абв" * 10) == 10


# ---------------------------------------------------------------------------
# Trimming order
# ---------------------------------------------------------------------------


def test_history_within_budget_is_sent_untrimmed() -> None:
    history = _chat(("user", "hi"), ("assistant", "hello"), ("user", "again"))

    assert _fit(history, 10_000) == build_llm_messages(history, {})


def test_oldest_messages_are_dropped_first() -> None:
    history = _chat(
        ("user", "first " + LONG),
        ("assistant", "second " + LONG),
        ("user", "third " + LONG),
        ("assistant", "fourth " + LONG),
        ("user", "latest"),
    )
    full = _size(build_llm_messages(history, {}))

    messages = _fit(history, full - 600)

    assert messages[0] == {"role": "system", "content": HISTORY_TRIMMED_NOTE}
    texts = [m["content"].split()[0] for m in messages[1:]]
    assert texts == ["third", "fourth", "latest"]
    assert _size(messages) <= full - 600


def test_latest_user_message_and_last_reply_are_never_dropped() -> None:
    history = _chat(
        ("user", "old " + LONG),
        ("assistant", "reply " + LONG),
        ("user", "failed send"),
        ("user", "latest " + LONG),
    )
    kept_only = [
        {"role": "assistant", "content": history[1].content},
        {"role": "user", "content": history[3].content},
    ]
    budget = _size([{"role": "system", "content": HISTORY_TRIMMED_NOTE}, *kept_only])

    messages = _fit(history, budget)

    assert messages[1:] == kept_only


def test_full_quote_is_shortened_only_after_the_history_is_dropped() -> None:
    history = _chat(
        ("user", "old " + LONG),
        ("assistant", "old reply"),
        ("user", "shorten it"),
        ("assistant", "done"),
        ("user", "undo that"),
    )
    removed = "removed passage " * 100
    cards = {"m03": [_card("m03", removed)]}
    full = build_llm_messages(history, cards)
    assert REMOVED_TEXT_LABEL in full[-2]["content"]

    # Room for everything but the oldest message: the full quote stays.
    dropped_old = _fit(history, _size(full) - 400, cards)
    assert REMOVED_TEXT_LABEL in dropped_old[-2]["content"]
    assert dropped_old[1] == {"role": "assistant", "content": "old reply"}

    # No room for the full quote even with only the kept messages: short form.
    short_form = [
        {"role": "system", "content": HISTORY_TRIMMED_NOTE},
        {"role": "assistant", "content": "done"},
        {"role": "system", "content": card_history_note(cards["m03"])},
        {"role": "user", "content": "undo that"},
    ]
    short = _fit(history, _size(short_form), cards)
    assert REMOVED_TEXT_LABEL not in short[-2]["content"]
    assert "accepted: replace 'removed passage" in short[-2]["content"]
    assert [m["content"] for m in short if m["role"] != "system"] == [
        "done",
        "undo that",
    ]


def test_cv_and_vacancy_alone_over_budget_raise_a_clear_error() -> None:
    huge_system = "CV " * 20_000
    history = _chat(("user", "hi"))

    with pytest.raises(ChatUserError) as caught:
        _fit(history, 6500, system=huge_system)

    assert caught.value.detail == PROMPT_TOO_LARGE_DETAIL["en"]


# ---------------------------------------------------------------------------
# Through the endpoint
# ---------------------------------------------------------------------------


@contextmanager
def _budget(tokens: int) -> Iterator[None]:
    settings = get_settings()
    old = settings.CHAT_INPUT_TOKEN_BUDGET
    settings.CHAT_INPUT_TOKEN_BUDGET = tokens
    try:
        yield
    finally:
        settings.CHAT_INPUT_TOKEN_BUDGET = old


async def test_over_budget_chat_sends_an_error_frame_and_no_request(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    fake = _SequenceGroq([_chunk("never")])

    with _budget(1000):
        events = await _send_seq(client, setup, fake, "Сделай короче " * 400)

    assert fake.calls == []
    assert events == [("error", {"detail": PROMPT_TOO_LARGE_DETAIL["ru"]})]


async def test_trimmed_history_reaches_groq(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    for text in ("first " + LONG, "second " + LONG):
        await _send_seq(client, setup, _SequenceGroq([_chunk("ok " + LONG)]), text)
    fake = _SequenceGroq([_chunk("Your CV looks fine.")])
    probe = _SequenceGroq([_chunk("x")])
    await _send_seq(client, setup, probe, "measure")
    full = request_tokens(
        probe.calls[0]["messages"][0]["content"],
        probe.calls[0]["messages"][1:],
        probe.calls[0]["tools"],
    )

    with _budget(full - 300):
        await _send_seq(client, setup, fake, "latest")

    sent = fake.calls[0]["messages"]
    assert sent[1] == {"role": "system", "content": HISTORY_TRIMMED_NOTE}
    assert sent[-1] == {"role": "user", "content": "latest"}
    assert not any(m["content"].startswith("first") for m in sent)
    assert request_tokens(sent[0]["content"], sent[1:], fake.calls[0]["tools"]) <= (
        full - 300
    )


async def test_follow_up_reuses_trimmed_messages(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    await _send_seq(client, setup, _SequenceGroq([_chunk("ok " + LONG)]), LONG)
    probe = _SequenceGroq([_chunk("Your CV looks fine.")])
    await _send_seq(client, setup, probe, "measure")
    full = request_tokens(
        probe.calls[0]["messages"][0]["content"],
        probe.calls[0]["messages"][1:],
        probe.calls[0]["tools"],
    )
    fake = _SequenceGroq([_chunk("Here are the edits:")], [_chunk("Nothing to do.")])

    with _budget(full - 200):
        await _send_seq(client, setup, fake, "Shorten it")

    assert len(fake.calls) == 2
    first, second = (call["messages"] for call in fake.calls)
    assert second[: len(first)] == first
    assert second[len(first) :] == [
        {"role": "assistant", "content": "Here are the edits:"},
        {"role": "system", "content": FOLLOW_UP_NUDGE},
    ]


async def test_follow_up_is_skipped_when_it_would_exceed_the_budget(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    probe = _SequenceGroq([_chunk("Your CV looks fine.")])
    await _send_seq(client, setup, probe, "Shorten it")
    # Room for this message, but not for the reply + nudge on top of it.
    first = request_tokens(
        probe.calls[0]["messages"][0]["content"],
        probe.calls[0]["messages"][1:],
        probe.calls[0]["tools"],
    )
    fake = _SequenceGroq([_chunk("Here are the edits:")], [_chunk("never")])

    with _budget(first + 40):
        events = await _send_seq(client, setup, fake, "Shorten it")

    assert len(fake.calls) == 1
    assert events[-1][0] == "done"
    history = await client.get(
        f"{APPS}/{setup['app_id']}/chat", headers=_h(setup["token"])
    )
    assert history.json()[-1]["content"] == "Here are the edits:"


# ---------------------------------------------------------------------------
# Groq 413 / 429
# ---------------------------------------------------------------------------


def _status_error(status: int, cls: type[groq.APIStatusError]) -> groq.APIStatusError:
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(status, request=request)
    body = {"error": {"message": "Request too large", "type": "tokens"}}
    return cls("Request too large", response=response, body=body)


class _RaisingGroq(_SequenceGroq):
    """Answers the n-th `create` call (1-based), or every one from it, with an
    error."""

    def __init__(
        self, error: Exception, at: int, *answers: list[Any], every: bool = False
    ) -> None:
        super().__init__(*answers)
        self.error = error
        self.at = at
        self.every = every  # also every call after the n-th

    async def _create(self, **kwargs: Any) -> AsyncIterator[Any]:
        n = len(self.calls) + 1
        if n == self.at or (self.every and n > self.at):
            self.calls.append(kwargs)
            raise self.error
        return await super()._create(**kwargs)


async def test_groq_413_becomes_too_large_error() -> None:
    fake = _RaisingGroq(_status_error(413, groq.APIStatusError), 1)

    with (
        patch("app.services.groq_client._get_client", return_value=fake),
        pytest.raises(LlmRequestTooLargeError),
    ):
        async for _ in stream_llm_response(SYSTEM, [], tools=TOOLS):
            pass


@pytest.mark.parametrize(
    ("status", "cls", "texts"),
    [
        (413, groq.APIStatusError, PROMPT_TOO_LARGE_DETAIL),
        (429, groq.RateLimitError, RATE_LIMITED_DETAIL),
    ],
)
async def test_groq_size_and_rate_errors_reach_the_user_clearly(
    client: httpx.AsyncClient,
    setup: dict[str, str],
    status: int,
    cls: type[groq.APIStatusError],
    texts: dict[str, str],
) -> None:
    # A 413 is retried once smaller: only a second 413 reaches the user.
    fake = _RaisingGroq(_status_error(status, cls), 1, every=True)

    events = await _send_seq(client, setup, fake, "Hello")

    assert len(fake.calls) == (2 if status == 413 else 1)
    assert events == [("error", {"detail": texts["en"]})]


async def test_rate_limited_follow_up_keeps_the_first_reply(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    fake = _RaisingGroq(
        _status_error(429, groq.RateLimitError), 2, [_chunk("Here are the edits:")]
    )

    events = await _send_seq(client, setup, fake, "Shorten it")

    assert len(fake.calls) == 2
    assert [name for name, _ in events] == ["token", "cards", "done"]
    history = await client.get(
        f"{APPS}/{setup['app_id']}/chat", headers=_h(setup["token"])
    )
    assert history.json()[-1]["content"] == "Here are the edits:"
