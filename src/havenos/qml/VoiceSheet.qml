import QtQuick

// Bottom sheet: 40-bar waveform driven every frame (FrameAnimation), state label, transcript.
Item {
    id: root
    property Item backdrop
    readonly property real u: Store.u
    readonly property bool shown: Store.voice !== "idle"

    // dim the screen behind
    Rectangle {
        anchors.fill: parent; color: "black"
        opacity: root.shown ? 0.4 : 0
        visible: opacity > 0
        Behavior on opacity { NumberAnimation { duration: 200 } }
    }

    Glass {
        id: sheet
        backdrop: root.backdrop
        watch: y
        flatOnly: true      // glass-over-glass: see README ("recursive sources") — flat tint here
        radius: 2 * u
        width: parent.width; height: 11.25 * u + radius
        y: root.shown ? root.height - 11.25 * u : root.height
        visible: y < root.height
        Behavior on y { NumberAnimation { duration: 280; easing.type: Easing.OutBack; easing.overshoot: 0.6 } }
        flatTint: "#d9121216"

        MouseArea { anchors.fill: parent }   // swallow touches

        Text {
            anchors.horizontalCenter: parent.horizontalCenter; y: 1.3 * u
            text: ({ idle: "", listening: "LISTENING…", processing: "THINKING…", responding: "SPEAKING…", error: "SOMETHING WENT WRONG" })[Store.voice]
            color: "#99f0ede8"; font.family: Store.sans; font.pixelSize: 0.8125 * u; font.letterSpacing: 0.12 * u
        }

        FrameAnimation { id: frames; running: sheet.visible }

        Row {
            id: bars
            anchors.horizontalCenter: parent.horizontalCenter; y: 2.8 * u
            height: 4 * u; spacing: 0.3 * u
            Repeater {
                model: 40
                Rectangle {
                    required property int index
                    readonly property real d: Math.abs(index - 19.5) / 19.5
                    readonly property real env: 1 - d * d * 0.85
                    readonly property real s: frames.elapsedTime
                    readonly property real amp: {
                        var v = Store.voice
                        if (v === "listening")
                            return (0.35 + 0.65 * Math.abs(Math.sin(s * 7 + index * 0.7) * Math.sin(s * 3.1 + index * 1.9))) * env
                        if (v === "processing")
                            return (0.12 + 0.1 * Math.sin(s * 2.4 - d * 4)) * env + 0.04
                        return (0.3 + 0.7 * Math.abs(Math.sin(s * 5 + index * 0.5))) * env * (0.6 + 0.4 * Math.sin(s * 1.7))
                    }
                    width: 0.28 * u; radius: width / 2; color: Store.voice === "error" ? "#e5484d" : "#4a9eff"
                    height: Math.max(0.06, amp) * bars.height
                    y: (bars.height - height) / 2
                }
            }
        }

        Text {
            anchors.horizontalCenter: parent.horizontalCenter; y: 7.6 * u
            text: Store.voice === "responding" ? Store.response : Store.transcript
            color: "#f0ede8"; font.family: Store.sans; font.pixelSize: 1.125 * u
        }

        Tap {
            anchors.right: parent.right; anchors.rightMargin: 1 * u; y: 0.75 * u
            width: 3 * u; height: 3 * u
            onClicked: Store.dismissVoice()
            Icon { name: "close"; size: 1.4 * u; anchors.centerIn: parent; opacity: 0.6 }
        }
    }
}
