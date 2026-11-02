import QtQuick

// Two stacked layers.  Next photo loads (async decode) into the back layer, then fades in over
// the front one (Store.crossfadeMs, OpacityAnimator = render thread), then roles swap and the old one is freed.
Item {
    id: stage
    property PhotoLayer front: a
    property PhotoLayer back: b
    property string topUrl: ""
    property string loadingUrl: ""

    // The core hands us one prepared file:// URL at a time (local folder or Immich preview, already downscaled).
    function load(u) {
        if (u === "" || u === topUrl) return
        if (fade.running || loadingUrl !== "") return   // re-checked when the current one finishes
        loadingUrl = u
        back.source = u
        if (back.ready) startFade()
    }

    function startFade() {
        if (loadingUrl === "") return
        if (topUrl === "") {                         // very first photo: no fade
            back.opacity = 1
            swap()
            return
        }
        back.z = 2; front.z = 1
        back.opacity = 0
        fade.target = back
        fade.restart()
    }

    function swap() {
        var old = front
        front = back
        back = old
        old.opacity = 0
        old.source = ""
        topUrl = loadingUrl
        loadingUrl = ""
        if (Store.photoUrl !== topUrl) load(Store.photoUrl)
    }

    PhotoLayer { id: a; anchors.fill: parent; opacity: 0; onReadyChanged: if (ready && stage.back === a) stage.startFade() }
    PhotoLayer { id: b; anchors.fill: parent; opacity: 0; onReadyChanged: if (ready && stage.back === b) stage.startFade() }

    OpacityAnimator {
        id: fade
        from: 0; to: 1; duration: Store.crossfadeMs
        easing.type: Easing.InOutQuad
        onFinished: stage.swap()
    }

    Connections {
        target: Store
        function onPhotoUrlChanged() { stage.load(Store.photoUrl) }
    }
    Component.onCompleted: load(Store.photoUrl)
}
