# Contributing

## Set up

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest
```

Run the tests before you say something works.

## Ground rules

- **`core/` never imports Qt.** `tests/test_import_boundary.py` enforces it. Qt lives in `bridge/` and `qml/`.
- **One command path.** Every action goes through `Core.handle("name.sub", ...)`, which runs `Core._cmd_name_sub`. Touch, web UI and Home Assistant all use it. See [Architecture](architecture.md).
- **QML is view only.** Logic that decides what happens next belongs in the core.
- **Use `qasync`**, not `PySide6.QtAsyncio`.
- **Say what is unverified.** A real Music Assistant library, voice on a microphone, Spotify, and the Pi performance gates are untested unless stated.

## Tests

Tests live in `tests/` and `tests/core/`. They use:

- a fake clock (`FakeClock` in `tests/conftest.py`) and an `instant_sleep` helper, so timing tests are fast,
- in-process fake Home Assistant, Immich and Music Assistant servers (`tests/fakes.py`),
- a real in-process Sendspin server for the Sendspin adapter,
- a real aioesphomeapi client for the ESPHome device.

`pytest-asyncio` is in auto mode, so `async def test_...` just works. A headless Qt check can be run with `QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software`; remember that this backend does not render blur.

## Adding things

**A command.** Add `_cmd_<name>` to `Core`; the dotted name `photo.next` maps to `_cmd_photo_next`. If the UI needs it, add a slot on `AppModel` and call it from `Store.qml`.

**A music source.** Subclass `SourceAdapter` in `core/media/sources/base.py`, push events (`Availability`, `SessionStarted`, `Playback`, `Metadata`, and so on) to the sink, and implement `command`, `release` and `set_volume`. Register it in `Core._register_music_sources`. Adapters report what their protocol says; the coordinator decides who is active.

**A config key.** Add it to `Config` and to `from_env` in `core/config.py`, to `config.example.toml`, to the [configuration reference](configuration.md), and to the web UI if users should set it there.

**An ESPHome entity.** Add it declaratively in `core/esphome/device.py`. Keys come from hashes of object ids, so a stable id keeps Home Assistant from creating duplicates.

## The TODO list

`TODO.md` at the project root is the single list of what is left. If you work on something that is on it, update it in the same change: tick the item or move it to Done with the date and a line on what changed. **Do not add new items without the maintainer's agreement.** Suggest them in your pull request or message instead. If a spec's Built and Not built lists change, update them too.

`AGENTS.md` contains the same rules for AI agents working in the repository.

## Specs

The designs are in [`docs/specs/`](specs/00-common.md). When you decide an open question or drop something from scope, record it in the matching spec and in `TODO.md`.

## Docs site

The docs in `docs/` are built with docmd (`npm install && npm run docs:dev` to preview, `npx docmd validate` to check links). The GitHub Actions workflow `.github/workflows/docs.yml` builds them and publishes to GitHub Pages on every push to `main` that touches the docs. One-time setup: repository **Settings, Pages, Source: GitHub Actions**.

## Licence

havenOS is MIT licensed (see `LICENSE`), and contributions are accepted under the same licence. Qt is LGPLv3 and is used as a separately installed library, never bundled or modified; do not use its GPL-only modules (the VirtualKeyboard). New dependencies and assets need a licence that is compatible with MIT redistribution, and assets need an attribution file next to them like the others. The voice sounds are CC BY and are credited in `src/havenos/assets/sounds/ATTRIBUTION.md`; keep that file in step if you add or change a sound.
