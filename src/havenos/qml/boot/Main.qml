import QtQuick
import QtQuick.Window

Window {
    id: win
    property bool sceneReady: false           // set by main.py when the core is up
    width: Config.width; height: Config.height
    visible: true
    visibility: Config.fullscreen ? Window.FullScreen : Window.Windowed
    color: "#0a0a0b"
    title: "havenOS (Qt single app)"

    // The interface is loaded once the core is ready; until then the window shows the splash (self-contained: it does
    // not touch the core, so the window can be up while Python is still importing).
    Loader { id: scene; anchors.fill: parent; active: win.sceneReady; source: "../Scene.qml"; focus: true }
    BootSplash { anchors.fill: parent; photosReady: scene.item ? scene.item.photosReady : false }
}
