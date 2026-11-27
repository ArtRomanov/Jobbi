"""Whole-CV change card, `op: replace_all` (backlog #34). Fake Groq, no tokens.

The model proposes the whole new CV in one call; the user sees one card and
accepts or rejects it. Accept replaces the CV text only if the CV is still the
one the model saw; other pending cards on that CV then go stale.
"""

import json
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_change_card import ChatChangeCard
from app.services.chat_card_service import card_history_line
from app.services.chat_service import parse_retry_nudge, retry_nudge
from app.services.chat_tools import (
    MALFORMED_CALL_NOTE,
    PROPOSE_CV_EDIT_TOOL,
    CallRejection,
    check_propose_cv_edit,
)
from app.services.groq_client import build_system_prompt
from tests.test_chat_cards import (
    APPS,
    CV_TEXT,
    _call_chunks,
    _chunk,
    _create_app,
    _create_cv,
    _cv_content,
    _decide,
    _h,
    _propose,
    _send,
)
from tests.test_chat_follows_requests import _send_seq, _SequenceGroq

NEW_CV = (
    "# Jane Doe\n"
    "jane@example.com\n"
    "\n"
    "## Summary\n"
    "SRE, 5 years of production ops.\n"
    "\n"
    "## Skills\n"
    "- Python\n"
    "- Kubernetes"
)
_WHOLE = {"op": "replace_all", "after": NEW_CV}


@pytest.fixture
async def setup(client: httpx.AsyncClient, registered_user: dict) -> dict[str, str]:
    token = registered_user["access_token"]
    cv_id = await _create_cv(client, token, CV_TEXT)
    app_id = await _create_app(client, token, cv_id)
    return {"token": token, "cv_id": cv_id, "app_id": app_id}


def _cards(events: list[tuple[str, Any]]) -> list[dict]:
    return next(data for name, data in events if name == "cards")


def _tokens(events: list[tuple[str, Any]]) -> str:
    return "".join(data["text"] for name, data in events if name == "token")


# ---------------------------------------------------------------------------
# Tool-call validation
# ---------------------------------------------------------------------------


def test_replace_all_parses_with_the_whole_new_cv() -> None:
    edit = check_propose_cv_edit("propose_cv_edit", json.dumps(_WHOLE))

    assert not isinstance(edit, CallRejection)
    assert edit.op == "replace_all"
    assert edit.after_text == NEW_CV
    assert edit.before_text == ""
    assert edit.position is None and edit.anchor_text is None


@pytest.mark.parametrize("op", ["replace_all", "Replace-All", "replace all"])
def test_replace_all_op_spellings(op: str) -> None:
    edit = check_propose_cv_edit(
        "propose_cv_edit", json.dumps({"op": op, "after": NEW_CV})
    )
    assert not isinstance(edit, CallRejection)
    assert edit.op == "replace_all"


@pytest.mark.parametrize(
    "args",
    [
        {"op": "replace_all"},
        {"op": "replace_all", "after": "   "},
        # Not in the CV Markdown shape: no heading at all.
        {"op": "replace_all", "after": "Jane Doe\nSRE with 5 years."},
    ],
)
def test_replace_all_without_a_markdown_cv_is_rejected(args: dict) -> None:
    result = check_propose_cv_edit("propose_cv_edit", json.dumps(args))
    assert isinstance(result, CallRejection)
    assert result.reason == "invalid_args"


def test_truncated_replace_all_is_rejected_not_cut() -> None:
    raw = json.dumps(_WHOLE)
    result = check_propose_cv_edit("propose_cv_edit", raw[: len(raw) // 2])
    assert isinstance(result, CallRejection)
    assert result.reason == "bad_json"


def test_tool_schema_and_nudges_name_replace_all() -> None:
    op_help = PROPOSE_CV_EDIT_TOOL["function"]["parameters"]["properties"]["op"]
    assert "replace_all" in op_help["description"]
    assert "replace_all" in retry_nudge("x")
    assert "replace_all" in parse_retry_nudge([])


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------


class _App:
    company_name = "Acme"
    role_title = "SRE"
    job_url = None
    status = "researching"
    notes = None


class _Cv:
    content = CV_TEXT


def test_prompt_steers_whole_draft_requests_to_replace_all() -> None:
    prompt = build_system_prompt(_App(), _Cv())  # type: ignore[arg-type]

    assert 'op "replace_all"' in prompt
    assert "whole draft" in prompt
    assert "fit N pages" in prompt
    # Written in the CV Markdown shape even when the CV is plain text.
    assert "even if the CV block is plain text" in prompt
    # Still never the edited CV as reply text.
    assert "Never write the edited CV out in your reply" in prompt


# ---------------------------------------------------------------------------
# Chat turn
# ---------------------------------------------------------------------------


async def test_replace_all_becomes_one_card_holding_both_versions(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    events, _ = await _send(
        client,
        setup,
        _chunk("Moved the whole draft."),
        *_call_chunks(0, _WHOLE),
        text="переносим целиком",
    )

    (card,) = _cards(events)
    assert card["op"] == "replace_all"
    assert card["before_text"] == CV_TEXT  # the CV the model saw
    assert card["after_text"] == NEW_CV
    assert card["warning"] is None
    assert card["state"] == "pending"


async def test_replace_all_drops_other_edits_of_the_same_reply(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    events, _ = await _send(
        client,
        setup,
        _chunk("Done."),
        *_call_chunks(0, {"op": "remove", "before": "- jQuery"}),
        *_call_chunks(1, _WHOLE),
    )

    assert [c["op"] for c in _cards(events)] == ["replace_all"]
    assert MALFORMED_CALL_NOTE in _tokens(events)


async def test_truncated_replace_all_makes_no_card(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    raw = json.dumps(_WHOLE)
    cut = [_chunk("Here it is."), *_call_chunks(0, raw[: len(raw) // 2])]
    fake = _SequenceGroq(cut, cut)

    events = await _send_seq(client, setup, fake, "apply the whole draft")

    assert len(fake.calls) == 2  # one parse retry, never more
    assert _cards(events) == []
    assert MALFORMED_CALL_NOTE in _tokens(events)
    assert (await _cv_content(client, setup))["content"] == CV_TEXT


async def test_replace_all_with_unsupported_names_is_left_out(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    invented = NEW_CV + "\n- TanStack Query"
    events, _ = await _send(
        client,
        setup,
        _chunk("Moved it."),
        *_call_chunks(0, {"op": "replace_all", "after": invented}),
    )

    assert _cards(events) == []
    assert "TanStack" in _tokens(events)


async def test_replace_all_dropping_a_section_gets_a_warning(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    no_skills = "# Jane Doe\njane@example.com\n\n## Summary\nSRE."
    broken = [
        _chunk("Shorter."),
        *_call_chunks(0, {"op": "replace_all", "after": no_skills}),
    ]
    fake = _SequenceGroq(broken, broken)

    events = await _send_seq(client, setup, fake, "fit it into 2 pages")

    assert len(fake.calls) == 2  # one structure repair
    (card,) = _cards(events)
    assert card["op"] == "replace_all"
    assert card["warning"] == "This change removes the Skills section."


async def test_plain_text_cv_gaining_markdown_breaks_nothing(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    plain = (
        "Jane Doe\njane@example.com\nSummary\nSRE, 5 years of production ops.\n"
        "Skills: Python, Kubernetes"
    )
    cv_id = await _create_cv(client, token, plain)
    app_id = await _create_app(client, token, cv_id)
    s = {"token": token, "cv_id": cv_id, "app_id": app_id}

    events, fake = await _send(
        client, s, _chunk("Moved."), *_call_chunks(0, _WHOLE), text="переносим"
    )

    assert len(fake.calls) == 1
    (card,) = _cards(events)
    assert card["warning"] is None


# ---------------------------------------------------------------------------
# Accept / reject
# ---------------------------------------------------------------------------


async def test_accept_replaces_the_whole_cv(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    (card,) = await _propose(client, setup, _WHOLE)
    version = (await _cv_content(client, setup))["version"]

    resp = await _decide(client, setup, card["id"])

    assert resp.status_code == 200
    assert resp.json()["state"] == "accepted"
    cv = await _cv_content(client, setup)
    assert cv["content"] == NEW_CV
    assert cv["version"] == version + 1


async def test_accept_after_the_cv_changed_is_stale(
    client: httpx.AsyncClient, setup: dict[str, str], db_session: AsyncSession
) -> None:
    (card,) = await _propose(client, setup, _WHOLE)
    cv = await _cv_content(client, setup)
    edited = await client.patch(
        f"/api/v1/cvs/{setup['cv_id']}",
        json={"content": CV_TEXT + "\n- Go", "version": cv["version"]},
        headers=_h(setup["token"]),
    )
    assert edited.status_code == 200, edited.text

    resp = await _decide(client, setup, card["id"])

    assert resp.status_code == 409
    assert resp.json()["detail"] == "CARD_STALE"
    assert (await _cv_content(client, setup))["content"] == CV_TEXT + "\n- Go"


async def test_accept_on_a_crlf_cv_still_applies(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    cv_id = await _create_cv(client, token, CV_TEXT.replace("\n", "\r\n"))
    app_id = await _create_app(client, token, cv_id)
    s = {"token": token, "cv_id": cv_id, "app_id": app_id}
    (card,) = await _propose(client, s, _WHOLE)

    resp = await _decide(client, s, card["id"])

    assert resp.status_code == 200
    assert (await _cv_content(client, s))["content"] == NEW_CV


async def test_accepting_replace_all_makes_other_pending_cards_stale(
    client: httpx.AsyncClient, setup: dict[str, str], db_session: AsyncSession
) -> None:
    (card,) = await _propose(client, setup, _WHOLE)
    # A pending card on the same CV, from the same reply (stored by hand: the
    # chat never pairs replace_all with other edits).
    other = ChatChangeCard(
        application_id=setup["app_id"],
        message_id=card["message_id"],
        cv_id=setup["cv_id"],
        op="remove",
        before_text="- Python",
        after_text="",
        state="pending",
    )
    db_session.add(other)
    await db_session.commit()
    other_id = other.id

    assert (await _decide(client, setup, card["id"])).status_code == 200

    db_session.expire_all()
    state = await db_session.scalar(
        select(ChatChangeCard.state).where(ChatChangeCard.id == other_id)
    )
    assert state == "stale"


async def test_a_pending_replace_all_goes_stale_after_another_card_is_accepted(
    client: httpx.AsyncClient, setup: dict[str, str], db_session: AsyncSession
) -> None:
    (whole,) = await _propose(client, setup, _WHOLE)
    other = ChatChangeCard(
        application_id=setup["app_id"],
        message_id=whole["message_id"],
        cv_id=setup["cv_id"],
        op="remove",
        before_text="- jQuery",
        after_text="",
        state="pending",
    )
    db_session.add(other)
    await db_session.commit()

    assert (await _decide(client, setup, other.id)).status_code == 200
    resp = await _decide(client, setup, whole["id"])

    assert resp.status_code == 409
    assert resp.json()["detail"] == "CARD_STALE"


async def test_reject_leaves_the_cv_alone(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    (card,) = await _propose(client, setup, _WHOLE)

    resp = await _decide(client, setup, card["id"], "reject")

    assert resp.status_code == 200
    assert (await _cv_content(client, setup))["content"] == CV_TEXT


# ---------------------------------------------------------------------------
# History note
# ---------------------------------------------------------------------------


def test_history_line_does_not_quote_the_whole_cv() -> None:
    card = ChatChangeCard(
        op="replace_all",
        before_text=CV_TEXT,
        after_text=NEW_CV,
        state="accepted",
    )
    line = card_history_line(card, quote_removed=True)

    assert line.startswith("- accepted: replace_all")
    assert "Earlier text" not in line
    assert "jQuery" not in line


async def test_history_after_accept_tells_the_model(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    (card,) = await _propose(client, setup, _WHOLE)
    await _decide(client, setup, card["id"])

    _, fake = await _send(client, setup, _chunk("ok"), text="thanks")

    notes = [
        m["content"]
        for m in fake.calls[0]["messages"]
        if m["role"] == "system" and "CARD EDITS" in m["content"]
    ]
    assert any("accepted: replace_all" in n for n in notes)


async def test_history_endpoint_returns_the_card(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    await _propose(client, setup, _WHOLE)
    resp = await client.get(
        f"{APPS}/{setup['app_id']}/chat", headers=_h(setup["token"])
    )
    assert [c["op"] for c in resp.json()[-1]["cards"]] == ["replace_all"]
