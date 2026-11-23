"""Base CV and tailored copies (spec 011, slices 5 and 6; functional 2.4–2.6).

Covers `POST /cvs/{id}/make-base`, the CvRead fields `is_base` / `kind` /
`tailored_for` / `tailored_application_deleted`, the `GET /cvs` order, the
manual FK nulling in `delete_cv` / `delete_application`, the tailored copy made
by "Add & tailor CV" and the frozen classification rule of migration
cd2779fea0d9.
"""

import importlib.util
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.cv import Cv
from app.models.user import User
from app.services.vacancy_service import tailored_cv_name
from tests.cv_upload_files import make_docx
from tests.test_vacancies_api import add_card

CVS_URL = "/api/v1/cvs"
APPS_URL = "/api/v1/applications"
VACANCIES_URL = "/api/v1/vacancies"
T0 = datetime(2026, 11, 1, 12, 0)
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def token(registered_user: dict) -> str:
    return registered_user["access_token"]


@pytest.fixture
def user_id(registered_user: dict) -> str:
    return registered_user["user"]["id"]


async def _make_cv(
    db: AsyncSession,
    user_id: str,
    name: str,
    *,
    updated_minutes: int = 0,
    kind: str = "own",
    tailored_for_application_id: str | None = None,
) -> Cv:
    stamp = T0 + timedelta(minutes=updated_minutes)
    cv = Cv(
        user_id=user_id,
        name=name,
        content=f"# {name}",
        kind=kind,
        tailored_for_application_id=tailored_for_application_id,
        created_at=stamp,
        updated_at=stamp,
    )
    db.add(cv)
    await db.commit()
    return cv


async def _make_application(
    db: AsyncSession,
    user_id: str,
    company: str = "Kleos",
    role: str = "Frontend Engineer",
) -> Application:
    application = Application(
        user_id=user_id, company_name=company, role_title=role, status="applied"
    )
    db.add(application)
    await db.commit()
    return application


async def _list(client: httpx.AsyncClient, token: str) -> list[dict]:
    resp = await client.get(CVS_URL, headers=_auth(token))
    assert resp.status_code == 200
    return resp.json()


async def _make_base(
    client: httpx.AsyncClient, token: str, cv_id: str
) -> httpx.Response:
    return await client.post(f"{CVS_URL}/{cv_id}/make-base", headers=_auth(token))


async def _base_cv_id(db: AsyncSession, user_id: str) -> str | None:
    return await db.scalar(
        select(User.base_cv_id)
        .where(User.id == user_id)
        .execution_options(populate_existing=True)
    )


async def _fresh_cv(db: AsyncSession, cv_id: str) -> Cv | None:
    return await db.get(Cv, cv_id, populate_existing=True)


# ---------------------------------------------------------------------------
# CvRead shape
# ---------------------------------------------------------------------------


class TestCvReadShape:
    async def test_new_cv_is_own_and_not_base(self, client, token) -> None:
        resp = await client.post(CVS_URL, json={"name": "Mine"}, headers=_auth(token))

        body = resp.json()
        assert body["kind"] == "own"
        assert body["is_base"] is False
        assert body["tailored_for"] is None
        assert body["tailored_application_deleted"] is False

    async def test_tailored_copy_shows_its_application(
        self, client, token, user_id, db_session
    ) -> None:
        application = await _make_application(db_session, user_id, "Codery", "QA")
        copy = await _make_cv(
            db_session,
            user_id,
            "Copy",
            kind="tailored",
            tailored_for_application_id=application.id,
        )

        body = (await client.get(f"{CVS_URL}/{copy.id}", headers=_auth(token))).json()

        assert body["kind"] == "tailored"
        assert body["tailored_for"] == {
            "application_id": application.id,
            "company_name": "Codery",
            "role_title": "QA",
        }
        assert body["tailored_application_deleted"] is False

    @pytest.mark.parametrize("link", ["none", "dangling"])
    async def test_tailored_copy_without_application_reads_deleted(
        self, client, token, user_id, db_session, link
    ) -> None:
        copy = await _make_cv(
            db_session,
            user_id,
            "Copy",
            kind="tailored",
            tailored_for_application_id=None if link == "none" else "gone-app-id",
        )

        body = (await client.get(f"{CVS_URL}/{copy.id}", headers=_auth(token))).json()

        assert body["tailored_for"] is None
        assert body["tailored_application_deleted"] is True

    async def test_another_users_application_is_never_described(
        self, client, token, user_id, other_registered_user, db_session
    ) -> None:
        foreign = await _make_application(
            db_session, other_registered_user["user"]["id"], "Secret Co", "Spy"
        )
        copy = await _make_cv(
            db_session,
            user_id,
            "Copy",
            kind="tailored",
            tailored_for_application_id=foreign.id,
        )

        body = (await client.get(f"{CVS_URL}/{copy.id}", headers=_auth(token))).json()

        assert body["tailored_for"] is None
        assert "Secret Co" not in str(body)

    async def test_own_cv_linked_to_an_application_is_not_tailored(
        self, client, token, user_id, db_session
    ) -> None:
        application = await _make_application(db_session, user_id)
        cv = await _make_cv(
            db_session, user_id, "Hand-linked", tailored_for_application_id=None
        )
        application.cv_id = cv.id
        await db_session.commit()

        body = (await client.get(f"{CVS_URL}/{cv.id}", headers=_auth(token))).json()

        assert body["kind"] == "own"
        assert body["tailored_for"] is None
        assert body["tailored_application_deleted"] is False
        assert body["linked_applications_count"] == 1


# ---------------------------------------------------------------------------
# GET /cvs order
# ---------------------------------------------------------------------------


async def test_list_order_base_then_own_then_tailored(
    client, token, user_id, db_session
) -> None:
    application = await _make_application(db_session, user_id)
    old_own = await _make_cv(db_session, user_id, "old own", updated_minutes=1)
    base = await _make_cv(db_session, user_id, "base", updated_minutes=2)
    new_own = await _make_cv(db_session, user_id, "new own", updated_minutes=3)
    old_copy = await _make_cv(
        db_session,
        user_id,
        "old copy",
        updated_minutes=4,
        kind="tailored",
        tailored_for_application_id=application.id,
    )
    new_copy = await _make_cv(
        db_session,
        user_id,
        "new copy",
        updated_minutes=5,
        kind="tailored",
        tailored_for_application_id=None,
    )
    assert (await _make_base(client, token, base.id)).status_code == 200

    listed = await _list(client, token)

    assert [cv["id"] for cv in listed] == [
        base.id,
        new_own.id,
        old_own.id,
        new_copy.id,
        old_copy.id,
    ]
    assert [cv["is_base"] for cv in listed] == [True, False, False, False, False]


async def test_list_without_base_is_own_then_tailored(
    client, token, user_id, db_session
) -> None:
    copy = await _make_cv(
        db_session, user_id, "copy", updated_minutes=9, kind="tailored"
    )
    own = await _make_cv(db_session, user_id, "own", updated_minutes=1)

    listed = await _list(client, token)

    assert [cv["id"] for cv in listed] == [own.id, copy.id]
    assert not any(cv["is_base"] for cv in listed)


# ---------------------------------------------------------------------------
# POST /cvs/{id}/make-base
# ---------------------------------------------------------------------------


class TestMakeBase:
    async def test_sets_base_and_returns_cv(
        self, client, token, user_id, db_session
    ) -> None:
        cv = await _make_cv(db_session, user_id, "Main")

        resp = await _make_base(client, token, cv.id)

        assert resp.status_code == 200
        body = resp.json()
        assert (body["id"], body["is_base"], body["kind"]) == (cv.id, True, "own")
        assert body["version"] == 1
        assert await _base_cv_id(db_session, user_id) == cv.id

    async def test_previous_base_becomes_ordinary(
        self, client, token, user_id, db_session
    ) -> None:
        first = await _make_cv(db_session, user_id, "First")
        second = await _make_cv(db_session, user_id, "Second")
        await _make_base(client, token, first.id)

        await _make_base(client, token, second.id)

        listed = {cv["id"]: cv["is_base"] for cv in await _list(client, token)}
        assert listed == {first.id: False, second.id: True}

    async def test_is_idempotent(self, client, token, user_id, db_session) -> None:
        cv = await _make_cv(db_session, user_id, "Main")

        first = await _make_base(client, token, cv.id)
        second = await _make_base(client, token, cv.id)

        assert first.status_code == second.status_code == 200
        assert second.json()["is_base"] is True
        assert await _base_cv_id(db_session, user_id) == cv.id

    @pytest.mark.parametrize("whose", ["other", "unknown"])
    async def test_foreign_or_unknown_cv_404_and_base_unchanged(
        self, client, token, user_id, other_registered_user, db_session, whose
    ) -> None:
        mine = await _make_cv(db_session, user_id, "Mine")
        await _make_base(client, token, mine.id)
        if whose == "other":
            other_id = other_registered_user["user"]["id"]
            target = (await _make_cv(db_session, other_id, "Theirs")).id
        else:
            target = "no-such-cv"

        resp = await _make_base(client, token, target)

        assert resp.status_code == 404
        assert await _base_cv_id(db_session, user_id) == mine.id
        if whose == "other":
            assert await _base_cv_id(db_session, other_id) is None

    async def test_requires_auth(self, client, user_id, db_session) -> None:
        cv = await _make_cv(db_session, user_id, "Main")

        resp = await client.post(f"{CVS_URL}/{cv.id}/make-base")

        assert resp.status_code == 401
        assert await _base_cv_id(db_session, user_id) is None

    async def test_one_users_base_does_not_affect_another(
        self, client, token, user_id, other_registered_user, db_session
    ) -> None:
        other_id = other_registered_user["user"]["id"]
        other_token = other_registered_user["access_token"]
        mine = await _make_cv(db_session, user_id, "Mine")
        theirs = await _make_cv(db_session, other_id, "Theirs")

        await _make_base(client, token, mine.id)
        await _make_base(client, other_token, theirs.id)

        assert await _base_cv_id(db_session, user_id) == mine.id
        assert await _base_cv_id(db_session, other_id) == theirs.id

    async def test_tailored_copy_becomes_own_for_good_and_keeps_its_link(
        self, client, token, user_id, db_session
    ) -> None:
        application = await _make_application(db_session, user_id, "Welldin", "Dev")
        copy = await _make_cv(
            db_session,
            user_id,
            "Copy",
            updated_minutes=5,
            kind="tailored",
            tailored_for_application_id=application.id,
        )
        other = await _make_cv(db_session, user_id, "Other")

        resp = await _make_base(client, token, copy.id)

        body = resp.json()
        assert (body["kind"], body["is_base"]) == ("own", True)
        assert body["tailored_for"] is None
        assert body["tailored_application_deleted"] is False
        assert body["version"] == 1
        saved = await _fresh_cv(db_session, copy.id)
        assert saved.tailored_for_application_id == application.id
        # The list position is not moved by the kind change.
        assert saved.updated_at == T0 + timedelta(minutes=5)

        # Another CV becoming the base does not send it back to "tailored".
        await _make_base(client, token, other.id)
        saved = await _fresh_cv(db_session, copy.id)
        assert saved.kind == "own"
        listed = await _list(client, token)
        assert [cv["id"] for cv in listed] == [other.id, copy.id]
        assert all(cv["kind"] == "own" for cv in listed)


# ---------------------------------------------------------------------------
# Delete / duplicate
# ---------------------------------------------------------------------------


async def test_deleting_the_base_leaves_no_base(
    client, token, user_id, db_session
) -> None:
    base = await _make_cv(db_session, user_id, "Base")
    other = await _make_cv(db_session, user_id, "Other")
    await _make_base(client, token, base.id)

    resp = await client.delete(f"{CVS_URL}/{base.id}", headers=_auth(token))

    assert resp.status_code == 200
    assert await _base_cv_id(db_session, user_id) is None
    listed = await _list(client, token)
    assert [(cv["id"], cv["is_base"]) for cv in listed] == [(other.id, False)]


async def _point_base_at(db: AsyncSession, user_id: str, cv_id: str) -> None:
    """Set `users.base_cv_id` directly, bypassing the API (SQLite does not
    enforce the FK, so a pointer to a deleted CV can exist)."""
    await db.execute(update(User).where(User.id == user_id).values(base_cv_id=cv_id))
    await db.commit()


async def test_dangling_base_pointer_counts_as_no_base(
    client, token, user_id, db_session
) -> None:
    own = await _make_cv(db_session, user_id, "Own", updated_minutes=1)
    newer = await _make_cv(db_session, user_id, "Newer", updated_minutes=2)
    await _point_base_at(db_session, user_id, "missing-cv-id")

    listed = await _list(client, token)

    assert [(cv["id"], cv["is_base"]) for cv in listed] == [
        (newer.id, False),
        (own.id, False),
    ]
    one = await client.get(f"{CVS_URL}/{own.id}", headers=_auth(token))
    assert one.json()["is_base"] is False


async def test_upload_replaces_a_dangling_base_pointer(
    client, token, user_id, db_session
) -> None:
    await _point_base_at(db_session, user_id, "missing-cv-id")

    resp = await client.post(
        f"{CVS_URL}/upload",
        files={"file": ("up.docx", make_docx(), DOCX_MIME)},
        headers=_auth(token),
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["became_base"] is True
    assert body["is_base"] is True
    assert await _base_cv_id(db_session, user_id) == body["id"]


async def test_upload_replaces_a_pointer_to_another_users_cv(
    client, token, user_id, other_registered_user, db_session
) -> None:
    theirs = await _make_cv(db_session, other_registered_user["user"]["id"], "Theirs")
    await _point_base_at(db_session, user_id, theirs.id)

    resp = await client.post(
        f"{CVS_URL}/upload",
        files={"file": ("up.docx", make_docx(), DOCX_MIME)},
        headers=_auth(token),
    )

    assert resp.json()["became_base"] is True
    assert [cv["is_base"] for cv in await _list(client, token)] == [True]


async def test_deleting_another_cv_keeps_the_base(
    client, token, user_id, db_session
) -> None:
    base = await _make_cv(db_session, user_id, "Base")
    other = await _make_cv(db_session, user_id, "Other")
    await _make_base(client, token, base.id)

    await client.delete(f"{CVS_URL}/{other.id}", headers=_auth(token))

    assert await _base_cv_id(db_session, user_id) == base.id


async def test_deleting_a_cv_does_not_touch_another_users_base(
    client, token, user_id, other_registered_user, db_session
) -> None:
    other_id = other_registered_user["user"]["id"]
    theirs = await _make_cv(db_session, other_id, "Theirs")
    await _make_base(client, other_registered_user["access_token"], theirs.id)

    resp = await client.delete(f"{CVS_URL}/{theirs.id}", headers=_auth(token))

    assert resp.status_code == 404
    assert await _base_cv_id(db_session, other_id) == theirs.id


@pytest.mark.parametrize("source", ["base", "tailored"])
async def test_duplicate_is_always_own_and_not_base(
    client, token, user_id, db_session, source
) -> None:
    application = await _make_application(db_session, user_id)
    if source == "base":
        original = await _make_cv(db_session, user_id, "Original")
        await _make_base(client, token, original.id)
    else:
        original = await _make_cv(
            db_session,
            user_id,
            "Original",
            kind="tailored",
            tailored_for_application_id=application.id,
        )

    resp = await client.post(
        f"{CVS_URL}/{original.id}/duplicate", json={}, headers=_auth(token)
    )

    body = resp.json()
    assert resp.status_code == 201
    assert body["name"] == "Original (copy)"
    assert (body["kind"], body["is_base"], body["tailored_for"]) == (
        "own",
        False,
        None,
    )
    saved = await _fresh_cv(db_session, body["id"])
    assert saved.tailored_for_application_id is None
    expected_base = original.id if source == "base" else None
    assert await _base_cv_id(db_session, user_id) == expected_base


# ---------------------------------------------------------------------------
# "Add & tailor CV" and deleting its application
# ---------------------------------------------------------------------------


async def _add_and_tailor(
    client: httpx.AsyncClient,
    token: str,
    card_id: str,
    cv_id: str,
    company: str = "Kleos",
    role: str = "Frontend Engineer",
) -> dict:
    resp = await client.post(
        f"{VACANCIES_URL}/{card_id}/add-to-tracker",
        json={"company_name": company, "role_title": role, "base_cv_id": cv_id},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()


async def test_add_and_tailor_makes_a_tailored_copy_of_the_chosen_cv(
    client, token, user_id, db_session
) -> None:
    base = await _make_cv(db_session, user_id, "Base")
    chosen = await _make_cv(db_session, user_id, "Chosen")
    await _make_base(client, token, base.id)
    card = await add_card(db_session, user_id, "a")

    added = await _add_and_tailor(client, token, card.id, chosen.id)

    copy = (
        await client.get(f"{CVS_URL}/{added['cv_id']}", headers=_auth(token))
    ).json()
    assert copy["name"] == "Chosen — Kleos Frontend Engineer"
    assert copy["kind"] == "tailored"
    assert copy["is_base"] is False
    assert copy["tailored_for"] == {
        "application_id": added["application_id"],
        "company_name": "Kleos",
        "role_title": "Frontend Engineer",
    }
    assert copy["linked_applications_count"] == 1
    # The base does not move, and the copy lands after own CVs.
    assert await _base_cv_id(db_session, user_id) == base.id
    listed = await _list(client, token)
    assert listed[0]["id"] == base.id
    assert listed[-1]["id"] == copy["id"]


async def test_copy_of_a_tailored_copy_is_named_after_it(
    client, token, user_id, db_session
) -> None:
    source = await _make_cv(db_session, user_id, "Main — Old Co Dev", kind="tailored")
    card = await add_card(db_session, user_id, "a")

    added = await _add_and_tailor(client, token, card.id, source.id, "New Co", "QA")

    saved = await _fresh_cv(db_session, added["cv_id"])
    assert saved.name == "Main — Old Co Dev — New Co QA"
    assert saved.kind == "tailored"


async def test_deleting_the_application_marks_its_copy_deleted(
    client, token, user_id, db_session
) -> None:
    chosen = await _make_cv(db_session, user_id, "Chosen")
    card = await add_card(db_session, user_id, "a")
    added = await _add_and_tailor(client, token, card.id, chosen.id)
    copy_before = await _fresh_cv(db_session, added["cv_id"])
    updated_before = copy_before.updated_at

    resp = await client.delete(
        f"{APPS_URL}/{added['application_id']}", headers=_auth(token)
    )

    assert resp.status_code in (200, 204)
    saved = await _fresh_cv(db_session, added["cv_id"])
    assert saved.tailored_for_application_id is None
    assert saved.kind == "tailored"
    assert saved.updated_at == updated_before
    body = (
        await client.get(f"{CVS_URL}/{added['cv_id']}", headers=_auth(token))
    ).json()
    assert body["tailored_for"] is None
    assert body["tailored_application_deleted"] is True
    assert body["linked_applications_count"] == 0


async def test_deleting_another_application_keeps_the_copy_link(
    client, token, user_id, db_session
) -> None:
    chosen = await _make_cv(db_session, user_id, "Chosen")
    card = await add_card(db_session, user_id, "a")
    added = await _add_and_tailor(client, token, card.id, chosen.id)
    unrelated = await _make_application(db_session, user_id, "Other", "Role")

    await client.delete(f"{APPS_URL}/{unrelated.id}", headers=_auth(token))

    saved = await _fresh_cv(db_session, added["cv_id"])
    assert saved.tailored_for_application_id == added["application_id"]


@pytest.mark.parametrize(
    ("company", "role", "expected"),
    [
        ("Kleos", "Frontend Engineer", "CV — Kleos Frontend Engineer"),
        ("", "Frontend Engineer", "CV — Frontend Engineer"),
        ("Kleos", "", "CV — Kleos"),
        ("  ", "Frontend Engineer", "CV — Frontend Engineer"),
        ("", "", "CV"),
        (" ", " ", "CV"),
    ],
)
def test_tailored_cv_name_leaves_out_empty_parts(
    company: str, role: str, expected: str
) -> None:
    assert tailored_cv_name("CV", company, role) == expected


def test_tailored_cv_name_is_cut_to_255() -> None:
    name = tailored_cv_name("C" * 250, "Company", "Role")

    assert name == f"{'C' * 250} — Company Role"[:255]
    assert len(name) == 255


# ---------------------------------------------------------------------------
# Migration cd2779fea0d9: the frozen classification rule
# ---------------------------------------------------------------------------

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "cd2779fea0d9_add_base_cv_and_tailored_copies.py"
)


def _load_migration() -> ModuleType:
    """Import the migration file as a plain module (see test_cv_text_migration:
    the local `backend/alembic/` folder shadows the package under pytest)."""
    spec = importlib.util.spec_from_file_location("migration_cd2779fea0d9", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"alembic": SimpleNamespace(op=SimpleNamespace())}):
        spec.loader.exec_module(module)
    return module


find_tailored_copies = _load_migration().find_tailored_copies


class TestMigrationRule:
    def test_seeded_cases(self) -> None:
        cvs = [
            ("inbox-copy", "u1", T0),
            ("plain-copy", "u1", T0 + timedelta(hours=1, seconds=1)),
            ("hand-linked", "u1", T0 - timedelta(days=3)),
            ("unlinked", "u1", T0),
        ]
        applications = [
            ("app-inbox", "u1", "inbox-copy", T0 + timedelta(seconds=1)),
            ("app-plain", "u1", "plain-copy", T0 + timedelta(hours=1)),
            ("app-hand", "u1", "hand-linked", T0),
            ("app-none", "u1", None, T0),
        ]

        assert find_tailored_copies(cvs, applications) == {
            "inbox-copy": "app-inbox",
            "plain-copy": "app-plain",
        }

    @pytest.mark.parametrize(
        ("gap", "matches"),
        [
            (timedelta(seconds=5), True),
            (timedelta(seconds=-5), True),
            (timedelta(seconds=5, microseconds=1), False),
            (timedelta(seconds=-6), False),
        ],
    )
    def test_five_second_window(self, gap: timedelta, matches: bool) -> None:
        result = find_tailored_copies(
            [("cv", "u1", T0)], [("app", "u1", "cv", T0 + gap)]
        )

        assert (result == {"cv": "app"}) is matches

    def test_other_users_application_never_matches(self) -> None:
        assert find_tailored_copies([("cv", "u1", T0)], [("app", "u2", "cv", T0)]) == {}

    def test_closest_application_wins(self) -> None:
        result = find_tailored_copies(
            [("cv", "u1", T0)],
            [
                ("far", "u1", "cv", T0 + timedelta(seconds=4)),
                ("near", "u1", "cv", T0 + timedelta(seconds=1)),
            ],
        )

        assert result == {"cv": "near"}

    def test_unknown_cv_or_missing_dates_are_skipped(self) -> None:
        cvs = [("cv", "u1", None), ("cv2", "u1", T0)]
        applications = [
            ("a1", "u1", "missing-cv", T0),
            ("a2", "u1", "cv", T0),
            ("a3", "u1", "cv2", None),
        ]

        assert find_tailored_copies(cvs, applications) == {}
