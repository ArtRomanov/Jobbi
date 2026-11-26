"""Quotes that differ from the CV only in whitespace still find their passage.

Hard-wrapped CVs (PDF or plain-text uploads) break a paragraph with single
line breaks; the model quotes it with spaces instead. The card must still be
saved with the exact CV text and Accept must apply it. A quote that is not in
the CV even so is no card: the reply gets a "could not prepare" note.
"""

import time

import httpx
import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_change_card import ChatChangeCard
from app.services.chat_card_service import (
    _PassageMissing,
    _PassageNotUnique,
    apply_card_edit,
    apply_card_edit_rebased,
    place_edit,
)
from app.services.chat_tools import PASSAGE_NOT_FOUND_NOTE, CvEdit
from tests.test_chat_cards import (
    _call_chunks,
    _chunk,
    _create_app,
    _create_cv,
    _cv_content,
    _decide,
    _send,
)

# A PROFILE paragraph hard-wrapped the way PDF text extraction leaves it.
WRAPPED = (
    "Frontend developer with 6 years of experience building React apps.\n"
    "Led the migration of a large codebase to TypeScript and mentored\n"
    "three junior engineers."
)
JOINED = " ".join(WRAPPED.split("\n"))
CV = f"# Jane Doe\n\n## Profile\n{WRAPPED}\n\n## Skills\n- React\n- jQuery\n"
NEW_PROFILE = "Senior frontend engineer, 6 years with React and TypeScript."


def _edit(**kwargs: object) -> CvEdit:
    fields: dict = {
        "op": "replace",
        "before_text": "",
        "after_text": "",
        "position": None,
        "anchor_text": None,
    }
    fields.update(kwargs)
    return CvEdit(**fields)


def _apply(content: str, edit: CvEdit) -> str:
    return apply_card_edit(
        content,
        op=edit.op,
        before_text=edit.before_text,
        after_text=edit.after_text,
        position=edit.position,
        anchor_text=edit.anchor_text,
    )


# ---------------------------------------------------------------------------
# Pure: locating and placing
# ---------------------------------------------------------------------------


def test_replace_with_space_joined_quote_applies_to_the_wrapped_paragraph() -> None:
    edit = _edit(before_text=JOINED, after_text=NEW_PROFILE)

    assert _apply(CV, edit) == CV.replace(WRAPPED, NEW_PROFILE)


def test_place_edit_rewrites_the_quote_to_the_exact_cv_text() -> None:
    placed = place_edit(CV, _edit(before_text=JOINED, after_text=NEW_PROFILE))

    assert placed is not None
    assert placed.before_text == WRAPPED
    assert placed.after_text == NEW_PROFILE  # kept as the model wrote it


def test_place_edit_keeps_an_exact_quote_as_it_is() -> None:
    edit = _edit(op="remove", before_text="- jQuery")

    assert place_edit(CV, edit) == edit


def test_remove_with_space_joined_quote() -> None:
    placed = place_edit(CV, _edit(op="remove", before_text=JOINED))

    assert placed is not None and placed.before_text == WRAPPED
    assert _apply(CV, placed) == CV.replace(f"{WRAPPED}\n", "")


def test_insert_anchor_quoted_with_spaces_goes_after_the_last_wrapped_line() -> None:
    anchor = "building React apps. Led the migration"
    edit = _edit(
        op="insert", after_text="Open to relocation.", position="after_line",
        anchor_text=anchor,
    )  # fmt: skip

    placed = place_edit(CV, edit)

    assert placed is not None
    assert placed.anchor_text == "building React apps.\nLed the migration"
    expected = CV.replace("mentored\n", "mentored\nOpen to relocation.\n")
    assert _apply(CV, placed) == expected
    assert _apply(CV, edit) == expected  # Accept without the rewrite, too


@pytest.mark.parametrize(
    ("cv_paragraph", "quote"),
    [
        # CRLF hard wraps, quoted with spaces.
        ("Built React apps.\r\nLed a TypeScript migration.", None),
        # Double spaces in the CV, single in the quote.
        ("Built React apps.  Led a TypeScript migration.", None),
        # A tab in the CV.
        ("Built React apps.\tLed a TypeScript migration.", None),
        # The quote has the extra whitespace (two spaces and a line break).
        ("Built React apps. Led a TypeScript migration.", "Built React apps.  \nLed"),
    ],
)
def test_whitespace_variants_are_matched(cv_paragraph: str, quote: str | None) -> None:
    cv = f"# Jane\n\n## Profile\n{cv_paragraph}\n\n## Skills\n- React\n"
    quote = quote or "Built React apps. Led a TypeScript migration."
    exact = cv.replace("\r\n", "\n")
    lf_paragraph = cv_paragraph.replace("\r\n", "\n")

    placed = place_edit(cv, _edit(before_text=quote, after_text="Built things."))

    assert placed is not None
    assert placed.before_text in exact
    assert placed.before_text.startswith("Built React apps.")
    result = _apply(cv, placed)
    assert result == exact.replace(placed.before_text, "Built things.")
    assert _apply(cv, _edit(before_text=quote, after_text="Built things.")) == result
    assert lf_paragraph.startswith(placed.before_text)


def test_ambiguous_whitespace_match_is_not_re_aimed() -> None:
    cv = "# Jane\n\n## A\nShipped the\nnew app.\n\n## B\nShipped the  new app.\n"
    edit = _edit(before_text="Shipped the new app.", after_text="Shipped it.")

    with pytest.raises(_PassageMissing):
        _apply(cv, edit)
    assert place_edit(cv, edit) is None


def test_exact_repeat_is_still_not_unique() -> None:
    edit = _edit(op="remove", before_text="- ")

    with pytest.raises(_PassageNotUnique):
        _apply(CV, edit)
    # Kept as today: Accept answers PASSAGE_NOT_UNIQUE and the card stays.
    assert place_edit(CV, edit) == edit


def test_quote_not_in_the_cv_cannot_be_placed() -> None:
    edit = _edit(before_text="Backend developer with Go.", after_text="x")

    assert place_edit(CV, edit) is None


def test_missing_anchor_cannot_be_placed() -> None:
    edit = _edit(op="insert", after_text="x", position="after_line", anchor_text="- Go")

    assert place_edit(CV, edit) is None


def test_whitespace_alone_does_not_match_inside_a_word() -> None:
    """Only whitespace runs are equal; other characters must still match."""
    edit = _edit(before_text="Frontend  developer with 7 years", after_text="x")

    assert place_edit(CV, edit) is None


def test_rebased_accept_uses_the_same_locating() -> None:
    """The structure dry-run and Accept both go through `apply_card_edit_rebased`."""
    result = apply_card_edit_rebased(
        CV,
        op="replace",
        before_text=JOINED,
        after_text=NEW_PROFILE,
        position=None,
        anchor_text=None,
    )

    assert result == CV.replace(WRAPPED, NEW_PROFILE)


def test_long_cv_and_long_quote_locate_fast() -> None:
    words = [f"word{i}" for i in range(2_500)]
    # ~20k chars, hard-wrapped every 8 words, with mixed whitespace.
    lines = [" \t ".join(words[i : i + 8]) for i in range(0, len(words), 8)]
    cv = "\n".join(lines)[:20_000]
    quote = " ".join(cv.split())[2_000:19_000].split(" ", 1)[1].rsplit(" ", 1)[0]
    missing = quote + " nowhere"
    spaces = "x" + " " * 19_000 + "y"

    start = time.perf_counter()
    placed = place_edit(cv, _edit(op="remove", before_text=quote))
    assert place_edit(cv, _edit(op="remove", before_text=missing)) is None
    assert place_edit(spaces, _edit(op="remove", before_text="x  \n y")) is not None
    no_z = "x" + " " * 5_000 + "z"
    assert place_edit(spaces, _edit(op="remove", before_text=no_z)) is None
    assert time.perf_counter() - start < 0.5

    assert placed is not None
    assert " ".join(placed.before_text.split()) == quote


# ---------------------------------------------------------------------------
# Through the chat and Accept
# ---------------------------------------------------------------------------


@pytest.fixture
async def setup(client: httpx.AsyncClient, registered_user: dict) -> dict[str, str]:
    token = registered_user["access_token"]
    cv_id = await _create_cv(client, token, CV)
    app_id = await _create_app(client, token, cv_id)
    return {"token": token, "cv_id": cv_id, "app_id": app_id}


async def _propose_events(
    client: httpx.AsyncClient, s: dict[str, str], *edits: dict, text: str = "Hi"
) -> list:
    chunks = [_chunk("Here you go.")]
    for i, edit in enumerate(edits):
        chunks += _call_chunks(i, edit)
    events, _ = await _send(client, s, *chunks, text=text)
    return events


def _cards(events: list) -> list[dict]:
    return next(data for name, data in events if name == "cards")


def _tokens(events: list) -> str:
    return "".join(data["text"] for name, data in events if name == "token")


async def test_space_joined_quote_is_stored_exact_and_accept_succeeds(
    client: httpx.AsyncClient, setup: dict[str, str], db_session: AsyncSession
) -> None:
    events = await _propose_events(
        client, setup, {"op": "replace", "before": JOINED, "after": NEW_PROFILE}
    )
    (card,) = _cards(events)
    stored = await db_session.scalar(
        select(ChatChangeCard.before_text).where(ChatChangeCard.id == card["id"])
    )
    assert stored == WRAPPED
    assert card["before_text"] == WRAPPED

    resp = await _decide(client, setup, card["id"])

    assert resp.status_code == 200, resp.text
    assert (await _cv_content(client, setup))["content"] == CV.replace(
        WRAPPED, NEW_PROFILE
    )


async def test_space_joined_anchor_is_stored_exact_and_accept_succeeds(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    events = await _propose_events(
        client,
        setup,
        {
            "op": "insert",
            "after": "Open to relocation.",
            "position": "after_line",
            "anchor": "to TypeScript and mentored three junior engineers.",
        },
    )
    (card,) = _cards(events)
    assert card["anchor_text"] == "to TypeScript and mentored\nthree junior engineers."

    resp = await _decide(client, setup, card["id"])

    assert resp.status_code == 200, resp.text
    assert (await _cv_content(client, setup))["content"] == CV.replace(
        "junior engineers.\n", "junior engineers.\nOpen to relocation.\n"
    )


@pytest.mark.parametrize(
    ("text", "note"),
    [
        ("Rewrite my profile", PASSAGE_NOT_FOUND_NOTE["en"]),
        ("Перепиши профиль", PASSAGE_NOT_FOUND_NOTE["ru"]),
    ],
)
async def test_quote_not_in_cv_is_no_card_and_gets_a_note(
    client: httpx.AsyncClient,
    setup: dict[str, str],
    db_session: AsyncSession,
    text: str,
    note: str,
) -> None:
    events = await _propose_events(
        client,
        setup,
        {"op": "replace", "before": "Backend developer with Go.", "after": "x"},
        {"op": "remove", "before": "- jQuery"},
        text=text,
    )

    (card,) = _cards(events)
    assert card["before_text"] == "- jQuery"
    assert _tokens(events) == f"Here you go.\n\n{note}"
    count = len((await db_session.execute(select(ChatChangeCard))).scalars().all())
    assert count == 1


async def test_already_stored_space_joined_card_is_accepted_via_fallback(
    client: httpx.AsyncClient, setup: dict[str, str], db_session: AsyncSession
) -> None:
    """Like the live card: stored before the fix, with the model's spaced quote."""
    (card,) = _cards(
        await _propose_events(
            client, setup, {"op": "replace", "before": WRAPPED, "after": NEW_PROFILE}
        )
    )
    await db_session.execute(
        update(ChatChangeCard)
        .where(ChatChangeCard.id == card["id"])
        .values(before_text=JOINED)
    )
    await db_session.commit()

    resp = await _decide(client, setup, card["id"])

    assert resp.status_code == 200, resp.text
    assert resp.json()["state"] == "accepted"
    assert (await _cv_content(client, setup))["content"] == CV.replace(
        WRAPPED, NEW_PROFILE
    )
