"""MusicLibrary (docs/specs/07-music-pipeline.md section 5): search, browse and play-from-display against Music Assistant.

Music Assistant's WebSocket API lives at `<url>/ws`. The server sends `server_info` on connect; newer servers then want
`{"command": "auth", "args": {"token": ...}}` (a long-lived token from Settings -> Profile). Requests are
`{"message_id", "command", "args"}`; replies carry the same `message_id` and either `result` (possibly in `partial`
batches) or `error_code` + `details`. Events (`{"event": ...}`) are ignored here.

Playing is just `player_queues/play_media` against this display's own Sendspin player: Music Assistant then opens a
Sendspin session and the arbiter takes over like for any other source. There is no self-initiated playback path.
"""
from __future__ import annotations

import asyncio
import itertools
import logging
from typing import Any, Awaitable, Callable
from urllib.parse import quote, urlsplit, urlunsplit

import aiohttp

log = logging.getLogger(__name__)

SEARCH_TYPES = ["playlist", "album", "artist", "track"]
SECTION_TITLES = {"playlists": "Playlists", "albums": "Albums", "artists": "Artists", "tracks": "Tracks", "radio": "Radio"}
ART_SIZE = 256


class LibraryError(Exception):
    pass


class MusicAssistantClient:
    """Request/response over MA's WebSocket, connected lazily and reconnected on the next call after a drop."""

    def __init__(self, url: str, token: str = "", *, timeout: float = 10.0,
                 session_factory: Callable[[], aiohttp.ClientSession] | None = None) -> None:
        parts = urlsplit(url if "://" in url else "http://" + url)
        scheme = "wss" if parts.scheme == "https" else "ws"
        self.base_url = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
        self._ws_url = urlunsplit((scheme, parts.netloc, "/ws", "", ""))
        self._token = token
        self._timeout = timeout
        self._session_factory = session_factory or aiohttp.ClientSession
        self._session: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._reader: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._ids = itertools.count(1)
        self._pending: dict[str, tuple[asyncio.Future, list]] = {}
        self.server_info: dict[str, Any] = {}

    @property
    def connected(self) -> bool:
        return self._ws is not None and not self._ws.closed

    async def close(self) -> None:
        if self._reader:
            self._reader.cancel()
            await asyncio.gather(self._reader, return_exceptions=True)
            self._reader = None
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def _connect(self) -> None:
        async with self._lock:
            if self.connected:
                return
            if self._session is None:
                self._session = self._session_factory()
            try:
                self._ws = await self._session.ws_connect(self._ws_url, heartbeat=25, timeout=aiohttp.ClientWSTimeout(ws_close=self._timeout))
                first = await asyncio.wait_for(self._ws.receive_json(), self._timeout)    # server_info
            except (aiohttp.ClientError, OSError, asyncio.TimeoutError, ValueError) as e:
                self._ws = None
                raise LibraryError(f"cannot reach Music Assistant at {self.base_url}: {e}") from e
            if first.get("error_code") is not None:
                await self._ws.close()
                raise LibraryError(first.get("details") or "Music Assistant refused the connection")
            self.server_info = first
            self._reader = asyncio.create_task(self._read(), name="ma-reader")
            if self._token:
                await self._request("auth", {"token": self._token})

    async def _read(self) -> None:
        ws = self._ws
        try:
            async for msg in ws:
                if msg.type != aiohttp.WSMsgType.TEXT:
                    continue
                try:
                    data = msg.json()
                except ValueError:
                    continue
                self._on_message(data)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.debug("music assistant reader failed", exc_info=True)
        finally:
            for fut, _ in self._pending.values():
                if not fut.done():
                    fut.set_exception(LibraryError("connection to Music Assistant closed"))
            self._pending.clear()

    def _on_message(self, data: dict) -> None:
        mid = data.get("message_id")
        entry = self._pending.get(str(mid)) if mid is not None else None
        if entry is None:
            return                                                      # an event, or a reply nobody waits for
        fut, acc = entry
        if data.get("error_code") is not None:
            del self._pending[str(mid)]
            if not fut.done():
                fut.set_exception(LibraryError(data.get("details") or f"error {data['error_code']}"))
        elif data.get("partial"):
            acc.extend(data.get("result") or [])                       # large listings arrive in batches
        else:
            del self._pending[str(mid)]
            result = data.get("result")
            if acc and isinstance(result, list):
                result = acc + result
            if not fut.done():
                fut.set_result(result)

    async def _request(self, command: str, args: dict) -> Any:
        assert self._ws is not None
        mid = str(next(self._ids))
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[mid] = (fut, [])
        try:
            await self._ws.send_json({"message_id": mid, "command": command, "args": args})
            return await asyncio.wait_for(fut, self._timeout)
        except asyncio.TimeoutError as e:
            raise LibraryError(f"Music Assistant did not answer {command}") from e
        finally:
            self._pending.pop(mid, None)

    async def call(self, command: str, **args: Any) -> Any:
        await self._connect()
        try:
            return await self._request(command, {k: v for k, v in args.items() if v is not None})
        except (aiohttp.ClientError, ConnectionError) as e:
            raise LibraryError(str(e)) from e


def _name(x: Any) -> str:
    return x.get("name", "") if isinstance(x, dict) else str(x or "")


def normalise(d: dict, base_url: str) -> dict:
    """A Music Assistant media item (full item or ItemMapping) as the small dict the UI shows."""
    kind = d.get("media_type") or "item"
    artists = [_name(a) for a in d.get("artists") or [] if a]
    sub = ", ".join(x for x in artists if x)
    if kind == "track" and d.get("album"):
        sub = " · ".join(x for x in (sub, _name(d["album"])) if x)
    elif kind == "playlist":
        sub = d.get("owner") or "Playlist"
    elif kind == "artist":
        sub = "Artist"
    elif kind == "radio":
        sub = "Radio"
    return {"uri": d.get("uri") or "", "name": d.get("name") or "", "type": kind, "subtitle": sub,
            "art": _art_url(d, base_url)}


def _art_url(d: dict, base_url: str) -> str:
    img = d.get("image")
    if not img:
        images = (d.get("metadata") or {}).get("images") or []
        img = next((i for i in images if i.get("type") == "thumb"), images[0] if images else None)
    if not img:
        return ""
    if img.get("proxy_id"):
        return f"{base_url}/imageproxy/{img['proxy_id']}?size={ART_SIZE}"
    if img.get("remotely_accessible") and img.get("path"):
        return img["path"]
    if img.get("path") and img.get("provider"):
        return f"{base_url}/imageproxy?provider={quote(img['provider'])}&path={quote(img['path'], safe='')}&size={ART_SIZE}"
    return ""


class MusicLibrary:
    """What the library screen talks to. `player_id` is this display's own player in Music Assistant."""

    available = True

    def __init__(self, client: MusicAssistantClient, *, player_id: str = "", player_name: str = "",
                 sendspin_client_id: Callable[[], str] = lambda: "") -> None:
        self._client = client
        self._player_id = player_id
        self._player_name = player_name
        self._sendspin_client_id = sendspin_client_id

    async def close(self) -> None:
        await self._client.close()

    async def search(self, query: str, limit: int = 6) -> list[dict]:
        query = query.strip()
        if not query:
            return []
        res = await self._client.call("music/search", search_query=query, media_types=SEARCH_TYPES, limit=limit) or {}
        return self._sections(res, ("playlists", "albums", "artists", "tracks"))

    async def browse(self) -> list[dict]:
        """Recently played first, then the user's playlists and albums. A section that fails is left out."""
        async def fetch(title: str, command: str, **args: Any) -> dict | None:
            try:
                items = await self._client.call(command, **args) or []
            except LibraryError as e:
                log.info("library: %s unavailable: %s", title, e)
                return None
            rows = [normalise(i, self._client.base_url) for i in items if i.get("uri")]
            return {"title": title, "items": rows} if rows else None

        got = await asyncio.gather(
            fetch("Recently played", "music/recently_played_items", limit=12, media_types=["album", "playlist", "radio"]),
            fetch("Playlists", "music/playlists/library_items", limit=24),
            fetch("Albums", "music/albums/library_items", limit=24))
        sections = [s for s in got if s]
        if not sections:
            await self._client.call("music/recently_played_items", limit=1)      # raises the real connection error
        return sections

    def _sections(self, res: dict, order: tuple[str, ...]) -> list[dict]:
        out = []
        for key in order:
            rows = [normalise(i, self._client.base_url) for i in res.get(key) or [] if i.get("uri")]
            if rows:
                out.append({"title": SECTION_TITLES[key], "items": rows})
        return out

    async def resolve_player(self) -> str:
        """This display's player id: the configured one, else the Music Assistant player carrying our Sendspin name,
        else the Sendspin client id (which is what Music Assistant keys its Sendspin players by)."""
        if self._player_id:
            return self._player_id
        try:
            players = await self._client.call("players/all") or []
        except LibraryError:
            players = []
        for p in players:
            if self._player_name and self._player_name in (p.get("name"), p.get("display_name")):
                return p["player_id"]
        client_id = self._sendspin_client_id()
        if client_id:
            return client_id
        raise LibraryError("this display is not a Music Assistant player yet (is Sendspin enabled and paired?)")

    async def play(self, uri: str, mode: str = "replace") -> None:
        player = await self.resolve_player()
        await self._client.call("player_queues/play_media", queue_id=player, media=uri, option=mode)


class DemoLibrary:
    """Canned library for demo mode (HAVENOS_MUSIC_DEMO=1 with no Music Assistant configured)."""

    available = True
    ITEMS = {
        "Playlists": [("Evening Wind-down", "Playlist"), ("Kitchen Radio", "Playlist"), ("Focus", "Playlist")],
        "Albums": [("Low Tide", "The Harbour Choir"), ("Signal Fires", "Aurelia Vance"), ("Evenings", "Mika Ostrander")],
    }

    def __init__(self, on_play: Callable[[dict], None]) -> None:
        self._on_play = on_play

    def _rows(self, title: str, q: str = "") -> list[dict]:
        return [{"uri": f"demo://{title.lower()}/{n}", "name": n, "type": title[:-1].lower(), "subtitle": s, "art": ""}
                for n, s in self.ITEMS[title] if q.lower() in f"{n} {s}".lower()]

    async def close(self) -> None: ...

    async def browse(self) -> list[dict]:
        return [{"title": t, "items": self._rows(t)} for t in self.ITEMS]

    async def search(self, query: str, limit: int = 6) -> list[dict]:
        found = [{"title": t, "items": self._rows(t, query.strip())} for t in self.ITEMS]
        return [s for s in found if s["items"]] if query.strip() else []

    async def play(self, uri: str, mode: str = "replace") -> None:
        for sections in self.ITEMS.values():
            for n, s in sections:
                if uri.endswith("/" + n):
                    self._on_play({"name": n, "subtitle": s})
                    return
