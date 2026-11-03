"""Regenerate the images of the Plymouth boot theme (deploy/plymouth/havenos) from the app's own sun icon and font.

    .venv/bin/python scripts/build_plymouth.py

Writes sun-core.png, sun-rays.png (white on transparent, 384 px, the theme scales them) and wordmark.png.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "src" / "havenos" / "assets"
OUT = ROOT / "deploy" / "plymouth" / "havenos"
SIZE = 384


def svg_png(name: str) -> None:
    img = QImage(SIZE, SIZE, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
    QSvgRenderer(str(ASSETS / "icons" / f"{name}.svg")).render(p, QRectF(0, 0, SIZE, SIZE))
    p.end()
    img.save(str(OUT / f"{name}.png"))


def wordmark() -> None:
    fid = QFontDatabase.addApplicationFont(str(ASSETS / "fonts" / "Urbanist-Light.ttf"))
    family = QFontDatabase.applicationFontFamilies(fid)[0]
    font = QFont(family, 1)
    font.setPixelSize(72)
    font.setLetterSpacing(QFont.AbsoluteSpacing, 6)
    img = QImage(520, 110, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
    p.setFont(font)
    p.setPen(QColor("#f0ede8"))
    p.drawText(QRectF(0, 0, 520, 110), Qt.AlignCenter, "havenOS")
    p.end()
    img.save(str(OUT / "wordmark.png"))


if __name__ == "__main__":
    app = QGuiApplication(sys.argv)
    OUT.mkdir(parents=True, exist_ok=True)
    svg_png("sun-core")
    svg_png("sun-rays")
    wordmark()
    print("wrote", *sorted(p.name for p in OUT.glob("*.png")))
