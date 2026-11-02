"""Which Home Assistant entities this device may show, and which room it lives in.

Rules (all of them fail closed):
  * An entity is shown only if it is exposed to Assist (HA: Settings > Voice assistants > Expose, the "conversation"
    flag). Anything not exposed never reaches the UI, however it is configured here.
  * Entities that are disabled, hidden, or config/diagnostic category are never shown.
  * This device's own entities are never shown (a display does not control itself).
  * An entity belongs to its own area, or else its device's area.
  * The device's room is the area of its entry in HA's device registry (found by MAC), unless a room is configured.

Pure functions over registry data, so it is all testable without Home Assistant.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# What a room screen can show, in display order, with the section title.
ROOM_DOMAINS: list[tuple[str, str]] = [
    ("light", "Lights"), ("climate", "Climate"), ("fan", "Fans"), ("cover", "Covers"),
    ("media_player", "Media"), ("lock", "Locks"), ("switch", "Switches"), ("input_boolean", "Switches"),
    ("scene", "Scenes"), ("script", "Scripts"), ("vacuum", "Vacuum"), ("humidifier", "Humidifiers"),
    ("water_heater", "Water heaters"), ("valve", "Valves"),
    ("sensor", "Sensors"), ("binary_sensor", "Sensors"),
]
DOMAIN_ORDER = {d: i for i, (d, _) in enumerate(ROOM_DOMAINS)}
SECTION_TITLE = dict(ROOM_DOMAINS)
INFO_DOMAINS = {"sensor", "binary_sensor"}

# "Major" entities for the quick tiles: one of each in this order first, then fill up.
TILE_DOMAINS = ["light", "climate", "fan", "cover", "media_player", "switch", "scene", "vacuum", "humidifier", "water_heater"]
MAX_TILES = 6

ON_STATES = {"on", "unlocked", "open", "opening", "heat", "cool", "heat_cool", "auto", "dry", "fan_only", "playing",
             "cleaning", "armed_home", "armed_away", "armed_night", "armed_vacation", "eco", "performance", "high_demand"}


def _norm_mac(m: str) -> str:
    return re.sub(r"[^0-9a-f]", "", m.lower())


def _deg(v: Any) -> int | None:
    try:
        return None if v is None else round(float(v))
    except (TypeError, ValueError):
        return None


@dataclass
class RoomIndex:
    areas: dict[str, str]                        # area_id -> name
    entity_area: dict[str, str | None]           # entity_id -> area_id (own or via device)
    exposed: set[str]                            # exposed to Assist
    hidden: set[str]                             # disabled / hidden / config / diagnostic
    own: set[str]                                # this device's entities
    device_area: str | None                      # the area this device is in (None = unknown)
    names: dict[str, str] = field(default_factory=dict)   # registry names (fallback when a state has none)

    @classmethod
    def build(cls, areas: list[dict], devices: list[dict], entities: list[dict], exposed: dict[str, dict],
              own_mac: str | None = None, room_override: str | None = None) -> "RoomIndex":
        area_names = {a["area_id"]: (a.get("name") or a["area_id"]).strip() for a in areas}
        dev_by_id = {d["id"]: d for d in devices}
        own_dev = None
        if own_mac:
            want = _norm_mac(own_mac)
            for d in devices:
                if any(c[0] == "mac" and _norm_mac(c[1]) == want for c in d.get("connections", [])):
                    own_dev = d
                    break
        entity_area: dict[str, str | None] = {}
        hidden: set[str] = set()
        own: set[str] = set()
        names: dict[str, str] = {}
        for e in entities:
            eid = e["entity_id"]
            dev = dev_by_id.get(e.get("device_id"))
            entity_area[eid] = e.get("area_id") or (dev.get("area_id") if dev else None)
            if e.get("disabled_by") or e.get("hidden_by") or e.get("entity_category"):
                hidden.add(eid)
            if own_dev and e.get("device_id") == own_dev["id"]:
                own.add(eid)
            if e.get("name") or e.get("original_name"):
                names[eid] = e.get("name") or e.get("original_name")
        device_area = own_dev.get("area_id") if own_dev else None
        if room_override:
            wanted = room_override.strip().lower()
            for aid, name in area_names.items():
                if aid.lower() == wanted or name.lower() == wanted:
                    device_area = aid
                    break
        return cls(areas=area_names, entity_area=entity_area,
                   exposed={eid for eid, flags in exposed.items() if flags.get("conversation")},
                   hidden=hidden, own=own, device_area=device_area, names=names)

    # -- queries --
    def visible(self, entity_id: str) -> bool:
        return entity_id in self.exposed and entity_id not in self.hidden and entity_id not in self.own

    def area_of(self, entity_id: str) -> str | None:
        return self.entity_area.get(entity_id)

    def room_entities(self, area_id: str) -> list[str]:
        """Visible entities of one room whose domain a room screen can show."""
        return sorted((e for e in self.exposed if self.visible(e) and self.entity_area.get(e) == area_id
                       and e.split(".", 1)[0] in DOMAIN_ORDER),
                      key=lambda e: (DOMAIN_ORDER[e.split(".", 1)[0]], e))

    def room_ids(self) -> list[str]:
        """Rooms that have something to show; this device's room first, then alphabetical."""
        found = {self.entity_area.get(e) for e in self.exposed
                 if self.visible(e) and e.split(".", 1)[0] in DOMAIN_ORDER}
        found.discard(None)
        found = {a for a in found if a in self.areas}
        return sorted(found, key=lambda a: (a != self.device_area, self.areas[a].lower()))

    def first_visible(self, domain: str, area_id: str | None = None) -> str | None:
        for e in sorted(self.exposed):
            if e.startswith(domain + ".") and self.visible(e) and (area_id is None or self.entity_area.get(e) == area_id):
                return e
        return None


# ---- entity view-models (what the UI renders) ----------------------------------------------------------

def display_name(state: dict, index: RoomIndex | None, area_name: str | None) -> str:
    eid = state["entity_id"]
    name = (state.get("attributes", {}).get("friendly_name") or (index.names.get(eid) if index else "") or eid).strip()
    if area_name and name.lower().startswith(area_name.lower() + " ") and len(name) > len(area_name) + 1:
        name = name[len(area_name) + 1:]               # "Kitchen Main Lights" in the Kitchen is just "Main Lights"
        name = name[:1].upper() + name[1:]
    return name


def entity_view(state: dict, name: str) -> dict:
    """One flat, UI-ready dict. `kind` picks the card layout; extra fields depend on the kind."""
    eid, st, a = state["entity_id"], state.get("state", "unavailable"), state.get("attributes", {})
    domain = eid.split(".", 1)[0]
    unavailable = st in ("unavailable", "unknown")
    v: dict[str, Any] = {"id": eid, "name": name, "domain": domain, "state": st, "unavailable": unavailable,
                         "on": st in ON_STATES and not unavailable, "kind": "info", "status": "Unavailable" if unavailable else st.replace("_", " ").title()}
    if unavailable:
        v["kind"] = {"light": "toggle", "switch": "toggle"}.get(domain, "info")
        return v
    if domain == "light":
        v["kind"] = "light"
        modes = set(a.get("supported_color_modes") or [])
        v["dimmable"] = bool(modes - {"onoff"})
        v["brightness"] = round((a.get("brightness") or 0) / 255 * 100) if st == "on" else 0
        v["status"] = f"{v['brightness']}%" if v["dimmable"] and st == "on" else v["status"]
    elif domain in ("switch", "input_boolean"):
        v["kind"] = "toggle"
    elif domain == "fan":
        v["kind"] = "fan"
        v["percentage"] = a.get("percentage") or 0
        v["speedable"] = bool(a.get("supported_features", 0) & 1) or a.get("percentage") is not None
        v["status"] = f"{v['percentage']}%" if st == "on" and v["speedable"] else v["status"]
    elif domain == "cover":
        v["kind"] = "cover"
        pos = a.get("current_position")
        v["position"] = pos
        v["status"] = f"{st.title()}" + (f" {pos}%" if pos is not None and st not in ("open", "closed") else "")
    elif domain == "climate":
        v["kind"] = "climate"
        v.update(current=_deg(a.get("current_temperature")), target=a.get("temperature"),
                 low=a.get("target_temp_low"), high=a.get("target_temp_high"),
                 step=a.get("target_temp_step") or 1, min=a.get("min_temp"), max=a.get("max_temp"),
                 mode=st, action=a.get("hvac_action"), unit=a.get("temperature_unit", ""))
        cur = f"{v['current']}°" if v["current"] is not None else ""
        v["status"] = f"{cur} · {st.replace('_', ' ')}".strip(" ·")
    elif domain == "media_player":
        v["kind"] = "media"
        v.update(title=a.get("media_title") or "", artist=a.get("media_artist") or "", playing=st == "playing",
                 volume=round((a.get("volume_level") or 0) * 100) if a.get("volume_level") is not None else None)
        v["status"] = v["title"] or ("Playing" if st == "playing" else st.title())
    elif domain == "lock":
        v["kind"] = "lock"
        v["on"] = st == "unlocked"                          # "lit" means open/unlocked: the state worth noticing
    elif domain in ("scene", "script"):
        v["kind"] = "button"
        v["status"] = "Run"
    elif domain == "vacuum":
        v["kind"] = "vacuum"
    elif domain in INFO_DOMAINS:
        unit = a.get("unit_of_measurement") or ""
        v["status"] = f"{st} {unit}".strip() if domain == "sensor" else st.replace("_", " ").title()
        v["on"] = False
    return v


def tile_from_view(v: dict) -> dict:
    """The quick-tile shape (matches the old `controls` entries the QML tiles already render)."""
    icon = {"light": "bulb", "climate": "thermo", "fan": "fan", "cover": "blinds", "media_player": "speaker",
            "lock": "lock", "scene": "scenes", "script": "scenes", "switch": "plug", "vacuum": "gear"}.get(v["domain"], "gear")
    return {"id": v["id"], "label": v["name"], "icon": icon, "domain": v["domain"], "state": v["state"],
            "status": v["status"] if v["domain"] not in ("scene", "script") else "", "on": v["on"],
            "actionable": v["domain"] not in ("climate", "sensor", "binary_sensor", "water_heater", "humidifier")}


def auto_tiles(index: RoomIndex, area_id: str | None, states: dict[str, dict], limit: int = MAX_TILES) -> list[dict]:
    """The device room's 'major' entities: one of each kind first (light, climate, fan, ...), then more lights."""
    if not area_id:
        return []
    area_name = index.areas.get(area_id)
    by_domain: dict[str, list[str]] = {}
    for eid in index.room_entities(area_id):
        d = eid.split(".", 1)[0]
        if d in TILE_DOMAINS and eid in states:
            by_domain.setdefault(d, []).append(eid)
    picked: list[str] = []
    for round_no in range(limit):
        for d in TILE_DOMAINS:
            if len(picked) < limit and len(by_domain.get(d, [])) > round_no:
                picked.append(by_domain[d][round_no])
    return [tile_from_view(entity_view(states[e], display_name(states[e], index, area_name))) for e in picked]


def room_summary(index: RoomIndex, area_id: str, states: dict[str, dict]) -> dict:
    ids = [e for e in index.room_entities(area_id) if e in states]
    lights = [e for e in ids if e.startswith("light.")]
    on = sum(1 for e in lights if states[e].get("state") == "on")
    climate = next((states[e] for e in ids if e.startswith("climate.")), None)
    temp = _deg((climate or {}).get("attributes", {}).get("current_temperature"))
    parts = []
    if lights:
        parts.append(f"{on} of {len(lights)} lights on")
    if temp is not None:
        parts.append(f"{temp}°")
    return {"id": area_id, "name": index.areas[area_id], "count": len(ids), "lights_on": on, "lights": len(lights),
            "summary": " · ".join(parts) or f"{len(ids)} devices", "here": area_id == index.device_area}


def room_view(index: RoomIndex, area_id: str, states: dict[str, dict]) -> dict | None:
    if area_id not in index.areas:
        return None
    area_name = index.areas[area_id]
    sections: list[dict] = []
    for eid in index.room_entities(area_id):
        if eid not in states:
            continue
        v = entity_view(states[eid], display_name(states[eid], index, area_name))
        title = SECTION_TITLE[v["domain"]]
        if not sections or sections[-1]["title"] != title:
            sections.append({"title": title, "info": v["domain"] in INFO_DOMAINS, "items": []})
        sections[-1]["items"].append(v)
    return {"id": area_id, "name": area_name, "sections": sections, "here": area_id == index.device_area}
