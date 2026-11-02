import QtQuick

// One controllable entity on a room screen. `e` is the core's view-model (kind decides the layout and controls).
Item {
    id: root
    property var e
    readonly property real u: Store.u
    readonly property string kind: e ? e.kind : "info"
    height: 9 * u                            // one size for every card: the grid stays tidy
    readonly property bool hasSlider: (kind === "light" && e.dimmable) || (kind === "fan" && e.speedable)
    readonly property bool hasToggle: kind === "toggle" || (kind === "light" && !e.dimmable) || (kind === "fan" && !e.speedable) || kind === "button"

    property real pendingTarget: NaN        // climate taps are applied optimistically so quick double taps add up
    property bool confirming: false         // lock: first tap on Unlock arms it
    Timer { id: disarm; interval: 4000; onTriggered: root.confirming = false }
    onEChanged: pendingTarget = NaN

    readonly property string iconName: {
        var m = { light: "bulb", climate: "thermo", fan: "fan", cover: "blinds", media_player: "speaker", lock: "lock",
                  switch: "plug", input_boolean: "plug", scene: "scenes", script: "scenes", vacuum: "gear" }
        return e && m[e.domain] ? m[e.domain] : "gear"
    }

    function act(action, args) { Store.act(e.id, action, args || ({})) }
    function bodyTap() {
        if (!e || e.unavailable) return
        if (kind === "light" || kind === "toggle" || kind === "fan") act("toggle")
        else if (kind === "button") act("run")
    }

    Rectangle {
        anchors.fill: parent; radius: 1.25 * u
        color: e && e.on ? "#2e4a9eff" : "#990e0e12"
        border.color: e && e.on ? "#994a9eff" : "#29ffffff"; border.width: 1
        opacity: e && e.unavailable ? 0.5 : 1
    }

    Tap {                                    // header: icon, name, status; tapping it does the obvious thing
        x: 0; y: 0; width: parent.width; height: 5.6 * u
        enabled: root.kind === "light" || root.kind === "toggle" || root.kind === "fan" || root.kind === "button"
        onClicked: root.bodyTap()
        Rectangle {
            id: badge; x: 1.1 * u; anchors.verticalCenter: parent.verticalCenter
            width: 3.4 * u; height: width; radius: width / 2
            color: root.e && root.e.on ? "#4a9eff" : "#14ffffff"
            Icon { name: root.iconName; dark: root.e && root.e.on; size: 1.8 * u; anchors.centerIn: parent }
        }
        Column {
            anchors.left: badge.right; anchors.leftMargin: 0.9 * u; anchors.right: parent.right; anchors.rightMargin: 1 * u
            anchors.verticalCenter: parent.verticalCenter; spacing: 0.15 * u
            Text { width: parent.width; elide: Text.ElideRight; text: root.e ? root.e.name : ""
                   color: "#f0ede8"; font.family: Store.sans; font.pixelSize: 1.1 * u; font.weight: Font.Medium }
            Text { width: parent.width; elide: Text.ElideRight; text: root.e ? root.e.status : ""
                   color: "#99f0ede8"; font.family: Store.sans; font.pixelSize: 0.9 * u }
        }
    }

    // ---- controls row (below the header) ----
    Item {
        x: 1.1 * u; y: 5.5 * u; width: parent.width - 2.2 * u; height: 3 * u
        enabled: root.e && !root.e.unavailable

        Pill {                               // plain on/off things and scenes: one clear button
            visible: root.hasToggle; anchors.verticalCenter: parent.verticalCenter
            primary: root.kind !== "button" && root.e && !root.e.on
            text: root.kind === "button" ? "Run" : root.e && root.e.on ? "Turn off" : "Turn on"
            onClicked: root.bodyTap()
        }

        MiniSlider {                         // light brightness / fan speed
            visible: root.hasSlider
            anchors.verticalCenter: parent.verticalCenter; width: parent.width
            value: root.e ? ((root.kind === "light" ? root.e.brightness : root.e.percentage) || 0) : 0
            onCommitted: (v) => root.act(root.kind === "light" ? "brightness" : "percentage", { percent: v })
        }

        Row {                                // cover
            visible: root.kind === "cover"; spacing: 0.6 * u; anchors.verticalCenter: parent.verticalCenter
            Pill { text: "Open"; onClicked: root.act("open") }
            Pill { text: "Stop"; onClicked: root.act("stop") }
            Pill { text: "Close"; onClicked: root.act("close") }
        }

        Row {                                // vacuum
            visible: root.kind === "vacuum"; spacing: 0.6 * u; anchors.verticalCenter: parent.verticalCenter
            Pill { text: "Start"; onClicked: root.act("start") }
            Pill { text: "Pause"; onClicked: root.act("pause") }
            Pill { text: "Dock"; onClicked: root.act("dock") }
        }

        Row {                                // climate: - target +
            id: clim
            visible: root.kind === "climate"; spacing: 1 * u; anchors.verticalCenter: parent.verticalCenter
            readonly property bool single: root.e && root.e.target !== null && root.e.target !== undefined
            readonly property real step: root.e && root.e.step ? root.e.step : 1
            readonly property real shown: isNaN(root.pendingTarget) ? (single ? root.e.target : 0) : root.pendingTarget
            function nudge(dir) {
                if (!root.e) return
                if (single) { root.pendingTarget = shown + dir * step; root.act("temperature", { temperature: root.pendingTarget }) }
                else if (root.e.low !== null && root.e.low !== undefined)
                    root.act("range", { low: root.e.low + dir * step, high: root.e.high + dir * step })
            }
            Pill { icon: "minus"; width: 3.4 * u; onClicked: clim.nudge(-1) }
            Text {
                anchors.verticalCenter: parent.verticalCenter; width: 6 * u; horizontalAlignment: Text.AlignHCenter
                text: clim.single ? Math.round(clim.shown * 10) / 10 + "°"
                      : root.e && root.e.low !== null && root.e.low !== undefined ? Math.round(root.e.low) + "–" + Math.round(root.e.high) + "°" : "—"
                color: "#f0ede8"; font.family: Store.display; font.weight: Font.Light; font.pixelSize: 1.9 * u
            }
            Pill { icon: "plus"; width: 3.4 * u; onClicked: clim.nudge(1) }
        }

        Row {                                // media
            visible: root.kind === "media"; spacing: 0.8 * u; anchors.verticalCenter: parent.verticalCenter
            Pill { icon: "prev"; width: 3.4 * u; onClicked: root.act("prev") }
            Pill { icon: root.e && root.e.playing ? "pause" : "play"; primary: true; width: 3.8 * u; onClicked: root.act("playpause") }
            Pill { icon: "next"; width: 3.4 * u; onClicked: root.act("next") }
        }

        Row {                                // lock: unlocking needs a second, deliberate tap
            visible: root.kind === "lock"; spacing: 0.8 * u; anchors.verticalCenter: parent.verticalCenter
            Pill {
                visible: root.e && root.e.state === "locked"
                danger: root.confirming; text: root.confirming ? "Tap again to unlock" : "Unlock"
                onClicked: {
                    if (root.confirming) { root.confirming = false; disarm.stop(); root.act("unlock", { confirmed: true }) }
                    else { root.confirming = true; disarm.restart() }
                }
            }
            Pill { visible: root.e && root.e.state !== "locked"; text: "Lock"; primary: true; onClicked: root.act("lock") }
        }
    }
}
