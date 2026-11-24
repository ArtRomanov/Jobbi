"""Errors raised by the board fetchers, and the shared "blocked" text."""

from datetime import datetime
from typing import Literal

BoardErrorReason = Literal["not_found", "unreachable", "blocked"]

# Shown for a bot-protection challenge (reason `blocked`) by the API (preview,
# add, edit) and as the worker's Unavailable reason: one text everywhere.
BLOCKED_MESSAGE = "This site blocks automated readers"


class BoardReadError(Exception):
    """A job board could not be read.

    ``reason`` is ``"not_found"`` when the board does not exist (HTTP 404 or a
    handle that cannot be a valid board), ``"blocked"`` for a bot-protection
    challenge (403/429/503 with ``cf-mitigated: challenge``) and
    ``"unreachable"`` for everything else: network errors, timeouts, 429, 5xx,
    oversized or malformed responses.
    """

    def __init__(self, reason: BoardErrorReason) -> None:
        super().__init__(reason)
        self.reason: BoardErrorReason = reason


# Stand-in `posted_at` for a job whose listing carries no usable date. It is
# far in the past, so a dateless job always counts as OLD: an initial scan
# never turns it into a pending post (it is only recorded as seen).
UNKNOWN_POSTED_AT = datetime(1970, 1, 1)
