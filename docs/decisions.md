# havenOS: decisions

Status as of 2026-11-01. What was decided, and what is still open. The detailed designs are in `docs/specs/`.

## 1. Goal

An open-source Raspberry Pi 4 Home Assistant smart display, a Nest Hub alternative. Framing: "a Voice Preview Edition with a screen." Priorities: polished, fast, very modern. Development speed is not a constraint (AI-assisted).

## 2. Decided

- **One process: a pure-Python core plus a Qt Quick (QML) UI**, sharing a `qasync` event loop. `core/` never imports Qt (enforced by `tests/test_import_boundary.py`); the bridge is the only place Qt and core meet. Design: `docs/specs/03-qt-python-single.md`.
- **Why Qt:** low RAM and boot cost, no compositor needed (EGLFS), and the glass look is achievable with `ShaderEffectSource` + `MultiEffect`. The core stays in Python so the Home Assistant and ESPHome libraries are available.
- **asyncio and Qt:** `PySide6.QtAsyncio` has no network I/O (aiohttp hangs) and hangs on process-pool futures, so the app uses `qasync`.
- **Home Assistant identity:** the ESPHome native API. HA adopts the display as an ESPHome device and exposes its screen, brightness and media-player entities.
- **Voice:** VPE parity through the satellite protocol, planned in `docs/specs/05-voice-pipeline.md`. Wake word on-device, our own audio worker and two-bus mixer (not mpv), and a USB mic array with a built-in DSP: the reSpeaker XVF3800 (preferred) or the Lite, chosen through a device profile. The chips' own AEC and the XVF3800's 48 kHz USB firmware are assumed to work; the Lite plays everything at 16 kHz; ESPHome Noise encryption is used; the speaker is not a concern; exact VPE parity (flags, API version) is not required. Software AEC is the fallback if bring-up shows a board's AEC does not work.
- **Music:** AirPlay (shairport-sync), Spotify Connect (go-librespot), Sendspin and Music Assistant, with one source active at a time (`docs/specs/07-music-pipeline.md`).
- **Photos:** a local folder or Immich, behind one interface.
- **Deployment:** host-level systemd, no containers.
- **Exposure rule:** only entities exposed to Assist are shown, and it fails closed (`docs/specs/06-rooms-exposure-notifications.md`).
- **Scope for this version:** no calendar or alarm panels, no crossfade on music takeover, no on-screen keyboard (library search is by physical keyboard or by voice), no multi-room sync, OTA updates, user accounts, cloud services, camera feeds or video playback (`docs/specs/00-common.md` section 8).

## 3. Traps to remember

- `MultiEffect` (used for the glass) needs Qt 6.5 or newer. Raspberry Pi OS Bookworm ships 6.4, so use Trixie or the PySide6 wheel. Not verified on hardware.
- Glass over glass cannot sample itself, so nested panels use a flat tint.
- Headless Qt screenshots do not render blur (software backend), so judge the look on a real display.

## 4. Open

- Pi 4 measurements: RAM, CPU, boot time, temperature and frame pacing (`TODO.md` section 3).
- Judge the look in person, with blur on and off, on the target 7" and 10.1" panels.
- Touch latency, rotation and DSI behaviour.
- Tile safety for locks and the garage door.
- Confirm in bring-up (V0b) that the XVF3800 and Lite really cancel our playback and that the XVF3800's 48 kHz USB firmware works; both are assumed.
- Licensing: havenOS is MIT (decided 2026-11-02). Qt is LGPLv3, used as a separately installed library (its VirtualKeyboard is GPL-only and unused). No CLA or DCO: contributions come in under the same MIT licence.
