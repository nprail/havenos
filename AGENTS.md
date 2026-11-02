# Notes for agents working on havenOS

The project root is the app (pure-Python `core/` with no Qt imports, Qt Quick QML UI, one process, qasync). Specs are in `docs/specs/`; `docs/decisions.md` explains why. Launchers and dev tools are in `scripts/`, Pi units in `deploy/`.

## Keep `TODO.md` up to date

`TODO.md` at the repo root is the single list of what is left. Treat it as part of the work, not an afterthought:

- When you finish or start something that is already on the list, update `TODO.md` in the same turn: tick the item, or move it to "Done" with the date and one line on what changed.
- **Never add a new item to `TODO.md` unless the user has explicitly said you may.** If you find something that belongs on the list (a bug, a gap, a follow-up, an unverified piece), suggest it in your reply instead, with the section it would go in, and wait for a yes. One approval covers that item only.
- When the user drops something from scope or decides an open question, record it under "Out of scope" or in the relevant item, and update the matching spec.
- Do not mark something done that was only tested against fakes if the item says "verify against the real thing". Say what was and was not verified.
- Keep the "Last updated" date current. Keep entries to one or two lines.
- If a spec's "Built" and "Not built" lists change, update them too, and keep `TODO.md` consistent with them.

## Working conventions

- Run the tests with the project venv (`.venv/bin/python -m pytest`) before saying something works.
- `core/` must not import Qt (`tests/test_import_boundary.py` enforces it).
- Quit the app with `q`, Ctrl-C or SIGTERM when restarting it: all stop the helper daemons. `kill -9` leaves the AirPlay child process (`shairport-sync`) holding port 7100.
- Say plainly what is unverified (a real Music Assistant library, voice on a microphone, Spotify, the Pi performance gates).
