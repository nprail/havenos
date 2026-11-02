"""Photo pipeline: scan, decode, downscale into a cache dir. Runs in a process pool, never on the event loop."""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, ImageOps

EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


@dataclass(frozen=True)
class Photo:
    name: str
    path: str           # absolute path of the prepared (downscaled) file
    width: int
    height: int
    orientation: str    # "landscape" | "portrait"
    id: str = ""              # source id (file name, Immich asset id)
    ephemeral: bool = False   # cache file owned by the playlist: deleted when it ages out
    raw: str = ""             # downloaded original/preview to delete along with it

    def to_dict(self) -> dict:
        return asdict(self)


def scan(photo_dir: Path) -> list[Path]:
    return sorted(p for p in photo_dir.iterdir() if p.suffix.lower() in EXTENSIONS)


def prepare_photo(src: str, cache_dir: str, max_w: int, max_h: int) -> Photo:
    """CPU-heavy and blocking: call via an executor. Top-level function so it can be pickled."""
    s = Path(src)
    st = s.stat()
    key = hashlib.sha1(f"{s.resolve()}:{st.st_mtime_ns}:{st.st_size}:{max_w}x{max_h}".encode()).hexdigest()[:16]
    out = Path(cache_dir) / f"{s.stem}-{key}.jpg"
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    if out.exists():
        with Image.open(out) as im:
            w, h = im.size
    else:
        with Image.open(s) as im:
            if im.format == "JPEG":
                im.draft("RGB", (max_w, max_h))              # decode at 1/2, 1/4 or 1/8 size when that is still enough
            im = ImageOps.exif_transpose(im).convert("RGB")
            im.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
            im.save(out, "JPEG", quality=88)
            w, h = im.size
    return Photo(s.name, str(out), w, h, "portrait" if h > w else "landscape")
