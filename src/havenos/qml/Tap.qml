import QtQuick

// Every tappable element: same press feedback (scale .95, 100 ms).
Item {
    id: root
    signal clicked()
    property alias pressed: ma.pressed
    scale: ma.pressed ? 0.95 : 1
    Behavior on scale { NumberAnimation { duration: 100; easing.type: Easing.OutQuad } }
    // the hit area is at least 44 px each way (a fingertip), even where the drawn button is smaller
    MouseArea { id: ma; anchors.centerIn: parent; width: Math.max(root.width, 44); height: Math.max(root.height, 44)
                onClicked: root.clicked() }
}
