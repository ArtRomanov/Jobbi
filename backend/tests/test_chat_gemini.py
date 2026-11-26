"""The CV chat on Gemini (`CHAT_PROVIDER=gemini`). Fake OpenAI client only:
nothing here calls Google or Groq."""

import json
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import httpx
import openai
import pytest
import structlog

from app.core.config import get_settings
from app.services import chat_service, gemini_client
from app.services.chat_budget import (
    PROMPT_TOO_LARGE_DETAIL,
    PROVIDER_NOT_CONFIGURED_DETAIL,
    RATE_LIMITED_DETAIL,
    chat_sizing,
    input_budget,
    reply_tokens,
)
from app.services.chat_tools import PROPOSE_CV_EDIT_TOOL
from app.services.gemini_client import (
    APP_NOTE_PREFIX,
    ChatProviderNotConfiguredError,
    gemini_messages,
    parse_too_long,
    stream_gemini_response,
)
from app.services.groq_client import stream_llm_response
from app.services.llm_stream import (
    NO_LIMIT_NUMBERS,
    LlmLimit,
    LlmRateLimitError,
    LlmRequestTooLargeError,
    LlmToolCall,
)
from tests.test_chat_cards import APPS, _chunk, _events, _h
from tests.test_chat_follows_requests import setup

__all__ = ["setup"]  # the fixture, re-used

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
TOO_LONG = (
    "The input token count (1048577) exceeds the maximum number of tokens "
    "allowed (1048576). project secret-project-123"
)
QUOTA = "Quota exceeded for metric generate_content_free_tier_requests, key AIza-secret"
REMOVE_JQUERY = json.dumps({"op": "remove", "before": "- jQuery"})


@contextmanager
def _settings(**values: Any) -> Iterator[None]:
    settings = get_settings()
    old = {name: getattr(settings, name) for name in values}
    for name, value in values.items():
        setattr(settings, name, value)
    try:
        yield
    finally:
        for name, value in old.items():
            setattr(settings, name, value)


@pytest.fixture
def gemini() -> Iterator[None]:
    with _settings(CHAT_PROVIDER="gemini", GEMINI_API_KEY="test-gemini-key"):
        yield


@pytest.fixture
def logs(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[dict[str, Any]]]:
    with structlog.testing.capture_logs() as captured:
        monkeypatch.setattr(chat_service, "logger", structlog.get_logger())
        monkeypatch.setattr(gemini_client, "logger", structlog.get_logger())
        yield captured


def _call(
    name: str | None, arguments: str | None, *, index: int | None, id: str | None
) -> Any:
    return SimpleNamespace(
        index=index,
        id=id,
        type="function",
        function=SimpleNamespace(name=name, arguments=arguments),
    )


class _FakeOpenAI:
    """`chat.completions.create` answers each call with the next chunks or error."""

    def __init__(self, *answers: list[Any] | Exception) -> None:
        self.answers = list(answers)
        self.calls: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs: Any) -> AsyncIterator[Any]:
        self.calls.append(kwargs)
        answer = self.answers[min(len(self.calls), len(self.answers)) - 1]
        if isinstance(answer, Exception):
            raise answer

        async def _gen() -> AsyncIterator[Any]:
            for chunk in answer:
                yield chunk

        return _gen()


def _status_error(
    cls: type[openai.APIStatusError], status: int, body: object
) -> openai.APIStatusError:
    response = httpx.Response(status, request=httpx.Request("POST", GEMINI_URL))
    return cls("error", response=response, body=body)


async def _collect(fake: _FakeOpenAI, **kwargs: Any) -> list[str | LlmToolCall]:
    with patch("app.services.gemini_client._get_client", return_value=fake):
        return [
            item
            async for item in stream_gemini_response(
                "sys", [{"role": "user", "content": "hi"}], **kwargs
            )
        ]


# ---------------------------------------------------------------------------
# Stream items
# ---------------------------------------------------------------------------


async def test_text_only_reply(gemini: None) -> None:
    fake = _FakeOpenAI([_chunk("Hello"), _chunk(", world"), _chunk(None)])

    items = await _collect(fake, tools=[PROPOSE_CV_EDIT_TOOL])

    assert items == ["Hello", ", world"]


async def test_single_whole_tool_call_in_one_chunk(gemini: None) -> None:
    fake = _FakeOpenAI(
        [
            _chunk("Removing jQuery."),
            _chunk(
                None,
                [_call("propose_cv_edit", REMOVE_JQUERY, index=None, id="")],
            ),
        ]
    )

    items = await _collect(fake, tools=[PROPOSE_CV_EDIT_TOOL])

    assert items == [
        "Removing jQuery.",
        LlmToolCall(name="propose_cv_edit", arguments=REMOVE_JQUERY),
    ]


@pytest.mark.parametrize(
    "chunks",
    [
        # Both calls in one chunk, no index: positions tell them apart.
        [
            _chunk(
                None,
                [
                    _call("propose_cv_edit", '{"a": 1}', index=None, id="c1"),
                    _call("propose_cv_edit", '{"b": 2}', index=None, id="c2"),
                ],
            )
        ],
        # One chunk per call, both at index 0 with their own ids.
        [
            _chunk(None, [_call("propose_cv_edit", '{"a": 1}', index=0, id="c1")]),
            _chunk(None, [_call("propose_cv_edit", '{"b": 2}', index=0, id="c2")]),
        ],
        # Both at index 0 without ids: a new name after complete args.
        [
            _chunk(None, [_call("propose_cv_edit", '{"a": 1}', index=0, id="")]),
            _chunk(None, [_call("propose_cv_edit", '{"b": 2}', index=0, id="")]),
        ],
        # OpenAI-style: indexes 0 and 1, arguments split over deltas.
        [
            _chunk(None, [_call("propose_cv_edit", '{"a"', index=0, id="c1")]),
            _chunk(None, [_call(None, ": 1}", index=0, id=None)]),
            _chunk(None, [_call("propose_cv_edit", '{"b": 2}', index=1, id="c2")]),
        ],
    ],
)
async def test_multiple_tool_calls(gemini: None, chunks: list[Any]) -> None:
    items = await _collect(_FakeOpenAI(chunks), tools=[PROPOSE_CV_EDIT_TOOL])

    assert items == [
        LlmToolCall(name="propose_cv_edit", arguments='{"a": 1}'),
        LlmToolCall(name="propose_cv_edit", arguments='{"b": 2}'),
    ]


# ---------------------------------------------------------------------------
# Request shape: no Groq/gpt-oss options
# ---------------------------------------------------------------------------


async def test_request_has_gemini_model_and_no_gpt_oss_options(gemini: None) -> None:
    fake = _FakeOpenAI([_chunk("ok")])

    with _settings(
        GROQ_MODEL="openai/gpt-oss-20b",
        CHAT_REASONING_EFFORT="high",
        GEMINI_REASONING_EFFORT="low",
    ):
        await _collect(fake, tools=[PROPOSE_CV_EDIT_TOOL], tool_choice="required")

    sent = fake.calls[0]
    assert sent["model"] == get_settings().GEMINI_CHAT_MODEL
    assert sent["reasoning_effort"] == "low"  # Gemini's setting, not gpt-oss's
    assert "parallel_tool_calls" not in sent
    assert sent["tool_choice"] == "auto"  # "required" is off by default
    assert sent["max_tokens"] == get_settings().GEMINI_CHAT_MAX_TOKENS
    assert sent["stream"] is True


async def test_empty_reasoning_effort_sends_none(gemini: None) -> None:
    fake = _FakeOpenAI([_chunk("ok")])

    with _settings(GEMINI_REASONING_EFFORT=""):
        await _collect(fake)

    assert "reasoning_effort" not in fake.calls[0]
    assert "tools" not in fake.calls[0]


async def test_required_tool_choice_when_enabled(gemini: None) -> None:
    fake = _FakeOpenAI([_chunk("ok")])

    with _settings(GEMINI_TOOL_CHOICE_REQUIRED=True):
        await _collect(fake, tools=[PROPOSE_CV_EDIT_TOOL], tool_choice="required")

    assert fake.calls[0]["tool_choice"] == "required"


def test_later_system_messages_become_marked_user_notes() -> None:
    messages = gemini_messages(
        "sys",
        [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
            {"role": "system", "content": "nudge"},
        ],
    )

    assert messages == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "user", "content": APP_NOTE_PREFIX + "nudge"},
    ]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({"error": {"message": TOO_LONG}}, LlmLimit("input", 1048576, 1048577)),
        ([{"error": {"message": TOO_LONG}}], LlmLimit("input", 1048576, 1048577)),
        ({"error": {"message": "Request payload is too long"}}, NO_LIMIT_NUMBERS),
        ({"error": {"message": "Invalid value at 'tools'"}}, None),
        (None, None),
    ],
)
def test_parse_too_long(body: object, expected: LlmLimit | None) -> None:
    assert parse_too_long(body) == expected


async def test_429_maps_to_rate_limit_and_logs_no_text(
    gemini: None, logs: list[dict[str, Any]]
) -> None:
    body = [{"error": {"code": 429, "message": QUOTA, "status": "RESOURCE_EXHAUSTED"}}]
    fake = _FakeOpenAI(_status_error(openai.RateLimitError, 429, body))

    with pytest.raises(LlmRateLimitError):
        await _collect(fake)

    entry = next(e for e in logs if e["event"] == "gemini_rate_limited")
    assert entry["status_code"] == 429
    assert entry["kind"] == "RESOURCE_EXHAUSTED"
    assert "AIza-secret" not in repr(logs)
    assert "test-gemini-key" not in repr(logs)


@pytest.mark.parametrize("status", [400, 413])
async def test_too_long_maps_to_request_too_large(
    gemini: None, logs: list[dict[str, Any]], status: int
) -> None:
    body = {"error": {"code": status, "message": TOO_LONG, "status": "X"}}
    fake = _FakeOpenAI(_status_error(openai.APIStatusError, status, body))

    with pytest.raises(LlmRequestTooLargeError):
        await _collect(fake)

    assert any(e["event"] == "gemini_request_too_large" for e in logs)
    assert "secret-project-123" not in repr(logs)


async def test_other_400_is_a_plain_error(
    gemini: None, logs: list[dict[str, Any]]
) -> None:
    body = {"error": {"message": "Invalid value at 'tools' AIza-secret"}}
    fake = _FakeOpenAI(_status_error(openai.BadRequestError, 400, body))

    with pytest.raises(RuntimeError) as caught:
        await _collect(fake)

    assert not isinstance(caught.value, LlmRequestTooLargeError)
    assert "AIza-secret" not in repr(logs) + str(caught.value)


async def test_missing_key_raises_not_configured() -> None:
    with (
        _settings(CHAT_PROVIDER="gemini", GEMINI_API_KEY=None),
        pytest.raises(ChatProviderNotConfiguredError),
    ):
        async for _ in stream_gemini_response("s", []):
            pass


# ---------------------------------------------------------------------------
# Provider switch and sizing
# ---------------------------------------------------------------------------


def test_get_chat_llm_follows_chat_provider() -> None:
    assert chat_service.get_chat_llm() is stream_llm_response
    with _settings(CHAT_PROVIDER="gemini"):
        assert chat_service.get_chat_llm() is stream_gemini_response


def test_gemini_sizing_fits_a_whole_cv_job_post_and_history() -> None:
    settings = get_settings()
    with _settings(CHAT_PROVIDER="gemini"):
        sizing = chat_sizing(settings)
    groq = chat_sizing(settings)

    assert groq.request_limit == settings.CHAT_REQUEST_TOKEN_LIMIT
    assert sizing.request_limit == settings.GEMINI_CHAT_REQUEST_TOKEN_LIMIT
    budget = input_budget(
        sizing.request_limit, min_reply=sizing.min_reply, cap=sizing.input_cap
    )
    # Default sizing: ~24k input estimate and the full reply cap.
    assert budget == 24000
    assert (
        reply_tokens(
            budget,
            limit=sizing.request_limit,
            max_tokens=sizing.max_tokens,
            min_reply=sizing.min_reply,
        )
        == 8192
    )


async def _send(
    client: httpx.AsyncClient, s: dict[str, str], fake: _FakeOpenAI, text: str
) -> list[tuple[str, Any]]:
    with patch("app.services.gemini_client._get_client", return_value=fake):
        resp = await client.post(
            f"{APPS}/{s['app_id']}/chat", json={"content": text}, headers=_h(s["token"])
        )
    assert resp.status_code == 200
    return _events(resp.text)


async def test_chat_on_gemini_makes_a_card(
    client: httpx.AsyncClient, setup: dict[str, str], gemini: None
) -> None:
    fake = _FakeOpenAI(
        [
            _chunk("Removed jQuery."),
            _chunk(None, [_call("propose_cv_edit", REMOVE_JQUERY, index=0, id="x")]),
        ]
    )

    with patch("app.services.groq_client._get_client") as groq_client:
        events = await _send(client, setup, fake, "Remove jQuery")

    groq_client.assert_not_called()
    assert len(fake.calls) == 1
    # Gemini sizing: the request may use the larger reply cap.
    assert fake.calls[0]["max_tokens"] == get_settings().GEMINI_CHAT_MAX_TOKENS
    cards = next(data for name, data in events if name == "cards")
    assert [c["op"] for c in cards] == ["remove"]


async def test_parse_retry_works_on_gemini(
    client: httpx.AsyncClient, setup: dict[str, str], gemini: None
) -> None:
    bad = json.dumps({"op": "remove"})  # no `before`: our parser rejects it
    fake = _FakeOpenAI(
        [
            _chunk("Edit:"),
            _chunk(None, [_call("propose_cv_edit", bad, index=0, id="")]),
        ],
        [_chunk(None, [_call("propose_cv_edit", REMOVE_JQUERY, index=0, id="")])],
    )

    events = await _send(client, setup, fake, "Remove jQuery")

    assert len(fake.calls) == 2
    retry = fake.calls[1]
    assert retry["tool_choice"] == "auto"  # "required" downgraded
    assert retry["messages"][-1]["role"] == "user"
    assert retry["messages"][-1]["content"].startswith(APP_NOTE_PREFIX)
    cards = next(data for name, data in events if name == "cards")
    assert [c["op"] for c in cards] == ["remove"]


@pytest.mark.parametrize(
    ("error", "detail"),
    [
        (
            _status_error(
                openai.RateLimitError,
                429,
                {"error": {"message": QUOTA, "status": "RESOURCE_EXHAUSTED"}},
            ),
            RATE_LIMITED_DETAIL["en"],
        ),
        (
            _status_error(
                openai.BadRequestError, 400, {"error": {"message": TOO_LONG}}
            ),
            PROMPT_TOO_LARGE_DETAIL["en"],
        ),
    ],
)
async def test_chat_errors_reach_the_user(
    client: httpx.AsyncClient,
    setup: dict[str, str],
    gemini: None,
    error: Exception,
    detail: str,
) -> None:
    events = await _send(client, setup, _FakeOpenAI(error), "Remove jQuery")

    assert events[-1] == ("error", {"detail": detail})


@pytest.mark.parametrize(("text", "language"), [("Hi there", "en"), ("Привет", "ru")])
async def test_missing_key_is_a_user_message_not_a_crash(
    client: httpx.AsyncClient,
    setup: dict[str, str],
    logs: list[dict[str, Any]],
    text: str,
    language: str,
) -> None:
    fake = _FakeOpenAI([_chunk("never")])

    with _settings(CHAT_PROVIDER="gemini", GEMINI_API_KEY=None):
        events = await _send(client, setup, fake, text)

    assert fake.calls == []
    assert events == [("error", {"detail": PROVIDER_NOT_CONFIGURED_DETAIL[language]})]
    assert any(e["event"] == "chat_provider_not_configured" for e in logs)
    history = await client.get(
        f"{APPS}/{setup['app_id']}/chat", headers=_h(setup["token"])
    )
    assert history.json() == []  # the failed send left no trace
