# havenOS

An open-source ambient smart display for a Raspberry Pi 4: a photo slideshow with glass overlays, a Home Assistant dashboard, music from AirPlay, Sendspin and Spotify Connect, and (planned) a voice assistant that behaves like a Home Assistant Voice Preview Edition.

## Start here

- [Getting started](getting-started.md): run it on a desktop in a few minutes, with or without your own servers.
- [Configuration reference](configuration.md) and the [settings web UI](settings-ui.md).
- [Troubleshooting](troubleshooting.md).

## Connect it to your home

- [Home Assistant](home-assistant.md): data source, rooms, and adopting the display as an ESPHome device.
- [Music](music/index.md): [AirPlay](music/airplay.md), [Sendspin](music/sendspin.md), [Spotify Connect](music/spotify.md) and the [Music Assistant library](music/music-assistant.md).
- [Raspberry Pi](raspberry-pi.md): the target hardware.

## How it works

- [Architecture](architecture.md), [Contributing](contributing.md), [Decisions](decisions.md) and [Implementation notes](implementation-notes.md).
- The specs: [common requirements](specs/00-common.md), the [Qt + Python app](specs/03-qt-python-single.md), [ESPHome](specs/04-esphome-integration.md), [voice](specs/05-voice-pipeline.md), [rooms and notifications](specs/06-rooms-exposure-notifications.md) and [music](specs/07-music-pipeline.md).

## What has been checked

| Area | Checked on |
|---|---|
| ESPHome device, AirPlay, Sendspin | A real Home Assistant |
| Spotify Connect | Works only on some accounts |
| Rooms, exposure, announcements, notifications | A real Home Assistant |
| Music Assistant library | A fake server only |
| Raspberry Pi | One Pi 4: the app, touch, AirPlay 2, Sendspin and Home Assistant work; no performance gates measured |
