import QtQuick

// The resting screen while something is going on: music casting to this display and/or timers running. One thing fills
// the screen; two or three share it (never more than three splits). Timers that do not fit get a "+N more" button.
// Tapping a tile opens its control view on top (NowPlaying, TimersSheet) without leaving; swiping up or Home goes to
// the dashboard. Nothing else is decided here: tiles just draw core state.
Item {
    id: root
    property Item backdrop
    readonly property real u: Store.u
    readonly property bool shown: Store.liveShown
    readonly property int maxSplits: 3

    opacity: shown ? 1 : 0
    visible: opacity > 0
    Behavior on opacity { NumberAnimation { duration: 250 } }

    // timers by when they would finish. A paused one is placed by its remaining time, so pausing a tile does not move it
    // (the order is worked out when the timers change, not every tick, so tiles never shuffle under a finger)
    function order(a, b) { return a.key - b.key }
    readonly property var timerIds: {
        var now = Date.now(), ts = []
        for (var i = 0; i < Store.timers.length; i++) {
            var t = Store.timers[i]
            if (t.ringing) continue                      // a ringing timer is shown full screen by Main.qml
            ts.push({ id: t.id, key: t.paused ? now + t.left * 1000 : t.end })
        }
        ts.sort(order)
        return ts.map(function (t) { return t.id })
    }
    readonly property int hasMedia: Store.musicActive ? 1 : 0
    readonly property var shownTimers: timerIds.slice(0, maxSplits - hasMedia)
    readonly property int more: timerIds.length - shownTimers.length
    // the tiles, in order: music first, then timers
    readonly property var tiles: {
        var out = []
        if (hasMedia) out.push({ kind: "media", id: -1 })
        for (var i = 0; i < shownTimers.length; i++) out.push({ kind: "timer", id: shownTimers[i] })
        return out
    }

    // The tiles live in a list model that is updated in place, so a change (a timer paused, one cancelled) reuses the
    // tiles that stay instead of rebuilding them all.
    ListModel { id: tileModel }
    function syncTiles() {
        var want = tiles
        for (var i = 0; i < want.length; i++) {
            if (i < tileModel.count) {
                var cur = tileModel.get(i)
                if (cur.kind !== want[i].kind || cur.tid !== want[i].id) tileModel.set(i, { kind: want[i].kind, tid: want[i].id })
            } else tileModel.append({ kind: want[i].kind, tid: want[i].id })
        }
        while (tileModel.count > want.length) tileModel.remove(tileModel.count - 1)
    }
    onTilesChanged: syncTiles()
    Component.onCompleted: syncTiles()

    Rectangle { anchors.fill: parent; color: "#e60a0a0b" }          // the photo, dimmed right down

    // header: the time, and the way out
    Item {
        id: header
        x: 2.5 * u; y: 1.5 * u; width: parent.width - 5 * u; height: Math.max(3.6 * u, 44)
        Row {
            anchors.verticalCenter: parent.verticalCenter; spacing: 1 * u
            Text {
                id: timeTxt
                text: { var d = new Date(Store.now); var h = d.getHours() % 12; if (h === 0) h = 12
                        var m = d.getMinutes(); return h + ":" + (m < 10 ? "0" : "") + m }
                color: "#f0ede8"; font.family: Store.display; font.weight: Font.ExtraLight; font.pixelSize: 2.25 * u
            }
            Text {
                anchors.baseline: timeTxt.baseline
                text: Qt.formatDate(new Date(Store.now), "dddd, MMMM d")
                color: "#99f0ede8"; font.family: Store.sans; font.pixelSize: 1.0625 * u
            }
        }
        Pill {
            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
            icon: "home"; text: "Home"
            onClicked: Store.setScreen("active")
        }
    }

    // the splits
    Item {
        id: area
        x: 2 * u; y: header.y + header.height + 1 * u
        width: parent.width - 4 * u; height: parent.height - y - 2 * u
        readonly property real gap: 1 * u
        readonly property bool landscape: width >= height
        readonly property int n: tileModel.count

        // x, y, w, h of tile i of n
        function rect(i, n) {
            var W = width, H = height, g = gap
            if (n <= 1) return { x: 0, y: 0, w: W, h: H }
            if (n === 2) return landscape ? { x: i * ((W - g) / 2 + g), y: 0, w: (W - g) / 2, h: H }
                                          : { x: 0, y: i * ((H - g) / 2 + g), w: W, h: (H - g) / 2 }
            if (landscape) return i === 0 ? { x: 0, y: 0, w: (W - g) / 2, h: H }
                                          : { x: (W - g) / 2 + g, y: (i - 1) * ((H - g) / 2 + g), w: (W - g) / 2, h: (H - g) / 2 }
            return i === 0 ? { x: 0, y: 0, w: W, h: (H - g) / 2 }
                           : { x: (i - 1) * ((W - g) / 2 + g), y: (H - g) / 2 + g, w: (W - g) / 2, h: (H - g) / 2 }
        }

        Repeater {
            model: tileModel
            Loader {
                id: slot
                required property string kind
                required property int tid
                required property int index
                readonly property var r: area.rect(index, area.n)
                x: r.x; y: r.y; width: r.w; height: r.h
                Behavior on x { NumberAnimation { duration: 250; easing.type: Easing.OutCubic } }
                Behavior on y { NumberAnimation { duration: 250; easing.type: Easing.OutCubic } }
                Behavior on width { NumberAnimation { duration: 250; easing.type: Easing.OutCubic } }
                Behavior on height { NumberAnimation { duration: 250; easing.type: Easing.OutCubic } }
                sourceComponent: kind === "media" ? mediaTile : timerTile
                Component { id: mediaTile; MediaTile { } }
                Component {
                    id: timerTile
                    TimerTile {
                        timerId: slot.tid
                        // the "+N more" button sits on the last timer when some did not fit
                        moreCount: slot.index === area.n - 1 ? root.more : 0
                    }
                }
                // the Loader sizes its item
                onLoaded: { item.width = Qt.binding(function () { return slot.width }); item.height = Qt.binding(function () { return slot.height }) }
            }
        }
    }

    // swipe up for the dashboard (a drag handler, so taps and buttons on the tiles keep working)
    DragHandler {
        target: null; enabled: root.shown; dragThreshold: 30
        onActiveChanged: {
            if (active) return
            // (`translation` is already reset when the drag ends; the pointer positions are not)
            var dx = centroid.scenePosition.x - centroid.scenePressPosition.x
            var dy = centroid.scenePosition.y - centroid.scenePressPosition.y
            if (dy < -80 && Math.abs(dy) > Math.abs(dx) * 1.5) Store.setScreen("active")
        }
    }
}
