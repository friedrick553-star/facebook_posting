"""Random delay between monitoring cycles."""
from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone

from app.models import MonitoringSetting

logger = logging.getLogger(__name__)


def normalize_interval_bounds(monitoring: MonitoringSetting) -> tuple[int, int]:
    min_s = monitoring.refresh_interval_min_seconds or 30
    max_s = monitoring.refresh_interval_max_seconds or 45
    if min_s > max_s:
        min_s, max_s = max_s, min_s
    min_s = max(30, min_s)
    max_s = max(min_s, max_s)
    return min_s, max_s


def random_delay_seconds(monitoring: MonitoringSetting) -> int:
    min_s, max_s = normalize_interval_bounds(monitoring)
    return random.randint(min_s, max_s)


def schedule_next_scan(monitoring: MonitoringSetting, from_time: datetime | None = None) -> datetime:
    base = from_time or datetime.now(timezone.utc)
    delay = random_delay_seconds(monitoring)
    monitoring.next_scan_at = base + timedelta(seconds=delay)
    logger.info("Next monitoring cycle in %d sec (at %s)", delay, monitoring.next_scan_at.isoformat())
    return monitoring.next_scan_at
