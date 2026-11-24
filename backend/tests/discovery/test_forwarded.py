"""Posts forwarded to the bot: storing them, rating them within a minute, and
the bot's reply with the result (spec 012, 2.2)."""

import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from telegram.error import BadRequest, Forbidden

from app.discovery import service
from app.discovery.evaluator import MAX_DIGEST_VACANCIES
from app.discovery.forward_replies import (
    ForwardResult,
    ForwardResultKind,
    format_forward_reply,
)
from app.discovery.service import (
    FORWARDED_KIND,
    MAX_EVAL_ATTEMPTS,
    ForwardedChannel,
    ForwardOutcome,
    check_all,
    cleanup,
    evaluate_pending,
    run_initial_scans,
    store_forwarded_post,
)
from app.discovery.types import PostLink, RawPost
from app.models.forwarded_post import ForwardedPost
from app.models.vacancy import Vacancy, VacancyCardSource
from app.models.vacancy_search_settings import VacancySearchSettings
from app.models.vacancy_seen_key import VacancySeenKey
from tests.discovery.fake_bot import FakeBot
from tests.discovery.test_digests import (
    DIGEST_TEXT,
    REACT_ITEM,
    REACT_LINK,
    VUE_ITEM,
    DigestGroq,
    digest,
)
from tests.discovery.test_service import (
    CHAT_ID,
    CONFIG,
    NOW,
    FakeGroq,
    at,
    link_telegram,
    make_pending,
    make_user,
    seen_keys,
    vacancies,
)

CHANNEL = ForwardedChannel(handle="c1234567890", label="Secret Jobs")
MESSAGE_ID = 31


def _post(
    n: int = 1,
    text: str = "MATCH HIGH",
    job_link: str | None = None,
    links: tuple[PostLink, ...] = (),
) -> RawPost:
    return RawPost(
        external_key=f"tgc:1234567890/{n}",
        url=f"https://t.me/c/1234567890/{n}",
        job_link=job_link,
        title=None,
        company=None,
        text=text,
        posted_at=NOW - timedelta(hours=3),
        links=links,
    )


async def _store(
    factory, user_id: str, post: RawPost, *, message_id: int = MESSAGE_ID
) -> ForwardOutcome:
    return await store_forwarded_post(
        factory,
        user_id,
        CHANNEL,
        post,
        NOW,
        chat_id=CHAT_ID,
        message_id=message_id,
    )


async def _forwards(db: async_sessionmaker[AsyncSession]) -> list[ForwardedPost]:
    async with db() as session:
        return list(
            (
                await session.scalars(
                    select(ForwardedPost).order_by(ForwardedPost.external_key)
                )
            ).all()
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


async def _make_card(
    db,
    user_id: str,
    *,
    job_link: str,
    title: str | None = "React Dev",
    company: str | None = "Old Co",
) -> None:
    async with db() as session:
        session.add(
            Vacancy(
                id="card-1",
                user_id=user_id,
                external_key="tg:public/7",
                url="https://t.me/public/7",
                job_link=job_link,
                title=title,
                company=company,
                text="MATCH",
                posted_at=NOW - timedelta(days=1),
                found_at=NOW - timedelta(days=1),
                state="new",
                fit="high",
            )
        )
        await session.commit()


# --- storing -----------------------------------------------------------------------


async def test_forwarded_post_becomes_pending_card_and_reply_target(
    factory, db
) -> None:
    user_id = await make_user(db)

    outcome = await _store(factory, user_id, _post())

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
    [forward] = await _forwards(db)
    assert (
        forward.user_id,
        forward.external_key,
        forward.chat_id,
        forward.message_id,
        forward.created_at,
        forward.reported_at,
    ) == (user_id, "tgc:1234567890/1", CHAT_ID, MESSAGE_ID, NOW, None)


async def test_forwarding_the_same_post_twice_stores_it_once(factory, db) -> None:
    user_id = await make_user(db)
    await _store(factory, user_id, _post())

    outcome = await _store(factory, user_id, _post(), message_id=99)

    assert outcome is ForwardOutcome.ALREADY_SEEN
    assert len(await vacancies(db)) == 1
    assert [f.message_id for f in await _forwards(db)] == [MESSAGE_ID]


async def test_repost_of_a_card_is_not_merged_at_store(factory, db) -> None:
    user_id = await make_user(db)
    link = "https://jobs.example.com/42"
    await _make_card(db, user_id, job_link=link)

    outcome = await _store(factory, user_id, _post(job_link=link))

    assert outcome is ForwardOutcome.ADDED
    assert sorted(c.state for c in await vacancies(db)) == ["new", "pending"]


async def test_cards_are_per_user(factory, db) -> None:
    first = await make_user(db)
    second = await make_user(db, email="u2@example.com")
    await _store(factory, first, _post())

    outcome = await _store(factory, second, _post())

    assert outcome is ForwardOutcome.ADDED
    assert len(await vacancies(db)) == 2
    assert len(await _forwards(db)) == 2


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
        factory,
        user_id,
        ForwardedChannel(handle="other", label="@other"),
        post,
        NOW,
        chat_id=CHAT_ID,
        message_id=MESSAGE_ID,
    )

    assert outcome is ForwardOutcome.ALREADY_SEEN
    [card] = await vacancies(db)
    assert card.alert_handled_at == NOW
    # Not rated yet: the rating is replied to this forward later.
    [forward] = await _forwards(db)
    assert (
        forward.user_id,
        forward.external_key,
        forward.chat_id,
        forward.message_id,
        forward.reported_at,
    ) == (user_id, "tg:other/1", CHAT_ID, MESSAGE_ID, None)


def _watched_post(n: int = 1) -> RawPost:
    return RawPost(
        external_key=f"tg:other/{n}",
        url=f"https://t.me/other/{n}",
        job_link=None,
        title=None,
        company=None,
        text="MATCH",
        posted_at=NOW,
    )


async def _store_watched(factory, user_id: str, *, message_id: int = MESSAGE_ID):
    return await store_forwarded_post(
        factory,
        user_id,
        ForwardedChannel(handle="other", label="@other"),
        _watched_post(),
        NOW,
        chat_id=CHAT_ID,
        message_id=message_id,
    )


async def test_forwarding_an_evaluated_post_records_no_reply_target(
    factory, db
) -> None:
    user_id = await make_user(db)
    async with db() as session:  # rated earlier: seen key only, no pending row
        session.add(
            VacancySeenKey(
                user_id=user_id,
                external_key="tg:other/1",
                first_seen_at=NOW - timedelta(hours=2),
                evaluated_at=NOW - timedelta(hours=1),
            )
        )
        await session.commit()

    outcome = await _store_watched(factory, user_id)

    assert outcome is ForwardOutcome.ALREADY_SEEN
    assert await _forwards(db) == []


async def test_forwarding_a_pending_post_twice_keeps_the_first_target(
    factory, db
) -> None:
    user_id = await make_user(db)
    await make_pending(db, user_id, 1)
    await _store_watched(factory, user_id)

    outcome = await _store_watched(factory, user_id, message_id=99)

    assert outcome is ForwardOutcome.ALREADY_SEEN
    assert [f.message_id for f in await _forwards(db)] == [MESSAGE_ID]


# --- the result reply --------------------------------------------------------------


@pytest.fixture
def bot(factory) -> FakeBot:
    return FakeBot(open_transactions=factory.open_transactions)


async def _rate(factory, ai, sleep, bot: FakeBot | None):
    """The per-minute run (rates forwarded posts on their first attempt)."""
    return await run_initial_scans(
        factory, None, ai, at(NOW), config=CONFIG, sleep=sleep, bot=bot
    )


async def test_single_match_replies_with_the_card(factory, db, ai, sleep, bot) -> None:
    user_id = await make_user(db)
    await link_telegram(db, user_id)
    await _store(factory, user_id, _post())

    report = await _rate(factory, ai, sleep, bot)

    [card] = await vacancies(db)
    assert (card.state, card.fit) == ("new", "high")
    assert bot.sent == [
        (CHAT_ID, "✅ Added to your Inbox: High · Frontend Developer — Acme")
    ]
    assert bot.reply_to == [MESSAGE_ID]
    assert bot.violations == 0  # sent outside any transaction
    assert ai.violations == 0
    [forward] = await _forwards(db)
    assert forward.reported_at == NOW
    assert report.forward_replies_sent == 1


async def test_forwarded_cards_are_not_in_the_combined_alert(
    factory, db, ai, sleep, bot
) -> None:
    user_id = await make_user(db)
    await link_telegram(db, user_id)
    await make_pending(db, user_id, 1)  # a watched channel's post, alertable
    await _store(factory, user_id, _post())

    await check_all(factory, None, ai, at(NOW), config=CONFIG, sleep=sleep, bot=bot)

    assert len(await vacancies(db)) == 2
    [alert] = [text for text in bot.texts if text.startswith("🔎")]
    assert alert.startswith("🔎 1 new vacancy")
    assert "✅ Added to your Inbox: High · Frontend Developer — Acme" in bot.texts
    assert sorted(bot.reply_to, key=str) == [MESSAGE_ID, None]


async def test_single_repost_merges_after_rating_and_says_already_in_inbox(
    factory, db, ai, sleep, bot
) -> None:
    user_id = await make_user(db)
    await link_telegram(db, user_id)
    link = "https://jobs.example.com/42"
    await _make_card(db, user_id, job_link=link)
    await _store(factory, user_id, _post(job_link=link))

    await _rate(factory, ai, sleep, bot)

    assert [card.id for card in await vacancies(db)] == ["card-1"]
    assert ("card-1", FORWARDED_KIND, "c1234567890", "Secret Jobs") in (
        await _card_sources(db)
    )
    assert bot.texts == ["React Dev — Old Co is already in your Inbox."]
    assert bot.reply_to == [MESSAGE_ID]


async def test_merged_reply_falls_back_to_the_verdict_names(
    factory, db, ai, sleep, bot
) -> None:
    user_id = await make_user(db)
    await link_telegram(db, user_id)
    link = "https://jobs.example.com/42"
    await _make_card(db, user_id, job_link=link, title=None, company=None)
    await _store(factory, user_id, _post(job_link=link))

    await _rate(factory, ai, sleep, bot)

    assert bot.texts == ["Frontend Developer — Acme is already in your Inbox."]


@pytest.mark.parametrize(
    ("text", "reply"),
    [
        ("News", "This post doesn't look like a vacancy."),
        ("NOMATCH Java dev", "None of the vacancies in this post match your search."),
    ],
    ids=["not-a-vacancy", "no-match"],
)
async def test_rejected_forward_is_deleted_and_replied(
    factory, db, ai, sleep, bot, text: str, reply: str
) -> None:
    user_id = await make_user(db)
    await link_telegram(db, user_id)
    await _store(factory, user_id, _post(text=text))

    await _rate(factory, ai, sleep, bot)

    assert await vacancies(db) == []  # like a channel post: no card
    assert bot.texts == [reply]
    assert bot.reply_to == [MESSAGE_ID]


async def test_unratable_forward_is_deleted_after_the_last_attempt(
    factory, db, ai, sleep, bot
) -> None:
    user_id = await make_user(db)
    await link_telegram(db, user_id)
    await _store(factory, user_id, _post(text="BADITEM"))

    for hour in range(MAX_EVAL_ATTEMPTS):
        await check_all(
            factory,
            None,
            ai,
            at(NOW + timedelta(hours=hour)),
            config=CONFIG,
            sleep=sleep,
            bot=bot,
        )
        if hour < MAX_EVAL_ATTEMPTS - 1:
            assert bot.sent == []  # no reply before the last attempt

    assert await vacancies(db) == []
    assert bot.texts == ["Jobbi couldn't rate this post."]
    assert bot.reply_to == [MESSAGE_ID]
    [forward] = await _forwards(db)
    assert forward.reported_at == NOW + timedelta(hours=MAX_EVAL_ATTEMPTS - 1)


async def test_digest_reply_counts_new_and_merged_vacancies(
    factory, db, sleep, bot
) -> None:
    user_id = await make_user(db)
    await link_telegram(db, user_id)
    await _make_card(db, user_id, job_link=REACT_LINK)  # React vacancy merges
    links = (PostLink(3, REACT_LINK), PostLink(7, "https://design.example.com/x"))
    await _store(factory, user_id, _post(text=DIGEST_TEXT, links=links))
    ai = DigestGroq({"DG_FOUR": digest(REACT_ITEM, VUE_ITEM, count=4)}, factory)

    await _rate(factory, ai, sleep, bot)

    cards = await vacancies(db)
    assert sorted(c.external_key for c in cards) == [
        "tg:public/7",
        "tgc:1234567890/1#2",
    ]
    assert bot.texts == ["✅ 2 of 4 vacancies match. Added to your Inbox."]
    assert bot.reply_to == [MESSAGE_ID]
    assert bot.violations == 0


async def test_digest_without_matches_replies_none(factory, db, sleep, bot) -> None:
    user_id = await make_user(db)
    await link_telegram(db, user_id)
    await _store(factory, user_id, _post(text="DG_NONE\nSales\nSupport"))
    ai = DigestGroq({"DG_NONE": digest(count=2)}, factory)

    await _rate(factory, ai, sleep, bot)

    assert await vacancies(db) == []
    assert bot.texts == ["None of the vacancies in this post match your search."]


@pytest.mark.parametrize(
    "error",
    [BadRequest("Message to be replied not found"), Forbidden("bot was blocked")],
)
async def test_telegram_error_still_marks_the_post_reported(
    factory, db, ai, sleep, bot, error: Exception
) -> None:
    user_id = await make_user(db)
    await link_telegram(db, user_id)
    await _store(factory, user_id, _post())
    bot.errors = [error]

    report = await _rate(factory, ai, sleep, bot)

    assert bot.sent == []
    assert bot.attempts == 1  # no retry loop
    [forward] = await _forwards(db)
    assert forward.reported_at == NOW
    assert report.forward_replies_sent == 0


async def test_without_a_bot_the_post_stays_unreported(factory, db, ai, sleep) -> None:
    user_id = await make_user(db)
    await link_telegram(db, user_id)
    await _store(factory, user_id, _post())

    report = await _rate(factory, ai, sleep, None)

    [card] = await vacancies(db)
    assert card.state == "new"
    [forward] = await _forwards(db)
    assert forward.reported_at is None
    assert len(report.forward_results) == 1


async def test_unlinked_chat_gets_no_reply_but_is_marked(
    factory, db, ai, sleep, bot
) -> None:
    user_id = await make_user(db)
    await _store(factory, user_id, _post())  # Telegram unlinked meanwhile

    await _rate(factory, ai, sleep, bot)

    assert bot.attempts == 0
    [forward] = await _forwards(db)
    assert forward.reported_at == NOW


async def test_reported_post_is_not_replied_again(factory, db, ai, sleep, bot) -> None:
    user_id = await make_user(db)
    await link_telegram(db, user_id)
    await _store(factory, user_id, _post())
    async with db() as session:
        await session.execute(
            update(ForwardedPost).values(reported_at=NOW - timedelta(minutes=1))
        )
        await session.commit()

    report = await _rate(factory, ai, sleep, bot)

    assert report.forward_results == []
    assert bot.attempts == 0


async def test_cancellation_sends_no_reply(factory, db, ai, sleep, bot) -> None:
    user_id = await make_user(db)
    await link_telegram(db, user_id)
    await make_pending(db, user_id, 1)  # its alert is sent first, then cancelled
    await _store(factory, user_id, _post())
    bot.errors = [asyncio.CancelledError()]

    with pytest.raises(asyncio.CancelledError):
        await check_all(factory, None, ai, at(NOW), config=CONFIG, sleep=sleep, bot=bot)

    assert bot.sent == []
    assert bot.attempts == 1  # only the alert was attempted
    [forward] = await _forwards(db)
    assert forward.reported_at is None


async def test_channel_posts_get_no_reply(factory, db, ai, sleep, bot) -> None:
    user_id = await make_user(db)
    await link_telegram(db, user_id)
    await make_pending(db, user_id, 1, text="News")

    report = await check_all(
        factory, None, ai, at(NOW), config=CONFIG, sleep=sleep, bot=bot
    )

    assert report.forward_results == []
    assert bot.sent == []


@pytest.mark.parametrize(
    ("result", "text"),
    [
        (
            ForwardResult(
                user_id="u",
                external_key="k",
                kind=ForwardResultKind.MATCHED,
                fit="medium",
            ),
            "✅ Added to your Inbox: Medium · Unknown role — Unknown company",
        ),
        (
            ForwardResult(
                user_id="u",
                external_key="k",
                kind=ForwardResultKind.MATCHED,
                fit="low",
                title="  QA\nEngineer ",
                company="Acme\u202e",
            ),
            "✅ Added to your Inbox: Low · QA Engineer — Acme",
        ),
        (
            ForwardResult(user_id="u", external_key="k", kind=ForwardResultKind.MERGED),
            "Unknown role — Unknown company is already in your Inbox.",
        ),
        (
            ForwardResult(
                user_id="u",
                external_key="k",
                kind=ForwardResultKind.DIGEST,
                matched=1,
                total=6,
            ),
            "✅ 1 of 6 vacancies match. Added to your Inbox.",
        ),
    ],
)
def test_format_forward_reply(result: ForwardResult, text: str) -> None:
    assert format_forward_reply(result) == text


async def test_forwarded_pending_channel_post_is_replied_after_rating(
    factory, db, ai, sleep, bot
) -> None:
    user_id = await make_user(db)
    await link_telegram(db, user_id)
    await make_pending(db, user_id, 1)  # tg:other/1 "MATCH 1"
    await _store_watched(factory, user_id)

    await _rate(factory, ai, sleep, bot)  # the per-minute run

    [card] = await vacancies(db)
    assert card.state == "new"
    assert bot.texts == ["✅ Added to your Inbox: Medium · Frontend Developer — Acme"]
    assert bot.reply_to == [MESSAGE_ID]  # no combined alert either


async def test_digest_reply_total_is_capped(factory, db, sleep, bot) -> None:
    user_id = await make_user(db)
    await link_telegram(db, user_id)
    await _store(factory, user_id, _post(text=DIGEST_TEXT))
    ai = DigestGroq({"DG_FOUR": digest(REACT_ITEM, count=10**12)}, factory)

    await _rate(factory, ai, sleep, bot)

    assert bot.texts == ["✅ 1 of 200 vacancies match. Added to your Inbox."]


@pytest.mark.parametrize("kind", list(ForwardResultKind))
def test_forward_reply_with_max_values_fits_telegram(kind) -> None:
    result = ForwardResult(
        user_id="u",
        external_key="k",
        kind=kind,
        fit="high",
        title="T" * 10_000,
        company="C" * 10_000,
        matched=MAX_DIGEST_VACANCIES,
        total=200,
    )

    assert len(format_forward_reply(result)) < 4096


class _DeletingGroq(FakeGroq):
    """Deletes every pending card while the AI is "thinking" (e.g. the user
    removed the card meanwhile)."""

    async def _create(self, **kwargs):
        async with self.factory() as session:
            await session.execute(
                Vacancy.__table__.delete().where(Vacancy.state == "pending")
            )
            await session.commit()
        return await super()._create(**kwargs)


@pytest.mark.parametrize("text", ["News", "NOMATCH Java dev"])
async def test_forward_gone_before_its_verdict_gets_no_reply(
    factory, db, sleep, bot, text: str
) -> None:
    user_id = await make_user(db)
    await link_telegram(db, user_id)
    await _store(factory, user_id, _post(text=text))
    ai = _DeletingGroq(factory)

    report = await _rate(factory, ai, sleep, bot)

    assert report.forward_results == []
    assert bot.attempts == 0
    [forward] = await _forwards(db)
    assert forward.reported_at is None


async def test_alert_failure_does_not_skip_forward_replies(
    factory, db, ai, sleep, bot, monkeypatch
) -> None:
    user_id = await make_user(db)
    await link_telegram(db, user_id)
    await _store(factory, user_id, _post())

    async def broken_alerts(*args, **kwargs):
        raise RuntimeError("alerts broke")

    monkeypatch.setattr(service, "send_run_alerts", broken_alerts)

    with pytest.raises(RuntimeError, match="alerts broke"):
        await _rate(factory, ai, sleep, bot)

    assert bot.texts == ["✅ Added to your Inbox: High · Frontend Developer — Acme"]
    [forward] = await _forwards(db)
    assert forward.reported_at == NOW


# --- rated within a minute ---------------------------------------------------------


async def test_per_minute_run_skips_users_without_forwarded_posts(
    factory, db, http, ai, sleep
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


async def test_per_minute_run_rates_only_forwarded_posts(
    factory, db, http, ai, sleep
) -> None:
    user_id = await make_user(db)
    await make_pending(db, user_id, 2, text="MATCH")  # watched posts
    async with db() as session:  # tg:other/1 already failed once (hourly retry)
        await session.execute(
            update(Vacancy)
            .where(Vacancy.external_key == "tg:other/1")
            .values(eval_attempts=1)
        )
        await session.commit()
    await _store(factory, user_id, _post(text="MATCH HIGH forwarded"))

    await run_initial_scans(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)

    assert ai.posts_sent == ["MATCH HIGH forwarded"]
    states = {c.external_key: (c.state, c.eval_attempts) for c in await vacancies(db)}
    assert states == {
        "tg:other/1": ("pending", 1),
        "tg:other/2": ("pending", 0),
        "tgc:1234567890/1": ("new", 0),
    }


async def test_rejected_watched_post_is_still_deleted(factory, db, ai, sleep) -> None:
    user_id = await make_user(db)
    await make_pending(db, user_id, 1, text="News")

    await evaluate_pending(factory, ai, at(NOW), config=CONFIG, sleep=sleep)

    assert await vacancies(db) == []


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
    await _store(factory, user_id, _post())
    await _settings(db, user_id, **state)

    await run_initial_scans(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)

    assert ai.calls == []


async def test_per_minute_run_does_not_retry_a_failed_attempt(
    factory, db, http, ai, sleep
) -> None:
    user_id = await make_user(db)
    await _store(factory, user_id, _post(text="BADITEM"))

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


# --- retention ---------------------------------------------------------------------


async def test_cleanup_deletes_forwarded_posts_after_30_days(factory, db) -> None:
    user_id = await make_user(db)
    async with db() as session:
        for n, age in ((1, timedelta(days=31)), (2, timedelta(days=29))):
            session.add(
                ForwardedPost(
                    user_id=user_id,
                    external_key=f"tgc:1/{n}",
                    chat_id=CHAT_ID,
                    message_id=n,
                    created_at=NOW - age,
                    reported_at=None if n == 1 else NOW - age,
                )
            )
        await session.commit()

    report = await cleanup(factory, at(NOW))

    assert report.forwarded_posts_deleted == 1
    assert [f.external_key for f in await _forwards(db)] == ["tgc:1/2"]
