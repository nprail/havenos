"""Playing a URL that Home Assistant sends to the display's media_player (real ffmpeg, a fake sound sink)."""
import asyncio
import wave

import numpy as np
import pytest

from havenos.core.media import MediaCoordinator
from havenos.core.media.sources.fake import FakeSource
from havenos.core.media.sources.url import UrlSource, title_from
from conftest import wait_for
from fakes import FakeSink


def make_wav(path, secs=1.0, rate=44100, hz=440):
    t = np.arange(int(rate * secs)) / rate
    pcm = np.repeat((np.sin(2 * np.pi * hz * t) * 0.4 * 32767).astype(np.int16), 2).tobytes()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return path


@pytest.fixture
async def rig(tmp_path):
    states = []
    music = MediaCoordinator(lambda **kw: states.append(kw), echo_window_s=0.0)
    sink = FakeSink()
    src = UrlSource(sink)
    music.register(src)
    await music.start()

    class R:
        pass
    r = R()
    r.music, r.sink, r.src, r.tmp = music, sink, src, tmp_path
    yield r
    await music.stop()


def test_title_comes_from_the_url():
    assert title_from("http://ha.local:8123/api/tts_proxy/abc123_en.mp3") == "abc123_en"
    assert title_from("http://x/media/My%20Song.flac?token=1") == "My Song"
    assert title_from("http://x/") == ""


async def test_a_url_plays_through_to_the_end_and_takes_the_speaker(rig):
    wav = make_wav(rig.tmp / "chime.wav", 1.0)
    await rig.src.play_url(str(wav), "Chime")
    await wait_for(lambda: rig.music.active == "homeassistant")
    st = rig.music.state()
    assert st["track"]["title"] == "Chime" and st["status"] == "playing" and st["source_label"] == "Home Assistant"
    assert set(st["capabilities"]) == {"play", "pause"}
    await wait_for(lambda: rig.music.active is None, timeout=8)           # the clip ended: the speaker is free again
    secs = len(rig.sink.data) / (48000 * 4)
    assert 1.0 <= secs <= 1.3                                      # the whole second, resampled to 48 kHz, plus the start-up padding
    assert np.abs(np.frombuffer(bytes(rig.sink.data[:96000]), dtype=np.int16)).max() > 5000


async def test_pause_and_resume(rig):
    wav = make_wav(rig.tmp / "long.wav", 4.0)
    await rig.src.play_url(str(wav))
    await wait_for(lambda: len(rig.sink.data) > 48000 * 4 * 0.3)
    assert await rig.music.command("pause") is True
    await wait_for(lambda: rig.music.state()["status"] == "paused")
    at_pause = len(rig.sink.data)
    await asyncio.sleep(0.4)
    assert len(rig.sink.data) <= at_pause + 48000 * 4 * 0.1          # nothing more is fed while paused
    assert rig.sink.clears >= 1
    assert await rig.music.command("play") is True
    await wait_for(lambda: len(rig.sink.data) > at_pause + 48000 * 4 * 0.5)
    assert rig.music.state()["status"] == "playing"


async def test_a_missing_or_broken_url_tells_the_user(rig):
    notes = []
    rig.music._notify = lambda message, title: notes.append((message, title))
    await rig.src.play_url(str(rig.tmp / "nope.wav"))
    await wait_for(lambda: notes, timeout=8)
    assert "Could not play" in notes[0][0] and notes[0][1] == "Home Assistant"
    bad = rig.tmp / "junk.mp3"
    bad.write_bytes(b"not audio at all" * 100)
    notes.clear()
    await rig.src.play_url(str(bad))
    await wait_for(lambda: notes, timeout=8)


async def test_it_takes_the_speaker_from_another_source_and_gives_it_back(rig):
    other = FakeSource("spotify", "Spotify")
    rig.music.register(other)
    await other.start()
    other.connect("phone")
    other.play()
    await wait_for(lambda: rig.music.active == "spotify")
    await rig.src.play_url(str(make_wav(rig.tmp / "a.wav", 3.0)), "Doorbell")
    await wait_for(lambda: rig.music.active == "homeassistant")
    await rig.music.settle()
    assert other.released == 1                                       # Spotify was asked to step back
    assert rig.music.takeovers[-1] == ("spotify", "homeassistant")
    other.play()                                                     # the phone starts again: it wins the speaker back
    await wait_for(lambda: rig.music.active == "spotify")
    await wait_for(lambda: rig.src._paused)                          # and the URL source stops feeding the speaker
    assert rig.music.state()["status"] == "playing"


async def test_the_device_volume_reaches_the_sink(rig):
    await rig.src.play_url(str(make_wav(rig.tmp / "v.wav", 2.0)))
    await wait_for(lambda: rig.music.active == "homeassistant")
    await rig.music.command("volume", level=35)
    await wait_for(lambda: (35, False) in rig.sink.volumes)


async def test_no_audio_output_or_ffmpeg_is_reported_not_raised(tmp_path):
    notes = []
    music = MediaCoordinator(lambda **kw: None, notify=lambda m, t: notes.append(m))
    src = UrlSource(None)
    music.register(src)
    await music.start()
    await src.play_url("http://x/a.mp3")
    assert "no audio output" in notes[0].lower()
    await music.stop()
