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
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterSingletonInstance
from PySide6.QtCore import QTimer, QUrl
from PySide6.QtQuick import QQuickWindow
import qasync
from shiboken6 import getCppPointer, wrapInstance

from .bridge import AppModel
from .core import Config, Core, childproc
from .core.web import WebUI
from .core.esphome import ESPHomeDevice
from .core.persist import SettingsPersister

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"
log = logging.getLogger("havenos")


def main() -> int:
    logging.basicConfig(level=os.environ.get("HAVENOS_LOG", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = QGuiApplication(sys.argv)
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
    pool = ProcessPoolExecutor(max_workers=2)   # photo decode/resize: processes, so the GIL never touches the GUI thread
    core = Core(config, executor=pool)
    model = AppModel(core)
    qmlRegisterSingletonInstance(AppModel, "Haven", 1, 0, "App", model)

    engine = QQmlApplicationEngine()   # kept alive by this frame for the life of the loop
    engine.rootContext().setContextProperty("Config", {
        "width": config.width, "height": config.height, "fullscreen": config.fullscreen})

    esphome = ESPHomeDevice(core, name=config.esphome_name or None, port=config.esphome_port, key=config.esphome_key or None) if config.esphome_enabled else None
    web = WebUI(core, ASSETS, esphome=esphome)
    persister = SettingsPersister(core)

    async def boot() -> None:
        await core.start()                 # photos prepared before the first frame is built
        persister.start()                  # display settings changed at runtime (HA, HUD) are saved to config.toml
        if config.web_enabled:
            await web.start()              # settings UI; a busy port is logged, not fatal
        if esphome:
            try:
                await esphome.start()      # appears in Home Assistant under Settings > Devices > ESPHome
            except OSError as e:
                log.error("ESPHome device could not start on port %s: %s", config.esphome_port, e)
        engine.load(QUrl.fromLocalFile(str(HERE / "qml" / "Main.qml")))
        if not engine.rootObjects():
            log.error("QML failed to load")
            app.exit(1)
            return
        # rootObjects() hands back a plain QWindow wrapper; we need the QQuickWindow API (grabWindow, rendererInterface)
        obj = engine.rootObjects()[0]
        win = wrapInstance(getCppPointer(obj)[0], QQuickWindow)
        win.sceneGraphInitialized.connect(lambda: model.set_api(str(win.rendererInterface().graphicsApi()).split(".")[-1]))
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
            persister.stop()
            if esphome:
                loop.run_until_complete(esphome.stop())
            loop.run_until_complete(web.stop())        # then tear down on the same loop
            loop.run_until_complete(core.stop())
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
