"""Declarative ESPHome entities. Each knows how to describe itself, report state, and take a command.

`get` reads the current value from havenOS state; `set` (if any) turns an HA command into a core command.
Keys are a stable hash of object_id so entity identities survive restarts and re-ordering.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from aioesphomeapi import api_pb2 as pb

CATEGORY_NONE, CATEGORY_CONFIG, CATEGORY_DIAGNOSTIC = 0, 1, 2


def fnv1(s: str) -> int:
    """ESPHome's entity key hash, so keys look like a real ESPHome device's."""
    h = 2166136261
    for ch in s.encode():
        h = (h * 16777619) & 0xFFFFFFFF
        h ^= ch
    return h


@dataclass
class Entity:
    object_id: str
    name: str
    get: Callable[[], Any]
    icon: str = ""
    category: int = CATEGORY_NONE
    min_interval: float = 0.0          # throttle pushes (noisy diagnostics)
    key: int = field(init=False)
    _last_push: float = field(default=0.0, init=False, repr=False)
    _last_value: Any = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.key = fnv1(self.object_id)

    # -- subclass API --
    def describe(self) -> Any: raise NotImplementedError
    def state(self) -> Any | None: raise NotImplementedError
    def command(self, msg: Any) -> bool:
        return False                    # True when this entity consumed the message

    def _common(self) -> dict:
        return dict(object_id=self.object_id, key=self.key, name=self.name, icon=self.icon,
                    entity_category=self.category)

    def changed(self, now: float) -> bool:
        """True if a new state should be pushed (value differs and the throttle allows it)."""
        value = self.get()
        if value == self._last_value:
            return False
        if now - self._last_push < self.min_interval:
            return False
        self._last_value, self._last_push = value, now
        return True

    def mark_sent(self, now: float | None = None) -> None:
        self._last_value, self._last_push = self.get(), now if now is not None else time.monotonic()


@dataclass
class Switch(Entity):
    set: Callable[[bool], None] = lambda v: None
    def describe(self): return pb.ListEntitiesSwitchResponse(**self._common())
    def state(self): return pb.SwitchStateResponse(key=self.key, state=bool(self.get()))
    def command(self, msg):
        if isinstance(msg, pb.SwitchCommandRequest) and msg.key == self.key:
            self.set(bool(msg.state)); return True
        return False


@dataclass
class Number(Entity):
    min_value: float = 0.0
    max_value: float = 100.0
    step: float = 1.0
    unit: str = ""
    set: Callable[[float], None] = lambda v: None
    def describe(self):
        return pb.ListEntitiesNumberResponse(**self._common(), min_value=self.min_value, max_value=self.max_value,
                                             step=self.step, unit_of_measurement=self.unit)
    def state(self): return pb.NumberStateResponse(key=self.key, state=float(self.get()))
    def command(self, msg):
        if isinstance(msg, pb.NumberCommandRequest) and msg.key == self.key:
            self.set(min(self.max_value, max(self.min_value, float(msg.state)))); return True
        return False


@dataclass
class Select(Entity):
    options: list[str] = field(default_factory=list)
    set: Callable[[str], None] = lambda v: None
    def describe(self): return pb.ListEntitiesSelectResponse(**self._common(), options=self.options)
    def state(self): return pb.SelectStateResponse(key=self.key, state=str(self.get()))
    def command(self, msg):
        if isinstance(msg, pb.SelectCommandRequest) and msg.key == self.key and msg.state in self.options:
            self.set(msg.state); return True
        return False


@dataclass
class Button(Entity):
    press: Callable[[], None] = lambda: None
    get: Callable[[], Any] = lambda: None
    def describe(self): return pb.ListEntitiesButtonResponse(**self._common())
    def state(self): return None                                  # buttons are stateless
    def command(self, msg):
        if isinstance(msg, pb.ButtonCommandRequest) and msg.key == self.key:
            self.press(); return True
        return False


@dataclass
class Sensor(Entity):
    unit: str = ""
    decimals: int = 0
    def describe(self):
        return pb.ListEntitiesSensorResponse(**self._common(), unit_of_measurement=self.unit,
                                             accuracy_decimals=self.decimals, state_class=pb.STATE_CLASS_MEASUREMENT)
    def state(self): return pb.SensorStateResponse(key=self.key, state=round(float(self.get() or 0), self.decimals))


@dataclass
class TextSensor(Entity):
    def describe(self): return pb.ListEntitiesTextSensorResponse(**self._common())
    def state(self): return pb.TextSensorStateResponse(key=self.key, state=str(self.get() or ""))


@dataclass
class BinarySensor(Entity):
    device_class: str = ""
    def describe(self): return pb.ListEntitiesBinarySensorResponse(**self._common(), device_class=self.device_class)
    def state(self): return pb.BinarySensorStateResponse(key=self.key, state=bool(self.get()))


@dataclass
class MediaPlayer(Entity):
    """The display as a Home Assistant media_player. `get` returns (state, volume 0-100, muted) with state one of
    idle | playing | paused; `run(command, volume)` takes what HA asked for (command is "play", "pause", "stop", "toggle",
    "mute", "unmute", "volume" or "announce") and returns nothing.

    The ESPHome media_player has no title, artist or art: those go out as text sensors next to it."""
    features: int = 0
    run: Callable[..., None] = lambda command, volume, url="": None
    _STATES = {"idle": pb.MEDIA_PLAYER_STATE_IDLE, "playing": pb.MEDIA_PLAYER_STATE_PLAYING,
               "paused": pb.MEDIA_PLAYER_STATE_PAUSED}
    _COMMANDS = {pb.MEDIA_PLAYER_COMMAND_PLAY: "play", pb.MEDIA_PLAYER_COMMAND_PAUSE: "pause",
                 pb.MEDIA_PLAYER_COMMAND_STOP: "stop", pb.MEDIA_PLAYER_COMMAND_TOGGLE: "toggle",
                 pb.MEDIA_PLAYER_COMMAND_MUTE: "mute", pb.MEDIA_PLAYER_COMMAND_UNMUTE: "unmute",
                 pb.MEDIA_PLAYER_COMMAND_VOLUME_UP: "volume_up", pb.MEDIA_PLAYER_COMMAND_VOLUME_DOWN: "volume_down"}

    def describe(self):
        return pb.ListEntitiesMediaPlayerResponse(**self._common(), supports_pause=True, feature_flags=self.features)

    def state(self):
        state, volume, muted = self.get()
        return pb.MediaPlayerStateResponse(key=self.key, state=self._STATES.get(state, pb.MEDIA_PLAYER_STATE_IDLE),
                                           volume=max(0.0, min(1.0, volume / 100.0)), muted=bool(muted))

    def command(self, msg):
        if not (isinstance(msg, pb.MediaPlayerCommandRequest) and msg.key == self.key):
            return False
        if msg.has_media_url:
            self.run("announce" if msg.announcement else "play_media", None, msg.media_url)
        if msg.has_volume:
            self.run("volume", float(msg.volume) * 100.0)
        if msg.has_command and msg.command in self._COMMANDS:
            self.run(self._COMMANDS[msg.command], None)
        return True


@dataclass
class Event(Entity):
    event_types: list[str] = field(default_factory=list)
    get: Callable[[], Any] = lambda: None
    def describe(self): return pb.ListEntitiesEventResponse(**self._common(), event_types=self.event_types)
    def state(self): return None                                  # events are pushed when they happen, never "current"
    def fire(self, kind: str) -> Any: return pb.EventResponse(key=self.key, event_type=kind)


@dataclass
class Service:
    """A user-defined ESPHome service: shows up in HA as esphome.<node>_<name>."""
    name: str
    args: dict[str, str]                       # arg name -> "int" | "string" | "bool" | "float"
    run: Callable[..., None]
    key: int = field(init=False)

    _TYPES = {"bool": pb.SERVICE_ARG_TYPE_BOOL, "int": pb.SERVICE_ARG_TYPE_INT,
              "float": pb.SERVICE_ARG_TYPE_FLOAT, "string": pb.SERVICE_ARG_TYPE_STRING}

    def __post_init__(self) -> None:
        self.key = fnv1("service:" + self.name)

    def describe(self):
        return pb.ListEntitiesServicesResponse(
            name=self.name, key=self.key,
            args=[pb.ListEntitiesServicesArgument(name=n, type=self._TYPES[t]) for n, t in self.args.items()])

    def execute(self, msg: "pb.ExecuteServiceRequest") -> None:
        values: dict[str, Any] = {}
        for (name, kind), arg in zip(self.args.items(), msg.args):
            values[name] = {"bool": arg.bool_, "int": arg.int_, "float": arg.float_, "string": arg.string_}[kind]
        self.run(**values)
