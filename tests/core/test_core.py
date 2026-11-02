import asyncio
import os

from havenos.core.photos import prepare_photo
from conftest import instant_sleep, wait_for
from havenos.core import Core


def events(core):
    seen = []
    core.bus.subscribe(seen.append)
    return seen


async def test_start_loads_first_photo_downscaled_and_demo_data(core):
    photo = core.state["photo"]
    assert max(photo["width"], photo["height"]) <= 1920 and photo["orientation"] == "landscape"
    assert core.state["timers"][0]["label"] == "Pasta"
    assert core.state["ha_status"] == "demo" and core.state["weather"]["temp"] == 72
    assert core.state["room"] == {"id": "living_room", "name": "Living Room"}
    assert len(core.state["controls"]) == 6 and len(core.state["rooms"]) == 4


async def test_photo_cache_is_reused(tmp_path, photo_dir):
    src = str(sorted(photo_dir.iterdir())[0])
    first = prepare_photo(src, str(tmp_path / "c"), 1920, 1200)
    m1 = os.stat(first.path).st_mtime_ns
    second = prepare_photo(src, str(tmp_path / "c"), 1920, 1200)
    assert second.path == first.path and os.stat(second.path).st_mtime_ns == m1


async def test_photo_cycles_on_interval_and_wraps(core, clock):
    names = [core.state["photo"]["name"]]
    for _ in range(3):
        clock.advance(8.1)
        await core.tick()
        await core.settle()
        names.append(core.state["photo"]["name"])
    assert names == ["00.jpg", "01.jpg", "02.jpg", "00.jpg"]    # wrapped


async def test_manual_photo_change_restarts_cycle(core, clock):
    clock.advance(7)
    core.handle("photo.next", delta=1)
    await core.settle()
    clock.advance(7)
    await core.tick()
    await core.settle()
    assert core.state["photo"]["name"] == "01.jpg"    # auto-advance did not also fire


async def test_swipe_back_returns_to_previous_photo(core):
    core.handle("photo.next", delta=1)
    await core.settle()
    core.handle("photo.next", delta=-1)
    await core.settle()
    assert core.state["photo"]["name"] == "00.jpg"


async def test_patch_only_emitted_on_change(core):
    seen = events(core)
    core.handle("mode.set", mode="dashboard")
    core.handle("mode.set", mode="dashboard")
    patches = [e for e in seen if e.type == "state.patch" and "mode" in e.data["patch"]]
    assert len(patches) == 1


async def test_dashboard_returns_to_ambient_after_idle_and_activity_resets(core, clock):
    core.handle("mode.set", mode="dashboard")
    clock.advance(20)
    core.handle("ui.activity")
    clock.advance(20)
    await core.tick()
    assert core.state["mode"] == "dashboard"      # activity pushed the deadline out
    clock.advance(11)
    await core.tick()
    assert core.state["mode"] == "ambient"


async def test_timer_expiry_rings_then_auto_dismisses(core, clock):
    core.handle("timer.start", seconds=5, label="Tea")
    clock.advance(6)
    await core.tick()
    assert core.state["ringing"]["label"] == "Tea"
    assert all(t["label"] != "Tea" for t in core.state["timers"])
    clock.advance(31)
    await core.tick()
    assert core.state["ringing"] is None


async def test_snooze_creates_new_timer(core, clock):
    core.handle("timer.start", seconds=5, label="Tea")
    clock.advance(6)
    await core.tick()
    core.handle("timer.snooze", seconds=60)
    assert core.state["ringing"] is None
    snoozed = [t for t in core.state["timers"] if t["label"] == "Tea"]
    assert len(snoozed) == 1 and snoozed[0]["total"] == 60


async def test_demo_control_tile_toggles_through_the_real_action_path(core):
    tile = lambda: next(c for c in core.state["controls"] if c["id"] == "light.living_room_ceiling")
    assert tile()["on"] is False
    core.handle("control.toggle", id="light.living_room_ceiling")
    await wait_for(lambda: tile()["on"])


async def test_demo_media_toggle(core):
    core.handle("media.toggle")
    await wait_for(lambda: core.state["media"] and core.state["media"]["playing"] is True)


async def test_cancel_timer(core):
    tid = core.state["timers"][0]["id"]
    core.handle("timer.cancel", id=tid)
    assert core.state["timers"] == []


async def test_voice_sequence_runs_to_idle(core):
    core.handle("voice.start")
    seen_states = []
    core.bus.subscribe(lambda e: e.type == "state.patch" and "voice" in e.data["patch"]
                       and seen_states.append(e.data["patch"]["voice"]))
    for _ in range(50):
        await asyncio.sleep(0)
    assert seen_states == ["listening", "processing", "responding", "idle"]
    assert core.state["response"].startswith("Okay")


async def test_voice_stop_cancels(core):
    core.handle("voice.start")
    core.handle("voice.stop")
    for _ in range(20):
        await asyncio.sleep(0)
    assert core.state["voice"] == "idle"


async def test_unknown_command_reports_error(core):
    seen = events(core)
    core.handle("nope.nothing")
    assert seen[-1].type == "error"


async def test_event_seq_is_monotonic(core):
    seen = events(core)
    core.handle("music.toggle")
    core.handle("music.toggle")
    assert [e.seq for e in seen] == sorted(e.seq for e in seen)


async def test_music_takeover_through_the_core(make_config, clock):
    c = Core(make_config(music_demo=True), clock=clock, sleep=instant_sleep)
    await c.start()
    c.handle("music.simulate", source="spotify", action="play")
    assert c.state["music"]["active_source"] == "spotify" and c.state["music"]["status"] == "playing"
    c.handle("music.simulate", source="airplay", action="play")
    await c.settle()
    assert c.state["music"]["active_source"] == "airplay"
    c.handle("music.command", name="toggle")
    await c.settle()
    assert c.state["music"]["status"] == "paused"
    clock.advance(c.config.music_idle_s + 1)
    await c.tick()
    assert c.state["music"]["active_source"] is None
    await c.settle()
    await c.stop()


async def test_music_simulation_is_off_outside_demo_mode(core):
    core.handle("music.simulate", source="spotify", action="play")
    assert core.state["music"]["active_source"] is None


# ---- music library and ducking ----

async def test_library_commands_browse_search_and_play(make_config, clock):
    c = Core(make_config(music_demo=True), clock=clock, sleep=instant_sleep)
    await c.start()
    assert c.state["library"]["available"] is True
    c.handle("library.open")
    await wait_for(lambda: c.state["library"]["sections"])
    assert [s["title"] for s in c.state["library"]["sections"]] == ["Playlists", "Albums"]
    c.handle("library.search", query="signal")
    await wait_for(lambda: c.state["library"]["query"] == "signal" and not c.state["library"]["busy"])
    row = c.state["library"]["sections"][0]["items"][0]
    assert row["name"] == "Signal Fires"
    c.handle("library.search", query="zzzz")
    await wait_for(lambda: c.state["library"]["error"] == "Nothing found")
    c.handle("library.search", query="signal")
    await wait_for(lambda: c.state["library"]["sections"])
    c.handle("library.play", uri=row["uri"])
    await wait_for(lambda: c.state["music"]["status"] == "playing")
    assert c.state["music"]["track"]["title"] == "Signal Fires"            # the library only asks; a source starting is what plays
    await c.stop()


async def test_library_is_unavailable_without_music_assistant(core):
    assert core.state["library"]["available"] is False
    core.handle("library.open")
    core.handle("library.play", uri="x")
    assert core.state["library"]["sections"] == []


async def test_announcements_and_timers_duck_the_music(core):
    ducks = []
    core.music.duck = ducks.append
    core.handle("announce.show", message="Dinner", kind="info", seconds=5)
    assert ducks[-1] is True
    core.handle("announce.dismiss")
    assert ducks[-1] is False


async def test_the_display_can_pause_resume_and_extend_its_own_timers(core, clock):
    core.handle("timer.start", seconds=100, label="Tea")
    tid = next(t["id"] for t in core.state["timers"] if t["label"] == "Tea")
    get = lambda: next(t for t in core.state["timers"] if t["id"] == tid)
    clock.advance(40)
    core.handle("timer.pause", id=tid)
    assert get()["paused"] and get()["left"] == 60 and get()["local"] is True
    clock.advance(150)                                            # (the demo Pasta timer still has 80 s)
    await core.tick()
    assert core.state["ringing"] is None                          # a paused timer never rings
    core.handle("timer.extend", id=tid, seconds=60)
    assert get()["left"] == 120 and get()["total"] == 160
    core.handle("timer.resume", id=tid)
    assert not get()["paused"] and get()["end"] == int(clock() * 1000) + 120_000


async def test_voice_timers_can_be_cancelled_on_the_display_but_not_paused_or_extended(core, clock):
    core.handle("voice.timer", kind=0, ha_id="t1", name="Eggs", total=600, left=600)
    t = next(t for t in core.state["timers"] if t["label"] == "Eggs")
    assert t["local"] is False
    before = dict(t)
    for cmd in ("timer.pause", "timer.extend", "timer.resume"):
        core.handle(cmd, id=t["id"], **({"seconds": 60} if cmd == "timer.extend" else {}))
    assert next(x for x in core.state["timers"] if x["id"] == t["id"]) == before          # untouched: HA keeps the clock
    core.handle("timer.cancel", id=t["id"])
    assert not any(x["label"] == "Eggs" for x in core.state["timers"])
    core.handle("voice.timer", kind=3, ha_id="t1", name="Eggs", total=600, left=0)       # HA's late "finished" is ignored
    await core.tick()
    assert core.state["ringing"] is None
