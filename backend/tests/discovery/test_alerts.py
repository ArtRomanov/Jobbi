"""Alert text and `send_run_alerts` against a file-backed SQLite and a fake Bot."""

import itertools
import logging
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from telegram.error import Forbidden, NetworkError, RetryAfter

from app.core.database import Base
from app.discovery import alerts
from app.discovery.alerts import AlertCard, format_alert, send_run_alerts
from app.models.telegram_link import TelegramLink
from app.models.user import User
from app.models.vacancy import Vacancy
from tests.discovery.fake_bot import FakeBot

NOW = datetime(2026, 11, 22, 12, 0)
INBOX = "https://jobbi.example/inbox"
CHAT_ID = 4242
_KEYS = itertools.count(1)


def card(
    fit: str | None = "medium",
    title: str | None = "Frontend Developer",
    company: str | None = "Acme",
    *,
    hours_ago: int = 1,
) -> AlertCard:
    return AlertCard(
        fit=fit,
        title=title,
        company=company,
        posted_at=NOW - timedelta(hours=hours_ago),
    )


# --- format_alert ------------------------------------------------------------------


class TestFormatAlert:
    def test_single_card_exact_text(self) -> None:
        text = format_alert([card("high", "Frontend Developer", "Acme")], INBOX)

        assert text == (
            "🔎 1 new vacancy\n"
            "\n"
            "High · Frontend Developer — Acme\n"
            "\n"
            f"🔗 Open Inbox: {INBOX}"
        )

    def test_plural_header(self) -> None:
        text = format_alert([card(), card()], INBOX)

        assert text.splitlines()[0] == "🔎 2 new vacancies"

    def test_orders_by_fit_then_newest(self) -> None:
        cards = [
            card("low", "L-new", hours_ago=1),
            card("medium", "M-old", hours_ago=9),
            card("high", "H-old", hours_ago=8),
            card("medium", "M-new", hours_ago=2),
            card("high", "H-new", hours_ago=3),
        ]

        lines = format_alert(cards, INBOX).splitlines()[2:7]

        assert [line.split(" · ")[1].split(" — ")[0] for line in lines] == [
            "H-new",
            "H-old",
            "M-new",
            "M-old",
            "L-new",
        ]
        assert [line.split(" · ")[0] for line in lines] == [
            "High",
            "High",
            "Medium",
            "Medium",
            "Low",
        ]

    @pytest.mark.parametrize(
        ("title", "company", "expected"),
        [
            (None, "Acme", "Medium · Unknown role — Acme"),
            ("Dev", None, "Medium · Dev — Unknown company"),
            ("  ", "", "Medium · Unknown role — Unknown company"),
        ],
        ids=["no-role", "no-company", "blank-both"],
    )
    def test_unknown_role_and_company(
        self, title: str | None, company: str | None, expected: str
    ) -> None:
        text = format_alert([card("medium", title, company)], INBOX)

        assert text.splitlines()[2] == expected

    def test_caps_at_ten_lines_with_more_line(self) -> None:
        cards = [card("low", f"Low {n}", hours_ago=n) for n in range(1, 12)]
        cards.append(card("high", "Top", hours_ago=50))

        lines = format_alert(cards, INBOX).splitlines()

        assert lines[0] == "🔎 12 new vacancies"
        body = lines[2:-2]
        assert len(body) == 11
        assert body[0] == "High · Top — Acme"
        assert body[1:10] == [f"Low · Low {n} — Acme" for n in range(1, 10)]
        assert body[10] == "+2 more in Inbox"
        assert lines[-2:] == ["", f"🔗 Open Inbox: {INBOX}"]

    def test_long_role_and_company_are_shortened(self) -> None:
        text = format_alert([card("high", "R" * 200, "C\nCorp " * 40)], INBOX)

        line = text.splitlines()[2]
        role, company = line.removeprefix("High · ").split(" — ")
        assert role == "R" * 79 + "…"
        # Line breaks collapsed (one alert line per card), cut with "…".
        assert company.startswith("C Corp C Corp")
        assert len(company) <= 80 and company.endswith("…")

    def test_ten_huge_cards_fit_telegram_limit(self) -> None:
        cards = [card("high", "R" * 200, "C" * 200) for _ in range(10)]

        text = format_alert(cards, INBOX)

        assert telegram_len(text) <= 4096
        assert len(text.splitlines()) == 2 + 10 + 2

    def test_over_limit_drops_trailing_lines_and_counts_them(self) -> None:
        cards = [card("high", f"Role {n}", hours_ago=n) for n in range(1, 13)]
        full = format_alert(cards, INBOX)

        text = format_alert(cards, INBOX, max_chars=len(full) - 30)

        lines = text.splitlines()
        assert lines[0] == "🔎 12 new vacancies"
        assert lines[-1] == f"🔗 Open Inbox: {INBOX}"
        shown = [line for line in lines if line.startswith("High · ")]
        assert len(shown) < 10
        assert shown == [f"High · Role {n} — Acme" for n in range(1, len(shown) + 1)]
        assert lines[-3] == f"+{12 - len(shown)} more in Inbox"
        assert telegram_len(text) <= len(full) - 30

    def test_exactly_ten_cards_has_no_more_line(self) -> None:
        text = format_alert([card() for _ in range(10)], INBOX)

        assert "more in Inbox" not in text
        assert len(text.splitlines()) == 2 + 10 + 2


def telegram_len(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


# --- send_run_alerts ---------------------------------------------------------------


class TrackingFactory:
    def __init__(self, maker: async_sessionmaker[AsyncSession]) -> None:
        self.maker = maker
        self.sessions: list[AsyncSession] = []

    def __call__(self) -> AsyncSession:
        session = self.maker()
        self.sessions.append(session)
        return session

    def open_transactions(self) -> int:
        return sum(1 for s in self.sessions if s.in_transaction())


@pytest.fixture
async def factory(tmp_path: Path) -> AsyncGenerator[TrackingFactory, None]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'alerts.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield TrackingFactory(async_sessionmaker(engine, expire_on_commit=False))
    await engine.dispose()


@pytest.fixture
def db(factory: TrackingFactory) -> async_sessionmaker[AsyncSession]:
    return factory.maker


@pytest.fixture
def bot(factory: TrackingFactory) -> FakeBot:
    return FakeBot(open_transactions=factory.open_transactions)


class Sleeper:
    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


async def make_user(
    db: async_sessionmaker[AsyncSession], *, chat_id: int | None = CHAT_ID
) -> str:
    async with db() as session:
        user = User(
            email=f"u{next(_KEYS)}@example.com", password_hash="x", full_name="U"
        )
        session.add(user)
        await session.flush()
        if chat_id is not None:
            session.add(TelegramLink(user_id=user.id, chat_id=chat_id))
        await session.commit()
        return user.id


async def link(db: async_sessionmaker[AsyncSession], user_id: str) -> None:
    async with db() as session:
        session.add(TelegramLink(user_id=user_id, chat_id=CHAT_ID))
        await session.commit()


async def make_card(
    db: async_sessionmaker[AsyncSession],
    user_id: str,
    *,
    state: str = "new",
    fit: str = "medium",
    title: str | None = "Frontend Developer",
    initial: bool = False,
    hours_ago: int = 1,
) -> str:
    async with db() as session:
        vacancy = Vacancy(
            user_id=user_id,
            external_key=f"tg:chan/{next(_KEYS)}",
            url="https://t.me/chan/1",
            title=title,
            company="Acme",
            text="text",
            posted_at=NOW - timedelta(hours=hours_ago),
            found_at=NOW,
            state=state,
            fit=fit,
            from_initial_scan=initial,
            # As stored by the worker: first-scan cards are handled at insert.
            alert_handled_at=NOW - timedelta(hours=1) if initial else None,
        )
        session.add(vacancy)
        await session.commit()
        return vacancy.id


async def handled_at(
    db: async_sessionmaker[AsyncSession], ids: list[str]
) -> list[datetime | None]:
    async with db() as session:
        rows = await session.execute(
            select(Vacancy.id, Vacancy.alert_handled_at).where(Vacancy.id.in_(ids))
        )
        by_id = dict(rows.all())
    return [by_id[i] for i in ids]


async def run(
    factory: TrackingFactory,
    bot: FakeBot | None,
    ids_by_user: dict[str, list[str]],
    **kwargs: Any,
) -> int:
    return await send_run_alerts(
        factory,
        bot,  # type: ignore[arg-type]
        ids_by_user,
        lambda: NOW,
        inbox_url=INBOX,
        **kwargs,
    )


class TestSendRunAlerts:
    async def test_one_message_per_user(self, factory, db, bot) -> None:
        first = await make_user(db, chat_id=1)
        second = await make_user(db, chat_id=2)
        first_ids = [
            await make_card(db, first, fit="low", title="A"),
            await make_card(db, first, fit="high", title="B"),
        ]
        second_ids = [await make_card(db, second, title="C")]

        sent = await run(factory, bot, {first: first_ids, second: second_ids})

        assert sent == 2
        assert bot.sent == [
            (1, format_alert([card("high", "B"), card("low", "A")], INBOX)),
            (2, format_alert([card("medium", "C")], INBOX)),
        ]
        assert bot.texts[0].splitlines()[:4] == [
            "🔎 2 new vacancies",
            "",
            "High · B — Acme",
            "Low · A — Acme",
        ]
        assert await handled_at(db, first_ids + second_ids) == [NOW] * 3
        assert bot.violations == 0

    async def test_no_message_without_telegram_link(self, factory, db, bot) -> None:
        user_id = await make_user(db, chat_id=None)
        ids = [await make_card(db, user_id)]

        assert await run(factory, bot, {user_id: ids}) == 0

        assert bot.sent == []
        assert await handled_at(db, ids) == [NOW]

    async def test_no_message_without_bot_but_cards_handled(self, factory, db) -> None:
        user_id = await make_user(db)
        ids = [await make_card(db, user_id)]

        assert await run(factory, None, {user_id: ids}) == 0

        assert await handled_at(db, ids) == [NOW]

    async def test_initial_scan_cards_are_never_announced(
        self, factory, db, bot
    ) -> None:
        user_id = await make_user(db)
        initial_ids = [await make_card(db, user_id, initial=True) for _ in range(3)]
        hourly_id = await make_card(db, user_id, title="Hourly")

        await run(factory, bot, {user_id: [*initial_ids, hourly_id]})

        assert len(bot.sent) == 1
        assert bot.texts[0].splitlines()[0] == "🔎 1 new vacancy"
        assert "Hourly" in bot.texts[0]
        # First-scan cards keep the timestamp from their insert.
        assert await handled_at(db, initial_ids) == [NOW - timedelta(hours=1)] * 3

    async def test_only_initial_scan_cards_sends_nothing(
        self, factory, db, bot
    ) -> None:
        user_id = await make_user(db)
        ids = [await make_card(db, user_id, initial=True)]

        await run(factory, bot, {user_id: ids})

        assert bot.sent == []

    async def test_cards_that_left_the_inbox_are_not_counted(
        self, factory, db, bot
    ) -> None:
        user_id = await make_user(db)
        visible = [
            await make_card(db, user_id, state="new", title="New"),
            await make_card(db, user_id, state="seen", title="Seen"),
        ]
        gone = [
            await make_card(db, user_id, state="dismissed", title="Dismissed"),
            await make_card(db, user_id, state="added", title="Added"),
        ]

        await run(factory, bot, {user_id: visible + gone + ["deleted-card-id"]})

        [text] = bot.texts
        assert text.splitlines()[0] == "🔎 2 new vacancies"
        assert "Dismissed" not in text and "Added" not in text
        assert await handled_at(db, visible + gone) == [NOW] * 4

    async def test_handled_cards_are_not_resent(self, factory, db, bot) -> None:
        user_id = await make_user(db)
        ids = [await make_card(db, user_id)]

        await run(factory, bot, {user_id: ids})
        await run(factory, bot, {user_id: ids})

        assert len(bot.sent) == 1

    async def test_linking_telegram_later_brings_no_message_about_old_cards(
        self, factory, db, bot
    ) -> None:
        user_id = await make_user(db, chat_id=None)
        ids = [await make_card(db, user_id)]
        await run(factory, bot, {user_id: ids})

        await link(db, user_id)
        await run(factory, bot, {user_id: ids})

        assert bot.sent == []

    async def test_other_users_cards_are_ignored(self, factory, db, bot) -> None:
        me = await make_user(db, chat_id=1)
        other = await make_user(db, chat_id=2)
        other_id = await make_card(db, other)

        await run(factory, bot, {me: [other_id]})

        assert bot.sent == []
        assert await handled_at(db, [other_id]) == [None]

    async def test_empty_input_sends_nothing(self, factory, db, bot) -> None:
        user_id = await make_user(db)

        assert await run(factory, bot, {user_id: []}) == 0
        assert bot.sent == []

    async def test_retry_after_is_retried_once(self, factory, db, bot) -> None:
        user_id = await make_user(db)
        ids = [await make_card(db, user_id)]
        bot.errors.append(RetryAfter(7))
        sleep = Sleeper()

        assert await run(factory, bot, {user_id: ids}, sleep=sleep) == 1

        assert sleep.calls == [7]
        assert bot.attempts == 2
        assert len(bot.sent) == 1
        assert await handled_at(db, ids) == [NOW]

    async def test_second_retry_after_gives_up(self, factory, db, bot) -> None:
        user_id = await make_user(db)
        ids = [await make_card(db, user_id)]
        bot.errors.extend([RetryAfter(7), RetryAfter(7)])
        sleep = Sleeper()

        assert await run(factory, bot, {user_id: ids}, sleep=sleep) == 0

        assert sleep.calls == [7]
        assert bot.attempts == 2
        assert await handled_at(db, ids) == [NOW]

    @pytest.mark.parametrize(
        "error",
        [Forbidden("bot was blocked by the user"), NetworkError("connection reset")],
        ids=["forbidden", "network"],
    )
    async def test_send_errors_are_swallowed_and_cards_handled(
        self, factory, db, bot, error: Exception
    ) -> None:
        blocked = await make_user(db, chat_id=1)
        fine = await make_user(db, chat_id=2)
        blocked_ids = [await make_card(db, blocked)]
        fine_ids = [await make_card(db, fine)]
        bot.errors.append(error)

        sent = await run(factory, bot, {blocked: blocked_ids, fine: fine_ids})

        assert sent == 1
        assert [chat for chat, _ in bot.sent] == [2]
        assert await handled_at(db, blocked_ids + fine_ids) == [NOW, NOW]

    async def test_error_log_never_contains_the_token(
        self, factory, db, bot, caplog: pytest.LogCaptureFixture
    ) -> None:
        user_id = await make_user(db)
        ids = [await make_card(db, user_id)]
        bot.errors.append(
            NetworkError(f"failed https://api.telegram.org/bot{bot.token}/x")
        )

        with caplog.at_level(logging.DEBUG):
            await run(factory, bot, {user_id: ids})

        assert "Telegram error sending" in caplog.text
        assert bot.token not in caplog.text

    async def test_ten_huge_cards_are_still_sent(self, factory, db, bot) -> None:
        user_id = await make_user(db)
        ids = [await make_card(db, user_id, title="Role " * 60) for _ in range(10)]

        assert await run(factory, bot, {user_id: ids}) == 1

        [text] = bot.texts
        assert telegram_len(text) <= 4096

    async def test_database_error_for_one_user_does_not_stop_others(
        self, factory, db, bot, monkeypatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        broken = await make_user(db, chat_id=1)
        fine = await make_user(db, chat_id=2)
        broken_ids = [await make_card(db, broken)]
        fine_ids = [await make_card(db, fine)]
        real_load = alerts._load

        async def flaky_load(session_factory, user_id, card_ids):  # type: ignore[no-untyped-def]
            if user_id == broken:
                raise OperationalError("SELECT", {}, Exception("database is locked"))
            return await real_load(session_factory, user_id, card_ids)

        monkeypatch.setattr(alerts, "_load", flaky_load)

        with caplog.at_level(logging.ERROR, logger=alerts.__name__):
            sent = await run(factory, bot, {broken: broken_ids, fine: fine_ids})

        assert sent == 1
        assert [chat for chat, _ in bot.sent] == [2]
        assert f"Alerts for user {broken} failed" in caplog.text
        assert bot.token not in caplog.text
        assert await handled_at(db, fine_ids) == [NOW]
