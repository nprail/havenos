from pathlib import Path

import pytest

from havenos.core import Core
from havenos.core.config import ImmichConfig
from havenos.core.immich import ImmichError, ImmichSource
from havenos.core.playlist import Playlist
from conftest import wait_for
from fakes import FakeImmich


def cfg_for(server, **kw):
    return ImmichConfig(url=server.url, api_key=FakeImmich.KEY, shuffle=False, **kw)


async def test_ping_and_list_filters_non_images(immich, tmp_path):
    src = ImmichSource(cfg_for(immich), tmp_path)
    assert await src.ping()
    ids = await src.list_ids()
    assert len(ids) == 10 and "video-1" not in ids
    await src.close()


async def test_album_listing(tmp_path):
    s = FakeImmich(album="alb-1")
    await s.start()
    src = ImmichSource(cfg_for(s, album_id="alb-1"), tmp_path)
    assert len(await src.list_ids()) == 4
    await src.close()
    await s.stop()


async def test_fetch_downloads_preview_once_and_caches(immich, tmp_path):
    src = ImmichSource(cfg_for(immich), tmp_path)
    p1 = await src.fetch("asset-00")
    p2 = await src.fetch("asset-00")
    assert p1 == p2 and p1.exists() and immich.downloads == ["asset-00"]
    await src.close()


async def test_bad_key_is_reported(immich, tmp_path):
    src = ImmichSource(ImmichConfig(url=immich.url, api_key="wrong"), tmp_path)
    with pytest.raises(ImmichError, match="API key"):
        await src.list_ids()
    await src.close()


async def test_playlist_bounds_the_cache_and_deletes_evicted_files(immich, make_config, tmp_path):
    cfg = make_config(history=2, prefetch=2)
    src = ImmichSource(cfg_for(immich), cfg.cache_dir)
    pl = Playlist(src, cfg)
    first = await pl.start()
    first_files = [first.path, first.raw]
    for _ in range(5):       # stays inside one pass over the 10 ids, so the first asset is not re-fetched
        await pl.advance(1)
        if pl._refill:
            await pl._refill
    assert pl.cached_count <= cfg.history + 1 + cfg.prefetch
    assert all(not __import__("pathlib").Path(f).exists() for f in first_files)     # aged out and deleted
    on_disk = list((cfg.cache_dir / "immich").glob("*.jpg"))
    assert len(on_disk) <= pl.cached_count
    await pl.close()


async def test_playlist_skips_broken_assets(immich, make_config):
    immich.broken = {"asset-00", "asset-01"}
    cfg = make_config()
    pl = Playlist(ImmichSource(cfg_for(immich), cfg.cache_dir), cfg)
    first = await pl.start()
    assert first.id == "asset-02"
    await pl.close()


async def test_swipe_back_within_history(immich, make_config):
    cfg = make_config()
    pl = Playlist(ImmichSource(cfg_for(immich), cfg.cache_dir), cfg)
    a = await pl.start()
    b = await pl.advance(1)
    assert (await pl.advance(-1)).id == a.id
    assert (await pl.advance(1)).id == b.id
    await pl.close()


async def test_core_runs_on_immich_and_recovers_when_server_comes_back(immich, make_config, clock):
    immich.broken = {a["id"] for a in immich.assets}
    core = Core(make_config(immich=cfg_for(immich)), clock=clock)
    await core.start()
    assert core.state["photo"] is None and core.state["photo_source"] == "immich"
    immich.broken = set()
    clock.advance(11)
    await core.tick()
    await core.settle()
    assert core.state["photo"]["id"].startswith("asset-")
    await core.stop()


async def test_eviction_keeps_files_still_used_by_a_duplicate_timeline_entry(immich, make_config):
    """The id list wraps, so one asset can be in history and ahead at once; evicting the old entry must not delete its file."""
    cfg = make_config(history=1, prefetch=1)
    pl = Playlist(ImmichSource(cfg_for(immich), cfg.cache_dir), cfg)
    await pl.start()
    first = pl.current
    pl._line[:] = [first, first, first, first]      # same asset several times on the timeline
    pl._cursor = 3
    pl._evict()                             # drops the original entry; the duplicates still need the files
    assert Path(first.path).exists() and Path(first.raw).exists()
    await pl.close()


async def test_start_wipes_orphaned_cache_from_earlier_runs(immich, make_config):
    cfg = make_config()
    (cfg.cache_dir / "immich").mkdir(parents=True)
    (cfg.cache_dir / "ephemeral").mkdir(parents=True)
    old_raw, old_prep = cfg.cache_dir / "immich" / "stale.jpg", cfg.cache_dir / "ephemeral" / "stale-abc.jpg"
    old_raw.write_bytes(b"x")
    old_prep.write_bytes(b"x")
    pl = Playlist(ImmichSource(cfg_for(immich), cfg.cache_dir), cfg)
    await pl.start()
    assert not old_raw.exists() and not old_prep.exists()
    await pl.close()


# ---- recency weighting ------------------------------------------------------------------------

import random
from collections import Counter
from datetime import datetime, timedelta, timezone

from havenos.core.immich import recency_weight, weighted_order

NOW = datetime(2026, 10, 29, tzinfo=timezone.utc)


def iso(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat()


def test_recency_weight_halves_per_half_life_and_respects_floor():
    assert recency_weight(iso(0), NOW, 365, 0.1) == 1.0
    assert abs(recency_weight(iso(365), NOW, 365, 0.1) - 0.5) < 1e-9
    assert recency_weight(iso(5000), NOW, 365, 0.1) == 0.1           # old photos never reach zero
    assert recency_weight(None, NOW, 365, 0.1) == 0.1                 # undated: lowest priority, still eligible
    assert recency_weight(iso(5000), NOW, 0, 0.1) == 1.0              # half_life 0 disables the preference


def test_weighted_order_prefers_recent_but_old_still_appear():
    cfg = ImmichConfig(url="x", api_key="k")
    assets = [{"id": "new", "fileCreatedAt": iso(5)}, {"id": "mid", "fileCreatedAt": iso(400)},
              {"id": "old", "fileCreatedAt": iso(3000)}]
    rng = random.Random(7)
    first = Counter(weighted_order(assets, NOW, cfg, rng)[0] for _ in range(3000))
    assert first["new"] > first["mid"] > first["old"] > 0
    assert sorted(weighted_order(assets, NOW, cfg, rng)) == ["mid", "new", "old"]    # nothing dropped


async def test_library_listing_samples_every_age_bucket(make_config, tmp_path):
    s = FakeImmich(n=24)
    await s.start()
    src = ImmichSource(ImmichConfig(url=s.url, api_key=FakeImmich.KEY, list_size=50), tmp_path,
                       rng=random.Random(1))
    ids = await src.list_ids()
    assert len(s.random_bodies) == 4                                   # one query per age bucket
    assert all("takenBefore" in b for b in s.random_bodies)
    assert "asset-00" in ids and "asset-23" in ids                      # newest and oldest both in the pool
    assert len(ids) == len(set(ids)) and "video-1" not in ids
    await src.close()
    await s.stop()


async def test_recent_photos_come_up_more_often_but_old_ones_do_too(tmp_path):
    s = FakeImmich(n=24)
    await s.start()
    src = ImmichSource(ImmichConfig(url=s.url, api_key=FakeImmich.KEY, list_size=8), tmp_path,
                       rng=random.Random(3))
    shown = Counter()
    for _ in range(150):                                                # 150 playlist passes of 8 photos
        shown.update(await src.list_ids())
    age_rank = lambda aid: int(aid.split("-")[1])                       # 0 = newest
    recent = sum(c for a, c in shown.items() if age_rank(a) < 6)
    old = sum(c for a, c in shown.items() if age_rank(a) >= 18)
    assert recent > old * 1.5 and old > 0
    await src.close()
    await s.stop()


async def test_album_mode_weights_by_recency_without_bucket_queries(tmp_path):
    s = FakeImmich(n=10, album="alb")
    await s.start()
    src = ImmichSource(ImmichConfig(url=s.url, api_key=FakeImmich.KEY, album_id="alb"), tmp_path)
    assert sorted(await src.list_ids()) == [f"asset-0{i}" for i in range(4)]
    assert s.random_bodies == []
    await src.close()
    await s.stop()
