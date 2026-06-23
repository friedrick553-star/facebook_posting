"""Per-user monitoring settings helpers."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import MonitoringSetting


def get_user_monitoring(db: Session, user_id: int) -> MonitoringSetting:
    row = db.query(MonitoringSetting).filter(MonitoringSetting.user_id == user_id).first()
    if not row:
        row = MonitoringSetting(
            user_id=user_id,
            is_enabled=False,
            refresh_interval_seconds=45,
            refresh_interval_min_seconds=30,
            refresh_interval_max_seconds=45,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def is_user_monitoring_enabled(user_id: int) -> bool:
    db = SessionLocal()
    try:
        row = db.query(MonitoringSetting).filter(MonitoringSetting.user_id == user_id).first()
        return bool(row and row.is_enabled)
    except Exception:
        return False
    finally:
        db.close()


def set_user_monitoring_enabled(user_id: int, enabled: bool) -> None:
    db = SessionLocal()
    try:
        row = get_user_monitoring(db, user_id)
        row.is_enabled = enabled
        if not enabled:
            row.is_scanning = False
            row.next_scan_at = None
        db.commit()
    except Exception:
        pass
    finally:
        db.close()


def list_enabled_monitoring_user_ids() -> list[int]:
    db = SessionLocal()
    try:
        rows = db.query(MonitoringSetting).filter(MonitoringSetting.is_enabled == True).all()
        return [r.user_id for r in rows]
    except Exception:
        return []
    finally:
        db.close()
