import QtQuick

// Full now-playing view for whatever source is casting (AirPlay, Spotify, Sendspin...). Opens from the ambient strip or
// the dashboard music card. View only: every control is a command to the core, and a control the active source cannot do
// (Store.can) is greyed out and inert.
Item {
    id: root
    property Item backdrop
    readonly property real u: Store.u
    readonly property bool shown: Store.nowPlayingOpen && Store.musicActive

    opacity: shown ? 1 : 0
    visible: opacity > 0
    Behavior on opacity { NumberAnimation { duration: 250 } }

    Rectangle { anchors.fill: parent; color: "#d90a0a0b" }                   // dim the photo behind
    MouseArea { anchors.fill: parent }                                       // swallow touches

    Glass {
        id: card
        backdrop: root.backdrop; watch: root.opacity
        flatOnly: true
        anchors.centerIn: parent
        width: parent.width - 8 * u; height: 35 * u
        radius: 2 * u
        flatTint: "#e6121216"

        // artwork
        Rectangle {
            id: art
            x: 3 * u; anchors.verticalCenter: parent.verticalCenter
            width: 26 * u; height: 26 * u; radius: 1.5 * u
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0; color: "#ff9a5a" }
                GradientStop { position: 0.5; color: "#c24a7a" }
                GradientStop { position: 1; color: "#4a2a8a" }
            }
            Image {
                anchors.fill: parent; source: Store.nowArt; visible: status === Image.Ready
                fillMode: Image.PreserveAspectCrop; asynchronous: true
            }
        }

        Column {
            id: info
            x: art.x + art.width + 3 * u; width: parent.width - x - 3 * u
            anchors.verticalCenter: parent.verticalCenter
            spacing: 0.4 * u

            // which source and which sender: makes a takeover visible
            Row {
                spacing: 0.6 * u
                Icon { name: "speaker"; size: 1.2 * u; anchors.verticalCenter: parent.verticalCenter; opacity: 0.7 }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: Store.musicActive ? (Store.music.source_label + (Store.music.client ? "  ·  " + Store.music.client : "")).toUpperCase() : ""
                    color: "#99f0ede8"; font.family: Store.sans; font.pixelSize: 0.8125 * u; font.letterSpacing: 0.12 * u
                }
            }
            Item { width: 1; height: 1.2 * u }
            Text {
                width: parent.width; elide: Text.ElideRight; maximumLineCount: 2; wrapMode: Text.Wrap
                text: Store.nowTitle; color: "#f0ede8"; font.family: Store.display; font.weight: Font.Light; font.pixelSize: 3 * u
            }
            Text { width: parent.width; elide: Text.ElideRight; text: Store.nowArtist
                   color: "#f0ede8"; font.family: Store.sans; font.pixelSize: 1.5 * u }
            Text { width: parent.width; elide: Text.ElideRight; text: Store.track ? Store.track.album : ""
                   color: "#99f0ede8"; font.family: Store.sans; font.pixelSize: 1.125 * u }
            Item { width: 1; height: 1.6 * u }

            // scrubber (inert when the source cannot seek or the length is unknown)
            Item {
                width: parent.width; height: 2.4 * u
                enabled: Store.can("seek") && Store.nowDuration > 0
                opacity: enabled ? 1 : 0.5
                MiniSlider {
                    anchors.fill: parent
                    value: Store.nowDuration > 0 ? Math.round(100 * Store.nowPosition / Store.nowDuration) : 0
                    onCommitted: (v) => Store.musicSeek(v / 100 * Store.nowDuration)
                }
            }
            Item {
                width: parent.width; height: 1.2 * u
                Text { text: Store.fmt(Store.nowPosition); color: "#99f0ede8"; font.family: Store.sans; font.pixelSize: 0.875 * u }
                Text { anchors.right: parent.right; visible: Store.nowDuration > 0; text: Store.fmt(Store.nowDuration)
                       color: "#99f0ede8"; font.family: Store.sans; font.pixelSize: 0.875 * u }
            }
            Item { width: 1; height: 0.8 * u }

            // transport
            Row {
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: 2 * u
                Tap {
                    width: 4 * u; height: 4 * u; enabled: Store.can("prev"); opacity: enabled ? 1 : 0.3
                    onClicked: Store.prevMedia()
                    Icon { name: "prev"; size: 2.2 * u; anchors.centerIn: parent }
                }
                Tap {
                    width: 5 * u; height: 5 * u; enabled: Store.can("pause") || Store.can("play"); opacity: enabled ? 1 : 0.3
                    onClicked: Store.toggleMedia()
                    Rectangle { anchors.fill: parent; radius: width / 2; color: "white" }
                    Icon { name: Store.musicPlaying ? "pause" : "play"; dark: true; size: 2.4 * u; anchors.centerIn: parent }
                }
                Tap {
                    width: 4 * u; height: 4 * u; enabled: Store.can("next"); opacity: enabled ? 1 : 0.3
                    onClicked: Store.nextMedia()
                    Icon { name: "next"; size: 2.2 * u; anchors.centerIn: parent }
                }
            }
            Item { width: 1; height: 0.8 * u }

            // device master volume (one level for every source)
            Row {
                width: parent.width; spacing: 1 * u
                Icon { name: "speaker"; size: 1.4 * u; anchors.verticalCenter: parent.verticalCenter; opacity: 0.7 }
                MiniSlider {
                    width: parent.width - 2.4 * u; anchors.verticalCenter: parent.verticalCenter
                    value: Store.musicActive ? Store.music.volume : 0
                    onCommitted: (v) => Store.musicVolume(v)
                }
            }
            Item { width: 1; height: 0.6 * u }
            Row {
                spacing: 1 * u
                Pill { visible: Store.libraryAvailable; icon: "speaker"; text: "Library"
                       onClicked: { Store.nowPlayingOpen = false; Store.openLibrary() } }
                Pill { text: "Stop"; icon: "close"; onClicked: Store.musicStop() }
            }
        }

        Tap {
            anchors.right: parent.right; anchors.rightMargin: 1 * u; y: 1 * u
            width: 3 * u; height: 3 * u
            onClicked: Store.nowPlayingOpen = false
            Icon { name: "close"; size: 1.4 * u; anchors.centerIn: parent; opacity: 0.6 }
        }
    }
}
