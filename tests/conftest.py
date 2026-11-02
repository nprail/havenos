import asyncio

import pytest
from PIL import Image

from havenos.core import Config, Core
from fakes import FakeHA, FakeImmich


class FakeClock:
    def __init__(self, t: float = 1_000_000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, s: float) -> None:
        self.t += s


async def instant_sleep(_s: float) -> None:
    await asyncio.sleep(0)


@pytest.fixture
def photo_dir(tmp_path):
    d = tmp_path / "photos"
    d.mkdir()
    for i, size in enumerate([(3000, 2000), (2400, 1600), (1200, 2000)]):
        Image.new("RGB", size, (i * 40, 90, 160)).save(d / f"{i:02d}.jpg")
    return d


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def make_config(tmp_path, photo_dir):
    def make(**kw) -> Config:
        base = dict(photo_dir=photo_dir, cache_dir=tmp_path / "cache", photo_interval_s=8, idle_s=30,
                    ring_auto_dismiss_s=30, config_path=tmp_path / "cfg" / "config.toml")
        base.update(kw)
        return Config(**base)
    return make


@pytest.fixture
async def core(make_config, clock):
    c = Core(make_config(), clock=clock, sleep=instant_sleep)
    await c.start()
    yield c
    await c.stop()


@pytest.fixture
async def ha():
    s = FakeHA()
    await s.start()
    yield s
    await s.stop()


@pytest.fixture
async def immich():
    s = FakeImmich()
    await s.start()
    yield s
    await s.stop()


async def wait_for(pred, timeout: float = 3.0):
    """Poll until pred() is truthy (real time; for tests that talk to the fake servers)."""
    async with asyncio.timeout(timeout):
        while not pred():
            await asyncio.sleep(0.01)


def stock_house(ha, mac):
    """A small house: this display lives in the kitchen; some entities are exposed to Assist, some are not."""
    ha.own_device(mac, "kitchen")
    ha.place("weather.home", None, state="sunny", temperature=70)
    ha.place("media_player.kitchen_speaker", "kitchen", state="paused", friendly_name="Kitchen Speaker", media_title="Slow Light", media_artist="Choir")
    ha.place("light.kitchen_main", "kitchen", state="off", friendly_name="Kitchen Main", supported_color_modes=["brightness"])
    ha.place("climate.kitchen", "kitchen", state="heat", friendly_name="Kitchen Climate", current_temperature=68, temperature=70)
    ha.place("light.secret_lamp", "kitchen", exposed=False, state="on", friendly_name="Secret Lamp")   # not exposed
    ha.place("light.bedroom_lamp", "bedroom", state="off", friendly_name="Bedroom Lamp")
    ha.forecasts["daily"] = [{"temperature": 80, "templow": 60}]
    ha.forecasts["hourly"] = [{"datetime": "2026-10-29T13:00:00+00:00", "temperature": 71, "condition": "cloudy"}]


