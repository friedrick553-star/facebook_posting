"""Playwright flow — Facebook Marketplace item listing via sidebar UI."""
from __future__ import annotations

import asyncio
import logging
import random
import re
from dataclasses import dataclass, field

from playwright.async_api import BrowserContext, Locator, Page, TimeoutError as PlaywrightTimeout

from app.config import Settings
from app.services.facebook_session import (
    MARKETPLACE_URL,
    dismiss_login_popup_once,
    is_login_fully_complete,
    is_on_facebook_auth_flow,
    reload_marketplace_after_login,
    save_session,
    wait_until_marketplace_logged_in,
)

logger = logging.getLogger(__name__)

MARKETPLACE_CREATE_URL = "https://it-it.facebook.com/marketplace/create/"
PUBLISH_TIMEOUT_MS = 120_000
DRY_RUN_REVIEW_PAUSE_SEC = 5

CONDITION_LABELS = {
    "new": ("New", "Nuovo", "Nuova", "Nuevo"),
    "used": ("Used", "Usato", "Usata", "Usado"),
}

AVAILABILITY_LABELS = {
    "single": (
        "List as a single item",
        "List as single item",
        "Single item",
        "Articolo singolo",
        "Singolo",
    ),
    "stock": ("In stock", "Disponibile", "Multiple items"),
}

# CSV category → Facebook picker labels to scroll/find (no typing in category field)
CATEGORY_FB_SEARCH: dict[str, list[str]] = {
    "bicycles": ["Bicycles", "Biciclette", "Sporting Goods", "Vehicles"],
    "biciclette": ["Biciclette", "Bicycles", "Sporting Goods"],
    "vehicles": ["Bicycles", "Vehicles", "Sporting Goods"],
    "scooters": ["Scooters", "Monopattini", "Vehicles", "Sporting Goods"],
    "cell phones": ["Cell Phones", "Mobile Phones", "Cellulari", "Telefoni", "Smartphone"],
    "cell phone": ["Cell Phones", "Mobile Phones", "Cellulari", "Telefoni"],
    "mobile phones": ["Mobile Phones", "Cell Phones", "Cellulari", "Telefoni"],
    "mobile phone": ["Mobile Phones", "Cell Phones", "Cellulari", "Telefoni"],
    "electronics": ["Electronics", "Cell Phones", "Computers"],
    "furniture": ["Furniture", "Home & Garden", "Home and Garden", "Arredamento"],
    "office supplies": ["Office Supplies"],
    "laptops": ["Computers", "Electronics", "Laptops", "Computer"],
    "audio equipment": ["Electronics", "Audio"],
    "cameras": ["Cameras", "Electronics", "Fotocamere"],
    "sporting goods": ["Sporting Goods", "Articoli sportivi"],
    "home & garden": ["Home & Garden", "Home and Garden", "Garden", "Casa e giardino"],
    "entertainment": ["Entertainment", "Intrattenimento"],
}


@dataclass
class ProductListingPayload:
    title: str
    description: str
    price: float | None
    currency: str
    image_paths: list[str]
    category: str | None = None
    condition: str = "new"
    availability: str = "single"
    extra_details: dict[str, str] = field(default_factory=dict)


async def _human_pause(min_s: float = 1.8, max_s: float = 3.5) -> None:
    await asyncio.sleep(random.uniform(min_s, max_s))


async def _scroll_into_view(loc: Locator) -> None:
    try:
        await loc.scroll_into_view_if_needed(timeout=5000)
        await _human_pause(0.4, 0.9)
    except Exception:
        pass


async def _fill_first_visible(page: Page, selectors: list[str], value: str) -> bool:
    for sel in selectors:
        loc = page.locator(sel).first
        try:
            if await loc.count() and await loc.is_visible(timeout=2500):
                await _scroll_into_view(loc)
                await loc.click(timeout=4000)
                await loc.fill(value, timeout=8000)
                await _human_pause(0.6, 1.2)
                return True
        except Exception:
            continue
    return False


async def _fill_by_label(page: Page, labels: list[str], value: str) -> bool:
    for label in labels:
        try:
            loc = page.get_by_label(re.compile(label, re.I)).first
            if await loc.count() and await loc.is_visible(timeout=2500):
                await _scroll_into_view(loc)
                await loc.click(timeout=4000)
                await loc.fill(value, timeout=8000)
                await _human_pause(0.6, 1.2)
                return True
        except Exception:
            continue
    return False


async def _type_slow(loc: Locator, value: str) -> None:
    await loc.click(timeout=4000)
    try:
        await loc.fill("")
    except Exception:
        pass
    await loc.press_sequentially(value, delay=random.randint(60, 110))
    await _human_pause(0.8, 1.5)


async def _click_button(page: Page, *labels: str) -> bool:
    for label in labels:
        try:
            btn = page.get_by_role("button", name=re.compile(re.escape(label), re.I))
            if await btn.count():
                await btn.first.click(timeout=5000)
                await _human_pause()
                return True
        except Exception:
            pass
        try:
            btn = page.locator(f'div[aria-label="{label}" i], span:has-text("{label}")').first
            if await btn.count() and await btn.is_visible(timeout=2000):
                await btn.click(timeout=5000)
                await _human_pause()
                return True
        except Exception:
            continue
    return False


async def _publish_button_visible(page: Page) -> bool:
    """True only on the post-Next wizard step — not the first create/item form."""
    url = page.url.lower()
    if "marketplace/create" not in url:
        return False

    labels = ("Publish", "Pubblica", "Publicar")
    max_x = await _sidebar_max_x(page)
    try:
        win_h = float(await page.evaluate("window.innerHeight"))
    except Exception:
        win_h = 900.0
    min_y = win_h * 0.72

    for label in labels:
        try:
            role_btns = page.get_by_role("button", name=re.compile(f"^{re.escape(label)}$", re.I))
            count = await role_btns.count()
            for i in range(count):
                btn = role_btns.nth(i)
                if not await btn.is_visible(timeout=600):
                    continue
                text = (await btn.inner_text()).strip()
                if text.lower() != label.lower():
                    continue
                box = await btn.bounding_box()
                if box and box["x"] <= max_x and box["y"] >= min_y:
                    return True
        except Exception:
            pass
        try:
            div_btns = page.locator(f'div[role="button"]')
            count = await div_btns.count()
            for i in range(count):
                btn = div_btns.nth(i)
                try:
                    text = (await btn.inner_text()).strip()
                except Exception:
                    continue
                if text.lower() != label.lower():
                    continue
                if not await btn.is_visible(timeout=400):
                    continue
                box = await btn.bounding_box()
                if box and box["x"] <= max_x and box["y"] >= min_y:
                    return True
        except Exception:
            continue
    return False


async def _wait_for_publish_screen(page: Page, log, *, timeout_s: float = 90.0) -> bool:
    log("Waiting for next page — Publish must appear (will NOT click it)")
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        if await _publish_button_visible(page):
            await _human_pause(1.5, 2.5)
            log("Publish button visible — dry run stops here")
            return True
        url = page.url.lower()
        if "step=" in url and "marketplace/create" in url:
            log("Wizard advanced to next step", {"url": page.url})
        await asyncio.sleep(1.2)
    log("Publish screen did not appear in time", {"url": page.url})
    return False


async def _log_browser_layout(page: Page, log) -> None:
    try:
        size = await page.evaluate(
            """() => ({
              innerWidth: window.innerWidth,
              innerHeight: window.innerHeight,
              devicePixelRatio: window.devicePixelRatio,
            })"""
        )
        log("Browser window size (no_viewport)", size)
    except Exception:
        pass


async def _reveal_marketplace_sidebar_next(page: Page, log) -> dict:
    """Scroll the create/item LEFT column so the fixed Next footer (below blue line) is on screen."""
    try:
        info = await page.evaluate(
            """() => {
              const winH = window.innerHeight;
              const winW = window.innerWidth;
              const isNext = (el) => /^(Next|Avanti|Continua|Continue|Siguiente)$/i.test(
                (el.innerText || el.textContent || '').trim()
              );
              const leftNext = [...document.querySelectorAll('[role="button"], button')]
                .filter(isNext)
                .filter(el => el.getBoundingClientRect().left < winW * 0.55)
                .sort((a, b) => b.getBoundingClientRect().top - a.getBoundingClientRect().top);

              const isLeftScrollable = (el) => {
                const r = el.getBoundingClientRect();
                const s = getComputedStyle(el);
                const oy = s.overflowY;
                const scrollable = (oy === 'auto' || oy === 'scroll')
                  && el.scrollHeight > el.clientHeight + 24;
                return scrollable && r.left < winW * 0.52 && r.width > 160 && r.right < winW * 0.6;
              };

              const scrollables = [...document.querySelectorAll('div, section, form')]
                .filter(isLeftScrollable)
                .sort((a, b) => a.getBoundingClientRect().left - b.getBoundingClientRect().left);

              for (const el of scrollables) {
                el.scrollTop = el.scrollHeight;
              }

              const anchorRe = /availability|disponibilit|description|descrizione|product tags|color|condizione|condition/i;
              const anchors = [...document.querySelectorAll(
                'textarea, [role="combobox"], label, span, div[aria-label]'
              )].filter(el => {
                const t = (el.innerText || el.getAttribute('aria-label') || '').trim();
                return anchorRe.test(t) && el.getBoundingClientRect().left < winW * 0.55;
              });

              for (const anchor of anchors) {
                let p = anchor;
                for (let i = 0; i < 10 && p; i++) {
                  const s = getComputedStyle(p);
                  if ((s.overflowY === 'auto' || s.overflowY === 'scroll')
                      && p.scrollHeight > p.clientHeight + 20) {
                    p.scrollTop = p.scrollHeight;
                  }
                  p = p.parentElement;
                }
              }

              const next = leftNext[0];
              if (next) {
                let p = next.parentElement;
                while (p) {
                  const s = getComputedStyle(p);
                  if ((s.overflowY === 'auto' || s.overflowY === 'scroll')
                      && p.scrollHeight > p.clientHeight + 20) {
                    p.scrollTop = p.scrollHeight;
                  }
                  p = p.parentElement;
                }
                next.scrollIntoView({ block: 'end', inline: 'nearest', behavior: 'instant' });
              }

              if (!next) {
                return { found: false, scrollables: scrollables.length, winH, winW };
              }
              const r = next.getBoundingClientRect();
              return {
                found: true,
                scrollables: scrollables.length,
                nextTop: Math.round(r.top),
                nextBottom: Math.round(r.bottom),
                inViewport: r.top >= 0 && r.bottom <= winH + 4,
                winH,
                winW,
                ariaDisabled: next.getAttribute('aria-disabled') === 'true',
              };
            }"""
        )
        log("Sidebar scroll toward fixed Next footer", info)
        return info
    except Exception as exc:
        log("Sidebar scroll failed", {"error": str(exc)[:120]})
        return {"found": False}


async def _wheel_scroll_left_sidebar(page: Page, log) -> None:
    """Wheel over the left form column — same as manual scroll in the user's screenshot."""
    try:
        anchor = page.get_by_text(re.compile(r"Item for sale|Elemento in vendita|Articolo", re.I)).first
        if not await anchor.count():
            anchor = page.locator('textarea').first
        box = await anchor.bounding_box()
        if not box:
            return
        x = box["x"] + min(120, max(40, box["width"] * 0.35))
        y = min(box["y"] + 280, (await page.evaluate("window.innerHeight")) - 120)
        await page.mouse.move(x, y)
        for _ in range(14):
            await page.mouse.wheel(0, 500)
            await asyncio.sleep(0.12)
        log("Mouse wheel on left sidebar", {"x": round(x), "y": round(y)})
    except Exception:
        pass


async def _scroll_listing_sidebar_to_bottom(page: Page, log) -> None:
    """Reveal the sticky Next bar at the bottom of the create/item left sidebar."""
    for attempt in range(3):
        info = await _reveal_marketplace_sidebar_next(page, log)
        if info.get("inViewport"):
            break
        await _wheel_scroll_left_sidebar(page, log)
        await _human_pause(0.4, 0.7)
        info = await _reveal_marketplace_sidebar_next(page, log)
        if info.get("inViewport"):
            break
        await _human_pause(0.5, 0.8)


async def _sidebar_max_x(page: Page) -> float:
    vp = page.viewport_size
    if vp:
        return vp["width"] * 0.55
    try:
        w = await page.evaluate("window.innerWidth")
        return float(w) * 0.55
    except Exception:
        return 1920 * 0.55


async def _find_sidebar_next_button(page: Page, log) -> Locator | None:
    """Next lives at the bottom of the main create/item sidebar — not an inner scroll area."""
    await _scroll_listing_sidebar_to_bottom(page, log)

    patterns = ("Next", "Avanti", "Continua", "Continue", "Siguiente")
    candidates: list[Locator] = []

    for pattern in patterns:
        try:
            role_btns = page.get_by_role("button", name=re.compile(f"^{re.escape(pattern)}$", re.I))
            count = await role_btns.count()
            for i in range(count):
                candidates.append(role_btns.nth(i))
        except Exception:
            pass
        try:
            div_btns = page.locator(
                f'div[role="button"]:has-text("{pattern}"), span[role="button"]:has-text("{pattern}")'
            )
            count = await div_btns.count()
            for i in range(count):
                candidates.append(div_btns.nth(i))
        except Exception:
            pass

    best: Locator | None = None
    best_y = -1.0
    for cand in candidates:
        try:
            text = (await cand.inner_text()).strip()
            if text.lower() not in {p.lower() for p in patterns}:
                continue
            box = await cand.bounding_box()
            if not box:
                continue
            # Sidebar Next is in the left column only (ignore preview pane buttons).
            max_x = await _sidebar_max_x(page)
            if box["x"] > max_x:
                continue
            if box["y"] > best_y:
                best_y = box["y"]
                best = cand
        except Exception:
            continue

    if not best:
        try:
            fallback = page.locator(
                'div[role="button"]:has-text("Next"), button:has-text("Next"), '
                'div[role="button"]:has-text("Avanti"), button:has-text("Avanti")'
            ).last
            if await fallback.count():
                box = await fallback.bounding_box()
                if box and box["x"] < await _sidebar_max_x(page):
                    best = fallback
                    best_y = box["y"]
        except Exception:
            pass

    if best and log:
        try:
            enabled = await best.is_enabled(timeout=800)
        except Exception:
            enabled = None
        log("Found sidebar Next button", {"screen_y": round(best_y), "enabled": enabled})
    elif log:
        log("Sidebar Next button not visible yet")
    return best


async def _next_button(page: Page) -> Locator | None:
    return await _find_sidebar_next_button(page, None)


async def _next_is_enabled(page: Page) -> bool:
    btn = await _next_button(page)
    if not btn:
        return False
    try:
        return await btn.is_enabled(timeout=2000)
    except Exception:
        return False


async def _wait_form_fully_loaded(page: Page, log) -> None:
    log("Waiting for create/item form to fully load")
    try:
        await page.wait_for_load_state("networkidle", timeout=30_000)
    except PlaywrightTimeout:
        pass

    loaded = False
    checks = [
        ('input[type="file"]', "file input"),
        ('[aria-label*="photo" i], [aria-label*="foto" i]', "photo area"),
        ('input[aria-label*="Title" i], input[aria-label*="Titolo" i]', "title field"),
    ]
    for selector, label in checks:
        try:
            await page.wait_for_selector(selector, state="visible", timeout=20_000)
            log(f"Form element ready: {label}")
            loaded = True
            break
        except PlaywrightTimeout:
            continue

    if not loaded:
        try:
            await page.get_by_text(
                re.compile(r"add photos?|drag|trascina|aggiungi foto|carica foto", re.I)
            ).first.wait_for(state="visible", timeout=15_000)
            loaded = True
            log("Form element ready: photo drop text")
        except PlaywrightTimeout:
            pass

    if not loaded:
        raise RuntimeError("Listing form did not load — try again after login")

    await _human_pause(2.0, 3.0)
    log("Form loaded — uploading photos next")


async def _wait_step_after_next(page: Page, log) -> None:
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=20_000)
    except PlaywrightTimeout:
        pass
    await _human_pause(3.0, 5.5)
    log("Next step loaded")


async def _open_item_listing_form(page: Page, log) -> None:
    """Marketplace home → sidebar Create new listing → Item for sale."""
    url = page.url.lower()
    if "/marketplace/create/item" in url:
        log("Already on item listing form")
        await _wait_form_fully_loaded(page, log)
        return

    if "marketplace" not in url:
        log("Opening Facebook Marketplace")
        await page.goto(MARKETPLACE_URL, wait_until="domcontentloaded", timeout=90_000)
        await _human_pause()
        await dismiss_login_popup_once(page)

    if "/marketplace/create" not in page.url.lower():
        log("Clicking sidebar — Create new listing")
        clicked = False
        for attempt in (
            lambda: page.get_by_role("link", name=re.compile(r"create new listing|crea.*annuncio|nuova inserzione", re.I)),
            lambda: page.get_by_role("button", name=re.compile(r"create new listing|crea.*annuncio", re.I)),
            lambda: page.locator('a[href*="/marketplace/create"]').first,
            lambda: page.get_by_text(re.compile(r"\+?\s*Create new listing|Crea.*annuncio|Nuova inserzione", re.I)).first,
        ):
            try:
                loc = attempt()
                if await loc.count() and await loc.is_visible(timeout=3000):
                    await loc.click(timeout=8000)
                    clicked = True
                    break
            except Exception:
                continue
        if not clicked:
            log("Sidebar button not found — opening /marketplace/create/")
            await page.goto(MARKETPLACE_CREATE_URL, wait_until="domcontentloaded", timeout=90_000)
        await _human_pause(2.5, 4.0)

    if "/marketplace/create/item" not in page.url.lower():
        log("Choosing listing type — Item for sale")
        picked = False
        for label in ("Item for sale", "Oggetto in vendita", "Articolo in vendita", "Objet en vente"):
            try:
                card = page.locator(
                    f'div[role="button"]:has-text("{label}"), '
                    f'div[role="link"]:has-text("{label}"), '
                    f'span:has-text("{label}")'
                ).first
                if await card.count() and await card.is_visible(timeout=3000):
                    await card.click(timeout=8000)
                    picked = True
                    break
            except Exception:
                continue
        if not picked:
            try:
                teapot = page.get_by_text(re.compile(r"Create a single listing for one or more items", re.I)).first
                if await teapot.count():
                    await teapot.click(timeout=5000)
                    picked = True
            except Exception:
                pass
        await _human_pause(2.5, 4.5)

    if "/marketplace/create/item" not in page.url.lower():
        log("Direct open — /marketplace/create/item")
        await page.goto(
            "https://it-it.facebook.com/marketplace/create/item",
            wait_until="domcontentloaded",
            timeout=90_000,
        )
        await _human_pause(2.0, 3.0)

    if "/marketplace/create/item" not in page.url.lower():
        raise RuntimeError("Could not open Item for sale form — check Marketplace sidebar access")

    await _wait_form_fully_loaded(page, log)


async def _wait_photos_ready(page: Page, expected: int, log) -> None:
    log("Waiting for photo previews", {"expected": expected})
    for _ in range(25):
        previews = page.locator('img[src*="blob:"], img[src*="scontent"], div[aria-label*="photo" i] img')
        try:
            if await previews.count() >= min(expected, 1):
                await _human_pause(1.5, 2.5)
                log("Photos appear uploaded")
                return
        except Exception:
            pass
        await asyncio.sleep(1.0)
    await _human_pause(2.0, 3.0)


async def _find_photo_drop_zone(page: Page) -> Locator | None:
    """Find the drag-and-drop / add-photos area on create/item."""
    candidates: list[Locator] = [
        page.get_by_text(re.compile(
            r"add photos?|add video or photos?|drag photos?|drag and drop|"
            r"drop photos?|upload photos?|photos/videos|"
            r"aggiungi foto|trascina|carica foto|carica le foto",
            re.I,
        )).first,
        page.locator('[aria-label*="Add photo" i], [aria-label*="Aggiungi foto" i], [aria-label*="photo" i]').first,
        page.locator('label:has(input[type="file"])').first,
        page.locator('div[role="button"]:has(input[type="file"])').first,
    ]
    for loc in candidates:
        try:
            if await loc.count() and await loc.is_visible(timeout=2500):
                return loc
        except Exception:
            continue
    return None


async def _upload_photos(page: Page, image_paths: list[str], log) -> None:
    """Upload via create/item drag-and-drop zone — photos first, before any other field."""
    if "/marketplace/create/item" not in page.url.lower():
        log("Not on create/item yet — waiting")
        await _human_pause(2.0, 3.0)

    log("Photo step — drag-and-drop zone on create/item")
    await _human_pause(2.0, 3.0)

    drop_zone = await _find_photo_drop_zone(page)
    if drop_zone:
        log("Found photo drop zone — clicking to activate upload")
        await _scroll_into_view(drop_zone)
        await _human_pause(1.0, 2.0)
        try:
            async with page.expect_file_chooser(timeout=20_000) as fc_info:
                await drop_zone.click(timeout=10_000)
            fc = await fc_info.value
            await fc.set_files(image_paths)
            log("Photos sent via file chooser from drop zone", {"count": len(image_paths)})
            await _wait_photos_ready(page, len(image_paths), log)
            return
        except Exception:
            log("Drop zone click did not open file chooser — trying hidden input")

    async def _set_files_on_inputs(scope) -> bool:
        selectors = ['input[type="file"][accept*="image"]', 'input[type="file"]']
        for sel in selectors:
            loc = scope.locator(sel)
            try:
                count = await loc.count()
                for i in range(count):
                    candidate = loc.nth(i)
                    try:
                        await candidate.set_input_files(image_paths, timeout=45_000)
                        log("Photos set on file input", {"index": i})
                        return True
                    except Exception:
                        continue
            except Exception:
                continue
        return False

    if drop_zone:
        try:
            nested = drop_zone.locator('input[type="file"]').first
            if await nested.count():
                await nested.set_input_files(image_paths, timeout=45_000)
                log("Photos set on nested file input inside drop zone")
                await _wait_photos_ready(page, len(image_paths), log)
                return
        except Exception:
            pass

    if await _set_files_on_inputs(page):
        await _wait_photos_ready(page, len(image_paths), log)
        return

    upload_patterns = (
        r"add photos?", r"add video or photos?", r"upload photos?",
        r"aggiungi foto", r"carica foto", r"photos/videos",
    )
    for pattern in upload_patterns:
        try:
            trigger = page.get_by_role("button", name=re.compile(pattern, re.I)).first
            if not await trigger.count():
                trigger = page.get_by_text(re.compile(pattern, re.I)).first
            if await trigger.count() and await trigger.is_visible(timeout=3000):
                await _scroll_into_view(trigger)
                await _human_pause(1.0, 2.0)
                async with page.expect_file_chooser(timeout=20_000) as fc_info:
                    await trigger.click(timeout=10_000)
                fc = await fc_info.value
                await fc.set_files(image_paths)
                log("Photos sent via Add photos button")
                await _wait_photos_ready(page, len(image_paths), log)
                return
        except Exception:
            continue

    for frame in page.frames:
        if frame == page.main_frame:
            continue
        if await _set_files_on_inputs(frame):
            await _wait_photos_ready(page, len(image_paths), log)
            return

    raise RuntimeError("Could not upload photos — drag-and-drop zone not found on create/item")


async def _find_combobox(page: Page, field_labels: list[str]) -> Locator | None:
    for label in field_labels:
        try:
            loc = page.get_by_label(re.compile(label, re.I)).first
            if await loc.count() and await loc.is_visible(timeout=2500):
                return loc
        except Exception:
            pass
        try:
            loc = page.get_by_role("combobox", name=re.compile(label, re.I)).first
            if await loc.count() and await loc.is_visible(timeout=2500):
                return loc
        except Exception:
            pass
        try:
            loc = page.locator(
                f'input[aria-label*="{label}" i], input[placeholder*="{label}" i]'
            ).first
            if await loc.count() and await loc.is_visible(timeout=2500):
                return loc
        except Exception:
            pass
    return None


async def _list_dropdown_options(page: Page) -> list[str]:
    options = page.locator('[role="option"], [role="listbox"] [role="option"]')
    texts: list[str] = []
    try:
        count = await options.count()
        for i in range(min(count, 12)):
            opt = options.nth(i)
            if await opt.is_visible(timeout=800):
                text = (await opt.inner_text()).strip()
                if text:
                    texts.append(text)
    except Exception:
        pass
    return texts


async def _pick_dropdown_option(page: Page, prefer: list[str], log, *, context: str) -> str | None:
    options = page.locator('[role="option"], [role="listbox"] [role="option"]')
    try:
        count = await options.count()
    except Exception:
        return None
    if count == 0:
        return None

    visible: list[tuple[int, str]] = []
    for i in range(count):
        opt = options.nth(i)
        try:
            if await opt.is_visible(timeout=1000):
                text = (await opt.inner_text()).strip()
                if text:
                    visible.append((i, text))
        except Exception:
            continue

    if not visible:
        return None

    log(f"{context} dropdown options", {"options": [t for _, t in visible[:8]]})

    for want in prefer:
        want_l = want.lower()
        for idx, text in visible:
            if want_l in text.lower() or text.lower() in want_l:
                await options.nth(idx).click(timeout=5000)
                await _human_pause(1.0, 2.0)
                log(f"Selected {context}", {"picked": text, "wanted": want})
                return text

    idx, text = visible[0]
    await options.nth(idx).click(timeout=5000)
    await _human_pause(1.0, 2.0)
    log(f"Selected first {context} option", {"picked": text})
    return text


async def _category_search_terms(csv_category: str | None) -> list[str]:
    if not csv_category:
        return []
    key = csv_category.strip().lower()
    mapped = CATEGORY_FB_SEARCH.get(key, [])
    terms = mapped + [csv_category.strip()]
    seen: set[str] = set()
    out: list[str] = []
    for t in terms:
        tl = t.lower()
        if tl not in seen:
            seen.add(tl)
            out.append(t)
    return out


def _category_option_first_line(option_text: str) -> str:
    return (option_text or "").split("\n")[0].strip()


def _category_option_matches(term: str, option_text: str) -> bool:
    """Match CSV category to picker row — avoid Electronics when CSV says Cell Phones."""
    term_l = term.lower().strip()
    line = _category_option_first_line(option_text).lower()
    if not term_l or not line:
        return False
    if term_l == line:
        return True

    phone_terms = ("phone", "cell", "mobile", "cellulari", "telefon", "smartphone")
    if any(p in term_l for p in phone_terms):
        if ("computer" in line or "informatica" in line) and not any(
            p in line for p in phone_terms
        ):
            return False
        return term_l in line or line in term_l or any(p in line for p in phone_terms if p in term_l)

    if term_l in line:
        return len(term_l) >= max(4, int(len(line) * 0.4))
    return line in term_l


async def _open_category_picker(page: Page, log) -> bool:
    """Open category picker — click selector row, do NOT type."""
    label = page.get_by_text(re.compile(r"^Category$|^Categoria$", re.I)).first
    try:
        if await label.count() and await label.is_visible(timeout=2000):
            row = label.locator(
                "xpath=ancestor::div[@role='button' or @role='combobox' or @tabindex][1]"
            ).first
            if await row.count():
                await _scroll_into_view(row)
                await row.click(timeout=8000)
                await _human_pause(1.0, 1.8)
                log("Category picker opened via label row")
                return True
            parent = label.locator("xpath=..").first
            await _scroll_into_view(parent)
            await parent.click(timeout=8000)
            await _human_pause(1.0, 1.8)
            log("Category picker opened via label parent")
            return True
    except Exception:
        pass

    triggers: list[Locator] = [
        page.get_by_role("combobox", name=re.compile(r"category|categoria", re.I)).first,
        page.locator('[aria-haspopup="listbox"][aria-label*="Category" i]').first,
        page.locator('[aria-haspopup="listbox"][aria-label*="Categoria" i]').first,
        page.locator('[aria-label*="Category" i][role="button"]').first,
        page.locator('[aria-label*="Categoria" i][role="button"]').first,
        page.locator('div[role="button"]:has-text("Category"), div[role="button"]:has-text("Categoria")').first,
        page.locator('[aria-label*="Category" i], [aria-label*="Categoria" i]').first,
    ]
    for trigger in triggers:
        try:
            if await trigger.count() and await trigger.is_visible(timeout=2000):
                await _scroll_into_view(trigger)
                await trigger.click(timeout=8000)
                await _human_pause(1.0, 1.8)
                log("Category picker opened")
                return True
        except Exception:
            continue
    return False


async def _scroll_picker_and_pick(page: Page, terms: list[str], log, *, context: str) -> str | None:
    """Scroll Facebook list picker and click a visible option — no typing."""
    scroll_targets = [
        page.locator('[role="listbox"]').first,
        page.locator('[role="dialog"]').first,
        page.locator('div[class*="xjyslct"]').first.locator("xpath=ancestor::div[1]").first,
    ]
    scroll_el: Locator | None = None
    for target in scroll_targets:
        try:
            if await target.count():
                scroll_el = target
                break
        except Exception:
            continue

    seen_options: list[str] = []
    for scroll_round in range(30):
        for term in terms:
            candidates = [
                page.get_by_role("option", name=re.compile(re.escape(term), re.I)).first,
                page.locator(f'div[role="button"]:has-text("{term}")').first,
                page.locator(f'div[class*="xjyslct"]:has-text("{term}")').first,
                page.locator(f'[role="option"]:has-text("{term}")').first,
            ]
            for cand in candidates:
                try:
                    if not await cand.count():
                        continue
                    if not await cand.is_visible(timeout=600):
                        continue
                    text = (await cand.inner_text()).strip()
                    if not text or len(text) > 80:
                        continue
                    if not _category_option_matches(term, text):
                        continue
                    await _scroll_into_view(cand)
                    await cand.click(timeout=6000)
                    await _human_pause(0.8, 1.5)
                    log(f"Selected {context}", {"picked": text, "wanted": term})
                    return text
                except Exception:
                    continue

        if scroll_el:
            try:
                await scroll_el.evaluate("el => { el.scrollTop = el.scrollTop + 300; }")
            except Exception:
                await page.keyboard.press("PageDown")
        else:
            await page.keyboard.press("PageDown")
        await asyncio.sleep(0.45)

        opts = await _list_dropdown_options(page)
        if opts and opts != seen_options:
            seen_options = opts
            log(f"Scrolling {context} picker", {"visible": opts[:6]})

    return None


async def _select_category(page: Page, csv_category: str | None, log) -> bool:
    if not csv_category:
        return False

    terms = await _category_search_terms(csv_category)
    log("Category — open picker and scroll (no typing)", {"csv": csv_category, "targets": terms})

    if not await _open_category_picker(page, log):
        log("Category picker trigger not found")
        return False

    picked = await _scroll_picker_and_pick(page, terms, log, context="category")
    if picked:
        return True

    try:
        await page.keyboard.press("Escape")
    except Exception:
        pass
    log("Category not found in picker after scrolling")
    return False


async def _select_condition(page: Page, condition: str, log) -> bool:
    key = "used" if condition.lower() in ("used", "usato", "usata", "usado") else "new"
    labels = CONDITION_LABELS[key]
    log("Condition — click option (no typing)", {"condition": key})

    for text in labels:
        for factory in (
            lambda t=text: page.get_by_role("radio", name=re.compile(re.escape(t), re.I)).first,
            lambda t=text: page.locator(f'label:has-text("{t}")').first,
            lambda t=text: page.locator(f'div[role="button"]:has-text("{t}")').first,
            lambda t=text: page.get_by_text(t, exact=True).first,
        ):
            try:
                opt = factory()
                if await opt.count() and await opt.is_visible(timeout=2500):
                    await _scroll_into_view(opt)
                    await opt.click(timeout=6000)
                    await _human_pause(0.8, 1.5)
                    log("Selected condition", {"picked": text})
                    return True
            except Exception:
                continue

    field = await _find_combobox(page, ["Condition", "Condizione", "Stato"])
    if field:
        await _scroll_into_view(field)
        await field.click(timeout=5000)
        await _human_pause(0.8, 1.2)
        picked = await _scroll_picker_and_pick(page, list(labels), log, context="condition")
        if picked:
            return True

    log("Condition not found on current step")
    return False


async def _select_availability(page: Page, availability: str, log) -> bool:
    key = "stock" if availability.lower() in ("stock", "in_stock", "in stock") else "single"
    log("Selecting availability", {"availability": key})

    want_patterns = AVAILABILITY_LABELS[key]
    combobox = page.get_by_role("combobox", name=re.compile(r"availability|disponibilit", re.I)).first
    try:
        if await combobox.count() and await combobox.is_visible(timeout=2000):
            current = (await combobox.input_value()).strip().lower()
            if any(p.lower() in current for p in want_patterns):
                log("Availability already set", {"value": current})
                return True
            await _scroll_into_view(combobox)
            await combobox.click(timeout=5000)
            await _human_pause(0.6, 1.0)
            picked = await _scroll_picker_and_pick(page, list(want_patterns), log, context="availability")
            if picked:
                return True
    except Exception:
        pass

    for text in want_patterns:
        for loc_factory in (
            lambda t=text: page.get_by_role("radio", name=re.compile(re.escape(t), re.I)).first,
            lambda t=text: page.locator(f'label:has-text("{t}")').first,
            lambda t=text: page.get_by_text(t, exact=False).first,
        ):
            try:
                opt = loc_factory()
                if await opt.count() and await opt.is_visible(timeout=2500):
                    await _scroll_into_view(opt)
                    await opt.click(timeout=5000)
                    await _human_pause(1.0, 2.0)
                    log("Selected availability", {"picked": text})
                    return True
            except Exception:
                continue

    log("Availability field not visible on current step")
    return False


async def _fill_after_condition(page: Page, payload: ProductListingPayload, log) -> None:
    """After condition: optional brand/color, description, availability, then Next."""
    log("More details — optional fields, then description + availability")
    try:
        await page.evaluate("window.scrollBy(0, 500)")
        await _human_pause(0.6, 1.0)
    except Exception:
        pass
    if payload.extra_details:
        await _fill_extra_details(page, payload.extra_details, log)
    await _fill_description(page, payload.description or payload.title, log)
    await _select_availability(page, payload.availability, log)


async def _return_to_marketplace_home(
    page: Page, context: BrowserContext, cfg: Settings, log,
) -> None:
    """After listing step — back to Marketplace feed until next scheduled item."""
    from app.services.facebook_flow import stage_open_marketplace

    log("Returning to Marketplace — waiting for next scheduled product")
    try:
        if is_on_facebook_auth_flow(page):
            return
        await stage_open_marketplace(page, cfg, log, context=context)
        await dismiss_login_popup_once(page)
        await save_session(context, cfg)
        log("Marketplace home ready")
    except Exception as exc:
        log("Could not return to Marketplace", {"error": str(exc)[:200]})


async def _log_default_listing_location(log) -> None:
    log("Listing location — Facebook account default only (never typing Zurich/city)")


async def _ensure_marketplace_logged_in(
    page: Page,
    context: BrowserContext,
    cfg: Settings,
    log,
) -> None:
    """Login check first — same idea as Facebook monitoring Start flow."""
    from app.services.facebook_flow import stage_open_marketplace

    log("Checking Facebook login on Marketplace first")
    if is_on_facebook_auth_flow(page):
        log("Login/verification in progress — complete it in Chromium, bot is idle")
        ok = await wait_until_marketplace_logged_in(page, context, cfg, log_fn=log, timeout_seconds=900)
        if not ok:
            raise RuntimeError("Facebook login not completed — log in manually in Chromium")
    elif "marketplace" not in page.url.lower():
        await stage_open_marketplace(page, cfg, log, context=context)

    if await is_login_fully_complete(context, page):
        log("Logged in — Marketplace ready")
        await dismiss_login_popup_once(page)
        return

    dismissed = await dismiss_login_popup_once(page)
    if dismissed:
        log("Login popup dismissed — use Email/Password in the TOP header (not the popup)")
    else:
        log("Not logged in — dismiss popup if shown, then log in via top header")

    ok = await wait_until_marketplace_logged_in(page, context, cfg, log_fn=log, timeout_seconds=900)
    if not ok:
        raise RuntimeError("Facebook login required — log in manually in Chromium, then retry")

    if not is_on_facebook_auth_flow(page):
        await reload_marketplace_after_login(page, cfg)
    await dismiss_login_popup_once(page)
    log("Login complete — Marketplace loaded")


async def _fill_extra_details(page: Page, details: dict[str, str], log) -> None:
    if not details:
        return

    visible_any = False
    for field_name, value in details.items():
        if not value.strip():
            continue

        filled = False
        if await _fill_by_label(page, [field_name], value):
            filled = True
        elif await _fill_first_visible(
            page,
            [
                f'input[aria-label*="{field_name}" i]',
                f'textarea[aria-label*="{field_name}" i]',
                f'input[placeholder*="{field_name}" i]',
            ],
            value,
        ):
            filled = True

        if filled:
            visible_any = True
            log(f"Filled detail: {field_name}", {"value": value})
        else:
            log(f"Detail placeholder not visible: {field_name}")

    if visible_any:
        await _human_pause(0.6, 1.0)


async def _fill_description(page: Page, text: str, log) -> bool:
    try:
        await page.evaluate("window.scrollBy(0, Math.min(600, document.body.scrollHeight * 0.35))")
        await _human_pause(1.0, 2.0)
    except Exception:
        pass

    selectors = [
        'textarea[aria-label*="Description" i]',
        'textarea[placeholder*="Description" i]',
        'textarea[aria-label*="Descrizione" i]',
        'div[role="textbox"][aria-label*="Description" i]',
        'div[role="textbox"][aria-label*="Descrizione" i]',
    ]
    for sel in selectors:
        loc = page.locator(sel).first
        try:
            if await loc.count() and await loc.is_visible(timeout=3000):
                await _scroll_into_view(loc)
                await _type_slow(loc, text[:5000])
                log("Filled description")
                return True
        except Exception:
            continue

    if await _fill_by_label(page, ["Description", "Descrizione", "Describe your item"], text[:5000]):
        log("Filled description")
        return True

    log("Description not visible on current step")
    return False


async def _fill_title(page: Page, title: str, log) -> None:
    log("Filling listing title")
    title_ok = await _fill_by_label(page, ["Title", "Titolo", "What are you selling"], title[:100])
    if not title_ok:
        title_ok = await _fill_first_visible(
            page,
            [
                'input[aria-label*="Title" i]',
                'input[placeholder*="Title" i]',
                'input[aria-label*="Titolo" i]',
            ],
            title[:100],
        )
    if not title_ok:
        raise RuntimeError("Could not find title field — form may not be ready")
    log("Title filled")


async def _price_locator(page: Page) -> Locator:
    return page.locator(
        'input[aria-label*="Price" i], input[aria-label*="Prezzo" i], '
        'input[inputmode="decimal"], input[placeholder*="Price" i], input[placeholder*="Prezzo" i]'
    ).first


async def _price_field(page: Page) -> Locator:
    """FB create/item: title=input[0], price=input[1] (often no aria-label)."""
    return page.locator(
        'input[type="text"]:not([role="combobox"]):not([aria-label="Location" i])'
    ).nth(1)


async def _price_is_filled(page: Page, price: float | None) -> bool:
    if price is None:
        return True
    expected = str(int(price)) if price == int(price) else f"{price:.2f}"
    exp_digits = re.sub(r"[^\d]", "", expected)
    if not exp_digits:
        return False

    try:
        loc = await _price_field(page)
        if await loc.count():
            val = (await loc.input_value()).strip()
            val_digits = re.sub(r"[^\d]", "", val)
            if val_digits and (val_digits == exp_digits or exp_digits in val_digits):
                return True
    except Exception:
        pass

    locators = [
        page.locator('input[aria-label*="Price" i], input[aria-label*="Prezzo" i]').first,
        page.locator('input[inputmode="decimal"]').first,
    ]
    for loc in locators:
        try:
            if not await loc.count():
                continue
            val = (await loc.input_value()).strip()
            val_digits = re.sub(r"[^\d]", "", val)
            if val_digits and (val_digits == exp_digits or exp_digits in val_digits):
                return True
        except Exception:
            continue
    return False


async def _fill_price_via_tab_from_title(page: Page, price: float, price_str: str, log) -> bool:
    title_loc = page.locator(
        'input[aria-label*="Title" i], input[aria-label*="Titolo" i]'
    ).first
    try:
        if not await title_loc.count() or not await title_loc.is_visible(timeout=2000):
            return False
        await title_loc.click(timeout=3000)
        await page.keyboard.press("Tab")
        await asyncio.sleep(0.4)
        await page.keyboard.press("Control+A")
        await page.keyboard.type(price_str, delay=60)
        await _human_pause(0.5, 0.8)
        if await _price_is_filled(page, price):
            log("Price filled via Tab from title", {"value": price_str})
            return True
    except Exception:
        pass
    return False


async def _fill_price_by_scanning(page: Page, price: float, price_str: str, log) -> bool:
    """Find price input by scanning visible form fields (FB hides label sometimes)."""
    inputs = page.locator(
        'input:not([type="file"]):not([type="hidden"]):not([type="checkbox"])'
    )
    try:
        count = await inputs.count()
    except Exception:
        return False

    for i in range(count):
        inp = inputs.nth(i)
        try:
            if not await inp.is_visible(timeout=400):
                continue
            al = (await inp.get_attribute("aria-label") or "").lower()
            if any(x in al for x in ("title", "titolo", "search", "category", "categoria", "location")):
                continue
            if "price" in al or "prezzo" in al:
                await _scroll_into_view(inp)
                await inp.click(timeout=3000)
                await inp.fill("")
                await inp.fill(price_str)
                if await _price_is_filled(page, price):
                    log("Price filled via aria-label scan", {"index": i})
                    return True
            val = (await inp.input_value()).strip()
            if not val:
                await _scroll_into_view(inp)
                await inp.click(timeout=3000)
                await inp.fill(price_str)
                if await _price_is_filled(page, price):
                    log("Price filled via empty input scan", {"index": i, "aria": al})
                    return True
        except Exception:
            continue
    return False


async def _fill_price(page: Page, price: float | None, log) -> None:
    if price is None:
        return
    price_str = str(int(price)) if price == int(price) else f"{price:.2f}"
    log("Filling price", {"value": price_str})

    try:
        loc = await _price_field(page)
        if await loc.count() and await loc.is_visible(timeout=3000):
            await _scroll_into_view(loc)
            await loc.click(timeout=4000)
            await loc.fill("")
            await loc.fill(price_str)
            if await _price_is_filled(page, price):
                log("Price filled on title+1 input", {"value": price_str})
                return
    except Exception:
        pass

    if await _fill_price_via_tab_from_title(page, price, price_str, log):
        return

    label = page.get_by_text(re.compile(r"^Price$|^Prezzo$", re.I)).first
    try:
        if await label.count() and await label.is_visible(timeout=2000):
            sibling = label.locator(
                "xpath=following::input[1] | following::div[@role='textbox'][1]"
            ).first
            if await sibling.count() and await sibling.is_visible(timeout=1500):
                await _scroll_into_view(sibling)
                await sibling.click(timeout=4000)
                await sibling.fill("")
                await sibling.press_sequentially(price_str, delay=70)
                if await _price_is_filled(page, price):
                    log("Price filled via label sibling", {"value": price_str})
                    return
    except Exception:
        pass

    candidates = [
        page.get_by_role("spinbutton").first,
        page.get_by_label(re.compile(r"price|prezzo", re.I)).first,
        page.locator('input[aria-label*="Price" i]').first,
        page.locator('input[aria-label*="Prezzo" i]').first,
        page.locator('div[role="textbox"][aria-label*="Price" i]').first,
        page.locator('div[role="textbox"][aria-label*="Prezzo" i]').first,
        page.locator('input[inputmode="decimal"]').first,
        page.locator('input[inputmode="numeric"]').first,
    ]
    for loc in candidates:
        try:
            if not await loc.count() or not await loc.is_visible(timeout=2000):
                continue
            await _scroll_into_view(loc)
            await loc.click(timeout=4000)
            await asyncio.sleep(0.2)
            try:
                await loc.fill("")
                await loc.fill(price_str)
            except Exception:
                await loc.press_sequentially(price_str, delay=70)
            await _human_pause(0.4, 0.8)
            if await _price_is_filled(page, price):
                log("Price filled", {"value": price_str})
                return
        except Exception:
            continue

    if await _fill_price_by_scanning(page, price, price_str, log):
        return

    raise RuntimeError(f"Could not fill price field — expected {price_str}")


async def _ensure_price_filled(page: Page, price: float | None, log) -> None:
    if price is None:
        return
    if await _price_is_filled(page, price):
        log("Price confirmed", {"value": str(int(price)) if price == int(price) else price})
        return
    log("Price missing or empty — retrying")
    try:
        await _fill_price(page, price, log)
    except RuntimeError as exc:
        log(f"Price still not filled: {exc}")


async def _fill_visible_step_fields(
    page: Page,
    payload: ProductListingPayload,
    log,
    *,
    photos_done: bool,
    fill_extra_details: bool = True,
) -> bool:
    """Fill whatever fields are visible on the current wizard step."""
    touched = False

    if not photos_done and payload.image_paths:
        return False

    title_loc = page.locator('input[aria-label*="Title" i], input[aria-label*="Titolo" i]').first
    try:
        if await title_loc.count() and await title_loc.is_visible(timeout=1200):
            val = await title_loc.input_value()
            if not val.strip():
                await _fill_title(page, payload.title, log)
                touched = True
    except Exception:
        pass

    price_loc = page.locator('input[aria-label*="Price" i], input[aria-label*="Prezzo" i]').first
    try:
        if payload.price is not None and await price_loc.count() and await price_loc.is_visible(timeout=1200):
            val = await price_loc.input_value()
            if not val.strip():
                await _fill_price(page, payload.price, log)
                touched = True
    except Exception:
        pass

    await _ensure_price_filled(page, payload.price, log)

    if payload.category and await _find_combobox(page, ["Category", "Categoria"]):
        cat_field = await _find_combobox(page, ["Category", "Categoria"])
        if cat_field:
            try:
                val = await cat_field.input_value()
            except Exception:
                val = ""
            if not val.strip():
                if await _select_category(page, payload.category, log):
                    touched = True

    if await _find_combobox(page, ["Condition", "Condizione", "Stato"]) or await page.get_by_text(
        re.compile(r"^New$|^Nuovo$|^Used$|^Usato$", re.I)
    ).count():
        if await _select_condition(page, payload.condition, log):
            touched = True

    if fill_extra_details:
        await _fill_extra_details(page, payload.extra_details, log)
    if await _fill_description(page, payload.description or payload.title, log):
        touched = True

    if await _select_availability(page, payload.availability, log):
        touched = True

    return touched


async def _sidebar_next_state(page: Page) -> dict:
    try:
        return await page.evaluate(
            """() => {
              const winW = window.innerWidth;
              const isNext = (el) => /^(Next|Avanti|Continua|Continue|Siguiente)$/i.test(
                (el.innerText || el.textContent || '').trim()
              );
              const btn = [...document.querySelectorAll('[role="button"], button')]
                .filter(isNext)
                .filter(el => el.getBoundingClientRect().left < winW * 0.55)
                .sort((a, b) => b.getBoundingClientRect().top - a.getBoundingClientRect().top)[0];
              if (!btn) return { found: false };
              const r = btn.getBoundingClientRect();
              const style = getComputedStyle(btn);
              const ariaDisabled = btn.getAttribute('aria-disabled') === 'true';
              const disabledAttr = btn.hasAttribute('disabled');
              const clickable = !ariaDisabled && !disabledAttr;
              return {
                found: true,
                clickable,
                ariaDisabled,
                inViewport: r.top >= 0 && r.bottom <= window.innerHeight + 4,
                nextBottom: Math.round(r.bottom),
              };
            }"""
        )
    except Exception:
        return {"found": False}


async def _wait_for_next_enabled(page: Page, log, *, timeout_s: float = 90.0) -> bool:
    log("Waiting until sidebar Next is enabled")
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        if await _publish_button_visible(page):
            return False
        state = await _sidebar_next_state(page)
        if state.get("found") and state.get("clickable"):
            await _scroll_listing_sidebar_to_bottom(page, log)
            await _human_pause(1.0, 2.0)
            log("Sidebar Next is clickable", state)
            return True
        btn = await _find_sidebar_next_button(page, None)
        if btn:
            try:
                if await btn.is_enabled(timeout=500):
                    await _scroll_listing_sidebar_to_bottom(page, log)
                    return True
            except Exception:
                pass
        await asyncio.sleep(1.2)
    log("Next still disabled — fill required fields in the left sidebar", await _sidebar_next_state(page))
    return False


async def _click_sidebar_next_js(page: Page, log) -> bool:
    try:
        clicked = await page.evaluate(
            """() => {
              const winW = window.innerWidth;
              const isNext = (el) => /^(Next|Avanti|Continua|Continue|Siguiente)$/i.test(
                (el.innerText || el.textContent || '').trim()
              );
              const btn = [...document.querySelectorAll('[role="button"], button')]
                .filter(isNext)
                .filter(el => el.getBoundingClientRect().left < winW * 0.55)
                .sort((a, b) => b.getBoundingClientRect().top - a.getBoundingClientRect().top)[0];
              if (!btn) return false;
              btn.scrollIntoView({ block: 'end', behavior: 'instant' });
              btn.click();
              return true;
            }"""
        )
        if clicked:
            log("Clicked sidebar Next via JS (fixed footer)")
        return bool(clicked)
    except Exception:
        return False


async def _safe_click_next(page: Page, log) -> bool:
    await _scroll_listing_sidebar_to_bottom(page, log)
    state = await _sidebar_next_state(page)
    btn = await _find_sidebar_next_button(page, log)
    if not btn and not state.get("found"):
        log("Next not in DOM on left sidebar — trying JS click after scroll")
        if await _click_sidebar_next_js(page, log):
            await _wait_step_after_next(page, log)
            return True
        return False
    playwright_enabled = True
    if btn:
        try:
            playwright_enabled = await btn.is_enabled(timeout=2000)
        except Exception:
            playwright_enabled = False
    if not playwright_enabled and not state.get("clickable"):
        log("Next is disabled — not clicking", state)
        return False
    if btn:
        await _scroll_into_view(btn)
        await _human_pause(1.2, 2.5)
        try:
            await btn.click(timeout=8000)
        except Exception:
            log("Next click normal failed — trying force / JS on fixed sidebar footer")
            try:
                await btn.click(timeout=8000, force=True)
            except Exception:
                if not await _click_sidebar_next_js(page, log):
                    return False
    elif not await _click_sidebar_next_js(page, log):
        return False
    log("Clicked sidebar Next — waiting for next step")
    await _wait_step_after_next(page, log)
    return True


async def _advance_to_publish_screen(
    page: Page,
    payload: ProductListingPayload,
    log,
    *,
    max_steps: int = 6,
    fill_extra_details: bool = True,
) -> bool:
    for step in range(max_steps):
        if await _publish_button_visible(page):
            log("Publish screen visible")
            return True

        await _fill_visible_step_fields(
            page, payload, log, photos_done=True, fill_extra_details=fill_extra_details,
        )

        if await _publish_button_visible(page):
            return True

        if not await _wait_for_next_enabled(page, log):
            break

        if not await _safe_click_next(page, log):
            break

        log(f"Wizard step {step + 1} complete")

    return await _publish_button_visible(page)


async def _advance_listing_steps(
    page: Page,
    payload: ProductListingPayload,
    log,
    *,
    max_steps: int = 6,
    fill_extra_details: bool = True,
) -> None:
    for _ in range(max_steps):
        if await _click_button(page, "Publish", "Pubblica", "Post", "Publicar"):
            return
        await _fill_visible_step_fields(
            page, payload, log, photos_done=True, fill_extra_details=fill_extra_details,
        )
        if not await _wait_for_next_enabled(page, log, timeout_s=45.0):
            break
        if not await _safe_click_next(page, log):
            break


async def publish_marketplace_item(
    page: Page,
    payload: ProductListingPayload,
    cfg: Settings,
    *,
    context: BrowserContext | None = None,
    log_fn=None,
    skip_publish: bool = False,
    stop_after_first_next: bool = False,
    fill_extra_details: bool = True,
    return_to_marketplace_after: bool = False,
) -> str:
    """
    Slow step-by-step UI flow:
    Marketplace → Create new listing → Item for sale →
    wait for full load → photos → title → price → category → condition →
    details → description → availability → Next (only when enabled) → Publish
    """
    log = log_fn or (lambda msg, details=None: logger.info("%s %s", msg, details or {}))

    if not payload.image_paths:
        raise RuntimeError("At least one product image is required")

    nav_timeout = max(cfg.PLAYWRIGHT_TIMEOUT, PUBLISH_TIMEOUT_MS)
    page.set_default_timeout(nav_timeout)

    if context is not None:
        await _ensure_marketplace_logged_in(page, context, cfg, log)

    await _open_item_listing_form(page, log)
    await _log_browser_layout(page, log)
    await dismiss_login_popup_once(page)
    await _log_default_listing_location(log)

    if "login" in page.url.lower() and "marketplace" not in page.url.lower():
        raise RuntimeError("Facebook login required — log in manually in Chromium")

    log("Photos on create/item (2–3s after load)", {"count": len(payload.image_paths)})
    await _upload_photos(page, payload.image_paths, log)
    await _human_pause(1.0, 1.5)

    log("Title")
    await _fill_title(page, payload.title, log)
    await _human_pause(0.6, 1.0)

    log("Price (right after title)")
    try:
        await _fill_price(page, payload.price, log)
    except RuntimeError:
        log("Price not filled yet — will retry after category")

    if payload.category:
        log("Category — picker scroll")
        if not await _select_category(page, payload.category, log):
            log("Category not set — check CSV category name")
        await _ensure_price_filled(page, payload.price, log)

    log("Condition")
    await _select_condition(page, payload.condition, log)
    await _ensure_price_filled(page, payload.price, log)

    log("Description, optional details, availability, then Next")
    await _fill_after_condition(page, payload, log)
    await _scroll_listing_sidebar_to_bottom(page, log)

    if skip_publish and stop_after_first_next:
        await _scroll_listing_sidebar_to_bottom(page, log)
        if DRY_RUN_REVIEW_PAUSE_SEC > 0:
            log(f"Brief pause {DRY_RUN_REVIEW_PAUSE_SEC}s before sidebar Next")
            await asyncio.sleep(DRY_RUN_REVIEW_PAUSE_SEC)

        on_publish = False
        if await _publish_button_visible(page):
            log("Publish screen already visible — dry run stops here")
            on_publish = True
        else:
            log("Clicking fixed sidebar Next after availability")
            clicked = False
            for attempt in range(60):
                state = await _sidebar_next_state(page)
                if attempt % 4 == 0:
                    log("Sidebar Next state", state)
                if state.get("found") and not state.get("ariaDisabled"):
                    clicked = await _safe_click_next(page, log)
                    if clicked:
                        break
                if await _publish_button_visible(page):
                    on_publish = True
                    break
                await _scroll_listing_sidebar_to_bottom(page, None)
                await asyncio.sleep(1.5)

            if clicked and not on_publish:
                on_publish = await _wait_for_publish_screen(page, log, timeout_s=90.0)

        log(
            "Dry run complete — stopped at Publish screen (Publish NOT clicked)"
            if on_publish
            else "Dry run stopped — Next click or Publish screen not reached",
            {"url": page.url, "publish_visible": on_publish},
        )
        if return_to_marketplace_after and context is not None:
            await _return_to_marketplace_home(page, context, cfg, log)
        else:
            await save_session(page.context, cfg)
        return page.url

    log("Next only when enabled")
    if skip_publish:
        on_publish = await _advance_to_publish_screen(
            page, payload, log, max_steps=6, fill_extra_details=fill_extra_details,
        )
        log(
            "Dry run complete — reached publish screen" if on_publish else "Dry run complete — form filled",
            {"url": page.url, "publish_visible": on_publish},
        )
        if return_to_marketplace_after and context is not None:
            await _return_to_marketplace_home(page, context, cfg, log)
        else:
            await save_session(page.context, cfg)
        return page.url

    log("Submitting listing — Next only when enabled, then Publish")
    await _advance_listing_steps(
        page, payload, log, max_steps=6, fill_extra_details=fill_extra_details,
    )
    await _human_pause(2.0, 3.5)

    if await _click_button(page, "Publish", "Pubblica", "Post", "Publicar"):
        await _human_pause(3.0, 5.0)

    try:
        await page.wait_for_url(re.compile(r"marketplace/item|marketplace/you/selling"), timeout=60_000)
    except PlaywrightTimeout:
        pass

    listing_url = page.url
    if "marketplace/create" in listing_url and "step=audience" not in listing_url:
        err_text = ""
        try:
            err_text = await page.locator('[role="alert"]').first.inner_text(timeout=2000)
        except Exception:
            pass
        raise RuntimeError(f"Publish did not complete. {err_text[:300]}")

    await save_session(page.context, cfg)
    log("Listing published", {"url": listing_url})
    if return_to_marketplace_after and context is not None:
        await _return_to_marketplace_home(page, context, cfg, log)
    return listing_url
