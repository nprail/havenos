"""Hand-over from the boot splash (Plymouth) to the app, on a Pi. Does nothing anywhere else.

havenos.service runs `plymouth deactivate` as root just before the app starts (Qt's EGLFS opens the display when the
app starts, and Plymouth must have let go by then; the splash image stays up). The app opens its window at once, and
when the first frame is on screen it tells systemd it is ready (Type=notify); plymouth-quit waits for that
(deploy/plymouth/havenos-boot.conf). Until the first photo, BootSplash.qml keeps the same picture moving.
"""
from __future__ import annotations

import logging
import os
import socket

log = logging.getLogger(__name__)


def notify_ready() -> None:
    """systemd READY=1; safe from any thread, a no-op outside a Type=notify unit."""
    path = os.environ.get("NOTIFY_SOCKET")
    if not path:
        return
    if path.startswith("@"):
        path = "\0" + path[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as s:
            s.sendto(b"READY=1", path)
    except OSError as e:
        log.warning("sd_notify failed: %s", e)
