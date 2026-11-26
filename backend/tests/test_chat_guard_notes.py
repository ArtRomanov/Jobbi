"""The fact guard's note follows the chat language and marks the left-out item."""

import httpx
import pytest

from app.services.chat_guard_notes import (
    NOT_PROPOSED_MARKER,
    UNSUPPORTED_NAMES_NOTE,
    mark_left_out_items,
    reply_language,
    unsupported_names_note,
)
from tests.test_chat_cards import (
    APPS,
    CV_TEXT,
    _call_chunks,
    _chunk,
    _create_app,
    _create_cv,
    _h,
    _send,
)

RU = NOT_PROPOSED_MARKER["ru"]
EN = NOT_PROPOSED_MARKER["en"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Адаптируй CV под вакансию", "ru"),
        ("Add REST API, пожалуйста", "ru"),
        ("Tailor my CV", "en"),
        ("", "en"),
    ],
)
def test_reply_language_follows_cyrillic(text: str, expected: str) -> None:
    assert reply_language(text) == expected


def test_note_in_russian() -> None:
    assert unsupported_names_note(["REST API"], "ru") == (
        "Пункт про REST API не предложил: в вашем CV нет REST API. "
        "Если опыт есть — напишите, добавлю."
    )


def test_marks_the_numbered_item_with_the_name() -> None:
    reply = (
        "Предлагаю:\n"
        "1. Перенести REST API и WebSocket в строку Frontend.\n"
        "2. Сократить профиль.\n"
        "3. Убрать jQuery."
    )

    marked = mark_left_out_items(reply, [["REST API"]], "ru")

    assert marked == reply.replace("Frontend.", f"Frontend {RU}.")


def test_item_with_continuation_lines_gets_the_marker_on_its_first_line() -> None:
    reply = (
        "1. **Skills line:**\n"
        "   After: React, REST API\n"
        "\n"
        "2. **Profile:**\n"
        "   After: shorter"
    )

    marked = mark_left_out_items(reply, [["REST API"]], "en")

    # Markdown closers end the line: the marker simply goes after them.
    assert marked.splitlines()[0] == f"1. **Skills line:** {EN}"
    assert marked.count(EN) == 1


def test_bullets_work_too() -> None:
    reply = "- Add TanStack Query\n- Drop jQuery"

    assert mark_left_out_items(reply, [["TanStack"]], "en") == (
        f"- Add TanStack Query {EN}\n- Drop jQuery"
    )


def test_without_a_list_the_sentence_is_marked() -> None:
    reply = "I shortened the profile. I also added Argo CD to your skills. Done!"

    assert mark_left_out_items(reply, [["Argo CD"]], "en") == (
        f"I shortened the profile. I also added Argo CD to your skills {EN}. Done!"
    )


@pytest.mark.parametrize(
    "reply",
    [
        "1. Add REST API\n2. Mention REST API in the profile",  # two items
        "Shortened the profile.",  # no mention at all
    ],
)
def test_no_single_match_leaves_the_text_alone(reply: str) -> None:
    assert mark_left_out_items(reply, [["REST API"]], "en") == reply


def test_two_left_out_edits_on_one_item_mark_it_once() -> None:
    reply = "1. Add REST API and GraphQL\n2. Drop jQuery"

    marked = mark_left_out_items(reply, [["REST API"], ["GraphQL"]], "en")

    assert marked == f"1. Add REST API and GraphQL {EN}\n2. Drop jQuery"


# ---------------------------------------------------------------------------
# Through the chat stream
# ---------------------------------------------------------------------------


@pytest.fixture
async def setup(client: httpx.AsyncClient, registered_user: dict) -> dict[str, str]:
    token = registered_user["access_token"]
    cv_id = await _create_cv(client, token, CV_TEXT)
    app_id = await _create_app(client, token, cv_id)
    return {"token": token, "cv_id": cv_id, "app_id": app_id}


_RU_REPLY = (
    "Предлагаю три правки:\n"
    "1. Перенести REST API и WebSocket в строку Frontend.\n"
    "2. Убрать jQuery."
)
_ADD_REST = {"op": "replace", "before": "- Python", "after": "- Python, REST API"}
_DROP_JQUERY = {"op": "remove", "before": "- jQuery"}


async def _set_job_post(client: httpx.AsyncClient, s: dict[str, str]) -> None:
    resp = await client.patch(
        f"{APPS}/{s['app_id']}",
        json={"notes": "Frontend. Must have: REST API, WebSocket."},
        headers=_h(s["token"]),
    )
    assert resp.status_code == 200, resp.text


async def _history(client: httpx.AsyncClient, s: dict[str, str]) -> list[dict]:
    resp = await client.get(f"{APPS}/{s['app_id']}/chat", headers=_h(s["token"]))
    return resp.json()


async def test_russian_chat_gets_a_russian_note_and_a_marked_item(
    client: httpx.AsyncClient,
    setup: dict[str, str],
) -> None:
    await _set_job_post(client, setup)

    events, _ = await _send(
        client,
        setup,
        _chunk(_RU_REPLY),
        *_call_chunks(0, _ADD_REST),
        *_call_chunks(1, _DROP_JQUERY),
        text="Адаптируй CV под вакансию",
    )

    names = [name for name, _ in events]
    # The text already streamed is replaced once, before the cards.
    assert names == ["token", "reply", "cards", "done"]
    reply = events[1][1]["text"]
    expected = (
        _RU_REPLY.replace("Frontend.", f"Frontend {RU}.")
        + "\n\n"
        + UNSUPPORTED_NAMES_NOTE["ru"].format(names="REST API")
    )
    assert reply == expected
    assert [c["op"] for c in events[2][1]] == ["remove"]
    # What the user saw is what was stored.
    assert (await _history(client, setup))[-1]["content"] == expected


async def test_unmatched_item_keeps_text_and_streams_only_the_note(
    client: httpx.AsyncClient,
    setup: dict[str, str],
) -> None:
    await _set_job_post(client, setup)

    events, _ = await _send(
        client,
        setup,
        _chunk("Here are the edits."),
        *_call_chunks(0, _ADD_REST),
        text="Tailor my CV",
    )

    assert [name for name, _ in events] == ["token", "token", "cards", "done"]
    note = UNSUPPORTED_NAMES_NOTE["en"].format(names="REST API")
    assert events[1][1]["text"] == "\n\n" + note
    content = (await _history(client, setup))[-1]["content"]
    assert content == "Here are the edits.\n\n" + note
