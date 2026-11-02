"""Spotify Connect source (docs/specs/07-music-pipeline.md section 3): havenOS appears as a Spotify Connect device.

The protocol work is done by `go-librespot`, which this adapter runs as a child process (or talks to as an already-running
daemon, `manage_process=False`, which is how the Pi's systemd unit will do it):

  - events and state: go-librespot's local WebSocket `/events` and `GET /status`
  - control: its HTTP API (`/player/pause`, `/player/seek`, ...)
  - audio: its `pipe` backend, a FIFO of 16-bit stereo PCM that we read and hand to an audio sink

Login is Spotify Connect's own zeroconf flow: pick the device once in the Spotify app (Premium required); go-librespot
keeps the credentials.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any

import aiohttp

from ... import childproc
from .pipe_audio import PipeAudio
from .base import (Availability, Capabilities, Metadata, Notice, Playback, Position, SessionEnded, SessionStarted, SourceAdapter,
                   Volume)

log = logging.getLogger(__name__)

API_PORT = 3678
PIPE_RATE = 44100                     # what Spotify decodes to; go-librespot's pipe carries it as s16le stereo
ERROR_BURST = 3                       # this many playback errors within ERROR_WINDOW_S: stop instead of skipping on
ERROR_WINDOW_S = 10.0
COMMANDS = frozenset({"play", "pause", "next", "prev", "seek"})


class SpotifySource(SourceAdapter):
    id = "spotify"
    label = "Spotify"

    def __init__(
        self,
        name: str,
        state_dir: Path,
        *,
        api_port: int = API_PORT,
        binary: str | None = None,
        manage_process: bool = True,
        audio_sink: Any = None,
    ) -> None:
        super().__init__()
        self.name = name
        self.dir = Path(state_dir) / "spotify"
        self.api_port = api_port
        self.binary = binary or shutil.which("go-librespot") or ""
        self.manage_process = manage_process
        self.audio_sink = audio_sink
        self.pipe = self.dir / "audio.pipe"
        self._base = f"http://127.0.0.1:{api_port}"
        self._http: aiohttp.ClientSession | None = None
        self._tasks: list[asyncio.Task] = []
        self._proc: asyncio.subprocess.Process | None = None
        self._audio = PipeAudio(self.pipe, audio_sink, lambda: self.feed_on)
        self._session = False
        self._duration_ms = 0
        self._steps = 100
        self._errors: list[float] = []

    # ---- lifecycle ----------------------------------------------------------------------------

    async def start(self) -> None:
        self._http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5))
        if self.manage_process:
            if not self.binary:
                log.error("spotify: go-librespot not found (brew install go-librespot); Spotify Connect is off")
                self.emit(Availability(False))
                return
            self._write_config()
            self._tasks.append(asyncio.create_task(self._supervise(), name="spotify-daemon"))
        if self.audio_sink is not None:
            self._audio.open()
            self._tasks.append(asyncio.create_task(self._audio.run(), name="spotify-audio"))
        self._tasks.append(asyncio.create_task(self._events(), name="spotify-events"))

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        if self._proc is not None and self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), 5)
            except asyncio.TimeoutError:
                self._proc.kill()
        self._proc = None
        self._audio.close()
        if self._http is not None:
            await self._http.close()
        if self.audio_sink is not None and hasattr(self.audio_sink, "stop"):
            with contextlib.suppress(Exception):
                self.audio_sink.stop()

    def _write_config(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        q = json.dumps                              # a JSON string is a valid YAML scalar
        lines = [
            f"device_name: {q(self.name)}",
            "device_type: speaker",
            "zeroconf_enabled: true",
            "credentials:",
            "  type: zeroconf",
            "  zeroconf:",
            "    persist_credentials: true",
            "external_volume: true",                # havenOS owns the volume; go-librespot only reports and accepts it
            "server:",
            "  enabled: true",
            "  address: 127.0.0.1",
            f"  port: {self.api_port}",
        ]
        if self.audio_sink is not None:
            lines += ["audio_backend: pipe", f"audio_output_pipe: {q(str(self.pipe))}", "audio_output_pipe_format: s16le"]
        else:                                       # display/remote only: nothing plays from this process
            lines += ["audio_backend: pipe", "audio_output_pipe: /dev/null", "audio_output_pipe_format: s16le"]
        (self.dir / "config.yml").write_text("\n".join(lines) + "\n")

    async def _supervise(self) -> None:
        """Keep go-librespot running; restart it with a short backoff if it exits."""
        delay = 1.0
        while True:
            try:
                self._proc = childproc.register(await asyncio.create_subprocess_exec(
                    *childproc.die_with_parent(), self.binary, "--config_dir", str(self.dir),
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT))
            except OSError as e:
                log.error("spotify: could not start %s: %s", self.binary, e)
                self.emit(Availability(False))
                return
            log.info("spotify: go-librespot started (pid %s) as %r", self._proc.pid, self.name)
            assert self._proc.stdout is not None
            async for line in self._proc.stdout:
                log.info("go-librespot: %s", line.decode(errors="replace").rstrip())
            rc = await self._proc.wait()
            childproc.unregister(self._proc)
            log.warning("spotify: go-librespot exited (%s); restarting in %.0fs", rc, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30.0)

    # ---- audio: pipe -> sink (see pipe_audio.py) ----

    def set_feed(self, on: bool) -> None:
        super().set_feed(on)
        if not on and self.audio_sink is not None:
            self.audio_sink.clear()

    # ---- go-librespot -> coordinator ----------------------------------------------------------

    async def _events(self) -> None:
        backoff = 1.0
        while True:
            try:
                async with self._http.ws_connect(self._base + "/events", heartbeat=30, timeout=5) as ws:
                    backoff = 1.0
                    self.emit(Availability(True))
                    self.emit(Capabilities(COMMANDS))
                    await self._sync_status()
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            self._on_event(json.loads(msg.data))
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            break
            except asyncio.CancelledError:
                raise
            except (aiohttp.ClientError, OSError, asyncio.TimeoutError, ValueError):
                pass
            self._end_session()
            self.emit(Availability(False))
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 10.0)

    async def _sync_status(self) -> None:
        """Catch up on a session that was already running when we connected."""
        try:
            async with self._http.get(self._base + "/status") as r:
                if r.status != 200:
                    return
                st = await r.json()
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            return
        self._steps = int(st.get("volume_steps") or 100)
        self._begin_session()
        if st.get("track"):
            self._metadata(st["track"])
        self.emit(Volume(self._level(st.get("volume", 0)), False))
        self.emit(Playback("stopped" if st.get("stopped") else "paused" if st.get("paused")
                           else "buffering" if st.get("buffering") else "playing"))

    def _begin_session(self) -> None:
        if not self._session:
            self._session = True
            self.emit(SessionStarted(None))

    def _end_session(self) -> None:
        if self._session:
            self._session = False
            if self.audio_sink is not None:
                self.audio_sink.clear()
            self.emit(SessionEnded())

    def _level(self, value: int) -> int:
        return round(100 * int(value) / max(1, self._steps))

    def _metadata(self, d: dict) -> None:
        self._duration_ms = int(d.get("duration") or 0)
        self.emit(Metadata(title=d.get("name") or "", artist=", ".join(d.get("artist_names") or []),
                           album=d.get("album_name") or "", art_uri=d.get("album_cover_url") or "",
                           duration=self._duration_ms / 1000.0 or None))
        if d.get("position") is not None:
            self.emit(Position(int(d["position"]) / 1000.0))

    def _on_event(self, msg: dict) -> None:
        kind, d = msg.get("type"), msg.get("data") or {}
        if kind == "active":
            self._begin_session()
        elif kind == "inactive":
            self._end_session()
        elif kind == "metadata":
            self._begin_session()
            self._metadata(d)
        elif kind == "playing":
            self._begin_session()
            self.emit(Playback("playing"))
        elif kind == "paused":
            self.emit(Playback("paused"))
        elif kind in ("not_playing", "stopped"):
            self.emit(Playback("stopped"))
        elif kind == "seek":
            self.emit(Position(int(d.get("position") or 0) / 1000.0))
        elif kind == "volume":
            self._steps = int(d.get("max") or self._steps)
            self.emit(Volume(self._level(d.get("value", 0)), False))
        elif kind == "playback_error":
            self._on_playback_error(d)

    def _on_playback_error(self, d: dict) -> None:
        """go-librespot skips an unplayable track and tries the next, so a Spotify that refuses everything (typically an
        account that is not Premium, or one that is rate limited) races through the whole queue and earns a 429 on the
        account. After a short burst, stop playback and say why."""
        log.warning("spotify: playback error: %s", d.get("message") or d)
        now = time.monotonic()
        self._errors = [t for t in self._errors if now - t < ERROR_WINDOW_S] + [now]
        if len(self._errors) >= ERROR_BURST:
            self._errors = []
            asyncio.get_running_loop().create_task(self._post("/player/stop"))
            self.emit(Notice("Spotify refused to play (it would not release the audio). Spotify Connect needs a Premium "
                             "account; if you have one, wait a few minutes and try again.", "Spotify"))

    # ---- coordinator -> go-librespot ----------------------------------------------------------

    async def _post(self, path: str, body: dict | None = None) -> bool:
        try:
            async with self._http.post(self._base + path, json=body or {}) as r:
                if r.status >= 400:
                    log.warning("spotify: %s -> HTTP %s", path, r.status)
                return r.status < 400
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
            log.warning("spotify: %s failed: %s", path, e)
            return False

    async def command(self, name: str, **args: Any) -> None:
        if name == "play":
            await self._post("/player/resume")
        elif name == "pause":
            await self._post("/player/pause")
        elif name == "next":
            await self._post("/player/next")
        elif name == "prev":
            await self._post("/player/prev")
        elif name == "seek":
            await self._post("/player/seek", {"position": int(float(args["seconds"]) * 1000)})

    async def release(self) -> None:
        """Evicted: stop playback and drop the Connect session (so the Spotify app shows the device as idle), and make
        sure none of its audio reaches the speaker."""
        if self.audio_sink is not None:
            self.audio_sink.clear()
        await self._post("/player/stop")

    async def set_volume(self, level: int, muted: bool) -> None:
        if self.audio_sink is not None and hasattr(self.audio_sink, "set_volume"):
            self.audio_sink.set_volume(level, muted)
        await self._post("/player/volume", {"volume": round(level * self._steps / 100)})
