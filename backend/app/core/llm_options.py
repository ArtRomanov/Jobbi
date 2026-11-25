"""Per-model Groq request options shared by the chat and discovery calls."""

from typing import Literal

ReasoningEffort = Literal["low", "medium", "high"]

GPT_OSS_PREFIX = "openai/gpt-oss"


def is_gpt_oss(model: str) -> bool:
    """True for Groq's gpt-oss models (they reason before answering)."""
    return model.startswith(GPT_OSS_PREFIX)


def reasoning_options(model: str, effort: ReasoningEffort) -> dict[str, str]:
    """`reasoning_effort` for gpt-oss models, nothing for other models.

    Only gpt-oss takes these values; other model families either reject the
    parameter or give it another meaning.
    """
    if is_gpt_oss(model):
        return {"reasoning_effort": effort}
    return {}
