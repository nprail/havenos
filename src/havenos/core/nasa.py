"""NASA Image of the Day photo source. The data is an RSS feed, not a documented API: one plain GET, no key,
about 50 <item>s newest first, each with an <enclosure url=...> that is the full-size original."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import random
import warnings
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
from PIL import Image, ImageOps, UnidentifiedImageError

from .config import NasaConfig

log = logging.getLogger(__name__)

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
MAX_BYTES = 80 * 1024 * 1024     # originals can be large; refuse anything absurd rather than fill the cache
MAX_EDGE = 1920                  # the displays are 1280x800 at most; keep room for the blurred backdrop and a little zoom
KEEP_BYTES = 600 * 1024          # a JPEG already this small and this short is kept exactly as downloaded
JPEG_QUALITY = 82


class NasaError(Exception):
    pass


def shrink(src: Path, dst: Path) -> None:
    """Turn a downloaded original (often 10 to 40 MB, tens of megapixels) into a screen-sized JPEG (a few hundred KB) at
    `dst`, and remove `src`. Blocking: call it in an executor. A JPEG decodes at 1/2, 1/4 or 1/8 size when it is going to be
    shrunk anyway (`draft`), so a huge original never has to be held in memory in full. A file that Pillow cannot read is
    kept as it is, and left for the photo pipeline to reject."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)        # NASA's largest are just over Pillow's limit
            with Image.open(src) as im:
                is_jpeg = im.format == "JPEG"
                if is_jpeg and max(im.size) <= MAX_EDGE and src.stat().st_size <= KEEP_BYTES:
                    src.replace(dst)
                    return
                if is_jpeg:
                    im.draft("RGB", (MAX_EDGE, MAX_EDGE))
                im = ImageOps.exif_transpose(im).convert("RGB")
                im.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)
                part = dst.with_name(dst.name + ".small")
                im.save(part, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
        if is_jpeg and part.stat().st_size >= src.stat().st_size:                    # never make a file bigger
            part.unlink()
            src.replace(dst)
        else:
            part.replace(dst)
            src.unlink(missing_ok=True)
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as e:
        log.warning("nasa: could not shrink %s (%s); keeping it as it is", src.name, e)
        if src.exists():
            src.replace(dst)


@dataclass(frozen=True)
class NasaImage:
    url: str            # the full-size original (the <enclosure> url); also this source's photo id
    title: str
    date: str
    link: str           # the nasa.gov page for the image
    caption: str


def parse_feed(xml: str | bytes) -> list[NasaImage]:
    """Items that carry an http(s) image enclosure, in feed order. Anything else is skipped."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        raise NasaError(f"the feed is not valid XML ({e})") from e
    out = []
    for item in root.iter("item"):
        enc = item.find("enclosure")
        if enc is None:
            continue
        url = enc.get("url") or ""
        parsed = urlparse(url)
        is_image = (enc.get("type") or "").startswith("image/") or Path(parsed.path).suffix.lower() in IMAGE_SUFFIXES
        if parsed.scheme not in ("http", "https") or not parsed.netloc or not is_image:
            continue
        text = lambda tag: (item.findtext(tag) or "").strip()
        out.append(NasaImage(url, text("title"), text("pubDate"), text("link"), text("description")))
    return out


class NasaSource:
    kind = "nasa"
    ephemeral = True    # downloaded originals are cache; the playlist deletes them when they age out

    def __init__(self, cfg: NasaConfig, cache_dir: Path, session: aiohttp.ClientSession | None = None, *,
                 rng: random.Random | None = None) -> None:
        self.cfg = cfg
        self._rng = rng or random.Random()
        self.dir = Path(cache_dir) / "nasa"
        self.dir.mkdir(parents=True, exist_ok=True)
        self._session = session
        self._own_session = session is None
        self._closed = False
        self.images: dict[str, NasaImage] = {}      # by url, from the last feed read

    async def _http(self) -> aiohttp.ClientSession:
        if self._closed:                            # a download that outlived a settings change must not open a session nobody closes
            raise NasaError("the photo source was closed")
        if self._session is None:
            self._session = aiohttp.ClientSession(headers={"User-Agent": "havenOS"},
                                                  timeout=aiohttp.ClientTimeout(total=120))
        return self._session

    async def close(self) -> None:
        self._closed = True
        if self._session and self._own_session:
            await self._session.close()
            self._session = None

    async def list_ids(self) -> list[str]:
        """The whole feed in random order. Each pass is a fresh shuffle of whatever the feed holds today."""
        s = await self._http()
        try:
            async with s.get(self.cfg.url) as r:
                if r.status >= 400:
                    raise NasaError(f"NASA returned HTTP {r.status}")
                body = await r.read()
        except aiohttp.ClientError as e:
            raise NasaError(f"could not reach NASA ({e})") from e
        images = parse_feed(body)
        if not images:
            raise NasaError("the NASA feed had no images")
        self.images = {i.url: i for i in images}
        ids = list(self.images)
        self._rng.shuffle(ids)
        return ids

    async def fetch(self, photo_id: str) -> Path:
        out = self.dir / (hashlib.sha1(photo_id.encode()).hexdigest()[:16] + ".jpg")       # always a JPEG once shrunk
        if out.exists():
            return out
        s = await self._http()
        tmp = out.with_suffix(".part")
        try:
            async with s.get(photo_id) as r:
                if r.status >= 400:
                    raise NasaError(f"NASA returned HTTP {r.status} for an image")
                size = 0
                with open(tmp, "wb") as fh:
                    async for chunk in r.content.iter_chunked(64 * 1024):
                        size += len(chunk)
                        if size > MAX_BYTES:
                            raise NasaError("an image was larger than the size limit")
                        fh.write(chunk)
            await asyncio.get_running_loop().run_in_executor(None, shrink, tmp, out)
        except BaseException:
            tmp.unlink(missing_ok=True)
            out.with_name(out.name + ".small").unlink(missing_ok=True)
            raise
        return out
