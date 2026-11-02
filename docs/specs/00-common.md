# havenOS: common requirements

Status: draft. Python is the core language. The architecture is in [03 Qt + Python, single app](03-qt-python-single.md).

## 1. Goal

An ambient home-control appliance for a Raspberry Pi 4 with a touch panel. It shows a photo slideshow with glass overlays (clock, weather, now playing, timers), and a touch dashboard for Home Assistant (HA). Voice via HA Assist.

## 2. Target hardware and OS

- Raspberry Pi 4 (4 GB assumed; verify 2 GB), 64-bit Raspberry Pi OS Lite (Trixie preferred), KMS/V3D graphics.
- Panels from 1024x600 to 1920x1080, touch input, optional USB or I2S audio.
- No desktop environment. Boots straight to the app under systemd.

## 3. Functional requirements (ambient UI)

| ID | Requirement |
|---|---|
| F1 | Ambient: two-layer photo crossfade (800 ms), preloaded and decoded; portrait photos get a blurred backdrop plus letterbox. |
| F2 | Glass panels: clock, weather, now-playing strip, timer pill. Blur can be disabled (flat tint fallback). |
| F3 | Tap opens the dashboard (weather, music, timers, quick controls, mic). Swipe left/right changes photo. Swipe down dismisses. |
| F4 | Voice sheet: 40-bar waveform, Assist sequence (listening, transcript, thinking, reply). |
| F5 | Timers with expiry takeover screen. |
| F6 | Auto-return to ambient after idle (default 30 s). |
| F7 | Stats HUD (fps, worst frame, memory), toggled by triple-tap on top-left corner or `f`. |
| F8 | Layout scales from window size: 1 unit = 16 px = `min(w/80, h/50)`. |
| F9 | Fonts: Urbanist ExtraLight/Light, Inter Regular/Medium. |
| F10 | Keyboard shortcuts for dev: `f b v t a d`, arrows, `Esc`. |
| F11 | Live screen: while music is casting to the display or any timer runs, the resting screen is not the photos but a full-screen player and/or timers. One thing fills the screen; two or three share it (never more than three splits, music first, then the timers that finish soonest). Timers that do not fit get a "+N more" button. Tapping a tile opens its control view over the live screen (the now-playing view, or the timers view with every timer) without leaving it; swipe up or Home goes to the dashboard, and the idle timeout comes back to the live screen. With nothing playing and no timers the photos return. |

Beyond the ambient UI:

| ID | Requirement |
|---|---|
| N1 | Home Assistant integration: states, service calls, areas/entities for quick controls. |
| N2 | Photo source: local folder, Immich and NASA Image of the Day (the default) behind one interface. |
| N3 | Assist pipeline: wake or tap-to-talk, audio capture, STT/TTS via HA. |
| N4 | Config file plus first-run setup (HA URL and token, photo source, display size). Built: a code-protected settings web UI edits all of it live (see the root README). |
| N5 | Crash recovery: the display recovers to ambient within 5 s of a process crash. |
| N6 | Health and logs: structured logs to journald, `/health` or equivalent status. |

## 4. Non-functional targets (to be confirmed by Pi measurement)

- Boot to first photo: < 25 s from power.
- Interaction (tap to dashboard visible): < 150 ms.
- Animation: no more than 1 slow frame (> 33 ms) per 10 s during crossfade, slide, waveform.
- Idle steady state: total RSS (all processes) < 600 MB on a 4 GB board; no growth > 5% over 12 h soak.
- CPU at idle ambient: < 25% of one core average, SoC temp < 70 C without active cooling.

## 5. Core responsibilities (Python)

The core owns everything that is not drawing pixels.

1. **State store**: one typed, in-memory model (display mode, current photo, timers, weather, media, quick controls, voice session). Single writer; every change emits an event.
2. **HA client**: persistent WebSocket to HA (`/api/websocket`), subscribes to entity state changes, performs service calls. Reconnect with backoff.
3. **Photo pipeline**: list, decode, downscale to display size (max 1920x1200), pre-blur backdrop, bounded cache (N photos). Runs in a worker process or thread pool, never on the event loop.
4. **Timers**: monotonic clock, persisted across restarts.
5. **Voice**: audio capture, Assist pipeline, waveform levels.
6. **Idle and display policy**: idle timeout, screen dim/off, mode transitions.
7. **Config and secrets**: TOML file, token in a root-readable file, not in the repo.

Language and libraries: Python 3.12+, `asyncio`, `aiohttp` (HA WebSocket), `pydantic` v2 (models), `Pillow` (images), `structlog` or stdlib logging, `pytest` + `pytest-asyncio`. Packaging with `uv` or `pip` + venv; Python deps pinned in a lockfile.

## 6. Core/UI contract

The core and UI talk through one logical contract (state snapshots, events, commands), so the UI could be swapped or moved to another process. Today it is an in-process interface.

**Events (core to UI):** `state.snapshot` (full state on connect), `state.patch` (partial update), `photo.changed {id, url|path, orientation, dominant_color}`, `timer.started|tick|expired`, `voice.level {bars[40]}`, `voice.transcript {text, final}`, `voice.reply {text}`, `ha.entity {id, state, attrs}`, `error {code, message}`.

**Commands (UI to core):** `mode.set {ambient|dashboard|voice}`, `photo.next|prev`, `timer.start {seconds, label}`, `timer.cancel {id}`, `voice.start|stop`, `ha.call {domain, service, target, data}`, `ui.activity` (resets idle), `config.set {blur}`.

Rules: the UI holds no business state beyond view state (hover, drag position, animation). Every event carries a monotonic `seq`. The UI must render correctly from `state.snapshot` alone, so a reconnect or restart is always safe.

## 7. Test and measurement plan

1. Unit tests for core (state, timers, HA client with a fake server, photo pipeline).
2. Contract tests: a recorded event stream replayed against the UI.
3. Pi measurement per `scripts/measure.sh`: boot-to-photo, 10 min idle, HUD worst-frame, blur on/off, 12 h soak.
4. Gate: the build proceeds only if it meets section 4 on the Pi.

## 8. Out of scope for the first milestone

Multi-room sync, OTA update system, user accounts, cloud services, camera feeds, video playback. Also out of scope for the current version: calendar and alarm panels, crossfade on music takeover, and an on-screen keyboard (library search is by physical keyboard or by voice).
