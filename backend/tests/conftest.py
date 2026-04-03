import os

# Set env vars before any app imports (database.py calls get_settings() at import time)
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests-only")

from collections.abc import AsyncGenerator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.core.deps import get_db
from app.main import create_app

# In-memory SQLite engine for tests
test_engine = create_async_engine("sqlite+aiosqlite://", echo=False)
TestSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
async def _setup_db() -> AsyncGenerator[None, None]:
    """Create all tables before each test and drop them after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an async DB session for direct database access in tests."""
    async with TestSessionLocal() as session:
        yield session


@pytest.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Async HTTP client wired to the FastAPI test app."""
    app = create_app()

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with TestSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def registered_user(client: httpx.AsyncClient) -> dict:
    """Register a user and return the response payload (access_token + user)."""
    payload = {
        "email": "testuser@example.com",
        "password": "securepassword123",
        "full_name": "Test User",
    }
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    # Include the original password for convenience in login tests
    data["password"] = payload["password"]
    return data
