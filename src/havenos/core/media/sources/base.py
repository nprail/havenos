"""The contract every music source implements (docs/specs/07-music-pipeline.md section 3).

Adapters push `SourceEvent`s up to the coordinator through the sink it binds; the coordinator calls `command`,
`release` and `set_volume` back down. Adapters never decide who is active: they only report what their protocol says.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable

# What a source can currently do. The UI disables controls the active source lacks.
CAPABILITIES = frozenset({"play", "pause", "next", "prev", "seek"})
STATUSES = ("playing", "paused", "buffering", "stopped")


@dataclass(frozen=True)
class Availability:
    """The protocol endpoint is up (listening / reachable) or down."""
    available: bool


@dataclass(frozen=True)
class SessionStarted:
    """A sender connected. Does not by itself take over the speaker; only `Playback('playing')` does."""
    client: str | None = None


@dataclass(frozen=True)
class SessionEnded:
    pass


@dataclass(frozen=True)
class Playback:
    status: str          # one of STATUSES


@dataclass(frozen=True)
class Metadata:
    title: str = ""
    artist: str = ""
    album: str = ""
    art_uri: str = ""
    duration: float | None = None    # seconds; None = unknown / live


@dataclass(frozen=True)
class Position:
    seconds: float


@dataclass(frozen=True)
class Capabilities:
    commands: frozenset[str]


@dataclass(frozen=True)
class Volume:
    level: int           # 0-100
    muted: bool = False


@dataclass(frozen=True)
class Pairing:
    """A pairing code the user must enter on the sender (None clears it)."""
    code: str | None


@dataclass(frozen=True)
class Notice:
    """Something the user should be told (shown as an announcement): a failure the source cannot fix by itself."""
    message: str
    title: str = ""


SourceEvent = (Availability | SessionStarted | SessionEnded | Playback | Metadata | Position | Capabilities
               | Volume | Pairing | Notice)
Sink = Callable[[str, SourceEvent], None]


class SourceAdapter(ABC):
    id: str = ""
    label: str = ""

    def __init__(self) -> None:
        self._sink: Sink | None = None
        self.feed_on = True       # False: another source owns the speaker; drop our audio instead of playing it

    def bind(self, sink: Sink) -> None:
        self._sink = sink

    def set_feed(self, on: bool) -> None:
        """The coordinator's `select_feed`: whether this source's audio may reach the speaker."""
        self.feed_on = on

    def local_volume(self, level: int, muted: bool) -> None:
        """The sender changed its volume slider: apply it to our own output (we do not echo it back to the sender)."""
        sink = getattr(self, "audio_sink", None)
        if sink is not None and hasattr(sink, "set_volume"):
            sink.set_volume(level, muted)

    def emit(self, event: SourceEvent) -> None:
        if self._sink:
            self._sink(self.id, event)

    @abstractmethod
    async def start(self) -> None:
        """Bring the endpoint up. A failure should emit `Availability(False)` rather than raise."""

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    async def command(self, name: str, **args) -> None:
        """name: play | pause | next | prev | seek (`seconds=`)."""

    @abstractmethod
    async def release(self) -> None:
        """Evicted by another source: stop contributing audio and leave the sender in a sane state.
        Must not raise (a sender that ignores us is handled by the coordinator deselecting the audio feed)."""

    async def set_volume(self, level: int, muted: bool) -> None:
        """The device master volume changed; tell the sender so its slider stays in step. Optional."""
