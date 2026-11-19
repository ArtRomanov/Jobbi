"""The documented .env.example must work with the async engine as-is."""

from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import Settings

ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"


def _example_value(key: str) -> str:
    for line in ENV_EXAMPLE.read_text().splitlines():
        name, sep, value = line.partition("=")
        if sep and name.strip() == key:
            return value.strip()
    raise AssertionError(f"{key} missing from .env.example")


def test_env_example_database_url_works_with_async_engine() -> None:
    url = _example_value("DATABASE_URL")

    engine = create_async_engine(url)  # raises for a sync-only driver

    assert engine.dialect.is_async
    assert url == Settings.model_fields["DATABASE_URL"].default
