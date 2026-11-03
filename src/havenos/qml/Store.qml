pragma Singleton
import QtQuick
import Haven 1.0

// View-side facade. Business state lives in the Python core and arrives through `App` (bridge.AppModel);
// this singleton only mirrors it read-only, forwards commands, and holds pure view state
// (scale unit, dashboard slide position, a wall-clock tick for rendering the clock).
QtObject {
    id: store

    // ---- view state ----
    property real u: 16                // 1u == 16px at 1280x800, set from the window size in Main.qml
    readonly property string display: "Urbanist"
    readonly property string sans: "Inter"
    property real dashY: 0             // dashboard slide position, read by the backdrop dim layer
    property double now: Date.now()    // rendering only (clock text, countdown display); expiry is the core's job
    property Timer tick: Timer {
        interval: 250; repeat: true; running: true
        onTriggered: store.now = Date.now()
    }

    // ---- core state (read-only mirrors) ----
    readonly property string mode: App.mode
    // rooms and notifications slide over the dashboard, which stays "active" underneath
    readonly property string screen: App.mode === "ambient" ? "ambient" : "active"
    readonly property var room: App.room ? App.room : null
    readonly property var rooms: App.rooms
    readonly property string roomSelected: App.roomSelected
    readonly property var roomView: App.roomView ? App.roomView : null
    readonly property var announcement: App.announcement ? App.announcement : null
    readonly property var notifications: App.notifications
    readonly property var haExposure: App.haExposure ? App.haExposure : null
    readonly property bool blur: App.blur
    readonly property bool stats: App.statsVisible
    readonly property string photoUrl: App.photo ? App.photo.url : ""
    readonly property string photoSource: App.photoSource
    readonly property int cachedPhotos: App.cachedPhotos
    readonly property var weather: App.weather ? App.weather : null
    readonly property var media: App.media ? App.media : null
    // Music: the active source from the music pipeline (AirPlay, Spotify, Sendspin...) wins over the Home Assistant
    // media player, which is only shown when nothing is casting to this display.
    readonly property var music: App.music ? App.music : null
    readonly property bool musicActive: music !== null && music.active_source !== null && music.active_source !== undefined
    readonly property bool musicPlaying: musicActive ? music.status === "playing" || music.status === "buffering"
                                                     : (App.media ? App.media.playing : false)
    readonly property bool musicShown: musicActive || (App.media ? App.media.playing : false)
    readonly property var track: musicActive && music.track ? music.track : null
    readonly property string nowTitle: musicActive ? (track ? track.title : "") : (media ? media.title : "")
    readonly property string nowArtist: musicActive ? (track ? track.artist : "") : (media ? media.artist : "")
    readonly property string nowArt: musicActive && track ? track.art_uri : ""
    readonly property real nowDuration: musicActive ? (track && track.duration ? track.duration : 0) : (media && media.duration ? media.duration : 0)
    // seconds into the track; the core sends an anchor (position at position_at) and we advance it while playing
    readonly property real nowPosition: {
        if (!musicActive) return media && media.position ? media.position : 0
        var p = music.position + (music.status === "playing" ? Math.max(0, now - music.position_at) / 1000 : 0)
        return nowDuration > 0 ? Math.min(p, nowDuration) : p
    }
    function can(cmd) { return musicActive && music.capabilities.indexOf(cmd) >= 0 }
    property bool nowPlayingOpen: false
    property bool timersOpen: false
    // The resting screen is the live screen while music is casting to this display or a timer is running; the photos
    // come back when neither is. (The dashboard and the other screens slide over it as they do over the photos.)
    readonly property bool liveActive: musicActive || timers.length > 0
    readonly property bool liveShown: screen === "ambient" && liveActive
    onTimersChanged: if (timers.length === 0) timersOpen = false
    readonly property var controls: App.controls
    readonly property string haStatus: App.haStatus
    readonly property int crossfadeMs: App.crossfadeMs
    readonly property bool screenOn: App.screenOn
    readonly property int brightness: App.brightness
    readonly property bool backlight: App.backlight
    readonly property string webUrl: App.webUrl
    readonly property string webCode: App.webCode
    readonly property string webLink: App.webLink
    readonly property var webQr: App.webQr
    readonly property bool setupDone: App.setupDone
    property bool setupOpen: false                  // the pairing screen, opened by hand from the dashboard
    property bool setupDismissed: false             // "Not now" on first boot (comes back next boot until setup is done)
    readonly property bool setupShown: webLink !== "" && (setupOpen || (!setupDone && !setupDismissed))
    readonly property var timers: App.timers
    readonly property var ringing: App.ringing ? App.ringing : null
    readonly property string voice: App.voice
    readonly property bool voiceMuted: App.voiceMuted
    readonly property bool voiceReady: App.voiceReady
    readonly property string transcript: App.transcript
    readonly property string response: App.response
    readonly property real rssMb: App.rssMb
    readonly property real lagWorstMs: App.lagWorstMs
    readonly property int lagSlow: App.lagSlow
    readonly property string api: App.api

    // ---- commands (forwarded to the core) ----
    function setScreen(s) { App.setMode(s === "active" ? "dashboard" : "ambient") }   // "active" = the dashboard
    function nextPhoto(d) { App.nextPhoto(d) }
    function toggleMedia() { musicActive ? App.musicCommand("toggle") : App.toggleMedia() }
    function nextMedia() { musicActive ? App.musicCommand("next") : App.nextMedia() }
    function prevMedia() { musicActive ? App.musicCommand("prev") : App.prevMedia() }
    function musicSeek(seconds) { App.musicSeek(seconds) }
    function musicVolume(level) { App.musicVolume(level) }
    function musicStop() { App.musicCommand("stop"); nowPlayingOpen = false }
    function simulateMusic(source, action) { App.simulateMusic(source, action) }

    // Music library (Music Assistant): search/browse on the display, play on this display.
    readonly property var library: App.library ? App.library : null
    readonly property bool libraryAvailable: library !== null && library.available === true
    property bool libraryOpen: false
    function openLibrary() { if (libraryAvailable) { libraryOpen = true; App.libraryOpen() } }
    function searchLibrary(query) { App.librarySearch(query) }
    function voiceSearchLibrary() { App.libraryVoice() }
    function playLibrary(uri) { App.libraryPlay(uri); libraryOpen = false }
    function toggleControl(id) { App.toggleControl(id) }
    function toggleBlur() { App.setBlur(!App.blur) }
    function toggleStats() { App.setStats(!App.statsVisible) }
    function setStats(on) { App.setStats(on) }
    function addTimer(sec, label) { App.addTimer(sec, label) }
    function cancelTimer(id) { App.cancelTimer(id) }
    function pauseTimer(id) { App.pauseTimer(id) }
    function resumeTimer(id) { App.resumeTimer(id) }
    function extendTimer(id, seconds) { App.extendTimer(id, seconds) }
    function dismissRing() { App.dismissRing() }
    function snooze(sec) { App.snooze(sec) }
    function startVoice() { App.startVoice() }
    function dismissVoice() { App.dismissVoice() }
    function activity() { App.activity() }
    function testAnnouncement() { App.testAnnouncement() }
    function openRooms() { App.openRooms() }
    function selectRoom(id) { App.selectRoom(id) }
    function roomsBack() { App.roomsBack() }
    function act(id, action, args) { App.act(id, action, args || ({})) }
    function dismissAnnouncement() { App.dismissAnnouncement() }
    function openNotifications() { App.openNotifications() }
    function clearNotifications() { App.clearNotifications() }
    function removeNotification(id) { App.removeNotification(id) }
    function gesture(kind) { App.gesture(kind) }
    function setDisplay(on) { App.setDisplay(on) }

    // seconds left on a timer: frozen while it is paused
    function timerSecs(t) { return !t ? 0 : t.paused ? t.left : (t.end - now) / 1000 }
    function fmt(secs) {
        var s = Math.max(0, Math.ceil(secs))
        var m = Math.floor(s / 60)
        return m + ":" + (s % 60 < 10 ? "0" : "") + (s % 60)
    }
}
