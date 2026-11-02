from pathlib import Path

from havenos.core.config import Config

TOML = """
[homeassistant]
url = "http://ha.local:8123/"
token_file = "{token}"
weather = "weather.home"
media_player = "media_player.kitchen"
[[homeassistant.controls]]
entity = "light.kitchen"
label = "Kitchen"
icon = "bulb"
[photos]
source = "immich"
[photos.immich]
url = "http://immich.local:2283"
api_key = "k123"
album = "alb"
"""


def test_toml_config(tmp_path, monkeypatch):
    tok = tmp_path / "tok"
    tok.write_text("secret\n")
    cfg = tmp_path / "c.toml"
    cfg.write_text(TOML.format(token=tok))
    for k in ("HAVENOS_HA_URL", "HAVENOS_HA_TOKEN", "HAVENOS_IMMICH_URL", "HAVENOS_IMMICH_KEY", "HAVENOS_PHOTO_SOURCE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("HAVENOS_CONFIG", str(cfg))
    c = Config.from_env(Path("/assets"))
    assert c.ha.url == "http://ha.local:8123" and c.ha.token == "secret"
    assert c.ha.controls[0].label == "Kitchen" and c.ha.weather_entity == "weather.home"
    assert c.immich.api_key == "k123" and c.immich.album_id == "alb"


def test_env_overrides_and_defaults_to_demo(tmp_path, monkeypatch):
    monkeypatch.setenv("HAVENOS_CONFIG", str(tmp_path / "missing.toml"))
    for k in ("HAVENOS_HA_URL", "HAVENOS_HA_TOKEN", "HAVENOS_IMMICH_URL", "HAVENOS_IMMICH_KEY", "HAVENOS_PHOTO_SOURCE"):
        monkeypatch.delenv(k, raising=False)
    c = Config.from_env(Path("/assets"))
    assert c.ha is None and c.immich is None          # demo data + local photos
    monkeypatch.setenv("HAVENOS_HA_URL", "http://x:8123")
    monkeypatch.setenv("HAVENOS_HA_TOKEN", "t")
    assert Config.from_env(Path("/assets")).ha.token == "t"
