"""Finding one utterance in the capture stream."""
import shutil
import subprocess
import sys

import numpy as np
import pytest

from havenos.core.voice.capture import SpeechCapture

RNG = np.random.default_rng(3)


def noise(secs, db):
    return (RNG.normal(0, 1, int(16000 * secs)) * 32768 * 10 ** (db / 20)).astype(np.int16)


def speechlike(secs, db=-22):
    t = np.arange(int(16000 * secs)) / 16000
    return (np.sin(2 * np.pi * 300 * t) * 32768 * 10 ** (db / 20)).astype(np.int16) + noise(secs, -50)


def feed(cap, pcm, chunk=640):
    for i in range(0, len(pcm), chunk):
        cap.feed(pcm[i:i + chunk].tobytes())
        if cap.finished:
            break
    return cap


def test_it_finds_an_utterance_in_quiet_and_stops_after_it_ends():
    cap = feed(SpeechCapture(), np.concatenate([noise(1.0, -60), speechlike(1.2), noise(3, -60)]))
    assert cap.state == "done"
    secs = len(cap.audio) / 32000
    assert 1.2 <= secs <= 2.0                                  # the words, a little lead-in, a short tail: not the whole silence


def test_nothing_said_times_out():
    cap = feed(SpeechCapture(wait_s=3), noise(6, -58))
    assert cap.state == "timeout" and cap.audio == b""


def test_a_click_is_not_speech():
    sig = np.concatenate([noise(1, -60), speechlike(0.06), noise(5, -60)])
    assert feed(SpeechCapture(wait_s=3), sig).state == "timeout"


def test_it_works_whatever_the_chunk_size():
    sig = np.concatenate([noise(0.5, -60), speechlike(1.0), noise(2, -60)])
    sizes = {n: len(feed(SpeechCapture(), sig, n).audio) for n in (160, 640, 1000, 4096)}
    assert all(v > 0 for v in sizes.values()) and max(sizes.values()) - min(sizes.values()) <= 1600


def test_a_very_long_utterance_is_cut_at_the_limit():
    cap = feed(SpeechCapture(max_s=2.0), np.concatenate([noise(0.3, -60), speechlike(8.0)]))
    assert cap.state == "done" and len(cap.audio) / 32000 <= 2.4


def test_the_noise_floor_follows_a_noisy_room_but_speech_still_stands_out():
    cap = SpeechCapture(wait_s=10)
    feed(cap, noise(2, -40))                                   # a loud room: its level becomes the floor, it is not speech
    assert cap.state == "waiting" and cap.threshold_db > -40
    feed(cap, speechlike(1.0, -12) + noise(1.0, -40))
    feed(cap, noise(2, -40))
    assert cap.state == "done"


def test_quiet_rooms_use_the_minimum_threshold():
    cap = feed(SpeechCapture(), noise(1, -80))
    assert cap.threshold_db == -48.0


@pytest.mark.skipif(sys.platform != "darwin" or not shutil.which("say") or not shutil.which("ffmpeg"), reason="needs macOS speech")
def test_it_captures_real_synthesized_speech(tmp_path):
    aiff = tmp_path / "q.aiff"
    subprocess.run(["say", "-o", str(aiff), "play some jazz"], check=True)
    raw = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(aiff), "-ar", "16000", "-ac", "1", "-f", "s16le", "-"],
                         check=True, capture_output=True).stdout
    speech = np.frombuffer(raw, dtype=np.int16)
    cap = feed(SpeechCapture(), np.concatenate([noise(1, -60), speech, noise(3, -60)]))
    assert cap.state == "done"
    got = np.frombuffer(cap.audio, dtype=np.int16)
    assert len(got) >= len(speech) * 0.95                      # the whole phrase is in there
    assert np.abs(got).max() >= np.abs(speech).max() * 0.9


def test_speech_in_the_first_200_ms_is_taken_as_the_room():
    """Documented limit: the detector learns the noise floor from the start of the stream, so the satellite starts it after
    its chime, when the user has not begun yet."""
    assert feed(SpeechCapture(wait_s=3), speechlike(4.0)).state == "timeout"
