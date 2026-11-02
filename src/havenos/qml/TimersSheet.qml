import QtQuick

// The timers control view: every timer, with the buttons for the ones the display owns, and quick ways to add one.
// It opens over the live screen and closes back to it.
Item {
    id: root
    property Item backdrop
    readonly property real u: Store.u
    readonly property bool shown: Store.timersOpen

    opacity: shown ? 1 : 0
    visible: opacity > 0
    Behavior on opacity { NumberAnimation { duration: 250 } }

    Rectangle { anchors.fill: parent; color: "#d90a0a0b" }
    MouseArea { anchors.fill: parent; onClicked: Store.timersOpen = false }

    Glass {
        id: card
        backdrop: root.backdrop; watch: root.opacity; flatOnly: true; flatTint: "#e6121216"
        anchors.centerIn: parent
        width: Math.min(parent.width - 8 * u, 56 * u); height: Math.min(parent.height - 6 * u, 40 * u)
        radius: 2 * u
        MouseArea { anchors.fill: parent }                                    // taps inside the card stay inside

        Text {
            x: 2.5 * u; y: 2 * u; text: "TIMERS"; color: "#99f0ede8"; font.family: Store.sans
            font.pixelSize: 0.8125 * u; font.letterSpacing: 0.12 * u
        }
        Tap {
            anchors.right: parent.right; anchors.rightMargin: 1 * u; y: 1 * u; width: 3 * u; height: 3 * u
            onClicked: Store.timersOpen = false
            Icon { name: "close"; size: 1.4 * u; anchors.centerIn: parent; opacity: 0.6 }
        }

        ListView {
            id: list
            x: 2.5 * u; y: 4.4 * u; width: parent.width - 5 * u; height: parent.height - y - 8 * u
            clip: true; spacing: 0.5 * u
            model: Store.timers
            delegate: Rectangle {
                id: row
                required property var modelData
                readonly property bool paused: modelData.paused
                width: list.width; height: 5.4 * u; radius: 1.2 * u; color: "#0dffffff"

                Text {
                    x: 1.5 * u; y: 0.9 * u; width: parent.width * 0.3; elide: Text.ElideRight
                    text: row.modelData.label; color: "#f0ede8"; font.family: Store.sans; font.pixelSize: 1.1 * u
                }
                Text {
                    x: 1.5 * u; y: 2.7 * u
                    text: row.paused ? "Paused" : (row.modelData.local ? "" : "Set by voice")
                    visible: text !== ""; color: "#99f0ede8"; font.family: Store.sans; font.pixelSize: 0.8125 * u
                }
                Text {
                    x: parent.width * 0.34
                    anchors.verticalCenter: parent.verticalCenter
                    text: Store.fmt(Store.timerSecs(row.modelData))
                    color: row.paused ? "#99f0ede8" : "#f0ede8"; font.family: Store.display; font.weight: Font.Light
                    font.pixelSize: 2.4 * u; font.features: { "tnum": 1 }
                }
                Row {
                    anchors.right: parent.right; anchors.rightMargin: 1 * u; anchors.verticalCenter: parent.verticalCenter
                    spacing: 0.8 * u
                    Pill { visible: row.modelData.local; anchors.verticalCenter: parent.verticalCenter
                           text: row.paused ? "Resume" : "Pause"; icon: row.paused ? "play" : "pause"
                           onClicked: row.paused ? Store.resumeTimer(row.modelData.id) : Store.pauseTimer(row.modelData.id) }
                    Pill { visible: row.modelData.local; anchors.verticalCenter: parent.verticalCenter
                           text: "+1 min"; onClicked: Store.extendTimer(row.modelData.id, 60) }
                    Tap {
                        width: 3 * u; height: 3 * u; anchors.verticalCenter: parent.verticalCenter
                        onClicked: Store.cancelTimer(row.modelData.id)
                        Icon { name: "close"; size: 1.3 * u; anchors.centerIn: parent; opacity: 0.7 }
                    }
                }
            }
        }

        Text {
            x: 2.5 * u; y: parent.height - 6.2 * u; text: "ADD A TIMER"; color: "#99f0ede8"; font.family: Store.sans
            font.pixelSize: 0.8125 * u; font.letterSpacing: 0.12 * u
        }
        Row {
            x: 2.5 * u; y: parent.height - 4.4 * u; spacing: 1 * u
            Repeater {
                model: [[60, "1 min"], [300, "5 min"], [600, "10 min"], [900, "15 min"], [1800, "30 min"]]
                Pill { required property var modelData; text: modelData[1]; onClicked: Store.addTimer(modelData[0], modelData[1]) }
            }
        }
    }
}
