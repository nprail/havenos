# havenOS

A fully local smart display for Raspberry Pi that connects to Home Assistant, displays a custom touch-first UI, and supports offline voice workflows.

## Installation Plan

The installer is intentionally spec-first right now. Implementation should follow the requirements in the install script spec in [SPEC.md](SPEC.md).

Target installer behavior:

- One-command setup for Raspberry Pi OS Lite
- Deterministic package and runtime bootstrap
- Safe re-runs (idempotent behavior)
- Local config bootstrap with clear post-install steps

havenOS is designed as a Nest Hub-style ambient display without cloud dependencies. It runs in Chromium kiosk mode, uses Home Assistant as a data/control bus, and keeps rendering and interaction in a bespoke frontend.

## Status

- Version: `0.1` (draft)
- Project state: pre-development
- Primary reference: [SPEC.md](SPEC.md)

## Core Goals

- Local-only operation (no cloud APIs)
- Touch-first interface designed for Raspberry Pi touchscreens
- Ambient-first display that stays glanceable from across a room
- Fully custom UI (no Lovelace dependency for core views)
- Home Assistant integration via API, not UI embedding (except dedicated HA Dashboard page)

## Planned Feature Set

- Ambient photo slideshow with large clock and weather
- Active dashboard with module cards and quick controls
- Voice listening/processing/responding UI from local voice pipeline
- Module detail overlays for weather, music, timers, lights, climate, cameras, and scenes
- Embedded Home Assistant dashboard escape hatch in a full-screen iframe
- Local broadcast announcements (visual + optional TTS)
- Cast source support:
  - AirPlay via `shairport-sync`
  - Sendspin via `sendspin-cli`

## Hardware Target

- Raspberry Pi 4 (4GB+)
- 7"-10" HDMI touchscreen (target layout: 1280x800; graceful fallback: 1024x600)
- ReSpeaker 2/4-mic input hardware
- USB DAC or 3.5mm audio output path
- Raspberry Pi OS Lite 64-bit

## High-Level Architecture

Runtime is split across four systemd-managed processes:

1. `havenOS-server` (Node.js)
2. `havenOS-ui` (Chromium kiosk)
3. `linux-voice-assistant`
4. `shairport-sync`
5. `sendspin`

Browser responsibilities:

- UI rendering (React)
- App state (Zustand)
- HA entity subscriptions/service calls for most modules
- Music browse and queue via Music Assistant REST API
- Sendspin metadata/artwork/controller WebSocket roles
- Photo retrieval from Immich API

Server responsibilities (`havenOS-server`):

- Serve static app from `dist/`
- Read/write local config (`~/.havenOS/config.json`)
- Brightness and wake-word control endpoints
- Broadcast endpoint and browser event fanout (`/events`)
- HA WebSocket sync for havenOS entities
- Voice phase subscription via ESPHome API on `localhost:6053`
- AirPlay metadata pipe watcher and Sendspin metadata sync
- Active audio source arbitration

## Technology Stack (Planned)

- Frontend: React 18, Tailwind CSS v4, Framer Motion
- State: Zustand
- Data/query: TanStack Query
- WebSockets: `react-use-websocket`
- Build: Vite + TypeScript (strict)
- Runtime browser: Chromium kiosk mode
- Backend: Node.js

## Integrations

### Home Assistant

- Connection: HA WebSocket API + long-lived token
- Used for: entity subscriptions, service calls, and havenOS entity registration
- Custom havenOS entities include:
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

### Voice

- Powered by `linux-voice-assistant` using ESPHome protocol
- Wake word and phase updates are sourced locally from `localhost:6053`
- Supports listening, processing, and responding visual phases in UI

### Photos

- Source: Immich (local network)
- Modes: album, favorites, all photos, date range
- Fallback: if unavailable, ambient uses a dark background

### Music

- Browse and queue: Music Assistant REST API (`:8095`)
- Playback and realtime metadata/control: Sendspin roles
- Additional source: AirPlay via `shairport-sync`

## User Experience Model

Primary screen states:

1. `ambient`
2. `active`
3. `listening`
4. `detail`
5. `ha_dashboard`

Transitions are gesture and inactivity-driven, with progressive disclosure from ambient to detailed controls.

## Local API Surface (Planned)

`havenOS-server` exposes local endpoints on `http://localhost:3000`:

- `GET /api/config`
- `POST /api/config`
- `POST /api/brightness`
- `POST /api/broadcast`
- `POST /api/wake-word`
- `WS /events`

Broadcast example:

```json
{
  "message": "Front door opened",
  "title": "Security",
  "icon": "door",
  "tts": true
}
```

## Development Notes

This repository currently contains the product specification and no implementation code yet.

Expected near-term implementation structure:

- `src/` for React app
- `server/` for Node.js backend process
- `dist/` for built static assets served by backend
- `systemd/` for service unit files

## Performance Targets (Spec)

- Cold start to ambient: `< 8s`
- Touch to active transition: `< 100ms`
- Wake word to listening visual: `< 300ms`
- HA update to render: `< 50ms`
- Ambient idle CPU: `< 5%`

## Scope Boundaries (v0.1)

Out of scope for initial version:

- Video playback/services
- Video calls
- Automatic smart device onboarding
- Multi-user profiles
- Cloud integrations
- OTA update system
- Multi-display orchestration

## Open Questions Before Build

- Exact linux-voice-assistant phase entity schema over ESPHome API
- Timer naming/intents mapping in current HA Assist
- On-screen keyboard approach for touch text input
- Brightness control compatibility across HDMI touchscreen hardware
- Immich version compatibility range and enforcement

## Canonical Spec

For complete behavior, module details, UI states, and implementation constraints, read [SPEC.md](SPEC.md).