"""havenOS as an ESPHome device: maps core state to entities and HA commands back to core commands."""
from __future__ import annotations

import logging
import re
import socket
import time
from typing import TYPE_CHECKING

from aioesphomeapi import api_pb2 as pb

from . import entities as ent
from ..identity import device_mac
from .mdns import Advertiser
from .noise import decode_key
from ..voice.satellite import FEATURE_FLAGS
from .server import ESPHomeServer

if TYPE_CHECKING:
    from ..core import Core
    from ..events import Event

log = logging.getLogger(__name__)
_MEDIA_FEATURES = 1 | 4 | 8 | 4096 | 16384       # PAUSE | VOLUME_SET | VOLUME_MUTE | STOP | PLAY
_MEDIA_PLAY_MEDIA = 512                           # HA may send us a URL to play
_MEDIA_ANNOUNCE = 1048576                         # and, with voice on, spoken announcements
ESPHOME_VERSION = "2025.9.0"        # what we claim to speak; matches the API level the server implements


def default_name() -> str:
    host = re.sub(r"[^a-z0-9-]+", "-", socket.gethostname().split(".")[0].lower()).strip("-") or "device"
    return f"havenos-{host}"


class ESPHomeDevice:
    def __init__(self, core: "Core", *, name: str | None = None, port: int = 6053, host: str = "0.0.0.0",
                 mac: str | None = None, advertise: bool = True, ip: str | None = None, key: str | None = None,
                 voice_audio=None, voice_engine=None) -> None:
        self.core = core
        self.name = name or default_name()
        self.friendly_name = "havenOS " + self.name.removeprefix("havenos-")
        self.mac = mac or core.device_mac
        self._host, self._port, self._advertise, self._ip = host, port, advertise, ip
        self._stats = {"rss_mb": 0.0, "lag_worst_ms": 0.0, "cached_photos": 0}
        self.encrypted = bool(key)
        self.server = ESPHomeServer(self._device_info, self.name, server_info="havenOS",
                                    noise_psk=decode_key(key) if key else None)
        self.events: ent.Event = None  # type: ignore[assignment]
        self._voice_parts = (voice_audio, voice_engine)         # fakes in tests; None = the real ones
        self.voice = self._make_voice()
        self._build()
        self._adv: Advertiser | None = None
        self._unsubscribe = None
        self.port = 0

    # ---- identity ---------------------------------------------------------------------------

    def _device_info(self) -> pb.DeviceInfoResponse:
        return pb.DeviceInfoResponse(
            name=self.name, friendly_name=self.friendly_name, mac_address=self.mac, esphome_version=ESPHOME_VERSION,
            compilation_time="havenOS prototype", model="havenOS display", manufacturer="havenOS",
            project_name="havenos.display", project_version="0.1.0", uses_password=False,
            voice_assistant_feature_flags=FEATURE_FLAGS if self.voice else 0,
            api_encryption_supported=self.encrypted)

    def _make_voice(self):
        cfg = self.core.config
        if not cfg.voice_enabled:
            return None
        if not self.encrypted:                  # the link will carry microphone audio: never in plain text
            log.error("voice needs ESPHome Noise encryption: set [esphome] key (python -m havenos.core.esphome.noise makes one). Voice is off.")
            return None
        from .. import voice
        return voice.build(self.core, self.server, audio=self._voice_parts[0], engine=self._voice_parts[1])

    # ---- entities ---------------------------------------------------------------------------

    def _build(self) -> None:
        s, h = self.core.state, self.core.handle
        E = ent
        self.touch = E.Event("touch", "Touch", lambda: None, icon="mdi:gesture-tap",
                             event_types=["tap", "swipe_left", "swipe_right", "swipe_down"])
        music = lambda: s["music"] or {}
        self.server.entities = [
            E.MediaPlayer("media_player", "Music", lambda: (music().get("status", "idle"), music().get("volume", 0),
                                                           music().get("muted", False)),
                          icon="mdi:speaker", features=_MEDIA_FEATURES | _MEDIA_PLAY_MEDIA | (_MEDIA_ANNOUNCE if self.voice else 0),
                          run=self._media_command),
            E.Button("next_track", "Next track", icon="mdi:skip-next", press=lambda: h("music.command", name="next")),
            E.Button("previous_track", "Previous track", icon="mdi:skip-previous", press=lambda: h("music.command", name="prev")),
            E.TextSensor("music_title", "Music title", lambda: ((music().get("track") or {}).get("title", "")), icon="mdi:music"),
            E.TextSensor("music_artist", "Music artist", lambda: ((music().get("track") or {}).get("artist", "")), icon="mdi:account-music"),
            E.TextSensor("music_album", "Music album", lambda: ((music().get("track") or {}).get("album", "")), icon="mdi:album"),
            E.TextSensor("music_source", "Music source",
                         lambda: " · ".join(x for x in (music().get("source_label"), music().get("client")) if x), icon="mdi:cast-audio"),
            E.Switch("screen", "Screen", lambda: s["screen_on"], icon="mdi:monitor",
                     set=lambda v: h("screen.set", on=v)),
            E.Number("brightness", "Brightness", lambda: s["brightness"], icon="mdi:brightness-6",
                     min_value=10, max_value=100, step=5, unit="%", set=lambda v: h("brightness.set", percent=v)),
            E.Select("mode", "Mode", lambda: s["mode"] if s["mode"] in ("ambient", "dashboard") else "dashboard", icon="mdi:view-dashboard", options=["ambient", "dashboard"],
                     set=lambda v: h("mode.set", mode=v)),
            E.Button("next_photo", "Next photo", icon="mdi:skip-next", press=lambda: h("photo.next", delta=1)),
            E.Button("previous_photo", "Previous photo", icon="mdi:skip-previous", press=lambda: h("photo.next", delta=-1)),
            E.Number("photo_interval", "Seconds per photo", lambda: s["photo_interval_s"], icon="mdi:timer-sand",
                     category=E.CATEGORY_CONFIG, min_value=2, max_value=600, step=1, unit="s",
                     set=lambda v: h("config.set", photo_interval_s=v)),
            E.Number("crossfade", "Crossfade", lambda: s["crossfade_ms"], icon="mdi:blur-linear",
                     category=E.CATEGORY_CONFIG, min_value=0, max_value=4000, step=100, unit="ms",
                     set=lambda v: h("config.set", crossfade_ms=int(v))),
            E.Switch("blur", "Glass blur", lambda: s["blur"], icon="mdi:blur", category=E.CATEGORY_CONFIG,
                     set=lambda v: h("config.set", blur=v)),
            E.TextSensor("photo", "Current photo", lambda: (s["photo"] or {}).get("name", ""), icon="mdi:image"),
            E.Sensor("active_timers", "Active timers", lambda: len(s["timers"]), icon="mdi:timer-outline"),
            E.Sensor("notification_count", "Notifications", lambda: len(s["notifications"]), icon="mdi:bell-outline"),
            E.TextSensor("room", "Room", lambda: (s["room"] or {}).get("name", ""), icon="mdi:floor-plan", category=E.CATEGORY_DIAGNOSTIC),
            E.TextSensor("photo_source", "Photo source", lambda: s["photo_source"], category=E.CATEGORY_DIAGNOSTIC),
            E.BinarySensor("ha_link", "Home Assistant link", lambda: s["ha_status"] in ("connected", "demo"),
                           device_class="connectivity", category=E.CATEGORY_DIAGNOSTIC),
            E.Sensor("memory", "Memory", lambda: round(self._stats["rss_mb"]), unit="MB", category=E.CATEGORY_DIAGNOSTIC,
                     min_interval=15),
            E.Sensor("loop_lag", "Event loop lag", lambda: round(self._stats["lag_worst_ms"]), unit="ms", decimals=0,
                     category=E.CATEGORY_DIAGNOSTIC, min_interval=15),
            E.Sensor("cached_photos", "Cached photos", lambda: self._stats["cached_photos"],
                     category=E.CATEGORY_DIAGNOSTIC, min_interval=15),
            self.touch,
            *self._voice_entities(),
        ]
        self.server.services = [
            E.Service("start_timer", {"seconds": "int", "label": "string"},
                      lambda seconds, label: h("timer.start", seconds=seconds, label=label or "Timer")),
            E.Service("dismiss_timer", {}, lambda: h("timer.dismiss")),
            E.Service("announce", {"message": "string", "title": "string", "kind": "string", "seconds": "int"},
                      lambda message, title, kind, seconds: h("announce.show", message=message, title=title,
                                                              kind=kind or "info", seconds=seconds or None)),
            E.Service("notify", {"message": "string", "title": "string", "kind": "string"},
                      lambda message, title, kind: h("notify.add", message=message, title=title, kind=kind or "info")),
            E.Service("clear_notifications", {}, lambda: h("notifications.clear")),
            E.Service("dismiss_announcement", {}, lambda: h("announce.dismiss")),
        ]

    def _voice_entities(self) -> list:
        v, s, E = self.voice, self.core.state, ent
        if v is None:
            return []
        from ..voice.wake import SENSITIVITIES
        return [
            E.Switch("mute", "Mute", lambda: s["voice_muted"], icon="mdi:microphone-off", category=E.CATEGORY_CONFIG,
                     set=v.set_muted),
            E.Switch("wake_sound", "Wake sound", lambda: s["voice_wake_sound"], icon="mdi:bullhorn", category=E.CATEGORY_CONFIG,
                     set=v.set_wake_sound),
            E.Select("wake_word_sensitivity", "Wake word sensitivity", lambda: s["voice_sensitivity"], icon="mdi:tune",
                     category=E.CATEGORY_CONFIG, options=list(SENSITIVITIES), set=v.set_sensitivity),
        ]

    def _media_command(self, command: str, volume: float | None, url: str = "") -> None:
        """HA's media_player commands become the same core commands a touch sends, so the capability checks and the
        takeover rules are the ones the display itself obeys. HA never takes over the speaker: only a source starting to
        play does (spec 07 rule 4.2.1)."""
        h, m = self.core.handle, self.core.state["music"] or {}
        if command in ("play", "pause", "stop", "toggle"):
            h("music.command", name=command)
        elif command in ("mute", "unmute"):
            h("music.command", name="mute", muted=command == "mute")
        elif command == "volume" and volume is not None:
            h("music.command", name="volume", level=round(volume))
        elif command == "announce" and self.voice and url:
            self.core._spawn(self.voice.announce(media_id=url))
        elif command == "play_media" and url:
            h("music.play_url", url=url)
        elif command in ("volume_up", "volume_down"):
            step = 5 if command == "volume_up" else -5
            h("music.command", name="volume", level=max(0, min(100, int(m.get("volume", 0)) + step)))
        else:
            log.info("media_player: %s is not supported", command)

    # ---- lifecycle --------------------------------------------------------------------------

    async def start(self) -> int:
        self.port = await self.server.start(self._host, self._port)
        if self.voice:
            self.voice.start()
        for e in self.server.entities:
            e.mark_sent()
        self._unsubscribe = self.core.bus.subscribe(self._on_event)
        if self._advertise:
            try:
                from ..web import lan_ip
                self._adv = Advertiser(self.name, self.port, self.mac, self._ip or lan_ip(), ESPHOME_VERSION, self.encrypted)
                await self._adv.start()
            except Exception:                    # mDNS trouble must not stop the device from working by IP
                log.exception("could not announce on mDNS; add the device in HA by IP instead")
        log.info("ESPHome device %r listening on port %s", self.name, self.port)
        return self.port

    async def stop(self) -> None:
        if self._unsubscribe:
            self._unsubscribe()
        if self._adv:
            await self._adv.stop()
        await self.server.stop()

    # ---- core -> HA -------------------------------------------------------------------------

    def _on_event(self, ev: "Event") -> None:
        if ev.type == "gesture":
            self.server.broadcast([self.touch.fire(ev.data["kind"])])
            return
        if ev.type == "stats":
            self._stats.update({k: ev.data[k] for k in ("rss_mb", "lag_worst_ms", "cached_photos") if k in ev.data})
        elif ev.type != "state.patch":
            return
        now = time.monotonic()
        msgs = [e.state() for e in self.server.entities if e.changed(now)]
        self.server.broadcast([m for m in msgs if m is not None])
