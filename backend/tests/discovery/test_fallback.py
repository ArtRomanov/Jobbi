"""Fallback Groq model for discovery: a daily (TPD/RPD) 429 on the primary
model moves evaluation to the fallback model until the primary's retry time."""

import logging
from datetime import timedelta
from types import SimpleNamespace
from typing import Any

import groq
import httpx
import pytest

from app.core.config import Settings
from app.discovery.evaluator import (
    DEFAULT_DAILY_RETRY_S,
    MAX_DAILY_RETRY_S,
    EvaluationRateLimitedError,
    EvaluationTransportError,
    ModelChooser,
    evaluate_with_fallback,
)
from app.discovery.service import (
    DiscoveryConfig,
    ForwardedChannel,
    evaluate_pending,
    run_initial_scans,
    store_forwarded_post,
)
from app.discovery.types import RawPost
from tests.discovery.test_service import (
    CHAT_ID,
    NOW,
    at,
    get_settings_row,
    make_pending,
    make_user,
    seen_keys,
    vacancies,
)

PRIMARY = "openai/gpt-oss-20b"
FALLBACK = "openai/gpt-oss-120b"
GROQ_REQUEST = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")

TPD_MESSAGE = (
    "Rate limit reached for model `openai/gpt-oss-20b` in organization `org_x` "
    "service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 198396, "
    "Requested 3080. Please try again in 10m37.632s. Need more tokens? Upgrade."
)
TPM_MESSAGE = (
    "Rate limit reached for model `openai/gpt-oss-20b` in organization `org_x` "
    "service tier `on_demand` on tokens per minute (TPM): Limit 8000, Used 6000, "
    "Requested 3080. Please try again in 8.6s. Need more tokens? Upgrade."
)
RPD_MESSAGE = (
    "Rate limit reached for model `openai/gpt-oss-20b` in organization `org_x` "
    "service tier `on_demand` on requests per day (RPD): Limit 1000, Used 1000, "
    "Requested 1. Please try again in 1h2m3s."
)


def rate_limit(message: str, *, retry_after: str | None = None) -> groq.RateLimitError:
    body = {"message": message, "type": "tokens", "code": "rate_limit_exceeded"}
    headers = {"retry-after": retry_after} if retry_after is not None else {}
    response = httpx.Response(
        429, request=GROQ_REQUEST, json={"error": body}, headers=headers
    )
    return groq.RateLimitError(message, response=response, body={"error": body})


class Clock:
    """A fake `time.monotonic`."""

    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


def config(fallback: str = FALLBACK, clock: Clock | None = None) -> DiscoveryConfig:
    return DiscoveryConfig(
        model=PRIMARY,
        fallback_model=fallback,
        daily_limit=150,
        monotonic=clock or Clock(),
    )


# --- 429 parsing -------------------------------------------------------------------


class FakeCompletions:
    """Raises the queued error for a model (once), else answers with a match."""

    def __init__(self) -> None:
        self.errors: dict[str, list[Exception]] = {}
        self.models: list[str] = []
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        self.models.append(kwargs["model"])
        queued = self.errors.get(kwargs["model"])
        if queued:
            raise queued.pop(0)
        content = (
            '{"results": [{"key": "p1", "is_vacancy": true, "match": true, '
            '"fit": "high", "reason": "ok", "company": "A", "title": "Dev"}]}'
        )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
            usage=SimpleNamespace(total_tokens=10),
        )


class Client:
    def __init__(self) -> None:
        self.completions = FakeCompletions()
        self.chat = SimpleNamespace(completions=self.completions)


def post() -> RawPost:
    return RawPost(
        external_key="tg:jobs/1",
        url="https://t.me/jobs/1",
        job_link=None,
        title=None,
        company=None,
        text="Frontend developer wanted",
        posted_at=NOW,
    )


async def rate(client: Client, chooser: ModelChooser):
    return await evaluate_with_fallback(client, chooser, "Frontend", {}, [post()])  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("error", "daily", "retry_after_s"),
    [
        (rate_limit(TPD_MESSAGE), True, 637.632),
        (rate_limit(RPD_MESSAGE), True, 3723.0),
        (rate_limit(TPM_MESSAGE), False, 8.6),
        (rate_limit("tokens per day (TPD)", retry_after="120"), True, 120.0),
        (rate_limit("tokens per day (TPD)"), True, None),
        (rate_limit("Please try again in 250ms (TPM)"), False, 0.25),
    ],
    ids=["tpd", "rpd", "tpm", "tpd-header", "tpd-no-time", "ms"],
)
async def test_rate_limit_error_says_daily_and_retry_time(
    error: groq.RateLimitError, daily: bool, retry_after_s: float | None
) -> None:
    client = Client()
    client.completions.errors[PRIMARY] = [error]

    with pytest.raises(EvaluationRateLimitedError) as exc_info:
        await rate(client, ModelChooser(PRIMARY))

    assert exc_info.value.daily is daily
    assert exc_info.value.retry_after_s == pytest.approx(retry_after_s)


async def test_tpd_on_primary_retries_the_same_request_on_the_fallback() -> None:
    client = Client()
    client.completions.errors[PRIMARY] = [rate_limit(TPD_MESSAGE)]

    batch = await rate(client, ModelChooser(PRIMARY, FALLBACK, monotonic=Clock()))

    assert client.completions.models == [PRIMARY, FALLBACK]
    first, second = client.completions.calls
    assert {k: v for k, v in first.items() if k != "model"} == {
        k: v for k, v in second.items() if k != "model"
    }
    # Same family: same JSON mode, reasoning effort and completion cap.
    assert second["response_format"] == {"type": "json_object"}
    assert second["reasoning_effort"] == "medium"
    assert second["max_completion_tokens"] == first["max_completion_tokens"]
    assert batch.model == FALLBACK
    assert set(batch.results) == {"tg:jobs/1"}


async def test_tpm_on_primary_does_not_use_the_fallback() -> None:
    client = Client()
    client.completions.errors[PRIMARY] = [rate_limit(TPM_MESSAGE)]
    chooser = ModelChooser(PRIMARY, FALLBACK, monotonic=Clock())

    with pytest.raises(EvaluationRateLimitedError):
        await rate(client, chooser)

    assert client.completions.models == [PRIMARY]
    assert chooser.available() == [PRIMARY, FALLBACK]


async def test_primary_exhaustion_is_remembered_until_its_retry_time() -> None:
    clock = Clock()
    client = Client()
    client.completions.errors[PRIMARY] = [rate_limit(TPD_MESSAGE)]
    chooser = ModelChooser(PRIMARY, FALLBACK, monotonic=clock)

    await rate(client, chooser)
    await rate(client, chooser)
    clock.now += 637
    await rate(client, chooser)
    clock.now += 1
    batch = await rate(client, chooser)

    assert client.completions.models == [PRIMARY, FALLBACK, FALLBACK, FALLBACK, PRIMARY]
    assert batch.model == PRIMARY


async def test_daily_429_without_retry_time_waits_the_default() -> None:
    clock = Clock()
    chooser = ModelChooser(PRIMARY, FALLBACK, monotonic=clock)

    chooser.mark_exhausted(PRIMARY, None)
    clock.now += DEFAULT_DAILY_RETRY_S - 1
    assert chooser.available() == [FALLBACK]
    clock.now += 1
    assert chooser.available() == [PRIMARY, FALLBACK]


async def test_both_models_over_the_daily_limit_raises_and_skips_later_calls() -> None:
    client = Client()
    client.completions.errors[PRIMARY] = [rate_limit(TPD_MESSAGE)]
    client.completions.errors[FALLBACK] = [rate_limit(TPD_MESSAGE)]
    chooser = ModelChooser(PRIMARY, FALLBACK, monotonic=Clock())

    with pytest.raises(EvaluationRateLimitedError) as first:
        await rate(client, chooser)
    with pytest.raises(EvaluationRateLimitedError) as second:
        await rate(client, chooser)

    assert first.value.daily and second.value.daily
    # The second batch makes no request: both models are known to be out.
    assert client.completions.models == [PRIMARY, FALLBACK]


async def test_tpm_on_the_fallback_raises() -> None:
    client = Client()
    client.completions.errors[PRIMARY] = [rate_limit(TPD_MESSAGE)]
    client.completions.errors[FALLBACK] = [rate_limit(TPM_MESSAGE)]

    with pytest.raises(EvaluationRateLimitedError) as exc_info:
        await rate(client, ModelChooser(PRIMARY, FALLBACK, monotonic=Clock()))

    assert not exc_info.value.daily
    assert client.completions.models == [PRIMARY, FALLBACK]


async def test_no_fallback_when_disabled() -> None:
    client = Client()
    client.completions.errors[PRIMARY] = [rate_limit(TPD_MESSAGE)]
    chooser = ModelChooser(PRIMARY, "", monotonic=Clock())

    with pytest.raises(EvaluationRateLimitedError):
        await rate(client, chooser)

    assert client.completions.models == [PRIMARY]


def test_fallback_equal_to_primary_is_ignored() -> None:
    assert ModelChooser(PRIMARY, PRIMARY).available() == [PRIMARY]
    assert ModelChooser(PRIMARY, "  ").available() == [PRIMARY]


# --- worker runs -------------------------------------------------------------------


async def test_run_moves_to_the_fallback_and_stores_results(
    factory, db, ai, sleep, caplog
) -> None:
    user_id = await make_user(db)
    await make_pending(db, user_id, 7, text="MATCH HIGH")
    ai.errors.append(rate_limit(TPD_MESSAGE))
    cfg = config()

    with caplog.at_level(logging.INFO, logger="app.discovery.service"):
        report = await evaluate_pending(factory, ai, at(NOW), config=cfg, sleep=sleep)

    # 7 posts: a batch of 5 then 2; the 429 is retried at once on the fallback,
    # and the next batch goes straight to the fallback.
    assert ai.models == [PRIMARY, FALLBACK, FALLBACK]
    assert {c.state for c in await vacancies(db)} == {"new"}
    assert report.posts_evaluated == 7
    assert (await get_settings_row(db, user_id)).ai_failing_since is None
    assert f"rated by {FALLBACK}" in caplog.text
    assert "MATCH HIGH" not in caplog.text  # no post text in logs

    await make_pending(db, user_id, 1, start=50)
    await evaluate_pending(factory, ai, at(NOW), config=cfg, sleep=sleep)
    assert ai.models[-1] == FALLBACK  # remembered across runs of the process


async def test_tpm_stops_the_run_without_the_fallback(factory, db, ai, sleep) -> None:
    first = await make_user(db, email="a@example.com")
    second = await make_user(db, email="b@example.com")
    await make_pending(db, first, 2)
    await make_pending(db, second, 2, start=100)
    ai.errors.append(rate_limit(TPM_MESSAGE))

    await evaluate_pending(factory, ai, at(NOW), config=config(), sleep=sleep)

    assert ai.models == [PRIMARY]
    assert {r.state for r in await vacancies(db)} == {"pending"}
    failing = [
        (await get_settings_row(db, uid)).ai_failing_since for uid in (first, second)
    ]
    assert sorted(failing, key=lambda v: v is None) == [NOW, None]


async def test_fallback_429_stops_the_run(factory, db, ai, sleep) -> None:
    first = await make_user(db, email="a@example.com")
    second = await make_user(db, email="b@example.com")
    await make_pending(db, first, 2)
    await make_pending(db, second, 2, start=100)
    ai.errors.extend([rate_limit(TPD_MESSAGE), rate_limit(TPD_MESSAGE)])

    await evaluate_pending(factory, ai, at(NOW), config=config(), sleep=sleep)

    assert ai.models == [PRIMARY, FALLBACK]
    assert {r.state for r in await vacancies(db)} == {"pending"}
    failing = [
        (await get_settings_row(db, uid)).ai_failing_since for uid in (first, second)
    ]
    assert sorted(failing, key=lambda v: v is None) == [NOW, None]


async def test_primary_is_tried_again_after_its_retry_time(
    factory, db, ai, sleep
) -> None:
    clock = Clock()
    cfg = config(clock=clock)
    user_id = await make_user(db)
    await make_pending(db, user_id, 1)
    ai.errors.append(rate_limit(TPD_MESSAGE))
    await evaluate_pending(factory, ai, at(NOW), config=cfg, sleep=sleep)

    clock.now += 638
    await make_pending(db, user_id, 1, start=2)
    await evaluate_pending(factory, ai, at(NOW), config=cfg, sleep=sleep)

    assert ai.models == [PRIMARY, FALLBACK, PRIMARY]


async def test_disabled_fallback_stops_the_run_as_before(
    factory, db, ai, sleep
) -> None:
    user_id = await make_user(db)
    await make_pending(db, user_id, 2)
    ai.errors.append(rate_limit(TPD_MESSAGE))

    await evaluate_pending(factory, ai, at(NOW), config=config(""), sleep=sleep)

    assert ai.models == [PRIMARY]
    assert {r.state for r in await vacancies(db)} == {"pending"}
    assert (await get_settings_row(db, user_id)).ai_failing_since == NOW


async def test_daily_cap_counts_posts_rated_by_either_model(
    factory, db, ai, sleep
) -> None:
    user_id = await make_user(db)
    await make_pending(db, user_id, 3)
    ai.errors.append(rate_limit(TPD_MESSAGE))
    cfg = DiscoveryConfig(
        model=PRIMARY, fallback_model=FALLBACK, daily_limit=2, monotonic=Clock()
    )

    report = await evaluate_pending(factory, ai, at(NOW), config=cfg, sleep=sleep)

    assert ai.models == [PRIMARY, FALLBACK]
    assert report.posts_evaluated == 2
    assert user_id in report.users_capped
    rated = [key for key, at_ in (await seen_keys(db)).items() if at_ is not None]
    assert len(rated) == 2


async def test_forwarded_post_is_rated_by_the_fallback(factory, db, ai, sleep) -> None:
    user_id = await make_user(db)
    forwarded = RawPost(
        external_key="tgc:1234567890/1",
        url="https://t.me/c/1234567890/1",
        job_link=None,
        title=None,
        company=None,
        text="MATCH HIGH forwarded",
        posted_at=NOW - timedelta(hours=3),
    )
    await store_forwarded_post(
        factory,
        user_id,
        ForwardedChannel(handle="c1234567890", label="Secret Jobs"),
        forwarded,
        NOW,
        chat_id=CHAT_ID,
        message_id=31,
    )
    ai.errors.append(rate_limit(TPD_MESSAGE))

    report = await run_initial_scans(
        factory, None, ai, at(NOW), config=config(), sleep=sleep
    )

    assert ai.models == [PRIMARY, FALLBACK]
    [card] = await vacancies(db)
    assert (card.state, card.fit) == ("new", "high")
    assert [r.external_key for r in report.forward_results] == ["tgc:1234567890/1"]


# --- gate fixes: odd retry times, a wrong fallback name, the chat model ---------


@pytest.mark.parametrize("header", ["nan", "inf", "-inf"])
async def test_non_finite_retry_after_header_counts_as_no_retry_time(
    header: str,
) -> None:
    client = Client()
    client.completions.errors[PRIMARY] = [
        rate_limit("tokens per day (TPD)", retry_after=header)
    ]

    with pytest.raises(EvaluationRateLimitedError) as exc_info:
        await rate(client, ModelChooser(PRIMARY))

    assert exc_info.value.daily
    assert exc_info.value.retry_after_s is None


@pytest.mark.parametrize("wait", [float("nan"), float("inf")])
def test_non_finite_wait_marks_the_model_out_for_the_default(wait: float) -> None:
    clock = Clock()
    chooser = ModelChooser(PRIMARY, FALLBACK, monotonic=clock)

    chooser.mark_exhausted(PRIMARY, wait)
    clock.now += DEFAULT_DAILY_RETRY_S - 1
    assert chooser.available() == [FALLBACK]
    clock.now += 1
    assert chooser.available() == [PRIMARY, FALLBACK]


def test_huge_wait_is_capped_at_a_day() -> None:
    clock = Clock()
    chooser = ModelChooser(PRIMARY, FALLBACK, monotonic=clock)

    chooser.mark_exhausted(PRIMARY, 1e12)
    clock.now += MAX_DAILY_RETRY_S - 1
    assert chooser.available() == [FALLBACK]
    clock.now += 1
    assert chooser.available() == [PRIMARY, FALLBACK]


async def test_huge_try_again_in_is_capped_at_a_day() -> None:
    clock = Clock()
    client = Client()
    client.completions.errors[PRIMARY] = [
        rate_limit("tokens per day (TPD). Please try again in 99999999h0m0s.")
    ]
    chooser = ModelChooser(PRIMARY, FALLBACK, monotonic=clock)

    await rate(client, chooser)
    clock.now += MAX_DAILY_RETRY_S

    assert chooser.available() == [PRIMARY, FALLBACK]


def model_not_found(model: str) -> groq.NotFoundError:
    body = {
        "message": f"The model `{model}` does not exist or you do not have access.",
        "type": "invalid_request_error",
        "code": "model_not_found",
    }
    response = httpx.Response(404, request=GROQ_REQUEST, json={"error": body})
    return groq.NotFoundError("not found", response=response, body={"error": body})


async def test_unknown_fallback_is_dropped_for_the_process_with_one_error(
    caplog,
) -> None:
    clock = Clock()
    client = Client()
    client.completions.errors[PRIMARY] = [rate_limit(TPD_MESSAGE)]
    client.completions.errors[FALLBACK] = [model_not_found(FALLBACK)]
    chooser = ModelChooser(PRIMARY, FALLBACK, monotonic=clock)

    with caplog.at_level(logging.WARNING, logger="app.discovery.evaluator"):
        with pytest.raises(EvaluationRateLimitedError) as first:
            await rate(client, chooser)
        with pytest.raises(EvaluationRateLimitedError):
            await rate(client, chooser)

    # The primary's daily 429 decides: the run stops, as without a fallback.
    assert first.value.daily
    assert client.completions.models == [PRIMARY, FALLBACK]
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert FALLBACK in errors[0].getMessage()
    assert chooser.fallback == ""
    clock.now += 638
    assert chooser.available() == [PRIMARY]


async def test_unknown_primary_still_raises_a_transport_error() -> None:
    client = Client()
    client.completions.errors[PRIMARY] = [model_not_found(PRIMARY)]
    chooser = ModelChooser(PRIMARY, FALLBACK, monotonic=Clock())

    with pytest.raises(EvaluationTransportError) as exc_info:
        await rate(client, chooser)

    assert not isinstance(exc_info.value, EvaluationRateLimitedError)
    assert client.completions.models == [PRIMARY]
    assert chooser.available() == [PRIMARY, FALLBACK]


async def test_unknown_fallback_stops_the_run_not_each_user(
    factory, db, ai, sleep
) -> None:
    first = await make_user(db, email="a@example.com")
    second = await make_user(db, email="b@example.com")
    await make_pending(db, first, 1)
    await make_pending(db, second, 1, start=100)
    ai.errors.extend([rate_limit(TPD_MESSAGE), model_not_found(FALLBACK)])

    await evaluate_pending(factory, ai, at(NOW), config=config(), sleep=sleep)

    assert ai.models == [PRIMARY, FALLBACK]
    failing = [
        (await get_settings_row(db, uid)).ai_failing_since for uid in (first, second)
    ]
    assert sorted(failing, key=lambda v: v is None) == [NOW, None]


def test_startup_warns_when_the_fallback_is_the_chat_model(caplog) -> None:
    settings = Settings(
        GROQ_API_KEY="test-key",
        GROQ_MODEL="qwen/qwen3.8-27b",
        GROQ_DISCOVERY_FALLBACK_MODEL="qwen/qwen3.8-27b",
    )

    with caplog.at_level(logging.WARNING, logger="app.discovery.service"):
        DiscoveryConfig.from_settings(settings)

    assert "chat model" in caplog.text


def test_no_warning_for_the_default_fallback(caplog) -> None:
    settings = Settings(GROQ_API_KEY="test-key")

    with caplog.at_level(logging.WARNING, logger="app.discovery.service"):
        DiscoveryConfig.from_settings(settings)

    assert "chat model" not in caplog.text
