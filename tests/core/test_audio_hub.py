"""The shared mixer, its streams and the sinks music sources write to (no sound device needed)."""
import numpy as np
import pytest

from havenos.core.audio import mixer as mx
from havenos.core.audio.output import AudioHub, BusSink, candidates

RATE = 48000


class Fmt:
    def __init__(self, rate=RATE, channels=2, depth=16):
        self.pcm_format = type("P", (), {"sample_rate": rate, "channels": channels, "bit_depth": depth})


def pcm(value: int, frames: int, channels: int = 2) -> bytes:
    return np.full(frames * channels, value, dtype=np.int16).tobytes()


def pull(hub: AudioHub, frames: int) -> np.ndarray:
    return np.frombuffer(hub.mixer.read(frames), dtype=np.int16)


@pytest.fixture
def hub():
    return AudioHub(RATE, mode="null", volume=1.0)


def unity(h):                           # the master gain is the VPE's 0.85 cap; the tests compare against it
    return h.mixer.gain


def near(out, want, tol=2):
    return (np.abs(np.asarray(out, dtype=int) - int(want)) <= tol).all()


def test_silent_until_prebuffered_then_plays_in_order(hub):
    s = hub.open(RATE, prebuffer_ms=100)
    s.set_volume(100, False)
    s.write(0, pcm(10000, 2000), Fmt())                 # 2000 frames < 100 ms (4800): still buffering
    assert not pull(hub, 100).any()
    s.write(0, pcm(20000, 4000), Fmt())
    out = pull(hub, 100)
    assert near(out[:200], 10000 * unity(hub))                   # first chunk first


def test_underrun_rebuffers_instead_of_stuttering(hub):
    s = hub.open(RATE, prebuffer_ms=10)
    s.write(0, pcm(5000, 600), Fmt())
    assert pull(hub, 600).any()
    assert not pull(hub, 100).any()                     # ran dry: silence, and it waits for more audio
    s.write(0, pcm(5000, 100), Fmt())
    assert not pull(hub, 100).any()                     # below the prebuffer again


def test_volume_curve_and_mute(hub):
    s = hub.open(RATE, prebuffer_ms=0)
    s.write(0, pcm(10000, 4000), Fmt())
    s.set_volume(50, False)
    assert abs(int(pull(hub, 100)[0]) - int(10000 * 0.5 ** 1.5 * unity(hub))) <= 2
    s.set_volume(50, True)
    assert not pull(hub, 100).any()


def test_clear_drops_buffered_audio_and_buffered_ms_reports_it(hub):
    s = hub.open(RATE, prebuffer_ms=10)
    s.write(0, pcm(1, 4800), Fmt())
    assert s.buffered_ms() == pytest.approx(100)
    s.clear()
    assert s.buffered_ms() == 0 and not pull(hub, 100).any()


def test_a_source_clearing_its_own_audio_does_not_touch_the_one_that_took_over(hub):
    old, new = hub.open(RATE, 0), hub.open(RATE, 0)
    old.write(0, pcm(3000, 2400), Fmt())
    new.write(0, pcm(9000, 4800), Fmt())                # the new source starts while the old one's tail is still queued
    old.clear()                                         # ...and the evicted source cleans up late
    out = pull(hub, 100)
    assert near(out, 9000 * unity(hub))                                    # only the new source is heard
    assert new.buffered_ms() == pytest.approx(100 - 100 / 48 * 48 / 48, abs=2) or new.buffered_ms() > 90


def test_both_sources_are_heard_until_one_is_cleared(hub):
    a, b = hub.open(RATE, 0), hub.open(RATE, 0)
    a.write(0, pcm(1000, 480), Fmt())
    b.write(0, pcm(2000, 480), Fmt())
    assert near(pull(hub, 100), 3000 * unity(hub))          # the short overlap of an old tail and a new start


def test_odd_formats_are_handled(hub):
    s = hub.open(RATE, 0)
    s.write(0, pcm(1, 4000), Fmt(depth=24))             # not 16-bit: dropped
    assert s.buffered_ms() == 0
    s.write(0, pcm(1, 4000, 1), Fmt(channels=6))
    assert s.buffered_ms() == 0
    mono = hub.open(RATE, 0)
    mono.write(0, pcm(5000, 480, 1), Fmt(channels=1))   # mono is copied to both sides
    out = pull(hub, 480).reshape(-1, 2)
    assert (out[:, 0] == out[:, 1]).all() and near(out[0, 0], 5000 * unity(hub))


def test_a_44_1k_source_is_resampled_to_the_mixer_rate(hub):
    s = hub.open(44100, 0)
    t = np.arange(44100) / 44100
    tone = np.repeat((np.sin(2 * np.pi * 1000 * t) * 12000).astype(np.int16), 2).tobytes()
    s.write(0, tone, None)                              # sources without a format object use the sink's rate
    assert s.buffered_ms() == pytest.approx(1000, abs=5)
    out = pull(hub, 24000).reshape(-1, 2)[:, 0].astype(float)
    peak = np.abs(out[2000:]).max()
    assert peak == pytest.approx(12000 * unity(hub), rel=0.03)


def test_a_sink_follows_a_source_that_changes_rate(hub):
    s = hub.open(RATE, 0)
    s.write(0, pcm(1000, 4800), Fmt(rate=RATE))
    s.write(0, pcm(1000, 4410), Fmt(rate=44100))        # Sendspin switching tracks: the old audio is dropped, the new converted
    assert s.buffered_ms() == pytest.approx(100, abs=3)


def test_lite_hub_converts_down_to_16k():
    h = AudioHub(16000, mode="null")
    s = h.open(48000, 0)
    s.write(0, pcm(8000, 4800), None)                   # 100 ms at 48 kHz
    assert s.buffered_ms() == pytest.approx(100, abs=3)


def test_duck_drops_at_once_and_restores_over_a_second(hub):
    s = hub.open(RATE, 0)
    s.write(0, pcm(10000, RATE * 4), Fmt())
    s.set_duck(-20)
    first = pull(hub, 100)
    assert abs(int(first[0]) - 1000 * unity(hub)) <= 2                 # -20 dB = x0.1, immediately
    s.set_duck(None)
    got = [pull(hub, 4800)[-1] for _ in range(10)]                     # ten 100 ms blocks: ramping up
    assert got == sorted(got) and got[0] > 1000 * unity(hub)
    assert abs(int(pull(hub, 4800)[-1]) - 10000 * unity(hub)) <= 3     # restored after 1 s


def test_duck_depth_follows_the_configured_db():
    h = AudioHub(RATE, mode="null", duck_db=-10.0)
    s = h.open(RATE, 0)
    s.write(0, pcm(10000, 4800), Fmt())
    s.set_duck(-10.0)
    assert abs(int(pull(h, 100)[0]) - 10000 * 10 ** -0.5 * h.mixer.gain) <= 3


def test_voice_announce_audio_is_not_ducked_but_mixes_over_music(hub):
    s = hub.open(RATE, 0)
    s.write(0, pcm(10000, RATE), Fmt())
    hub.mixer.write("announce", pcm(4000, 4800, 1), 1)
    s.set_duck(-20)
    out = pull(hub, 100)
    assert abs(int(out[0]) - int((4000 + 1000) * unity(hub))) <= 3


def test_closing_a_sink_removes_its_stream_and_stopping_the_hub_closes_all(hub):
    a, b = hub.open(RATE, 0), hub.open(RATE, 0)
    a.write(0, pcm(1, 100), Fmt())
    a.close()
    assert not pull(hub, 100).any()
    hub.stop()
    assert hub._sinks == [] and not hub.started


async def test_null_and_capture_modes_pull_the_mixer():
    h = AudioHub(RATE, mode="capture")
    h.start()
    try:
        s = h.open(RATE, 0)
        s.write(0, pcm(8000, 4800), Fmt())
        import asyncio
        await asyncio.sleep(0.2)
        assert len(h.captured) >= 4800 * 4 and s.buffered_ms() == 0
    finally:
        h.stop()


class FakeSD:
    class _D(dict):
        pass

    def __init__(self, devices, default):
        self.devices, self.default = devices, default

    def query_devices(self, device=None, kind=None):
        if kind == "output":
            return self.devices[self.default]
        return self.devices


def dev(name, out):
    return {"name": name, "max_output_channels": out}


def test_device_selection():
    sd = FakeSD([dev("Headset (call mode)", 1), dev("reSpeaker XVF3800", 2), dev("MacBook Speakers", 2)], default=0)
    assert candidates(sd, "respeaker") == [1]                           # a named device is the only candidate
    assert candidates(sd, None) == [1, 2]                               # the default is mono: skip it
    sd.default = 2
    assert candidates(sd, None) == [None, 1, 2]                         # a stereo default goes first
    with pytest.raises(RuntimeError):
        candidates(sd, "nonexistent")
    assert candidates(sd, 5) == [5]


# ---- how the core wires it ---------------------------------------------------------------------------------------------

from conftest import instant_sleep
from havenos.core import Core
from havenos.core.media.sources.fake import FakeSource
from havenos.core.voice.audio import LocalAudio
from havenos.core.voice.profiles import LITE


async def test_the_hub_runs_at_the_voice_profiles_rate(make_config, clock):
    for profile, rate in (("lite", 16000), ("xvf3800", 48000), ("default", 48000)):
        core = Core(make_config(voice_enabled=True, voice_profile=profile), clock=clock, sleep=instant_sleep)
        assert core.audio_hub().rate == rate and core.audio_hub() is core.audio_hub()
    core = Core(make_config(voice_enabled=True, voice_profile="nonsense"), clock=clock, sleep=instant_sleep)    # logged, not fatal
    assert core.audio_hub().rate == 48000
    core = Core(make_config(), clock=clock, sleep=instant_sleep)
    assert core.audio_hub().rate == 48000 and core.audio_hub().match is None


async def test_a_source_gets_a_sink_on_the_shared_hub_or_none_without_a_device(make_config, clock, monkeypatch):
    core = Core(make_config(), clock=clock, sleep=instant_sleep)
    core.audio_hub().mode = "null"
    sink = core._open_audio(44100, 150)
    assert isinstance(sink, BusSink) and sink.rate == 44100 and core.audio_hub().started
    core.audio_hub().stop()

    core = Core(make_config(), clock=clock, sleep=instant_sleep)

    def no_device():
        raise RuntimeError("no usable stereo output device")
    monkeypatch.setattr(core.audio_hub(), "start", no_device)
    assert core._open_audio() is None                              # the source then runs display/remote only


async def test_music_and_voice_share_one_mixer_and_voice_ducks_the_music(make_config, clock):
    core = Core(make_config(voice_enabled=True, voice_profile="lite"), clock=clock, sleep=instant_sleep)
    hub = core.audio_hub()
    hub.mode = "capture"
    voice = LocalAudio(LITE, hub=hub)
    assert voice.hub is hub and voice.mixer is hub.mixer
    music = FakeSource("spotify", "Spotify")
    sink = core._open_audio(48000, 0)
    music.audio_sink = sink
    core.music.register(music)
    voice.hub.start()
    voice._on_chunk = lambda pcm: None
    try:
        assert hub.mixer.ducked is False
        core._set(voice="listening")                                # the assistant starts: music steps back by 20 dB
        assert hub.mixer.ducked is True
        core._set(voice="idle")
        assert hub.mixer.ducked is False
    finally:
        voice.stop()
        hub.stop()


async def test_a_lite_hub_rejects_a_mismatched_voice_profile():
    from havenos.core.voice.profiles import XVF3800
    with pytest.raises(ValueError):
        LocalAudio(XVF3800, hub=AudioHub(16000, mode="null"))


# ---- choosing the output device ----

class FakePortAudio:
    """Just enough of sounddevice for output_choices and AudioHub._open_device."""
    class PortAudioError(Exception):
        pass

    def __init__(self, devices, broken=()):
        self._devices, self.broken, self.opened = devices, set(broken), []

    def query_devices(self, device=None, kind=None):
        if kind == "output":
            return {"name": self._devices[0]["name"], "max_output_channels": 2}
        return self._devices[device] if device is not None else list(self._devices)

    def RawOutputStream(self, device=None, **kw):
        outer = self
        name = self._devices[device]["name"] if device is not None else "default"
        if any(b in name for b in self.broken):
            raise self.PortAudioError("busy")
        self.opened.append(name)
        return type("S", (), {"start": lambda s: None, "stop": lambda s: None, "close": lambda s: None})()


PI = [{"name": "bcm2835 Headphones: - (hw:0,0)", "max_output_channels": 8},
      {"name": "sysdefault", "max_output_channels": 128}, {"name": "upmix", "max_output_channels": 8},
      {"name": "USB Audio: - (hw:2,0)", "max_output_channels": 2}, {"name": "mic", "max_output_channels": 0},
      {"name": "default", "max_output_channels": 128}]


def test_output_choices_lists_real_hardware_with_stable_names():
    from havenos.core.audio.output import output_choices
    got = output_choices(FakePortAudio(PI))
    assert [c["value"] for c in got] == ["bcm2835 Headphones: -", "USB Audio: -"]          # no (hw:N,M), no aliases, no inputs
    assert [c["label"] for c in got] == ["bcm2835 Headphones", "USB Audio"]


def test_output_choices_without_alsa_names_hides_only_the_default_alias():
    from havenos.core.audio.output import output_choices
    mac = [{"name": "MacBook Pro Speakers", "max_output_channels": 2}, {"name": "default", "max_output_channels": 2}]
    assert [c["value"] for c in output_choices(FakePortAudio(mac))] == ["MacBook Pro Speakers"]


def test_a_saved_choice_still_matches_the_full_alsa_name():
    sd = FakePortAudio(PI)
    assert candidates(sd, "USB Audio: -") == [3]          # the stored value is a substring of "USB Audio: - (hw:2,0)"


def test_set_match_moves_the_running_output_and_restores_the_old_one_on_failure(monkeypatch):
    import sys
    sd = FakePortAudio(PI, broken=("USB",))
    monkeypatch.setitem(sys.modules, "sounddevice", sd)
    h = AudioHub(RATE, mode="device", match="Headphones")
    h.start()
    assert sd.opened == ["bcm2835 Headphones: - (hw:0,0)"]
    with pytest.raises(RuntimeError):
        h.set_match("USB Audio")                           # will not open
    assert h.match == "Headphones" and sd.opened[-1] == "bcm2835 Headphones: - (hw:0,0)"      # back on the old output
    sd.broken.clear()
    h.set_match("USB Audio")
    assert sd.opened[-1] == "USB Audio: - (hw:2,0)" and h.started


def test_test_tone_reaches_the_media_bus(hub):
    import asyncio

    async def go():
        hub.test_tone(0.2)
        sink_pcm = pull(hub, 2000)
        return sink_pcm
    out = asyncio.run(go())
    assert out.any()
