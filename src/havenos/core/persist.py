"""Writes runtime changes to the settings that belong in config.toml, so a value changed from Home Assistant (or the HUD)
survives a restart. Debounced: dragging a slider in HA produces one write, not dozens.

Only display preferences persist. Moment-to-moment state (screen on/off, mode, current photo) deliberately does not:
the display should always boot awake, on the ambient screen.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from . import settings as st
from .core import Core
from .events import Event

log = logging.getLogger(__name__)

# state key -> (config table, key, normaliser)
PERSISTED: dict[str, tuple[str, str, Callable[[Any], Any]]] = {
    "photo_interval_s": ("display", "photo_interval_s", float),
    "crossfade_ms": ("display", "crossfade_ms", int),
    "brightness": ("display", "brightness", int),
    "blur": ("display", "blur", bool),
    "voice_wake_sound": ("voice", "wake_sound", bool),            # only written when voice is on
    "voice_sensitivity": ("voice", "sensitivity", str),
    "voice_wake_words": ("voice", "wake_words", list),
}


class SettingsPersister:
    def __init__(self, core: Core, *, delay: float = 1.0) -> None:
        self.core = core
        self._delay = delay
        self._handle: asyncio.TimerHandle | None = None
        self._unsub: Callable[[], None] | None = None

    def start(self) -> None:
        self._unsub = self.core.bus.subscribe(self._on_event)

    def stop(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None
        if self._handle:                       # don't lose a change made just before shutdown
            self._handle.cancel()
            self._handle = None
            self.flush()

    def _on_event(self, ev: Event) -> None:
        if ev.type != "state.patch" or not (PERSISTED.keys() & ev.data["patch"].keys()):
            return
        if self._handle:
            self._handle.cancel()
        self._handle = asyncio.get_running_loop().call_later(self._delay, self._flush_timer)

    def _flush_timer(self) -> None:
        self._handle = None
        self.flush()

    def flush(self) -> bool:
        """Write any setting whose current value differs from the file. Returns True if the file changed."""
        path = self.core.config.config_path
        try:
            toml = st.read_toml(path)
            changed = False
            for key, (table, name, norm) in PERSISTED.items():
                if table == "voice" and self.core.voice is None:
                    continue
                value = norm(self.core.state[key])
                node = toml.setdefault(table, {})
                if name not in node or norm(node[name]) != value:
                    node[name] = value
                    changed = True
            if changed:
                st.write_toml(path, toml)
                log.info("saved display settings to %s", path)
            return changed
        except Exception:                      # a read-only disk must not take the display down
            log.exception("could not save settings to %s", path)
            return False
