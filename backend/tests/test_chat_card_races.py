"""Concurrent card decisions (spec 011 pre-merge F1/F2).

Each session is its own connection to a file-backed SQLite DB, so two
"tabs" can each load the pending card before either decides it.
"""

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models.application import Application
from app.models.chat_change_card import ChatChangeCard
from app.models.chat_message import ChatMessage
from app.models.cv import Cv
from app.models.user import User
from app.services import cv_service
from app.services.chat_card_service import (
    CardDecidedError,
    CardStaleError,
    _get_card,
    accept_card,
    reject_card,
)

CV_TEXT = "## Skills\n- Python\n- jQuery\n- Kubernetes"

INSERT = {"op": "insert", "after_text": "- Docker", "position": "end"}
REMOVE = {"op": "remove", "before_text": "- jQuery"}


@pytest.fixture
async def sessions(
    tmp_path: Path,
) -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'cards.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def _seed(
    sessions: async_sessionmaker[AsyncSession], edit: dict[str, Any]
) -> tuple[Application, str, str]:
    """A user, a CV, an application linked to it and one pending card."""
    async with sessions() as db:
        user = User(email="race@example.com", password_hash="x", full_name="Race")
        db.add(user)
        await db.flush()
        cv = Cv(user_id=user.id, name="CV", content=CV_TEXT)
        db.add(cv)
        await db.flush()
        application = Application(
            user_id=user.id, cv_id=cv.id, company_name="Acme", role_title="SRE"
        )
        db.add(application)
        await db.flush()
        message = ChatMessage(
            application_id=application.id, role="assistant", content="Here."
        )
        db.add(message)
        await db.flush()
        card = ChatChangeCard(
            application_id=application.id,
            message_id=message.id,
            cv_id=cv.id,
            **edit,
        )
        db.add(card)
        await db.commit()
        return application, cv.id, card.id


async def _stored(
    sessions: async_sessionmaker[AsyncSession], cv_id: str, card_id: str
) -> tuple[str, int, str]:
    async with sessions() as db:
        cv = (await db.execute(select(Cv).where(Cv.id == cv_id))).scalar_one()
        state = await db.scalar(
            select(ChatChangeCard.state).where(ChatChangeCard.id == card_id)
        )
        return cv.content, cv.version, state


async def _tab_b_loaded_then_tab_a_accepted(
    sessions: async_sessionmaker[AsyncSession],
    application: Application,
    card_id: str,
    tab_b: AsyncSession,
) -> ChatChangeCard:
    """Tab B reads the card while it is pending; tab A then accepts it.

    The caller keeps the returned card alive: the session's identity map holds
    objects weakly, and tab B must still see its pending copy.
    """
    seen_by_b = await _get_card(tab_b, application, card_id)
    assert seen_by_b.state == "pending"
    await tab_b.commit()  # end the read, as a request would between awaits
    async with sessions() as tab_a:
        accepted = await accept_card(tab_a, application, card_id)
        assert accepted.state == "accepted"
    return seen_by_b


async def test_second_accept_of_an_insert_does_not_apply_it_twice(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    application, cv_id, card_id = await _seed(sessions, INSERT)

    async with sessions() as tab_b:
        seen_by_b = await _tab_b_loaded_then_tab_a_accepted(
            sessions, application, card_id, tab_b
        )
        assert seen_by_b.state == "pending"
        with pytest.raises(CardDecidedError):
            await accept_card(tab_b, application, card_id)

    assert await _stored(sessions, cv_id, card_id) == (
        CV_TEXT + "\n- Docker",
        2,
        "accepted",
    )


async def test_second_accept_of_a_remove_does_not_mark_the_card_stale(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    application, cv_id, card_id = await _seed(sessions, REMOVE)

    async with sessions() as tab_b:
        seen_by_b = await _tab_b_loaded_then_tab_a_accepted(
            sessions, application, card_id, tab_b
        )
        assert seen_by_b.state == "pending"
        with pytest.raises(CardDecidedError):
            await accept_card(tab_b, application, card_id)

    assert await _stored(sessions, cv_id, card_id) == (
        CV_TEXT.replace("- jQuery\n", ""),
        2,
        "accepted",
    )


async def test_reject_after_a_concurrent_accept_keeps_the_card_accepted(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    application, cv_id, card_id = await _seed(sessions, REMOVE)

    async with sessions() as tab_b:
        seen_by_b = await _tab_b_loaded_then_tab_a_accepted(
            sessions, application, card_id, tab_b
        )
        assert seen_by_b.state == "pending"
        with pytest.raises(CardDecidedError):
            await reject_card(tab_b, application, card_id)

    assert await _stored(sessions, cv_id, card_id) == (
        CV_TEXT.replace("- jQuery\n", ""),
        2,
        "accepted",
    )


async def test_accept_after_a_concurrent_reject_rolls_back_the_cv_write(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """The card is rejected after tab B's checks but before its card write."""
    application, cv_id, card_id = await _seed(sessions, INSERT)
    real_write = cv_service.update_cv_content_if_version

    async def _reject_first(db: AsyncSession, *args: Any, **kw: Any) -> Cv:
        async with sessions() as tab_a:
            await reject_card(tab_a, application, card_id)
        return await real_write(db, *args, **kw)

    async with sessions() as tab_b:
        with (
            patch.object(cv_service, "update_cv_content_if_version", _reject_first),
            pytest.raises(CardDecidedError),
        ):
            await accept_card(tab_b, application, card_id)

    assert await _stored(sessions, cv_id, card_id) == (CV_TEXT, 1, "rejected")


async def test_accept_racing_a_relink_does_not_edit_the_unlinked_cv(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """F2: the application is re-linked between the link check and the write."""
    application, cv_id, card_id = await _seed(sessions, REMOVE)
    real_write = cv_service.update_cv_content_if_version

    async def _relink_first(db: AsyncSession, *args: Any, **kw: Any) -> Cv:
        async with sessions() as other:
            other_cv = Cv(user_id=application.user_id, name="Other", content="x")
            other.add(other_cv)
            await other.flush()
            await other.execute(
                update(Application)
                .where(Application.id == application.id)
                .values(cv_id=other_cv.id)
            )
            await other.commit()
        return await real_write(db, *args, **kw)

    async with sessions() as tab:
        with (
            patch.object(cv_service, "update_cv_content_if_version", _relink_first),
            pytest.raises(CardStaleError),
        ):
            await accept_card(tab, application, card_id)

    assert await _stored(sessions, cv_id, card_id) == (CV_TEXT, 1, "stale")
