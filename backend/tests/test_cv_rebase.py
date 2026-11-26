"""Accepting a card after the CV changed: the change is re-aimed when clear."""

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_change_card import ChatChangeCard
from app.services.chat_card_service import _PassageMissing, apply_card_edit_rebased
from app.services.cv_rebase import rebase_anchor, rebase_replace
from tests.test_chat_cards import (
    _call_chunks,
    _chunk,
    _create_app,
    _create_cv,
    _cv_content,
    _decide,
    _h,
    _send,
)

PROFILE = (
    "Frontend developer with 6 years of experience building React apps. "
    "Led the migration of a large codebase to TypeScript. "
    "Mentored three junior engineers and ran code reviews."
)
CV = f"# Jane Doe\n\n## Profile\n{PROFILE}\n\n## Skills\n- React\n- jQuery\n"

# Two cards of one reply, both quoting the whole profile paragraph.
EDIT_A = PROFILE.replace(
    "Frontend developer with 6 years of experience building React apps.",
    "Senior frontend engineer, 6 years with React.",
)
EDIT_B = PROFILE.replace(
    "Mentored three junior engineers and ran code reviews.",
    "Mentored three juniors.",
)


def _replace(content: str, before: str, after: str) -> str:
    return apply_card_edit_rebased(
        content,
        op="replace",
        before_text=before,
        after_text=after,
        position=None,
        anchor_text=None,
    )


# ---------------------------------------------------------------------------
# Pure
# ---------------------------------------------------------------------------


def test_second_edit_of_the_same_paragraph_applies_on_top_of_the_first() -> None:
    after_a = _replace(CV, PROFILE, EDIT_A)

    after_b = _replace(after_a, PROFILE, EDIT_B)

    assert after_b == CV.replace(
        PROFILE,
        "Senior frontend engineer, 6 years with React. "
        "Led the migration of a large codebase to TypeScript. "
        "Mentored three juniors.",
    )


def test_order_does_not_matter() -> None:
    both = _replace(_replace(CV, PROFILE, EDIT_B), PROFILE, EDIT_A)

    assert both == _replace(_replace(CV, PROFILE, EDIT_A), PROFILE, EDIT_B)


def test_ambiguous_target_is_rejected() -> None:
    # The changed sentences, context and all, are in the CV twice: there is
    # no telling which copy card B meant once card A changed the paragraph.
    tail = PROFILE.split("React apps. ")[1]
    content = CV.replace("- jQuery\n", f"- jQuery\n\n## Notes\n{tail}\n")
    content = _replace(content, PROFILE, EDIT_A)

    with pytest.raises(_PassageMissing):
        _replace(content, PROFILE, EDIT_B)


def test_rewritten_region_is_rejected() -> None:
    content = CV.replace(PROFILE, "Engineer who ships accessible web products.")

    with pytest.raises(_PassageMissing):
        _replace(content, PROFILE, EDIT_B)


def test_mostly_rewritten_paragraph_is_rejected_even_if_the_target_survived() -> None:
    # Only the sentence card B changes is still there: under half of the card's
    # before text, so the paragraph is not the one the card was made for.
    content = CV.replace(
        PROFILE,
        "Product-minded engineer who ships accessible web apps for banks. "
        "Mentored three junior engineers and ran code reviews.",
    )

    with pytest.raises(_PassageMissing):
        _replace(content, PROFILE, EDIT_B)


def test_rebase_replace_returns_a_unique_passage() -> None:
    content = _replace(CV, PROFILE, EDIT_A)

    rebased = rebase_replace(content, PROFILE, EDIT_B)

    assert rebased is not None
    before, after = rebased
    assert content.count(before) == 1
    assert "Mentored three juniors." in after


def test_remove_never_rebases() -> None:
    content = _replace(CV, PROFILE, EDIT_A)

    with pytest.raises(_PassageMissing):
        apply_card_edit_rebased(
            content,
            op="remove",
            before_text=PROFILE,
            after_text="",
            position=None,
            anchor_text=None,
        )


def _insert_after(content: str, anchor: str) -> str:
    return apply_card_edit_rebased(
        content,
        op="insert",
        before_text="",
        after_text="- Docker",
        position="after_line",
        anchor_text=anchor,
    )


def test_insert_follows_an_edited_anchor_line() -> None:
    content = CV.replace("- React\n", "- React 18\n")

    assert _insert_after(content, "- React") == content.replace(
        "- React 18\n", "- React 18\n- Docker\n"
    )


def test_insert_with_an_ambiguous_edited_anchor_is_rejected() -> None:
    content = CV.replace("- React\n", "- React Hooks\n- React Hook\n")

    # Both lines are close to the old anchor "- React hooks".
    with pytest.raises(_PassageMissing):
        _insert_after(content, "- React hooks")


def test_insert_with_a_gone_anchor_is_rejected() -> None:
    assert rebase_anchor(CV, "- Kubernetes operators") is None
    with pytest.raises(_PassageMissing):
        _insert_after(CV, "- Kubernetes operators")


# ---------------------------------------------------------------------------
# Through the API (the live case)
# ---------------------------------------------------------------------------


async def test_accept_a_then_b_on_the_same_paragraph(
    client: httpx.AsyncClient, registered_user: dict, db_session: AsyncSession
) -> None:
    token = registered_user["access_token"]
    cv_id = await _create_cv(client, token, CV)
    s = {
        "token": token,
        "cv_id": cv_id,
        "app_id": await _create_app(client, token, cv_id),
    }
    events, _ = await _send(
        client,
        s,
        _chunk("Two edits."),
        *_call_chunks(0, {"op": "replace", "before": PROFILE, "after": EDIT_A}),
        *_call_chunks(1, {"op": "replace", "before": PROFILE, "after": EDIT_B}),
    )
    card_a, card_b = next(data for name, data in events if name == "cards")

    assert (await _decide(client, s, card_a["id"])).status_code == 200
    resp = await _decide(client, s, card_b["id"])

    assert resp.status_code == 200, resp.text
    assert resp.json()["state"] == "accepted"
    content = (await _cv_content(client, s))["content"]
    assert "Senior frontend engineer, 6 years with React." in content
    assert "Mentored three juniors." in content
    assert PROFILE not in content


async def test_accept_after_the_paragraph_was_rewritten_is_still_stale(
    client: httpx.AsyncClient, registered_user: dict, db_session: AsyncSession
) -> None:
    token = registered_user["access_token"]
    cv_id = await _create_cv(client, token, CV)
    s = {
        "token": token,
        "cv_id": cv_id,
        "app_id": await _create_app(client, token, cv_id),
    }
    events, _ = await _send(
        client,
        s,
        *_call_chunks(0, {"op": "replace", "before": PROFILE, "after": EDIT_B}),
    )
    (card,) = next(data for name, data in events if name == "cards")
    cv = await _cv_content(client, s)
    resp = await client.patch(
        f"/api/v1/cvs/{cv_id}",
        json={
            "content": CV.replace(PROFILE, "Engineer who ships web products."),
            "version": cv["version"],
        },
        headers=_h(token),
    )
    assert resp.status_code == 200

    resp = await _decide(client, s, card["id"])

    assert resp.status_code == 409
    assert resp.json()["detail"] == "CARD_STALE"
    state = await db_session.scalar(
        select(ChatChangeCard.state).where(ChatChangeCard.id == card["id"])
    )
    assert state == "stale"


def test_long_anchor_is_not_re_aimed_and_returns_fast() -> None:
    """A model-written anchor is capped only at 20k chars; the line matcher is quadratic."""
    import time

    lines = [
        f"- Built feature {i} with React, TypeScript and a lot of care"
        for i in range(300)
    ]
    content = "\n".join(lines) + "\n"
    anchor = "\n".join(line.replace("care", "kare") for line in lines[100:130])

    start = time.perf_counter()
    assert rebase_anchor(content, anchor) is None
    assert time.perf_counter() - start < 0.5


def test_edited_long_single_line_anchor_is_still_re_aimed() -> None:
    line = "- " + "Led the migration of the payments platform to React. " * 7
    content = f"# Jane\n\n## Experience\n{line.replace('Led', 'Drove', 1)}\n- jQuery\n"

    assert rebase_anchor(content, line) == line.replace("Led", "Drove", 1)
