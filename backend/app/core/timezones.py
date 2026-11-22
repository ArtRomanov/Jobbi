"""IANA timezone validation shared by the API schemas and the Telegram bot.

Membership in `zoneinfo.available_timezones()` is used instead of trying
`ZoneInfo(name)`, because the constructor is a filesystem lookup: on Python
<3.13 a directory such as "America" raises IsADirectoryError, and on
case-insensitive filesystems (macOS) "europe/berlin" resolves locally but not
on Linux.
"""

from datetime import UTC, date, datetime, time, timedelta
from functools import cache
from zoneinfo import ZoneInfo, available_timezones

# Present in tzdata but not real places a user could live in.
_EXCLUDED_ZONES = frozenset({"Factory", "localtime", "posixrules"})


@cache
def valid_timezones() -> frozenset[str]:
    """All selectable IANA zone names (computed once; it scans the tz database)."""
    return frozenset(available_timezones()) - _EXCLUDED_ZONES


def is_valid_timezone(name: str) -> bool:
    return name in valid_timezones()


def zone_or_utc(name: str | None) -> ZoneInfo:
    """The user's zone, or UTC when unset or not a valid IANA name."""
    if name and is_valid_timezone(name):
        return ZoneInfo(name)
    return ZoneInfo("UTC")


def local_day_bounds(now: datetime, zone: ZoneInfo) -> tuple[date, datetime, datetime]:
    """The local date of `now` (naive UTC) in `zone` and that day's bounds.

    Returns `(local_date, start, end)` where `start`/`end` are naive UTC and the
    day is the half-open range `[start, end)`. DST days are 23 or 25 hours long.
    """
    local_date = now.replace(tzinfo=UTC).astimezone(zone).date()
    start = datetime.combine(local_date, time.min, tzinfo=zone)
    end = datetime.combine(local_date + timedelta(days=1), time.min, tzinfo=zone)
    return (
        local_date,
        start.astimezone(UTC).replace(tzinfo=None),
        end.astimezone(UTC).replace(tzinfo=None),
    )
