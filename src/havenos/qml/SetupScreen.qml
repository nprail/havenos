import QtQuick

// Pairing screen: a QR code that opens the settings page already signed in, plus the address and code to type by hand.
// Shown on first boot until setup is finished (the web wizard marks it done), and any time from the gear on the dashboard,
// so the setup code never needs the debug HUD.
Item {
    id: root
    readonly property real u: Store.u
    readonly property bool shown: Store.setupShown
    readonly property bool firstRun: !Store.setupDone

    Rectangle {
        id: shade
        anchors.fill: parent; color: "#f2050507"
        opacity: root.shown ? 1 : 0; visible: opacity > 0
        Behavior on opacity { NumberAnimation { duration: 250 } }
        MouseArea { anchors.fill: parent }                        // swallow touches

        readonly property bool landscape: width >= height
        readonly property real qrSize: landscape ? Math.min(height - 8 * u, width * 0.44) : Math.min(width - 8 * u, height * 0.42)

        // the QR code: dark modules on a white plate with a two-module quiet zone
        Rectangle {
            id: plate
            x: shade.landscape ? 4 * u : (shade.width - width) / 2
            y: shade.landscape ? (shade.height - height) / 2 : 5 * u
            width: shade.qrSize; height: width; radius: 1.2 * u; color: "white"
            Canvas {
                id: qr
                anchors.fill: parent
                property var rows: Store.webQr
                onRowsChanged: requestPaint()
                onWidthChanged: requestPaint()
                onPaint: {
                    var c = getContext("2d"); c.reset()
                    var n = rows.length; if (n === 0) return
                    var cell = width / (n + 4)                           // 2 modules of quiet zone each side
                    c.fillStyle = "#000000"
                    for (var y = 0; y < n; y++) {
                        var row = rows[y]
                        for (var x = 0; x < n; x++)
                            if (row.charAt(x) === "1")
                                c.fillRect(Math.floor((x + 2) * cell), Math.floor((y + 2) * cell), Math.ceil(cell), Math.ceil(cell))
                    }
                }
            }
        }

        Column {
            x: shade.landscape ? plate.x + plate.width + 4 * u : 4 * u
            y: shade.landscape ? (shade.height - height) / 2 : plate.y + plate.height + 2 * u
            width: shade.landscape ? shade.width - x - 4 * u : shade.width - 8 * u
            spacing: 1.2 * u
            Text {
                text: root.firstRun ? "Welcome to havenOS" : "Pair with this display"
                color: "#f0ede8"; font.family: Store.display; font.weight: Font.Light; font.pixelSize: Math.max(2.8 * u, 24)
                width: parent.width; elide: Text.ElideRight
            }
            Text {
                width: parent.width; wrapMode: Text.WordWrap
                text: root.firstRun ? "Scan this code with your phone's camera to finish setting up. It takes a couple of minutes."
                                    : "Scan this code with your phone's camera to open the settings page."
                color: "#c8f0ede8"; font.family: Store.sans; font.pixelSize: Math.max(1.3 * u, 15)
            }
            Item { width: 1; height: 0.4 * u }
            Text {
                text: "OR ENTER BY HAND"
                color: "#99f0ede8"; font.family: Store.sans; font.pixelSize: Math.max(0.95 * u, 11); font.letterSpacing: 0.12 * u
            }
            Text {
                text: Store.webUrl.replace("http://", "")
                color: "#f0ede8"; font.family: Store.sans; font.pixelSize: Math.max(1.5 * u, 16); font.weight: Font.Medium
            }
            Row {
                spacing: 1 * u
                Text { anchors.verticalCenter: parent.verticalCenter; text: "Code"; color: "#99f0ede8"; font.family: Store.sans; font.pixelSize: Math.max(1.3 * u, 15) }
                Text {
                    anchors.verticalCenter: parent.verticalCenter; text: Store.webCode
                    color: "#4a9eff"; font.family: Store.sans; font.pixelSize: Math.max(2.4 * u, 22); font.weight: Font.Medium; font.letterSpacing: 0.15 * u
                }
            }
            Item { width: 1; height: 0.6 * u }
            Pill {
                text: root.firstRun ? "Not now" : "Close"
                onClicked: { Store.setupOpen = false; Store.setupDismissed = true }
            }
        }
    }
}
