import QtQuick

// Static core + rays that turn 30 degrees every 5 s. A rotation that never stops redraws the scene on every vsync
// (measured: ~150% of a core on an idle ambient screen), so the rays only animate for a moment at each step.
Item {
    id: root
    property real size: 24 * Store.u / 16
    property bool spin: true
    width: size; height: size
    Icon { name: "sun-core"; size: root.size; anchors.centerIn: parent }
    Icon {
        id: rays
        name: "sun-rays"; size: root.size; anchors.centerIn: parent
        Behavior on rotation { NumberAnimation { duration: 700; easing.type: Easing.InOutQuad } }
    }
    Timer {
        interval: 5000; repeat: true; running: root.spin && root.visible
        onTriggered: rays.rotation += 30
    }
}
