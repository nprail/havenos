import asyncio
import tomllib
from pathlib import Path

import pytest
from aioesphomeapi import APIClient

from havenos.core import Config, Core
from havenos.core import settings as st
from havenos.core.esphome import ESPHomeDevice
from havenos.core.persist import SettingsPersister
from conftest import wait_for, instant_sleep


@pytest.fixture
async def rig(make_config, tmp_path):
    cfg_path = tmp_path / "cfg" / "config.toml"
    core = Core(make_config(config_path=cfg_path), sleep=instant_sleep)
    await core.start()
    p = SettingsPersister(core, delay=0.05)
    p.start()
    yield core, p, cfg_path
    p.stop()
    await core.stop()


def saved(path: Path) -> dict:
    return tomllib.loads(path.read_text())


async def test_runtime_display_changes_are_saved(rig):
    core, _, path = rig
    core.handle("config.set", blur=False, photo_interval_s=20, crossfade_ms=2000)
    core.handle("brightness.set", percent=40)
    await wait_for(lambda: path.exists() and saved(path).get("display", {}).get("brightness") == 40)
    assert saved(path)["display"] == {"photo_interval_s": 20.0, "crossfade_ms": 2000, "brightness": 40, "blur": False}


async def test_moment_to_moment_state_is_not_saved(rig):
    core, p, path = rig
    core.handle("screen.set", on=False)
    core.handle("mode.set", mode="dashboard")
    await asyncio.sleep(0.2)
    assert not path.exists()                         # nothing persistable changed
    core.handle("brightness.set", percent=70)
    await wait_for(path.exists)
    assert "screen_on" not in str(saved(path)) and "mode" not in str(saved(path))


async def test_a_burst_of_changes_writes_once(rig, monkeypatch):
    core, _, path = rig
    writes = []
    real = st.write_toml
    monkeypatch.setattr(st, "write_toml", lambda p, d: (writes.append(1), real(p, d)))
    for pct in range(10, 101, 5):                    # dragging a slider in HA
        core.handle("brightness.set", percent=pct)
    await wait_for(lambda: path.exists() and saved(path)["display"]["brightness"] == 100)
    await asyncio.sleep(0.2)
    assert len(writes) == 1


async def test_unchanged_values_do_not_rewrite_the_file(rig):
    core, p, path = rig
    core.handle("brightness.set", percent=60)
    await wait_for(path.exists)
    mtime = path.stat().st_mtime_ns
    assert p.flush() is False                         # identical to what is on disk
    core.handle("brightness.set", percent=60)
    await asyncio.sleep(0.2)
    assert path.stat().st_mtime_ns == mtime


async def test_other_settings_and_comments_free_tables_are_preserved(rig):
    core, _, path = rig
    path.parent.mkdir(parents=True)
    path.write_text('[homeassistant]\nurl = "http://ha:8123"\n[esphome]\nenabled = true\n')
    core.handle("config.set", crossfade_ms=900)
    await wait_for(lambda: "crossfade_ms" in saved(path).get("display", {}))
    t = saved(path)
    assert t["homeassistant"]["url"] == "http://ha:8123" and t["esphome"]["enabled"] is True


async def test_pending_change_is_flushed_on_shutdown(make_config, tmp_path):
    path = tmp_path / "c.toml"
    core = Core(make_config(config_path=path))
    await core.start()
    p = SettingsPersister(core, delay=30)             # far longer than the test
    p.start()
    core.handle("brightness.set", percent=25)
    p.stop()
    assert saved(path)["display"]["brightness"] == 25
    await core.stop()


async def test_saved_values_come_back_after_a_restart(rig, monkeypatch):
    core, p, path = rig
    core.handle("config.set", photo_interval_s=33, crossfade_ms=700, blur=False)
    core.handle("brightness.set", percent=55)
    await wait_for(lambda: path.exists() and saved(path)["display"].get("brightness") == 55)
    monkeypatch.setenv("HAVENOS_CONFIG", str(path))
    for k in ("HAVENOS_INTERVAL", "HAVENOS_CROSSFADE", "HAVENOS_BLUR", "HAVENOS_BRIGHTNESS"):
        monkeypatch.delenv(k, raising=False)
    cfg = Config.from_env(Path("/assets"))
    assert (cfg.photo_interval_s, cfg.crossfade_ms, cfg.blur, cfg.brightness) == (33.0, 700, False, 55)
    reborn = Core(cfg)
    assert reborn.state["brightness"] == 55 and reborn.state["crossfade_ms"] == 700


async def test_unwritable_location_does_not_crash(make_config, tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, so a directory cannot be created under it")
    core = Core(make_config(config_path=blocker / "config.toml"))
    await core.start()
    p = SettingsPersister(core, delay=0.01)
    p.start()
    core.handle("brightness.set", percent=30)
    await asyncio.sleep(0.1)
    assert core.state["brightness"] == 30             # still running; the failure was only logged
    p.stop()
    await core.stop()


async def test_changes_made_in_home_assistant_persist(make_config, tmp_path):
    """The real path: an HA entity changes -> ESPHome command -> core -> config.toml."""
    path = tmp_path / "cfg" / "config.toml"
    core = Core(make_config(config_path=path))
    await core.start()
    p = SettingsPersister(core, delay=0.05)
    p.start()
    dev = ESPHomeDevice(core, name="havenos-test", port=0, host="127.0.0.1", mac="AA:BB:CC:DD:EE:01", advertise=False)
    await dev.start()
    client = APIClient("127.0.0.1", dev.port, None)
    await client.connect(login=True)
    ents, _ = await client.list_entities_services()
    by = {e.object_id: e for e in ents}
    client.number_command(by["photo_interval"].key, 45)
    client.number_command(by["brightness"].key, 65)
    client.number_command(by["crossfade"].key, 2500)
    client.switch_command(by["blur"].key, False)
    await wait_for(lambda: path.exists() and saved(path)["display"] == {
        "photo_interval_s": 45.0, "crossfade_ms": 2500, "brightness": 65, "blur": False})
    await client.disconnect()
    await dev.stop()
    p.stop()
    await core.stop()
