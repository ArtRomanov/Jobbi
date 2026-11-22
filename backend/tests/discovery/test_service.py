"""Discovery worker runs against a file-backed SQLite, respx and a fake Groq."""

import asyncio
import json
import re
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import groq
import httpx
import pytest
import respx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.core.database import Base
from app.discovery import service
from app.discovery.service import (
    EVAL_PAUSE_S,
    DiscoveryConfig,
    check_all,
    evaluate_pending,
    run_initial_scans,
)
from app.models.telegram_link import TelegramLink
from app.models.user import User
from app.models.vacancy import Vacancy, VacancyCardSource
from app.models.vacancy_search_settings import VacancySearchSettings
from app.models.vacancy_seen_key import VacancySeenKey
from app.models.vacancy_source import VacancySource
from tests.discovery.board_stubs import GreenhouseBoard, LeverBoard
from tests.discovery.fake_bot import FakeBot

NOW = datetime(2026, 11, 22, 12, 0)
CHANNEL = "jobbi_jobs"
CHANNEL_URL = f"https://t.me/s/{CHANNEL}"
DESCRIPTION = "Senior frontend, React, remote"
CONFIG = DiscoveryConfig(model="test-model", daily_limit=150)
GROQ_REQUEST = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
_POST_RE = re.compile(r"<<<POST (p\d+)>>>\n(.*?)\n<<<END \1>>>", re.DOTALL)


# --- infrastructure --------------------------------------------------------------


class TrackingFactory:
    """Session factory that remembers every session it made, so tests can ask
    whether any of them has an open transaction at a given moment."""

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
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'worker.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield TrackingFactory(async_sessionmaker(engine, expire_on_commit=False))
    await engine.dispose()


@pytest.fixture
def db(factory: TrackingFactory) -> async_sessionmaker[AsyncSession]:
    """Untracked sessions for test setup and assertions."""
    return factory.maker


class Sleeper:
    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


@pytest.fixture
def sleep() -> Sleeper:
    return Sleeper()


# --- Telegram stub ---------------------------------------------------------------


@dataclass
class Channel:
    """Serves `t.me/s/<name>` like Telegram: newest 20 posts, `?before=` pages."""

    name: str = CHANNEL
    posts: dict[int, tuple[str, datetime]] = field(default_factory=dict)
    requests: int = 0
    on_request: Callable[[], None] | None = None

    def add(self, post_id: int, text: str, posted_at: datetime | None = None) -> None:
        self.posts[post_id] = (text, posted_at or NOW - timedelta(hours=1))

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests += 1
        if self.on_request is not None:
            self.on_request()
        before = request.url.params.get("before")
        ids = sorted(
            (i for i in self.posts if before is None or i < int(before)),
            reverse=True,
        )[:20]
        messages = []
        for post_id in sorted(ids):
            text, posted_at = self.posts[post_id]
            messages.append(
                f'<div class="tgme_widget_message" data-post="{self.name}/{post_id}">'
                f'<div class="tgme_widget_message_text">{text}</div>'
                f'<a class="tgme_widget_message_date">'
                f'<time datetime="{posted_at.isoformat()}+00:00"></time></a></div>'
            )
        return httpx.Response(
            200, text=f"<html><body>{''.join(messages)}</body></html>"
        )


@pytest.fixture
def channel(respx_mock: respx.MockRouter) -> Channel:
    stub = Channel()
    respx_mock.get(CHANNEL_URL).mock(side_effect=stub)
    return stub


@pytest.fixture
def http() -> httpx.AsyncClient:
    return httpx.AsyncClient()


# --- Groq stub -------------------------------------------------------------------


def at(moment: datetime) -> Callable[[], datetime]:
    """A fixed clock."""
    return lambda: moment


class Ticker:
    """A clock that moves forward by `step` on every call."""

    def __init__(self, start: datetime, step: timedelta) -> None:
        self.now = start - step
        self.step = step

    def __call__(self) -> datetime:
        self.now += self.step
        return self.now


def status_error(cls: type[groq.APIStatusError], status: int) -> groq.APIStatusError:
    body = {"message": "error", "type": "error", "code": None}
    response = httpx.Response(status, request=GROQ_REQUEST, json={"error": body})
    return cls("error", response=response, body=body)


class FakeGroq:
    """Answers by post text: "MATCH" → match (fit from "HIGH"/"LOW", else
    medium), "SKIP" → left out of the answer, "BADITEM" → a malformed item
    (match without fit), "GARBAGE" anywhere in a call → the whole answer is
    not JSON, "NOVAC" → match without `is_vacancy` (live Qwen quirk), anything
    else → not a vacancy. `errors` are raised by the next calls, one each."""

    def __init__(self, factory: TrackingFactory | None = None) -> None:
        self.factory = factory
        self.calls: list[list[str]] = []  # post texts per call
        self.errors: list[Exception] = []
        self.violations = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs: Any) -> SimpleNamespace:
        if self.factory is not None and self.factory.open_transactions():
            self.violations += 1
        posts = _POST_RE.findall(kwargs["messages"][1]["content"])
        self.calls.append([text for _, text in posts])
        if self.errors:
            raise self.errors.pop(0)
        if any("GARBAGE" in text for _, text in posts):
            content = "not json"
        else:
            content = json.dumps(
                {"results": [self._verdict(*p) for p in posts if "SKIP" not in p[1]]}
            )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
            usage=SimpleNamespace(total_tokens=100),
        )

    @staticmethod
    def _verdict(key: str, text: str) -> dict[str, Any]:
        if "BADITEM" in text:
            return {"key": key, "is_vacancy": True, "match": True, "fit": None}
        if "NOVAC" in text:
            return {"key": key, "match": True, "fit": "high", "reason": "ok"}
        if "MATCH" not in text:
            return {"key": key, "is_vacancy": False, "match": False, "reason": "News"}
        fit = "high" if "HIGH" in text else "low" if "LOW" in text else "medium"
        return {
            "key": key,
            "is_vacancy": True,
            "match": True,
            "fit": fit,
            "reason": "Remote React role",
            "company": "Acme",
            "title": "Frontend Developer",
        }

    @property
    def posts_sent(self) -> list[str]:
        return [text for call in self.calls for text in call]


@pytest.fixture
def ai(factory: TrackingFactory) -> FakeGroq:
    return FakeGroq(factory)


# --- data helpers ----------------------------------------------------------------


async def make_user(
    db: async_sessionmaker[AsyncSession],
    *,
    description: str | None = DESCRIPTION,
    exclude: list[str] | None = None,
    timezone: str | None = None,
    email: str = "u1@example.com",
) -> str:
    async with db() as session:
        user = User(
            email=email,
            password_hash="x",
            full_name="U",
            timezone=timezone,
            desired_role="Frontend developer",
        )
        session.add(user)
        await session.flush()
        session.add(
            VacancySearchSettings(
                user_id=user.id, description=description, exclude_terms=exclude or []
            )
        )
        await session.commit()
        return user.id


async def make_source(
    db: async_sessionmaker[AsyncSession],
    user_id: str,
    *,
    handle: str = CHANNEL,
    scanned: bool = False,
) -> str:
    async with db() as session:
        source = VacancySource(
            user_id=user_id,
            kind="telegram",
            handle=handle,
            display_name=f"@{handle}",
            initial_scan_completed_at=NOW - timedelta(days=1) if scanned else None,
        )
        session.add(source)
        await session.commit()
        return source.id


async def make_pending(
    db: async_sessionmaker[AsyncSession],
    user_id: str,
    count: int,
    *,
    text: str = "MATCH",
    found_at: datetime = NOW - timedelta(hours=2),
    start: int = 1,
) -> None:
    async with db() as session:
        for n in range(start, start + count):
            key = f"tg:other/{n}"
            session.add(
                VacancySeenKey(
                    user_id=user_id, external_key=key, first_seen_at=found_at
                )
            )
            session.add(
                Vacancy(
                    user_id=user_id,
                    external_key=key,
                    url=f"https://t.me/other/{n}",
                    text=f"{text} {n}",
                    posted_at=found_at,
                    found_at=found_at + timedelta(seconds=n),
                    state="pending",
                )
            )
        await session.commit()


async def vacancies(db: async_sessionmaker[AsyncSession]) -> list[Vacancy]:
    async with db() as session:
        return list(
            (
                await session.scalars(select(Vacancy).order_by(Vacancy.external_key))
            ).all()
        )


async def seen_keys(db: async_sessionmaker[AsyncSession]) -> dict[str, datetime | None]:
    async with db() as session:
        rows = await session.execute(
            select(VacancySeenKey.external_key, VacancySeenKey.evaluated_at)
        )
        return {key: evaluated_at for key, evaluated_at in rows}


async def get_source(
    db: async_sessionmaker[AsyncSession], source_id: str
) -> VacancySource:
    async with db() as session:
        source = await session.get(VacancySource, source_id)
        assert source is not None
        return source


async def get_settings_row(
    db: async_sessionmaker[AsyncSession], user_id: str
) -> VacancySearchSettings:
    async with db() as session:
        row = await session.get(VacancySearchSettings, user_id)
        assert row is not None
        return row


# --- initial scan ----------------------------------------------------------------


class TestInitialScan:
    async def test_stores_pending_posts_with_seen_keys_and_card_source(
        self, factory, db, channel, http, ai, sleep
    ) -> None:
        user_id = await make_user(db, description=None)
        source_id = await make_source(db, user_id)
        channel.add(10, "MATCH one")
        channel.add(11, "MATCH two")
        channel.add(5, "too old", NOW - timedelta(days=8))

        report = await run_initial_scans(
            factory, http, ai, at(NOW), config=CONFIG, sleep=sleep
        )

        rows = await vacancies(db)
        assert [r.external_key for r in rows] == [
            f"tg:{CHANNEL}/10",
            f"tg:{CHANNEL}/11",
        ]
        for row in rows:
            assert row.state == "pending"
            assert row.from_initial_scan is True
            assert row.alert_handled_at == NOW  # never alerted
            assert row.found_at == NOW
            assert row.source_id == source_id
            assert (
                row.url
                == f"https://t.me/{CHANNEL}/{row.external_key.rsplit('/', 1)[1]}"
            )
        assert await seen_keys(db) == {
            f"tg:{CHANNEL}/10": None,
            f"tg:{CHANNEL}/11": None,
        }
        async with db() as session:
            rows = await session.execute(
                select(
                    VacancyCardSource.source_id,
                    VacancyCardSource.source_kind,
                    VacancyCardSource.source_handle,
                    VacancyCardSource.label,
                )
            )
            assert [tuple(r) for r in rows] == [
                (source_id, "telegram", CHANNEL, f"@{CHANNEL}")
            ] * 2
        source = await get_source(db, source_id)
        assert source.initial_scan_completed_at == NOW
        assert source.last_checked_at == NOW
        # No description: nothing sent to the AI.
        assert ai.calls == []
        assert report.posts_stored == 2

    async def test_completed_source_is_not_scanned_again(
        self, factory, db, channel, http, ai, sleep
    ) -> None:
        user_id = await make_user(db, description=None)
        await make_source(db, user_id)
        channel.add(10, "MATCH")

        await run_initial_scans(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)
        requests_after_first_scan = channel.requests
        await run_initial_scans(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)

        assert requests_after_first_scan > 0
        assert channel.requests == requests_after_first_scan

    async def test_evaluates_with_description(
        self, factory, db, channel, http, ai, sleep
    ) -> None:
        user_id = await make_user(db)
        await make_source(db, user_id)
        channel.add(10, "MATCH HIGH")
        channel.add(11, "Our channel turns 5")

        await run_initial_scans(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)

        rows = await vacancies(db)
        assert len(rows) == 1
        card = rows[0]
        assert (card.state, card.fit, card.fit_reason) == (
            "new",
            "high",
            "Remote React role",
        )
        assert (card.company, card.title) == ("Acme", "Frontend Developer")
        assert card.alert_handled_at == NOW
        # Rejected post: row gone, key kept and marked evaluated.
        assert await seen_keys(db) == {f"tg:{CHANNEL}/10": NOW, f"tg:{CHANNEL}/11": NOW}
        async with db() as session:
            assert (
                await session.scalar(
                    select(func.count()).select_from(VacancyCardSource)
                )
                == 1
            )

    async def test_exclude_words_record_key_without_card(
        self, factory, db, channel, http, ai, sleep
    ) -> None:
        user_id = await make_user(db, exclude=["java"])
        await make_source(db, user_id)
        channel.add(10, "MATCH Senior Java engineer")
        channel.add(11, "MATCH JavaScript developer")

        await run_initial_scans(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)

        assert [r.external_key for r in await vacancies(db)] == [f"tg:{CHANNEL}/11"]
        assert await seen_keys(db) == {
            f"tg:{CHANNEL}/10": None,
            f"tg:{CHANNEL}/11": NOW,
        }
        assert ai.posts_sent == ["MATCH JavaScript developer"]

    async def test_readded_source_skips_posts_seen_before(
        self, factory, db, channel, http, ai, sleep
    ) -> None:
        user_id = await make_user(db, description=None)
        async with db() as session:
            session.add(
                VacancySeenKey(
                    user_id=user_id, external_key=f"tg:{CHANNEL}/10", first_seen_at=NOW
                )
            )
            await session.commit()
        await make_source(db, user_id)
        channel.add(10, "MATCH old")
        channel.add(11, "MATCH new")

        await run_initial_scans(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)

        assert [r.external_key for r in await vacancies(db)] == [f"tg:{CHANNEL}/11"]

    @pytest.mark.parametrize(
        ("response", "message"),
        [
            (
                httpx.Response(302, headers={"Location": f"https://t.me/{CHANNEL}"}),
                "Channel is private or deleted",
            ),
            (httpx.Response(500), "Could not reach the source"),
        ],
    )
    async def test_read_error_marks_source_and_retries(
        self, factory, db, respx_mock, http, ai, sleep, response, message
    ) -> None:
        route = respx_mock.get(CHANNEL_URL).mock(return_value=response)
        user_id = await make_user(db)
        source_id = await make_source(db, user_id)

        await run_initial_scans(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)
        await run_initial_scans(
            factory,
            http,
            ai,
            at(NOW + timedelta(minutes=1)),
            config=CONFIG,
            sleep=sleep,
        )

        source = await get_source(db, source_id)
        assert source.failing_since == NOW  # first failure kept
        assert source.last_error == message
        assert source.initial_scan_completed_at is None
        assert source.last_checked_at is None
        assert route.call_count == 2  # retried on the next minute run
        assert await vacancies(db) == []

    async def test_success_after_failure_clears_error(
        self, factory, db, channel, http, ai, sleep
    ) -> None:
        user_id = await make_user(db, description=None)
        source_id = await make_source(db, user_id)
        async with db() as session:
            source = await session.get(VacancySource, source_id)
            source.failing_since = NOW - timedelta(hours=30)
            source.last_error = "Could not reach the source"
            await session.commit()

        await run_initial_scans(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)

        source = await get_source(db, source_id)
        assert (source.failing_since, source.last_error) == (None, None)
        assert source.initial_scan_completed_at == NOW

    async def test_source_removed_during_fetch_stores_nothing(
        self, factory, db, channel, http, ai, sleep, monkeypatch
    ) -> None:
        user_id = await make_user(db, description=None)
        source_id = await make_source(db, user_id)
        channel.add(10, "MATCH")
        original = service.fetch_channel_posts

        async def fetch_then_user_removes_source(*args: Any, **kwargs: Any) -> Any:
            posts = await original(*args, **kwargs)
            async with db() as session:
                await session.delete(await session.get(VacancySource, source_id))
                await session.commit()
            return posts

        monkeypatch.setattr(
            service, "fetch_channel_posts", fetch_then_user_removes_source
        )

        await run_initial_scans(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)

        assert channel.requests >= 1
        assert await vacancies(db) == []
        assert await seen_keys(db) == {}


# --- hourly check ----------------------------------------------------------------


class TestCheckAll:
    async def test_skips_sources_mid_scan(
        self, factory, db, channel, http, ai, sleep
    ) -> None:
        user_id = await make_user(db)
        await make_source(db, user_id, scanned=False)
        channel.add(10, "MATCH")

        await check_all(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)

        assert channel.requests == 0
        assert await vacancies(db) == []

    async def test_new_posts_are_pending_then_rated_not_from_initial_scan(
        self, factory, db, channel, http, ai, sleep
    ) -> None:
        user_id = await make_user(db)
        source_id = await make_source(db, user_id, scanned=True)
        channel.add(10, "MATCH LOW")

        await check_all(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)

        [card] = await vacancies(db)
        assert (card.state, card.fit, card.from_initial_scan) == ("new", "low", False)
        assert card.alert_handled_at == NOW  # handled by alerts, even with no bot
        source = await get_source(db, source_id)
        assert source.last_checked_at == NOW

    async def test_nothing_evaluated_twice_across_runs(
        self, factory, db, channel, http, ai, sleep
    ) -> None:
        user_id = await make_user(db)
        await make_source(db, user_id)
        channel.add(10, "MATCH a")
        channel.add(11, "not a vacancy")

        await run_initial_scans(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)
        await check_all(
            factory, http, ai, at(NOW + timedelta(hours=1)), config=CONFIG, sleep=sleep
        )
        assert ai.posts_sent == ["MATCH a", "not a vacancy"]

        channel.add(12, "MATCH b")
        await check_all(
            factory, http, ai, at(NOW + timedelta(hours=2)), config=CONFIG, sleep=sleep
        )
        await check_all(
            factory, http, ai, at(NOW + timedelta(hours=3)), config=CONFIG, sleep=sleep
        )

        assert ai.posts_sent == ["MATCH a", "not a vacancy", "MATCH b"]
        assert len(await vacancies(db)) == 2  # the rejected post never comes back
        assert len(await seen_keys(db)) == 3

    async def test_read_failure_does_not_stop_other_sources(
        self, factory, db, channel, respx_mock, http, ai, sleep
    ) -> None:
        user_id = await make_user(db)
        broken_id = await make_source(
            db, user_id, handle="broken_channel", scanned=True
        )
        respx_mock.get("https://t.me/s/broken_channel").mock(
            return_value=httpx.Response(503)
        )
        await make_source(db, user_id, scanned=True)
        channel.add(10, "MATCH")

        report = await check_all(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)

        broken = await get_source(db, broken_id)
        assert (broken.failing_since, broken.last_error) == (
            NOW,
            "Could not reach the source",
        )
        assert report.sources_failed == 1
        assert [c.state for c in await vacancies(db)] == ["new"]

    async def test_success_clears_failing_source(
        self, factory, db, channel, http, ai, sleep
    ) -> None:
        user_id = await make_user(db)
        source_id = await make_source(db, user_id, scanned=True)
        async with db() as session:
            source = await session.get(VacancySource, source_id)
            source.failing_since = NOW - timedelta(hours=2)
            source.last_error = "Channel is private or deleted"
            await session.commit()

        await check_all(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)

        source = await get_source(db, source_id)
        assert (source.failing_since, source.last_error, source.last_checked_at) == (
            None,
            None,
            NOW,
        )


# --- evaluation ------------------------------------------------------------------


class TestEvaluation:
    async def test_missing_keys_stay_pending_and_are_not_resent_this_run(
        self, factory, db, ai, sleep
    ) -> None:
        user_id = await make_user(db)
        await make_pending(db, user_id, 1, text="MATCH")
        await make_pending(db, user_id, 1, text="SKIP", start=2)

        report = await evaluate_pending(
            factory, ai, at(NOW), config=CONFIG, sleep=sleep
        )

        states = {
            r.external_key: (r.state, r.eval_attempts) for r in await vacancies(db)
        }
        assert states == {"tg:other/1": ("new", 0), "tg:other/2": ("pending", 1)}
        keys = await seen_keys(db)
        assert keys["tg:other/2"] is None
        assert len(ai.calls) == 1
        assert report.posts_evaluated == 1

        await evaluate_pending(
            factory, ai, at(NOW + timedelta(hours=1)), config=CONFIG, sleep=sleep
        )
        assert ai.posts_sent[-1] == "SKIP 2"  # retried on the next run

    async def test_company_and_title_only_fill_missing(
        self, factory, db, ai, sleep
    ) -> None:
        user_id = await make_user(db)
        await make_pending(db, user_id, 1)
        async with db() as session:
            row = (await session.scalars(select(Vacancy))).one()
            row.company = "Known Co"
            await session.commit()

        await evaluate_pending(factory, ai, at(NOW), config=CONFIG, sleep=sleep)

        [card] = await vacancies(db)
        assert (card.company, card.title) == ("Known Co", "Frontend Developer")

    async def test_batches_of_five_paced_30s(self, factory, db, ai, sleep) -> None:
        user_id = await make_user(db)
        await make_pending(db, user_id, 7)

        await evaluate_pending(factory, ai, at(NOW), config=CONFIG, sleep=sleep)

        assert [len(call) for call in ai.calls] == [5, 2]
        assert ai.posts_sent == [f"MATCH {n}" for n in range(1, 8)]  # oldest first
        assert sleep.calls == [EVAL_PAUSE_S]

    async def test_no_description_stays_pending(self, factory, db, ai, sleep) -> None:
        user_id = await make_user(db, description=None)
        await make_pending(db, user_id, 2)

        await evaluate_pending(factory, ai, at(NOW), config=CONFIG, sleep=sleep)

        assert ai.calls == []
        assert {r.state for r in await vacancies(db)} == {"pending"}
        assert set((await seen_keys(db)).values()) == {None}

    async def test_daily_cap_across_local_midnight(
        self, factory, db, ai, sleep
    ) -> None:
        # Tbilisi is UTC+4: 19:30 UTC is 23:30 local, 20:30 UTC is 00:30 next day.
        user_id = await make_user(db, timezone="Asia/Tbilisi")
        config = DiscoveryConfig(model="m", daily_limit=3)
        async with db() as session:
            for n in range(3):  # evaluated earlier the same local day (14:00 local)
                session.add(
                    VacancySeenKey(
                        user_id=user_id,
                        external_key=f"tg:done/{n}",
                        first_seen_at=NOW - timedelta(hours=2),
                        evaluated_at=datetime(2026, 11, 22, 10, 0),
                    )
                )
            await session.commit()
        await make_pending(db, user_id, 5)

        late_evening = datetime(2026, 11, 22, 19, 30)
        report = await evaluate_pending(
            factory, ai, at(late_evening), config=config, sleep=sleep
        )
        assert ai.calls == []
        assert report.users_capped == {user_id}
        assert (await get_settings_row(db, user_id)).limit_reached_on == date(
            2026, 11, 22
        )

        after_midnight = datetime(2026, 11, 22, 20, 30)
        await evaluate_pending(
            factory, ai, at(after_midnight), config=config, sleep=sleep
        )
        assert ai.posts_sent == ["MATCH 1", "MATCH 2", "MATCH 3"]
        assert (await get_settings_row(db, user_id)).limit_reached_on == date(
            2026, 11, 23
        )
        states = [r.state for r in await vacancies(db)]
        assert states.count("pending") == 2  # waiting, never dropped

    async def test_invalid_timezone_counts_utc_day(
        self, factory, db, ai, sleep
    ) -> None:
        user_id = await make_user(db, timezone="Not/AZone")
        config = DiscoveryConfig(model="m", daily_limit=1)
        async with db() as session:
            session.add(
                VacancySeenKey(
                    user_id=user_id,
                    external_key="tg:done/1",
                    first_seen_at=NOW,
                    evaluated_at=datetime(2026, 11, 21, 23, 59),  # yesterday in UTC
                )
            )
            await session.commit()
        await make_pending(db, user_id, 2)

        await evaluate_pending(factory, ai, at(NOW), config=config, sleep=sleep)

        assert ai.posts_sent == ["MATCH 1"]

    async def test_rate_limit_stops_the_run(self, factory, db, ai, sleep) -> None:
        first = await make_user(db, email="a@example.com")
        second = await make_user(db, email="b@example.com")
        await make_pending(db, first, 6)
        await make_pending(db, second, 2, start=100)
        ai.errors.append(status_error(groq.RateLimitError, 429))

        await evaluate_pending(factory, ai, at(NOW), config=CONFIG, sleep=sleep)

        assert len(ai.calls) == 1
        assert {r.state for r in await vacancies(db)} == {"pending"}
        failing = [
            (await get_settings_row(db, uid)).ai_failing_since
            for uid in (first, second)
        ]
        assert sorted(failing, key=lambda v: v is None) == [NOW, None]

    async def test_transport_error_sets_failing_and_success_clears(
        self, factory, db, ai, sleep
    ) -> None:
        first = await make_user(db, email="a@example.com")
        second = await make_user(db, email="b@example.com")
        await make_pending(db, first, 1)
        await make_pending(db, second, 1, start=100)
        users = [first, second]  # served by oldest pending post
        ai.errors.append(groq.APIConnectionError(request=GROQ_REQUEST))
        ai.errors.append(status_error(groq.InternalServerError, 503))

        await evaluate_pending(factory, ai, at(NOW), config=CONFIG, sleep=sleep)
        # Both users tried once (a transport error stops only that user).
        assert len(ai.calls) == 2
        for uid in users:
            assert (await get_settings_row(db, uid)).ai_failing_since == NOW

        ai.errors.append(groq.APIConnectionError(request=GROQ_REQUEST))
        later = NOW + timedelta(hours=1)
        await evaluate_pending(factory, ai, at(later), config=CONFIG, sleep=sleep)
        failed_again, recovered = users
        assert (
            await get_settings_row(db, failed_again)
        ).ai_failing_since == NOW  # kept
        assert (await get_settings_row(db, recovered)).ai_failing_since is None
        assert {r.user_id: r.state for r in await vacancies(db)} == {
            failed_again: "pending",
            recovered: "new",
        }

    async def test_format_error_counts_attempts_then_rejects(
        self, factory, db, ai, sleep
    ) -> None:
        user_id = await make_user(db)
        await make_pending(db, user_id, 1, text="GARBAGE")
        async with db() as session:
            row = await session.get(VacancySearchSettings, user_id)
            row.ai_failing_since = NOW - timedelta(hours=3)
            await session.commit()

        await evaluate_pending(factory, ai, at(NOW), config=CONFIG, sleep=sleep)
        [row] = await vacancies(db)
        assert (row.state, row.eval_attempts) == ("pending", 1)
        assert len(ai.calls) == 1  # one attempt per run
        assert (await get_settings_row(db, user_id)).ai_failing_since is None

        await evaluate_pending(factory, ai, at(NOW), config=CONFIG, sleep=sleep)
        report = await evaluate_pending(
            factory, ai, at(NOW), config=CONFIG, sleep=sleep
        )

        assert report.rejected == 1
        assert await vacancies(db) == []
        assert "tg:other/1" in await seen_keys(db)

    async def test_malformed_item_hurts_only_its_post(
        self, factory, db, ai, sleep
    ) -> None:
        """Live 2026-11-22: one bad item used to fail the whole batch."""
        user_id = await make_user(db)
        await make_pending(db, user_id, 1, text="MATCH HIGH")
        await make_pending(db, user_id, 1, text="BADITEM", start=2)
        await make_pending(db, user_id, 1, text="news", start=3)

        report = await evaluate_pending(
            factory, ai, at(NOW), config=CONFIG, sleep=sleep
        )

        assert len(ai.calls) == 1
        rows = {r.external_key: (r.state, r.eval_attempts) for r in await vacancies(db)}
        assert rows == {"tg:other/1": ("new", 0), "tg:other/2": ("pending", 1)}
        keys = await seen_keys(db)
        assert (keys["tg:other/1"], keys["tg:other/2"], keys["tg:other/3"]) == (
            NOW,
            None,
            NOW,
        )
        assert report.posts_evaluated == 2

    async def test_post_without_valid_verdict_rejected_after_three_runs(
        self, factory, db, ai, sleep
    ) -> None:
        user_id = await make_user(db)
        await make_pending(db, user_id, 1, text="BADITEM")
        await make_pending(db, user_id, 1, text="SKIP", start=2)

        for hour in range(2):
            await evaluate_pending(
                factory, ai, at(NOW + timedelta(hours=hour)), config=CONFIG, sleep=sleep
            )
            assert {r.eval_attempts for r in await vacancies(db)} == {hour + 1}
        report = await evaluate_pending(
            factory, ai, at(NOW + timedelta(hours=2)), config=CONFIG, sleep=sleep
        )

        assert report.rejected == 2
        assert await vacancies(db) == []
        assert set(await seen_keys(db)) == {"tg:other/1", "tg:other/2"}
        assert len(ai.calls) == 3  # one call per run, never retried in a run

    async def test_missing_is_vacancy_still_creates_card(
        self, factory, db, ai, sleep
    ) -> None:
        user_id = await make_user(db)
        await make_pending(db, user_id, 1, text="NOVAC")

        await evaluate_pending(factory, ai, at(NOW), config=CONFIG, sleep=sleep)

        [card] = await vacancies(db)
        assert (card.state, card.fit) == ("new", "high")

    async def test_whole_batch_format_error_is_split_into_single_posts(
        self, factory, db, ai, sleep
    ) -> None:
        user_id = await make_user(db)
        await make_pending(db, user_id, 2, text="MATCH")
        await make_pending(db, user_id, 1, text="GARBAGE", start=3)
        await make_pending(db, user_id, 1, text="news", start=4)

        await evaluate_pending(factory, ai, at(NOW), config=CONFIG, sleep=sleep)

        assert [len(call) for call in ai.calls] == [4, 1, 1, 1, 1]
        assert sleep.calls == [EVAL_PAUSE_S] * 4  # single posts are paced too
        rows = {r.external_key: (r.state, r.eval_attempts) for r in await vacancies(db)}
        assert rows == {
            "tg:other/1": ("new", 0),
            "tg:other/2": ("new", 0),
            "tg:other/3": ("pending", 1),  # only the poison post pays
        }
        assert "tg:other/4" in await seen_keys(db)

    async def test_split_stops_on_transport_error(self, factory, db, ai, sleep) -> None:
        user_id = await make_user(db)
        await make_pending(db, user_id, 1, text="GARBAGE")
        await make_pending(db, user_id, 1, text="MATCH", start=2)
        # First call: whole batch not JSON; second call (first single): 429.
        original = ai.chat.completions.create
        calls = 0

        async def create(**kwargs: Any) -> Any:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise status_error(groq.RateLimitError, 429)
            return await original(**kwargs)

        ai.chat.completions.create = create

        await evaluate_pending(factory, ai, at(NOW), config=CONFIG, sleep=sleep)

        assert calls == 2
        rows = {r.external_key: (r.state, r.eval_attempts) for r in await vacancies(db)}
        assert rows == {"tg:other/1": ("pending", 0), "tg:other/2": ("pending", 0)}
        assert (await get_settings_row(db, user_id)).ai_failing_since == NOW

    async def test_clock_is_read_per_batch(self, factory, db, ai, sleep) -> None:
        user_id = await make_user(db)
        await make_pending(db, user_id, 7)
        clock = Ticker(NOW, timedelta(seconds=30))

        await evaluate_pending(factory, ai, clock, config=CONFIG, sleep=sleep)

        stamps = sorted(set((await seen_keys(db)).values()))
        assert len(stamps) == 2 and stamps[0] < stamps[1]

    async def test_daily_cap_rolls_over_midnight_within_one_run(
        self, factory, db, ai, sleep
    ) -> None:
        user_id = await make_user(db)  # UTC
        await make_pending(db, user_id, 4)
        config = DiscoveryConfig(model="m", daily_limit=2)
        # Each call to the clock moves 10 minutes; the run starts 23:40 UTC.
        clock = Ticker(datetime(2026, 11, 22, 23, 40), timedelta(minutes=10))

        await evaluate_pending(factory, ai, clock, config=config, sleep=sleep)

        # 2 posts on Nov 22, then the new day allows 2 more in the same run.
        assert len(ai.posts_sent) == 4
        days = sorted(v.date() for v in (await seen_keys(db)).values() if v)
        assert days == [date(2026, 11, 22)] * 2 + [date(2026, 11, 23)] * 2

    async def test_users_served_by_oldest_pending_post(
        self, factory, db, ai, sleep
    ) -> None:
        newer = await make_user(db, email="a@example.com")
        older = await make_user(db, email="b@example.com")
        await make_pending(
            db, newer, 1, text="MATCH newer", found_at=NOW - timedelta(hours=1)
        )
        await make_pending(
            db,
            older,
            1,
            text="MATCH older",
            found_at=NOW - timedelta(hours=5),
            start=50,
        )
        ai.errors.append(status_error(groq.RateLimitError, 429))

        await evaluate_pending(factory, ai, at(NOW), config=CONFIG, sleep=sleep)

        # The longest-waiting user is tried first; 429 stops the run.
        assert ai.posts_sent == ["MATCH older 50"]
        await evaluate_pending(
            factory, ai, at(NOW + timedelta(hours=1)), config=CONFIG, sleep=sleep
        )
        assert ai.posts_sent[1:] == ["MATCH older 50", "MATCH newer 1"]


# --- alerts ----------------------------------------------------------------------

CHAT_ID = 777


@pytest.fixture
def bot(factory: TrackingFactory) -> FakeBot:
    return FakeBot(open_transactions=factory.open_transactions)


async def link_telegram(db: async_sessionmaker[AsyncSession], user_id: str) -> None:
    async with db() as session:
        session.add(TelegramLink(user_id=user_id, chat_id=CHAT_ID))
        await session.commit()


async def set_description(
    db: async_sessionmaker[AsyncSession], user_id: str, description: str
) -> None:
    async with db() as session:
        row = await session.get(VacancySearchSettings, user_id)
        assert row is not None
        row.description = description
        await session.commit()


class TestAlerts:
    async def test_check_all_sends_one_grouped_message(
        self, factory, db, channel, http, ai, sleep, bot
    ) -> None:
        user_id = await make_user(db)
        await link_telegram(db, user_id)
        await make_source(db, user_id, scanned=True)
        channel.add(10, "MATCH LOW", NOW - timedelta(hours=1))
        channel.add(11, "MATCH HIGH", NOW - timedelta(hours=3))
        channel.add(12, "not a vacancy")

        report = await check_all(
            factory, http, ai, at(NOW), config=CONFIG, sleep=sleep, bot=bot
        )

        inbox = f"{get_settings().JOBBI_PUBLIC_URL.rstrip('/')}/inbox"
        assert bot.sent == [
            (
                CHAT_ID,
                (
                    "🔎 2 new vacancies\n"
                    "\n"
                    "High · Frontend Developer — Acme\n"
                    "Low · Frontend Developer — Acme\n"
                    "\n"
                    f"🔗 Open Inbox: {inbox}"
                ),
            )
        ]
        assert report.alerts_sent == 1
        assert bot.violations == 0
        assert {card.alert_handled_at for card in await vacancies(db)} == {NOW}

    async def test_no_message_when_nothing_new(
        self, factory, db, channel, http, ai, sleep, bot
    ) -> None:
        user_id = await make_user(db)
        await link_telegram(db, user_id)
        await make_source(db, user_id, scanned=True)
        channel.add(10, "not a vacancy")

        await check_all(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep, bot=bot)
        await check_all(
            factory,
            http,
            ai,
            at(NOW + timedelta(hours=1)),
            config=CONFIG,
            sleep=sleep,
            bot=bot,
        )

        assert bot.sent == []

    async def test_cards_are_announced_once_across_runs(
        self, factory, db, channel, http, ai, sleep, bot
    ) -> None:
        user_id = await make_user(db)
        await link_telegram(db, user_id)
        await make_source(db, user_id, scanned=True)
        channel.add(10, "MATCH a")

        await check_all(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep, bot=bot)
        channel.add(11, "MATCH b")
        await check_all(
            factory,
            http,
            ai,
            at(NOW + timedelta(hours=1)),
            config=CONFIG,
            sleep=sleep,
            bot=bot,
        )

        assert [text.splitlines()[0] for text in bot.texts] == [
            "🔎 1 new vacancy",
            "🔎 1 new vacancy",
        ]

    async def test_initial_scan_never_alerts_even_when_rated_in_check_all(
        self, factory, db, channel, http, ai, sleep, bot
    ) -> None:
        # No description during the first scan: its posts stay pending and are
        # only rated by the hourly check after the description is set.
        user_id = await make_user(db, description=None)
        await link_telegram(db, user_id)
        await make_source(db, user_id)
        channel.add(10, "MATCH HIGH")
        channel.add(11, "MATCH")
        await run_initial_scans(
            factory, http, ai, at(NOW), config=CONFIG, sleep=sleep, bot=bot
        )
        await set_description(db, user_id, DESCRIPTION)

        await check_all(
            factory,
            http,
            ai,
            at(NOW + timedelta(hours=1)),
            config=CONFIG,
            sleep=sleep,
            bot=bot,
        )

        assert [card.state for card in await vacancies(db)] == ["new", "new"]
        assert bot.sent == []

    async def test_initial_scan_with_description_never_alerts(
        self, factory, db, channel, http, ai, sleep, bot
    ) -> None:
        user_id = await make_user(db)
        await link_telegram(db, user_id)
        await make_source(db, user_id)
        channel.add(10, "MATCH HIGH")

        await run_initial_scans(
            factory, http, ai, at(NOW), config=CONFIG, sleep=sleep, bot=bot
        )

        assert [card.state for card in await vacancies(db)] == ["new"]
        assert bot.sent == []

    async def test_delayed_matches_are_alerted(
        self, factory, db, http, ai, sleep, bot
    ) -> None:
        # Found by an earlier hourly check, waited for the daily cap / the AI.
        user_id = await make_user(db)
        await link_telegram(db, user_id)
        await make_pending(db, user_id, 2, found_at=NOW - timedelta(days=1))

        await check_all(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep, bot=bot)

        [text] = bot.texts
        assert text.splitlines()[0] == "🔎 2 new vacancies"

    async def test_delayed_matches_rated_during_an_initial_scan_run_are_alerted(
        self, factory, db, channel, http, ai, sleep, bot
    ) -> None:
        user_id = await make_user(db)
        await link_telegram(db, user_id)
        await make_pending(db, user_id, 1, found_at=NOW - timedelta(days=1))
        await make_source(db, user_id)
        channel.add(10, "MATCH first scan")

        await run_initial_scans(
            factory, http, ai, at(NOW), config=CONFIG, sleep=sleep, bot=bot
        )

        [text] = bot.texts
        assert text.splitlines()[0] == "🔎 1 new vacancy"
        assert len([c for c in await vacancies(db) if c.state == "new"]) == 2

    async def test_no_message_without_link_and_none_after_linking_late(
        self, factory, db, channel, http, ai, sleep, bot
    ) -> None:
        user_id = await make_user(db)
        await make_source(db, user_id, scanned=True)
        channel.add(10, "MATCH")

        await check_all(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep, bot=bot)
        assert bot.sent == []

        await link_telegram(db, user_id)
        await check_all(
            factory,
            http,
            ai,
            at(NOW + timedelta(hours=1)),
            config=CONFIG,
            sleep=sleep,
            bot=bot,
        )

        assert bot.sent == []
        [card] = await vacancies(db)
        assert card.alert_handled_at == NOW

    @pytest.mark.parametrize(
        ("error", "is_sent"),
        [(RuntimeError("boom"), True), (asyncio.CancelledError(), False)],
        ids=["error-alerts", "cancel-marks-only"],
    )
    async def test_interrupted_run_still_handles_cards_made_new(
        self, factory, db, http, ai, sleep, bot, error: BaseException, is_sent: bool
    ) -> None:
        user_id = await make_user(db)
        await link_telegram(db, user_id)
        await make_pending(db, user_id, 6)  # two batches: 5 + 1
        first_call = ai.chat.completions.create

        async def fail_on_second_call(**kwargs: Any) -> Any:
            if ai.calls:
                raise error
            return await first_call(**kwargs)

        ai.chat.completions.create = fail_on_second_call

        with pytest.raises(type(error)):
            await check_all(
                factory, http, ai, at(NOW), config=CONFIG, sleep=sleep, bot=bot
            )

        cards = await vacancies(db)
        made_new = [card for card in cards if card.state == "new"]
        assert len(made_new) == 5
        assert {card.alert_handled_at for card in made_new} == {NOW}
        assert [card.alert_handled_at for card in cards if card.state == "pending"] == [
            None
        ]
        if is_sent:
            [text] = bot.texts
            assert text.splitlines()[0] == "🔎 5 new vacancies"
        else:  # shutting down: no network, cards only marked handled
            assert bot.sent == []

    async def test_without_bot_cards_are_still_handled(
        self, factory, db, channel, http, ai, sleep
    ) -> None:
        user_id = await make_user(db)
        await link_telegram(db, user_id)
        await make_source(db, user_id, scanned=True)
        channel.add(10, "MATCH")

        report = await check_all(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)

        assert report.alerts_sent == 0
        [card] = await vacancies(db)
        assert card.alert_handled_at == NOW


# --- invariant: no network I/O inside a transaction --------------------------------


async def test_no_http_or_groq_call_while_a_transaction_is_open(
    factory, db, respx_mock, http, ai, sleep, bot
) -> None:
    http_violations: list[int] = []
    stub = Channel()

    def serve(request: httpx.Request) -> httpx.Response:
        http_violations.append(factory.open_transactions())
        return stub(request)

    respx_mock.get(CHANNEL_URL).mock(side_effect=serve)
    respx_mock.get("https://t.me/s/second_channel").mock(
        side_effect=lambda request: (
            http_violations.append(factory.open_transactions()) or httpx.Response(500)
        )
    )
    # Board sources (Slice 6): list, job details and Lever pages are tracked too.
    board = GreenhouseBoard(
        on_request=lambda request: http_violations.append(factory.open_transactions())
    )
    board.mount(respx_mock)
    board.add(1, "board news", NOW - timedelta(days=1))
    board.add(2, "board old job", NOW - timedelta(days=30))
    lever_board = LeverBoard(
        on_request=lambda request: http_violations.append(factory.open_transactions())
    )
    lever_board.mount(respx_mock)
    lever_board.add("a", "lever news", NOW - timedelta(days=1))
    user_id = await make_user(db, exclude=["spam"])
    await link_telegram(db, user_id)
    await make_source(db, user_id)
    await make_source(db, user_id, handle="second_channel", scanned=True)
    async with db() as session:
        session.add_all(
            [
                VacancySource(
                    user_id=user_id,
                    kind="greenhouse",
                    handle=board.token,
                    display_name=board.name,
                ),
                VacancySource(
                    user_id=user_id,
                    kind="lever",
                    handle=lever_board.company,
                    display_name="Acme Labs",
                ),
            ]
        )
        await session.commit()
    for n in range(1, 13):
        stub.add(n, "MATCH" if n % 3 else "spam MATCH")

    await run_initial_scans(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)
    stub.add(20, "MATCH new")
    stub.add(21, "SKIP")
    stub.add(22, "GARBAGE")  # whole-batch format error → single-post retries
    board.add(3, "board news new", NOW + timedelta(minutes=30))
    await check_all(
        factory,
        http,
        ai,
        at(NOW + timedelta(hours=1)),
        config=CONFIG,
        sleep=sleep,
        bot=bot,
    )

    assert board.detail_requests == [1, 3]
    assert lever_board.requests
    assert len(bot.sent) == 1 and bot.violations == 0
    assert len(http_violations) >= 8 and set(http_violations) == {0}
    assert len(ai.calls) >= 3 and ai.violations == 0
    # The checks are meaningful: sessions were opened and wrote data.
    assert len(factory.sessions) > 10
    assert len(await vacancies(db)) == 11
