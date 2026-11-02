"""Core -> UI event stream. Same logical contract as docs/specs/00-common.md section 6."""
from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Event:
    type: str
    seq: int
    data: dict[str, Any] = field(default_factory=dict)


Handler = Callable[[Event], None]


class EventBus:
    """Synchronous fan-out. Handlers must be fast and must not block (the UI hops threads itself)."""

    def __init__(self) -> None:
        self._handlers: list[Handler] = []
        self._seq = itertools.count(1)

    def subscribe(self, handler: Handler) -> Callable[[], None]:
        self._handlers.append(handler)
        return lambda: self._handlers.remove(handler)

    def emit(self, type: str, **data: Any) -> Event:
        ev = Event(type=type, seq=next(self._seq), data=data)
        for h in list(self._handlers):
            try:
                h(ev)
            except Exception:  # one bad subscriber must not break the core
                log.exception("event handler failed for %s", type)
        return ev
