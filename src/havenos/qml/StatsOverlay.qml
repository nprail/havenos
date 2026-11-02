import QtQuick

// Debug HUD + test buttons.  Metrics are *rendered* frames (Qt Quick doesn't redraw an idle scene),
// so "slow" only counts gaps of 25–200 ms between consecutive swaps, i.e. dropped frames mid-animation.
Rectangle {
    id: root
    visible: Store.stats
    readonly property real u: Store.u
    x: 1 * u; y: 1 * u; width: 20 * u; height: col.height + 2 * u
    radius: 1 * u; color: "#bf000000"

    property var swaps: []
    property int slow: 0
    property double last: 0
    property string text: ""

    function onSwap() {
        if (!Store.stats) return
        var t = Date.now()
        var d = t - last
        last = t
        if (d > 25 && d < 200) slow++
        swaps.push({ t: t, d: d })
        while (swaps.length && t - swaps[0].t > 5000) swaps.shift()
    }

    Timer {
        interval: 500; repeat: true; running: Store.stats
        onTriggered: {
            var t = Date.now(), n = 0, worst = 0
            for (var i = 0; i < root.swaps.length; i++) {
                if (t - root.swaps[i].t < 1000) n++
                if (root.swaps[i].d < 200 && root.swaps[i].d > worst) worst = root.swaps[i].d
            }
            root.text = "frames/s   " + n + "\nworst 5s   " + worst.toFixed(1) + " ms\nslow >25ms " + root.slow +
                        "\nrss        " + Store.rssMb.toFixed(0) + " MB\nloop lag   " + Store.lagWorstMs.toFixed(1) + " ms (" + Store.lagSlow + " >10)\nsource     " + Store.photoSource + " (" + Store.cachedPhotos + " cached)\nha         " + Store.haStatus + (Store.webUrl !== "" ? "\nweb        " + Store.webUrl + "\ncode       " + Store.webCode : "") + "\nview       " + root.Window.width + "x" + root.Window.height +
                        "\napi        " + Store.api
        }
    }

    Column {
        id: col
        x: 1 * u; y: 1 * u; width: parent.width - 2 * u; spacing: 0.6 * u
        Text { text: "QT QUICK · QML"; color: "#80ffffff"; font.family: "monospace"; font.pixelSize: 0.6875 * u; font.letterSpacing: 0.1 * u }
        Text { text: root.text; color: "white"; font.family: "monospace"; font.pixelSize: 0.75 * u; lineHeight: 1.25; lineHeightMode: Text.ProportionalHeight }
        Flow {
            width: parent.width; spacing: 0.5 * u
            Repeater {
                model: [["blur", 0], ["voice", 1], ["timer 5s", 2], ["next photo", 3], ["announce", 5], ["hide", 4]]
                Tap {
                    required property var modelData
                    width: label.width + 1.5 * u; height: 3 * u
                    onClicked: {
                        switch (modelData[1]) {
                        case 0: Store.toggleBlur(); break
                        case 1: Store.startVoice(); break
                        case 2: Store.addTimer(5, "Demo (5s)"); break
                        case 3: Store.nextPhoto(1); break
                        case 4: Store.setStats(false); break
                        case 5: Store.testAnnouncement(); break
                        }
                    }
                    Rectangle { anchors.fill: parent; radius: 0.75 * u; color: "#80000000"; border.color: "#40ffffff"; border.width: 1 }
                    Text { id: label; anchors.centerIn: parent
                           text: modelData[1] === 0 ? "blur: " + (Store.blur ? "on" : "off") : modelData[0]
                           color: "white"; font.family: "monospace"; font.pixelSize: 0.75 * u }
                }
            }
        }
    }
    MouseArea { anchors.fill: parent; z: -1 }   // swallow touches outside buttons
}
