"""Single timezone for all product scheduling and Chromium — Italy (Europe/Rome)."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

# Marketplace client is in Italy — never use UTC or server local time for scheduling.
POSTING_TIMEZONE = "Europe/Rome"
POSTING_TZ = ZoneInfo(POSTING_TIMEZONE)


def now_italy() -> datetime:
    return datetime.now(POSTING_TZ)


def italy_now_iso() -> str:
    return now_italy().strftime("%Y-%m-%dT%H:%M:%S")


def italy_now_display() -> str:
    return now_italy().strftime("%d/%m/%Y %H:%M:%S")


def italy_utc_offset() -> str:
    """Current offset e.g. +02:00 (CEST) or +01:00 (CET)."""
    n = now_italy()
    offset = n.utcoffset()
    if offset is None:
        return "+00:00"
    total = int(offset.total_seconds())
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    hours, rem = divmod(total, 3600)
    minutes = rem // 60
    return f"{sign}{hours:02d}:{minutes:02d}"


def parse_schedule_datetime(schedule_date: str, schedule_time: str) -> datetime | None:
    """Build aware datetime in Europe/Rome from CSV/UI date + HH:MM."""
    if not schedule_date or not schedule_time:
        return None
    try:
        y, mo, d = map(int, schedule_date.split("-"))
        h, mi = map(int, schedule_time.split(":"))
        if not (0 <= h <= 23 and 0 <= mi <= 59):
            return None
        return datetime(y, mo, d, h, mi, 0, tzinfo=POSTING_TZ)
    except ValueError:
        return None
