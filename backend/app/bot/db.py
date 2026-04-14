"""Async database session factory for the bot process.

Shares the same SQLAlchemy engine configuration as the FastAPI backend.
"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield an async session (context-manager style)."""
    async with async_session() as session:
        yield session
