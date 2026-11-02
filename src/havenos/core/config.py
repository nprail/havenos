from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    return default if v is None else v not in ("0", "false", "")


def _secret(table: dict, key: str, env: str) -> str | None:
    """A secret comes from the environment, a `<key>` value, or a `<key>_file` path (in that order)."""
    if os.environ.get(env):
        return os.environ[env].strip()
    if table.get(key):
        return str(table[key]).strip()
    f = table.get(key + "_file")
    if f:
        return Path(f).expanduser().read_text().strip()
    return None


@dataclass
class ControlConfig:
    entity_id: str
    label: str | None = None    # defaults to the entity's friendly name
    icon: str | None = None     # bulb | thermo | camera | scenes | gear (defaults by domain)


@dataclass
class HAConfig:
    url: str
    token: str
    weather_entity: str | None = None
    media_entity: str | None = None
    controls: list[ControlConfig] = field(default_factory=list)   # empty = automatic: the device room's major entities
    forecast_refresh_s: float = 1800.0
    room: str | None = None                  # area id or name; None = the area HA has assigned to this device
    persistent_notifications: bool = False   # also show Home Assistant's own notification list


@dataclass
class ImmichConfig:
    url: str
    api_key: str
    album_id: str | None = None   # None: random photos from the whole library
    shuffle: bool = True          # False: server order, no recency weighting
    # Recency preference: an asset's weight halves every `recency_half_life_days`, but never drops below
    # `recency_floor`, so old photos keep appearing. half_life 0 = no preference (uniform).
    recency_half_life_days: float = 365.0
    recency_floor: float = 0.1
    list_size: int = 120          # photos per playlist pass (each pass is a fresh weighted sample)


NASA_FEED = "https://www.nasa.gov/feeds/iotd-feed/"


@dataclass
class NasaConfig:
    url: str = NASA_FEED          # the Image of the Day RSS feed (no key, no parameters)


@dataclass
class Config:
    photo_dir: Path
    cache_dir: Path
    width: int = 1280
    height: int = 800
    fullscreen: bool = False
    photo_interval_s: float = 8.0   # photo cycle
    idle_s: float = 30.0            # dashboard -> ambient
    ring_auto_dismiss_s: float = 30.0
    blur: bool = True
    stats: bool = False
    max_photo_size: tuple[int, int] = field(default=(1920, 1200))
    ha: HAConfig | None = None          # None: demo data, no Home Assistant
    immich: ImmichConfig | None = None  # None: local photo_dir
    nasa: NasaConfig | None = None      # None (and no immich): local photo_dir
    history: int = 6                    # photos kept for swipe-back
    prefetch: int = 2                   # photos prepared ahead of the one on screen
    crossfade_ms: int = 1500
    brightness: int = 100               # percent, 10-100
    web_enabled: bool = True            # settings web UI
    setup_done: bool = False            # first-run setup finished ([setup] done, or Home Assistant is already configured)
    web_host: str = "0.0.0.0"
    web_port: int = 8787
    announcement_seconds: float = 20.0  # how long an announcement stays up (critical ones stay until dismissed)
    esphome_enabled: bool = False       # appear in Home Assistant as an ESPHome device (opt-in: plain-text, LAN only)
    esphome_name: str = ""              # "" = havenos-<hostname>
    esphome_port: int = 6053
    esphome_key: str = ""               # Noise encryption key (base64, 32 bytes); "" = plain text. Required for voice
    sendspin_enabled: bool = False      # receive from Music Assistant / any Sendspin server (opt-in: opens a LAN port)
    sendspin_name: str = ""             # "" = havenOS <hostname>
    sendspin_port: int = 8928
    sendspin_audio: bool = True         # play Sendspin audio on this device (declares the player role); False = display/remote only
    sendspin_allow_unpaired: bool = True  # offer guest access so Music Assistant can add us without a manual pairing step
    spotify_enabled: bool = False       # appear as a Spotify Connect device (runs go-librespot; Premium account needed)
    spotify_name: str = ""              # "" = havenOS <hostname>
    spotify_api_port: int = 3678        # go-librespot's local API (127.0.0.1)
    spotify_binary: str = ""            # "" = go-librespot on PATH
    spotify_manage: bool = True         # run go-librespot ourselves; False = talk to one already running (systemd on the Pi)
    spotify_audio: bool = True          # play Spotify audio on this device; False = display/remote only
    airplay_enabled: bool = False       # appear as an AirPlay receiver (runs shairport-sync built with pipe output)
    airplay_name: str = ""              # "" = havenOS <hostname>
    airplay_port: int = 7000            # macOS's own AirPlay Receiver uses 7000: pick another (e.g. 7100) when testing on a Mac
    airplay_binary: str = ""            # "" = shairport-sync on PATH
    airplay_manage: bool = True         # run shairport-sync ourselves; False = use one already running (systemd on the Pi)
    airplay_audio: bool = True          # play AirPlay audio on this device; False = display/remote only
    audio_device: str = ""              # output device name (substring); "" = the system default, else the first stereo one
    music_demo: bool = False            # fake AirPlay / Spotify sources + keys 1-3, to exercise the music UI
    music_idle_s: float = 600.0         # a paused source frees the speaker after this long
    music_hint: bool = False            # show a "ready to cast" hint with the available sources while nothing plays
    ma_url: str = ""                    # Music Assistant, e.g. http://homeassistant.local:8095 (enables the library)
    ma_token: str = ""                  # long-lived token (Music Assistant > Settings > Profile)
    ma_player_id: str = ""              # this display's player in Music Assistant; "" = find it by name / Sendspin id
    voice_enabled: bool = False         # behave like a Voice Preview Edition (needs the ESPHome device with a Noise key)
    voice_profile: str = "default"      # default | xvf3800 | lite (the USB mic array; see core/voice/profiles.py)
    voice_device: str = ""              # sound device name substring, overriding the profile's
    voice_stop_model: str = ""          # path to the VPE's "stop" microWakeWord .json (not bundled); "" = no stop word
    voice_stt_entity: str = ""          # Home Assistant speech-to-text entity for spoken library search; "" = the first stt.* one
    voice_language: str = ""            # language for it; "" = Home Assistant's own
    voice_wake_sound: bool = True
    voice_sensitivity: str = "Moderately sensitive"
    voice_wake_words: tuple[str, ...] = ("okay_nabu",)
    duck_db: float = -20.0              # music level while an announcement, timer or the assistant is speaking
    config_path: Path = field(default_factory=lambda: Path.home() / ".config" / "havenos" / "config.toml")

    @property
    def photo_source(self) -> str:
        return "immich" if self.immich else "nasa" if self.nasa else "local"

    @classmethod
    def from_env(cls, assets: Path) -> "Config":
        w, h = (int(x) for x in os.environ.get("HAVENOS_SIZE", "1280x800").split("x"))
        cfg_path = Path(os.environ.get("HAVENOS_CONFIG", Path.home() / ".config" / "havenos" / "config.toml"))
        toml: dict = tomllib.loads(cfg_path.read_text()) if cfg_path.exists() else {}
        disp = toml.get("display", {})
        web = toml.get("web", {})
        esp = toml.get("esphome", {})
        notif = toml.get("notifications", {})
        music = toml.get("music", {})
        sendspin = music.get("sendspin", {})
        spotify = music.get("spotify", {})
        airplay = music.get("airplay", {})
        ma = music.get("assistant", {})
        voice = toml.get("voice", {})
        cache = Path(os.environ.get("HAVENOS_CACHE", Path.home() / ".cache" / "havenos" / "photos"))

        ha_t = toml.get("homeassistant", {})
        ha_url = os.environ.get("HAVENOS_HA_URL") or ha_t.get("url")
        ha_token = _secret(ha_t, "token", "HAVENOS_HA_TOKEN")
        ha = None
        if ha_url and ha_token:
            ha = HAConfig(
                url=ha_url.rstrip("/"), token=ha_token,
                weather_entity=ha_t.get("weather"), media_entity=ha_t.get("media_player"),
                room=(ha_t.get("room") or None), persistent_notifications=bool(ha_t.get("persistent_notifications", False)),
                controls=[ControlConfig(entity_id=c["entity"], label=c.get("label"), icon=c.get("icon"))
                          for c in ha_t.get("controls", [])],
            )

        ph_t = toml.get("photos", {})
        im_t = ph_t.get("immich", {})
        im_url = os.environ.get("HAVENOS_IMMICH_URL") or im_t.get("url")
        im_key = _secret(im_t, "api_key", "HAVENOS_IMMICH_KEY")
        source = os.environ.get("HAVENOS_PHOTO_SOURCE") or ph_t.get("source") or ("immich" if im_url else "nasa")
        immich = None
        nasa = NasaConfig(url=(ph_t.get("nasa", {}).get("url") or NASA_FEED)) if source == "nasa" else None
        if source == "immich" and im_url and im_key:
            immich = ImmichConfig(url=im_url.rstrip("/"), api_key=im_key,
                                  album_id=os.environ.get("HAVENOS_IMMICH_ALBUM") or im_t.get("album"),
                                  shuffle=bool(im_t.get("shuffle", True)),
                                  recency_half_life_days=float(im_t.get("recency_half_life_days", 365)),
                                  recency_floor=float(im_t.get("recency_floor", 0.1)),
                                  list_size=int(im_t.get("list_size", 120)))

        return cls(
            photo_dir=Path(os.environ.get("HAVENOS_PHOTOS", ph_t.get("dir") or assets / "photos")),
            cache_dir=cache,
            width=w, height=h,
            fullscreen=_env_bool("HAVENOS_FULLSCREEN", False),
            photo_interval_s=(int(os.environ["HAVENOS_INTERVAL"]) / 1000.0 if "HAVENOS_INTERVAL" in os.environ
                              else float(disp.get("photo_interval_s", 8.0))),
            idle_s=float(os.environ.get("HAVENOS_IDLE", disp.get("idle_s", 30))),
            blur=_env_bool("HAVENOS_BLUR", bool(disp.get("blur", True))),
            stats=_env_bool("HAVENOS_STATS", False),
            ha=ha, immich=immich, nasa=nasa,
            crossfade_ms=int(os.environ.get("HAVENOS_CROSSFADE", disp.get("crossfade_ms", 1500))),
            brightness=min(100, max(10, int(os.environ.get("HAVENOS_BRIGHTNESS", disp.get("brightness", 100))))),
            setup_done=bool(toml.get("setup", {}).get("done")) or ha is not None,
            web_enabled=_env_bool("HAVENOS_WEB", bool(web.get("enabled", True))),
            web_host=os.environ.get("HAVENOS_WEB_HOST", web.get("host", "0.0.0.0")),
            web_port=int(os.environ.get("HAVENOS_WEB_PORT", web.get("port", 8787))),
            announcement_seconds=float(notif.get("announcement_seconds", 20)),
            esphome_enabled=_env_bool("HAVENOS_ESPHOME", bool(esp.get("enabled", False))),
            esphome_name=os.environ.get("HAVENOS_ESPHOME_NAME", esp.get("name", "")),
            esphome_port=int(os.environ.get("HAVENOS_ESPHOME_PORT", esp.get("port", 6053))),
            esphome_key=_secret(esp, "key", "HAVENOS_ESPHOME_KEY") or "",
            sendspin_enabled=_env_bool("HAVENOS_SENDSPIN", bool(sendspin.get("enabled", False))),
            sendspin_name=os.environ.get("HAVENOS_SENDSPIN_NAME", sendspin.get("name", "")),
            sendspin_port=int(os.environ.get("HAVENOS_SENDSPIN_PORT", sendspin.get("port", 8928))),
            sendspin_audio=_env_bool("HAVENOS_SENDSPIN_AUDIO", bool(sendspin.get("audio", True))),
            sendspin_allow_unpaired=bool(sendspin.get("allow_unpaired", True)),
            spotify_enabled=_env_bool("HAVENOS_SPOTIFY", bool(spotify.get("enabled", False))),
            spotify_name=os.environ.get("HAVENOS_SPOTIFY_NAME", spotify.get("name", "")),
            spotify_api_port=int(os.environ.get("HAVENOS_SPOTIFY_PORT", spotify.get("api_port", 3678))),
            spotify_binary=os.environ.get("HAVENOS_SPOTIFY_BINARY", spotify.get("binary", "")),
            spotify_manage=bool(spotify.get("manage", True)),
            spotify_audio=_env_bool("HAVENOS_SPOTIFY_AUDIO", bool(spotify.get("audio", True))),
            airplay_enabled=_env_bool("HAVENOS_AIRPLAY", bool(airplay.get("enabled", False))),
            airplay_name=os.environ.get("HAVENOS_AIRPLAY_NAME", airplay.get("name", "")),
            airplay_port=int(os.environ.get("HAVENOS_AIRPLAY_PORT", airplay.get("port", 7000))),
            airplay_binary=os.environ.get("HAVENOS_AIRPLAY_BINARY", airplay.get("binary", "")),
            airplay_manage=bool(airplay.get("manage", True)),
            airplay_audio=_env_bool("HAVENOS_AIRPLAY_AUDIO", bool(airplay.get("audio", True))),
            audio_device=os.environ.get("HAVENOS_AUDIO_DEVICE", music.get("audio_device", "")),
            music_demo=_env_bool("HAVENOS_MUSIC_DEMO", False),
            music_idle_s=float(music.get("idle_s", 600)),
            music_hint=bool(music.get("hint", False)),
            ma_url=os.environ.get("HAVENOS_MA_URL", ma.get("url", "")),
            ma_token=_secret(ma, "token", "HAVENOS_MA_TOKEN") or "",
            ma_player_id=os.environ.get("HAVENOS_MA_PLAYER", ma.get("player_id", "")),
            voice_enabled=_env_bool("HAVENOS_VOICE", bool(voice.get("enabled", False))),
            voice_profile=os.environ.get("HAVENOS_VOICE_PROFILE", voice.get("profile", "default")),
            voice_device=os.environ.get("HAVENOS_VOICE_DEVICE", voice.get("device", "")),
            voice_stop_model=voice.get("stop_model", ""),
            voice_stt_entity=voice.get("stt_entity", ""),
            voice_language=voice.get("language", ""),
            voice_wake_sound=bool(voice.get("wake_sound", True)),
            voice_sensitivity=str(voice.get("sensitivity", "Moderately sensitive")),
            voice_wake_words=tuple(voice.get("wake_words", ["okay_nabu"])),
            duck_db=float(music.get("duck_db", -20.0)),
            config_path=cfg_path,
        )
