"""The one output device and the sinks that feed it (docs/specs/05 section 4, docs/specs/07 section 5).

`AudioHub` owns the `Mixer` and the sound device. The voice side writes to its announce bus; every music source gets a
`BusSink` that resamples to the mixer's rate and writes to its own stream on the media bus. Ducking is the mixer's (20 dB
at once, a second to come back), so music and announcements share one clock and the mixer output is the exact echo
reference for software AEC.

Modes: "device" plays to the sound device; "null" discards (headless development); "capture" keeps the output in
`captured`, ten times faster than real time (tests).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from .mixer import Mixer, Stream
from .resample import Resampler

log = logging.getLogger(__name__)
CHANNELS = 2


def candidates(sd: Any, match: str | int | None) -> list[int | None]:
    """Output devices to try, best first. A named device (config) is the only candidate. Otherwise the system default when
    it can do stereo (a Bluetooth headset in call mode is mono), then every other stereo output until one starts."""
    devices = sd.query_devices()
    if isinstance(match, str) and match:
        found = [i for i, d in enumerate(devices)
                 if match.lower() in d["name"].lower() and d["max_output_channels"] >= CHANNELS]
        if not found:
            raise RuntimeError(f"no stereo output device matching {match!r}")
        return found
    if match is not None and not isinstance(match, str):
        return [match]
    out: list[int | None] = []
    if sd.query_devices(kind="output")["max_output_channels"] >= CHANNELS:
        out.append(None)
    out += [i for i, d in enumerate(devices) if d["max_output_channels"] >= CHANNELS]
    return out


_ALSA_ALIASES = {"default", "sysdefault", "lavrate", "samplerate", "speexrate", "speex", "upmix", "vdownmix", "dmix", "dsnoop",
                 "front", "iec958", "spdif", "null", "pulse", "jack", "oss"}


def output_choices(sd: Any) -> list[dict[str, str]]:
    """The outputs worth offering in settings: real stereo hardware, by a name that survives a reboot. `value` is what goes
    in config (`audio_device` matches it as a substring); `label` is what the person sees. On ALSA the hardware devices
    are named like "bcm2835 Headphones: - (hw:0,0)", where the card number can change between boots, so it is dropped.
    The ALSA plugin aliases (sysdefault, upmix, ...) are hidden; "System default" is the caller's own first entry."""
    import re
    seen: dict[str, str] = {}
    devices = [d for d in sd.query_devices() if d["max_output_channels"] >= CHANNELS]
    hardware = [d for d in devices if "(hw:" in d["name"]]
    for d in hardware or [d for d in devices if d["name"].lower() not in _ALSA_ALIASES]:
        name = re.sub(r"\s*\(hw:\d+,\d+\)\s*$", "", d["name"]).strip()
        if name:
            seen.setdefault(name, name.rstrip(":- ").strip() or name)
    return [{"value": v, "label": l} for v, l in seen.items()]


class AudioHub:
    def __init__(self, rate: int = 48000, *, mode: str = "device", match: str | int | None = None, duck_db: float = -20.0,
                 volume: float = 1.0) -> None:
        self.mixer = Mixer(rate, volume=volume, duck_db=duck_db)
        self.mode, self.match = mode, match
        self.captured = bytearray()
        self._stream: Any = None
        self._pump: asyncio.Task | None = None
        self._started = False
        self._sinks: list[BusSink] = []

    @property
    def rate(self) -> int:
        return self.mixer.rate

    def start(self) -> None:
        """Open the output. Raises when there is no usable device (callers then run without audio)."""
        if self._started:
            return
        if self.mode == "device":
            self._open_device()
        else:
            self._pump = asyncio.get_running_loop().create_task(self._pump_output(), name="audio-pump")
        self._started = True

    def stop(self) -> None:
        for s in list(self._sinks):
            s.close()
        if self._pump:
            self._pump.cancel()
            self._pump = None
        self._close_device()
        self._started = False

    @property
    def started(self) -> bool:
        return self._started

    def set_match(self, match: str | int | None) -> None:
        """Move the output to another device while running (music sources keep their sinks; only the sound device
        changes). If the new device will not open, the old one is restored and the error raised."""
        if match == self.match:
            return
        old = self.match
        self.match = match
        if self.mode != "device" or not self._started:
            return
        self._close_device()
        try:
            self._open_device()
        except Exception:
            self.match = old
            try:
                self._open_device()
            except Exception:
                log.exception("audio: could not reopen the previous output either")
            raise

    def _close_device(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            finally:
                self._stream = None

    def test_tone(self, seconds: float = 1.0) -> None:
        """A short two-note chime on the media bus, so a person can hear which output they picked."""
        import numpy as np
        t = np.arange(int(self.rate * seconds)) / self.rate
        env = np.minimum(1.0, np.minimum(t, seconds - t) * 20) * 0.35
        half = t < seconds / 2
        wave = np.sin(2 * np.pi * np.where(half, 523.25, 659.25) * t) * env
        pcm = np.repeat((wave * 32767).astype(np.int16), CHANNELS).tobytes()
        self.start()
        sink = self.open(self.rate, 0)
        sink.write(0, pcm, None)
        asyncio.get_running_loop().call_later(seconds + 0.5, sink.close)

    def _open_device(self) -> None:
        import sounddevice as sd
        errors = []
        for device in candidates(sd, self.match):
            try:
                self._stream = sd.RawOutputStream(samplerate=self.rate, channels=CHANNELS, dtype="int16", device=device,
                                                  blocksize=self.rate // 50, callback=self._callback)
                self._stream.start()
            except sd.PortAudioError as e:
                errors.append(f"{sd.query_devices(device)['name'] if device is not None else 'default'}: {e}")
                self._stream = None
                continue
            log.info("audio: %d Hz stereo out to %r", self.rate,
                     sd.query_devices(device)["name"] if device is not None else sd.query_devices(kind="output")["name"])
            return
        raise RuntimeError("no usable stereo output device (" + "; ".join(errors) + ")")

    def _callback(self, outdata, frames: int, _time, _status) -> None:
        outdata[:] = self.mixer.read(frames)

    async def _pump_output(self) -> None:
        block = self.rate // 50
        while True:
            data = self.mixer.read(block)
            if self.mode == "capture":
                if self.mixer.peak > 0:
                    self.captured += data
                await asyncio.sleep(0.002)
            else:
                await asyncio.sleep(0.02)

    # ---- music sinks ----

    def open(self, rate: int = 48000, prebuffer_ms: int = 300) -> "BusSink":
        """A sink for one music source: PCM at `rate` (16-bit stereo) in, the media bus out."""
        sink = BusSink(self, rate, prebuffer_ms)
        self._sinks.append(sink)
        return sink


class BusSink:
    """What a music source writes to (the interface the old per-source sound-device sink had)."""

    def __init__(self, hub: AudioHub, rate: int, prebuffer_ms: int) -> None:
        self._hub = hub
        self.rate = rate
        self._stream: Stream = hub.mixer.open("media", prebuffer_ms)
        self._resampler: Resampler | None = None
        self._channels = CHANNELS
        self._warned = False
        self._set_rate(rate)

    def _set_rate(self, rate: int) -> None:
        self.rate = rate
        self._resampler = Resampler(rate, self._hub.rate) if rate != self._hub.rate else None

    # ---- called on the event loop ----

    def start(self) -> None:
        self._hub.start()

    def stop(self) -> None:
        self.close()

    def close(self) -> None:
        self._stream.close()
        if self in self._hub._sinks:
            self._hub._sinks.remove(self)

    def write(self, server_timestamp_us: int, data: bytes, fmt: Any) -> None:
        pcm = getattr(fmt, "pcm_format", None)
        if pcm is not None:
            if pcm.bit_depth != 16 or pcm.channels not in (1, 2):
                if not self._warned:
                    self._warned = True
                    log.warning("audio: %s is not 16-bit mono or stereo; dropping it", pcm)
                return
            if pcm.sample_rate != self.rate or pcm.channels != self._channels:
                self._channels = pcm.channels
                self._set_rate(pcm.sample_rate)
                self._stream.clear()
        if self._resampler is not None or self._channels != CHANNELS:
            self._write_converted(data)
        else:
            self._stream.write(data, CHANNELS)

    def _write_converted(self, data: bytes) -> None:
        import numpy as np
        if self._channels == 1:                                   # mono source: duplicate, then resample as stereo
            a = np.frombuffer(data, dtype=np.int16)
            data = np.repeat(a, 2).tobytes()
        if self._resampler is not None:
            if self._resampler.channels != CHANNELS:
                self._resampler = Resampler(self.rate, self._hub.rate, CHANNELS)
            self._stream.write_float(self._resampler.process_float(data))
        else:
            self._stream.write(data, CHANNELS)

    def buffered_ms(self) -> float:
        return self._stream.buffered_ms()

    def clear(self) -> None:
        self._stream.clear()

    def set_volume(self, level: int, muted: bool) -> None:
        self._stream.set_level(level, muted)

    def set_duck(self, db: float | None) -> None:
        """Lower the music while something else speaks; None or 0 restores it. (The mixer ducks the whole media bus.)"""
        self._hub.mixer.set_duck(bool(db), db if db else None)
