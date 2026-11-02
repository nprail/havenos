"""The two-bus mixer from spec 05 section 2.4, pure numpy: no audio device, no asyncio, so it is easy to test.

Two buses feed one stereo output at `rate`: **announce** (chimes, TTS, timer sound, announcements) and **media** (music
and anything played through the media_player). The media bus is ducked by 20 dB the instant something on the announce
side starts, and comes back over one second when it ends. The master volume is clamped to the VPE's range.

Each bus carries any number of **streams**: one per music source and one for the voice side. A stream has its own queue,
gain and prebuffer, so a source that stops can clear its own audio without touching the source that just took over.
"""
from __future__ import annotations

import threading

import numpy as np

DUCK_DB = -20.0
DUCK_RESTORE_S = 1.0
VOLUME_MIN, VOLUME_MAX, VOLUME_STEP = 0.4, 0.85, 0.05       # the VPE's clamp: the speaker never goes quieter or louder
BUSES = ("announce", "media")


def volume_to_gain(volume: float) -> float:
    """Home Assistant's 0..1 slider mapped onto the VPE's clamped output range in 0.05 steps."""
    v = VOLUME_MIN + (VOLUME_MAX - VOLUME_MIN) * min(1.0, max(0.0, volume))
    return round(round(v / VOLUME_STEP) * VOLUME_STEP, 2)


def level_to_gain(level: int, muted: bool = False) -> float:
    """A source's 0-100 volume slider as a gain, on the Sendspin spec's loudness curve."""
    if muted:
        return 0.0
    return 1.0 if level >= 100 else (max(0, level) / 100.0) ** 1.5


def to_stereo(pcm: bytes, channels: int) -> np.ndarray:
    """Interleaved int16 PCM as a float32 (n, 2) array in -1..1 (mono is copied to both sides)."""
    a = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    if channels == 1:
        return np.stack([a, a], axis=1)
    if channels == 2:
        return a[: len(a) // 2 * 2].reshape(-1, 2)
    raise ValueError(f"unsupported channel count {channels}")


class Stream:
    """One writer's queue on a bus. Silent until `prebuffer_ms` of audio is queued; if it runs dry it goes quiet and waits
    for the prebuffer again rather than stuttering."""

    def __init__(self, mixer: "Mixer", bus: str, prebuffer_ms: float = 0.0) -> None:
        self._mixer, self.bus = mixer, bus
        self._q: list[np.ndarray] = []
        self._queued = 0
        self._prebuffer = int(mixer.rate * prebuffer_ms / 1000.0)
        self._armed = self._prebuffer == 0
        self.gain = 1.0                                   # linear; the source's own volume

    def write(self, pcm: bytes, channels: int = 2) -> None:
        block = to_stereo(pcm, channels)
        if len(block):
            with self._mixer._lock:
                self._q.append(block)
                self._queued += len(block)

    def write_float(self, block: np.ndarray) -> None:
        if len(block):
            with self._mixer._lock:
                self._q.append(block.astype(np.float32, copy=False))
                self._queued += len(block)

    def clear(self) -> None:
        with self._mixer._lock:
            self._q.clear()
            self._queued = 0
            self._armed = self._prebuffer == 0

    def set_level(self, level: int, muted: bool = False) -> None:
        self.gain = level_to_gain(level, muted)

    def buffered_ms(self) -> float:
        with self._mixer._lock:
            return self._queued * 1000.0 / self._mixer.rate

    def close(self) -> None:
        self._mixer._close(self)

    def _take(self, frames: int) -> np.ndarray | None:
        """Up to `frames` of audio (zero-padded), or None when silent. Called with the mixer lock held."""
        if not self._armed:
            if self._queued < self._prebuffer:
                return None
            self._armed = True
        if not self._queued:
            if self._prebuffer:
                self._armed = False                       # ran dry: wait for the prebuffer again
            return None
        out = np.zeros((frames, 2), dtype=np.float32)
        filled = 0
        while self._q and filled < frames:
            head = self._q[0]
            n = min(len(head), frames - filled)
            out[filled:filled + n] = head[:n]
            filled += n
            if n == len(head):
                self._q.pop(0)
            else:
                self._q[0] = head[n:]
        self._queued -= filled
        if filled < frames and self._prebuffer:
            self._armed = False                           # ran dry: rebuffer
        return out * self.gain if self.gain != 1.0 else out


class Mixer:
    def __init__(self, rate: int = 48000, *, volume: float = 1.0, duck_db: float = DUCK_DB) -> None:
        self.rate = rate
        self.duck_db = duck_db
        self._lock = threading.Lock()
        self._streams: dict[str, list[Stream]] = {b: [] for b in BUSES}
        self._default = {b: self.open(b) for b in BUSES}      # what write()/clear() use
        self._ducked = False
        self._duck_gain = 1.0                           # linear gain on the media bus right now
        self._gain = volume_to_gain(volume)
        self.peak = 0.0                                 # of the last block read (for level meters)

    # ---- streams ----

    def open(self, bus: str, prebuffer_ms: float = 0.0) -> Stream:
        s = Stream(self, bus, prebuffer_ms)
        with self._lock:
            self._streams[bus].append(s)
        return s

    def _close(self, stream: Stream) -> None:
        with self._lock:
            if stream in self._streams[stream.bus]:
                self._streams[stream.bus].remove(stream)

    # ---- control (any thread) ----

    def set_volume(self, volume: float) -> None:
        self._gain = volume_to_gain(volume)

    @property
    def gain(self) -> float:
        return self._gain

    def set_duck(self, ducked: bool, db: float | None = None) -> None:
        if db is not None:
            self.duck_db = db
        self._ducked = ducked

    @property
    def ducked(self) -> bool:
        return self._ducked

    def write(self, bus: str, pcm: bytes, channels: int = 2) -> None:
        """Queue interleaved int16 PCM (already at `rate`) on a bus's default stream."""
        self._default[bus].write(pcm, channels)

    def clear(self, bus: str | None = None) -> None:
        """Drop everything queued on a bus (every stream on it), or on both."""
        for b in (bus,) if bus else BUSES:
            for s in list(self._streams[b]):
                s.clear()

    def buffered_ms(self, bus: str) -> float:
        return sum(s.buffered_ms() for s in list(self._streams[bus]))

    def playing(self, bus: str) -> bool:
        return self.buffered_ms(bus) > 0

    # ---- audio thread ----

    def _sum(self, bus: str, frames: int) -> np.ndarray:
        out = np.zeros((frames, 2), dtype=np.float32)
        with self._lock:
            for s in self._streams[bus]:
                block = s._take(frames)
                if block is not None:
                    out += block
        return out

    def read(self, frames: int) -> bytes:
        """The next `frames` of mixed stereo int16 output. Always returns exactly that many (silence-padded)."""
        announce, media = self._sum("announce", frames), self._sum("media", frames)
        g0 = self._duck_gain
        if self._ducked:
            g1 = 10 ** (self.duck_db / 20.0)            # the drop is immediate and flat across the block
            ramp = np.full(frames, g1, dtype=np.float32)
        else:
            g1 = min(1.0, g0 + frames / (self.rate * DUCK_RESTORE_S))
            ramp = np.linspace(g0, g1, frames, dtype=np.float32) if g1 > g0 else np.full(frames, 1.0, dtype=np.float32)
        self._duck_gain = g1
        mixed = (announce + media * ramp[:, None]) * self._gain
        np.clip(mixed, -1.0, 1.0, out=mixed)
        self.peak = float(np.abs(mixed).max()) if frames else 0.0
        return (mixed * 32767.0).astype(np.int16).tobytes()
