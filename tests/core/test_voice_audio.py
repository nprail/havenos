"""The pure audio pieces of the voice pipeline: mixer ducking, profiles, resampling, the real ffmpeg decode path."""
import asyncio
import math
import wave

import numpy as np
import pytest

from havenos.core.audio import mixer as mx
from havenos.core.voice import sounds
from havenos.core.voice.audio import Downsampler, LocalAudio, pick_channel
from havenos.core.voice.profiles import DEFAULT, LITE, XVF3800, get_profile


def tone(rate: int, secs: float, freq: float = 440.0, amp: float = 0.5, channels: int = 2) -> bytes:
    t = np.arange(int(rate * secs)) / rate
    a = (np.sin(2 * np.pi * freq * t) * amp * 32767).astype(np.int16)
    return (np.repeat(a, channels) if channels == 2 else a).tobytes()


def rms(pcm: bytes) -> float:
    a = np.frombuffer(pcm, dtype=np.int16).astype(np.float64)
    return float(np.sqrt((a ** 2).mean())) if len(a) else 0.0


def test_volume_is_clamped_to_the_vpe_range_in_steps():
    assert mx.volume_to_gain(0) == 0.4 and mx.volume_to_gain(1) == 0.85 and mx.volume_to_gain(5) == 0.85
    assert mx.volume_to_gain(-1) == 0.4
    for v in range(21):
        g = mx.volume_to_gain(v / 20)
        assert abs(g * 20 - round(g * 20)) < 1e-6                 # always a multiple of 0.05


@pytest.mark.parametrize("rate", [48000, 16000])
def test_ducking_drops_20_db_instantly_and_returns_over_one_second(rate):
    m = mx.Mixer(rate, volume=1.0)
    block = rate // 50                                          # 20 ms
    m.write("media", tone(rate, 4.0, amp=0.5), 2)
    full = rms(m.read(block))
    m.set_duck(True)
    ducked = rms(m.read(block))                                 # the very next block is already down
    assert 20 * math.log10(ducked / full) == pytest.approx(-20, abs=0.5)
    for _ in range(10):
        assert rms(m.read(block)) == pytest.approx(ducked, rel=0.05)     # flat while ducked
    m.set_duck(False)
    levels = [rms(m.read(block)) for _ in range(50)]            # 50 x 20 ms = 1 s
    assert levels[0] < full * 0.2                                         # a ramp, not a jump
    assert all(b >= a * 0.97 for a, b in zip(levels, levels[1:]))         # rising (the sine's own wobble aside)
    assert levels[-1] == pytest.approx(full, rel=0.1)                     # back to 0 dB after one second


def test_announce_bus_is_not_ducked():
    m = mx.Mixer(48000, volume=1.0)
    m.write("announce", tone(48000, 0.2, 880, 0.3, channels=1), 1)
    m.set_duck(True)
    plain = mx.Mixer(48000, volume=1.0)
    plain.write("announce", tone(48000, 0.2, 880, 0.3, channels=1), 1)
    assert rms(m.read(480)) == pytest.approx(rms(plain.read(480)), rel=0.01)


def test_read_always_returns_the_requested_frames_and_buffers_drain():
    m = mx.Mixer(16000)
    assert len(m.read(320)) == 320 * 4 and rms(m.read(320)) == 0
    m.write("announce", tone(16000, 0.1, channels=1), 1)
    assert m.playing("announce") and m.buffered_ms("announce") == pytest.approx(100)
    for _ in range(5):
        m.read(320)
    assert not m.playing("announce")
    m.write("media", tone(16000, 1.0))
    m.clear("media")
    assert m.buffered_ms("media") == 0


def test_master_volume_scales_output():
    loud, quiet = mx.Mixer(16000, volume=1.0), mx.Mixer(16000, volume=0.0)
    for m in (loud, quiet):
        m.write("media", tone(16000, 0.1))
    assert rms(loud.read(800)) / rms(quiet.read(800)) == pytest.approx(0.85 / 0.4, rel=0.02)


def test_profiles():
    assert get_profile("xvf3800") == XVF3800 and XVF3800.playback_rate == 48000 and XVF3800.hw_aec
    assert get_profile("LITE") == LITE and LITE.playback_rate == 16000 and LITE.capture_rate == 16000
    assert get_profile("") == DEFAULT and not DEFAULT.hw_aec
    assert get_profile("lite", device="My Array").match == "My Array"
    with pytest.raises(ValueError):
        get_profile("nope")


def test_downsampler_keeps_speech_band_and_removes_aliasing_across_chunks():
    t = np.arange(48000) / 48000
    low, high = np.sin(2 * np.pi * 1000 * t), np.sin(2 * np.pi * 14000 * t)      # 14 kHz would alias into 2 kHz

    def run(x):
        d = Downsampler(48000)
        return np.concatenate([d.process(x[i:i + 480]) for i in range(0, len(x), 480)])

    y_low, y_high = run(low), run(high)
    assert abs(len(y_low) - 16000) <= 2
    assert np.sqrt((y_low[200:] ** 2).mean()) > 0.6                                # the passband survives
    assert np.sqrt((y_high[200:] ** 2).mean()) < 0.02                              # the stopband does not alias
    assert Downsampler(16000).process(np.arange(5)).tolist() == [0, 1, 2, 3, 4]
    with pytest.raises(ValueError):
        Downsampler(44100)


def test_pick_channel_takes_the_processed_channel():
    raw = np.array([[1, 100], [2, 200], [3, 300]], dtype=np.int16).tobytes()
    assert pick_channel(raw, 2, 1).tolist() == [100, 200, 300]
    assert pick_channel(raw, 2, 0).tolist() == [1, 2, 3]
    assert pick_channel(np.array([5, 6], dtype=np.int16).tobytes(), 1, 0).tolist() == [5, 6]


def test_placeholder_sounds_render_at_any_rate():
    for name in sounds.sound_names():
        for rate in (16000, 48000):
            pcm = sounds.render(name, rate)
            assert len(pcm) > rate * 0.2 and rms(pcm) > 500


def test_the_vpe_sounds_ship_with_their_attribution():
    for name in sounds.sound_names():
        assert sounds.path(name) is not None, name
    text = (sounds.ASSETS / "ATTRIBUTION.md").read_text()
    assert "Clayton Charles Tapp" in text and "Creative Commons Attribution 4.0" in text
    assert all(f in text for f in sounds.FILES.values())                  # every shipped file is credited
    shipped = {p.name for p in sounds.ASSETS.iterdir() if p.suffix in (".flac", ".mp3")}
    assert shipped == set(sounds.FILES.values())                           # and nothing else is in the folder


@pytest.mark.parametrize("profile", [XVF3800, LITE])
async def test_each_real_vpe_sound_decodes_and_plays_at_the_boards_rate(profile):
    for name in sounds.sound_names():
        audio = LocalAudio(profile, sink="capture")
        audio.start(lambda pcm: None)
        try:
            assert await asyncio.wait_for(audio.play(f"sound:{name}"), 15) is True
            secs = len(audio.captured) / 4 / profile.playback_rate
            assert 0.5 < secs < 9 and rms(bytes(audio.captured)) > 300, (name, secs)
        finally:
            audio.stop()


async def test_a_missing_sound_file_falls_back_to_the_placeholder(monkeypatch):
    monkeypatch.setattr(sounds, "path", lambda name: None)
    audio = LocalAudio(LITE, sink="capture")
    audio.start(lambda pcm: None)
    try:
        assert await asyncio.wait_for(audio.play("sound:wake"), 3) is True
        assert rms(bytes(audio.captured)) > 500
    finally:
        audio.stop()


async def test_playing_before_start_returns_instead_of_hanging():
    assert await asyncio.wait_for(LocalAudio(LITE, sink="null").play("sound:wake"), 1) is False


async def test_local_audio_plays_a_sound_and_a_decoded_file_through_the_mixer(tmp_path):
    audio = LocalAudio(LITE, sink="capture", volume=1.0)
    audio.start(lambda pcm: None)
    try:
        assert await asyncio.wait_for(audio.play("sound:wake"), 3) is True
        assert rms(bytes(audio.captured)) > 500
        audio.captured.clear()
        wav = tmp_path / "t.wav"                                # a real file through the real ffmpeg decode, 44.1 kHz stereo
        with wave.open(str(wav), "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(44100)
            w.writeframes(tone(44100, 0.3, 660, 0.4))
        assert await asyncio.wait_for(audio.play(str(wav)), 5) is True
        got = bytes(audio.captured)
        assert len(got) > 0.25 * 16000 * 4 and rms(got) > 1000                   # resampled to the Lite's 16 kHz, not dropped
        assert await asyncio.wait_for(audio.play(str(tmp_path / "missing.wav")), 5) is False
    finally:
        audio.stop()


async def test_stop_playback_cuts_a_playing_sound_short():
    audio = LocalAudio(XVF3800, sink="null")
    audio.start(lambda pcm: None)
    try:
        audio.mixer.write("announce", tone(48000, 5.0), 2)      # 5 s queued ahead of the play() call below
        task = asyncio.create_task(audio.play("sound:timer"))
        await asyncio.sleep(0.1)
        audio.stop_playback("announce")
        assert await asyncio.wait_for(task, 1) is False
        assert not audio.mixer.playing("announce")
    finally:
        audio.stop()


async def test_capture_goes_to_the_satellite_as_16k_mono():
    audio = LocalAudio(XVF3800, sink="null")
    got = []
    audio.start(got.append)
    try:
        two_ch = np.zeros((4800, 2), dtype=np.int16)
        two_ch[:, 1] = 5000                                     # the processed channel
        audio.feed_capture(two_ch.tobytes())
        await asyncio.sleep(0.05)
        pcm = np.frombuffer(b"".join(got), dtype=np.int16)
        assert 1500 <= len(pcm) <= 1700 and abs(int(pcm[-1]) - 5000) < 200
    finally:
        audio.stop()
