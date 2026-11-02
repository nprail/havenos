"""The real microWakeWord engine on real audio: macOS's own speech synthesis saying the wake words."""
import shutil
import subprocess
import sys

import numpy as np
import pytest

pytest.importorskip("pymicro_wakeword")

from havenos.core.voice import wake as ww
from havenos.core.voice.microwake import MicroWakeEngine

say = pytest.mark.skipif(sys.platform != "darwin" or not shutil.which("say") or not shutil.which("ffmpeg"),
                         reason="needs macOS speech synthesis and ffmpeg")


def speak(tmp_path, phrase: str) -> bytes:
    aiff = tmp_path / "s.aiff"
    subprocess.run(["say", "-o", str(aiff), phrase], check=True)
    out = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(aiff), "-ar", "16000", "-ac", "1", "-f", "s16le", "-"],
                         check=True, capture_output=True).stdout
    quiet = bytes(16000 * 2)
    return quiet + out + quiet


def run(engine, audio: bytes) -> list[str]:
    heard = []
    for i in range(0, len(audio), 640):                          # 20 ms chunks, like the capture stream
        heard += engine.feed(audio[i:i + 640])
    return heard


def test_cutoffs_are_the_vpe_firmware_values():
    assert [ww.cutoff("okay_nabu", s) for s in ww.SENSITIVITIES] == [217, 176, 143]
    assert [ww.cutoff("hey_jarvis", s) for s in ww.SENSITIVITIES] == [247, 235, 212]
    assert [ww.cutoff("hey_mycroft", s) for s in ww.SENSITIVITIES] == [253, 242, 237]
    e = MicroWakeEngine()
    e.configure(("okay_nabu",), "Very sensitive")
    assert e._models["okay_nabu"].probability_cutoff == pytest.approx(143 / 255)
    e.configure(("hey_jarvis", "okay_nabu"), "Slightly sensitive")
    assert e._models["okay_nabu"].probability_cutoff == pytest.approx(217 / 255)
    e.configure(("hey_jarvis",), "Slightly sensitive")
    assert set(e._models) == {"hey_jarvis"}                        # a deselected word is dropped


def test_silence_and_noise_do_not_wake_it():
    e = MicroWakeEngine()
    e.configure(("okay_nabu", "hey_jarvis", "hey_mycroft"), "Very sensitive")
    rng = np.random.default_rng(7)
    assert run(e, bytes(16000 * 2 * 5)) == []
    assert run(e, rng.normal(0, 3000, 16000 * 10).astype(np.int16).tobytes()) == []


@say
def test_it_hears_okay_nabu_once_and_only_for_the_active_word(tmp_path):
    audio = speak(tmp_path, "okay nabu")
    e = MicroWakeEngine()
    e.configure(("okay_nabu",), "Very sensitive")
    assert run(e, audio) == ["okay_nabu"]                          # one detection, not one per chunk
    other = MicroWakeEngine()
    other.configure(("hey_jarvis",), "Very sensitive")
    assert run(other, audio) == []                                 # a different wake word does not answer to it


@say
def test_a_second_wake_after_the_quiet_period_is_heard_again(tmp_path):
    audio = speak(tmp_path, "okay nabu")
    e = MicroWakeEngine()
    e.configure(("okay_nabu",), "Very sensitive")
    assert run(e, audio + bytes(16000 * 2 * 3) + audio) == ["okay_nabu", "okay_nabu"]


def test_stop_word_needs_a_model_and_is_off_unless_enabled():
    e = MicroWakeEngine()                                          # no stop model configured
    e.configure(("okay_nabu",), "Moderately sensitive")
    e.set_stop_enabled(True)
    assert e._stop_enabled is False
    assert run(e, bytes(16000 * 2)) == []
