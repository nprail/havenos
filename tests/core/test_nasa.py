import random

import pytest
from aiohttp import web

from havenos.core import Core
from havenos.core.config import Config, NasaConfig
from havenos.core.nasa import NasaError, NasaSource, parse_feed
from havenos.core.playlist import Playlist
from fakes import _start, jpeg

N = 6


def feed(base: str, n: int = N) -> str:
    items = "".join(
        f"<item><title>Image {i}</title><link>https://www.nasa.gov/image-article/{i}/</link>"
        f"<pubDate>Mon, 0{i + 1} Oct 2026 12:00:00 +0000</pubDate><description>Caption {i}</description>"
        f'<enclosure url="{base}/img/{i}.jpg" length="1" type="image/jpeg"/></item>' for i in range(n))
    items += "<item><title>No picture</title></item>"
    items += f'<item><title>Video</title><enclosure url="{base}/v/1.mp4" type="video/mp4"/></item>'
    return f'<?xml version="1.0"?><rss version="2.0"><channel>{items}</channel></rss>'


class FakeNasa:
    def __init__(self) -> None:
        self.broken: set[str] = set()
        self.feed_status = 200
        self.feed_hits = 0
        self.downloads: list[str] = []

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/feeds/iotd-feed/", self._feed)
        app.router.add_get("/img/{n}.jpg", self._img)
        self._runner, self.url = await _start(app, 0)
        self.feed_url = self.url + "/feeds/iotd-feed/"

    async def stop(self) -> None:
        await self._runner.cleanup()

    async def _feed(self, request):
        self.feed_hits += 1
        return web.Response(text=feed(self.url), status=self.feed_status, content_type="application/rss+xml")

    async def _img(self, request):
        n = request.match_info["n"]
        self.downloads.append(n)
        if n in self.broken:
            return web.Response(status=500)
        return web.Response(body=jpeg(), content_type="image/jpeg")


@pytest.fixture
async def nasa():
    s = FakeNasa()
    await s.start()
    yield s
    await s.stop()


def test_parse_feed_keeps_only_image_items():
    items = parse_feed(feed("http://x"))
    assert len(items) == N
    assert items[0].url == "http://x/img/0.jpg" and items[0].title == "Image 0"
    assert items[0].link == "https://www.nasa.gov/image-article/0/" and items[0].caption == "Caption 0"


def test_parse_feed_rejects_garbage():
    with pytest.raises(NasaError):
        parse_feed("<rss><channel>")


async def test_list_is_a_shuffle_of_the_whole_feed(nasa, tmp_path):
    src = NasaSource(NasaConfig(url=nasa.feed_url), tmp_path, rng=random.Random(1))
    a, b = await src.list_ids(), await src.list_ids()
    assert sorted(a) == sorted(b) == sorted(f"{nasa.url}/img/{i}.jpg" for i in range(N))
    assert a != b and a != sorted(a)        # random order, a fresh shuffle each pass
    await src.close()


async def test_feed_errors_surface_as_nasa_error(nasa, tmp_path):
    nasa.feed_status = 503
    src = NasaSource(NasaConfig(url=nasa.feed_url), tmp_path)
    with pytest.raises(NasaError, match="503"):
        await src.list_ids()
    await src.close()
    dead = NasaSource(NasaConfig(url="http://127.0.0.1:1/feed"), tmp_path)
    with pytest.raises(NasaError, match="could not reach"):
        await dead.list_ids()
    await dead.close()


async def test_fetch_downloads_once_and_leaves_no_partial_file(nasa, tmp_path):
    src = NasaSource(NasaConfig(url=nasa.feed_url), tmp_path)
    await src.list_ids()
    url = f"{nasa.url}/img/0.jpg"                      # not the feed's first (it is shuffled): image 3 is the broken one below
    p = await src.fetch(url)
    assert p.read_bytes() == jpeg() and await src.fetch(url) == p
    assert len(nasa.downloads) == 1
    nasa.broken.add("3")
    with pytest.raises(NasaError):
        await src.fetch(f"{nasa.url}/img/3.jpg")
    assert not list(src.dir.glob("*.part"))
    await src.close()


async def test_playlist_runs_on_nasa_and_skips_broken_images(nasa, make_config):
    nasa.broken = {"0", "1", "2"}
    cfg = make_config()
    pl = Playlist(NasaSource(NasaConfig(url=nasa.feed_url), cfg.cache_dir), cfg)
    first = await pl.start()
    assert first is not None and first.id.endswith(".jpg") and first.id not in {f"{nasa.url}/img/{i}.jpg" for i in (0, 1, 2)}
    await pl.close()


async def test_start_wipes_orphaned_downloads(nasa, make_config):
    cfg = make_config()
    stale = cfg.cache_dir / "nasa" / "stale.jpg"
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"x")
    pl = Playlist(NasaSource(NasaConfig(url=nasa.feed_url), cfg.cache_dir), cfg)
    await pl.start()
    assert not stale.exists()
    await pl.close()


async def test_core_reports_nasa_source(nasa, make_config, clock):
    core = Core(make_config(nasa=NasaConfig(url=nasa.feed_url)), clock=clock)
    await core.start()
    assert core.state["photo_source"] == "nasa" and core.state["photo"] is not None
    await core.stop()


def test_nasa_is_the_default_source(tmp_path, monkeypatch):
    monkeypatch.setenv("HAVENOS_CONFIG", str(tmp_path / "missing.toml"))
    for k in ("HAVENOS_IMMICH_URL", "HAVENOS_IMMICH_KEY", "HAVENOS_PHOTO_SOURCE"):
        monkeypatch.delenv(k, raising=False)
    c = Config.from_env(tmp_path)
    assert c.photo_source == "nasa" and c.nasa and c.nasa.url.startswith("https://www.nasa.gov/")
    monkeypatch.setenv("HAVENOS_PHOTO_SOURCE", "local")
    c = Config.from_env(tmp_path)
    assert c.photo_source == "local" and c.nasa is None


async def test_a_download_after_close_does_not_open_a_session_nobody_closes(tmp_path):
    import pytest
    from havenos.core.config import NasaConfig
    from havenos.core.nasa import NasaError, NasaSource
    src = NasaSource(NasaConfig(), tmp_path)
    await src.close()                                  # a settings change rebuilt the photo source...
    with pytest.raises(NasaError):
        await src._http()                              # ...while a fetch of the old one was still running
    assert src._session is None


def _noisy_jpeg(path, size, fmt="JPEG"):
    import os
    from PIL import Image
    Image.frombytes("RGB", size, os.urandom(size[0] * size[1] * 3)).save(path, fmt, quality=95)      # incompressible, like a big original


def test_shrink_turns_a_huge_original_into_a_screen_sized_jpeg(tmp_path):
    from PIL import Image
    from havenos.core.nasa import MAX_EDGE, shrink
    src, dst = tmp_path / "big.part", tmp_path / "big.jpg"
    _noisy_jpeg(src, (3000, 2000))
    before = src.stat().st_size
    shrink(src, dst)
    assert not src.exists() and dst.exists()
    with Image.open(dst) as im:
        assert max(im.size) == MAX_EDGE and im.format == "JPEG" and im.size[0] / im.size[1] == pytest.approx(1.5, abs=0.01)
    assert dst.stat().st_size < before / 2


def test_shrink_keeps_small_jpegs_and_unreadable_files_as_they_are(tmp_path):
    from havenos.core.nasa import shrink
    small, junk = tmp_path / "s.part", tmp_path / "j.part"
    small.write_bytes(jpeg())
    junk.write_bytes(b"not an image")
    shrink(small, tmp_path / "s.jpg")
    shrink(junk, tmp_path / "j.jpg")
    assert (tmp_path / "s.jpg").read_bytes() == jpeg() and (tmp_path / "j.jpg").read_bytes() == b"not an image"


def test_shrink_converts_other_formats_to_jpeg(tmp_path):
    from PIL import Image
    from havenos.core.nasa import shrink
    src, dst = tmp_path / "p.part", tmp_path / "p.jpg"
    _noisy_jpeg(src, (2400, 1600), "PNG")
    shrink(src, dst)
    with Image.open(dst) as im:
        assert im.format == "JPEG" and max(im.size) == 1920
