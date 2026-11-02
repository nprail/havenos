"""MusicLibrary against a fake Music Assistant WebSocket server (envelope, auth and partial batches as the real one)."""
import pytest
from aiohttp import web

from conftest import wait_for
from havenos.core.media.library import DemoLibrary, LibraryError, MusicAssistantClient, MusicLibrary, normalise

ALBUM = {"media_type": "album", "uri": "library://album/1", "name": "Low Tide", "artists": [{"name": "The Harbour Choir"}],
         "image": {"type": "thumb", "path": "a.jpg", "provider": "filesystem", "proxy_id": "abc123"}}
PLAYLIST = {"media_type": "playlist", "uri": "library://playlist/9", "name": "Focus", "owner": "Nick",
            "metadata": {"images": [{"type": "thumb", "path": "http://img.example/p.jpg", "provider": "x", "remotely_accessible": True}]}}
TRACK = {"media_type": "track", "uri": "library://track/5", "name": "Slow Light", "artists": [{"name": "Aurelia"}],
         "album": {"name": "Signal Fires"}}


class FakeMA:
    def __init__(self, token="secret", players=None, fail=()):
        self.token, self.players, self.fail = token, players if players is not None else [], set(fail)
        self.calls: list[tuple[str, dict]] = []
        self.runner = self.url = None

    async def start(self):
        app = web.Application()
        app.router.add_get("/ws", self._ws)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        self.url = f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}"

    async def stop(self):
        await self.runner.cleanup()

    async def _ws(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await ws.send_json({"server_version": "2.9.0", "schema_version": 30})
        authed = False
        async for msg in ws:
            m = msg.json()
            cmd, args, mid = m["command"], m.get("args", {}), m["message_id"]
            if cmd == "auth":
                authed = args.get("token") == self.token
                await ws.send_json({"message_id": mid, "result": {"authenticated": True}} if authed else
                                   {"message_id": mid, "error_code": 20, "details": "Invalid or expired token"})
                continue
            if not authed:
                await ws.send_json({"message_id": mid, "error_code": 20, "details": "authentication required"})
                continue
            self.calls.append((cmd, args))
            if cmd in self.fail:
                await ws.send_json({"message_id": mid, "error_code": 999, "details": "boom"})
            elif cmd == "music/search":
                await ws.send_json({"message_id": mid, "result": {"albums": [ALBUM], "tracks": [TRACK], "playlists": [PLAYLIST]}})
            elif cmd == "music/recently_played_items":
                await ws.send_json({"message_id": mid, "result": [ALBUM]})
            elif cmd == "music/playlists/library_items":       # a big listing arrives in partial batches
                await ws.send_json({"message_id": mid, "partial": True, "result": [PLAYLIST]})
                await ws.send_json({"message_id": mid, "result": [{**PLAYLIST, "uri": "library://playlist/10", "name": "Two"}]})
            elif cmd == "music/albums/library_items":
                await ws.send_json({"message_id": mid, "result": []})
            elif cmd == "players/all":
                await ws.send_json({"message_id": mid, "result": self.players})
            elif cmd == "player_queues/play_media":
                await ws.send_json({"message_id": mid, "result": None})
            else:
                await ws.send_json({"message_id": mid, "error_code": 1, "details": "unknown command"})
        return ws


@pytest.fixture
async def ma():
    s = FakeMA(players=[{"player_id": "up123", "name": "havenOS test"}, {"player_id": "x", "name": "Kitchen"}])
    await s.start()
    yield s
    await s.stop()


@pytest.fixture
async def lib(ma):
    client = MusicAssistantClient(ma.url, "secret", timeout=3)
    yield MusicLibrary(client, player_name="havenOS test", sendspin_client_id=lambda: "sendspin-id")
    await client.close()


def test_normalise_builds_rows_art_and_subtitles():
    a = normalise(ALBUM, "http://ma:8095")
    assert a == {"uri": "library://album/1", "name": "Low Tide", "type": "album", "subtitle": "The Harbour Choir",
                 "art": "http://ma:8095/imageproxy/abc123?size=256"}
    assert normalise(PLAYLIST, "http://ma:8095")["art"] == "http://img.example/p.jpg"       # remotely accessible: used as is
    t = normalise(TRACK, "http://ma:8095")
    assert t["subtitle"] == "Aurelia · Signal Fires" and t["art"] == ""
    legacy = normalise({"media_type": "album", "uri": "u", "name": "n", "image": {"path": "a b.jpg", "provider": "fs"}}, "http://ma")
    assert legacy["art"] == "http://ma/imageproxy?provider=fs&path=a%20b.jpg&size=256"


async def test_search_groups_results_and_sends_the_right_command(lib, ma):
    sections = await lib.search("harbour")
    assert [s["title"] for s in sections] == ["Playlists", "Albums", "Tracks"]
    cmd, args = ma.calls[-1]
    assert cmd == "music/search" and args["search_query"] == "harbour" and "track" in args["media_types"] and args["limit"] == 6
    assert await lib.search("   ") == []                                  # nothing is sent for a blank query
    assert len(ma.calls) == 1


async def test_browse_collects_partial_batches_and_skips_empty_sections(lib):
    sections = await lib.browse()
    assert [s["title"] for s in sections] == ["Recently played", "Playlists"]
    assert [i["name"] for i in sections[1]["items"]] == ["Focus", "Two"]


async def test_browse_survives_one_failing_section(ma):
    ma.fail.add("music/playlists/library_items")
    client = MusicAssistantClient(ma.url, "secret", timeout=3)
    sections = await MusicLibrary(client).browse()
    assert [s["title"] for s in sections] == ["Recently played"]
    await client.close()


async def test_bad_token_and_unreachable_server_are_library_errors(ma):
    bad = MusicAssistantClient(ma.url, "wrong", timeout=3)
    with pytest.raises(LibraryError, match="Invalid or expired token"):
        await bad.call("music/search", search_query="x")
    await bad.close()
    down = MusicAssistantClient("http://127.0.0.1:9", "t", timeout=1)
    with pytest.raises(LibraryError, match="cannot reach Music Assistant"):
        await down.call("music/search", search_query="x")
    await down.close()


async def test_play_targets_our_player_found_by_name(lib, ma):
    await lib.play("library://album/1")
    cmd, args = ma.calls[-1]
    assert cmd == "player_queues/play_media"
    assert args == {"queue_id": "up123", "media": "library://album/1", "option": "replace"}


async def test_player_id_falls_back_to_the_sendspin_id_and_config_wins(ma):
    ma.players = []
    c1 = MusicAssistantClient(ma.url, "secret", timeout=3)
    assert await MusicLibrary(c1, player_name="nope", sendspin_client_id=lambda: "sendspin-id").resolve_player() == "sendspin-id"
    assert await MusicLibrary(c1, player_id="fixed", player_name="nope").resolve_player() == "fixed"
    with pytest.raises(LibraryError, match="not a Music Assistant player"):
        await MusicLibrary(c1, player_name="nope").resolve_player()
    await c1.close()


async def test_client_reconnects_after_the_server_drops_it(lib, ma):
    await lib.search("a")
    await lib._client._ws.close()
    await wait_for(lambda: not lib._client.connected)
    assert await lib.search("again")


async def test_demo_library_searches_and_plays_through_the_callback():
    played = []
    d = DemoLibrary(played.append)
    assert [s["title"] for s in await d.browse()] == ["Playlists", "Albums"]
    found = await d.search("signal")
    assert found[0]["items"][0]["name"] == "Signal Fires"
    await d.play(found[0]["items"][0]["uri"])
    assert played == [{"name": "Signal Fires", "subtitle": "Aurelia Vance"}]
