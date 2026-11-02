"""Audio for the voice satellite: the backend seam, the real local implementation, and the capture-side DSP helpers.

`AudioBackend` is what the satellite needs: a stream of 16 kHz mono capture chunks, and a way to play a sound or URL on
the announce bus and wait for it to finish. `LocalAudio` is the real one: sounddevice for the USB array, ffmpeg to decode
URLs, and the `Mixer` between them. Spec 05 wants this in its own process; it runs in-process for now behind the same
interface, so moving it is a transport change. Not run on real hardware yet (bring-up V0b).
"""
from __future__ import annotations

import asyncio
import logging
import shutil
from typing import Any, Callable, Protocol

import numpy as np

from . import sounds
from ..audio.output import AudioHub
from .profiles import DeviceProfile

log = logging.getLogger(__name__)

CAPTURE_RATE = 16000                    # what the wake word and Home Assistant want
Chunk = Callable[[bytes], None]


class AudioBackend(Protocol):
    def start(self, on_chunk: Chunk) -> None: ...
    def stop(self) -> None: ...
    async def play(self, source: str, bus: str = "announce") -> bool:
        """Play `source` ("sound:<name>", a URL or a file path) and return when it ends: True if it played to the end,
        False if it was cut off or could not be decoded."""
    def stop_playback(self, bus: str | None = None) -> None: ...
    def set_volume(self, volume: float) -> None: ...


class Downsampler:
    """Stateful low-pass + decimate from an integer multiple of 16 kHz (48 kHz -> 16 kHz) over a stream of chunks."""

    def __init__(self, rate: int, taps: int = 63) -> None:
        if rate % CAPTURE_RATE:
            raise ValueError(f"capture rate {rate} is not a multiple of {CAPTURE_RATE}")
        self.factor = rate // CAPTURE_RATE
        n = np.arange(taps) - (taps - 1) / 2
        cutoff = 0.5 / self.factor * 0.9               # a little under the new Nyquist
        h = np.sinc(2 * cutoff * n) * np.hamming(taps)
        self._h = (h / h.sum()).astype(np.float32)
        self._tail = np.zeros(taps - 1, dtype=np.float32)
        self._phase = 0

    def process(self, x: np.ndarray) -> np.ndarray:
        if self.factor == 1:
            return x
        x = np.concatenate([self._tail, x.astype(np.float32)])
        self._tail = x[-(len(self._h) - 1):]
        y = np.convolve(x, self._h, mode="valid")
        out = y[self._phase::self.factor]
        self._phase = (self._phase - len(y)) % self.factor
        return out


def pick_channel(raw: bytes, channels: int, channel: int) -> np.ndarray:
    a = np.frombuffer(raw, dtype=np.int16)
    return a if channels == 1 else a[: len(a) // channels * channels].reshape(-1, channels)[:, channel]


class LocalAudio:
    """Capture from the USB array, and playback on the announce bus of the shared `AudioHub` (so music and voice use one
    mixer and one output). `sink` matters only when no hub is passed: "device" plays to the sound device, "null" discards,
    "capture" keeps the output in `captured` (tests)."""

    def __init__(self, profile: DeviceProfile, *, sink: str = "device", volume: float = 1.0, hub: AudioHub | None = None) -> None:
        self.profile = profile
        self.sink = sink
        self._own_hub = hub is None
        self.hub = hub or AudioHub(profile.playback_rate, mode=sink, match=profile.match or None, volume=volume)
        if self.hub.rate != profile.playback_rate:
            raise ValueError(f"the audio hub runs at {self.hub.rate} Hz but profile {profile.name} plays at {profile.playback_rate}")
        self.mixer = self.hub.mixer
        self._capture: Any = None
        self._on_chunk: Chunk | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._down = Downsampler(profile.capture_rate)
        self._procs: dict[str, set[asyncio.subprocess.Process]] = {"announce": set(), "media": set()}
        self._plays: dict[str, set[asyncio.Task]] = {"announce": set(), "media": set()}

    @property
    def captured(self) -> bytearray:
        return self.hub.captured

    # ---- lifecycle ----

    def start(self, on_chunk: Chunk) -> None:
        self._on_chunk, self._loop = on_chunk, asyncio.get_running_loop()
        self.hub.start()
        if self.sink == "device" or not self._own_hub:
            self._open_capture()

    def stop(self) -> None:
        self.stop_playback()
        if self._capture is not None:
            try:
                self._capture.stop()
                self._capture.close()
            except Exception:
                log.debug("closing the capture stream failed", exc_info=True)
            self._capture = None
        if self._own_hub:
            self.hub.stop()
        self._on_chunk = None

    def _open_capture(self) -> None:
        import sounddevice as sd
        p = self.profile
        self._capture = sd.RawInputStream(samplerate=p.capture_rate, channels=p.capture_channels, dtype="int16",
                                          device=self._find(sd, p.match), blocksize=p.capture_rate // 50,
                                          callback=self._capture_cb)
        self._capture.start()
        log.info("voice capture: %s, %d Hz channel %d of %d", p.name, p.capture_rate, p.capture_channel, p.capture_channels)

    @staticmethod
    def _find(sd: Any, match: str) -> int | None:
        if not match:
            return None
        for i, d in enumerate(sd.query_devices()):
            if match.lower() in d["name"].lower() and d["max_input_channels"]:
                return i
        raise RuntimeError(f"no sound device matching {match!r} with an input")

    # ---- capture (audio thread -> loop) ----

    def _capture_cb(self, indata, frames, _time, _status) -> None:
        self.feed_capture(bytes(indata))

    def feed_capture(self, raw: bytes) -> None:
        """Process one raw block from the device (any thread): pick the board's processed channel, resample to 16 kHz,
        hand 16-bit mono to the satellite on the loop thread. Public so tests can inject audio."""
        x = pick_channel(raw, self.profile.capture_channels, self.profile.capture_channel).astype(np.float32)
        pcm = np.clip(self._down.process(x), -32768, 32767).astype(np.int16).tobytes()
        if pcm and self._on_chunk and self._loop:
            self._loop.call_soon_threadsafe(self._on_chunk, pcm)

    # ---- playback ----

    def set_volume(self, volume: float) -> None:
        self.mixer.set_volume(volume)

    def stop_playback(self, bus: str | None = None) -> None:
        for b in (bus,) if bus else tuple(self._plays):
            for t in list(self._plays[b]):
                t.cancel()
            for proc in list(self._procs[b]):
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
            self.mixer.clear(b)

    async def play(self, source: str, bus: str = "announce") -> bool:
        if self._on_chunk is None:
            return False                                       # not started: nothing is pulling the mixer, so it would never drain
        task = asyncio.current_task()
        self._plays[bus].add(task)
        try:
            if source.startswith("sound:"):
                name = source[6:]
                file = sounds.path(name)
                if file is None:                               # the file is missing: a placeholder tone, not silence
                    self.mixer.write(bus, sounds.render(name, self.profile.playback_rate), 1)
                elif not await self._decode(str(file), bus):
                    return False
            elif not await self._decode(source, bus):
                return False
            while self.mixer.playing(bus):
                await asyncio.sleep(0.02)
            return True
        except asyncio.CancelledError:
            self.mixer.clear(bus)
            return False
        finally:
            self._plays[bus].discard(task)

    async def _decode(self, source: str, bus: str) -> bool:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            log.error("ffmpeg is not installed: cannot play %s", source)
            return False
        rate = self.profile.playback_rate
        proc = await asyncio.create_subprocess_exec(
            ffmpeg, "-nostdin", "-loglevel", "error", "-i", source, "-f", "s16le", "-ac", "2", "-ar", str(rate), "-",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        self._procs[bus].add(proc)
        try:
            got = False
            while chunk := await proc.stdout.read(rate // 5 * 4):
                got = True
                self.mixer.write(bus, chunk, 2)
                while self.mixer.buffered_ms(bus) > 800:        # let a long stream trickle in, don't buffer all of it
                    await asyncio.sleep(0.05)
            await proc.wait()
            return got and proc.returncode == 0
        finally:
            self._procs[bus].discard(proc)
            if proc.returncode is None:
                proc.kill()
