from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    SECRET_KEY: str
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/jobbi.db"
    ACCESS_TOKEN_EXPIRE_DAYS: int = 7
    CORS_ORIGINS: str = "http://localhost:5173"
    SENTRY_DSN: str = ""
    LOG_LEVEL: str = "INFO"
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-6-20250514"
    TELEGRAM_BOT_TOKEN: str = ""
    JOBBI_PUBLIC_URL: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()
