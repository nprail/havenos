"""Cover-art cache (docs/specs/07 section 6): the core fetches and resizes art, QML only ever sees a local file.

`resolve(uri)` is synchronous and cheap, which is what the coordinator's state projection needs: a local path or
`file://` URI passes through, an `http(s)` URL returns its cached `file://` URI, or "" while the download runs in the
background (`on_ready` then fires so the state is published again with the real file).
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import logging
from pathlib import Path
from typing import Awaitable, Callable

import aiohttp

log = logging.getLogger(__name__)

SIZE = 512
MAX_BYTES = 8 * 1024 * 1024
MAX_FILES = 150


class ArtCache:
    def __init__(self, directory: Path, *, on_ready: Callable[[], None] = lambda: None,
                 fetch: Callable[[str], Awaitable[bytes]] | None = None, size: int = SIZE, max_files: int = MAX_FILES) -> None:
        self.dir = Path(directory)
        self._on_ready = on_ready
        self._fetch = fetch or self._http_fetch
        self._size = size
        self._max_files = max_files
        self._pending: set[str] = set()
        self._failed: set[str] = set()
        self._tasks: set[asyncio.Task] = set()
        self._session: aiohttp.ClientSession | None = None

    def _path(self, uri: str) -> Path:
        return self.dir / (hashlib.sha1(uri.encode()).hexdigest()[:20] + ".jpg")

    def resolve(self, uri: str) -> str:
        if not uri:
            return ""
        if uri.startswith(("file://", "/")):
            return uri if uri.startswith("file://") else "file://" + uri
        if not uri.startswith(("http://", "https://")):
            return ""
        path = self._path(uri)
        if path.exists():
            return "file://" + str(path)
        if uri not in self._pending and uri not in self._failed:
            try:
                task = asyncio.get_running_loop().create_task(self._download(uri, path))
            except RuntimeError:                       # no loop (a unit test of the projection): nothing to schedule
                return ""
            self._pending.add(uri)
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        return ""

    def path_for(self, uri: str) -> Path | None:
        """The cached file for `uri` if it is on disk (used to serve art to Home Assistant)."""
        r = self.resolve(uri)
        return Path(r.removeprefix("file://")) if r else None

    async def close(self) -> None:
        for t in list(self._tasks):
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def _http_fetch(self, uri: str) -> bytes:
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        async with self._session.get(uri) as r:
            r.raise_for_status()
            data = await r.content.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("cover art too large")
        return data

    async def _download(self, uri: str, path: Path) -> None:
        try:
            raw = await self._fetch(uri)
            jpeg = await asyncio.to_thread(self._shrink, raw)
            self.dir.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".part")
            tmp.write_bytes(jpeg)
            tmp.replace(path)
            self._prune()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.info("art: could not load %s: %s", uri, e)
            self._failed.add(uri)
        else:
            self._on_ready()
        finally:
            self._pending.discard(uri)

    def _shrink(self, raw: bytes) -> bytes:
        from PIL import Image
        with Image.open(io.BytesIO(raw)) as im:
            im = im.convert("RGB")
            im.thumbnail((self._size, self._size))
            out = io.BytesIO()
            im.save(out, "JPEG", quality=88)
            return out.getvalue()

    def _prune(self) -> None:
        files = sorted(self.dir.glob("*.jpg"), key=lambda p: p.stat().st_mtime)
        for p in files[:max(0, len(files) - self._max_files)]:
            p.unlink(missing_ok=True)
