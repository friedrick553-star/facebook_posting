import asyncio
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.db_async import run_sync
from app.services.monitoring_runner import run_async_in_thread
from app.services.monitoring_user import list_enabled_monitoring_user_ids
from app.services.monitoring_service import monitoring_service

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()
_monitor_lock = asyncio.Lock()
TICK_SECONDS = 60
_SCHEDULER_DB_TIMEOUT = 8.0


def _load_monitoring_row():
    from app.database import SessionLocal
    from app.models import MonitoringSetting

    db = SessionLocal()
    try:
        return db.query(MonitoringSetting).first()
    finally:
        db.close()


def _read_monitoring_enabled() -> bool:
    return bool(list_enabled_monitoring_user_ids())


async def check_product_posting_due():
    """Every minute: legacy fallback only when wait loop is not used."""
    from app.config import get_settings

    if get_settings().STOP_AFTER_MARKETPLACE:
        return

    from app.services.product_posting_service import run_posting_cycle

    for user_id in list_enabled_monitoring_user_ids():
        try:
            stats = await run_posting_cycle(user_id)
            if stats.get("published") or stats.get("failed"):
                logger.info("Product posting cycle user %s: %s", user_id, stats)
        except Exception as exc:
            logger.exception("Product posting cycle failed for user %s: %s", user_id, exc)


async def check_monitoring_due():
    if _monitor_lock.locked():
        return

    from app.services.monitoring_service import is_monitoring_busy

    if is_monitoring_busy():
        return

    async with _monitor_lock:
        try:
            from app.database import SessionLocal
            from app.models import MonitoringSetting

            def _load_due_rows():
                db = SessionLocal()
                try:
                    now = datetime.now(timezone.utc)
                    return (
                        db.query(MonitoringSetting)
                        .filter(
                            MonitoringSetting.is_enabled == True,
                            MonitoringSetting.is_scanning == False,
                        )
                        .all()
                    )
                finally:
                    db.close()

            rows = await run_sync(_load_due_rows, timeout=_SCHEDULER_DB_TIMEOUT)
        except asyncio.TimeoutError:
            logger.warning("Scheduler: database check timed out")
            return
        except Exception as exc:
            logger.warning("Scheduler: database check failed: %s", exc)
            return

        now = datetime.now(timezone.utc)
        from app.config import get_settings

        posting_app = get_settings().STOP_AFTER_MARKETPLACE
        for monitoring in rows:
            if posting_app and monitoring.is_enabled:
                continue
            if monitoring.next_scan_at is not None and now < monitoring.next_scan_at:
                continue
            if is_monitoring_busy():
                return

            logger.info(
                "Monitoring interval reached for user %s",
                monitoring.user_id,
            )

            async def _run_scheduled_scan(uid: int = monitoring.user_id) -> None:
                try:
                    await monitoring_service.run_scan(uid)
                except Exception as exc:
                    logger.exception("Scheduled monitoring scan failed: %s", exc)

            run_async_in_thread(_run_scheduled_scan, name=f"monitoring-scheduled-{monitoring.user_id}")
            return


async def resume_monitoring_on_startup():
    await asyncio.sleep(3)
    enabled_ids = list_enabled_monitoring_user_ids()
    if not enabled_ids:
        logger.info("Monitoring OFF — press Start on Dashboard")
        return

    from app.config import get_settings

    if get_settings().STOP_AFTER_MARKETPLACE:
        from app.services.product_posting_service import start_posting_loop

        for user_id in enabled_ids:
            logger.info("User %s bot was ON — resuming posting wait loop (no test flow repeat)", user_id)

            async def _resume_posting(uid: int = user_id) -> None:
                try:
                    await start_posting_loop(uid)
                except Exception as exc:
                    logger.exception("Startup posting loop failed for user %s: %s", uid, exc)

            run_async_in_thread(_resume_posting, name=f"posting-resume-{user_id}")
        return

    for user_id in enabled_ids:
        fb = monitoring_service.facebook(user_id)
        if fb.has_live_browser():
            logger.info("User %s monitoring ON — browser already open", user_id)
            continue
        logger.info("User %s monitoring was ON — resuming after server restart", user_id)

        async def _run_startup_scan(uid: int = user_id) -> None:
            try:
                await monitoring_service.run_scan(uid)
            except Exception as exc:
                logger.exception("Startup monitoring scan failed for user %s: %s", uid, exc)

        run_async_in_thread(_run_startup_scan, name=f"monitoring-startup-{user_id}")


def start_scheduler():
    try:
        is_enabled = _read_monitoring_enabled()
    except Exception as exc:
        logger.warning("Could not read monitoring settings for scheduler: %s", exc)
        is_enabled = False

    if not scheduler.running:
        scheduler.add_job(
            check_monitoring_due,
            trigger=IntervalTrigger(seconds=TICK_SECONDS),
            id="monitoring_check",
            replace_existing=True,
            max_instances=1,
        )
        scheduler.add_job(
            check_product_posting_due,
            trigger=IntervalTrigger(seconds=TICK_SECONDS),
            id="product_posting_check",
            replace_existing=True,
            max_instances=1,
        )
        scheduler.start()
        state = "ON" if is_enabled else "OFF — press Start"
        logger.info(
            "Scheduler started — monitoring + product posting every %ds (%s)",
            TICK_SECONDS,
            state,
        )


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
