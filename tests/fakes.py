"""In-process fake Home Assistant and Immich servers (aiohttp) for tests."""
from __future__ import annotations

import asyncio
import io
from datetime import datetime, timedelta, timezone
from typing import Any

from aiohttp import WSMsgType, web
from PIL import Image


async def _start(app: web.Application, port: int = 0) -> tuple[web.AppRunner, str]:
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    return runner, f"http://127.0.0.1:{port}"


class FakeHA:
    TOKEN = "good-token"

    def __init__(self) -> None:
        self.states: dict[str, dict] = {}
        self.calls: list[dict] = []
        self.sockets: list[web.WebSocketResponse] = []
        self.subs: dict[web.WebSocketResponse, dict[str, int]] = {}     # per socket: subscription key -> message id
        self.connections = 0
        self.forecasts: dict[str, list] = {"daily": [], "hourly": []}
        # registries + exposure (what the room screens are built from)
        self.areas: list[dict] = []
        self.devices: list[dict] = []
        self.entity_reg: dict[str, dict] = {}
        self.exposed: dict[str, dict] = {}
        self.expose_error: str | None = None       # make the exposure command fail (non-admin token)
        self.notifications: dict[str, dict] = {}
        self.stt_requests: list[dict] = []          # what /api/stt/<entity> was sent: entity, headers, audio
        self.stt_text = "play some jazz"
        self.stt_status = 200
        self.language = "en"

    def set(self, entity_id: str, state: str, **attrs: Any) -> dict:
        self.states[entity_id] = {"entity_id": entity_id, "state": state, "attributes": attrs}
        return self.states[entity_id]

    def area(self, area_id: str, name: str | None = None) -> None:
        if not any(a["area_id"] == area_id for a in self.areas):
            self.areas.append({"area_id": area_id, "name": name or area_id.replace("_", " ").title()})

    def place(self, entity_id: str, area: str | None, *, exposed: bool = True, state: str = "off", **attrs: Any) -> None:
        """Create an entity with a registry record in `area`, exposed to Assist or not."""
        if entity_id not in self.states:
            self.set(entity_id, state, **attrs)
        if area:
            self.area(area)
        self.entity_reg[entity_id] = {"entity_id": entity_id, "area_id": area, "device_id": None, "entity_category": None,
                                      "hidden_by": None, "disabled_by": None}
        if exposed:
            self.exposed[entity_id] = {"conversation": True}

    def own_device(self, mac: str, area: str | None) -> None:
        self.devices.append({"id": "dev-havenos", "name": "havenOS", "area_id": area, "connections": [["mac", mac.lower()]]})
        if area:
            self.area(area)

    async def start(self, port: int = 0) -> str:
        app = web.Application()
        app.router.add_get("/api/websocket", self._ws)
        app.router.add_post("/api/stt/{entity}", self._stt)
        self._runner, self.url = await _start(app, port)
        return self.url

    async def stop(self) -> None:
        for ws in list(self.sockets):
            await ws.close()
        await self._runner.cleanup()

    async def _event(self, key: str, event: dict) -> None:
        for ws in list(self.sockets):
            sid = self.subs.get(ws, {}).get(key)
            if sid is not None:
                await ws.send_json({"type": "event", "id": sid, "event": event})

    async def push(self, entity_id: str) -> None:
        await self._event("state_changed", {"event_type": "state_changed", "data": {
            "entity_id": entity_id, "new_state": self.states.get(entity_id)}})

    async def registry_changed(self) -> None:
        for key in ("entity_registry_updated", "device_registry_updated", "area_registry_updated"):
            await self._event(key, {"event_type": key, "data": {}})

    async def notify_ha(self, nid: str, title: str, message: str) -> None:
        self.notifications[nid] = {"notification_id": nid, "title": title, "message": message, "created_at": "2026-10-29T12:00:00+00:00"}
        await self._event("persistent_notification", {"type": "added", "notifications": {nid: self.notifications[nid]}})

    async def drop(self) -> None:
        for ws in list(self.sockets):
            await ws.close()

    async def _stt(self, request: web.Request) -> web.Response:
        if request.headers.get("Authorization") != f"Bearer {self.TOKEN}":
            return web.Response(status=401)
        body = await request.read()
        self.stt_requests.append({"entity": request.match_info["entity"], "headers": dict(request.headers), "audio": body})
        if self.stt_status != 200:
            return web.Response(status=self.stt_status)
        return web.json_response({"result": "success" if self.stt_text is not None else "error", "text": self.stt_text or ""})

    async def _ws(self, request: web.Request) -> web.WebSocketResponse:
        from havenos.core.demo import apply_service
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.connections += 1
        await ws.send_json({"type": "auth_required", "ha_version": "2026.1.0"})
        auth = await ws.receive_json()
        if auth.get("access_token") != self.TOKEN:
            await ws.send_json({"type": "auth_invalid", "message": "Invalid access token"})
            await ws.close()
            return ws
        await ws.send_json({"type": "auth_ok", "ha_version": "2026.1.0"})
        self.sockets.append(ws)
        self.subs[ws] = {}
        try:
            async for msg in ws:
                if msg.type != WSMsgType.TEXT:
                    continue
                m = msg.json()
                reply: dict[str, Any] = {"id": m["id"], "type": "result", "success": True, "result": None}
                t = m["type"]
                if t == "subscribe_events":
                    self.subs[ws][m["event_type"]] = m["id"]
                elif t == "persistent_notification/subscribe":
                    self.subs[ws]["persistent_notification"] = m["id"]
                    await ws.send_json(reply)
                    await ws.send_json({"type": "event", "id": m["id"], "event": {"type": "current", "notifications": dict(self.notifications)}})
                    continue
                elif t == "get_states":
                    reply["result"] = list(self.states.values())
                elif t == "get_config":
                    reply["result"] = {"language": self.language}
                elif t == "config/area_registry/list":
                    reply["result"] = self.areas
                elif t == "config/device_registry/list":
                    reply["result"] = self.devices
                elif t == "config/entity_registry/list":
                    reply["result"] = list(self.entity_reg.values())
                elif t == "homeassistant/expose_entity/list":
                    if self.expose_error:
                        reply.update(success=False, error={"code": "unauthorized", "message": self.expose_error})
                    else:
                        reply["result"] = {"exposed_entities": self.exposed}
                elif t == "call_service":
                    self.calls.append(m)
                    eid = (m.get("target") or {}).get("entity_id")
                    if m["service"] == "get_forecasts":
                        kind = m["service_data"]["type"]
                        reply["result"] = {"response": {eid: {"forecast": self.forecasts[kind]}}}
                    elif m["domain"] == "nope":
                        reply.update(success=False, error={"code": "not_found", "message": "Service not found"})
                    elif eid in self.states:
                        apply_service(self.states, m["domain"], m["service"], eid, m.get("service_data"))
                        await self.push(eid)
                await ws.send_json(reply)
        finally:
            if ws in self.sockets:
                self.sockets.remove(ws)
            self.subs.pop(ws, None)
        return ws


def jpeg(size: tuple[int, int] = (1440, 960), color: tuple[int, int, int] = (60, 90, 160)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "JPEG")
    return buf.getvalue()


class FakeImmich:
    KEY = "good-key"

    def __init__(self, n: int = 10, album: str | None = None) -> None:
        now = datetime.now(timezone.utc)
        # asset-00 is brand new; each next one is ~90 days older (so n=24 spans about six years)
        self.assets = [{"id": f"asset-{i:02d}", "type": "IMAGE",
                        "fileCreatedAt": (now - timedelta(days=90 * i + 1)).isoformat()} for i in range(n)]
        self.assets.append({"id": "video-1", "type": "VIDEO", "fileCreatedAt": now.isoformat()})
        self.random_bodies: list[dict] = []
        self.forbid_view = False        # simulate a key without the asset.view permission
        self.album = album
        self.downloads: list[str] = []
        self.broken: set[str] = set()
        self.requests = 0

    def image_bytes(self, asset_id: str) -> bytes:
        return jpeg()

    async def start(self, port: int = 0) -> str:
        app = web.Application(middlewares=[self._auth])
        app.router.add_get("/api/server/ping", lambda r: web.json_response({"res": "pong"}))
        app.router.add_post("/api/search/random", self._random)
        app.router.add_get("/api/albums", self._albums)
        app.router.add_get("/api/albums/{id}", self._album)
        app.router.add_get("/api/assets/{id}/thumbnail", self._thumb)
        self._runner, self.url = await _start(app, port)
        return self.url

    async def stop(self) -> None:
        await self._runner.cleanup()

    @web.middleware
    async def _auth(self, request: web.Request, handler):
        self.requests += 1
        if request.headers.get("x-api-key") != self.KEY and not request.path.endswith("/ping"):
            return web.json_response({"message": "Invalid API key"}, status=401)
        return await handler(request)

    async def _random(self, request: web.Request) -> web.Response:
        body = await request.json()
        self.random_bodies.append(body)
        after, before = body.get("takenAfter"), body.get("takenBefore")
        out = [a for a in self.assets
               if (not after or a["fileCreatedAt"] >= after) and (not before or a["fileCreatedAt"] <= before)]
        return web.json_response(out[: body.get("size", 100)])   # older servers return a bare array

    async def _albums(self, request: web.Request) -> web.Response:
        return web.json_response([{"id": "alb-1", "albumName": "Family", "assetCount": 4}])

    async def _album(self, request: web.Request) -> web.Response:
        if request.match_info["id"] != self.album:
            return web.json_response({}, status=404)
        return web.json_response({"id": self.album, "assets": self.assets[:4]})

    async def _thumb(self, request: web.Request) -> web.Response:
        aid = request.match_info["id"]
        if self.forbid_view:
            return web.json_response({"message": "Missing required permission: asset.view"}, status=403)
        if aid in self.broken:
            return web.Response(status=500)
        self.downloads.append(aid)
        assert request.query.get("size") == "preview"
        return web.Response(body=self.image_bytes(aid), content_type="image/jpeg")


# ---- voice ----------------------------------------------------------------------------------------------------------

class FakeAudio:
    """An AudioBackend that records what it was asked to play. `gate` stays open (instant playback) unless a test clears it."""

    def __init__(self) -> None:
        self.plays: list[tuple[str, str]] = []
        self.stopped: list[str | None] = []
        self.on_chunk = None
        self.started = 0
        self.volume = 1.0
        self.gate = asyncio.Event()
        self.gate.set()
        self._tasks: set[asyncio.Task] = set()

    def start(self, on_chunk) -> None:
        self.on_chunk, self.started = on_chunk, self.started + 1

    def stop(self) -> None:
        self.on_chunk = None
        self.stop_playback()

    async def play(self, source: str, bus: str = "announce") -> bool:
        self.plays.append((source, bus))
        task = asyncio.current_task()
        self._tasks.add(task)
        try:
            await self.gate.wait()
            return True
        except asyncio.CancelledError:
            return False
        finally:
            self._tasks.discard(task)

    def stop_playback(self, bus: str | None = None) -> None:
        self.stopped.append(bus)
        for t in list(self._tasks):
            t.cancel()

    def set_volume(self, volume: float) -> None:
        self.volume = volume

    def sources(self) -> list[str]:
        return [s for s, _ in self.plays]


class ScriptedWake:
    """A WakeEngine that returns the words a test queues on the next audio chunk."""

    def __init__(self) -> None:
        self.queue: list[str] = []
        self.fed = 0
        self.stop_enabled = False
        self.configured: list[tuple] = []

    def feed(self, pcm: bytes) -> list[str]:
        self.fed += 1
        out, self.queue = self.queue, []
        return out

    def configure(self, active, sensitivity) -> None:
        self.configured.append((tuple(active), sensitivity))

    def set_stop_enabled(self, enabled: bool) -> None:
        self.stop_enabled = enabled


class FakeSink:
    """A SoundDeviceSink stand-in that 'plays' what it is given, `speed` times faster than real time."""

    def __init__(self, rate: int = 48000, speed: float = 25.0) -> None:
        import time
        self._time = time
        self.rate, self.speed = rate, speed
        self.data = bytearray()
        self.clears = 0
        self.volumes: list[tuple[int, bool]] = []
        self.stopped = False
        self._queued_ms, self._t = 0.0, time.monotonic()

    def _drain(self) -> None:
        now = self._time.monotonic()
        self._queued_ms = max(0.0, self._queued_ms - (now - self._t) * 1000 * self.speed)
        self._t = now

    def write(self, ts: int, data: bytes, fmt) -> None:
        self._drain()
        self.data += data
        self._queued_ms += len(data) * 1000.0 / (self.rate * 4)

    def buffered_ms(self) -> float:
        self._drain()
        return self._queued_ms

    def clear(self) -> None:
        self.clears += 1
        self._queued_ms = 0.0

    def set_volume(self, level: int, muted: bool) -> None:
        self.volumes.append((level, muted))

    def stop(self) -> None:
        self.stopped = True
