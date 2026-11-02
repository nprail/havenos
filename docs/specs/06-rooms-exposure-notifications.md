# Spec 06: room screens, Assist-exposure filtering, announcements and notifications

Status: built in this repo, covered by tests (against in-process fake Home Assistant and the demo home), and tried on a real Home Assistant (confirmed by the maintainer, 2026-11-02).

## 1. The rule: only what Home Assistant exposes to voice assistants

The device shows an entity only if it is exposed to **Assist** (HA: Settings, Voice assistants, Expose; the `conversation` flag returned by the `homeassistant/expose_entity/list` WebSocket command). This applies to everything from HA: quick tiles, room screens, the weather panel and the media player, including anything named explicitly in `config.toml`. Also excluded: disabled and hidden entities, config/diagnostic-category entities, and the display's own ESPHome entities.

It **fails closed**: if the exposure list or the registries cannot be read (they need an administrator's access token), nothing from HA is shown and the screens and settings page say why. Exposure has no change event in HA, so the device re-reads it on registry updates and every 5 minutes.

Observed on your HA (read-only inspection): 180 entities are exposed to Assist, spread over 17 areas; the exposed domains are light, climate, fan, cover, lock, switch, script, media_player, sensor, binary_sensor, water_heater and vacuum. **No `weather` entity was exposed at the time**, so the weather panel stays hidden until you expose one (the settings page lists what is hidden and why). Alarm panels are out of scope for this version.

## 2. This display's room

The device finds its own entry in HA's device registry by MAC (HA stores the ESPHome device with a `mac` connection) and uses that device's **area**. Your display is assigned to *Sunroom*. A `room` setting (area id or name; also on the settings page) overrides it. Entities belong to an area directly or through their device.

## 3. Quick tiles

Automatic by default: the room's "major" exposed entities, one of each kind first (light, climate, fan, cover, media player, switch, scene, ...), then more lights, up to six. Locks and sensors are not tiles. A tile tap does the obvious thing; **a lock tile can only lock**, never unlock. Listing custom tiles in the config overrides the automatic set (still filtered by exposure).

## 4. Room screens

Dashboard, **Rooms** button. The Rooms screen lists every area that has something to show (this display's room first, marked HERE), with a summary such as "1 of 2 lights on · 69°". A room shows controllable entities as a uniform grid, sensors last. Controls: light on/off and brightness slider; fan on/off and speed; cover open/stop/close; climate minus/plus on the target (or the low-high range); media prev/play-pause/next; scene and script run; vacuum start/pause/dock; lock/unlock (**unlock needs a second, deliberate tap**). Entities in no area are not shown in v1.

All touches go through one allowlist (`core/actions.py`): each (domain, action) maps to a fixed service with range-checked arguments, and the core re-checks exposure on every call, so a request for an unexposed entity or an unlisted service is refused (an `error` event, nothing sent to HA). Unlocking additionally requires `confirmed=True`.

## 5. Announcements and notifications

- **Announcement:** a full-screen card that wakes the display. Fields: title, message, kind (`info`, `warning`, `critical`), seconds. Info and warning time out (default 20 s, visible countdown); **critical stays until dismissed**. Extras queue ("+N more"). Text is length-limited and unknown kinds fall back to info.
- **Notification:** a quiet message that goes into the notification list and the bell badge without taking over the screen. The list keeps 50, newest first; "Clear all" and per-item remove.
- **Sending:** ESPHome services on this device, `esphome.<name>_announce` (message, title, kind, seconds), `_notify`, `_clear_notifications`, `_dismiss_announcement`; the Notifications sensor shows the count. The core command `announce.show` is the one entry point, so spoken announcements from the voice assistant (spec 05) will use the same screen.
- **Home Assistant's own notifications** (updates, new devices) can be mirrored into the list (`persistent_notifications` setting, off by default). They can only be dismissed in HA.

## 6. Settings page

Room, exposure summary (this display's room, how many entities are exposed, what is hidden and why), custom tiles (optional), announcement length, and the HA-notifications switch. The connection test lists areas and marks entities that are not exposed.

## 7. Open items

- Entities with no area ("Whole home") are not shown anywhere. Decided: that stays as is.
- No exposure-change event exists in HA, so a change can take up to 5 minutes (or a registry edit) to appear.
- HA does let you expose `weather` entities (tested on your instance); a weather panel appears once the entity is exposed.
- Alarm panels are out of scope for this version (see spec 00 section 8).
- Spoken announcements and the notification sound need the voice work (spec 05).
