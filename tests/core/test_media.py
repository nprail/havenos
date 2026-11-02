"""MediaCoordinator: the takeover rules of docs/specs/07-music-pipeline.md section 4."""
import pytest

from conftest import FakeClock
from havenos.core.media import MediaCoordinator
from havenos.core.media.sources.base import Availability, Metadata, Pairing, Playback, Position
from havenos.core.media.sources.fake import FakeSource


class Harness:
    def __init__(self, clock: FakeClock, **kw) -> None:
        self.states: list[dict] = []
        self.feeds: list = []
        self.notes: list = []
        self.co = MediaCoordinator(lambda **ch: self.states.append(ch["music"]), clock=clock,
                                   select_feed=self.feeds.append, notify=lambda m, t: self.notes.append((t, m)), **kw)
        self.a = FakeSource("airplay", "AirPlay")
        self.s = FakeSource("spotify", "Spotify")
        self.x = FakeSource("sendspin", "Sendspin")
        for src in (self.a, self.s, self.x):
            self.co.register(src)

    @property
    def now(self) -> dict:
        return self.co.state()


@pytest.fixture
async def h(clock):
    h = Harness(clock)
    await h.co.start()
    yield h
    await h.co.stop()


async def test_idle_until_something_plays(h):
    h.s.connect("Nick's iPhone")
    h.s.emit(Metadata("A", "B"))
    await h.co.settle()
    assert h.now["active_source"] is None and h.now["status"] == "idle"
    assert h.now["sources"]["spotify"]["client"] == "Nick's iPhone"        # connecting alone takes nothing


async def test_playing_takes_the_slot_and_shows_its_metadata(h):
    h.s.play()
    assert h.now["active_source"] == "spotify" and h.now["status"] == "playing"
    assert h.now["track"]["title"] == "Northern Lines"                      # metadata that arrived before "playing"
    assert h.now["source_label"] == "Spotify" and h.feeds == ["spotify"]


async def test_new_source_takes_over_and_evicts_the_old_one(h):
    h.s.play()
    h.a.play()
    await h.co.settle()
    assert h.now["active_source"] == "airplay" and h.now["track"]["title"] == "Slow Light"
    assert h.s.released == 1 and h.a.released == 0
    assert h.feeds == ["spotify", "airplay"]
    assert h.co.takeovers == [(None, "spotify"), ("spotify", "airplay")]


async def test_only_one_source_is_ever_shown_active(h):
    for src in (h.s, h.a, h.x, h.s):
        src.play()
        await h.co.settle()
        assert h.now["active_source"] == src.id


async def test_active_is_set_before_the_old_source_is_released(h):
    seen = []
    orig = h.s.release

    async def spy():
        seen.append(h.co.active)
        await orig()
    h.s.release = spy
    h.s.play()
    h.a.play()
    await h.co.settle()
    assert seen == ["airplay"]


async def test_stale_events_from_the_evicted_source_do_not_flip_control_back(h):
    h.s.release_pauses = False                  # a sender that keeps saying "playing" after we evicted it
    h.s.play()
    h.a.play()
    await h.co.settle()
    h.s.emit(Playback("playing"))               # laggy echo
    h.s.emit(Metadata("Old", "Old"))
    await h.co.settle()
    assert h.now["active_source"] == "airplay" and h.now["track"]["title"] == "Slow Light"
    assert h.s.released == 1


async def test_evicted_source_can_take_back_after_it_settles(h):
    h.s.play()
    h.a.play()
    await h.co.settle()                         # spotify reports paused (the polite release)
    h.s.play()                                  # the user presses play in the Spotify app again
    await h.co.settle()
    assert h.now["active_source"] == "spotify" and h.a.released == 1


async def test_ignoring_expires_so_a_real_restart_is_not_lost(h, clock):
    h.s.release_pauses = False
    h.s.play()
    h.a.play()
    await h.co.settle()
    clock.advance(h.co.echo_window_s + 0.1)
    h.s.emit(Playback("playing"))
    await h.co.settle()
    assert h.now["active_source"] == "spotify"


async def test_inactive_sources_are_inert(h):
    h.s.play()
    h.a.connect("Mac")
    h.a.emit(Metadata("Quiet", "Quiet"))
    h.a.emit(Playback("paused"))
    await h.co.settle()
    assert h.now["active_source"] == "spotify" and h.now["track"]["title"] == "Northern Lines"
    assert h.a.released == 0 and h.s.released == 0


async def test_pause_keeps_the_slot_and_resumes(h):
    h.s.play()
    h.s.pause()
    assert h.now["active_source"] == "spotify" and h.now["status"] == "paused"
    h.s.emit(Playback("playing"))
    assert h.now["status"] == "playing" and h.s.released == 0


async def test_paused_slot_clears_after_the_idle_timeout(clock):
    h = Harness(clock, idle_timeout_s=60)
    await h.co.start()
    h.s.play()
    h.s.pause()
    clock.advance(59)
    h.co.tick()
    assert h.now["active_source"] == "spotify"
    clock.advance(2)
    h.co.tick()
    assert h.now["active_source"] is None and h.feeds[-1] is None
    await h.co.stop()


async def test_resuming_cancels_the_idle_timeout(clock):
    h = Harness(clock, idle_timeout_s=60)
    await h.co.start()
    h.s.play()
    h.s.pause()
    clock.advance(30)
    h.s.emit(Playback("playing"))
    clock.advance(600)
    h.co.tick()
    assert h.now["active_source"] == "spotify"
    await h.co.stop()


async def test_session_end_clears_the_active_source_without_resuming_the_previous(h):
    h.s.play()
    h.a.play()
    await h.co.settle()
    h.a.disconnect()
    await h.co.settle()
    assert h.now["active_source"] is None and h.now["status"] == "idle"     # spotify is NOT resumed (decided)
    assert h.s.calls == []


async def test_source_going_unavailable_frees_the_slot(h):
    h.s.play()
    h.s.emit(Availability(False))
    assert h.now["active_source"] is None and h.now["sources"]["spotify"]["available"] is False


async def test_position_freezes_on_pause_and_extrapolates_from_its_anchor(h, clock):
    h.s.play(position=10.0)
    clock.advance(5)
    h.s.pause()
    st = h.now
    assert st["position"] == pytest.approx(15.0) and st["status"] == "paused"
    clock.advance(100)
    assert h.now["position"] == pytest.approx(15.0)                          # paused: nothing moves


async def test_new_track_restarts_position(h, clock):
    h.s.play(position=50)
    h.s.emit(Metadata("Next one", "X"))
    assert h.now["position"] == 0.0


# ---- commands ----------------------------------------------------------------------------------------------------------

async def test_commands_go_to_the_active_source_only(h):
    h.s.play()
    h.a.connect()
    assert await h.co.command("next") is True
    assert h.s.calls == [("next", {})] and h.a.calls == []


async def test_toggle_pauses_then_plays(h):
    h.s.play()
    await h.co.command("toggle")
    assert h.now["status"] == "paused"
    await h.co.command("toggle")
    assert h.now["status"] == "playing"
    assert [c[0] for c in h.s.calls] == ["pause", "play"]


async def test_commands_the_source_cannot_do_are_refused(clock):
    h = Harness(clock)
    h.a.commands = frozenset({"play", "pause", "next", "prev"})              # AirPlay: no seek
    await h.co.start()
    h.a.play()
    assert await h.co.command("seek", seconds=30) is False
    assert h.a.calls == []
    assert "seek" not in h.now["capabilities"]
    await h.co.stop()


async def test_command_with_nothing_active_is_a_noop(h):
    assert await h.co.command("pause") is False


async def test_volume_is_the_device_master_and_is_pushed_to_the_sender(h):
    h.s.play()
    await h.co.command("volume", level=35)
    assert h.now["volume"] == 35
    assert h.s.volumes[-1] == (35, False)
    h.s.set_level(80)                                                         # sender moves its slider
    assert h.now["volume"] == 80
    h.a.set_level(10)                                                         # an inactive sender cannot
    assert h.now["volume"] == 80


async def test_a_new_active_source_gets_the_device_volume(h):
    await h.co.command("volume", level=20)
    h.s.play()
    await h.co.settle()
    h.a.play()
    await h.co.settle()
    assert h.s.volumes[-1] == (20, False) and h.a.volumes[-1] == (20, False)


async def test_stop_releases_the_slot(h):
    h.s.play()
    assert await h.co.command("stop") is True
    assert h.now["active_source"] is None and h.s.released == 1 and h.feeds[-1] is None


async def test_pairing_code_is_announced(h):
    h.x.emit(Pairing("123-456"))
    assert h.notes and "123-456" in h.notes[0][1]
    assert h.now["sources"]["sendspin"]["pairing_code"] == "123-456"


async def test_adapter_that_fails_to_release_does_not_break_takeover(h):
    async def boom():
        raise RuntimeError("daemon gone")
    h.s.release = boom
    h.s.play()
    h.a.play()
    await h.co.settle()
    assert h.now["active_source"] == "airplay"


# ---- toast, fights, hint, ducking, art ----

async def test_takeover_leaves_a_toast_for_the_ui_but_a_first_play_does_not(h):
    h.s.connect("Nick's iPhone")
    h.s.play()
    assert h.now["takeover"] is None                                       # nothing was playing: the strip appearing is enough
    h.a.connect("Sam's iPad")
    h.a.play()
    t = h.now["takeover"]
    assert (t["source"], t["client"], t["from"], t["seq"]) == ("AirPlay", "Sam's iPad", "Spotify", 1)


async def test_senders_fighting_over_the_speaker_are_logged(clock, caplog):
    h = Harness(clock, fight_limit=3)
    await h.co.start()
    with caplog.at_level("WARNING"):
        for src in (h.a, h.s, h.a, h.s):
            clock.advance(5)
            src.play()
    await h.co.settle()
    assert "fighting over the speaker" in caplog.text
    await h.co.stop()


async def test_idle_hint_lists_ready_sources_only_when_enabled_and_idle(clock):
    h = Harness(clock, hint=True)
    await h.co.start()
    assert h.now["hint"] == ["AirPlay", "Spotify", "Sendspin"]
    h.s.play()
    assert h.now["hint"] == []
    await h.co.stop()
    off = Harness(clock)
    await off.co.start()
    assert off.now["hint"] == []
    await off.co.stop()


async def test_duck_reaches_every_sink_once_per_change(h):
    class Sink:
        def __init__(self): self.calls = []
        def set_duck(self, db): self.calls.append(db)
    sinks = {}
    for src in (h.a, h.s):
        src.audio_sink = sinks[src.id] = Sink()
    h.co.duck_db = -18
    h.co.duck(True); h.co.duck(True)
    h.co.duck(False)
    assert sinks["airplay"].calls == [-18, None] and sinks["spotify"].calls == [-18, None]


async def test_track_art_goes_through_the_art_resolver(clock):
    seen = []
    h = Harness(clock, art=lambda uri: seen.append(uri) or "file:///cache/x.jpg")
    await h.co.start()
    h.s.play(Metadata("T", "A", "", "http://x/c.jpg", 10.0))
    assert h.now["track"]["art_uri"] == "file:///cache/x.jpg" and set(seen) == {"http://x/c.jpg"}
    await h.co.stop()
