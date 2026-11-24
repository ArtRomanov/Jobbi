from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.vacancy import Vacancy, VacancyCardSource
from app.models.vacancy_search_settings import VacancySearchSettings
from app.models.vacancy_seen_key import VacancySeenKey
from app.models.vacancy_source import VacancySource

URL = "/api/v1/vacancies"
SOURCES_URL = "/api/v1/vacancy-sources"
BASE = datetime(2026, 11, 20, 12, 0)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest.fixture
def token(registered_user: dict) -> str:
    return registered_user["access_token"]


@pytest.fixture
def user_id(registered_user: dict) -> str:
    return registered_user["user"]["id"]


async def add_card(
    db: AsyncSession,
    user_id: str,
    key: str,
    *,
    state: str = "new",
    fit: str | None = "medium",
    hours: int = 0,
    labels: tuple[str | tuple[str, str], ...] = ("@jobs",),
    source_id: str | None = None,
) -> Vacancy:
    card = Vacancy(
        user_id=user_id,
        source_id=source_id,
        external_key=f"tg:jobs/{key}",
        url=f"https://t.me/jobs/{key}",
        job_link=f"https://acme.example/jobs/{key}",
        title=f"Role {key}",
        company="Acme",
        text=f"Text {key}",
        posted_at=BASE + timedelta(hours=hours),
        found_at=BASE + timedelta(hours=hours, minutes=5),
        state=state,
        fit=None if state == "pending" else fit,
        fit_reason=None if state == "pending" else "Remote React role",
    )
    db.add(card)
    await db.flush()
    for entry in labels:
        # "@name" → telegram source "name" labelled "@name"; or (handle, label).
        handle, label = entry if isinstance(entry, tuple) else (entry[1:], entry)
        db.add(
            VacancyCardSource(
                vacancy_id=card.id,
                source_id=source_id,
                source_kind="telegram",
                source_handle=handle,
                label=label,
            )
        )
    await db.commit()
    return card


async def list_keys(
    client: httpx.AsyncClient, token: str, **params: object
) -> list[str]:
    resp = await client.get(URL, params=params, headers=_auth(token))
    assert resp.status_code == 200, resp.text
    return [item["url"].rsplit("/", 1)[1] for item in resp.json()["items"]]


class TestListVacancies:
    async def test_lists_only_new_and_seen_newest_first(
        self, client, token, user_id, db_session
    ) -> None:
        await add_card(db_session, user_id, "new1", hours=1)
        await add_card(db_session, user_id, "seen1", state="seen", hours=3)
        for state in ("pending", "dismissed", "added"):
            await add_card(db_session, user_id, state, state=state, hours=5)

        resp = await client.get(URL, headers=_auth(token))

        body = resp.json()
        assert body["total"] == 2
        assert (body["page"], body["per_page"]) == (1, 20)
        assert [i["url"].rsplit("/", 1)[1] for i in body["items"]] == ["seen1", "new1"]
        item = body["items"][1]
        assert item == {
            "id": item["id"],
            "title": "Role new1",
            "company": "Acme",
            "url": "https://t.me/jobs/new1",
            "job_link": "https://acme.example/jobs/new1",
            "text": "Text new1",
            "posted_at": "2026-11-20T13:00:00Z",
            "found_at": "2026-11-20T13:05:00Z",
            "state": "new",
            "fit": "medium",
            "fit_reason": "Remote React role",
            "sources": [{"key": "telegram:jobs", "label": "@jobs"}],
            "existing_application": None,
        }

    async def test_state_filter(self, client, token, user_id, db_session) -> None:
        await add_card(db_session, user_id, "n", hours=1)
        await add_card(db_session, user_id, "s", state="seen", hours=2)

        assert await list_keys(client, token, state="new") == ["n"]
        assert await list_keys(client, token, state="seen") == ["s"]
        assert await list_keys(client, token, state="all") == ["s", "n"]

    async def test_source_filter_by_label_combines_with_state(
        self, client, token, user_id, db_session
    ) -> None:
        await add_card(db_session, user_id, "a", labels=("@a",), hours=1)
        await add_card(db_session, user_id, "ab", labels=("@a", "@b"), hours=2)
        await add_card(
            db_session, user_id, "b-seen", state="seen", labels=("@b",), hours=3
        )

        assert await list_keys(client, token, source="telegram:b") == ["b-seen", "ab"]
        assert await list_keys(client, token, source="telegram:b", state="new") == [
            "ab"
        ]
        assert await list_keys(client, token, source="telegram:nope") == []
        assert await list_keys(client, token, source="no-colon") == []
        resp = await client.get(
            URL, params={"source": "telegram:a"}, headers=_auth(token)
        )
        merged = next(i for i in resp.json()["items"] if i["url"].endswith("/ab"))
        assert merged["sources"] == [
            {"key": "telegram:a", "label": "@a"},
            {"key": "telegram:b", "label": "@b"},
        ]

    async def test_fit_sort_uses_explicit_order_then_newest(
        self, client, token, user_id, db_session
    ) -> None:
        await add_card(db_session, user_id, "low-new", fit="low", hours=9)
        await add_card(db_session, user_id, "medium-old", fit="medium", hours=1)
        await add_card(db_session, user_id, "high-old", fit="high", hours=2)
        await add_card(db_session, user_id, "medium-new", fit="medium", hours=8)
        await add_card(db_session, user_id, "high-new", fit="high", hours=7)

        assert await list_keys(client, token, sort="fit") == [
            "high-new",
            "high-old",
            "medium-new",
            "medium-old",
            "low-new",
        ]
        assert (await list_keys(client, token, sort="date"))[0] == "low-new"

    async def test_pagination(self, client, token, user_id, db_session) -> None:
        for n in range(5):
            await add_card(db_session, user_id, f"c{n}", hours=n)

        resp = await client.get(
            URL, params={"page": 2, "per_page": 2}, headers=_auth(token)
        )

        body = resp.json()
        assert body["total"] == 5
        assert [i["url"].rsplit("/", 1)[1] for i in body["items"]] == ["c2", "c1"]

    @pytest.mark.parametrize(
        "params",
        [{"state": "pending"}, {"sort": "name"}, {"page": 0}, {"per_page": 101}],
    )
    async def test_invalid_params_422(self, client, token, params) -> None:
        resp = await client.get(URL, params=params, headers=_auth(token))
        assert resp.status_code == 422

    async def test_other_users_cards_are_invisible(
        self, client, token, user_id, other_registered_user, db_session
    ) -> None:
        other_id = other_registered_user["user"]["id"]
        await add_card(db_session, other_id, "theirs")
        await add_card(db_session, user_id, "mine")

        assert await list_keys(client, token) == ["mine"]
        other_token = other_registered_user["access_token"]
        assert await list_keys(client, other_token) == ["theirs"]
        resp = await client.get(f"{URL}/new-count", headers=_auth(other_token))
        assert resp.json() == {"count": 1}

    async def test_requires_auth(self, client) -> None:
        assert (await client.get(URL)).status_code == 401
        assert (await client.get(f"{URL}/new-count")).status_code == 401


async def test_new_count_counts_only_new(client, token, user_id, db_session) -> None:
    await add_card(db_session, user_id, "n1")
    await add_card(db_session, user_id, "n2")
    for state in ("seen", "pending", "dismissed", "added"):
        await add_card(db_session, user_id, state, state=state)

    resp = await client.get(f"{URL}/new-count", headers=_auth(token))

    assert resp.status_code == 200
    assert resp.json() == {"count": 2}


class TestSourcesStatus:
    async def _status(self, client: httpx.AsyncClient, token: str) -> dict:
        resp = await client.get(SOURCES_URL, headers=_auth(token))
        assert resp.status_code == 200
        return resp.json()

    async def test_defaults_without_settings(self, client, token) -> None:
        body = await self._status(client, token)
        assert body["status"] == {
            "ai_unavailable": False,
            "limit_reached": False,
            "waiting_count": 0,
            "filtered_last_24h": 0,
        }
        assert body["removed_sources"] == []

    async def test_waiting_count_and_flags(
        self, client, token, user_id, db_session
    ) -> None:
        await add_card(db_session, user_id, "p1", state="pending")
        await add_card(db_session, user_id, "p2", state="pending")
        await add_card(db_session, user_id, "n1")
        # A web row whose job page is not read yet is not waiting for the AI.
        unread = await add_card(db_session, user_id, "w1", state="pending")
        unread.needs_detail = True
        await db_session.commit()
        today_utc = datetime.now(UTC).date()
        db_session.add(
            VacancySearchSettings(
                user_id=user_id,
                description="Frontend",
                ai_failing_since=_now_naive() - timedelta(hours=2),
                limit_reached_on=today_utc,
            )
        )
        await db_session.commit()

        status = (await self._status(client, token))["status"]

        assert status == {
            "ai_unavailable": True,
            "limit_reached": True,
            "waiting_count": 2,
            "filtered_last_24h": 0,
        }

    async def test_filtered_last_24h_counts_recent_filtered_keys(
        self, client, token, user_id, db_session, other_registered_user
    ) -> None:
        now = _now_naive()
        other_id = other_registered_user["user"]["id"]

        def key(owner: str, n: int, filtered_at: datetime | None) -> VacancySeenKey:
            return VacancySeenKey(
                user_id=owner,
                external_key=f"tg:jobs/{n}",
                first_seen_at=now - timedelta(days=2),
                filtered_at=filtered_at,
            )

        db_session.add_all(
            [
                key(user_id, 1, now - timedelta(minutes=5)),
                key(user_id, 2, now - timedelta(hours=23)),
                key(user_id, 3, now - timedelta(hours=25)),  # older than 24 h
                key(user_id, 4, None),  # seen, never filtered
                key(other_id, 5, now - timedelta(minutes=5)),  # another user
            ]
        )
        await db_session.commit()

        status = (await self._status(client, token))["status"]

        assert status["filtered_last_24h"] == 2

    async def test_flags_off_for_recent_failure_and_other_day(
        self, client, token, user_id, db_session
    ) -> None:
        db_session.add(
            VacancySearchSettings(
                user_id=user_id,
                description="Frontend",
                ai_failing_since=_now_naive() - timedelta(minutes=30),
                limit_reached_on=date(2020, 1, 1),
            )
        )
        await db_session.commit()

        status = (await self._status(client, token))["status"]

        assert (status["ai_unavailable"], status["limit_reached"]) == (False, False)

    async def test_limit_reached_uses_users_local_day(
        self, client, token, user_id, db_session
    ) -> None:
        user = await db_session.get(User, user_id)
        user.timezone = "Pacific/Kiritimati"  # UTC+14: often a different date
        local_today = datetime.now(ZoneInfo("Pacific/Kiritimati")).date()
        db_session.add(
            VacancySearchSettings(
                user_id=user_id,
                description="Frontend",
                limit_reached_on=local_today,
            )
        )
        await db_session.commit()

        assert (await self._status(client, token))["status"]["limit_reached"] is True

    async def test_removed_sources_by_identity(
        self, client, token, user_id, db_session
    ) -> None:
        live = VacancySource(
            user_id=user_id,
            kind="telegram",
            handle="live_jobs",
            default_name="Live Jobs (new title)",
            display_name="Live Jobs (new title)",
        )
        db_session.add(live)
        await db_session.commit()
        await add_card(db_session, user_id, "1", labels=("@gone",), hours=1)
        # Newest card of a removed source gives its label.
        await add_card(
            db_session,
            user_id,
            "2",
            labels=(("gone", "Gone v2"), "@also_gone"),
            hours=2,
        )
        # Re-added source (same kind + handle, another title): not "(removed)".
        await add_card(db_session, user_id, "3", labels=(("live_jobs", "Old title"),))
        # Only visible cards count.
        await add_card(db_session, user_id, "4", state="dismissed", labels=("@hidden",))

        body = await self._status(client, token)

        assert body["removed_sources"] == [
            {"key": "telegram:also_gone", "label": "@also_gone"},
            {"key": "telegram:gone", "label": "Gone v2"},
        ]
        assert [s["key"] for s in body["sources"]] == ["telegram:live_jobs"]

    async def test_readded_source_filters_old_and_new_cards_under_live_name(
        self, client, token, user_id, db_session
    ) -> None:
        source = VacancySource(
            user_id=user_id,
            kind="telegram",
            handle="jobs",
            default_name="Jobs 2026",
            display_name="Jobs 2026",
        )
        db_session.add(source)
        await db_session.commit()
        await add_card(db_session, user_id, "old", labels=(("jobs", "Old Jobs"),))
        await add_card(
            db_session, user_id, "new", labels=(("jobs", "Jobs 2026"),), hours=1
        )

        resp = await client.get(
            URL, params={"source": "telegram:jobs"}, headers=_auth(token)
        )

        items = resp.json()["items"]
        assert [i["url"].rsplit("/", 1)[1] for i in items] == ["new", "old"]
        assert all(
            i["sources"] == [{"key": "telegram:jobs", "label": "Jobs 2026"}]
            for i in items
        )


async def test_source_delete_clears_references(
    client, token, user_id, db_session
) -> None:
    source = VacancySource(
        user_id=user_id,
        kind="telegram",
        handle="jobs_channel",
        default_name="@jobs_channel",
        display_name="@jobs_channel",
    )
    db_session.add(source)
    await db_session.commit()
    card = await add_card(
        db_session, user_id, "1", labels=("@jobs_channel",), source_id=source.id
    )
    card_id = card.id

    resp = await client.delete(f"{SOURCES_URL}/{source.id}", headers=_auth(token))

    assert resp.status_code == 204
    db_session.expire_all()
    refreshed = await db_session.get(Vacancy, card_id)
    assert refreshed is not None and refreshed.source_id is None
    card_sources = (await db_session.scalars(select(VacancyCardSource))).all()
    assert [(c.source_id, c.label) for c in card_sources] == [(None, "@jobs_channel")]
    body = (await client.get(SOURCES_URL, headers=_auth(token))).json()
    assert body["removed_sources"] == [
        {"key": "telegram:jobs_channel", "label": "@jobs_channel"}
    ]
    assert await list_keys(client, token, source="telegram:jobs_channel") == ["1"]


async def test_source_delete_removes_its_pending_posts_only(
    client, token, user_id, db_session
) -> None:
    source = VacancySource(
        user_id=user_id,
        kind="telegram",
        handle="jobs",
        default_name="@jobs",
        display_name="@jobs",
    )
    other = VacancySource(
        user_id=user_id,
        kind="telegram",
        handle="other",
        default_name="@other",
        display_name="@other",
    )
    db_session.add_all([source, other])
    await db_session.commit()
    source_id = source.id
    await add_card(db_session, user_id, "p", state="pending", source_id=source_id)
    await add_card(db_session, user_id, "n", source_id=source_id)
    await add_card(
        db_session,
        user_id,
        "o",
        state="pending",
        labels=("@other",),
        source_id=other.id,
    )

    resp = await client.delete(f"{SOURCES_URL}/{source_id}", headers=_auth(token))

    assert resp.status_code == 204
    db_session.expire_all()
    remaining = (await db_session.scalars(select(Vacancy.external_key))).all()
    assert sorted(remaining) == ["tg:jobs/n", "tg:jobs/o"]
    card_handles = (
        await db_session.scalars(select(VacancyCardSource.source_handle))
    ).all()
    assert sorted(card_handles) == ["jobs", "other"]


async def test_source_delete_of_other_user_keeps_references(
    client, token, other_registered_user, db_session
) -> None:
    other_id = other_registered_user["user"]["id"]
    source = VacancySource(
        user_id=other_id,
        kind="telegram",
        handle="their_jobs",
        default_name="@their_jobs",
        display_name="@their_jobs",
    )
    db_session.add(source)
    await db_session.commit()
    card = await add_card(db_session, other_id, "1", source_id=source.id)
    card_id, source_id = card.id, source.id

    resp = await client.delete(f"{SOURCES_URL}/{source_id}", headers=_auth(token))

    assert resp.status_code == 404
    db_session.expire_all()
    assert (await db_session.get(Vacancy, card_id)).source_id == source_id


async def _act(
    client: httpx.AsyncClient, token: str, card_id: str, action: str
) -> httpx.Response:
    return await client.post(f"{URL}/{card_id}/{action}", headers=_auth(token))


async def _state(db: AsyncSession, card_id: str) -> str:
    db.expire_all()
    return (await db.get(Vacancy, card_id)).state


async def _new_count(client: httpx.AsyncClient, token: str) -> int:
    resp = await client.get(f"{URL}/new-count", headers=_auth(token))
    return resp.json()["count"]


class TestCardActions:
    @pytest.mark.parametrize(
        ("action", "before", "after"),
        [
            ("seen", "new", "seen"),
            ("seen", "seen", "seen"),
            ("dismiss", "new", "dismissed"),
            ("dismiss", "seen", "dismissed"),
            ("dismiss", "dismissed", "dismissed"),
            ("restore", "dismissed", "seen"),
            ("restore", "new", "new"),
            ("restore", "seen", "seen"),
        ],
    )
    async def test_transition_or_idempotent_noop(
        self, client, token, user_id, db_session, action, before, after
    ) -> None:
        card = await add_card(db_session, user_id, "c", state=before)

        resp = await _act(client, token, card.id, action)

        assert resp.status_code == 204
        assert resp.content == b""
        assert await _state(db_session, card.id) == after

    @pytest.mark.parametrize(
        ("action", "state"),
        [
            ("seen", "dismissed"),
            ("seen", "added"),
            ("dismiss", "added"),
            ("restore", "added"),
        ],
    )
    async def test_card_out_of_inbox_409(
        self, client, token, user_id, db_session, action, state
    ) -> None:
        card = await add_card(db_session, user_id, "c", state=state)

        resp = await _act(client, token, card.id, action)

        assert resp.status_code == 409
        assert resp.json() == {"detail": "Vacancy is not in the Inbox."}
        assert await _state(db_session, card.id) == state

    @pytest.mark.parametrize("action", ["seen", "dismiss", "restore"])
    async def test_pending_or_missing_404(
        self, client, token, user_id, db_session, action
    ) -> None:
        card = await add_card(db_session, user_id, "p", state="pending")

        pending = await _act(client, token, card.id, action)
        missing = await _act(client, token, "no-such-id", action)

        for resp in (pending, missing):
            assert resp.status_code == 404
            assert resp.json() == {"detail": "Vacancy not found."}
        assert await _state(db_session, card.id) == "pending"

    @pytest.mark.parametrize(
        ("action", "state"),
        [("seen", "new"), ("dismiss", "new"), ("restore", "dismissed")],
    )
    async def test_other_users_card_404_and_unchanged(
        self, client, token, other_registered_user, db_session, action, state
    ) -> None:
        other_id = other_registered_user["user"]["id"]
        card = await add_card(db_session, other_id, "theirs", state=state)

        resp = await _act(client, token, card.id, action)

        assert resp.status_code == 404
        assert await _state(db_session, card.id) == state

    @pytest.mark.parametrize("action", ["seen", "dismiss", "restore"])
    async def test_requires_auth(self, client, user_id, db_session, action) -> None:
        card = await add_card(db_session, user_id, "c")
        resp = await client.post(f"{URL}/{card.id}/{action}")
        assert resp.status_code == 401
        assert await _state(db_session, card.id) == "new"

    async def test_seen_drops_new_count_and_keeps_card_listed(
        self, client, token, user_id, db_session
    ) -> None:
        card = await add_card(db_session, user_id, "a", hours=1)
        await add_card(db_session, user_id, "b")
        assert await _new_count(client, token) == 2

        assert (await _act(client, token, card.id, "seen")).status_code == 204

        assert await _new_count(client, token) == 1
        assert await list_keys(client, token, state="seen") == ["a"]
        assert await list_keys(client, token, state="new") == ["b"]

    async def test_dismiss_then_undo_returns_card_as_seen(
        self, client, token, user_id, db_session
    ) -> None:
        card = await add_card(db_session, user_id, "a", hours=1)
        await add_card(db_session, user_id, "b")

        assert (await _act(client, token, card.id, "dismiss")).status_code == 204

        assert await list_keys(client, token) == ["b"]
        assert await _new_count(client, token) == 1

        assert (await _act(client, token, card.id, "restore")).status_code == 204

        # Undo brings it back as seen, so the badge does not rise again.
        assert await list_keys(client, token) == ["a", "b"]
        assert await list_keys(client, token, state="seen") == ["a"]
        assert await _new_count(client, token) == 1

    async def test_dismissed_card_hides_its_removed_source(
        self, client, token, user_id, db_session
    ) -> None:
        card = await add_card(db_session, user_id, "a", labels=("@gone",))
        removed = [{"key": "telegram:gone", "label": "@gone"}]

        async def removed_sources() -> list[dict]:
            resp = await client.get(SOURCES_URL, headers=_auth(token))
            return resp.json()["removed_sources"]

        assert await removed_sources() == removed
        await _act(client, token, card.id, "dismiss")
        assert await removed_sources() == []
        await _act(client, token, card.id, "restore")
        assert await removed_sources() == removed


# ---------------------------------------------------------------------------
# PATCH /vacancy-sources/{id} — rename (spec 010 Slice 5)
# ---------------------------------------------------------------------------


async def _jobs_source(db: AsyncSession, user_id: str) -> str:
    source = VacancySource(
        user_id=user_id,
        kind="telegram",
        handle="jobs",
        default_name="@jobs",
        display_name="@jobs",
    )
    db.add(source)
    await db.commit()
    return source.id


async def _patch(
    client: httpx.AsyncClient, token: str, source_id: str, body: dict
) -> httpx.Response:
    return await client.patch(
        f"{SOURCES_URL}/{source_id}", json=body, headers=_auth(token)
    )


class TestRenameSource:
    async def test_rename_shows_in_list_and_on_cards(
        self, client, token, user_id, db_session
    ) -> None:
        source_id = await _jobs_source(db_session, user_id)
        await add_card(db_session, user_id, "1", source_id=source_id)

        resp = await _patch(client, token, source_id, {"name": "  My jobs  "})

        assert resp.status_code == 200, resp.text
        assert resp.json()["display_name"] == "My jobs"
        assert resp.json()["name_is_custom"] is True
        listed = (await client.get(SOURCES_URL, headers=_auth(token))).json()
        assert [
            (s["display_name"], s["name_is_custom"]) for s in listed["sources"]
        ] == [("My jobs", True)]
        cards = (await client.get(URL, headers=_auth(token))).json()["items"]
        assert cards[0]["sources"] == [{"key": "telegram:jobs", "label": "My jobs"}]

    @pytest.mark.parametrize("name", ["", "   ", None])
    async def test_blank_name_restores_default(
        self, client, token, user_id, db_session, name
    ) -> None:
        source_id = await _jobs_source(db_session, user_id)
        await _patch(client, token, source_id, {"name": "Custom"})

        resp = await _patch(client, token, source_id, {"name": name})

        assert resp.status_code == 200
        assert resp.json()["display_name"] == "@jobs"
        assert resp.json()["name_is_custom"] is False

    async def test_name_length_limit(self, client, token, user_id, db_session) -> None:
        source_id = await _jobs_source(db_session, user_id)

        too_long = await _patch(client, token, source_id, {"name": "x" * 101})
        exact = await _patch(client, token, source_id, {"name": "y" * 100})

        assert too_long.status_code == 400
        assert too_long.json()["detail"] == "Name can be up to 100 characters"
        assert exact.status_code == 200
        assert exact.json()["display_name"] == "y" * 100

    async def test_new_source_is_not_custom(
        self, client, token, user_id, db_session
    ) -> None:
        await _jobs_source(db_session, user_id)

        body = (await client.get(SOURCES_URL, headers=_auth(token))).json()

        assert body["sources"][0]["name_is_custom"] is False

    async def test_empty_body_changes_nothing(
        self, client, token, user_id, db_session
    ) -> None:
        source_id = await _jobs_source(db_session, user_id)
        await _patch(client, token, source_id, {"name": "Custom"})

        resp = await _patch(client, token, source_id, {})

        assert resp.status_code == 200
        assert resp.json()["display_name"] == "Custom"

    @pytest.mark.parametrize(
        "body",
        [
            {"name": "New", "job_link_contains": "/job/"},
            {"name": "New", "job_link_contains": None},
            {"name": "New", "input": None},
        ],
    )
    async def test_web_only_pattern_and_null_input_are_ignored_for_channels(
        self, client, token, user_id, db_session, respx_mock, body
    ) -> None:
        source_id = await _jobs_source(db_session, user_id)

        resp = await _patch(client, token, source_id, body)

        assert resp.status_code == 200, resp.text
        assert (resp.json()["id"], resp.json()["display_name"]) == (source_id, "New")
        assert resp.json()["job_link_contains"] is None
        assert not respx_mock.calls

    async def test_same_channel_in_another_form_is_a_rename_only(
        self, client, token, user_id, db_session, respx_mock
    ) -> None:
        source = VacancySource(
            user_id=user_id,
            kind="telegram",
            handle="jobs_feed",
            default_name="Jobs Feed",
            display_name="Jobs Feed",
        )
        db_session.add(source)
        await db_session.commit()

        resp = await _patch(
            client, token, source.id, {"input": "https://t.me/s/Jobs_Feed", "name": "X"}
        )

        assert resp.status_code == 200, resp.text
        assert (resp.json()["id"], resp.json()["display_name"]) == (source.id, "X")
        assert not respx_mock.calls


CHANNEL_PAGE = """<html><body><div class="tgme_channel_info">
<div class="tgme_channel_info_header_title"><span>Other Jobs</span></div>
</div></body></html>"""


class TestReplaceSource:
    async def test_rename_then_replace_channel(
        self, client, token, user_id, db_session, respx_mock
    ) -> None:
        route = respx_mock.get("https://t.me/s/other_jobs").respond(
            200, text=CHANNEL_PAGE
        )
        source_id = await _jobs_source(db_session, user_id)
        await add_card(db_session, user_id, "1", source_id=source_id)
        await add_card(db_session, user_id, "2", state="pending", source_id=source_id)
        await _patch(client, token, source_id, {"name": "Renamed jobs"})

        resp = await _patch(client, token, source_id, {"input": "t.me/other_jobs"})

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["id"] != source_id
        assert data["key"] == "telegram:other_jobs"
        # The old custom name stays with the removed source, not the new one.
        assert (data["display_name"], data["name_is_custom"]) == ("Other Jobs", False)
        assert data["scanning"] is True
        assert data["editable"] is True
        assert route.call_count == 1
        body = (await client.get(SOURCES_URL, headers=_auth(token))).json()
        assert [s["id"] for s in body["sources"]] == [data["id"]]
        # "(removed)" shows the latest name, not the one the card was found with.
        assert body["removed_sources"] == [
            {"key": "telegram:jobs", "label": "Renamed jobs"}
        ]
        cards = (await client.get(URL, headers=_auth(token))).json()["items"]
        assert [c["sources"] for c in cards] == [
            [{"key": "telegram:jobs", "label": "Renamed jobs"}]
        ]
        pending = await db_session.execute(
            select(Vacancy).where(Vacancy.state == "pending")
        )
        assert pending.scalars().all() == []
        new = await db_session.get(VacancySource, data["id"])
        assert new is not None and new.initial_scan_completed_at is None

    async def test_replace_with_default_name_uses_the_new_channel_title(
        self, client, token, user_id, db_session, respx_mock
    ) -> None:
        respx_mock.get("https://t.me/s/other_jobs").respond(200, text=CHANNEL_PAGE)
        source_id = await _jobs_source(db_session, user_id)

        resp = await _patch(client, token, source_id, {"input": "@other_jobs"})

        assert resp.status_code == 200, resp.text
        assert (resp.json()["display_name"], resp.json()["name_is_custom"]) == (
            "Other Jobs",
            False,
        )

    @pytest.mark.parametrize(
        ("name", "expected", "is_custom"),
        [
            ("Brand new", "Brand new", True),
            ("  Renamed jobs  ", "Other Jobs", False),  # old name echoed back
        ],
    )
    async def test_replace_name_applies_only_when_it_differs_from_the_old_one(
        self, client, token, user_id, db_session, respx_mock, name, expected, is_custom
    ) -> None:
        respx_mock.get("https://t.me/s/other_jobs").respond(200, text=CHANNEL_PAGE)
        source_id = await _jobs_source(db_session, user_id)
        await add_card(db_session, user_id, "1", source_id=source_id)
        await _patch(client, token, source_id, {"name": "Renamed jobs"})

        resp = await _patch(
            client, token, source_id, {"input": "@other_jobs", "name": name}
        )

        assert resp.status_code == 200, resp.text
        assert (resp.json()["display_name"], resp.json()["name_is_custom"]) == (
            expected,
            is_custom,
        )
        body = (await client.get(SOURCES_URL, headers=_auth(token))).json()
        assert body["removed_sources"] == [
            {"key": "telegram:jobs", "label": "Renamed jobs"}
        ]

    async def test_failed_live_check_keeps_the_old_source(
        self, client, token, user_id, db_session, respx_mock
    ) -> None:
        respx_mock.get("https://t.me/s/other_jobs").respond(302)
        source_id = await _jobs_source(db_session, user_id)
        await add_card(db_session, user_id, "1", source_id=source_id)
        added = await client.post(
            SOURCES_URL, json={"input": "@other_jobs"}, headers=_auth(token)
        )

        resp = await _patch(client, token, source_id, {"input": "@other_jobs"})

        assert resp.status_code == added.status_code == 400
        assert resp.json() == added.json()
        body = (await client.get(SOURCES_URL, headers=_auth(token))).json()
        assert [s["id"] for s in body["sources"]] == [source_id]
        assert body["removed_sources"] == []

    async def test_replace_with_another_watched_channel_is_409(
        self, client, token, user_id, db_session, respx_mock
    ) -> None:
        source_id = await _jobs_source(db_session, user_id)
        db_session.add(
            VacancySource(
                user_id=user_id,
                kind="telegram",
                handle="other_jobs",
                default_name="Other Jobs",
                display_name="Other Jobs",
            )
        )
        await db_session.commit()

        resp = await _patch(client, token, source_id, {"input": "@Other_Jobs"})

        assert resp.status_code == 409
        assert resp.json() == {"detail": "Already in your sources"}
        assert not respx_mock.calls

    async def test_unknown_or_foreign_source_is_404(
        self, client, token, user_id, db_session, other_registered_user
    ) -> None:
        source_id = await _jobs_source(db_session, user_id)
        other_token = other_registered_user["access_token"]

        foreign = await _patch(client, other_token, source_id, {"name": "Mine"})
        unknown = await _patch(client, token, "no-such-id", {"name": "Mine"})

        assert foreign.status_code == 404
        assert unknown.status_code == 404
        listed = (await client.get(SOURCES_URL, headers=_auth(token))).json()
        assert listed["sources"][0]["display_name"] == "@jobs"

    async def test_rename_then_delete_keeps_latest_name_as_removed_label(
        self, client, token, user_id, db_session
    ) -> None:
        source_id = await _jobs_source(db_session, user_id)
        await add_card(db_session, user_id, "1", source_id=source_id)
        await _patch(client, token, source_id, {"name": "Renamed jobs"})

        resp = await client.delete(f"{SOURCES_URL}/{source_id}", headers=_auth(token))

        assert resp.status_code == 204
        body = (await client.get(SOURCES_URL, headers=_auth(token))).json()
        assert body["removed_sources"] == [
            {"key": "telegram:jobs", "label": "Renamed jobs"}
        ]
        cards = (await client.get(URL, headers=_auth(token))).json()["items"]
        assert cards[0]["sources"] == [{"key": "telegram:jobs", "label": "Renamed jobs"}]
