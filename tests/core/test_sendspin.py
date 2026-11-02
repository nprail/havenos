"""SendspinSource against a fake client that speaks aiosendspin's real listener API and payload models."""
import asyncio

import pytest
from aiosendspin.client.models import ServerInfo
from aiosendspin.models.controller import ControllerStatePayload
from aiosendspin.models.core import GroupUpdateServerPayload, PlayerCommandPayload, ServerCommandPayload, ServerStatePayload
from aiosendspin.models.metadata import Progress, SessionUpdateMetadata
from aiosendspin.models.types import MediaCommand, PlaybackStateType, PlayerCommand, RepeatMode

from conftest import wait_for
from havenos.core.media import MediaCoordinator
from havenos.core.media.sources.fake import FakeSource
from havenos.core.media.sources.sendspin import SendspinSource


class FakeClient:
    """Just enough of SendspinClient: listener registries, an admission handshake, and a record of what we sent."""

    def __init__(self, identity, store) -> None:
        self.identity, self.store = identity, store
        self.cb: dict[str, list] = {k: [] for k in ("metadata", "controller", "group", "disconnect", "audio", "end", "clear", "cmd")}
        self.server_info = None
        self.sent: list[tuple] = []
        self.position_ms: int | None = None
        self.hold = asyncio.Event()
        self.refuse: Exception | None = None

    def _reg(self, kind):
        def add(cb):
            self.cb[kind].append(cb)
            return lambda: self.cb[kind].remove(cb)
        return add

    def __getattr__(self, name):
        kinds = {"add_metadata_listener": "metadata", "add_controller_state_listener": "controller",
                 "add_group_update_listener": "group", "add_disconnect_listener": "disconnect",
                 "add_audio_chunk_listener": "audio", "add_stream_end_listener": "end",
                 "add_stream_clear_listener": "clear", "add_server_command_listener": "cmd"}
        if name in kinds:
            return self._reg(kinds[name])
        raise AttributeError(name)

    async def attach_websocket(self, ws):
        if self.refuse:
            raise self.refuse
        self.server_info = ServerInfo(server_id="ma", name="Music Assistant")
        await self.hold.wait()
        for cb in list(self.cb["disconnect"]):
            cb()

    def current_track_position(self):
        return self.position_ms

    async def send_group_command(self, command, **kw):
        self.sent.append(("cmd", command, kw))

    async def send_leave(self):
        self.sent.append(("leave",))

    async def send_player_state(self, **kw):
        self.sent.append(("player_state", kw))

    async def disconnect(self, *a):
        pass

    async def set_unpaired_access(self, *, enabled):
        self.unpaired = enabled

    def fire(self, kind, *args):
        for cb in list(self.cb[kind]):
            cb(*args)


class FakeListener:
    def __init__(self, client_id):
        self.started = False

    async def start(self):
        self.started = True

    async def stop(self):
        self.started = False


class Sink:
    def __init__(self):
        self.written, self.cleared = [], 0

    def write(self, ts, data, fmt):
        self.written.append((ts, data))

    def clear(self):
        self.cleared += 1


@pytest.fixture
async def src(tmp_path):
    events = []
    s = SendspinSource("Kitchen", tmp_path, client_factory=FakeClient, listener_factory=FakeListener)
    s.bind(lambda sid, ev: events.append(ev))
    s.events = events
    await s.start()
    yield s
    await s.stop()


def meta(**kw) -> ServerStatePayload:
    return ServerStatePayload(metadata=SessionUpdateMetadata(timestamp=0, **kw))


async def test_start_announces_availability_and_persists_a_stable_identity(tmp_path):
    a = SendspinSource("A", tmp_path, client_factory=FakeClient, listener_factory=FakeListener)
    b = SendspinSource("A", tmp_path, client_factory=FakeClient, listener_factory=FakeListener)
    a.bind(lambda *_: None)
    b.bind(lambda *_: None)
    await a.start()
    await b.start()
    assert a._client.identity.peer_id == b._client.identity.peer_id        # same keypair after a "restart"
    assert (tmp_path / "sendspin_identity.json").stat().st_mode & 0o777 == 0o600


async def test_unavailable_when_the_listener_cannot_start(tmp_path):
    class Busy(FakeListener):
        async def start(self):
            raise OSError("address in use")
    s = SendspinSource("A", tmp_path, client_factory=FakeClient, listener_factory=Busy)
    seen = []
    s.bind(lambda sid, ev: seen.append(ev))
    await s.start()
    assert [e.available for e in seen] == [False]


async def test_session_follows_the_server_connection(src):
    task = asyncio.create_task(src._on_connection(object()))
    await wait_for(lambda: any(type(e).__name__ == "SessionStarted" for e in src.events))
    assert src.events[-1].client == "Music Assistant"
    src._client.hold.set()
    await task
    assert type(src.events[-1]).__name__ == "SessionEnded"


async def test_rejected_connection_starts_no_session(src):
    src._client.refuse = RuntimeError("busy with another server")
    await src._on_connection(object())
    assert not any(type(e).__name__ == "SessionStarted" for e in src.events)


async def test_metadata_maps_to_track_and_position(src):
    src._client.position_ms = 61_500
    src._client.fire("metadata", meta(title="Paper Lanterns", artist="Mika", album="Evenings",
                                      artwork_url="http://ma/art.jpg",
                                      progress=Progress(track_progress=60_000, track_duration=242_000, playback_speed=1000)))
    m, p = src.events[-2:]
    assert (m.title, m.artist, m.album, m.art_uri, m.duration) == ("Paper Lanterns", "Mika", "Evenings", "http://ma/art.jpg", 242.0)
    assert p.seconds == 61.5                                                # the client's extrapolated position wins
    src._client.position_ms = None
    src._client.fire("metadata", meta(title="X", progress=Progress(60_000, 0, 1000)))
    assert src.events[-1].seconds == 60.0 and src.events[-2].duration is None   # duration 0 = unknown / live


async def test_group_playback_state_maps(src):
    for state, want in ((PlaybackStateType.PLAYING, "playing"), (PlaybackStateType.PAUSED, "paused"),
                        (PlaybackStateType.STOPPED, "stopped")):
        src._client.fire("group", GroupUpdateServerPayload(playback_state=state))
        assert src.events[-1].status == want


async def test_controller_state_maps_to_capabilities(src):
    src._client.fire("controller", ServerStatePayload(controller=ControllerStatePayload(
        supported_commands=[MediaCommand.PLAY, MediaCommand.PAUSE, MediaCommand.NEXT, MediaCommand.PREVIOUS,
                            MediaCommand.SHUFFLE, MediaCommand.VOLUME],
        volume=50, muted=False, repeat=RepeatMode.OFF, shuffle=False)))
    assert src.events[-1].commands == frozenset({"play", "pause", "next", "prev"})      # no seek: the UI greys it out


async def test_commands_become_group_commands(src):
    await src.command("pause")
    await src.command("prev")
    await src.command("seek", seconds=30.5)
    assert src._client.sent == [("cmd", MediaCommand.PAUSE, {}), ("cmd", MediaCommand.PREVIOUS, {}),
                                ("cmd", MediaCommand.SEEK, {"position_ms": 30500})]


async def test_a_refused_command_is_logged_not_raised(src):
    async def refuse(*a, **k):
        raise ValueError("not in supported_commands")
    src._client.send_group_command = refuse
    await src.command("next")


async def test_release_leaves_the_group_instead_of_pausing_it(src):
    await src.release()
    assert src._client.sent == [("leave",)]                                  # a group pause would stop the other rooms


async def test_release_survives_a_dead_connection(src):
    async def dead():
        raise RuntimeError("Client is not connected")
    src._client.send_leave = dead
    await src.release()


async def test_without_a_sink_we_are_not_a_player(src):
    from aiosendspin.models.types import Roles
    from aiosendspin.client import SendspinClient
    real = SendspinSource("K", src.state_dir)._make_client(src._client.identity, src._client.store)
    assert Roles.PLAYER not in real.roles and {Roles.METADATA, Roles.CONTROLLER} <= set(real.roles)
    sink = SendspinSource("K", src.state_dir, audio_sink=Sink())._make_client(src._client.identity, src._client.store)
    assert Roles.PLAYER in sink.roles
    await real.disconnect()
    await sink.disconnect()


async def test_audio_is_forwarded_to_the_sink_and_cleared_on_stream_end(tmp_path):
    sink = Sink()
    s = SendspinSource("K", tmp_path, audio_sink=sink, client_factory=FakeClient, listener_factory=FakeListener)
    s.bind(lambda *_: None)
    await s.start()
    s._client.fire("audio", 123, b"pcm", object(), 0)
    assert sink.written == [(123, b"pcm")]
    s._client.fire("end", None)
    s._client.fire("clear", ["player"])
    await s.release()
    assert sink.cleared == 3
    await s.stop()


async def test_server_volume_command_becomes_a_volume_event(tmp_path):
    seen = []
    s = SendspinSource("K", tmp_path, audio_sink=Sink(), client_factory=FakeClient, listener_factory=FakeListener)
    s.bind(lambda sid, ev: seen.append(ev))
    await s.start()
    s._client.fire("cmd", ServerCommandPayload(player=PlayerCommandPayload(command=PlayerCommand.VOLUME, volume=42)))
    s._client.fire("cmd", ServerCommandPayload(player=PlayerCommandPayload(command=PlayerCommand.MUTE, mute=True)))
    assert [(e.level, e.muted) for e in seen if hasattr(e, "level")] == [(42, False), (42, True)]
    await s.set_volume(70, False)
    assert s._client.sent[-1] == ("player_state", {"available": True, "volume": 70, "muted": False})
    await s.stop()


async def test_pairing_code_is_surfaced(src):
    await src._show_pairing_code("123456", grouped="123-456")
    assert src.events[-1].code == "123-456"
    await src._show_pairing_code(None, grouped=None)
    assert src.events[-1].code is None


async def test_end_to_end_with_the_coordinator_a_sendspin_play_is_taken_over_by_airplay(tmp_path, clock):
    states = []
    co = MediaCoordinator(lambda **ch: states.append(ch["music"]), clock=clock)
    s = SendspinSource("K", tmp_path, client_factory=FakeClient, listener_factory=FakeListener)
    air = FakeSource("airplay", "AirPlay")
    co.register(s)
    co.register(air)
    await co.start()
    s._client.fire("controller", ServerStatePayload(controller=ControllerStatePayload(
        supported_commands=[MediaCommand.PAUSE, MediaCommand.PLAY], volume=1, muted=False, repeat=RepeatMode.OFF, shuffle=False)))
    s._client.fire("metadata", meta(title="Paper Lanterns", artist="Mika"))
    s._client.fire("group", GroupUpdateServerPayload(playback_state=PlaybackStateType.PLAYING))
    assert co.state()["active_source"] == "sendspin" and co.state()["track"]["title"] == "Paper Lanterns"
    assert await co.command("pause") is True
    assert s._client.sent[-1][:2] == ("cmd", MediaCommand.PAUSE)
    air.play()
    await co.settle()
    assert co.state()["active_source"] == "airplay" and ("leave",) in s._client.sent
    await co.stop()


async def test_guest_access_is_offered_so_music_assistant_can_add_us_unprompted(tmp_path):
    on = SendspinSource("K", tmp_path, client_factory=FakeClient, listener_factory=FakeListener)
    off = SendspinSource("K", tmp_path, allow_unpaired=False, client_factory=FakeClient, listener_factory=FakeListener)
    for s in (on, off):
        s.bind(lambda *_: None)
        await s.start()
    assert on._client.unpaired is True and not hasattr(off._client, "unpaired")


async def test_sink_follows_master_volume(tmp_path):
    class VolSink(Sink):
        def set_volume(self, level, muted):
            self.vol = (level, muted)
    sink = VolSink()
    s = SendspinSource("K", tmp_path, audio_sink=sink, client_factory=FakeClient, listener_factory=FakeListener)
    s.bind(lambda *_: None)
    await s.start()
    await s.set_volume(33, True)
    assert sink.vol == (33, True)
    await s.stop()
