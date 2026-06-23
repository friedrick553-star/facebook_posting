"""Staged Facebook Marketplace scan flow with activity logging."""
from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass
from typing import Callable

from playwright.async_api import Browser, BrowserContext, Page
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import LogCategory, LogLevel
from app.services.facebook_session import (
    USER_AGENT,
    MARKETPLACE_URL,
    POST_LOGIN_SETTLE_SECONDS,
    dismiss_login_popup_once,
    is_login_fully_complete,
    is_on_facebook_auth_flow,
    _is_login_required,
    _is_marketplace_ready,
    reload_marketplace_after_login,
    save_session,
    session_file,
    wait_passive_for_login,
)
from app.services.log_service import log_activity_isolated

logger = logging.getLogger(__name__)

MANUAL_LOGIN_WAIT_SECONDS = 900
VEHICLES_CATEGORY_URL = "https://www.facebook.com/marketplace/category/vehicles"
VEHICLES_CATEGORY_ID = "546583916084032"
STEP_PAUSE = 1.5
NAV_RETRIES = 3
BEFORE_VEHICLES_DELAY_SECONDS = 5


def clean_fb_url(url: str) -> str:
    """Strip Facebook redirect noise (_rdc, _rdr) for logs — harmless tracking params."""
    return (url or "").split("?")[0].rstrip("/")


def _price_query_from_url(url: str) -> tuple[str | None, str | None]:
    from urllib.parse import parse_qs, urlparse

    qs = parse_qs(urlparse(url or "").query)
    min_p = (qs.get("minPrice") or qs.get("minprice") or [None])[0]
    max_p = (qs.get("maxPrice") or qs.get("maxprice") or [None])[0]
    return min_p, max_p


def _normalize_price_digits(value: str | None) -> int | None:
    if not value:
        return None
    digits = re.sub(r"[^\d]", "", value.replace("'", "").replace(",", ""))
    return int(digits) if digits else None


async def _read_price_filter_state(page: Page) -> dict:
    """Read Min/Max price from sidebar inputs and URL query params."""
    min_input, max_input = await _find_price_inputs(page)
    input_min = input_max = None
    if min_input:
        try:
            input_min = (await min_input.input_value()).strip()
        except Exception:
            pass
    if max_input:
        try:
            input_max = (await max_input.input_value()).strip()
        except Exception:
            pass

    url_min, url_max = _price_query_from_url(page.url)
    return {
        "url": page.url,
        "url_min_price": url_min,
        "url_max_price": url_max,
        "input_min": input_min or None,
        "input_max": input_max or None,
        "input_min_value": _normalize_price_digits(input_min),
        "input_max_value": _normalize_price_digits(input_max),
    }


async def _fill_price_input(input_loc, value: int) -> None:
    await input_loc.click()
    await input_loc.press("Control+A")
    await input_loc.fill(str(value))
    await asyncio.sleep(0.3)
    await input_loc.press("Enter")
    await asyncio.sleep(1.2)


async def _fast_goto(
    page: Page,
    url: str,
    *,
    nav_timeout: int = 60000,
) -> None:
    """Navigate without waiting for full DOM — used after Marketplace 5s wait."""
    await page.goto(url, wait_until="commit", timeout=nav_timeout)


def vehicles_search_url(city: str) -> str:
    """Direct Vehicles search URL — e.g. /marketplace/zurich/search/?category_id=…&query=Vehicles"""
    slug = (
        city.lower()
        .strip()
        .replace("ü", "u")
        .replace("ö", "o")
        .replace("ä", "a")
        .replace(" ", "")
    )
    return (
        f"https://www.facebook.com/marketplace/{slug}/search/"
        f"?category_id={VEHICLES_CATEGORY_ID}&query=Vehicles&referral_ui_component=category_menu_item"
    )


# Backwards-compatible alias
_vehicles_search_fallback_url = vehicles_search_url


def _is_on_vehicles_page(page: Page) -> bool:
    url = page.url.lower()
    if "/marketplace/category/vehicles" in url:
        return True
    if "/marketplace/" in url and "/search/" in url and "category_id=" in url and "vehicles" in url:
        return True
    return False


async def _vehicles_filters_sidebar_ready(page: Page, *, timeout_ms: int = 15000) -> bool:
    """Filters sidebar visible — location row NOT required yet (Stage 4 sets location)."""
    try:
        await page.wait_for_function(
            """
            () => {
                const sidebar =
                    document.querySelector('[data-pagelet="MarketplaceLeftRail"]') ||
                    document.querySelector('[data-pagelet="MarketplaceSidebar"]') ||
                    document.querySelector('aside');
                const blob = sidebar ? sidebar.innerText : document.body.innerText;
                return blob.includes('Filters');
            }
            """,
            timeout=timeout_ms,
        )
        return True
    except Exception:
        return False


async def _open_vehicles_page(
    page: Page,
    log: LogFn,
    *,
    nav_timeout: int,
    location: MarketplaceLocation | None = None,
) -> None:
    """Marketplace done → open /category/vehicles (normal browser URL, no city pre-set)."""
    log("Stage 3/7 — Opening Vehicles category", {"url": VEHICLES_CATEGORY_URL})
    await _safe_goto(page, VEHICLES_CATEGORY_URL, log, "Stage 3/7", nav_timeout=nav_timeout)
    await asyncio.sleep(0.5)
    log("Stage 3/7 — Vehicles category loaded", {"url": clean_fb_url(page.url)})


async def _require_scrape_page_ready(page: Page, log: LogFn, stage: str) -> None:
    """On Vehicles search page we only need Filters — not Marketplace home."""
    if _is_on_vehicles_page(page):
        return
    await require_marketplace_ready(page, log, stage)


async def _safe_goto(
    page: Page,
    url: str,
    log: LogFn,
    label: str,
    *,
    nav_timeout: int = 60000,
) -> None:
    last_error: Exception | None = None
    for attempt in range(1, NAV_RETRIES + 1):
        try:
            await page.goto(url, wait_until="commit", timeout=nav_timeout)
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=min(45000, nav_timeout))
            except Exception:
                pass
            return
        except Exception as exc:
            last_error = exc
            if attempt < NAV_RETRIES:
                log(
                    f"{label} — page load slow, retry {attempt + 1}/{NAV_RETRIES}",
                    {"url": url, "error": str(exc)},
                    level=LogLevel.WARNING,
                )
                await asyncio.sleep(2)
    raise last_error or RuntimeError(f"Failed to open {url}")


async def require_marketplace_ready(page: Page, log: LogFn, stage: str, context: BrowserContext | None = None) -> None:
    """Stop the scan if Facebook login wall is still blocking Marketplace."""
    if await _is_marketplace_ready(page, context):
        return
    if await _is_login_required(page):
        log(
            f"{stage} — blocked: Facebook login required (complete login in browser first)",
            level=LogLevel.ERROR,
        )
        raise RuntimeError("Facebook login required — Marketplace is blocked by login popup")
    log(f"{stage} — Marketplace not ready", level=LogLevel.ERROR)
    raise RuntimeError("Facebook Marketplace not ready")


@dataclass
class MarketplaceLocation:
    city: str
    country: str | None
    radius_km: int

    @property
    def label(self) -> str:
        if self.country:
            return f"{self.city}, {self.country}"
        return self.city


LogFn = Callable[[str, dict | None, LogLevel], None]


def _make_db_logger(db: Session | None) -> LogFn:
    """Scraper logs use an isolated DB session so manual login waits do not hold transactions open."""

    def _log(message: str, details: dict | None = None, level: LogLevel = LogLevel.INFO) -> None:
        if details:
            logger.info("%s | %s", message, details)
        else:
            logger.info("%s", message)
        log_activity_isolated(LogCategory.SCRAPER, message, level=level, details=details, source="facebook")

    return _log


async def _create_context(
    browser: Browser, cfg: Settings, *, headless: bool = True
) -> tuple[BrowserContext, Page]:
    path = session_file(cfg)
    context_kwargs: dict = {
        "locale": cfg.BROWSER_LOCALE,
        "timezone_id": cfg.BROWSER_TIMEZONE,
        "extra_http_headers": {
            "Accept-Language": f"{cfg.BROWSER_LOCALE},it;q=0.9,en;q=0.8",
        },
    }
    if headless:
        context_kwargs["user_agent"] = USER_AGENT
        context_kwargs["viewport"] = {"width": 1920, "height": 1080}
        context_kwargs["device_scale_factor"] = 1
    else:
        # Use the real maximized window so the fixed sidebar Next button stays on screen.
        context_kwargs["no_viewport"] = True
        context_kwargs["screen"] = {"width": 1920, "height": 1080}
        # Do not override user_agent in visible mode — real Chrome UA keeps Facebook auth working.

    if path.exists():
        context_kwargs["storage_state"] = str(path)

    context = await browser.new_context(**context_kwargs)
    page = await context.new_page()
    return context, page


async def stage_open_marketplace(
    page: Page,
    cfg: Settings,
    log: LogFn,
    *,
    context: BrowserContext | None = None,
    nav_timeout: int | None = None,
) -> None:
    timeout = nav_timeout or cfg.PLAYWRIGHT_TIMEOUT
    log("Stage 1/7 — Opening Facebook Marketplace", {"url": MARKETPLACE_URL})
    await _safe_goto(page, MARKETPLACE_URL, log, "Stage 1/7", nav_timeout=timeout)
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=min(15000, timeout))
    except Exception:
        pass
    await asyncio.sleep(1.0)

    if is_on_facebook_auth_flow(page):
        log("Stage 1/7 — Facebook login/verification page — bot stays completely idle")
        return

    if context and await is_login_fully_complete(context, page):
        log("Stage 1/7 — Marketplace loaded (logged in)", {"url": clean_fb_url(page.url)})
    else:
        dismissed = await dismiss_login_popup_once(page)
        if dismissed:
            log(
                "Stage 1/7 — Login popup closed — log in using Email/Password in the top header (not the popup)",
            )
        else:
            log(
                "Stage 1/7 — Not logged in — log in using Email/Password in the top header",
                {"url": page.url},
            )
        log(
            "Stage 1/7 — Bot idle on Marketplace (login reminder email after 5 minutes)",
        )


async def stage_ensure_login(page: Page, context: BrowserContext, cfg: Settings, log: LogFn, db: Session | None = None) -> bool:
    log("Stage 2/7 — Checking Facebook login")

    if await is_login_fully_complete(context, page):
        log("Stage 2/7 — Logged in (saved session)")
        await save_session(context, cfg)
        return True

    if is_on_facebook_auth_flow(page):
        log("Stage 2/7 — Complete Facebook login/verification in browser — bot is completely idle")
    else:
        if "marketplace" in page.url.lower():
            if await dismiss_login_popup_once(page):
                log("Stage 2/7 — Login popup closed — use top header Email/Password to log in")
        log(
            "Stage 2/7 — Not logged in — bot stays static until you log in via the top header "
            "(reminder email after 5 minutes)",
            {"url": page.url},
        )

    if await wait_passive_for_login(context, page, timeout_seconds=MANUAL_LOGIN_WAIT_SECONDS):
        log("Stage 2/7 — Login and verification complete — opening Marketplace")
        await asyncio.sleep(POST_LOGIN_SETTLE_SECONDS)
        if not is_on_facebook_auth_flow(page):
            await reload_marketplace_after_login(page, cfg)
        if not await _is_marketplace_ready(page, context):
            log("Stage 2/7 — Marketplace not ready after login", level=LogLevel.ERROR)
            return False
        await save_session(context, cfg)
        log("Stage 2/7 — Login complete — Marketplace ready")
        return True

    log("Stage 2/7 — Login timed out", level=LogLevel.ERROR)
    return False


async def _wait_marketplace_ready(
    page: Page,
    log: LogFn,
    stage: str,
    *,
    context: BrowserContext | None = None,
    timeout_sec: int = 45,
) -> None:
    for _ in range(timeout_sec):
        if await _is_marketplace_ready(page, context):
            return
        await asyncio.sleep(1)
    await require_marketplace_ready(page, log, stage, context)


async def _find_marketplace_sidebar(page: Page):
    for sel in (
        'div[data-pagelet="MarketplaceLeftRail"]',
        'div[data-pagelet="MarketplaceSidebar"]',
        '[role="navigation"]',
        "aside",
    ):
        loc = page.locator(sel).first
        try:
            if await loc.is_visible(timeout=1500):
                return loc
        except Exception:
            continue
    return page.locator("body")


async def _wait_location_dialog(page: Page, timeout_ms: int = 8000):
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        dialogs = page.locator('[role="dialog"], [aria-modal="true"]')
        count = await dialogs.count()
        for i in range(count - 1, -1, -1):
            dialog = dialogs.nth(i)
            try:
                if not await dialog.is_visible(timeout=400):
                    continue
                text = (await dialog.inner_text()).lower()
                if any(k in text for k in ("location", "radius", "change location", "kilomet", "mile")):
                    await _normalize_location_panel(page, dialog)
                    return dialog
            except Exception:
                continue

        # Popover panel (no role=dialog) — often stuck bottom-right in Playwright
        panel = page.locator(
            'div:has(input[placeholder*="Location" i]), '
            'div:has(input[aria-label*="Location" i]), '
            'div:has([role="combobox"])'
        ).filter(has_text=re.compile(r"location|radius|apply", re.I))
        try:
            if await panel.count() > 0:
                candidate = panel.last
                if await candidate.is_visible(timeout=400):
                    await _normalize_location_panel(page, candidate)
                    return candidate
        except Exception:
            pass

        await asyncio.sleep(0.3)
    return None


async def _normalize_location_panel(page: Page, panel) -> None:
    """Force location form centered + scrollable like normal Chrome."""
    try:
        await panel.evaluate(
            """
            (el) => {
                const r = el.getBoundingClientRect();
                const stuckCorner =
                    r.left > window.innerWidth * 0.45 ||
                    r.top > window.innerHeight * 0.45 ||
                    r.bottom > window.innerHeight - 40;

                el.style.setProperty('position', 'fixed', 'important');
                el.style.setProperty('top', '50%', 'important');
                el.style.setProperty('left', '50%', 'important');
                el.style.setProperty('transform', 'translate(-50%, -50%)', 'important');
                el.style.setProperty('right', 'auto', 'important');
                el.style.setProperty('bottom', 'auto', 'important');
                el.style.setProperty('max-height', '85vh', 'important');
                el.style.setProperty('max-width', 'min(480px, 92vw)', 'important');
                el.style.setProperty('overflow-y', 'auto', 'important');
                el.style.setProperty('overflow-x', 'hidden', 'important');
                el.style.setProperty('z-index', '999999', 'important');
                el.style.setProperty('box-shadow', '0 8px 32px rgba(0,0,0,0.24)', 'important');

                if (stuckCorner) {
                    el.dataset.fbPanelFixed = '1';
                }

                for (const child of el.querySelectorAll('*')) {
                    if (child.scrollHeight > child.clientHeight + 12 && child.clientHeight > 80) {
                        child.style.overflowY = 'auto';
                        child.style.maxHeight = '70vh';
                    }
                }
            }
            """
        )
    except Exception:
        pass
    await asyncio.sleep(0.3)


SIDEBAR_LOCATION_PATTERN = re.compile(r"within\s+\d+\s*(km|mi|miles|kilomet)", re.I)
WITHIN_RADIUS_PATTERN = re.compile(r"within\s+(\d+)\s*(km|mi|miles|kilomet)", re.I)


def _miles_to_km(miles: int) -> int:
    return round(miles * 1.609344)


def _parse_sidebar_location_text(text: str) -> dict | None:
    cleaned = re.sub(r"\s+", " ", (text or "")).strip()
    match = WITHIN_RADIUS_PATTERN.search(cleaned)
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2).lower()
    radius_km = _miles_to_km(amount) if unit in ("mi", "miles") else amount
    city_part = cleaned[: match.start()].strip(" ·•-\u00a0")
    if not city_part:
        return None
    return {"city": city_part, "radius_km": radius_km, "raw": cleaned}


def _sidebar_locator(page: Page):
    return page.locator(
        '[data-pagelet="MarketplaceLeftRail"], [data-pagelet="MarketplaceSidebar"], aside'
    ).first


def _location_row_locator(page: Page):
    sidebar = _sidebar_locator(page)
    return sidebar.locator('span[dir="auto"]').filter(has_text=SIDEBAR_LOCATION_PATTERN)


async def _wait_vehicles_filters_ready(
    page: Page,
    log: LogFn,
    timeout_ms: int = 5000,
    *,
    require_location: bool = False,
) -> bool:
    """Wait for Filters sidebar. Location row only required after Stage 4."""
    log(
        "Stage 3/7 — Waiting for Filters sidebar on Vehicles page",
        {"timeout_ms": timeout_ms, "require_location": require_location},
    )
    await _scroll_sidebar_filters(page)
    try:
        if require_location:
            check_js = """
            () => {
                const sidebar =
                    document.querySelector('[data-pagelet="MarketplaceLeftRail"]') ||
                    document.querySelector('[data-pagelet="MarketplaceSidebar"]') ||
                    document.querySelector('aside');
                const blob = sidebar ? sidebar.innerText : document.body.innerText;
                const hasFilters = blob.includes('Filters');
                const hasLoc = /Within\\s+\\d+\\s*(km|mi|miles|kilomet)/i.test(blob);
                return hasFilters && hasLoc;
            }
            """
        else:
            check_js = """
            () => {
                const sidebar =
                    document.querySelector('[data-pagelet="MarketplaceLeftRail"]') ||
                    document.querySelector('[data-pagelet="MarketplaceSidebar"]') ||
                    document.querySelector('aside');
                const blob = sidebar ? sidebar.innerText : document.body.innerText;
                return blob.includes('Filters');
            }
            """
        await page.wait_for_function(check_js, timeout=timeout_ms)
        await _scroll_sidebar_filters(page)
        return True
    except Exception:
        log(
            "Stage 3/7 — Filters sidebar slow to load — continuing",
            level=LogLevel.WARNING,
        )
        return False


async def _find_location_row_coords(page: Page) -> dict | None:
    """Find span[dir=auto] e.g. 'Bahawalpur · Within 65 km' under Filters."""
    return await page.evaluate(
        """
        () => {
            const clean = (t) => (t || '').replace(/\\s+/g, ' ').trim();
            const isRow = (t) => /Within\\s+\\d+\\s*(km|mi|miles|kilomet)/i.test(t || '');

            const pick = (span) => {
                const t = clean(span.innerText || span.textContent);
                if (!isRow(t)) return null;
                span.scrollIntoView({ block: 'center', behavior: 'instant' });
                const r = span.getBoundingClientRect();
                if (r.width < 8 || r.height < 5) return null;
                if (r.left > window.innerWidth * 0.58) return null;
                return { text: t, x: r.x + r.width / 2, y: r.y + r.height / 2 };
            };

            const sidebar =
                document.querySelector('[data-pagelet="MarketplaceLeftRail"]') ||
                document.querySelector('[data-pagelet="MarketplaceSidebar"]');
            if (sidebar) {
                for (const span of sidebar.querySelectorAll('span[dir="auto"]')) {
                    const hit = pick(span);
                    if (hit) return hit;
                }
            }

            const filtersEl = [...document.querySelectorAll('h2 span, h2')].find(
                (el) => clean(el.textContent) === 'Filters'
            );
            if (filtersEl) {
                let block = filtersEl.closest('div.x78zum5');
                if (block && block.parentElement) block = block.parentElement;
                if (!block) block = filtersEl.closest('[data-pagelet="MarketplaceLeftRail"]');
                const searchRoot = block || document;
                for (const span of searchRoot.querySelectorAll('span[dir="auto"]')) {
                    const hit = pick(span);
                    if (hit) return hit;
                }
            }

            for (const span of document.querySelectorAll('span[dir="auto"]')) {
                const hit = pick(span);
                if (hit) return hit;
            }
            return null;
        }
        """
    )


def _norm_location_city(text: str) -> str:
    """Compare cities ignoring case and accents (Zürich vs Zurich)."""
    import unicodedata

    normalized = unicodedata.normalize("NFKD", text or "")
    ascii_city = normalized.encode("ascii", "ignore").decode("ascii")
    return ascii_city.lower().strip().split(",")[0].strip()


def _location_already_matches(current: dict, target: MarketplaceLocation) -> bool:
    current_city = _norm_location_city(current["city"])
    target_city = _norm_location_city(target.city)
    city_ok = current_city == target_city
    radius_ok = abs(current["radius_km"] - target.radius_km) <= max(3, int(target.radius_km * 0.12))
    return city_ok and radius_ok


async def _read_sidebar_location(page: Page) -> dict | None:
    row = await _find_visible_location_row(page)
    if row is None:
        return None
    try:
        raw = re.sub(r"\s+", " ", (await row.inner_text())).strip()
    except Exception:
        return None
    parsed = _parse_sidebar_location_text(raw)
    if parsed:
        parsed["raw"] = raw
    return parsed


async def _find_visible_location_row(page: Page):
    coords = await _find_location_row_coords(page)
    if not coords:
        return None
    rows = _location_row_locator(page)
    if await rows.count() > 0:
        return rows.first
    return page.locator('span[dir="auto"]').filter(has_text=SIDEBAR_LOCATION_PATTERN).first


async def _scroll_sidebar_filters(page: Page) -> None:
    sidebar = _sidebar_locator(page)
    try:
        if await sidebar.is_visible(timeout=2000):
            await sidebar.evaluate(
                """
                (sidebar) => {
                    sidebar.scrollTop = 0;
                    const isRow = (t) => /Within\\s+\\d+\\s*(km|mi|miles|kilomet)/i.test(t || '');
                    for (const span of sidebar.querySelectorAll('span[dir="auto"]')) {
                        if (isRow(span.textContent)) {
                            span.scrollIntoView({ block: 'center', behavior: 'instant' });
                            return;
                        }
                    }
                    for (const el of sidebar.querySelectorAll('h2, span')) {
                        if ((el.textContent || '').trim() === 'Filters') {
                            el.scrollIntoView({ block: 'start', behavior: 'instant' });
                            return;
                        }
                    }
                }
                """
            )
    except Exception:
        pass
    await page.evaluate("window.scrollTo(0, 0)")
    await asyncio.sleep(0.2)


async def _wait_for_sidebar_location_row(page: Page, log: LogFn) -> None:
    await _wait_vehicles_filters_ready(page, log)
    coords = await _find_location_row_coords(page)
    if coords:
        log("Stage 4/7 — Location row detected", {"text": coords["text"]})
    else:
        log("Stage 4/7 — Location row not found in DOM yet", level=LogLevel.WARNING)


async def _click_sidebar_location_row(page: Page, log: LogFn) -> bool:
    """Click span[dir=auto] under Filters — opens Change location dialog."""
    log("Stage 4/7 — Opening location dialog from Filters sidebar")

    for attempt in range(5):
        await _scroll_sidebar_filters(page)
        coords = await _find_location_row_coords(page)
        if coords:
            log(
                "Stage 4/7 — Mouse click on location row",
                {"text": coords["text"], "attempt": attempt + 1},
            )
            await page.mouse.click(coords["x"], coords["y"])
            await asyncio.sleep(0.55)
            dialog = await _wait_location_dialog(page, timeout_ms=8000)
            if dialog:
                return True

        try:
            row = _location_row_locator(page).first
            await row.scroll_into_view_if_needed(timeout=3000)
            await row.click(force=True, timeout=3000)
            await asyncio.sleep(0.55)
            if await _wait_location_dialog(page, timeout_ms=8000):
                log("Stage 4/7 — Location dialog opened (Playwright click)")
                return True
        except Exception:
            pass

        try:
            row = page.get_by_text(SIDEBAR_LOCATION_PATTERN).first
            await row.click(force=True, timeout=3000)
            await asyncio.sleep(0.55)
            if await _wait_location_dialog(page, timeout_ms=8000):
                return True
        except Exception:
            pass

        await asyncio.sleep(0.7)

    return False


async def _open_location_dialog(page: Page, log: LogFn):
    for try_num in range(3):
        if await _click_sidebar_location_row(page, log):
            dialog = await _wait_location_dialog(page, timeout_ms=8000)
            if dialog:
                return dialog
        log(
            "Stage 4/7 — Location dialog not open yet, retry sidebar click",
            {"try": try_num + 2},
            level=LogLevel.WARNING,
        )
        await _scroll_sidebar_filters(page)
        await asyncio.sleep(0.8)
    log("Stage 4/7 — Could not open Change location dialog", level=LogLevel.ERROR)
    return None


async def _pick_first_location_suggestion(page: Page, dialog, log: LogFn) -> None:
    """After typing location: wait for list, pick first suggestion, else keyboard."""
    log("Stage 4/7 — Selecting first location suggestion (top of list)")
    deadline = time.time() + 12
    while time.time() < deadline:
        for selector in (
            '[role="listbox"] [role="option"]',
            '[role="option"]',
            'ul[role="listbox"] li',
        ):
            options = dialog.locator(selector)
            count = await options.count()
            if count == 0:
                continue
            first = options.first
            try:
                if await first.is_visible(timeout=400):
                    text = re.sub(r"\s+", " ", (await first.inner_text())).strip()
                    await first.click()
                    log("Stage 4/7 — First suggestion selected", {"text": text})
                    await asyncio.sleep(0.35)
                    return
            except Exception:
                continue
        await asyncio.sleep(0.2)

    await page.keyboard.press("ArrowDown")
    await asyncio.sleep(0.15)
    await page.keyboard.press("Enter")
    log("Stage 4/7 — First suggestion selected via keyboard")
    await asyncio.sleep(0.35)


async def _find_radius_combobox(dialog):
    """Radius row combobox — not the location field."""
    try:
        label = dialog.get_by_text(re.compile(r"^Radius$", re.I)).first
        if await label.is_visible(timeout=2000):
            near = label.locator('xpath=ancestor::div[1]//*[@role="combobox"]').first
            if await near.count() > 0:
                return near
    except Exception:
        pass
    combos = dialog.locator('[role="combobox"]')
    if await combos.count() >= 2:
        return combos.last
    return combos.first


async def _select_radius_in_dialog(page: Page, dialog, radius_km: int, log: LogFn | None = None) -> None:
    """After location pick: focus Radius only, type km from filter (no Ctrl+A — that selects whole dialog)."""
    radius_str = str(int(radius_km))

    await asyncio.sleep(0.5)
    try:
        await page.keyboard.press("Escape")
        await asyncio.sleep(0.25)
    except Exception:
        pass

    combo = await _find_radius_combobox(dialog)
    await combo.scroll_into_view_if_needed(timeout=5000)
    await combo.click(timeout=5000)
    await asyncio.sleep(0.35)

    for _ in range(6):
        await page.keyboard.press("Backspace")
        await asyncio.sleep(0.05)

    await page.keyboard.type(radius_str, delay=70)
    await asyncio.sleep(0.5)
    await page.keyboard.press("Enter")
    await asyncio.sleep(0.35)

    if log:
        log("Stage 4/7 — Radius typed in field (from filter)", {"radius_km": radius_km, "typed": radius_str})


async def _scroll_location_dialog(dialog, page: Page) -> None:
    """Scroll Change location modal — Chromium often hides Apply until inner form is scrolled."""
    try:
        await dialog.click(position={"x": 20, "y": 20}, force=True)
    except Exception:
        pass

    await dialog.evaluate(
        """
        (dialog) => {
            const scrollNode = (el) => {
                if (!el) return;
                if (el.scrollHeight > el.clientHeight + 4) {
                    el.scrollTop = el.scrollHeight;
                }
            };
            scrollNode(dialog);
            const nodes = [...dialog.querySelectorAll('*')];
            nodes.sort(
                (a, b) => (b.scrollHeight - b.clientHeight) - (a.scrollHeight - a.clientHeight)
            );
            for (const el of nodes.slice(0, 12)) {
                scrollNode(el);
            }
            const applySpan = [...dialog.querySelectorAll('span, div[role="button"], button')].find(
                (el) => /^apply$/i.test((el.textContent || '').trim())
            );
            if (applySpan) {
                const btn = applySpan.closest('[role="button"]') || applySpan;
                btn.scrollIntoView({ block: 'end', inline: 'nearest', behavior: 'instant' });
            }
        }
        """
    )

    box = await dialog.bounding_box()
    if box:
        for y_frac in (0.35, 0.55, 0.75):
            cx = box["x"] + box["width"] * 0.55
            cy = box["y"] + box["height"] * y_frac
            await page.mouse.move(cx, cy)
            for _ in range(18):
                await page.mouse.wheel(0, 450)
                await asyncio.sleep(0.06)

    await page.keyboard.press("End")
    await asyncio.sleep(0.35)
    await page.keyboard.press("PageDown")
    await asyncio.sleep(0.35)


async def _click_apply_in_dialog(dialog, page: Page, log: LogFn) -> bool:
    log("Stage 4/7 — Scrolling location form and clicking Apply")

    apply_locators = [
        dialog.get_by_role("button", name=re.compile(r"^apply$", re.I)),
        dialog.locator('[role="button"]').filter(has_text=re.compile(r"^apply$", re.I)),
        dialog.locator('[aria-label="Apply"], [aria-label="apply"]'),
    ]

    for attempt in range(6):
        await _scroll_location_dialog(dialog, page)

        for loc in apply_locators:
            try:
                if await loc.count() == 0:
                    continue
                btn = loc.last
                await btn.wait_for(state="visible", timeout=3000)
                await btn.scroll_into_view_if_needed(timeout=5000)
                await btn.click(force=True, timeout=5000)
                log("Stage 4/7 — Apply button clicked", {"attempt": attempt + 1})
                await asyncio.sleep(STEP_PAUSE)
                try:
                    await dialog.wait_for(state="hidden", timeout=8000)
                    log("Stage 4/7 — Location dialog closed after Apply")
                    return True
                except Exception:
                    pass
            except Exception:
                continue

        js_clicked = await dialog.evaluate(
            """
            (dialog) => {
                const candidates = [
                    ...dialog.querySelectorAll('[role="button"]'),
                    ...dialog.querySelectorAll('button'),
                    ...dialog.querySelectorAll('div[tabindex="0"]'),
                ];
                for (const el of candidates) {
                    const text = (el.textContent || '').replace(/\\s+/g, ' ').trim();
                    if (text === 'Apply' || /^apply$/i.test(text)) {
                        el.scrollIntoView({ block: 'center', behavior: 'instant' });
                        el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                        el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                        el.click();
                        return true;
                    }
                }
                for (const span of dialog.querySelectorAll('span')) {
                    if ((span.textContent || '').trim() !== 'Apply') continue;
                    const btn = span.closest('[role="button"]') || span.parentElement;
                    if (btn) {
                        btn.scrollIntoView({ block: 'center', behavior: 'instant' });
                        btn.click();
                        return true;
                    }
                }
                return false;
            }
            """
        )
        if js_clicked:
            log("Stage 4/7 — Apply clicked (JS)", {"attempt": attempt + 1})
            await asyncio.sleep(STEP_PAUSE)
            try:
                await dialog.wait_for(state="hidden", timeout=8000)
                log("Stage 4/7 — Location dialog closed after Apply")
                return True
            except Exception:
                pass

        coords = await page.evaluate(
            """
            () => {
                const dialog = document.querySelector('[role="dialog"]');
                if (!dialog) return null;
                for (const el of dialog.querySelectorAll('[role="button"], button, span')) {
                    const text = (el.textContent || '').trim();
                    if (text !== 'Apply') continue;
                    const btn = el.closest('[role="button"]') || el;
                    btn.scrollIntoView({ block: 'center' });
                    const r = btn.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0) {
                        return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
                    }
                }
                return null;
            }
            """
        )
        if coords:
            log("Stage 4/7 — Apply clicked (mouse)", {"attempt": attempt + 1})
            await page.mouse.click(coords["x"], coords["y"])
            await asyncio.sleep(STEP_PAUSE)
            try:
                await dialog.wait_for(state="hidden", timeout=8000)
                log("Stage 4/7 — Location dialog closed after Apply")
                return True
            except Exception:
                pass

        await asyncio.sleep(0.5)

    try:
        if await dialog.is_visible(timeout=800):
            log("Stage 4/7 — Apply button failed — dialog still open", level=LogLevel.ERROR)
            return False
    except Exception:
        return True

    log("Stage 4/7 — Apply via keyboard Enter (fallback)")
    await page.keyboard.press("Tab")
    await asyncio.sleep(0.2)
    await page.keyboard.press("Enter")
    await asyncio.sleep(STEP_PAUSE)
    try:
        await dialog.wait_for(state="hidden", timeout=8000)
        return True
    except Exception:
        return False


async def _wait_location_input_in_dialog(dialog, page: Page, log: LogFn):
    """Find the city/location text field inside the change-location dialog."""
    deadline = time.time() + 14
    while time.time() < deadline:
        await _normalize_location_panel(page, dialog)
        for sel in (
            'input[placeholder*="Location" i]',
            'input[aria-label*="Location" i]',
            'input[type="search"]',
            'input[type="text"]',
        ):
            loc = dialog.locator(sel)
            try:
                count = await loc.count()
                for i in range(count):
                    candidate = loc.nth(i)
                    if not await candidate.is_visible(timeout=400):
                        continue
                    ph = (await candidate.get_attribute("placeholder") or "").lower()
                    al = (await candidate.get_attribute("aria-label") or "").lower()
                    if "radius" in ph or "radius" in al:
                        continue
                    return candidate
            except Exception:
                continue
        await asyncio.sleep(0.35)
    raise RuntimeError("Location input not visible in change-location dialog")


async def stage_set_location(page: Page, location: MarketplaceLocation, log: LogFn) -> bool:
    """On /vehicles: set location FIRST (before price). Change only if filter differs."""
    log(
        "Stage 4/7 — LOCATION FIRST on Vehicles page",
        {"location": location.label, "radius_km": location.radius_km},
    )

    current = await _read_sidebar_location(page)
    if not current:
        await asyncio.sleep(0.8)
        current = await _read_sidebar_location(page)
    if current and _location_already_matches(current, location):
        log(
            "Stage 4/7 — Location already correct on Facebook, skipping change",
            {"current": current["raw"], "wanted": location.label, "radius_km": location.radius_km},
        )
        return True

    if current:
        log(
            "Stage 4/7 — Location differs — opening change dialog",
            {"current": current["raw"], "wanted": location.label},
        )
    else:
        log(
            "Stage 4/7 — Could not read current location text — opening change dialog anyway",
            {"wanted": location.label},
            level=LogLevel.WARNING,
        )

    dialog = await _open_location_dialog(page, log)
    if dialog is None:
        log("Stage 4/7 — Change location dialog did not open", level=LogLevel.ERROR)
        raise RuntimeError("Could not open Change location dialog on Vehicles page")

    try:
        log("Stage 4/7 — Typing location in dialog", {"location": location.label})
        location_input = await _wait_location_input_in_dialog(dialog, page, log)
        await location_input.click()
        await location_input.fill("")
        await location_input.fill(location.label)
        await asyncio.sleep(1.0)

        await _pick_first_location_suggestion(page, dialog, log)
        await asyncio.sleep(0.6)

        log("Stage 4/7 — Selecting radius", {"radius_km": location.radius_km})
        await _select_radius_in_dialog(page, dialog, location.radius_km, log)
        await _normalize_location_panel(page, dialog)
        await asyncio.sleep(0.35)

        applied = await _click_apply_in_dialog(dialog, page, log)
        if not applied:
            applied = await _click_apply_in_dialog(dialog, page, log)
        if not applied:
            raise RuntimeError("Apply button could not be clicked — location dialog still open")

        try:
            await dialog.wait_for(state="hidden", timeout=12000)
        except Exception:
            pass

        await asyncio.sleep(0.6)
        updated = None
        for _ in range(10):
            updated = await _read_sidebar_location(page)
            if updated and location.city.lower() in updated.get("city", "").lower():
                break
            await asyncio.sleep(0.6)
        if updated and _location_already_matches(updated, location):
            log("Stage 4/7 — Location applied on Vehicles page (Apply confirmed)", {"location": location.label})
            return True

        log(
            "Stage 4/7 — Apply clicked but sidebar not updated yet",
            {"wanted": location.label},
            level=LogLevel.WARNING,
        )
        log("Stage 4/7 — Location applied on Vehicles page", {"location": location.label})
        return True
    except Exception as exc:
        log("Stage 4/7 — Failed to set location", {"error": str(exc)}, level=LogLevel.ERROR)
        raise


async def wait_then_open_vehicles(
    page: Page,
    log: LogFn,
    *,
    nav_timeout: int = 60000,
    location: MarketplaceLocation | None = None,
    refresh: bool = True,
    context: BrowserContext | None = None,
) -> None:
    """Logged-in Marketplace → wait full load → immediately /category/vehicles."""
    if _is_on_vehicles_page(page):
        log("Stage 3/7 — Already on Vehicles page", {"url": clean_fb_url(page.url)})
        await stage_open_vehicles_category(
            page, log, nav_timeout=nav_timeout, location=location, refresh=refresh
        )
        return

    t0 = time.monotonic()
    log("Stage 2/7 — Waiting for Marketplace to fully load", {"url": clean_fb_url(page.url)})
    await _wait_marketplace_ready(page, log, "Stage 2/7", context=context, timeout_sec=45)
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=15000)
    except Exception:
        pass
    try:
        await page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass
    load_sec = round(time.monotonic() - t0, 2)
    log(
        "Stage 2/7 — Marketplace fully loaded — opening Vehicles now",
        {"marketplace_url": clean_fb_url(page.url), "load_seconds": load_sec},
    )

    t_nav = time.monotonic()
    await stage_open_vehicles_category(
        page, log, nav_timeout=nav_timeout, location=location, refresh=refresh
    )
    nav_elapsed = round(time.monotonic() - t_nav, 2)
    log(
        "Stage 3/7 — Vehicles navigation complete",
        {
            "url": clean_fb_url(page.url),
            "navigation_seconds": nav_elapsed,
            "total_from_load_start": round(time.monotonic() - t0, 2),
        },
    )


async def stage_open_vehicles_category(
    page: Page,
    log: LogFn,
    *,
    nav_timeout: int = 60000,
    prepare_location: bool = True,
    location: MarketplaceLocation | None = None,
    refresh: bool = True,
) -> None:
    """After Marketplace wait → /category/vehicles → optional refresh → ready for location + price."""
    first_open = not _is_on_vehicles_page(page)
    if first_open:
        await _open_vehicles_page(page, log, nav_timeout=nav_timeout, location=location)

    try:
        await page.wait_for_load_state("domcontentloaded", timeout=8000)
    except Exception:
        pass

    if refresh:
        log("Stage 3/7 — Refresh Vehicles page")
        await page.reload(wait_until="commit", timeout=min(15000, nav_timeout))
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=8000)
        except Exception:
            pass
        await asyncio.sleep(0.5)
    elif first_open:
        log("Stage 3/7 — First Vehicles open — skipping refresh for speed")
        await asyncio.sleep(0.5)

    await _wait_vehicles_filters_ready(
        page, log, timeout_ms=8000, require_location=False
    )
    log("Stage 3/7 — Vehicles ready — setting location next", {"url": clean_fb_url(page.url)})


async def _find_price_inputs(page: Page):
    """Locate Min / Max price fields on Vehicles sidebar (under Filters)."""
    await _scroll_sidebar_filters(page)
    await page.evaluate(
        """
        () => {
            const sidebar =
                document.querySelector('[data-pagelet="MarketplaceLeftRail"]') ||
                document.querySelector('[data-pagelet="MarketplaceSidebar"]') ||
                document.querySelector('aside');
            const root = sidebar || document;
            for (const el of root.querySelectorAll('span, h2, label')) {
                const t = (el.textContent || '').trim();
                if (t === 'Price' || t.startsWith('Price range')) {
                    el.scrollIntoView({ block: 'center', behavior: 'instant' });
                    return;
                }
            }
        }
        """
    )
    await asyncio.sleep(0.4)

    coords = await page.evaluate(
        """
        () => {
            const sidebar =
                document.querySelector('[data-pagelet="MarketplaceLeftRail"]') ||
                document.querySelector('[data-pagelet="MarketplaceSidebar"]') ||
                document.querySelector('aside');
            const root = sidebar || document;
            const inputs = [...root.querySelectorAll('input')].filter((inp) => {
                const r = inp.getBoundingClientRect();
                if (r.width < 20 || r.height < 10) return false;
                const ph = (inp.placeholder || '').toLowerCase();
                const al = (inp.getAttribute('aria-label') || '').toLowerCase();
                return ph.includes('min') || ph.includes('max') || al.includes('min') || al.includes('max');
            });
            if (inputs.length >= 2) {
                const sorted = inputs.sort((a, b) => a.getBoundingClientRect().x - b.getBoundingClientRect().x);
                return sorted.slice(0, 2).map((inp) => ({
                    placeholder: inp.placeholder || '',
                    ariaLabel: inp.getAttribute('aria-label') || '',
                }));
            }
            return null;
        }
        """
    )

    if coords and len(coords) >= 2:
        min_input = page.locator(
            f'input[placeholder="{coords[0]["placeholder"]}"], '
            f'input[aria-label="{coords[0]["ariaLabel"]}"]'
        ).first
        max_input = page.locator(
            f'input[placeholder="{coords[1]["placeholder"]}"], '
            f'input[aria-label="{coords[1]["ariaLabel"]}"]'
        ).first
        try:
            if await min_input.is_visible(timeout=1500) and await max_input.is_visible(timeout=1500):
                return min_input, max_input
        except Exception:
            pass

    selectors_min = [
        'input[aria-label*="Min" i]',
        'input[placeholder*="Min" i]',
        'label:has-text("Min") + input',
        'span:has-text("Min.") ~ input',
    ]
    selectors_max = [
        'input[aria-label*="Max" i]',
        'input[placeholder*="Max" i]',
        'label:has-text("Max") + input',
        'span:has-text("Max.") ~ input',
    ]

    min_input = max_input = None
    for sel in selectors_min:
        try:
            loc = page.locator(sel).first
            if await loc.is_visible(timeout=1000):
                min_input = loc
                break
        except Exception:
            continue

    for sel in selectors_max:
        try:
            loc = page.locator(sel).first
            if await loc.is_visible(timeout=1000):
                max_input = loc
                break
        except Exception:
            continue

    if min_input and max_input:
        return min_input, max_input

    # Fallback: two number/text inputs under a Price label
    try:
        price_label = page.get_by_text("Price", exact=True).first
        if await price_label.is_visible(timeout=2000):
            container = price_label.locator("xpath=ancestor::div[1]")
            inputs = container.locator("input")
            count = await inputs.count()
            if count >= 2:
                return inputs.nth(0), inputs.nth(1)
    except Exception:
        pass

    # Last resort: first two visible inputs in left sidebar
    sidebar = page.locator("aside, [role='complementary']").first
    inputs = sidebar.locator('input[type="text"], input[type="number"], input[inputmode="numeric"]')
    count = await inputs.count()
    if count >= 2:
        return inputs.nth(0), inputs.nth(1)
    return None, None


async def stage_apply_vehicle_price(
    page: Page,
    min_price: float | None,
    max_price: float | None,
    log: LogFn,
) -> bool:
    if (min_price is None or min_price <= 0) and (max_price is None or max_price <= 0):
        log("Stage 5/7 — No price range set, skipping price filter")
        return False

    log(
        "Stage 5/7 — Applying Min/Max price on Vehicles page",
        {"min_price": min_price, "max_price": max_price},
    )
    await _require_scrape_page_ready(page, log, "Stage 5/7")

    min_input, max_input = await _find_price_inputs(page)
    if not min_input or not max_input:
        log("Stage 5/7 — Price inputs not found (login popup may be blocking page)", level=LogLevel.ERROR)
        raise RuntimeError("Could not find Min/Max price fields on Vehicles page")

    try:
        if min_price is not None and min_price > 0:
            await _fill_price_input(min_input, int(min_price))
            state_after_min = await _read_price_filter_state(page)
            log(
                "Stage 5/7 — Min price entered",
                {
                    "wanted_min": int(min_price),
                    "input_min": state_after_min.get("input_min"),
                    "url_min_price": state_after_min.get("url_min_price"),
                },
            )

        if max_price is not None and max_price > 0:
            await _fill_price_input(max_input, int(max_price))
            state_after_max = await _read_price_filter_state(page)
            log(
                "Stage 5/7 — Max price entered",
                {
                    "wanted_max": int(max_price),
                    "input_max": state_after_max.get("input_max"),
                    "url_max_price": state_after_max.get("url_max_price"),
                },
            )

        await asyncio.sleep(2)
        final_state = await _read_price_filter_state(page)
        log(
            "Stage 5/7 — Price range applied",
            {
                "wanted_min": int(min_price) if min_price and min_price > 0 else None,
                "wanted_max": int(max_price) if max_price and max_price > 0 else None,
                **final_state,
            },
        )
        return True
    except Exception as exc:
        log("Stage 5/7 — Could not apply price", {"error": str(exc)}, level=LogLevel.ERROR)
        raise


_EXTRACT_LISTING_DETAIL_JS = """
    () => {
        const spans = [...document.querySelectorAll('span')].map(s => s.textContent.trim());
        const price = spans.find(s => /CHF|€|\\$|EUR/.test(s)) || '';
        const candidates = [
            document.querySelector('h1[dir="auto"]')?.textContent?.trim(),
            document.querySelector('[role="main"] h1')?.textContent?.trim(),
            ...[...document.querySelectorAll('span[dir="auto"]')]
                .map(s => s.textContent.trim())
                .filter(t => t.length > 12 && !/CHF|€|\\$|EUR|km away|Listed/i.test(t)),
        ].filter(Boolean);
        let title = candidates.find(t => t && t !== 'Notifications' && t !== 'Marketplace') || '';
        if (!title) {
            const m = (document.title || '').match(/Marketplace\\s*-\\s*(.+?)\\s*\\|\\s*Facebook/i);
            if (m) title = m[1].trim();
        }
        const desc = document.querySelector('[data-ad-preview="message"]')?.textContent
            || document.querySelector('div[dir="auto"]')?.textContent || '';
        const location = spans.find(s => /,\\s*[A-Z]{2}\\b/.test(s) || /km away/i.test(s)) || '';
        return { title, price, description: desc, location };
    }
"""


async def _fetch_listing_detail_fields(page: Page, url: str, nav_timeout: int = 60000) -> dict:
    await page.goto(url, wait_until="domcontentloaded", timeout=nav_timeout)
    await asyncio.sleep(1.2)
    return await page.evaluate(_EXTRACT_LISTING_DETAIL_JS)


async def stage_enrich_listing_details(
    page: Page,
    items: list[dict],
    log: LogFn,
    *,
    return_url: str | None = None,
    nav_timeout: int = 120000,
) -> list[dict]:
    """Open detail pages only for hinted listings — then return to the vehicles list."""
    if not items:
        return items

    log(
        "Stage 6b/7 — Opening detail pages for main-page hints only",
        {"count": len(items)},
    )
    for idx, item in enumerate(items, 1):
        url = item.get("url")
        if not url:
            continue
        try:
            detail = await _fetch_listing_detail_fields(page, url, nav_timeout=nav_timeout)
            title = " ".join((detail.get("title") or "").split())
            if title:
                item["title"] = title
            if detail.get("price") and not item.get("price_text"):
                item["price_text"] = detail["price"]
            if detail.get("location") and not item.get("location"):
                item["location"] = detail["location"]
            if detail.get("description"):
                item["description"] = detail["description"]
            if idx < len(items):
                await asyncio.sleep(0.8)
        except Exception as exc:
            log(
                f"Stage 6b/7 — Could not read listing {idx}/{len(items)}",
                {"url": url, "error": str(exc)},
                level=LogLevel.WARNING,
            )

    if return_url:
        try:
            await page.goto(return_url, wait_until="domcontentloaded", timeout=nav_timeout)
            await asyncio.sleep(1)
        except Exception as exc:
            log(
                "Stage 6b/7 — Could not return to vehicles list after detail checks",
                {"url": return_url, "error": str(exc)},
                level=LogLevel.WARNING,
            )
    return items


async def stage_refresh_listings_page(page: Page, log: LogFn, *, nav_timeout: int = 120000) -> None:
    """Soft refresh on the same filtered Vehicles URL — keeps min/max price in URL."""
    log("Stage 6/7 — Refreshing listings page for new results", {"url": page.url})
    await page.reload(wait_until="domcontentloaded", timeout=nav_timeout)
    await asyncio.sleep(2)
    await page.evaluate("window.scrollTo(0, 0)")
    await asyncio.sleep(0.5)


async def stage_scrape_listings(
    page: Page,
    max_results: int,
    log: LogFn,
    *,
    scroll_passes: int = 3,
) -> list[dict]:
    log(
        "Stage 6/7 — Reading listings from Vehicles page (only filter-matched ones are saved)",
        {"max_read": max_results},
    )
    await _require_scrape_page_ready(page, log, "Stage 6/7")
    passes = max(1, scroll_passes)
    for _ in range(passes):
        await page.evaluate("window.scrollBy(0, window.innerHeight)")
        await asyncio.sleep(0.8)
    if passes > 1:
        await page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(0.5)

    items = await page.evaluate("""
        () => {
            const results = [];
            const links = document.querySelectorAll('a[href*="/marketplace/item/"]');
            const seen = new Set();
            const isPrice = (t) => /CHF|€|\\$|EUR|PKR|Rs\\.?|Rs\\b|\\.\\-/.test(t) || /\\d['']\\d/.test(t);
            const isNoise = (t) => /^Just listed$/i.test(t) || /^Free$/i.test(t) || /^Sponsored$/i.test(t);

            const parseAriaLabel = (al) => {
                const out = { title: '', price: '', location: '' };
                if (!al) return out;
                for (const part of al.split(',').map(s => s.trim()).filter(Boolean)) {
                    if (/^listing\\s+\\d+$/i.test(part)) continue;
                    if (/^CHF|^€|\\$|EUR/i.test(part)) {
                        if (!out.price) out.price = part;
                        continue;
                    }
                    if (/^[A-Z]{2}$/.test(part)) continue;
                    if (/^[A-Za-zÀ-ÿ .''-]+,\\s*[A-Z]{2}$/.test(part)) {
                        if (!out.location) out.location = part;
                        continue;
                    }
                    if (part.length > 3 && !out.title) out.title = part;
                }
                return out;
            };

            const findCardRoot = (link) => {
                let node = link;
                for (let i = 0; i < 10; i++) {
                    if (!node.parentElement) break;
                    node = node.parentElement;
                    const itemLinks = node.querySelectorAll('a[href*="/marketplace/item/"]');
                    if (itemLinks.length === 1 && node.contains(link)) {
                        const h = node.getBoundingClientRect?.().height || 0;
                        if (h >= 60 && h <= 520) return node;
                    }
                }
                return link.parentElement || link;
            };

            links.forEach(link => {
                const href = link.href.split('?')[0];
                if (seen.has(href)) return;
                seen.add(href);
                const idMatch = href.match(/\\/item\\/(\\d+)/);
                if (!idMatch) return;
                const img = link.querySelector('img');
                const al = (link.getAttribute('aria-label') || '').trim();
                const parsed = parseAriaLabel(al);
                let title = parsed.title;
                let price = parsed.price;
                let location = parsed.location;
                const spans = [...link.querySelectorAll('span')].map(s => s.textContent.trim()).filter(Boolean);

                for (const t of spans) {
                    if (isPrice(t)) {
                        if (!price) price = t;
                        continue;
                    }
                    if (isNoise(t)) continue;
                }

                for (const t of spans) {
                    if (isPrice(t) || isNoise(t)) continue;
                    if (/,.\\s*[A-Z]{2}\\b/.test(t) && !location) location = t;
                }

                const card = findCardRoot(link);
                const cardSpans = [...card.querySelectorAll('span[dir="auto"], span')]
                    .map(s => s.textContent.trim())
                    .filter(Boolean);
                const cardText = [...new Set(cardSpans.filter(t => !isPrice(t) && !isNoise(t)))].join(' ');

                if (!title || title === location) {
                    const titleCandidate = cardSpans.find(t =>
                        t.length > 10 &&
                        !isPrice(t) &&
                        !isNoise(t) &&
                        !/^\\s*in\\s/i.test(t) &&
                        !/,.\\s*[A-Z]{2}\\b/.test(t)
                    );
                    if (titleCandidate) title = titleCandidate;
                }

                const imgAlt = (img?.alt || '').trim();
                if ((!title || title === location) && imgAlt.length > 5 && !/^\\s*in\\s/i.test(imgAlt)) {
                    title = imgAlt;
                }

                if (!title) title = cardText || location || 'Unknown Vehicle';
                results.push({
                    external_id: idMatch[1],
                    url: href,
                    title: title,
                    card_text: cardText,
                    aria_label: al,
                    price_text: price,
                    location: location,
                    image: img ? img.src : null
                });
            });
            return results;
        }
    """)
    log("Stage 6/7 — Listings read from main page", {"count": len(items[:max_results])})
    return items[:max_results]
