import QtQuick
import QtQuick.Effects

// Landscape: cover.  Portrait: blurred, scaled copy behind + original letterboxed.
Item {
    id: layer
    property url source
    property bool portrait: false      // latched when the image finishes loading (a binding would loop with fillMode)
    readonly property bool ready: fg.status === Image.Ready && (!portrait || bg.status === Image.Ready)

    Rectangle { anchors.fill: parent; color: "#0a0a0b" }

    // Tiny decode for the backdrop — the blur hides the lost detail and it costs almost nothing.
    Image {
        id: bg
        anchors.fill: parent
        source: layer.portrait ? layer.source : ""
        asynchronous: true
        fillMode: Image.PreserveAspectCrop
        sourceSize.width: 200
        visible: false
    }
    MultiEffect {
        anchors.fill: parent
        visible: layer.portrait
        source: bg
        scale: 1.1
        blurEnabled: true
        blurMax: 64
        blur: 1.0
        autoPaddingEnabled: false
    }

    Image {
        id: fg
        anchors.fill: parent
        source: layer.source
        asynchronous: true
        fillMode: layer.portrait ? Image.PreserveAspectFit : Image.PreserveAspectCrop
        onStatusChanged: {
            if (status === Image.Ready) layer.portrait = implicitHeight > implicitWidth
            else if (status === Image.Null) layer.portrait = false
        }
    }
}
