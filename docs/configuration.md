# Configuration reference

havenOS reads one TOML file, `~/.config/havenos/config.toml` by default. Point `HAVENOS_CONFIG` at a different file to use another. Every key is optional. You normally edit settings in the [web UI](settings-ui.md), which writes this file for you; saving there rewrites the file, drops comments and keeps the previous version as `config.toml.bak`.

`config.example.toml` in the project root is a commented starting point.

## Precedence

For most settings: **environment variable, then config file, then default**. Settings changed in the web UI that are also set by an environment variable stay overridden, and the web API lists them as `env_overrides`.

Boolean environment variables are false when they are `0`, `false` or empty, and true for anything else.

## Secrets

A secret (the Home Assistant token, the Immich key, the Music Assistant token) can be given three ways, checked in this order:

1. its environment variable,
2. an inline value (`token = "..."`),
3. a file path (`token_file = "~/.config/havenos/ha_token"`).

Prefer the file form with a file readable only by the service user. The web UI always writes secrets to their own `0600` files (`ha_token`, `immich_key`, `ma_token`) and the config only points at them.

## `[homeassistant]`

Home Assistant is used only when both a URL and a token are set. Without them the dashboard shows demo data.

| Key | Default | Env | Meaning |
|---|---|---|---|
| `url` | none | `HAVENOS_HA_URL` | Base URL, for example `http://homeassistant.local:8123` |
| `token` / `token_file` | none | `HAVENOS_HA_TOKEN` | Long-lived access token (HA profile page) |
| `weather` | none | | Weather entity shown on the ambient screen and dashboard |
| `media_player` | none | | Media player for the now-playing strip and dashboard music card |
| `room` | the area HA assigns to this device | | Area id or name for this display |
| `persistent_notifications` | `false` | | Also show Home Assistant's own notification list |

### `[[homeassistant.controls]]`

Up to 6 quick-control tiles, in order. With none listed, the tiles are the device room's major exposed entities.

| Key | Meaning |
|---|---|
| `entity` | Entity id (required) |
| `label` | Shown name; defaults to the entity's friendly name |
| `icon` | `bulb`, `thermo`, `camera`, `scenes` or `gear`; defaults by domain |

Tap behaviour depends on the domain: `light`, `switch`, `fan`, `input_boolean` and `cover` toggle, `lock` locks and unlocks, `scene` and `script` run, and others are display-only.

## `[photos]`

| Key | Default | Env | Meaning |
|---|---|---|---|
| `source` | `immich` if an Immich URL is set, else `nasa` | `HAVENOS_PHOTO_SOURCE` | `nasa`, `local` or `immich` |
| `dir` | the bundled sample photos | `HAVENOS_PHOTOS` | Folder used when the source is `local` |

### `[photos.nasa]`

NASA's Image of the Day, shuffled. It needs internet access and no key. The feed holds about 50 to 60 recent images; each full-size original is downloaded when it comes up, scaled down, and deleted as it ages out.

| Key | Default | Meaning |
|---|---|---|
| `url` | `https://www.nasa.gov/feeds/iotd-feed/` | The RSS feed (only worth changing if NASA moves it) |

### `[photos.immich]`

Used when `source = "immich"` and both a URL and a key are set.

| Key | Default | Env | Meaning |
|---|---|---|---|
| `url` | none | `HAVENOS_IMMICH_URL` | Immich base URL |
| `api_key` / `api_key_file` | none | `HAVENOS_IMMICH_KEY` | API key |
| `album` | empty | `HAVENOS_IMMICH_ALBUM` | Album id; empty means random photos from the whole library |
| `shuffle` | `true` | | `false` = server order, no recency weighting |
| `recency_half_life_days` | `365` | | An asset's weight halves every this many days; `0` turns the preference off |
| `recency_floor` | `0.1` | | Lowest weight, so old photos still appear |
| `list_size` | `120` | | Photos per pass; each pass is a fresh weighted sample |

## `[display]`

| Key | Default | Env | Meaning |
|---|---|---|---|
| `photo_interval_s` | `8` | `HAVENOS_INTERVAL` (milliseconds) | Seconds per photo |
| `idle_s` | `30` | `HAVENOS_IDLE` | Seconds before the dashboard returns to the ambient screen |
| `crossfade_ms` | `1500` | `HAVENOS_CROSSFADE` | Photo crossfade |
| `blur` | `true` | `HAVENOS_BLUR` | Glass blur behind panels |
| `brightness` | `100` | `HAVENOS_BRIGHTNESS` | Percent, 10 to 100 (software dimming for now) |

Seconds per photo, crossfade, brightness and blur can also be changed from Home Assistant, and those changes are written back to this file. Screen on/off, mode and the current photo are not saved: the display always starts awake on the ambient screen.

## `[web]`

| Key | Default | Env | Meaning |
|---|---|---|---|
| `enabled` | `true` | `HAVENOS_WEB` | Run the settings web UI |
| `host` | `0.0.0.0` | `HAVENOS_WEB_HOST` | Bind address; `127.0.0.1` for the device only |
| `port` | `8787` | `HAVENOS_WEB_PORT` | |

## `[esphome]`

Opt-in. See [Home Assistant](home-assistant.md).

| Key | Default | Env | Meaning |
|---|---|---|---|
| `enabled` | `false` | `HAVENOS_ESPHOME` | Appear in Home Assistant as an ESPHome device |
| `name` | `havenos-<hostname>` | `HAVENOS_ESPHOME_NAME` | Device name |
| `port` | `6053` | `HAVENOS_ESPHOME_PORT` | ESPHome API port |
| `key` / `key_file` | none | `HAVENOS_ESPHOME_KEY` | Noise encryption key (base64, 32 bytes). Empty means plain text. **Required for voice.** Make one with `python -m havenos.core.esphome.noise` |

## `[voice]`

Opt-in; behaves like a Home Assistant Voice Preview Edition. Needs `[esphome]` enabled **with a `key`** (the link carries microphone audio, so voice refuses to start in plain text). Install the wake word detector with `pip install 'havenos[voice]'`. Design: [spec 05](specs/05-voice-pipeline.md). Not yet run on real hardware.

| Key | Default | Env | Meaning |
|---|---|---|---|
| `enabled` | `false` | `HAVENOS_VOICE` | Turn the voice satellite on |
| `profile` | `default` | `HAVENOS_VOICE_PROFILE` | `xvf3800` (reSpeaker XVF3800 USB, 48 kHz, preferred), `lite` (reSpeaker Lite USB, 16 kHz) or `default` (the system's own sound device, no hardware echo cancellation) |
| `device` | profile's name | `HAVENOS_VOICE_DEVICE` | Sound device name substring, overriding the profile's |
| `wake_words` | `["okay_nabu"]` | | Up to two of `okay_nabu`, `hey_jarvis`, `hey_mycroft`. Home Assistant can change them and the change is saved here |
| `sensitivity` | `Moderately sensitive` | | `Slightly sensitive`, `Moderately sensitive` or `Very sensitive` |
| `wake_sound` | `true` | | Play a chime after the wake word |
| `stop_model` | none | | Path to the VPE's "stop" microWakeWord `.json` (not bundled). Without it there is no stop word |
| `stt_entity` | first `stt.*` | | Home Assistant speech-to-text entity used for spoken library search, for example `stt.faster_whisper` |
| `language` | Home Assistant's | | Language sent with that speech-to-text request |

## `[notifications]`

| Key | Default | Meaning |
|---|---|---|
| `announcement_seconds` | `20` | How long an announcement stays up; critical ones stay until dismissed |

## `[music]`

See [Music](music/index.md).

| Key | Default | Env | Meaning |
|---|---|---|---|
| `audio_device` | system default | `HAVENOS_AUDIO_DEVICE` | Output device name (substring); set on the settings page under Sound. Empty uses the system default if it is stereo, else the first stereo output |
| `idle_s` | `600` | | A paused source frees the speaker after this many seconds |
| `hint` | `false` | | Show "ready to cast" with the available sources while nothing plays |
| `duck_db` | `-20` | | Music level while an announcement, timer or the assistant is speaking |

### `[music.airplay]`

| Key | Default | Env | Meaning |
|---|---|---|---|
| `enabled` | `false` | `HAVENOS_AIRPLAY` | |
| `name` | `havenOS <hostname>` | `HAVENOS_AIRPLAY_NAME` | Name senders see |
| `port` | `7000` | `HAVENOS_AIRPLAY_PORT` | Use `7100` on a Mac |
| `binary` | `shairport-sync` on `PATH` | `HAVENOS_AIRPLAY_BINARY` | Path to the binary |
| `manage` | `true` | | Run shairport-sync as a child process; `false` uses one already running |
| `audio` | `true` | `HAVENOS_AIRPLAY_AUDIO` | Play the audio on this device; `false` = display and remote only |

### `[music.sendspin]`

| Key | Default | Env | Meaning |
|---|---|---|---|
| `enabled` | `false` | `HAVENOS_SENDSPIN` | Opens a LAN port and advertises over mDNS |
| `name` | `havenOS <hostname>` | `HAVENOS_SENDSPIN_NAME` | |
| `port` | `8928` | `HAVENOS_SENDSPIN_PORT` | |
| `audio` | `true` | `HAVENOS_SENDSPIN_AUDIO` | Play on this device (declares the player role) |
| `allow_unpaired` | `true` | | Offer guest access so Music Assistant can add the display without a manual pairing step |

### `[music.spotify]`

| Key | Default | Env | Meaning |
|---|---|---|---|
| `enabled` | `false` | `HAVENOS_SPOTIFY` | |
| `name` | `havenOS <hostname>` | `HAVENOS_SPOTIFY_NAME` | |
| `api_port` | `3678` | `HAVENOS_SPOTIFY_PORT` | go-librespot's local API (127.0.0.1) |
| `binary` | `go-librespot` on `PATH` | `HAVENOS_SPOTIFY_BINARY` | |
| `manage` | `true` | | Run go-librespot as a child process; `false` connects to one already running |
| `audio` | `true` | `HAVENOS_SPOTIFY_AUDIO` | |

### `[music.assistant]`

| Key | Default | Env | Meaning |
|---|---|---|---|
| `url` | empty | `HAVENOS_MA_URL` | For example `http://homeassistant.local:8095`; setting it enables the library |
| `token` / `token_file` | empty | `HAVENOS_MA_TOKEN` | Long-lived token from Music Assistant, Settings, Profile |
| `player_id` | empty | `HAVENOS_MA_PLAYER` | This display's player; empty finds it by its Sendspin name |

## Environment variables with no config key

| Variable | Meaning |
|---|---|
| `HAVENOS_CONFIG` | Path of the config file |
| `HAVENOS_SIZE` | Window size, for example `1024x600` (default `1280x800`) |
| `HAVENOS_FULLSCREEN` | `1` for a kiosk-style window |
| `HAVENOS_STATS` | `1` shows the stats HUD (memory, loop lag, photo source, HA status) |
| `HAVENOS_CACHE` | Photo cache folder (default `~/.cache/havenos/photos`) |
| `HAVENOS_LOG` | Log level (default `INFO`) |
| `HAVENOS_MUSIC_DEMO` | `1` adds fake AirPlay and Spotify sources, keys `1` to `4` |
| `HAVENOS_SHOT` | Headless screenshot path prefix; takes screenshots, then quits (use with `QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software`) |
| `QT_QPA_PLATFORM` | Qt platform plugin; `eglfs` on a Pi without a desktop |

## Files the app writes

| Path | What |
|---|---|
| `~/.config/havenos/config.toml` | Settings (and `config.toml.bak`) |
| `~/.config/havenos/web_code` | Web UI setup code |
| `~/.config/havenos/ha_token`, `immich_key`, `ma_token` | Secrets written by the web UI |
| `~/.config/havenos/device_mac` | Stable device identity for Home Assistant |
| `~/.cache/havenos/photos` | Photo cache, trimmed as photos age out |

On the Pi service these live in `/var/lib/havenos` (see [Raspberry Pi](raspberry-pi.md)).
