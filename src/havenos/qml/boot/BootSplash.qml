import QtQuick

// The first thing on screen, and the last part of the boot: the same picture as the Plymouth theme in deploy/plymouth
// (dark, the sun with turning rays, the name), so the hand-over from the boot splash shows no jump. Sizes match
// havenos.script. It covers the window until the interface (Scene.qml) has its first photo, or after a while, so a
// source that never delivers does not leave it up. It must not use Store or the core: it is shown while Python is
// still importing them.
Rectangle {
    id: root
    property bool photosReady: false
    property bool timedOut: false
    readonly property real sun: Math.min(width, height) * 0.20
    readonly property real cy: height / 2 - sun * 0.25
    color: "#0a0a0b"
    z: 80
    opacity: photosReady || timedOut ? 0 : 1
    visible: opacity > 0
    Behavior on opacity { NumberAnimation { duration: 700; easing.type: Easing.InOutQuad } }

    Timer { interval: 30000; running: root.visible; onTriggered: root.timedOut = true }

    Item {
        width: root.sun; height: root.sun
        x: (root.width - root.sun) / 2; y: root.cy - root.sun / 2
        Image { anchors.fill: parent; source: Qt.resolvedUrl("../../assets/icons/sun-core.svg"); sourceSize: Qt.size(96, 96); smooth: true; mipmap: true }
        Image {
            id: rays
            anchors.fill: parent; source: Qt.resolvedUrl("../../assets/icons/sun-rays.svg"); sourceSize: Qt.size(96, 96); smooth: true; mipmap: true
            Behavior on rotation { NumberAnimation { duration: 720; easing.type: Easing.InOutQuad } }   // a step at a time, as the boot splash
        }
        Timer { interval: 1200; repeat: true; running: root.visible; onTriggered: rays.rotation += 30 }
    }
    Text {
        text: "havenOS"
        anchors.horizontalCenter: parent.horizontalCenter
        y: root.cy + root.sun * 0.9 + (root.sun * 1.9 * 110 / 520 - height) / 2
        color: "#f0ede8"; opacity: 0.85
        font.family: "Urbanist"; font.weight: Font.Light
        font.pixelSize: root.sun * 1.9 * 72 / 520; font.letterSpacing: root.sun * 1.9 * 6 / 520
    }
    MouseArea { anchors.fill: parent }       // swallow touches while it is up
}
