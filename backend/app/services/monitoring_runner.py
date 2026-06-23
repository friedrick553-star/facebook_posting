"""Run Facebook monitoring off the FastAPI event loop so /health always responds."""
from __future__ import annotations

import asyncio
import logging
import sys
import threading
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)


def _configure_child_event_loop() -> None:
    if sys.platform == "win32":
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        except Exception:
            pass


def run_async_in_thread(coro_factory: Callable[[], Awaitable[None]], *, name: str = "monitoring-scan") -> None:
    """Execute monitoring in a dedicated thread with its own event loop (visible Chrome on Windows)."""

    def _target() -> None:
        _configure_child_event_loop()
        try:
            asyncio.run(coro_factory())
        except Exception as exc:
            logger.exception("Background %s failed: %s", name, exc)

    thread = threading.Thread(target=_target, name=name, daemon=False)
    thread.start()
