"""Audio device profiles: what the voice code needs to know about the USB mic array it is talking to (spec 05 section 6).

Both supported boards are USB Audio Class 2.0 devices with an XMOS DSP that does echo cancellation, noise suppression and
gain before we see the audio, and a speaker output we play to so the chip can cancel it. They differ in rate and channels.
"""
from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class DeviceProfile:
    name: str
    match: str                  # substring of the sound device's name, used to find it
    capture_rate: int           # Hz
    capture_channels: int
    capture_channel: int        # which channel carries the board's processed (post-AEC) speech
    playback_rate: int          # Hz; everything (TTS, chimes, timers, music) plays at this rate
    playback_channels: int = 2
    hw_aec: bool = True         # the chip cancels what we play to it (assumed; confirmed in bring-up V0b)


# XVF3800 with the `48k2ch` USB firmware. UNVERIFIED: which of the two channels is the processed one. Seeed's wiki
# names channel 1 "ASR" for its I2S build; check with the bring-up script and set `capture_channel` if USB differs.
XVF3800 = DeviceProfile("xvf3800", "reSpeaker XVF3800", capture_rate=48000, capture_channels=2, capture_channel=1,
                        playback_rate=48000)
# ReSpeaker Lite with the USB firmware (v2.0.7): 16 kHz only, so music through it is telephone quality (accepted).
LITE = DeviceProfile("lite", "ReSpeaker Lite", capture_rate=16000, capture_channels=1, capture_channel=0,
                     playback_rate=16000)
# Whatever the system default is (a Mac for development): no hardware AEC to assume.
DEFAULT = DeviceProfile("default", "", capture_rate=16000, capture_channels=1, capture_channel=0, playback_rate=48000,
                        hw_aec=False)

PROFILES = {p.name: p for p in (XVF3800, LITE, DEFAULT)}


def get_profile(name: str, *, device: str = "") -> DeviceProfile:
    """The named profile (unknown names fall back to the default with a clear error from the caller's log), with the
    device-name substring overridden when the user set one."""
    profile = PROFILES.get((name or "default").lower())
    if profile is None:
        raise ValueError(f"unknown voice profile {name!r} (use one of: {', '.join(PROFILES)})")
    return replace(profile, match=device) if device else profile
