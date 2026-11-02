# Getting started

Run havenOS on a Mac or Linux desktop first. You do not need a Raspberry Pi, a Home Assistant server or an Immich library to see it work: with nothing configured it shows demo data and NASA's Image of the Day (set `HAVENOS_PHOTO_SOURCE=local` for the bundled sample photos, e.g. when offline).

## Requirements

- Python 3.12 or newer.
- A desktop with a GPU-backed window system. PySide6 (Qt 6) is installed from a wheel, so you do not need a system Qt on a desktop.
- Optional, for the music sources: `shairport-sync` (AirPlay) and `go-librespot` (Spotify Connect). See [Music](music/index.md).

## First run

From the project root:

```bash
./scripts/launch.command
```

It creates `.venv`, installs the project with its dev extras, and starts the app with the stats HUD on. The first window is the ambient screen: photos, the clock and the weather.

On a new install the display opens on the **pairing screen** (a QR code and a setup code for the [settings page](settings-ui.md)). Choose **Not now** to look around; the gear on the dashboard brings it back.

To install by hand instead:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
HAVENOS_STATS=1 python -m havenos
```

## Try it against fake servers

`scripts/dev_servers.py` runs a fake Home Assistant and a fake Immich. The second launcher starts both and points the app at them with `scripts/dev-config.toml`:

```bash
./scripts/launch-dev.command
```

Use this to exercise the Home Assistant and Immich code paths, rooms, announcements and notifications without touching your real home. Run `./scripts/launch.command` once first so the virtual environment exists.

## Keyboard

These work in a desktop window. On the device the same things happen by touch.

| Key | Action |
|---|---|
| `a` / `d` | Ambient screen / dashboard |
| `←` / `→` | Previous / next photo |
| `r` | Rooms screen |
| `n` | Notification list |
| `l` | Music Assistant library |
| `m` | Now-playing view (while music is active) |
| `u` | Timers view (while a timer is running) |
| `t` | Start a 5-second demo timer |
| `v` | Run the simulated voice sequence |
| `b` | Toggle glass blur |
| `f` | Toggle the stats HUD |
| `1` `2` `3` `4` | Demo music: AirPlay plays, Spotify plays, pause, end (needs `HAVENOS_MUSIC_DEMO=1`) |
| `Esc` | Dismiss a ringing timer, the voice sheet, an announcement, the library, or the now-playing and timers views |
| `q` | Quit |

On a touch-only kiosk, triple-tap the top-left corner to toggle the stats HUD.

## The live screen

While music is casting to the display, or any timer is running, the resting screen is not the photos but the **live screen**: a full-screen player, a full-screen timer, or a split of up to three.

- One thing fills the screen. Music and one timer split it in two; music and two timers, or three timers, make three. With more timers than fit, the last one gets a **+N more** button. Music always comes first, then the timers that finish soonest.
- **Tap a tile** to open its controls over the live screen: the now-playing view (seek, previous and next, volume, library, stop) or the timers view (every timer with pause, +1 min and cancel, and quick buttons to add one). Close it and you are back where you were.
- **Swipe up**, or tap **Home**, for the dashboard. When the dashboard times out it returns to the live screen.
- Timers set by voice can be cancelled on the display but not paused or extended, because Home Assistant keeps their clock.
- With no music and no timers, the photos come back.

## Point it at your own things

Open the settings page at `http://<this-machine>:8787`. See the [settings web UI](settings-ui.md) for the sign-in code and what you can change. The same settings can be written by hand in `~/.config/havenos/config.toml`; every key is listed in the [configuration reference](configuration.md).

The usual order:

1. Photos: pick a local folder or Immich.
2. Home Assistant: URL and a long-lived access token, then the weather and media-player entities. See [Home Assistant](home-assistant.md).
3. Optional: let Home Assistant adopt the display as an ESPHome device.
4. Optional: turn on AirPlay, Sendspin, Spotify Connect and Music Assistant.

## Run the tests

```bash
.venv/bin/python -m pytest
```

The tests use a fake clock and in-process fake Home Assistant, Immich and Music Assistant servers, so they need no network. They run headless.

## Quitting

Quit with `q`, by closing the window, or with Ctrl-C or SIGTERM: all stop the helper processes (`shairport-sync`, `go-librespot`) too. Only `kill -9` can leave one holding port 7100 (or 7000). See [Troubleshooting](troubleshooting.md).
