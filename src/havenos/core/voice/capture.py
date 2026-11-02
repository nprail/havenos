"""Listen for one utterance in the 16 kHz mono capture stream: wait for speech, follow it, stop after it ends.

Energy-based, with a noise floor that adapts while nothing is being said. The USB arrays in spec 05 already clean the audio
(echo, noise, gain), which is what makes a simple detector good enough; it is not a general-purpose VAD. Used by library
voice search, where Home Assistant's own end-of-speech detection is not in the loop.
"""
from __future__ import annotations

import math
from collections import deque

import numpy as np

RATE = 16000
FRAME = RATE // 50                         # 20 ms
FRAME_BYTES = FRAME * 2
CALIBRATION_FRAMES = 10


def frame_db(frame: np.ndarray) -> float:
    rms = float(np.sqrt(np.mean(np.square(frame.astype(np.float64))))) / 32768.0
    return 20 * math.log10(rms) if rms > 0 else -120.0


class SpeechCapture:
    """Feed chunks of 16-bit mono PCM; `state` goes waiting -> speaking -> done, or waiting -> timeout. Start it just before the user is
    expected to speak (the satellite does it after its chime): the first 200 ms set the noise floor. When done,
    `audio` holds the utterance with a little lead-in and the trailing quiet trimmed to a short tail."""

    def __init__(self, *, wait_s: float = 6.0, max_s: float = 10.0, end_silence_s: float = 0.8, min_speech_s: float = 0.16,
                 preroll_s: float = 0.3, margin_db: float = 10.0, min_db: float = -48.0) -> None:
        self.wait_frames = int(wait_s * 50)
        self.max_frames = int(max_s * 50)
        self.end_frames = int(end_silence_s * 50)
        self.min_speech_frames = max(1, int(min_speech_s * 50))
        self.margin_db, self.min_db = margin_db, min_db
        self.state = "waiting"
        self.audio = b""
        self._buf = bytearray()
        self._floor = -60.0
        self._calib: list[float] = []                           # the first 200 ms are taken to be the room, not speech
        self._seen = 0
        self._run = 0                                           # consecutive loud frames while waiting
        self._quiet = 0                                         # consecutive quiet frames while speaking
        self._preroll: deque[bytes] = deque(maxlen=max(1, int(preroll_s * 50)))
        self._speech: list[bytes] = []

    @property
    def finished(self) -> bool:
        return self.state in ("done", "timeout")

    @property
    def threshold_db(self) -> float:
        return max(self._floor + self.margin_db, self.min_db)

    def feed(self, pcm: bytes) -> str:
        self._buf += pcm
        while len(self._buf) >= FRAME_BYTES and not self.finished:
            raw = bytes(self._buf[:FRAME_BYTES])
            del self._buf[:FRAME_BYTES]
            self._frame(raw)
        return self.state

    def _frame(self, raw: bytes) -> None:
        db = frame_db(np.frombuffer(raw, dtype=np.int16))
        self._seen += 1
        if len(self._calib) < CALIBRATION_FRAMES:
            self._calib.append(max(db, -90.0))
            self._floor = float(np.mean(self._calib))
            self._preroll.append(raw)
            return
        loud = db > self.threshold_db
        if self.state == "waiting":
            if not loud:
                self._floor = 0.95 * self._floor + 0.05 * max(db, -90.0)       # follow the room, only while nobody speaks
                self._run = 0
                self._preroll.append(raw)
                if self._seen >= self.wait_frames:
                    self.state = "timeout"
                return
            self._run += 1
            self._preroll.append(raw)
            if self._run >= self.min_speech_frames:
                self.state = "speaking"
                self._speech = list(self._preroll)
                self._quiet = 0
            return
        self._speech.append(raw)
        self._quiet = 0 if loud else self._quiet + 1
        if self._quiet >= self.end_frames or len(self._speech) >= self.max_frames:
            keep = len(self._speech) - max(0, self._quiet - 10)          # leave a 200 ms tail, not the whole silence
            self.audio = b"".join(self._speech[:keep])
            self.state = "done"
