from functools import lru_cache
from typing import Literal

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
    # Chat model (CV tailoring, tool edits). gpt-oss since 2026-11-25 (was
    # qwen/qwen3.8-27b): the same model as discovery's primary.
    GROQ_MODEL: str = "openai/gpt-oss-20b"
    # Cap on one chat reply (Groq max_tokens). gpt-oss counts its reasoning in
    # these tokens, so a low cap can leave the visible reply empty or cut.
    CHAT_MAX_TOKENS: int = Field(default=6000, ge=256)
    # How hard a gpt-oss chat model reasons before replying; other models get
    # no reasoning_effort at all (see app.core.llm_options).
    CHAT_REASONING_EFFORT: Literal["low", "medium", "high"] = "medium"
    # Groq checks input + max_tokens of each request against GROQ_MODEL's
    # tokens-per-minute limit and answers 413 above it (gpt-oss-20b free tier:
    # 8000). Each chat request is sized to fit: the history is trimmed and
    # max_tokens lowered (never under CHAT_MIN_REPLY_TOKENS) so that the input
    # estimate (+15% margin) + max_tokens <= this.
    CHAT_REQUEST_TOKEN_LIMIT: int = Field(default=8000, ge=2000)
    # Reply tokens a request always keeps (gpt-oss reasons inside them): older
    # history is left out before max_tokens goes below this.
    CHAT_MIN_REPLY_TOKENS: int = Field(default=2048, ge=256)
    # Upper bound on the estimated input of one chat request (system prompt
    # with CV and vacancy, history, tools schema), on top of the room
    # CHAT_REQUEST_TOKEN_LIMIT leaves (about 5175 at the defaults).
    CHAT_INPUT_TOKEN_BUDGET: int = Field(default=6500, ge=1000)
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
