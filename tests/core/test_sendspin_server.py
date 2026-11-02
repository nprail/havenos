"""SendspinSource against a real in-process aiosendspin *server* (what Music Assistant runs): real handshake, real roles,
real metadata/controller/group messages. Skipped when the server extra (numpy, av) is not installed."""
import asyncio
import socket

import pytest

pytest.importorskip("aiosendspin.server")

from aiosendspin.client import ClientListener
from aiosendspin.models.types import ConnectionReason, MediaCommand, PlaybackStateType
from aiosendspin.noise import Identity, InMemoryServerPairingStore
from aiosendspin.server import SendspinServer

from conftest import wait_for
from havenos.core.media import MediaCoordinator
from havenos.core.media.sources.fake import FakeSource
from havenos.core.media.sources.sendspin import SendspinSource


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Rig:
    """Music Assistant stand-in dialling our listener, plus the coordinator on our side."""

    async def start(self, tmp_path, clock) -> "Rig":
        self.port = free_port()
        self.music: list[dict] = []
        self.co = MediaCoordinator(lambda **ch: self.music.append(ch["music"]), clock=clock)
        self.src = SendspinSource(
            "havenOS test", tmp_path, port=self.port,
            listener_factory=lambda cid: ClientListener(client_id=cid, on_connection=self.src._on_connection, port=self.port,
                                                        host="127.0.0.1", advertise_mdns=False))
        self.air = FakeSource("airplay", "AirPlay")
        self.co.register(self.src)
        self.co.register(self.air)
        await self.co.start()
        self.server = SendspinServer(asyncio.get_running_loop(), Identity.generate(), "Test MA",
                                     pairing_store=InMemoryServerPairingStore(), allow_unencrypted=True)
        self.server.connect_to_client(f"ws://127.0.0.1:{self.port}/sendspin", retry_initial_connection=True,
                                      connection_reason=ConnectionReason.PLAYBACK)
        await wait_for(lambda: self.co.state()["sources"]["sendspin"]["client"], timeout=10)
        self.sc = self.server.clients[0]
        # What Music Assistant's auto-trust does for a client that offers guest access (the source does, by default);
        # without that offer the roles stay inactive until a manual pairing.
        await self.server.trust_unpaired(self.sc.client_id, approved_roles={"controller", "metadata"})
        self.group = self.sc.group
        self.events: list = []
        self.group.add_event_listener(lambda g, ev: self.events.append(type(ev).__name__))
        self.group.group_role("controller").set_supported_commands(
            [MediaCommand.PLAY, MediaCommand.PAUSE, MediaCommand.NEXT, MediaCommand.PREVIOUS])
        return self

    async def stop(self) -> None:
        await self.co.stop()
        await self.server.close() if hasattr(self.server, "close") else None


@pytest.fixture
async def rig(tmp_path, clock):
    r = await Rig().start(tmp_path, clock)
    yield r
    await r.stop()


async def test_connect_metadata_play_control_and_eviction(rig):
    assert rig.co.state()["sources"]["sendspin"]["client"] == "Test MA"
    assert rig.co.state()["active_source"] is None                           # connected, not playing: nothing taken

    rig.group.group_role("metadata").update(title="Real Song", artist="Real Artist", album="Real Album",
                                            track_duration=200_000, track_progress=5_000, playback_speed=1000)
    rig.group._set_playback_state(PlaybackStateType.PLAYING)
    await wait_for(lambda: rig.co.state()["active_source"] == "sendspin" and rig.co.state()["track"]
                   and rig.co.state()["capabilities"])
    st = rig.co.state()
    assert (st["track"]["title"], st["track"]["duration"], st["position"]) == ("Real Song", 200.0, pytest.approx(5.0, abs=1))
    assert st["status"] == "playing" and st["capabilities"] == ["next", "pause", "play", "prev"]   # no seek offered

    assert await rig.co.command("pause") is True
    await wait_for(lambda: "ControllerPauseEvent" in rig.events)
    assert await rig.co.command("seek", seconds=10) is False                  # refused before it reaches the wire

    rig.air.play()                                                            # AirPlay starts: we are evicted
    await rig.co.settle()
    assert rig.co.state()["active_source"] == "airplay"
    await wait_for(lambda: rig.group.state is PlaybackStateType.STOPPED)      # we left the group, nobody paused it
    assert rig.sc.group is not None and "ControllerPauseEvent" in rig.events


async def test_pause_from_the_server_side_shows_up(rig):
    rig.group.group_role("metadata").update(title="T", artist="A", track_progress=0, track_duration=1000, playback_speed=1000)
    rig.group._set_playback_state(PlaybackStateType.PLAYING)
    await wait_for(lambda: rig.co.state()["status"] == "playing")
    rig.group._set_playback_state(PlaybackStateType.PAUSED)
    await wait_for(lambda: rig.co.state()["status"] == "paused")
    assert rig.co.state()["active_source"] == "sendspin"                      # pause keeps the slot
