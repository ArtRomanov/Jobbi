"""Errors raised by the Greenhouse / Lever board fetchers."""

from datetime import datetime
from typing import Literal

BoardErrorReason = Literal["not_found", "unreachable"]


class BoardReadError(Exception):
    """A job board could not be read.

    ``reason`` is ``"not_found"`` when the board does not exist (HTTP 404 or a
    handle that cannot be a valid board) and ``"unreachable"`` for everything
    else: network errors, timeouts, 429, 5xx, oversized or malformed responses.
    """

    def __init__(self, reason: BoardErrorReason) -> None:
        super().__init__(reason)
        self.reason: BoardErrorReason = reason


# Stand-in `posted_at` for a job whose listing carries no usable date. It is
# far in the past, so a dateless job always counts as OLD: an initial scan
# never turns it into a pending post (it is only recorded as seen).
UNKNOWN_POSTED_AT = datetime(1970, 1, 1)
