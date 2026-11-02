# AirPlay

havenOS appears as an AirPlay receiver by running [`shairport-sync`](https://github.com/mikebrady/shairport-sync) as a child process. It has been tested end to end with a phone and with a real Home Assistant setup.

## Requirements

`shairport-sync` built with the pipe backend and metadata support:

```
./configure --with-pipe --with-metadata --with-metadata-pipe
```

On a Raspberry Pi, also pass `--with-airplay-2` (and install `nqptp`). The adapter is the same for classic AirPlay and AirPlay 2. [`deploy/install-music.sh`](../raspberry-pi.md) builds all of this on a Pi.

## Turn it on

```toml
[music.airplay]
enabled = true
name = "Kitchen display"     # optional; default is "havenOS <hostname>"
```

or set `HAVENOS_AIRPLAY=1`. If `shairport-sync` is not on `PATH`, set `binary` or `HAVENOS_AIRPLAY_BINARY`.

On a Mac, port 7000 belongs to the system's AirPlay Receiver. Pick another port:

```toml
port = 7100
```

(`HAVENOS_AIRPLAY_PORT=7100`.)

## How it works

- Audio comes from shairport-sync's pipe backend. State and cover art come from its metadata pipe.
- Play, pause, next and previous are sent to the sender's own remote-control service (DACP). Only some senders offer it. Apple Music and the iOS Music app do. Spotify and most third-party apps are display-only.
- A paused sender stays on the display. A new sender interrupts the old one (`sessioncontrol` in the generated shairport-sync config).
- Eviction, when another source takes over: the sender is paused if it can be, and the receiver restarts to drop the session.

## Running shairport-sync yourself

Set `manage = false` to use a receiver you started yourself, for example as a systemd unit on a Pi. havenOS then reads the pipes from its state directory and does not start or stop the process. Keep the pipe paths in the unit, the shairport-sync config and the state directory identical.

## Known limits

- Remote control only works with senders that offer it.
- On quit (including Ctrl-C and SIGTERM), `shairport-sync` is stopped with the app. Only `kill -9` can leave it behind and holding the port. See [Troubleshooting](../troubleshooting.md).

Design: [spec 07](../specs/07-music-pipeline.md).
