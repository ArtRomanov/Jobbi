"""IANA timezone validation shared by the API schemas and the Telegram bot.

Membership in `zoneinfo.available_timezones()` is used instead of trying
`ZoneInfo(name)`, because the constructor is a filesystem lookup: on Python
<3.13 a directory such as "America" raises IsADirectoryError, and on
case-insensitive filesystems (macOS) "europe/berlin" resolves locally but not
on Linux.
"""

from functools import cache
from zoneinfo import available_timezones

# Present in tzdata but not real places a user could live in.
_EXCLUDED_ZONES = frozenset({"Factory", "localtime", "posixrules"})


@cache
def valid_timezones() -> frozenset[str]:
    """All selectable IANA zone names (computed once; it scans the tz database)."""
    return frozenset(available_timezones()) - _EXCLUDED_ZONES


def is_valid_timezone(name: str) -> bool:
    return name in valid_timezones()
