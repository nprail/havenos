"""havenOS single-app entry point: core + Qt Quick UI in one process, one shared event loop.

    python -m havenos                      # windowed 1280x800 (desktop)
    HAVENOS_FULLSCREEN=1 python -m havenos # kiosk-style
    QT_QPA_PLATFORM=eglfs HAVENOS_FULLSCREEN=1 python -m havenos   # Pi, no desktop/compositor

Env: HAVENOS_INTERVAL (ms, 8000)  HAVENOS_IDLE (s, 30)  HAVENOS_BLUR=0  HAVENOS_STATS=1
     HAVENOS_SIZE=1024x600  HAVENOS_WEB=0  HAVENOS_WEB_PORT=8787  HAVENOS_PHOTOS=/dir  HAVENOS_CACHE=/dir  HAVENOS_SHOT=/path/prefix (headless shots, then quit)
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterSingletonType
from PySide6.QtCore import QTimer, QUrl
from PySide6.QtQuick import QQuickWindow
import qasync
from shiboken6 import getCppPointer, wrapInstance

from . import START, boot as boot_handover
from .bridge import AppModel
from .core import childproc
from .core.config import Config

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"
log = logging.getLogger("havenos")


def mark(what: str) -> None:
    """Startup checkpoint: seconds since the package was first imported (read these to see where boot time goes)."""
    log.info("startup: %-22s %5.2f s", what, time.monotonic() - START)


def _import_core() -> None:
    """Import the heavy modules (aiohttp, aioesphomeapi, numpy, the core) in a thread while the window comes up: their
    import is most of the boot time on a Pi, and the window only needs Qt. Core modules only: importing Qt modules off
    the main thread breaks QML ("expected QObject" when it builds the interface)."""
    from .core import core, esphome, persist, web               # noqa: F401


def main() -> int:
    logging.basicConfig(level=os.environ.get("HAVENOS_LOG", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    mark("Qt imported")
    # Start the photo workers (fork) first, while there is one thread and no GPU state to copy: workers forked after EGL
    # is up break the display (every page flip fails with EINVAL on the Pi, a blank screen). They import only what a
    # photo task needs, so they stay small.
    pool = ProcessPoolExecutor(max_workers=2)
    for f in [pool.submit(time.sleep, 0.2), pool.submit(time.sleep, 0.2)]:
        f.result()
    preload = threading.Thread(target=_import_core, name="preload", daemon=True)
    preload.start()
    app = QGuiApplication(sys.argv)
    mark("Qt platform up")
    # SIGTERM and SIGINT quit normally (which stops the helper daemons); a second one kills them and exits. Python only
    # runs signal handlers when it runs Python code, so a no-op timer keeps the Qt loop coming back to it.
    childproc.install(app.quit)
    keepalive = QTimer()
    keepalive.start(250)
    keepalive.timeout.connect(lambda: None)
    for f in sorted((ASSETS / "fonts").glob("*.ttf")):
        if QFontDatabase.addApplicationFont(str(f)) < 0:
            log.warning("font failed: %s", f.name)

    config = Config.from_env(ASSETS)
    parts: dict = {}                   # core, model, web, esphome, persister: built once the heavy imports are done
    # The App singleton must be registered before the engine exists (registering later breaks QML's type lookups); the
    # interface only asks for it once Scene.qml is loaded, by when the model is built.
    qmlRegisterSingletonType(AppModel, "Haven", 1, 0, "App", lambda _engine: parts["model"])
    engine = QQmlApplicationEngine()   # kept alive by this frame for the life of the loop
    engine.rootContext().setContextProperty("Config", {
        "width": config.width, "height": config.height, "fullscreen": config.fullscreen})

    async def boot() -> None:
        # The window comes first: on a Pi the boot splash has let go of the display just before we started, and
        # BootSplash.qml (it needs nothing from the core) keeps the picture moving while the rest loads.
        engine.load(QUrl.fromLocalFile(str(HERE / "qml" / "boot" / "Main.qml")))
        if not engine.rootObjects():
            log.error("QML failed to load")
            app.exit(1)
            return
        # rootObjects() hands back a plain QWindow wrapper; we need the QQuickWindow API (grabWindow, rendererInterface)
        obj = engine.rootObjects()[0]
        win = wrapInstance(getCppPointer(obj)[0], QQuickWindow)
        first = []
        def on_first_frame() -> None:          # render thread; the window has drawn, so the boot splash can go
            if not first:
                first.append(1)
                boot_handover.notify_ready()
                log.info("startup: first frame %9.2f s", time.monotonic() - START)
        win.frameSwapped.connect(on_first_frame)
        mark("window loaded")

        await asyncio.get_running_loop().run_in_executor(None, preload.join)
        mark("core imported")
        from .core.core import Core
        from .core.esphome import ESPHomeDevice
        from .core.persist import SettingsPersister
        from .core.web import WebUI
        core = Core(config, executor=pool)
        model = AppModel(core)
        esphome = ESPHomeDevice(core, name=config.esphome_name or None, port=config.esphome_port, key=config.esphome_key or None) if config.esphome_enabled else None
        web = WebUI(core, ASSETS, esphome=esphome)
        persister = SettingsPersister(core)
        parts.update(model=model, core=core, web=web, esphome=esphome, persister=persister)
        ri = win.rendererInterface()
        if ri is not None:                      # the scene graph is already up: the window has been drawing the splash
            model.set_api(str(ri.graphicsApi()).split(".")[-1])
        obj.setProperty("sceneReady", True)     # Main.qml loads the interface now that the App singleton exists
        mark("interface loading")
        await core.start()
        mark("core started")
        persister.start()                  # display settings changed at runtime (HA, HUD) are saved to config.toml
        if config.web_enabled:
            await web.start()              # settings UI; a busy port is logged, not fatal
        if esphome:
            try:
                await esphome.start()      # appears in Home Assistant under Settings > Devices > ESPHome
            except OSError as e:
                log.error("ESPHome device could not start on port %s: %s", config.esphome_port, e)
        shot = os.environ.get("HAVENOS_SHOT")
        if shot:
            from .devtools import install_shots
            install_shots(app, win, core, shot)

    # qasync, not PySide6.QtAsyncio: QtAsyncio's loop has no network I/O (aiohttp hangs), qasync does.
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    try:
        with loop:
            loop.create_task(boot())
            loop.run_forever()                         # returns when the app quits (aboutToQuit stops qasync's loop)
            if parts:
                parts["persister"].stop()
                if parts["esphome"]:
                    loop.run_until_complete(parts["esphome"].stop())
                loop.run_until_complete(parts["web"].stop())        # then tear down on the same loop
                loop.run_until_complete(parts["core"].stop())
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
