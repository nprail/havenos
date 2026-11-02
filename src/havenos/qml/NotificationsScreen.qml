import QtQuick

// The notification list: announcements that have been and gone, plus anything sent quietly (and, optionally, Home Assistant's own).
Item {
    id: root
    property Item backdrop
    readonly property real u: Store.u
    readonly property bool shown: Store.mode === "notifications"

    y: shown ? 0 : height
    visible: y < height
    Behavior on y { NumberAnimation { duration: root.shown ? 300 : 250; easing.type: root.shown ? Easing.OutCubic : Easing.InCubic } }

    Rectangle { anchors.fill: parent; color: "#f50a0a0d" }
    MouseArea { anchors.fill: parent }

    function ago(ts) {
        if (!ts) return ""
        var s = Math.max(0, (Store.now - ts) / 1000)
        if (s < 60) return "just now"
        if (s < 3600) return Math.floor(s / 60) + " min ago"
        if (s < 86400) return Math.floor(s / 3600) + " h ago"
        return Qt.formatDateTime(new Date(ts), "MMM d, h:mm AP")
    }

    Glass {
        id: header
        backdrop: root.backdrop; watch: root.y; flatOnly: true
        x: 2.5 * u; y: 2 * u; width: parent.width - 5 * u; height: 4.75 * u; radius: 1.75 * u
        Tap {
            id: backBtn; x: 0.9 * u; anchors.verticalCenter: parent.verticalCenter; width: 3.4 * u; height: 3.4 * u
            onClicked: Store.setScreen("active")
            Rectangle { anchors.fill: parent; radius: width / 2; color: "#14ffffff" }
            Icon { name: "back"; size: 1.7 * u; anchors.centerIn: parent }
        }
        Text { anchors.left: backBtn.right; anchors.leftMargin: 1 * u; anchors.verticalCenter: parent.verticalCenter
               text: "Notifications"; color: "#f0ede8"; font.family: Store.display; font.weight: Font.Light; font.pixelSize: 2.25 * u }
        Pill {
            anchors.right: parent.right; anchors.rightMargin: 1.5 * u; anchors.verticalCenter: parent.verticalCenter
            text: "Clear all"; visible: Store.notifications.length > 0; onClicked: Store.clearNotifications()
        }
    }

    Text {
        visible: Store.notifications.length === 0; anchors.centerIn: parent
        text: "Nothing new"; color: "#99f0ede8"; font.family: Store.display; font.weight: Font.Light; font.pixelSize: 2.4 * u
    }

    ListView {
        x: 2.5 * u; y: header.y + header.height + 1.2 * u; width: parent.width - 5 * u; height: parent.height - y - 1.5 * u
        clip: true; spacing: 0.8 * u; model: Store.notifications
        delegate: Item {
            required property var modelData
            width: ListView.view.width; height: Math.max(6 * u, body.height + 2.4 * u)
            Rectangle { anchors.fill: parent; radius: 1.25 * u; color: "#990e0e12"; border.color: "#29ffffff"; border.width: 1 }
            Rectangle { x: 0; y: 1 * u; width: 0.3 * u; height: parent.height - 2 * u; radius: width / 2
                        color: modelData.kind === "critical" ? "#e5534b" : modelData.kind === "warning" ? "#e0a030" : "#4a9eff" }
            Column {
                id: body; x: 1.6 * u; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 6.5 * u; spacing: 0.3 * u
                Row { spacing: 0.7 * u
                    Text { text: modelData.title !== "" ? modelData.title : "Notification"; color: "#f0ede8"; font.family: Store.sans
                           font.pixelSize: 1.1 * u; font.weight: Font.Medium }
                    Text { text: root.ago(modelData.ts); color: "#80f0ede8"; font.family: Store.sans; font.pixelSize: 0.85 * u
                           anchors.baseline: parent.children[0].baseline } }
                Text { width: parent.width; wrapMode: Text.WordWrap; maximumLineCount: 4; elide: Text.ElideRight; text: modelData.message
                       color: "#ccf0ede8"; font.family: Store.sans; font.pixelSize: 1 * u }
            }
            Tap {
                visible: modelData.id.indexOf("ha:") !== 0
                anchors.right: parent.right; anchors.rightMargin: 0.8 * u; anchors.verticalCenter: parent.verticalCenter; width: 3 * u; height: 3 * u
                onClicked: Store.removeNotification(modelData.id)
                Icon { name: "close"; size: 1.25 * u; anchors.centerIn: parent; opacity: 0.6 }
            }
        }
    }
}
