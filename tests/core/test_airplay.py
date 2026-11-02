"""AirPlaySource against a fake shairport-sync: items written to its metadata FIFO, audio to its audio FIFO, and a fake DACP
server standing in for the sender's remote-control service."""
import asyncio
import base64
import os
import struct

import pytest
from aiohttp import web

from conftest import wait_for
from havenos.core.media import MediaCoordinator
from havenos.core.media.sources.airplay import AirPlaySource, decode_items
from havenos.core.media.sources.fake import FakeSource


def item(typ: str, code: str, data: bytes | None = None) -> bytes:
    """One metadata item as shairport-sync writes it."""
    head = f"<item><type>{typ.encode().hex()}</type><code>{code.encode().hex()}</code><length>{len(data or b'')}</length>"
    if data is None or data == b"":
        return (head + "</item>\n").encode()
    return (head + '\n<data encoding="base64">\n' + base64.b64encode(data).decode() + "\n</data></item>\n").encode()


def ssnc(code, text=None):
    return item("ssnc", code, None if text is None else text.encode())


def core(code, text):
    return item("core", code, text.encode())


class Dacp:
    def __init__(self):
        self.hits: list[tuple[str, str | None]] = []
        self.runner = None

    async def start(self) -> int:
        app = web.Application()
        app.router.add_get("/ctrl-int/1/{cmd}", self._h)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        return site._server.sockets[0].getsockname()[1]

    async def _h(self, req):
        self.hits.append((req.match_info["cmd"], req.headers.get("Active-Remote")))
        return web.Response(status=204)

    async def stop(self):
        await self.runner.cleanup()


class Sink:
    def __init__(self):
        self.chunks, self.cleared, self.vol, self.ms = [], 0, None, 0.0

    def write(self, ts, data, fmt):
        self.chunks.append(data)

    def clear(self):
        self.cleared += 1

    def buffered_ms(self):
        return self.ms

    def set_volume(self, level, muted):
        self.vol = (level, muted)


@pytest.fixture
async def rig(tmp_path, clock):
    dacp = Dacp()
    dport = await dacp.start()
    sink = Sink()
    src = AirPlaySource("havenOS test", tmp_path, manage_process=False, audio_sink=sink)
    spot = FakeSource("spotify", "Spotify")
    co = MediaCoordinator(lambda **ch: None, clock=clock, select_feed=lambda a: [
        x.set_feed(a is None or x.id == a) for x in (src, spot)])
    co.register(src)
    co.register(spot)
    await co.start()
    wr = os.open(src.meta_pipe, os.O_WRONLY | os.O_NONBLOCK)

    def send(*items: bytes):
        os.write(wr, b"".join(items))

    def start_track(title="Slow Light", artist="The Harbour Choir", album="Low Tide", ms=214000):
        send(ssnc("snam", "Nick's iPhone"), ssnc("clip", "127.0.0.1"), ssnc("daid", "AB12CD34"), ssnc("acre", "999"),
             ssnc("dapo", str(dport)), ssnc("pbeg"), ssnc("mdst"), core("minm", title), core("asar", artist), core("asal", album),
             item("core", "astm", struct.pack(">I", ms)), ssnc("mden"), ssnc("pffr"))

    r = type("Rig", (), dict(dacp=dacp, sink=sink, src=src, spot=spot, co=co, send=staticmethod(send),
                             start_track=staticmethod(start_track)))
    yield r
    os.close(wr)
    await co.stop()
    await dacp.stop()


async def test_a_session_becomes_the_active_source_with_its_metadata(rig):
    rig.start_track()
    await wait_for(lambda: rig.co.state()["status"] == "playing")
    st = rig.co.state()
    assert st["active_source"] == "airplay" and st["client"] == "Nick's iPhone"
    assert (st["track"]["title"], st["track"]["artist"], st["track"]["album"], st["track"]["duration"]) == (
        "Slow Light", "The Harbour Choir", "Low Tide", 214.0)
    assert set(st["capabilities"]) == {"play", "pause", "next", "prev"}


async def test_flush_pauses_resume_plays_and_end_clears(rig):
    rig.start_track()
    await wait_for(lambda: rig.co.state()["status"] == "playing")
    rig.send(ssnc("pfls"))
    await wait_for(lambda: rig.co.state()["status"] == "paused")
    rig.send(ssnc("prsm"))
    await wait_for(lambda: rig.co.state()["status"] == "playing")
    rig.send(ssnc("pend"))                       # classic AirPlay: pause ends the play stream, the sender is still connected
    await wait_for(lambda: rig.co.state()["status"] == "paused")
    assert rig.co.state()["active_source"] == "airplay" and rig.co.state()["track"]["title"] == "Slow Light"
    rig.send(ssnc("pbeg"), ssnc("pffr"))         # resume starts a new play stream within the same session
    await wait_for(lambda: rig.co.state()["status"] == "playing")
    rig.send(ssnc("pend"), ssnc("aend"))         # only leaving the active state ends the session
    await wait_for(lambda: rig.co.state()["active_source"] is None)


async def test_progress_gives_position_and_a_duration_when_the_sender_gave_none(rig):
    rig.send(ssnc("pbeg"), ssnc("mdst"), core("minm", "Live"), ssnc("mden"), ssnc("pffr"),
             ssnc("prgr", f"1000/{1000 + 44100 * 30}/{1000 + 44100 * 200}"))
    await wait_for(lambda: rig.co.state()["track"] and rig.co.state()["track"]["duration"])
    st = rig.co.state()
    assert st["track"]["duration"] == pytest.approx(200.0) and st["position"] == pytest.approx(30.0, abs=1)


async def test_cover_art_is_saved_to_a_file_the_ui_can_load(rig):
    rig.start_track()
    jpeg = b"\xff\xd8\xff\xe0" + b"x" * 500
    rig.send(item("ssnc", "PICT", jpeg))
    await wait_for(lambda: (rig.co.state()["track"] or {}).get("art_uri"))
    uri = rig.co.state()["track"]["art_uri"]
    assert uri.startswith("file://") and uri.endswith(".jpg")
    from urllib.parse import unquote, urlparse
    assert open(unquote(urlparse(uri).path), "rb").read() == jpeg


async def test_volume_maps_airplay_db_to_percent_and_mute(rig):
    rig.start_track()
    await wait_for(lambda: rig.co.state()["status"] == "playing")
    rig.send(ssnc("pvol", "-15.00,0.0,-30.0,0.0"))
    await wait_for(lambda: rig.co.state()["volume"] == 50)
    assert rig.sink.vol == (50, False)           # and it reaches the sound output, not just the state
    rig.send(ssnc("pvol", "-144.00,0.0,-30.0,0.0"))
    await wait_for(lambda: rig.co.state()["muted"] is True)


async def test_controls_go_to_the_senders_dacp_service(rig):
    rig.start_track()
    await wait_for(lambda: rig.co.state()["capabilities"])
    await rig.co.command("pause")
    await rig.co.command("next")
    await rig.co.command("prev")
    rig.send(ssnc("pfls"))
    await wait_for(lambda: rig.co.state()["status"] == "paused")
    await rig.co.command("play")
    assert rig.dacp.hits == [("pause", "999"), ("nextitem", "999"), ("previtem", "999"), ("playpause", "999")]


async def test_a_sender_without_dacp_is_display_only(rig):
    rig.send(ssnc("snam", "Spotify on a phone"), ssnc("pbeg"), ssnc("mdst"), core("minm", "T"), ssnc("mden"), ssnc("pffr"))
    await wait_for(lambda: rig.co.state()["active_source"] == "airplay")
    assert rig.co.state()["capabilities"] == []
    assert await rig.co.command("pause") is False and rig.dacp.hits == []


async def test_takeover_pauses_the_sender_and_silences_the_audio(rig):
    rig.start_track()
    await wait_for(lambda: rig.co.state()["active_source"] == "airplay")
    rig.spot.play()
    await rig.co.settle()
    assert ("pause", "999") in rig.dacp.hits and rig.sink.cleared >= 1
    assert rig.src.feed_on is False and rig.co.state()["active_source"] == "spotify"


async def test_audio_is_read_only_while_live_and_paced_by_the_sink(rig):
    wr = os.open(rig.src.audio_pipe, os.O_WRONLY | os.O_NONBLOCK)
    try:
        os.write(wr, b"a" * 4000)
        await wait_for(lambda: sum(map(len, rig.sink.chunks)) == 4000)
        rig.sink.ms = 400
        os.write(wr, b"b" * 4000)
        await asyncio.sleep(0.2)
        assert sum(map(len, rig.sink.chunks)) == 4000
        rig.sink.ms = 0
        await wait_for(lambda: sum(map(len, rig.sink.chunks)) == 8000)
    finally:
        os.close(wr)


async def test_partial_items_and_junk_are_handled():
    buf = bytearray(b"junk<item><type>73736e63</type><code>70626567</code><length>0</length></item>\n<item><type>636f7265</type>")
    assert decode_items(buf) == [("ssnc", "pbeg", b"")]
    buf.extend(b"<code>6d696e6d</code><length>2</length>\n<data encoding=\"base64\">\nSGk=\n</data></item>")
    assert decode_items(buf) == [("core", "minm", b"Hi")]
    assert len(buf) == 0


async def test_config_for_shairport_sync(tmp_path):
    s = AirPlaySource('Kitchen "Pi"', tmp_path, port=7100, audio_sink=Sink())
    s._write_config()
    text = (tmp_path / "airplay" / "shairport-sync.conf").read_text()
    for want in ('name = "Kitchen \\"Pi\\"";', "port = 7100;", 'output_backend = "pipe";', 'ignore_volume_control = "yes";',
                 "sessioncontrol = {", 'allow_session_interruption = "yes";', "active_state_timeout = 300.0;", f'name = "{tmp_path}/airplay/audio.pipe";', 'include_cover_art = "yes";',
                 f'pipe_name = "{tmp_path}/airplay/metadata.pipe";'):
        assert want in text


async def test_missing_binary_means_unavailable_not_a_crash(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _n: None)
    s = AirPlaySource("x", tmp_path)
    seen = []
    s.bind(lambda sid, ev: seen.append(ev))
    await s.start()
    assert [e.available for e in seen] == [False]
    await s.stop()
