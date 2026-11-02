"""AirPlay source (docs/specs/07-music-pipeline.md section 3): havenOS as an AirPlay receiver, through `shairport-sync`.

shairport-sync does the protocol; this adapter runs it as a child process (or talks to one already running,
`manage_process=False`, which is how the Pi's systemd unit will do it) and connects three things:

  - audio: its `pipe` backend, 44.1 kHz 16-bit stereo PCM in a FIFO that we read (pipe_audio.py)
  - state:  its metadata pipe: title/artist/album, cover art, progress, volume, and play/pause/flush/end markers
  - control: DACP, the sender's own remote-control HTTP service, whose address shairport-sync reports in the metadata.
             Only senders that expose DACP (Apple Music, iTunes, iOS Music) can be controlled; others (Spotify, most
             third-party apps) are display-only.

The same adapter serves classic AirPlay (what the Mac build is) and AirPlay 2 (the Pi build): the difference is how
shairport-sync is compiled, not the pipes or the metadata.
"""
from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import logging
import os
import re
import shutil
import struct
from pathlib import Path
from typing import Any

import aiohttp

from .base import (Availability, Capabilities, Metadata, Playback, Position, SessionEnded, SessionStarted, SourceAdapter,
                   Volume)
from ... import childproc
from .pipe_audio import PipeAudio

log = logging.getLogger(__name__)

PORT = 7000
RATE = 44100
META_POLL_S = 0.05
DACP_COMMANDS = frozenset({"play", "pause", "next", "prev"})
AIRPLAY_MIN_DB, AIRPLAY_MUTE_DB = -30.0, -144.0
KEEP_COVERS = 6
ACTIVE_TIMEOUT_S = 300.0

_ITEM = re.compile(rb"<item><type>([0-9a-fA-F]{8})</type><code>([0-9a-fA-F]{8})</code><length>(\d+)</length>"
                   rb"(?:\s*<data encoding=\"base64\">(.*?)</data>)?\s*</item>", re.S)


def decode_items(buf: bytearray) -> list[tuple[str, str, bytes]]:
    """Pull complete metadata items off the front of `buf` (leaving any partial one) as (type, code, payload)."""
    out = []
    pos = 0
    for m in _ITEM.finditer(buf):
        raw = base64.b64decode(re.sub(rb"\s+", b"", m.group(4) or b""))
        out.append((bytes.fromhex(m.group(1).decode()).decode("latin-1"), bytes.fromhex(m.group(2).decode()).decode("latin-1"), raw))
        pos = m.end()
    del buf[:pos]
    if len(buf) > 4_000_000:            # junk that never forms an item: do not grow without bound
        buf.clear()
    return out


class AirPlaySource(SourceAdapter):
    id = "airplay"
    label = "AirPlay"

    def __init__(
        self,
        name: str,
        state_dir: Path,
        *,
        port: int = PORT,
        binary: str | None = None,
        manage_process: bool = True,
        audio_sink: Any = None,
    ) -> None:
        super().__init__()
        self.name = name
        self.dir = Path(state_dir) / "airplay"
        self.port = port
        self.binary = binary or shutil.which("shairport-sync") or ""
        self.manage_process = manage_process
        self.audio_sink = audio_sink
        self.audio_pipe = self.dir / "audio.pipe"
        self.meta_pipe = self.dir / "metadata.pipe"
        self._audio = PipeAudio(self.audio_pipe, audio_sink, lambda: self.feed_on)
        self._meta_fds: list[int] = []
        self._buf = bytearray()
        self._tasks: list[asyncio.Task] = []
        self._proc: asyncio.subprocess.Process | None = None
        self._http: aiohttp.ClientSession | None = None
        self._reset_session()

    def _reset_session(self) -> None:
        self._session = False
        self._playing = False
        self._client = self._ip = self._daid = self._acre = None
        self._dacp_port: int | None = None
        self._meta: dict[str, Any] = {}
        self._bundle: dict[str, Any] = {}
        self._cover = ""
        self._progress: tuple[int, int, int] | None = None

    # ---- lifecycle ----------------------------------------------------------------------------

    async def start(self) -> None:
        self._http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3))
        if self.manage_process and not self.binary:
            log.error("airplay: shairport-sync not found; AirPlay is off (see README: building it with pipe output)")
            self.emit(Availability(False))
            return
        self.dir.mkdir(parents=True, exist_ok=True)
        self._open_meta_pipe()
        if self.audio_sink is not None:
            self._audio.open()
            self._tasks.append(asyncio.create_task(self._audio.run(), name="airplay-audio"))
        self._tasks.append(asyncio.create_task(self._read_meta(), name="airplay-meta"))
        if self.manage_process:
            self._write_config()
            self._tasks.append(asyncio.create_task(self._supervise(), name="airplay-daemon"))
        else:
            self.emit(Availability(True))

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        await self._kill_daemon()
        self._audio.close()
        for fd in self._meta_fds:
            with contextlib.suppress(OSError):
                os.close(fd)
        self._meta_fds = []
        if self._http is not None:
            await self._http.close()
        if self.audio_sink is not None and hasattr(self.audio_sink, "stop"):
            with contextlib.suppress(Exception):
                self.audio_sink.stop()

    def _write_config(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        q = lambda v: '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'          # noqa: E731  libconfig string
        (self.dir / "shairport-sync.conf").write_text("\n".join([
            "general = {",
            f"  name = {q(self.name)};",
            f"  port = {self.port};",
            '  output_backend = "pipe";',
            '  ignore_volume_control = "yes";',            # havenOS owns the volume; the phone's slider is reported, not applied
            "};",
            "sessioncontrol = {",
            '  allow_session_interruption = "yes";',       # a new sender takes over from the current one: last to play wins
            f"  active_state_timeout = {ACTIVE_TIMEOUT_S};",  # how long a paused sender stays on the display before it is dropped
            "};",
            "pipe = {",
            f"  name = {q(self.audio_pipe)};",
            "};",
            "metadata = {",
            '  enabled = "yes";',
            '  include_cover_art = "yes";',
            f"  pipe_name = {q(self.meta_pipe)};",
            "  pipe_timeout = 5000;",
            "};",
        ]) + "\n")

    async def _supervise(self) -> None:
        delay = 1.0
        while True:
            try:
                self._proc = childproc.register(await asyncio.create_subprocess_exec(
                    *childproc.die_with_parent(), self.binary, "-c", str(self.dir / "shairport-sync.conf"), "-v",
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT))
            except OSError as e:
                log.error("airplay: could not start %s: %s", self.binary, e)
                self.emit(Availability(False))
                return
            log.info("airplay: shairport-sync started (pid %s) as %r on port %s", self._proc.pid, self.name, self.port)
            self.emit(Availability(True))
            started = asyncio.get_running_loop().time()
            assert self._proc.stdout is not None
            async for line in self._proc.stdout:
                log.info("shairport-sync: %s", line.decode(errors="replace").rstrip())
            rc = await self._proc.wait()
            childproc.unregister(self._proc)
            self._end_session()                                  # a dead receiver means no session
            self.emit(Availability(False))
            if asyncio.get_running_loop().time() - started > 30:
                delay = 1.0                                      # it ran for a while: this is a fresh failure, not a loop
            log.warning("airplay: shairport-sync exited (%s); restarting in %.0fs", rc, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30.0)

    async def _kill_daemon(self) -> None:
        proc = self._proc
        if proc is not None and proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), 5)
            except asyncio.TimeoutError:
                proc.kill()

    # ---- metadata pipe ------------------------------------------------------------------------

    def _open_meta_pipe(self) -> None:
        if not self.meta_pipe.exists():
            os.mkfifo(self.meta_pipe, 0o600)
        self._meta_fds = [os.open(self.meta_pipe, os.O_RDONLY | os.O_NONBLOCK),
                          os.open(self.meta_pipe, os.O_WRONLY | os.O_NONBLOCK)]

    async def _read_meta(self) -> None:
        rd = self._meta_fds[0]
        while True:
            try:
                while True:
                    chunk = os.read(rd, 65536)
                    if not chunk:
                        break
                    self._buf.extend(chunk)
            except BlockingIOError:
                pass
            except OSError:
                return
            for typ, code, data in decode_items(self._buf):
                try:
                    self._item(typ, code, data)
                except Exception:
                    log.exception("airplay: bad metadata item %s/%s", typ, code)
            await asyncio.sleep(META_POLL_S)

    def _item(self, typ: str, code: str, data: bytes) -> None:
        text = data.decode("utf-8", "replace")
        if typ == "ssnc" and code in ("abeg", "aend", "pbeg", "pend", "pfls", "prsm", "pffr", "paus", "snam"):
            log.info("airplay: %s %s", code, text if code == "snam" else "")
        if typ == "ssnc":
            if code == "snam":
                self._client = text
            elif code == "clip":
                self._ip = text
            elif code == "daid":
                self._daid = text
            elif code == "acre":
                self._acre = text
                self._capabilities()
            elif code == "dapo":
                with contextlib.suppress(ValueError):
                    self._dacp_port = int(text)
                self._capabilities()
            elif code == "pbeg":
                self._begin_session()
            elif code in ("pffr", "prsm"):
                self._begin_session()
                self._set_playing(True)
            elif code in ("pend", "pfls", "paus"):
                # Classic AirPlay ends the "play stream" on every pause, but the sender is still connected: the session
                # ends only when shairport-sync leaves its active state (`aend`, after active_state_timeout).
                self._set_playing(False)
            elif code == "abeg":
                self._begin_session()
            elif code == "aend":
                self._end_session()
            elif code == "mdst":
                self._bundle = {}
            elif code == "mden":
                self._meta.update(self._bundle)
                self._bundle = {}
                self._emit_metadata()
            elif code == "PICT":
                self._cover = self._save_cover(data)
                self._emit_metadata()
            elif code == "prgr":
                self._on_progress(text)
            elif code == "pvol":
                self._on_volume(text)
        elif typ == "core":
            if code == "minm":
                self._bundle["title"] = text
            elif code == "asar":
                self._bundle["artist"] = text
            elif code == "asal":
                self._bundle["album"] = text
            elif code == "astm" and len(data) == 4:
                self._bundle["duration"] = struct.unpack(">I", data)[0] / 1000.0

    # ---- metadata -> events -------------------------------------------------------------------

    def _begin_session(self) -> None:
        if not self._session:
            self._session = True
            self.emit(SessionStarted(self._client))
            self._capabilities()

    def _end_session(self) -> None:
        if self._session:
            if self.audio_sink is not None:
                self.audio_sink.clear()
            self.emit(SessionEnded())
        self._reset_session()

    def _set_playing(self, playing: bool) -> None:
        if playing != self._playing:
            self._playing = playing
            self.emit(Playback("playing" if playing else "paused"))

    def _capabilities(self) -> None:
        if self._session:
            ok = self._ip and self._acre and self._dacp_port
            self.emit(Capabilities(DACP_COMMANDS if ok else frozenset()))

    def _emit_metadata(self) -> None:
        m = self._meta
        duration = m.get("duration")
        if duration is None and self._progress:
            start, _cur, end = self._progress
            duration = (end - start) / RATE if end > start else None
        self.emit(Metadata(title=m.get("title", ""), artist=m.get("artist", ""), album=m.get("album", ""),
                           art_uri=self._cover, duration=duration))

    def _on_progress(self, text: str) -> None:
        try:
            start, cur, end = (int(x) for x in text.split("/"))
        except ValueError:
            return
        first = self._progress is None
        self._progress = (start, cur, end)
        if first and "duration" not in self._meta:
            self._emit_metadata()
        self.emit(Position(max(0, cur - start) / RATE))

    def _on_volume(self, text: str) -> None:
        """`airplay_volume,volume,lowest,highest` in dB: -30 (quietest) to 0, or -144 for mute."""
        try:
            db = float(text.split(",")[0])
        except ValueError:
            return
        if db <= AIRPLAY_MUTE_DB:
            self.emit(Volume(0, True))
        else:
            self.emit(Volume(round(100 * (min(0.0, max(AIRPLAY_MIN_DB, db)) - AIRPLAY_MIN_DB) / -AIRPLAY_MIN_DB), False))

    def _save_cover(self, data: bytes) -> str:
        """Cover art arrives as JPEG/PNG bytes; the UI loads it from a file."""
        if not data:
            return ""
        ext = "png" if data[:4] == b"\x89PNG" else "jpg"
        path = self.dir / f"cover-{hashlib.sha1(data).hexdigest()[:12]}.{ext}"
        if not path.exists():
            path.write_bytes(data)
            for old in sorted(self.dir.glob("cover-*"), key=lambda p: p.stat().st_mtime)[:-KEEP_COVERS]:
                with contextlib.suppress(OSError):
                    old.unlink()
        return path.as_uri()

    # ---- coordinator -> sender (DACP) ---------------------------------------------------------

    async def _dacp(self, cmd: str) -> bool:
        if not (self._ip and self._acre and self._dacp_port):
            return False
        url = f"http://{self._ip}:{self._dacp_port}/ctrl-int/1/{cmd}"
        try:
            async with self._http.get(url, headers={"Active-Remote": self._acre}) as r:
                if r.status >= 400:
                    log.warning("airplay: DACP %s -> HTTP %s", cmd, r.status)
                return r.status < 400
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
            log.warning("airplay: DACP %s failed: %s", cmd, e)
            return False

    async def command(self, name: str, **args: Any) -> None:
        if name == "play":
            await self._dacp("playpause")
        elif name == "pause":
            await self._dacp("pause")
        elif name == "next":
            await self._dacp("nextitem")
        elif name == "prev":
            await self._dacp("previtem")

    async def release(self) -> None:
        """Evicted: pause the sender if it lets us, then drop the session by restarting the receiver (our own process; the
        supervisor brings it straight back). The audio feed is deselected first, so nothing leaks while that happens."""
        if self.audio_sink is not None:
            self.audio_sink.clear()
        await self._dacp("pause")
        if self.manage_process:
            await self._kill_daemon()

    async def set_volume(self, level: int, muted: bool) -> None:
        if self.audio_sink is not None and hasattr(self.audio_sink, "set_volume"):
            self.audio_sink.set_volume(level, muted)

    def set_feed(self, on: bool) -> None:
        super().set_feed(on)
        if not on and self.audio_sink is not None:
            self.audio_sink.clear()
