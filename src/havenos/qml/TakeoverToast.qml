import QtQuick

// Names the new source when one takes the speaker from another ("AirPlay · Nick's iPhone"). Driven by music.takeover.seq.
Item {
    id: root
    property Item backdrop
    readonly property real u: Store.u
    readonly property var tk: Store.musicActive && Store.music.takeover ? Store.music.takeover : null
    readonly property int seq: tk ? tk.seq : 0
    property string line: ""
    property bool up: false

    onSeqChanged: if (seq > 0 && tk) {
        line = tk.source + (tk.client ? "  ·  " + tk.client : "")
        up = true; hide.restart()
    }
    Timer { id: hide; interval: 3500; onTriggered: root.up = false }

    Glass {
        backdrop: root.backdrop; watch: y; flatOnly: true
        anchors.horizontalCenter: parent.horizontalCenter
        y: root.up ? 5.5 * u : -height - u
        Behavior on y { NumberAnimation { duration: 300; easing.type: Easing.OutCubic } }
        width: label.implicitWidth + 4 * u; height: 4 * u; radius: 2 * u
        Row {
            anchors.centerIn: parent; spacing: 0.8 * u
            Icon { name: "speaker"; size: 1.4 * u; anchors.verticalCenter: parent.verticalCenter }
            Text { id: label; text: "Now playing from " + root.line; color: "#f0ede8"
                   font.family: Store.sans; font.pixelSize: 1.2 * u; anchors.verticalCenter: parent.verticalCenter }
        }
    }
}
