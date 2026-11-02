import QtQuick
import QtQuick.Controls.Basic

// Search and browse the Music Assistant library, and play an item on this display. View only: typing and tapping are
// commands to the core (library.search / library.play); the rows come from Store.library.
Item {
    id: root
    property Item backdrop
    readonly property real u: Store.u
    readonly property bool shown: Store.libraryOpen && Store.libraryAvailable
    readonly property var lib: Store.library

    // sections -> one flat list of header and item rows
    readonly property var rows: {
        var out = []
        var secs = lib ? lib.sections : []
        for (var i = 0; i < secs.length; ++i) {
            out.push({ header: secs[i].title })
            for (var j = 0; j < secs[i].items.length; ++j) out.push(secs[i].items[j])
        }
        return out
    }

    opacity: shown ? 1 : 0
    visible: opacity > 0
    Behavior on opacity { NumberAnimation { duration: 250 } }
    // the search words, when the core (a spoken search) rather than the keyboard changed them
    property bool settingFromCore: false
    readonly property string coreQuery: Store.library ? Store.library.query : ""
    onCoreQueryChanged: if (search.text !== coreQuery && !search.activeFocus) {
        settingFromCore = true; search.text = coreQuery; settingFromCore = false
    }
    onShownChanged: if (!shown) { search.focus = false; root.parent.forceActiveFocus() }

    Rectangle { anchors.fill: parent; color: "#fa0a0a0d" }
    MouseArea { anchors.fill: parent }

    Glass {
        id: header
        backdrop: root.backdrop; watch: root.opacity; flatOnly: true
        x: 2.5 * u; y: 2 * u; width: parent.width - 5 * u; height: 4.75 * u; radius: 1.75 * u
        Tap {
            x: 1 * u; anchors.verticalCenter: parent.verticalCenter; width: 3 * u; height: 3 * u
            onClicked: Store.libraryOpen = false
            Icon { name: "back"; size: 1.6 * u; anchors.centerIn: parent }
        }
        TextField {
            id: search
            anchors.left: parent.left; anchors.leftMargin: 4.5 * u
            anchors.right: parent.right; anchors.rightMargin: (Store.voiceReady ? 5 : 1.5) * u
            anchors.verticalCenter: parent.verticalCenter
            placeholderText: Store.library && Store.library.listening ? "Listening…" : "Search your music"
            color: "#f0ede8"; placeholderTextColor: "#80f0ede8"
            font.family: Store.sans; font.pixelSize: 1.5 * u
            background: Item {}
            inputMethodHints: Qt.ImhNoPredictiveText
            onAccepted: Store.searchLibrary(text)
            onTextChanged: if (!root.settingFromCore) debounce.restart()
            Timer { id: debounce; interval: 450; onTriggered: Store.searchLibrary(search.text) }
        }
        // A spoken search: the core records, transcribes and searches; the words appear in the box.
        Tap {
            visible: Store.voiceReady
            anchors.right: parent.right; anchors.rightMargin: 0.75 * u; anchors.verticalCenter: parent.verticalCenter
            width: 3.5 * u; height: 3.5 * u
            onClicked: Store.voiceSearchLibrary()
            Rectangle { anchors.fill: parent; radius: width / 2
                        color: Store.library && Store.library.listening ? "#e5484d" : "#4a9eff" }
            Icon { name: "mic"; dark: true; size: 1.6 * u; anchors.centerIn: parent }
        }
    }

    ListView {
        id: list
        anchors { left: parent.left; right: parent.right; top: header.bottom; bottom: parent.bottom
                  leftMargin: 2.5 * u; rightMargin: 2.5 * u; topMargin: 1 * u }
        clip: true; spacing: 0.4 * u
        model: root.rows
        delegate: Item {
            width: list.width
            height: modelData.header !== undefined ? 3.2 * u : 5.6 * u
            Text {
                visible: modelData.header !== undefined
                anchors.bottom: parent.bottom; anchors.bottomMargin: 0.5 * u
                text: (modelData.header || "").toUpperCase(); color: "#99f0ede8"
                font.family: Store.sans; font.pixelSize: 0.8125 * u; font.letterSpacing: 0.12 * u
            }
            Tap {
                visible: modelData.header === undefined
                anchors.fill: parent
                onClicked: Store.playLibrary(modelData.uri)
                Rectangle { anchors.fill: parent; radius: 1 * u; color: "#14ffffff" }
                Rectangle {
                    id: thumb
                    x: 0.5 * u; anchors.verticalCenter: parent.verticalCenter; width: 4.6 * u; height: width; radius: 0.8 * u
                    color: "#26ffffff"
                    Image { anchors.fill: parent; source: modelData.art || ""; visible: status === Image.Ready
                            fillMode: Image.PreserveAspectCrop; asynchronous: true; sourceSize.width: 256; sourceSize.height: 256 }
                }
                Column {
                    anchors.left: thumb.right; anchors.leftMargin: 1.2 * u; anchors.right: parent.right; anchors.rightMargin: 1 * u
                    anchors.verticalCenter: parent.verticalCenter
                    Text { width: parent.width; elide: Text.ElideRight; text: modelData.name || ""
                           color: "#f0ede8"; font.family: Store.sans; font.pixelSize: 1.375 * u }
                    Text { width: parent.width; elide: Text.ElideRight; text: modelData.subtitle || ""
                           color: "#99f0ede8"; font.family: Store.sans; font.pixelSize: 1 * u }
                }
            }
        }
    }

    Text {                                   // busy / empty / error, centred in the list area
        anchors.centerIn: list
        visible: root.rows.length === 0
        width: list.width * 0.8; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
        text: !lib ? "" : lib.busy ? "Loading…" : lib.error
        color: "#99f0ede8"; font.family: Store.sans; font.pixelSize: 1.5 * u
    }
}
