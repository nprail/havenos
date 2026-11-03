"""Headless verification: script the running app through core commands and save screenshots.
Visual check only: software rendering says nothing about Pi performance."""
from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QEvent, QPoint, Qt, QTimer
from PySide6.QtGui import QKeyEvent
from PySide6.QtTest import QTest

from .core import Core


def install_shots(app, win, core: Core, prefix: str) -> None:
    def shot(name: str) -> None:
        img = win.grabWindow()
        ok = img.save(f"{prefix}-{name}.png")
        print("shot", name, img.width(), img.height(), "ok" if ok else "FAILED", flush=True)

    def key(k: int) -> None:
        for kind in (QEvent.KeyPress, QEvent.KeyRelease):
            QCoreApplication.sendEvent(win, QKeyEvent(kind, k, Qt.NoModifier))

    h = core.handle
    core._set(setup_done=True)                        # the first-run pairing screen would cover every shot
    music = [                                        # demo mode only: a takeover, the library, and the full view
        (200, lambda: h("mode.set", mode="ambient")),
        (0, lambda: h("music.simulate", source="airplay", action="play")), (1200, lambda: shot("7-music-strip")),
        (0, lambda: h("music.simulate", source="spotify", action="play")), (900, lambda: shot("8-takeover-toast")),
        (0, lambda: h("mode.set", mode="dashboard")), (700, lambda: shot("9-dashboard-music")),
        (0, lambda: key(Qt.Key_L)), (1200, lambda: shot("10-library")),
        (0, lambda: h("library.search", query="signal")), (900, lambda: shot("11-library-search")),
        (0, lambda: key(Qt.Key_L)), (300, lambda: key(Qt.Key_M)), (900, lambda: shot("12-now-playing")),
    ] if core.config.music_demo else []
    live = [                                         # demo mode only: the live screen, one thing then two then three splits
        (0, lambda: key(Qt.Key_Escape)), (0, lambda: h("mode.set", mode="ambient")), (0, lambda: h("timer.cancel", id=1)),
        (0, lambda: h("music.simulate", source="airplay", action="play")), (1500, lambda: shot("13-live-music")),
        (0, lambda: h("timer.start", seconds=480, label="Pasta")), (1200, lambda: shot("14-live-music-timer")),
        (0, lambda: h("timer.start", seconds=95, label="Laundry")), (1200, lambda: shot("15-live-music-two-timers")),
        (0, lambda: h("timer.start", seconds=2400, label="Oven")), (1200, lambda: shot("16-live-music-three-timers-more")),
        (0, lambda: key(Qt.Key_U)), (900, lambda: shot("17-timers-sheet")), (0, lambda: key(Qt.Key_Escape)),
        (300, lambda: key(Qt.Key_M)), (900, lambda: shot("18-now-playing-over-live")), (0, lambda: key(Qt.Key_Escape)),
        (0, lambda: h("music.simulate", source="airplay", action="end")), (1200, lambda: shot("19-live-three-timers")),
        (0, lambda: h("timer.pause", id=3)), (900, lambda: shot("20-live-timer-paused")),
        (0, lambda: h("timer.cancel", id=3)), (0, lambda: h("timer.cancel", id=4)), (1000, lambda: shot("21-live-two-timers")),
        (0, lambda: h("timer.cancel", id=2)), (1000, lambda: shot("22-live-one-timer")),
    ] if core.config.music_demo else []
    def tap(x: int, y: int) -> None:
        QTest.mouseClick(win, Qt.LeftButton, Qt.NoModifier, QPoint(x, y))

    finger = QTest.createTouchDevice()               # real touch events: that is what the Pi's panel sends

    def swipe(x: int, y0: int, y1: int) -> None:
        seq = QTest.touchEvent(win, finger)
        seq.press(0, QPoint(x, y0), win).commit()
        for i in range(1, 9):
            seq.move(0, QPoint(x, y0 + (y1 - y0) * i // 8), win).commit()
        seq.release(0, QPoint(x, y1), win).commit()          # (each commit renders a frame, so a swipe takes about a second)

    def check(name: str, ok) -> None:
        print("check", name, "PASS" if ok() else "FAIL", "(mode: %s)" % core.state["mode"], flush=True)

    def timer(label: str) -> dict:
        return next((t for t in core.state["timers"] if t["label"] == label), {})

    touch = [                                        # demo mode, 1280x800 only: real mouse events on the live screen
        (0, lambda: key(Qt.Key_Escape)), (0, lambda: h("mode.set", mode="ambient")),
        (0, lambda: [h("timer.cancel", id=t["id"]) for t in list(core.state["timers"])]),
        (0, lambda: h("music.simulate", source="airplay", action="play")),
        (0, lambda: h("timer.start", seconds=600, label="Alpha")), (0, lambda: h("timer.start", seconds=300, label="Beta")),
        (1500, lambda: shot("23-touch-start")),
        (0, lambda: tap(728, 262)), (500, lambda: check("a timer's Pause button pauses it", lambda: timer("Beta").get("paused") is True)),
        (0, lambda: tap(728, 262)), (500, lambda: check("...and Resume resumes it", lambda: timer("Beta").get("paused") is False)),
        (0, lambda: tap(1168, 262)), (500, lambda: check("the Stop button cancels it", lambda: not timer("Beta"))),
        (0, lambda: tap(330, 250)), (900, lambda: shot("24-touch-media-controls")), (0, lambda: key(Qt.Key_Escape)),
        (400, lambda: tap(1100, 400)), (900, lambda: shot("25-touch-timers-sheet")), (0, lambda: key(Qt.Key_Escape)),
        (400, lambda: check("the live screen is still there after both control views", lambda: core.state["mode"] == "ambient")),
        (0, lambda: h("mode.set", mode="dashboard")), (700, lambda: swipe(640, 250, 650)),
        (2500, lambda: check("swiping down on the dashboard goes back to the live screen", lambda: core.state["mode"] == "ambient")),
        (0, lambda: swipe(640, 650, 250)), (2500, lambda: check("swiping up on the live screen goes to the dashboard", lambda: core.state["mode"] == "dashboard")),
        (0, lambda: h("mode.set", mode="ambient")), (1500, lambda: shot("27-before-home")), (0, lambda: tap(1190, 52)),
        (1500, lambda: check("Home goes to the dashboard", lambda: core.state["mode"] == "dashboard")),
        (0, lambda: h("mode.set", mode="ambient")),
        (0, lambda: [h("timer.cancel", id=t["id"]) for t in list(core.state["timers"])]),
        (0, lambda: h("music.simulate", source="airplay", action="end")), (1200, lambda: shot("26-touch-back-to-photos")),
        (0, lambda: check("with nothing left the photos come back", lambda: not core.state["timers"])),
    ] if core.config.music_demo and win.width() == 1280 else []
    steps = [
        (1500, lambda: shot("1-ambient")),
        (0, lambda: h("config.set", stats=True)), (1200, lambda: shot("1b-ambient-stats")),
        (0, lambda: h("config.set", stats=False)),
        (200, lambda: h("mode.set", mode="dashboard")), (900, lambda: shot("2-dashboard")),
        (0, lambda: h("control.toggle", id="light.kitchen")), (1800, lambda: shot("2b-dashboard-light-on")),
        (0, lambda: h("voice.start")), (1800, lambda: shot("3-voice")), (6500, lambda: None),
        (0, lambda: h("mode.set", mode="ambient")), (500, lambda: h("timer.start", seconds=5, label="Demo (5s)")),
        (5800, lambda: None), (500, lambda: shot("4-timer-ring")),
        (0, lambda: tap(win.width() // 2 + 60, win.height() // 2 - 40)), (400, lambda: check("tapping inside the ring stops a ringing timer", lambda: core.state["ringing"] is None)),
        (0, lambda: h("timer.dismiss")), (0, lambda: h("photo.next", delta=-1)), (1600, lambda: shot("5-portrait")),
        (0, lambda: h("config.set", blur=False)), (200, lambda: h("mode.set", mode="dashboard")),
        (800, lambda: shot("6-dashboard-blur-off")),
        *music,
        *live,
        *touch,
        (200, lambda: app.quit()),
    ]
    t = 0
    for delay, fn in steps:
        t += delay
        QTimer.singleShot(t, fn)
