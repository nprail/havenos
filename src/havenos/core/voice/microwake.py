"""The real wake engine: microWakeWord (the VPE's detector) through `pymicro-wakeword`, with its bundled Okay Nabu, Hey
Jarvis and Hey Mycroft models. Needs `pip install havenos[voice]`; without it `build()` falls back to the null engine.

The per-model probability cutoffs are the VPE firmware's (spec 05 section 2.5), scaled from 0-255 to 0-1. The VPE's "stop"
model is not bundled with the package: point `[voice] stop_model` at its `.json` to enable the stop word, otherwise stopping
a timer or a reply is by button, tap or wake word. Not run on a Pi yet, so CPU is unmeasured (bring-up V2).
"""
from __future__ import annotations

import logging
from pathlib import Path

from . import wake as ww

log = logging.getLogger(__name__)
REFRACTORY_S = 2.0              # after a detection, the same word is ignored for this much audio (the model stays high for a while)


def available() -> bool:
    try:
        import pymicro_wakeword  # noqa: F401
        return True
    except ImportError:
        return False


class MicroWakeEngine:
    def __init__(self, stop_model: str = "") -> None:
        from pymicro_wakeword import MicroWakeWordFeatures
        self._features = MicroWakeWordFeatures()
        self._models: dict[str, object] = {}
        self._stop_path = Path(stop_model).expanduser() if stop_model else None
        self._stop: object | None = None
        self._stop_enabled = False
        self._active: tuple[str, ...] = ()
        self._sensitivity = ww.DEFAULT_SENSITIVITY
        self._clock = 0.0                          # seconds of audio fed so far (no wall clock: tests and replays stay exact)
        self._quiet_until: dict[str, float] = {}

    def configure(self, active: tuple[str, ...], sensitivity: str) -> None:
        from pymicro_wakeword import MicroWakeWord, Model
        self._active, self._sensitivity = tuple(active), sensitivity
        for word in list(self._models):
            if word not in active:
                del self._models[word]
        for word in active:
            if word not in self._models:
                self._models[word] = MicroWakeWord.from_builtin(Model(word))
            self._models[word].probability_cutoff = ww.cutoff(word, sensitivity) / 255.0

    def set_stop_enabled(self, enabled: bool) -> None:
        if enabled and self._stop is None and self._stop_path:
            from pymicro_wakeword import MicroWakeWord
            try:
                self._stop = MicroWakeWord.from_config(self._stop_path)
                self._stop.probability_cutoff = ww.STOP_CUTOFF / 255.0
            except Exception:
                log.exception("could not load the stop word model %s", self._stop_path)
                self._stop_path = None
        self._stop_enabled = enabled and self._stop is not None

    def feed(self, pcm: bytes) -> list[str]:
        heard: list[str] = []
        self._clock += len(pcm) / 32000.0
        for features in self._features.process_streaming(pcm):
            hits = [w for w, m in self._models.items() if m.process_streaming(features)]
            if self._stop_enabled and self._stop.process_streaming(features):
                hits.append(ww.STOP_WORD)
            for word in hits:
                if word not in heard and self._clock >= self._quiet_until.get(word, 0.0):
                    heard.append(word)
                    self._quiet_until[word] = self._clock + REFRACTORY_S
        return heard
