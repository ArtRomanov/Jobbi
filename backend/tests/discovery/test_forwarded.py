"""Posts forwarded to the bot: storing them and rating them within a minute."""

from datetime import timedelta

import pytest
from sqlalchemy import select, update

from app.discovery.service import (
    FORWARDED_KIND,
    MAX_EVAL_ATTEMPTS,
    NOT_RATED_REASON,
    ForwardedChannel,
    ForwardOutcome,
    evaluate_pending,
    run_initial_scans,
    store_forwarded_post,
)
from app.discovery.types import RawPost
from app.models.vacancy import Vacancy, VacancyCardSource
from app.models.vacancy_search_settings import VacancySearchSettings
from tests.discovery.fake_bot import FakeBot
from tests.discovery.test_service import (
    CONFIG,
    NOW,
    at,
    link_telegram,
    make_pending,
    make_user,
    seen_keys,
    vacancies,
)

CHANNEL = ForwardedChannel(handle="c1234567890", label="Secret Jobs")


def _post(n: int = 1, text: str = "MATCH HIGH", job_link: str | None = None) -> RawPost:
    return RawPost(
        external_key=f"tgc:1234567890/{n}",
        url=f"https://t.me/c/1234567890/{n}",
        job_link=job_link,
        title=None,
        company=None,
        text=text,
        posted_at=NOW - timedelta(hours=3),
    )


async def _card_sources(db) -> list[tuple[str, str, str, str]]:
    async with db() as session:
        rows = await session.execute(
            select(
                VacancyCardSource.vacancy_id,
                VacancyCardSource.source_kind,
                VacancyCardSource.source_handle,
                VacancyCardSource.label,
            )
        )
        return [tuple(row) for row in rows]


async def test_forwarded_post_becomes_pending_card(factory, db) -> None:
    user_id = await make_user(db)

    outcome = await store_forwarded_post(factory, user_id, CHANNEL, _post(), NOW)

    assert outcome is ForwardOutcome.ADDED
    [card] = await vacancies(db)
    assert card.state == "pending"
    assert card.source_id is None
    assert card.url == "https://t.me/c/1234567890/1"
    assert card.alert_handled_at == NOW  # the user already knows about it
    assert await _card_sources(db) == [
        (card.id, FORWARDED_KIND, "c1234567890", "Secret Jobs")
    ]
    assert "tgc:1234567890/1" in await seen_keys(db)


async def test_forwarding_the_same_post_twice_stores_it_once(factory, db) -> None:
    user_id = await make_user(db)
    await store_forwarded_post(factory, user_id, CHANNEL, _post(), NOW)

    outcome = await store_forwarded_post(factory, user_id, CHANNEL, _post(), NOW)

    assert outcome is ForwardOutcome.ALREADY_SEEN
    assert len(await vacancies(db)) == 1


async def test_forwarded_post_ignores_exclude_terms(factory, db) -> None:
    user_id = await make_user(db, exclude=["java"])

    outcome = await store_forwarded_post(
        factory, user_id, CHANNEL, _post(text="Java developer"), NOW
    )

    assert outcome is ForwardOutcome.ADDED


async def test_repost_of_a_card_merges_into_it(factory, db) -> None:
    user_id = await make_user(db)
    link = "https://jobs.example.com/42"
    async with db() as session:
        session.add(
            Vacancy(
                id="card-1",
                user_id=user_id,
                external_key="tg:public/7",
                url="https://t.me/public/7",
                job_link=link,
                text="MATCH",
                posted_at=NOW - timedelta(days=1),
                found_at=NOW - timedelta(days=1),
                state="new",
                fit="high",
            )
        )
        await session.commit()

    outcome = await store_forwarded_post(
        factory, user_id, CHANNEL, _post(job_link=link), NOW
    )

    assert outcome is ForwardOutcome.MERGED
    assert [card.id for card in await vacancies(db)] == ["card-1"]
    assert await _card_sources(db) == [
        ("card-1", FORWARDED_KIND, "c1234567890", "Secret Jobs")
    ]


async def test_cards_are_per_user(factory, db) -> None:
    first = await make_user(db)
    second = await make_user(db, email="u2@example.com")
    await store_forwarded_post(factory, first, CHANNEL, _post(), NOW)

    outcome = await store_forwarded_post(factory, second, CHANNEL, _post(), NOW)

    assert outcome is ForwardOutcome.ADDED
    assert len(await vacancies(db)) == 2


class TestRatedWithinAMinute:
    @pytest.fixture
    def bot(self, factory) -> FakeBot:
        return FakeBot(open_transactions=factory.open_transactions)

    async def test_per_minute_run_rates_forwarded_post_without_alerting(
        self, factory, db, http, ai, sleep, bot
    ) -> None:
        user_id = await make_user(db)
        await link_telegram(db, user_id)
        await store_forwarded_post(factory, user_id, CHANNEL, _post(), NOW)

        await run_initial_scans(
            factory, http, ai, at(NOW), config=CONFIG, sleep=sleep, bot=bot
        )

        [card] = await vacancies(db)
        assert (card.state, card.fit) == ("new", "high")
        assert ai.violations == 0
        assert bot.sent == []

    async def test_per_minute_run_skips_users_without_forwarded_posts(
        self, factory, db, http, ai, sleep
    ) -> None:
        user_id = await make_user(db)
        async with db() as session:
            session.add(
                Vacancy(
                    user_id=user_id,
                    external_key="tg:public/1",
                    url="https://t.me/public/1",
                    text="MATCH",
                    posted_at=NOW,
                    found_at=NOW,
                    state="pending",
                )
            )
            await session.commit()

        await run_initial_scans(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)

        assert ai.calls == []


# --- the user picked it: never silently dropped ------------------------------------


async def test_rejected_forward_stays_as_low_fit_card(factory, db, ai, sleep) -> None:
    user_id = await make_user(db)
    await store_forwarded_post(factory, user_id, CHANNEL, _post(text="News"), NOW)

    await evaluate_pending(factory, ai, at(NOW), config=CONFIG, sleep=sleep)

    [card] = await vacancies(db)
    assert (card.state, card.fit, card.fit_reason) == ("new", "low", "News")


async def test_unratable_forward_stays_after_last_attempt(
    factory, db, ai, sleep
) -> None:
    user_id = await make_user(db)
    await store_forwarded_post(factory, user_id, CHANNEL, _post(text="BADITEM"), NOW)

    for hour in range(MAX_EVAL_ATTEMPTS):
        await evaluate_pending(
            factory, ai, at(NOW + timedelta(hours=hour)), config=CONFIG, sleep=sleep
        )

    [card] = await vacancies(db)
    assert (card.state, card.fit, card.fit_reason) == ("new", "low", NOT_RATED_REASON)


async def test_rejected_watched_post_is_still_deleted(factory, db, ai, sleep) -> None:
    user_id = await make_user(db)
    await make_pending(db, user_id, 1, text="News")

    await evaluate_pending(factory, ai, at(NOW), config=CONFIG, sleep=sleep)

    assert await vacancies(db) == []


async def test_forwarding_a_fetched_pending_post_stops_its_alert(factory, db) -> None:
    user_id = await make_user(db)
    await make_pending(db, user_id, 1)  # key tg:other/1, alert_handled_at NULL
    post = RawPost(
        external_key="tg:other/1",
        url="https://t.me/other/1",
        job_link=None,
        title=None,
        company=None,
        text="MATCH",
        posted_at=NOW,
    )

    outcome = await store_forwarded_post(
        factory, user_id, ForwardedChannel(handle="other", label="@other"), post, NOW
    )

    assert outcome is ForwardOutcome.ALREADY_SEEN
    [card] = await vacancies(db)
    assert card.alert_handled_at == NOW


# --- the per-minute run only makes the first attempt --------------------------------


async def _settings(db, user_id, **values) -> None:
    async with db() as session:
        await session.execute(
            update(VacancySearchSettings)
            .where(VacancySearchSettings.user_id == user_id)
            .values(**values)
        )
        await session.commit()


@pytest.mark.parametrize(
    "state",
    [
        {"ai_failing_since": NOW - timedelta(minutes=5)},
        {"limit_reached_on": NOW.date()},
        {"description": None},
    ],
    ids=["ai-failing", "daily-cap", "no-description"],
)
async def test_per_minute_run_leaves_stuck_forwards_to_the_hourly_check(
    factory, db, http, ai, sleep, state
) -> None:
    user_id = await make_user(db)
    await store_forwarded_post(factory, user_id, CHANNEL, _post(), NOW)
    await _settings(db, user_id, **state)

    await run_initial_scans(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)

    assert ai.calls == []


async def test_per_minute_run_does_not_retry_a_failed_attempt(
    factory, db, http, ai, sleep
) -> None:
    user_id = await make_user(db)
    await store_forwarded_post(factory, user_id, CHANNEL, _post(text="BADITEM"), NOW)

    for minute in range(3):
        await run_initial_scans(
            factory,
            http,
            ai,
            at(NOW + timedelta(minutes=minute)),
            config=CONFIG,
            sleep=sleep,
        )

    assert len(ai.calls) == 1
    [card] = await vacancies(db)
    assert (card.state, card.eval_attempts) == ("pending", 1)
