"""SpotifySource against a fake go-librespot (its HTTP API, /events WebSocket and audio FIFO)."""
import asyncio
import os

import pytest
from aiohttp import WSMsgType, web

from conftest import wait_for
from havenos.core.media import MediaCoordinator
from havenos.core.media.sources.fake import FakeSource
from havenos.core.media.sources.spotify import SpotifySource

TRACK = {"uri": "spotify:track:1", "name": "Northern Lines", "artist_names": ["Aurelia Vance", "Guest"],
         "album_name": "Signal Fires", "album_cover_url": "https://i.scdn.co/image/abc", "position": 12000, "duration": 187000}


class FakeLibrespot:
    def __init__(self) -> None:
        self.posts: list[tuple[str, dict]] = []
        self.status: dict | None = None
        self.sockets: list[web.WebSocketResponse] = []
        self.runner: web.AppRunner | None = None

    async def start(self, port: int = 0) -> int:
        app = web.Application()
        app.router.add_get("/status", self._status)
        app.router.add_get("/events", self._events)
        app.router.add_post("/player/{action}", self._post)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", port)
        await site.start()
        return site._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        for ws in self.sockets:
            await ws.close()
        await self.runner.cleanup()

    async def _status(self, req):
        return web.json_response(self.status) if self.status else web.Response(status=204)

    async def _events(self, req):
        ws = web.WebSocketResponse()
        await ws.prepare(req)
        self.sockets.append(ws)
        async for msg in ws:
            if msg.type == WSMsgType.CLOSE:
                break
        return ws

    async def _post(self, req):
        self.posts.append((req.match_info["action"], await req.json()))
        return web.Response()

    async def send(self, type: str, **data) -> None:
        await asyncio.gather(*(ws.send_json({"type": type, "data": data}) for ws in self.sockets))


class Sink:
    def __init__(self) -> None:
        self.chunks: list[bytes] = []
        self.cleared = 0
        self.vol = None
        self.ms = 0.0

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
    gl = FakeLibrespot()
    port = await gl.start()
    sink = Sink()
    src = SpotifySource("havenOS test", tmp_path, api_port=port, manage_process=False, audio_sink=sink)
    air = FakeSource("airplay", "AirPlay")
    co = MediaCoordinator(lambda **ch: None, clock=clock, select_feed=lambda a: [
        x.set_feed(a is None or x.id == a) for x in (src, air)])
    co.register(src)
    co.register(air)
    await co.start()
    await wait_for(lambda: gl.sockets)
    await wait_for(lambda: co.state()["sources"]["spotify"]["available"])
    r = type("Rig", (), dict(gl=gl, sink=sink, src=src, air=air, co=co))
    yield r
    await co.stop()
    await gl.stop()


async def test_a_spotify_session_becomes_the_active_source(rig):
    await rig.gl.send("active")
    await rig.gl.send("metadata", **TRACK)
    await rig.gl.send("playing", uri="spotify:track:1", resume=False)
    await wait_for(lambda: rig.co.state()["status"] == "playing")
    st = rig.co.state()
    assert st["active_source"] == "spotify"
    assert (st["track"]["title"], st["track"]["artist"], st["track"]["album"]) == ("Northern Lines", "Aurelia Vance, Guest", "Signal Fires")
    assert st["track"]["art_uri"].startswith("https://i.scdn.co") and st["track"]["duration"] == 187.0
    assert st["position"] == 12.0 and set(st["capabilities"]) == {"play", "pause", "next", "prev", "seek"}


async def test_pause_seek_and_end_of_session(rig):
    await rig.gl.send("metadata", **TRACK)
    await rig.gl.send("playing")
    await wait_for(lambda: rig.co.state()["status"] == "playing")
    await rig.gl.send("paused")
    await wait_for(lambda: rig.co.state()["status"] == "paused")
    await rig.gl.send("seek", position=90000, duration=187000)
    await wait_for(lambda: rig.co.state()["position"] == 90.0)
    await rig.gl.send("inactive")
    await wait_for(lambda: rig.co.state()["active_source"] is None)


async def test_commands_map_to_the_http_api(rig):
    await rig.gl.send("metadata", **TRACK)
    await rig.gl.send("playing")
    await wait_for(lambda: rig.co.state()["active_source"] == "spotify")
    for cmd, args in (("pause", {}), ("play", {}), ("next", {}), ("prev", {}), ("seek", {"seconds": 42.5})):
        assert await rig.co.command(cmd, **args) is True
    assert [p[0] for p in rig.gl.posts if p[0] != "volume"] == ["pause", "resume", "next", "prev", "seek"]
    assert rig.gl.posts[-1] == ("seek", {"position": 42500})


async def test_takeover_stops_spotify_and_silences_its_audio(rig):
    await rig.gl.send("metadata", **TRACK)
    await rig.gl.send("playing")
    await wait_for(lambda: rig.co.state()["active_source"] == "spotify")
    rig.air.play()
    await rig.co.settle()
    assert ("stop", {}) in rig.gl.posts and rig.sink.cleared >= 1
    assert rig.src.feed_on is False and rig.co.state()["active_source"] == "airplay"


async def test_volume_both_ways_uses_the_daemons_steps(rig):
    await rig.gl.send("volume", value=25, max=50)
    await rig.gl.send("metadata", **TRACK)
    await rig.gl.send("playing")
    await wait_for(lambda: rig.co.state()["active_source"] == "spotify")
    await rig.gl.send("volume", value=25, max=50)
    await wait_for(lambda: rig.co.state()["volume"] == 50)               # 25 of 50 steps
    await rig.co.command("volume", level=80)
    assert rig.gl.posts[-1] == ("volume", {"volume": 40}) and rig.sink.vol == (80, False)


async def test_joins_a_session_that_is_already_playing(tmp_path, clock):
    gl = FakeLibrespot()
    gl.status = {"stopped": False, "paused": False, "buffering": False, "volume": 30, "volume_steps": 100, "track": TRACK}
    port = await gl.start()
    src = SpotifySource("x", tmp_path, api_port=port, manage_process=False)
    co = MediaCoordinator(lambda **ch: None, clock=clock)
    co.register(src)
    await co.start()
    await wait_for(lambda: co.state()["active_source"] == "spotify")
    assert co.state()["track"]["title"] == "Northern Lines" and co.state()["status"] == "playing"
    await co.stop()
    await gl.stop()


async def test_daemon_down_is_unavailable_and_it_reconnects(tmp_path, clock):
    gl = FakeLibrespot()
    port = await gl.start()
    src = SpotifySource("x", tmp_path, api_port=port, manage_process=False)
    co = MediaCoordinator(lambda **ch: None, clock=clock)
    co.register(src)
    await co.start()
    await wait_for(lambda: co.state()["sources"]["spotify"]["available"])
    await gl.stop()
    await wait_for(lambda: not co.state()["sources"]["spotify"]["available"])
    gl2 = FakeLibrespot()
    await gl2.start(port)
    await wait_for(lambda: co.state()["sources"]["spotify"]["available"], timeout=6)
    await co.stop()
    await gl2.stop()


async def test_audio_is_read_from_the_pipe_only_while_the_sink_needs_it(rig):
    wr = os.open(rig.src.pipe, os.O_WRONLY | os.O_NONBLOCK)
    try:
        os.write(wr, b"a" * 4000)
        await wait_for(lambda: sum(map(len, rig.sink.chunks)) == 4000)
        rig.sink.ms = 400                                                    # the sink is full: leave the pipe alone
        os.write(wr, b"b" * 4000)
        await asyncio.sleep(0.2)
        assert sum(map(len, rig.sink.chunks)) == 4000
        rig.sink.ms = 0
        await wait_for(lambda: sum(map(len, rig.sink.chunks)) == 8000)
        rig.src.set_feed(False)                                              # evicted: audio is drained and dropped
        os.write(wr, b"c" * 4000)
        await asyncio.sleep(0.2)
        assert sum(map(len, rig.sink.chunks)) == 8000
        with pytest.raises(BlockingIOError):                                 # the pipe was emptied, not left to back up
            os.read(rig.src._audio.fds[0], 10)
    finally:
        os.close(wr)


async def test_config_for_go_librespot(tmp_path):
    s = SpotifySource('Kitchen "Pi"', tmp_path, api_port=4000, audio_sink=Sink())
    s._write_config()
    text = (tmp_path / "spotify" / "config.yml").read_text()
    for want in ('device_name: "Kitchen \\"Pi\\""', "audio_backend: pipe", f'audio_output_pipe: "{tmp_path}/spotify/audio.pipe"',
                 "port: 4000", "address: 127.0.0.1", "external_volume: true", "persist_credentials: true"):
        assert want in text
    s2 = SpotifySource("x", tmp_path / "b")
    s2._write_config()
    assert "/dev/null" in (tmp_path / "b" / "spotify" / "config.yml").read_text()


async def test_missing_binary_means_unavailable_not_a_crash(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _n: None)
    s = SpotifySource("x", tmp_path)
    seen = []
    s.bind(lambda sid, ev: seen.append(ev))
    await s.start()
    assert [e.available for e in seen] == [False]
    await s.stop()


async def test_a_burst_of_playback_errors_stops_playback_and_tells_the_user(tmp_path, clock):
    gl = FakeLibrespot()
    port = await gl.start()
    notes = []
    src = SpotifySource("x", tmp_path, api_port=port, manage_process=False)
    co = MediaCoordinator(lambda **ch: None, clock=clock, notify=lambda m, t: notes.append((t, m)))
    co.register(src)
    await co.start()
    await wait_for(lambda: gl.sockets)
    err = dict(message="failed retrieving audio key", unplayable=True)
    await gl.send("playback_error", **err)
    await gl.send("playback_error", **err)
    await asyncio.sleep(0.2)
    assert ("stop", {}) not in gl.posts and not notes                      # two failures: a track may just be bad
    await gl.send("playback_error", **err)
    await wait_for(lambda: ("stop", {}) in gl.posts and notes)
    assert notes[0][0] == "Spotify" and "Premium" in notes[0][1]
    await co.stop()
    await gl.stop()
