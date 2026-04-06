from collections.abc import AsyncIterator

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.chat_message import ChatMessage
from app.models.cv import Cv
from app.services.claude_client import build_system_prompt, stream_claude_response


async def get_chat_history(
    db: AsyncSession, application_id: str
) -> list[ChatMessage]:
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.application_id == application_id)
        .order_by(ChatMessage.created_at.asc())
    )
    return list(result.scalars().all())


async def save_message(
    db: AsyncSession, application_id: str, role: str, content: str
) -> ChatMessage:
    message = ChatMessage(
        application_id=application_id,
        role=role,
        content=content,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message


async def clear_chat_history(db: AsyncSession, application_id: str) -> None:
    await db.execute(
        delete(ChatMessage).where(ChatMessage.application_id == application_id)
    )
    await db.commit()


async def get_application_context(
    db: AsyncSession, application: Application
) -> tuple[str, Application, Cv | None]:
    """Build system prompt from application + linked CV."""
    cv = None
    if application.cv_id:
        result = await db.execute(select(Cv).where(Cv.id == application.cv_id))
        cv = result.scalar_one_or_none()

    system_prompt = build_system_prompt(application, cv)
    return system_prompt, application, cv


async def stream_chat_response(
    db: AsyncSession,
    application: Application,
    user_content: str,
) -> AsyncIterator[str]:
    """Save user message, build context, stream Claude response, save assistant message."""
    # Save user message
    await save_message(db, application.id, "user", user_content)

    # Build context
    system_prompt, _, _ = await get_application_context(db, application)

    # Get conversation history for Claude
    history = await get_chat_history(db, application.id)
    messages = [
        {"role": msg.role, "content": msg.content}
        for msg in history
    ]

    # Stream response
    full_response = []
    async for chunk in stream_claude_response(system_prompt, messages):
        full_response.append(chunk)
        yield chunk

    # Save complete assistant response
    assistant_content = "".join(full_response)
    if assistant_content:
        await save_message(db, application.id, "assistant", assistant_content)
