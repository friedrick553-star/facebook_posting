"""Live test: schedule +2min, start bot, watch Chromium + real publish."""
from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.timezone import now_italy  # noqa: E402
from app.services.product_posting_service import REFRESH_BEFORE_SEC  # noqa: E402

BASE = "http://127.0.0.1:8002/api"
EMAIL = "usmanamjad2522@gmail.com"
PASSWORD = "usman123"
MINUTES_AHEAD = 2.0
POLL_SEC = 5
WATCH_AFTER_DUE_SEC = 360


def login(client: httpx.Client) -> str:
    r = client.post(f"{BASE}/auth/login", json={"email": EMAIL, "password": PASSWORD})
    r.raise_for_status()
    return r.json()["access_token"]


def H(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def get_logs(client: httpx.Client, token: str) -> list[dict]:
    r = client.get(f"{BASE}/logs", params={"page_size": 80, "page": 1}, headers=H(token))
    r.raise_for_status()
    return r.json()["items"]


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


def main() -> int:
    errors: list[str] = []
    seen_msgs: set[str] = set()

    now = now_italy()
    due = (now + timedelta(minutes=MINUTES_AHEAD)).replace(second=0, microsecond=0)
    if (due - now).total_seconds() < 90:
        due = due + timedelta(minutes=1)
    today = due.strftime("%Y-%m-%d")
    due_time = due.strftime("%H:%M")
    open_expected = due - timedelta(seconds=REFRESH_BEFORE_SEC)

    print("=" * 60)
    print("LIVE BOT TEST — schedule, start bot, real publish")
    print("=" * 60)
    print(f"Italy now:     {now.strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"Schedule due:  {due.strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"Chromium ~at:  {open_expected.strftime('%d/%m/%Y %H:%M:%S')} (+/- few sec)")
    print("NOTE: Pubblica WILL be clicked — real Marketplace listing")
    print()

    with httpx.Client(timeout=120.0) as client:
        try:
            client.get("http://127.0.0.1:8002/health", timeout=5).raise_for_status()
        except Exception as exc:
            print(f"FAIL: backend not running — {exc}")
            return 1

        token = login(client)
        print("Login OK")

        try:
            client.post(f"{BASE}/monitoring/stop", headers=H(token), timeout=30)
            time.sleep(2)
            print("Bot stopped (clean start)")
        except Exception:
            pass

        prod = find_iphone(client, token)
        if not prod:
            print("FAIL: iPhone 13 Pro not in DB — upload CSV first")
            return 1

        pid = prod["id"]
        client.put(
            f"{BASE}/products/{pid}",
            json={"schedule_date": today, "schedule_time": due_time},
            headers=H(token),
        ).raise_for_status()
        print(f"Product id={pid} scheduled -> {today} {due_time} Italy")

        sched = client.get(
            f"{BASE}/products",
            params={"status": "scheduled", "page_size": 50, "sort": "schedule"},
            headers=H(token),
        ).json()["items"]
        if not any(p["id"] == pid for p in sched):
            errors.append("Product not in Scheduled list right after save")
        else:
            print("Scheduled list: product visible OK")

        client.post(f"{BASE}/monitoring/start", headers=H(token), timeout=60).raise_for_status()
        bot_started_utc = now_italy().astimezone(timezone.utc)
        print(f"Bot START at {now_italy().strftime('%H:%M:%S')} Italy")
        print(f"Watching logs every {POLL_SEC}s...\n")

        deadline = time.time() + (MINUTES_AHEAD * 60) + WATCH_AFTER_DUE_SEC + 30
        flags = {
            "next_post": False,
            "bot_on_wait": False,
            "chromium_open": False,
            "published": False,
            "double_publish_cycle": False,
            "peek_on_start": False,
        }
        chromium_log_time: str | None = None

        keywords = (
            "Next post",
            "Bot ON",
            "Opening Playwright Chromium",
            "Published to Marketplace",
            "Publishing 1 scheduled",
            "Start — opening Marketplace",
            "Scheduled products waiting",
            "Publish failed",
        )

        def log_after_bot_start(created_at: str) -> bool:
            if not created_at:
                return True
            raw = created_at.replace("Z", "+00:00")
            try:
                log_dt = datetime.fromisoformat(raw)
            except ValueError:
                return True
            if log_dt.tzinfo is None:
                log_dt = log_dt.replace(tzinfo=timezone.utc)
            return log_dt >= bot_started_utc - timedelta(seconds=2)

        while time.time() < deadline:
            now_s = now_italy().strftime("%H:%M:%S")
            for log in get_logs(client, token):
                msg = log.get("message") or ""
                if not log_after_bot_start(log.get("created_at") or ""):
                    continue
                key = f"{log.get('id')}:{msg[:80]}"
                if key in seen_msgs:
                    continue
                if not any(k in msg for k in keywords):
                    continue
                seen_msgs.add(key)
                ts = log.get("created_at", "")[:19]
                print(f"[{now_s} poll] LOG {ts} {msg[:120]}")

                if "Next post" in msg:
                    flags["next_post"] = True
                if "Bot ON — waiting" in msg:
                    flags["bot_on_wait"] = True
                if "Opening Playwright Chromium" in msg:
                    flags["chromium_open"] = True
                    chromium_log_time = ts
                if "Published to Marketplace" in msg:
                    flags["published"] = True
                if "Publishing 1 scheduled product" in msg:
                    flags["double_publish_cycle"] = True
                if "Start — opening Marketplace" in msg:
                    flags["peek_on_start"] = True

            if flags["published"] and flags["chromium_open"]:
                print("\nDone: published + chromium seen in logs.")
                break

            if now_italy() > due + timedelta(seconds=WATCH_AFTER_DUE_SEC):
                if flags["chromium_open"]:
                    break

            time.sleep(POLL_SEC)

        print("\n" + "=" * 60)
        print("RESULTS")
        print("=" * 60)
        for k, v in flags.items():
            print(f"  {k}: {'YES' if v else 'NO'}")

        if not flags["bot_on_wait"]:
            errors.append("Missing 'Bot ON — waiting' log")
        if not flags["next_post"]:
            errors.append("Missing 'Next post' log")
        if flags["peek_on_start"]:
            errors.append("Marketplace peek on start — should NOT when scheduled + cookies")
        if flags["double_publish_cycle"]:
            errors.append("60s scheduler double-browser bug")
        if not flags["chromium_open"]:
            errors.append("Chromium never opened")
        if not flags["published"]:
            errors.append("Not published — check Facebook login/cookies")
        elif chromium_log_time:
            print(f"\nChromium log at: {chromium_log_time}")
            print(f"Expected open ~: {open_expected.strftime('%H:%M:%S')} Italy")

        published_end = client.get(
            f"{BASE}/products",
            params={"status": "published", "page_size": 50},
            headers=H(token),
        ).json()["items"]
        in_published = any(p["id"] == pid for p in published_end)
        print(f"\nAfter test: published_list={'YES' if in_published else 'NO'}")

        try:
            client.post(f"{BASE}/monitoring/stop", headers=H(token), timeout=30)
            print("Bot stopped after test")
        except Exception:
            pass

    if errors:
        print("\nFAILURES:")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("\nPASS: Full live scheduled publish verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
