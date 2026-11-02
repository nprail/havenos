import QtQuick

// Resting screen: clock (bottom-left), weather (bottom-right), timer pill, now-playing strip.
Item {
    id: root
    property Item backdrop
    readonly property real u: Store.u
    readonly property bool active: Store.screen === "active"
    readonly property real panelBottom: Store.musicShown ? 6.5 * u : 2.5 * u

    readonly property bool hidden: active || Store.liveShown      // the live screen replaces the resting one while it has something to show
    opacity: hidden ? 0 : 1
    visible: opacity > 0
    Behavior on opacity { NumberAnimation { duration: 250 } }

    function clockParts() {
        var d = new Date(Store.now)
        var h = d.getHours() % 12; if (h === 0) h = 12
        var mm = d.getMinutes(); mm = (mm < 10 ? "0" : "") + mm
        return { time: h + ":" + mm, ampm: d.getHours() >= 12 ? "PM" : "AM",
                 date: Qt.formatDate(d, "dddd, MMMM d") }
    }
    readonly property var clock: clockParts()

    GestureArea {
        anchors.fill: parent
        enabled: !root.hidden
        onTapped: { Store.gesture("tap"); Store.setScreen("active") }
        onSwipedX: (dir) => { Store.gesture(dir > 0 ? "swipe_left" : "swipe_right"); Store.nextPhoto(dir) }
    }

    // timer pill
    Glass {
        id: pill
        backdrop: root.backdrop
        visible: Store.timers.length > 0
        width: pillRow.width + 3.2 * u; height: 3 * u
        radius: height / 2
        anchors.horizontalCenter: parent.horizontalCenter
        y: 1.5 * u
        Row {
            id: pillRow
            anchors.centerIn: parent
            spacing: 0.5 * u
            Icon { name: "timer"; size: 1.25 * u; anchors.verticalCenter: parent.verticalCenter }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: Store.timers.length ? Store.fmt(Store.timerSecs(Store.timers[0])) : ""
                color: "#f0ede8"; font.family: Store.display; font.weight: Font.Light
                font.pixelSize: 1.25 * u; font.features: { "tnum": 1 }
            }
        }
    }

    // clock
    Glass {
        id: clockPanel
        backdrop: root.backdrop
        watch: anchors.bottomMargin
        width: clockCol.width + 3.5 * u; height: clockCol.height + 2.5 * u
        radius: 1.75 * u
        anchors.left: parent.left; anchors.leftMargin: 2.5 * u
        anchors.bottom: parent.bottom; anchors.bottomMargin: root.panelBottom
        Behavior on anchors.bottomMargin { NumberAnimation { duration: 300; easing.type: Easing.OutQuad } }
        Column {
            id: clockCol
            anchors.centerIn: parent
            Row {
                spacing: 0.75 * u
                Text {
                    text: root.clock.time
                    color: "#f0ede8"; font.family: Store.display; font.weight: Font.ExtraLight
                    font.pixelSize: 7.5 * u; font.letterSpacing: -0.15 * u
                    lineHeight: 0.95; lineHeightMode: Text.ProportionalHeight
                }
                Text {
                    anchors.baseline: parent.children[0].baseline
                    text: root.clock.ampm
                    color: "#99f0ede8"; font.family: Store.display; font.weight: Font.Light
                    font.pixelSize: 1.75 * u
                }
            }
            Text {
                text: root.clock.date
                color: "#f0ede8"; font.family: Store.display; font.weight: Font.Light
                font.pixelSize: 1.75 * u
            }
        }
    }

    // weather
    Glass {
        id: weatherPanel
        visible: Store.weather !== null
        backdrop: root.backdrop
        watch: anchors.bottomMargin
        width: wRow.width + 3.5 * u; height: wRow.height + 2.5 * u
        radius: 1.75 * u
        anchors.right: parent.right; anchors.rightMargin: 2.5 * u
        anchors.bottom: parent.bottom; anchors.bottomMargin: root.panelBottom
        Behavior on anchors.bottomMargin { NumberAnimation { duration: 300; easing.type: Easing.OutQuad } }
        Row {
            id: wRow
            anchors.centerIn: parent
            spacing: 1.25 * u
            WeatherIcon { kind: Store.weather ? Store.weather.icon : "sun"; size: 3.25 * u; anchors.verticalCenter: parent.verticalCenter }
            Column {
                Text {
                    text: Store.weather && Store.weather.temp !== null ? Store.weather.temp + "°" : "--"
                    color: "#f0ede8"; font.family: Store.display; font.weight: Font.ExtraLight
                    font.pixelSize: 3 * u
                }
                Text {
                    text: Store.weather ? Store.weather.condition + (Store.weather.high !== null ? " · H " + Store.weather.high + "° L " + Store.weather.low + "°" : "") : ""
                    color: "#99f0ede8"; font.family: Store.sans; font.pixelSize: 0.9375 * u
                }
            }
        }
    }

    // idle hint (off by default): which casting sources are ready while nothing plays
    Text {
        readonly property var ready: Store.music && Store.music.hint ? Store.music.hint : []
        visible: !Store.musicShown && ready.length > 0
        anchors.horizontalCenter: parent.horizontalCenter; y: root.height - height - 1.5 * u
        text: "Ready to cast  ·  " + ready.join("  ·  ")
        color: "#80f0ede8"; font.family: Store.sans; font.pixelSize: 0.9375 * u; font.letterSpacing: 0.04 * u
    }

    // now-playing strip
    Glass {
        id: strip
        backdrop: root.backdrop
        watch: y
        visible: y < root.height
        x: 2.5 * u; width: parent.width - 5 * u; height: 4.5 * u
        radius: 1 * u
        y: Store.musicShown ? root.height - height - 1.5 * u : root.height
        Behavior on y { NumberAnimation { duration: 300; easing.type: Easing.OutQuad } }
        Rectangle {
            id: art
            x: 1 * u; anchors.verticalCenter: parent.verticalCenter
            width: 3 * u; height: 3 * u; radius: 0.5 * u
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0; color: "#ff9a5a" }
                GradientStop { position: 1; color: "#6a3fa0" }
            }
            Image {
                anchors.fill: parent; source: Store.nowArt; visible: status === Image.Ready
                fillMode: Image.PreserveAspectCrop; asynchronous: true
            }
        }
        Column {
            anchors.left: art.right; anchors.leftMargin: 1 * u
            anchors.verticalCenter: parent.verticalCenter
            Text { text: Store.nowTitle; color: "#f0ede8"; font.family: Store.sans; font.pixelSize: 1.125 * u }
            Text { text: Store.nowArtist; color: "#99f0ede8"; font.family: Store.sans; font.pixelSize: 0.875 * u }
        }
        Tap {                       // play/pause on the strip; tapping the rest opens the full view when music is casting
            id: stripToggle
            anchors.right: parent.right; anchors.rightMargin: 1 * u; anchors.verticalCenter: parent.verticalCenter
            width: 3 * u; height: 3 * u
            visible: Store.musicActive
            onClicked: Store.toggleMedia()
            Icon { name: Store.musicPlaying ? "pause" : "play"; size: 1.5 * u; anchors.centerIn: parent }
        }
        MouseArea {
            anchors.fill: parent; anchors.rightMargin: 5 * u; enabled: Store.musicActive
            onClicked: { Store.gesture("tap"); Store.nowPlayingOpen = true }
        }
    }
}
