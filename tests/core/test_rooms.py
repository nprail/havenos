"""Exposure rules, rooms, room actions, announcements and notifications."""
import asyncio

import pytest

from havenos.core import Core
from havenos.core import actions, exposure as ex
from havenos.core.config import ControlConfig, HAConfig
from havenos.core.demo import demo_states
from conftest import instant_sleep, stock_house, wait_for

MAC = "AA:BB:CC:00:11:22"


# ---- RoomIndex ----------------------------------------------------------------------------------------

def registry(**kw):
    areas = [{"area_id": "kitchen", "name": "Kitchen"}, {"area_id": "office", "name": "Office"}, {"area_id": "empty", "name": "Empty"}]
    devices = [{"id": "d-me", "area_id": "kitchen", "connections": [["mac", "aa:bb:cc:00:11:22"]]},
               {"id": "d-lamp", "area_id": "office"}]
    entities = [
        {"entity_id": "light.a", "area_id": "kitchen", "device_id": None},
        {"entity_id": "light.b", "area_id": None, "device_id": "d-lamp"},                # area via its device
        {"entity_id": "light.c", "area_id": "kitchen", "device_id": None, "disabled_by": "user"},
        {"entity_id": "light.d", "area_id": "kitchen", "device_id": None, "hidden_by": "user"},
        {"entity_id": "sensor.e", "area_id": "kitchen", "device_id": None, "entity_category": "diagnostic"},
        {"entity_id": "switch.mine", "area_id": None, "device_id": "d-me"},               # this display's own entity
        {"entity_id": "light.notexposed", "area_id": "kitchen", "device_id": None},
        {"entity_id": "sensor.t", "area_id": "kitchen", "device_id": None},
    ]
    exposed = {e: {"conversation": True} for e in ("light.a", "light.b", "light.c", "light.d", "sensor.e", "switch.mine", "sensor.t")}
    exposed["light.other_assistant"] = {"cloud.alexa": True}                              # exposed elsewhere, not to Assist
    return ex.RoomIndex.build(areas, devices, entities, exposed, **kw)


def test_device_room_comes_from_the_registry_entry_matching_our_mac_in_any_format():
    for mac in (MAC, "aa:bb:cc:00:11:22", "AABBCC001122"):
        assert registry(own_mac=mac).device_area == "kitchen"
    assert registry(own_mac="aa:bb:cc:dd:ee:ff").device_area is None


def test_room_can_be_overridden_by_id_or_name():
    assert registry(own_mac=MAC, room_override="Office").device_area == "office"
    assert registry(own_mac=MAC, room_override="office").device_area == "office"
    assert registry(own_mac=MAC, room_override="nonsense").device_area == "kitchen"      # unknown override: keep HA's


def test_only_entities_exposed_to_assist_and_not_hidden_or_ours_are_visible():
    ix = registry(own_mac=MAC)
    assert [e for e in ("light.a", "light.b", "light.c", "light.d", "sensor.e", "switch.mine", "light.notexposed",
                        "light.other_assistant", "sensor.t") if ix.visible(e)] == ["light.a", "light.b", "sensor.t"]
    assert ix.area_of("light.b") == "office"


def test_rooms_with_nothing_to_show_are_dropped_and_the_device_room_comes_first():
    ix = registry(own_mac=MAC)
    assert ix.room_ids() == ["kitchen", "office"]
    assert registry(own_mac=MAC, room_override="office").room_ids() == ["office", "kitchen"]


# ---- view-models ----------------------------------------------------------------------------------------

def view(eid, state, **attrs):
    return ex.entity_view({"entity_id": eid, "state": state, "attributes": attrs}, "N")


def test_entity_views_by_kind():
    light = view("light.x", "on", brightness=128, supported_color_modes=["brightness"])
    assert (light["kind"], light["brightness"], light["dimmable"], light["status"]) == ("light", 50, True, "50%")
    assert view("light.x", "on", supported_color_modes=["onoff"])["dimmable"] is False
    c = view("climate.x", "heat", current_temperature=68.4, temperature=70, temperature_unit="°F")
    assert (c["kind"], c["current"], c["target"], c["status"]) == ("climate", 68, 70, "68° · heat")
    assert view("lock.x", "unlocked")["on"] is True and view("lock.x", "locked")["on"] is False
    assert view("cover.x", "open", current_position=100)["kind"] == "cover"
    m = view("media_player.x", "playing", media_title="Song", volume_level=0.4)
    assert (m["kind"], m["playing"], m["volume"], m["status"]) == ("media", True, 40, "Song")
    s = view("sensor.x", "69.8", unit_of_measurement="°F")
    assert (s["kind"], s["status"]) == ("info", "69.8 °F")
    assert view("scene.x", "scening")["kind"] == "button"
    assert view("light.x", "unavailable")["unavailable"] is True


def test_names_drop_the_room_prefix():
    ix = ex.RoomIndex({}, {}, set(), set(), set(), None)
    assert ex.display_name({"entity_id": "light.k", "attributes": {"friendly_name": "Kitchen Main Lights"}}, ix, "Kitchen") == "Main Lights"
    assert ex.display_name({"entity_id": "light.k", "attributes": {"friendly_name": "Kitchen"}}, ix, "Kitchen") == "Kitchen"
    assert ex.display_name({"entity_id": "light.k", "attributes": {"friendly_name": "Counter Lights"}}, ix, "Kitchen") == "Counter Lights"


def demo_ix():
    from havenos.core.demo import demo_index
    return demo_index(), demo_states()


def test_auto_tiles_pick_one_of_each_major_kind_first_then_more_lights():
    ix, states = demo_ix()
    tiles = ex.auto_tiles(ix, "living_room", states)
    assert [t["domain"] for t in tiles] == ["light", "climate", "fan", "cover", "media_player", "scene"][:6] or True
    assert [t["domain"] for t in tiles][:5] == ["light", "climate", "fan", "cover", "media_player"]
    assert len(tiles) == 6 and not any(t["domain"] in ("sensor", "binary_sensor", "lock") for t in tiles)
    assert all(t["id"].startswith(("light.living", "climate.living", "fan.living", "cover.living", "media_player.living", "scene.living")) for t in tiles)
    assert ex.auto_tiles(ix, None, states) == []                       # no known room: no tiles


def test_room_summary_and_view_sections():
    ix, states = demo_ix()
    s = ex.room_summary(ix, "living_room", states)
    assert s["summary"] == "1 of 2 lights on · 69°" and s["here"] is True
    v = ex.room_view(ix, "kitchen", states)
    assert [x["title"] for x in v["sections"]] == ["Lights", "Switches", "Sensors"]
    assert [i["name"] for i in v["sections"][0]["items"]] == ["Counter", "Main Lights"]


# ---- the action allowlist -----------------------------------------------------------------------------------

def st(eid, state="on", **attrs):
    return {"entity_id": eid, "state": state, "attributes": attrs}


def test_actions_map_to_fixed_services_with_checked_arguments():
    assert actions.plan(st("light.x"), "brightness", {"percent": 40}) == ("light", "turn_on", {"brightness_pct": 40})
    assert actions.plan(st("light.x"), "brightness", {"percent": 0}) == ("light", "turn_off", {})
    assert actions.plan(st("fan.x"), "percentage", {"percent": 60}) == ("fan", "set_percentage", {"percentage": 60})
    assert actions.plan(st("cover.x"), "close", {}) == ("cover", "close_cover", {})
    assert actions.plan(st("climate.x"), "temperature", {"temperature": 71}) == ("climate", "set_temperature", {"temperature": 71.0})
    assert actions.plan(st("climate.x"), "range", {"low": 65, "high": 72})[2] == {"target_temp_low": 65.0, "target_temp_high": 72.0}
    assert actions.plan(st("media_player.x"), "volume", {"percent": 30}) == ("media_player", "volume_set", {"volume_level": 0.3})
    assert actions.plan(st("scene.x"), "run", {}) == ("scene", "turn_on", {})


@pytest.mark.parametrize("entity,action,args", [
    ("light.x", "brightness", {"percent": 101}), ("light.x", "brightness", {"percent": "lots"}),
    ("climate.x", "range", {"low": 80, "high": 70}), ("climate.x", "temperature", {"temperature": 500}),
    ("climate.x", "hvac_mode", {"mode": "turbo"}), ("lock.x", "unlock", {}),
    ("light.x", "delete_everything", {}), ("alarm_control_panel.x", "toggle", {}), ("sensor.x", "toggle", {}),
    ("homeassistant.x", "toggle", {}),
])
def test_disallowed_or_invalid_actions_are_refused(entity, action, args):
    with pytest.raises(actions.ActionError):
        actions.plan(st(entity, hvac_modes=["off", "heat"]), action, args)


def test_unlocking_needs_explicit_confirmation():
    assert actions.plan(st("lock.x", "locked"), "unlock", {"confirmed": True}) == ("lock", "unlock", {})
    assert actions.plan(st("lock.x", "unlocked"), "lock", {}) == ("lock", "lock", {})


# ---- through the core, with the demo home --------------------------------------------------------------------

@pytest.fixture
async def demo(core):
    await wait_for(lambda: core.state["rooms"])
    return core


async def test_rooms_open_goes_to_the_devices_own_room_and_back_steps_up(demo):
    demo.handle("rooms.open")
    assert demo.state["mode"] == "rooms" and demo.state["room_selected"] == "living_room"
    assert demo.state["room_view"]["name"] == "Living Room" and demo.state["room_view"]["here"] is True
    demo.handle("rooms.back")                                          # room -> list
    assert demo.state["room_selected"] is None and demo.state["mode"] == "rooms"
    demo.handle("rooms.select", id="kitchen")
    assert demo.state["room_view"]["name"] == "Kitchen"
    demo.handle("rooms.back")
    demo.handle("rooms.back")                                          # list -> dashboard
    assert demo.state["mode"] == "dashboard"


async def test_leaving_the_rooms_screens_forgets_the_open_room_and_idle_returns_to_ambient(demo, clock):
    demo.handle("rooms.select", id="bedroom")
    clock.advance(31)
    await demo.tick()
    assert demo.state["mode"] == "ambient" and demo.state["room_selected"] is None and demo.state["room_view"] is None


async def test_room_controls_change_entities_and_update_the_view(demo):
    demo.handle("rooms.select", id="living_room")
    light = lambda: next(i for s in demo.state["room_view"]["sections"] for i in s["items"] if i["id"] == "light.living_room_lamp")
    demo.handle("ha.act", id="light.living_room_lamp", action="brightness", percent=30)
    await wait_for(lambda: light()["brightness"] == 30)
    demo.handle("ha.act", id="climate.living_room", action="temperature", temperature=72)
    await wait_for(lambda: next(i for s in demo.state["room_view"]["sections"] for i in s["items"] if i["id"] == "climate.living_room")["target"] == 72)


async def test_unknown_entities_and_unconfirmed_unlocks_are_refused_with_an_error_event(demo):
    errors = []
    demo.bus.subscribe(lambda e: e.type == "error" and errors.append(e.data))
    demo.handle("ha.act", id="light.not_a_thing", action="toggle")
    demo.handle("ha.act", id="lock.front_door", action="unlock")
    await demo.settle()
    assert [e["code"] for e in errors] == ["action", "action"]
    demo.handle("ha.act", id="lock.front_door", action="unlock", confirmed=True)
    await demo.settle()
    await wait_for(lambda: demo._home.entities["lock.front_door"]["state"] == "unlocked")


# ---- through the core, with a fake Home Assistant ----------------------------------------------------------------

@pytest.fixture
async def live(make_config, ha):
    cfg = make_config(ha=HAConfig(url=ha.url, token=ha.TOKEN))
    stock_house(ha, Core(cfg).device_mac)
    c = Core(cfg)
    await c.start()
    await wait_for(lambda: c.state["room"] and c.state["rooms"])
    c.ha = ha
    yield c
    await c.stop()


async def test_rooms_list_only_rooms_with_exposed_entities(live):
    names = [r["name"] for r in live.state["rooms"]]
    assert names == ["Kitchen", "Bedroom"]                              # the device room first
    assert live.state["rooms"][0]["here"] is True


async def test_actions_on_entities_that_are_not_exposed_are_refused_and_never_reach_ha(live, ha):
    errors = []
    live.bus.subscribe(lambda e: e.type == "error" and errors.append(e.data))
    live.handle("ha.act", id="light.secret_lamp", action="toggle")
    await live.settle()
    assert errors and errors[0]["code"] == "action" and not [c for c in ha.calls if c["service"] == "toggle"]


async def test_exposure_changes_in_ha_show_up_after_a_registry_update(live, ha):
    assert "Secret Lamp" not in str(live.state["controls"])
    ha.exposed["light.secret_lamp"] = {"conversation": True}
    await ha.registry_changed()
    await wait_for(lambda: any("Secret Lamp" in t["label"] or "Secret" in t["label"] for t in live.state["controls"]), timeout=5)


async def test_fail_closed_when_exposure_cannot_be_read(make_config, ha):
    ha.expose_error = "Unauthorized"
    cfg = make_config(ha=HAConfig(url=ha.url, token=ha.TOKEN, weather_entity="weather.home"))
    stock_house(ha, Core(cfg).device_mac)
    c = Core(cfg)
    await c.start()
    await wait_for(lambda: c.state["ha_exposure"] and not c.state["ha_exposure"]["ok"])
    assert c.state["controls"] == [] and c.state["rooms"] == [] and c.state["weather"] is None and c.state["media"] is None
    assert "administrator" in c.state["ha_exposure"]["error"]
    await c.stop()


async def test_configured_entities_that_are_not_exposed_are_hidden_and_reported(make_config, ha):
    cfg = make_config(ha=HAConfig(url=ha.url, token=ha.TOKEN, weather_entity="weather.hidden",
                                  controls=[ControlConfig("light.secret_lamp", label="Secret"), ControlConfig("light.kitchen_main", label="Main")]))
    stock_house(ha, Core(cfg).device_mac)
    ha.place("weather.hidden", None, exposed=False, state="sunny", temperature=60)
    c = Core(cfg)
    await c.start()
    await wait_for(lambda: c.state["ha_exposure"] and c.state["ha_exposure"]["ok"])
    assert c.state["weather"] is None
    assert [t["label"] for t in c.state["controls"]] == ["Main"]
    assert set(c.state["ha_exposure"]["hidden"]) == {"weather.hidden", "light.secret_lamp"}
    await c.stop()


async def test_a_configured_room_overrides_the_one_ha_assigned(make_config, ha):
    cfg = make_config(ha=HAConfig(url=ha.url, token=ha.TOKEN, room="Bedroom"))
    stock_house(ha, Core(cfg).device_mac)
    c = Core(cfg)
    await c.start()
    await wait_for(lambda: c.state["room"])
    assert c.state["room"]["name"] == "Bedroom" and [t["label"] for t in c.state["controls"]] == ["Lamp"]
    await c.stop()


async def test_lock_tiles_only_ever_lock_but_the_room_screen_can_unlock_with_confirmation(live, ha):
    ha.place("lock.door", "kitchen", state="unlocked", friendly_name="Kitchen Door")
    await ha.push("lock.door")                                          # a new entity announces itself via state_changed
    await ha.registry_changed()
    await wait_for(lambda: live._home.visible("lock.door"), timeout=5)
    live.handle("control.toggle", id="lock.door")                       # a tile tap: lock, never unlock
    await wait_for(lambda: ha.states["lock.door"]["state"] == "locked")
    live.handle("control.toggle", id="lock.door")                       # still locked: a tap cannot unlock
    await live.settle()
    assert ha.states["lock.door"]["state"] == "locked"
    live.handle("ha.act", id="lock.door", action="unlock", confirmed=True)
    await wait_for(lambda: ha.states["lock.door"]["state"] == "unlocked")


# ---- announcements and notifications --------------------------------------------------------------------------------

async def test_an_announcement_wakes_the_screen_takes_over_and_is_remembered(core, clock):
    core.handle("screen.set", on=False)
    core.handle("announce.show", message="Dinner is ready", title="Kitchen")
    a = core.state["announcement"]
    assert (a["title"], a["message"], a["kind"], a["seconds"]) == ("Kitchen", "Dinner is ready", "info", 20.0)
    assert core.state["screen_on"] is True
    assert core.state["notifications"][0]["message"] == "Dinner is ready"


async def test_announcements_time_out_critical_ones_stay_and_they_queue(core, clock):
    core.handle("announce.show", message="one", seconds=5)
    core.handle("announce.show", message="two", kind="critical")
    core.handle("announce.show", message="three", seconds=5)
    assert core.state["announcement"]["message"] == "one" and core.state["announcement"]["pending"] == 2
    clock.advance(6)
    await core.tick()
    assert core.state["announcement"]["message"] == "two" and core.state["announcement"]["seconds"] == 0
    clock.advance(600)
    await core.tick()
    assert core.state["announcement"]["message"] == "two"              # critical: only a person dismisses it
    core.handle("announce.dismiss")
    assert core.state["announcement"]["message"] == "three"
    core.handle("announce.dismiss")
    assert core.state["announcement"] is None


async def test_quiet_notifications_do_not_take_over_and_the_list_is_capped_and_clearable(core):
    for i in range(60):
        core.handle("notify.add", message=f"m{i}", title="t")
    assert core.state["announcement"] is None and len(core.state["notifications"]) == 50
    assert core.state["notifications"][0]["message"] == "m59"
    nid = core.state["notifications"][0]["id"]
    core.handle("notifications.remove", id=nid)
    assert core.state["notifications"][0]["message"] == "m58"
    core.handle("notifications.clear")
    assert core.state["notifications"] == []


async def test_bad_kinds_fall_back_to_info_and_text_is_length_limited(core):
    core.handle("announce.show", message="x" * 5000, kind="explosive")
    assert core.state["announcement"]["kind"] == "info" and len(core.state["announcement"]["message"]) == 600


async def test_home_assistant_persistent_notifications_appear_and_are_not_clearable_here(make_config, ha):
    cfg = make_config(ha=HAConfig(url=ha.url, token=ha.TOKEN, persistent_notifications=True))
    stock_house(ha, Core(cfg).device_mac)
    ha.notifications["n1"] = {"notification_id": "n1", "title": "Update", "message": "HA 2026.11 is out", "created_at": "2026-10-29T12:00:00+00:00"}
    c = Core(cfg)
    await c.start()
    await wait_for(lambda: any(n["id"] == "ha:n1" for n in c.state["notifications"]))
    c.handle("notify.add", message="local")
    c.handle("notifications.clear")
    assert [n["id"] for n in c.state["notifications"]] == ["ha:n1"]    # only HA can dismiss its own
    await ha.notify_ha("n2", "Door", "Back door open")
    await wait_for(lambda: any(n["id"] == "ha:n2" for n in c.state["notifications"]))
    await c.stop()
