"""The CV chat keeps the CV structure (backlog #27). Fake Groq, no tokens.

An edit that drops a section the user did not ask to drop gets one repair
call; if the repair is still broken (or brings no usable edit), the card is
kept with a `warning`.
"""

from typing import Any
from unittest.mock import patch

import httpx
import pytest

from app.core.config import get_settings
from app.services.chat_budget import estimate_tokens, fixed_tokens
from app.services.chat_service import repair_nudge
from app.services.chat_tools import PROPOSE_CV_EDIT_TOOL
from app.services.cv_structure import Problem
from app.services.groq_client import (
    _CV_EDIT_RULES,
    _CV_STRUCTURE_RULES,
    build_system_prompt,
)
from evals.cv_chat.fixtures import CV as EVAL_CV
from evals.cv_chat.fixtures import VACANCY as EVAL_VACANCY
from tests.test_chat_cards import (
    APPS,
    CV_TEXT,
    _call_chunks,
    _chunk,
    _create_app,
    _create_cv,
    _decide,
    _h,
)
from tests.test_chat_follows_requests import _send_seq, _SequenceGroq

_SKILLS = "## Skills\n- Python\n- jQuery\n- Kubernetes"
_DROP_SKILLS = {"op": "remove", "before": _SKILLS}
_FIXED = {"op": "remove", "before": "- jQuery"}
_EN_WARNING = "This change removes the Skills section."
_RU_WARNING = "Эта правка удаляет раздел Skills."


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


async def test_broken_structure_gets_one_repair_that_fixes_it(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    fake = _SequenceGroq(
        [_chunk("Shortened."), *_call_chunks(0, _DROP_SKILLS)],
        [_chunk("Kept the section."), *_call_chunks(0, _FIXED)],
    )

    events = await _send_seq(client, setup, fake, "Make it shorter")

    assert len(fake.calls) == 2
    repair = fake.calls[1]
    assert repair["tool_choice"] == "required"
    assert repair["tools"] == fake.calls[0]["tools"]
    assert repair["messages"][-2] == {"role": "assistant", "content": "Shortened."}
    assert repair["messages"][-1] == {
        "role": "system",
        "content": repair_nudge([Problem("section_removed", "Skills")]),
    }
    assert "removes the Skills section" in repair["messages"][-1]["content"]
    cards = _cards(events)
    assert [(c["op"], c["before_text"], c["warning"]) for c in cards] == [
        ("remove", "- jQuery", None)
    ]
    assert _tokens(events) == "Shortened.\n\nKept the section."


async def test_still_broken_after_repair_keeps_the_card_with_a_warning(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    broken = [_chunk("Shortened."), *_call_chunks(0, _DROP_SKILLS)]
    fake = _SequenceGroq(broken, broken)

    events = await _send_seq(client, setup, fake, "Make it shorter")

    assert len(fake.calls) == 2  # one repair, never more
    cards = _cards(events)
    assert [c["warning"] for c in cards] == [_EN_WARNING]

    history = await client.get(
        f"{APPS}/{setup['app_id']}/chat", headers=_h(setup["token"])
    )
    assert [c["warning"] for c in history.json()[-1]["cards"]] == [_EN_WARNING]

    # The user stays in control: the warned card can still be accepted.
    accepted = await _decide(client, setup, cards[0]["id"])
    assert accepted.status_code == 200
    assert accepted.json()["warning"] == _EN_WARNING
    assert accepted.json()["state"] == "accepted"


async def test_repair_with_no_usable_edit_keeps_the_first_cards_warned(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    fake = _SequenceGroq(
        [_chunk("Shortened."), *_call_chunks(0, _DROP_SKILLS)],
        [_chunk("Sorry, I cannot do it without removing it.")],
    )

    events = await _send_seq(client, setup, fake, "Make it shorter")

    assert len(fake.calls) == 2
    cards = _cards(events)
    assert [(c["before_text"], c["warning"]) for c in cards] == [(_SKILLS, _EN_WARNING)]


async def test_explicit_removal_gets_no_repair_and_no_warning(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    fake = _SequenceGroq([_chunk("Removed."), *_call_chunks(0, _DROP_SKILLS)])

    events = await _send_seq(client, setup, fake, "Remove the Skills section")

    assert len(fake.calls) == 1
    assert [c["warning"] for c in _cards(events)] == [None]


async def test_russian_conversation_gets_a_russian_warning(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    broken = [_chunk("Сократил."), *_call_chunks(0, _DROP_SKILLS)]
    fake = _SequenceGroq(broken, broken)

    events = await _send_seq(client, setup, fake, "Сделай CV короче")

    assert [c["warning"] for c in _cards(events)] == [_RU_WARNING]


async def test_russian_explicit_removal_gets_no_repair(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    fake = _SequenceGroq([_chunk("Готово."), *_call_chunks(0, _DROP_SKILLS)])

    events = await _send_seq(client, setup, fake, "Убери раздел skills")

    assert len(fake.calls) == 1
    assert [c["warning"] for c in _cards(events)] == [None]


async def test_only_the_breaking_card_is_warned(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    broken = [
        _chunk("Two edits."),
        *_call_chunks(0, {"op": "replace", "before": "# Jane Doe", "after": "# J."}),
        *_call_chunks(1, _DROP_SKILLS),
    ]
    fake = _SequenceGroq(broken, broken)

    events = await _send_seq(client, setup, fake, "Tidy it up")

    assert [c["warning"] for c in _cards(events)] == [None, _EN_WARNING]


async def test_edits_that_keep_the_structure_get_no_repair(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    fake = _SequenceGroq([_chunk("Removed."), *_call_chunks(0, _FIXED)])

    events = await _send_seq(client, setup, fake, "Make it shorter")

    assert len(fake.calls) == 1
    assert [c["warning"] for c in _cards(events)] == [None]


async def test_repair_that_would_not_fit_the_budget_is_skipped(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    broken = [_chunk("Shortened."), *_call_chunks(0, _DROP_SKILLS)]
    fake = _SequenceGroq(broken, broken)
    over = get_settings().CHAT_INPUT_TOKEN_BUDGET + 1

    # Only second calls (retry, follow-up, repair) are sized with it.
    with patch("app.services.chat_service.request_tokens", return_value=over):
        events = await _send_seq(client, setup, fake, "Make it shorter")

    assert len(fake.calls) == 1
    assert [c["warning"] for c in _cards(events)] == [_EN_WARNING]


# ---------------------------------------------------------------------------
# Prompt and API contract
# ---------------------------------------------------------------------------


class _App:
    company_name = "Acme"
    role_title = "SRE"
    job_url = None
    status = None
    notes: str | None = None


class _Cv:
    content = "# Jane Doe"


def test_structure_rules_follow_the_edit_rules_when_a_cv_is_linked() -> None:
    prompt = build_system_prompt(_App(), _Cv())  # type: ignore[arg-type]

    assert _CV_STRUCTURE_RULES in prompt
    assert prompt.index(_CV_EDIT_RULES) < prompt.index(_CV_STRUCTURE_RULES)
    assert '"#### Project"' in _CV_STRUCTURE_RULES
    assert "structure or format the CV" in _CV_STRUCTURE_RULES


def test_no_structure_rules_without_a_cv() -> None:
    assert _CV_STRUCTURE_RULES not in build_system_prompt(_App(), None)  # type: ignore[arg-type]


# The fixed part of every CV chat request (rules + tool schema, tiny CV). The
# Groq chat model's input cap is 7 000 tokens a minute; the CV, the vacancy
# and the history need the rest.
FIXED_PROMPT_TOKEN_CAP = 1_600


def test_fixed_prompt_part_stays_under_its_cap() -> None:
    prompt = build_system_prompt(_App(), _Cv())  # type: ignore[arg-type]
    assert fixed_tokens(prompt, [PROPOSE_CV_EDIT_TOOL]) < FIXED_PROMPT_TOKEN_CAP
    assert estimate_tokens(_CV_STRUCTURE_RULES) < 350


def test_a_typical_cv_and_vacancy_leave_room_for_the_chat() -> None:
    app = _App()
    app.notes = EVAL_VACANCY
    cv = _Cv()
    cv.content = EVAL_CV
    prompt = build_system_prompt(app, cv)  # type: ignore[arg-type]
    room = get_settings().CHAT_INPUT_TOKEN_BUDGET - fixed_tokens(
        prompt, [PROPOSE_CV_EDIT_TOOL]
    )
    assert room > 3_000


@pytest.mark.parametrize("schema", ["ChangeCardRead"])
async def test_openapi_exposes_the_card_warning(
    client: httpx.AsyncClient, schema: str
) -> None:
    spec = (await client.get("/openapi.json")).json()
    card = spec["components"]["schemas"][schema]
    assert "warning" in card["required"]
    assert {"type": "null"} in card["properties"]["warning"]["anyOf"]
    assert {"type": "string"} in card["properties"]["warning"]["anyOf"]
