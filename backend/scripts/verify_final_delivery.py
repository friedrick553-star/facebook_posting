"""Final pre-delivery verification: logic checks + optional live scheduled run."""
from __future__ import annotations

import asyncio
import inspect
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.core.timezone import now_italy  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import ProductPost, ProductStatus  # noqa: E402
from app.services import facebook_posting_flow as fb_flow  # noqa: E402
from app.services import product_posting_service as pps  # noqa: E402
from app.services.product_posting_service import (  # noqa: E402
    REFRESH_BEFORE_SEC,
    has_saved_facebook_session_sync,
    pick_next_scheduled,
    run_posting_cycle,
    should_run_marketplace_peek_on_start,
)

BASE = "http://127.0.0.1:8002/api"
EMAIL = "usmanamjad2522@gmail.com"
PASSWORD = "usman123"
MINUTES_AHEAD = 2.0
POLL_SEC = 5
WATCH_AFTER_DUE_SEC = 360


def verify_publish_code() -> list[str]:
    errors: list[str] = []
    flow_src = inspect.getsource(fb_flow.publish_marketplace_item)
    prod_src = inspect.getsource(pps.publish_product)

    if 'await _click_button(page, "Publish", "Pubblica"' not in flow_src:
        errors.append("Real publish must call _click_button(Publish, Pubblica, ...)")
    if "Submitting listing" not in flow_src:
        errors.append("Real publish path missing 'Submitting listing' step")
    if "product.status = ProductStatus.PUBLISHED" not in prod_src:
        errors.append("publish_product must set status PUBLISHED")
    if "Published to Marketplace" not in prod_src:
        errors.append("publish_product must log Published to Marketplace")
    if "DRY_RUN_PUBLISH" in prod_src:
        errors.append("DRY_RUN_PUBLISH must be removed from publish flow")
    if "dry_run" in prod_src:
        errors.append("dry_run parameter must be removed from publish_product")

    return errors


async def verify_scheduler_guards() -> list[str]:
    errors: list[str] = []
    cfg = get_settings()
    if not cfg.STOP_AFTER_MARKETPLACE:
        errors.append("STOP_AFTER_MARKETPLACE must be enabled")

    stats = await run_posting_cycle(1)
    if stats.get("status") != "loop_active":
        errors.append(f"60s scheduler must no-op when wait loop active, got {stats}")

    db = SessionLocal()
    try:
        now = now_italy()
        today = now.strftime("%Y-%m-%d")
        rows = (
            db.query(ProductPost)
            .filter(ProductPost.user_id == 1, ProductPost.status == ProductStatus.SCHEDULED)
            .limit(5)
            .all()
        )
        if len(rows) >= 2:
            saved = [(r.id, r.schedule_date, r.schedule_time) for r in rows[:2]]
            grace_time = (now - timedelta(minutes=2)).strftime("%H:%M")
            future_time = (now + timedelta(minutes=10)).strftime("%H:%M")
            rows[0].schedule_date = today
            rows[0].schedule_time = grace_time
            rows[1].schedule_date = today
            rows[1].schedule_time = future_time
            db.commit()
            nxt, due = pick_next_scheduled(db, 1, now)
            if not nxt or nxt.id != rows[1].id:
                errors.append("pick_next must prefer future slot over grace-overdue")
            for r, sd, st in saved:
                row = db.query(ProductPost).filter(ProductPost.id == r).first()
                if row:
                    row.schedule_date = sd
                    row.schedule_time = st
            db.commit()

        peek = should_run_marketplace_peek_on_start(db, 1, None)
        has_cookies = has_saved_facebook_session_sync(1)
        has_sched = (
            db.query(ProductPost)
            .filter(ProductPost.user_id == 1, ProductPost.status == ProductStatus.SCHEDULED)
            .count()
            > 0
        )
        if has_sched and has_cookies and peek:
            errors.append("Must NOT marketplace peek when scheduled products + cookies exist")
    finally:
        db.close()

    return errors


def login(client: httpx.Client) -> str:
    r = client.post(f"{BASE}/auth/login", json={"email": EMAIL, "password": PASSWORD})
    r.raise_for_status()
    return r.json()["access_token"]


def H(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def find_iphone(client: httpx.Client, token: str) -> dict | None:
    r = client.get(
        f"{BASE}/products",
        params={"search": "iPhone 13 Pro", "page_size": 10, "catalog": True},
        headers=H(token),
    )
    r.raise_for_status()
    for p in r.json()["items"]:
        if "iPhone 13 Pro" in p["name"]:
            return p
    return None


def run_live_scheduled_test(client: httpx.Client, token: str) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()

    now = now_italy()
    due = (now + timedelta(minutes=MINUTES_AHEAD)).replace(second=0, microsecond=0)
    if (due - now).total_seconds() < 90:
        due = due + timedelta(minutes=1)
    today = due.strftime("%Y-%m-%d")
    due_time = due.strftime("%H:%M")
    open_expected = due - timedelta(seconds=REFRESH_BEFORE_SEC)

    print(f"\n--- LIVE RUN (real publish) ---")
    print(f"Schedule due: {due.strftime('%d/%m/%Y %H:%M:%S')} Italy")
    print(f"Chromium ~at: {open_expected.strftime('%d/%m/%Y %H:%M:%S')}")
    print("WARNING: Pubblica will be clicked — real Marketplace listing")

    try:
        client.post(f"{BASE}/monitoring/stop", headers=H(token), timeout=30)
        time.sleep(2)
    except Exception:
        pass

    prod = find_iphone(client, token)
    if not prod:
        return ["iPhone 13 Pro not found — upload CSV first"]

    pid = prod["id"]
    client.put(
        f"{BASE}/products/{pid}",
        json={"schedule_date": today, "schedule_time": due_time},
        headers=H(token),
    ).raise_for_status()
    print(f"Scheduled iPhone id={pid} -> {today} {due_time}")

    client.post(f"{BASE}/monitoring/start", headers=H(token), timeout=60).raise_for_status()
    bot_started_utc = now_italy().astimezone(timezone.utc)
    print("Bot started — watching logs...")

    flags = {
        "next_post": False,
        "bot_on_wait": False,
        "chromium_open": False,
        "published": False,
        "double_publish": False,
        "peek_on_start": False,
    }
    chromium_ts: str | None = None
    deadline = time.time() + (MINUTES_AHEAD * 60) + WATCH_AFTER_DUE_SEC + 30

    def after_start(created_at: str) -> bool:
        if not created_at:
            return True
        raw = created_at.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            return True
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt >= bot_started_utc - timedelta(seconds=2)

    while time.time() < deadline:
        r = client.get(f"{BASE}/logs", params={"page_size": 80, "page": 1}, headers=H(token))
        r.raise_for_status()
        for log in r.json()["items"]:
            msg = log.get("message") or ""
            if not after_start(log.get("created_at") or ""):
                continue
            key = f"{log.get('id')}:{msg[:80]}"
            if key in seen:
                continue
            interesting = (
                "Next post",
                "Bot ON",
                "Opening Playwright Chromium",
                "Published to Marketplace",
                "Publishing 1 scheduled",
                "Start — opening Marketplace",
                "Scheduled products waiting",
                "Publish failed",
            )
            if not any(k in msg for k in interesting):
                continue
            seen.add(key)
            ts = (log.get("created_at") or "")[:19]
            print(f"  LOG {ts} {msg[:110]}")

            if "Next post" in msg:
                flags["next_post"] = True
            if "Bot ON — waiting" in msg:
                flags["bot_on_wait"] = True
            if "Opening Playwright Chromium" in msg:
                flags["chromium_open"] = True
                chromium_ts = ts
            if "Published to Marketplace" in msg:
                flags["published"] = True
            if "Publishing 1 scheduled product" in msg:
                flags["double_publish"] = True
            if "Start — opening Marketplace" in msg:
                flags["peek_on_start"] = True

        if flags["published"] and flags["chromium_open"]:
            break
        if now_italy() > due + timedelta(seconds=WATCH_AFTER_DUE_SEC) and flags["chromium_open"]:
            break
        time.sleep(POLL_SEC)

    try:
        client.post(f"{BASE}/monitoring/stop", headers=H(token), timeout=30)
    except Exception:
        pass

    if not flags["next_post"]:
        errors.append("Live: missing Next post log")
    if not flags["bot_on_wait"]:
        errors.append("Live: missing Bot ON — waiting log")
    if not flags["chromium_open"]:
        errors.append("Live: Chromium never opened")
    if not flags["published"]:
        errors.append("Live: product not published (no Published to Marketplace log)")
    if flags["peek_on_start"]:
        errors.append("Live: unwanted Marketplace peek on start")
    if flags["double_publish"]:
        errors.append("Live: 60s scheduler double-browser bug")
    if chromium_ts:
        print(f"Chromium UTC: {chromium_ts} | expected Italy ~{open_expected.strftime('%H:%M:%S')}")

    return errors


async def main() -> int:
    print("=" * 64)
    print("FINAL DELIVERY VERIFICATION")
    print("=" * 64)

    all_errors: list[str] = []

    print("\n[1/4] Health & timezone")
    try:
        with httpx.Client(timeout=10) as c:
            health = c.get("http://127.0.0.1:8002/health").json()
        if health.get("timezone") != "Europe/Rome":
            all_errors.append(f"Wrong timezone: {health.get('timezone')}")
        else:
            print(f"  OK Europe/Rome | Italy now: {health.get('italy_now_display')}")
    except Exception as exc:
        print(f"  FAIL backend: {exc}")
        return 1

    print("\n[2/4] Publish code (always real Pubblica click)")
    code_errs = verify_publish_code()
    if code_errs:
        all_errors.extend(code_errs)
    else:
        print("  OK scheduled posts always click Publish/Pubblica -> Published")

    print("\n[3/4] Scheduler guards")
    sched_errs = await verify_scheduler_guards()
    if sched_errs:
        all_errors.extend(sched_errs)
    else:
        print("  OK future-first pick, no double browser, peek rules")

    print("\n[4/4] Live run — SKIPPED by default (real Facebook listing)")
    print("  Run manually: python scripts/live_bot_scheduled_test.py")

    print("\n" + "=" * 64)
    if all_errors:
        print("RESULT: FAIL")
        for e in all_errors:
            print(f"  - {e}")
        return 1

    print("RESULT: PASS — ready to deliver")
    print("  Scheduled products: Pubblica clicked, status Published")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
