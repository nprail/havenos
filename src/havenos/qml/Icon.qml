import QtQuick

// SVG path data; rasterised once at 96px and scaled.
Image {
    property string name
    property real size: 24 * Store.u / 16
    property bool dark: false
    width: size; height: size
    source: name === "" ? "" : Qt.resolvedUrl("../assets/icons/" + name + (dark ? "-dark" : "") + ".svg")
    sourceSize: Qt.size(96, 96)
    smooth: true
    mipmap: true
}
