"""The ESPHome server: TCP listener, per-client connections, the standard handshake, and entity plumbing.

Anything beyond that (voice assistant, later) plugs in through `add_handler(MessageClass, fn)` and
`Connection.send(...)`, so the transport never needs to learn about it.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Iterable

from aioesphomeapi import api_pb2 as pb
from aioesphomeapi.core import MESSAGE_TYPE_TO_PROTO
from google.protobuf import message

from . import framing, noise
from .entities import Entity, Service

log = logging.getLogger(__name__)

API_VERSION = (1, 10)
Handler = Callable[["Connection", message.Message], "None | Awaitable[None]"]


class Connection:
    def __init__(self, server: "ESPHomeServer", reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.server = server
        self._framer = noise.NoiseFramer(server.noise_psk, server.name) if server.noise_psk else framing.PlainFramer()
        self._reader, self._writer = reader, writer
        self.peer = ":".join(str(x) for x in (writer.get_extra_info("peername") or ("?", 0))[:2])
        self.client_info = ""
        self.subscribed = False
        self.closed = False

    def send(self, *msgs: message.Message) -> None:
        if self.closed or not msgs:
            return
        try:
            self._writer.write(self._framer.encode(msgs))
        except Exception:                       # a dying socket must not take the core down
            log.debug("send to %s failed", self.peer, exc_info=True)
            self.close()

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            self._writer.close()

    async def run(self) -> None:
        try:
            while not self.closed:
                data = await self._reader.read(8192)
                if not data:
                    break
                reply, frames = self._framer.feed(data)
                if reply:
                    self._writer.write(reply)
                for type_id, payload in frames:
                    cls = MESSAGE_TYPE_TO_PROTO.get(type_id)
                    if cls is None:
                        log.debug("ignoring unknown message type %s", type_id)
                        continue
                    await self.server._dispatch(self, cls.FromString(payload))
        except framing.FrameError as e:
            log.warning("%s: %s; closing", self.peer, e)
            if getattr(e, "reply", b""):
                try:
                    self._writer.write(e.reply)
                except Exception:
                    pass
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            self.close()


class ESPHomeServer:
    def __init__(self, info: Callable[[], pb.DeviceInfoResponse], name: str, *, server_info: str = "havenOS",
                 noise_psk: bytes | None = None) -> None:
        self._info = info
        self.noise_psk = noise_psk                  # 32 bytes = Noise encryption on (clients must have the same key)
        self.name = name
        self.server_info = server_info
        self.entities: list[Entity] = []
        self.services: list[Service] = []
        self.connections: set[Connection] = set()
        self._handlers: dict[type, list[Handler]] = {}
        self._server: asyncio.AbstractServer | None = None
        self.port = 0
        self.on_clients_changed: Callable[[int], None] = lambda n: None
        self._on_disconnect: list[Callable[["Connection"], None]] = []

    # ---- extension point (voice assistant registers here) --------------------------------------

    def add_handler(self, cls: type, fn: Handler) -> None:
        self._handlers.setdefault(cls, []).append(fn)

    def on_disconnect(self, fn: Callable[["Connection"], None]) -> None:
        self._on_disconnect.append(fn)

    # ---- lifecycle -----------------------------------------------------------------------------

    async def start(self, host: str, port: int) -> int:
        self._server = await asyncio.start_server(self._client, host, port)
        self.port = self._server.sockets[0].getsockname()[1]
        return self.port

    async def stop(self) -> None:
        for c in list(self.connections):
            c.close()
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        conn = Connection(self, reader, writer)
        self.connections.add(conn)
        log.info("ESPHome client connected: %s", conn.peer)
        self.on_clients_changed(len(self.connections))
        try:
            await conn.run()
        finally:
            self.connections.discard(conn)
            log.info("ESPHome client disconnected: %s", conn.peer)
            for fn in self._on_disconnect:
                try:
                    fn(conn)
                except Exception:
                    log.exception("disconnect handler failed")
            self.on_clients_changed(len(self.connections))

    # ---- outgoing ------------------------------------------------------------------------------

    def broadcast(self, msgs: Iterable[message.Message]) -> None:
        msgs = [m for m in msgs if m is not None]
        for c in list(self.connections):
            if c.subscribed:
                c.send(*msgs)

    # ---- incoming ------------------------------------------------------------------------------

    async def _dispatch(self, conn: Connection, msg: message.Message) -> None:
        handled = await self._standard(conn, msg)
        for fn in self._handlers.get(type(msg), []):
            result = fn(conn, msg)
            if asyncio.iscoroutine(result):
                await result
            handled = True
        if not handled:
            log.debug("unhandled %s from %s", type(msg).__name__, conn.peer)

    async def _standard(self, conn: Connection, msg: message.Message) -> bool:
        if isinstance(msg, pb.HelloRequest):
            conn.client_info = msg.client_info
            conn.send(pb.HelloResponse(api_version_major=API_VERSION[0], api_version_minor=API_VERSION[1],
                                       server_info=self.server_info, name=self.name))
        elif isinstance(msg, pb.AuthenticationRequest):
            conn.send(pb.AuthenticationResponse(invalid_password=False))     # no password: the LAN is the boundary
        elif isinstance(msg, pb.PingRequest):
            conn.send(pb.PingResponse())
        elif isinstance(msg, pb.DisconnectRequest):
            conn.send(pb.DisconnectResponse())
            conn.close()
        elif isinstance(msg, pb.DeviceInfoRequest):
            conn.send(self._info())
        elif isinstance(msg, pb.ListEntitiesRequest):
            conn.send(*[e.describe() for e in self.entities], *[s.describe() for s in self.services],
                      pb.ListEntitiesDoneResponse())
        elif isinstance(msg, pb.SubscribeStatesRequest):
            conn.subscribed = True
            conn.send(*[m for m in (e.state() for e in self.entities) if m is not None])
        elif isinstance(msg, pb.ExecuteServiceRequest):
            for s in self.services:
                if s.key == msg.key:
                    try:
                        s.execute(msg)
                    except Exception:
                        log.exception("service %s failed", s.name)
        elif isinstance(msg, (pb.SwitchCommandRequest, pb.NumberCommandRequest, pb.SelectCommandRequest,
                              pb.ButtonCommandRequest, pb.MediaPlayerCommandRequest)):
            for e in self.entities:
                if e.command(msg):
                    break
        elif isinstance(msg, (pb.SubscribeHomeassistantServicesRequest, pb.SubscribeHomeAssistantStatesRequest,
                              pb.SubscribeLogsRequest, pb.SubscribeVoiceAssistantRequest)):
            pass                                                          # accepted, nothing to send (yet)
        else:
            return False
        return True
