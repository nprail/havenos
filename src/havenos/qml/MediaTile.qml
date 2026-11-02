import QtQuick

// The music tile of the live screen: whatever is casting to this display. View only. Tapping it (or the controls hint)
// opens the control view (NowPlaying) on top, without leaving the live screen; the play/pause button works in place.
Item {
    id: tile
    readonly property real u: Store.u
    readonly property bool wide: width >= height * 1.25
    // everything scales with the tile, so the same item is a full screen, a half or a third
    readonly property real k: Math.max(0.7, Math.min(1.5, Math.min(width / (34 * u), height / (26 * u))))
    readonly property real pad: 2 * u * Math.min(1, k + 0.2)
    // a tall tile gives the art whatever the text and button leave, so everything always fits, whatever the split
    readonly property real artSize: wide ? Math.min(height - 2 * pad, width * 0.42)
                                         : Math.max(height * 0.2, Math.min(width - 2 * pad, height - 2 * pad - infoGap - info.height))

    Rectangle {
        anchors.fill: parent; radius: 2 * u
        color: "#d9121216"; border.color: "#1affffff"; border.width: 1
    }
    MouseArea { anchors.fill: parent; onClicked: { Store.gesture("tap"); Store.nowPlayingOpen = true } }

    // a tall tile centres art + text as one block, so a full portrait screen has no dead space at the bottom
    readonly property real infoGap: pad * 0.6
    readonly property real blockTop: Math.max(pad, (height - artSize - infoGap - info.height) / 2)

    Rectangle {
        id: art
        x: tile.wide ? tile.pad : (tile.width - width) / 2
        y: tile.wide ? (tile.height - height) / 2 : tile.blockTop
        width: tile.artSize; height: width; radius: 1.5 * u * tile.k
        opacity: Store.musicPlaying ? 1 : 0.55
        Behavior on opacity { NumberAnimation { duration: 250 } }
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
        x: tile.wide ? art.x + art.width + tile.pad * 1.2 : tile.pad
        y: tile.wide ? (tile.height - height) / 2 : art.y + art.height + tile.infoGap
        width: tile.width - x - tile.pad
        spacing: 0.45 * u * tile.k

        Row {
            spacing: 0.6 * u
            Icon { name: "speaker"; size: 1.2 * u * Math.max(1, tile.k * 0.9); anchors.verticalCenter: parent.verticalCenter; opacity: 0.7 }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: Store.musicActive ? ((Store.musicPlaying ? "" : "Paused  ·  ") + Store.music.source_label
                                           + (Store.music.client ? "  ·  " + Store.music.client : "")).toUpperCase() : ""
                color: "#99f0ede8"; font.family: Store.sans; font.pixelSize: 0.8125 * u * Math.max(1, tile.k * 0.9)
                font.letterSpacing: 0.12 * u
            }
        }
        Text {
            width: parent.width; elide: Text.ElideRight; wrapMode: Text.Wrap; maximumLineCount: tile.wide ? 2 : 3
            text: Store.nowTitle; color: "#f0ede8"; font.family: Store.display; font.weight: Font.Light
            font.pixelSize: 3 * u * tile.k
        }
        Text { width: parent.width; elide: Text.ElideRight; text: Store.nowArtist
               color: "#f0ede8"; font.family: Store.sans; font.pixelSize: 1.5 * u * tile.k }
        Text { width: parent.width; elide: Text.ElideRight; text: Store.track ? Store.track.album : ""
               visible: text !== "" && tile.height > 16 * u
               color: "#99f0ede8"; font.family: Store.sans; font.pixelSize: 1.1 * u * tile.k }
        Item { width: 1; height: 0.6 * u * tile.k }

        // progress (view only: seeking is in the control view)
        Item {
            width: parent.width; height: 0.4 * u; visible: Store.nowDuration > 0
            Rectangle { anchors.fill: parent; radius: height / 2; color: "#26ffffff" }
            Rectangle {
                height: parent.height; radius: height / 2; color: "#4a9eff"
                width: Store.nowDuration > 0 ? parent.width * Math.min(1, Store.nowPosition / Store.nowDuration) : 0
            }
        }
        Item {
            width: parent.width; height: 1.2 * u; visible: Store.nowDuration > 0
            Text { text: Store.fmt(Store.nowPosition); color: "#99f0ede8"; font.family: Store.sans; font.pixelSize: 0.875 * u }
            Text { anchors.right: parent.right; text: Store.fmt(Store.nowDuration)
                   color: "#99f0ede8"; font.family: Store.sans; font.pixelSize: 0.875 * u }
        }
        Item { width: 1; height: 0.5 * u * tile.k }

        Row {
            spacing: 1.2 * u
            Tap {
                width: (tile.wide ? 4.6 : 3.8) * u * Math.max(0.9, tile.k); height: width
                enabled: Store.can("pause") || Store.can("play"); opacity: enabled ? 1 : 0.3
                onClicked: Store.toggleMedia()
                Rectangle { anchors.fill: parent; radius: width / 2; color: "white" }
                Icon { name: Store.musicPlaying ? "pause" : "play"; dark: true; size: parent.width * 0.48; anchors.centerIn: parent }
            }
            Pill { text: "Controls"; icon: "gear"; anchors.verticalCenter: parent.verticalCenter
                   onClicked: Store.nowPlayingOpen = true }
        }
    }
}
