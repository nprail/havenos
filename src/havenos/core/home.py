"""Maps Home Assistant onto havenOS state: weather, media, the device room's quick tiles, room screens, notifications,
and the commands that go back. Everything shown here passes the exposure rules in `exposure.py`.

HomeBase holds the model and all UI-facing logic and talks to the outside through one method, `_call`. HomeIntegration
implements it over the HA WebSocket; DemoHome (demo.py) implements it over a few fake entities, so the room screens
work and are testable with no Home Assistant at all.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Callable

from . import actions
from . import exposure as ex
from .config import ControlConfig, HAConfig
from .ha import HAClient, HAError

log = logging.getLogger(__name__)

# HA weather condition -> (label, icon). Icons: sun | partly | cloud (what the UI has art for).
CONDITIONS = {
    "sunny": ("Sunny", "sun"), "clear-night": ("Clear", "sun"),
    "partlycloudy": ("Partly cloudy", "partly"), "cloudy": ("Cloudy", "cloud"),
    "rainy": ("Rain", "cloud"), "pouring": ("Heavy rain", "cloud"), "snowy": ("Snow", "cloud"),
    "snowy-rainy": ("Sleet", "cloud"), "fog": ("Fog", "cloud"), "hail": ("Hail", "cloud"),
    "lightning": ("Thunderstorm", "cloud"), "lightning-rainy": ("Thunderstorm", "cloud"),
    "windy": ("Windy", "partly"), "windy-variant": ("Windy", "partly"), "exceptional": ("Exceptional", "cloud"),
}
TOGGLE_DOMAINS = {"light", "switch", "fan", "input_boolean", "cover"}
BUTTON_DOMAINS = {"scene", "script"}
DEFAULT_ICONS = {"light": "bulb", "switch": "plug", "climate": "thermo", "camera": "camera", "fan": "fan",
                 "cover": "blinds", "media_player": "speaker", "alarm_control_panel": "camera", "lock": "lock",
                 "scene": "scenes"}
ON_STATES = ex.ON_STATES
PUBLISH_DEBOUNCE_S = 0.25
REGISTRY_REFRESH_S = 300.0           # exposure changes fire no event, so poll; registry edits refresh sooner


def hour_label(iso: str) -> str:
    h = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone().hour
    return f"{h % 12 or 12} {'AM' if h < 12 else 'PM'}"


def _deg(v: Any) -> int | None:
    return None if v is None else round(float(v))


def weather_from(entity: dict | None, forecasts: dict) -> dict | None:
    if not entity or entity.get("state") in (None, "unavailable", "unknown"):
        return None
    attrs = entity.get("attributes", {})
    label, icon = CONDITIONS.get(entity["state"], (entity["state"].replace("-", " ").title(), "cloud"))
    daily = (forecasts.get("daily") or [{}])[0]
    hourly = [{"label": hour_label(f["datetime"]),
               "icon": CONDITIONS.get(f.get("condition", ""), ("", "cloud"))[1],
               "temp": _deg(f.get("temperature"))} for f in (forecasts.get("hourly") or [])[:4]]
    return {"temp": _deg(attrs.get("temperature")), "condition": label, "icon": icon,
            "high": _deg(daily.get("temperature")), "low": _deg(daily.get("templow")), "hourly": hourly}


def media_from(entity: dict | None) -> dict | None:
    if not entity or entity.get("state") in (None, "unavailable", "unknown", "off"):
        return None
    a = entity.get("attributes", {})
    return {"title": a.get("media_title") or "", "artist": a.get("media_artist") or "",
            "playing": entity["state"] == "playing",
            "position": a.get("media_position"), "duration": a.get("media_duration")}


def control_from(cfg: ControlConfig, entity: dict | None) -> dict:
    """A tile for an entity the user listed explicitly in the config (the automatic tiles come from exposure.auto_tiles)."""
    domain = cfg.entity_id.split(".", 1)[0]
    attrs = (entity or {}).get("attributes", {})
    state = (entity or {}).get("state", "unavailable")
    if state == "unavailable" or entity is None:
        status = "Unavailable"
    elif domain == "climate":
        cur = attrs.get("current_temperature")
        status = f"{round(float(cur))}°" if cur is not None else state.title()
    elif domain in BUTTON_DOMAINS:
        status = ""
    else:
        status = state.replace("_", " ").title()
    return {
        "id": cfg.entity_id,
        "label": cfg.label or attrs.get("friendly_name") or cfg.entity_id,
        "icon": cfg.icon or DEFAULT_ICONS.get(domain, "gear"),
        "domain": domain, "state": state, "status": status,
        "on": state in ON_STATES, "actionable": domain in TOGGLE_DOMAINS | BUTTON_DOMAINS | {"lock"},
    }


class HomeBase:
    """Model + UI-facing logic. Subclasses provide `_call` and keep `entities` / `index` current."""

    def __init__(self, patch: Callable[..., None], *, weather_entity: str | None = None, media_entity: str | None = None,
                 controls: list[ControlConfig] | None = None) -> None:
        self._patch = patch
        self.weather_cfg, self.media_cfg, self.controls_cfg = weather_entity, media_entity, controls or []
        self.entities: dict[str, dict] = {}
        self.forecasts: dict[str, list] = {}
        self.index: ex.RoomIndex | None = None
        self.exposure_error: str | None = None
        self.selected: str | None = None
        self._publish_handle: asyncio.TimerHandle | None = None

    # ---- what is shown ---------------------------------------------------------------------------

    def visible(self, entity_id: str) -> bool:
        return bool(self.index and self.index.visible(entity_id))

    @property
    def weather_id(self) -> str | None:
        if self.weather_cfg:
            return self.weather_cfg if self.visible(self.weather_cfg) else None
        return self.index.first_visible("weather") if self.index else None

    @property
    def media_id(self) -> str | None:
        if self.media_cfg:
            return self.media_cfg if self.visible(self.media_cfg) else None
        return self.index.first_visible("media_player", self.index.device_area) if self.index and self.index.device_area else None

    def _weather_value(self) -> dict | None:
        wid = self.weather_id
        return weather_from(self.entities.get(wid), self.forecasts) if wid else None

    def _tiles(self) -> list[dict]:
        if not self.index:
            return []
        if self.controls_cfg:
            return [control_from(c, self.entities.get(c.entity_id)) for c in self.controls_cfg if self.visible(c.entity_id)]
        return ex.auto_tiles(self.index, self.index.device_area, self.entities)

    def _hidden_config(self) -> list[str]:
        """Entities named in the config that are not exposed to Assist, so the settings page can say why they are missing."""
        wanted = [e for e in (self.weather_cfg, self.media_cfg, *[c.entity_id for c in self.controls_cfg]) if e]
        return [e for e in wanted if not self.visible(e)] if self.index else []

    def exposure_info(self) -> dict:
        if not self.index:
            return {"ok": False, "error": self.exposure_error or "waiting for Home Assistant", "exposed": 0, "hidden": []}
        return {"ok": True, "error": "", "exposed": sum(1 for e in self.index.exposed if self.index.visible(e)),
                "hidden": self._hidden_config()}

    def publish_all(self) -> None:
        ix = self.index
        changes: dict[str, Any] = {"weather": self._weather_value(), "media": media_from(self.entities.get(self.media_id)) if self.media_id else None,
                                   "controls": self._tiles(), "ha_exposure": self.exposure_info()}
        if ix:
            changes["room"] = ({"id": ix.device_area, "name": ix.areas[ix.device_area]}
                               if ix.device_area in ix.areas else None)
            changes["rooms"] = [ex.room_summary(ix, a, self.entities) for a in ix.room_ids()]
            if self.selected and self.selected not in ix.room_ids():
                self.selected = None
            changes["room_selected"] = self.selected
            changes["room_view"] = ex.room_view(ix, self.selected, self.entities) if self.selected else None
        else:
            changes.update(room=None, rooms=[], room_selected=None, room_view=None)
        self._patch(**changes)

    def schedule_publish(self) -> None:
        """Coalesce bursts of state changes into one UI update."""
        if self._publish_handle is None:
            self._publish_handle = asyncio.get_running_loop().call_later(PUBLISH_DEBOUNCE_S, self._run_publish)

    def _run_publish(self) -> None:
        self._publish_handle = None
        self.publish_all()

    # ---- room navigation ---------------------------------------------------------------------------

    def select_room(self, area_id: str | None) -> None:
        self.selected = area_id if (self.index and area_id in self.index.room_ids()) else None
        self.publish_all()

    # ---- commands ------------------------------------------------------------------------------------

    async def _call(self, domain: str, service: str, entity_id: str, data: dict | None = None) -> None:
        raise NotImplementedError

    async def act(self, entity_id: str, action: str, **args: Any) -> None:
        """A touch on a room screen. Exposure and the action allowlist are enforced here, not trusted from the UI."""
        if not self.visible(entity_id):
            raise actions.ActionError(f"{entity_id} is not exposed to this device")
        state = self.entities.get(entity_id)
        if state is None:
            raise actions.ActionError(f"{entity_id} is not available")
        domain, service, data = actions.plan(state, action, args)
        await self._call(domain, service, entity_id, data)

    async def toggle_control(self, entity_id: str) -> None:
        """A quick-tile tap: the obvious action for the entity's kind (locks only ever lock from here)."""
        domain = entity_id.split(".", 1)[0]
        if domain in BUTTON_DOMAINS:
            await self.act(entity_id, "run")
        elif domain == "lock":
            await self.act(entity_id, "lock")
        elif domain == "media_player":
            await self.act(entity_id, "playpause")
        elif domain == "vacuum":
            await self.act(entity_id, "dock" if self.entities.get(entity_id, {}).get("state") == "cleaning" else "start")
        elif domain in TOGGLE_DOMAINS:
            await self.act(entity_id, "toggle")

    async def media(self, action: str) -> None:
        mid = self.media_id
        if mid:
            await self.act(mid, {"toggle": "playpause", "next": "next", "prev": "prev"}[action])


class HomeIntegration(HomeBase):
    def __init__(self, cfg: HAConfig, patch: Callable[..., None], *, own_mac: str | None = None,
                 on_ha_notifications: Callable[[list[dict]], None] | None = None) -> None:
        super().__init__(patch, weather_entity=cfg.weather_entity, media_entity=cfg.media_entity, controls=cfg.controls)
        self.cfg = cfg
        self.own_mac = own_mac
        self._on_ha_notifications = on_ha_notifications
        self._persistent: dict[str, dict] = {}
        self._forecast_task: asyncio.Task | None = None
        self._registry_task: asyncio.Task | None = None
        self._registry_wake = asyncio.Event()
        self._registry_fast = True                   # first load after (re)connect has nothing to wait for
        self._forecast_wake = asyncio.Event()
        self.client = HAClient(cfg.url, cfg.token, on_status=self._on_status,
                               on_states=self._on_states, on_changed=self._on_changed)
        for event_type in ("entity_registry_updated", "device_registry_updated", "area_registry_updated"):
            self.client.add_subscription({"type": "subscribe_events", "event_type": event_type}, lambda ev: self.refresh_soon())
        if cfg.persistent_notifications:
            self.client.add_subscription({"type": "persistent_notification/subscribe"}, self._on_persistent)

    def start(self) -> None:
        self.client.start()
        self._forecast_task = asyncio.create_task(self._forecast_loop(), name="ha-forecast")
        self._registry_task = asyncio.create_task(self._registry_loop(), name="ha-registry")

    async def stop(self) -> None:
        tasks = [t for t in (self._forecast_task, self._registry_task) if t]
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if self._publish_handle:
            self._publish_handle.cancel()
        await self.client.stop()

    # ---- HA -> state ------------------------------------------------------------------

    def _on_status(self, status: str) -> None:
        self._patch(ha_status=status)
        if status == "connected":
            self._forecast_wake.set()
            self._registry_fast = True
            self._registry_wake.set()
        else:
            self._persistent.clear()

    def _on_states(self, states: list[dict]) -> None:
        self.entities = {s["entity_id"]: s for s in states}
        self.publish_all()

    def _on_changed(self, entity_id: str | None, new_state: dict | None) -> None:
        if not entity_id:
            return
        if new_state is None:
            self.entities.pop(entity_id, None)
        else:
            self.entities[entity_id] = new_state
        if self.visible(entity_id) or entity_id in (self.weather_id, self.media_id):
            self.schedule_publish()          # only entities that can appear on screen cost a refresh

    def _on_persistent(self, ev: dict) -> None:
        notifs = ev.get("notifications") or {}
        if ev.get("type") in ("current", "added", "updated"):
            self._persistent.update(notifs)
        elif ev.get("type") == "removed":
            for nid in notifs:
                self._persistent.pop(nid, None)
        if self._on_ha_notifications:
            self._on_ha_notifications([{"id": f"ha:{k}", "title": v.get("title") or "Home Assistant",
                                        "message": v.get("message") or "", "kind": "info",
                                        "created": v.get("created_at") or ""} for k, v in self._persistent.items()])

    # ---- registries (areas, devices, exposure) -------------------------------------------------

    def refresh_soon(self) -> None:
        self._registry_wake.set()

    async def _registry_loop(self) -> None:
        while True:
            try:
                await asyncio.wait_for(self._registry_wake.wait(), REGISTRY_REFRESH_S)
            except asyncio.TimeoutError:
                pass
            self._registry_wake.clear()
            if not self._registry_fast:
                await asyncio.sleep(1.0)             # let a burst of registry edits settle
            self._registry_fast = False
            await self.refresh_registry()

    async def refresh_registry(self) -> None:
        if self.client.status != "connected":
            return
        req = self.client.request
        try:
            areas, devices, entities, exposed = await asyncio.gather(
                req({"type": "config/area_registry/list"}), req({"type": "config/device_registry/list"}),
                req({"type": "config/entity_registry/list"}), req({"type": "homeassistant/expose_entity/list"}))
        except HAError as e:
            # Fail closed: if we cannot tell what is exposed, show nothing from HA. (These commands need an admin user's token.)
            log.warning("cannot read exposure settings: %s", e)
            self.index, self.exposure_error = None, f"could not read exposure settings ({e}); the access token's user must be an administrator"
            self.publish_all()
            return
        self.exposure_error = None
        self.index = ex.RoomIndex.build(areas, devices, entities, (exposed or {}).get("exposed_entities", {}),
                                        own_mac=self.own_mac, room_override=self.cfg.room)
        self.publish_all()
        self._forecast_wake.set()

    # ---- forecasts (a service call with a response, not an entity attribute) -----------------

    async def _forecast_loop(self) -> None:
        while True:
            try:
                await asyncio.wait_for(self._forecast_wake.wait(), self.cfg.forecast_refresh_s)
            except asyncio.TimeoutError:
                pass
            self._forecast_wake.clear()
            await self.refresh_forecasts()

    async def refresh_forecasts(self) -> None:
        eid = self.weather_id
        if not eid or self.client.status != "connected":
            return
        for kind in ("daily", "hourly"):
            try:
                res = await self.client.call_service("weather", "get_forecasts", entity_id=eid,
                                                     data={"type": kind}, return_response=True)
                self.forecasts[kind] = ((res or {}).get("response") or {}).get(eid, {}).get("forecast", [])
            except HAError as e:
                log.warning("forecast %s unavailable: %s", kind, e)
        self.publish_all()

    # ---- commands -----------------------------------------------------------------------

    async def _call(self, domain: str, service: str, entity_id: str, data: dict | None = None) -> None:
        await self.client.call_service(domain, service, entity_id=entity_id, data=data or None)
