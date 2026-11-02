"""Announce the device on the LAN so Home Assistant offers it under Settings > Devices > ESPHome."""
from __future__ import annotations

import logging
import socket

from zeroconf.asyncio import AsyncServiceInfo, AsyncZeroconf

log = logging.getLogger(__name__)
SERVICE = "_esphomelib._tcp.local."


class Advertiser:
    def __init__(self, name: str, port: int, mac: str, ip: str, version: str, encrypted: bool = False) -> None:
        props = {"version": version, "mac": mac.replace(":", "").lower(), "board": "host", "platform": "HOST",
                 "network": "ethernet", "friendly_name": name}
        if encrypted:
            props["api_encryption"] = "Noise_NNpsk0_25519_ChaChaPoly_SHA256"      # tells HA to ask for the key
        self._info = AsyncServiceInfo(
            SERVICE, f"{name}.{SERVICE}", addresses=[socket.inet_aton(ip)], port=port, server=f"{name}.local.",
            properties=props)
        self._zc: AsyncZeroconf | None = None

    async def start(self) -> None:
        self._zc = AsyncZeroconf()
        await self._zc.async_register_service(self._info)
        log.info("announced %s on mDNS (port %s)", self._info.name, self._info.port)

    async def stop(self) -> None:
        if self._zc:
            await self._zc.async_unregister_service(self._info)
            await self._zc.async_close()
            self._zc = None
