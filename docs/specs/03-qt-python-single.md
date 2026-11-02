# Spec 03: Qt + Python, single application

> **Chosen.** Implemented at the project root; findings and later specs (`04`, `05`) are recorded alongside.

Builds on [00-common](00-common.md). One Python process hosts both the core logic and the Qt Quick UI. The core/UI contract exists as an in-process interface, not a socket.

## 1. Architecture

```
 Raspberry Pi 4
 ┌─────────────────────────────────────────────┐       ┌───────────────┐
 │ havenos (single Python process)             │◄─WS──►│ Home Assistant│
 │                                             │       └───────────────┘
 │  core/   (pure Python, no Qt imports)       │
 │    state · ha · photos · timers · voice     │
 │        ▲ events / commands (same contract)  │
 │  bridge/ (Qt glue: QObjects, models)        │
 │        ▲                                    │
 │  qml/    (view only)  → Qt Quick on EGLFS   │
 └─────────────────────────────────────────────┘
```

Hard rule: `core/` must not import Qt. The bridge is the only place where Qt and core meet. This keeps the option to move the UI into its own process later (swap the bridge for a WebSocket server) without rewriting the core.

## 2. Components

### Event loop
- Use `qasync` so `asyncio` and the Qt event loop share one thread. (`PySide6.QtAsyncio` was rejected: its loop has no network I/O, so aiohttp hangs.) Core code is written as ordinary `async` functions.
- Anything blocking or CPU-heavy leaves the loop: photo decode/resize/blur in a `ProcessPoolExecutor` (not threads, to avoid GIL contention with the GUI thread); audio capture in a dedicated thread; file I/O via `run_in_executor`.
- Rendering and QML animations run on Qt's render thread, so Python load rarely affects animation, but a blocked GUI thread delays input and property updates. Rule: no call on the GUI thread may exceed 10 ms (enforced by a debug-mode slow-callback logger).

### core/ (pure Python)
Same responsibilities as 00-common §5. API shape:
- `CoreState` (pydantic model) plus `EventBus` (`subscribe(handler)`, `emit(event)`), events as in the 00-common contract.
- `Core.handle(command)` is the single entry point for commands; it returns nothing and emits events.
- Modules are independently testable with a fake clock and fake HA.

### bridge/ (Qt glue)
- `AppModel(QObject)`: Qt `Property`/`Signal` mirrors of `CoreState`; updates come from `EventBus` handlers on the GUI thread.
- `TimerModel(QAbstractListModel)`, `QuickControlsModel(QAbstractListModel)`.
- `Commands(QObject)`: slots that translate QML calls into `Core.handle(...)`.
- Thread hops go through queued signals; never touch QObjects from worker threads.

### qml/
- QML is view only: no logic beyond animation and layout.

### Packaging and run
- Single systemd unit `havenos.service` (`Restart=always`, `WatchdogSec=15`). The app calls `sd_notify("WATCHDOG=1")` from a timer on the GUI thread, so a frozen UI thread triggers a restart.
- Env: `QT_QPA_PLATFORM=eglfs QT_QPA_EGLFS_KMS_ATOMIC=1 HAVENOS_FULLSCREEN=1`.

## 3. Repo layout

```
havenos/
  pyproject.toml
  src/havenos/
    core/      state.py, events.py, ha.py, photos.py, timers.py, voice.py, config.py
    bridge/    app_model.py, models.py, commands.py
    qml/       Main.qml, components/, assets/
    main.py
  tests/       core/ (pytest, no Qt), bridge/ (pytest-qt), qml/ (QQuickTest)
  deploy/      havenos.service, udev rules, install.sh
  docs/      specs/, decisions.md
  scripts/   launchers and dev tools
```

## 4. Dev workflow

- `uv run python -m havenos` on the Mac, windowed; `HAVENOS_FAKE_HA=1` uses the fake HA.
- Core tests run without Qt, fast and on any CI runner.
- An import-lint check (e.g. `import-linter`) fails the build if `core/` imports `PySide6`.
- Event-script replay drives the bridge for UI tests.

## 5. Strengths

- Simplest deployment and lowest overhead: one process, one language, one service, no socket.
- Small RAM footprint and fast boot.
- Easiest for the HA/Python community to read and contribute to (outside the QML layer).
- Direct object access: photo paths and models shared with no serialization.

## 6. Risks and mitigations

| Risk | Mitigation |
|---|---|
| One crash or hang takes down core and UI (timers, HA connection) | systemd watchdog, fast restart, persisted timers, snapshot-style startup; keep core code defensive (all tasks with exception logging). |
| GUI thread blocked by core work | Strict rule + slow-callback detector; heavy work in process pool; load tests in CI. |
| GIL contention between audio/HA/photo threads and the GUI | Processes for photos; minimal pure-Python work per frame; measure worst-frame under load (gate G2). |
| asyncio/Qt loop integration quirks (`QtAsyncio` has no network I/O; use `qasync`) | Prototype early (M0); fallback to `qasync` or to running asyncio in a worker thread with queued signals. |
| Core becomes entangled with Qt over time | `core/` import-lint; code review rule; bridge-only Qt types. |
| No remote/companion UI | Optional later: add a `bridge_ws` module exposing the same contract over WebSocket. |
| QML skill gap | Keep QML view-only; document component library. |

## 7. Pi gates

- G1: idle RSS < 350 MB, no growth over 12 h.
- G2: <= 1 slow frame per 10 s in crossfade, dashboard slide and waveform, with HA events and photo prefetch running concurrently.
- G3: boot to first photo < 18 s.
- G4: simulate a hung GUI thread; the watchdog restarts and returns to ambient in < 15 s.

## 8. Findings from building it

- M0 spike result: `PySide6.QtAsyncio` handles sleeps, tasks and thread pools but has no network I/O (aiohttp hangs) and hangs on process-pool futures. `qasync` handles all of them (aiohttp client+server, WebSockets, `ProcessPoolExecutor`) on macOS with PySide6 6.12, so the app uses qasync. Re-verify on the Pi.
- HA (WebSocket) and Immich (REST) clients run on the same loop with no threads. Both are tested against in-process fake servers; the HA client has also run against a real Home Assistant (Immich against a real instance is not confirmed).
- The loop-lag monitor (50 ms sleep drift) is built into the HUD to measure gate G2 directly.
- Core state is dicts/dataclasses; pydantic deferred until the HA/Assist models need validation.

## 9. Milestones

1. M0: `core/` skeleton with fake HA; bridge + QML; `qasync` spike; runs on the Mac.
2. M1: EGLFS on the Pi; photo pipeline in a process pool; measure G1-G3.
3. M2: HA states and quick controls.
4. M3: Timers + takeover, persistence.
5. M4: Voice and audio.
6. M5: Hardening: watchdog, soak, install script, first-run setup.
