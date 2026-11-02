import QtQuick

// kind: "sun" | "partly" | "cloud" (what the core's weather mapping emits)
Item {
    id: root
    property string kind: "sun"
    property real size: 24 * Store.u / 16
    property bool spin: true
    width: size; height: size
    SunIcon { visible: root.kind === "sun"; size: root.size; spin: root.spin; anchors.centerIn: parent }
    Icon { visible: root.kind !== "sun"; name: root.kind === "partly" ? "partly" : "cloud"; size: root.size; anchors.centerIn: parent }
}
