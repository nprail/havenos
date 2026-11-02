"""Demo mode: a handful of fake entities in four rooms, run through the real exposure / room / action code, so the room
screens work with no Home Assistant (and so the same mutator can back the fake HA used in tests and dev)."""
from __future__ import annotations

import copy
from typing import Any

from .exposure import RoomIndex
from .home import HomeBase

DEMO_WEATHER = {"temp": 72, "condition": "Mostly sunny", "icon": "sun", "high": 78, "low": 61,
                "hourly": [{"label": "1 PM", "icon": "sun", "temp": 74}, {"label": "2 PM", "icon": "sun", "temp": 76},
                           {"label": "3 PM", "icon": "partly", "temp": 77}, {"label": "4 PM", "icon": "cloud", "temp": 74}]}


def _s(eid: str, state: str, **attrs: Any) -> dict:
    return {"entity_id": eid, "state": state, "attributes": attrs}


def demo_states() -> dict[str, dict]:
    rows = [
        _s("light.living_room_lamp", "on", friendly_name="Living Room Lamp", brightness=190, supported_color_modes=["brightness"]),
        _s("light.living_room_ceiling", "off", friendly_name="Living Room Ceiling", supported_color_modes=["brightness"]),
        _s("climate.living_room", "heat", friendly_name="Living Room Climate", current_temperature=69, temperature=70,
           target_temp_step=1, hvac_modes=["off", "heat", "cool", "heat_cool"], temperature_unit="°F", min_temp=50, max_temp=90),
        _s("fan.living_room_fan", "on", friendly_name="Living Room Fan", percentage=50, supported_features=1),
        _s("cover.living_room_blinds", "open", friendly_name="Living Room Blinds", current_position=100),
        _s("media_player.living_room_speaker", "paused", friendly_name="Living Room Speaker", media_title="Slow Light",
           media_artist="The Harbour Choir", volume_level=0.4),
        _s("scene.living_room_movie", "scening", friendly_name="Living Room Movie"),
        _s("sensor.living_room_temperature", "69.8", friendly_name="Living Room Temperature", unit_of_measurement="°F"),
        _s("binary_sensor.living_room_motion", "off", friendly_name="Living Room Motion"),
        _s("light.kitchen_main_lights", "on", friendly_name="Kitchen Main Lights", brightness=255, supported_color_modes=["brightness"]),
        _s("light.kitchen_counter", "off", friendly_name="Kitchen Counter", supported_color_modes=["onoff"]),
        _s("switch.kitchen_coffee_maker", "off", friendly_name="Kitchen Coffee Maker"),
        _s("sensor.kitchen_humidity", "48", friendly_name="Kitchen Humidity", unit_of_measurement="%"),
        _s("light.bedroom_lamp", "off", friendly_name="Bedroom Lamp", supported_color_modes=["brightness"]),
        _s("climate.bedroom", "heat_cool", friendly_name="Bedroom Climate", current_temperature=67, target_temp_low=65,
           target_temp_high=72, hvac_modes=["off", "heat_cool"], temperature_unit="°F"),
        _s("fan.bedroom_fan", "off", friendly_name="Bedroom Fan", percentage=0, supported_features=1),
        _s("lock.front_door", "locked", friendly_name="Hallway Front Door"),
        _s("light.hallway_lights", "on", friendly_name="Hallway Lights", brightness=120, supported_color_modes=["brightness"]),
        _s("weather.demo_home", "sunny", friendly_name="Home", temperature=72),
    ]
    return {r["entity_id"]: r for r in rows}


def demo_index() -> RoomIndex:
    areas = [{"area_id": "living_room", "name": "Living Room"}, {"area_id": "kitchen", "name": "Kitchen"},
             {"area_id": "bedroom", "name": "Bedroom"}, {"area_id": "hallway", "name": "Hallway"}]
    where = {"living_room": "living_room", "kitchen": "kitchen", "bedroom": "bedroom", "front_door": "hallway", "hallway": "hallway"}
    entities = []
    for eid in demo_states():
        slug = eid.split(".", 1)[1]
        area = next((a for k, a in where.items() if slug.startswith(k)), None)
        entities.append({"entity_id": eid, "area_id": area})
    exposed = {e["entity_id"]: {"conversation": True} for e in entities}
    ix = RoomIndex.build(areas, [], entities, exposed)
    ix.device_area = "living_room"
    return ix


def apply_service(states: dict[str, dict], domain: str, service: str, entity_id: str, data: dict | None) -> None:
    """Enough of Home Assistant's service behavior to drive the room screens (used by the demo and by the fake HA)."""
    data = data or {}
    st = states.get(entity_id)
    if st is None:
        return
    st = copy.deepcopy(st)
    a, cur = st["attributes"], st["state"]
    if service == "toggle":
        st["state"] = {"on": "off", "off": "on", "open": "closed", "closed": "open"}.get(cur, cur)
        if domain == "cover":
            a["current_position"] = 100 if st["state"] == "open" else 0
    elif service in ("turn_on", "turn_off") and domain in ("light", "switch", "fan", "input_boolean"):
        st["state"] = "on" if service == "turn_on" else "off"
        if domain == "light" and "brightness_pct" in data:
            a["brightness"] = round(data["brightness_pct"] / 100 * 255)
        elif domain == "light" and st["state"] == "on" and not a.get("brightness"):
            a["brightness"] = 255
        if domain == "fan" and st["state"] == "off":
            a["percentage"] = 0
    elif service == "set_percentage":
        st["state"], a["percentage"] = "on", data["percentage"]
    elif service in ("open_cover", "close_cover", "stop_cover"):
        st["state"] = {"open_cover": "open", "close_cover": "closed", "stop_cover": cur}[service]
        if service != "stop_cover":
            a["current_position"] = 100 if st["state"] == "open" else 0
    elif service == "set_cover_position":
        a["current_position"] = data["position"]
        st["state"] = "open" if data["position"] else "closed"
    elif service == "set_temperature":
        for k in ("temperature", "target_temp_low", "target_temp_high"):
            if k in data:
                a[k] = data[k]
    elif service == "set_hvac_mode":
        st["state"] = data["hvac_mode"]
    elif service == "media_play_pause":
        st["state"] = "paused" if cur == "playing" else "playing"
    elif service == "volume_set":
        a["volume_level"] = data["volume_level"]
    elif service in ("lock", "unlock"):
        st["state"] = "locked" if service == "lock" else "unlocked"
    elif service == "turn_on" and domain in ("scene", "script"):
        pass
    else:
        return
    states[entity_id] = st


class DemoHome(HomeBase):
    def __init__(self, patch) -> None:
        super().__init__(patch)
        self.entities = demo_states()
        self.index = demo_index()

    def start(self) -> None:
        self.publish_all()

    async def stop(self) -> None:
        if self._publish_handle:
            self._publish_handle.cancel()

    def _weather_value(self) -> dict:
        return dict(DEMO_WEATHER)

    async def _call(self, domain: str, service: str, entity_id: str, data: dict | None = None) -> None:
        apply_service(self.entities, domain, service, entity_id, data)
        self.schedule_publish()
