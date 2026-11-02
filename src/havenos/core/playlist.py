"""Photo playlist over a PhotoSource: bounded history for swipe-back, a small prefetch window ahead,
and eviction of cache files that age out. This is the bounded cache Immich photos need."""
from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path
from typing import Awaitable, Callable, Protocol

from .config import Config
from .photos import Photo, prepare_photo, scan
from .blocking import run_blocking
from concurrent.futures import Executor

log = logging.getLogger(__name__)


class PhotoSource(Protocol):
    kind: str
    ephemeral: bool
    dir: Path        # where an ephemeral source keeps its downloads (wiped on start)
    async def list_ids(self) -> list[str]: ...
    async def fetch(self, photo_id: str) -> Path: ...
    async def close(self) -> None: ...


class LocalSource:
    kind = "local"
    ephemeral = False

    def __init__(self, photo_dir: Path) -> None:
        self._dir = Path(photo_dir)

    async def list_ids(self) -> list[str]:
        return [p.name for p in scan(self._dir)]

    async def fetch(self, photo_id: str) -> Path:
        return self._dir / photo_id

    async def close(self) -> None:
        pass


class Playlist:
    def __init__(self, source: PhotoSource, config: Config, executor: Executor | None = None) -> None:
        self._src = source
        self._cfg = config
        self._pool = executor
        self._ids: list[str] = []
        self._pos = 0
        self._line: list[Photo] = []        # timeline: [... history, current, ahead ...]
        self._cursor = -1
        self._lock = asyncio.Lock()
        self._refill: asyncio.Task | None = None
        self._failures = 0
        # Prepared files of a remote source live in a directory we own and wipe on start, so crashes and
        # restarts cannot leave an unbounded pile of orphans behind.
        self._out_dir = Path(config.cache_dir) / "ephemeral" if source.ephemeral else Path(config.cache_dir)

    @property
    def current(self) -> Photo | None:
        return self._line[self._cursor] if 0 <= self._cursor < len(self._line) else None

    @property
    def cached_count(self) -> int:
        return len(self._line)

    async def start(self) -> Photo | None:
        if self._src.ephemeral:
            shutil.rmtree(self._out_dir, ignore_errors=True)
            shutil.rmtree(self._src.dir, ignore_errors=True)
            self._src.dir.mkdir(parents=True, exist_ok=True)
        await self.advance(1)
        self._schedule_refill()
        return self.current

    async def close(self) -> None:
        if self._refill:
            self._refill.cancel()
            await asyncio.gather(self._refill, return_exceptions=True)
        await self._src.close()

    async def advance(self, delta: int) -> Photo | None:
        """Move the cursor. Returns the (possibly unchanged) current photo."""
        async with self._lock:
            if delta < 0:
                self._cursor = max(0, self._cursor + delta)
            else:
                for _ in range(delta):
                    if self._cursor + 1 >= len(self._line) and not await self._append():
                        break
                    self._cursor += 1
            self._evict()
        self._schedule_refill()
        return self.current

    # ---- internals ---------------------------------------------------------------------

    async def _next_id(self) -> str | None:
        if self._pos >= len(self._ids):
            self._ids = await self._src.list_ids()
            self._pos = 0
            if not self._ids:
                return None
        pid = self._ids[self._pos]
        self._pos += 1
        return pid

    async def _append(self) -> bool:
        """Fetch + prepare the next photo onto the end of the timeline. Skips bad assets."""
        for _ in range(5):
            try:
                pid = await self._next_id()
                if pid is None:
                    return False
                raw = await self._src.fetch(pid)
                photo = await run_blocking(prepare_photo, str(raw), str(self._out_dir),
                                           *self._cfg.max_photo_size, pool=self._pool)
                self._line.append(_tag(photo, pid, self._src.ephemeral, raw))
                self._failures = 0
                return True
            except asyncio.CancelledError:
                raise
            except Exception as e:      # network, decode, auth: log, skip this asset, try the next
                self._failures += 1
                log.warning("photo skipped (%s: %s)", type(e).__name__, e)
        return False

    def _schedule_refill(self) -> None:
        if self._refill and not self._refill.done():
            return
        self._refill = asyncio.create_task(self._fill_ahead(), name="photo-prefetch")

    async def _fill_ahead(self) -> None:
        while True:
            async with self._lock:
                if len(self._line) - self._cursor - 1 >= self._cfg.prefetch:
                    return
                if not await self._append():
                    return
            await asyncio.sleep(0)

    def _evict(self) -> None:
        while self._cursor > self._cfg.history:
            old = self._line.pop(0)
            self._cursor -= 1
            if old.ephemeral:
                # The same asset can be on the timeline twice (the id list wraps); only delete files nothing else uses.
                in_use = {f for p in self._line for f in (p.path, p.raw)}
                for f in (old.path, old.raw):
                    if f and f not in in_use:
                        Path(f).unlink(missing_ok=True)


def _tag(photo: Photo, pid: str, ephemeral: bool, raw: Path) -> Photo:
    from dataclasses import replace
    return replace(photo, id=pid, ephemeral=ephemeral, raw=str(raw) if ephemeral else "")
