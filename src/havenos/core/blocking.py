from __future__ import annotations

import asyncio
import logging
from concurrent.futures import BrokenExecutor, Executor
from typing import Callable, TypeVar

log = logging.getLogger(__name__)
T = TypeVar("T")


async def run_blocking(fn: Callable[..., T], *args, pool: Executor | None = None) -> T:
    """Run blocking/CPU-heavy work off the event loop (default thread pool, or the given executor).

    If the given pool is broken (a worker was killed, e.g. by the OOM killer) fall back to threads
    rather than failing every later call.
    """
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(pool, fn, *args)
    except BrokenExecutor:
        log.warning("worker pool is broken; running %s on a thread", getattr(fn, "__name__", fn))
        return await loop.run_in_executor(None, fn, *args)
