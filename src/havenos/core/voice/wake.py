"""Wake words, sensitivity and the wake-engine seam (spec 05 section 2.5).

The detector itself (microWakeWord with the VPE's models) plugs in behind `WakeEngine`. Until it is installed
`NullWakeEngine` never fires, so the satellite still works from the on-screen mic button.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class WakeWord:
    id: str
    label: str
    languages: tuple[str, ...] = ("en",)


# Same ids and names as the VPE, so Home Assistant's wake word selects look the same.
WAKE_WORDS = (WakeWord("okay_nabu", "Okay Nabu"), WakeWord("hey_jarvis", "Hey Jarvis"), WakeWord("hey_mycroft", "Hey Mycroft"))
DEFAULT_WAKE_WORDS = ("okay_nabu",)
MAX_ACTIVE = 2

SENSITIVITIES = ("Slightly sensitive", "Moderately sensitive", "Very sensitive")
DEFAULT_SENSITIVITY = "Moderately sensitive"
# probability cutoff (0-255) per model per sensitivity, straight from the VPE firmware
CUTOFFS = {"okay_nabu": (217, 176, 143), "hey_jarvis": (247, 235, 212), "hey_mycroft": (253, 242, 237)}
STOP_WORD = "stop"
STOP_CUTOFF = 200               # not in the firmware table we read; a conservative default until tuned on a Pi


def cutoff(word: str, sensitivity: str) -> int:
    return CUTOFFS[word][SENSITIVITIES.index(sensitivity)]


class WakeEngine(Protocol):
    """Fed 16 kHz s16 mono audio; returns the ids of any wake words (or `STOP_WORD`) heard in that chunk."""

    def feed(self, pcm: bytes) -> list[str]: ...
    def configure(self, active: tuple[str, ...], sensitivity: str) -> None: ...
    def set_stop_enabled(self, enabled: bool) -> None: ...


class NullWakeEngine:
    """Hears nothing. Stands in until microWakeWord is wired up (V2)."""

    def feed(self, pcm: bytes) -> list[str]:
        return []

    def configure(self, active: tuple[str, ...], sensitivity: str) -> None:
        pass

    def set_stop_enabled(self, enabled: bool) -> None:
        pass
