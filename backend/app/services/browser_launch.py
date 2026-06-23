"""Playwright Chromium — session cookies in facebook_session.json (no Chrome profile)."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from playwright.async_api import Browser, BrowserContext, Page, Playwright

from app.config import Settings, get_settings
from app.playwright_browsers import configure_playwright_browsers_path, is_chromium_installed
from app.services.facebook_session import USER_AGENT, session_file

configure_playwright_browsers_path()

logger = logging.getLogger(__name__)

LAUNCH_TIMEOUT_SECONDS = 90
DESKTOP_VIEWPORT = {"width": 1920, "height": 1080}

_VISIBLE_ARGS = [
    "--start-maximized",
    "--window-position=0,0",
    "--force-device-scale-factor=1",
]


def _locale_args(cfg: Settings) -> list[str]:
    lang = cfg.BROWSER_LOCALE
    return [f"--lang={lang}", f"--accept-lang={lang},it;q=0.9"]


def _context_kwargs(cfg: Settings, *, headless: bool) -> dict:
    kwargs: dict = {
        "locale": cfg.BROWSER_LOCALE,
        "timezone_id": cfg.BROWSER_TIMEZONE,
        "extra_http_headers": {
            "Accept-Language": f"{cfg.BROWSER_LOCALE},it;q=0.9,en;q=0.8",
        },
    }
    if headless:
        kwargs["viewport"] = DESKTOP_VIEWPORT
        kwargs["user_agent"] = USER_AGENT
        kwargs["device_scale_factor"] = 1
        kwargs["screen"] = {"width": 1920, "height": 1080}
    else:
        # Real maximized window — do NOT emulate a fixed viewport (hides fixed sidebar Next).
        kwargs["no_viewport"] = True
        kwargs["screen"] = {"width": 1920, "height": 1080}
    path: Path = session_file(cfg)
    if path.exists():
        kwargs["storage_state"] = str(path)
    return kwargs


async def launch_facebook_context(
    playwright: Playwright,
    cfg: Settings,
    *,
    headless: bool,
) -> tuple[BrowserContext, Page, Browser | None]:
    """Playwright bundled Chromium — cookies restored from facebook_session.json."""
    if not is_chromium_installed():
        raise RuntimeError(
            "Playwright Chromium is not installed. Run install-chromium.bat once, then Start ON."
        )
    try:
        browser = await asyncio.wait_for(
            playwright.chromium.launch(
                headless=headless,
                args=(list(_VISIBLE_ARGS) + _locale_args(cfg)) if not headless else _locale_args(cfg),
            ),
            timeout=LAUNCH_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        msg = str(exc)
        if "Executable doesn't exist" in msg or "playwright install" in msg.lower():
            raise RuntimeError(
                "Playwright Chromium is not installed. Run install-chromium.bat once "
                "(one-time ~180 MB download), then press Start ON again."
            ) from exc
        raise
    context = await browser.new_context(**_context_kwargs(cfg, headless=headless))
    page = await context.new_page()
    logger.info(
        "Playwright Chromium ready (headless=%s, no_viewport=%s, session=%s)",
        headless,
        not headless,
        session_file(cfg).exists(),
    )
    return context, page, browser


async def launch_chromium(playwright: Playwright, headless: bool) -> Browser:
    cfg = get_settings()
    return await asyncio.wait_for(
        playwright.chromium.launch(
            headless=headless,
            args=(list(_VISIBLE_ARGS) + _locale_args(cfg)) if not headless else _locale_args(cfg),
        ),
        timeout=LAUNCH_TIMEOUT_SECONDS,
    )
