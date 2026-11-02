import QtQuick

// Full-screen takeover for an announcement (HA `announce` service now; spoken announcements later).
// Info and warning ones time out with a visible countdown bar; critical ones stay until dismissed.
Item {
    id: root
    readonly property real u: Store.u
    readonly property var a: Store.announcement
    readonly property bool shown: a !== null
    readonly property color accent: !a ? "#4a9eff" : a.kind === "critical" ? "#e5534b" : a.kind === "warning" ? "#e0a030" : "#4a9eff"

    Rectangle {
        anchors.fill: parent; color: "#b3000000"
        opacity: root.shown ? 1 : 0; visible: opacity > 0
        Behavior on opacity { NumberAnimation { duration: 200 } }
        MouseArea { anchors.fill: parent }

        Rectangle {
            id: card
            anchors.centerIn: parent
            width: Math.min(parent.width - 6 * u, 44 * u); height: col.height + 8.5 * u; radius: 2 * u
            color: "#f2131318"; border.color: root.accent; border.width: 1.5
            scale: root.shown ? 1 : 0.92; opacity: root.shown ? 1 : 0
            Behavior on scale { NumberAnimation { duration: 200; easing.type: Easing.OutQuad } }
            Behavior on opacity { NumberAnimation { duration: 200 } }

            Column {
                id: col
                x: 3 * u; y: 2.4 * u; width: parent.width - 6 * u; spacing: 1 * u
                Row {
                    spacing: 0.9 * u
                    Icon { name: root.a && root.a.kind !== "info" ? "warning" : "bell"; size: 2.2 * u; anchors.verticalCenter: parent.verticalCenter }
                    Text { anchors.verticalCenter: parent.verticalCenter
                           text: root.a && root.a.title !== "" ? root.a.title : "Announcement"
                           color: root.accent; font.family: Store.sans; font.pixelSize: 1.2 * u; font.weight: Font.Medium
                           font.letterSpacing: 0.06 * u }
                }
                Text {
                    width: parent.width; wrapMode: Text.WordWrap; maximumLineCount: 6; elide: Text.ElideRight
                    text: root.a ? root.a.message : ""
                    color: "#f0ede8"; font.family: Store.display; font.weight: Font.Light
                    font.pixelSize: (root.a && root.a.message.length > 90 ? 2.2 : 3.0) * u
                }
            }

            Rectangle {          // countdown to auto-dismiss
                visible: root.a && root.a.seconds > 0
                x: 3 * u; y: card.height - 5.2 * u; width: card.width - 6 * u; height: 0.25 * u; radius: height / 2; color: "#26ffffff"
                Rectangle {
                    id: bar; height: parent.height; radius: height / 2; color: root.accent; width: parent.width
                    NumberAnimation on width {
                        id: shrink; running: false; to: 0
                        duration: root.a && root.a.seconds > 0 ? root.a.seconds * 1000 : 1
                    }
                }
            }
            Connections {
                target: Store
                function onAnnouncementChanged() {
                    if (root.a && root.a.seconds > 0) { bar.width = card.width - 6 * root.u; shrink.restart() } else shrink.stop()
                }
            }

            Row {
                anchors.horizontalCenter: parent.horizontalCenter; y: card.height - 3.9 * u; spacing: 1 * u
                Text { anchors.verticalCenter: parent.verticalCenter; visible: root.a && root.a.pending > 0
                       text: "+" + (root.a ? root.a.pending : 0) + " more"; color: "#99f0ede8"; font.family: Store.sans; font.pixelSize: 0.95 * u }
                Tap {
                    width: 8.5 * u; height: 3 * u
                    onClicked: Store.dismissAnnouncement()
                    Rectangle { anchors.fill: parent; radius: 1 * u; color: "white" }
                    Text { anchors.centerIn: parent; text: "Dismiss"; color: "black"; font.family: Store.sans
                           font.weight: Font.Medium; font.pixelSize: 1.1 * u }
                }
            }
        }
    }
}
