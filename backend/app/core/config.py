from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    SECRET_KEY: str
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/jobbi.db"
    ACCESS_TOKEN_EXPIRE_DAYS: int = 7
    CORS_ORIGINS: str = "http://localhost:5174"
    SENTRY_DSN: str = ""
    LOG_LEVEL: str = "INFO"
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "qwen/qwen3.8-27b"
    # Model for vacancy discovery (separate from the chat model above).
    GROQ_DISCOVERY_MODEL: str = "openai/gpt-oss-20b"
    # Rates discovery posts while GROQ_DISCOVERY_MODEL is out of its daily token
    # quota (Groq counts TPD per model). Not the chat model: that would spend the
    # chat's quota. Empty string disables the fallback.
    GROQ_DISCOVERY_FALLBACK_MODEL: str = "openai/gpt-oss-120b"
    # Posts evaluated by AI per user per local day (shared Groq token budget).
    DISCOVERY_DAILY_EVAL_LIMIT: int = Field(default=150, ge=1)
    TELEGRAM_BOT_TOKEN: str = ""
    JOBBI_PUBLIC_URL: str = "http://localhost:5174"

    @model_validator(mode="after")
    def _require_groq_api_key(self) -> "Settings":
        if not self.GROQ_API_KEY:
            raise ValueError(
                "GROQ_API_KEY is required. Set it in the environment or .env file."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
