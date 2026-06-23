"""Scheduled + retry publishing of ProductPost rows to Facebook Marketplace."""
from __future__ import annotations

import asyncio
import json
import logging
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

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

POSTING_TZ = ZoneInfo("Europe/Rome")
WEEKDAY_CODES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
MAX_RETRIES = 5
REFRESH_BEFORE_SEC = 3.5
IDLE_POLL_SEC = 15.0
POST_PUBLISH_STAY_SEC = 12.0
TEST_PUBLISH_SCREEN_SEC = 5.5

_posting_lock = asyncio.Lock()
_posting_loop_tasks: dict[int, asyncio.Task] = {}
_posting_loop_cancel: dict[int, asyncio.Event] = {}
_test_full_flow_done: set[int] = set()
# Dry-run keeps status SCHEDULED — track ids already handled this bot session to avoid re-posting.
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


def is_posting_loop_active(user_id: int) -> bool:
    task = _posting_loop_tasks.get(user_id)
    return task is not None and not task.done()


def is_test_full_flow_done(user_id: int) -> bool:
    return user_id in _test_full_flow_done


def mark_test_full_flow_done(user_id: int) -> None:
    _test_full_flow_done.add(user_id)


def clear_test_full_flow_session(user_id: int) -> None:
    _test_full_flow_done.discard(user_id)


def _session_skip_ids(user_id: int) -> set[int]:
    return _session_posted_ids.get(user_id, set())


def _now_local() -> datetime:
    return datetime.now(POSTING_TZ)


def _day_code_to_weekday(code: str) -> int | None:
    key = (code or "").lower()[:3]
    if key not in WEEKDAY_CODES:
        return None
    return WEEKDAY_CODES.index(key)


def _is_due(product: ProductPost, now: datetime) -> bool:
    if product.status != ProductStatus.SCHEDULED:
        return False
    if not product.schedule_day or not product.schedule_time:
        return False
    day_code = WEEKDAY_CODES[now.weekday()]
    if product.schedule_day.lower()[:3] != day_code:
        return False
    try:
        h, m = product.schedule_time.split(":")
        sched_minutes = int(h) * 60 + int(m)
    except ValueError:
        return False
    now_minutes = now.hour * 60 + now.minute
    return now_minutes >= sched_minutes


def next_due_moment(product: ProductPost, now: datetime) -> datetime | None:
    """Italy-local datetime when this scheduled product becomes due (today or next weekday)."""
    if product.status != ProductStatus.SCHEDULED:
        return None
    if not product.schedule_day or not product.schedule_time:
        return None
    target_wd = _day_code_to_weekday(product.schedule_day)
    if target_wd is None:
        return None
    try:
        h, m = map(int, product.schedule_time.split(":"))
    except ValueError:
        return None

    candidate = now.replace(hour=h, minute=m, second=0, microsecond=0)
    days_ahead = (target_wd - now.weekday()) % 7
    if days_ahead == 0:
        if candidate <= now:
            return candidate
        return candidate
    return candidate + timedelta(days=days_ahead)


def pick_next_scheduled(db: Session, user_id: int, now: datetime) -> tuple[ProductPost | None, datetime | None]:
    """Next product to post and when to start (now if already due)."""
    skip_ids = _session_skip_ids(user_id)
    candidates = (
        db.query(ProductPost)
        .filter(
            ProductPost.user_id == user_id,
            ProductPost.status == ProductStatus.SCHEDULED,
            ProductPost.retry_count < MAX_RETRIES,
        )
        .order_by(ProductPost.id.asc())
        .all()
    )
    due_now: ProductPost | None = None
    next_product: ProductPost | None = None
    next_moment: datetime | None = None

    for product in candidates:
        if product.id in skip_ids:
            continue
        if _is_due(product, now):
            due_now = product
            break
        moment = next_due_moment(product, now)
        if moment is None:
            continue
        if next_moment is None or moment < next_moment:
            next_product = product
            next_moment = moment

    if due_now:
        return due_now, now
    return next_product, next_moment


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
    due = [p for p in candidates if p.id not in _session_skip_ids(user_id) and _is_due(p, now)]
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


def should_open_browser_on_start(db: Session, user_id: int, monitoring) -> bool:
    """Open Chromium immediately on Start when no saved session or test full flow is ON."""
    if monitoring and getattr(monitoring, "test_full_flow", False):
        return True
    return not has_saved_facebook_session_sync(user_id)


def has_saved_facebook_session_sync(user_id: int) -> bool:
    from app.services.facebook_session import has_facebook_session_saved

    cfg = get_settings()
    token = set_workspace_user_id(user_id)
    try:
        return has_facebook_session_saved(cfg)
    finally:
        reset_workspace_user_id(token)


async def prepare_browser_on_bot_start(user_id: int, db: Session) -> None:
    """Start ON with no session / test flow — open Chromium right away for Facebook login."""
    log_activity(
        db,
        LogCategory.MONITORING,
        "Opening Chromium on Start — Facebook Marketplace (log in when the tab opens)",
        source="posting",
    )
    db.commit()
    await _open_browser_for_user(user_id, wait_for_login=False)


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
                skip_publish=False,
                stop_after_first_next=False,
                fill_extra_details=True,
                return_to_marketplace_after=return_to_marketplace,
            )
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
    log_activity_isolated(
        LogCategory.MONITORING,
        "Bot ON — waiting for scheduled product time (Chromium opens when a post is due)",
        details={"user_id": user_id, "locale": cfg.BROWSER_LOCALE, "tz": cfg.BROWSER_TIMEZONE},
        source="posting",
    )

    try:
        while not cancel.is_set():
            if not is_user_monitoring_enabled(user_id):
                break

            db = SessionLocal()
            try:
                now = _now_local()
                product, due_at = pick_next_scheduled(db, user_id, now)

                if not product or due_at is None:
                    fb = get_facebook_source(user_id)
                    if fb.has_live_browser() and fb._page and fb._context:
                        try:
                            if await is_login_fully_complete(fb._context, fb._page):
                                await save_session(fb._context, cfg)
                        except Exception:
                            pass
                    await asyncio.sleep(IDLE_POLL_SEC)
                    continue

                if due_at > now:
                    open_at = due_at - timedelta(seconds=REFRESH_BEFORE_SEC)
                    log_activity_isolated(
                        LogCategory.MONITORING,
                        f"Next post: {product.name[:50]} at {due_at.strftime('%a %H:%M')} (Italy)",
                        details={
                            "product_id": product.id,
                            "chromium_opens_at": open_at.isoformat(),
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
                    if not await _sleep_until(cancel, due_at):
                        break
                else:
                    await _open_browser_for_user(user_id)

                if cancel.is_set() or not is_user_monitoring_enabled(user_id):
                    break

                fresh = db.query(ProductPost).filter(ProductPost.id == product.id).first()
                if not fresh or fresh.status != ProductStatus.SCHEDULED:
                    continue

                try:
                    async with _posting_lock:
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


async def start_posting_loop(user_id: int) -> None:
    await stop_posting_loop(user_id)
    cancel = asyncio.Event()
    _posting_loop_cancel[user_id] = cancel
    _posting_loop_tasks[user_id] = asyncio.create_task(
        _posting_wait_loop(user_id, cancel),
        name=f"posting-loop-{user_id}",
    )


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
    """Fallback: pick due scheduled products (60s scheduler tick)."""
    if _posting_loop_tasks.get(user_id) and not _posting_loop_tasks[user_id].done():
        return {"status": "loop_active", "published": 0, "failed": 0, "skipped": 0}

    if _posting_lock.locked():
        return {"status": "busy", "published": 0, "failed": 0, "skipped": 0}

    async with _posting_lock:
        db = SessionLocal()
        stats = {"status": "completed", "published": 0, "failed": 0, "skipped": 0}
        try:
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
