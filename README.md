# havenOS

An open-source ambient smart display for a Raspberry Pi 4. It shows a slideshow of photos behind glass-style overlays, becomes a Home Assistant dashboard when you touch it, plays music from your phone, and can act as a voice assistant that looks like a Home Assistant Voice Preview Edition to Home Assistant.

It is one Python process: a pure-Python core (no Qt) with a Qt Quick interface on top, drawing straight to the display (EGLFS) with no desktop.

> **Status: early.** It runs on a Raspberry Pi 4 with a touch screen, with AirPlay 2, Sendspin and a real Home Assistant checked. Voice is built but has not run on a microphone, Spotify Connect only works on some accounts, and the Pi performance gates are not measured. [What has been checked](docs/index.md#what-has-been-checked) lists it area by area.

## What it does

- **Ambient screen.** Photos from NASA's Image of the Day (the default, no account needed), an [Immich](https://immich.app) library, or a local folder, with a clock, weather and now-playing on top.
- **Dashboard.** Tap the screen for weather, music, timers and quick controls from Home Assistant. A Rooms screen controls each room's lights, climate, fans, covers, media, locks and scenes. Only entities you have exposed to Assist are ever shown.
- **Music.** Appears as an AirPlay 2 receiver, a Sendspin player for Music Assistant, and (on some accounts) a Spotify Connect device. One source plays at a time, the newest wins, and the screen shows what is playing. Browse and search a Music Assistant library on the display.
- **Timers, announcements, notifications.** Timers get a full-screen view; Home Assistant announcements take over the screen.
- **A Home Assistant device.** Optionally shows up in Home Assistant as an ESPHome device, with screen, brightness, timers and a media player. Built to also act as a voice satellite.
- **Easy setup.** On first boot the display shows a QR code. Scan it with your phone and a guided setup page walks through Home Assistant, photos, sound and music. Everything can be changed later on the same page.

## Install on a Raspberry Pi

You need a Raspberry Pi 4 (2 GB or more), a display, and a fresh **Raspberry Pi OS Lite 64-bit (Debian 13, "Trixie")**. Connect the display, then on the Pi:

```bash
curl -fsSL https://raw.githubusercontent.com/nprail/havenos/main/deploy/install.sh | sudo bash
```

It installs the packages, builds the AirPlay 2 receiver (about ten minutes), starts havenOS as a service and prints the settings address. Scan the QR code on the display to finish setup. Details, options and things to know about the Pi are in [docs/raspberry-pi.md](docs/raspberry-pi.md). Tested so far on a Pi 4 with an 800x480 DSI touch screen; the install script has been re-run on an installed Pi but not yet from a blank card.

## Try it on a Mac or Linux desktop

No Pi, Home Assistant or Immich is needed: with nothing configured it shows demo data and NASA photos.

```bash
git clone https://github.com/nprail/havenos && cd havenos
./scripts/launch.command        # creates .venv, installs, runs (Python 3.12 or newer)
```

On first run the display shows the pairing screen; choose **Not now** to look around. [Getting started](docs/getting-started.md) covers keyboard shortcuts, fake Home Assistant and Immich servers, and music on a desktop.

## Documentation

Start at [docs/index.md](docs/index.md); `npm install && npm run docs:dev` serves it as a site.

| | |
|---|---|
| [Getting started](docs/getting-started.md) | Run it on a desktop |
| [Raspberry Pi](docs/raspberry-pi.md) | Install and notes |
| [Settings page](docs/settings-ui.md) | Pairing, setup wizard, every setting |
| [Configuration](docs/configuration.md) | `config.toml` and environment variables |
| [Home Assistant](docs/home-assistant.md) | Data, rooms, the ESPHome device |
| [Music](docs/music/index.md) | AirPlay, Sendspin, Spotify, Music Assistant |
| [Troubleshooting](docs/troubleshooting.md) | Common problems |
| [Architecture](docs/architecture.md), [Contributing](docs/contributing.md), [Specs](docs/specs/) | How it works and why |
| [TODO.md](TODO.md) | What is left |

## Repository layout

```
src/havenos/
  core/     pure Python, no Qt imports (enforced by tests/test_import_boundary.py): state, commands, Home Assistant,
            photos, music sources and the audio mixer, voice, the settings web server
  bridge/   the one place Qt meets the core (a QObject mirror of core state, and slots that forward commands)
  qml/      the interface; view only, no logic
  web/      the settings page (plain JS, prebuilt Tailwind CSS, no Node needed to run)
  assets/   fonts, icons, sample photos, sounds
deploy/     install.sh, systemd units, the music daemon installer
scripts/    desktop launchers and fake Home Assistant and Immich servers
docs/       user docs, specs and design notes
tests/      the test suite
```

## Development

```bash
.venv/bin/python -m pytest      # about 380 tests: fake clock, in-process fake servers, a real aioesphomeapi client and Sendspin server
```

The ground rules (the core never imports Qt, one command path, QML is view only) are in [docs/contributing.md](docs/contributing.md). Developer notes that used to live here are in [docs/implementation-notes.md](docs/implementation-notes.md).

## Licence

havenOS is released under the [MIT License](LICENSE). The bundled icons, sounds, photos and fonts keep their own licences (see Credits). It uses Qt (LGPLv3) as a separately installed library: the Pi install takes it from Debian, and it is not bundled or modified.

## Credits

- **Voice sounds** (wake chime, timer, mute, cloud-expired message): from the [Home Assistant Voice Preview Edition](https://github.com/esphome/home-assistant-voice-pe/tree/dev/sounds) firmware, © 2024 [Clayton Charles Tapp](https://www.cctaudio.com/), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). See [`src/havenos/assets/sounds/ATTRIBUTION.md`](src/havenos/assets/sounds/ATTRIBUTION.md).
- **Sample photos:** NASA Image of the Day. See [`src/havenos/assets/photos/ATTRIBUTION.md`](src/havenos/assets/photos/ATTRIBUTION.md).
- **Icons:** [Lucide](https://lucide.dev) (ISC, with MIT-licensed Feather portions). See [`src/havenos/assets/icons/LICENSE.md`](src/havenos/assets/icons/LICENSE.md).
- **Fonts:** [Inter](https://github.com/rsms/inter) and [Urbanist](https://github.com/coreyhu/Urbanist), SIL Open Font License 1.1. See [`src/havenos/assets/fonts/LICENSE.md`](src/havenos/assets/fonts/LICENSE.md).
- Built on [Qt](https://www.qt.io/) / PySide6, aiohttp, aioesphomeapi, aiosendspin, [shairport-sync](https://github.com/mikebrady/shairport-sync) and [go-librespot](https://github.com/devgianlu/go-librespot).
