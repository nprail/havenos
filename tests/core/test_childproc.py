"""Signals and helper processes, with real processes: a small program stands in for the app."""
import os
import signal
import subprocess
import sys
import textwrap
import time

import pytest

from havenos.core import childproc

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")

PRELUDE = """
import asyncio, os, sys
sys.path.insert(0, {src!r})
from havenos.core import childproc
"""


def run_app(body: str, tmp_path):
    src = os.path.join(os.path.dirname(__file__), "..", "..", "src")
    script = tmp_path / "app.py"
    script.write_text(PRELUDE.format(src=os.path.abspath(src)) + textwrap.dedent(body))
    p = subprocess.Popen([sys.executable, "-I", str(script)], stdout=subprocess.PIPE, text=True)
    child = int(p.stdout.readline())                       # the helper's pid, printed once everything is set up
    return p, child


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def gone(pid: int, timeout: float = 5.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if not alive(pid):
            return True
        time.sleep(0.05)
    return False


APP = """
async def main():
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    proc = childproc.register(await asyncio.create_subprocess_exec("sleep", "60"))
    childproc.install(lambda: loop.call_soon_threadsafe(stop.set) if {graceful} else None)
    print(proc.pid, flush=True)
    await stop.wait()
    proc.terminate(); await proc.wait()                      # what the real sources do on a normal quit
asyncio.run(main())
"""


def test_sigterm_quits_normally_and_the_helper_goes_with_it(tmp_path):
    p, child = run_app(APP.format(graceful=True), tmp_path)
    assert alive(child)
    p.send_signal(signal.SIGTERM)
    assert p.wait(10) == 0
    assert gone(child)


def test_sigint_does_the_same(tmp_path):
    p, child = run_app(APP.format(graceful=True), tmp_path)
    p.send_signal(signal.SIGINT)
    assert p.wait(10) == 0 and gone(child)


def test_a_stuck_quit_is_overridden_by_a_second_signal(tmp_path):
    p, child = run_app(APP.format(graceful=False), tmp_path)      # the quit callback does nothing: the app hangs
    p.send_signal(signal.SIGTERM)
    time.sleep(0.5)
    assert p.poll() is None and alive(child)                      # first signal: asked to quit, still stuck
    p.send_signal(signal.SIGTERM)
    assert p.wait(10) == 128 + signal.SIGTERM
    assert gone(child)


def test_a_helper_does_not_outlive_a_python_exit_that_skipped_cleanup(tmp_path):
    p, child = run_app("""
async def main():
    proc = childproc.register(await asyncio.create_subprocess_exec("sleep", "60"))
    childproc.install(lambda: None)
    print(proc.pid, flush=True)
asyncio.run(main())                                           # returns without stopping the helper
""", tmp_path)
    assert p.wait(10) == 0
    assert gone(child)


def test_kill_all_reaches_stubborn_children():
    p = subprocess.Popen([sys.executable, "-c", "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)"])
    time.sleep(0.3)
    childproc.register(p)
    assert p.pid in childproc.tracked()
    childproc.kill_all()
    assert p.wait(5) == -signal.SIGKILL
    assert childproc.tracked() == []


def test_unregister_forgets_a_finished_child():
    p = subprocess.Popen(["sleep", "0"])
    childproc.register(p)
    p.wait()
    childproc.unregister(p)
    assert p.pid not in childproc._children


def test_the_parent_death_prefix_is_linux_only():
    prefix = childproc.die_with_parent()
    if sys.platform.startswith("linux"):
        assert prefix == [] or prefix[:2] == ["setpriv", "--pdeathsig"]
    else:
        assert prefix == []
