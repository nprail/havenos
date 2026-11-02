"""ESPHome native-API server: makes havenOS appear in Home Assistant as an ESPHome device.

Pattern credit: OHF-Voice/linux-voice-assistant (Apache-2.0), which showed that a plain-text ESPHome server on top of
aioesphomeapi's protobuf messages is enough for HA to adopt a Linux box. This is an independent implementation
shaped for havenOS: declarative entities, multi-client broadcast, and a handler registry so the voice-assistant
messages can be added without touching the transport.
"""
from .device import ESPHomeDevice
from .server import ESPHomeServer

__all__ = ["ESPHomeDevice", "ESPHomeServer"]
