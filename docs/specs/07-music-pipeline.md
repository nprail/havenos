# Spec 07: music pipeline (AirPlay 2, Spotify Connect, Sendspin / Music Assistant)

Status: **partly built** (see the end of section 7): M7.0, M7.1 and the Sendspin part of M7.2 exist in this repo. The rest is plan. It builds on `03-qt-python-single.md` (core/bridge/QML split, `Core.handle`, `EventBus`) and `05-voice-pipeline.md` (the audio worker process and its mixer, which this spec plugs into).

## 1. Goal

A havenOS display is a music endpoint that three kinds of sender can cast to, and it shows and controls whatever is playing:

- **AirPlay 2** (receiver), from iPhones, Macs and HomePods' ecosystem.
- **Spotify Connect**, from the Spotify app.
- **Sendspin**, Music Assistant's streaming protocol. Music Assistant (MA) plays to the display by opening a Sendspin session.

Requirements:

1. **One active source at a time.** If Spotify is playing and someone starts AirPlay, AirPlay takes over and Spotify stops. Last to start playing wins.
2. **The display shows the current state** (track, artist, art, position, source) and **controls it** (play/pause, next/previous, seek where possible, volume).
3. **The display can start playback** (browse and search MA, pick something). This goes through the MA API and arrives as an ordinary Sendspin session, so it needs no special path in the arbiter.
4. **Voice and timers duck the music** exactly as spec 05 §2.4 describes. They are not sources.

Non-goals: local library playback, a Bluetooth source, multi-room grouping controls beyond what Sendspin gives for free, a queue editor for non-MA sources.

## 2. Architecture

```
 shairport-sync (AirPlay 2) ─┐  pcm pipe + metadata pipe
 go-librespot (Spotify)     ─┤  pcm pipe + local API/WebSocket
 Sendspin client (in-proc)  ─┘  pcm + controller/metadata roles
            │ events / control                    │ PCM
            ▼                                     ▼
   ┌──────────────────┐                ┌────────────────────┐
   │ SourceAdapters   │                │ audio worker       │
   │ (core, no Qt)    │                │  media bus ◄─ one  │
   └────────┬─────────┘                │  voice bus   feed  │
            ▼                          │  mixer, ducking    │
   ┌──────────────────┐   select feed  └────────────────────┘
   │ MediaCoordinator │───────────────────────▲
   │ (arbiter, state) │
   └───┬──────────┬───┘
       │ state    │ MusicLibrary (MA API: browse, search, play_media)
       ▼          ▼
   MediaModel   LibraryModel  ──► QML
```

Placement, following spec 03's rule that `core/` never imports Qt:

```
core/media/
  state.py          MediaState, Track, Capabilities
  coordinator.py    MediaCoordinator (the arbiter)
  sources/
    base.py         SourceAdapter, SourceEvent types
    airplay.py      shairport-sync adapter
    spotify.py      go-librespot adapter
    sendspin.py     Sendspin client adapter
  library.py        MusicLibrary (MA API), not a source
bridge/media_model.py   MediaModel, LibraryModel, Commands.media_*
qml/NowPlaying*.qml     mini pill, full view, source picker
deploy/                 systemd units for shairport-sync, nqptp, go-librespot
```

### 2.1 Audio path (reconciling with spec 05)

Spec 05 puts audio in its own process with **our own mixer, not PipeWire or mpv**, because exact ducking and a clean **echo reference for software AEC** both need the mixer to see every sample played. Music must therefore pass through that mixer:

- Each external daemon is configured to write raw PCM to a **pipe** (shairport-sync `pipe` backend, go-librespot pipe backend) rather than to an ALSA device. The Sendspin client is in-process and hands PCM over directly.
- The audio worker exposes a **media bus** and reads from exactly one feed at a time. `MediaCoordinator` tells it which feed is live (`select_feed(source | None)`); the other feeds are drained and discarded so their daemons never block on a full pipe.
- The media bus is one of the two buses spec 05 mixes. Ducking (20 dB instant, 1 s restore) is applied there. The same output is the AEC reference.
- Device master volume is **one number owned by havenOS**. Volume changes arriving from a sender (AirPlay, Spotify) map onto it; there are no per-source levels.

### 2.2 Why a pipe feed and not PipeWire

PipeWire would make source switching trivial, but it puts the speaker output outside our mixer and breaks the echo-reference and ducking guarantees. This is a deliberate trade: we accept pipe plumbing and drain logic to keep one audio owner. If the Pi gates (§8) show the pipe path cannot hold AirPlay 2 / Sendspin sync, revisit this first.

## 3. Source adapters

All adapters implement one async contract; the rest of the system never knows which protocol is behind it.

```python
class SourceAdapter(Protocol):
    id: str                    # "airplay" | "spotify" | "sendspin"
    capabilities: Capabilities # which controls this source supports right now
    async def start(self) -> None: ...        # connect to daemon / open listener
    async def stop(self) -> None: ...
    async def command(self, cmd: MediaCommand) -> None: ...  # play, pause, next, prev, seek, set_volume
    async def release(self) -> None: ...      # evict: stop contributing audio (see §4.3)
    events: AsyncIterator[SourceEvent]
```

Events (adapter → coordinator): `Availability(bool)`, `SessionStarted(client_name)`, `SessionEnded`, `Playback(playing|paused|buffering)`, `Metadata(title, artist, album, art_uri, duration)`, `Position(seconds, at)`, `Volume(level, muted)`, `Capabilities(...)`.

| Source | Backend | State and art in | Control out | Notes |
|---|---|---|---|---|
| `airplay` | `shairport-sync` built with AirPlay 2, plus `nqptp` | metadata pipe (or MPRIS): title, artist, album, cover art, progress | DACP back to the sender: play/pause, next, previous, volume | Seek is usually unavailable; the UI greys it out. |
| `spotify` | `go-librespot` | its local HTTP/WebSocket API | same API: play/pause, next, previous, seek, volume | Needs Spotify Premium. `librespot` with `--onevent` hooks is the fallback and gives events only. |
| `sendspin` | Python Sendspin client library, in-process | metadata and artwork roles | controller role: play, pause, next, previous, volume, probably shuffle and repeat | Verify the exact command set against the protocol spec before building. |

An adapter whose daemon is down reports `Availability(False)`. It never crashes the process, and the coordinator simply never selects it. Daemons run as their own systemd units, supervised separately from `havenos.service`.

## 4. MediaCoordinator (the arbiter)

### 4.1 State

```python
MediaState:
    active_source: str | None          # "airplay" | "spotify" | "sendspin" | None
    status: idle | playing | paused | buffering
    track: Track | None                # title, artist, album, art_uri, duration
    position: float                    # seconds at position_at
    position_at: float                 # monotonic timestamp; UI extrapolates locally
    volume: float; muted: bool
    capabilities: set[str]             # of the active source
    sources: dict[str, SourceInfo]     # available, last_client, last_status
```

The UI never polls: it extrapolates `position` from `position_at` while `status == playing` and only redraws on real events. Only the active source's metadata ever reaches `MediaState`; inactive sources keep their last state privately.

### 4.2 Takeover rules

1. **Trigger on transition to `playing`**, not on connect, not on metadata, not on volume. Opening the Spotify app or a stale event from a sender must not steal the speaker.
2. If the source that just started playing is not `active_source`: set `active = new`, **then** `await old.release()`, then `select_feed(new)`. The order matters: the new source is never silent waiting on the old one to finish dying.
3. **Ignore the evicted source's events** until it reports `paused`/`ended` or reconnects with a fresh session. Without this, a late "playing" echo from the old source flips control back and forth.
4. Sources that are **not** active are inert. Their pause/resume does not touch `MediaState`.
5. **Pause does not release the slot.** A paused active source stays active and resumable from the display. If idle (nothing playing) for `media_idle_timeout` (default 10 min), `active_source` clears and the display returns to ambient.
6. A source that ends (`SessionEnded`) clears `active_source` when it was active. The previous source is **not** resumed automatically.
7. Two sources reporting `playing` within a small window (default 300 ms): the later event wins; ties go to the one with the newer session.

### 4.3 Eviction (`release`)

`release()` must make the source stop contributing audio and leave the sender in a sane state.

| Source | `release()` |
|---|---|
| `spotify` | pause via API; if the session lingers, disconnect it |
| `airplay` | DACP pause; if it does not take, drop the session. Either way the feed is already deselected, so no audio leaks. |
| `sendspin` | **Leave the group / stop our stream. Do not issue a group-wide pause**, which would stop other rooms that are in the same MA group. If the protocol cannot leave cleanly, fall back to deselecting the feed (our room goes silent, the group keeps playing). Verify against the protocol. |

Deselecting the feed in the audio worker is always done first and is the safety net: even if a sender ignores `release()`, you hear only the active source.

### 4.4 Commands

`MediaCommand` goes UI → `Commands.media_*` → `Core.handle(...)` → coordinator → `active.command(...)`. Commands are rejected (and the control disabled in the UI) when the active source's `capabilities` lack them. Volume is the exception: it is handled by the coordinator against the master level, not forwarded as a per-source command (senders are told the new level so their sliders stay in step).

### 4.5 Voice and timers

Voice assistant, announcements and ringing timers are not sources and never trigger takeover. They call the audio worker's ducking directly (spec 05). The coordinator is informed of the pause that spec 05 §2.2 asks for ("pause media instead of starting the assistant") and issues `command(pause)` to the active source, so the sender's UI shows the right state.

## 5. MusicLibrary (Music Assistant API)

Sendspin alone is enough to **show and control** what is playing. It is not a library API: it cannot browse, search or start something from idle. That is the only reason to integrate with MA directly, and it is why MA is not a fourth source.

- `MusicLibrary` is a core service (pure Python, MA WebSocket API client) exposing `search`, `browse` (playlists, albums, artists, recently played, radio), and `play(item, mode)`.
- `play(...)` calls MA's play-media against **this display's own Sendspin player id**. MA then opens a Sendspin session; our `sendspin` adapter reports `playing`; the arbiter takes over like any other source. There is no "self-initiated" branch.
- When `sendspin` is the active source, richer transport (queue, shuffle, repeat, seek) can be sent to MA's API for this player instead of the protocol's controller role, if the protocol subset proves too small. Decide when prototyping; the adapter interface does not change.
- The library UI is a second phase (milestone M7.3). The first useful version needs no MA API at all.
- Config: MA URL and token, and the display's player id (discovered from the Sendspin session, shown in the settings page).

### 5.1 Home Assistant `media_player`

The display appears in HA as a `media_player` entity over the ESPHome server from spec 04, the same seam spec 05 uses for its media-player commands. `MediaCoordinator` is its backend; the entity adds no state of its own.

- **State out:** `MediaState` maps to the entity: `idle`/`playing`/`paused`, title, artist, album, duration, position, volume, mute. Cover art is served to HA from the core's art cache. Source name and client are exposed as attributes (for example `source: airplay`).
- **Commands in:** play, pause, stop, next, previous, volume set/mute, and seek where the active source supports it. They go through the same `Core.handle(MediaCommand)` path as touches, so they obey the same capability checks.
- **Play from HA** (`play_media`, TTS and announcement URLs): announcements and TTS belong to the voice bus and duck the music (spec 05). Anything else is not a source here: if it names a Music Assistant item it goes to `MusicLibrary.play(...)`; other URLs play as the **Home Assistant** source (`core/media/sources/url.py`): ffmpeg decodes the URL to the same interim sound-device sink, it takes the speaker like any source, supports play and pause, and tells the user when a URL cannot be played. Tested with real ffmpeg and a fake sink, not on a real device or Home Assistant.
- **Stop** from HA stops the active source and clears `active_source`. It is the one external command that releases the slot.
- Treat HA commands as a normal controller: they never trigger a takeover, because only a source starting to play does (rule 4.2.1).
- Milestone: M7.5, after M7.2. It needs only the coordinator and the ESPHome media-player entity; it does not wait on the library.

## 6. UI

- **Mini pill** over the slideshow and dashboard while a source is active: art thumbnail, title, play/pause. Hidden when idle.
- **Full now-playing view** (tap the pill): large art, title/artist/album, scrubber (disabled without seek), previous/play-pause/next, master volume, and a **source badge** with client name ("Nick's iPhone · AirPlay"). Background is the blurred art, reusing the photo blur pipeline in the process pool.
- **Takeover moment**: short toast naming the new source and client. (A crossfade was dropped from scope.)
- **Idle hint** (optional, off by default): small "ready to cast" indicator listing available sources.
- **Library** (M7.3): search field, rows for playlists/recents, tap to play on this display.
- Art is fetched and cached by the core (never by QML), resized in the worker pool, and served to QML as a file URL or image provider, in keeping with the photo path.

## 7. Milestones

1. **M7.0, coordinator + fakes.** `state.py`, `coordinator.py`, a `FakeSource`, and tests for every rule in §4.2 and §4.3 (takeover, echo from evicted source, pause keeps the slot, tie-break, idle timeout). No audio, no Qt. This is where the bugs live, so it comes first.
2. **M7.1, bridge + UI on fakes.** `MediaModel`, mini pill, full view, a dev panel in the demo build to fire fake source events.
3. **M7.2, real sources, one at a time**, in this order: `sendspin` (in-process, no daemon), `spotify` (go-librespot), `airplay` (shairport-sync AirPlay 2 + nqptp). After each, run the pairwise takeover matrix against it.
4. **M7.3, MusicLibrary** and the library UI.
5. **M7.4, audio worker integration**: pipe feeds into the media bus, `select_feed`, ducking with real music, the master-volume mapping.

6. **M7.5, HA `media_player`** (section 5.1).

**Built so far:** everything in sections 2 to 6 except what is listed as not built below.
- M7.0/M7.1: coordinator (`core/media/coordinator.py`, the rules of 4.2 and 4.3 under test), fake source, `MediaModel` as `App.music`, strip, dashboard card, full now-playing view.
- M7.2: all three sources, `sendspin` (tested against a real in-process server), `spotify` (fake go-librespot; see the risk below) and `airplay` (shairport-sync as a child process, metadata pipe and DACP; verified end to end with a phone on macOS using classic AirPlay, and on a real Home Assistant setup; Sendspin is also verified on a real setup).
- M7.3: `MusicLibrary` (`core/media/library.py`) over Music Assistant's WebSocket API (`/ws`, `auth` command with a long-lived token, `music/search`, `music/recently_played_items`, `music/{playlists,albums}/library_items`, `players/all`, `player_queues/play_media`, checked against the server source) and the library screen (search box, browse sections, tap to play). Tested against a fake MA server; **not yet tried against a real Music Assistant**. Finding the display's own player: configured id, else the MA player carrying our Sendspin name, else our Sendspin client id.
- Art: `core/media/art.py` fetches, resizes (512 px JPEG) and caches covers; QML only ever sees a `file://` URI.
- Takeover toast ("Now playing from AirPlay · Nick's iPhone"), the opt-in idle "ready to cast" hint, and a warning in the log when senders fight (4+ takeovers in a minute).
- M7.4: every source writes to its own stream on the media bus of the shared mixer (`core/audio/`: `Mixer`, `AudioHub`, `BusSink`, `Resampler`), one sound output, no per-source devices. Ducking is the mixer's (default -20 dB, instant drop, 1 s restore; `music.duck_db`), driven by ringing timers, announcements and the assistant. Sources at 44.1 kHz are resampled (cubic) to the output rate; the output rate is the voice profile's (48 kHz, or 16 kHz for the Lite). The master volume is the VPE's 0.4-0.85 clamp, so full volume is 0.85 of full scale, and a source's own 0-100 slider is a per-stream gain. Tested with fake devices; not run on a Pi. The mixer runs in-process, not in the separate audio worker of spec 05.
- M7.5: the display is a `media_player` over the ESPHome server (play, pause, stop, volume set, mute). Deviations from 5.1: the ESPHome media_player carries only state, volume and mute, so title, artist, album and source are sensors beside it and next/previous are buttons; cover art cannot go to HA over ESPHome; announcement URLs go to the voice satellite when voice is on and are otherwise ignored; `play_media` URLs play as the Home Assistant source (see section 5).
- Settings page: a Music card (sources on/off and names, Music Assistant URL/token with a connection test, idle timeout, duck level, hint). Turning a source on or off needs a restart.
- `deploy/`: systemd units, daemon configs and an install script for the Pi. Run on one Pi 4 (2026-11-02): units start, AirPlay 2 builds and advertises; **no sound heard and no sender tried yet**, Spotify not installed.

**Built since:** library voice search. The mic button in the search bar records one phrase (the voice satellite's capture, after its chime), posts it to Home Assistant's speech-to-text (`POST /api/stt/<entity>`, `[voice] stt_entity` or the first `stt.*`) and searches for the words. It does not use the Assist pipeline, so nothing said is run as a command. Tested with fakes and a fake Home Assistant; **not tried on a real speech-to-text provider or real audio**, and whether providers want raw PCM or a WAV header with that endpoint is unconfirmed.

**Not built:** the mixer in its own process, multi-room clock sync or latency calibration, and all Pi gates in section 8. **Dropped from scope:** crossfade on takeover, and an on-screen keyboard for library search.

**Spotify risk (confirmed on real hardware):** Spotify refuses audio keys to librespot-family clients on some accounts (go-librespot #279/#317, Premium accounts included; zeroconf and OAuth both affected; the fix would need PlayPlay, which the maintainer will not implement). On the author's account both go-librespot and Music Assistant's Spotify provider fail on every track. Section 8 should list this as a risk of the `spotify` source: it may not work for a given user, and Spotify must also be reachable through AirPlay (and Music Assistant) as a fallback.

**Spotify findings:** go-librespot's pipe backend is not paced, so we read the FIFO only while the sink is short of audio (the pipe backs up and go-librespot blocks), which also keeps pause prompt; its volume is in steps (`volume_steps`), mapped to the 0-100 master; `external_volume: true` leaves volume to havenOS. The coordinator now pushes the master volume to whichever source takes over, and `select_feed` is implemented (each adapter's `set_feed`), so an evicted source's audio is dropped.

**Sendspin findings (from building it):**
- The client library is `aiosendspin.client.SendspinClient` (the `sendspin` package is the CLI built on it). Our adapter follows the reference `sendspin daemon`: a `ClientListener` advertises over mDNS and the server dials us.
- `send_leave()` exists, so section 4.3 holds: eviction leaves the group (a real server then shows the group stopped for us) instead of pausing it.
- **Roles activate only after pairing/trust.** An unpaired connection is admitted but receives no metadata or controller state until the server pairs with us (pairing code, shown on our display through `Pairing` events) or trusts us. Section 8 should list pairing UX as a real step in M7.2, not a detail.
- The controller role only lists commands the server application supports; we mirror that as capabilities, so seek is greyed out unless the server offers it.
- Without an audio sink we declare only metadata + controller; declaring the player role without somewhere to send audio would make the group think this room is playing.

M7.2 and M7.4 can overlap; M7.0 and M7.1 need no hardware.

## 8. Risks and open questions

| Risk | Mitigation |
|---|---|
| **AirPlay 2 / Sendspin sync through a pipe.** Multi-room sync needs accurate output timing; a pipe plus our mixer adds buffering the daemons do not see. | Pi gate below. Each backend takes an output-latency offset; calibrate once. Fallback: let the daemon write to a loopback device that the worker captures with a known latency. |
| `shairport-sync` AirPlay 2 builds are fiddlier than AirPlay 1 (nqptp, newer libs, per-OS quirks). | Treat as a `deploy/` step with an `install.sh` check; verify on the Pi in M7.2 before UI polish. Fall back to AirPlay 1 if blocked, accepting no multi-room sync. |
| Sendspin protocol details (controller command set, leaving a group) are assumed from the protocol's role model. | Read the current protocol spec at the start of M7.2; adjust §3 and §4.3 and note differences here. |
| `go-librespot` API stability; Spotify Premium requirement; Spotify may change Connect behavior. | Pin versions; keep the adapter thin so `librespot` + hooks remains a drop-in with fewer features. |
| Sender "ping-pong": two phones fighting over the speaker. | Rules 4.2.3 and 4.2.7. Takeovers are never blocked (decided), so log a warning when there are more than N in a minute to make fights visible. |
| Pipe backpressure blocks a daemon whose feed is deselected. | The worker always drains unselected feeds. A soak test runs with feeds switching every few seconds. |
| Extra daemons increase RAM on the Pi. | Counts toward G1 below; daemons are idle when nothing is casting. |
| Voice wake word is weakest during playback (spec 05 §6). | Unchanged by this spec; the mixer keeps the media bus as AEC reference. |

Decided:
1. **The display exposes itself to Home Assistant as a `media_player`** (section 5.1).
2. **No resume after takeover.** A takeover kicks out and stops the old source for good; when the new source ends, nothing resumes (rule 4.2.6).
3. **Blocking a takeover** ("do not disturb", "locked to MA") is out of scope.

### Pi gates

- M1: idle RSS stays under the spec 03 G1 budget with all three daemons running and nothing casting; no growth over 12 h of casting and switching.
- M2: switching source every ~5 s for an hour leaves no stuck feed, no leaked audio from the old source and no unbounded memory growth.
- M3: AirPlay 2 and Sendspin playback stay in sync with another device at the same latency offset, and the offset survives a daemon restart.
- M4: a takeover is audible as a clean switch in under 1 s from the new source's first sound.
