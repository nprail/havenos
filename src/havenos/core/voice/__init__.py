"""Voice: the scripted fake (UI demo) and the real Voice Preview Edition-style satellite (docs/specs/05)."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .fake import simulate_assist

if TYPE_CHECKING:
    from ..core import Core
    from .satellite import VoiceSatellite

__all__ = ["simulate_assist", "build"]
log = logging.getLogger(__name__)


def build(core: "Core", server, *, audio=None, engine=None) -> "VoiceSatellite":
    """The satellite for this device: the configured USB mic array, the wake engine (none installed yet) and settings from
    config. Registers itself with the core (which then stops running the scripted demo)."""
    from .audio import LocalAudio
    from .profiles import get_profile
    from .satellite import VoiceSatellite, VoiceSettings
    from .wake import NullWakeEngine
    from . import microwake

    cfg = core.config
    profile = get_profile(cfg.voice_profile, device=cfg.voice_device)
    if engine is None and microwake.available():
        engine = microwake.MicroWakeEngine(cfg.voice_stop_model)
    elif engine is None:
        log.warning("voice: pymicro-wakeword is not installed (pip install 'havenos[voice]'), so only the mic button starts the assistant")
    settings = VoiceSettings(wake_sound=cfg.voice_wake_sound, sensitivity=cfg.voice_sensitivity,
                             wake_words=cfg.voice_wake_words)
    satellite = VoiceSatellite(server, audio or LocalAudio(profile, hub=core.audio_hub()), engine or NullWakeEngine(), profile, patch=core._set, handle=core.handle,
                               state=core.state, settings=settings, sleep=core._sleep)
    core.attach_voice(satellite)
    return satellite
