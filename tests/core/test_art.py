import asyncio
import io

from PIL import Image

from conftest import wait_for
from havenos.core.media.art import ArtCache


def jpg(size=(1200, 900)) -> bytes:
    b = io.BytesIO()
    Image.new("RGB", size, (200, 40, 40)).save(b, "JPEG")
    return b.getvalue()


async def test_remote_art_downloads_resizes_and_notifies(tmp_path):
    ready, fetched = [], []

    async def fetch(uri):
        fetched.append(uri)
        return jpg()
    art = ArtCache(tmp_path / "art", fetch=fetch, on_ready=lambda: ready.append(1))
    assert art.resolve("http://x/c.jpg") == ""                          # not there yet; the download is under way
    assert art.resolve("http://x/c.jpg") == ""                          # and is not started twice
    await wait_for(lambda: ready)
    uri = art.resolve("http://x/c.jpg")
    assert uri.startswith("file://") and fetched == ["http://x/c.jpg"]
    with Image.open(uri.removeprefix("file://")) as im:
        assert max(im.size) == 512
    await art.close()


async def test_local_paths_pass_through_and_junk_is_ignored(tmp_path):
    art = ArtCache(tmp_path)
    assert art.resolve("") == "" and art.resolve("nonsense") == ""
    assert art.resolve("file:///a/b.jpg") == "file:///a/b.jpg" and art.resolve("/a/b.jpg") == "file:///a/b.jpg"


async def test_failed_download_is_not_retried_in_a_loop(tmp_path):
    calls = []

    async def fetch(uri):
        calls.append(uri)
        raise OSError("down")
    art = ArtCache(tmp_path, fetch=fetch)
    art.resolve("http://x/bad.jpg")
    await wait_for(lambda: calls)
    await asyncio.sleep(0.05)
    art.resolve("http://x/bad.jpg")
    await asyncio.sleep(0.05)
    assert len(calls) == 1
    await art.close()


async def test_old_covers_are_pruned(tmp_path):
    async def fetch(uri):
        return jpg((40, 40))
    art = ArtCache(tmp_path / "art", fetch=fetch, max_files=3)
    for i in range(6):
        art.resolve(f"http://x/{i}.jpg")
        await wait_for(lambda i=i: art.resolve(f"http://x/{i}.jpg"))
    assert len(list((tmp_path / "art").glob("*.jpg"))) <= 3
    await art.close()
