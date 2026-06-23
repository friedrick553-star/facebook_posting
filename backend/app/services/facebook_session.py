"""Facebook session — Playwright Chromium + cookie backup in facebook_session.json."""
from __future__ import annotations

import asyncio
import logging
import re
import shutil
import time
from pathlib import Path

from playwright.async_api import BrowserContext, Page

from app.config import Settings, get_settings
from app.services.user_workspace import resolve_profile_dir, resolve_session_file
from app.services.scan_control import is_scan_cancelled

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

MARKETPLACE_URL = "https://it-it.facebook.com/marketplace/"
PASSIVE_LOGIN_POLL_SECONDS = 2
POST_LOGIN_SETTLE_SECONDS = 5


def session_file(cfg: Settings | None = None) -> Path:
    cfg = cfg or get_settings()
    return resolve_session_file(cfg)


def profile_dir(cfg: Settings | None = None) -> Path:
    cfg = cfg or get_settings()
    return resolve_profile_dir(cfg)


def clear_facebook_browser_data(cfg: Settings | None = None) -> dict:
    cfg = cfg or get_settings()
    removed_session = clear_session_file(cfg)
    profile = profile_dir(cfg)
    removed_profile = False
    profile_still_exists = False

    if profile.exists():
        for attempt in range(5):
            try:
                shutil.rmtree(profile)
                removed_profile = True
                break
            except Exception as exc:
                logger.warning("Profile delete attempt %s/5 failed: %s", attempt + 1, exc)
                time.sleep(0.8 * (attempt + 1))
        profile_still_exists = profile.exists()

    profile.mkdir(parents=True, exist_ok=True)
    return {
        "session_file": removed_session,
        "profile_dir": removed_profile and not profile_still_exists,
        "profile_cleared": not profile_still_exists,
    }


def clear_session_file(cfg: Settings | None = None) -> bool:
    cfg = cfg or get_settings()
    path = session_file(cfg)
    if path.exists():
        path.unlink()
        return True
    return False


def is_on_facebook_auth_flow(page: Page) -> bool:
    """Passive URL check — user is still logging in or on Facebook verification."""
    url = page.url.lower()
    if any(
        token in url
        for token in (
            "checkpoint",
            "two_step",
            "two_step_verification",
            "authentication",
            "confirmemail",
            "recover",
        )
    ):
        return True
    if "/login" in url and "marketplace" not in url:
        return True
    return False


def needs_marketplace_navigation(page: Page) -> bool:
    """True when browser should go to Marketplace — never during login/2FA."""
    if is_on_facebook_auth_flow(page):
        return False
    url = page.url.lower().strip()
    if not url or url == "about:blank" or url.startswith("chrome://"):
        return True
    return "marketplace" not in url


async def has_login_cookies(context: BrowserContext) -> bool:
    """Passive — full Facebook session (login + verification done)."""
    try:
        names = {c.get("name") for c in await context.cookies() if c.get("value")}
        return "c_user" in names and "xs" in names
    except Exception:
        pass
    return False


async def is_login_fully_complete(context: BrowserContext, page: Page) -> bool:
    """
    Login is done only when full session cookies exist, auth pages are left,
    and Marketplace is usable (guest preview does not count as logged in).
    """
    if not await has_login_cookies(context):
        return False
    if is_on_facebook_auth_flow(page):
        return False
    return await _is_marketplace_ready(page, context)


LOGIN_WALL_PHRASES = (
    "See more on Facebook",
    "Log in to Facebook",
    "Log Into Facebook",
    "Vedi di più su Facebook",
    "Accedi a Facebook",
    "Altro su Facebook",
)

LOGIN_DIALOG_PATTERN = re.compile(
    r"See more on Facebook|Log in to Facebook|Log Into Facebook|"
    r"Vedi di più su Facebook|Accedi a Facebook|Altro su Facebook|"
    r"Crea nuovo account|Create new account",
    re.I,
)


async def _has_login_wall(page: Page) -> bool:
    if is_on_facebook_auth_flow(page):
        return True
    for phrase in LOGIN_WALL_PHRASES:
        try:
            if await page.get_by_text(phrase, exact=False).first.is_visible(timeout=400):
                return True
        except Exception:
            pass
    return False


async def _login_overlay_visible(page: Page) -> bool:
    if is_on_facebook_auth_flow(page):
        return False
    patterns = LOGIN_DIALOG_PATTERN
    try:
        dialogs = page.locator('[role="dialog"], [aria-modal="true"]')
        count = await dialogs.count()
        for i in range(count):
            dialog = dialogs.nth(i)
            if not await dialog.is_visible(timeout=300):
                continue
            text = await dialog.inner_text()
            if patterns.search(text):
                return True
    except Exception:
        pass
    return False


async def _is_marketplace_ready(page: Page, context: BrowserContext | None = None) -> bool:
    if is_on_facebook_auth_flow(page):
        return False
    if context is not None and not await has_login_cookies(context):
        return False
    if await _has_login_wall(page):
        return False
    if await _login_overlay_visible(page):
        return False

    for sel in (
        'input[placeholder*="Search Marketplace" i]',
        'a[href*="/marketplace/category/"]',
        'a[href*="/marketplace/item/"]',
    ):
        try:
            if await page.locator(sel).first.is_visible(timeout=1500):
                return True
        except Exception:
            continue
    return False


async def _is_login_required(page: Page) -> bool:
    if is_on_facebook_auth_flow(page):
        return True
    if await _has_login_wall(page):
        return True
    if await _login_overlay_visible(page):
        return True
    return not await _is_marketplace_ready(page)


async def dismiss_login_popup_once(page: Page) -> bool:
    """
    Close the Marketplace login modal (X) so the user can log in via the top header
    Email/Password fields — not through the popup (popup uses a separate Facebook flow).
    Never runs on login/checkpoint/authentication pages.
    """
    if is_on_facebook_auth_flow(page):
        return False
    if "marketplace" not in page.url.lower():
        return False

    try:
        dialog = page.locator('[role="dialog"]').filter(has_text=LOGIN_DIALOG_PATTERN).first
        if not await dialog.is_visible(timeout=2000):
            return False
        for close_sel in (
            '[aria-label="Close"]', '[aria-label="close"]',
            '[aria-label="Chiudi"]', '[aria-label="chiudi"]',
        ):
            close_btn = dialog.locator(close_sel).first
            if await close_btn.is_visible(timeout=800):
                await close_btn.click()
                await asyncio.sleep(1.0)
                return True
    except Exception:
        pass
    return False


async def dismiss_all_login_overlays(page: Page) -> bool:
    return await dismiss_login_popup_once(page)


async def reload_marketplace_after_login(page: Page, cfg: Settings) -> None:
    """Only after login + authentication fully finished — never during checkpoint."""
    if is_on_facebook_auth_flow(page):
        return
    await page.goto(
        MARKETPLACE_URL,
        wait_until="domcontentloaded",
        timeout=max(cfg.PLAYWRIGHT_TIMEOUT, 90000),
    )
    await asyncio.sleep(2)
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=12000)
    except Exception:
        pass


async def wait_passive_for_login(
    context: BrowserContext,
    page: Page,
    *,
    timeout_seconds: int = 900,
) -> bool:
    """
    Bot is completely static while user logs in manually.
    After 5 minutes without login, sends one email reminder to admin/alert recipients.
    """
    from app.services.login_reminder_service import (
        LOGIN_REMINDER_AFTER_SECONDS,
        send_facebook_login_reminder,
    )

    deadline = time.monotonic() + timeout_seconds
    started = time.monotonic()
    reminder_sent = False

    while time.monotonic() < deadline:
        if is_scan_cancelled():
            return False
        if await is_login_fully_complete(context, page):
            return True

        try:
            await dismiss_login_popup_once(page)
        except Exception:
            pass

        elapsed = time.monotonic() - started
        if not reminder_sent and elapsed >= LOGIN_REMINDER_AFTER_SECONDS:
            reminder_sent = True
            logger.info("Facebook login still pending after 5 minutes — sending reminder email")
            try:
                await send_facebook_login_reminder()
            except Exception as exc:
                logger.warning("Login reminder email failed: %s", exc)

        await asyncio.sleep(PASSIVE_LOGIN_POLL_SECONDS)
    return False


async def wait_until_marketplace_logged_in(
    page: Page,
    context: BrowserContext,
    cfg: Settings,
    *,
    log_fn=None,
    timeout_seconds: int = 900,
) -> bool:
    if log_fn:
        log_fn(
            "Bot paused — finish login and any Facebook verification in the browser",
            {"timeout_seconds": timeout_seconds},
        )
    return await wait_passive_for_login(context, page, timeout_seconds=timeout_seconds)


async def save_session(context: BrowserContext, cfg: Settings) -> None:
    try:
        await context.storage_state(path=str(session_file(cfg)))
    except Exception as exc:
        logger.warning("Could not save session backup: %s", exc)


def has_facebook_session_saved(cfg: Settings | None = None) -> bool:
    """True when facebook_session.json contains c_user + xs cookies."""
    import json

    cfg = cfg or get_settings()
    path = session_file(cfg)
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        names = {c.get("name") for c in data.get("cookies", []) if c.get("value")}
        return "c_user" in names and "xs" in names
    except Exception:
        return False


def _normalize_cookie_entry(raw: dict) -> dict | None:
    name = (raw.get("name") or "").strip()
    value = raw.get("value")
    if not name or value is None or str(value).strip() == "":
        return None
    domain = (raw.get("domain") or ".facebook.com").strip()
    if "facebook" in domain and not domain.startswith("."):
        domain = f".{domain.lstrip('.')}"
    expires = raw.get("expires", -1)
    if expires in (None, ""):
        expires = -1
    same_site = raw.get("sameSite") or raw.get("same_site") or "None"
    return {
        "name": name,
        "value": str(value),
        "domain": domain or ".facebook.com",
        "path": raw.get("path") or "/",
        "expires": expires,
        "httpOnly": bool(raw.get("httpOnly", raw.get("http_only", True))),
        "secure": bool(raw.get("secure", True)),
        "sameSite": same_site,
    }


def parse_facebook_cookies(raw: str) -> dict:
    """
    Build Playwright storage_state from:
    - Playwright storage_state JSON
    - JSON array of cookie objects
    - document.cookie string (c_user=...; xs=...)
    """
    import json
    from datetime import datetime, timezone

    text = (raw or "").strip()
    if not text:
        raise ValueError("Cookie data is empty")

    cookie_rows: list[dict] = []

    if text.startswith("{"):
        data = json.loads(text)
        if isinstance(data.get("cookies"), list):
            cookie_rows = data["cookies"]
        else:
            raise ValueError("JSON must include a cookies array")
    elif text.startswith("["):
        cookie_rows = json.loads(text)
    else:
        for part in text.split(";"):
            part = part.strip()
            if not part or "=" not in part:
                continue
            name, _, value = part.partition("=")
            cookie_rows.append({"name": name.strip(), "value": value.strip(), "domain": ".facebook.com"})

    normalized: list[dict] = []
    for row in cookie_rows:
        if not isinstance(row, dict):
            continue
        entry = _normalize_cookie_entry(row)
        if entry:
            normalized.append(entry)

    if not normalized:
        raise ValueError("No valid cookies found")

    names = {c["name"] for c in normalized}
    if "c_user" not in names or "xs" not in names:
        raise ValueError("Missing Facebook login cookies — c_user and xs are required")

    fallback_expires = int(datetime.now(timezone.utc).timestamp()) + 86400 * 180
    for c in normalized:
        if c["expires"] in (-1, 0):
            c["expires"] = fallback_expires

    return {"cookies": normalized, "origins": []}


def import_facebook_session(raw: str, cfg: Settings | None = None) -> dict:
    """Save imported browser cookies to facebook_session.json."""
    import json

    cfg = cfg or get_settings()
    state = parse_facebook_cookies(raw)
    path = session_file(cfg)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return {
        "has_session": True,
        "cookie_count": len(state["cookies"]),
        "path": str(path),
    }
