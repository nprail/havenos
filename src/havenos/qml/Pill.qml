import QtQuick

// A small labelled button used on entity cards.
Tap {
    id: root
    property string text
    property bool primary: false
    property bool danger: false
    property string icon: ""
    readonly property real u: Store.u
    width: Math.max(3.4 * u, 64, row.width + 2 * u); height: Math.max(2.6 * u, 40)

    Rectangle {
        anchors.fill: parent; radius: height / 2
        color: root.danger ? "#d94a4a" : root.primary ? "white" : "#1affffff"
        border.color: "#33ffffff"; border.width: root.primary || root.danger ? 0 : 1
    }
    Row {
        id: row; anchors.centerIn: parent; spacing: 0.4 * u
        Icon { visible: root.icon !== ""; name: root.icon; dark: root.primary; size: Math.max(1.3 * u, 16); anchors.verticalCenter: parent.verticalCenter }
        Text {
            visible: root.text !== ""; anchors.verticalCenter: parent.verticalCenter
            text: root.text; font.family: Store.sans; font.pixelSize: Math.max(0.9375 * u, 13); font.weight: Font.Medium
            color: root.primary ? "black" : "#f0ede8"
        }
    }
}
