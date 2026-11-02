"""Play a URL that Home Assistant sends to the display's media_player (`media_player.play_media`).

A music source like the others: starting to play takes the speaker, the arbiter shows the takeover toast, and anything else
that starts playing later takes it back. ffmpeg decodes the URL (HTTP stream or file) to 48 kHz stereo PCM, which is
fed to the same interim sound-device sink the other sources use, at playback speed. Announcements are not this: they
go through the voice satellite on the announce bus (docs/specs/05).
"""
from __future__ import annotations

import asyncio
import logging
import shutil
from typing import Any
from urllib.parse import unquote, urlparse

from .base import (Availability, Capabilities, Metadata, Notice, Playback, Position, SessionEnded, SessionStarted,
                   SourceAdapter)

log = logging.getLogger(__name__)

RATE, FRAME = 48000, 4                      # 16-bit stereo
TARGET_BUFFER_MS = 300                      # read only while the sink holds less than this: paces ffmpeg at playback speed
CHUNK = RATE * FRAME // 20                  # 50 ms
DRAIN_TIMEOUT_S = 30.0


def title_from(url: str) -> str:
    name = unquote(urlparse(url).path.rsplit("/", 1)[-1])
    return name.rsplit(".", 1)[0] if "." in name else name


class UrlSource(SourceAdapter):
    id = "homeassistant"
    label = "Home Assistant"

    def __init__(self, audio_sink: Any, *, prebuffer_ms: int = 150) -> None:
        super().__init__()
        self.audio_sink = audio_sink
        self._prebuffer_ms = prebuffer_ms
        self._ffmpeg = shutil.which("ffmpeg")
        self._task: asyncio.Task | None = None
        self._proc: asyncio.subprocess.Process | None = None
        self._paused = False

    async def start(self) -> None:
        self.emit(Availability(self._ffmpeg is not None and self.audio_sink is not None))

    async def stop(self) -> None:
        await self._halt()
        if self.audio_sink is not None and hasattr(self.audio_sink, "stop"):
            self.audio_sink.stop()

    # ---- playing ----

    async def play_url(self, url: str, title: str = "") -> None:
        if self.audio_sink is None or self._ffmpeg is None:
            self.emit(Notice("There is no audio output to play that on." if self.audio_sink is None else
                             "ffmpeg is not installed, so Home Assistant media cannot be played.", "Home Assistant"))
            return
        await self._halt()
        self._paused = False
        self.emit(SessionStarted("Home Assistant"))
        self.emit(Capabilities(frozenset({"play", "pause"})))
        self.emit(Metadata(title or title_from(url) or "Home Assistant media"))
        self.emit(Position(0.0))
        self.emit(Playback("playing"))
        self._task = asyncio.create_task(self._run(url), name="ha-url-audio")

    async def _halt(self) -> None:
        task, self._task = self._task, None
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self._kill()
        if self.audio_sink is not None:
            self.audio_sink.clear()

    def _kill(self) -> None:
        proc, self._proc = self._proc, None
        if proc is not None and proc.returncode is None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass

    async def _run(self, url: str) -> None:
        try:
            self._proc = proc = await asyncio.create_subprocess_exec(
                self._ffmpeg, "-nostdin", "-loglevel", "error", "-i", url, "-f", "s16le", "-ac", "2", "-ar", str(RATE), "-",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            got = False
            while chunk := await proc.stdout.read(CHUNK):
                got = True
                while self._paused:
                    await asyncio.sleep(0.05)
                if self.feed_on:
                    while self.audio_sink.buffered_ms() >= TARGET_BUFFER_MS:
                        await asyncio.sleep(0.02)
                    self.audio_sink.write(0, chunk, None)
                else:                                       # another source owns the speaker: drop, at playback speed
                    await asyncio.sleep(len(chunk) / (RATE * FRAME))
            await proc.wait()
            if not got or proc.returncode:
                self.emit(Notice(f"Could not play {title_from(url) or 'that media'} from Home Assistant.", "Home Assistant"))
                self.emit(SessionEnded())
                return
            await self._drain()
            self.emit(Playback("stopped"))
            self.emit(SessionEnded())
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("playing %s failed", url)
            self.emit(SessionEnded())
        finally:
            self._kill()

    async def _drain(self) -> None:
        """Let the last of the audio play out. A clip shorter than the sink's prebuffer is padded so it starts at all."""
        if self.feed_on:
            self.audio_sink.write(0, bytes(RATE * FRAME * self._prebuffer_ms // 1000), None)
        waited = 0.0
        while self.feed_on and self.audio_sink.buffered_ms() > 30 and waited < DRAIN_TIMEOUT_S:
            await asyncio.sleep(0.05)
            waited += 0.05

    # ---- the contract ----

    async def command(self, name: str, **args) -> None:
        if name == "pause":
            self._paused = True
            self.audio_sink.clear()                        # prompt: at most the buffered 300 ms is dropped
            self.emit(Playback("paused"))
        elif name == "play":
            self._paused = False
            self.emit(Playback("playing"))

    async def release(self) -> None:
        self._paused = True
        if self.audio_sink is not None:
            self.audio_sink.clear()
        self.emit(Playback("paused"))

    async def set_volume(self, level: int, muted: bool) -> None:
        if self.audio_sink is not None and hasattr(self.audio_sink, "set_volume"):
            self.audio_sink.set_volume(level, muted)
