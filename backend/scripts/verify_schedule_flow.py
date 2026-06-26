"""End-to-end verify: CSV upload, schedule changes, past slots in Failed list."""
from __future__ import annotations

import json
import sys
from datetime import timedelta
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.timezone import now_italy  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import ProductPost, ProductStatus  # noqa: E402
from app.services.product_posting_service import (  # noqa: E402
    mark_past_schedules_missed,
    pick_next_scheduled,
    scheduled_moment,
)

BASE = "http://127.0.0.1:8002/api"
EMAIL = "usmanamjad2522@gmail.com"
PASSWORD = "usman123"
CSV_PATH = ROOT.parent / "sample_products.csv"
USER_ID = 1


def login(client: httpx.Client) -> str:
    r = client.post(f"{BASE}/auth/login", json={"email": EMAIL, "password": PASSWORD})
    r.raise_for_status()
    return r.json()["access_token"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def wipe_catalog(client: httpx.Client, token: str) -> None:
    for status in ("scheduled", "pending", "published", "failed", "duplicate"):
        r = client.get(f"{BASE}/products", params={"status": status, "page_size": 100}, headers=auth_headers(token))
        r.raise_for_status()
        ids = [p["id"] for p in r.json()["items"]]
        if ids:
            client.request(
                "DELETE",
                f"{BASE}/products",
                json={"ids": ids},
                headers=auth_headers(token),
            ).raise_for_status()


def upload_csv(client: httpx.Client, token: str) -> dict:
    with CSV_PATH.open("rb") as f:
        r = client.post(
            f"{BASE}/products/upload-csv",
            files={"file": ("sample_products.csv", f, "text/csv")},
            headers=auth_headers(token),
        )
    r.raise_for_status()
    return r.json()


def list_by_status(client: httpx.Client, token: str, status: str) -> list[dict]:
    r = client.get(
        f"{BASE}/products",
        params={"status": status, "page_size": 100, "sort": "schedule" if status == "scheduled" else "newest"},
        headers=auth_headers(token),
    )
    r.raise_for_status()
    return r.json()["items"]


def update_schedule(client: httpx.Client, token: str, product_id: int, schedule_date: str, schedule_time: str) -> dict:
    r = client.put(
        f"{BASE}/products/{product_id}",
        json={"schedule_date": schedule_date, "schedule_time": schedule_time},
        headers=auth_headers(token),
    )
    r.raise_for_status()
    return r.json()


def fmt_slot(p: dict) -> str:
    err = (p.get("error_message") or "")[:60]
    return f"{p.get('schedule_date')} {p.get('schedule_time')} [{p['status']}] {p['name'][:35]} | {err}"


def main() -> int:
    now = now_italy()
    today = now.strftime("%Y-%m-%d")
    past_grace_time = (now - timedelta(minutes=2)).strftime("%H:%M")
    past_expired_time = (now - timedelta(minutes=10)).strftime("%H:%M")
    near_future = (now + timedelta(minutes=8)).strftime("%H:%M")
    far_future = (now + timedelta(hours=2)).strftime("%H:%M")

    print(f"Italy now: {now.strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"Test — grace past {past_grace_time}, expired past {past_expired_time}, near {near_future}")

    with httpx.Client(timeout=60.0) as client:
        health = client.get("http://127.0.0.1:8002/health").json()
        assert health["timezone"] == "Europe/Rome", health

        token = login(client)
        print("Login OK")

        db = SessionLocal()
        db.query(ProductPost).filter(ProductPost.user_id == USER_ID).delete()
        db.commit()
        db.close()

        upload_result = upload_csv(client, token)
        print(f"CSV upload: imported={upload_result.get('imported')} dup={upload_result.get('duplicates_skipped')}")

        scheduled = list_by_status(client, token, "scheduled")
        assert scheduled, "Expected scheduled products after CSV upload"

        past_grace_id = scheduled[0]["id"]
        past_expired_id = scheduled[1]["id"]
        near_id = scheduled[2]["id"]
        far_id = scheduled[3]["id"]

        update_schedule(client, token, past_grace_id, today, past_grace_time)
        update_schedule(client, token, past_expired_id, today, past_expired_time)
        update_schedule(client, token, near_id, today, near_future)
        update_schedule(client, token, far_id, today, far_future)

        scheduled_after = list_by_status(client, token, "scheduled")
        failed = list_by_status(client, token, "failed")
        stats = client.get(f"{BASE}/products/stats", headers=auth_headers(token)).json()

        print("\n--- Scheduled ---")
        for p in scheduled_after:
            print(" ", fmt_slot(p))
        print("\n--- Failed (includes missed-time) ---")
        for p in failed:
            print(" ", fmt_slot(p))
        print(f"\nStats: scheduled={stats['scheduled']} failed={stats['failed']}")

        errors: list[str] = []
        failed_ids = {p["id"] for p in failed}
        scheduled_ids = {p["id"] for p in scheduled_after}

        if past_grace_id in failed_ids:
            errors.append(f"Product {past_grace_id} (2 min past) must NOT be Failed yet — bot grace window")
        if past_grace_id in scheduled_ids:
            errors.append(f"Product {past_grace_id} (2 min past) must NOT show in Scheduled UI")
        if past_expired_id not in failed_ids:
            errors.append(f"Product {past_expired_id} (10 min past) must be in Failed list")
        expired_row = next((p for p in failed if p["id"] == past_expired_id), None)
        if expired_row and "Missed scheduled time" not in (expired_row.get("error_message") or ""):
            errors.append("Expired past product should have Missed scheduled time message")

        if near_id not in scheduled_ids:
            errors.append(f"Near-future product {near_id} should stay Scheduled")
        if scheduled_after and scheduled_after[0]["id"] != near_id:
            errors.append(f"Nearest future should be id={near_id}, got {scheduled_after[0]['id']}")

        db = SessionLocal()
        try:
            from app.services.product_posting_service import PUBLISH_GRACE_AFTER_SEC

            mark_past_schedules_missed(db, USER_ID, now)
            grace_row = db.query(ProductPost).filter(ProductPost.id == past_grace_id).first()
            if not grace_row or grace_row.status != ProductStatus.SCHEDULED:
                errors.append("2-min-past product must stay SCHEDULED in DB during grace")
            else:
                print("Grace window OK — recent past slot still SCHEDULED for bot")

            nxt, due = pick_next_scheduled(db, USER_ID, now)
            if not nxt or nxt.id != near_id:
                errors.append(
                    f"pick_next must prefer nearest FUTURE id={near_id}, got {nxt.id if nxt else None}"
                )
            else:
                print(f"pick_next OK (future first): {nxt.name[:30]} at {due.strftime('%H:%M') if due else '?'}")

            publish_fail = ProductPost(
                user_id=USER_ID,
                name="TEST publish fail",
                description="x",
                price=10.0,
                currency="EUR",
                images="[]",
                schedule_date=today,
                schedule_time=past_expired_time,
                status=ProductStatus.FAILED,
                content_hash="testpublishfailhash123456789012345678901234",
                error_message="Facebook login required",
            )
            db.add(publish_fail)
            db.commit()
            db.refresh(publish_fail)
            mark_past_schedules_missed(db, USER_ID, now)
            db.refresh(publish_fail)
            if publish_fail.status != ProductStatus.FAILED:
                errors.append("Publish-failure row must stay FAILED")
            elif "Facebook login" not in (publish_fail.error_message or ""):
                errors.append("Publish-failure message overwritten")
            else:
                print("Publish failure row preserved OK")
            db.delete(publish_fail)
            db.commit()
        finally:
            db.close()

        if errors:
            print("\nFAILURES:")
            for e in errors:
                print(" -", e)
            return 1

        print("\nAll checks passed — bot grace OK, expired past in Failed, future in Scheduled.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
