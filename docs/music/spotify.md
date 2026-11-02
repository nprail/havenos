# Spotify Connect

havenOS can appear as a Spotify Connect device by running [`go-librespot`](https://github.com/devgianlu/go-librespot) as a child process. It reads go-librespot's local API for state and control and takes the audio from a pipe.

> **This only works on some Spotify accounts.** On other accounts Spotify refuses every audio key to librespot-based clients, and nothing plays. If Spotify does not work for you, send Spotify to the display with [AirPlay](airplay.md), or play it through [Music Assistant](sendspin.md).

## The upstream problem

On affected accounts go-librespot logs `failed retrieving aes key with code 1`. It is tracked upstream in go-librespot issues #279 and #317. It happens on Premium accounts, with zeroconf or OAuth login, and also affects Music Assistant's own Spotify provider. It is a Spotify-side refusal, not a havenOS bug.

havenOS detects a burst of these errors, stops, and shows a notice on the display so it does not appear to hang. There is no known workaround.

## Requirements

- A Spotify **Premium** account (and, as above, one that Spotify allows).
- `go-librespot` installed (on a Mac, `brew install go-librespot`; on a Pi, a release binary in `/usr/local/bin`).

## Turn it on

```toml
[music.spotify]
enabled = true
name = "Kitchen display"    # optional; default is "havenOS <hostname>"
```

or set `HAVENOS_SPOTIFY=1`. The first time, open the Spotify app and pick the display from the device list (Connect's zeroconf login).

## Settings

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `false` | |
| `name` | `havenOS <hostname>` | |
| `api_port` | `3678` | go-librespot's local API on 127.0.0.1 |
| `binary` | `go-librespot` on `PATH` | |
| `manage` | `true` | `false` connects to a go-librespot you started yourself (systemd on a Pi) |
| `audio` | `true` | Play on this device |

Environment overrides: `HAVENOS_SPOTIFY`, `HAVENOS_SPOTIFY_NAME`, `HAVENOS_SPOTIFY_PORT`, `HAVENOS_SPOTIFY_BINARY`, `HAVENOS_SPOTIFY_AUDIO`.

## Takeover

When another source takes the speaker, playback stops and the session is dropped.
