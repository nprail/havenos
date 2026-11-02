# Deploying the music daemons on the Pi

Run on one Raspberry Pi 4 (see docs/raspberry-pi.md): the units start, AirPlay 2 builds, advertises and plays from a real sender, and Sendspin was found by a real
Music Assistant. go-librespot (Spotify) is not installed by the scripts. `install.sh` installs the whole app; the rest of this page is the music daemons.

| File | What it is |
|---|---|
| `install-music.sh` | builds nqptp + shairport-sync with AirPlay 2, installs go-librespot's config, installs the units |
| `nqptp.service`, `shairport-sync.service`, `shairport-sync.conf` | AirPlay 2 receiver writing PCM and metadata to pipes in `/var/lib/havenos/airplay/` |
| `go-librespot.service`, `go-librespot/config.yml` | Spotify Connect writing PCM to `/var/lib/havenos/spotify/audio.pipe`, API on 127.0.0.1:3678 |
| `havenos.service` | the display app; reads the pipes (`manage = false`) and talks to the daemons |

`/var/lib/havenos/config.toml` for this layout:

```toml
[music.airplay]
enabled = true
manage = false          # shairport-sync runs as its own unit

[music.spotify]
enabled = true
manage = false

[music.sendspin]
enabled = true          # in-process; nothing to install

[music.assistant]
url = "http://homeassistant.local:8095"
token_file = "/var/lib/havenos/ma_token"
```

Keep the pipe paths in the unit files, the shairport-sync config and the go-librespot config identical to the state
directory the app uses (`dirname($HAVENOS_CONFIG)`). The AirPlay and Spotify adapters read their FIFOs from there.

What is still missing for the Pi: the audio worker and mixer of docs/specs/05 (the app currently plays through a sound device
directly, with ducking but no echo reference and no multi-room clock sync), and the Pi gates (memory, switching soak,
sync, takeover latency).
