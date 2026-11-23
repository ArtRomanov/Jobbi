"""CV change cards in the application chat (spec 011, slice 7)."""

import json
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import groq
import httpx
import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_change_card import ChatChangeCard
from app.models.chat_message import ChatMessage
from app.models.cv import Cv
from app.services import cv_service
from app.services.chat_tools import MALFORMED_CALL_NOTE, parse_propose_cv_edit

APPS = "/api/v1/applications"

CV_TEXT = (
    "# Jane Doe\n"
    "jane@example.com\n"
    "\n"
    "## Summary\n"
    "Experienced SRE with 5 years of production ops.\n"
    "\n"
    "## Skills\n"
    "- Python\n"
    "- jQuery\n"
    "- Kubernetes"
)


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Fake Groq client: streams text deltas, then tool-call deltas
# ---------------------------------------------------------------------------


def _chunk(content: str | None = None, tool_calls: list | None = None) -> Any:
    delta = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])


def _tool_delta(
    index: int, *, name: str | None = None, arguments: str | None = None
) -> Any:
    return SimpleNamespace(
        index=index,
        id=f"call_{index}" if name else None,
        type="function" if name else None,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def _call_chunks(index: int, args: dict | str) -> list[Any]:
    """One tool call split over three deltas, as Groq may stream it."""
    raw = args if isinstance(args, str) else json.dumps(args)
    cut = len(raw) // 2
    return [
        _chunk(tool_calls=[_tool_delta(index, name="propose_cv_edit")]),
        _chunk(tool_calls=[_tool_delta(index, arguments=raw[:cut])]),
        _chunk(tool_calls=[_tool_delta(index, arguments=raw[cut:])]),
    ]


class _FakeGroq:
    def __init__(self, chunks: list[Any]) -> None:
        self.chunks = chunks
        self.calls: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs: Any) -> AsyncIterator[Any]:
        self.calls.append(kwargs)

        async def _gen() -> AsyncIterator[Any]:
            for chunk in self.chunks:
                yield chunk

        return _gen()


@contextmanager
def _fake_groq(*chunks: Any) -> Iterator[_FakeGroq]:
    fake = _FakeGroq(list(chunks))
    with patch("app.services.groq_client._get_client", return_value=fake):
        yield fake


def _events(body: str) -> list[tuple[str, Any]]:
    events = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


async def _create_cv(client: httpx.AsyncClient, token: str, content: str) -> str:
    resp = await client.post(
        "/api/v1/cvs", json={"name": "Main", "content": content}, headers=_h(token)
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _create_app(
    client: httpx.AsyncClient, token: str, cv_id: str | None = None
) -> str:
    resp = await client.post(
        APPS, json={"company_name": "Acme", "role_title": "SRE"}, headers=_h(token)
    )
    assert resp.status_code == 201
    app_id = resp.json()["id"]
    if cv_id:
        await _link(client, token, app_id, cv_id)
    return app_id


async def _link(
    client: httpx.AsyncClient, token: str, app_id: str, cv_id: str | None
) -> None:
    resp = await client.patch(
        f"{APPS}/{app_id}", json={"cv_id": cv_id}, headers=_h(token)
    )
    assert resp.status_code == 200, resp.text


@pytest.fixture
async def setup(client: httpx.AsyncClient, registered_user: dict) -> dict[str, str]:
    token = registered_user["access_token"]
    cv_id = await _create_cv(client, token, CV_TEXT)
    app_id = await _create_app(client, token, cv_id)
    return {"token": token, "cv_id": cv_id, "app_id": app_id}


async def _send(
    client: httpx.AsyncClient, s: dict[str, str], *chunks: Any, text: str = "Hi"
) -> tuple[list[tuple[str, Any]], _FakeGroq]:
    with _fake_groq(*chunks) as fake:
        resp = await client.post(
            f"{APPS}/{s['app_id']}/chat", json={"content": text}, headers=_h(s["token"])
        )
    assert resp.status_code == 200
    return _events(resp.text), fake


async def _propose(
    client: httpx.AsyncClient, s: dict[str, str], *edits: dict
) -> list[dict]:
    chunks = [_chunk("Here you go.")]
    for i, edit in enumerate(edits):
        chunks += _call_chunks(i, edit)
    events, _ = await _send(client, s, *chunks)
    return next(data for name, data in events if name == "cards")


async def _decide(
    client: httpx.AsyncClient, s: dict[str, str], card_id: str, action: str = "accept"
) -> httpx.Response:
    return await client.post(
        f"{APPS}/{s['app_id']}/chat/cards/{card_id}/{action}", headers=_h(s["token"])
    )


async def _cv_content(client: httpx.AsyncClient, s: dict[str, str]) -> dict:
    resp = await client.get(f"/api/v1/cvs/{s['cv_id']}", headers=_h(s["token"]))
    return resp.json()


# ---------------------------------------------------------------------------
# Tool-call validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "args",
    [
        {"op": "replace", "before": "x", "after": "y"},
        {"op": "replace", "before": "x", "after": ""},
        {"op": "remove", "before": "x"},
        {"op": "insert", "after": "y", "position": "start"},
        {"op": "insert", "after": "y", "position": "end"},
        {"op": "insert", "after": "y", "position": "after_line", "anchor": "x"},
    ],
)
def test_valid_calls_parse(args: dict) -> None:
    assert parse_propose_cv_edit("propose_cv_edit", json.dumps(args)) is not None


@pytest.mark.parametrize(
    "raw",
    [
        "{not json",
        "[]",
        json.dumps({"op": "rewrite", "before": "x", "after": "y"}),
        json.dumps({"op": "replace", "before": "", "after": "y"}),
        json.dumps({"op": "replace", "before": "x"}),
        json.dumps({"op": "replace", "before": "x", "after": "x"}),
        json.dumps({"op": "remove", "before": "   "}),
        json.dumps({"op": "insert", "after": "", "position": "end"}),
        json.dumps({"op": "insert", "after": "y"}),
        json.dumps({"op": "insert", "after": "y", "position": "middle"}),
        json.dumps({"op": "insert", "after": "y", "position": "after_line"}),
        json.dumps({"op": "replace", "before": "x" * 20_001, "after": "y"}),
    ],
)
def test_malformed_calls_do_not_parse(raw: str) -> None:
    assert parse_propose_cv_edit("propose_cv_edit", raw) is None


def test_other_tool_name_does_not_parse() -> None:
    raw = json.dumps({"op": "remove", "before": "x"})
    assert parse_propose_cv_edit("update_application", raw) is None


# ---------------------------------------------------------------------------
# Streaming: cards stored and sent before `done`
# ---------------------------------------------------------------------------


async def test_stream_stores_cards_and_emits_them_before_done(
    client: httpx.AsyncClient, setup: dict[str, str], db_session: AsyncSession
) -> None:
    events, fake = await _send(
        client,
        setup,
        _chunk("Two "),
        _chunk("edits."),
        *_call_chunks(0, {"op": "remove", "before": "- jQuery"}),
        *_call_chunks(
            1,
            {
                "op": "insert",
                "after": "- Docker",
                "position": "after_line",
                "anchor": "- Python",
            },
        ),
    )

    assert [name for name, _ in events] == ["token", "token", "cards", "done"]
    cards = events[2][1]
    assert [c["op"] for c in cards] == ["remove", "insert"]
    assert all(c["state"] == "pending" and c["cv_id"] == setup["cv_id"] for c in cards)
    assert cards[1]["position"] == "after_line"
    assert cards[1]["anchor_text"] == "- Python"
    assert fake.calls[0]["tools"][0]["function"]["name"] == "propose_cv_edit"

    stored = (await db_session.execute(select(ChatChangeCard))).scalars().all()
    message = await db_session.get(ChatMessage, stored[0].message_id)
    assert message is not None
    assert message.role == "assistant"
    assert message.content == "Two edits."
    assert cards[0]["message_id"] == message.id


async def test_history_returns_cards_per_assistant_message(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    cards = await _propose(client, setup, {"op": "remove", "before": "- jQuery"})

    resp = await client.get(
        f"{APPS}/{setup['app_id']}/chat", headers=_h(setup["token"])
    )

    user_msg, assistant_msg = resp.json()
    assert user_msg["cards"] == []
    assert [c["id"] for c in assistant_msg["cards"]] == [cards[0]["id"]]
    assert assistant_msg["cards"][0]["state"] == "pending"


async def test_reply_with_only_a_tool_call_still_saves_a_message(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    events, _ = await _send(
        client, setup, *_call_chunks(0, {"op": "remove", "before": "- jQuery"})
    )

    assert [name for name, _ in events] == ["cards", "done"]
    assert len(events[0][1]) == 1


async def test_no_tools_when_no_cv_linked(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    s = {"token": token, "app_id": await _create_app(client, token)}

    events, fake = await _send(client, s, _chunk("No CV is linked."))

    assert "tools" not in fake.calls[0]
    system = fake.calls[0]["messages"][0]["content"]
    assert "No CV is linked" in system
    assert "application panel" in system
    assert events[-2] == ("cards", [])
    assert events[-1][0] == "done"


async def test_no_tools_when_linked_cv_belongs_to_someone_else(
    client: httpx.AsyncClient,
    setup: dict[str, str],
    other_registered_user: dict,
    db_session: AsyncSession,
) -> None:
    from app.models.application import Application

    other_cv = await _create_cv(client, other_registered_user["access_token"], "x")
    await db_session.execute(
        update(Application)
        .where(Application.id == setup["app_id"])
        .values(cv_id=other_cv)
    )
    await db_session.commit()

    _, fake = await _send(client, setup, _chunk("ok"))

    assert "tools" not in fake.calls[0]


async def test_system_prompt_with_cv_has_edit_rules(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    _, fake = await _send(client, setup, _chunk("ok"))

    system = fake.calls[0]["messages"][0]["content"]
    assert "propose_cv_edit" in system
    assert "exactly" in system
    assert "cannot change the application" in system


async def test_malformed_call_becomes_inline_error_and_no_card(
    client: httpx.AsyncClient, setup: dict[str, str], db_session: AsyncSession
) -> None:
    events, _ = await _send(
        client,
        setup,
        _chunk("Sure."),
        *_call_chunks(0, '{"op": "replace", "before": "x"'),
        *_call_chunks(1, {"op": "remove", "before": "- jQuery"}),
    )

    tokens = "".join(data["text"] for name, data in events if name == "token")
    assert tokens == f"Sure.\n\n{MALFORMED_CALL_NOTE}"
    cards = next(data for name, data in events if name == "cards")
    assert len(cards) == 1
    message = (
        await db_session.execute(
            select(ChatMessage).where(ChatMessage.role == "assistant")
        )
    ).scalar_one()
    assert message.content == f"Sure.\n\n{MALFORMED_CALL_NOTE}"


async def test_history_sent_to_model_has_one_line_per_card(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    long_before = "Experienced SRE with 5 years of production ops."
    cards = await _propose(
        client,
        setup,
        {"op": "replace", "before": long_before, "after": "SRE, 5 years."},
        {"op": "remove", "before": "- jQuery"},
        {"op": "insert", "after": "- Docker", "position": "end"},
    )
    assert (await _decide(client, setup, cards[0]["id"])).status_code == 200
    assert (await _decide(client, setup, cards[1]["id"], "reject")).status_code == 200

    _, fake = await _send(client, setup, _chunk("ok"), text="Next")

    history = fake.calls[0]["messages"][1:]
    assert [m["role"] for m in history] == ["user", "assistant", "user"]
    assert history[1]["content"].splitlines() == [
        "Here you go.",
        f"[Card accepted: replace '{long_before}']",
        "[Card rejected: remove '- jQuery']",
        "[Card pending: insert '- Docker']",
    ]


async def test_history_line_cuts_long_quotes(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    await _propose(
        client, setup, {"op": "insert", "after": "y" * 100, "position": "end"}
    )

    _, fake = await _send(client, setup, _chunk("ok"), text="Next")

    line = fake.calls[0]["messages"][2]["content"].splitlines()[-1]
    assert line == f"[Card pending: insert '{'y' * 60}…']"


# ---------------------------------------------------------------------------
# Accept: each op
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("edit", "expected"),
    [
        (
            {
                "op": "replace",
                "before": "5 years of production ops",
                "after": "6 years",
            },
            CV_TEXT.replace("5 years of production ops", "6 years"),
        ),
        (
            {"op": "remove", "before": "- jQuery"},
            CV_TEXT.replace("- jQuery\n", ""),
        ),
        (
            {"op": "remove", "before": "- Kubernetes"},
            CV_TEXT.replace("\n- Kubernetes", ""),
        ),
        (
            {"op": "remove", "before": "production "},
            CV_TEXT.replace("production ", ""),
        ),
        (
            {"op": "insert", "after": "Open to relocation", "position": "start"},
            "Open to relocation\n" + CV_TEXT,
        ),
        (
            {"op": "insert", "after": "## Languages\nEnglish\n", "position": "end"},
            CV_TEXT + "\n## Languages\nEnglish",
        ),
        (
            {
                "op": "insert",
                "after": "- Docker",
                "position": "after_line",
                "anchor": "- Python",
            },
            CV_TEXT.replace("- Python\n", "- Python\n- Docker\n"),
        ),
        (
            {
                "op": "insert",
                "after": "- Docker",
                "position": "after_line",
                "anchor": "Kubernetes",
            },
            CV_TEXT + "\n- Docker",
        ),
        (
            # The anchor is part of a line: the text goes after the whole line.
            {
                "op": "insert",
                "after": "Available now.",
                "position": "after_line",
                "anchor": "Experienced SRE",
            },
            CV_TEXT.replace("ops.\n", "ops.\nAvailable now.\n"),
        ),
    ],
)
async def test_accept_applies_only_that_edit_and_bumps_version(
    client: httpx.AsyncClient, setup: dict[str, str], edit: dict, expected: str
) -> None:
    (card,) = await _propose(client, setup, edit)
    version = (await _cv_content(client, setup))["version"]

    resp = await _decide(client, setup, card["id"])

    assert resp.status_code == 200, resp.text
    assert resp.json()["state"] == "accepted"
    assert resp.json()["decided_at"] is not None
    cv = await _cv_content(client, setup)
    assert cv["content"] == expected
    assert cv["version"] == version + 1


async def test_two_cards_from_one_reply_accept_one_after_another(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    cards = await _propose(
        client,
        setup,
        {"op": "remove", "before": "- jQuery"},
        {
            "op": "insert",
            "after": "- Docker",
            "position": "after_line",
            "anchor": "- Python",
        },
    )

    assert (await _decide(client, setup, cards[1]["id"])).status_code == 200
    assert (await _decide(client, setup, cards[0]["id"])).status_code == 200

    content = (await _cv_content(client, setup))["content"]
    assert content.endswith("## Skills\n- Python\n- Docker\n- Kubernetes")


# ---------------------------------------------------------------------------
# Accept: failures
# ---------------------------------------------------------------------------


async def _card_state(db: AsyncSession, card_id: str) -> str:
    return (
        await db.execute(
            select(ChatChangeCard.state).where(ChatChangeCard.id == card_id)
        )
    ).scalar_one()


async def test_accept_missing_passage_marks_stale(
    client: httpx.AsyncClient, setup: dict[str, str], db_session: AsyncSession
) -> None:
    (card,) = await _propose(client, setup, {"op": "remove", "before": "- Rust"})

    resp = await _decide(client, setup, card["id"])

    assert resp.status_code == 409
    assert resp.json()["detail"] == "CARD_STALE"
    assert await _card_state(db_session, card["id"]) == "stale"
    assert (await _cv_content(client, setup))["content"] == CV_TEXT
    # Stale cards can still be rejected, and not accepted again.
    assert (await _decide(client, setup, card["id"])).json()["detail"] == "CARD_STALE"
    rejected = await _decide(client, setup, card["id"], "reject")
    assert rejected.status_code == 200
    assert rejected.json()["state"] == "rejected"


async def test_accept_after_user_edited_the_passage_is_stale(
    client: httpx.AsyncClient, setup: dict[str, str], db_session: AsyncSession
) -> None:
    (card,) = await _propose(client, setup, {"op": "remove", "before": "- jQuery"})
    cv = await _cv_content(client, setup)
    resp = await client.patch(
        f"/api/v1/cvs/{setup['cv_id']}",
        json={"content": CV_TEXT.replace("jQuery", "React"), "version": cv["version"]},
        headers=_h(setup["token"]),
    )
    assert resp.status_code == 200

    resp = await _decide(client, setup, card["id"])

    assert resp.json()["detail"] == "CARD_STALE"
    assert await _card_state(db_session, card["id"]) == "stale"


async def test_accept_missing_anchor_marks_stale(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    (card,) = await _propose(
        client,
        setup,
        {"op": "insert", "after": "x", "position": "after_line", "anchor": "- Go"},
    )

    resp = await _decide(client, setup, card["id"])

    assert resp.status_code == 409
    assert resp.json()["detail"] == "CARD_STALE"


async def test_accept_after_cv_deleted_is_stale(
    client: httpx.AsyncClient, setup: dict[str, str], db_session: AsyncSession
) -> None:
    (card,) = await _propose(client, setup, {"op": "remove", "before": "- jQuery"})

    resp = await client.delete(
        f"/api/v1/cvs/{setup['cv_id']}", headers=_h(setup["token"])
    )
    assert resp.status_code == 200
    # Deleting the CV already made the pending card stale.
    assert await _card_state(db_session, card["id"]) == "stale"

    resp = await _decide(client, setup, card["id"])

    assert resp.status_code == 409
    assert resp.json()["detail"] == "CARD_STALE"


async def test_accept_after_application_relinked_is_stale(
    client: httpx.AsyncClient, setup: dict[str, str], db_session: AsyncSession
) -> None:
    (card,) = await _propose(client, setup, {"op": "remove", "before": "- jQuery"})
    other_cv = await _create_cv(client, setup["token"], CV_TEXT)
    await _link(client, setup["token"], setup["app_id"], other_cv)

    resp = await _decide(client, setup, card["id"])

    assert resp.status_code == 409
    assert resp.json()["detail"] == "CARD_STALE"
    assert await _card_state(db_session, card["id"]) == "stale"
    assert (await _cv_content(client, setup))["content"] == CV_TEXT


async def test_accept_after_cv_unlinked_is_stale(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    (card,) = await _propose(client, setup, {"op": "remove", "before": "- jQuery"})
    await _link(client, setup["token"], setup["app_id"], None)

    resp = await _decide(client, setup, card["id"])

    assert resp.json()["detail"] == "CARD_STALE"


@pytest.mark.parametrize(
    "edit",
    [
        {"op": "remove", "before": "- "},
        {"op": "replace", "before": "##", "after": "#"},
        {"op": "insert", "after": "x", "position": "after_line", "anchor": "##"},
    ],
)
async def test_accept_passage_not_unique_stays_pending(
    client: httpx.AsyncClient,
    setup: dict[str, str],
    db_session: AsyncSession,
    edit: dict,
) -> None:
    (card,) = await _propose(client, setup, edit)

    resp = await _decide(client, setup, card["id"])

    assert resp.status_code == 409
    assert resp.json()["detail"] == "PASSAGE_NOT_UNIQUE"
    assert await _card_state(db_session, card["id"]) == "pending"
    assert (await _cv_content(client, setup))["content"] == CV_TEXT


async def test_accept_too_long_stays_pending(
    client: httpx.AsyncClient, setup: dict[str, str], db_session: AsyncSession
) -> None:
    after = "x" * (20_000 - len(CV_TEXT))
    (card,) = await _propose(
        client, setup, {"op": "insert", "after": after, "position": "end"}
    )

    resp = await _decide(client, setup, card["id"])

    assert resp.status_code == 422
    assert resp.json()["detail"] == "TOO_LONG"
    assert await _card_state(db_session, card["id"]) == "pending"
    assert (await _cv_content(client, setup))["content"] == CV_TEXT


async def test_accept_up_to_the_limit_succeeds(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    after = "x" * (20_000 - len(CV_TEXT) - 1)
    (card,) = await _propose(
        client, setup, {"op": "insert", "after": after, "position": "end"}
    )

    resp = await _decide(client, setup, card["id"])

    assert resp.status_code == 200
    assert len((await _cv_content(client, setup))["content"]) == 20_000


@pytest.mark.parametrize("first", ["accept", "reject"])
@pytest.mark.parametrize("second", ["accept", "reject"])
async def test_decided_card_cannot_be_decided_again(
    client: httpx.AsyncClient, setup: dict[str, str], first: str, second: str
) -> None:
    (card,) = await _propose(client, setup, {"op": "remove", "before": "- jQuery"})
    assert (await _decide(client, setup, card["id"], first)).status_code == 200
    content = (await _cv_content(client, setup))["content"]

    resp = await _decide(client, setup, card["id"], second)

    assert resp.status_code == 409
    assert resp.json()["detail"] == "CARD_DECIDED"
    assert (await _cv_content(client, setup))["content"] == content


async def test_reject_changes_nothing(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    (card,) = await _propose(client, setup, {"op": "remove", "before": "- jQuery"})
    before = await _cv_content(client, setup)

    resp = await _decide(client, setup, card["id"], "reject")

    assert resp.status_code == 200
    assert resp.json()["state"] == "rejected"
    assert resp.json()["decided_at"] is not None
    assert await _cv_content(client, setup) == before


async def test_accept_retries_once_when_the_version_moved(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    """A write landing between the read and the guarded update is retried."""
    (card,) = await _propose(client, setup, {"op": "remove", "before": "- jQuery"})
    real_write = cv_service.update_cv_content_if_version
    attempts: list[int] = []

    async def _racing_write(
        db: AsyncSession, user_id: str, cv_id: str, expected_version: int, **kw: Any
    ) -> Cv:
        attempts.append(expected_version)
        if len(attempts) == 1:
            # Another writer bumps the version (and edits elsewhere) first.
            await db.execute(
                update(Cv)
                .where(Cv.id == cv_id)
                .values(content=Cv.content + "\nExtra", version=Cv.version + 1)
            )
            await db.commit()
        return await real_write(db, user_id, cv_id, expected_version, **kw)

    with patch.object(cv_service, "update_cv_content_if_version", _racing_write):
        resp = await _decide(client, setup, card["id"])

    assert resp.status_code == 200, resp.text
    assert len(attempts) == 2
    cv = await _cv_content(client, setup)
    assert cv["content"] == CV_TEXT.replace("- jQuery\n", "") + "\nExtra"
    assert cv["version"] == attempts[1] + 1


async def test_accept_gives_up_after_losing_the_race_twice(
    client: httpx.AsyncClient, setup: dict[str, str], db_session: AsyncSession
) -> None:
    (card,) = await _propose(client, setup, {"op": "remove", "before": "- jQuery"})
    attempts: list[int] = []

    async def _always_lose(
        db: AsyncSession, user_id: str, cv_id: str, expected_version: int, **kw: Any
    ) -> Cv:
        attempts.append(expected_version)
        raise cv_service.CvVersionConflict(cv_id)

    with patch.object(cv_service, "update_cv_content_if_version", _always_lose):
        resp = await _decide(client, setup, card["id"])

    assert resp.status_code == 409
    assert resp.json()["detail"] == "CARD_STALE"
    assert len(attempts) == 2
    assert await _card_state(db_session, card["id"]) == "pending"
    assert (await _cv_content(client, setup))["content"] == CV_TEXT


async def test_accept_when_cv_vanishes_before_the_write_is_stale(
    client: httpx.AsyncClient, setup: dict[str, str], db_session: AsyncSession
) -> None:
    (card,) = await _propose(client, setup, {"op": "remove", "before": "- jQuery"})

    async def _gone(
        db: AsyncSession, user_id: str, cv_id: str, expected_version: int, **kw: Any
    ) -> Cv:
        raise cv_service.CvNotFoundError(cv_id)

    with patch.object(cv_service, "update_cv_content_if_version", _gone):
        resp = await _decide(client, setup, card["id"])

    assert resp.status_code == 409
    assert resp.json()["detail"] == "CARD_STALE"
    assert await _card_state(db_session, card["id"]) == "stale"


# ---------------------------------------------------------------------------
# Owner scoping and cleanup
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("action", ["accept", "reject"])
async def test_other_user_gets_404(
    client: httpx.AsyncClient,
    setup: dict[str, str],
    other_registered_user: dict,
    action: str,
) -> None:
    (card,) = await _propose(client, setup, {"op": "remove", "before": "- jQuery"})
    other = other_registered_user["access_token"]
    other_app = await _create_app(client, other)

    for app_id in (setup["app_id"], other_app):
        resp = await client.post(
            f"{APPS}/{app_id}/chat/cards/{card['id']}/{action}", headers=_h(other)
        )
        assert resp.status_code == 404

    assert (await _cv_content(client, setup))["content"] == CV_TEXT


async def test_card_of_another_application_is_404(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    (card,) = await _propose(client, setup, {"op": "remove", "before": "- jQuery"})
    second_app = await _create_app(client, setup["token"], setup["cv_id"])

    resp = await client.post(
        f"{APPS}/{second_app}/chat/cards/{card['id']}/accept",
        headers=_h(setup["token"]),
    )

    assert resp.status_code == 404


async def test_unknown_card_is_404(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    assert (await _decide(client, setup, "nope")).status_code == 404


async def _card_count(db: AsyncSession) -> int:
    return (await db.execute(select(func.count(ChatChangeCard.id)))).scalar_one()


async def test_clearing_the_chat_removes_its_cards(
    client: httpx.AsyncClient, setup: dict[str, str], db_session: AsyncSession
) -> None:
    await _propose(client, setup, {"op": "remove", "before": "- jQuery"})
    assert await _card_count(db_session) == 1

    resp = await client.delete(
        f"{APPS}/{setup['app_id']}/chat", headers=_h(setup["token"])
    )

    assert resp.status_code == 200
    assert await _card_count(db_session) == 0


async def test_deleting_the_application_removes_cards_and_messages(
    client: httpx.AsyncClient, setup: dict[str, str], db_session: AsyncSession
) -> None:
    await _propose(client, setup, {"op": "remove", "before": "- jQuery"})
    keep_app = await _create_app(client, setup["token"], setup["cv_id"])
    await _propose(
        client, {**setup, "app_id": keep_app}, {"op": "remove", "before": "- jQuery"}
    )

    resp = await client.delete(f"{APPS}/{setup['app_id']}", headers=_h(setup["token"]))

    assert resp.status_code in (200, 204)
    assert await _card_count(db_session) == 1
    messages = (await db_session.execute(select(ChatMessage))).scalars().all()
    assert {m.application_id for m in messages} == {keep_app}


async def test_deleting_a_cv_leaves_decided_cards_alone(
    client: httpx.AsyncClient, setup: dict[str, str], db_session: AsyncSession
) -> None:
    cards = await _propose(
        client,
        setup,
        {"op": "remove", "before": "- jQuery"},
        {"op": "remove", "before": "- Python"},
    )
    await _decide(client, setup, cards[0]["id"], "reject")

    await client.delete(f"/api/v1/cvs/{setup['cv_id']}", headers=_h(setup["token"]))

    assert await _card_state(db_session, cards[0]["id"]) == "rejected"
    assert await _card_state(db_session, cards[1]["id"]) == "stale"


# ---------------------------------------------------------------------------
# Groq errors mid-stream
# ---------------------------------------------------------------------------


class _FailingGroq(_FakeGroq):
    """Streams some chunks, then raises a Groq error mid-stream."""

    def __init__(self, chunks: list[Any], body: object) -> None:
        super().__init__(chunks)
        self.body = body

    async def _create(self, **kwargs: Any) -> AsyncIterator[Any]:
        self.calls.append(kwargs)

        async def _gen() -> AsyncIterator[Any]:
            for chunk in self.chunks:
                yield chunk
            raise groq.APIError(
                "boom", httpx.Request("POST", "http://groq.test"), body=self.body
            )

        return _gen()


async def _send_failing(
    client: httpx.AsyncClient, s: dict[str, str], fake: _FailingGroq
) -> list[tuple[str, Any]]:
    with patch("app.services.groq_client._get_client", return_value=fake):
        resp = await client.post(
            f"{APPS}/{s['app_id']}/chat",
            json={"content": "Edit"},
            headers=_h(s["token"]),
        )
    return _events(resp.text)


async def test_groq_tool_use_failed_becomes_inline_error(
    client: httpx.AsyncClient, setup: dict[str, str], db_session: AsyncSession
) -> None:
    fake = _FailingGroq([_chunk("Let me fix that.")], {"code": "tool_use_failed"})

    events = await _send_failing(client, setup, fake)

    assert [name for name, _ in events] == ["token", "token", "cards", "done"]
    assert events[1][1]["text"] == f"\n\n{MALFORMED_CALL_NOTE}"
    assert events[2][1] == []
    assert await _card_count(db_session) == 0


async def test_other_groq_errors_still_end_the_stream_with_error(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    fake = _FailingGroq([_chunk("Partial")], {"code": "internal_error"})

    events = await _send_failing(client, setup, fake)

    assert [name for name, _ in events] == ["token", "error"]
