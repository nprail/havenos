"""The display's backlight, through Linux sysfs (`/sys/class/backlight/<name>/brightness`). No Qt.

`Backlight.find()` returns None where there is no backlight to drive (a Mac, an HDMI monitor); the interface then dims
in software instead. Levels are percentages: a perceptual curve (gamma) maps them to the panel's raw range, because a
PWM backlight looks far brighter at 30 % raw than at 30 % "felt". Changes ramp, so the screen fades instead of jumping.

Who decides the level is the core (`Core._display_level`): the user's brightness, scaled by an automatic factor that a
future ambient light sensor will supply. This module only puts a number on the panel.
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

SYSFS = Path("/sys/class/backlight")
FADE_STEP_S = 0.025


class Backlight:
    def __init__(self, path: Path, gamma: float = 1.8) -> None:
        self.path = Path(path)
        self.name = self.path.name
        self.gamma = max(1.0, gamma)
        self.max = max(1, int(self._read("max_brightness") or 255))
        self.level = self.percent_of(int(self._read("brightness") or self.max))     # where the panel is now, 0..100
        self._fade: asyncio.Task | None = None

    @classmethod
    def find(cls, setting: str = "auto", gamma: float = 1.8, root: Path = SYSFS) -> "Backlight | None":
        """`auto`: the first backlight there is. `none`: never. Otherwise a name under /sys/class/backlight or a path."""
        setting = (setting or "auto").strip()
        if setting.lower() in ("none", "off", "software"):
            return None
        if setting.lower() == "auto":
            found = sorted(p for p in root.glob("*") if (p / "brightness").exists()) if root.is_dir() else []
            path = found[0] if found else None
        else:
            path = Path(setting) if "/" in setting else root / setting
        if path is None or not (path / "brightness").exists():
            if setting.lower() != "auto":
                log.warning("backlight %r not found", setting)
            return None
        if not os.access(path / "brightness", os.W_OK):
            log.warning("backlight %s is not writable by this user (see deploy/90-havenos-backlight.rules); dimming in software", path.name)
            return None
        return cls(path, gamma)

    # ---- sysfs ------------------------------------------------------------------------------

    def _read(self, name: str) -> str:
        try:
            return (self.path / name).read_text().strip()
        except OSError:
            return ""

    def _write(self, name: str, value: int) -> bool:
        try:
            (self.path / name).write_text(str(value))
            return True
        except OSError as e:
            log.warning("backlight: cannot write %s: %s", name, e)
            return False

    # ---- levels -----------------------------------------------------------------------------

    def raw_of(self, percent: float) -> int:
        """0 is off. Anything above it is at least raw 1, so the lowest setting is dim, not dark."""
        p = min(100.0, max(0.0, percent))
        if p <= 0:
            return 0
        return max(1, round(self.max * (p / 100.0) ** self.gamma))

    def percent_of(self, raw: int) -> float:
        return 100.0 * (min(self.max, max(0, raw)) / self.max) ** (1.0 / self.gamma)

    def set(self, percent: float) -> None:
        """Put `percent` on the panel now."""
        self.level = min(100.0, max(0.0, percent))
        raw = self.raw_of(self.level)
        if raw > 0:
            self._write("bl_power", 0)          # panels with a power switch: on before the light comes up
        self._write("brightness", raw)
        if raw == 0:
            self._write("bl_power", 4)          # FB_BLANK_POWERDOWN: off for real

    async def _ramp(self, to: float, ms: int) -> None:
        start, steps = self.level, max(1, int(ms / 1000 / FADE_STEP_S))
        for i in range(1, steps + 1):
            self.set(start + (to - start) * i / steps)
            await asyncio.sleep(FADE_STEP_S)

    def fade_to(self, percent: float, ms: int = 400) -> None:
        """Go to `percent` over `ms` (a new target replaces a fade in progress)."""
        if self._fade and not self._fade.done():
            self._fade.cancel()
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            self.set(percent)
            return
        if ms <= 0 or abs(percent - self.level) < 1:
            self.set(percent)
            return
        self._fade = asyncio.ensure_future(self._ramp(percent, ms))

    def close(self) -> None:
        if self._fade and not self._fade.done():
            self._fade.cancel()
