import QtQuick
import QtQuick.Window

Window {
    id: win
    width: Config.width; height: Config.height
    visible: true
    visibility: Config.fullscreen ? Window.FullScreen : Window.Windowed
    color: "#0a0a0b"
    title: "havenOS (Qt single app)"

    Binding { target: Store; property: "u"; value: Math.min(win.width / 80, win.height / 50) }

    Connections {
        target: win
        function onFrameSwapped() { stats.onSwap() }
    }

    // Debug keyboard shortcuts. Each one forwards a command to the core via Store.
    function cmd(c) {
        switch (c) {
        case "f": Store.toggleStats(); break
        case "b": Store.toggleBlur(); break
        case "v": Store.startVoice(); break
        case "t": Store.addTimer(5, "Demo (5s)"); break
        case "a": Store.setScreen("ambient"); break
        case "d": Store.setScreen("active"); break
        case "right": Store.nextPhoto(1); break
        case "left": Store.nextPhoto(-1); break
        case "r": Store.openRooms(); break
        case "n": Store.openNotifications(); break
        case "1": Store.simulateMusic("airplay", "play"); break                    // demo mode (HAVENOS_MUSIC_DEMO=1)
        case "2": Store.simulateMusic("spotify", "play"); break
        case "3": if (Store.musicActive) Store.simulateMusic(Store.music.active_source, "pause"); break
        case "4": if (Store.musicActive) Store.simulateMusic(Store.music.active_source, "end"); break
        case "l": Store.libraryOpen ? Store.libraryOpen = false : Store.openLibrary(); break
        case "m": if (Store.musicActive) Store.nowPlayingOpen = !Store.nowPlayingOpen; break
        case "p": Store.setupOpen = !Store.setupOpen; break
        case "u": if (Store.timers.length) Store.timersOpen = !Store.timersOpen; break
        case "esc": Store.dismissRing(); Store.dismissVoice(); Store.dismissAnnouncement(); Store.libraryOpen = false
                    Store.nowPlayingOpen = false; Store.timersOpen = false; Store.setupOpen = false; break
        case "q": Qt.quit(); break
        }
    }

    Item {
        id: scene
        anchors.fill: parent
        focus: true

        Keys.onPressed: (e) => {
            var m = {}
            m[Qt.Key_F] = "f"; m[Qt.Key_B] = "b"; m[Qt.Key_V] = "v"; m[Qt.Key_T] = "t"; m[Qt.Key_A] = "a"
            m[Qt.Key_D] = "d"; m[Qt.Key_R] = "r"; m[Qt.Key_N] = "n"; m[Qt.Key_1] = "1"; m[Qt.Key_2] = "2"; m[Qt.Key_3] = "3"; m[Qt.Key_4] = "4"; m[Qt.Key_M] = "m"; m[Qt.Key_U] = "u"; m[Qt.Key_L] = "l"; m[Qt.Key_Right] = "right"; m[Qt.Key_Left] = "left"; m[Qt.Key_Escape] = "esc"; m[Qt.Key_Q] = "q"
            if (m[e.key]) win.cmd(m[e.key])
        }

        // everything the glass panels sample: photo + scrim + dashboard dim
        Item {
            id: backdrop
            anchors.fill: parent
            PhotoStage { anchors.fill: parent }
            Rectangle {
                anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
                height: parent.height * 0.55
                opacity: Store.screen === "active" ? 0 : 1
                Behavior on opacity { NumberAnimation { duration: 250 } }
                gradient: Gradient {
                    GradientStop { position: 0; color: "#00000000" }
                    GradientStop { position: 1; color: "#8c000000" }
                }
            }
            Rectangle {      // dashboard dim: slides up together with the dashboard
                width: parent.width; height: parent.height
                y: Store.dashY; visible: y < height
                color: "#8c000000"
            }
        }

        Ambient { anchors.fill: parent; backdrop: backdrop }
        LiveScreen { anchors.fill: parent; backdrop: backdrop }
        Dashboard { id: dash; width: parent.width; height: parent.height; backdrop: backdrop }  // no anchors: y slides
        Binding { target: Store; property: "dashY"; value: dash.y }
        RoomsScreen { width: parent.width; height: parent.height; backdrop: backdrop }            // no anchors: y slides
        NotificationsScreen { width: parent.width; height: parent.height; backdrop: backdrop }
        NowPlaying { anchors.fill: parent; backdrop: backdrop }
        TimersSheet { anchors.fill: parent; backdrop: backdrop }
        LibraryScreen { anchors.fill: parent; backdrop: backdrop }
        TakeoverToast { anchors.fill: parent; backdrop: backdrop }
        VoiceSheet { anchors.fill: parent; backdrop: backdrop }
        AnnouncementCard { anchors.fill: parent }
        SetupScreen { anchors.fill: parent }
        // a ringing timer is its tile, full screen over everything
        Rectangle {
            id: ringShade
            anchors.fill: parent; color: "#f2000000"
            opacity: Store.ringing !== null ? 1 : 0
            visible: opacity > 0
            Behavior on opacity { NumberAnimation { duration: 200 } }
            MouseArea { anchors.fill: parent }       // swallow touches outside the ring
            Loader {
                anchors.fill: parent
                active: Store.ringing !== null
                sourceComponent: TimerTile { timerId: Store.ringing ? Store.ringing.id : -1; card: false }
            }
        }
        StatsOverlay { id: stats }

        // display power + brightness: software dimming for now (the Pi's backlight comes later). Touching a dark screen wakes it.
        Rectangle {
            anchors.fill: parent; z: 90; color: "black"
            opacity: Store.screenOn ? (1 - Store.brightness / 100) * 0.85 : 1
            visible: opacity > 0
            Behavior on opacity { NumberAnimation { duration: 300 } }
            MouseArea { anchors.fill: parent; enabled: !Store.screenOn; onPressed: Store.activity() }
        }

        // hot corner: triple-tap top-left toggles the debug HUD (for touch-only kiosks)
        MouseArea {
            id: hot
            x: 0; y: 0; width: 5 * Store.u; height: 5 * Store.u; z: 100
            property var taps: []
            onPressed: {
                var n = Date.now()
                taps = taps.filter(function (t) { return n - t < 900 }); taps.push(n)
                if (taps.length >= 3) { taps = []; Store.toggleStats() }
            }
        }

        // idle timeout lives in the core; the view only reports touches
        TapHandler { acceptedButtons: Qt.AllButtons; onPressedChanged: Store.activity() }   // passive: observes all presses
    }
}
