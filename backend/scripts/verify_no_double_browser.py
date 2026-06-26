"""Verify no duplicate browser / no 60s scheduler conflict with wait loop."""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import asyncio

from app.config import get_settings
from app.core.timezone import now_italy
from app.database import SessionLocal
from app.models import ProductPost, ProductStatus
from app.services.product_posting_service import (
    pick_next_scheduled,
    run_posting_cycle,
    scheduled_moment,
    should_run_marketplace_peek_on_start,
    has_saved_facebook_session_sync,
)


async def main() -> int:
    errors: list[str] = []
    cfg = get_settings()

    if not cfg.STOP_AFTER_MARKETPLACE:
        errors.append("STOP_AFTER_MARKETPLACE should be enabled for posting app")

    stats = await run_posting_cycle(1)
    if stats.get("status") != "loop_active":
        errors.append(f"run_posting_cycle must no-op in posting mode, got {stats}")

    db = SessionLocal()
    try:
        now = now_italy()
        today = now.strftime("%Y-%m-%d")
        grace_time = (now - timedelta(minutes=2)).strftime("%H:%M")
        future_time = (now + timedelta(minutes=5)).strftime("%H:%M")

        rows = (
            db.query(ProductPost)
            .filter(ProductPost.user_id == 1, ProductPost.status == ProductStatus.SCHEDULED)
            .limit(5)
            .all()
        )
        if len(rows) < 2:
            print("SKIP: need 2+ scheduled products in DB for pick test")
        else:
            rows[0].schedule_date = today
            rows[0].schedule_time = grace_time
            rows[1].schedule_date = today
            rows[1].schedule_time = future_time
            db.commit()

            nxt, due = pick_next_scheduled(db, 1, now)
            if not nxt or nxt.id != rows[1].id:
                errors.append("pick_next must choose FUTURE slot over grace-overdue")
            elif due and due <= now:
                errors.append("Future pick must return future due_at")

        peek = should_run_marketplace_peek_on_start(db, 1, None)
        has_cookies = has_saved_facebook_session_sync(1)
        has_sched = db.query(ProductPost).filter(
            ProductPost.user_id == 1, ProductPost.status == ProductStatus.SCHEDULED
        ).count() > 0
        if has_sched and has_cookies and peek:
            errors.append("Must NOT marketplace peek when scheduled + cookies exist")
        elif has_sched and not peek:
            print("OK: no peek when products scheduled")
    finally:
        db.close()

    if errors:
        print("FAILURES:")
        for e in errors:
            print(" -", e)
        return 1

    print("All anti-loop / future-first checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
