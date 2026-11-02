import asyncio

import pytest

from havenos.core import Core
from havenos.core.config import ControlConfig, HAConfig
from havenos.core.ha import HAClient, HAError
from havenos.core.home import control_from, media_from, weather_from
from conftest import stock_house, wait_for


def make_client(url, token=None, **kw):
    seen = {"status": [], "states": None, "changed": []}
    c = HAClient(url, token or "good-token",
                 on_status=seen["status"].append,
                 on_states=lambda s: seen.__setitem__("states", s),
                 on_changed=lambda eid, st: seen["changed"].append((eid, st)),
                 backoff=(0.05,), **kw)
    return c, seen


async def test_connects_authenticates_and_loads_states(ha):
    ha.set("light.kitchen", "on", friendly_name="Kitchen")
    c, seen = make_client(ha.url)
    c.start()
    await wait_for(lambda: c.status == "connected")
    assert [s["entity_id"] for s in seen["states"]] == ["light.kitchen"]
    await c.stop()


async def test_state_changes_are_pushed(ha):
    ha.set("light.kitchen", "off")
    c, seen = make_client(ha.url)
    c.start()
    await wait_for(lambda: c.status == "connected")
    ha.set("light.kitchen", "on")
    await ha.push("light.kitchen")
    await wait_for(lambda: seen["changed"])
    assert seen["changed"][0][0] == "light.kitchen" and seen["changed"][0][1]["state"] == "on"
    await c.stop()


async def test_bad_token_stops_without_retry_storm(ha):
    c, seen = make_client(ha.url, token="wrong")
    c.start()
    await wait_for(lambda: c.status == "auth_failed")
    await asyncio.sleep(0.3)
    assert ha.connections == 1
    await c.stop()


async def test_reconnects_after_drop(ha):
    c, seen = make_client(ha.url)
    c.start()
    await wait_for(lambda: c.status == "connected")
    await ha.drop()
    await wait_for(lambda: ha.connections == 2 and c.status == "connected")
    assert "disconnected" in seen["status"]
    await c.stop()


async def test_service_call_and_error(ha):
    c, _ = make_client(ha.url)
    c.start()
    await wait_for(lambda: c.status == "connected")
    await c.call_service("light", "toggle", entity_id="light.kitchen")
    assert ha.calls[-1]["target"] == {"entity_id": "light.kitchen"}
    with pytest.raises(HAError, match="Service not found"):
        await c.call_service("nope", "nothing")
    await c.stop()


async def test_call_when_disconnected_raises():
    c, _ = make_client("http://127.0.0.1:1")
    with pytest.raises(HAError):
        await c.call_service("light", "toggle")


# ---- entity -> state mapping -----------------------------------------------------------------

def test_weather_mapping_uses_forecasts():
    ent = {"state": "partlycloudy", "attributes": {"temperature": 71.6}}
    fc = {"daily": [{"temperature": 78, "templow": 61}],
          "hourly": [{"datetime": "2026-10-29T18:00:00+00:00", "temperature": 74.2, "condition": "sunny"}] * 5}
    w = weather_from(ent, fc)
    assert (w["temp"], w["condition"], w["icon"], w["high"], w["low"]) == (72, "Partly cloudy", "partly", 78, 61)
    assert len(w["hourly"]) == 4 and w["hourly"][0]["icon"] == "sun" and w["hourly"][0]["temp"] == 74


def test_weather_unavailable_is_none():
    assert weather_from({"state": "unavailable", "attributes": {}}, {}) is None
    assert weather_from(None, {}) is None


def test_media_mapping():
    m = media_from({"state": "playing", "attributes": {"media_title": "T", "media_artist": "A", "media_position": 5}})
    assert m["playing"] and m["title"] == "T" and m["position"] == 5
    assert media_from({"state": "off", "attributes": {}}) is None


def test_control_mapping():
    light = control_from(ControlConfig("light.kitchen", icon=None), {"state": "on", "attributes": {"friendly_name": "Kitchen"}})
    assert (light["label"], light["icon"], light["on"], light["status"], light["actionable"]) == ("Kitchen", "bulb", True, "On", True)
    climate = control_from(ControlConfig("climate.hall", label="Climate"), {"state": "heat", "attributes": {"current_temperature": 67.8}})
    assert climate["status"] == "68°" and climate["actionable"] is False
    missing = control_from(ControlConfig("scene.movie"), None)
    assert missing["status"] == "Unavailable" and missing["on"] is False


# ---- through the core -------------------------------------------------------------------------

stock_ha = stock_house


@pytest.fixture
async def ha_core(make_config, ha):
    cfg = make_config(ha=HAConfig(url=ha.url, token=ha.TOKEN))
    stock_ha(ha, Core(cfg).device_mac)
    c = Core(cfg)
    await c.start()
    await wait_for(lambda: c.state["ha_status"] == "connected" and c.state["room"])
    yield c
    await c.stop()


async def test_core_starts_empty_not_demo_when_ha_configured(make_config, ha):
    c = Core(make_config(ha=HAConfig(url="http://127.0.0.1:1", token="x")))
    assert c.state["weather"] is None and c.state["media"] is None and c.state["controls"] == [] and c.state["rooms"] == []


async def test_core_finds_its_room_and_publishes_only_exposed_things(ha_core):
    s = ha_core.state
    assert s["room"] == {"id": "kitchen", "name": "Kitchen"}
    await wait_for(lambda: s["weather"] and s["weather"]["high"] == 80)
    assert s["weather"]["temp"] == 70 and s["weather"]["hourly"][0]["icon"] == "cloud"
    assert s["media"]["title"] == "Slow Light"                           # the room's media player, found automatically
    labels = [c["label"] for c in s["controls"]]
    assert labels == ["Main", "Climate", "Speaker"] and "Secret Lamp" not in str(s)   # tiles: this room's exposed major entities only


async def test_toggle_control_round_trips_through_ha(ha_core, ha):
    ha_core.handle("control.toggle", id="light.kitchen_main")
    await wait_for(lambda: ha_core.state["controls"][0]["on"])
    assert ha.calls[-1]["service"] == "toggle"


async def test_media_commands_call_media_player_services(ha_core, ha):
    ha_core.handle("media.toggle")
    ha_core.handle("media.next")
    await ha_core.settle()
    assert [c["service"] for c in ha.calls if c["domain"] == "media_player"] == ["media_play_pause", "media_next_track"]


async def test_live_state_change_updates_core(ha_core, ha):
    ha.set("media_player.kitchen_speaker", "playing", media_title="New Song", media_artist="X")
    await ha.push("media_player.kitchen_speaker")
    await wait_for(lambda: ha_core.state["media"]["title"] == "New Song")
    assert ha_core.state["media"]["playing"] is True


async def test_ha_error_becomes_event_not_crash(ha_core):
    errors = []
    ha_core.bus.subscribe(lambda e: e.type == "error" and errors.append(e))
    ha_core._spawn(ha_core._home.client.call_service("nope", "nothing"))
    await ha_core.settle()
    assert errors and errors[0].data["code"] == "ha"


# ---- speech to text ----------------------------------------------------------------------------------------------------

async def test_speech_to_text_uses_the_first_provider_and_homeassistants_language(ha):
    ha.set("stt.faster_whisper", "unknown", friendly_name="Whisper")
    ha.set("light.kitchen", "on")
    ha.language = "de"
    c, _ = make_client(ha.url)
    c.start()
    await wait_for(lambda: c.status == "connected")
    audio = b"\x01\x00" * 16000
    assert await c.speech_to_text(audio) == "play some jazz"
    req = ha.stt_requests[0]
    assert req["entity"] == "stt.faster_whisper" and req["audio"] == audio
    assert "sample_rate=16000" in req["headers"]["X-Speech-Content"] and "language=de" in req["headers"]["X-Speech-Content"]
    assert req["headers"]["Authorization"] == "Bearer good-token"
    await c.speech_to_text(audio, entity_id="stt.other", language="fr")          # explicit settings win
    assert ha.stt_requests[1]["entity"] == "stt.other" and "language=fr" in ha.stt_requests[1]["headers"]["X-Speech-Content"]
    await c.stop()


async def test_speech_to_text_failures_are_reported_plainly(ha):
    c, _ = make_client(ha.url)
    c.start()
    await wait_for(lambda: c.status == "connected")
    with pytest.raises(HAError, match="no speech-to-text provider"):
        await c.speech_to_text(b"\0\0")
    ha.set("stt.w", "unknown")
    c2, _ = make_client(ha.url)
    c2.start()
    await wait_for(lambda: c2.status == "connected")
    ha.stt_status = 500
    with pytest.raises(HAError, match="500"):
        await c2.speech_to_text(b"\0\0")
    ha.stt_status, ha.stt_text = 200, None                                        # HA answered "error"
    with pytest.raises(HAError, match="did not understand"):
        await c2.speech_to_text(b"\0\0")
    await c.stop()
    await c2.stop()
