"""The ESPHome server, exercised with aioesphomeapi's real client: the library Home Assistant itself uses."""
import asyncio

import pytest
from aioesphomeapi import APIClient
from aioesphomeapi import api_pb2 as pb
from aioesphomeapi.model import EventInfo

from havenos.core.esphome import ESPHomeDevice
from havenos.core.esphome import framing
from conftest import wait_for


@pytest.fixture
async def device(core):
    d = ESPHomeDevice(core, name="havenos-test", port=0, host="127.0.0.1", mac="AA:BB:CC:DD:EE:FF", advertise=False)
    await d.start()
    yield d
    await d.stop()


@pytest.fixture
async def client(device):
    c = APIClient("127.0.0.1", device.port, None, client_info="pytest")
    await c.connect(login=True)
    yield c
    await c.disconnect()


async def entities(client):
    ents, services = await client.list_entities_services()
    return {e.object_id: e for e in ents}, {s.name: s for s in services}


async def states(client):
    got: dict[int, object] = {}
    client.subscribe_states(lambda s: got.__setitem__(s.key, s))
    await wait_for(lambda: len(got) >= 10)
    return got


async def test_identity_and_handshake(client):
    info = await client.device_info()
    assert (info.name, info.mac_address, info.manufacturer) == ("havenos-test", "AA:BB:CC:DD:EE:FF", "havenOS")
    assert info.uses_password is False and info.voice_assistant_feature_flags == 0


async def test_lists_entities_with_categories_and_services(client):
    ents, services = await entities(client)
    assert {"screen", "brightness", "mode", "next_photo", "previous_photo", "photo_interval", "crossfade", "blur",
            "photo", "active_timers", "photo_source", "ha_link", "memory", "loop_lag", "cached_photos", "touch", "notification_count", "room", "backlight_level"} <= set(ents)
    assert ents["memory"].entity_category.name == "DIAGNOSTIC" and ents["blur"].entity_category.name == "CONFIG"
    assert ents["brightness"].min_value == 10 and ents["brightness"].max_value == 100 and ents["brightness"].unit_of_measurement == "%"
    assert ents["mode"].options == ["ambient", "dashboard"]
    assert isinstance(ents["touch"], EventInfo) and "swipe_left" in ents["touch"].event_types
    assert set(services) == {"start_timer", "dismiss_timer", "announce", "notify", "clear_notifications", "dismiss_announcement"}
    assert [a.name for a in services["start_timer"].args] == ["seconds", "label"]


async def test_entity_keys_are_stable_across_restarts(core):
    keys = []
    for _ in range(2):
        d = ESPHomeDevice(core, name="havenos-test", port=0, host="127.0.0.1", advertise=False)
        keys.append({e.object_id: e.key for e in d.server.entities})
    assert keys[0] == keys[1]


async def test_subscribe_sends_current_state(client, core):
    ents, _ = await entities(client)
    got = await states(client)
    assert got[ents["screen"].key].state is True
    assert got[ents["brightness"].key].state == 100
    assert got[ents["mode"].key].state == "ambient"
    assert got[ents["photo_source"].key].state == "local"
    assert got[ents["ha_link"].key].state is True            # demo mode counts as linked
    assert got[ents["active_timers"].key].state == 1          # the demo "Pasta" timer


async def test_commands_drive_the_core_and_state_echoes_back(client, core):
    ents, _ = await entities(client)
    got = await states(client)
    client.switch_command(ents["screen"].key, False)
    await wait_for(lambda: core.state["screen_on"] is False)
    await wait_for(lambda: got[ents["screen"].key].state is False)

    client.number_command(ents["brightness"].key, 40)
    await wait_for(lambda: core.state["brightness"] == 40)
    client.number_command(ents["brightness"].key, 1)                  # below the minimum: clamped, not rejected
    await wait_for(lambda: core.state["brightness"] == 10)

    client.select_command(ents["mode"].key, "dashboard")
    await wait_for(lambda: core.state["mode"] == "dashboard")
    await wait_for(lambda: got[ents["mode"].key].state == "dashboard")

    client.select_command(ents["mode"].key, "nonsense")               # invalid option ignored
    await asyncio.sleep(0.1)
    assert core.state["mode"] == "dashboard"

    client.number_command(ents["crossfade"].key, 2000)
    client.switch_command(ents["blur"].key, False)
    client.number_command(ents["photo_interval"].key, 20)
    await wait_for(lambda: (core.state["crossfade_ms"], core.state["blur"], core.state["photo_interval_s"]) == (2000, False, 20.0))


async def test_buttons_and_photo_text_sensor(client, core):
    ents, _ = await entities(client)
    got = await states(client)
    before = got[ents["photo"].key].state
    client.button_command(ents["next_photo"].key)
    await wait_for(lambda: got[ents["photo"].key].state != before)
    assert got[ents["photo"].key].state == core.state["photo"]["name"]
    client.button_command(ents["previous_photo"].key)
    await wait_for(lambda: got[ents["photo"].key].state == before)


async def test_services_start_a_timer_and_dismiss_the_ring(client, core):
    _, services = await entities(client)
    await client.execute_service(services["start_timer"], {"seconds": 90, "label": "Tea"})
    await wait_for(lambda: any(t["label"] == "Tea" and t["total"] == 90 for t in core.state["timers"]))
    core.state["ringing"] = {"id": 99, "label": "x", "total": 1, "end": 0}
    await client.execute_service(services["dismiss_timer"], {})
    await wait_for(lambda: core.state["ringing"] is None)


async def test_touch_gestures_arrive_as_events(client, core):
    ents, _ = await entities(client)
    seen = []
    client.subscribe_states(lambda s: seen.append(s) if s.key == ents["touch"].key else None)
    await asyncio.sleep(0.1)
    core.handle("ui.gesture", kind="swipe_left")
    await wait_for(lambda: seen and seen[-1].event_type == "swipe_left")


async def test_noisy_diagnostics_are_throttled(client, core):
    ents, _ = await entities(client)
    updates = []
    client.subscribe_states(lambda s: updates.append(s.state) if s.key == ents["memory"].key else None)
    await asyncio.sleep(0.1)
    updates.clear()
    for rss in (101.0, 102.0, 103.0):
        core.bus.emit("stats", rss_mb=rss, lag_worst_ms=0.0, lag_slow=0, cached_photos=0)
    await asyncio.sleep(0.2)
    assert len(updates) <= 1


async def test_two_clients_both_get_updates(device, core):
    a, b = (APIClient("127.0.0.1", device.port, None) for _ in range(2))
    await a.connect(login=True)
    await b.connect(login=True)
    ents, _ = await entities(a)
    got_a, got_b = {}, {}
    a.subscribe_states(lambda s: got_a.__setitem__(s.key, s))
    b.subscribe_states(lambda s: got_b.__setitem__(s.key, s))
    await wait_for(lambda: len(got_a) >= 10 and len(got_b) >= 10)
    core.handle("brightness.set", percent=55)
    await wait_for(lambda: got_a[ents["brightness"].key].state == 55 and got_b[ents["brightness"].key].state == 55)
    await a.disconnect()
    core.handle("brightness.set", percent=65)
    await wait_for(lambda: got_b[ents["brightness"].key].state == 65)     # survivor keeps working
    await b.disconnect()


async def test_unknown_message_and_garbage_do_not_kill_the_server(device, client):
    r, w = await asyncio.open_connection("127.0.0.1", device.port)
    w.write(b"\x01garbage")                                              # e.g. a Noise-encrypted client
    await w.drain()
    assert await r.read() == b""                                         # server closed that connection
    assert (await client.device_info()).name == "havenos-test"          # others unaffected


async def test_extension_handlers_receive_messages_for_voice_and_other_features(device):
    """The seam the voice assistant will use: register a handler for a protobuf message type."""
    seen = []
    device.server.add_handler(pb.VoiceAssistantRequest, lambda conn, msg: seen.append(msg.start))
    r, w = await asyncio.open_connection("127.0.0.1", device.port)
    w.write(framing.encode(pb.VoiceAssistantRequest(start=True)))
    await w.drain()
    await wait_for(lambda: seen == [True])
    w.close()


def test_frame_decoder_handles_split_and_batched_frames():
    d = framing.Decoder()
    wire = framing.encode(pb.PingRequest()) + framing.encode(pb.HelloRequest(client_info="x" * 300))
    out = []
    for i in range(0, len(wire), 7):                                     # dribble it in 7 bytes at a time
        out += d.feed(wire[i:i + 7])
    assert [t for t, _ in out] == [framing.PROTO_TO_TYPE[pb.PingRequest], framing.PROTO_TO_TYPE[pb.HelloRequest]]
    with pytest.raises(framing.FrameError):
        framing.Decoder().feed(b"\x01\x02\x03")
    with pytest.raises(framing.FrameError):
        framing.Decoder().feed(b"\x00" + framing.varuint(framing.MAX_FRAME + 1) + b"\x01")


def test_device_id_is_valid_unique_and_stable(tmp_path):
    from havenos.core.esphome.device import device_mac
    store = tmp_path / "device_mac"
    first = device_mac(store)
    assert device_mac(store) == first                                       # persisted, never changes
    assert int(first.split(":")[0], 16) & 0x02 and not int(first.split(":")[0], 16) & 0x01   # local, unicast
    assert device_mac(tmp_path / "other") != first                          # two devices never share an id


async def test_ha_can_announce_and_notify_through_services(client, core):
    _, services = await entities(client)
    await client.execute_service(services["announce"], {"message": "Dinner", "title": "Kitchen", "kind": "warning", "seconds": 7})
    await wait_for(lambda: core.state["announcement"] and core.state["announcement"]["message"] == "Dinner")
    assert core.state["announcement"]["kind"] == "warning" and core.state["announcement"]["seconds"] == 7.0
    await client.execute_service(services["notify"], {"message": "Laundry done", "title": "", "kind": ""})
    await wait_for(lambda: any(n["message"] == "Laundry done" for n in core.state["notifications"]))
    await client.execute_service(services["clear_notifications"], {})
    await wait_for(lambda: core.state["notifications"] == [])
    await client.execute_service(services["dismiss_announcement"], {})
    await wait_for(lambda: core.state["announcement"] is None)


async def test_media_player_mirrors_the_music_state_and_takes_commands(client, core):
    from havenos.core.media.sources.fake import FakeSource
    src = FakeSource("spotify", "Spotify")
    core.music.register(src)
    ents, _ = await entities(client)
    mp = ents["media_player"]
    assert mp.supports_pause and mp.feature_flags & 4 and mp.feature_flags & 4096          # volume set + stop
    got = await states(client)
    assert got[mp.key].state.name == "IDLE"

    src.connect("Nick's phone")
    src.play()
    await wait_for(lambda: got[mp.key].state.name == "PLAYING")
    await wait_for(lambda: got[ents["music_title"].key].state == "Northern Lines")
    assert got[ents["music_source"].key].state == "Spotify · Nick's phone"

    client.media_player_command(mp.key, command=pb_cmd("PAUSE"))
    await wait_for(lambda: got[mp.key].state.name == "PAUSED")
    client.media_player_command(mp.key, volume=0.35)
    await wait_for(lambda: core.state["music"]["volume"] == 35 and abs(got[mp.key].volume - 0.35) < 0.01)
    client.media_player_command(mp.key, command=pb_cmd("MUTE"))
    await wait_for(lambda: core.state["music"]["muted"] is True)

    client.button_command(ents["next_track"].key)
    await wait_for(lambda: ("next", {}) in src.calls)
    client.media_player_command(mp.key, command=pb_cmd("STOP"))                       # the one external command that frees the slot
    await wait_for(lambda: core.state["music"]["active_source"] is None)


def pb_cmd(name: str):
    from aioesphomeapi import MediaPlayerCommand
    return MediaPlayerCommand[name]


# ---- Noise encryption ----------------------------------------------------------------------------------------------

from aioesphomeapi import InvalidEncryptionKeyAPIError
from havenos.core.esphome import noise


async def test_noise_encryption_works_with_the_real_client(core):
    key = noise.generate_key()
    d = ESPHomeDevice(core, name="havenos-test", port=0, host="127.0.0.1", advertise=False, key=key)
    await d.start()
    try:
        c = APIClient("127.0.0.1", d.port, None, noise_psk=key)
        await c.connect(login=True)
        info = await c.device_info()
        assert info.name == "havenos-test" and info.api_encryption_supported is True
        ents, _ = await entities(c)
        got = {}
        c.subscribe_states(lambda s: got.__setitem__(s.key, s))
        await wait_for(lambda: len(got) >= 10)
        c.switch_command(ents["screen"].key, False)                      # commands also travel encrypted
        await wait_for(lambda: core.state["screen_on"] is False)
        await c.disconnect()
    finally:
        await d.stop()


async def test_noise_rejects_a_wrong_key_and_plain_text_clients(core):
    d = ESPHomeDevice(core, name="havenos-test", port=0, host="127.0.0.1", advertise=False, key=noise.generate_key())
    await d.start()
    try:
        bad = APIClient("127.0.0.1", d.port, None, noise_psk=noise.generate_key())
        with pytest.raises(InvalidEncryptionKeyAPIError):
            await bad.connect(login=True)
        plain = APIClient("127.0.0.1", d.port, None)
        with pytest.raises(Exception):
            await plain.connect(login=True)
        r, w = await asyncio.open_connection("127.0.0.1", d.port)
        w.write(framing.encode(pb.HelloRequest(client_info="x")))        # plain frame: no state leaks, connection closes
        await w.drain()
        assert await r.read() == b""
        w.close()
        assert not d.server.connections or all(c.closed for c in d.server.connections)
    finally:
        await d.stop()


def test_noise_key_helpers():
    key = noise.generate_key()
    assert len(noise.decode_key(key)) == 32 and key != noise.generate_key()
    for bad in ("", "not base64!!", "AAAA"):
        with pytest.raises(ValueError):
            noise.decode_key(bad)


async def test_ha_play_media_plays_a_url_on_the_display(client, core, tmp_path):
    import wave
    import numpy as np
    from fakes import FakeSink
    sink = FakeSink()
    core._open_url_audio = lambda: sink
    wav = tmp_path / "ding.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes((np.sin(np.arange(22050) * 0.1) * 12000).astype(np.int16).tobytes())
    ents, _ = await entities(client)
    mp = ents["media_player"]
    assert mp.feature_flags & 512                                    # PLAY_MEDIA, so HA offers play_media at all
    assert not mp.feature_flags & 1048576                            # announce needs voice
    client.media_player_command(mp.key, media_url=str(wav), announcement=False)
    await wait_for(lambda: core.state["music"]["active_source"] == "homeassistant")
    assert core.state["music"]["track"]["title"] == "ding"
    await wait_for(lambda: len(sink.data) > 0)
    got = await states(client)
    await wait_for(lambda: got[mp.key].state.name in ("PLAYING", "IDLE"))
    client.media_player_command(mp.key, command=pb_cmd("STOP"))
    await wait_for(lambda: core.state["music"]["active_source"] is None)
