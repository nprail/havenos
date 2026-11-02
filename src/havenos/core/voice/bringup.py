"""Bring-up check for a USB mic array on the Pi (TODO V0b). Run it on the device with the board plugged in:

    python -m havenos.core.voice.bringup list
    python -m havenos.core.voice.bringup check --profile xvf3800     # formats, then the playback-while-recording test
    python -m havenos.core.voice.bringup check --profile lite --wav loopback.wav

`check` records a few seconds of room, then plays a tone (48 kHz or 16 kHz, per profile) out of the board's own speaker
output while recording, and reports how much of it reached the processed capture channel. If the chip's echo canceller
works, the tone should be nearly gone from the capture. The numbers decide the assumption in spec 05 section 6: they are
the thing nobody has measured yet.
"""
from __future__ import annotations

import argparse
import math
import sys
import time
import wave

import numpy as np

from .audio import pick_channel
from .profiles import PROFILES, DeviceProfile, get_profile

TONE_HZ = 880.0


def dbfs(x: np.ndarray) -> float:
    rms = float(np.sqrt(np.mean(np.square(x.astype(np.float64))))) / 32768.0
    return 20 * math.log10(rms) if rms > 0 else -120.0


def tone_dbfs_at(x: np.ndarray, rate: int, hz: float = TONE_HZ) -> float:
    """Level of one frequency in `x` (a single-bin DFT), so room noise at other frequencies does not count as echo."""
    if len(x) == 0:
        return -120.0
    t = np.arange(len(x)) / rate
    c = np.abs(np.sum(x.astype(np.float64) / 32768.0 * np.exp(-2j * np.pi * hz * t))) * 2 / len(x)
    return 20 * math.log10(c) if c > 0 else -120.0


def verdict(played_dbfs: float, heard_before: float, heard_during: float) -> str:
    """How much of the played tone is left in the capture: the echo return loss, and a plain-words reading of it."""
    erl = played_dbfs - heard_during
    if heard_during <= max(heard_before, -90) + 3:
        return f"echo cancellation looks WORKING: the {TONE_HZ:.0f} Hz tone is at the noise floor (return loss > {erl:.0f} dB)"
    if erl >= 25:
        return f"echo cancellation looks PARTLY working (return loss {erl:.0f} dB): wake-while-playing will be marginal"
    return f"echo cancellation looks NOT working (return loss {erl:.0f} dB): use software AEC (spec 05 section 6.1)"


def list_devices() -> None:
    import sounddevice as sd
    for i, d in enumerate(sd.query_devices()):
        print(f"{i:3d}  in {d['max_input_channels']:2d}  out {d['max_output_channels']:2d}  {d['default_samplerate']:>7.0f} Hz  {d['name']}")


def find(profile: DeviceProfile) -> int:
    import sounddevice as sd
    for i, d in enumerate(sd.query_devices()):
        if profile.match.lower() in d["name"].lower() and d["max_input_channels"] and d["max_output_channels"]:
            return i
    raise SystemExit(f"no device matching {profile.match!r} with input and output; run `list`")


def check(profile: DeviceProfile, seconds: float, wav_path: str | None) -> int:
    import sounddevice as sd
    idx = find(profile) if profile.match else None
    print(f"device: {sd.query_devices(idx)['name']} (profile {profile.name})")
    for kind, rate, ch in (("input", profile.capture_rate, profile.capture_channels), ("output", profile.playback_rate, 2)):
        try:
            (sd.check_input_settings if kind == "input" else sd.check_output_settings)(idx, channels=ch, samplerate=rate, dtype="int16")
            print(f"  {kind}: {rate} Hz, {ch} ch  OK")
        except Exception as e:
            print(f"  {kind}: {rate} Hz, {ch} ch  FAILED ({e})")
            return 1
    state = {"pos": 0, "play": False}
    chunks: list[tuple[bool, np.ndarray]] = []
    prate = profile.playback_rate

    def out_cb(outdata, frames, _t, _s):
        if state["play"]:
            t = (state["pos"] + np.arange(frames)) / prate
            outdata[:] = (np.sin(2 * np.pi * TONE_HZ * t) * 0.3 * 32767).astype(np.int16)[:, None].repeat(2, axis=1).tobytes()
            state["pos"] += frames
        else:
            outdata[:] = bytes(frames * 4)

    def in_cb(indata, frames, _t, _s):
        chunks.append((state["play"], pick_channel(bytes(indata), profile.capture_channels, profile.capture_channel).copy()))

    with sd.RawOutputStream(samplerate=prate, channels=2, dtype="int16", device=idx, callback=out_cb), \
            sd.RawInputStream(samplerate=profile.capture_rate, channels=profile.capture_channels, dtype="int16", device=idx,
                              callback=in_cb):
        print(f"recording {seconds:.0f} s of room, then playing a tone for {seconds:.0f} s (keep quiet)...")
        time.sleep(seconds)
        state["play"] = True
        time.sleep(seconds)
        state["play"] = False
    rate = profile.capture_rate
    before = np.concatenate([c for p, c in chunks if not p][3:] or [np.zeros(1, np.int16)])           # skip the stream's start-up
    during = np.concatenate([c for p, c in chunks if p][1:] or [np.zeros(1, np.int16)])
    heard_before, heard_during = tone_dbfs_at(before, rate), tone_dbfs_at(during, rate)
    played = 20 * math.log10(0.3)
    print(f"room level {dbfs(before):.1f} dBFS; tone in capture before {heard_before:.1f} dBFS, during playback {heard_during:.1f} dBFS "
          f"(played at {played:.1f} dBFS)")
    print(verdict(played, heard_before, heard_during))
    if wav_path:
        allpcm = np.concatenate([c for _, c in chunks])
        with wave.open(wav_path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(allpcm.tobytes())
        print(f"wrote {wav_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    c = sub.add_parser("check")
    c.add_argument("--profile", default="xvf3800", choices=sorted(PROFILES))
    c.add_argument("--device", default="", help="sound device name substring (overrides the profile's)")
    c.add_argument("--seconds", type=float, default=4.0)
    c.add_argument("--wav", help="also save the capture (processed channel) to this file")
    args = ap.parse_args(argv)
    if args.cmd == "list":
        list_devices()
        return 0
    return check(get_profile(args.profile, device=args.device), args.seconds, args.wav)


if __name__ == "__main__":
    sys.exit(main())
