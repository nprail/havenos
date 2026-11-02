"""Timer bookkeeping. Pure data + a caller-supplied clock, so it is trivial to test."""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class Timer:
    id: int
    label: str
    total: int      # seconds
    end: int        # epoch ms (while paused: meaningless; use `left`)
    paused: bool = False
    left: int = 0   # seconds remaining while paused
    local: bool = True   # False: Home Assistant owns it (a voice timer), so the display can cancel it but not pause or extend it

    def to_dict(self) -> dict:
        return asdict(self)


class TimerBook:
    def __init__(self) -> None:
        self._timers: list[Timer] = []
        self._next_id = 1

    def add(self, seconds: int, label: str, now_ms: int, total: int | None = None) -> Timer:
        """`total` is the original length when `seconds` is only what is left (a timer started elsewhere)."""
        t = Timer(self._next_id, label, total if total is not None else seconds, now_ms + seconds * 1000)
        self._next_id += 1
        self._timers.append(t)
        return t

    def get(self, timer_id: int) -> Timer | None:
        return next((t for t in self._timers if t.id == timer_id), None)

    def set_left(self, timer_id: int, seconds: int, now_ms: int, label: str | None = None, total: int | None = None) -> bool:
        t = self.get(timer_id)
        if t is None:
            return False
        t.end, t.left = now_ms + seconds * 1000, seconds
        if label is not None:
            t.label = label
        if total is not None:
            t.total = total
        return True

    def pause(self, timer_id: int, now_ms: int) -> bool:
        t = self.get(timer_id)
        if t is None or t.paused:
            return t is not None
        t.left, t.paused = max(0, -(-(t.end - now_ms) // 1000)), True            # ceil, like the countdown shows
        return True

    def resume(self, timer_id: int, now_ms: int) -> bool:
        t = self.get(timer_id)
        if t is None or not t.paused:
            return t is not None
        t.end, t.paused = now_ms + t.left * 1000, False
        return True

    def extend(self, timer_id: int, seconds: int, now_ms: int) -> bool:
        """Add time (the original length grows too, so the ring stays a fraction of 1)."""
        t = self.get(timer_id)
        if t is None:
            return False
        t.total += seconds
        if t.paused:
            t.left += seconds
        else:
            t.end += seconds * 1000
        return True

    def cancel(self, timer_id: int) -> bool:
        before = len(self._timers)
        self._timers = [t for t in self._timers if t.id != timer_id]
        return len(self._timers) != before

    def pop_expired(self, now_ms: int) -> Timer | None:
        for t in self._timers:
            if not t.paused and t.end <= now_ms:
                self._timers.remove(t)
                return t
        return None

    def snapshot(self) -> list[dict]:
        return [t.to_dict() for t in self._timers]
