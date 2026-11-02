import numpy as np
import pytest

from havenos.core.audio.resample import Resampler


def sine(rate, secs, hz, amp=0.5, channels=2):
    t = np.arange(int(rate * secs)) / rate
    a = (np.sin(2 * np.pi * hz * t) * amp * 32767).astype(np.int16)
    return np.repeat(a, channels).tobytes() if channels == 2 else a.tobytes()


def snr_and_amp(pcm: bytes, rate: int, hz: float, skip: int = 2000):
    y = np.frombuffer(pcm, dtype=np.int16).reshape(-1, 2)[skip:, 0].astype(np.float64) / 32768
    n = np.arange(len(y))
    basis = np.stack([np.sin(2 * np.pi * hz * n / rate), np.cos(2 * np.pi * hz * n / rate)], axis=1)
    coef = np.linalg.lstsq(basis, y, rcond=None)[0]
    fit = basis @ coef
    return 10 * np.log10((fit ** 2).mean() / max(((y - fit) ** 2).mean(), 1e-20)), float(np.hypot(*coef))


def run(r: Resampler, pcm: bytes, chunk: int) -> bytes:
    return b"".join(r.process(pcm[i:i + chunk]) for i in range(0, len(pcm), chunk))


@pytest.mark.parametrize("rin,rout,hz,min_snr", [(44100, 48000, 1000, 55), (44100, 48000, 4000, 45), (44100, 48000, 8000, 30),
                                                 (48000, 16000, 1000, 55), (44100, 16000, 3000, 45)])
def test_tones_come_through_at_the_right_pitch_level_and_length(rin, rout, hz, min_snr):
    out = run(Resampler(rin, rout), sine(rin, 2, hz), 4 * 441 * 3 + 4)
    assert abs(len(out) // 4 - 2 * rout) <= 3
    snr, amp = snr_and_amp(out, rout, hz)
    assert amp == pytest.approx(0.5, abs=0.015) and snr > min_snr             # (8 kHz loses a little: cubic interpolation)


def test_downsampling_does_not_alias_ultrasonic_content():
    out = run(Resampler(48000, 16000), sine(48000, 2, 14000), 4800)           # 14 kHz would fold into 2 kHz at 16 kHz
    _, amp = snr_and_amp(out, 16000, 2000)
    assert amp < 0.01


def test_chunking_does_not_change_the_sound():
    pcm = sine(44100, 1, 1234)
    whole = np.frombuffer(Resampler(44100, 48000).process(pcm), dtype=np.int16).astype(int)
    parts = np.frombuffer(run(Resampler(44100, 48000), pcm, 4 * 97), dtype=np.int16).astype(int)    # awkward 97-frame chunks
    n = min(len(whole), len(parts))
    assert abs(len(whole) - len(parts)) <= 4 and np.abs(whole[:n] - parts[:n]).max() <= 1


def test_empty_and_tiny_chunks_are_fine():
    r = Resampler(44100, 48000)
    assert r.process(b"") == b""
    assert len(r.process(np.zeros(2, dtype=np.int16).tobytes())) >= 0           # one stereo frame
    mono = Resampler(44100, 48000, channels=1)
    assert len(mono.process(sine(44100, 0.1, 440, channels=1))) > 0
