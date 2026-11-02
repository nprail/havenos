"""A streaming sample-rate converter for the music path (44.1 or 48 kHz sources into whatever rate the mixer runs at).

Catmull-Rom cubic interpolation, which is clean enough for an upsample (44.1 to 48 kHz) and for speech-band output; when
the output rate is lower (48 to 16 kHz for the Lite) a windowed-sinc low-pass runs first so nothing aliases. It keeps
state between chunks, so any chunking gives the same sound.
"""
from __future__ import annotations

import numpy as np

TAPS = 63


class Resampler:
    def __init__(self, rate_in: int, rate_out: int, channels: int = 2) -> None:
        self.rate_in, self.rate_out, self.channels = rate_in, rate_out, channels
        self.step = rate_in / rate_out
        self._tail = np.zeros((4, channels), dtype=np.float32)    # the last 4 samples: a cubic needs one before and two after
        self._pos = 4.0                                   # where the next output sits in (tail + new) coordinates
        self._fir: np.ndarray | None = None
        if rate_out < rate_in:
            n = np.arange(TAPS) - (TAPS - 1) / 2
            cutoff = 0.45 * rate_out / rate_in            # a little under the new Nyquist, as a fraction of the input rate
            h = np.sinc(2 * cutoff * n) * np.hamming(TAPS)
            self._fir = (h / h.sum()).astype(np.float32)
            self._fir_tail = np.zeros((TAPS - 1, channels), dtype=np.float32)

    def process(self, pcm: bytes) -> bytes:
        """Interleaved int16 in, interleaved int16 out (about len * rate_out / rate_in)."""
        x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32).reshape(-1, self.channels)
        if self._fir is not None:
            ext = np.concatenate([self._fir_tail, x])
            self._fir_tail = ext[-(TAPS - 1):]
            x = np.stack([np.convolve(ext[:, c], self._fir, mode="valid") for c in range(self.channels)], axis=1)
        buf = np.concatenate([self._tail, x])
        m = len(buf)
        if self._pos > m - 3:
            n_out = 0
        else:
            n_out = int((m - 3 - self._pos) / self.step) + 1
        if n_out:
            p = self._pos + np.arange(n_out) * self.step
            i = p.astype(np.int64)
            t = (p - i).astype(np.float32)[:, None]
            x0, x1, x2, x3 = buf[i - 1], buf[i], buf[i + 1], buf[i + 2]
            y = x1 + 0.5 * t * (x2 - x0 + t * (2 * x0 - 5 * x1 + 4 * x2 - x3 + t * (3 * (x1 - x2) + x3 - x0)))
        else:
            y = np.zeros((0, self.channels), dtype=np.float32)
        self._pos = self._pos + n_out * self.step - (m - 4)
        self._tail = buf[-4:]
        return np.clip(y, -32768, 32767).astype(np.int16).tobytes()

    def process_float(self, pcm: bytes) -> np.ndarray:
        """Same, as float32 (n, channels) in -1..1 for the mixer."""
        return np.frombuffer(self.process(pcm), dtype=np.int16).astype(np.float32).reshape(-1, self.channels) / 32768.0
