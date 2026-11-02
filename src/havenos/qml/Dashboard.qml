import QtQuick

// Slides up from the bottom (300 ms OutCubic). Photo dims behind it (dim layer lives in the backdrop).
Item {
    id: root
    property Item backdrop
    readonly property real u: Store.u
    readonly property bool active: Store.screen === "active"

    y: active ? 0 : height
    visible: y < height
    Behavior on y { NumberAnimation { duration: root.active ? 300 : 250; easing.type: root.active ? Easing.OutCubic : Easing.InCubic } }

    GestureArea {
        anchors.fill: parent
        enabled: root.active
        onSwipedDown: { Store.gesture("swipe_down"); Store.setScreen("ambient") }
    }

    // header bar
    Glass {
        id: header
        backdrop: root.backdrop; watch: root.y
        x: 2.5 * u; y: 2 * u; width: parent.width - 5 * u; height: 4.75 * u
        radius: 1.75 * u
        Row {
            anchors.left: parent.left; anchors.leftMargin: 1.75 * u; anchors.verticalCenter: parent.verticalCenter
            spacing: 1 * u
            Text {
                id: timeTxt
                text: { var d = new Date(Store.now); var h = d.getHours() % 12; if (h === 0) h = 12
                        var m = d.getMinutes(); return h + ":" + (m < 10 ? "0" : "") + m }
                color: "#f0ede8"; font.family: Store.display; font.weight: Font.ExtraLight; font.pixelSize: 2.25 * u
            }
            Text {
                id: dateTxt
                anchors.baseline: timeTxt.baseline
                text: Qt.formatDate(new Date(Store.now), "dddd, MMMM d")
                color: "#99f0ede8"; font.family: Store.sans; font.pixelSize: 1.0625 * u
            }
        }
        Row {
            anchors.right: parent.right; anchors.rightMargin: 1.75 * u; anchors.verticalCenter: parent.verticalCenter
            spacing: 1.25 * u
            Pill { icon: "home"; text: "Rooms"; anchors.verticalCenter: parent.verticalCenter; onClicked: Store.openRooms() }
            Tap {
                width: 3 * u; height: 3 * u; anchors.verticalCenter: parent.verticalCenter
                onClicked: Store.openNotifications()
                Icon { name: "bell"; size: 1.6 * u; anchors.centerIn: parent }
                Rectangle {
                    visible: Store.notifications.length > 0
                    x: parent.width - 1.35 * u; y: -0.2 * u; width: Math.max(1.3 * u, cnt.width + 0.7 * u); height: 1.3 * u; radius: height / 2; color: "#e5534b"
                    Text { id: cnt; anchors.centerIn: parent; text: Store.notifications.length > 9 ? "9+" : Store.notifications.length
                           color: "white"; font.family: Store.sans; font.pixelSize: 0.8 * u; font.weight: Font.Medium }
                }
            }
            Tap {
                width: 3 * u; height: 3 * u; anchors.verticalCenter: parent.verticalCenter
                onClicked: Store.setupOpen = true
                Icon { name: "gear"; size: 1.6 * u; anchors.centerIn: parent }
            }
            WeatherIcon { visible: Store.weather !== null; kind: Store.weather ? Store.weather.icon : "sun"; size: 1.6 * u; spin: false; anchors.verticalCenter: parent.verticalCenter }
            Text { visible: Store.weather !== null; text: Store.weather && Store.weather.temp !== null ? Store.weather.temp + "°" : ""; color: "#f0ede8"; font.family: Store.display; font.weight: Font.Light
                   font.pixelSize: 1.75 * u; anchors.verticalCenter: parent.verticalCenter }
        }
    }

    // three cards
    Row {
        id: cards
        x: 2.5 * u; y: header.y + header.height + 1 * u
        width: parent.width - 5 * u; height: parent.height - y - 8.5 * u
        spacing: 1 * u
        readonly property real cw: (width - 2 * spacing) / 3

        // ---- weather ----
        Glass {
            backdrop: root.backdrop; watch: root.y
            width: cards.cw; height: cards.height; radius: 1.5 * u
            Text { x: 1.5 * u; y: 1.5 * u; text: "WEATHER"; color: "#99f0ede8"; font.family: Store.sans
                   font.pixelSize: 0.8125 * u; font.letterSpacing: 0.12 * u }
            Row {
                x: 1.5 * u; y: 3.4 * u; spacing: 1 * u
                Text { text: Store.weather && Store.weather.temp !== null ? Store.weather.temp + "°" : "--"; color: "#f0ede8"; font.family: Store.display; font.weight: Font.ExtraLight; font.pixelSize: 3.5 * u }
                Column {
                    anchors.verticalCenter: parent.verticalCenter
                    Row { spacing: 0.5 * u
                        WeatherIcon { kind: Store.weather ? Store.weather.icon : "sun"; size: 1.4 * u; spin: false }
                        Text { text: Store.weather ? Store.weather.condition : "No weather entity"; color: "#f0ede8"; font.family: Store.sans; font.pixelSize: 1.0625 * u } }
                    Text { visible: Store.weather !== null && Store.weather.high !== null; text: Store.weather ? "H " + Store.weather.high + "° · L " + Store.weather.low + "°" : ""; color: "#99f0ede8"; font.family: Store.sans; font.pixelSize: 0.9375 * u }
                }
            }
            Row {
                anchors.bottom: parent.bottom; anchors.bottomMargin: 1.5 * u
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: 0.5 * u
                Repeater {
                    model: Store.weather ? Store.weather.hourly : []
                    Rectangle {
                        required property var modelData
                        width: (cards.cw - 3 * u - 3 * 0.5 * u) / 4; height: 5.2 * u; radius: 1 * u
                        color: "#0dffffff"
                        Column {
                            anchors.centerIn: parent; spacing: 0.15 * u
                            Text { anchors.horizontalCenter: parent.horizontalCenter; text: modelData.label
                                   color: "#99f0ede8"; font.family: Store.sans; font.pixelSize: 0.75 * u }
                            WeatherIcon { anchors.horizontalCenter: parent.horizontalCenter; kind: modelData.icon; size: 1.4 * u; spin: false }
                            Text { anchors.horizontalCenter: parent.horizontalCenter; text: modelData.temp !== null ? modelData.temp + "°" : "--"
                                   color: "#f0ede8"; font.family: Store.display; font.pixelSize: 1.0625 * u }
                        }
                    }
                }
            }
        }

        // ---- music ----
        Glass {
            id: musicCard
            backdrop: root.backdrop; watch: root.y
            width: cards.cw; height: cards.height; radius: 1.5 * u
            Text { x: 1.5 * u; y: 1.5 * u; text: "MUSIC"; color: "#99f0ede8"; font.family: Store.sans
                   font.pixelSize: 0.8125 * u; font.letterSpacing: 0.12 * u }
            Tap {
                visible: Store.libraryAvailable
                anchors.right: parent.right; anchors.rightMargin: 1 * u; y: 0.9 * u; width: 6.5 * u; height: 2.6 * u
                onClicked: Store.openLibrary()
                Rectangle { anchors.fill: parent; radius: height / 2; color: "#26ffffff" }
                Text { anchors.centerIn: parent; text: "Library"; color: "#f0ede8"; font.family: Store.sans; font.pixelSize: 1 * u }
            }
            Rectangle {
                id: albumArt
                x: 1.5 * u; y: 3.4 * u; width: 5 * u; height: 5 * u; radius: 1 * u
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
                MouseArea { anchors.fill: parent; enabled: Store.musicActive; onClicked: Store.nowPlayingOpen = true }
            }
            Column {
                anchors.left: albumArt.right; anchors.leftMargin: 1 * u; anchors.verticalCenter: albumArt.verticalCenter
                Text { text: Store.musicShown ? Store.nowTitle : "Nothing playing"; color: "#f0ede8"; font.family: Store.sans; font.pixelSize: 1.25 * u }
                Text { text: Store.musicShown ? Store.nowArtist : ""; color: "#99f0ede8"; font.family: Store.sans; font.pixelSize: 0.9375 * u }
            }
            Rectangle {
                x: 1.5 * u; y: albumArt.y + albumArt.height + 1 * u
                width: parent.width - 3 * u; height: 0.25 * u; radius: height / 2; color: "#26ffffff"
                Rectangle {
                    height: parent.height; radius: height / 2; color: "#4a9eff"
                    width: parent.width * (Store.nowDuration > 0 ? Math.min(1, Store.nowPosition / Store.nowDuration) : 0)
                }
            }
            Row {
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: parent.bottom; anchors.bottomMargin: 1.5 * u
                spacing: 1.25 * u
                Tap { width: 3 * u; height: 3 * u; onClicked: Store.prevMedia(); Icon { name: "prev"; size: 1.6 * u; anchors.centerIn: parent } }
                Tap {
                    width: 3.5 * u; height: 3.5 * u
                    onClicked: Store.toggleMedia()
                    Rectangle { anchors.fill: parent; radius: width / 2; color: "white" }
                    Icon { name: Store.musicPlaying ? "pause" : "play"; dark: true; size: 1.75 * u; anchors.centerIn: parent }
                }
                Tap { width: 3 * u; height: 3 * u; onClicked: Store.nextMedia(); Icon { name: "next"; size: 1.6 * u; anchors.centerIn: parent } }
            }
        }

        // ---- timers ----
        Glass {
            backdrop: root.backdrop; watch: root.y
            width: cards.cw; height: cards.height; radius: 1.5 * u
            Text { x: 1.5 * u; y: 1.5 * u; text: "TIMERS"; color: "#99f0ede8"; font.family: Store.sans
                   font.pixelSize: 0.8125 * u; font.letterSpacing: 0.12 * u }
            Column {
                x: 1.5 * u; y: 3.4 * u; width: parent.width - 3 * u; spacing: 0.75 * u
                Text { visible: Store.timers.length === 0; text: "No active timers"; color: "#99f0ede8"
                       font.family: Store.sans; font.pixelSize: 1 * u; topPadding: 1.5 * u
                       anchors.horizontalCenter: parent.horizontalCenter }
                Repeater {
                    model: Math.min(3, Store.timers.length)
                    Item {
                        required property int index
                        readonly property var t: Store.timers[index]
                        readonly property real secs: Store.timerSecs(t)
                        width: parent.width; height: 3.25 * u
                        Item {
                            id: ring
                            width: 3.25 * u; height: 3.25 * u
                            Rectangle { anchors.fill: parent; anchors.margins: 0.2 * u; radius: width / 2; color: "transparent"
                                        border.color: "#26ffffff"; border.width: 0.19 * u }
                            Canvas {
                                anchors.fill: parent
                                property real frac: parent.parent.t ? Math.max(0, Math.min(1, parent.parent.secs / parent.parent.t.total)) : 0
                                onFracChanged: requestPaint()
                                onPaint: {
                                    var c = getContext("2d"); c.reset()
                                    c.strokeStyle = "#4a9eff"; c.lineWidth = 0.19 * Store.u; c.lineCap = "round"
                                    c.beginPath()
                                    c.arc(width / 2, height / 2, width / 2 - 0.2 * Store.u - 0.1 * Store.u,
                                          -Math.PI / 2, -Math.PI / 2 + 2 * Math.PI * frac)
                                    c.stroke()
                                }
                            }
                        }
                        Column {
                            anchors.left: ring.right; anchors.leftMargin: 1 * u; anchors.verticalCenter: parent.verticalCenter
                            Text { text: t ? t.label + (t.paused ? " · paused" : "") : ""; color: "#f0ede8"; font.family: Store.sans; font.pixelSize: 1.0625 * u }
                            Text { text: Store.fmt(secs); color: "#f0ede8"; opacity: t && t.paused ? 0.5 : 1; font.family: Store.display; font.weight: Font.Light
                                   font.pixelSize: 1.5 * u; font.features: { "tnum": 1 } }
                        }
                        Tap {
                            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                            width: 3 * u; height: 3 * u
                            onClicked: Store.cancelTimer(t.id)
                            Icon { name: "close"; size: 1.25 * u; anchors.centerIn: parent; opacity: 0.6 }
                        }
                    }
                }
            }
            Tap {
                anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
                anchors.margins: 1.5 * u; height: 3 * u
                onClicked: Store.addTimer(10, "Demo (10s)")
                Rectangle { anchors.fill: parent; radius: 1 * u; color: "transparent"; border.color: "#33ffffff"; border.width: 1 }
                Row {
                    anchors.centerIn: parent; spacing: 0.5 * u
                    Icon { name: "plus"; size: 1.1 * u; anchors.verticalCenter: parent.verticalCenter }
                    Text { text: "New timer (10 s demo)"; color: "#f0ede8"; font.family: Store.sans; font.pixelSize: 1 * u
                           anchors.verticalCenter: parent.verticalCenter }
                }
            }
        }
    }

    // quick controls + mic
    Row {
        x: 2.5 * u; y: parent.height - 7.5 * u; spacing: 1 * u
        Repeater {
            model: Store.controls.slice(0, 6)
            Item {
                required property var modelData
                width: 7.5 * u; height: 5 * u
                Glass {
                    anchors.fill: parent; backdrop: root.backdrop; watch: root.y; radius: 1 * u
                }
                Rectangle {     // lit tile when the entity is on
                    anchors.fill: parent; radius: 1 * u; color: "#334a9eff"
                    border.color: "#804a9eff"; border.width: 1
                    visible: modelData.on
                }
                Tap {
                    anchors.fill: parent
                    enabled: modelData.actionable
                    onClicked: Store.toggleControl(modelData.id)
                    Column {
                        anchors.centerIn: parent; spacing: 0.2 * u
                        Icon { anchors.horizontalCenter: parent.horizontalCenter; name: modelData.icon; size: 1.6 * u }
                        Text { anchors.horizontalCenter: parent.horizontalCenter; text: modelData.label
                               width: 7 * u; horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight
                               color: "#f0ede8"; font.family: Store.sans; font.pixelSize: 0.8125 * u }
                        Text { anchors.horizontalCenter: parent.horizontalCenter; text: modelData.status
                               visible: text !== ""
                               color: "#99f0ede8"; font.family: Store.sans; font.pixelSize: 0.6875 * u }
                    }
                }
            }
        }
    }
    Tap {
        x: parent.width - 2.5 * u - width; y: parent.height - 7.5 * u + 0.5 * u
        width: 4 * u; height: 4 * u
        onClicked: Store.startVoice()
        Rectangle { anchors.fill: parent; radius: width / 2; color: "#4a9eff" }
        Icon { name: "mic"; dark: true; size: 1.9 * u; anchors.centerIn: parent }
    }
}
