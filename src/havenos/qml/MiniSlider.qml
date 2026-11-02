import QtQuick

// A touch slider that reports only when released, so dragging does not flood Home Assistant with service calls.
Item {
    id: root
    property int value: 0                 // 0..100, follows the entity while not dragging
    property color accent: "#4a9eff"
    signal committed(int v)
    readonly property real u: Store.u
    property bool dragging: false
    property int dragValue: 0
    readonly property int shown: dragging ? dragValue : value
    height: 2.4 * u

    function at(x) { return Math.round(Math.max(0, Math.min(1, x / width)) * 100) }

    Rectangle { id: track; anchors.verticalCenter: parent.verticalCenter; width: parent.width; height: 0.4 * u; radius: height / 2; color: "#26ffffff" }
    Rectangle { anchors.verticalCenter: parent.verticalCenter; width: track.width * root.shown / 100; height: track.height; radius: height / 2; color: root.accent }
    Rectangle {
        x: track.width * root.shown / 100 - width / 2; anchors.verticalCenter: parent.verticalCenter
        width: 1.4 * u; height: width; radius: width / 2; color: "white"
        scale: root.dragging ? 1.25 : 1
        Behavior on scale { NumberAnimation { duration: 100 } }
    }
    MouseArea {
        anchors.fill: parent; preventStealing: true
        onPressed: (m) => { root.dragging = true; root.dragValue = root.at(m.x) }
        onPositionChanged: (m) => { if (pressed) root.dragValue = root.at(m.x) }
        onReleased: { root.dragging = false; root.committed(root.dragValue) }
        onCanceled: root.dragging = false
    }
}
