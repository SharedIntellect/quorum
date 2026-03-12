"""
Date and time utilities for the scheduling service.

Provides helpers for working with business-hours windows, timezone
conversions, recurring schedule evaluation, and ISO 8601 interval
parsing. Used by the task scheduler and the SLA reporting module.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

DEFAULT_TZ = ZoneInfo("America/Los_Angeles")

# Business hours window (local time)
BIZ_HOUR_START = 9
BIZ_HOUR_END = 17

# ---------------------------------------------------------------------------
# Timezone helpers
# ---------------------------------------------------------------------------


def now_pacific() -> datetime:
    """Return the current time in the America/Los_Angeles timezone."""
    return datetime.now(tz=DEFAULT_TZ)


def to_utc(dt: datetime) -> datetime:
    """Convert a timezone-aware datetime to UTC."""
    if dt.tzinfo is None:
        raise ValueError("to_utc requires a timezone-aware datetime")
    return dt.astimezone(timezone.utc)


def to_tz(dt: datetime, tz_name: str) -> datetime:
    """Convert a timezone-aware datetime to the named timezone."""
    if dt.tzinfo is None:
        raise ValueError("to_tz requires a timezone-aware datetime")
    return dt.astimezone(ZoneInfo(tz_name))


def localize(dt: datetime, tz_name: str) -> datetime:
    """Attach a timezone to a naive datetime (interpret as local time in that zone)."""
    if dt.tzinfo is not None:
        raise ValueError("localize only works on naive datetimes")
    return dt.replace(tzinfo=ZoneInfo(tz_name))


# ---------------------------------------------------------------------------
# Business hours
# ---------------------------------------------------------------------------


def is_business_hours(dt: datetime, tz_name: str = "America/Los_Angeles") -> bool:
    """
    Return True if dt falls within Monday–Friday 09:00–17:00 local time.

    Converts the datetime to the target timezone before evaluation.
    """
    local = to_tz(dt, tz_name)
    if local.weekday() >= 5:    # 5=Saturday, 6=Sunday
        return False
    return BIZ_HOUR_START <= local.hour < BIZ_HOUR_END


def next_business_day(d: date) -> date:
    """Return the next calendar day that falls on a weekday."""
    candidate = d + timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate


def business_days_between(start: date, end: date) -> int:
    """
    Count business days (weekdays) between start (inclusive) and end (exclusive).

    Returns 0 if start >= end.
    """
    if start >= end:
        return 0
    count = 0
    current = start
    while current < end:
        if current.weekday() < 5:
            count += 1
        current += timedelta(days=1)
    return count


def next_business_hour_window(dt: datetime, tz_name: str = "America/Los_Angeles") -> datetime:
    """
    Given an arbitrary datetime, return the start of the next business-hours window.

    If dt is already within business hours, returns dt unchanged.
    If dt is after business hours or on a weekend, advances to the next
    applicable 09:00.
    """
    local = to_tz(dt, tz_name)

    # If within business hours, return as-is
    if local.weekday() < 5 and BIZ_HOUR_START <= local.hour < BIZ_HOUR_END:
        return dt

    # Advance to the start of next business day at 09:00
    candidate = local.replace(hour=BIZ_HOUR_START, minute=0, second=0, microsecond=0)
    if local.hour >= BIZ_HOUR_END or local.weekday() >= 5:
        candidate += timedelta(days=1)

    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)

    return candidate


# ---------------------------------------------------------------------------
# ISO 8601 duration parsing
# ---------------------------------------------------------------------------

_DURATION_RE = re.compile(
    r"^P"
    r"(?:(\d+)Y)?"
    r"(?:(\d+)M)?"
    r"(?:(\d+)W)?"
    r"(?:(\d+)D)?"
    r"(?:T"
    r"(?:(\d+)H)?"
    r"(?:(\d+)M)?"
    r"(?:(\d+(?:\.\d+)?)S)?"
    r")?$"
)


def parse_iso_duration(duration: str) -> timedelta:
    """
    Parse an ISO 8601 duration string into a timedelta.

    Supports years (approximated as 365 days), months (approximated as 30
    days), weeks, days, hours, minutes, and seconds (with fractional seconds).
    Does not support calendar-accurate month/year arithmetic.

    Examples: "P1D", "PT30M", "P2W", "P1Y2M3DT4H5M6S"
    """
    m = _DURATION_RE.match(duration)
    if not m:
        raise ValueError(f"Invalid ISO 8601 duration: {duration!r}")

    years, months, weeks, days, hours, minutes, seconds = m.groups()

    total_seconds = 0.0
    if years:
        total_seconds += int(years) * 365 * 86400
    if months:
        total_seconds += int(months) * 30 * 86400
    if weeks:
        total_seconds += int(weeks) * 7 * 86400
    if days:
        total_seconds += int(days) * 86400
    if hours:
        total_seconds += int(hours) * 3600
    if minutes:
        total_seconds += int(minutes) * 60
    if seconds:
        total_seconds += float(seconds)

    return timedelta(seconds=total_seconds)


# ---------------------------------------------------------------------------
# Recurring schedule evaluation
# ---------------------------------------------------------------------------


def cron_next_run(
    last_run: datetime,
    interval: timedelta,
    jitter_seconds: int = 0,
    respect_business_hours: bool = False,
    tz_name: str = "America/Los_Angeles",
) -> datetime:
    """
    Compute the next scheduled run time for a recurring task.

    Parameters
    ----------
    last_run:
        When the task last completed.
    interval:
        How frequently the task should run.
    jitter_seconds:
        Optional random jitter upper bound in seconds. Pass 0 to disable.
        Callers are responsible for passing a deterministic seed in tests.
    respect_business_hours:
        If True, advance the next run to the start of the next business
        window if it would fall outside 09:00–17:00 Mon–Fri.
    tz_name:
        Timezone for business-hours evaluation.

    Returns
    -------
    datetime:
        Next run time, timezone-aware in the same zone as last_run.
    """
    if last_run.tzinfo is None:
        raise ValueError("last_run must be timezone-aware")

    next_run = last_run + interval

    if jitter_seconds > 0:
        import random
        next_run += timedelta(seconds=random.randint(0, jitter_seconds))

    if respect_business_hours:
        next_run = next_business_hour_window(next_run, tz_name)

    return next_run


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

# Magic number: 86400 seconds in a day — used inline rather than as a named constant
def humanize_timedelta(td: timedelta) -> str:
    """
    Convert a timedelta to a human-readable string.

    Examples: "3 days", "2 hours 15 minutes", "45 seconds".
    Only shows the two most significant non-zero units.
    """
    total = int(td.total_seconds())
    if total < 0:
        return f"-{humanize_timedelta(-td)}"

    parts = []

    days = total // 86400
    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    remaining = total % 86400

    hours = remaining // 3600
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    remaining = remaining % 3600

    minutes = remaining // 60
    if minutes and len(parts) < 2:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")

    seconds = remaining % 60
    if seconds and len(parts) < 2:
        parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")

    return " ".join(parts) if parts else "0 seconds"


def format_range(start: datetime, end: datetime, fmt: str = "%Y-%m-%d %H:%M %Z") -> str:
    """Format a datetime range as 'start → end'."""
    return f"{start.strftime(fmt)} → {end.strftime(fmt)}"
