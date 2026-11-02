import QtQuick

// Rooms: a list of rooms that have something to show, and a screen per room with its controls.
// Only entities exposed to Assist in Home Assistant ever get here (the core enforces that).
Item {
    id: root
    property Item backdrop
    readonly property real u: Store.u
    readonly property bool shown: Store.mode === "rooms"
    readonly property bool inRoom: Store.roomSelected !== ""
    // Controls first (one flat grid, already ordered by kind), sensors last. Section titles add nothing the icons do not.
    function flat(info) {
        var out = []
        if (!Store.roomView) return out
        for (var i = 0; i < Store.roomView.sections.length; i++)
            if (Store.roomView.sections[i].info === info) out = out.concat(Store.roomView.sections[i].items)
        return out
    }
    readonly property var controlItems: flat(false)
    readonly property var infoItems: flat(true)

    y: shown ? 0 : height
    visible: y < height
    Behavior on y { NumberAnimation { duration: root.shown ? 300 : 250; easing.type: root.shown ? Easing.OutCubic : Easing.InCubic } }

    Rectangle { anchors.fill: parent; color: "#f50a0a0d" }
    MouseArea { anchors.fill: parent }       // swallow touches meant for what is underneath

    Glass {
        id: header
        backdrop: root.backdrop; watch: root.y; flatOnly: true
        x: 2.5 * u; y: 2 * u; width: parent.width - 5 * u; height: 4.75 * u; radius: 1.75 * u
        Tap {
            id: backBtn; x: 0.9 * u; anchors.verticalCenter: parent.verticalCenter; width: 3.4 * u; height: 3.4 * u
            onClicked: Store.roomsBack()
            Rectangle { anchors.fill: parent; radius: width / 2; color: "#14ffffff" }
            Icon { name: "back"; size: 1.7 * u; anchors.centerIn: parent }
        }
        Text {
            anchors.left: backBtn.right; anchors.leftMargin: 1 * u; anchors.verticalCenter: parent.verticalCenter
            text: root.inRoom && Store.roomView ? Store.roomView.name : "Rooms"
            color: "#f0ede8"; font.family: Store.display; font.weight: Font.Light; font.pixelSize: 2.25 * u
        }
        Text {
            anchors.right: parent.right; anchors.rightMargin: 1.75 * u; anchors.verticalCenter: parent.verticalCenter
            visible: root.inRoom && Store.roomView && Store.roomView.here
            text: "This display is here"; color: "#4a9eff"; font.family: Store.sans; font.pixelSize: 0.95 * u
        }
    }

    // ---- empty / blocked states ----
    Column {
        visible: !root.inRoom && Store.rooms.length === 0
        anchors.centerIn: parent; width: parent.width * 0.6; spacing: 0.8 * u
        Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap
               text: Store.haExposure && !Store.haExposure.ok ? "Can't read Home Assistant's exposure settings" : "No rooms to show yet"
               color: "#f0ede8"; font.family: Store.display; font.weight: Font.Light; font.pixelSize: 2.2 * u }
        Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap
               text: Store.haExposure && !Store.haExposure.ok ? Store.haExposure.error
                     : "In Home Assistant, expose entities to Assist (Settings → Voice assistants → Expose) and give them an area."
               color: "#99f0ede8"; font.family: Store.sans; font.pixelSize: 1.05 * u }
    }

    // ---- room list ----
    Flickable {
        visible: !root.inRoom && Store.rooms.length > 0
        x: 2.5 * u; y: header.y + header.height + 1.2 * u; width: parent.width - 5 * u; height: parent.height - y - 1.5 * u
        contentWidth: width; contentHeight: roomFlow.height + 1 * u; clip: true
        Flow {
            id: roomFlow; width: parent.width; spacing: 1 * u
            Repeater {
                model: Store.rooms
                Tap {
                    required property var modelData
                    width: (roomFlow.width - 2 * roomFlow.spacing) / 3; height: 7.4 * u
                    onClicked: Store.selectRoom(modelData.id)
                    Rectangle { anchors.fill: parent; radius: 1.25 * u; color: modelData.here ? "#2e4a9eff" : "#990e0e12"
                                border.color: modelData.here ? "#994a9eff" : "#29ffffff"; border.width: 1 }
                    Column {
                        anchors.left: parent.left; anchors.leftMargin: 1.4 * u; anchors.right: parent.right; anchors.rightMargin: 1 * u
                        anchors.verticalCenter: parent.verticalCenter; spacing: 0.3 * u
                        Text { width: parent.width; elide: Text.ElideRight; text: modelData.name
                               color: "#f0ede8"; font.family: Store.display; font.weight: Font.Light; font.pixelSize: 1.9 * u }
                        Text { width: parent.width; elide: Text.ElideRight; text: modelData.summary
                               color: "#99f0ede8"; font.family: Store.sans; font.pixelSize: 0.95 * u }
                    }
                    Text { visible: modelData.here; anchors.right: parent.right; anchors.rightMargin: 1 * u; y: 0.8 * u
                           text: "HERE"; color: "#4a9eff"; font.family: Store.sans; font.pixelSize: 0.7 * u; font.letterSpacing: 0.1 * u }
                }
            }
        }
    }

    // ---- one room ----
    Flickable {
        id: roomScroll
        visible: root.inRoom && Store.roomView !== null
        x: 2.5 * u; y: header.y + header.height + 1.2 * u; width: parent.width - 5 * u; height: parent.height - y - 1.5 * u
        contentWidth: width; contentHeight: sections.height + 1 * u; clip: true
        onVisibleChanged: if (visible) contentY = 0
        Column {
            id: sections; width: parent.width; spacing: 1.4 * u
            Text { visible: root.controlItems.length === 0 && root.infoItems.length === 0; text: "Nothing in this room is exposed to Assist."
                   color: "#99f0ede8"; font.family: Store.sans; font.pixelSize: 1.05 * u }
            Flow {
                id: ctlFlow; width: parent.width; spacing: 0.9 * u
                Repeater {
                    model: root.controlItems
                    EntityCard { required property var modelData; e: modelData; width: (ctlFlow.width - 2 * ctlFlow.spacing) / 3 }
                }
            }
            Text { visible: root.infoItems.length > 0; text: "SENSORS"; color: "#99f0ede8"; font.family: Store.sans
                   font.pixelSize: 0.8125 * u; font.letterSpacing: 0.12 * u }
            Flow {
                id: infoFlow; width: parent.width; spacing: 0.9 * u; visible: root.infoItems.length > 0
                Repeater {
                    model: root.infoItems
                    Item {
                        required property var modelData
                        width: (infoFlow.width - 3 * infoFlow.spacing) / 4; height: 4.2 * u
                        Rectangle { anchors.fill: parent; radius: 1 * u; color: "#990e0e12"; border.color: "#29ffffff"; border.width: 1 }
                        Column { anchors.verticalCenter: parent.verticalCenter; anchors.left: parent.left; anchors.leftMargin: 1.1 * u
                                 anchors.right: parent.right; anchors.rightMargin: 0.8 * u; spacing: 0.1 * u
                            Text { width: parent.width; elide: Text.ElideRight; text: modelData.name; color: "#99f0ede8"
                                   font.family: Store.sans; font.pixelSize: 0.8 * u }
                            Text { width: parent.width; elide: Text.ElideRight; text: modelData.status; color: "#f0ede8"
                                   font.family: Store.display; font.pixelSize: 1.35 * u } }
                    }
                }
            }
        }
    }
}
