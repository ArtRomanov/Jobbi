"""Inbox "Add to tracker" / "Add & tailor CV" (spec 009 Slice 5), the
`existing_application` hint on cards, and the non-committing builders."""

import asyncio
from collections.abc import AsyncGenerator
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.core.deps import get_db
from app.core.security import create_access_token
from app.main import create_app
from app.models.application import Application, ApplicationStatusHistory
from app.models.cv import Cv
from app.models.user import User
from app.models.vacancy import Vacancy
from app.schemas.application import ApplicationCreate
from app.services import application_service, cv_service
from tests.test_vacancies_api import URL, _auth, add_card

APPS_URL = "/api/v1/applications"


@pytest.fixture
def token(registered_user: dict) -> str:
    return registered_user["access_token"]


@pytest.fixture
def user_id(registered_user: dict) -> str:
    return registered_user["user"]["id"]


def _add_url(card_id: str) -> str:
    return f"{URL}/{card_id}/add-to-tracker"


async def _add(
    client: httpx.AsyncClient, token: str, card_id: str, **body: object
) -> httpx.Response:
    payload = {"company_name": "Acme", "role_title": "Frontend Engineer", **body}
    return await client.post(_add_url(card_id), json=payload, headers=_auth(token))


async def _count(db: AsyncSession, model: type[Base]) -> int:
    return await db.scalar(select(func.count()).select_from(model)) or 0


async def _card(db: AsyncSession, card_id: str) -> Vacancy:
    card = await db.get(Vacancy, card_id, populate_existing=True)
    assert card is not None
    return card


async def _make_cv(db: AsyncSession, user_id: str, name: str = "Base CV") -> Cv:
    cv = Cv(
        user_id=user_id,
        name=name,
        personal_info={"full_name": "Jane Doe", "email": "jane@example.com"},
        summary="Frontend engineer",
        work_experience=[{"company": "Old Co", "role": "Dev", "is_current": False}],
        education=[{"institution": "Uni"}],
        skills="React, TypeScript",
        languages="English",
    )
    db.add(cv)
    await db.commit()
    return cv


async def _make_application(
    db: AsyncSession, user_id: str, job_url: str | None, company: str = "Acme"
) -> Application:
    application = Application(
        user_id=user_id,
        company_name=company,
        role_title="Old Role",
        job_url=job_url,
        status="applied",
    )
    db.add(application)
    await db.commit()
    return application


async def _new_count(client: httpx.AsyncClient, token: str) -> int:
    resp = await client.get(f"{URL}/new-count", headers=_auth(token))
    return resp.json()["count"]


class TestAddToTracker:
    async def test_happy_path(self, client, token, user_id, db_session) -> None:
        card = await add_card(db_session, user_id, "a")
        other = await add_card(db_session, user_id, "b", hours=1)
        assert await _new_count(client, token) == 2

        resp = await _add(client, token, card.id)

        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body == {"application_id": body["application_id"], "cv_id": None}
        application = await db_session.get(Application, body["application_id"])
        assert application is not None
        assert (
            application.user_id,
            application.company_name,
            application.role_title,
            application.job_url,
            application.notes,
            application.status,
            application.cv_id,
        ) == (
            user_id,
            "Acme",
            "Frontend Engineer",
            "https://acme.example/jobs/a",
            "Text a",
            "researching",
            None,
        )
        history = (
            await db_session.scalars(
                select(ApplicationStatusHistory.status).where(
                    ApplicationStatusHistory.application_id == application.id
                )
            )
        ).all()
        assert history == ["researching"]
        saved = await _card(db_session, card.id)
        assert (saved.state, saved.application_id) == ("added", application.id)
        listed = await client.get(URL, headers=_auth(token))
        assert [item["id"] for item in listed.json()["items"]] == [other.id]
        assert await _new_count(client, token) == 1

    async def test_given_notes_and_trimmed_names(
        self, client, token, user_id, db_session
    ) -> None:
        card = await add_card(db_session, user_id, "a", state="seen")

        resp = await _add(
            client,
            token,
            card.id,
            company_name="  Acme Labs ",
            role_title=" Dev ",
            notes="My notes",
        )

        assert resp.status_code == 201
        application = await db_session.get(Application, resp.json()["application_id"])
        assert (application.company_name, application.role_title) == (
            "Acme Labs",
            "Dev",
        )
        assert application.notes == "My notes"

    async def test_card_without_job_link_uses_post_url(
        self, client, token, user_id, db_session
    ) -> None:
        card = await add_card(db_session, user_id, "a")
        card.job_link = None
        await db_session.commit()

        resp = await _add(client, token, card.id)

        application = await db_session.get(Application, resp.json()["application_id"])
        assert application.job_url == "https://t.me/jobs/a"

    @pytest.mark.parametrize(
        "body",
        [
            {"company_name": "", "role_title": "Dev"},
            {"company_name": "Acme", "role_title": "   "},
            {"company_name": "A" * 256, "role_title": "Dev"},
            {"role_title": "Dev"},
            {"company_name": "Acme"},
        ],
    )
    async def test_invalid_body_422_and_nothing_changes(
        self, client, token, user_id, db_session, body
    ) -> None:
        card = await add_card(db_session, user_id, "a")

        resp = await client.post(_add_url(card.id), json=body, headers=_auth(token))

        assert resp.status_code == 422
        assert (await _card(db_session, card.id)).state == "new"
        assert await _count(db_session, Application) == 0

    async def test_requires_auth(self, client, user_id, db_session) -> None:
        card = await add_card(db_session, user_id, "a")
        resp = await client.post(
            _add_url(card.id), json={"company_name": "A", "role_title": "B"}
        )
        assert resp.status_code == 401

    @pytest.mark.parametrize(
        ("state", "detail"),
        [("added", "Already added"), ("dismissed", "Vacancy is not in the Inbox.")],
    )
    async def test_card_out_of_inbox_409(
        self, client, token, user_id, db_session, state, detail
    ) -> None:
        card = await add_card(db_session, user_id, "a", state=state)

        resp = await _add(client, token, card.id)

        assert resp.status_code == 409
        assert resp.json() == {"detail": detail}
        assert (await _card(db_session, card.id)).state == state
        assert await _count(db_session, Application) == 0

    async def test_second_add_is_already_added(
        self, client, token, user_id, db_session
    ) -> None:
        card = await add_card(db_session, user_id, "a")

        first = await _add(client, token, card.id)
        second = await _add(client, token, card.id, allow_duplicate=True)

        assert first.status_code == 201
        assert second.status_code == 409
        assert second.json() == {"detail": "Already added"}
        assert await _count(db_session, Application) == 1

    async def test_pending_or_missing_404(
        self, client, token, user_id, db_session
    ) -> None:
        card = await add_card(db_session, user_id, "p", state="pending")

        for card_id in (card.id, "no-such-id"):
            resp = await _add(client, token, card_id)
            assert resp.status_code == 404
            assert resp.json() == {"detail": "Vacancy not found."}
        assert (await _card(db_session, card.id)).state == "pending"
        assert await _count(db_session, Application) == 0

    async def test_other_users_card_404_and_unchanged(
        self, client, token, other_registered_user, db_session
    ) -> None:
        card = await add_card(db_session, other_registered_user["user"]["id"], "x")

        resp = await _add(client, token, card.id)

        assert resp.status_code == 404
        assert resp.json() == {"detail": "Vacancy not found."}
        assert (await _card(db_session, card.id)).state == "new"
        assert await _count(db_session, Application) == 0


class TestDuplicateDetection:
    @pytest.mark.parametrize(
        "tracked_url",
        [
            "https://acme.example/jobs/a",
            "https://acme.example/jobs/a/",
            "https://ACME.example/jobs/a?utm_source=telegram&utm_medium=post",
            "https://acme.example/jobs/a#apply",
            "  https://acme.example:443/jobs/a/?utm_campaign=x#top ",
        ],
    )
    async def test_normalized_match_409_structured(
        self, client, token, user_id, db_session, tracked_url
    ) -> None:
        existing = await _make_application(db_session, user_id, tracked_url)
        card = await add_card(db_session, user_id, "a", state="seen")

        resp = await _add(client, token, card.id)

        assert resp.status_code == 409
        assert resp.json() == {
            "detail": {
                "message": "You already track this",
                "application": {
                    "id": existing.id,
                    "company_name": "Acme",
                    "role_title": "Old Role",
                },
            }
        }
        saved = await _card(db_session, card.id)
        assert (saved.state, saved.application_id) == ("seen", None)
        assert await _count(db_session, Application) == 1

    @pytest.mark.parametrize(
        "tracked_url",
        [
            "https://acme.example/jobs/b",
            "https://acme.example/jobs/a?ref=1",
            "https://other.example/jobs/a",
            None,
            "",
        ],
    )
    async def test_different_link_is_not_a_duplicate(
        self, client, token, user_id, db_session, tracked_url
    ) -> None:
        await _make_application(db_session, user_id, tracked_url)
        card = await add_card(db_session, user_id, "a")

        resp = await _add(client, token, card.id)

        assert resp.status_code == 201

    async def test_other_users_application_is_not_a_duplicate(
        self, client, token, user_id, other_registered_user, db_session
    ) -> None:
        await _make_application(
            db_session,
            other_registered_user["user"]["id"],
            "https://acme.example/jobs/a",
        )
        card = await add_card(db_session, user_id, "a")

        assert (await _add(client, token, card.id)).status_code == 201

    async def test_allow_duplicate_adds_anyway(
        self, client, token, user_id, db_session
    ) -> None:
        await _make_application(db_session, user_id, "https://acme.example/jobs/a/")
        card = await add_card(db_session, user_id, "a")

        resp = await _add(client, token, card.id, allow_duplicate=True)

        assert resp.status_code == 201
        assert await _count(db_session, Application) == 2
        assert (await _card(db_session, card.id)).state == "added"


class TestAddAndTailorCv:
    async def test_copies_base_cv_and_links_it(
        self, client, token, user_id, db_session
    ) -> None:
        base = await _make_cv(db_session, user_id, "Main CV")
        card = await add_card(db_session, user_id, "a")

        resp = await _add(client, token, card.id, base_cv_id=base.id)

        assert resp.status_code == 201
        body = resp.json()
        assert body["cv_id"] not in (None, base.id)
        copy = await db_session.get(Cv, body["cv_id"])
        assert copy.user_id == user_id
        assert copy.name == "Main CV — Acme Frontend Engineer"
        for field in (
            "personal_info",
            "summary",
            "work_experience",
            "education",
            "skills",
            "languages",
        ):
            assert getattr(copy, field) == getattr(base, field)
        application = await db_session.get(Application, body["application_id"])
        assert application.cv_id == copy.id
        assert (await _card(db_session, card.id)).application_id == application.id
        assert await _count(db_session, Cv) == 2

    async def test_copy_name_is_cut_to_255(
        self, client, token, user_id, db_session
    ) -> None:
        base = await _make_cv(db_session, user_id, "C" * 200)
        card = await add_card(db_session, user_id, "a")

        resp = await _add(
            client,
            token,
            card.id,
            base_cv_id=base.id,
            company_name="Company" * 10,
            role_title="Role" * 10,
        )

        copy = await db_session.get(Cv, resp.json()["cv_id"])
        expected = f"{'C' * 200} — {'Company' * 10} {'Role' * 10}"[:255]
        assert copy.name == expected
        assert len(copy.name) == 255

    @pytest.mark.parametrize("whose", ["other", "unknown"])
    async def test_foreign_or_unknown_cv_404_and_nothing_persisted(
        self, client, token, user_id, other_registered_user, db_session, whose
    ) -> None:
        if whose == "other":
            cv_id = (await _make_cv(db_session, other_registered_user["user"]["id"])).id
        else:
            cv_id = "no-such-cv"
        card = await add_card(db_session, user_id, "a")

        resp = await _add(client, token, card.id, base_cv_id=cv_id)

        assert resp.status_code == 404
        assert resp.json() == {"detail": "CV not found."}
        saved = await _card(db_session, card.id)
        assert (saved.state, saved.application_id) == ("new", None)
        assert await _count(db_session, Application) == 0
        assert await _count(db_session, ApplicationStatusHistory) == 0
        assert await _count(db_session, Cv) == (1 if whose == "other" else 0)

    async def test_copy_failure_rolls_everything_back(
        self, client, token, user_id, db_session, monkeypatch
    ) -> None:
        base = await _make_cv(db_session, user_id)
        card = await add_card(db_session, user_id, "a", state="seen")

        async def _fail(*_args: object, **_kwargs: object) -> Cv:
            raise RuntimeError("disk full")

        monkeypatch.setattr(cv_service, "build_cv_copy", _fail)

        with pytest.raises(RuntimeError, match="disk full"):
            await _add(client, token, card.id, base_cv_id=base.id)

        saved = await _card(db_session, card.id)
        assert (saved.state, saved.application_id) == ("seen", None)
        assert await _count(db_session, Application) == 0
        assert await _count(db_session, ApplicationStatusHistory) == 0
        assert await _count(db_session, Cv) == 1


class TestExistingApplicationInList:
    async def test_card_shows_matching_application(
        self, client, token, user_id, other_registered_user, db_session
    ) -> None:
        tracked = await _make_application(
            db_session, user_id, "https://Acme.example/jobs/a/?utm_source=x#f"
        )
        await _make_application(
            db_session,
            other_registered_user["user"]["id"],
            "https://acme.example/jobs/b",
        )
        await add_card(db_session, user_id, "a", hours=1)
        await add_card(db_session, user_id, "b")
        no_link = await add_card(db_session, user_id, "c", hours=2)
        no_link.job_link = None
        await db_session.commit()
        await _make_application(db_session, user_id, "https://t.me/jobs/c", "TG")

        resp = await client.get(URL, headers=_auth(token))

        hints = {
            item["url"].rsplit("/", 1)[1]: item["existing_application"]
            for item in resp.json()["items"]
        }
        assert hints["a"] == {
            "id": tracked.id,
            "company_name": "Acme",
            "role_title": "Old Role",
        }
        assert hints["b"] is None
        assert hints["c"]["company_name"] == "TG"

    async def test_open_it_flow_card_stays_and_becomes_seen(
        self, client, token, user_id, db_session
    ) -> None:
        # "Open it" = the existing /seen action; the hint survives it.
        await _make_application(db_session, user_id, "https://acme.example/jobs/a")
        card = await add_card(db_session, user_id, "a")

        dup = await _add(client, token, card.id)
        seen = await client.post(f"{URL}/{card.id}/seen", headers=_auth(token))

        assert dup.status_code == 409
        assert seen.status_code == 204
        items = (await client.get(URL, headers=_auth(token))).json()["items"]
        assert [(i["state"], i["existing_application"] is not None) for i in items] == [
            ("seen", True)
        ]


async def test_delete_application_clears_vacancy_link(
    client, token, user_id, db_session
) -> None:
    card = await add_card(db_session, user_id, "a")
    keep = await add_card(db_session, user_id, "b")
    first = (await _add(client, token, card.id)).json()["application_id"]
    second = (await _add(client, token, keep.id)).json()["application_id"]

    resp = await client.delete(f"{APPS_URL}/{first}", headers=_auth(token))

    assert resp.status_code in (200, 204)
    saved = await _card(db_session, card.id)
    assert (saved.state, saved.application_id) == ("added", None)
    assert (await _card(db_session, keep.id)).application_id == second


class TestBuilders:
    async def test_build_application_does_not_commit(
        self, db_session, make_user
    ) -> None:
        user = await make_user()

        application = await application_service.build_application(
            db_session,
            user.id,
            ApplicationCreate(company_name="Acme", role_title="Dev"),
        )
        assert application.id is not None
        await db_session.rollback()

        assert await _count(db_session, Application) == 0
        assert await _count(db_session, ApplicationStatusHistory) == 0

    async def test_build_cv_copy_does_not_commit(self, db_session, make_user) -> None:
        user = await make_user()
        base = await _make_cv(db_session, user.id)

        copy = await cv_service.build_cv_copy(db_session, user.id, base.id, "Copy")
        assert (copy.name, copy.summary) == ("Copy", "Frontend engineer")
        await db_session.rollback()

        assert await _count(db_session, Cv) == 1

    async def test_build_cv_copy_of_foreign_cv_raises(
        self, db_session, make_user
    ) -> None:
        owner = await make_user()
        stranger = await make_user()
        base = await _make_cv(db_session, owner.id)

        with pytest.raises(cv_service.CvNotFoundError):
            await cv_service.build_cv_copy(db_session, stranger.id, base.id, "Copy")


# ---------------------------------------------------------------------------
# Concurrent double add (file-backed DB: each request gets its own connection,
# like two clicks processed at once)
# ---------------------------------------------------------------------------


@pytest.fixture
async def file_sessions(
    tmp_path: Path,
) -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'race.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def file_client(
    file_sessions: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[httpx.AsyncClient, None]:
    app = create_app()

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with file_sessions() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_concurrent_double_add_creates_one_application(
    file_client: httpx.AsyncClient,
    file_sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with file_sessions() as db:
        user = User(email="race@example.com", password_hash="x", full_name="Race")
        db.add(user)
        await db.commit()
        card = await add_card(db, user.id, "a")
        base = await _make_cv(db, user.id)
    token = create_access_token(user.id)

    results = await asyncio.gather(
        _add(file_client, token, card.id, base_cv_id=base.id),
        _add(file_client, token, card.id, base_cv_id=base.id, allow_duplicate=True),
    )

    assert sorted(r.status_code for r in results) == [201, 409]
    loser = next(r for r in results if r.status_code == 409)
    assert loser.json() == {"detail": "Already added"}
    winner = next(r for r in results if r.status_code == 201).json()
    async with file_sessions() as db:
        assert await _count(db, Application) == 1
        assert await _count(db, ApplicationStatusHistory) == 1
        assert await _count(db, Cv) == 2
        saved = await db.get(Vacancy, card.id)
        assert (saved.state, saved.application_id) == (
            "added",
            winner["application_id"],
        )
