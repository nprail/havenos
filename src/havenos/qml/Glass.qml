import QtQuick
import QtQuick.Effects

// Frosted-glass panel.  CSS gives you `backdrop-filter: blur()` in one line; in Qt Quick it is:
//   ShaderEffectSource (snapshot the region of the backdrop behind this panel)
//   -> MultiEffect (blur + saturation, masked to the rounded rect) -> tint + hairline border.
// Qt can't know when an ancestor moves, so panels that slide expose `watch` (bind it to the
// moving property) to re-aim the snapshot.
Item {
    id: glass
    property Item backdrop
    property real radius: 24 * Store.u / 16
    property bool flatOnly: false          // force the non-blurred look (e.g. glass-over-glass)
    property color tint: "#1affffff"       // rgba(255,255,255,.10)
    property color flatTint: "#8c0e0e12"   // rgba(14,14,18,.55)
    property var watch
    readonly property bool blurOn: Store.blur && !flatOnly && backdrop !== null

    default property alias content: contentItem.data

    function sync() {
        if (!blurOn || !backdrop) return
        var p = glass.mapToItem(backdrop, 0, 0)
        snap.sourceRect = Qt.rect(p.x, p.y, glass.width, glass.height)
    }
    onWatchChanged: sync()
    onXChanged: sync()
    onYChanged: sync()
    onWidthChanged: sync()
    onHeightChanged: sync()
    onBlurOnChanged: sync()
    Component.onCompleted: sync()

    ShaderEffectSource {
        id: snap
        anchors.fill: parent
        sourceItem: glass.blurOn ? glass.backdrop : null
        visible: false
        live: true
    }

    Rectangle {
        id: mask
        anchors.fill: parent
        radius: glass.radius
        layer.enabled: true
        visible: false
    }

    MultiEffect {
        anchors.fill: parent
        visible: glass.blurOn
        source: snap
        blurEnabled: true
        blurMax: 32
        blur: 0.8
        saturation: 0.3
        maskEnabled: true
        maskSource: mask
        autoPaddingEnabled: false
    }

    Rectangle {
        anchors.fill: parent
        radius: glass.radius
        color: glass.blurOn ? glass.tint : glass.flatTint
        border.color: "#29ffffff"
        border.width: 1
    }

    Item { id: contentItem; anchors.fill: parent }
}
