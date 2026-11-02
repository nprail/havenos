"""QR codes for the display: the first-run screen shows one that opens the settings page already signed in."""
from __future__ import annotations


def matrix(text: str) -> list[str]:
    """The QR code for `text` as rows of "0"/"1" characters (1 = dark module), without the quiet zone: the UI draws that."""
    import segno
    qr = segno.make(text, error="m", micro=False)
    return ["".join("1" if m else "0" for m in row) for row in qr.matrix]
