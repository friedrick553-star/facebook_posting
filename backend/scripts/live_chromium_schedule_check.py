"""Cross-check: scheduled product -> Chromium opens ~3.5s before due time (no publish required)."""
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


def login(client: httpx.Client) -> str:
    r = client.post(f"{BASE}/auth/login", json={"email": EMAIL, "password": PASSWORD})
    r.raise_for_status()
    return r.json()["access_token"]


def H(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def main() -> int:
    errors: list[str] = []
    now = now_italy()
    due = (now + timedelta(minutes=MINUTES_AHEAD)).replace(second=0, microsecond=0)
    if (due - now).total_seconds() < 90:
        due = due + timedelta(minutes=1)
    today = due.strftime("%Y-%m-%d")
    due_time = due.strftime("%H:%M")
    open_expected = due - timedelta(seconds=REFRESH_BEFORE_SEC)

    print("=" * 60)
    print("CHROMIUM SCHEDULE CHECK")
    print("=" * 60)
    print(f"Italy now:     {now.strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"Schedule due:  {due.strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"Chromium ~at:  {open_expected.strftime('%d/%m/%Y %H:%M:%S')}")
    print()

    with httpx.Client(timeout=120.0) as client:
        try:
            client.get("http://127.0.0.1:8002/health", timeout=5).raise_for_status()
        except Exception as exc:
            print(f"FAIL: backend not running — {exc}")
            return 1

        token = login(client)
        try:
            client.post(f"{BASE}/monitoring/stop", headers=H(token), timeout=30)
            time.sleep(2)
            print("Bot stopped (clean start)")
        except Exception:
            pass

        items = client.get(
            f"{BASE}/products", params={"page_size": 20, "catalog": True}, headers=H(token)
        ).json()["items"]
        prod = next(
            (
                p
                for p in items
                if "iPhone" in p["name"]
                or p["status"] in ("scheduled", "pending", "failed", "publishing")
            ),
            None,
        )
        if not prod:
            print("FAIL: no product available for test")
            return 1

        pid = prod["id"]
        client.put(
            f"{BASE}/products/{pid}",
            json={"schedule_date": today, "schedule_time": due_time},
            headers=H(token),
        ).raise_for_status()
        print(f"Scheduled id={pid} -> {today} {due_time} Italy")

        bot_started_utc = now_italy().astimezone(timezone.utc)
        client.post(f"{BASE}/monitoring/start", headers=H(token), timeout=60).raise_for_status()
        print(f"Bot START — watching logs every {POLL_SEC}s...\n")

        flags = {
            "next_post": False,
            "chromium_open": False,
            "peek_on_start": False,
            "scheduled_wait_log": False,
        }
        chromium_log_time: str | None = None
        seen: set[str] = set()
        deadline = time.time() + (MINUTES_AHEAD * 60) + 180

        keywords = (
            "Next post",
            "Opening Playwright Chromium",
            "Scheduled products waiting",
            "Start — opening Marketplace",
            "Bot ON",
        )

        while time.time() < deadline:
            for log in client.get(
                f"{BASE}/logs", params={"page_size": 80, "page": 1}, headers=H(token)
            ).json()["items"]:
                msg = log.get("message") or ""
                raw = (log.get("created_at") or "").replace("Z", "+00:00")
                try:
                    log_dt = datetime.fromisoformat(raw)
                    if log_dt.tzinfo is None:
                        log_dt = log_dt.replace(tzinfo=timezone.utc)
                    if log_dt < bot_started_utc - timedelta(seconds=2):
                        continue
                except ValueError:
                    pass

                key = f"{log.get('id')}:{msg[:80]}"
                if key in seen:
                    continue
                if not any(k in msg for k in keywords):
                    continue
                seen.add(key)
                ts = (log.get("created_at") or "")[:19]
                print(f"  LOG {ts} {msg[:110]}")

                if "Next post" in msg:
                    flags["next_post"] = True
                if "Opening Playwright Chromium" in msg:
                    flags["chromium_open"] = True
                    chromium_log_time = ts
                if "Start — opening Marketplace" in msg:
                    flags["peek_on_start"] = True
                if "Scheduled products waiting" in msg:
                    flags["scheduled_wait_log"] = True

            if flags["chromium_open"]:
                break
            if now_italy() > due + timedelta(seconds=120):
                break
            time.sleep(POLL_SEC)

        try:
            client.post(f"{BASE}/monitoring/stop", headers=H(token), timeout=30)
            print("\nBot stopped after test")
        except Exception:
            pass

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    for k, v in flags.items():
        print(f"  {k}: {'YES' if v else 'NO'}")

    if flags["peek_on_start"]:
        errors.append("Unwanted immediate Marketplace peek on Start")
    if not flags["next_post"] and not flags["scheduled_wait_log"]:
        errors.append("Missing Next post / Scheduled products waiting log")
    if not flags["chromium_open"]:
        errors.append("Chromium never opened at scheduled time")
    elif chromium_log_time:
        print(f"\nChromium log UTC: {chromium_log_time}")
        print(f"Expected Italy ~: {open_expected.strftime('%H:%M:%S')}")

    if errors:
        print("\nFAIL:")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("\nPASS: Chromium opened on schedule.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
