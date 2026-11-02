"""Fake Home Assistant + Immich on localhost, so the UI can be exercised without real servers.

    python scripts/dev_servers.py          # then:  HAVENOS_CONFIG=scripts/dev-config.toml python -m havenos

HA: ws on :18123 (token dev-token). Lights/switches toggle for real and push state_changed; the weather,
media player and climate entities are static. Immich: :12283 (api key dev-key), serving the sample photos.
Ctrl-C stops both. Test doubles only: nothing here speaks for a real installation.
"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "src"))
from fakes import FakeHA, FakeImmich  # noqa: E402

PHOTOS = sorted((ROOT / "src" / "havenos" / "assets" / "photos").glob("*.jpg"))


class DevImmich(FakeImmich):
    KEY = "dev-key"

    def image_bytes(self, asset_id: str) -> bytes:
        return PHOTOS[int(asset_id.split("-")[1]) % len(PHOTOS)].read_bytes()


class DevHA(FakeHA):
    TOKEN = "dev-token"


async def main() -> None:
    from havenos.core.demo import demo_index, demo_states
    ha = DevHA()
    # The same house the demo mode uses, served the way a real HA does: areas, registry records, and Assist exposure.
    ix = demo_index()
    for eid, st in demo_states().items():
        ha.place(eid, ix.entity_area.get(eid), state=st["state"], **st["attributes"])
    ha.area("living_room", "Living Room")
    ha.set("weather.demo_home", "partlycloudy", temperature=64.4, friendly_name="Home")
    ha.forecasts["daily"] = [{"datetime": "2026-10-29T00:00:00+00:00", "temperature": 69, "templow": 51, "condition": "sunny"}]
    ha.forecasts["hourly"] = [{"datetime": f"2026-10-29T{h}:00:00+00:00", "temperature": t, "condition": c}
                              for h, t, c in [(18, 64, "partlycloudy"), (19, 62, "cloudy"), (20, 59, "rainy"), (21, 57, "clear-night")]]
    ha.place("light.not_exposed_lamp", "living_room", exposed=False, state="on", friendly_name="Living Room Secret Lamp")
    await ha.start(18123)
    im = DevImmich(n=24)
    await im.start(12283)
    print(f"fake HA   {ha.url}   token dev-token\nfake Immich {im.url}   key dev-key\nCtrl-C to stop", flush=True)
    try:
        await asyncio.Event().wait()
    finally:
        await ha.stop()
        await im.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
