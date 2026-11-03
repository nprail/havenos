"""AppModel: Qt-visible mirror of the core state, plus slots that turn QML calls into core commands.

Runs on the GUI thread (the core shares the Qt event loop via QtAsyncio), so core events can
set properties directly. If the core ever moves off this thread, hop with a queued signal here.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot

if TYPE_CHECKING:                  # annotations only: importing the core here would make importing this module slow
    from ..core import Core, Event


class AppModel(QObject):
    modeChanged = Signal()
    photoChanged = Signal()
    photoSourceChanged = Signal()
    mediaChanged = Signal()
    musicChanged = Signal()
    libraryChanged = Signal()
    weatherChanged = Signal()
    controlsChanged = Signal()
    haStatusChanged = Signal()
    crossfadeChanged = Signal()
    screenChanged = Signal()
    roomChanged = Signal()
    roomsChanged = Signal()
    roomSelectedChanged = Signal()
    roomViewChanged = Signal()
    announcementChanged = Signal()
    notificationsChanged = Signal()
    exposureChanged = Signal()
    webChanged = Signal()
    timersChanged = Signal()
    ringingChanged = Signal()
    voiceChanged = Signal()
    transcriptChanged = Signal()
    responseChanged = Signal()
    blurChanged = Signal()
    statsVisibleChanged = Signal()
    statsChanged = Signal()

    def __init__(self, core: Core, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._core = core
        self._s: dict[str, Any] = dict(core.state)
        self._photo: dict | None = None
        self._cached = 0
        self._rss = 0.0
        self._lag_worst = 0.0
        self._lag_slow = 0
        self._api = "?"
        core.bus.subscribe(self._on_event)

    # ---- core -> Qt ---------------------------------------------------------------------

    _NOTIFY = {
        "mode": "modeChanged", "photo": "photoChanged", "photo_source": "photoSourceChanged",
        "media": "mediaChanged", "music": "musicChanged", "library": "libraryChanged", "weather": "weatherChanged", "controls": "controlsChanged",
        "ha_status": "haStatusChanged", "crossfade_ms": "crossfadeChanged", "screen_on": "screenChanged", "brightness": "screenChanged", "backlight": "screenChanged",
        "room": "roomChanged", "rooms": "roomsChanged", "room_selected": "roomSelectedChanged", "room_view": "roomViewChanged",
        "announcement": "announcementChanged", "notifications": "notificationsChanged", "ha_exposure": "exposureChanged", "web": "webChanged", "setup_done": "webChanged", "timers": "timersChanged", "ringing": "ringingChanged",
        "voice": "voiceChanged", "voice_ready": "voiceChanged", "voice_muted": "voiceChanged", "transcript": "transcriptChanged", "response": "responseChanged",
        "blur": "blurChanged", "stats": "statsVisibleChanged",
    }

    def _on_event(self, ev: Event) -> None:
        if ev.type == "state.snapshot":
            self._apply(ev.data["state"])
        elif ev.type == "state.patch":
            self._apply(ev.data["patch"])
        elif ev.type == "stats":
            self._rss = ev.data["rss_mb"]
            self._lag_worst = ev.data["lag_worst_ms"]
            self._lag_slow = ev.data["lag_slow"]
            self._cached = ev.data.get("cached_photos", 0)
            self.statsChanged.emit()

    def _apply(self, patch: dict[str, Any]) -> None:
        for key, value in patch.items():
            if key == "photo":
                self._photo = None if value is None else {
                    **value, "url": bytes(QUrl.fromLocalFile(str(Path(value["path"]))).toEncoded()).decode()}
            self._s[key] = value
        for key in patch:
            sig = self._NOTIFY.get(key)
            if sig:
                getattr(self, sig).emit()

    def set_api(self, name: str) -> None:
        self._api = name
        self.statsChanged.emit()

    # ---- properties (read-only from QML) -------------------------------------------------

    mode = Property(str, lambda s: s._s["mode"], notify=modeChanged)
    photo = Property("QVariant", lambda s: s._photo, notify=photoChanged)
    photoSource = Property(str, lambda s: s._s["photo_source"], notify=photoSourceChanged)
    media = Property("QVariant", lambda s: s._s["media"], notify=mediaChanged)
    music = Property("QVariant", lambda s: s._s["music"], notify=musicChanged)
    library = Property("QVariant", lambda s: s._s["library"], notify=libraryChanged)
    weather = Property("QVariant", lambda s: s._s["weather"], notify=weatherChanged)
    controls = Property("QVariantList", lambda s: s._s["controls"], notify=controlsChanged)
    haStatus = Property(str, lambda s: s._s["ha_status"], notify=haStatusChanged)
    crossfadeMs = Property(int, lambda s: s._s["crossfade_ms"], notify=crossfadeChanged)
    room = Property("QVariant", lambda s: s._s["room"], notify=roomChanged)
    rooms = Property("QVariantList", lambda s: s._s["rooms"], notify=roomsChanged)
    roomSelected = Property(str, lambda s: s._s["room_selected"] or "", notify=roomSelectedChanged)
    roomView = Property("QVariant", lambda s: s._s["room_view"], notify=roomViewChanged)
    announcement = Property("QVariant", lambda s: s._s["announcement"], notify=announcementChanged)
    notifications = Property("QVariantList", lambda s: s._s["notifications"], notify=notificationsChanged)
    haExposure = Property("QVariant", lambda s: s._s["ha_exposure"], notify=exposureChanged)
    screenOn = Property(bool, lambda s: s._s["screen_on"], notify=screenChanged)
    brightness = Property(int, lambda s: s._s["brightness"], notify=screenChanged)
    backlight = Property(bool, lambda s: s._s["backlight"], notify=screenChanged)      # a real backlight is driven: no software dimming
    webUrl = Property(str, lambda s: (s._s["web"] or {}).get("url", ""), notify=webChanged)
    webCode = Property(str, lambda s: (s._s["web"] or {}).get("code", ""), notify=webChanged)
    webLink = Property(str, lambda s: (s._s["web"] or {}).get("link", ""), notify=webChanged)
    webQr = Property("QVariantList", lambda s: (s._s["web"] or {}).get("qr", []), notify=webChanged)
    setupDone = Property(bool, lambda s: s._s["setup_done"], notify=webChanged)
    cachedPhotos = Property(int, lambda s: s._cached, notify=statsChanged)
    timers = Property("QVariantList", lambda s: s._s["timers"], notify=timersChanged)
    ringing = Property("QVariant", lambda s: s._s["ringing"], notify=ringingChanged)
    voice = Property(str, lambda s: s._s["voice"], notify=voiceChanged)
    voiceReady = Property(bool, lambda s: s._s["voice_ready"], notify=voiceChanged)
    voiceMuted = Property(bool, lambda s: s._s["voice_muted"], notify=voiceChanged)
    transcript = Property(str, lambda s: s._s["transcript"], notify=transcriptChanged)
    response = Property(str, lambda s: s._s["response"], notify=responseChanged)
    blur = Property(bool, lambda s: s._s["blur"], notify=blurChanged)
    statsVisible = Property(bool, lambda s: s._s["stats"], notify=statsVisibleChanged)
    rssMb = Property(float, lambda s: s._rss, notify=statsChanged)
    lagWorstMs = Property(float, lambda s: s._lag_worst, notify=statsChanged)
    lagSlow = Property(int, lambda s: s._lag_slow, notify=statsChanged)
    api = Property(str, lambda s: s._api, notify=statsChanged)

    # ---- commands (QML -> core). No logic here: translate and forward. ---------------------

    @Slot(str)
    def setMode(self, mode: str) -> None:
        self._core.handle("mode.set", mode=mode)

    @Slot(int)
    def nextPhoto(self, delta: int) -> None:
        self._core.handle("photo.next", delta=delta)

    @Slot(int, str)
    def addTimer(self, seconds: int, label: str) -> None:
        self._core.handle("timer.start", seconds=seconds, label=label)

    @Slot(int)
    def cancelTimer(self, timer_id: int) -> None:
        self._core.handle("timer.cancel", id=timer_id)

    @Slot(int)
    def pauseTimer(self, timer_id: int) -> None:
        self._core.handle("timer.pause", id=timer_id)

    @Slot(int)
    def resumeTimer(self, timer_id: int) -> None:
        self._core.handle("timer.resume", id=timer_id)

    @Slot(int, int)
    def extendTimer(self, timer_id: int, seconds: int) -> None:
        self._core.handle("timer.extend", id=timer_id, seconds=seconds)

    @Slot()
    def dismissRing(self) -> None:
        self._core.handle("timer.dismiss")

    @Slot(int)
    def snooze(self, seconds: int) -> None:
        self._core.handle("timer.snooze", seconds=seconds)

    @Slot()
    def toggleMedia(self) -> None:
        self._core.handle("media.toggle")

    @Slot()
    def nextMedia(self) -> None:
        self._core.handle("media.next")

    @Slot()
    def prevMedia(self) -> None:
        self._core.handle("media.prev")

    @Slot(str)
    def musicCommand(self, name: str) -> None:
        self._core.handle("music.command", name=name)

    @Slot(float)
    def musicSeek(self, seconds: float) -> None:
        self._core.handle("music.command", name="seek", seconds=seconds)

    @Slot(int)
    def musicVolume(self, level: int) -> None:
        self._core.handle("music.command", name="volume", level=level)

    @Slot()
    def libraryOpen(self) -> None:
        self._core.handle("library.open")

    @Slot(str)
    def librarySearch(self, query: str) -> None:
        self._core.handle("library.search", query=query)

    @Slot()
    def libraryVoice(self) -> None:
        self._core.handle("library.voice")

    @Slot(str)
    def libraryPlay(self, uri: str) -> None:
        self._core.handle("library.play", uri=uri)

    @Slot(str, str)
    def simulateMusic(self, source: str, action: str) -> None:
        self._core.handle("music.simulate", source=source, action=action)

    @Slot(str)
    def toggleControl(self, control_id: str) -> None:
        self._core.handle("control.toggle", id=control_id)

    @Slot()
    def startVoice(self) -> None:
        self._core.handle("voice.start")

    @Slot()
    def dismissVoice(self) -> None:
        self._core.handle("voice.stop")

    @Slot()
    def activity(self) -> None:
        self._core.handle("ui.activity")

    @Slot(bool)
    def setBlur(self, on: bool) -> None:
        self._core.handle("config.set", blur=on)

    @Slot()
    def openRooms(self) -> None:
        self._core.handle("rooms.open")

    @Slot(str)
    def selectRoom(self, room_id: str) -> None:
        self._core.handle("rooms.select", id=room_id)

    @Slot()
    def roomsBack(self) -> None:
        self._core.handle("rooms.back")

    @Slot(str, str, "QVariantMap")
    def act(self, entity_id: str, action: str, args: dict) -> None:
        self._core.handle("ha.act", id=entity_id, action=action, **dict(args))

    @Slot()
    def testAnnouncement(self) -> None:
        self._core.handle("announce.show", title="havenOS", message="This is a test announcement from the info panel.", kind="info")

    @Slot()
    def dismissAnnouncement(self) -> None:
        self._core.handle("announce.dismiss")

    @Slot()
    def openNotifications(self) -> None:
        self._core.handle("mode.set", mode="notifications")

    @Slot()
    def clearNotifications(self) -> None:
        self._core.handle("notifications.clear")

    @Slot(str)
    def removeNotification(self, note_id: str) -> None:
        self._core.handle("notifications.remove", id=note_id)

    @Slot(str)
    def gesture(self, kind: str) -> None:
        self._core.handle("ui.gesture", kind=kind)

    @Slot(bool)
    def setDisplay(self, on: bool) -> None:
        self._core.handle("screen.set", on=on)

    @Slot(bool)
    def setStats(self, on: bool) -> None:
        self._core.handle("config.set", stats=on)
