"""A scriptable in-memory source. Used by the coordinator tests and by the demo/dev mode (HAVENOS_MUSIC_DEMO=1), where it
stands in for AirPlay and Spotify Connect until those adapters exist. It records every call so tests can assert on them."""
from __future__ import annotations

from .base import (Availability, Capabilities, Metadata, Playback, Position, SessionEnded, SessionStarted,
                   SourceAdapter, Volume)

DEMO_TRACKS = {
    "airplay": Metadata("Slow Light", "The Harbour Choir", "Low Tide", "", 214.0),
    "spotify": Metadata("Northern Lines", "Aurelia Vance", "Signal Fires", "", 187.0),
    "sendspin": Metadata("Paper Lanterns", "Mika Ostrander", "Evenings", "", 242.0),
}


class FakeSource(SourceAdapter):
    def __init__(self, id: str, label: str | None = None, *, commands: frozenset[str] | None = None) -> None:
        super().__init__()
        self.id = id
        self.label = label or id.title()
        self.commands = commands if commands is not None else frozenset({"play", "pause", "next", "prev", "seek"})
        self.calls: list[tuple] = []
        self.volumes: list[tuple[int, bool]] = []
        self.released = 0
        self.started = False
        self.release_pauses = True      # a polite sender reports `paused` once released; False = it ignores us

    async def start(self) -> None:
        self.started = True
        self.emit(Availability(True))

    async def stop(self) -> None:
        self.started = False

    async def command(self, name: str, **args) -> None:
        self.calls.append((name, args))
        if name == "pause":
            self.emit(Playback("paused"))
        elif name == "play":
            self.emit(Playback("playing"))

    async def release(self) -> None:
        self.released += 1
        if self.release_pauses:
            self.emit(Playback("paused"))

    async def set_volume(self, level: int, muted: bool) -> None:
        self.volumes.append((level, muted))

    # ---- scripting: what a real sender would do ----

    def connect(self, client: str = "Test phone") -> None:
        self.emit(SessionStarted(client))

    def disconnect(self) -> None:
        self.emit(SessionEnded())

    def play(self, track: Metadata | None = None, *, position: float = 0.0) -> None:
        """A sender starts playing: capabilities and metadata first, then the playing state (as real protocols do)."""
        self.emit(Capabilities(self.commands))
        self.emit(track or DEMO_TRACKS.get(self.id, Metadata("Demo track", "Demo artist")))
        self.emit(Position(position))
        self.emit(Playback("playing"))

    def pause(self) -> None:
        self.emit(Playback("paused"))

    def set_level(self, level: int, muted: bool = False) -> None:
        self.emit(Volume(level, muted))
