"""Scheduled + retry publishing of ProductPost rows to Facebook Marketplace."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from app.core.timezone import (
    POSTING_TIMEZONE,
    POSTING_TZ,
    italy_now_display,
    italy_now_iso,
    italy_utc_offset,
    now_italy,
    parse_schedule_datetime,
)
import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models import LogCategory, LogLevel, ProductPost, ProductStatus
from app.services.facebook_posting_flow import ProductListingPayload, publish_marketplace_item
from app.services.facebook_session import dismiss_login_popup_once, is_login_fully_complete, save_session
from app.services.log_service import log_activity, log_activity_isolated
from app.services.facebook_source_registry import get_facebook_source
from app.services.monitoring_user import is_user_monitoring_enabled, list_enabled_monitoring_user_ids
from app.services.user_workspace import reset_workspace_user_id, set_workspace_user_id

logger = logging.getLogger(__name__)

MAX_RETRIES = 5
REFRESH_BEFORE_SEC = 3.5
# After scheduled minute: bot may open Chromium, publish, retry — only then mark Failed
PUBLISH_GRACE_AFTER_SEC = 300.0
IDLE_POLL_SEC = 2.0
POST_PUBLISH_STAY_SEC = 12.0
TEST_PUBLISH_SCREEN_SEC = 5.5
MARKETPLACE_PEEK_SEC = 10.0

WEEKDAY_CODES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

_posting_thread_lock = threading.Lock()
_posting_loop_tasks: dict[int, asyncio.Task] = {}
_posting_loop_cancel: dict[int, asyncio.Event] = {}
_posting_loop_active: set[int] = set()
_posting_state_lock = threading.Lock()
_test_full_flow_done: set[int] = set()
# Dry-run session skip — track ids already published this bot session to avoid re-posting.
_session_posted_ids: dict[int, set[int]] = {}


TEST_FULL_FLOW_IMAGE_URLS = [
    "https://images.pexels.com/photos/276517/pexels-photo-276517.jpeg?auto=compress&cs=tinysrgb&w=400",
    "https://images.pexels.com/photos/100582/pexels-photo-100582.jpeg?auto=compress&cs=tinysrgb&w=400",
]


def _test_bicycle_payload(image_paths: list[str]) -> ProductListingPayload:
    return ProductListingPayload(
        title="Bicicletta elettrica City",
        description=(
            "Bicicletta elettrica pieghevole, batteria 36V, autonomia 60km. "
            "Ottime condizioni, ideale per città."
        ),
        price=450.0,
        currency="EUR",
        image_paths=image_paths,
        category="Bicycles",
        condition="new",
        availability="single",
        extra_details={"Brand": "City", "Model": "Fold Pro", "Color": "Nero"},
    )


def mark_session_posted(user_id: int, product_id: int) -> None:
    _session_posted_ids.setdefault(user_id, set()).add(product_id)


def clear_session_posted(user_id: int) -> None:
    _session_posted_ids.pop(user_id, None)


def unmark_session_posted(user_id: int, product_id: int) -> None:
    posted = _session_posted_ids.get(user_id)
    if posted is not None:
        posted.discard(product_id)


def is_posting_loop_active(user_id: int) -> bool:
    with _posting_state_lock:
        if user_id in _posting_loop_active:
            return True
    task = _posting_loop_tasks.get(user_id)
    return task is not None and not task.done()


def _set_posting_loop_active(user_id: int, active: bool) -> None:
    with _posting_state_lock:
        if active:
            _posting_loop_active.add(user_id)
        else:
            _posting_loop_active.discard(user_id)


def is_test_full_flow_done(user_id: int) -> bool:
    return user_id in _test_full_flow_done


def mark_test_full_flow_done(user_id: int) -> None:
    _test_full_flow_done.add(user_id)


def clear_test_full_flow_session(user_id: int) -> None:
    _test_full_flow_done.discard(user_id)


def _session_skip_ids(user_id: int) -> set[int]:
    return _session_posted_ids.get(user_id, set())


def _now_local() -> datetime:
    return now_italy()


def _day_code_to_weekday(code: str) -> int | None:
    key = (code or "").lower()[:3]
    if key not in WEEKDAY_CODES:
        return None
    return WEEKDAY_CODES.index(key)


def _parse_time_parts(time_str: str) -> tuple[int, int] | None:
    try:
        h, m = map(int, (time_str or "").split(":"))
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h, m
    except ValueError:
        pass
    return None


def scheduled_moment(product: ProductPost) -> datetime | None:
    """Italy-local datetime when this product is scheduled to publish."""
    if not product.schedule_time:
        return None
    parts = _parse_time_parts(product.schedule_time)
    if parts is None:
        return None
    h, m = parts

    if product.schedule_date:
        return parse_schedule_datetime(product.schedule_date, product.schedule_time)

    # Legacy weekday scheduling (pre schedule_date migration)
    if not product.schedule_day:
        return None
    target_wd = _day_code_to_weekday(product.schedule_day)
    if target_wd is None:
        return None
    now = _now_local()
    candidate = now.replace(hour=h, minute=m, second=0, microsecond=0)
    days_ahead = (target_wd - now.weekday()) % 7
    if days_ahead == 0 and candidate <= now:
        return candidate
    return candidate + timedelta(days=days_ahead)


def _publish_grace_deadline(moment: datetime) -> datetime:
    return moment + timedelta(seconds=PUBLISH_GRACE_AFTER_SEC)


def _is_within_publish_window(moment: datetime | None, now: datetime) -> bool:
    """True from ~REFRESH_BEFORE before due until PUBLISH_GRACE_AFTER after due."""
    if moment is None:
        return False
    window_start = moment - timedelta(seconds=REFRESH_BEFORE_SEC + 1.0)
    return window_start <= now <= _publish_grace_deadline(moment)


def _is_actionable_schedule(moment: datetime | None, now: datetime) -> bool:
    """Bot can still open Chromium / publish (future slot or overdue within grace)."""
    if moment is None:
        return False
    return now <= _publish_grace_deadline(moment)


def _is_future_schedule(moment: datetime | None, now: datetime) -> bool:
    return moment is not None and moment > now


def _session_blocks_pick(user_id: int, product_id: int, moment: datetime | None, now: datetime) -> bool:
    """Already published this session — never block a future slot; only skip after due window ended."""
    if product_id not in _session_skip_ids(user_id):
        return False
    if moment is None:
        return True
    if moment > now:
        return False
    if _is_within_publish_window(moment, now):
        return False
    return True


def reset_publishing_on_bot_start(db: Session, user_id: int) -> int:
    """Clear rows stuck in PUBLISHING from a prior interrupted session when bot starts."""
    rows = (
        db.query(ProductPost)
        .filter(
            ProductPost.user_id == user_id,
            ProductPost.status == ProductStatus.PUBLISHING,
        )
        .all()
    )
    if not rows:
        return 0
    for product in rows:
        if product.schedule_date or product.schedule_day:
            product.status = ProductStatus.SCHEDULED
            product.error_message = None
        else:
            product.status = ProductStatus.FAILED
            product.error_message = "Previous publish was interrupted — set schedule and retry."
        unmark_session_posted(user_id, product.id)
    db.commit()
    return len(rows)


def count_queued_scheduled(db: Session, user_id: int, exclude_id: int) -> int:
    """Other scheduled products waiting — published one-by-one after the current one."""
    return (
        db.query(ProductPost)
        .filter(
            ProductPost.user_id == user_id,
            ProductPost.status == ProductStatus.SCHEDULED,
            ProductPost.id != exclude_id,
        )
        .count()
    )


def mark_past_schedules_missed(db: Session, user_id: int, now: datetime | None = None) -> int:
    """Move scheduled slots to FAILED only after publish grace expired (bot had time to run)."""
    now = now or _now_local()
    moved = 0

    legacy = (
        db.query(ProductPost)
        .filter(
            ProductPost.user_id == user_id,
            ProductPost.status == ProductStatus.MISSED,
        )
        .all()
    )
    for product in legacy:
        product.status = ProductStatus.FAILED
        if not product.error_message:
            moment = scheduled_moment(product)
            if moment:
                product.error_message = (
                    f"Missed scheduled time ({moment.strftime('%d/%m/%Y %H:%M')} Italy)"
                )
        moved += 1

    rows = (
        db.query(ProductPost)
        .filter(
            ProductPost.user_id == user_id,
            ProductPost.status == ProductStatus.SCHEDULED,
        )
        .all()
    )
    for product in rows:
        moment = scheduled_moment(product)
        if moment is None or now <= _publish_grace_deadline(moment):
            continue
        product.status = ProductStatus.FAILED
        product.error_message = (
            f"Missed scheduled time ({moment.strftime('%d/%m/%Y %H:%M')} Italy)"
        )
        moved += 1
    if moved:
        db.commit()
        log_activity(
            db,
            LogCategory.MONITORING,
            f"Moved {moved} past schedule(s) to Failed — set a new date/time to retry",
            details={"user_id": user_id, "count": moved},
            source="posting",
        )
        db.commit()
    return moved


def expire_stale_scheduled(db: Session, user_id: int, now: datetime | None = None) -> int:
    """Backward-compatible alias — past slots go to FAILED."""
    return mark_past_schedules_missed(db, user_id, now)


def _is_due(product: ProductPost, now: datetime) -> bool:
    if product.status != ProductStatus.SCHEDULED:
        return False
    moment = scheduled_moment(product)
    if moment is None:
        return False
    return moment <= now <= _publish_grace_deadline(moment)


def next_due_moment(product: ProductPost, now: datetime) -> datetime | None:
    """Italy-local datetime when this scheduled product becomes due."""
    if product.status != ProductStatus.SCHEDULED:
        return None
    return scheduled_moment(product)


def pick_next_scheduled(db: Session, user_id: int, now: datetime) -> tuple[ProductPost | None, datetime | None]:
    """Next product: earliest FUTURE slot first; overdue-in-grace only if no future left."""
    candidates = (
        db.query(ProductPost)
        .filter(
            ProductPost.user_id == user_id,
            ProductPost.status == ProductStatus.SCHEDULED,
            ProductPost.retry_count < MAX_RETRIES,
        )
        .all()
    )

    best_future: ProductPost | None = None
    best_future_moment: datetime | None = None
    best_grace: ProductPost | None = None
    best_grace_moment: datetime | None = None

    for product in candidates:
        moment = scheduled_moment(product)
        if not _is_actionable_schedule(moment, now):
            continue
        if _session_blocks_pick(user_id, product.id, moment, now):
            continue
        if moment > now:
            if best_future_moment is None or moment < best_future_moment:
                best_future = product
                best_future_moment = moment
        elif moment <= now:
            if best_grace_moment is None or moment < best_grace_moment:
                best_grace = product
                best_grace_moment = moment

    if best_future is not None and best_future_moment is not None:
        return best_future, best_future_moment
    if best_grace is not None and best_grace_moment is not None:
        return best_grace, best_grace_moment
    return None, None


def seconds_until_next_chromium_open(db: Session, user_id: int, now: datetime | None = None) -> float | None:
    """Seconds until REFRESH_BEFORE opens Chromium for the next actionable slot."""
    now = now or _now_local()
    product, due_at = pick_next_scheduled(db, user_id, now)
    if not product or not due_at:
        return None
    open_at = due_at - timedelta(seconds=REFRESH_BEFORE_SEC)
    return max(0.0, (open_at - now).total_seconds())


def get_due_products(db: Session, user_id: int, *, limit: int = 5) -> list[ProductPost]:
    now = _now_local()
    candidates = (
        db.query(ProductPost)
        .filter(
            ProductPost.user_id == user_id,
            ProductPost.status.in_([ProductStatus.SCHEDULED, ProductStatus.PENDING]),
            ProductPost.retry_count < MAX_RETRIES,
        )
        .order_by(ProductPost.id.asc())
        .limit(50)
        .all()
    )
    due = [
        p
        for p in candidates
        if not _session_blocks_pick(user_id, p.id, scheduled_moment(p), now) and _is_due(p, now)
    ]
    due.sort(key=lambda p: scheduled_moment(p) or now)
    return due[:limit]


async def _download_images(urls: list[str]) -> list[str]:
    paths: list[str] = []
    tmp = Path(tempfile.mkdtemp(prefix="fb_post_"))
    async with httpx.AsyncClient(timeout=45, follow_redirects=True) as client:
        for i, url in enumerate(urls[:10]):
            if not url or not url.startswith("http"):
                continue
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                ext = ".jpg"
                ct = (resp.headers.get("content-type") or "").lower()
                if "png" in ct:
                    ext = ".png"
                elif "webp" in ct:
                    ext = ".webp"
                path = tmp / f"photo_{i}{ext}"
                path.write_bytes(resp.content)
                paths.append(str(path))
            except Exception as exc:
                logger.warning("Image download failed %s: %s", url[:80], exc)
    if not paths:
        raise RuntimeError("Could not download any product images")
    return paths


def _images_from_product(product: ProductPost) -> list[str]:
    try:
        parsed = json.loads(product.images or "[]")
        return [u for u in parsed if isinstance(u, str) and u.strip()]
    except json.JSONDecodeError:
        return []


def _extra_details_from_product(product: ProductPost) -> dict[str, str]:
    try:
        parsed = json.loads(product.extra_details or "{}")
        if isinstance(parsed, dict):
            return {str(k): str(v) for k, v in parsed.items() if v is not None and str(v).strip()}
    except json.JSONDecodeError:
        pass
    return {}


async def _refresh_marketplace(user_id: int) -> None:
    """Refresh Marketplace feed a few seconds before the scheduled post time."""
    from app.services.facebook_flow import stage_open_marketplace

    cfg = get_settings()
    fb = get_facebook_source(user_id)
    if not fb.has_live_browser() or not fb._page or not fb._context:
        return

    page = fb._page
    context = fb._context
    token = set_workspace_user_id(user_id)
    try:

        def log(msg: str, details: dict | None = None) -> None:
            logger.info("%s %s", msg, details or {})

        log_activity_isolated(
            LogCategory.MONITORING,
            f"Refreshing Marketplace ({REFRESH_BEFORE_SEC}s before scheduled post)",
            source="posting",
        )
        await stage_open_marketplace(page, cfg, log, context=context)
        await dismiss_login_popup_once(page)
        await save_session(context, cfg)
    except Exception as exc:
        logger.warning("Marketplace refresh failed: %s", exc)
    finally:
        reset_workspace_user_id(token)


def has_scheduled_products(db: Session, user_id: int) -> bool:
    """True when user has at least one slot the bot can still act on."""
    now = _now_local()
    candidates = (
        db.query(ProductPost)
        .filter(
            ProductPost.user_id == user_id,
            ProductPost.status == ProductStatus.SCHEDULED,
            ProductPost.retry_count < MAX_RETRIES,
        )
        .limit(100)
        .all()
    )
    for p in candidates:
        moment = scheduled_moment(p)
        if _is_actionable_schedule(moment, now) and not _session_blocks_pick(user_id, p.id, moment, now):
            return True
    return False


def should_run_marketplace_peek_on_start(db: Session, user_id: int, monitoring) -> bool:
    """Peek on Start only when no demo, no scheduled work, and no saved Facebook cookies."""
    if monitoring and getattr(monitoring, "test_full_flow", False):
        if not is_test_full_flow_done(user_id):
            return False
    if has_scheduled_products(db, user_id):
        return False
    if has_saved_facebook_session_sync(user_id):
        return False
    return True


def has_saved_facebook_session_sync(user_id: int) -> bool:
    from app.services.facebook_session import has_facebook_session_saved

    cfg = get_settings()
    token = set_workspace_user_id(user_id)
    try:
        return has_facebook_session_saved(cfg)
    finally:
        reset_workspace_user_id(token)


async def run_marketplace_peek_on_start(user_id: int, db: Session | None = None) -> None:
    """Idle Start — open Marketplace, stay ~10s, close (no scheduled products, no demo)."""
    cfg = get_settings()
    own_db = db is None
    if own_db:
        db = SessionLocal()

    try:
        log_activity(
            db,
            LogCategory.MONITORING,
            f"Start — opening Marketplace (no scheduled products), closing in {MARKETPLACE_PEEK_SEC:.0f}s",
            details={"user_id": user_id, "tz": POSTING_TIMEZONE, "italy_now": _now_local().isoformat()},
            source="posting",
        )
        db.commit()
        await _open_browser_for_user(user_id, wait_for_login=False)
        fb = get_facebook_source(user_id)
        if fb.has_live_browser() and fb._page and fb._context:
            token = set_workspace_user_id(user_id)
            try:
                from app.services.facebook_flow import stage_open_marketplace

                def log(msg: str, details: dict | None = None) -> None:
                    logger.info("%s %s", msg, details or {})

                await stage_open_marketplace(fb._page, cfg, log, context=fb._context)
                await dismiss_login_popup_once(fb._page)
                await save_session(fb._context, cfg)
            finally:
                reset_workspace_user_id(token)
        log_activity(
            db,
            LogCategory.MONITORING,
            f"Marketplace open — waiting {MARKETPLACE_PEEK_SEC:.0f}s then closing Chromium",
            source="posting",
        )
        db.commit()
        await _close_browser_for_user(user_id, wait_sec=MARKETPLACE_PEEK_SEC)
        log_activity(
            db,
            LogCategory.MONITORING,
            "Marketplace peek complete — Chromium closed",
            source="posting",
        )
        db.commit()
    finally:
        if own_db and db:
            db.close()


async def prepare_browser_on_bot_start(user_id: int, db: Session) -> None:
    """Legacy alias — use run_marketplace_peek_on_start for idle Start."""
    await run_marketplace_peek_on_start(user_id, db)


async def _open_browser_for_user(user_id: int, *, wait_for_login: bool = True) -> None:
    fb = get_facebook_source(user_id)
    if fb.has_live_browser() and wait_for_login:
        return
    token = set_workspace_user_id(user_id)
    try:
        await fb.open_marketplace_browser(wait_for_login=wait_for_login)
    finally:
        reset_workspace_user_id(token)


async def _close_browser_for_user(user_id: int, *, wait_sec: float = 0) -> None:
    if wait_sec > 0:
        await asyncio.sleep(wait_sec)
    fb = get_facebook_source(user_id)
    if not fb.has_live_browser():
        return
    token = set_workspace_user_id(user_id)
    try:
        await fb.save_session_and_release()
    finally:
        reset_workspace_user_id(token)


async def publish_product(
    db: Session,
    product: ProductPost,
    *,
    return_to_marketplace: bool = False,
) -> None:
    cfg = get_settings()

    await _open_browser_for_user(product.user_id)
    fb = get_facebook_source(product.user_id)

    assert fb._page and fb._context
    page = fb._page
    context = fb._context

    token = set_workspace_user_id(product.user_id)
    try:
        def log(msg: str, details: dict | None = None) -> None:
            log_activity(
                db,
                LogCategory.MONITORING,
                msg,
                details={"product_id": product.id, **(details or {})},
                source="posting",
            )

        if not await is_login_fully_complete(context, page):
            from app.services.facebook_flow import stage_ensure_login

            log("Waiting for Facebook login before scheduled publish")
            if not await stage_ensure_login(page, context, cfg, log, db):
                raise RuntimeError("Facebook not logged in — complete login in Chromium")

        image_urls = _images_from_product(product)
        image_paths = await _download_images(image_urls)

        verify_only = os.getenv("VERIFY_PUBLISH_SCREEN_ONLY", "").lower() in ("1", "true", "yes")

        product.status = ProductStatus.PUBLISHING
        db.commit()

        try:
            listing_url = await publish_marketplace_item(
                page,
                ProductListingPayload(
                    title=product.name,
                    description=product.description or product.name,
                    price=product.price,
                    currency=product.currency or "EUR",
                    image_paths=image_paths,
                    category=product.category,
                    condition=product.condition or "new",
                    availability=product.availability or "single",
                    extra_details=_extra_details_from_product(product),
                ),
                cfg,
                context=context,
                log_fn=log,
                skip_publish=verify_only,
                stop_after_first_next=verify_only,
                fill_extra_details=True,
                return_to_marketplace_after=return_to_marketplace,
            )
            if verify_only:
                product.status = ProductStatus.SCHEDULED
                product.error_message = None
                db.commit()
                mark_session_posted(product.user_id, product.id)
                log_activity(
                    db,
                    LogCategory.MONITORING,
                    f"Publish button FOUND on audience screen — NOT clicked (verify test): {product.name[:60]}",
                    details={"product_id": product.id, "url": listing_url, "verify_only": True},
                    source="posting",
                )
                return
            product.status = ProductStatus.PUBLISHED
            product.facebook_url = listing_url
            product.published_at = datetime.now(timezone.utc)
            product.error_message = None
            db.commit()
            mark_session_posted(product.user_id, product.id)
            log_activity(
                db,
                LogCategory.MONITORING,
                f"Published to Marketplace: {product.name[:60]}",
                details={"product_id": product.id, "url": listing_url},
                source="posting",
            )
        except Exception as exc:
            product.status = ProductStatus.FAILED
            product.error_message = str(exc)[:2000]
            product.retry_count += 1
            db.commit()
            log_activity(
                db,
                LogCategory.ERROR,
                f"Publish failed: {product.name[:60]} — {exc}",
                level=LogLevel.ERROR,
                details={"product_id": product.id},
                source="posting",
            )
            raise
        finally:
            try:
                await save_session(context, cfg)
            except Exception:
                pass
    finally:
        reset_workspace_user_id(token)


async def run_test_full_flow(user_id: int, db: Session | None = None) -> None:
    """
    Settings → Test full flow: demo bicycle to Publish screen, stay ~5s, close Chromium.
    Runs once per Start — not repeated until Stop then Start again.
    """
    if is_test_full_flow_done(user_id):
        if db:
            log_activity(
                db,
                LogCategory.MONITORING,
                "Test full flow already completed this session — waiting for scheduled products",
                source="posting",
            )
            db.commit()
        return

    from app.services.facebook_flow import stage_ensure_login

    cfg = get_settings()
    await _open_browser_for_user(user_id, wait_for_login=False)
    fb = get_facebook_source(user_id)
    assert fb._page and fb._context

    page = fb._page
    context = fb._context
    own_db = db is None
    if own_db:
        db = SessionLocal()

    token = set_workspace_user_id(user_id)
    try:
        def log(msg: str, details: dict | None = None) -> None:
            log_activity(
                db,
                LogCategory.MONITORING,
                msg,
                details={"test_full_flow": True, **(details or {})},
                source="posting",
            )

        if not await is_login_fully_complete(context, page):
            log("Test full flow — waiting for Facebook login (dismiss popup, use top header)")
            if not await stage_ensure_login(page, context, cfg, log, db):
                log("Test full flow paused — complete Facebook login in Chromium, then press Start again")
                return

        image_paths = await _download_images(TEST_FULL_FLOW_IMAGE_URLS)
        payload = _test_bicycle_payload(image_paths)

        log("Test full flow — Bicicletta elettrica City (demo, not from CSV)")
        await publish_marketplace_item(
            page,
            payload,
            cfg,
            context=context,
            log_fn=log,
            skip_publish=True,
            stop_after_first_next=True,
            fill_extra_details=True,
            return_to_marketplace_after=False,
        )
        log(
            f"Test full flow — Publish screen reached, waiting {TEST_PUBLISH_SCREEN_SEC}s then closing Chromium",
        )
        await _close_browser_for_user(user_id, wait_sec=TEST_PUBLISH_SCREEN_SEC)
        log("Test full flow complete — Chromium closed (Pubblica NOT clicked)")
        mark_test_full_flow_done(user_id)
    finally:
        reset_workspace_user_id(token)
        if own_db and db:
            db.close()


async def _sleep_until(cancel: asyncio.Event, target: datetime) -> bool:
    """Sleep until target (Italy local). Returns False if cancelled."""
    while not cancel.is_set():
        remain = (target - _now_local()).total_seconds()
        if remain <= 0:
            return True
        await asyncio.sleep(min(remain, 1.0))
    return False


async def _posting_wait_loop(user_id: int, cancel: asyncio.Event) -> None:
    """Wait for schedule time — open Chromium, publish, stay ~12s, close. Bot stays ON."""
    cfg = get_settings()
    _set_posting_loop_active(user_id, True)
    log_activity_isolated(
        LogCategory.MONITORING,
        "Bot ON — waiting for scheduled product time (Chromium opens ~3.5s before due, Italy time)",
        details={"user_id": user_id, "locale": cfg.BROWSER_LOCALE, "tz": POSTING_TIMEZONE},
        source="posting",
    )

    try:
        while not cancel.is_set():
            if not is_user_monitoring_enabled(user_id):
                break

            db = SessionLocal()
            try:
                now = _now_local()
                mark_past_schedules_missed(db, user_id, now)
                product, due_at = pick_next_scheduled(db, user_id, now)

                if not product or due_at is None:
                    fb = get_facebook_source(user_id)
                    if fb.has_live_browser() and fb._page and fb._context:
                        try:
                            if await is_login_fully_complete(fb._context, fb._page):
                                await save_session(fb._context, cfg)
                        except Exception:
                            pass
                    wait_sec = seconds_until_next_chromium_open(db, user_id, now)
                    if wait_sec is not None:
                        if wait_sec > 5:
                            await asyncio.sleep(min(wait_sec - 1.0, 30.0))
                        else:
                            await asyncio.sleep(max(0.5, wait_sec))
                    else:
                        await asyncio.sleep(IDLE_POLL_SEC)
                    continue

                open_at = due_at - timedelta(seconds=REFRESH_BEFORE_SEC)
                log_activity_isolated(
                    LogCategory.MONITORING,
                    f"Next post: {product.name[:50]} at {due_at.strftime('%d/%m/%Y %H:%M')} Italy "
                    f"(now Italy {now.strftime('%d/%m/%Y %H:%M:%S')}, Chromium ~{REFRESH_BEFORE_SEC}s before)",
                    details={
                        "product_id": product.id,
                        "schedule_date": product.schedule_date,
                        "schedule_time": product.schedule_time,
                        "due_at_italy": due_at.isoformat(),
                        "italy_now": now.isoformat(),
                        "chromium_opens_at": open_at.isoformat(),
                        "timezone": POSTING_TIMEZONE,
                    },
                    source="posting",
                )
                if open_at > now:
                    if not await _sleep_until(cancel, open_at):
                        break
                    if cancel.is_set() or not is_user_monitoring_enabled(user_id):
                        break
                    await _open_browser_for_user(user_id)
                    await _refresh_marketplace(user_id)
                    if due_at > _now_local():
                        if not await _sleep_until(cancel, due_at):
                            break
                else:
                    log_activity_isolated(
                        LogCategory.MONITORING,
                        f"Due now (within grace) — opening Chromium for {product.name[:50]}",
                        details={"product_id": product.id},
                        source="posting",
                    )
                    await _open_browser_for_user(user_id)
                    await _refresh_marketplace(user_id)

                if cancel.is_set() or not is_user_monitoring_enabled(user_id):
                    break

                fresh = db.query(ProductPost).filter(ProductPost.id == product.id).first()
                if not fresh or fresh.status != ProductStatus.SCHEDULED:
                    continue

                queued = count_queued_scheduled(db, user_id, fresh.id)
                if queued:
                    log_activity_isolated(
                        LogCategory.MONITORING,
                        f"Queue: {queued} more scheduled product(s) — will publish after this one finishes",
                        details={"user_id": user_id, "current_product_id": fresh.id, "queued": queued},
                        source="posting",
                    )

                try:
                    with _posting_thread_lock:
                        await publish_product(db, fresh, return_to_marketplace=False)
                    log_activity_isolated(
                        LogCategory.MONITORING,
                        f"Published — waiting {POST_PUBLISH_STAY_SEC}s then closing Chromium",
                        details={"product_id": fresh.id},
                        source="posting",
                    )
                    await _close_browser_for_user(user_id, wait_sec=POST_PUBLISH_STAY_SEC)
                except Exception as exc:
                    logger.exception("Scheduled publish failed user %s: %s", user_id, exc)
                    fresh = db.query(ProductPost).filter(ProductPost.id == product.id).first()
                    if fresh and fresh.status == ProductStatus.PUBLISHING:
                        fresh.status = ProductStatus.FAILED
                        fresh.error_message = str(exc)[:2000]
                        db.commit()
                    log_activity_isolated(
                        LogCategory.ERROR,
                        f"Scheduled posting error: {exc}",
                        level=LogLevel.ERROR,
                        details={"user_id": user_id, "product_id": product.id},
                        source="posting",
                    )
                    await _close_browser_for_user(user_id, wait_sec=5.0)
                    await asyncio.sleep(IDLE_POLL_SEC)
            except asyncio.CancelledError:
                raise
            finally:
                db.close()
    except asyncio.CancelledError:
        log_activity_isolated(
            LogCategory.MONITORING,
            "Posting scheduler stopped",
            details={"user_id": user_id},
            source="posting",
        )
        raise
    finally:
        _set_posting_loop_active(user_id, False)


async def start_posting_loop(user_id: int) -> None:
    """Run until bot OFF — must await so the monitoring thread stays alive."""
    db = SessionLocal()
    try:
        reset_publishing_on_bot_start(db, user_id)
    finally:
        db.close()
    await stop_posting_loop(user_id)
    cancel = asyncio.Event()
    _posting_loop_cancel[user_id] = cancel
    task = asyncio.create_task(
        _posting_wait_loop(user_id, cancel),
        name=f"posting-loop-{user_id}",
    )
    _posting_loop_tasks[user_id] = task
    try:
        await task
    except asyncio.CancelledError:
        pass


async def stop_posting_loop(user_id: int) -> None:
    cancel = _posting_loop_cancel.pop(user_id, None)
    task = _posting_loop_tasks.pop(user_id, None)
    if cancel:
        cancel.set()
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    clear_session_posted(user_id)
    clear_test_full_flow_session(user_id)


async def run_posting_cycle(user_id: int) -> dict:
    """Legacy 60s tick — disabled when wait loop handles posting (STOP_AFTER_MARKETPLACE)."""
    cfg = get_settings()
    if cfg.STOP_AFTER_MARKETPLACE or is_posting_loop_active(user_id):
        return {"status": "loop_active", "published": 0, "failed": 0, "skipped": 0}

    if _posting_thread_lock.locked():
        return {"status": "busy", "published": 0, "failed": 0, "skipped": 0}

    with _posting_thread_lock:
        db = SessionLocal()
        stats = {"status": "completed", "published": 0, "failed": 0, "skipped": 0}
        try:
            mark_past_schedules_missed(db, user_id)
            due = get_due_products(db, user_id)
            if not due:
                return stats

            log_activity_isolated(
                LogCategory.MONITORING,
                f"Publishing {len(due)} scheduled product(s) to Marketplace",
                details={"ids": [p.id for p in due]},
                source="posting",
            )

            for product in due:
                fresh = db.query(ProductPost).filter(ProductPost.id == product.id).first()
                if not fresh or fresh.status in (ProductStatus.PUBLISHED, ProductStatus.PUBLISHING):
                    stats["skipped"] += 1
                    continue
                try:
                    await publish_product(db, fresh, return_to_marketplace=False)
                    await _close_browser_for_user(user_id, wait_sec=POST_PUBLISH_STAY_SEC)
                    stats["published"] += 1
                except Exception as exc:
                    logger.exception("Product %s publish failed: %s", product.id, exc)
                    await _close_browser_for_user(user_id, wait_sec=5.0)
                    stats["failed"] += 1
        finally:
            db.close()
        return stats
