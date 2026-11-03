import asyncio

from havenos.core.backlight import Backlight


def fake(tmp_path, maxb=255, now=255, power=True, name="10-0045"):
    d = tmp_path / name
    d.mkdir()
    (d / "max_brightness").write_text(str(maxb))
    (d / "brightness").write_text(str(now))
    if power:
        (d / "bl_power").write_text("0")
    return d


def test_find_picks_the_first_backlight_and_respects_none(tmp_path):
    fake(tmp_path, name="b"); fake(tmp_path, name="a")
    assert Backlight.find("auto", root=tmp_path).name == "a"
    assert Backlight.find("b", root=tmp_path).name == "b"
    assert Backlight.find("none", root=tmp_path) is None
    assert Backlight.find("auto", root=tmp_path / "missing") is None
    assert Backlight.find("nope", root=tmp_path) is None


def test_percent_maps_through_a_gamma_curve_and_zero_is_off(tmp_path):
    b = Backlight(fake(tmp_path), gamma=2.0)
    assert b.raw_of(100) == 255 and b.raw_of(0) == 0
    assert b.raw_of(50) == round(255 * 0.25)
    assert b.raw_of(0.5) == 1                      # never rounds a lit screen down to off
    assert abs(b.percent_of(b.raw_of(30)) - 30) < 1.5


def test_set_writes_the_raw_value_and_powers_the_panel(tmp_path):
    d = fake(tmp_path)
    b = Backlight(d, gamma=1.0)
    b.set(40)
    assert (d / "brightness").read_text() == str(round(255 * 0.4)) and (d / "bl_power").read_text() == "0"
    b.set(0)
    assert (d / "brightness").read_text() == "0" and (d / "bl_power").read_text() == "4"
    b.set(100)
    assert (d / "brightness").read_text() == "255" and (d / "bl_power").read_text() == "0"


def test_a_panel_without_bl_power_still_works(tmp_path):
    d = fake(tmp_path, power=False)
    b = Backlight(d, gamma=1.0)
    b.set(50)
    assert (d / "brightness").read_text() == str(round(255 * 0.5))


async def test_fade_ramps_and_a_new_target_replaces_it(tmp_path):
    d = fake(tmp_path)
    b = Backlight(d, gamma=1.0)
    b.fade_to(0, 100)
    await asyncio.sleep(0.05)
    mid = int((d / "brightness").read_text())
    assert 0 < mid < 255                           # on its way down
    b.fade_to(100, 100)
    await asyncio.sleep(0.2)
    assert (d / "brightness").read_text() == "255"
    b.close()
