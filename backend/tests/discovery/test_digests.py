"""Spec 012 §2.1: a digest post becomes one card per matching vacancy.

The fake Groq here does not depend on how posts are laid out in the prompt:
it finds the prompt keys (p1, p2, ...) and a marker word (`DG_...`) in the
user message and answers each key with the verdict configured for the marker
that follows it.
"""

import json
import re
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.discovery.evaluator import MAX_DIGEST_VACANCIES, MAX_POST_CHARS
from app.discovery.service import (
    FORWARDED_KIND,
    DiscoveryConfig,
    ForwardedChannel,
    ForwardOutcome,
    _links_from_json,
    check_all,
    evaluate_pending,
    store_forwarded_post,
)
from app.discovery.types import PostLink, RawPost
from app.models.vacancy import Vacancy, VacancyCardSource
from app.models.vacancy_seen_key import VacancySeenKey
from tests.discovery.fake_bot import FakeBot
from tests.discovery.test_service import (
    CHAT_ID,
    CONFIG,
    NOW,
    TrackingFactory,
    at,
    link_telegram,
    make_source,
    make_user,
    set_description,
    vacancies,
)

_TOKEN_RE = re.compile(r"\b(p\d+)\b|\b(DG_[A-Z0-9_]+)\b")
REACT_LINK = "https://jobs.example.com/react"
DESIGN_LINK = "https://design.example.com/x"

# A digest of the functional reference case: (1) and (3) match.
DIGEST_LINES = (
    "DG_FOUR Jobs of the week",  # L1
    "1. Senior React Developer, remote, €5000",  # L2
    "Apply: react role",  # L3 (REACT_LINK)
    "2. Senior Java backend engineer, remote",  # L4
    "3. Frontend developer (Vue), office in Berlin",  # L5
    "Write to HR",  # L6
    "4. Product designer, remote",  # L7 (DESIGN_LINK)
    "Subscribe!",  # L8
)
DIGEST_TEXT = "\n".join(DIGEST_LINES)
DIGEST_LINKS = [[3, REACT_LINK], [7, DESIGN_LINK]]
REACT_ITEM = {
    "lines": [2, 3],
    "fit": "high",
    "reason": "Remote React role",
    "company": None,
    "title": "Senior React Developer",
}
VUE_ITEM = {
    "lines": [5, 6],
    "fit": "low",
    "reason": "Office in Berlin",
    "company": "Vue GmbH",
    "title": "Frontend developer",
}


def digest(*items: dict[str, Any], count: int = 4) -> dict[str, Any]:
    return {
        "is_vacancy": True,
        "match": bool(items),
        "vacancy_count": count,
        "vacancies": list(items),
    }


class DigestGroq:
    """`answers` maps a marker word of the post text to the verdict fields
    (without `key`). Posts without a known marker are not vacancies."""

    def __init__(
        self, answers: dict[str, dict[str, Any]], factory: TrackingFactory
    ) -> None:
        self.answers = answers
        self.factory = factory
        self.calls = 0
        self.violations = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs: Any) -> SimpleNamespace:
        if self.factory.open_transactions():
            self.violations += 1
        self.calls += 1
        user = kwargs["messages"][-1]["content"]
        user = user.split("POSTS:", 1)[-1]
        markers: dict[str, str | None] = {}
        current: str | None = None
        for key, marker in _TOKEN_RE.findall(user):
            if key:
                current = key
                markers.setdefault(key, None)
            elif current is not None and markers[current] is None:
                markers[current] = marker
        results = []
        for key, marker in markers.items():
            answer = self.answers.get(marker or "")
            if answer is None:
                answer = {"is_vacancy": False, "match": False, "reason": "News"}
            results.append({"key": key, **answer})
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=json.dumps({"results": results}))
                )
            ],
            usage=SimpleNamespace(total_tokens=100),
        )


async def make_post(
    db: async_sessionmaker[AsyncSession],
    user_id: str,
    n: int,
    text: str,
    *,
    links: list[list[Any]] | None = None,
    source_id: str | None = None,
    kind: str = "telegram",
    handle: str = "jobbi_jobs",
    alert_handled_at: datetime | None = None,
    from_initial_scan: bool = False,
    found_at: datetime = NOW - timedelta(hours=2),
    key: str | None = None,
) -> str:
    """A pending post (`tg:other/<n>` unless `key` is given) with its seen key
    and one card source."""
    key = key or f"tg:other/{n}"
    async with db() as session:
        session.add(
            VacancySeenKey(user_id=user_id, external_key=key, first_seen_at=found_at)
        )
        card = Vacancy(
            user_id=user_id,
            source_id=source_id,
            external_key=key,
            url=f"https://t.me/other/{n}" if key.startswith("tg") else key,
            job_link=REACT_LINK if links else None,
            text=text,
            links=links,
            posted_at=NOW - timedelta(days=1, minutes=n),
            found_at=found_at + timedelta(seconds=n),
            state="pending",
            from_initial_scan=from_initial_scan,
            alert_handled_at=alert_handled_at,
        )
        session.add(card)
        await session.flush()
        session.add(
            VacancyCardSource(
                vacancy_id=card.id,
                source_id=source_id,
                source_kind=kind,
                source_handle=handle,
                label=f"@{handle}",
            )
        )
        await session.commit()
        return card.id


async def make_card(
    db: async_sessionmaker[AsyncSession],
    user_id: str,
    *,
    job_link: str,
    state: str = "seen",
) -> str:
    async with db() as session:
        card = Vacancy(
            user_id=user_id,
            external_key="tg:first/1",
            url="https://t.me/first/1",
            job_link=job_link,
            text="React role",
            posted_at=NOW - timedelta(days=3),
            found_at=NOW - timedelta(days=3),
            state=state,
            fit="medium",
        )
        session.add(card)
        await session.flush()
        session.add(
            VacancyCardSource(
                vacancy_id=card.id,
                source_kind="telegram",
                source_handle="first",
                label="@first",
            )
        )
        await session.commit()
        return card.id


async def card_sources(
    db: async_sessionmaker[AsyncSession],
) -> dict[str, set[tuple[str, str]]]:
    """Card id → its (kind, handle) pairs."""
    async with db() as session:
        rows = await session.execute(
            select(
                VacancyCardSource.vacancy_id,
                VacancyCardSource.source_kind,
                VacancyCardSource.source_handle,
            )
        )
        out: dict[str, set[tuple[str, str]]] = {}
        for vacancy_id, kind, handle in rows:
            out.setdefault(vacancy_id, set()).add((kind, handle))
        return out


async def seen_key(db: async_sessionmaker[AsyncSession], key: str) -> VacancySeenKey:
    async with db() as session:
        row = await session.scalar(
            select(VacancySeenKey).where(VacancySeenKey.external_key == key)
        )
        assert row is not None
        return row


@pytest.fixture
def four() -> dict[str, dict[str, Any]]:
    return {"DG_FOUR": digest(REACT_ITEM, VUE_ITEM)}


# --- splitting ---------------------------------------------------------------


async def test_digest_becomes_one_card_per_matching_vacancy(
    factory, db, sleep, four
) -> None:
    user_id = await make_user(db)
    source_id = await make_source(db, user_id, scanned=True)
    pending_id = await make_post(
        db,
        user_id,
        1,
        DIGEST_TEXT,
        links=DIGEST_LINKS,
        source_id=source_id,
        from_initial_scan=True,
        alert_handled_at=None,  # as stored by a first scan
    )
    ai = DigestGroq(four, factory)

    report = await evaluate_pending(factory, ai, at(NOW), config=CONFIG, sleep=sleep)

    react, vue = await vacancies(db)
    assert (react.external_key, vue.external_key) == ("tg:other/1#1", "tg:other/1#2")
    assert react.text == "1. Senior React Developer, remote, €5000\nApply: react role"
    assert vue.text == "3. Frontend developer (Vue), office in Berlin\nWrite to HR"
    assert (react.job_link, vue.job_link) == (REACT_LINK, None)
    assert (react.state, react.fit, react.fit_reason) == (
        "new",
        "high",
        "Remote React role",
    )
    assert (vue.fit, vue.fit_reason) == ("low", "Office in Berlin")
    assert (react.title, react.company) == ("Senior React Developer", None)
    assert (vue.title, vue.company) == ("Frontend developer", "Vue GmbH")
    for card in (react, vue):
        assert card.id != pending_id
        assert card.user_id == user_id
        assert card.source_id == source_id
        assert card.url == "https://t.me/other/1"
        assert card.posted_at == NOW - timedelta(days=1, minutes=1)
        assert card.found_at == NOW - timedelta(hours=2) + timedelta(seconds=1)
        assert card.from_initial_scan is True
        # Copied: the run's alert step sends the first-scan summary.
        assert card.alert_handled_at is None
        assert card.links is None
    # Copies of the pending row's card source; the pending row's own are gone.
    assert await card_sources(db) == {
        react.id: {("telegram", "jobbi_jobs")},
        vue.id: {("telegram", "jobbi_jobs")},
    }
    assert (await seen_key(db, "tg:other/1")).evaluated_at == NOW
    assert report.posts_evaluated == 1
    assert report.matches == 2
    assert report.posts_merged == 0
    assert report.new_card_ids == {user_id: [react.id, vue.id]}
    assert ai.violations == 0


async def test_board_job_is_never_split_as_a_digest(factory, db, sleep, four) -> None:
    """Only Telegram posts can be digests; a board job the AI calls a digest
    stays one card, rated by its first matching position."""
    user_id = await make_user(db)
    await make_post(
        db, user_id, 1, DIGEST_TEXT, key="gh:acme/1", kind="greenhouse", handle="acme"
    )
    ai = DigestGroq(four, factory)

    report = await evaluate_pending(factory, ai, at(NOW), config=CONFIG, sleep=sleep)

    [card] = await vacancies(db)
    assert card.external_key == "gh:acme/1"
    assert (card.state, card.fit, card.fit_reason) == (
        "new",
        "high",
        "Remote React role",
    )
    assert card.text == DIGEST_TEXT
    assert report.matches == 1
    assert report.new_card_ids == {user_id: [card.id]}


async def test_digest_card_keys_never_exceed_the_column(
    factory, db, sleep, four
) -> None:
    long_key = "tg:" + "x" * 250 + "/1"  # 255 characters: "#<n>" cannot fit
    user_id = await make_user(db)
    await make_post(db, user_id, 1, DIGEST_TEXT, key=long_key)
    ai = DigestGroq(four, factory)

    await evaluate_pending(factory, ai, at(NOW), config=CONFIG, sleep=sleep)

    assert all(len(card.external_key) <= 255 for card in await vacancies(db))
    assert (await seen_key(db, long_key)).evaluated_at == NOW


async def test_digest_without_matching_vacancies_is_deleted(factory, db, sleep) -> None:
    user_id = await make_user(db)
    await make_post(db, user_id, 1, "DG_NONE\nSales\nSupport", links=[[2, REACT_LINK]])
    ai = DigestGroq({"DG_NONE": digest(count=6)}, factory)

    report = await evaluate_pending(factory, ai, at(NOW), config=CONFIG, sleep=sleep)

    assert await vacancies(db) == []
    assert await card_sources(db) == {}
    assert (await seen_key(db, "tg:other/1")).evaluated_at == NOW
    assert report.matches == 0
    assert report.posts_evaluated == 1


async def test_job_link_is_the_first_link_on_the_vacancy_lines(
    factory, db, sleep
) -> None:
    user_id = await make_user(db)
    text = "DG_LINKS\nA role\nB role\nC role\nD role"
    links = [[1, "https://intro.example.com"], [3, "https://b.example.com/1"]]
    links.append([3, "https://b.example.com/2"])
    await make_post(db, user_id, 1, text, links=links)
    items = [
        {"lines": [2, 3], "fit": "high", "title": "A"},
        {"lines": [4, 5], "fit": "low", "title": "C"},
    ]
    ai = DigestGroq({"DG_LINKS": digest(*items, count=4)}, factory)

    await evaluate_pending(factory, ai, at(NOW), config=CONFIG, sleep=sleep)

    # A's lines hold two links (the intro link is outside them); C has none.
    cards = await vacancies(db)
    assert [(c.external_key, c.job_link) for c in cards] == [
        ("tg:other/1#1", "https://b.example.com/1"),
        ("tg:other/1#2", None),
    ]


async def test_vacancies_with_the_same_job_link_make_one_card(
    factory, db, sleep
) -> None:
    user_id = await make_user(db)
    text = "DG_TWICE\nReact role\nReact role again"
    await make_post(db, user_id, 1, text, links=[[2, REACT_LINK], [3, REACT_LINK]])
    items = [
        {"lines": [2, 2], "fit": "high", "title": "React"},
        {"lines": [3, 3], "fit": "high", "title": "React again"},
    ]
    ai = DigestGroq({"DG_TWICE": digest(*items, count=2)}, factory)

    report = await evaluate_pending(factory, ai, at(NOW), config=CONFIG, sleep=sleep)

    [card] = await vacancies(db)
    assert (card.external_key, card.job_link) == ("tg:other/1#1", REACT_LINK)
    assert report.matches == 1
    assert report.posts_merged == 1


async def test_vacancy_with_a_known_job_link_merges_into_that_card(
    factory, db, sleep, four
) -> None:
    user_id = await make_user(db)
    existing_id = await make_card(db, user_id, job_link=REACT_LINK)
    await make_post(db, user_id, 1, DIGEST_TEXT, links=DIGEST_LINKS)
    ai = DigestGroq(four, factory)

    report = await evaluate_pending(factory, ai, at(NOW), config=CONFIG, sleep=sleep)

    cards = {card.external_key: card for card in await vacancies(db)}
    assert set(cards) == {"tg:first/1", "tg:other/1#2"}
    existing = cards["tg:first/1"]
    assert (existing.state, existing.fit, existing.text) == (
        "seen",
        "medium",
        "React role",
    )
    sources = await card_sources(db)
    assert sources[existing_id] == {("telegram", "first"), ("telegram", "jobbi_jobs")}
    assert sources[cards["tg:other/1#2"].id] == {("telegram", "jobbi_jobs")}
    assert len(sources) == 2  # the pending row's source is gone
    assert report.matches == 1
    assert report.posts_merged == 1
    assert report.new_card_ids == {user_id: [cards["tg:other/1#2"].id]}


async def test_vacancies_without_stored_links_get_no_job_link(
    factory, db, sleep, four
) -> None:
    """Pending rows from before the migration have `links` NULL."""
    user_id = await make_user(db)
    await make_card(db, user_id, job_link=REACT_LINK)
    await make_post(db, user_id, 1, DIGEST_TEXT + f"\n{REACT_LINK}", links=None)
    ai = DigestGroq(four, factory)

    await evaluate_pending(factory, ai, at(NOW), config=CONFIG, sleep=sleep)

    digest_cards = [c for c in await vacancies(db) if "#" in c.external_key]
    assert [c.job_link for c in digest_cards] == [None, None]  # and no merge


async def test_at_most_twenty_cards_per_post(factory, db, sleep) -> None:
    user_id = await make_user(db)
    count = MAX_DIGEST_VACANCIES + 5
    text = "\n".join(["DG_MANY", *(f"Role {n}" for n in range(1, count + 1))])
    await make_post(db, user_id, 1, text)
    items = [
        {"lines": [n + 1, n + 1], "fit": "medium", "title": f"Role {n}"}
        for n in range(1, count + 1)
    ]
    ai = DigestGroq({"DG_MANY": digest(*items, count=count)}, factory)

    report = await evaluate_pending(factory, ai, at(NOW), config=CONFIG, sleep=sleep)

    cards = await vacancies(db)
    assert len(cards) == MAX_DIGEST_VACANCIES
    assert {c.title for c in cards} == {
        f"Role {n}" for n in range(1, MAX_DIGEST_VACANCIES + 1)
    }
    assert report.matches == MAX_DIGEST_VACANCIES


async def test_a_digest_counts_once_toward_the_daily_cap(factory, db, sleep) -> None:
    user_id = await make_user(db)
    for n in (1, 2, 3):
        await make_post(db, user_id, n, f"DG_THREE\nA\nB\nC\nnumber {n}")
    items = [
        {"lines": [n, n], "fit": "high", "title": t}
        for n, t in [(2, "A"), (3, "B"), (4, "C")]
    ]
    ai = DigestGroq({"DG_THREE": digest(*items, count=3)}, factory)
    config = DiscoveryConfig(model="test-model", daily_limit=2)

    report = await evaluate_pending(factory, ai, at(NOW), config=config, sleep=sleep)

    cards = await vacancies(db)
    assert [c.external_key for c in cards if c.state == "new"] == [
        f"tg:other/{n}#{i}" for n in (1, 2) for i in (1, 2, 3)
    ]
    assert [c.external_key for c in cards if c.state == "pending"] == ["tg:other/3"]
    assert report.posts_evaluated == 2
    assert report.users_capped == {user_id}


async def test_cut_digest_sets_cut_for_ai(factory, db, sleep) -> None:
    user_id = await make_user(db)
    text = "DG_LONG\nReact role\n" + "x" * MAX_POST_CHARS
    await make_post(db, user_id, 1, text)
    item = {"lines": [2, 2], "fit": "high", "title": "React"}
    ai = DigestGroq({"DG_LONG": digest(item, count=2)}, factory)

    report = await evaluate_pending(factory, ai, at(NOW), config=CONFIG, sleep=sleep)

    [card] = await vacancies(db)
    assert card.text == "React role"
    key = await seen_key(db, "tg:other/1")
    assert (key.evaluated_at, key.cut_for_ai) == (NOW, True)
    assert report.posts_cut == 1


async def test_single_posts_are_unchanged(factory, db, sleep) -> None:
    user_id = await make_user(db)
    await make_post(db, user_id, 1, "DG_SINGLE\nReact role", links=[[2, REACT_LINK]])
    single = {
        "is_vacancy": True,
        "match": True,
        "fit": "high",
        "reason": "ok",
        "title": "React",
        "vacancy_count": 1,
        "vacancies": [{"lines": [2, 2], "fit": "low"}],  # ignored
    }
    ai = DigestGroq({"DG_SINGLE": single}, factory)

    await evaluate_pending(factory, ai, at(NOW), config=CONFIG, sleep=sleep)

    [card] = await vacancies(db)
    assert (card.external_key, card.fit, card.text) == (
        "tg:other/1",
        "high",
        "DG_SINGLE\nReact role",
    )
    assert card.links == [[2, REACT_LINK]]


# --- forwarded digests ---------------------------------------------------------


async def test_forwarded_digest_without_matches_is_deleted(factory, db, sleep) -> None:
    user_id = await make_user(db)
    await make_post(
        db,
        user_id,
        1,
        "DG_NONE\nSales\nSupport",
        kind=FORWARDED_KIND,
        handle="c123",
        alert_handled_at=NOW,
    )
    ai = DigestGroq({"DG_NONE": digest(count=2)}, factory)

    await evaluate_pending(factory, ai, at(NOW), config=CONFIG, sleep=sleep)

    assert await vacancies(db) == []


async def test_forwarded_digest_cards_keep_the_forward_source(
    factory, db, sleep, four
) -> None:
    user_id = await make_user(db)
    await make_post(
        db,
        user_id,
        1,
        DIGEST_TEXT,
        links=DIGEST_LINKS,
        kind=FORWARDED_KIND,
        handle="c123",
        alert_handled_at=NOW,
    )
    ai = DigestGroq(four, factory)

    await evaluate_pending(factory, ai, at(NOW), config=CONFIG, sleep=sleep)

    cards = await vacancies(db)
    assert [c.alert_handled_at for c in cards] == [NOW, NOW]
    assert set(map(frozenset, (await card_sources(db)).values())) == {
        frozenset({(FORWARDED_KIND, "c123")})
    }


CHANNEL = ForwardedChannel(handle="c123", label="Private jobs")


def _forwarded(links: tuple[PostLink, ...]) -> RawPost:
    return RawPost(
        external_key="tgc:123/5",
        url="https://t.me/c/123/5",
        job_link=links[0].url,
        title=None,
        company=None,
        text="Jobs\nReact role\nJava role",
        posted_at=NOW,
        links=links,
    )


async def test_forwarded_post_with_several_links_is_not_merged_at_store(
    factory, db
) -> None:
    user_id = await make_user(db)
    await make_card(db, user_id, job_link=REACT_LINK)
    links = (PostLink(2, REACT_LINK), PostLink(3, "https://jobs.example.com/java"))

    outcome = await store_forwarded_post(
        factory, user_id, CHANNEL, _forwarded(links), NOW, chat_id=1, message_id=2
    )

    assert outcome is ForwardOutcome.ADDED
    pending = [c for c in await vacancies(db) if c.state == "pending"]
    assert [c.links for c in pending] == [
        [[2, REACT_LINK], [3, "https://jobs.example.com/java"]]
    ]


async def test_forwarded_post_with_one_link_is_not_merged_at_store(factory, db) -> None:
    user_id = await make_user(db)
    await make_card(db, user_id, job_link=REACT_LINK)

    outcome = await store_forwarded_post(
        factory,
        user_id,
        CHANNEL,
        _forwarded((PostLink(2, REACT_LINK),)),
        NOW,
        chat_id=1,
        message_id=2,
    )

    assert outcome is ForwardOutcome.ADDED
    assert sorted(c.state for c in await vacancies(db)) == ["pending", "seen"]


# --- through a watched channel -------------------------------------------------

CHANNEL_DIGEST = (
    "DG_CHAN Jobs<br/>"
    f'React developer <a href="{REACT_LINK}">apply</a><br/>'
    "Java developer<br/>"
    f'Vue developer <a href="https://jobs.example.com/vue">apply</a>'
)


async def test_links_are_stored_on_the_pending_row_and_used_after_rating(
    factory, db, channel, http, sleep
) -> None:
    user_id = await make_user(db, description=None)
    await make_source(db, user_id, scanned=True)
    channel.add(10, CHANNEL_DIGEST)
    items = [
        {"lines": [2, 2], "fit": "high", "title": "React"},
        {"lines": [4, 4], "fit": "low", "title": "Vue"},
    ]
    ai = DigestGroq({"DG_CHAN": digest(*items, count=3)}, factory)

    await check_all(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)

    [pending] = await vacancies(db)
    assert pending.state == "pending"  # no description yet
    assert pending.links == [[2, REACT_LINK], [4, "https://jobs.example.com/vue"]]

    await set_description(db, user_id, "Senior frontend, React, remote")
    await evaluate_pending(factory, ai, at(NOW), config=CONFIG, sleep=sleep)

    cards = await vacancies(db)
    assert [(c.external_key, c.job_link) for c in cards] == [
        ("tg:jobbi_jobs/10#1", REACT_LINK),
        ("tg:jobbi_jobs/10#2", "https://jobs.example.com/vue"),
    ]


async def test_alert_counts_digest_cards_and_skips_handled_ones(
    factory, db, channel, http, sleep, bot: FakeBot
) -> None:
    user_id = await make_user(db)
    await link_telegram(db, user_id)
    await make_source(db, user_id, scanned=True)
    channel.add(10, CHANNEL_DIGEST)
    # Forwarded earlier: its cards are never alerted.
    await make_post(
        db,
        user_id,
        1,
        DIGEST_TEXT,
        kind=FORWARDED_KIND,
        handle="c123",
        alert_handled_at=NOW - timedelta(minutes=5),
    )
    items = [
        {"lines": [2, 2], "fit": "high", "title": "React", "company": "Acme"},
        {"lines": [3, 3], "fit": "medium", "title": "Java", "company": "Acme"},
        {"lines": [4, 4], "fit": "low", "title": "Vue", "company": "Acme"},
    ]
    answers = {"DG_CHAN": digest(*items, count=3), "DG_FOUR": digest(REACT_ITEM)}
    ai = DigestGroq(answers, factory)

    report = await check_all(
        factory, http, ai, at(NOW), config=CONFIG, sleep=sleep, bot=bot
    )

    [(chat_id, text)] = bot.sent
    assert chat_id == CHAT_ID
    assert text.startswith("🔎 3 new vacancies\n")
    assert "High · React — Acme" in text
    assert "Senior React Developer" not in text
    assert report.alerts_sent == 1
    assert bot.violations == 0
    assert ai.violations == 0


# --- helpers -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ()),
        ([], ()),
        ("nonsense", ()),
        ([[2, "https://a.example"]], (PostLink(2, "https://a.example"),)),
        ([[True, "https://a.example"], ["2", "x"], [3], 5], ()),
    ],
)
def test_links_from_json(value: object, expected: tuple[PostLink, ...]) -> None:
    assert _links_from_json(value) == expected


async def test_channel_post_with_several_links_is_not_merged_at_store(
    factory, db, channel, http, sleep
) -> None:
    user_id = await make_user(db, description=None)
    await make_source(db, user_id, scanned=True)
    await make_card(db, user_id, job_link=REACT_LINK)
    channel.add(10, CHANNEL_DIGEST)

    report = await check_all(
        factory, http, DigestGroq({}, factory), at(NOW), config=CONFIG, sleep=sleep
    )

    assert report.posts_merged == 0
    assert [c.external_key for c in await vacancies(db) if c.state == "pending"] == [
        "tg:jobbi_jobs/10"
    ]


async def test_channel_post_repeating_one_link_merges_at_store(
    factory, db, channel, http, sleep
) -> None:
    """The same job link on two lines is one link: a repost, not a digest."""
    user_id = await make_user(db, description=None)
    await make_source(db, user_id, scanned=True)
    card_id = await make_card(db, user_id, job_link=REACT_LINK)
    channel.add(
        10,
        f'DG_CHAN React developer <a href="{REACT_LINK}">apply</a><br/>'
        f'Questions? <a href="{REACT_LINK}">see the job</a>',
    )

    report = await check_all(
        factory, http, DigestGroq({}, factory), at(NOW), config=CONFIG, sleep=sleep
    )

    assert report.posts_merged == 1
    assert [c.id for c in await vacancies(db)] == [card_id]
    assert ("telegram", "jobbi_jobs") in (await card_sources(db))[card_id]
