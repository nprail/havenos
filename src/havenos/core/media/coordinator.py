"""MediaCoordinator: the arbiter (docs/specs/07-music-pipeline.md section 4). One source is active at a time; the last one to
start playing wins. It owns the music state the UI shows, routes commands to the active source, and tells the audio
side which feed to play.

Everything here runs on the core's event loop. Adapter events arrive synchronously through `on_event`; anything that
needs to await (evicting the old source, forwarding a command) is handed to `spawn`.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable, Coroutine

from .sources.base import (Availability, Capabilities, Metadata, Notice, Pairing, Playback, Position, SessionEnded,
                           SessionStarted, SourceAdapter, SourceEvent, Volume)

log = logging.getLogger(__name__)

ACTIVE = ("playing", "buffering")


def _private() -> dict[str, Any]:
    """What we remember about a source whether or not it is active. The shown state is a projection of the active one."""
    return {"available": False, "client": None, "status": "stopped", "track": None, "position": 0.0,
            "position_at": 0.0, "commands": frozenset(), "pairing_code": None}


class MediaCoordinator:
    def __init__(
        self,
        set_state: Callable[..., None],
        *,
        clock: Callable[[], float] = time.time,
        spawn: Callable[[Coroutine], None] | None = None,
        notify: Callable[[str, str], None] | None = None,
        select_feed: Callable[[str | None], None] | None = None,
        idle_timeout_s: float = 600.0,
        echo_window_s: float = 3.0,
        volume: int = 60,
        art: Callable[[str], str] | None = None,
        duck_db: float = -20.0,
        hint: bool = False,
        fight_limit: int = 4,
    ) -> None:
        self._set_state = set_state
        self._clock = clock
        self._notify = notify
        self._select_feed = select_feed or (lambda _id: None)
        self.idle_timeout_s = idle_timeout_s
        self.echo_window_s = echo_window_s
        self._adapters: dict[str, SourceAdapter] = {}
        self._priv: dict[str, dict[str, Any]] = {}
        self._active: str | None = None
        self._ignored: dict[str, float] = {}       # evicted source id -> when we stop ignoring its stale events
        self._idle_deadline: float | None = None
        self._volume = volume
        self._muted = False
        self._art = art or (lambda uri: uri)
        self.duck_db = duck_db
        self.hint = hint
        self._ducked = False
        self._fight_limit = fight_limit
        self._recent_takeovers: list[float] = []
        self._takeover_seq = 0
        self._takeover: dict[str, Any] | None = None
        self._tasks: set[asyncio.Task] = set()
        self._spawn = spawn or self._own_spawn
        self.takeovers: list[tuple[str | None, str]] = []   # (from, to), for tests and the "fighting senders" warning

    # ---- lifecycle ----------------------------------------------------------------------------

    def register(self, adapter: SourceAdapter) -> None:
        self._adapters[adapter.id] = adapter
        self._priv[adapter.id] = _private()
        adapter.bind(self.on_event)

    @property
    def active(self) -> str | None:
        return self._active

    async def start(self) -> None:
        for a in self._adapters.values():
            try:
                await a.start()
            except Exception:
                log.exception("music source %s failed to start", a.id)
                self.on_event(a.id, Availability(False))
        self._publish()

    async def stop(self) -> None:
        for t in list(self._tasks):
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        for a in self._adapters.values():
            try:
                await a.stop()
            except Exception:
                log.exception("music source %s failed to stop", a.id)

    async def settle(self) -> None:
        """Wait for in-flight evictions and commands (tests, shutdown)."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    def _own_spawn(self, coro: Coroutine) -> None:
        async def guarded() -> None:
            try:
                await coro
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("music background job failed")
        t = asyncio.get_running_loop().create_task(guarded())
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)

    # ---- adapter events -----------------------------------------------------------------------

    def on_event(self, source_id: str, ev: SourceEvent) -> None:
        p = self._priv.get(source_id)
        if p is None:
            return
        now = self._clock()

        if isinstance(ev, Availability):
            p["available"] = ev.available
            if not ev.available and self._active == source_id:
                self._clear_active()
            self._publish()
            return
        if isinstance(ev, Notice):
            if self._notify:
                self._notify(ev.message, ev.title or self._adapters[source_id].label)
            return
        if isinstance(ev, Pairing):
            p["pairing_code"] = ev.code
            if ev.code and self._notify:
                self._notify(f"Enter pairing code {ev.code} on {self._adapters[source_id].label}.", "Pairing")
            self._publish()
            return

        if source_id in self._ignored:                      # rule 4.2.3: a source we just evicted
            settled = isinstance(ev, (SessionStarted, SessionEnded)) or (
                isinstance(ev, Playback) and ev.status in ("paused", "stopped"))
            if now >= self._ignored[source_id] or settled:
                del self._ignored[source_id]                # it has caught up with the eviction (or the window passed)
            else:
                return                                      # a stale echo ("still playing", old metadata): drop it

        if isinstance(ev, SessionStarted):
            p["client"] = ev.client
        elif isinstance(ev, SessionEnded):
            p.update(client=None, status="stopped", track=None, position=0.0, commands=frozenset())
            if self._active == source_id:
                self._clear_active()
        elif isinstance(ev, Playback):
            if p["status"] in ACTIVE and p["position_at"]:   # freeze the position where playback left off
                p["position"] += max(0.0, now * 1000 - p["position_at"]) / 1000
            p["position_at"] = now * 1000
            p["status"] = ev.status
            if ev.status in ACTIVE and self._active != source_id:
                self._take_over(source_id)                   # rule 4.2.1/4.2.2: only starting to play takes the speaker
            elif self._active == source_id:
                self._idle_deadline = None if ev.status in ACTIVE else now + self.idle_timeout_s
        elif isinstance(ev, Metadata):
            if not p["track"] or p["track"]["title"] != ev.title:    # a new track starts from the top unless told otherwise
                p["position"], p["position_at"] = 0.0, now * 1000
            p["track"] = {"title": ev.title, "artist": ev.artist, "album": ev.album, "art_uri": ev.art_uri,
                          "duration": ev.duration}
        elif isinstance(ev, Position):
            p["position"], p["position_at"] = ev.seconds, now * 1000
        elif isinstance(ev, Capabilities):
            p["commands"] = ev.commands
        elif isinstance(ev, Volume) and self._active == source_id:
            self._volume, self._muted = ev.level, ev.muted
            self._adapters[source_id].local_volume(ev.level, ev.muted)
        self._publish()

    def _take_over(self, new: str) -> None:
        old = self._active
        self._active = new
        self._idle_deadline = None
        self.takeovers.append((old, new))
        self._note_takeover(old, new)
        self._select_feed(new)
        self._spawn(self._push_volume())                     # the device volume applies to whichever source is playing
        if old is not None:
            # Active first, then evict: the new source is never silent waiting for the old one to finish dying.
            self._ignored[old] = self._clock() + self.echo_window_s
            log.info("music: %s takes over from %s", new, old)
            self._spawn(self._release(old))
        else:
            log.info("music: %s starts playing", new)

    def _note_takeover(self, old: str | None, new: str) -> None:
        """Remember the takeover for the UI toast, and warn when senders keep fighting over the speaker (takeovers are
        never blocked, so a ping-pong has to be visible in the log)."""
        now = self._clock()
        self._recent_takeovers = [t for t in self._recent_takeovers if now - t < 60.0] + [now]
        if old is not None:
            self._takeover_seq += 1
            self._takeover = {"seq": self._takeover_seq, "source": self._adapters[new].label,
                              "client": self._priv[new]["client"], "from": self._adapters[old].label}
        if len(self._recent_takeovers) >= self._fight_limit and old is not None:
            log.warning("music: %d takeovers in the last minute (latest %s -> %s): two senders are fighting over the speaker",
                        len(self._recent_takeovers), old, new)

    def duck(self, on: bool) -> None:
        """Voice, announcements and ringing timers lower the music; they are not sources and never take over."""
        if on == self._ducked:
            return
        self._ducked = on
        for a in self._adapters.values():
            sink = getattr(a, "audio_sink", None)
            if sink is not None and hasattr(sink, "set_duck"):
                sink.set_duck(self.duck_db if on else None)

    async def _release(self, source_id: str) -> None:
        try:
            await self._adapters[source_id].release()
        except Exception:
            log.exception("releasing %s failed (its audio feed is already deselected)", source_id)

    def _clear_active(self) -> None:
        self._active = None
        self._idle_deadline = None
        self._select_feed(None)

    # ---- commands (UI, later Home Assistant) --------------------------------------------------

    async def command(self, name: str, **args: Any) -> bool:
        """Route a control to the active source. Returns False when it is not possible right now (no active source,
        or the source lacks the capability); the UI normally prevents that by greying the control out."""
        if name == "volume":
            self._volume = int(min(100, max(0, args["level"])))
            self._muted = False
            self._publish()
            await self._push_volume()
            return True
        if name == "mute":
            self._muted = bool(args.get("muted", not self._muted))
            self._publish()
            await self._push_volume()
            return True

        src = self._active
        if src is None:
            return False
        adapter, p = self._adapters[src], self._priv[src]
        if name == "toggle":
            name = "pause" if p["status"] in ACTIVE else "play"
        if name == "stop":                                   # releases the slot (the one external command that does)
            self._ignored[src] = self._clock() + self.echo_window_s
            self._clear_active()
            self._publish()
            await self._release(src)
            return True
        if name not in p["commands"]:
            log.debug("music: %s does not support %s", src, name)
            return False
        await adapter.command(name, **args)
        return True

    async def _push_volume(self) -> None:
        if self._active:
            try:
                await self._adapters[self._active].set_volume(self._volume, self._muted)
            except Exception:
                log.exception("could not push the volume to %s", self._active)

    def handle(self, name: str, **args: Any) -> None:
        """Synchronous entry for `Core.handle`: runs the command in the background."""
        self._spawn(self.command(name, **args))

    # ---- scheduling ---------------------------------------------------------------------------

    def tick(self) -> None:
        """Rule 4.2.5: a paused/stopped active source frees the slot after `idle_timeout_s`."""
        if self._active and self._idle_deadline is not None and self._clock() >= self._idle_deadline:
            log.info("music: %s idle, clearing", self._active)
            self._clear_active()
            self._publish()

    # ---- state --------------------------------------------------------------------------------

    def state(self) -> dict[str, Any]:
        """The UI-facing state (spec 07 section 4.1). Positions are extrapolated by the UI from position + position_at."""
        a = self._active
        p = self._priv[a] if a else None
        return {
            "active_source": a,
            "source_label": self._adapters[a].label if a else "",
            "client": p["client"] if p else None,
            "status": (p["status"] if p["status"] in ACTIVE or p["status"] == "paused" else "idle") if p else "idle",
            "track": self._shown_track(p),
            "position": p["position"] if p else 0.0,
            "position_at": p["position_at"] if p else 0.0,
            "capabilities": sorted(p["commands"]) if p else [],
            "volume": self._volume,
            "muted": self._muted,
            "takeover": self._takeover,
            "hint": (self._sources_ready() if self.hint and not a else []),
            "sources": {sid: {"label": self._adapters[sid].label, "available": q["available"], "client": q["client"],
                              "status": q["status"], "pairing_code": q["pairing_code"]}
                        for sid, q in self._priv.items()},
        }

    def _sources_ready(self) -> list[str]:
        return [self._adapters[sid].label for sid, q in self._priv.items() if q["available"]]

    def _shown_track(self, p: dict[str, Any] | None) -> dict[str, Any] | None:
        if not p or not p["track"]:
            return None
        t = p["track"]
        return {**t, "art_uri": self._art(t["art_uri"]) if t.get("art_uri") else ""}

    def republish(self) -> None:
        """Something the state depends on changed outside an event (a cover finished downloading)."""
        self._publish()

    def _publish(self) -> None:
        self._set_state(music=self.state())
