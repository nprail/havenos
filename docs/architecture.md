# Architecture

havenOS is one process with one event loop. A pure-Python core holds all state and logic. A Qt Quick (QML) interface only draws it and reports touches. The two share an `asyncio` loop through `qasync`. The full design and its reasoning are in [spec 03](specs/03-qt-python-single.md).

```
 touch / keys            ┌───────────────┐  commands   ┌──────────────────────────┐
 ───────────────────────▶│  QML (view)   │────────────▶│  bridge/app_model.py     │
                         │  Store.qml    │◀────────────│  QObject mirror of state │
                         └───────────────┘  properties └───────────┬──────────────┘
                                                                   │ Core.handle(...)
                                                                   │ EventBus events
                         ┌─────────────────────────────────────────▼──────────────┐
                         │ core/  (pure Python, no Qt imports)                     │
                         │  core.py  state, commands, scheduling                   │
                         │  ha.py  immich.py  photos.py  playlist.py  timers.py    │
                         │  media/ (music)   esphome/ (HA device)   web.py         │
                         └─────────────────────────────────────────────────────────┘
```

## The layers

**`core/`** is pure Python and never imports Qt. `tests/test_import_boundary.py` fails if it does. This keeps the logic testable with a fake clock and without a display, and lets the Home Assistant and ESPHome libraries run unchanged.

**`bridge/app_model.py`** is the only place Qt and the core meet. `AppModel` is a `QObject` that mirrors core state as properties and forwards QML calls to `Core.handle`.

**`qml/`** is view only. `Store.qml` is a read-only facade over the bridge plus view-only state such as which sheet is open. Photo cycling, the idle timeout, timer expiry and the music state all live in the core; QML renders them and reports touches with `Store.activity()`.

**`main.py`** wires it together: config, the process pool for photo decoding, the core, the bridge, the settings web UI, the ESPHome device and the QML engine.

## State and events

`Core.state` is a plain dict (plain dicts and dataclasses are used throughout, not pydantic). Changes go out on the `EventBus` as:

| Event | Meaning |
|---|---|
| `state.snapshot` | The whole state (sent at start and on request) |
| `state.patch` | The keys that changed |
| `stats` | Memory, event-loop lag and other diagnostics |
| `error` | Something failed, with a code and a message |

The bus is synchronous fan-out. Handlers must be quick and must not block. The shared logical contract is in [spec 00](specs/00-common.md).

## Commands

Every action, whether from a touch, a key, the web UI or Home Assistant, goes through one entry point:

```python
core.handle("photo.next", delta=1)
```

`handle` turns the dotted name into a method, so `photo.next` runs `Core._cmd_photo_next`. An unknown command emits an `error` event. Because Home Assistant commands, the settings page and the touch UI all call the same `handle`, there is one code path per action. Touches that act on Home Assistant entities pass through an allowlist in `core/actions.py`.

## Where things live

| Path | What |
|---|---|
| `core/core.py` | State, commands, tick loop (photo cycle, idle, timer expiry, ring auto-dismiss) |
| `core/config.py`, `settings.py`, `persist.py` | Config loading, validate and write, saving settings changed from Home Assistant |
| `core/ha.py`, `home.py`, `exposure.py`, `actions.py` | Home Assistant WebSocket client, entity state, the exposure filter, the action allowlist |
| `core/immich.py`, `photos.py`, `playlist.py` | Photo sources, Pillow processing, history, prefetch and cache eviction |
| `core/timers.py`, `voice.py` | Timers; `voice/` holds the real [voice pipeline](specs/05-voice-pipeline.md) (satellite, mixer, wake engine; not yet run on real hardware) and `voice/fake.py`, the scripted demo used when voice is off |
| `core/media/` | The music coordinator, the source adapters, the Music Assistant library, art cache |
| `core/esphome/` | The ESPHome native API server, entities and mDNS announcement |
| `core/web.py`, `web/` | Settings web UI (aiohttp API and a static page) |
| `core/stats.py`, `blocking.py` | Memory and loop-lag stats; hopping blocking work to an executor |
| `devtools.py` | Headless screenshot script |

## Threads and processes

- One thread runs both Qt and asyncio. The HUD shows **loop lag**: how late a 50 ms sleep wakes up. That is the direct measure of GUI-thread stalls.
- Photo decoding and resizing run in a `ProcessPoolExecutor` of two workers, so the GIL never touches the GUI thread. If a worker dies, `run_blocking` falls back to threads rather than failing every later photo.
- AirPlay and Spotify run as child processes (`shairport-sync`, `go-librespot`) unless `manage = false`. Sendspin runs in-process.

## Music

`core/media/coordinator.py` keeps **one active source at a time; the last to start playing wins**. Each source implements the small `SourceAdapter` contract in `core/media/sources/base.py` and pushes events up (availability, session started or ended, playback status, metadata, position, capabilities, volume, pairing code, notices). The coordinator calls `command`, `release` and `set_volume` back down. Adapters never decide who is active. See [Music](music/index.md).

## Two traps worth knowing

- **Use `qasync`, not `PySide6.QtAsyncio`.** QtAsyncio's loop has no network I/O, so an aiohttp server or client hangs on first use. `qasync` runs aiohttp, WebSockets and process pools directly.
- **`None` reaches QML as `undefined`, not `null`.** The facade normalises it.

More in [Troubleshooting](troubleshooting.md) and [Decisions](decisions.md).
