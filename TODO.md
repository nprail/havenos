# havenOS todo

What is left to build, check or decide for the current version. Last updated: 2026-11-02.

Legend: **[ ]** open, **[~]** partly done, **[x]** done (move finished items to "Done" at the bottom).

## Out of scope for this version

Decided, do not build: calendar panels, alarm panels, crossfade on music takeover, an on-screen keyboard for library search, multi-room sync, OTA updates, user accounts, cloud services, camera feeds, video playback. Entities with no Home Assistant area stay hidden. (docs/specs/00 section 8, docs/specs/06 section 7)

## 1. Voice (specs 04 section 3, 05)

Built and tested against fakes and the real ESPHome client (spec 05 section 9 has the detail). **Nothing voice-related has run on a microphone, a speaker, a Pi or a real Assist pipeline** (a Pi 4 now runs the app and music, but has no microphone and voice is off there).

- [ ] V0 Check our flags, entities and media-player features against the Voice Preview Edition; exact parity not required
- [ ] V0b Mic array bring-up on the Pi, for both the reSpeaker XVF3800 (`48k2ch` firmware) and the Lite: formats, gain staging, and confirm the chip's AEC works (assumed; the XVF3800's 48 kHz firmware too). The tool is written: `python -m havenos.core.voice.bringup check`
- [~] V1 Audio: mixer with ducking ramps, local capture and playback, and the VPE sounds with their attribution are built and tested; still open: the separate worker process, the real sound-device path
- [ ] V1b Software echo cancellation spike (WebRTC/speexdsp) with the mixer as reference, only if bring-up shows a board's own AEC does not work (assumed it does); CPU under 25% of one core on a Pi 4
- [~] V2 Wake word, sensitivity, mute are built (microWakeWord, heard TTS "okay nabu"); open: the stop word needs the VPE's model (`[voice] stop_model`), false accepts and CPU on a Pi, a real voice
- [~] V3 `VoiceSatellite` built and tested over an encrypted link with a fake HA; open: try it against a real Assist pipeline
- [~] V4 Replies (early streaming TTS), continue conversation, announcements, start_conversation: built, same open item
- [~] V5 Timers from voice; pause and resume; ringing, stop by tap or word, 15 min cap: built; open: try on real HA
- [~] V6 ESPHome media player: announce and play_media work, feature set is close to the VPE's but not exact (no browse media); not tried on a real HA
- [ ] V7 Tuning: wake while music or a timer plays, volume cap, optional LED colours, Lite USR button
- [ ] V8 Side-by-side against the real VPE
- [~] Spoken announcements and the notification sound: announcements are built; the notification sound is not
- [~] ESPHome Noise encryption (decided: use it): built and tested with aioesphomeapi's client; voice refuses to start without a key; open: add the device to a real Home Assistant with a key

## 2. Music (spec 07)

Built: AirPlay, Sendspin, Spotify Connect, Music Assistant library, arbiter, takeover toast, ducking, HA `media_player`, settings Music card, art cache, Pi deploy files.

- [~] Real audio mixer and single media bus (AirPlay audio plays through a Pi 4 output, verified 2026-11-02): built (`core/audio/`, every source on the mixer's media bus, ducking is the mixer's) and tested with fake devices; open: move it to the separate audio process (V1)
- [ ] Echo reference for the wake word and AEC (V1b): the mixer output is now the exact reference; the AEC itself is only needed if bring-up says so
- [ ] Multi-room clock sync and latency calibration
- [~] Play-from-HA URLs and announcements through the media player: built (URLs as a music source, announcements through the satellite); not tried on a real HA or a real sound device
- [~] Voice library search: built (mic button, record one phrase, Home Assistant speech-to-text, search) and tested with fakes; open: try it with a real speech-to-text provider and real audio
- [ ] Verify the library against a real Music Assistant (URL, token, `play_media` argument, player-id lookup); Sendspin itself is verified
- [ ] Check the settings Music card in a browser
- [~] Verify AirPlay 2 and Spotify on the Pi: AirPlay 2 verified on a Pi 4 with a real sender (2026-11-02); Spotify not installed there (needs the go-librespot binary) and still only works on some accounts
- [ ] Soak test: feeds switching every few seconds, pipe backpressure

## 3. Pi bring-up and hardening (specs 03 sections 7 and 9)

- [~] M1 EGLFS on the Pi; photo pipeline in a process pool: EGLFS runs on a Pi 4 (Debian Qt 6.8, GPU, the 800x480 DSI panel) and the pool runs (2026-11-02, docs/raspberry-pi.md; the PySide6 pip wheel cannot do EGLFS on aarch64); frame pacing not measured
- [ ] G1 idle RSS under 350 MB, no growth over 12 h (Mac: about 180 MB; Pi, first 2 minutes: main process about 300 MB, about 515 MB with the two photo workers; say which one the gate means; no long run yet)
- [ ] G2 at most 1 slow frame per 10 s in crossfade, dashboard slide and waveform, with HA and prefetch running
- [~] G3 boot to first photo under 18 s (Pi, 2026-11-02: was 63 s reboot to web UI; now the window is up about 13 s after power-on and the core finishes starting about 23 s after power-on; first photo not timed; see docs/raspberry-pi.md, "Boot time")
- [ ] G4 hung-GUI watchdog restarts and returns to ambient in under 15 s (no watchdog code exists)
- [~] Real backlight and screen power: built and checked on a Pi 4 (2026-11-02): brightness and Screen drive `/sys/class/backlight`, with a fade and a udev rule for the `video` group, and a "Backlight level" HA sensor; open: try the HA Screen switch on a real HA, tune the gamma by eye, and automatic dimming from a light sensor (hook: `Core.set_auto_scale`)
- [~] M5 first-run setup (QR pairing screen on the display and a web setup wizard built 2026-11-02; tried on a Mac and in a browser, not yet on the Pi's panel), install script for the whole app (`deploy/install.sh` written 2026-11-02; only re-run on an installed Pi, not from a blank card), soak
- [ ] Re-profile CPU on the Pi: the Mac fix for the endless sun-icon rotation took the ambient screen from about 145% to about 2-6% of a core; check nothing else animates forever

## 4. Home Assistant, rooms and photos

- [ ] Exposure changes take up to 5 minutes to show; no HA event exists (accepted, revisit if it annoys)
- [ ] Tile safety for locks and the garage door (open decision; confirm what the Rooms screen does for each)
- [ ] Keep `aioesphomeapi` reasonably current against the VPE's ESPHome 2026.6.0 (exact parity not required); checked 2026-11-01: 46.25.0 is installed and is the latest

## 5. Decisions and housekeeping

- [ ] Not pushed yet: the folder is a git repo with no commits. Cleaned up 2026-11-02 (ignore rules, private notes moved to the ignored `notes/`, font licences, README, stale docs); icons are now Lucide with their notice (done); still needed: the first commit
- [ ] The Homebrew x265 symlink workaround for ffmpeg could break on a `brew upgrade` or `cleanup`

## Done

- 2026-11-02 GitHub Actions workflow (`.github/workflows/docs.yml`) that builds the docmd site and deploys it to GitHub Pages; the link check and build pass locally, the workflow itself has not run on GitHub (Pages must be set to "GitHub Actions" first)
- 2026-11-02 Icons replaced with Lucide (ISC, with Feather MIT notice in `assets/icons/LICENSE.md`; regenerate with `scripts/build_icons.py`)
- 2026-11-02 Licence chosen: MIT (`LICENSE`, `pyproject.toml`, README, contributing and decisions updated); no CLA or DCO
- 2026-11-02 Pre-push cleanup: `.gitignore`, runtime state out of `scripts/`, private bring-up notes moved to the ignored `notes/` (the useful parts are in docs/raspberry-pi.md), LAN addresses and a device name removed from tests and docs, font licences (`assets/fonts/LICENSE.md`), README rewritten (the developer notes are in docs/implementation-notes.md), docs updated for AirPlay and a real Home Assistant now being verified
- 2026-11-02 NASA photos smaller: downloads are shrunk to at most 1920 px and about 100 to 450 KB (originals are tens of MB), JPEGs decode at reduced size, and the bundled sample photos went from 4.1 MB to 2.4 MB; fixed a flaky NASA test (it depended on the shuffle)
- 2026-11-02 Rooms, exposure, announcements and notifications tried on a real Home Assistant (maintainer-confirmed; spec 06 and the docs updated)
- 2026-11-02 Pi 4 bring-up and first real install (notes in docs/raspberry-pi.md): Trixie, Debian's Qt 6.8 and PySide6 (the pip wheel cannot do EGLFS), EGLFS on the DSI panel, systemd units, AirPlay 2 (nqptp, shairport-sync) playing from a real sender, a real Home Assistant, 359 tests pass on the Pi, touch input confirmed. Not checked: Spotify, voice, the performance gates
- 2026-11-02 `deploy/install.sh`: one script from a fresh Trixie Lite to a running havenOS (packages, user, venv with system PySide6, AirPlay, config, units); re-run on the installed Pi, not yet from a blank card
- 2026-11-02 First-time setup: the display shows a QR code (the settings URL with `?code=`, signs in on scan) on first boot and from a gear on the dashboard, so the code no longer needs the HUD; a six-step web wizard (Home Assistant, photos, sound, music, review). Checked on a Mac, in a browser and on the Pi's panel by the user
- 2026-11-02 Sound output chosen on the settings page (real hardware only, live switch, Test sound); the settings page now flags a restart only for real changes
- 2026-11-02 Live screen on the 800x480 touch panel: Home works, a dismiss button on every timer tile, touch targets at least 44 px; the NASA source no longer leaks an HTTP session when settings change
- 2026-11-02 NASA Image of the Day photo source (`core/nasa.py`), shuffled each pass and now the default when no Immich URL is set (`nasa`, `local`, `immich` in the settings page too). Checked against the live feed: 60 images, one 20 MB original downloaded and scaled. The six placeholder sample photos are replaced by 20 bundled NASA images with an attribution file. Not run on a Pi; the full-size originals are large for its memory
- 2026-11-01 Live screen: while music is casting to the display or a timer runs, a full-screen player, a full-screen timer, or up to three splits with a "+N more" button; tapping a tile opens its control view (now-playing, or a new timers view) over it; swipe up or Home goes to the dashboard. Timers can be paused, resumed and extended from the display (not voice timers). Checked with screenshots and real touch events on a Mac, landscape and portrait; the Pi is untested
- 2026-11-01 Shared mixer and media bus (`core/audio/`: streams, `AudioHub`, `BusSink`, cubic `Resampler`); music and voice on one output; the per-source sound-device sink is gone. Child-process cleanup: SIGTERM and SIGINT quit normally, a second one kills the helpers, `setpriv` parent-death on Linux, checked on the real app headless with a fake daemon. Voice library search with Home Assistant speech-to-text. 350 tests pass
- 2026-11-01 Decided: crossfade on takeover and an on-screen keyboard are out of scope; Spotify stays as is with the "works only on some accounts" caveat (documented in README and docs/music/spotify.md); `aioesphomeapi` needed no upgrade
- 2026-11-01 The VPE sounds (CC BY, from firmware commit d4e6fa4) with `assets/sounds/ATTRIBUTION.md`; timer pause and resume from voice (shown in the dashboard and ambient pill); Home Assistant `play_media` URLs as a music source; ordinary voice errors are silent like the VPE's; 303 tests pass
- 2026-11-01 Voice build-out (no hardware): Noise encryption, device profiles, two-bus mixer with VPE ducking, local audio with ffmpeg decode and 48 to 16 kHz downsampling, microWakeWord engine, `VoiceSatellite` (wake cascade, early TTS, continue, announce, timers, mute), Mute / Wake sound / Sensitivity entities, voice settings saved, error state in the voice sheet, bring-up tool, docs; 286 tests pass
- 2026-11-01 Voice decisions: assume the chips' own AEC and the XVF3800 `48k2ch` firmware work (bring-up confirms); the Lite plays everything at 16 kHz; use ESPHome Noise encryption; the speaker is not a concern (item dropped); exact VPE parity not required (specs 04, 05, decisions.md updated)
- 2026-11-01 Voice hardware decided: reSpeaker XVF3800 USB array preferred, reSpeaker Lite 2-mic also supported, via a device profile; the KS0314 HAT is dropped (spec 05 section 6). Hardware echo cancellation is not yet verified on either
- 2026-11-01 Verified on a real Home Assistant: the ESPHome device (including its `media_player`), AirPlay and Sendspin. Spotify Connect works only on some accounts. docmd docs site added (`npm run docs:dev`)
- 2026-11-01 Calendar and alarm panels dropped from scope; no-area entities stay hidden; weather exposure confirmed (specs 00 and 06 updated)
- 2026-10-31 Ambient-screen CPU fix: the sun icon's endless rotation forced a redraw every frame; now a stepped turn every 5 s (`SunIcon.qml`), about 145% to 2-6% of a core
- 2026-10-31 Music build-out: Music Assistant library screen, art cache, takeover toast, idle hint, fight warning, ducking, HA `media_player` and next/previous buttons, settings Music card, Pi deploy files, docs; 234 tests pass
- Earlier: arbiter, AirPlay, Sendspin and Spotify adapters; ESPHome device; Home Assistant, Immich, photos, timers, rooms and notifications, settings web UI (see the READMEs and specs)
