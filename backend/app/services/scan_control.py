"""One bot at a time — Stop cancels, Start always takes over."""
from __future__ import annotations

import threading
import time

_scan_mutex = threading.Lock()
_scan_cancel = threading.Event()


def try_acquire_scan() -> bool:
    return _scan_mutex.acquire(blocking=False)


def release_scan() -> None:
    if _scan_mutex.locked():
        _scan_mutex.release()


def is_scan_busy() -> bool:
    return _scan_mutex.locked()


def request_scan_cancel() -> None:
    _scan_cancel.set()


def clear_scan_cancel() -> None:
    _scan_cancel.clear()


def is_scan_cancelled() -> bool:
    return _scan_cancel.is_set()


def wait_until_scan_idle(timeout_seconds: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not is_scan_busy():
            return True
        time.sleep(0.1)
    return not is_scan_busy()


def acquire_scan_or_wait(timeout_seconds: float = 15.0) -> bool:
    """Start — wait for Stop to finish, then take the lock."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if try_acquire_scan():
            return True
        time.sleep(0.1)
    return try_acquire_scan()
