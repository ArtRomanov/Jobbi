"""Plain data types shared by discovery fetchers, the pre-filter and the evaluator."""

from dataclasses import dataclass
from datetime import datetime

__all__ = ["RawPost"]


@dataclass(frozen=True, slots=True, kw_only=True)
class RawPost:
    """One post or job as read from a source, before any filtering or evaluation.

    `posted_at` is a naive datetime in UTC (the project stores naive UTC everywhere).
    """

    external_key: str
    url: str
    job_link: str | None
    title: str | None
    company: str | None
    text: str
    posted_at: datetime
