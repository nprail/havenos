"""The satellite's sounds. The real ones are the Voice Preview Edition's (CC BY 4.0, attribution in
assets/sounds/ATTRIBUTION.md); if a file is missing, a short synthesized tone stands in so nothing goes silent.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

ASSETS = Path(__file__).resolve().parents[2] / "assets" / "sounds"
FILES = {"wake": "wake_word_triggered.flac", "timer": "timer_finished.flac", "mute_on": "mute_switch_on.flac",
         "mute_off": "mute_switch_off.flac", "cloud_expired": "error_cloud_expired.mp3"}

_NOTES = {
    "wake": [(880.0, 0.09), (1175.0, 0.12)],            # rising two-note ping
    "timer": [(1046.0, 0.10), (0.0, 0.05), (1046.0, 0.10), (0.0, 0.05), (1046.0, 0.10)],
    "mute_on": [(660.0, 0.08), (440.0, 0.12)],
    "mute_off": [(440.0, 0.08), (660.0, 0.12)],
    "cloud_expired": [(330.0, 0.18), (247.0, 0.25)],
}


def sound_names() -> list[str]:
    return list(FILES)


def path(name: str) -> Path | None:
    """The sound's file, or None when it is not there (then `render` is used)."""
    p = ASSETS / FILES[name]
    return p if p.is_file() else None


def render(name: str, rate: int) -> bytes:
    """The placeholder tone for `name` as 16-bit mono PCM at `rate`."""
    parts = []
    for freq, secs in _NOTES[name]:
        t = np.arange(int(rate * secs)) / rate
        tone = np.sin(2 * np.pi * freq * t) if freq else np.zeros_like(t)
        fade = np.minimum(1.0, np.minimum(t / 0.01, (secs - t) / 0.02)).clip(0)
        parts.append(tone * fade)
    wave = np.concatenate(parts) * 0.45
    return (wave * 32767).astype(np.int16).tobytes()
