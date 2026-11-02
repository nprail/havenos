"""AppModel bridge: core events become Qt properties/signals; slots become core commands."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication

from havenos.bridge import AppModel
from havenos.core import Config, Core


@pytest.fixture(scope="module")
def qapp():
    return QCoreApplication.instance() or QCoreApplication([])


@pytest.fixture
def model(qapp, tmp_path):
    core = Core(Config(photo_dir=tmp_path, cache_dir=tmp_path))
    return core, AppModel(core)


def test_patch_updates_property_and_emits_signal(model):
    core, m = model
    hits = []
    m.modeChanged.connect(lambda: hits.append(1))
    core.handle("mode.set", mode="dashboard")
    assert m.mode == "dashboard" and hits == [1]


def test_snapshot_populates_photo_url(model, tmp_path):
    core, m = model
    core.state["photo"] = {"path": str(tmp_path / "a b.jpg"), "name": "a b.jpg"}
    core.emit_snapshot()
    assert m.photo["url"].startswith("file:///") and "a%20b.jpg" in m.photo["url"]


def test_slots_forward_commands(model):
    core, m = model
    m.addTimer(5, "Tea")
    assert core.state["timers"][-1]["label"] == "Tea"
    m.setBlur(False)
    assert m.blur is False


def test_stats_event(model):
    core, m = model
    core.bus.emit("stats", rss_mb=123.0, lag_worst_ms=4.5, lag_slow=0)
    assert m.rssMb == 123.0 and m.lagWorstMs == 4.5


async def test_music_state_reaches_qt_and_commands_flow_back(qapp, tmp_path):
    core = Core(Config(photo_dir=tmp_path, cache_dir=tmp_path, music_demo=True))
    m = AppModel(core)
    hits = []
    m.musicChanged.connect(lambda: hits.append(1))
    assert m.music["active_source"] is None
    core.handle("music.simulate", source="spotify", action="play")
    assert hits and m.music["active_source"] == "spotify" and m.music["track"]["title"] == "Northern Lines"
    core.handle("music.simulate", source="airplay", action="play")
    assert m.music["active_source"] == "airplay" and m.music["source_label"] == "AirPlay"
