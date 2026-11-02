import json
import os
import stat
import tomllib
from pathlib import Path

import aiohttp
import pytest

from havenos.core import Config, Core
from havenos.core.settings import SettingsError, apply_update, public_view
from havenos.core.web import WebUI
from conftest import wait_for
from fakes import FakeImmich

ASSETS = Path(__file__).resolve().parents[2] / "src" / "havenos" / "assets"
H = {"X-Requested-With": "havenos"}


@pytest.fixture
async def ui(tmp_path, photo_dir, monkeypatch):
    for k in [k for k in os.environ if k.startswith("HAVENOS_")]:
        monkeypatch.delenv(k)
    cfgdir = tmp_path / "cfg"
    monkeypatch.setenv("HAVENOS_CONFIG", str(cfgdir / "config.toml"))
    monkeypatch.setenv("HAVENOS_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("HAVENOS_PHOTOS", str(photo_dir))
    monkeypatch.setenv("HAVENOS_WEB_PORT", "0")
    monkeypatch.setenv("HAVENOS_WEB_HOST", "127.0.0.1")
    core = Core(Config.from_env(ASSETS))
    await core.start()
    web = WebUI(core, ASSETS)
    assert await web.start()
    web.cfgdir = cfgdir
    yield web
    await web.stop()
    await core.stop()


def url(web, path):
    return f"http://127.0.0.1:{web.port}{path}"


async def login(web, session):
    r = await session.post(url(web, "/api/login"), json={"code": web.code}, headers=H)
    assert r.status == 200
    return r


async def test_page_and_static_assets_are_served(ui):
    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as s:
        for path, kind in (("/", "text/html"), ("/static/app.css", "text/css"), ("/static/app.js", "javascript")):
            r = await s.get(url(ui, path))
            assert r.status == 200 and kind in r.headers["Content-Type"]
        assert "no-store" in (await s.get(url(ui, "/"))).headers["Cache-Control"]


async def test_api_requires_login(ui):
    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as s:
        for method, path in (("get", "/api/config"), ("get", "/api/status"), ("post", "/api/test/ha"), ("put", "/api/config")):
            r = await s.request(method, url(ui, path), headers=H, json={})
            assert r.status == 401, path
        assert (await (await s.get(url(ui, "/api/session"))).json()) == {"authenticated": False}


async def test_login_cookie_flags_and_session(ui):
    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as s:
        r = await login(ui, s)
        cookie = r.headers["Set-Cookie"].lower()
        assert "httponly" in cookie and "samesite=strict" in cookie
        assert (await (await s.get(url(ui, "/api/session"))).json()) == {"authenticated": True}
        assert (await s.get(url(ui, "/api/config"))).status == 200
        await s.post(url(ui, "/api/logout"), headers=H, json={})
        assert (await s.get(url(ui, "/api/config"))).status == 401


async def test_wrong_code_is_rate_limited_then_locked_out(ui):
    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as s:
        codes = [(await s.post(url(ui, "/api/login"), json={"code": "WRONG-000"}, headers=H)).status for _ in range(6)]
        assert codes == [401] * 5 + [429]
        r = await s.post(url(ui, "/api/login"), json={"code": ui.code}, headers=H)
        assert r.status == 429                      # even the right code is refused during the lockout


async def test_state_changing_calls_need_the_csrf_header(ui):
    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as s:
        await login(ui, s)
        r = await s.put(url(ui, "/api/config"), json={})            # no X-Requested-With
        assert r.status == 403


async def test_setup_code_is_persisted_private_and_shown_on_hud_state(ui):
    f = ui.cfgdir / "web_code"
    assert f.read_text().strip() == ui.code and stat.S_IMODE(f.stat().st_mode) == 0o600
    assert ui.core.state["web"]["code"] == ui.code and ui.core.state["web"]["url"].startswith("http://")


async def test_save_writes_config_secret_files_and_never_echoes_secrets(ui, ha):
    ha.place("light.kitchen", "office", state="off", friendly_name="Kitchen")
    ha.place("weather.home", None, state="sunny", temperature=70)
    body = {"homeassistant": {"url": ha.url, "weather": "weather.home", "media_player": "",
                              "controls": [{"entity": "light.kitchen", "label": "Kitchen", "icon": "bulb"}]},
            "display": {"crossfade_ms": 1800, "photo_interval_s": 12, "blur": False},
            "secrets": {"ha_token": ha.TOKEN}}
    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as s:
        await login(ui, s)
        r = await s.put(url(ui, "/api/config"), json=body, headers=H)
        text = await r.text()
        assert r.status == 200, text
        assert ha.TOKEN not in text                                       # write-only
        view = json.loads(text)["view"]
        assert view["secrets"]["ha_token_set"] is True and view["homeassistant"]["url"] == ha.url
        assert ha.TOKEN not in await (await s.get(url(ui, "/api/config"))).text()
    toml = tomllib.loads((ui.cfgdir / "config.toml").read_text())
    assert ha.TOKEN not in (ui.cfgdir / "config.toml").read_text()
    assert toml["homeassistant"]["controls"][0]["entity"] == "light.kitchen"
    assert toml["display"]["crossfade_ms"] == 1800
    tok = Path(toml["homeassistant"]["token_file"])
    assert tok.read_text().strip() == ha.TOKEN and stat.S_IMODE(tok.stat().st_mode) == 0o600
    # applied live, no restart: the core connected to the fake HA and picked up the display settings
    await wait_for(lambda: ui.core.state["ha_status"] == "connected")
    assert ui.core.state["crossfade_ms"] == 1800 and ui.core.state["blur"] is False
    await wait_for(lambda: ui.core.state["controls"])
    assert ui.core.state["controls"][0]["label"] == "Kitchen"


async def test_blank_secret_keeps_existing_and_clear_removes_it(ui, ha):
    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as s:
        await login(ui, s)
        base = {"homeassistant": {"url": ha.url, "controls": []}}
        await s.put(url(ui, "/api/config"), json={**base, "secrets": {"ha_token": ha.TOKEN}}, headers=H)
        await s.put(url(ui, "/api/config"), json={**base, "secrets": {"ha_token": ""}}, headers=H)
        assert (ui.cfgdir / "ha_token").read_text().strip() == ha.TOKEN               # blank = unchanged
        r = await s.put(url(ui, "/api/config"), json={**base, "secrets": {"clear_ha_token": True}}, headers=H)
        assert (await r.json())["view"]["secrets"]["ha_token_set"] is False
        assert not (ui.cfgdir / "ha_token").exists()


async def test_invalid_settings_return_field_errors_and_change_nothing(ui):
    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as s:
        await login(ui, s)
        r = await s.put(url(ui, "/api/config"), headers=H, json={
            "homeassistant": {"url": "not a url", "controls": [{"entity": "kitchen"}]},
            "display": {"crossfade_ms": 99999, "photo_interval_s": "abc"},
            "photos": {"source": "immich", "immich": {"url": ""}}})
        assert r.status == 422
        f = (await r.json())["fields"]
        assert {"homeassistant.url", "homeassistant.controls.0", "display.crossfade_ms",
                "display.photo_interval_s", "photos.immich.url"} <= set(f)
    assert not (ui.cfgdir / "config.toml").exists()


async def test_hot_switch_to_immich_and_back(ui, immich):
    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as s:
        await login(ui, s)
        r = await s.put(url(ui, "/api/config"), headers=H, json={
            "photos": {"source": "immich", "immich": {"url": immich.url, "shuffle": True}},
            "secrets": {"immich_api_key": FakeImmich.KEY}})
        assert r.status == 200, await r.text()
        assert ui.core.state["photo_source"] == "immich" and ui.core.state["photo"]["id"].startswith("asset-")
        r = await s.put(url(ui, "/api/config"), headers=H, json={"photos": {"source": "local"}})
        assert r.status == 200 and ui.core.state["photo_source"] == "local"


async def test_test_ha_lists_entities_using_typed_or_saved_token(ui, ha):
    ha.place("light.kitchen", "office", state="on", friendly_name="Kitchen")
    ha.set("light.hidden", "off", friendly_name="Hidden")                 # exists but is not exposed to Assist
    ha.place("weather.home", None, state="sunny")
    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as s:
        await login(ui, s)
        r = await (await s.post(url(ui, "/api/test/ha"), json={"url": ha.url, "token": ha.TOKEN}, headers=H)).json()
        assert r["ok"] and r["exposure_readable"] and r["exposed_count"] == 2
        assert r["areas"] == [{"id": "office", "name": "Office"}]
        lights = {x["id"]: x for x in r["entities"]["light"]}
        assert lights["light.kitchen"] == {"id": "light.kitchen", "name": "Kitchen", "state": "on", "exposed": True}
        assert lights["light.hidden"]["exposed"] is False
        bad = await (await s.post(url(ui, "/api/test/ha"), json={"url": ha.url, "token": "nope"}, headers=H)).json()
        assert not bad["ok"] and "rejected" in bad["error"]
        none = await (await s.post(url(ui, "/api/test/ha"), json={"url": ha.url}, headers=H)).json()
        assert not none["ok"]                                               # no token typed or saved
        await s.put(url(ui, "/api/config"), json={"homeassistant": {"url": ha.url}, "secrets": {"ha_token": ha.TOKEN}}, headers=H)
        saved = await (await s.post(url(ui, "/api/test/ha"), json={"url": ha.url}, headers=H)).json()
        assert saved["ok"]                                                  # falls back to the stored token
        down = await (await s.post(url(ui, "/api/test/ha"), json={"url": "http://127.0.0.1:1", "token": "x"}, headers=H)).json()
        assert not down["ok"] and "could not connect" in down["error"]


async def test_test_immich_reports_albums_and_missing_permission(ui, immich):
    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as s:
        await login(ui, s)
        ok = await (await s.post(url(ui, "/api/test/immich"), json={"url": immich.url, "api_key": FakeImmich.KEY}, headers=H)).json()
        assert ok["ok"] and ok["preview_bytes"] > 0 and ok["albums"] == [{"id": "alb-1", "name": "Family", "count": 4}]
        immich.forbid_view = True
        bad = await (await s.post(url(ui, "/api/test/immich"), json={"url": immich.url, "api_key": FakeImmich.KEY}, headers=H)).json()
        assert not bad["ok"] and "asset.view" in bad["error"]
        immich.forbid_view = False
        wrong = await (await s.post(url(ui, "/api/test/immich"), json={"url": immich.url, "api_key": "wrong"}, headers=H)).json()
        assert not wrong["ok"] and "rejected" in wrong["error"]


async def test_rotating_the_code_signs_everyone_out(ui):
    old = ui.code
    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as s:
        await login(ui, s)
        assert (await s.post(url(ui, "/api/rotate-code"), json={}, headers=H)).status == 200
        assert ui.code != old and ui.core.state["web"]["code"] == ui.code
        assert (await s.get(url(ui, "/api/config"))).status == 401


# ---- settings module -------------------------------------------------------------------------

def test_apply_update_preserves_unknown_keys_and_tidies_blanks():
    existing = {"web": {"port": 9000}, "homeassistant": {"token_file": "/x/tok", "url": "http://a:8123", "weather": "weather.old"}}
    new = apply_update(existing, {"homeassistant": {"url": "http://b:8123", "weather": "", "media_player": "", "controls": []}})
    assert new["web"] == {"port": 9000} and new["homeassistant"]["token_file"] == "/x/tok"
    assert new["homeassistant"]["url"] == "http://b:8123" and "weather" not in new["homeassistant"]


def test_apply_update_limits_tiles_and_icons():
    with pytest.raises(SettingsError) as e:
        apply_update({}, {"homeassistant": {"controls": [{"entity": f"light.l{i}"} for i in range(7)]}})
    assert "homeassistant.controls" in e.value.errors
    with pytest.raises(SettingsError) as e:
        apply_update({}, {"homeassistant": {"controls": [{"entity": "light.a", "icon": "rocket"}]}})
    assert "homeassistant.controls.0" in e.value.errors


def test_public_view_fills_defaults_and_hides_secrets():
    v = public_view({}, {"ha_token": True}, ["HAVENOS_HA_URL"])
    assert v["display"]["crossfade_ms"] == 1500 and v["photos"]["immich"]["recency_half_life_days"] == 365.0
    assert v["secrets"] == {"ha_token_set": True, "immich_key_set": False, "ma_token_set": False} and v["env_overrides"] == ["HAVENOS_HA_URL"]


def test_local_photo_folder_must_exist():
    with pytest.raises(SettingsError) as e:
        apply_update({}, {"photos": {"source": "local", "dir": "/definitely/not/here"}})
    assert "photos.dir" in e.value.errors
    assert apply_update({}, {"photos": {"source": "local", "dir": "/tmp"}})["photos"]["dir"] == "/tmp"


async def test_esphome_settings_validate_and_flag_restart(ui):
    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as s:
        await login(ui, s)
        bad = await s.put(url(ui, "/api/config"), headers=H, json={"esphome": {"enabled": True, "name": "Bad Name!", "port": 80}})
        assert bad.status == 422 and {"esphome.name", "esphome.port"} <= set((await bad.json())["fields"])
        ok = await s.put(url(ui, "/api/config"), headers=H, json={"esphome": {"enabled": True, "name": "havenos-kitchen", "port": 6153}})
        body = await ok.json()
        assert ok.status == 200 and body["restart_required"] is True
        assert body["view"]["esphome"] == {"enabled": True, "name": "havenos-kitchen", "port": 6153}
        again = await (await s.put(url(ui, "/api/config"), headers=H, json={"esphome": {"enabled": True, "name": "havenos-kitchen", "port": 6153}})).json()
        assert again["restart_required"] is False                      # unchanged: nothing to restart
        status = await (await s.get(url(ui, "/api/status"))).json()
        assert status["esphome"] == {"running": False}


async def test_brightness_is_a_setting_in_the_web_ui(ui):
    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as s:
        await login(ui, s)
        r = await s.put(url(ui, "/api/config"), headers=H, json={"display": {"brightness": 45}})
        assert r.status == 200 and (await r.json())["view"]["display"]["brightness"] == 45
        assert ui.core.state["brightness"] == 45
        bad = await s.put(url(ui, "/api/config"), headers=H, json={"display": {"brightness": 5}})
        assert bad.status == 422 and "display.brightness" in (await bad.json())["fields"]


async def test_rooms_and_notification_settings_validate_and_save(ui):
    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as s:
        await login(ui, s)
        bad = await s.put(url(ui, "/api/config"), headers=H, json={"notifications": {"announcement_seconds": 1}})
        assert bad.status == 422 and "notifications.announcement_seconds" in (await bad.json())["fields"]
        ok = await s.put(url(ui, "/api/config"), headers=H, json={
            "homeassistant": {"url": "", "room": "Sunroom", "persistent_notifications": True}, "notifications": {"announcement_seconds": 45}})
        view = (await ok.json())["view"]
        assert ok.status == 200 and view["homeassistant"]["room"] == "Sunroom" and view["homeassistant"]["persistent_notifications"] is True
        assert view["notifications"]["announcement_seconds"] == 45 and ui.core.config.announcement_seconds == 45.0


async def test_music_settings_validate_store_the_token_privately_and_flag_restart(ui):
    from conftest import wait_for
    from havenos.core.media.library import MusicAssistantClient
    from test_library import FakeMA
    ma = FakeMA(token="tok-9f3a")
    await ma.start()
    try:
        async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as s:
            await login(ui, s)
            bad = await s.put(url(ui, "/api/config"), headers=H, json={"music": {"idle_s": 1, "duck_db": 5, "assistant": {"url": "nope"}}})
            assert bad.status == 422 and {"music.idle_s", "music.duck_db", "music.assistant.url"} <= set((await bad.json())["fields"])

            probe = await (await s.post(url(ui, "/api/test/ma"), headers=H, json={"url": ma.url, "token": "wrong"})).json()
            assert probe["ok"] is False and "Invalid" in probe["error"]
            probe = await (await s.post(url(ui, "/api/test/ma"), headers=H, json={"url": ma.url, "token": "tok-9f3a"})).json()
            assert probe["ok"] is True and "2.9.0" in probe["msg"]

            body = {"music": {"idle_s": 120, "hint": True, "duck_db": -12, "assistant": {"url": ma.url, "player_id": ""},
                              "airplay": {"enabled": True, "name": "Kitchen"}}, "secrets": {"ma_token": "tok-9f3a"}}
            r = await s.put(url(ui, "/api/config"), headers=H, json=body)
            text = await r.text()
            assert r.status == 200 and "tok-9f3a" not in text
            view = json.loads(text)
            assert view["restart_required"] is True and view["view"]["secrets"]["ma_token_set"] is True
    finally:
        await ma.stop()
    toml = tomllib.loads((ui.cfgdir / "config.toml").read_text())
    assert toml["music"]["assistant"] == {"url": ma.url, "token_file": toml["music"]["assistant"]["token_file"]}
    tok = Path(toml["music"]["assistant"]["token_file"])
    assert tok.read_text().strip() == "tok-9f3a" and stat.S_IMODE(tok.stat().st_mode) == 0o600
    assert toml["music"]["airplay"] == {"enabled": True, "name": "Kitchen"}
    # applied live: the library is built from the saved URL and token, and the music knobs took effect
    assert ui.core.library is not None and ui.core.state["library"]["available"] is True
    assert (ui.core.music.idle_timeout_s, ui.core.music.duck_db, ui.core.music.hint) == (120.0, -12.0, True)


async def test_audio_output_is_a_setting_with_a_device_list_and_a_test_sound(ui, monkeypatch):
    ui.core.audio_choices = lambda: [{"value": "USB Audio: -", "label": "USB Audio"}]
    played = []
    ui.core.audio_test = lambda: played.append(1)
    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as s:
        assert (await s.get(url(ui, "/api/audio/devices"))).status == 401
        await login(ui, s)
        got = await (await s.get(url(ui, "/api/audio/devices"))).json()
        assert got["devices"] == [{"value": "USB Audio: -", "label": "USB Audio"}]
        assert (await (await s.post(url(ui, "/api/test/audio"), headers=H, json={})).json())["ok"] is True and played == [1]
        view = await (await s.get(url(ui, "/api/config"))).json()
        assert view["music"]["audio_device"] == ""                                   # default: the system's own
        r = await s.put(url(ui, "/api/config"), headers=H, json={"music": {"audio_device": "USB Audio: -"}})
        assert r.status == 200 and (await r.json())["view"]["music"]["audio_device"] == "USB Audio: -"
        assert ui.core.config.audio_device == "USB Audio: -"
        assert tomllib.loads((ui.cfgdir / "config.toml").read_text())["music"]["audio_device"] == "USB Audio: -"
        r = await s.put(url(ui, "/api/config"), headers=H, json={"music": {"audio_device": ""}})
        assert "audio_device" not in tomllib.loads((ui.cfgdir / "config.toml").read_text())["music"]       # blank == unset
        bad = await s.put(url(ui, "/api/config"), headers=H, json={"music": {"audio_device": "x" * 200}})
        assert bad.status == 422 and "music.audio_device" in (await bad.json())["fields"]


async def test_saving_a_new_output_switches_the_running_hub(ui, monkeypatch):
    seen = []
    hub = ui.core.audio_hub()
    monkeypatch.setattr(hub, "set_match", lambda m: seen.append(m))
    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as s:
        await login(ui, s)
        await s.put(url(ui, "/api/config"), headers=H, json={"music": {"audio_device": "USB Audio: -"}})
    assert seen == ["USB Audio: -"]


async def test_the_display_gets_a_pairing_link_and_qr_without_the_hud(ui):
    from havenos.core.qr import matrix
    web = ui.core.state["web"]
    assert web["link"] == f"{web['url']}/?code={ui.code}"
    assert web["qr"] == matrix(web["link"])
    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as s:
        await login(ui, s)
        await s.post(url(ui, "/api/rotate-code"), headers=H, json={})
    again = ui.core.state["web"]
    assert again["code"] == ui.code and again["code"] in again["link"] and again["qr"] != web["qr"]       # the QR follows a new code


async def test_first_run_flag_is_a_setting_and_follows_to_the_display(ui):
    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as s:
        await login(ui, s)
        view = await (await s.get(url(ui, "/api/config"))).json()
        assert view["setup"] == {"done": False} and ui.core.state["setup_done"] is False       # blank config: not set up yet
        r = await s.put(url(ui, "/api/config"), headers=H, json={"setup": {"done": True}})
        assert (await r.json())["view"]["setup"]["done"] is True
        assert ui.core.state["setup_done"] is True                                             # the pairing screen goes away
        assert tomllib.loads((ui.cfgdir / "config.toml").read_text())["setup"]["done"] is True


def test_setup_counts_as_done_for_an_install_that_already_has_home_assistant():
    from havenos.core.settings import setup_done
    assert setup_done({}) is False
    assert setup_done({"setup": {"done": True}}) is True
    assert setup_done({"homeassistant": {"url": "http://ha.local:8123"}}) is True
    assert apply_update({}, {"setup": {"done": True}})["setup"]["done"] is True


async def test_restart_is_only_flagged_for_real_changes_not_first_time_defaults(ui):
    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as s:
        await login(ui, s)
        same = {"esphome": {"enabled": False, "port": 6053}, "music": {"airplay": {"enabled": False}, "sendspin": {"enabled": False}}}
        r = await (await s.put(url(ui, "/api/config"), headers=H, json=same)).json()
        assert r["restart_required"] is False                                    # the setup wizard's first save writes defaults
        r = await (await s.put(url(ui, "/api/config"), headers=H, json={"music": {"airplay": {"enabled": True}}})).json()
        assert r["restart_required"] is True
