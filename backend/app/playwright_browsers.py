"""Playwright Chromium stored inside the project (install once via install-chromium.bat)."""
from __future__ import annotations

import os
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
BROWSERS_DIR = BACKEND_ROOT / "playwright-browsers"


def configure_playwright_browsers_path() -> Path:
    """All Playwright browser downloads go to backend/playwright-browsers/."""
    BROWSERS_DIR.mkdir(parents=True, exist_ok=True)
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(BROWSERS_DIR.resolve())
    return BROWSERS_DIR


def chromium_executable() -> Path | None:
    configure_playwright_browsers_path()
    for candidate in BROWSERS_DIR.glob("chromium-*/chrome-win64/chrome.exe"):
        if candidate.is_file():
            return candidate
    return None


def is_chromium_installed() -> bool:
    return chromium_executable() is not None
