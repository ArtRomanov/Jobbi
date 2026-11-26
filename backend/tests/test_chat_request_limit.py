"""Each CV chat request fits Groq's per-request token limit. Fake Groq only.

Groq checks input + `max_tokens` against the model's tokens-per-minute limit
(gpt-oss-20b free tier: 8000) and answers 413 when one request is over it.
"""

from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

import groq
import httpx
import pytest
import structlog

from app.core.config import get_settings
from app.services import chat_service, groq_client
from app.services.chat_budget import (
    HISTORY_TRIMMED_NOTE,
    PROMPT_TOO_LARGE_DETAIL,
    input_budget,
    reply_tokens,
    request_tokens,
    retry_limit,
    with_margin,
)
from app.services.chat_tools import PROPOSE_CV_EDIT_TOOL
from app.services.groq_client import (
    GroqLimit,
    LlmRateLimitError,
    LlmRequestTooLargeError,
    parse_groq_limit,
    stream_llm_response,
)
from tests.test_chat_cards import _chunk
from tests.test_chat_follows_requests import _send_seq, _SequenceGroq, setup

__all__ = ["setup"]  # the fixture, re-used

QWEN_413 = (
    "Request too large for model `qwen/qwen3-32b` in organization `org_secret` "
    "service tier `on_demand` on input tokens per minute (ITPM): Limit 7000, "
    "Requested 7608, please reduce your message size and try again. Need more "
    "tokens? Visit https://console.groq.com/settings/billing"
)
GPT_OSS_413 = (
    "Request too large for model `openai/gpt-oss-20b` in organization "
    "`org_secret` service tier `on_demand` on tokens per minute (TPM): "
    "Limit 8000, Requested 11950, please reduce your message size and try again."
)
TPM_429 = (
    "Rate limit reached for model `openai/gpt-oss-20b` in organization "
    "`org_secret` service tier `on_demand` on tokens per minute (TPM): "
    "Limit 8000, Used 5034, Requested 1443. Please try again in 4.77s."
)
# A small overshoot: shrinking max_tokens alone can absorb it.
SMALL_413 = GPT_OSS_413.replace("Requested 11950", "Requested 8500")
LONG = "word " * 400  # ~500 tokens


def _body(message: str) -> dict[str, Any]:
    return {
        "error": {"message": message, "type": "tokens", "code": "rate_limit_exceeded"}
    }


def _status_error(
    status: int, message: str, cls: type[groq.APIStatusError] = groq.APIStatusError
) -> groq.APIStatusError:
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(status, request=request)
    return cls(message, response=response, body=_body(message))


class _FailingGroq(_SequenceGroq):
    """Answers the listed `create` calls (1-based) with `error`."""

    def __init__(self, error: Exception, at: set[int], *answers: list[Any]) -> None:
        super().__init__(*answers)
        self.error = error
        self.at = at

    async def _create(self, **kwargs: Any) -> AsyncIterator[Any]:
        if len(self.calls) + 1 in self.at:
            self.calls.append(kwargs)
            raise self.error
        return await super()._create(**kwargs)


def _midstream_error(message: str) -> groq.APIError:
    """What the Groq SDK raises for an error event inside the stream: a plain
    APIError (no status code) whose body is the error object alone."""
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    return groq.APIError(message, request, body=_body(message)["error"])


class _MidStreamFailingGroq(_SequenceGroq):
    """The listed `create` calls (1-based) open a stream that raises `error`."""

    def __init__(self, error: Exception, at: set[int], *answers: list[Any]) -> None:
        super().__init__(*answers)
        self.error = error
        self.at = at

    async def _create(self, **kwargs: Any) -> AsyncIterator[Any]:
        if len(self.calls) + 1 not in self.at:
            return await super()._create(**kwargs)
        self.calls.append(kwargs)
        error = self.error

        async def _gen() -> AsyncIterator[Any]:
            raise error
            yield  # pragma: no cover

        return _gen()


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
def logs(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[dict[str, Any]]]:
    with structlog.testing.capture_logs() as captured:
        # The module loggers may be bound already: re-create them under capture.
        monkeypatch.setattr(chat_service, "logger", structlog.get_logger())
        monkeypatch.setattr(groq_client, "logger", structlog.get_logger())
        yield captured


def _sent_tokens(call: dict[str, Any]) -> int:
    messages = call["messages"]
    return request_tokens(messages[0]["content"], messages[1:], call.get("tools"))


# ---------------------------------------------------------------------------
# Parsing Groq's limit error
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (_body(QWEN_413), GroqLimit(kind="ITPM", limit=7000, requested=7608)),
        (_body(GPT_OSS_413), GroqLimit(kind="TPM", limit=8000, requested=11950)),
        (_body(TPM_429), GroqLimit(kind="TPM", limit=8000, requested=1443)),
        # The error object alone (raised mid-stream).
        (_body(GPT_OSS_413)["error"], GroqLimit("TPM", 8000, 11950)),
        (_body("Request too large"), GroqLimit(kind=None, limit=None, requested=None)),
        (None, GroqLimit(kind=None, limit=None, requested=None)),
        ({"error": "odd"}, GroqLimit(kind=None, limit=None, requested=None)),
    ],
)
def test_groq_limit_is_parsed_from_the_error_body(
    body: object, expected: GroqLimit
) -> None:
    assert parse_groq_limit(body) == expected


# ---------------------------------------------------------------------------
# Sizing: input + max_tokens within the limit
# ---------------------------------------------------------------------------


def test_margin_covers_the_measured_undercount() -> None:
    # The estimate came out 13% under o200k_base on a Russian CV.
    assert with_margin(1000) == 1150
    assert with_margin(1) == 2


def test_input_budget_leaves_the_minimum_reply_room() -> None:
    budget = input_budget(8000, min_reply=2048, cap=6500)

    assert with_margin(budget) + 2048 <= 8000
    assert with_margin(budget + 1) + 2048 > 8000
    assert input_budget(8000, min_reply=2048, cap=3000) == 3000
    assert input_budget(1000, min_reply=2048, cap=6500) == 0


@pytest.mark.parametrize(
    ("estimated", "expected"),
    [
        (1000, 6000),  # small request: the configured cap
        (4000, 8000 - 4600),  # what is left under the limit
        (5175, 8000 - with_margin(5175)),  # at the budget: still >= the floor
        (6000, 2048),  # over the budget (callers trim first): the floor
    ],
)
def test_reply_tokens_fit_the_limit(estimated: int, expected: int) -> None:
    assert (
        reply_tokens(estimated, limit=8000, max_tokens=6000, min_reply=2048) == expected
    )


def test_retry_limit_takes_off_groq_overshoot_plus_margin() -> None:
    sent = 8000
    assert retry_limit(sent, GroqLimit("TPM", 8000, 9000)) == sent - 1000 - 200
    # Groq's own limit is lower than ours: its overshoot still decides.
    assert retry_limit(sent, GroqLimit("ITPM", 7000, 7608)) == sent - 608 - 200
    # No numbers: 15% off.
    assert retry_limit(sent, GroqLimit(None, None, None)) == sent - 1200 - 200


# ---------------------------------------------------------------------------
# Through the endpoint
# ---------------------------------------------------------------------------


async def test_max_tokens_is_sized_so_the_request_fits_the_limit(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    fake = _SequenceGroq([_chunk("Fine.")])

    await _send_seq(client, setup, fake, "Hello")

    call = fake.calls[0]
    assert with_margin(_sent_tokens(call)) + call["max_tokens"] <= 8000
    assert call["max_tokens"] == min(6000, 8000 - with_margin(_sent_tokens(call)))


async def test_long_history_is_trimmed_to_leave_the_minimum_reply(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    for i in range(8):
        await _send_seq(
            client, setup, _SequenceGroq([_chunk(f"ok{i} " + LONG)]), f"q{i} " + LONG
        )
    fake = _SequenceGroq([_chunk("Fine.")])

    await _send_seq(client, setup, fake, "latest")

    call = fake.calls[0]
    assert call["messages"][1] == {"role": "system", "content": HISTORY_TRIMMED_NOTE}
    assert call["max_tokens"] >= 2048
    assert with_margin(_sent_tokens(call)) + call["max_tokens"] <= 8000


async def test_413_retries_once_smaller_and_succeeds(
    client: httpx.AsyncClient, setup: dict[str, str], logs: list[dict[str, Any]]
) -> None:
    fake = _FailingGroq(_status_error(413, SMALL_413), {1}, [_chunk("Fine.")])

    events = await _send_seq(client, setup, fake, "Hello")

    assert len(fake.calls) == 2
    first, retry = fake.calls
    sent_first = with_margin(_sent_tokens(first)) + first["max_tokens"]
    sent_retry = with_margin(_sent_tokens(retry)) + retry["max_tokens"]
    assert sent_retry <= sent_first - (8500 - 8000) - 200
    assert [name for name, _ in events] == ["token", "cards", "done"]
    assert any(e["event"] == "chat_request_too_large_retry" for e in logs)


async def test_413_retry_trims_history_when_max_tokens_cannot_absorb_it(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    for i in range(3):
        await _send_seq(
            client, setup, _SequenceGroq([_chunk(f"ok{i} " + LONG)]), f"q{i} " + LONG
        )
    huge = GPT_OSS_413.replace("Requested 11950", "Requested 9500")
    fake = _FailingGroq(_status_error(413, huge), {1}, [_chunk("Fine.")])

    await _send_seq(client, setup, fake, "latest")

    first, retry = fake.calls
    assert len(retry["messages"]) < len(first["messages"])
    assert retry["messages"][1] == {"role": "system", "content": HISTORY_TRIMMED_NOTE}
    assert retry["max_tokens"] >= 2048


async def test_413_twice_shows_the_error(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    fake = _FailingGroq(_status_error(413, SMALL_413), {1, 2})

    events = await _send_seq(client, setup, fake, "Hello")

    assert len(fake.calls) == 2
    assert events == [("error", {"detail": PROMPT_TOO_LARGE_DETAIL["en"]})]


async def test_413_retry_that_cannot_fit_shows_the_error_without_a_request(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    # Groq claims a vast overshoot: nothing left to trim fits the retry.
    vast = GPT_OSS_413.replace("Requested 11950", "Requested 30000")
    fake = _FailingGroq(_status_error(413, vast), {1})

    events = await _send_seq(client, setup, fake, "Привет")

    assert len(fake.calls) == 1
    assert events == [("error", {"detail": PROMPT_TOO_LARGE_DETAIL["ru"]})]


async def test_413_on_the_follow_up_retries_then_keeps_the_first_reply(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    fake = _FailingGroq(
        _status_error(413, SMALL_413), {2, 3}, [_chunk("Here are the edits:")]
    )

    events = await _send_seq(client, setup, fake, "Shorten it")

    assert len(fake.calls) == 3  # first, follow-up, its one retry
    assert fake.calls[2]["max_tokens"] < fake.calls[1]["max_tokens"]
    assert [name for name, _ in events] == ["token", "cards", "done"]


async def test_413_on_the_follow_up_retry_can_succeed(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    fake = _FailingGroq(
        _status_error(413, SMALL_413),
        {2},
        [_chunk("Here are the edits:")],
        [_chunk("never")],
        [_chunk("Nothing to change after all.")],
    )

    events = await _send_seq(client, setup, fake, "Shorten it")

    assert len(fake.calls) == 3
    text = "".join(d["text"] for n, d in events if n == "token")
    assert text == "Here are the edits:\n\nNothing to change after all."


# ---------------------------------------------------------------------------
# Logs: Groq's numbers, never the message text
# ---------------------------------------------------------------------------


async def test_413_log_has_groq_numbers_and_ours_but_no_text(
    logs: list[dict[str, Any]],
) -> None:
    fake = _FailingGroq(_status_error(413, GPT_OSS_413), {1})

    with (
        patch("app.services.groq_client._get_client", return_value=fake),
        pytest.raises(LlmRequestTooLargeError) as caught,
    ):
        async for _ in stream_llm_response(
            "secret system",
            [{"role": "user", "content": "secret user"}],
            tools=[PROPOSE_CV_EDIT_TOOL],
            max_tokens=3000,
            estimated_tokens=4321,
        ):
            pass

    assert caught.value.limit == GroqLimit("TPM", 8000, 11950)
    entry = next(e for e in logs if e["event"] == "groq_request_too_large")
    assert entry["limit_kind"] == "TPM"
    assert entry["limit"] == 8000
    assert entry["requested"] == 11950
    assert entry["estimated_tokens"] == 4321
    assert entry["max_tokens"] == 3000
    assert entry["model"] == get_settings().GROQ_MODEL
    assert entry["status_code"] == 413
    flat = repr(logs)
    for secret in ("org_secret", "secret system", "secret user", "reduce your"):
        assert secret not in flat


async def test_429_log_has_groq_numbers_but_no_text(
    logs: list[dict[str, Any]],
) -> None:
    fake = _FailingGroq(_status_error(429, TPM_429, groq.RateLimitError), {1})

    with (
        patch("app.services.groq_client._get_client", return_value=fake),
        pytest.raises(LlmRateLimitError) as caught,
    ):
        async for _ in stream_llm_response("s", [], max_tokens=2000):
            pass

    assert caught.value.limit == GroqLimit("TPM", 8000, 1443)
    entry = next(e for e in logs if e["event"] == "groq_rate_limited")
    assert (entry["limit_kind"], entry["limit"], entry["requested"]) == (
        "TPM",
        8000,
        1443,
    )
    assert entry["max_tokens"] == 2000
    assert "org_secret" not in repr(logs)


async def test_request_limit_setting_is_used(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    fake = _SequenceGroq([_chunk("Fine.")])

    with _settings(CHAT_REQUEST_TOKEN_LIMIT=6000):
        await _send_seq(client, setup, fake, "Hello")

    call = fake.calls[0]
    assert with_margin(_sent_tokens(call)) + call["max_tokens"] <= 6000


# ---------------------------------------------------------------------------
# The same limit errors raised inside the stream (no status code)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("message", "error_type", "limit"),
    [
        (GPT_OSS_413, LlmRequestTooLargeError, GroqLimit("TPM", 8000, 11950)),
        (TPM_429, LlmRateLimitError, GroqLimit("TPM", 8000, 1443)),
    ],
    ids=["413", "429"],
)
async def test_midstream_limit_error_maps_like_the_status_error(
    logs: list[dict[str, Any]],
    message: str,
    error_type: type[Exception],
    limit: GroqLimit,
) -> None:
    fake = _MidStreamFailingGroq(_midstream_error(message), {1})

    with (
        patch("app.services.groq_client._get_client", return_value=fake),
        pytest.raises(error_type) as caught,
    ):
        async for _ in stream_llm_response(
            "s", [], tools=[PROPOSE_CV_EDIT_TOOL], max_tokens=2000
        ):
            pass

    assert caught.value.limit == limit  # type: ignore[attr-defined]
    assert "org_secret" not in repr(logs)


async def test_midstream_other_error_is_logged_without_its_message(
    logs: list[dict[str, Any]],
) -> None:
    error = _midstream_error("Internal failure in organization `org_secret`")
    fake = _MidStreamFailingGroq(error, {1})

    with (
        patch("app.services.groq_client._get_client", return_value=fake),
        pytest.raises(groq.APIError),
    ):
        async for _ in stream_llm_response("s", [], tools=[PROPOSE_CV_EDIT_TOOL]):
            pass

    assert any(e["event"] == "Groq API error" for e in logs)
    assert "org_secret" not in repr(logs)


async def test_midstream_413_before_any_output_retries_once_smaller(
    client: httpx.AsyncClient, setup: dict[str, str], logs: list[dict[str, Any]]
) -> None:
    fake = _MidStreamFailingGroq(
        _midstream_error(SMALL_413), {1}, [_chunk("never")], [_chunk("Fine.")]
    )

    events = await _send_seq(client, setup, fake, "Hello")

    assert len(fake.calls) == 2
    assert fake.calls[1]["max_tokens"] < fake.calls[0]["max_tokens"]
    assert [name for name, _ in events] == ["token", "cards", "done"]
    assert "org_secret" not in repr(logs)


def test_groq_limit_with_a_huge_number_is_not_parsed() -> None:
    # int() refuses over 4300 digits: that must not escape the error handler.
    huge = GPT_OSS_413.replace("Requested 11950", "Requested " + "9" * 5_000)

    assert parse_groq_limit(_body(huge)) == GroqLimit("TPM", 8000, None)
