"""CV chat on gpt-oss: reasoning options and reply cap; a failed send leaves
no user message behind. Fake Groq only, no tokens."""

from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

import groq
import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.llm_options import is_gpt_oss, reasoning_options
from app.models.chat_message import ChatMessage
from app.services.chat_budget import RATE_LIMITED_DETAIL
from app.services.groq_client import stream_llm_response
from tests.test_chat_cards import APPS, _call_chunks, _chunk, _h
from tests.test_chat_follows_requests import _send_seq, _SequenceGroq, setup
from tests.test_chat_token_budget import _budget, _RaisingGroq, _status_error
from tests.test_env_example import _example_value

__all__ = ["setup"]  # the fixture, re-used

GPT_OSS = "openai/gpt-oss-20b"
QWEN = "qwen/qwen3.8-27b"


@contextmanager
def _chat_settings(**values: Any) -> Iterator[None]:
    settings = get_settings()
    old = {key: getattr(settings, key) for key in values}
    for key, value in values.items():
        setattr(settings, key, value)
    try:
        yield
    finally:
        for key, value in old.items():
            setattr(settings, key, value)


async def _history(client: httpx.AsyncClient, s: dict[str, str]) -> list[dict]:
    resp = await client.get(f"{APPS}/{s['app_id']}/chat", headers=_h(s["token"]))
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


def test_chat_defaults() -> None:
    fields = Settings.model_fields
    assert fields["GROQ_MODEL"].default == GPT_OSS
    assert fields["CHAT_MAX_TOKENS"].default == 6000
    assert fields["CHAT_REASONING_EFFORT"].default == "medium"


def test_env_example_documents_chat_settings_with_defaults() -> None:
    fields = Settings.model_fields
    assert _example_value("GROQ_MODEL") == fields["GROQ_MODEL"].default
    assert int(_example_value("CHAT_MAX_TOKENS")) == fields["CHAT_MAX_TOKENS"].default
    assert (
        _example_value("CHAT_REASONING_EFFORT")
        == fields["CHAT_REASONING_EFFORT"].default
    )


@pytest.mark.parametrize(
    ("model", "effort", "expected"),
    [
        (GPT_OSS, "medium", {"reasoning_effort": "medium"}),
        ("openai/gpt-oss-120b", "high", {"reasoning_effort": "high"}),
        (QWEN, "medium", {}),
        ("llama-3.3-70b-versatile", "low", {}),
    ],
)
def test_reasoning_options_only_for_gpt_oss(
    model: str, effort: Any, expected: dict[str, str]
) -> None:
    assert is_gpt_oss(model) is bool(expected)
    assert reasoning_options(model, effort) == expected


# ---------------------------------------------------------------------------
# Request options of the chat call
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("model", "effort", "expected_effort"),
    [(GPT_OSS, "medium", "medium"), (GPT_OSS, "low", "low"), (QWEN, "medium", None)],
)
async def test_chat_call_sends_reasoning_effort_and_reply_cap(
    model: str, effort: str, expected_effort: str | None
) -> None:
    fake = _SequenceGroq([_chunk("ok")])

    with (
        _chat_settings(
            GROQ_MODEL=model, CHAT_REASONING_EFFORT=effort, CHAT_MAX_TOKENS=6000
        ),
        patch("app.services.groq_client._get_client", return_value=fake),
    ):
        async for _ in stream_llm_response("system", []):
            pass

    call = fake.calls[0]
    assert call["model"] == model
    assert call["max_tokens"] == 6000
    assert call.get("reasoning_effort") == expected_effort
    assert ("reasoning_effort" in call) is (expected_effort is not None)


async def test_follow_up_call_gets_the_same_options(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    fake = _SequenceGroq(
        [_chunk("Let me fetch the current CV.")], [_chunk("Nothing to change.")]
    )

    # A limit far above the request: max_tokens is the configured cap (under
    # the 8000 default limit it would be lowered to fit the request).
    with _chat_settings(
        GROQ_MODEL=GPT_OSS,
        CHAT_REASONING_EFFORT="high",
        CHAT_MAX_TOKENS=7000,
        CHAT_REQUEST_TOKEN_LIMIT=100_000,
    ):
        await _send_seq(client, setup, fake, "Shorten it")

    assert len(fake.calls) == 2
    for call in fake.calls:
        assert call["reasoning_effort"] == "high"
        assert call["max_tokens"] == 7000


# ---------------------------------------------------------------------------
# A failed send leaves no user message
# ---------------------------------------------------------------------------


async def test_rate_limited_send_leaves_no_user_message(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    await _send_seq(client, setup, _SequenceGroq([_chunk("Hi!")]), "Hello")
    fake = _RaisingGroq(_status_error(429, groq.RateLimitError), 1)

    events = await _send_seq(client, setup, fake, "Shorten it")

    assert events == [("error", {"detail": RATE_LIMITED_DETAIL["en"]})]
    history = await _history(client, setup)
    assert [(m["role"], m["content"]) for m in history] == [
        ("user", "Hello"),
        ("assistant", "Hi!"),
    ]


async def test_over_budget_send_leaves_no_user_message(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    with _budget(1000):
        events = await _send_seq(
            client, setup, _SequenceGroq([_chunk("never")]), "Shorten it " * 400
        )

    assert [name for name, _ in events] == ["error"]
    assert await _history(client, setup) == []


class _BrokenStreamGroq(_SequenceGroq):
    """Streams some text, then the connection breaks mid-stream."""

    async def _create(self, **kwargs: Any) -> AsyncIterator[Any]:
        self.calls.append(kwargs)

        async def _gen() -> AsyncIterator[Any]:
            yield _chunk("Here is ")
            raise groq.APIConnectionError(request=httpx.Request("POST", "http://x"))

        return _gen()


async def test_send_failing_after_tokens_leaves_no_user_message(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    events = await _send_seq(client, setup, _BrokenStreamGroq(), "Shorten it")

    assert [name for name, _ in events] == ["token", "error"]
    assert await _history(client, setup) == []


async def test_failed_reply_commit_rolls_back_and_drops_the_user_message(
    client: httpx.AsyncClient, setup: dict[str, str], db_session: AsyncSession
) -> None:
    # The assistant message is flushed, then storing its card fails.
    fake = _SequenceGroq(
        [
            _chunk("Removed jQuery."),
            *_call_chunks(0, {"op": "remove", "before": "- jQuery"}),
        ]
    )

    with patch("app.services.chat_service.add_cards", side_effect=RuntimeError("boom")):
        events = await _send_seq(client, setup, fake, "Remove jQuery")

    assert [name for name, _ in events] == ["token", "error"]
    count = await db_session.scalar(select(func.count()).select_from(ChatMessage))
    assert count == 0


async def test_rate_limited_follow_up_keeps_the_user_message(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    fake = _RaisingGroq(
        _status_error(429, groq.RateLimitError), 2, [_chunk("Here are the edits:")]
    )

    events = await _send_seq(client, setup, fake, "Shorten it")

    assert [name for name, _ in events] == ["token", "cards", "done"]
    history = await _history(client, setup)
    assert [(m["role"], m["content"]) for m in history] == [
        ("user", "Shorten it"),
        ("assistant", "Here are the edits:"),
    ]
