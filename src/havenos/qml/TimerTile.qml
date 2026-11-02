import QtQuick

// One timer on the live screen: a ring that empties, the time left, its name. Tapping it opens the timers control view
// (all timers) on top. Timers that Home Assistant owns (set by voice) can be cancelled there but not paused or extended.
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
    readonly property real secs: Store.timerSecs(t)
    readonly property bool paused: t !== null && t.paused
    readonly property bool wide: width >= height * 1.6
    readonly property real k: Math.max(0.7, Math.min(1.5, Math.min(width / (34 * u), height / (26 * u))))
    readonly property real ringSize: wide ? Math.min(height - 4 * u, width * 0.4) : Math.min(width - 4 * u, (height - 9 * u) * 1.0)

    Rectangle {
        anchors.fill: parent; radius: 2 * u
        color: "#d9121216"; border.color: "#1affffff"; border.width: 1
    }
    MouseArea { anchors.fill: parent; onClicked: { Store.gesture("tap"); Store.timersOpen = true } }

    Item {
        id: ring
        x: tile.wide ? 2 * u + (tile.width * 0.5 - 2 * u - width) / 2 : (tile.width - width) / 2
        y: tile.wide ? (tile.height - height) / 2 : 5.4 * u
        width: Math.max(6 * u, tile.ringSize); height: width
        Rectangle { anchors.fill: parent; anchors.margins: 0.3 * u; radius: width / 2; color: "transparent"
                    border.color: "#26ffffff"; border.width: 0.45 * u * Math.max(0.8, tile.k) }
        Canvas {
            anchors.fill: parent
            property real frac: tile.t ? Math.max(0, Math.min(1, tile.secs / Math.max(1, tile.t.total))) : 0
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
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: Store.fmt(tile.secs)
                color: tile.paused ? "#99f0ede8" : "#f0ede8"; font.family: Store.display; font.weight: Font.ExtraLight
                font.pixelSize: ring.width * 0.24; font.features: { "tnum": 1 }
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: tile.paused ? "PAUSED" : (tile.t ? "of " + Store.fmt(tile.t.total) : "")
                color: "#99f0ede8"; font.family: Store.sans; font.pixelSize: Math.max(0.8 * u, ring.width * 0.05)
                font.letterSpacing: 0.12 * u
            }
        }
    }

    // name, and the buttons for a timer the display owns
    Column {
        x: tile.wide ? tile.width * 0.5 : 5 * u
        y: tile.wide ? (tile.height - height) / 2 : 1.6 * u
        width: tile.wide ? tile.width * 0.5 - 2 * u : tile.width - 10 * u
        spacing: 1 * u
        Text {
            width: parent.width; elide: Text.ElideRight; horizontalAlignment: tile.wide ? Text.AlignLeft : Text.AlignHCenter
            text: (tile.t ? tile.t.label : "").toUpperCase()
            color: "#99f0ede8"; font.family: Store.sans; font.pixelSize: 0.9375 * u * Math.max(1, tile.k * 0.9); font.letterSpacing: 0.12 * u
        }
        Row {
            visible: tile.wide && tile.t !== null && tile.t.local
            spacing: 1 * u
            Pill { text: tile.paused ? "Resume" : "Pause"; icon: tile.paused ? "play" : "pause"; primary: true
                   onClicked: tile.paused ? Store.resumeTimer(tile.timerId) : Store.pauseTimer(tile.timerId) }
            Pill { text: "+1 min"; onClicked: Store.extendTimer(tile.timerId, 60) }
        }
    }
    // narrow tiles: the buttons go under the ring
    Row {
        visible: !tile.wide && tile.t !== null && tile.t.local && tile.height > 20 * u
        anchors.horizontalCenter: parent.horizontalCenter; y: ring.y + ring.height + 0.8 * u
        spacing: 1 * u
        Pill { text: tile.paused ? "Resume" : "Pause"; icon: tile.paused ? "play" : "pause"; primary: true
               onClicked: tile.paused ? Store.resumeTimer(tile.timerId) : Store.pauseTimer(tile.timerId) }
        Pill { text: "+1 min"; onClicked: Store.extendTimer(tile.timerId, 60) }
    }

    // dismiss: cancels this timer (works for timers Home Assistant owns too)
    Tap {
        id: dismiss
        anchors.right: parent.right; anchors.rightMargin: 1 * u; anchors.top: parent.top; anchors.topMargin: 1 * u
        width: Math.max(3.2 * u, 40); height: width
        onClicked: Store.cancelTimer(tile.timerId)
        Rectangle { anchors.fill: parent; radius: width / 2; color: "#1affffff"; border.color: "#33ffffff"; border.width: 1 }
        Icon { name: "close"; size: Math.max(1.4 * u, 18); anchors.centerIn: parent }
    }

    Pill {
        visible: tile.moreCount > 0
        anchors.right: dismiss.left; anchors.rightMargin: 0.8 * u; anchors.verticalCenter: dismiss.verticalCenter
        text: "+" + tile.moreCount + " more"
        onClicked: Store.timersOpen = true
    }
}
