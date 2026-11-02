"""A stable device id in MAC format. HA keys the ESPHome device (and every entity's unique id) on it, and havenOS uses it
to find its own entry in HA's device registry (which is how it learns which room it is in)."""
from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path

log = logging.getLogger(__name__)
_MAC = re.compile(r"([0-9A-F]{2}:){5}[0-9A-F]{2}")


def device_mac(store: Path | None = None) -> str:
    """Real NIC MACs are unreliable here (uuid.getnode() falls back to a constant or random value), so generate a
    locally-administered one once and keep it next to the config."""
    if store and store.exists() and _MAC.fullmatch(store.read_text().strip()):
        return store.read_text().strip()
    raw = bytearray(uuid.uuid4().bytes[:6])
    raw[0] = (raw[0] | 0x02) & 0xFE                    # locally administered, unicast
    mac = ":".join(f"{b:02X}" for b in raw)
    if store:
        try:
            store.parent.mkdir(parents=True, exist_ok=True)
            store.write_text(mac + "\n")
        except OSError:
            log.warning("could not save the device id to %s; it will change on restart", store)
    return mac
