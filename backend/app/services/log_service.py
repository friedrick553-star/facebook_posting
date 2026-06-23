import json
import logging

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import ActivityLog, LogCategory, LogLevel

logger = logging.getLogger(__name__)


def log_activity(
    db: Session,
    category: LogCategory,
    message: str,
    level: LogLevel = LogLevel.INFO,
    details: dict | None = None,
    source: str | None = None,
) -> ActivityLog:
    entry = ActivityLog(
        category=category,
        level=level,
        message=message,
        details=json.dumps(details) if details else None,
        source=source,
    )
    try:
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry
    except Exception:
        db.rollback()
        raise


def log_activity_isolated(
    category: LogCategory,
    message: str,
    level: LogLevel = LogLevel.INFO,
    details: dict | None = None,
    source: str | None = None,
) -> None:
    """Write a log on a fresh DB connection (safe during long browser waits)."""
    db = SessionLocal()
    try:
        log_activity(db, category, message, level=level, details=details, source=source)
    except Exception as exc:
        logger.warning("Activity log write failed: %s", exc)
    finally:
        db.close()
