"""Quotes that differ from the CV in dashes, quote marks or Markdown markers.

The live bug: the CV holds a plain hard-wrapped paragraph and "Full‑stack"
(U+2011); the model had shown the paragraph as `> - Made the platform…` and
quoted it with that prefix and ASCII hyphens, so the edit was dropped with a
"could not prepare" note. Those quotes are placed now, stored as the exact CV
text, and an all-dropped reply gets one retry. Fake model clients only.
"""

import json
import time
from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import httpx
import pytest
import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_change_card import ChatChangeCard
from app.services import chat_service
from app.services.chat_card_service import (
    _PassageMissing,
    apply_card_edit,
    apply_card_edit_rebased,
    place_edit,
    quote_diagnostics,
)
from app.services.chat_service import QUOTE_RETRY_NUDGE
from app.services.chat_tools import PASSAGE_NOT_FOUND_NOTE, CvEdit
from app.services.cv_structure import unrequested_problems
from app.services.gemini_client import APP_NOTE_PREFIX
from tests.test_chat_cards import (
    APPS,
    _call_chunks,
    _chunk,
    _create_app,
    _create_cv,
    _cv_content,
    _decide,
    _events,
    _h,
)
from tests.test_chat_follows_requests import _send_seq, _SequenceGroq
from tests.test_chat_gemini import _call, _FakeOpenAI, gemini

__all__ = ["gemini"]  # the fixture, re-used

PARAGRAPH = (
    "Made the platform configurable by the client: fields can be renamed,\n"
    "reordered and hidden per tenant — one build for web, backend and\n"
    "mobile."
)
CV = (
    "# Jane Doe\n"
    "Full‑stack engineer · Berlin\n"
    "\n"
    "## Experience\n"
    "### Lead engineer – Acme (2020–2024)\n"
    "\n"
    f"{PARAGRAPH}\n"
    "\n"
    "Cut build time by 40% with “incremental” caching.\n"
    "\n"
    "## Skills\n"
    "- Python\n"
    "- **TypeScript**\n"
)
# The paragraph as the model displayed and then quoted it: a quoted list item,
# its line breaks as spaces and the em dash as an ASCII hyphen.
QUOTED_ITEM = (
    "> - Made the platform configurable by the client: fields can be renamed, "
    "reordered and hidden per tenant - one build for web, backend and mobile."
)
NEW_TEXT = "Made the platform configurable per tenant: one build for all clients."


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


@pytest.mark.parametrize(
    "quote",
    [
        QUOTED_ITEM,
        QUOTED_ITEM.removeprefix("> "),  # "- Made the platform…"
        QUOTED_ITEM.removeprefix("> - "),  # dash variant only
        "* " + QUOTED_ITEM.removeprefix("> - "),
        "1. " + QUOTED_ITEM.removeprefix("> - "),
        # Line by line, each line a quoted list line.
        "\n".join(f"> {line}" for line in PARAGRAPH.replace("—", "-").split("\n")),
    ],
)
def test_marked_and_dash_folded_quote_finds_the_plain_paragraph(quote: str) -> None:
    placed = place_edit(CV, _edit(before_text=quote, after_text=NEW_TEXT))

    assert placed is not None
    assert placed.before_text == PARAGRAPH  # the exact CV text
    assert placed.after_text == NEW_TEXT  # as the model wrote it
    assert _apply(CV, placed) == CV.replace(PARAGRAPH, NEW_TEXT)
    # Accept with the model's own quote (a card stored before the fix) too.
    assert _apply(CV, _edit(before_text=quote, after_text=NEW_TEXT)) == (
        CV.replace(PARAGRAPH, NEW_TEXT)
    )


@pytest.mark.parametrize(
    ("quote", "exact"),
    [
        ("Full-stack engineer", "Full‑stack engineer"),
        ("Full‐stack engineer", "Full‑stack engineer"),
        ("Lead engineer - Acme (2020-2024)", "Lead engineer – Acme (2020–2024)"),
        ("Lead engineer — Acme", "Lead engineer – Acme"),
        ('with "incremental" caching', "with “incremental” caching"),
        ("with ‘incremental’ caching", None),  # ' is not "
        ("Full‑stack engineer", "Full‑stack engineer"),  # NBSP
        ("Full‑st­ack engineer", "Full‑stack engineer"),  # soft hyphen
    ],
)
def test_dash_quote_and_space_variants(quote: str, exact: str | None) -> None:
    placed = place_edit(CV, _edit(before_text=quote, after_text="x"))

    if exact is None:
        assert placed is None
        return
    assert placed is not None
    assert placed.before_text == exact


def test_soft_hyphen_in_the_cv_is_ignored() -> None:
    cv = "# Jane\n\n## Profile\nBuilt dis­tributed systems.\n"

    placed = place_edit(
        cv, _edit(before_text="Built distributed systems.", after_text="x")
    )

    assert placed is not None
    assert placed.before_text == "Built dis­tributed systems."


def test_quote_without_markers_finds_a_bulleted_cv_list() -> None:
    quote = "Python TypeScript"  # the model dropped the bullets and the bold

    placed = place_edit(CV, _edit(before_text=quote, after_text="Python, TypeScript"))

    assert placed is not None
    # The span never cuts a bold pair: the closing ** goes with its opening.
    assert placed.before_text == "Python\n- **TypeScript**"
    assert _apply(CV, placed).endswith("## Skills\n- Python, TypeScript\n")
    lines = "- Python\n- TypeScript"
    placed = place_edit(CV, _edit(op="remove", before_text=lines))
    assert placed is not None
    assert placed.before_text == "Python\n- **TypeScript**"
    assert "**" not in _apply(CV, placed)


def test_heading_and_bold_markers_are_ignored() -> None:
    cv = "# Jane\n\n## Skills\n**Languages: Python, Go**\n"

    placed = place_edit(
        cv, _edit(before_text="### Skills\nLanguages: Python, Go", after_text="x")
    )

    assert placed is not None
    assert placed.before_text == "Skills\n**Languages: Python, Go**"
    assert _apply(cv, placed) == "# Jane\n\n## x\n"


@pytest.mark.parametrize(
    ("cv", "quote"),
    [
        # The quote starts inside a bold line and goes past its end: widening
        # to the opening ** would also replace "Led", which it never quoted.
        (
            "# Jane\n\n- **Led the team of five**\nShipped v2.\n",
            "the team of five Shipped",
        ),
        # The quote ends inside a bold line that started before it.
        (
            "# Jane\n\nShipped v2.\n**Led the team of five**\n",
            "Shipped v2. Led the team",
        ),
    ],
)
def test_a_loose_match_that_cuts_a_bold_pair_is_not_placed(cv: str, quote: str) -> None:
    edit = _edit(before_text=quote, after_text="x")

    assert place_edit(cv, edit) is None
    with pytest.raises(_PassageMissing):
        _apply(cv, edit)


def test_ambiguous_after_folding_is_not_placed() -> None:
    cv = "# Jane\n\n## A\nFull‑stack work.\n\n## B\nFull–stack work.\n"
    edit = _edit(before_text="Full-stack work.", after_text="x")

    assert place_edit(cv, edit) is None
    with pytest.raises(_PassageMissing):
        _apply(cv, edit)


def test_ambiguous_after_dropping_markers_is_not_placed() -> None:
    cv = "# Jane\n\n## A\n- Led the team.\n\n## B\nLed the team.\n"
    edit = _edit(before_text="> Led the team.\n> More", after_text="x")
    two = _edit(before_text="* Led the team.", after_text="x")

    assert place_edit(cv, edit) is None
    # "* Led the team." is in neither place as is; read loosely it is in both.
    assert place_edit(cv, two) is None


def test_an_exact_match_wins_over_a_loose_one() -> None:
    cv = "# Jane\n\n## A\n- Led the team.\n\n## B\nLed the team-work.\n"

    placed = place_edit(cv, _edit(before_text="- Led the team.", after_text="x"))

    assert placed is not None and placed.before_text == "- Led the team."


@pytest.mark.parametrize(
    "anchor",
    [
        "> - Made the platform configurable by the client: fields can be renamed,",
        "- reordered and hidden per tenant - one build for web",
        "mobile.",
    ],
)
def test_anchor_variants_insert_after_the_right_line(anchor: str) -> None:
    edit = _edit(
        op="insert", after_text="Led 4 engineers.", position="after_line",
        anchor_text=anchor,
    )  # fmt: skip

    placed = place_edit(CV, edit)

    assert placed is not None
    assert placed.anchor_text is not None and placed.anchor_text in CV
    result = _apply(CV, placed)
    assert result == _apply(CV, edit)
    added = result.split("\n").index("Led 4 engineers.")
    line_of_anchor = result.split("\n")[added - 1]
    assert placed.anchor_text.split("\n")[-1] in line_of_anchor


def test_rebased_accept_and_structure_dry_run_use_the_same_locating() -> None:
    result = apply_card_edit_rebased(
        CV,
        op="replace",
        before_text=QUOTED_ITEM,
        after_text=NEW_TEXT,
        position=None,
        anchor_text=None,
    )
    assert result == CV.replace(PARAGRAPH, NEW_TEXT)
    # The structure check dry-runs the edit the same way: nothing breaks.
    edit = _edit(before_text=QUOTED_ITEM, after_text=NEW_TEXT)
    assert unrequested_problems(CV, edit, "Rewrite it") == []


def test_quote_not_in_cv_is_still_not_placed() -> None:
    edit = _edit(before_text="- Made the app configurable by everyone.", after_text="x")

    assert place_edit(CV, edit) is None


def test_diagnostics_carry_flags_and_numbers_only() -> None:
    quote = "- made the PLATFORM configurable by the client: fields can be renamed"

    flags = quote_diagnostics(CV, quote)

    assert flags == {
        "quote_chars": len(quote),
        "matches_whitespace": 0,
        "matches_folded": 0,
        "matches_markers": 0,
        "found_ignoring_case": True,
        "quote_has_marker": True,
        "best_overlap_ratio": 0.91,  # 10 of 11 words ("renamed," in the CV)
    }
    assert all(isinstance(v, bool | int | float) for v in flags.values())


def test_diagnostics_count_an_ambiguous_loose_match() -> None:
    cv = "# Jane\n\n## A\nFull‑stack work.\n\n## B\nFull–stack work.\n"

    flags = quote_diagnostics(cv, "Full-stack work.")

    assert flags["matches_whitespace"] == 0
    assert flags["matches_folded"] == 2  # two or more
    assert flags["best_overlap_ratio"] == 1.0  # read case-blind and folded


def test_long_cv_and_long_quote_locate_fast() -> None:
    words = [f"word{i}" for i in range(2_500)]
    lines = [f"- {' '.join(words[i : i + 8])} — x‑y" for i in range(0, 2_500, 8)]
    cv = "\n".join(lines)[:20_000]
    body = cv[2_000:19_000]
    quote = "> " + body.replace("—", "-").replace("‑", "-")
    missing = quote + " nowhere"
    markers = "\n".join(["> - **" + "a" * 50 + "**"] * 300)

    start = time.perf_counter()
    placed = place_edit(cv, _edit(op="remove", before_text=quote))
    assert place_edit(cv, _edit(op="remove", before_text=missing)) is None
    quote_diagnostics(cv, missing)
    assert place_edit(markers, _edit(op="remove", before_text="b")) is None
    quote_diagnostics(markers, "b " * 1_000)
    assert time.perf_counter() - start < 1.0

    assert placed is not None
    assert placed.before_text in cv


# ---------------------------------------------------------------------------
# Through the chat (Groq and Gemini), Accept and the retry
# ---------------------------------------------------------------------------


@pytest.fixture
async def setup(client: httpx.AsyncClient, registered_user: dict) -> dict[str, str]:
    token = registered_user["access_token"]
    cv_id = await _create_cv(client, token, CV)
    app_id = await _create_app(client, token, cv_id)
    return {"token": token, "cv_id": cv_id, "app_id": app_id}


@pytest.fixture
def logs(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[dict[str, Any]]]:
    with structlog.testing.capture_logs() as captured:
        monkeypatch.setattr(chat_service, "logger", structlog.get_logger())
        yield captured


def _cards(events: list) -> list[dict]:
    return next(data for name, data in events if name == "cards")


def _tokens(events: list) -> str:
    return "".join(data["text"] for name, data in events if name == "token")


_ITEM_EDIT = {"op": "replace", "before": QUOTED_ITEM, "after": NEW_TEXT}
_MISSING = {"op": "replace", "before": "- Made the app for everyone.", "after": "x"}
_MISSING_TWO = {"op": "remove", "before": "Worked at Initech."}
_GOOD = {"op": "remove", "before": "- Python"}


async def test_marked_quote_becomes_a_card_and_accept_applies_it(
    client: httpx.AsyncClient, setup: dict[str, str], db_session: AsyncSession
) -> None:
    fake = _SequenceGroq([_chunk("Here it is."), *_call_chunks(0, _ITEM_EDIT)])

    events = await _send_seq(client, setup, fake, "Поправь варианты")

    assert len(fake.calls) == 1  # placed: no retry
    (card,) = _cards(events)
    assert card["before_text"] == PARAGRAPH
    assert card["after_text"] == NEW_TEXT
    stored = await db_session.scalar(
        select(ChatChangeCard.before_text).where(ChatChangeCard.id == card["id"])
    )
    assert stored == PARAGRAPH

    resp = await _decide(client, setup, card["id"])

    assert resp.status_code == 200, resp.text
    assert (await _cv_content(client, setup))["content"] == CV.replace(
        PARAGRAPH, NEW_TEXT
    )


async def test_stored_card_with_the_models_marked_quote_is_accepted(
    client: httpx.AsyncClient, setup: dict[str, str], db_session: AsyncSession
) -> None:
    """A card stored with the raw quote (before this fix) still applies."""
    fake = _SequenceGroq([_chunk("Here."), *_call_chunks(0, _ITEM_EDIT)])
    (card,) = _cards(await _send_seq(client, setup, fake, "Rewrite"))
    await db_session.execute(
        update(ChatChangeCard)
        .where(ChatChangeCard.id == card["id"])
        .values(before_text=QUOTED_ITEM)
    )
    await db_session.commit()

    resp = await _decide(client, setup, card["id"])

    assert resp.status_code == 200, resp.text
    assert (await _cv_content(client, setup))["content"] == CV.replace(
        PARAGRAPH, NEW_TEXT
    )


async def test_all_quotes_missing_gets_one_retry_that_succeeds(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    fake = _SequenceGroq(
        [*_call_chunks(0, _MISSING), *_call_chunks(1, _MISSING_TWO)],
        [*_call_chunks(0, _ITEM_EDIT)],
    )

    events = await _send_seq(client, setup, fake, "Поправь свои варианты")

    assert len(fake.calls) == 2
    retry = fake.calls[1]
    assert retry["tool_choice"] == "required"
    assert retry["tools"] == fake.calls[0]["tools"]
    assert retry["messages"][-1] == {"role": "system", "content": QUOTE_RETRY_NUDGE}
    # No reply text: no assistant message before the nudge.
    assert retry["messages"][-2]["role"] != "assistant"
    # The model's missed quotes are not echoed back.
    sent = json.dumps(retry["messages"], ensure_ascii=False)
    assert "Made the app for everyone" not in sent
    assert "Initech" not in sent
    (card,) = _cards(events)
    assert card["before_text"] == PARAGRAPH
    assert _tokens(events) == ""  # no "could not prepare" note


async def test_retry_keeps_the_text_and_adds_the_nudge_after_it(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    fake = _SequenceGroq(
        [_chunk("Updated version:"), *_call_chunks(0, _MISSING)],
        [_chunk("Fixed."), *_call_chunks(0, _ITEM_EDIT)],
    )

    events = await _send_seq(client, setup, fake, "Rewrite it")

    assert fake.calls[1]["messages"][-2] == {
        "role": "assistant",
        "content": "Updated version:",
    }
    assert _tokens(events) == "Updated version:\n\nFixed."
    assert [c["before_text"] for c in _cards(events)] == [PARAGRAPH]


@pytest.mark.parametrize(
    ("text", "language"), [("Rewrite it", "en"), ("Поправь варианты", "ru")]
)
async def test_retry_that_misses_again_keeps_the_note(
    client: httpx.AsyncClient,
    setup: dict[str, str],
    db_session: AsyncSession,
    text: str,
    language: str,
) -> None:
    fake = _SequenceGroq([*_call_chunks(0, _MISSING)], [*_call_chunks(0, _MISSING)])

    events = await _send_seq(client, setup, fake, text)

    assert len(fake.calls) == 2  # one retry, never more
    assert _cards(events) == []
    assert _tokens(events) == PASSAGE_NOT_FOUND_NOTE[language]  # type: ignore[index]
    assert (await db_session.execute(select(ChatChangeCard))).first() is None


async def test_retry_with_no_call_keeps_the_note(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    fake = _SequenceGroq(
        [_chunk("New wording:"), *_call_chunks(0, _MISSING)],
        [_chunk("Sorry.")],
    )

    events = await _send_seq(client, setup, fake, "Rewrite it")

    assert len(fake.calls) == 2
    assert _cards(events) == []
    assert _tokens(events) == (
        f"New wording:\n\nSorry.\n\n{PASSAGE_NOT_FOUND_NOTE['en']}"
    )


async def test_no_retry_when_one_card_is_placed(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    fake = _SequenceGroq(
        [_chunk("Two edits."), *_call_chunks(0, _MISSING), *_call_chunks(1, _GOOD)]
    )

    events = await _send_seq(client, setup, fake, "Rewrite it")

    assert len(fake.calls) == 1
    assert [c["before_text"] for c in _cards(events)] == ["- Python"]
    assert _tokens(events) == f"Two edits.\n\n{PASSAGE_NOT_FOUND_NOTE['en']}"


async def test_quote_retry_on_gemini_downgrades_required(
    client: httpx.AsyncClient, setup: dict[str, str], gemini: None
) -> None:
    fake = _FakeOpenAI(
        [
            _chunk(
                None, [_call("propose_cv_edit", json.dumps(_MISSING), index=0, id="a")]
            )
        ],
        [
            _chunk(
                None,
                [_call("propose_cv_edit", json.dumps(_ITEM_EDIT), index=0, id="b")],
            )
        ],
    )

    with patch("app.services.gemini_client._get_client", return_value=fake):
        resp = await client.post(
            f"{APPS}/{setup['app_id']}/chat",
            json={"content": "Rewrite it"},
            headers=_h(setup["token"]),
        )
    assert resp.status_code == 200
    events = _events(resp.text)
    assert len(fake.calls) == 2
    retry = fake.calls[1]
    assert retry["tool_choice"] == "auto"  # "required" downgraded on Gemini
    assert retry["messages"][-1]["role"] == "user"
    assert retry["messages"][-1]["content"].startswith(APP_NOTE_PREFIX)
    assert QUOTE_RETRY_NUDGE in retry["messages"][-1]["content"]
    assert [c["before_text"] for c in _cards(events)] == [PARAGRAPH]


async def test_dropped_quote_is_logged_without_text(
    client: httpx.AsyncClient,
    setup: dict[str, str],
    logs: list[dict[str, Any]],
) -> None:
    anchor_edit = {
        "op": "insert",
        "after": "x",
        "position": "after_line",
        "anchor": "- Worked at Initech as a lead",
    }
    fake = _SequenceGroq(
        [*_call_chunks(0, _MISSING), *_call_chunks(1, anchor_edit)],
        [*_call_chunks(0, _GOOD)],
    )

    await _send_seq(client, setup, fake, "Rewrite it")

    found = [e for e in logs if e["event"] == "chat_quote_not_found"]
    assert [(e["op"], e["field"]) for e in found] == [
        ("replace", "before"),
        ("insert", "anchor"),
    ]
    assert found[0]["quote_chars"] == len(_MISSING["before"])
    assert set(found[0]) == {
        "event",
        "log_level",
        "op",
        "field",
        "quote_chars",
        "matches_whitespace",
        "matches_folded",
        "matches_markers",
        "found_ignoring_case",
        "quote_has_marker",
        "best_overlap_ratio",
    }
    every = json.dumps(logs, ensure_ascii=False, default=str)
    assert "Initech" not in every
    assert "Made the app" not in every
    assert "configurable" not in every  # no CV text either
    assert any(e["event"] == "chat_quote_retry" for e in logs)
