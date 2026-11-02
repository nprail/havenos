from __future__ import annotations

import asyncio
import time


def rss_mb() -> float:
    try:
        with open("/proc/self/status") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024.0
    except OSError:
        pass
    try:  # macOS / other: ru_maxrss (peak, not current; good enough for a dev HUD)
        import resource
        import sys
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return peak / (1024.0 * 1024.0) if sys.platform == "darwin" else peak / 1024.0
    except Exception:
        return 0.0


class LoopLagMonitor:
    """Measures how late a 50 ms sleep wakes up = how long the shared Qt/asyncio thread was busy.
    This is the spec's 'no GUI-thread call over 10 ms' check (gate G2)."""

    PERIOD = 0.05

    def __init__(self, window_s: float = 5.0) -> None:
        self._window = window_s
        self._samples: list[tuple[float, float]] = []   # (t, lag_ms)

    async def run(self) -> None:
        while True:
            t0 = time.monotonic()
            await asyncio.sleep(self.PERIOD)
            now = time.monotonic()
            self.add(now, max(0.0, (now - t0 - self.PERIOD) * 1000.0))

    def add(self, now: float, lag_ms: float) -> None:
        self._samples.append((now, lag_ms))
        cutoff = now - self._window
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.pop(0)

    @property
    def worst_ms(self) -> float:
        return max((s[1] for s in self._samples), default=0.0)

    @property
    def slow_count(self) -> int:
        return sum(1 for s in self._samples if s[1] > 10.0)
