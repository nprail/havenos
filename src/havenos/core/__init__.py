"""havenOS core: pure Python, asyncio. Must never import Qt (enforced by tests/test_import_boundary.py).

The names below are imported on first use, so `import havenos.core.photos` (a photo worker process) or
`havenos.core.config` (window size, before the interface is up) does not pull in the whole core.
"""
from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import Config
    from .core import Core
    from .events import Event, EventBus

_LAZY = {"Config": ".config", "Core": ".core", "Event": ".events", "EventBus": ".events"}
__all__ = list(_LAZY)


def __getattr__(name: str):
    if name in _LAZY:
        return getattr(importlib.import_module(_LAZY[name], __name__), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
