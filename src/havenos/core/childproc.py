"""Keep helper processes (shairport-sync, go-librespot) from outliving the app.

A normal quit already stops them. This covers the rest:

  - SIGTERM and SIGINT ask the app to quit the normal way (the Qt loop sees them through a signal handler); a second one
    kills the registered children and exits at once, in case the quit is stuck.
  - Anything that makes Python exit still runs `kill_all` (atexit).
  - On Linux a child also asks the kernel to SIGTERM it if its parent dies for any reason, even SIGKILL (the Pi's case).

No Qt here; `main.py` supplies the "quit" callback.
"""
from __future__ import annotations

import atexit
import logging
import os
import shutil
import signal
import sys
from typing import Any, Callable

log = logging.getLogger(__name__)

_children: dict[int, Any] = {}
_signalled = False


def register(proc: Any) -> Any:
    """Track an asyncio or subprocess child so `kill_all` can reach it. Returns it for chaining."""
    if getattr(proc, "pid", None):
        _children[proc.pid] = proc
    return proc


def unregister(proc: Any) -> None:
    _children.pop(getattr(proc, "pid", None), None)


def tracked() -> list[int]:
    return [pid for pid, p in _children.items() if p.returncode is None]


def kill_all() -> None:
    """Stop every tracked child now: SIGTERM, then SIGKILL for any still alive a moment later. Safe to call twice."""
    pids = tracked()
    for pid in pids:
        _signal(pid, signal.SIGTERM)
    if pids:
        import time
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline and any(_alive(pid) for pid in pids):
            time.sleep(0.02)
        for pid in pids:
            if _alive(pid):
                _signal(pid, signal.SIGKILL)
    _children.clear()


def _signal(pid: int, sig: int) -> None:
    try:
        os.kill(pid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    try:                                    # a child that has exited but not been reaped still answers kill(0)
        done, _ = os.waitpid(pid, os.WNOHANG)
        return done == 0
    except ChildProcessError:
        return True


def die_with_parent() -> list[str]:
    """A command prefix that has the kernel SIGTERM the child if this process dies, even by SIGKILL. Linux's `setpriv`
    does it and then execs the program, so the pid stays the same. Empty elsewhere (and where `setpriv` is missing),
    leaving the signal handlers and `kill_all` as the cover. (A `preexec_fn` would do the same but is unsafe in a
    process with threads, which Qt has.)"""
    if sys.platform.startswith("linux") and shutil.which("setpriv"):
        return ["setpriv", "--pdeathsig", "SIGTERM", "--"]
    return []


def install(quit_app: Callable[[], None]) -> None:
    """On SIGTERM or SIGINT call `quit_app` (once); on the next one kill the children and leave immediately."""
    global _signalled
    _signalled = False
    atexit.register(kill_all)

    def handler(signum: int, _frame: Any) -> None:
        global _signalled
        if _signalled:
            log.warning("second %s: killing helper processes and exiting now", signal.Signals(signum).name)
            kill_all()
            os._exit(128 + signum)
        _signalled = True
        log.info("%s received: quitting", signal.Signals(signum).name)
        quit_app()

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, handler)
