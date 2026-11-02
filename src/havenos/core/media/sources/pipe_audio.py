"""Audio from a daemon's named pipe to a sink, at playback speed. Shared by the sources that run an external receiver
(go-librespot, shairport-sync) and get raw PCM through a FIFO."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Callable

PUMP_S = 0.04
TARGET_BUFFER_MS = 300     # read only while the sink holds less than this: a full pipe blocks the daemon's writes, which
                           # paces it at playback speed (and keeps pause prompt, with at most this much audio still queued)


class PipeAudio:
    def __init__(self, path: Path, sink: Any, live: Callable[[], bool]) -> None:
        self.path = Path(path)
        self.sink = sink
        self.live = live                 # False: another source owns the speaker; read and drop instead of playing
        self.fds: list[int] = []

    def open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            os.mkfifo(self.path, 0o600)
        # Read end without blocking, plus a write end of our own so the pipe never reports EOF between tracks.
        self.fds = [os.open(self.path, os.O_RDONLY | os.O_NONBLOCK), os.open(self.path, os.O_WRONLY | os.O_NONBLOCK)]

    def close(self) -> None:
        for fd in self.fds:
            try:
                os.close(fd)
            except OSError:
                pass
        self.fds = []

    async def run(self) -> None:
        rd = self.fds[0]
        while True:
            for _ in range(64):
                live = self.live()
                if live and self.sink.buffered_ms() >= TARGET_BUFFER_MS:
                    break
                try:
                    data = os.read(rd, 16384)
                except BlockingIOError:
                    break
                except OSError:
                    return
                if not data:
                    break
                if live:
                    self.sink.write(0, data, None)
            await asyncio.sleep(PUMP_S)
