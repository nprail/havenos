# Spec 04: exposing havenOS to Home Assistant (ESPHome native API), built to carry voice

Status: server + entities implemented in this repo and verified with aioesphomeapi's real client (the library HA uses) and over mDNS from a separate process, and **adopted and used on a real Home Assistant**. Voice is built on top of it (spec 05 section 9 says how far it was checked), and Noise encryption is available.

Pattern source: OHF-Voice/linux-voice-assistant (Apache-2.0). Its lesson: a plain-text ESPHome server written on aioesphomeapi's protobuf messages, plus an `_esphomelib._tcp` mDNS announcement, is enough for HA to adopt a Linux program as a device, voice satellite included. We follow that shape with our own code.

## 1. What HA sees today (all opt-in: `[esphome] enabled = true`)

| Entity | Type | Category | Drives |
|---|---|---|---|
| Screen | switch | | display off/on (the backlight, or a software black-out without one) |
| Brightness | number 10-100 % | | the backlight level, the ceiling for automatic dimming (saved) |
| Backlight level | sensor % | diagnostic | what is on the panel (brightness x screen x auto scale) |
| Mode | select ambient/dashboard | | what the screen shows |
| Next photo / Previous photo | button | | photo playlist |
| Current photo | text sensor | | file name or Immich asset |
| Active timers | sensor | | timer count |
| Touch | event: tap, swipe_left, swipe_right, swipe_down | | automations ("tap the frame, turn on the lamp") |
| Seconds per photo, Crossfade, Glass blur | number, number, switch | config | display preferences; **saved to config.toml automatically** (debounced), so they survive a restart |
| Photo source, Home Assistant link, Memory, Event loop lag, Cached photos | sensors | diagnostic | health |
| `start_timer(seconds, label)`, `dismiss_timer()`, `announce(message, title, kind, seconds)`, `notify(message, title, kind)`, `clear_notifications()`, `dismiss_announcement()` | services | | `esphome.<name>_...` in automations (see spec 06) |
| Notifications | sensor | | count in the notification list |
| Room | text sensor | diagnostic | the area this display is in |

## 2. Design

```
 core/esphome/
   framing.py   0x00 | varuint len | varuint type | protobuf   (incremental decoder, size-capped)
   server.py    asyncio TCP server; Connection per HA client; standard handshake; add_handler(MsgClass, fn) = the seam
   entities.py  declarative Switch/Number/Select/Button/Sensor/TextSensor/BinarySensor/Event/Service; keys = fnv1(object_id)
   device.py    ESPHomeDevice: builds entities over Core.state, pushes state on bus events, routes commands to Core.handle
   mdns.py      zeroconf announcement
```

- **Same loop, no threads.** Runs on the qasync loop beside the HA and Immich clients. Commands from HA become the same `Core.handle(...)` calls the touch UI makes, so there is exactly one code path for every action.
- **State push:** every `state.patch` re-checks all entities; only changed ones are sent. Noisy diagnostics are throttled (15 s).
- **Identity:** HA keys the device and every entity on the MAC. `uuid.getnode()` is not reliable (it returned a constant here), so a locally-administered id is generated once and stored in `~/.config/havenos/device_mac`. Entity keys are hashes of object ids, so they survive restarts and reordering.
- **Robustness:** garbage or encrypted-client bytes close only that connection; a failing service call is logged, not fatal; multiple HA clients all get updates.
- **Security:** plain text, no password, unless `[esphome] key` is set, which turns on Noise encryption (`core/esphome/noise.py`, verified with the real aioesphomeapi client). Without a key anyone on the LAN can read state and drive the screen, which is why it is opt-in; voice refuses to start without a key.

## 3. Voice plan (now built: see 05 section 9)

> The detailed, VPE-parity voice plan is now `05-voice-pipeline.md`. The summary below predates it; where they differ, 05 wins.

The ESPHome link is already the voice transport, so voice is additive, not a second integration.

1. **Advertise it.** `DeviceInfoResponse.voice_assistant_feature_flags` is 0 unless voice is on; then it is VOICE_ASSISTANT | SPEAKER | API_AUDIO | TIMERS | ANNOUNCE | START_CONVERSATION (63). HA then offers an Assist pipeline selector for the device.
2. **A `VoiceSatellite` object registers handlers** with `server.add_handler(...)` for `VoiceAssistantConfigurationRequest`, `VoiceAssistantEventResponse`, `VoiceAssistantAudio`, `VoiceAssistantAnnounceRequest`, `VoiceAssistantTimerEventResponse` (a test already proves a handler registered this way receives frames).
3. **Flow:** wake word or tap on the mic button → send `VoiceAssistantRequest(start=True)` → stream mic audio as `VoiceAssistantAudio` (16 kHz, 16-bit mono PCM) → HA replies with `VoiceAssistantEventResponse` events.
4. **UI mapping (the voice sheet already exists):** RUN_START to *listening*; STT_END to the transcript; INTENT_PROGRESS/END to *processing*; TTS_START to the reply text; TTS_END carries a URL to download and play; RUN_END returns to idle; ERROR shows an error. This replaces `core/voice.py`'s simulation with the same `voice`, `transcript`, `response` state, so no QML changes.
5. **Announcements:** `VoiceAssistantAnnounceRequest` (a media URL, optional text and pre-announce sound) plays through the speaker, then `VoiceAssistantAnnounceFinished`.
6. **Timers:** `VoiceAssistantTimerEventResponse` (STARTED/UPDATED/CANCELLED/FINISHED) maps onto `TimerBook`, so "set a timer for 10 minutes" shows on the dashboard and fires the existing ring takeover.
7. **Audio I/O:** designed in `05-voice-pipeline.md`: a separate audio worker process with our own two-bus mixer (not mpv), on-device wake word (microWakeWord, VPE models) with the model list returned from `VoiceAssistantConfigurationRequest`, and a USB mic array with a built-in DSP (reSpeaker XVF3800 or Lite) doing echo cancellation, with software AEC as the fallback. Whether the hardware AEC works needs a Pi to evaluate.
8. **Media player entity** (HA can play music or TTS to the display) shares the same output; add after the satellite.

Decided in `05-voice-pipeline.md`: wake word on-device; our own `VoiceSatellite` that follows the protocol (no dependency on the voice project's packages); mic hardware is the reSpeaker XVF3800 or Lite; AEC is the chip's own, with software AEC as the fallback. Also decided: the chips' own AEC and the XVF3800's 48 kHz USB firmware are assumed to work, the Lite plays everything at 16 kHz, Noise encryption is used, and the speaker is not a concern. Bring-up (V0b) only confirms the assumptions.

## 4. Acceptance checklist on a real HA (user-run)

1. Enable the device (settings page, or `HAVENOS_ESPHOME=1`), restart.
2. HA: Settings, Devices & services: the device is *Discovered* under ESPHome; Configure; no password or key.
3. Toggle Screen, move Brightness, press Next photo; check the Touch event fires from the screen; call `esphome.<name>_start_timer`.
4. Restart havenOS: the device comes back as the same device with the same entities (no duplicates).
