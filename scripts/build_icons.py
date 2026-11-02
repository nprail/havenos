"""Regenerate src/havenos/assets/icons from Lucide (https://lucide.dev, ISC licence).

    npm pack lucide-static && tar -xzf lucide-static-*.tgz      # in a scratch folder, not in the repo
    python scripts/build_icons.py /path/to/package/icons

Each havenOS icon name maps to a Lucide icon (MAP below). Every icon is written twice: white (`name.svg`) for dark
surfaces and black (`name-dark.svg`) for light buttons. The transport icons are drawn filled, as the interface expects.
The sun is split in two files (the disc, and the rays that SunIcon.qml turns). The licence text is kept in
src/havenos/assets/icons/LICENSE.md; update the version in it when you regenerate.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "src" / "havenos" / "assets" / "icons"

# havenOS name -> Lucide name
MAP = {
    "back": "chevron-left", "bell": "bell", "blinds": "blinds", "bulb": "lightbulb", "camera": "camera", "close": "x",
    "cloud": "cloud", "fan": "fan", "gear": "settings", "home": "house", "lock": "lock", "mic": "mic", "minus": "minus",
    "next": "skip-forward", "partly": "cloud-sun", "pause": "pause", "play": "play", "plug": "plug", "plus": "plus",
    "prev": "skip-back", "scenes": "layout-grid", "speaker": "speaker", "thermo": "thermometer", "timer": "timer",
    "warning": "triangle-alert",
}
FILLED = {"play", "pause", "next", "prev"}


def shapes(svg: str) -> list[str]:
    """The drawing elements of a Lucide SVG (everything inside the <svg> tag), one string each."""
    body = svg[svg.index(">", svg.index("<svg")) + 1:svg.rindex("</svg>")]
    return [re.sub(r"\s+", " ", m).strip() for m in re.findall(r"<(?:path|circle|rect|line|polygon|polyline|ellipse)\b.*?/>", body, re.S)]


def write(name: str, parts: list[str], filled: bool, version: str) -> None:
    for suffix, color in (("", "#ffffff"), ("-dark", "#000000")):
        fill = color if filled else "none"
        svg = (f'<!-- Lucide {version}, ISC licence: see LICENSE.md -->\n'
               f'<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 24 24" fill="{fill}" stroke="{color}" '
               f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{"".join(parts)}</svg>\n')
        (OUT / f"{name}{suffix}.svg").write_text(svg)


def main(src: Path) -> None:
    version = re.search(r"lucide-static (v[\d.]+)", (src / "bell.svg").read_text()).group(1)
    for ours, theirs in MAP.items():
        write(ours, shapes((src / f"{theirs}.svg").read_text()), ours in FILLED, version)
    sun = shapes((src / "sun.svg").read_text())
    write("sun-core", [s for s in sun if s.startswith("<circle")], False, version)
    write("sun-rays", [s for s in sun if not s.startswith("<circle")], False, version)
    print(f"wrote {len(MAP) * 2 + 4} icons from Lucide {version}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
