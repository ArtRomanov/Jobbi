"""The CV chat follows the user's requests (backlog #29). Fake Groq, no tokens."""

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from app.services.chat_card_service import REMOVED_TEXT_LABEL
from app.services.chat_guard_notes import UNSUPPORTED_NAMES_NOTE
from app.services.chat_service import (
    FOLLOW_UP_NUDGE,
    drop_unsupported_edits,
    needs_follow_up,
)
from app.services.chat_tools import CvEdit
from app.services.groq_client import LlmToolCall, build_system_prompt
from tests.test_chat_cards import (
    APPS,
    CV_TEXT,
    _call_chunks,
    _chunk,
    _create_app,
    _create_cv,
    _decide,
    _events,
    _FakeGroq,
    _h,
    _propose,
    _send,
)

_CALL = LlmToolCall(name="propose_cv_edit", arguments="{}")
# Live eval 2026-11-25: this reply came with no tool call and no card.
_PROMISE_FIRST = (
    "I'll shorten the CV and shift the emphasis to React: reorder the skills "
    "list and tidy the bullets."
)
_CONDITIONAL_PROMISE = (
    "The CV has no job before Bluefin. Once you share the dates and company, "
    "I'll add it."
)


@pytest.fixture
async def setup(client: httpx.AsyncClient, registered_user: dict) -> dict[str, str]:
    token = registered_user["access_token"]
    cv_id = await _create_cv(client, token, CV_TEXT)
    app_id = await _create_app(client, token, cv_id)
    return {"token": token, "cv_id": cv_id, "app_id": app_id}


@pytest.mark.parametrize(
    ("reply", "calls", "expected"),
    [
        ("", [], True),
        ("   \n", [], True),
        (
            "Let me first confirm your latest changes — fetching the current CV.",
            [],
            True,
        ),
        ("I'll re-pull the current CV to quote edits accurately:", [], True),
        ("Here are the three changes:", [], True),
        ("I will check the CV first.", [], True),
        (_PROMISE_FIRST, [], True),
        ("Good idea. Let me tighten the profile.", [], True),
        ("Хорошо.\nСейчас сокращу профиль.", [], True),
        (_CONDITIONAL_PROMISE, [], False),
        ("Your CV already matches the role well. Want me to shorten it?", [], False),
        ("I can't add that job: the CV has no details about it.", [], False),
        ("Here are the three changes:", [_CALL], False),
        ("", [_CALL], False),
    ],
)
def test_needs_follow_up(reply: str, calls: list[LlmToolCall], expected: bool) -> None:
    assert needs_follow_up(reply, calls) is expected


class _SequenceGroq(_FakeGroq):
    """Answers each `create` call with the next list of chunks."""

    def __init__(self, *answers: list[Any]) -> None:
        super().__init__([])
        self.answers = list(answers)

    async def _create(self, **kwargs: Any) -> AsyncIterator[Any]:
        self.calls.append(kwargs)
        chunks = self.answers[min(len(self.calls), len(self.answers)) - 1]

        async def _gen() -> AsyncIterator[Any]:
            for chunk in chunks:
                yield chunk

        return _gen()


async def _send_seq(
    client: httpx.AsyncClient, s: dict[str, str], fake: _SequenceGroq, text: str
) -> list[tuple[str, Any]]:
    with patch("app.services.groq_client._get_client", return_value=fake):
        resp = await client.post(
            f"{APPS}/{s['app_id']}/chat", json={"content": text}, headers=_h(s["token"])
        )
    return _events(resp.text)


async def test_reply_that_only_promises_gets_one_follow_up_with_the_edits(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    fake = _SequenceGroq(
        [_chunk("Let me fetch the current CV.")],
        [
            _chunk("Removed jQuery."),
            *_call_chunks(0, {"op": "remove", "before": "- jQuery"}),
        ],
    )

    events = await _send_seq(client, setup, fake, "Remove jQuery")

    assert len(fake.calls) == 2
    follow_up = fake.calls[1]["messages"]
    assert follow_up[-2] == {
        "role": "assistant",
        "content": "Let me fetch the current CV.",
    }
    assert follow_up[-1] == {"role": "system", "content": FOLLOW_UP_NUDGE}
    assert follow_up[-3] == {"role": "user", "content": "Remove jQuery"}
    assert fake.calls[1]["tools"] == fake.calls[0]["tools"]
    tokens = "".join(data["text"] for name, data in events if name == "token")
    assert tokens == "Let me fetch the current CV.\n\nRemoved jQuery."
    cards = next(data for name, data in events if name == "cards")
    assert [c["op"] for c in cards] == ["remove"]

    history = await client.get(
        f"{APPS}/{setup['app_id']}/chat", headers=_h(setup["token"])
    )
    assistant = history.json()[-1]
    assert assistant["content"] == "Let me fetch the current CV.\n\nRemoved jQuery."
    assert [c["id"] for c in assistant["cards"]] == [cards[0]["id"]]


async def test_empty_reply_follow_up_sends_no_empty_assistant_turn(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    fake = _SequenceGroq([], [_chunk("No change needed.")])

    events = await _send_seq(client, setup, fake, "Thanks")

    assert len(fake.calls) == 2
    assert fake.calls[1]["messages"][-2] == {"role": "user", "content": "Thanks"}
    tokens = "".join(data["text"] for name, data in events if name == "token")
    assert tokens == "No change needed."


async def test_follow_up_happens_at_most_once(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    fake = _SequenceGroq([_chunk("Here are the edits:")], [_chunk("And now:")])

    events = await _send_seq(client, setup, fake, "Shorten it")

    assert len(fake.calls) == 2
    assert events[-2] == ("cards", [])
    assert events[-1][0] == "done"


async def test_plain_answer_gets_no_follow_up(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    _, fake = await _send(client, setup, _chunk("Your CV fits the role well."))

    assert len(fake.calls) == 1


async def test_reply_with_a_tool_call_gets_no_follow_up(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    _, fake = await _send(
        client,
        setup,
        _chunk("Here are the edits:"),
        *_call_chunks(0, {"op": "remove", "before": "- jQuery"}),
    )

    assert len(fake.calls) == 1


async def test_no_follow_up_without_a_linked_cv(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    s = {"token": token, "app_id": await _create_app(client, token)}

    _, fake = await _send(client, s, _chunk("Let me fetch your CV."))

    assert len(fake.calls) == 1


async def test_several_tool_calls_are_allowed_in_one_reply(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    _, fake = await _send(client, setup, _chunk("ok"))

    assert fake.calls[0]["parallel_tool_calls"] is True
    assert fake.calls[0]["tool_choice"] == "auto"


async def test_only_the_latest_reply_quotes_removed_text_in_full(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    older = await _propose(client, setup, {"op": "remove", "before": "- jQuery"})
    assert (await _decide(client, setup, older[0]["id"])).status_code == 200
    summary = "Experienced SRE with 5 years of production ops."
    latest = await _propose(
        client, setup, {"op": "replace", "before": summary, "after": "SRE, 5 years."}
    )
    assert (await _decide(client, setup, latest[0]["id"])).status_code == 200

    _, fake = await _send(client, setup, _chunk("ok"), text="Put it back")

    notes = [m["content"] for m in fake.calls[0]["messages"] if m["role"] == "system"]
    older_note, latest_note = notes[1], notes[2]
    assert REMOVED_TEXT_LABEL not in older_note
    assert "- accepted: remove '- jQuery'" in older_note
    assert f"  {REMOVED_TEXT_LABEL}\n    {summary}" in latest_note


async def test_full_quote_keeps_line_breaks_and_skips_rejected_cards(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    block = "## Skills\n- Python\n- jQuery"
    cards = await _propose(
        client,
        setup,
        {"op": "remove", "before": block},
        {"op": "replace", "before": "# Jane Doe", "after": "# Jane D."},
    )
    assert (await _decide(client, setup, cards[0]["id"])).status_code == 200
    assert (await _decide(client, setup, cards[1]["id"], "reject")).status_code == 200

    _, fake = await _send(client, setup, _chunk("ok"), text="Undo")

    note = fake.calls[0]["messages"][3]["content"]
    assert "\n    ## Skills\n    - Python\n    - jQuery\n" in note
    assert note.count(REMOVED_TEXT_LABEL) == 1


def test_system_prompt_has_the_request_following_rules() -> None:
    class _App:
        company_name = "Acme"
        role_title = "SRE"
        job_url = None
        status = "researching"
        notes = None

    class _Cv:
        content = CV_TEXT

    prompt = build_system_prompt(_App(), _Cv())  # type: ignore[arg-type]

    for phrase in (
        "Handle every request in the user's latest message",
        "several calls in one reply are normal",
        "say plainly why",
        "Never invent facts",
        "explicit instruction wins",
        "describe only the edits you actually propose",
        "propose_cv_edit is your only tool",
        "never say you will fetch",
        "Reply in the language of the user's latest message",
    ):
        assert phrase in prompt, phrase


async def test_follow_up_after_a_promise_requires_a_tool_call(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    fake = _SequenceGroq([_chunk(_PROMISE_FIRST)], [])

    await _send_seq(client, setup, fake, "Make it shorter")

    assert fake.calls[0]["tool_choice"] == "auto"
    assert fake.calls[1]["tool_choice"] == "required"


async def test_follow_up_after_an_empty_reply_lets_the_model_just_answer(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    fake = _SequenceGroq([], [_chunk("No change needed.")])

    await _send_seq(client, setup, fake, "Thanks")

    assert fake.calls[1]["tool_choice"] == "auto"


_JOB_POST = "Senior SRE. Must have: Kubernetes, Argo CD, Terraform Cloud."
_ADD_ARGO = {
    "op": "replace",
    "before": "- Kubernetes",
    "after": "- Kubernetes, Argo CD",
}


async def _set_notes(client: httpx.AsyncClient, s: dict[str, str], notes: str) -> None:
    resp = await client.patch(
        f"{APPS}/{s['app_id']}", json={"notes": notes}, headers=_h(s["token"])
    )
    assert resp.status_code == 200, resp.text


async def test_edit_adding_a_job_post_name_the_cv_lacks_is_left_out(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    await _set_notes(client, setup, _JOB_POST)
    keep = {"op": "remove", "before": "- jQuery"}

    events, _ = await _send(
        client,
        setup,
        _chunk("Two edits."),
        *_call_chunks(0, _ADD_ARGO),
        *_call_chunks(1, keep),
        text="Adapt my CV",
    )

    cards = next(data for name, data in events if name == "cards")
    assert [c["op"] for c in cards] == ["remove"]
    tokens = "".join(data["text"] for name, data in events if name == "token")
    assert tokens == "Two edits.\n\n" + UNSUPPORTED_NAMES_NOTE["en"].format(
        names="Argo CD"
    )


async def test_edit_adding_a_name_the_user_gave_is_kept(
    client: httpx.AsyncClient, setup: dict[str, str]
) -> None:
    await _set_notes(client, setup, _JOB_POST)

    events, _ = await _send(
        client,
        setup,
        *_call_chunks(0, _ADD_ARGO),
        text="I use argo cd daily, add it to my skills",
    )

    cards = next(data for name, data in events if name == "cards")
    assert [c["after_text"] for c in cards] == ["- Kubernetes, Argo CD"]


def test_drop_unsupported_edits_keeps_order_and_names_each_left_out_edit() -> None:
    def _edit(after: str) -> CvEdit:
        return CvEdit(
            op="insert",
            before_text="",
            after_text=after,
            position="end",
            anchor_text=None,
        )

    edits = [_edit("- Python"), _edit("- TanStack Query"), _edit("- Docker")]

    kept, left_out = drop_unsupported_edits(
        edits, cv=CV_TEXT, user_texts=["add Docker"], job_post=""
    )

    assert [e.after_text for e in kept] == ["- Python", "- Docker"]
    assert left_out == [["TanStack"]]
