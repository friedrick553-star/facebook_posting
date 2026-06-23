"""One-time Playwright Chromium install into backend/playwright-browsers/."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.playwright_browsers import BROWSERS_DIR, configure_playwright_browsers_path, is_chromium_installed


def main() -> int:
    configure_playwright_browsers_path()

    if is_chromium_installed():
        print(f"Playwright Chromium already installed: {BROWSERS_DIR}")
        return 0

    print(f"Installing Playwright Chromium into {BROWSERS_DIR}")
    print("One-time download (~180 MB). Please wait...")
    result = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        check=False,
    )
    if result.returncode != 0:
        print("Install failed.", file=sys.stderr)
        return result.returncode or 1

    if is_chromium_installed():
        print("Playwright Chromium installed successfully.")
        return 0

    print("Install finished but chrome.exe not found.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
