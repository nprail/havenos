# havenOS — Feature Specification

**A fully local smart display application for Raspberry Pi, connecting to Home Assistant for data and control.**

Version: 0.1 (Draft)
Status: Pre-development

---

## 1. Overview

havenOS is a static web application served by a lightweight local Node.js server, displayed fullscreen in Chromium kiosk mode on a Raspberry Pi 4 with a touchscreen. It provides a Nest Hub-like ambient display experience — completely without Google, Amazon, or any cloud dependency. It connects to a local Home Assistant instance via the WebSocket API for data and control. It integrates with a local linux-voice-assistant pipeline for fully offline voice commands. It has no Lovelace dependency; the UI is fully custom.

The server process is minimal — it serves the static app, bridges filesystem access (photos, config), and relays wake word events from linux-voice-assistant to the browser via a local WebSocket. The browser does the rest.

### Design Philosophy

- **Touch is the primary input.** havenOS is designed as a touchscreen appliance first. Every interactive surface is sized, spaced, and animated for finger use. Mouse and keyboard are incidental — nothing in the UI should require them. Hover states do not exist.
- **Ambient-first.** The device should be glanceable from across a room. Large type, high contrast, no information overload.
- **Local-only.** No cloud calls, ever. Weather from a local HA integration (Met.no or Open-Meteo). Photos from a local Immich instance. Music from Music Assistant (local library, Navidrome, or any configured provider — all served locally).
- **HA as a data bus, not the UI.** HA entities drive the data; havenOS owns the rendering entirely — with one deliberate exception: the HA Dashboard page, which embeds a Lovelace view for full entity control.
- **Progressive disclosure.** The ambient (idle) screen is calm. Interaction surfaces appear on touch or voice trigger, then recede.

---

## 2. Hardware Target

| Component  | Spec                                                                |
| ---------- | ------------------------------------------------------------------- |
| SBC        | Raspberry Pi 4 (4GB+)                                               |
| Display    | 7"–10" HDMI touchscreen (e.g., Waveshare 10.1" 1280×800 capacitive) |
| Microphone | ReSpeaker 2-Mic HAT or ReSpeaker 4-Mic Array (USB)                  |
| Speaker    | USB DAC + powered bookshelf speaker, or 3.5mm to amp                |
| Storage    | 32GB+ microSD or USB SSD                                            |
| OS         | Raspberry Pi OS Lite (64-bit)                                       |

The app is designed for 1280×800 landscape. It should degrade gracefully to 1024×600.

---

## 3. Screen States

The application has five primary states with defined transition rules.

```
AMBIENT (idle)
    │
    ├── touch anywhere → ACTIVE
    ├── wake word detected → LISTENING
    └── [automatic] → AMBIENT (photo cycle, clock, weather)

ACTIVE (dashboard)
    │
    ├── 30s no interaction → AMBIENT
    ├── wake word → LISTENING
    ├── tap module → MODULE DETAIL
    └── tap HA Dashboard button → HA DASHBOARD

LISTENING (voice)
    │
    ├── speech detected → PROCESSING → response → ACTIVE
    ├── silence timeout (3s) → ACTIVE
    └── tap dismiss → ACTIVE

MODULE DETAIL (full-screen overlay)
    │
    ├── back button / swipe down → ACTIVE
    └── 60s no interaction → AMBIENT

HA DASHBOARD (embedded Lovelace)
    │
    ├── back button / swipe down → ACTIVE
    └── 60s no interaction → AMBIENT
```

### 3.1 AMBIENT State

The device's resting state. No interaction required to be useful.

**Layout (full 1280×800):**

```
┌────────────────────────────────────────────────────────────────┐
│  [Photo fills entire background — slideshow]                    │
│                                                                 │
│  ┌─────────────────────────────┐                               │
│  │  HH:MM          [AM/PM]     │  ← Large clock, bottom-left   │
│  │  Day, Month DD              │                               │
│  └─────────────────────────────┘                               │
│                                          ┌──────────────────┐  │
│                                          │  72°F  ⛅  Today  │  │
│                                          │  H:78 L:61       │  │
│                                          └──────────────────┘  │
└────────────────────────────────────────────────────────────────┘
```

**Elements:**

- **Photo background:** Full-bleed photo cycling on a configurable interval (default 60s). Source is a local directory path configured in settings. Images are preloaded and crossfade (500ms ease). Portrait photos get a blurred copy as the background with the original centered and letterboxed.
- **Clock:** Bottom-left, large. Primary font: time in ~120px. Date in ~28px below. Both use a semi-transparent dark scrim behind the text block (no solid card — the scrim hugs the text bounds with 16px padding and rounded corners). Text is always white; the scrim opacity adjusts based on photo brightness (computed via canvas pixel sampling).
- **Weather widget:** Bottom-right. Current temp, condition icon (SVG, not emoji), today's high/low. Same scrim treatment. Data comes from a HA `weather.*` entity.
- **Active timer indicator:** If any HA timer is active, a small pill appears top-center with remaining time (e.g., `⏱ 4:32`). Tapping it opens the Timers module.
- **Music now-playing strip:** If media is actively playing, a slim strip appears along the bottom edge (above any other elements) showing: cover art thumbnail, track name, artist. Not shown during idle.

**Transition to ACTIVE:** Any touch anywhere on screen triggers a smooth upward slide of the dashboard panel (300ms ease-out). The photo remains visible behind the dashboard.

---

### 3.2 ACTIVE State (Dashboard)

The main interactive surface. Slides up from the bottom of AMBIENT.

**Layout (1280×800):**

```
┌────────────────────────────────────────────────────────────────┐
│  [Photo — dimmed to 40% brightness behind panels]              │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ HH:MM     Day, Month DD     72°F ⛅                       │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │   WEATHER    │  │    MUSIC     │  │       TIMERS         │  │
│  │  [detail]    │  │  [controls]  │  │   [active/new]       │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              QUICK CONTROLS ROW                          │  │
│  │  [lights]  [climate]  [security]  [scenes]  [settings]   │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
```

**Panel system:** Panels are frosted glass cards (backdrop-filter: blur + semi-transparent background). They use the configured color theme (see §7.1).

**Compact header bar:** Time, date, temp, condition. Always visible at top of ACTIVE state. Tap weather section → Weather module detail.

**Main card row (3 equal columns):**

1. **Weather card** (see §4.1)
2. **Music card** (see §4.2)
3. **Timers card** (see §4.3)

**Quick controls row:** Horizontally scrollable row of quick-action buttons. Each button is 120×80px with an icon + label. Default buttons: Lights, Climate, Security Cameras, Scenes, **HA Dashboard**, Settings. Configurable. Tap → MODULE DETAIL (or HA DASHBOARD for the dashboard button).

---

### 3.3 LISTENING State

Triggered by wake word ("Ok Nabu" or custom) or microphone button tap.

**Visual treatment:**

- The current state (AMBIENT or ACTIVE) dims to 60% opacity.
- A bottom sheet rises from the bottom edge (~180px tall).
- The bottom sheet contains:
  - An animated waveform visualizer (real microphone amplitude, not fake) centered in the sheet.
  - State label: "Listening…", "Thinking…", "Speaking…"
  - A text display of the recognized speech (populated in real time as linux-voice-assistant streams partial results).
  - The assistant's response text (appears after processing).
  - A tap-to-dismiss × button top-right of the sheet.

**Waveform:** SVG bars updated at 60fps from microphone amplitude data. 40 bars, centered, symmetric around a baseline. Color matches the theme accent.

**States within LISTENING:**

- `listening` — waveform animates to mic input
- `processing` — waveform becomes a slow pulsing animation (processing indicator)
- `responding` — waveform animates to TTS audio output; text of response shown
- `done` — sheet auto-dismisses after 2s, or user taps ×

---

### 3.4 MODULE DETAIL State

Full-screen overlay for any module. Slides up over ACTIVE state. Has a back chevron (top-left) and swipe-down gesture to dismiss.

Modules: Weather, Music, Timers, Lights, Climate, Cameras, Scenes.

---

### 3.5 HA DASHBOARD State

A full-screen embedded view of the Home Assistant Lovelace frontend. Slides up over ACTIVE state in the same manner as MODULE DETAIL. Has a persistent back chevron (top-left, always rendered above the iframe) and swipe-down gesture to dismiss.

**Purpose:** The custom havenOS modules cover the most common touch interactions with a streamlined UI. The HA Dashboard page exists as an escape hatch for full entity control — any device, automation, or view that isn't surfaced in the havenOS modules is reachable here.

**Implementation:** An `<iframe>` pointing at the configured HA base URL (e.g., `http://homeassistant.local:8123`). The HA frontend loads inside the iframe; the user is already authenticated because the long-lived token is stored in havenOS config, and the iframe loads the HA frontend URL with no additional auth step required (HA session cookies are set on the domain). If HA requires login, the iframe shows the HA login page — the user logs in once and the session persists.

**Layout:**

```
┌─────────────────────────────────────────────────────────────────┐
│  ‹  Home Assistant                              [back chevron]  │  ← havenOS chrome (48px tall)
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   [Home Assistant Lovelace frontend — full iframe]              │
│                                                                 │
│   Scrollable. Touch events pass through to HA normally.         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Touch considerations for the iframe:**

- The iframe receives all touch events natively. Lovelace is already touch-capable.
- The back chevron and the top chrome bar are rendered by havenOS _over_ the iframe using `position: fixed` within the havenOS overlay layer (not inside the iframe). This ensures the dismiss control is always accessible regardless of what Lovelace renders.
- A 48px tall top chrome bar is reserved and the iframe is inset by that amount (`top: 48px`, `height: calc(100% - 48px)`). This prevents Lovelace's own header from being obscured.
- Swipe-down to dismiss: a gesture recognizer on the havenOS overlay layer (not the iframe) detects a downward swipe starting in the top 80px of the screen and dismisses. Swipes further down in the iframe are passed through to Lovelace.

**Lovelace view selection:** Configurable. Options:

- Default view (HA home dashboard)
- A specific named view path (e.g., `/lovelace/touch`) — allows the user to create a touch-optimized Lovelace view in HA and point havenOS at it
- A specific HA panel (e.g., `/config/dashboard`)

**Timeout behavior:** 60s idle (no touch events within the iframe or the havenOS chrome) → return to AMBIENT. A 10s countdown warning is shown in the havenOS chrome bar before dismissing: "Returning to home in 10s · Stay".

---

## 4. Modules

### 4.1 Weather Module

**Data source:** HA `weather.*` entity (Met.no, Open-Meteo, or any HA weather integration). Attributes: `temperature`, `humidity`, `wind_speed`, `wind_bearing`, `forecast` (hourly and daily arrays).

**Card (ACTIVE view):**

- Current temperature (large, ~56px)
- Condition label + SVG icon
- High / Low for today
- A 4-hour strip: hourly forecast, icon + temp per column

**Detail view (MODULE DETAIL):**

- Full-width today summary: temperature, feels-like, humidity, wind speed/direction, UV index, sunrise/sunset
- 7-day daily forecast: day name, icon, high, low, precipitation probability (rendered as a subtle bar)
- Hourly forecast for the next 24 hours: horizontal scrollable strip, icon + temp + precip probability

**Weather icons:** Custom SVG icon set (not emoji, not external font). Icons are drawn inline for: clear-day, clear-night, partly-cloudy-day, partly-cloudy-night, cloudy, rainy, snowy, sleety, windy, foggy, thunderstorm. Icons animate (sun rotates slowly, rain drops animate, lightning flashes).

**Voice commands (examples):**

- "What's the weather like?" → reads current conditions + today's forecast
- "Will it rain tomorrow?" → reads tomorrow's precipitation probability
- "What's the forecast this week?" → reads daily high/low for 7 days

---

### 4.2 Music Module

The music module has two distinct functions: **playback control and now-playing display** (via Sendspin), and **touchscreen library browsing and queue management** (via the Music Assistant REST API). No havenOS-server music endpoints. All music flows through Music Assistant.

**How it works:**

```
Browse / play intent
        │  MA REST API (http://MA_SERVER:8095)
        ▼
Music Assistant server  ──→  streams via Sendspin  ──→  sendspin-cli daemon (audio out)
        │                                                         │
        │  Sendspin WebSocket (metadata/artwork/controller roles) │
        ▼                                                         ▼
Browser (now-playing display, playback controls)         Speaker
```

The browser connects directly to the Sendspin server for the `metadata`, `artwork`, and `controller` roles — it receives real-time now-playing updates and sends play/pause/seek/volume/next/prev commands back. For browsing, it calls the MA REST API directly to search the library, browse artists/albums/playlists, and queue tracks to the havenOS Sendspin player. havenOS-server is not in the music hot path at all.

**Library browsing (MA REST API at `http://MA_SERVER:8095`):**

- Search: `GET /search?query=...&media_type=track|album|artist|playlist`
- Browse library: `GET /library/tracks`, `/library/albums`, `/library/artists`, `/library/playlists`
- Browse artist: `GET /artists/{id}/albums`
- Browse album: `GET /albums/{id}/tracks`
- Queue/play: `POST /player_queues/{player_id}/play_media` — body: `{ uri, enqueue_mode }`
- Player control: `POST /player_queues/{player_id}/play`, `/pause`, `/next`, `/previous`, `/seek`, `/volume`

The `player_id` for havenOS is the Sendspin client ID configured in `sendspin.service`. MA discovers the havenOS Sendspin player automatically via mDNS.

**Playback state (Sendspin `metadata` + `artwork` roles):**

The browser maintains a WebSocket connection to the Sendspin server and subscribes to `metadata` and `artwork` role updates. These push track title, artist, album, and artwork in real time. This feeds the Zustand `cast` slice directly — no polling, no havenOS-server intermediary.

**What havenOS-server reports to HA** (`media_player.havenos_display`):
havenOS-server subscribes to Sendspin metadata events (via a lightweight Sendspin client connection on `localhost`) and syncs the HA `media_player.havenos_display` entity — state, title, artist, artwork URL. HA can also send commands to this entity (from voice or automations), which havenOS-server translates to MA REST API calls.

**Card (ACTIVE view):**

- Album art (80×80px), track name, artist name
- Play/pause button (48px touch target), previous / next track buttons
- State read from Zustand `cast` slice (Sendspin metadata role)

**Detail view (MODULE DETAIL):**

- Full-width album art
- Track name (large), artist, album
- Seekable progress bar (tap/drag → Sendspin controller `seek`)
- Playback controls: previous, play/pause, next (all 64px touch targets)
- Volume slider (finger-draggable → Sendspin controller `volume`)
- Shuffle / repeat toggles
- **Browse button** — opens the library browser (see below)

**Library browser (within MODULE DETAIL):**

- Home screen: Recents, Favorites, Playlists, Artists, Albums, Tracks
- All data fetched from MA REST API with optimistic loading and a local LRU cache
- Tap an album → track list → tap track → queues and plays via MA REST API
- Search bar at top: live search across all media types
- Artwork loaded directly from MA (MA serves album art at `/library/albums/{id}/thumb`)

**Voice commands (HA Assist → `media_player.havenos_display` → havenOS-server → MA REST API):**

- "Play jazz on the display" → MA REST search → queue to havenOS player
- "Pause the music", "Next song", "Set volume to 40 percent", "Shuffle my music"

**Now-playing ambient integration:** AMBIENT state shows a bottom strip with album art + title + artist when a Sendspin stream is active. Reads from the Zustand `cast` slice.

---

Timers are managed as HA `timer.*` entities. havenOS can create, start, pause, cancel, and display timers. The app also supports multiple simultaneous timers with named labels.

**Card (ACTIVE view):**

- If no active timers: "No active timers" + a large + button
- If timers active: list of up to 3 timers (each showing label, remaining time in MM:SS or HH:MM:SS, a circular progress ring, and a × cancel button)
- A "+ New Timer" button always visible at bottom of card

**Detail view (MODULE DETAIL):**

- All active timers in a scrollable list (each with ring + label + remaining time + pause/resume + cancel)
- A timer creation interface:
  - Duration input: large numpad grid (0–9 + : + delete) — the user taps digits like a physical timer (e.g., "1", "0", "0" → 1:00:00... "1", "0" → 10:00)
  - Label input: text field (on-screen keyboard via OS, or voice)
  - Preset buttons: 5 min, 10 min, 15 min, 20 min, 30 min, 1 hour

**Timer completion:**

- A chime sound (configurable, local audio file) plays on the Pi's speaker.
- A full-screen notification overlays any current state: timer label, "Timer done!", a dismiss button, and a "+1 min" snooze button.
- The notification auto-dismisses after 30s.

**Voice commands:**

- "Set a timer for 10 minutes"
- "Set a pasta timer for 12 minutes"
- "How much time is left on my timer?"
- "How much time is left on the pasta timer?" (named lookup)
- "Cancel my timer" / "Cancel the pasta timer"
- "Add 5 minutes to my timer"

**HA integration note:** The voice pipeline runs via linux-voice-assistant → HA Assist. HA Assist handles the intent parsing for timer commands and calls `timer.start`, `timer.cancel`, etc. havenOS listens to HA state changes for `timer.*` entities to update its UI in real time.

---

### 4.4 Lights Module

**Data source:** HA `light.*` entities. Configurable list of light groups/individual lights to expose.

**Quick control (ACTIVE quick row):** Tap "Lights" → full MODULE DETAIL.

**Detail view:**

- Room tabs at top (configurable, matches HA areas)
- Per-room: a list of lights/groups with:
  - Toggle switch (large, 56px touch target)
  - Brightness slider (if the light supports it)
  - Color temperature slider (if the light supports it, shown as a warm-to-cool gradient bar)
  - Color picker (if light supports color — a simple hue ring, no complex picker)
- A room-level "all on / all off" toggle at the top of each room section

**Voice commands:**

- "Turn on the kitchen lights"
- "Dim the living room to 30 percent"
- "Turn off all the lights"
- "Set the bedroom lights to warm white"

---

### 4.5 Climate Module

**Data source:** HA `climate.*` entities.

**Quick control (ACTIVE quick row):** Shows current temperature setpoint + mode icon. Tap → MODULE DETAIL.

**Detail view:**

- Large current temperature readout (from linked `sensor.*` entity)
- Target temperature dial (large, circular, draggable — similar to a Nest UI treatment but rendered in havenOS's design language)
- Mode buttons: Heat / Cool / Auto / Off (row of 4 pills)
- Fan mode selector (if supported)
- Current humidity (from linked sensor)

**Voice commands:**

- "Set the thermostat to 70 degrees"
- "Turn on the heat"
- "What's the temperature inside?"

---

### 4.6 Cameras Module (Optional)

**Data source:** HA `camera.*` entities.

**Detail view:**

- Grid of camera thumbnails (refreshed every 10s via HA camera proxy endpoint)
- Tap any thumbnail → full-screen live view (MJPEG stream from HA)

No voice commands for cameras (privacy).

---

### 4.7 Scenes Module

**Data source:** HA `scene.*` entities and `script.*` entities marked as visible.

**Detail view:** Grid of scene buttons (icon + label). Each button is 160×100px with a configurable icon and label. Tap → calls `scene.turn_on` or `script.turn_on`.

**Voice commands:**

- "Activate movie mode"
- "Run the good morning scene"

---

### 4.8 Broadcast

Broadcast allows any local process or HA automation to push a spoken announcement and a visual notification to the havenOS display simultaneously. This is the equivalent of the Nest Hub's "broadcast" feature — a doorbell rings, a timer fires on another device, someone casts a message — and the display speaks it and shows it.

**Inbound paths:**

**1. Via HA (recommended for automations):**
havenOS registers a `notify.havenos_display` notify service with HA via the `media_player.havenos_display` entity's announcement capability. Any HA automation or script can call:

```yaml
action: notify.havenos_display
data:
  message: 'Front door opened'
  title: 'Security' # optional
  data:
    icon: 'door' # optional — one of havenOS's icon set names
```

havenOS-server receives this via its HA WebSocket connection (the same connection used for music sync) and dispatches it internally.

**2. Via direct HTTP (for local scripts and other processes):**

```
POST http://localhost:3000/api/broadcast
Content-Type: application/json

{
  "message": "Front door opened",
  "title": "Security",       // optional
  "icon": "door",            // optional
  "tts": true                // optional — default true
}
```

This path works entirely without HA. Any process on the Pi or local network can trigger a broadcast.

**What happens on broadcast:**

1. havenOS-server receives the broadcast (via either path)
2. If `tts: true` (default), havenOS-server calls Piper TTS via the HA pipeline to synthesize the message, then plays the audio on the Pi's speaker via linux-voice-assistant's announcement capability (the ESPHome protocol supports `announce` natively)
3. havenOS-server pushes a broadcast event to the browser over `/events`
4. The browser shows a **broadcast overlay** on whatever screen is currently displayed (AMBIENT or ACTIVE) — a bottom sheet slides up showing the title, message text, and optional icon. The overlay auto-dismisses after 8 seconds or on tap
5. If the display is off (quiet hours), it wakes briefly to show the overlay, then returns to off after dismissal

**Broadcast overlay UI:**

- Slides up from the bottom (same motion as the LISTENING sheet)
- Height: ~140px
- Left: large icon (48×48px) from havenOS's SVG icon set, or a default megaphone icon
- Center: title (16px, medium) and message (20px, regular), truncated at 2 lines each
- Right: a tap-to-dismiss × button (48px touch target)
- Background: frosted glass, same treatment as module cards
- Auto-dismiss: 8s countdown shown as a thin progress bar along the bottom edge of the sheet

**Audio:** TTS audio plays through linux-voice-assistant's announce channel, which handles ducking (lowers music volume during announcement, restores after). If `tts: false`, only the visual overlay is shown.

**Broadcast queue:** If a second broadcast arrives while one is already displayed, it is queued and shown immediately after the current one dismisses. Queue depth: 5 maximum. Older messages are dropped if the queue is full.

---

### 4.9 Cast Sources — AirPlay and Sendspin

havenOS's speaker can receive audio cast from phones, computers, and other devices via two open protocols. Both pipe audio directly to the system output via their own daemons. havenOS-server monitors both for active stream state and updates the `media_player.havenos_display` entity and `sensor.havenos_active_source` accordingly.

---

#### AirPlay (shairport-sync)

**`shairport-sync`** is an open-source AirPlay and AirPlay 2 receiver for Linux. Once running, the Pi appears as a named AirPlay speaker in iOS Control Center, macOS menu bar, and any AirPlay-capable app (Apple Music, Spotify, Podcasts, etc.).

**Service:** `shairport-sync.service` — a fourth systemd service. Outputs directly to ALSA/PipeWire, independent of havenOS-server.

**AirPlay 2 requirements:**

- Build from source with `--with-airplay-2` flag
- Companion daemon `nqptp` must have exclusive access to ports 319 and 320 for timing synchronisation
- FFmpeg with AAC decoder required for AirPlay 2 format support

**Metadata integration:** shairport-sync can write track metadata (title, artist, album, artwork) to a named pipe when compiled with `--with-metadata`. havenOS-server watches this pipe and uses it to:

- Update the Zustand `cast` slice with now-playing info
- Show the now-playing strip in AMBIENT state
- Sync `media_player.havenos_display` state to HA

**Source arbitration:** When an AirPlay session starts while Sendspin is active, havenOS-server applies the priority rules from §4.9 — the most recently started cast source wins.

**Display name:** Configurable in settings (defaults to the device name set at OS level). Shown in AirPlay device pickers.

---

#### Sendspin

**Sendspin** is an open protocol for synchronized multi-room audio, developed within the Open Home Foundation ecosystem. It is the emerging standard for synchronized playback across HA-connected speakers and is implemented by Music Assistant as its primary streaming protocol.

**`sendspin-cli`** running in daemon mode is the Linux receiver. It auto-discovers Sendspin servers on the local network via mDNS and appears as a named player in Music Assistant.

**Service:** `sendspin.service` — another systemd service. Installs via `pip install sendspin` + the provided systemd installer script.

**havenOS's role in Sendspin is richer than just audio.** The Sendspin protocol defines multiple client roles beyond `player`. havenOS can register with the Sendspin server as all of the following simultaneously:

| Role            | What havenOS does                                                                                                                  |
| --------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `player@v1`     | Receives and plays synchronized audio via `sendspin-cli` daemon                                                                    |
| `metadata@v1`   | Displays track title, artist, album on the havenOS screen                                                                          |
| `artwork@v1`    | Displays album art on the havenOS screen                                                                                           |
| `controller@v1` | The havenOS music module touch controls (play/pause, seek, volume, next/prev) send Sendspin controller messages back to the server |

The `metadata`, `artwork`, and `controller` roles are implemented directly in the browser via a WebSocket connection to the Sendspin server — havenOS-server proxies the connection through `/api/sendspin-proxy` to avoid CORS issues. This means the havenOS display becomes a full Sendspin participant: it plays the audio, shows the album art, shows the metadata, and provides touch controls — all synchronized with every other Sendspin player in the home.

**Configuration:** Sendspin server URL is auto-discovered via mDNS. No manual configuration needed if Music Assistant is on the same network. The device name (shown in Music Assistant) is configurable in havenOS settings.

**AirPlay vs Sendspin:** These serve different sources — AirPlay is for casting directly from a phone or app; Sendspin is for Music Assistant's library and synchronized multi-room playback. Both use the Pi's speaker.

---

**Active source arbitration:** Only one audio source plays at a time. Priority when multiple sources are active simultaneously:

1. Broadcast / TTS announce (always interrupts everything, resumes after)
2. Active voice assistant session (LISTENING state)
3. Most recently started cast session (AirPlay or Sendspin)

havenOS-server manages this through a simple active-source state machine. Paused sources are resumed in reverse priority order when the higher-priority source ends.

---

linux-voice-assistant uses the ESPHome protocol (via `aioesphomeapi`) to register directly with Home Assistant as a voice satellite device — the same protocol used by the HA Voice Preview Edition hardware. This gives it access to newer HA voice features unavailable to the old Wyoming-based satellite, including native timer support, stop wake word, start/continue conversation, and media player integration.

### 5.1 Architecture

```
ReSpeaker HAT / USB mic
        │
        ▼
linux-voice-assistant (running on the Pi)
        │  ESPHome protocol (aioesphomeapi)
        ▼
Home Assistant Assist (on HA server)
   ├── Whisper / Speech-to-Phrase (STT — local add-on)
   ├── Intent Parser (HA built-in)
   └── Piper (TTS — local add-on)
        │
        ▼
havenOS receives:
  - Wake word detection event  → trigger LISTENING state
  - STT partial results        → display transcript in LISTENING state
  - Intent result              → display response text
  - TTS audio                  → route to Pi speaker via linux-voice-assistant
```

linux-voice-assistant registers with HA and is auto-discovered. It handles mic input, wake word detection, audio streaming, and TTS playback entirely. havenOS only needs to know when the wake word fires (to show the LISTENING UI) and when a response is ready (to display it).

### 5.2 Wake Word → UI Integration

havenOS-server connects directly to linux-voice-assistant on `localhost:6053` using the ESPHome native API — the same port and protocol HA uses, but entirely local. No HA involvement in this path. Since both processes run on the same Pi, this is a loopback connection that cannot be affected by network issues or HA availability.

havenOS-server uses a Node.js ESPHome native API client (`hjdhjd/esphome-client` or equivalent) to subscribe to entity state changes from linux-voice-assistant. When the voice assistant phase entity changes (idle → wake word detected → listening → processing → responding), havenOS-server immediately pushes the new phase to the browser over the `/events` WebSocket.

```
linux-voice-assistant (localhost:6053, ESPHome native API)
        │  TCP loopback — no HA, no network
        ▼
havenOS-server (ESPHome client subscriber)
        │  /events WebSocket push
        ▼
Browser → LISTENING state transition + transcript display
```

HA still receives voice phase updates via linux-voice-assistant's own HA connection — but that is linux-voice-assistant's concern, not havenOS's. havenOS-server's direct loopback connection to port 6053 is independent of HA's connection to the same port. Both can be connected simultaneously.

### 5.3 Wake Word

- Default: `ok_nabu` (via OpenWakeWord, built into linux-voice-assistant)
- MicroWakeWord also supported as an alternative
- Wake word detection runs on-device (Pi), not on the HA server
- Custom wake word models: `.tflite` files placed in the linux-voice-assistant config directory

### 5.4 Microphone Button

A persistent microphone button is shown in ACTIVE state (bottom-right, 64px circular touch target). Tapping it calls `assist_satellite.accept_pipeline` (or equivalent ESPHome API call) to immediately trigger the voice pipeline without waiting for a wake word.

### 5.5 Volume / Mute

- Audio volume and mic mute are managed by linux-voice-assistant and ALSA
- havenOS exposes a software volume slider in Settings (calls `POST /api/brightness` pattern — a similar shell-exec endpoint for `amixer`)
- Mute state is shown as a persistent indicator in AMBIENT and ACTIVE states, read from the linux-voice-assistant ESPHome entity state via the direct loopback connection

---

## 6. Photo Album

Photos are sourced exclusively from a local **Immich** instance. There is no local directory option. Immich is required for photo functionality; if not configured, the AMBIENT background falls back to a solid dark color.

This is a deliberate constraint. Immich provides album organization, date metadata, shuffle/random logic, and a stable REST API — all things that would otherwise need to be re-implemented for a filesystem source. It also encourages a single photo library rather than a separate copy on the Pi.

### 6.1 Immich Integration

havenOS connects to Immich via its REST API using a configured base URL and API key. The Immich instance must be on the local network; no external Immich access is supported or needed.

**Supported fetch modes (configurable):**

- **Album** — photos from a specific named album (selected by album ID in settings)
- **Favorites** — photos marked as favorites in Immich
- **All photos** — entire library, shuffled
- **Date range** — random selection from a specified date range (e.g., "photos from this month in any year" — useful for a "on this day" feel)

**Fetch behavior:**

- On startup, havenOS fetches a batch of 50 asset IDs from Immich matching the configured mode.
- Photos are fetched individually as needed (`/api/assets/{id}/thumbnail?size=preview`) and cached in memory (LRU, max 20 photos).
- A background refresh runs every 30 minutes to pull new photos into the queue.
- The queue shuffles on each refresh.

### 6.2 Display Behavior

- Photos cycle at a configurable interval (30s–10min, default 60s)
- Transition: crossfade 500ms via Framer Motion `AnimatePresence`
- Portrait orientation photos: blurred copy (`filter: blur(40px) scale(1.1)`) fills the background, original centered and letterboxed
- Landscape photos: `object-fit: cover`, fill edge-to-edge
- If Immich is unreachable or returns no results, a solid `#0a0a0b` background is shown with no error message — the display degrades silently
- Quiet hours suppress photo cycling and dim the display (see §7.1)

### 6.3 Gestures

- Swipe left / right in AMBIENT state → previous / next photo (immediate, no wait for cycle timer)
- Long press on the photo background in AMBIENT → photo info overlay: Immich album name, date taken, location (if available in EXIF). Tap anywhere to dismiss.

---

## 7. Configuration

All configuration is stored in a local JSON file (`~/.havenOS/config.json`). There is no cloud configuration. A settings UI is accessible from the Quick Controls row in ACTIVE state.

### 7.1 Settings Screens

**General**

- Display name (shown in ACTIVE state header)
- Display brightness (0–100%, controls Pi backlight via `rpi-backlight` or HDMI-CEC)
- Quiet hours: start time, end time, dim-to % (or off)
- Screen timeout: minutes of inactivity before AMBIENT (default 30s in ACTIVE)
- Theme: Light / Dark / Auto (follows HA sun entity — light during day, dark at night)
- Accent color: a set of 8 preset colors

**Home Assistant Connection**

- HA base URL (e.g., `http://homeassistant.local:8123`)
- Long-lived access token (input field, stored locally, never transmitted anywhere but the local HA instance)
- Connection status indicator + reconnect button
- Entity selection for: weather entity, media player entity, climate entity(ies), light areas, scene list, camera list

**Photos**

- Immich base URL (e.g., `http://immich.local:2283`)
- Immich API key
- Fetch mode: Album / Favorites / All photos / Date range
- Album selector (dropdown, populated from Immich API after URL + key are saved)
- Date range inputs (shown only when fetch mode is "Date range")
- Cycle interval slider (30s – 10min)
- Shuffle toggle

**Voice**

- Enable/disable wake word
- Wake word model selection (OpenWakeWord or MicroWakeWord; dropdown of available models)
- Wake word sensitivity slider
- Microphone device selection (PipeWire/ALSA input device)
- Speaker device selection
- Speaker volume
- TTS voice selection (dropdown of installed Piper voices, configured in HA)

**Timers**

- Timer chime selection (dropdown of local audio files in configured dir, with preview button)
- Chime volume

**Advanced**

- Log level (Info / Debug)
- Export config / Import config
- Restart application
- Reboot device

---

## 8. HA Integration Details

### 8.1 Connection

havenOS connects to HA via the WebSocket API (`ws://`). It authenticates using a long-lived access token. It does **not** use the HA frontend, Lovelace, or any HA component — purely the API.

**On connect:**

1. Authenticate with token
2. Subscribe to state changes for all configured entities
3. Fetch current state of all configured entities (initial render)
4. Subscribe to HA events: `timer_finished`, `call_service` responses
5. Register all havenOS entities under the `havenOS Display` device:
   - `media_player.havenos_display`
   - `notify.havenos_display`
   - `number.havenos_brightness`
   - `switch.havenos_screen`
   - `sensor.havenos_screen_state`
   - `sensor.havenos_voice_state`
   - `switch.havenos_wake_word`
   - `button.havenos_next_photo`
   - `sensor.havenos_current_photo`
   - `sensor.havenos_active_source`
6. Push current state for all registered entities immediately after registration

**On disconnect:**

- Show a small "Reconnecting…" indicator (not a blocking overlay)
- Retry with exponential backoff (1s, 2s, 4s, 8s… max 60s)
- Continue showing last known state with a subtle "stale" indicator

### 8.2 Entity Subscriptions

| Module  | Entities                                                         |
| ------- | ---------------------------------------------------------------- |
| Clock   | `sun.sun` (for auto theme)                                       |
| Weather | `weather.*` (configured entity)                                  |
| Music   | `media_player.havenos_display` (havenOS's own registered entity) |
| Timers  | All `timer.*` entities                                           |
| Lights  | All `light.*` entities in configured areas                       |
| Climate | All `climate.*` entities (configured)                            |
| Cameras | All `camera.*` entities (configured)                             |
| Scenes  | All `scene.*` and selected `script.*` entities                   |

### 8.3 Service Calls

havenOS calls HA services over the WebSocket connection for all modules except Music:

| Action                | HA Service                               |
| --------------------- | ---------------------------------------- |
| Toggle light          | `light.turn_on` / `light.turn_off`       |
| Set brightness        | `light.turn_on` with `brightness_pct`    |
| Set color temperature | `light.turn_on` with `color_temp_kelvin` |
| Set climate temp      | `climate.set_temperature`                |
| Set climate mode      | `climate.set_hvac_mode`                  |
| Create timer          | `timer.start`                            |
| Cancel timer          | `timer.cancel`                           |
| Activate scene        | `scene.turn_on`                          |
| Run script            | `script.turn_on`                         |

**Music commands do not go through HA.** The browser calls the MA REST API and Sendspin controller role directly. havenOS-server syncs state to HA as a side effect. Music controls work even if HA is down.

### 8.5 HA-Registered Entities and Services

havenOS-server registers the following with HA on connection via the WebSocket API. All entities appear under a single `havenOS Display` device in HA and are available to automations, scripts, dashboards, and voice commands.

**Media**

| Entity                         | Type           | What it does                                                                                                                                           |
| ------------------------------ | -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `media_player.havenos_display` | `media_player` | Reflects Sendspin playback state (synced by havenOS-server). Accepts all standard `media_player` services — commands are forwarded to the MA REST API. |
| `notify.havenos_display`       | notify service | Triggers a broadcast. Accepts `message`, `title`, and `data.icon`. Equivalent to `POST /api/broadcast`.                                                |

**Display**

| Entity                      | Type             | What it does                                                                                                                                                                                                                                                  |
| --------------------------- | ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `number.havenos_brightness` | `number` (0–100) | Current display brightness. HA can read or set it. Setting it calls `POST /api/brightness` internally. Enables automations like "dim to 20% at sunset" or "full brightness at 7am".                                                                           |
| `switch.havenos_screen`     | `switch`         | Screen on/off. Turning off blanks the display and disables the photo slideshow (equivalent to quiet hours with dim=0). Turning on restores normal operation. Distinct from brightness — this is a hard on/off. Useful for "turn off all screens" automations. |

**Screen state**

| Entity                        | Type     | What it does                                                                                                                                                                                                                                                                                              |
| ----------------------------- | -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `sensor.havenos_screen_state` | `sensor` | Current screen state: `ambient`, `active`, `listening`, `detail`, `ha_dashboard`. Updated on every state transition. Lets HA conditionals and automations react to what the user is doing — e.g. pause a podcast when `listening`, trigger a welcome scene when transitioning from `ambient` to `active`. |

**Voice**

| Entity                       | Type     | What it does                                                                                                                                                                                                                                                        |
| ---------------------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `sensor.havenos_voice_state` | `sensor` | Current voice pipeline state: `idle`, `listening`, `processing`, `responding`. Sourced from the linux-voice-assistant ESPHome phase subscription. Lets HA pause music while the assistant is listening and resume when it returns to idle.                          |
| `switch.havenos_wake_word`   | `switch` | Wake word detection on/off. Turning off mutes the microphone listener. HA can tie this to a "do not disturb" mode, bedtime routine, or mute all smart speakers automation. State is bidirectional — toggling from the havenOS Settings UI also updates this entity. |

**Photos**

| Entity                         | Type     | What it does                                                                                                                                                                                                                                            |
| ------------------------------ | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `button.havenos_next_photo`    | `button` | Advances to the next photo immediately, bypassing the cycle timer. Useful for dashboards with a "next photo" button or automations that advance photos on a schedule.                                                                                   |
| `sensor.havenos_current_photo` | `sensor` | The Immich asset ID of the currently displayed photo, with attributes for `album_name`, `date_taken`, and `location` (when available). Useful for logging, conditionals, and displaying photo metadata in an HA dashboard alongside the havenOS iframe. |

**Audio sources**

| Entity                         | Type     | What it does                                                                                                                                                                                |
| ------------------------------ | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `sensor.havenos_active_source` | `sensor` | Current active audio source: `airplay`, `sendspin`, `broadcast`, `voice`, or `idle`. Lets HA automations react to what's playing — e.g. dim lights when Sendspin starts, restore when idle. |

**Implementation notes:**

- All entities are registered using the HA WebSocket API's entity registration pattern — no custom component or HACS integration required on the HA side.
- havenOS-server is the authoritative source for all entity states. It pushes state updates to HA immediately on any internal change (screen transition, brightness change, voice phase change, photo advance, source change).
- For `number.havenos_brightness` and `switch.havenos_screen`, HA commands are received by havenOS-server over the HA WebSocket and dispatched to the appropriate internal handler (brightness → shell-exec, screen → `/events` push to browser).
- For `switch.havenos_wake_word`, havenOS-server sends an ESPHome command to linux-voice-assistant on `localhost:6053` to enable/disable wake word detection.
- For `sensor.havenos_active_source`, havenOS-server updates the entity whenever source arbitration changes the active source.

### 8.6 Photo Fetch (Immich)

If Immich is configured, havenOS fetches photos using the Immich REST API (`/api/album/{id}/assets`, `/api/asset/{id}/original`). This is a direct local HTTP call — it does not go through HA. The Immich URL and API key are stored in the havenOS config.

---

### 9.1 Runtime

**Renderer:** Chromium, launched in kiosk mode by systemd on boot. Points at `http://localhost:3000`. No Electron, no Tauri.

```
chromium-browser \
  --kiosk \
  --noerror-dialogs \
  --disable-infobars \
  --no-first-run \
  --app=http://localhost:3000
```

Pi OS Bookworm ships Chromium 120+, which supports all required CSS features (`backdrop-filter`, CSS custom properties, `@keyframes`, canvas 2D). No bundled browser needed.

**Server:** A single Node.js process (`havenOS-server`) serving `localhost:3000`. It is the only backend process havenOS runs (besides linux-voice-assistant). Responsibilities:

- Serve the static app (HTML, CSS, JS, fonts, SVG icons) from `dist/`
- `GET /api/config` / `POST /api/config` — read and write `~/.havenOS/config.json`
- `POST /api/brightness` — set display brightness; shell-execs brightness control; syncs `number.havenos_brightness` to HA
- `POST /api/broadcast` — receive broadcast from any local process; dispatch TTS + visual overlay; also receives HA `notify.havenos_display` calls via HA WebSocket
- `POST /api/wake-word` — enable/disable wake word; sends ESPHome command to linux-voice-assistant; syncs `switch.havenos_wake_word` to HA
- `WebSocket /events` — persistent connection to browser; pushes voice phases, broadcasts, active source changes, and HA commands
- **Sendspin metadata client** — lightweight Sendspin connection to the local Sendspin server (metadata role only); translates now-playing state into `media_player.havenos_display` HA entity updates; forwards inbound HA media player commands to the MA REST API
- **shairport-sync metadata pipe watcher** — reads the shairport-sync named metadata pipe; updates `media_player.havenos_display` and `sensor.havenos_active_source` in HA on AirPlay session start/end/track-change
- **Active source arbitration** — tracks which audio source (AirPlay, Sendspin) is active; signals session start/end; updates `sensor.havenos_active_source` in HA
- **HA WebSocket** — connects to HA; registers and keeps all havenOS entities under the `havenOS Display` device in sync; receives inbound commands for all controllable entities
- **ESPHome client** — connects to `localhost:6053`; subscribes to voice phase changes; sends `announce` and wake-word enable/disable commands to linux-voice-assistant. Entirely local — does not go through HA

havenOS-server is intentionally narrow — it handles configuration, brightness, broadcast, wake word, and HA entity sync. All music flows through MA and Sendspin directly. No IPC between server and music daemons beyond the Sendspin metadata client and the shairport-sync pipe watcher.

### 9.2 Process Structure

Four processes managed by systemd, started in order on boot.

```
systemd
├── havenOS-server.service         (Node.js, localhost:3000)
│     ├── serves static app, config API, brightness API
│     ├── POST /api/broadcast      ← local processes or HA notify
│     ├── POST /api/wake-word      → ESPHome command + HA entity sync
│     ├── WebSocket /events        → browser (voice phases, broadcasts,
│     │                              active source changes)
│     ├── Sendspin metadata client → localhost (Sendspin server)
│     │                              syncs media_player.havenos_display to HA
│     │                              forwards inbound HA commands → MA REST API
│     ├── shairport-sync pipe watcher → AirPlay now-playing → HA entity sync
│     ├── active source arbitration → AirPlay vs Sendspin priority
│     ├── HA WebSocket             → registers all havenOS Display entities,
│     │                              syncs state bidirectionally,
│     │                              receives inbound commands (all entity types)
│     └── ESPHome client           → localhost:6053 (linux-voice-assistant)
│                                    subscribes to voice phases, sends announce
│                                    and wake-word enable/disable commands
│
├── havenOS-ui.service             (Chromium kiosk, depends on havenOS-server)
│     └── http://localhost:3000
│         browser also connects directly to:
│           · Sendspin server (metadata/artwork/controller roles)
│           · MA REST API (library browse, play_media)
│
├── linux-voice-assistant.service  (Python)
│     ├── localhost:6053  ESPHome native API ← havenOS-server connects here
│     └── → HA (ESPHome protocol, separately)
│           handles voice pipeline, STT, TTS, wake word, announces
│
├── shairport-sync.service         (AirPlay / AirPlay 2 receiver)
│     ├── advertises as named AirPlay speaker via mDNS
│     ├── outputs audio directly to ALSA/PipeWire
│     └── writes track metadata to named pipe → havenOS-server watches
│
└── sendspin.service               (Sendspin daemon — multi-room audio receiver)
      ├── auto-discovers Sendspin servers via mDNS
      └── plays synchronized audio (sendspin-cli daemon mode)
```

Each service has `Restart=always RestartSec=2`. **Boot sequence:** havenOS-server → Chromium (2s delay) → linux-voice-assistant (2s delay) → shairport-sync → sendspin.

### 9.3 What Lives Where

| Concern                                                  | Where it lives                                                                                             |
| -------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| UI rendering                                             | Browser                                                                                                    |
| App state management                                     | Browser (Zustand)                                                                                          |
| HA entity subscriptions (weather, lights, climate, etc.) | Browser → HA WebSocket                                                                                     |
| HA service calls (lights, climate, timers, scenes)       | Browser → HA WebSocket                                                                                     |
| Music library browse                                     | Browser → MA REST API (`http://MA_SERVER:8095`)                                                            |
| Music play / queue                                       | Browser → MA REST API `POST /player_queues/{id}/play_media`                                                |
| Music playback control (UI)                              | Browser → Sendspin server (controller role, direct WebSocket)                                              |
| Music now-playing state                                  | Sendspin server → browser (metadata + artwork roles, direct WebSocket)                                     |
| HA entity sync for music                                 | havenOS-server Sendspin metadata client → `media_player.havenos_display`                                   |
| Inbound HA music commands                                | HA → havenOS-server HA WebSocket → MA REST API                                                             |
| Photo cycling                                            | Browser → direct HTTP to Immich                                                                            |
| Config read/write                                        | Browser → `GET/POST /api/config` → havenOS-server                                                          |
| Wake word / voice phase relay                            | linux-voice-assistant (`localhost:6053`) → havenOS-server ESPHome client (loopback) → `/events` → browser  |
| Broadcast (inbound)                                      | Local: `POST /api/broadcast` → havenOS-server · HA: `notify.havenos_display` → havenOS-server HA WebSocket |
| Broadcast TTS + audio                                    | havenOS-server → ESPHome `announce` → linux-voice-assistant → speaker                                      |
| Broadcast visual overlay                                 | havenOS-server → `/events` → browser overlay                                                               |
| Display brightness (HA-controlled)                       | HA → havenOS-server HA WebSocket → shell-exec + `/events` → browser                                        |
| Display brightness (UI-controlled)                       | Browser → `POST /api/brightness` → havenOS-server → shell-exec + HA entity sync                            |
| Screen on/off (HA-controlled)                            | HA → havenOS-server HA WebSocket → `/events` → browser                                                     |
| Screen state reporting                                   | Browser screen transitions → havenOS-server → HA entity update                                             |
| Voice state reporting                                    | linux-voice-assistant ESPHome phases → havenOS-server → HA entity update + `/events` → browser             |
| Wake word enable/disable (HA)                            | HA → havenOS-server HA WebSocket → ESPHome command → linux-voice-assistant                                 |
| Wake word enable/disable (UI)                            | Browser → `POST /api/wake-word` → havenOS-server → ESPHome command + HA entity sync                        |
| Next photo (HA)                                          | HA → havenOS-server HA WebSocket → `/events` → browser                                                     |
| Current photo reporting                                  | Browser photo advance → havenOS-server → HA entity update                                                  |
| AirPlay audio playback                                   | shairport-sync daemon → ALSA/PipeWire                                                                      |
| AirPlay now-playing + HA sync                            | shairport-sync metadata pipe → havenOS-server → `media_player.havenos_display`                             |
| Sendspin audio playback                                  | sendspin-cli daemon → ALSA/PipeWire                                                                        |
| Sendspin now-playing / artwork / controls                | Browser → direct WebSocket to Sendspin server (metadata, artwork, controller roles)                        |
| Active source arbitration                                | havenOS-server — tracks AirPlay vs Sendspin; updates `sensor.havenos_active_source`                        |
| Audio playback                                           | shairport-sync (AirPlay) · sendspin-cli (Sendspin)                                                         |
| Audio routing (mic, wake word, TTS)                      | linux-voice-assistant + ALSA (entirely outside havenOS)                                                    |

HA is a sync target for music and display state, not a control path. Music controls, voice, and display brightness all work whether or not HA is connected.

### 9.4 Rendering

The UI is built with **React 18** and **Tailwind CSS v4**, compiled to a static bundle in `dist/` served by the local server.

**React:** Used for component composition, declarative rendering, and the animation lifecycle (mount/unmount for screen transitions). The component tree maps directly to screen states — each state is its own top-level component that mounts and unmounts with animated transitions. React's reconciler handles DOM updates efficiently without manual diffing.

**Tailwind CSS v4:** Used for all styling. No custom CSS files — all styles are Tailwind utility classes. Tailwind's `@theme` block in the root CSS file defines the design token system (colors, spacing, radii, fonts) so theme switching (dark/light, accent color) is handled by swapping CSS custom properties on the root element, which Tailwind's `var()` references pick up automatically.

**Build toolchain:**

- Vite for bundling and dev server (fast HMR during development on a separate machine)
- TypeScript strict mode throughout
- `vite build` output goes to `dist/` — the server serves this directly

**Key libraries:**

- `zustand` — state management (see §9.5)
- `framer-motion` — screen transition animations and gesture handling (swipe-to-dismiss, press feedback)
- `@tanstack/react-query` — data fetching from the local server API (photos, config)
- `react-use-websocket` — HA WebSocket connection and the local `/events` WebSocket

**No component library.** All UI components are bespoke. shadcn/ui and similar are not used — their interaction patterns and sizing are desktop-first and incompatible with the touch standards in §9.4.

**Font loading:** Both typefaces are bundled in `dist/fonts/` as WOFF2 files and referenced via `@font-face` in the Tailwind theme. No Google Fonts. No network font requests.

### 9.5 Touch Interaction Standards

Touch is the primary and assumed input method. Every decision in the component layer should be made with a finger, not a cursor, in mind.

**Minimum touch target:** 48×48px for all interactive elements, no exceptions. Elements that are visually smaller (e.g., a close × icon) must have an invisible touch target extended to 48px using padding or an absolute-positioned hit area.

**No hover states.** Tailwind's `hover:` utilities are not used anywhere in the codebase. Feedback for interactivity is communicated through visual affordance (size, contrast, border, icon) and press states only.

**Press feedback:** Every tappable element uses Framer Motion's `whileTap` scale animation (`scale: 0.95`, 100ms spring) to confirm the touch registered. This replaces `:active` CSS pseudo-class, which has poor latency on mobile Chromium.

**Gesture vocabulary:** Consistent across the entire app. No module invents its own gesture.

| Gesture                    | Action                                                                |
| -------------------------- | --------------------------------------------------------------------- |
| Tap                        | Primary action on element                                             |
| Long press (500ms)         | Secondary action / context (e.g., photo info in AMBIENT)              |
| Swipe down (from top 80px) | Dismiss MODULE DETAIL or HA DASHBOARD                                 |
| Swipe left / right         | Navigate photo slideshow (AMBIENT), scroll carousels (ACTIVE modules) |
| Swipe up (from bottom)     | No action (reserved to avoid conflict with OS gestures)               |
| Two-finger swipe down      | No action                                                             |
| Pinch                      | No action (no zoom anywhere)                                          |

Zoom is disabled globally via the viewport meta tag (`user-scalable=no`). Accidental pinch-zoom on a kiosk display breaks the layout and provides no benefit.

**Scroll behavior:** All scrollable containers use `-webkit-overflow-scrolling: touch` (via Tailwind's `overflow-y-auto` + `[touch-action:pan-y]`). Scrollable areas have visible scroll indicators (thin accent-colored scrollbar via Tailwind `scrollbar-thin`). Momentum scrolling is enabled. Horizontal scroll containers snap to item boundaries using CSS scroll snap (`snap-x snap-mandatory`, `snap-center` on each child).

**Touch target spacing:** Interactive elements within a group (e.g., playback controls) are spaced a minimum of 8px apart. Controls that trigger destructive or irreversible actions (timer cancel, scene activate) have 16px minimum spacing from adjacent controls and use a distinct visual treatment (outlined rather than filled).

**Input latency:** All tap handlers are on `onPointerDown` (not `onClick`) where immediate feedback is expected. `onClick` is reserved for actions where the tap-up confirmation is appropriate (e.g., form submission). This eliminates the 300ms click delay that Chromium applies on touch when `touch-action` is not set — which is mitigated globally via Tailwind's `[touch-action:manipulation]` on the root element.

### 9.6 State Management

State is managed with **Zustand**. A single store holds all application state. Components subscribe to specific slices — a timer component only re-renders when timer state changes, not when the photo changes.

```typescript
interface BroadcastMessage {
  id: string // uuid, for keying React list
  message: string
  title?: string
  icon?: string // name from havenOS SVG icon set, e.g. 'door', 'bell', 'alert'
  tts: boolean // whether audio was/should be played
  receivedAt: number // Date.now()
}

interface HavenStore {
  // Screen routing — every transition is reported to HA as sensor.havenos_screen_state
  screen: 'ambient' | 'active' | 'listening' | 'detail' | 'ha-dashboard'
  activeModule: Module | null
  navigate: (screen: Screen, module?: Module) => void

  // HA connection — weather, lights, climate, timers, scenes, cameras
  ha: {
    connected: boolean
    stale: boolean
    entities: Record<string, HAEntity>
  }
  callService: (domain: string, service: string, data: object) => void

  // Active audio source — determined by havenOS-server source arbitration
  // Reported to HA as sensor.havenos_active_source
  activeSource: 'airplay' | 'sendspin' | 'broadcast' | 'voice' | null

  // Now-playing — single source of truth for all audio playback display
  // AirPlay: populated from shairport-sync metadata pipe via havenOS-server /events
  // Sendspin: populated directly from Sendspin server metadata/artwork roles (browser WebSocket)
  nowPlaying: {
    source: 'airplay' | 'sendspin' | null
    state: 'playing' | 'paused' | 'stopped'
    title: string
    artist: string
    album: string
    artUrl: string
    duration: number
    position: number
    volume: number
    shuffle: boolean
    repeat: 'off' | 'track' | 'playlist'
  }

  // Voice pipeline — state sourced from ESPHome phase events via /events
  voice: {
    state: 'idle' | 'listening' | 'processing' | 'responding'
    transcript: string
    response: string
    wakeWordEnabled: boolean // mirrors switch.havenos_wake_word in HA
    setWakeWord: (enabled: boolean) => void // POSTs to /api/wake-word
  }

  // Display controls — mirrored to HA entities, settable from UI or HA
  display: {
    brightness: number // 0–100; mirrors number.havenos_brightness
    screenOn: boolean // mirrors switch.havenos_screen
    setBrightness: (value: number) => void // POSTs to /api/brightness
    setScreenOn: (on: boolean) => void // POSTs to /api/screen
  }

  // Broadcast queue — populated by /events pushes from havenOS-server
  // Supports both HA notify.havenos_display and direct POST /api/broadcast
  broadcasts: {
    queue: BroadcastMessage[]
    current: BroadcastMessage | null
    dismiss: () => void // removes current, advances queue
  }

  // Photos — current photo info reported to HA as sensor.havenos_current_photo
  photos: {
    current: PhotoAsset | null // { id, albumName, dateTaken, location }
    queue: PhotoAsset[]
    advance: () => void // also triggers HA sensor update
    previous: () => void
  }

  // Settings (persisted to server config API)
  settings: AppSettings
  updateSettings: (patch: Partial<AppSettings>) => void
}
```

No Redux, no Context-based prop drilling, no global event bus. Zustand's selector pattern keeps component re-renders surgical.

### 9.7 Performance Targets

| Metric                               | Target                                                        |
| ------------------------------------ | ------------------------------------------------------------- |
| Cold start to AMBIENT                | < 8 seconds (server + Chromium boot)                          |
| Touch to ACTIVE transition           | < 100ms                                                       |
| Wake word to LISTENING visual        | < 300ms (HA state change → havenOS-server → /events → render) |
| HA entity update to UI render        | < 50ms                                                        |
| Photo crossfade                      | 500ms, no dropped frames                                      |
| Memory footprint (Chromium + server) | < 300MB RSS total                                             |
| CPU idle (AMBIENT)                   | < 5%                                                          |

---

## 10. Visual Design Language

All design tokens are defined in the Tailwind `@theme` block in `src/index.css`. Components reference tokens via Tailwind utility classes — no hardcoded color or size values in component files.

### 10.1 Typography Scale

Both typefaces are loaded from `dist/fonts/` as WOFF2. No network requests.

| Role                 | Tailwind class                        | Font                     | Size  | Weight |
| -------------------- | ------------------------------------- | ------------------------ | ----- | ------ |
| Clock time           | `font-display text-[120px] font-thin` | Display (e.g., Urbanist) | 120px | 200    |
| Clock date           | `font-display text-[28px] font-light` | Display                  | 28px  | 300    |
| Temperature (detail) | `font-display text-[72px] font-thin`  | Display                  | 72px  | 200    |
| Module header        | `font-sans text-[22px] font-medium`   | UI Sans                  | 22px  | 500    |
| Card primary value   | `font-sans text-[28px] font-normal`   | UI Sans                  | 28px  | 400    |
| Card secondary       | `font-sans text-base font-normal`     | UI Sans                  | 16px  | 400    |
| Labels / captions    | `font-sans text-[13px] font-normal`   | UI Sans                  | 13px  | 400    |
| Voice transcript     | `font-sans text-lg font-normal`       | UI Sans                  | 18px  | 400    |
| Touch targets (min)  | `min-h-12 min-w-12`                   | —                        | 48px  | —      |

### 10.2 Color Themes

Two base themes defined as Tailwind `@theme` token sets. Switching themes swaps the CSS custom property values on `<html>` — all Tailwind classes that reference these tokens update automatically.

**Dark theme (default at night):**

- Background: `#0a0a0b` → `--color-bg`
- Surface: `rgba(255,255,255,0.07)` → `--color-surface` (frosted glass cards)
- Surface border: `rgba(255,255,255,0.12)` → `--color-border`
- Primary text: `#f0ede8` → `--color-text`
- Secondary text: `rgba(240,237,232,0.55)` → `--color-text-muted`
- Accent: configurable → `--color-accent` (default: `#4a9eff`)

**Light theme (default during day):**

- Background: photo (always visible)
- Surface: `rgba(255,255,255,0.75)` + `backdrop-blur-xl` → `--color-surface`
- Surface border: `rgba(0,0,0,0.08)` → `--color-border`
- Primary text: `#1a1a1c` → `--color-text`
- Secondary text: `rgba(26,26,28,0.55)` → `--color-text-muted`
- Accent: configurable → `--color-accent` (default: `#0066cc`)

**Accent colors (8 presets):** Blue, Teal, Coral, Amber, Green, Purple, Rose, Slate. Each preset defines a full `--color-accent` / `--color-accent-dim` / `--color-accent-contrast` triple.

### 10.3 Motion

All transitions are implemented with **Framer Motion**. No raw CSS `transition` or `@keyframes` for screen-level animations — Framer Motion's `AnimatePresence` handles mount/unmount sequencing cleanly with React.

| Event                        | Framer Motion implementation                                   |
| ---------------------------- | -------------------------------------------------------------- |
| AMBIENT → ACTIVE             | `y: '100%' → 0`, 300ms, `easeOut` cubic                        |
| ACTIVE → AMBIENT             | `y: 0 → '100%'`, 250ms, `easeIn` cubic                         |
| LISTENING sheet              | `y: '100%' → 0`, 200ms, spring (stiffness 400, damping 35)     |
| Photo crossfade              | `opacity: 0 → 1` on incoming, 500ms `easeInOut`                |
| MODULE DETAIL / HA DASHBOARD | `y: '100%' → 0`, 300ms, `easeOut` cubic                        |
| Card / button press          | `whileTap={{ scale: 0.95 }}`, spring                           |
| Timer completion overlay     | `scale: 0.9 → 1, opacity: 0 → 1`, 200ms `easeOut`              |
| Voice waveform bars          | `scaleY` keyed to mic amplitude, 60fps via `useAnimationFrame` |

All Framer Motion variants respect `prefers-reduced-motion` — set `transition={{ duration: 0 }}` when the media query is matched.

### 10.4 Iconography

Custom SVG icon set bundled as React components (not an icon font, not an external library). Each icon is a functional component accepting `size`, `className`, and `strokeWidth` props. Default: 24×24px, 1.5px stroke, round linecaps, no fill. Animated variants are implemented with Framer Motion `animate` props on SVG path elements.

Animated icons: sun (slow rotation), rain drops (falling loop), lightning (flash), play↔pause (path morph), microphone (pulsing ring when active).

---

## 11. Out of Scope (v0.1)

The following are deliberately excluded from v0.1 and may be considered for future versions:

- Video playback (YouTube, streaming services)
- Video calls
- Smart home device discovery / onboarding (users configure entity IDs in settings manually)
- Multiple simultaneous users / profiles
- Remote configuration UI (all config is done on-device)
- OTA updates (manual update process via `git pull` + restart)
- Multi-display support
- Integration with any cloud service

---

## 12. Open Questions

1. **Voice phase entity structure from linux-voice-assistant:** havenOS-server connects to linux-voice-assistant on `localhost:6053` via the ESPHome native API (using `hjdhjd/esphome-client` or equivalent Node.js library) and subscribes to entity state changes. The exact entity type, key, and phase values linux-voice-assistant exposes need to be confirmed against the current release. Validate by connecting an ESPHome client and listing entities before implementing the subscription handler. This connection is fully local — HA is not in the path.

2. **Timer creation via voice:** HA Assist natively handles "set a timer for X minutes" intents. However, the mapping between a voice-created timer and a displayed HA `timer.*` entity requires that the Assist intent calls `timer.start` with a predictable entity ID or a named variable. This needs validation against the current HA Assist intent schema.

3. **On-screen keyboard:** Timer labels and search require text input. Options: (a) rely on OS on-screen keyboard (e.g., `matchbox-keyboard`, invoked by the server on `POST /api/keyboard/show`), (b) ship a custom on-screen keyboard component in havenOS. Option (b) is better UX but significant scope. v0.1 uses the OS keyboard for text fields and limits text-heavy interactions to voice.

4. **Photo brightness sampling:** Computing photo brightness to determine scrim opacity requires canvas pixel access. This works in Chromium but may have performance implications on Pi. Alternative: use a fixed medium-opacity scrim and test legibility on a range of photos.

5. **Immich API stability:** Immich is now a required dependency (not optional), so API stability matters more. The Immich REST API is versioned but has broken changes between minor versions. havenOS should check the Immich server version on startup (`/api/server/version`) and warn the user if the version is outside the tested range. Document the minimum supported Immich version prominently in the README.

6. **Display brightness control:** `rpi-backlight` works for the official Pi display. Third-party HDMI touchscreens (e.g., Waveshare) may require different mechanisms (DDC/CI via `ddcutil`, or HDMI-CEC). This needs to be tested against the target hardware and documented; quiet hours dimming depends on it.

---

## 13. Installer Script Specification (Implementation Pending)

This section defines the requirements for a first-run installer script. The script itself is intentionally not implemented yet.

### 13.1 Goals

- Make havenOS setup possible with one command on Raspberry Pi OS Lite (64-bit)
- Ensure deterministic and repeatable host bootstrap
- Keep installation local-first and automation-friendly
- Support non-interactive and idempotent runs for re-provisioning

### 13.2 Script Location and Invocation

- Planned file path: `./install.sh`
- Must be executable
- Must support:
  - Interactive mode (default)
  - Non-interactive mode via `--yes`
- Must return non-zero exit code on any failed critical step

Canonical invocation examples:

```bash
./install.sh
./install.sh --yes
./install.sh --yes --user pi
```

### 13.3 Supported Flags

Required flags:

- `-y, --yes` skip prompts and run non-interactively
- `--user <name>` install per-user config and user units for a specific local account
- `--skip-packages` skip apt package installation
- `--skip-node` skip Node.js setup
- `--skip-kiosk` skip kiosk stack installation (X11 + Chromium)
- `-h, --help` print usage and exit 0

Unknown flags must fail fast with usage output.

### 13.4 Platform and Preflight Checks

The script must run preflight checks before any mutating step:

1. Confirm OS family is Debian/Raspberry Pi OS
2. Confirm architecture is `arm64` or `armv7l`
3. Confirm network connectivity if package installation is not skipped
4. Confirm required base commands exist (`bash`, `apt-get`, `sudo` when not root, `curl`)
5. Confirm target user exists when `--user` is provided
6. Confirm sufficient disk space (minimum 2 GB free)
7. Print a concise execution plan before proceeding

If any critical preflight check fails, the script must exit before changing system state.

### 13.5 Installation Stages

The script must execute in this order:

1. **System package bootstrap** (unless `--skip-packages`)
2. **Node.js bootstrap** (unless `--skip-node`)
3. **Local config bootstrap** (always)
4. **Service unit installation** (if service files are present)
5. **Post-install summary and next steps**

Each stage must emit structured logs with clear start/end markers.

### 13.6 Package Requirements

Base package set (minimum):

- `ca-certificates`
- `curl`
- `git`
- `jq`
- `unzip`
- `rsync`
- `build-essential`
- `shairport-sync`

Kiosk package set (when kiosk is enabled):

- `xserver-xorg`
- `x11-xserver-utils`
- `xinit`
- `openbox`
- `chromium` or `chromium-browser` (whichever is available on the host)

The script must detect Chromium package name differences and install whichever exists.

### 13.7 Node.js Requirements

- Minimum Node.js major version: 20
- If installed version is below minimum, script must upgrade to supported LTS
- If installed version satisfies minimum, script must not reinstall Node.js
- npm must be available on completion

### 13.8 Config Bootstrap

The installer must ensure a user-owned config file exists at:

- `~/.havenOS/config.json` (for target user)

Behavior:

- Create directory if missing
- Create starter config if file is absent
- Preserve existing config if present (no overwrite)
- Set owner/group to target user
- Set file permissions to user-readable/writeable only where practical

Starter config must include placeholders for:

- Home Assistant URL and long-lived token
- Weather entity ID
- Music Assistant URL and player ID
- Voice host/port
- Immich URL and API key placeholder

### 13.9 systemd Integration Requirements

If service files exist in a project `systemd/` directory:

- Install units to `/etc/systemd/system`
- Run daemon reload after unit copy
- Do not auto-enable or auto-start services unless explicitly requested by a future flag
- Print explicit enable/start commands in final summary

If no unit files exist yet, script must log a warning and continue.

### 13.10 Idempotency Requirements

Re-running installer must be safe:

- Reinstalling packages is acceptable if apt determines no changes
- Existing config must remain intact
- Existing units may be updated in place
- No duplicate unit files or duplicate startup entries
- Re-run should converge system state without destructive side effects

### 13.11 Logging and UX Requirements

- Use consistent log prefixes (`INFO`, `WARN`, `ERROR`)
- Keep output human-readable and CI-friendly (line oriented)
- On failure, print failing stage and remediation hint
- On success, print:
  - what was installed
  - what was skipped
  - where config lives
  - next commands to enable/start services

### 13.12 Failure Handling

Must fail fast for:

- missing prerequisites
- apt failures
- Node.js setup failures
- permission errors on required paths

Must continue with warning for non-critical conditions:

- optional package unavailable (with fallback path)
- no `systemd/` folder present yet

### 13.13 Security and Safety Constraints

- Never echo secrets in logs
- Do not fetch remote scripts without TLS
- Avoid `curl | bash` unless source and checksum strategy are documented
- Use least-privilege ownership for generated user files
- Avoid destructive operations on existing user config

### 13.14 Acceptance Criteria

The installer specification is considered satisfied when:

1. A fresh Raspberry Pi OS Lite device can be prepared in one command with non-interactive mode.
2. Re-running installer does not break existing config or service setup.
3. Installer exits with clear non-zero codes on critical failures.
4. Installer creates a valid starter config for havenOS integration points.
5. Installer handles both Chromium package naming variants.
6. Installer behavior matches all required flags and stage ordering above.
