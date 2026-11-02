"""Immich photo source (https://immich.app/docs/api). Read-only: lists image assets and downloads previews."""
from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import aiohttp

from .config import ImmichConfig

log = logging.getLogger(__name__)


class ImmichError(Exception):
    pass


# (start age, end age, sample size) in days. Each bucket is sampled separately so recent photos are
# actually in the pool; a single random sample of a big library would be dominated by its older years.
BUCKETS = ((0, 30, 100), (30, 365, 100), (365, 1095, 100), (1095, None, 100))


def recency_weight(created: str | None, now: datetime, half_life_days: float, floor: float) -> float:
    if half_life_days <= 0 or not created:
        return 1.0 if half_life_days <= 0 else floor
    try:
        age = (now - datetime.fromisoformat(created.replace("Z", "+00:00"))).total_seconds() / 86400
    except ValueError:
        return floor
    return max(floor, 0.5 ** (max(age, 0.0) / half_life_days))


def weighted_order(assets: list[dict], now: datetime, cfg: ImmichConfig, rng: random.Random) -> list[str]:
    """Weighted random order without replacement (Efraimidis-Spirakis): newer assets tend to come first,
    but every asset has a nonzero chance, so old photos still show up."""
    keyed = []
    for a in assets:
        w = recency_weight(a.get("fileCreatedAt"), now, cfg.recency_half_life_days, cfg.recency_floor)
        keyed.append((rng.random() ** (1.0 / w), a["id"]))
    keyed.sort(reverse=True)
    return [i for _, i in keyed]


class ImmichSource:
    kind = "immich"
    ephemeral = True    # downloaded files are cache; the playlist deletes them when they age out

    def __init__(self, cfg: ImmichConfig, cache_dir: Path, session: aiohttp.ClientSession | None = None, *,
                 now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 rng: random.Random | None = None) -> None:
        self.cfg = cfg
        self._now = now
        self._rng = rng or random.Random()
        self.dir = self._dir = Path(cache_dir) / "immich"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._session = session
        self._own_session = session is None

    async def _http(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession(
                headers={"x-api-key": self.cfg.api_key, "Accept": "application/json"},
                timeout=aiohttp.ClientTimeout(total=60))
        return self._session

    async def close(self) -> None:
        if self._session and self._own_session:
            await self._session.close()
            self._session = None

    async def ping(self) -> bool:
        s = await self._http()
        async with s.get(f"{self.cfg.url}/api/server/ping") as r:
            return r.status == 200

    async def albums(self) -> list[dict]:
        s = await self._http()
        async with s.get(f"{self.cfg.url}/api/albums") as r:
            self._check(r)
            return [{"id": a["id"], "name": a.get("albumName", a["id"]), "count": a.get("assetCount", 0)}
                    for a in await r.json()]

    async def probe(self) -> dict:
        """What the settings UI shows after 'Test': reachable, key works, previews download, which albums exist."""
        if not await self.ping():
            raise ImmichError("server did not answer the ping")
        ids = await self.list_ids()
        if not ids:
            raise ImmichError("connected, but no photos were returned")
        path = await self.fetch(ids[0])            # needs the asset.view permission, which a read-only key often lacks
        try:
            albums = await self.albums()
        except ImmichError:
            albums = []                            # album.read not granted: the photo source still works without it
        return {"sample_photos": len(ids), "preview_bytes": path.stat().st_size, "albums": albums}

    async def list_ids(self) -> list[str]:
        s = await self._http()
        if self.cfg.album_id:
            async with s.get(f"{self.cfg.url}/api/albums/{self.cfg.album_id}") as r:
                self._check(r)
                assets = (await r.json()).get("assets", [])
        elif not self.cfg.shuffle:
            assets = await self._random(s, {})
        else:
            assets = await self._bucketed(s)
        assets = [a for a in assets if a.get("type", "IMAGE") == "IMAGE" and not a.get("isTrashed")]
        if not self.cfg.shuffle:
            return [a["id"] for a in assets]
        return weighted_order(assets, self._now(), self.cfg, self._rng)[: self.cfg.list_size]

    async def _random(self, s: aiohttp.ClientSession, filters: dict) -> list[dict]:
        async with s.post(f"{self.cfg.url}/api/search/random", json={"size": 100, "type": "IMAGE", **filters}) as r:
            self._check(r)
            body = await r.json()
            return body if isinstance(body, list) else body.get("assets", {}).get("items", [])

    async def _bucketed(self, s: aiohttp.ClientSession) -> list[dict]:
        """One random sample per age bucket, merged and de-duplicated."""
        now = self._now()
        seen: dict[str, dict] = {}
        errors = 0
        for start, end, size in BUCKETS:
            filters: dict = {"takenBefore": (now - timedelta(days=start)).isoformat()}
            if end is not None:
                filters["takenAfter"] = (now - timedelta(days=end)).isoformat()
            try:
                for a in await self._random(s, {**filters, "size": size}):
                    seen.setdefault(a["id"], a)
            except ImmichError as e:
                if "API key" in str(e):
                    raise
                errors += 1
                log.warning("Immich bucket %s-%s days failed: %s", start, end, e)
        if errors == len(BUCKETS):
            raise ImmichError("all Immich bucket queries failed")
        return list(seen.values())

    async def fetch(self, asset_id: str) -> Path:
        """Download the preview rendition (about 1440 px, already EXIF-oriented): far cheaper than the original."""
        out = self._dir / f"{asset_id}.jpg"
        if out.exists():
            return out
        s = await self._http()
        async with s.get(f"{self.cfg.url}/api/assets/{asset_id}/thumbnail", params={"size": "preview"}) as r:
            self._check(r)
            tmp = out.with_suffix(".part")
            with open(tmp, "wb") as fh:
                async for chunk in r.content.iter_chunked(64 * 1024):
                    fh.write(chunk)
            tmp.replace(out)
        return out

    @staticmethod
    def _check(r: aiohttp.ClientResponse) -> None:
        if r.status == 403:
            raise ImmichError("the API key is missing a permission (needs asset.read and asset.view; album.read for albums)")
        if r.status == 401:
            raise ImmichError("Immich rejected the API key")
        if r.status >= 400:
            raise ImmichError(f"Immich returned HTTP {r.status}")
