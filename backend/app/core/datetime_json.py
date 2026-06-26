"""API datetimes from SQLite are UTC without tzinfo — serialize with offset for clients."""
from __future__ import annotations

from datetime import datetime, timezone


def as_utc_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def serialize_api_datetime(dt: datetime | None) -> str | None:
    aware = as_utc_aware(dt)
    if aware is None:
        return None
    return aware.isoformat()
