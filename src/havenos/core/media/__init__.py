"""Music pipeline (docs/specs/07-music-pipeline.md): source adapters, the arbiter, and the music state the UI shows."""
from .coordinator import MediaCoordinator
from .sources.base import SourceAdapter

__all__ = ["MediaCoordinator", "SourceAdapter"]
