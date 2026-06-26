"""Live test: set future schedule, poll Scheduled API until due — must stay visible."""
from __future__ import annotations

import sys
import time
from datetime import timedelta
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.timezone import now_italy  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import ProductPost, ProductStatus  # noqa: E402
from app.services.product_posting_service import scheduled_moment  # noqa: E402

BASE = "http://127.0.0.1:8002/api"
EMAIL = "usmanamjad2522@gmail.com"
PASSWORD = "usman123"
USER_ID = 1
PRODUCT_NAME = "iPhone 13 Pro 128GB"
MINUTES_AHEAD = 3
POLL_SEC = 15


def login(client: httpx.Client) -> str:
    r = client.post(f"{BASE}/auth/login", json={"email": EMAIL, "password": PASSWORD})
    r.raise_for_status()
    return r.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def scheduled_ids(client: httpx.Client, token: str) -> set[int]:
    r = client.get(
        f"{BASE}/products",
        params={"status": "scheduled", "page_size": 100, "sort": "schedule"},
        headers=auth(token),
    )
    r.raise_for_status()
    return {p["id"] for p in r.json()["items"]}


def failed_ids(client: httpx.Client, token: str) -> set[int]:
    r = client.get(
        f"{BASE}/products",
        params={"status": "failed", "page_size": 100},
        headers=auth(token),
    )
    r.raise_for_status()
    return {p["id"] for p in r.json()["items"]}


def find_product(client: httpx.Client, token: str) -> dict | None:
    r = client.get(
        f"{BASE}/products",
        params={"search": "iPhone 13 Pro", "page_size": 20, "catalog": True},
        headers=auth(token),
    )
    r.raise_for_status()
    for p in r.json()["items"]:
        if PRODUCT_NAME in p["name"]:
            return p
    return None


def main() -> int:
    now = now_italy()
    due = (now + timedelta(minutes=MINUTES_AHEAD)).replace(second=0, microsecond=0)
    today = due.strftime("%Y-%m-%d")
    due_time = due.strftime("%H:%M")

    print(f"Italy now: {now.strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"Setting {PRODUCT_NAME} -> {today} {due_time} Italy")
    print(f"Polling Scheduled list every {POLL_SEC}s until {MINUTES_AHEAD + 2} min...\n")

    errors: list[str] = []

    with httpx.Client(timeout=60.0) as client:
        token = login(client)
        prod = find_product(client, token)
        if not prod:
            print(f"FAIL: {PRODUCT_NAME} not found — upload CSV first")
            return 1

        pid = prod["id"]
        client.put(
            f"{BASE}/products/{pid}",
            json={"schedule_date": today, "schedule_time": due_time},
            headers=auth(token),
        ).raise_for_status()

        db = SessionLocal()
        row = db.query(ProductPost).filter(ProductPost.id == pid).first()
        moment = scheduled_moment(row) if row else None
        db.close()
        print(f"Product id={pid} status after save: {prod.get('status')} -> scheduled")
        print(f"DB moment: {moment.strftime('%d/%m/%Y %H:%M:%S') if moment else '?'}\n")

        deadline = time.time() + (MINUTES_AHEAD + 2) * 60
        checks = 0
        while time.time() < deadline:
            checks += 1
            now = now_italy()
            sched = scheduled_ids(client, token)
            fail = failed_ids(client, token)
            in_sched = pid in sched
            in_fail = pid in fail

            db = SessionLocal()
            row = db.query(ProductPost).filter(ProductPost.id == pid).first()
            st = row.status.value if row else "?"
            db.close()

            line = (
                f"[{now.strftime('%H:%M:%S')}] scheduled_list={'YES' if in_sched else 'NO'} "
                f"failed_list={'YES' if in_fail else 'NO'} db_status={st}"
            )
            print(line)

            if moment and now < moment:
                if not in_sched:
                    errors.append(f"Before due ({due_time}): missing from Scheduled list at {now.strftime('%H:%M:%S')}")
                if in_fail:
                    errors.append(f"Before due: already in Failed at {now.strftime('%H:%M:%S')}")
            elif moment and now <= moment + timedelta(minutes=5):
                if st in ("scheduled", "publishing") and not in_sched and not in_fail:
                    errors.append(f"During grace at {now.strftime('%H:%M:%S')}: vanished from both lists (status={st})")

            time.sleep(POLL_SEC)

        print(f"\n{checks} polls done.")
        if errors:
            print("FAILURES:")
            for e in errors:
                print(" -", e)
            return 1

        print("PASS: product stayed on Scheduled list until due window.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
