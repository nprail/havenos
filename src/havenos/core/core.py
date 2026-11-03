"""The havenOS core. Owns all state; the UI only renders events and sends commands.

Threading rule: everything here runs on the one shared event loop. Anything blocking or CPU-heavy
(photo decode, later audio capture) must leave the loop via an executor.
"""
from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import Executor
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Coroutine

from .config import Config
from .events import EventBus
from .actions import ActionError
from .demo import DemoHome
from .ha import HAError
from .home import HomeBase, HomeIntegration
from .identity import device_mac
from .immich import ImmichSource
from .nasa import NasaSource
from .media import MediaCoordinator
from .media.art import ArtCache
from .playlist import LocalSource, Playlist
from .stats import LoopLagMonitor, rss_mb
from .timers import TimerBook
from .voice import simulate_assist

if TYPE_CHECKING:
    from .audio.output import AudioHub
    from .voice.satellite import VoiceSatellite

log = logging.getLogger(__name__)

TICK_S = 0.25
STATS_S = 0.5
PHOTO_RETRY_S = 10.0

MODES = ("ambient", "dashboard", "rooms", "notifications")
MAX_NOTIFICATIONS = 50


class Core:
    def __init__(
        self,
        config: Config,
        *,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        executor: Executor | None = None,
    ) -> None:
        self.config = config
        self.bus = EventBus()
        self._clock = clock
        self._sleep = sleep
        self._executor = executor
        self._timers = TimerBook()
        self._tasks: list[asyncio.Task] = []
        self._voice_task: asyncio.Task | None = None
        self.voice: "VoiceSatellite | None" = None          # the real satellite, when voice is on (else the scripted demo)
        self._voice_timers: dict[str, int] = {}              # Home Assistant timer id -> TimerBook id
        self._hub: "AudioHub | None" = None                  # the one mixer and sound output, opened when first needed
        self._profile_match: str | None = None               # a voice profile that pins its own output device
        self._lag = LoopLagMonitor()
        self._ring_deadline: float | None = None
        self._idle_deadline: float | None = None
        self._cycle_deadline: float = 0.0
        self._photo_retry: float = 0.0
        self._playlist: Playlist | None = None
        self._home: HomeBase | None = None
        self._device_mac: str | None = None
        self._announce_queue: list[dict] = []
        self._announce_deadline: float | None = None
        self._note_seq = 0
        self._advancing = False
        self._jobs: set[asyncio.Task] = set()

        demo = config.ha is None
        self.state: dict[str, Any] = {
            "mode": "ambient",         # ambient | dashboard | rooms | notifications
            "photo": None,             # current photo dict or None
            "photo_source": config.photo_source,
            "timers": [],
            "ringing": None,
            "voice": "idle",           # idle | listening | processing | responding | error
            "transcript": "",
            "response": "",
            "voice_ready": False,      # the satellite is connected to Home Assistant
            "voice_muted": False,
            "voice_busy": False,       # a spoken announcement or a ringing timer is on the speaker
            "voice_wake_sound": config.voice_wake_sound,
            "voice_sensitivity": config.voice_sensitivity,
            "voice_wake_words": list(config.voice_wake_words),
            "blur": config.blur,
            "stats": config.stats,
            "crossfade_ms": config.crossfade_ms,
            "screen_on": True,         # software "display off": the UI draws black (real backlight control comes later)
            "brightness": config.brightness,   # percent; the UI dims with a black overlay
            "photo_interval_s": config.photo_interval_s,
            "web": None,               # {"url", "code", "link", "qr"} once the settings server is up (the setup screen and HUD)
            "setup_done": config.setup_done,   # first-run setup finished: until then the display shows the pairing QR code
            "ha_status": "demo" if demo else "connecting",
            "ha_exposure": None,       # {"ok", "error", "exposed", "hidden"}: what HA lets this device show
            "weather": None, "media": None, "controls": [],
            "room": None,              # {"id", "name"}: the room this device is in
            "rooms": [],               # summaries of rooms that have something to show
            "room_selected": None, "room_view": None,
            "announcement": None,      # the announcement on screen, if any
            "notifications": [],       # history, newest first
            "music": None,             # what the active music source is playing (core/media); filled in below
            "library": {"available": False, "busy": False, "listening": False, "query": "", "sections": [], "error": ""},
        }
        self.art = ArtCache(config.cache_dir.parent / "music-art", on_ready=lambda: self.music.republish())
        self.music = MediaCoordinator(self._set, clock=clock, spawn=self._spawn, idle_timeout_s=config.music_idle_s,
                                      select_feed=self._select_feed, art=self.art.resolve, duck_db=config.duck_db,
                                      hint=config.music_hint,
                                      notify=lambda message, title: self._cmd_announce_show(message=message, title=title))
        self._register_music_sources()
        self.library = self._make_library()
        self.state["music"] = self.music.state()
        self.state["library"] = {**self.state["library"], "available": self.library is not None}

    # ---- lifecycle -------------------------------------------------------------------------

    def _register_music_sources(self) -> None:
        cfg = self.config
        import socket
        host = f"havenOS {socket.gethostname().split('.')[0]}"
        if cfg.airplay_enabled:
            from .media.sources.airplay import RATE as AIRPLAY_RATE, AirPlaySource
            self.music.register(AirPlaySource(cfg.airplay_name or host, cfg.config_path.parent, port=cfg.airplay_port,
                                              binary=cfg.airplay_binary or None, manage_process=cfg.airplay_manage,
                                              audio_sink=self._open_audio(AIRPLAY_RATE, 150) if cfg.airplay_audio else None))
        if cfg.spotify_enabled:
            from .media.sources.spotify import PIPE_RATE, SpotifySource
            self.music.register(SpotifySource(cfg.spotify_name or host, cfg.config_path.parent, api_port=cfg.spotify_api_port,
                                              binary=cfg.spotify_binary or None, manage_process=cfg.spotify_manage,
                                              audio_sink=self._open_audio(PIPE_RATE, 150) if cfg.spotify_audio else None))
        if cfg.sendspin_enabled:
            from .media.sources.sendspin import SendspinSource
            self.music.register(SendspinSource(cfg.sendspin_name or host,
                                               cfg.config_path.parent, port=cfg.sendspin_port,
                                               audio_sink=self._open_audio() if cfg.sendspin_audio else None,
                                               allow_unpaired=cfg.sendspin_allow_unpaired))
        if cfg.music_demo:      # stand-ins for the sources that do not exist yet; see _cmd_music_simulate
            from .media.sources.fake import FakeSource
            for sid, label in (("airplay", "AirPlay"), ("spotify", "Spotify")):
                if sid not in self.music._adapters:             # a real source of the same name wins
                    self.music.register(FakeSource(sid, label))

    def _make_library(self):
        """Search/browse/play through Music Assistant when it is configured; canned data in demo mode."""
        cfg = self.config
        if cfg.ma_url:
            from .media.library import MusicAssistantClient, MusicLibrary
            sendspin = self.music._adapters.get("sendspin")
            return MusicLibrary(MusicAssistantClient(cfg.ma_url, cfg.ma_token), player_id=cfg.ma_player_id,
                                player_name=getattr(sendspin, "name", ""),
                                sendspin_client_id=lambda: getattr(self.music._adapters.get("sendspin"), "client_id", ""))
        if cfg.music_demo:
            from .media.library import DemoLibrary
            return DemoLibrary(self._demo_play)
        return None

    def _demo_play(self, item: dict) -> None:
        """Demo library: playing an item makes the fake Spotify source start a track named after it."""
        from .media.sources.base import Metadata
        src = self.music._adapters.get("spotify")
        if src is not None and hasattr(src, "play"):
            src.connect("Library")
            src.play(Metadata(item["name"], item["subtitle"], "", "", 200.0))

    def audio_hub(self) -> "AudioHub":
        """The shared mixer and sound output (docs/specs/05 section 4): music sources and the voice satellite both play
        through it, so ducking is the mixer's and its output is the echo reference. The sound device opens on `start()`."""
        if self._hub is None:
            from .audio.output import AudioHub
            from .voice.profiles import DEFAULT, get_profile
            cfg = self.config
            profile = DEFAULT
            if cfg.voice_enabled:
                try:
                    profile = get_profile(cfg.voice_profile, device=cfg.voice_device)
                except ValueError as e:
                    log.error("%s; using the system sound device", e)
            self._profile_match = profile.match
            self._hub = AudioHub(profile.playback_rate, match=profile.match or cfg.audio_device or None, duck_db=cfg.duck_db)
        return self._hub

    def audio_choices(self) -> list[dict[str, str]]:
        """Sound outputs for the settings page (real hardware only)."""
        import sounddevice as sd
        from .audio.output import output_choices
        return output_choices(sd)

    def audio_test(self) -> None:
        """Play a short chime on the current output (settings page, "Test sound")."""
        hub = self.audio_hub()
        hub.test_tone()

    def _open_audio(self, rate: int = 48000, prebuffer_ms: int = 300):
        """A sink on the shared media bus for one music source. Without an output device (or PortAudio) that source runs
        display/remote only (Music Assistant then shows Sendspin as a display rather than a player)."""
        try:
            hub = self.audio_hub()
            hub.start()
            return hub.open(rate, prebuffer_ms)
        except Exception as e:
            log.warning("no audio output (%s): this source will be display/remote only", e)
            return None

    def _select_feed(self, active: str | None) -> None:
        """Only the active source's audio reaches the speaker. With nothing active every feed stays open, so the source
        about to take over is not clipped."""
        for sid, adapter in self.music._adapters.items():
            adapter.set_feed(active is None or sid == active)

    async def start(self) -> None:
        cfg = self.config
        self._playlist = self._make_playlist()
        now = self._clock()
        self._cycle_deadline = now + cfg.photo_interval_s
        self._timers.add(600, "Pasta", int(now * 1000) - 328_000)   # demo timer, ~4:32 left
        self._set(timers=self._timers.snapshot())
        self.state["photo"] = await self._load_first_photo()
        self.emit_snapshot()
        self._home = self._make_home()
        self._home.start()
        await self.music.start()
        self._tasks = [asyncio.create_task(self._run(), name="core-tick"),
                       asyncio.create_task(self._stats_loop(), name="core-stats"),
                       asyncio.create_task(self._lag.run(), name="core-lag")]

    @property
    def device_mac(self) -> str:
        """This device's stable id: the ESPHome MAC, and how it finds its own room in HA's registry."""
        if self._device_mac is None:
            self._device_mac = device_mac(self.config.config_path.parent / "device_mac")
        return self._device_mac

    def _make_home(self) -> HomeBase:
        if self.config.ha:
            return HomeIntegration(self.config.ha, self._set, own_mac=self.device_mac,
                                   on_ha_notifications=self._ha_notifications)
        return DemoHome(self._set)

    def _make_playlist(self) -> Playlist:
        cfg = self.config
        if cfg.immich:
            source = ImmichSource(cfg.immich, cfg.cache_dir)
        elif cfg.nasa:
            source = NasaSource(cfg.nasa, cfg.cache_dir)
        else:
            source = LocalSource(cfg.photo_dir)
        return Playlist(source, cfg, self._executor)

    async def apply_config(self, cfg: Config) -> None:
        """Swap in a new configuration without restarting: rebuilds the HA link and the photo source."""
        if self._home:
            await self._home.stop()
            self._home = None
        if self._playlist:
            await self._playlist.close()
        self.config = cfg
        self._set(setup_done=cfg.setup_done)
        if self.library is not None:
            await self.library.close()
        self.library = self._make_library()
        self._set(library={**self.state["library"], "available": self.library is not None, "sections": [], "error": ""})
        self.music.idle_timeout_s, self.music.duck_db, self.music.hint = cfg.music_idle_s, cfg.duck_db, cfg.music_hint
        self.music.republish()
        demo = cfg.ha is None
        self._set(
            photo_source=cfg.photo_source, photo=None, blur=cfg.blur,
            crossfade_ms=cfg.crossfade_ms, photo_interval_s=cfg.photo_interval_s, brightness=cfg.brightness,
            ha_status="demo" if demo else "connecting", ha_exposure=None, weather=None, media=None, controls=[],
            room=None, rooms=[], room_selected=None, room_view=None)
        self._playlist = self._make_playlist()
        self._cycle_deadline = self._clock() + cfg.photo_interval_s
        self._set(photo=await self._load_first_photo())
        self._home = self._make_home()
        self._home.start()
        if self._hub is not None and not self._profile_match:      # a voice profile pins its own device; otherwise follow config
            self._hub.set_match(cfg.audio_device or None)

    async def _load_first_photo(self) -> dict | None:
        try:
            photo = await self._playlist.start()
        except Exception:
            log.exception("could not load the first photo")
            photo = None
        self._photo_retry = self._clock() + PHOTO_RETRY_S
        return photo.to_dict() if photo else None

    async def stop(self) -> None:
        if self.voice:
            await self.voice.stop()
        running = [*self._tasks, *self._jobs, *([self._voice_task] if self._voice_task else [])]
        for t in running:
            t.cancel()
        await asyncio.gather(*running, return_exceptions=True)
        self._tasks = []
        await self.music.stop()
        if self._hub is not None:
            self._hub.stop()
        await self.art.close()
        if self.library is not None:
            await self.library.close()
        if self._home:
            await self._home.stop()
        if self._playlist:
            await self._playlist.close()

    async def settle(self) -> None:
        """Wait for in-flight background jobs (photo advance, HA calls). For tests and shutdown."""
        while self._jobs:
            await asyncio.gather(*list(self._jobs), return_exceptions=True)

    def emit_snapshot(self) -> None:
        self.bus.emit("state.snapshot", state=dict(self.state))

    # ---- commands (single entry point) ------------------------------------------------------

    def handle(self, command: str, **args: Any) -> None:
        fn = getattr(self, "_cmd_" + command.replace(".", "_"), None)
        if fn is None:
            log.warning("unknown command %s", command)
            self.bus.emit("error", code="unknown_command", message=command)
            return
        fn(**args)

    def _cmd_mode_set(self, mode: str) -> None:
        if mode not in MODES:
            return
        if mode != "rooms" and self.state["room_selected"]:
            self._home.select_room(None)               # leaving the rooms screens forgets which room was open
        self._set(mode=mode)
        self._touch()

    # ---- rooms ---------------------------------------------------------------------------------

    def _cmd_rooms_open(self) -> None:
        """Open the rooms screen, straight into this device's own room if it has one."""
        here = (self.state["room"] or {}).get("id")
        self._home.select_room(here if here in [r["id"] for r in self.state["rooms"]] else None)
        self._set(mode="rooms")
        self._touch()

    def _cmd_rooms_select(self, id: str) -> None:
        self._home.select_room(id)
        self._set(mode="rooms")
        self._touch()

    def _cmd_rooms_back(self) -> None:
        """One level up: room -> room list -> dashboard."""
        if self.state["room_selected"]:
            self._home.select_room(None)
        else:
            self._cmd_mode_set("dashboard")
        self._touch()

    def _cmd_ha_act(self, id: str, action: str, **args: Any) -> None:
        """A control on a room screen. The home model enforces exposure and the action allowlist."""
        self._spawn(self._home.act(id, action, **args))
        self._touch()

    # ---- announcements and notifications -------------------------------------------------------

    def _next_note_id(self) -> str:
        self._note_seq += 1
        return f"n{self._note_seq}"

    def _remember(self, item: dict) -> None:
        local = [n for n in self.state["notifications"] if not n["id"].startswith("ha:")]
        ha = [n for n in self.state["notifications"] if n["id"].startswith("ha:")]
        self._set(notifications=[item, *local][:MAX_NOTIFICATIONS] + ha)

    def _cmd_announce_show(self, message: str, title: str = "", kind: str = "info", seconds: float | None = None) -> None:
        """Take over the screen with a message (HA announce service, later a voice announcement). Always logged."""
        kind = kind if kind in ("info", "warning", "critical") else "info"
        secs = 0.0 if kind == "critical" else float(self.config.announcement_seconds if seconds is None else seconds)
        item = {"id": self._next_note_id(), "title": str(title)[:80], "message": str(message)[:600], "kind": kind,
                "seconds": secs, "ts": int(self._clock() * 1000)}
        self._remember(item)
        self._announce_queue.append(item)
        self._set(screen_on=True)                      # an announcement wakes the display
        if self.state["announcement"] is None:
            self._show_next_announcement()
        else:                                          # the card shows "+N more"
            self._set(announcement={**self.state["announcement"], "pending": len(self._announce_queue)})

    def _show_next_announcement(self) -> None:
        if not self._announce_queue:
            self._announce_deadline = None
            self._set(announcement=None)
            return
        item = self._announce_queue.pop(0)
        self._announce_deadline = (self._clock() + item["seconds"]) if item["seconds"] > 0 else None
        self._set(announcement={**item, "pending": len(self._announce_queue)})

    def _cmd_announce_dismiss(self) -> None:
        self._show_next_announcement()

    def _cmd_notify_add(self, message: str, title: str = "", kind: str = "info") -> None:
        """A quiet notification: goes into the notification list (and its badge) without taking over the screen."""
        kind = kind if kind in ("info", "warning", "critical") else "info"
        self._remember({"id": self._next_note_id(), "title": str(title)[:80], "message": str(message)[:600],
                        "kind": kind, "seconds": 0, "ts": int(self._clock() * 1000)})

    def _cmd_notifications_clear(self) -> None:
        self._set(notifications=[n for n in self.state["notifications"] if n["id"].startswith("ha:")])

    def _cmd_notifications_remove(self, id: str) -> None:
        self._set(notifications=[n for n in self.state["notifications"] if n["id"] != id or id.startswith("ha:")])

    def _ha_notifications(self, items: list[dict]) -> None:
        """Home Assistant's own persistent notifications (optional). They replace the previous 'ha:' entries."""
        local = [n for n in self.state["notifications"] if not n["id"].startswith("ha:")]
        ha = [{**n, "seconds": 0, "ts": 0} for n in items]
        self._set(notifications=local + ha)

    def _cmd_photo_next(self, delta: int = 1) -> None:
        self._cycle_deadline = self._clock() + self.config.photo_interval_s
        if self._advancing or not self._playlist:
            return
        self._spawn(self._advance(delta))

    async def _advance(self, delta: int) -> None:
        self._advancing = True
        try:
            photo = await self._playlist.advance(delta)
            if photo:
                self._set(photo=photo.to_dict())
        finally:
            self._advancing = False

    def _cmd_timer_start(self, seconds: int, label: str) -> None:
        self._timers.add(int(seconds), label, int(self._clock() * 1000))
        self._set(timers=self._timers.snapshot())

    def _cmd_timer_cancel(self, id: int) -> None:
        r = self.state["ringing"]
        if r and r["id"] == int(id):
            self._cmd_timer_dismiss()
        elif self._timers.cancel(int(id)):
            self._set(timers=self._timers.snapshot())

    def _local_timer(self, id: int):
        t = self._timers.get(int(id))
        return t if t is not None and t.local else None

    def _cmd_timer_pause(self, id: int) -> None:
        if self._local_timer(id) and self._timers.pause(int(id), int(self._clock() * 1000)):
            self._set(timers=self._timers.snapshot())

    def _cmd_timer_resume(self, id: int) -> None:
        if self._local_timer(id) and self._timers.resume(int(id), int(self._clock() * 1000)):
            self._set(timers=self._timers.snapshot())

    def _cmd_timer_extend(self, id: int, seconds: int = 60) -> None:
        if self._local_timer(id) and self._timers.extend(int(id), int(seconds), int(self._clock() * 1000)):
            self._set(timers=self._timers.snapshot())

    def _cmd_timer_dismiss(self) -> None:
        """Stop the ringing timer (and remove it)."""
        r = self.state["ringing"]
        if r:
            self._timers.cancel(r["id"])
        self._ring_deadline = None
        self._set(ringing=None, timers=self._timers.snapshot())

    def _cmd_timer_snooze(self, seconds: int) -> None:
        """Stop the ringing and run the same timer again for `seconds`."""
        r = self.state["ringing"]
        if not r:
            return
        now_ms = int(self._clock() * 1000)
        if not self._timers.snooze(r["id"], int(seconds), now_ms):
            self._timers.add(int(seconds), r["label"], now_ms)
        self._ring_deadline = None
        self._set(ringing=None, timers=self._timers.snapshot())

    def _cmd_media_toggle(self) -> None:
        self._spawn(self._home.media("toggle"))

    def _cmd_media_next(self) -> None:
        self._spawn(self._home.media("next"))

    def _cmd_media_prev(self) -> None:
        self._spawn(self._home.media("prev"))

    # ---- music (core/media): the active source's transport, not the Home Assistant media player above ----------

    def _cmd_music_command(self, name: str, **args: Any) -> None:
        """toggle | play | pause | next | prev | seek (seconds=) | volume (level=) | mute | stop"""
        self.music.handle(name, **args)
        self._touch()

    def _cmd_music_play_url(self, url: str, title: str = "") -> None:
        """Home Assistant's media_player.play_media: play a URL on this display (it takes the speaker like any source)."""
        self._spawn(self._play_url(url, title))

    async def _play_url(self, url: str, title: str = "") -> None:
        source = self.music._adapters.get("homeassistant")
        if source is None:                                   # the audio output opens the first time it is needed
            from .media.sources.url import UrlSource
            source = UrlSource(self._open_url_audio())
            self.music.register(source)
            await source.start()
        await source.play_url(url, title)
        self._touch()

    def _open_url_audio(self):
        return self._open_audio(prebuffer_ms=150)

    def _cmd_music_simulate(self, source: str, action: str = "play") -> None:
        """Demo mode only: make a fake source behave like a sender (play | pause | end)."""
        src = self.music._adapters.get(source)
        if not self.config.music_demo or src is None or not hasattr(src, "play"):
            return
        {"play": lambda: (src.connect("Demo phone"), src.play()), "pause": src.pause, "end": src.disconnect}.get(action, lambda: None)()

    # ---- music library (Music Assistant) ---------------------------------------------------------

    def _library_state(self, **changes: Any) -> None:
        self._set(library={**self.state["library"], **changes})

    def _cmd_library_open(self) -> None:
        """Show the library screen: whatever was last searched, else the browse sections."""
        if self.library is None:
            return
        self._touch()
        if not self.state["library"]["sections"]:
            self._spawn(self._library_load(self.state["library"]["query"]))

    def _cmd_library_search(self, query: str) -> None:
        if self.library is None:
            return
        self._touch()
        self._spawn(self._library_load(str(query)[:100]))

    async def _library_load(self, query: str) -> None:
        from .media.library import LibraryError
        query = query.strip()
        self._library_state(busy=True, query=query, error="")
        try:
            sections = await (self.library.search(query) if query else self.library.browse())
        except LibraryError as e:
            self._library_state(busy=False, sections=[], error=str(e))
            return
        if self.state["library"]["query"] == query:             # a newer search may have replaced this one
            self._library_state(busy=False, sections=sections, error="" if sections else
                                ("Nothing found" if query else "Nothing in your library yet"))

    def _cmd_library_voice(self) -> None:
        """Search the library by speaking: record one utterance, have Home Assistant turn it into text, search for it."""
        if self.library is None:
            return
        if self.voice is None or not self.state["voice_ready"]:
            self._cmd_announce_show(message="Voice search needs the voice assistant connected to Home Assistant.",
                                    title="Voice", kind="warning")
            return
        self._touch()
        self._spawn(self._library_voice())

    async def _library_voice(self) -> None:
        self._library_state(listening=True, error="")
        try:
            text = await self.voice.listen_for_text(self._transcribe)
        finally:
            self._library_state(listening=False)
        if text:
            await self._library_load(text[:100])
        else:
            self._library_state(error="Didn't catch that")

    async def _transcribe(self, pcm: bytes) -> str:
        client = getattr(self._home, "client", None)
        if client is None or client.status != "connected":
            raise HAError("Home Assistant is not connected")
        return await client.speech_to_text(pcm, entity_id=self.config.voice_stt_entity, language=self.config.voice_language)

    def _cmd_library_play(self, uri: str) -> None:
        if self.library is None:
            return
        self._touch()
        self._spawn(self._library_play(str(uri)))

    async def _library_play(self, uri: str) -> None:
        from .media.library import LibraryError
        try:
            await self.library.play(uri)
        except LibraryError as e:
            self._cmd_announce_show(message=str(e), title="Music", kind="warning")

    def _cmd_control_toggle(self, id: str) -> None:
        self._spawn(self._home.toggle_control(id))

    def attach_voice(self, satellite: "VoiceSatellite") -> None:
        """Switch from the scripted demo to the real satellite. A ringing timer now stops by itself after 15 minutes
        (the VPE's cap), so the display's own 30 s auto-dismiss gets out of the way."""
        self.voice = satellite
        self.config.ring_auto_dismiss_s = max(self.config.ring_auto_dismiss_s, 15 * 60)
        self.bus.subscribe(lambda ev: satellite.on_state(ev.data["patch"]) if ev.type == "state.patch" else None)

    def _cmd_voice_start(self) -> None:
        """The on-screen mic button is the VPE's centre button: it runs the wake cascade."""
        if self.voice is None:
            self._cancel_voice()
            self._voice_task = asyncio.create_task(simulate_assist(self._set, self._sleep), name="voice")
        elif not self.state["voice_ready"]:
            self._cmd_announce_show(message="Voice is not connected to Home Assistant yet.", title="Voice", kind="warning")
        else:
            self.voice.wake(button=True)

    def _cmd_voice_stop(self) -> None:
        if self.voice is None:
            self._cancel_voice()
            self._set(voice="idle")
        else:
            self.voice.stop_assistant()

    def _cmd_voice_timer(self, kind: int, ha_id: str, name: str, total: int, left: int, active: bool = True) -> None:
        """A timer event from Home Assistant's voice pipeline (0 started, 1 updated, 2 cancelled, 3 finished). An update
        with `active` false is "pause the timer"; active again is "resume"."""
        now_ms, book = int(self._clock() * 1000), self._timers
        local = self._voice_timers.get(ha_id)
        if local is not None and book.get(local) is None:
            local = self._voice_timers.pop(ha_id, None)
        if kind in (0, 1):
            if local is not None:
                book.set_left(local, left, now_ms, name or None, total)
            else:
                t = book.add(left, name or "Timer", now_ms, total=total)
                t.local = False                              # Home Assistant keeps the real clock for this one
                local = self._voice_timers[ha_id] = t.id
            (book.resume if active else book.pause)(local, now_ms)
        elif kind == 2 and local is not None:
            book.cancel(local)
            self._voice_timers.pop(ha_id, None)
        elif kind == 3 and local is not None:
            book.set_left(local, 0, now_ms)                  # ring now; tick() turns the expired timer into the ring
            book.resume(local, now_ms)                       # (a paused timer that finishes still rings)
            self._voice_timers.pop(ha_id, None)
        self._set(timers=book.snapshot())

    def _cmd_ui_activity(self) -> None:
        self._touch()
        if not self.state["screen_on"]:         # touching a dark screen wakes it
            self._set(screen_on=True)

    def _cmd_ui_gesture(self, kind: str) -> None:
        """Report a touch gesture (tap, swipe_left, swipe_right, swipe_down) for integrations such as HA events."""
        self.bus.emit("gesture", kind=kind)

    def _cmd_screen_set(self, on: bool) -> None:
        self._set(screen_on=bool(on))
        if on:
            self._touch()

    def _cmd_brightness_set(self, percent: float) -> None:
        self._set(brightness=int(min(100, max(10, percent))))

    def _cmd_config_set(self, blur: bool | None = None, stats: bool | None = None,
                        photo_interval_s: float | None = None, crossfade_ms: int | None = None) -> None:
        """Runtime tweaks (not persisted: the settings web UI is what writes config.toml)."""
        if blur is not None:
            self._set(blur=bool(blur))
        if stats is not None:
            self._set(stats=bool(stats))
        if photo_interval_s is not None:
            self.config.photo_interval_s = float(min(3600, max(2, photo_interval_s)))
            self._cycle_deadline = self._clock() + self.config.photo_interval_s
            self._set(photo_interval_s=self.config.photo_interval_s)
        if crossfade_ms is not None:
            self._set(crossfade_ms=int(min(5000, max(0, crossfade_ms))))

    # ---- internals --------------------------------------------------------------------------

    def _spawn(self, coro: Coroutine) -> None:
        """Run a background job; failures become an `error` event, never a crashed core."""
        async def guarded() -> None:
            try:
                await coro
            except asyncio.CancelledError:
                raise
            except HAError as e:
                self.bus.emit("error", code="ha", message=str(e))
            except ActionError as e:
                self.bus.emit("error", code="action", message=str(e))
            except Exception as e:
                log.exception("background job failed")
                self.bus.emit("error", code="internal", message=str(e))
        t = asyncio.create_task(guarded())
        self._jobs.add(t)
        t.add_done_callback(self._jobs.discard)

    def _cancel_voice(self) -> None:
        if self._voice_task and not self._voice_task.done():
            self._voice_task.cancel()
        self._voice_task = None

    def _touch(self) -> None:
        """User activity: restart the dashboard idle countdown."""
        self._idle_deadline = (self._clock() + self.config.idle_s) if self.state["mode"] != "ambient" else None

    def _set(self, **changes: Any) -> None:
        patch = {k: v for k, v in changes.items() if self.state.get(k) != v}
        if not patch:
            return
        self.state.update(patch)
        self.bus.emit("state.patch", patch=patch)
        if "ringing" in patch or "announcement" in patch or "voice" in patch or "voice_busy" in patch:
            self._update_duck()

    def _update_duck(self) -> None:
        """Music steps back while a timer rings, an announcement is up or the assistant is talking."""
        music = getattr(self, "music", None)
        if music is not None:
            s = self.state
            music.duck(bool(s["ringing"] or s["announcement"] or s["voice"] != "idle" or s["voice_busy"]))

    async def tick(self) -> None:
        """One scheduling pass. Public so tests can drive it with a fake clock."""
        now = self._clock()
        self.music.tick()

        expired = None if self.state["ringing"] else self._timers.start_ringing(int(now * 1000))
        if expired:
            self._ring_deadline = now + self.config.ring_auto_dismiss_s
            self._set(ringing=expired.to_dict(), timers=self._timers.snapshot())
        if self._ring_deadline is not None and now >= self._ring_deadline:
            self._cmd_timer_dismiss()

        if self.state["mode"] != "ambient":
            if self._idle_deadline is None:
                self._touch()
            elif now >= self._idle_deadline:
                self._cmd_mode_set("ambient")
                self._idle_deadline = None

        if self._announce_deadline is not None and now >= self._announce_deadline:
            self._show_next_announcement()

        if self._playlist and not self._advancing:
            if self.state["photo"] is None:                 # source was down: keep trying
                if now >= self._photo_retry:
                    self._photo_retry = now + PHOTO_RETRY_S
                    self._spawn(self._advance(1))
            elif now >= self._cycle_deadline:
                self._cmd_photo_next(1)

    async def _run(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:
                log.exception("tick failed")
            await asyncio.sleep(TICK_S)

    async def _stats_loop(self) -> None:
        while True:
            self.bus.emit("stats", rss_mb=rss_mb(), lag_worst_ms=self._lag.worst_ms, lag_slow=self._lag.slow_count,
                          cached_photos=self._playlist.cached_count if self._playlist else 0)
            await asyncio.sleep(STATS_S)
