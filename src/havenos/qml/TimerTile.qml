import QtQuick

// One timer: on the live screen, and full screen over everything while it rings (Main.qml). Running: pause (or resume) on the left, a big ring in the middle (the name, the time left),
// stop on the right. Tapping the tile opens the timers control view (all timers) on top. Timers that Home Assistant owns
// (set by voice) can be stopped but not paused, so their pause button is not shown. Ringing (time is up): the ring pulses and
// says "Timer done!", +1 min takes the place of pause, and tapping anywhere inside the ring stops the timer.
Item {
    id: tile
    property int timerId: -1
    property int moreCount: 0                       // timers that did not fit: shown as a "+N more" button
    readonly property real u: Store.u
    readonly property var t: {
        var ts = Store.timers
        for (var i = 0; i < ts.length; i++) if (ts[i].id === timerId) return ts[i]
        return null
    }
    readonly property real secs: Math.max(0, Store.timerSecs(t))
    readonly property bool paused: t !== null && t.paused
    readonly property bool ringing: t !== null && t.ringing
    property bool card: true                        // the tile's own panel; off when it fills the screen
    readonly property real btn: Math.max(3.6 * u, 44)
    readonly property real k: Math.max(0.7, Math.min(1.5, Math.min(width / (34 * u), height / (26 * u))))
    readonly property real ringSize: Math.max(6 * u, Math.min(height - 3 * u, width - 2 * (btn + 1.5 * u) - 1 * u))

    Rectangle {
        visible: tile.card
        anchors.fill: parent; radius: 2 * u
        color: "#d9121216"; border.color: "#1affffff"; border.width: 1
    }
    MouseArea { anchors.fill: parent; enabled: !tile.ringing; onClicked: { Store.gesture("tap"); Store.timersOpen = true } }

    Item {
        id: ring
        anchors.centerIn: parent
        width: tile.ringSize; height: width
        Rectangle {
            id: pulse
            visible: tile.ringing
            anchors.fill: parent; radius: width / 2; color: "transparent"
            border.color: "#4a9eff"; border.width: 2
            ParallelAnimation {                      // only while it rings: an endless animation redraws every frame
                running: tile.ringing; loops: Animation.Infinite
                NumberAnimation { target: pulse; property: "scale"; from: 1.0; to: 1.12; duration: 1400; easing.type: Easing.OutQuad }
                NumberAnimation { target: pulse; property: "opacity"; from: 0.6; to: 0; duration: 1400; easing.type: Easing.OutQuad }
            }
        }
        Rectangle { anchors.fill: parent; anchors.margins: 0.3 * u; radius: width / 2; color: "transparent"
                    border.color: "#26ffffff"; border.width: 0.45 * u * Math.max(0.8, tile.k) }
        Canvas {
            anchors.fill: parent
            property real frac: tile.ringing ? 1 : tile.t ? Math.max(0, Math.min(1, tile.secs / Math.max(1, tile.t.total))) : 0
            property bool paused: tile.paused
            onFracChanged: requestPaint()
            onPausedChanged: requestPaint()
            onWidthChanged: requestPaint()
            onPaint: {
                var c = getContext("2d"); c.reset()
                var lw = 0.45 * Store.u * Math.max(0.8, tile.k)
                c.strokeStyle = paused ? "#99f0ede8" : "#4a9eff"; c.lineWidth = lw; c.lineCap = "round"
                c.beginPath()
                c.arc(width / 2, height / 2, width / 2 - 0.3 * Store.u - lw / 2, -Math.PI / 2, -Math.PI / 2 + 2 * Math.PI * frac)
                c.stroke()
            }
        }
        Column {
            anchors.centerIn: parent
            spacing: ring.width * 0.03
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                width: ring.width * 0.7; elide: Text.ElideRight; horizontalAlignment: Text.AlignHCenter
                text: tile.t ? tile.t.label : ""
                color: "#99f0ede8"; font.family: Store.sans; font.pixelSize: Math.max(0.9 * u, ring.width * 0.055)
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: tile.ringing ? "Timer done!" : Store.fmt(tile.secs)
                color: tile.paused ? "#99f0ede8" : "#f0ede8"; font.family: Store.display
                font.weight: tile.ringing ? Font.Light : Font.ExtraLight
                font.pixelSize: ring.width * (tile.ringing ? 0.105 : 0.24); font.features: { "tnum": 1 }
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                visible: tile.paused || tile.ringing
                text: tile.ringing ? "Tap to stop" : "PAUSED"
                color: "#99f0ede8"; font.family: Store.sans; font.pixelSize: Math.max(0.8 * u, ring.width * 0.05)
                font.letterSpacing: 0.12 * u
            }
        }
    }

    // anywhere inside the ring stops a ringing timer
    MouseArea {
        enabled: tile.ringing
        x: ring.x; y: ring.y; width: ring.width; height: ring.height
        onClicked: Store.cancelTimer(tile.timerId)
    }

    // pause / resume (+1 min while ringing), left of the ring (only for a timer the display owns)
    Tap {
        id: pauseBtn
        visible: tile.t !== null && (tile.t.local || tile.ringing)
        width: tile.btn; height: width
        anchors.verticalCenter: parent.verticalCenter
        x: (ring.x - width) / 2
        onClicked: tile.ringing ? Store.snooze(60) : tile.paused ? Store.resumeTimer(tile.timerId) : Store.pauseTimer(tile.timerId)
        Rectangle { anchors.fill: parent; radius: width / 2; color: "#1affffff"; border.color: "#59ffffff"; border.width: 1 }
        Icon { visible: !tile.ringing; name: tile.paused ? "play" : "pause"; size: parent.width * 0.42; anchors.centerIn: parent }
        Text { visible: tile.ringing; anchors.centerIn: parent; text: "+1m"; color: "#f0ede8"; font.family: Store.sans; font.pixelSize: parent.width * 0.3 }
    }

    // stop, right of the ring: cancels this timer (works for timers Home Assistant owns too)
    Tap {
        id: stopBtn
        width: tile.btn; height: width
        anchors.verticalCenter: parent.verticalCenter
        x: ring.x + ring.width + (tile.width - ring.x - ring.width - width) / 2
        onClicked: Store.cancelTimer(tile.timerId)
        Rectangle { anchors.fill: parent; radius: width / 2; color: "#1affffff"; border.color: "#59ffffff"; border.width: 1 }
        Icon { name: "close"; size: parent.width * 0.42; anchors.centerIn: parent }
    }

    Pill {
        visible: tile.moreCount > 0
        anchors.right: parent.right; anchors.rightMargin: 1 * u; anchors.top: parent.top; anchors.topMargin: 1 * u
        text: "+" + tile.moreCount + " more"
        onClicked: Store.timersOpen = true
    }
}
