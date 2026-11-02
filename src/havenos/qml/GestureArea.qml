import QtQuick

// One gesture vocabulary: tap, horizontal swipe, swipe down.
MouseArea {
    id: area
    signal tapped()
    signal swipedX(int dir)
    signal swipedDown()
    property real sx; property real sy; property double st
    onPressed: (m) => { sx = m.x; sy = m.y; st = Date.now() }
    onReleased: (m) => {
        var dx = m.x - sx, dy = m.y - sy
        var dist = Math.sqrt(dx * dx + dy * dy)
        if (dist < 14 && Date.now() - st < 600) { tapped(); return }
        if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.5) { swipedX(dx < 0 ? 1 : -1); return }
        if (dy > 80 && dy > Math.abs(dx) * 1.5) swipedDown()
    }
}
