import QtQuick

// Full-screen takeover when a timer expires.
Item {
    id: root
    readonly property real u: Store.u
    readonly property bool shown: Store.ringing !== null

    Rectangle {
        id: shade
        anchors.fill: parent; color: "#b3000000"
        opacity: root.shown ? 1 : 0
        visible: opacity > 0
        Behavior on opacity { NumberAnimation { duration: 200 } }
        MouseArea { anchors.fill: parent }   // swallow touches

        Rectangle {
            id: card
            anchors.centerIn: parent
            width: 34 * u; height: 21 * u; radius: 2 * u
            color: "#f2131318"; border.color: "#29ffffff"; border.width: 1
            scale: root.shown ? 1 : 0.9
            opacity: root.shown ? 1 : 0
            Behavior on scale { NumberAnimation { duration: 200; easing.type: Easing.OutQuad } }
            Behavior on opacity { NumberAnimation { duration: 200 } }

            Item {
                id: iconWrap
                anchors.horizontalCenter: parent.horizontalCenter; y: 2 * u
                width: 6 * u; height: 6 * u
                Rectangle {
                    id: pulse
                    anchors.fill: parent; radius: width / 2; color: "transparent"
                    border.color: "#4a9eff"; border.width: 2
                    ParallelAnimation {
                        running: root.shown; loops: Animation.Infinite
                        NumberAnimation { target: pulse; property: "scale"; from: 0.9; to: 1.5; duration: 1400; easing.type: Easing.OutQuad }
                        NumberAnimation { target: pulse; property: "opacity"; from: 0.6; to: 0; duration: 1400; easing.type: Easing.OutQuad }
                    }
                }
                Icon { name: "timer"; size: 3.25 * u; anchors.centerIn: parent }
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter; y: 8.9 * u
                text: Store.ringing ? Store.ringing.label : ""
                color: "#99f0ede8"; font.family: Store.sans; font.pixelSize: 1.125 * u
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter; y: 10.2 * u
                text: "Timer done!"
                color: "#f0ede8"; font.family: Store.display; font.weight: Font.Light; font.pixelSize: 3.5 * u
            }
            Row {
                anchors.horizontalCenter: parent.horizontalCenter; y: 15.4 * u; spacing: 1 * u
                Tap {
                    width: 7 * u; height: 3.5 * u
                    onClicked: Store.snooze(60)
                    Rectangle { anchors.fill: parent; radius: 1 * u; color: "transparent"; border.color: "#40ffffff"; border.width: 1 }
                    Text { anchors.centerIn: parent; text: "+1 min"; color: "#f0ede8"; font.family: Store.sans; font.pixelSize: 1.125 * u }
                }
                Tap {
                    width: 8.5 * u; height: 3.5 * u
                    onClicked: Store.dismissRing()
                    Rectangle { anchors.fill: parent; radius: 1 * u; color: "white" }
                    Text { anchors.centerIn: parent; text: "Dismiss"; color: "black"; font.family: Store.sans
                           font.weight: Font.Medium; font.pixelSize: 1.125 * u }
                }
            }
        }
    }

}
