# Sendspin

[Sendspin](https://www.music-assistant.io/) is Music Assistant's synchronised-audio protocol. With Sendspin on, the display shows up in Music Assistant as a player, and anything Music Assistant plays to it appears on screen. It runs inside havenOS using `aiosendspin`, so there is nothing else to install. It has been tested with a real Home Assistant and Music Assistant setup.

## Turn it on

```toml
[music.sendspin]
enabled = true
name = "Kitchen display"    # optional; default is "havenOS <hostname>"
```

or set `HAVENOS_SENDSPIN=1`.

This opens a LAN port (8928 by default) and advertises over mDNS. Music Assistant discovers the display and adds it as a player.

## Roles

Sendspin lets a client declare roles:

- **Metadata and controller**: always. The display shows what is playing and can send play, pause, next, previous, seek and volume.
- **Player**: declared when `audio = true` (the default). havenOS plays the audio on this device. Set `audio = false` to make it a display and remote only.

## Pairing

The metadata and controller roles activate after the server pairs with, or trusts, the display. With `allow_unpaired = true` (the default) the display offers guest access so Music Assistant can add it without a manual step. If a pairing code is needed, it is shown on the display as an announcement.

## With the library

The Music Assistant [library](music-assistant.md) plays through this same Sendspin player, so Sendspin must be enabled to use the Library button.

## Settings

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `false` | |
| `name` | `havenOS <hostname>` | |
| `port` | `8928` | |
| `audio` | `true` | Play on this device |
| `allow_unpaired` | `true` | Guest access |

Environment overrides: `HAVENOS_SENDSPIN`, `HAVENOS_SENDSPIN_NAME`, `HAVENOS_SENDSPIN_PORT`, `HAVENOS_SENDSPIN_AUDIO`.
