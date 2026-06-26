"""Quick live test: schedule +2min, reach Publish screen, log button found, NO click."""
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
POLL_SEC = 4
MAX_WAIT_SEC = 600


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


def main() -> int:
    now = now_italy()
    due = (now + timedelta(minutes=MINUTES_AHEAD)).replace(second=0, microsecond=0)
    if (due - now).total_seconds() < 90:
        due += timedelta(minutes=1)
    today = due.strftime("%Y-%m-%d")
    due_time = due.strftime("%H:%M")

    print("LIVE VERIFY — Publish screen only (NO click)")
    print(f"Due: {due.strftime('%H:%M')} Italy | Chromium ~{(due - timedelta(seconds=REFRESH_BEFORE_SEC)).strftime('%H:%M:%S')}")
    print("Backend must run with VERIFY_PUBLISH_SCREEN_ONLY=1\n")

    with httpx.Client(timeout=120) as client:
        client.get("http://127.0.0.1:8002/health").raise_for_status()
        token = login(client)
        try:
            client.post(f"{BASE}/monitoring/stop", headers=H(token), timeout=30)
            time.sleep(2)
        except Exception:
            pass

        prod = find_iphone(client, token)
        if not prod:
            print("FAIL: no iPhone — upload CSV first")
            return 1

        pid = prod["id"]
        client.put(
            f"{BASE}/products/{pid}",
            json={"schedule_date": today, "schedule_time": due_time},
            headers=H(token),
        ).raise_for_status()
        client.post(f"{BASE}/monitoring/start", headers=H(token), timeout=60).raise_for_status()
        started = now_italy().astimezone(timezone.utc)
        print(f"Bot ON — product id={pid} @ {due_time}")

        seen: set[str] = set()
        found = False
        deadline = time.time() + MAX_WAIT_SEC

        while time.time() < deadline:
            for log in client.get(f"{BASE}/logs", params={"page_size": 60}, headers=H(token)).json()["items"]:
                raw = (log.get("created_at") or "").replace("Z", "+00:00")
                try:
                    dt = datetime.fromisoformat(raw)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if dt < started - timedelta(seconds=2):
                        continue
                except ValueError:
                    pass
                msg = log.get("message") or ""
                key = f"{log.get('id')}:{msg[:70]}"
                if key in seen:
                    continue
                for kw in (
                    "Next post",
                    "Opening Playwright",
                    "Submitting listing",
                    "Publish button",
                    "Publish screen",
                    "Clicked sidebar Next",
                    "verify test",
                    "NOT clicked",
                ):
                    if kw.lower() in msg.lower():
                        seen.add(key)
                        print(f"  {(log.get('created_at') or '')[:19]} {msg[:110]}")
                        break
                if "Publish button FOUND" in msg or (
                    "Publish button visible" in msg and "NOT" in msg
                ):
                    found = True
                    break
                if "verify test" in msg.lower() and "NOT clicked" in msg:
                    found = True
                    break
            if found:
                break
            time.sleep(POLL_SEC)

        try:
            client.post(f"{BASE}/monitoring/stop", headers=H(token), timeout=30)
        except Exception:
            pass

        if found:
            print("\nPASS: Publish button found on audience screen — NOT clicked.")
            return 0
        print("\nFAIL: Did not see Publish button found log — check Facebook login / logs page")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
