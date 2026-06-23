"""Run sync database work off the asyncio event loop with a hard timeout."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

DEFAULT_DB_OP_TIMEOUT = 10.0


async def run_sync(
    func: Callable[..., T],
    /,
    *args,
    timeout: float = DEFAULT_DB_OP_TIMEOUT,
    **kwargs,
) -> T:
    return await asyncio.wait_for(asyncio.to_thread(func, *args, **kwargs), timeout=timeout)
