"""Plain data types shared by discovery fetchers, the pre-filter and the evaluator."""

from dataclasses import dataclass
from datetime import datetime

__all__ = ["MAX_LINK_CHARS", "PostLink", "RawPost"]

# Same bound as the job-link column.
MAX_LINK_CHARS = 2048


@dataclass(frozen=True, slots=True)
class PostLink:
    """An http(s) link of a post outside Telegram, normalized (`normalize_url`).

    `line` is the 1-based line of the post's stored text (split on "\\n") on
    which the link's visible text starts.
    """

    line: int
    url: str


@dataclass(frozen=True, slots=True, kw_only=True)
class RawPost:
    """One post or job as read from a source, before any filtering or evaluation.

    `posted_at` is a naive datetime in UTC (the project stores naive UTC everywhere).
    `links` are the post's outside links with their lines in `text` (Telegram
    sources only; empty for boards).
    """

    external_key: str
    url: str
    job_link: str | None
    title: str | None
    company: str | None
    text: str
    posted_at: datetime
    links: tuple[PostLink, ...] = ()
