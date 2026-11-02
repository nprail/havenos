# Connecting to Home Assistant

havenOS talks to Home Assistant in two independent ways:

1. **As a client.** It connects to your Home Assistant over the WebSocket API to show weather, a media player, quick controls and rooms.
2. **As a device.** Optionally, it announces itself so Home Assistant adopts it as an ESPHome device, with entities and services of its own.

You can use either or both.

> **Status.** The ESPHome device has been adopted and used on a real Home Assistant. The client side (rooms, Assist exposure, announcements, notifications) is built, tested against in-process fake servers, and has been tried on a real Home Assistant. Voice is built and tested against fakes and the real ESPHome client, **but has not been run on a microphone, a speaker or a real Assist pipeline** (see [spec 05](specs/05-voice-pipeline.md) section 9). Without `[voice] enabled`, the voice sheet runs a scripted simulation.

## Using Home Assistant as a data source

1. In Home Assistant, open your profile and create a **long-lived access token**.
2. In the [settings page](settings-ui.md), enter the URL (for example `http://homeassistant.local:8123`) and the token, and press **Test connection**.
3. Choose the weather entity and the media player. Optionally pick up to 6 quick-control tiles.

Or in the config file:

```toml
[homeassistant]
url = "http://homeassistant.local:8123"
token_file = "~/.config/havenos/ha_token"
weather = "weather.home"
media_player = "media_player.kitchen"
```

Without a URL and token, the dashboard shows demo data. With them, nothing is faked: missing entities show "Unavailable", a failed call becomes an `error` event, a dropped connection reconnects with backoff, and a bad token stops retrying and shows `auth_failed` in the HUD.

### Which entities show up

Everything from Home Assistant passes one rule: **only entities exposed to Assist are shown, and the filter fails closed.** If an entity does not appear:

- Expose it in Home Assistant, under Settings, Voice assistants, Expose.
- Give it an area. Entities with no area stay hidden by design.
- Wait up to five minutes. Exposure changes are picked up on a timer because Home Assistant sends no event for them.

Weather entities can be exposed to Assist like any other, so expose the one you want to show.

### Rooms

The display finds its own room from Home Assistant's device registry, or from the `room` setting. The quick tiles are that room's major exposed entities. The **Rooms** screen (`r` on a desktop) lists every room and controls lights, climate, fans, covers, media, locks, scenes and vacuums. Unlocking needs a confirmation. Touches go through the allowlist in `core/actions.py`, so the screen cannot call arbitrary services.

Details and the safety rules are in [spec 06](specs/06-rooms-exposure-notifications.md).

### Announcements and notifications

An announcement takes over the screen for `announcement_seconds` (critical ones stay until dismissed). A bell opens the notification list. Set `persistent_notifications = true` to include Home Assistant's own persistent notifications. You trigger both with the services below.

## Letting Home Assistant adopt the display

Turn on the ESPHome device, then restart:

```toml
[esphome]
enabled = true
```

or set `HAVENOS_ESPHOME=1`, or use the settings page.

havenOS announces itself over mDNS (`_esphomelib._tcp`, port 6053). In Home Assistant, go to **Settings, Devices & services**. The display appears as a discovered ESPHome device. Press **Configure**. There is no password or key to enter unless you set an encryption key (below).

### What Home Assistant gets

| Entity | Type | What it does |
|---|---|---|
| Screen | switch | Display off and on (software black-out until real backlight control) |
| Brightness | number, 10 to 100 % | UI dimming |
| Mode | select | `ambient` or `dashboard` |
| Next photo, Previous photo | button | Move the playlist |
| Current photo | text sensor | File name or Immich asset |
| Active timers | sensor | Timer count |
| Touch | event | `tap`, `swipe_left`, `swipe_right`, `swipe_down`, for automations |
| Seconds per photo, Crossfade, Glass blur | number, number, switch | Display preferences, saved to `config.toml` |
| Photo source, Home Assistant link, Memory, Event loop lag, Cached photos | diagnostic sensors | Health |
| Notifications | sensor | Count in the notification list |
| Room | text sensor, diagnostic | The area this display is in |
| Media player | media player | Play, pause, stop, volume and mute for the active music source, with title, artist, album and source sensors and next and previous buttons |

Home Assistant commands to the media player never take over the speaker.

### Services

Call these as `esphome.<device_name>_<service>` in automations and scripts.

| Service | Arguments |
|---|---|
| `start_timer` | `seconds`, `label` |
| `dismiss_timer` | none |
| `announce` | `message`, `title`, `kind`, `seconds` |
| `notify` | `message`, `title`, `kind` |
| `clear_notifications` | none |
| `dismiss_announcement` | none |

For example, an automation that shows a message on the display:

```yaml
action: esphome.havenos_kitchen_announce
data:
  title: Doorbell
  message: Someone is at the front door
  kind: info
  seconds: 15
```

### Identity and persistence

Home Assistant keys the device and every entity on its MAC address. havenOS generates a locally-administered ID once and stores it in `~/.config/havenos/device_mac`, because the operating system's value is not reliable. Entity keys are hashes of object ids, so restarting does not create duplicates. Keep `device_mac` when you move or reinstall.

Seconds per photo, crossfade, brightness and blur changed from Home Assistant are written back to `config.toml` (debounced by one second and flushed at shutdown, only when the value actually changed). Screen on or off, mode and the current photo are not saved.

### Security

By default the ESPHome link is **plain text with no password**. Anyone on the LAN can read state and drive the screen. That is why it is opt-in. Use it on a trusted home network.

For Noise encryption, make a key and put it in the config; Home Assistant asks for the same key when you add the device:

```bash
python -m havenos.core.esphome.noise
```

```toml
[esphome]
enabled = true
key = "<the printed key>"      # or key_file = "~/.config/havenos/esphome_key"
```

Encryption is **required for voice**, because the link then carries microphone audio. Verified against the real `aioesphomeapi` client (the library Home Assistant uses), not yet against Home Assistant itself.

## When it does not appear

See [Troubleshooting](troubleshooting.md). The usual causes are mDNS blocked between network segments, a firewall on port 6053, or two devices with the same name.

The design, the voice plan and an acceptance checklist are in [spec 04](specs/04-esphome-integration.md).
