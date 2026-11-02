# Music

The display can receive music from four places and show what is playing on the ambient strip, the dashboard music card and a full now-playing view (tap the strip).

| Source | What it is | Status |
|---|---|---|
| [AirPlay](airplay.md) | Appears as an AirPlay receiver. Runs `shairport-sync`. | Verified on a real Home Assistant setup |
| [Sendspin](sendspin.md) | Appears as a player in Music Assistant (or any Sendspin server). In-process. | Verified on a real Home Assistant setup |
| [Spotify Connect](spotify.md) | Appears as a Spotify device. Runs `go-librespot`. | Works only on some accounts |
| [Music Assistant library](music-assistant.md) | Browse, search and play your library from the display. | Tested against a fake server only |

All sources are opt-in and off by default.

## One source at a time

Only one source is active at a time, and **the last to start playing wins**. A new sender takes over from the old one, a toast tells you who took over, and the old source is asked to stop:

- AirPlay: the sender is paused if it allows remote control, and the receiver restarts to drop the session.
- Spotify: playback stops and the session is dropped.

A paused source stays on the display, because pausing is not the end of a session. After `[music] idle_s` (600 seconds by default) a paused source frees the speaker. The Home Assistant `media_player` is shown only when nothing is casting.

If two senders keep taking the speaker from each other, havenOS logs a warning.

## What the display shows

Title, artist, album, cover art, position and transport controls. Controls a source cannot honour are disabled: AirPlay play, pause, next and previous only work when the sender offers remote control (Apple Music on iOS and macOS does; most third-party apps are display-only).

## Audio output

Every source plays through one shared mixer and one output device (`core/audio/`), and only the active source is heard. Sources at 44.1 kHz are resampled to the output rate. havenOS uses the system default output if it is stereo, otherwise the first stereo output. To choose one, for example when the default is a Bluetooth headset, set `[music] audio_device` or `HAVENOS_AUDIO_DEVICE` to part of the device name.

The mixer's output is also the exact echo reference that software echo cancellation would need. It runs inside the app rather than in a separate audio process, and there is no multi-room sync. Tested with fake devices; not run on a Pi.

## Ducking

Music drops by `duck_db` (20 dB by default) while an announcement is up, a timer rings or the assistant is active, and comes back over about a second.

## Other settings

- `[music] hint = true` shows "ready to cast" and the available sources while nothing plays.
- Cover art is cached by the core.
- With the [ESPHome device](../home-assistant.md) enabled, the display is also a Home Assistant media player.

## Try it without a sender

```bash
HAVENOS_MUSIC_DEMO=1 ./scripts/launch.command
```

Keys `1` and `2` start fake AirPlay and Spotify playback, `3` pauses, `4` ends it, and `m` opens the now-playing view.

## Not built

The mixer in its own process ([spec 05](../specs/05-voice-pipeline.md)) and multi-room sync. Crossfade on takeover and an on-screen keyboard were dropped from scope. (Home Assistant `play_media` URLs do play, as a source named "Home Assistant"; tested with a fake sound sink only.) The full design is [spec 07](../specs/07-music-pipeline.md).
