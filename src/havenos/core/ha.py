"""Home Assistant WebSocket client (https://developers.home-assistant.io/docs/api/websocket).

One persistent connection: auth, `get_states`, a `state_changed` subscription, and request/response
for service calls. Reconnects with backoff. Pure asyncio + aiohttp; no Qt.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

import aiohttp

log = logging.getLogger(__name__)

StatusCb = Callable[[str], None]
StatesCb = Callable[[list[dict]], None]
ChangedCb = Callable[[str, dict | None], None]

BACKOFF = (1.0, 2.0, 5.0, 10.0, 30.0)


class HAError(Exception):
    pass


class HAClient:
    def __init__(self, url: str, token: str, *, on_status: StatusCb, on_states: StatesCb,
                 on_changed: ChangedCb, backoff: tuple[float, ...] = BACKOFF) -> None:
        self._base = url.rstrip("/")
        self._stt_entity: str | None = None
        self._language: str | None = None
        self._ws_url = url.rstrip("/").replace("https://", "wss://", 1).replace("http://", "ws://", 1) + "/api/websocket"
        self._token = token
        self._on_status, self._on_states, self._on_changed = on_status, on_states, on_changed
        self._backoff = backoff
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._next_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._task: asyncio.Task | None = None
        self.status = "connecting"
        # Subscriptions are replayed on every (re)connect; events are routed to their callback by subscription id.
        self._subscriptions: list[tuple[dict, Callable[[dict], None]]] = []
        self._subs: dict[int, Callable[[dict], None]] = {}
        self.add_subscription({"type": "subscribe_events", "event_type": "state_changed"}, self._state_changed_event)

    def add_subscription(self, message: dict, callback: Callable[[dict], None]) -> None:
        """Subscribe to an event stream (`subscribe_events`, `persistent_notification/subscribe`, ...). Survives reconnects."""
        self._subscriptions.append((message, callback))

    def _state_changed_event(self, ev: dict) -> None:
        d = ev.get("data", {})
        self._on_changed(d.get("entity_id"), d.get("new_state"))

    # ---- lifecycle ---------------------------------------------------------------------

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="ha-client")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    def _set_status(self, status: str) -> None:
        if status != self.status:
            self.status = status
            self._on_status(status)

    async def _run(self) -> None:
        attempt = 0
        async with aiohttp.ClientSession() as session:
            while True:
                self._set_status("connecting")
                try:
                    await self._session(session)
                    attempt = 0
                except asyncio.CancelledError:
                    raise
                except HAError as e:
                    if str(e) == "auth_failed":
                        log.error("Home Assistant rejected the access token; not retrying")
                        self._set_status("auth_failed")
                        return
                    log.warning("HA connection error: %s", e)
                except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
                    log.warning("HA connection failed: %s", e)
                self._fail_pending()
                self._set_status("disconnected")
                delay = self._backoff[min(attempt, len(self._backoff) - 1)]
                attempt += 1
                await asyncio.sleep(delay)

    async def _session(self, session: aiohttp.ClientSession) -> None:
        async with session.ws_connect(self._ws_url, heartbeat=30, receive_timeout=90) as ws:
            first = await ws.receive_json()
            if first.get("type") != "auth_required":
                raise HAError(f"unexpected greeting {first.get('type')}")
            await ws.send_json({"type": "auth", "access_token": self._token})
            reply = await ws.receive_json()
            if reply.get("type") == "auth_invalid":
                raise HAError("auth_failed")
            if reply.get("type") != "auth_ok":
                raise HAError(f"unexpected auth reply {reply.get('type')}")
            self._ws = ws
            reader = asyncio.create_task(self._read(ws))
            try:
                for message, callback in self._subscriptions:
                    await self._request_with_id(message, callback=callback)
                states = await self._request({"type": "get_states"})
                self._on_states(states)
                self._set_status("connected")
                await reader          # runs until the socket closes
            finally:
                reader.cancel()
                self._ws = None
                self._subs.clear()

    async def _read(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        async for msg in ws:
            if msg.type != aiohttp.WSMsgType.TEXT:
                continue
            data = msg.json()
            kind = data.get("type")
            if kind == "result":
                fut = self._pending.pop(data["id"], None)
                if fut and not fut.done():
                    if data.get("success"):
                        fut.set_result(data.get("result"))
                    else:
                        fut.set_exception(HAError((data.get("error") or {}).get("message", "request failed")))
            elif kind == "event":
                cb = self._subs.get(data.get("id"))
                if cb:
                    try:
                        cb(data.get("event", {}))
                    except Exception:
                        log.exception("HA event handler failed")

    def _fail_pending(self) -> None:
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(HAError("connection lost"))
        self._pending.clear()

    # ---- requests ----------------------------------------------------------------------

    async def _request_with_id(self, message: dict, timeout: float = 15.0,
                               callback: Callable[[dict], None] | None = None) -> int:
        """Send a request, wait for its result, and return the message id (the subscription id for event streams)."""
        ws = self._ws
        if ws is None:
            raise HAError("not connected")
        self._next_id += 1
        mid = self._next_id
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[mid] = fut
        if callback:
            self._subs[mid] = callback         # before sending: HA may push the first event right behind the result
        await ws.send_json({"id": mid, **message})
        try:
            await asyncio.wait_for(fut, timeout)
        except BaseException:
            self._subs.pop(mid, None)
            raise
        finally:
            self._pending.pop(mid, None)
        return mid

    async def request(self, message: dict, timeout: float = 15.0) -> Any:
        """Send any WebSocket command and return its result (registries, exposure list, services, ...)."""
        ws = self._ws
        if ws is None:
            raise HAError("not connected")
        self._next_id += 1
        mid = self._next_id
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[mid] = fut
        await ws.send_json({"id": mid, **message})
        try:
            return await asyncio.wait_for(fut, timeout)
        finally:
            self._pending.pop(mid, None)

    _request = request

    async def speech_to_text(self, pcm: bytes, *, entity_id: str = "", language: str = "", timeout: float = 25.0) -> str:
        """Transcribe 16 kHz 16-bit mono speech with one of Home Assistant's speech-to-text providers (`POST /api/stt/<entity>`),
        without running an Assist pipeline, so nothing the user says is carried out as a command. With no `entity_id` it
        uses the first `stt.*` entity; with no `language`, Home Assistant's own."""
        if not entity_id:
            if self._stt_entity is None:
                states = await self.request({"type": "get_states"})
                self._stt_entity = next((s["entity_id"] for s in states if s["entity_id"].startswith("stt.")), "")
            entity_id = self._stt_entity
            if not entity_id:
                raise HAError("Home Assistant has no speech-to-text provider (add Whisper, or Home Assistant Cloud)")
        if not language:
            if self._language is None:
                self._language = (await self.request({"type": "get_config"})).get("language", "en")
            language = self._language
        headers = {"Authorization": f"Bearer {self._token}", "X-Speech-Content":
                   f"format=wav; codec=pcm; sample_rate=16000; bit_rate=16; channel=1; language={language}"}
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as http:
                async with http.post(f"{self._base}/api/stt/{entity_id}", data=pcm, headers=headers) as r:
                    if r.status != 200:
                        raise HAError(f"speech-to-text failed ({r.status})")
                    body = await r.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            raise HAError(f"speech-to-text failed: {e}") from e
        if body.get("result") != "success":
            raise HAError("speech-to-text did not understand that")
        return str(body.get("text", "")).strip()

    async def call_service(self, domain: str, service: str, *, entity_id: str | None = None,
                           data: dict | None = None, return_response: bool = False) -> Any:
        msg: dict[str, Any] = {"type": "call_service", "domain": domain, "service": service}
        if data:
            msg["service_data"] = data
        if entity_id:
            msg["target"] = {"entity_id": entity_id}
        if return_response:
            msg["return_response"] = True
        return await self._request(msg)


async def probe(url: str, token: str, timeout: float = 8.0) -> dict:
    """One-shot connection for the settings UI: authenticate, fetch states, and (best effort) which entities are exposed to
    Assist and what areas exist. Raises HAError on a bad token."""
    ws_url = url.rstrip("/").replace("https://", "wss://", 1).replace("http://", "ws://", 1) + "/api/websocket"
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
        async with session.ws_connect(ws_url) as ws:
            await ws.receive_json()
            await ws.send_json({"type": "auth", "access_token": token})
            reply = await ws.receive_json()
            if reply.get("type") == "auth_invalid":
                raise HAError("Home Assistant rejected that access token")
            if reply.get("type") != "auth_ok":
                raise HAError("unexpected reply from Home Assistant")
            async def ask(i: int, t: str) -> Any:
                await ws.send_json({"id": i, "type": t})
                r = await ws.receive_json()
                return r.get("result") if r.get("success") else None
            states = await ask(1, "get_states") or []
            exposed = await ask(2, "homeassistant/expose_entity/list")      # admin-only: None if we may not read it
            areas = await ask(3, "config/area_registry/list")
            return {"version": str(reply.get("ha_version", "")), "states": states,
                    "exposed": None if exposed is None else {k for k, v in exposed.get("exposed_entities", {}).items() if v.get("conversation")},
                    "areas": [{"id": a["area_id"], "name": a["name"].strip()} for a in (areas or [])]}
