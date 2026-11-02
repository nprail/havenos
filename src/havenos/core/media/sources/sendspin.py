"""Sendspin source (docs/specs/07-music-pipeline.md section 3): havenOS as a Sendspin client that Music Assistant (or any
Sendspin server) discovers over mDNS and connects to.

Roles: metadata + controller always (track info, art URL, group transport commands). The **player** role (actually
receiving audio) is only declared when an `audio_sink` is supplied, because the audio worker and mixer (spec 05 / M7.4)
do not exist yet: without a sink we are a display and remote control for the group, not an audio target.

Built on `aiosendspin.client.SendspinClient`; the connection handling follows the reference `sendspin daemon`.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Callable, Protocol

from .base import (Availability, Capabilities, Metadata, Pairing, Playback, Position, SessionEnded, SessionStarted,
                   SourceAdapter, Volume)

log = logging.getLogger(__name__)

PORT = 8928


class AudioSink(Protocol):
    """Where decoded-or-PCM audio goes once the mixer exists. `write` gets the server timestamp (us) the chunk should
    play at; `clear` drops everything buffered (stream end, seek, eviction)."""
    def write(self, server_timestamp_us: int, data: bytes, fmt: Any) -> None: ...
    def clear(self) -> None: ...
    # optional: set_volume(level: int, muted: bool), the device master level


class SendspinSource(SourceAdapter):
    id = "sendspin"
    label = "Sendspin"

    def __init__(
        self,
        name: str,
        state_dir: Path,
        *,
        port: int = PORT,
        audio_sink: AudioSink | None = None,
        output_delay_ms: float = 0.0,
        allow_unpaired: bool = True,
        client_factory: Callable[..., Any] | None = None,
        listener_factory: Callable[..., Any] | None = None,
    ) -> None:
        super().__init__()
        self.name = name
        self.state_dir = Path(state_dir)
        self.port = port
        self.audio_sink = audio_sink
        self.output_delay_ms = output_delay_ms
        self.allow_unpaired = allow_unpaired
        self.client_id = ""             # our Sendspin peer id, known once started (Music Assistant keys its player by it)
        self._client_factory = client_factory
        self._listener_factory = listener_factory
        self._client: Any = None
        self._listener: Any = None
        self._unsubscribe: list[Callable[[], None]] = []
        self._session = False
        self._volume, self._muted = 60, False

    # ---- lifecycle ----------------------------------------------------------------------------

    async def start(self) -> None:
        try:
            identity, store = await self._load_identity()
            self._client = (self._client_factory or self._make_client)(identity, store)
            self._attach(self._client)
            if self.allow_unpaired:
                # Offer "guest" access. Music Assistant never starts pairing by itself; it only auto-approves a client that
                # offers this, so without it the player has to be set up by hand in Music Assistant first.
                await self._client.set_unpaired_access(enabled=True)
            self.client_id = identity.peer_id
            self._listener = (self._listener_factory or self._make_listener)(identity.peer_id)
            await self._listener.start()
        except Exception:
            log.exception("sendspin: could not start")
            self.emit(Availability(False))
            return
        log.info("sendspin: listening on port %s as %r (mDNS _sendspin._tcp)", self.port, self.name)
        self.emit(Availability(True))

    async def stop(self) -> None:
        for unsub in self._unsubscribe:
            with contextlib.suppress(Exception):
                unsub()
        self._unsubscribe = []
        if self._client is not None:
            with contextlib.suppress(Exception):
                await self._client.disconnect()
        if self._listener is not None:
            with contextlib.suppress(Exception):
                await self._listener.stop()
        self._client = self._listener = None
        if self.audio_sink is not None and hasattr(self.audio_sink, "stop"):
            with contextlib.suppress(Exception):
                self.audio_sink.stop()

    async def _load_identity(self) -> tuple[Any, Any]:
        """A stable keypair (so Music Assistant recognises us after a restart) and the pairing records, next to the config."""
        from aiosendspin.noise import FileClientPairingStore, Identity, b64url_decode, b64url_encode
        path = self.state_dir / "sendspin_identity.json"
        identity = None
        with contextlib.suppress(OSError, ValueError, KeyError):
            identity = Identity.from_private_bytes(b64url_decode(json.loads(path.read_text())["private_key"]))
        if identity is None:
            identity = Identity.generate()
            try:
                self.state_dir.mkdir(parents=True, exist_ok=True)
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, "w") as f:
                    json.dump({"private_key": b64url_encode(identity.private_bytes)}, f)
            except OSError:
                log.warning("sendspin: could not save the identity to %s; pairing will be lost on restart", path)
        return identity, await FileClientPairingStore.open(self.state_dir / "sendspin_pairing.json")

    def _make_client(self, identity: Any, store: Any) -> Any:
        from aiosendspin.client import PairingSupport, SendspinClient
        from aiosendspin.models.core import DeviceInfo
        from aiosendspin.models.player import ClientHelloPlayerSupport, SupportedAudioFormat
        from aiosendspin.models.types import AudioCodec, PlayerCommand, Roles

        roles = [Roles.METADATA, Roles.CONTROLLER]
        extra: dict[str, Any] = {}
        if self.audio_sink is not None:
            roles.append(Roles.PLAYER)
            extra = dict(
                player_support=ClientHelloPlayerSupport(
                    supported_formats=[SupportedAudioFormat(codec=AudioCodec.PCM, channels=2, sample_rate=48000, bit_depth=16)],
                    buffer_capacity=32_000_000),
                state_supported_commands=[PlayerCommand.VOLUME, PlayerCommand.MUTE],
                initial_volume=self._volume, initial_muted=self._muted,
                output_delay_ms=self.output_delay_ms)
        return SendspinClient(
            identity=identity, client_name=self.name, roles=roles, pairing_store=store,
            pairing_support=PairingSupport(pairing_code_display=self._show_pairing_code, offer_static_pairing_code=True),
            device_info=DeviceInfo(product_name="havenOS display", manufacturer="havenOS"), **extra)

    def _make_listener(self, client_id: str) -> Any:
        from aiosendspin.client import ClientListener
        return ClientListener(client_id=client_id, on_connection=self._on_connection, port=self.port, client_name=self.name)

    async def _show_pairing_code(self, pairing_code: str | None, *, grouped: str | None) -> None:
        self.emit(Pairing(grouped))

    # ---- client -> coordinator ----------------------------------------------------------------

    def _attach(self, client: Any) -> None:
        self._unsubscribe = [
            client.add_metadata_listener(self._on_metadata),
            client.add_controller_state_listener(self._on_controller),
            client.add_group_update_listener(self._on_group),
            client.add_disconnect_listener(self._end_session),
        ]
        if self.audio_sink is not None:
            sink = self.audio_sink
            self._unsubscribe += [
                client.add_audio_chunk_listener(lambda ts, data, fmt, _ahead: sink.write(ts, data, fmt) if self.feed_on else None),
                client.add_stream_end_listener(lambda _roles: sink.clear()),
                client.add_stream_clear_listener(lambda _roles: sink.clear()),
                client.add_server_command_listener(self._on_server_command),
            ]

    async def _on_connection(self, ws: Any) -> None:
        """A Sendspin server dialled us. `attach_websocket` blocks while the connection is admitted, so follow it until
        the client shows a new server (admitted) or the attempt ends (rejected / failed)."""
        client = self._client
        previous = client.server_info
        attach = asyncio.ensure_future(client.attach_websocket(ws))
        while not attach.done():
            current = client.server_info
            if current is not None and current is not previous:
                break
            await asyncio.sleep(0.01)
        else:
            if attach.exception():
                log.warning("sendspin: handshake failed: %s", attach.exception())
            return
        self._session = True
        self.emit(SessionStarted(current.name))
        try:
            await attach
        except Exception:
            log.exception("sendspin: connection error")
        finally:
            self._end_session()

    def _end_session(self) -> None:
        if self._session:
            self._session = False
            if self.audio_sink is not None:
                self.audio_sink.clear()
            self.emit(SessionEnded())

    def _on_metadata(self, payload: Any) -> None:
        from aiosendspin.models.metadata import SessionUpdateMetadata
        meta = getattr(payload, "metadata", None)
        if not isinstance(meta, SessionUpdateMetadata):
            return
        prog = meta.progress
        self.emit(Metadata(title=meta.title or "", artist=meta.artist or meta.album_artist or "", album=meta.album or "",
                           art_uri=meta.artwork_url or "",
                           duration=(prog.track_duration / 1000.0) if prog and prog.track_duration else None))
        if prog is not None:
            pos = self._client.current_track_position() if self._client else None
            self.emit(Position((pos if pos is not None else prog.track_progress) / 1000.0))

    def _on_controller(self, payload: Any) -> None:
        from aiosendspin.models.controller import ControllerStatePayload
        from aiosendspin.models.types import MediaCommand
        ctl = getattr(payload, "controller", None)
        if not isinstance(ctl, ControllerStatePayload):
            return
        names = {MediaCommand.PLAY: "play", MediaCommand.PAUSE: "pause", MediaCommand.NEXT: "next",
                 MediaCommand.PREVIOUS: "prev", MediaCommand.SEEK: "seek"}
        self.emit(Capabilities(frozenset(names[c] for c in ctl.supported_commands if c in names)))

    def _on_group(self, payload: Any) -> None:
        state = getattr(payload, "playback_state", None)
        if state is not None:
            self.emit(Playback({"playing": "playing", "paused": "paused", "stopped": "stopped"}.get(state.value, "stopped")))

    def _on_server_command(self, payload: Any) -> None:
        """The server set this player's volume / mute (Music Assistant's slider): becomes the device master."""
        from aiosendspin.models.types import PlayerCommand
        cmd = getattr(payload, "player", None)
        if cmd is None:
            return
        if cmd.command == PlayerCommand.VOLUME and cmd.volume is not None:
            self._volume = int(cmd.volume)
        elif cmd.command == PlayerCommand.MUTE and cmd.mute is not None:
            self._muted = bool(cmd.mute)
        else:
            return
        self._sink_volume()
        self.emit(Volume(self._volume, self._muted))

    def _sink_volume(self) -> None:
        if self.audio_sink is not None and hasattr(self.audio_sink, "set_volume"):
            self.audio_sink.set_volume(self._volume, self._muted)

    # ---- coordinator -> client ----------------------------------------------------------------

    async def command(self, name: str, **args: Any) -> None:
        from aiosendspin.models.types import MediaCommand
        media = {"play": MediaCommand.PLAY, "pause": MediaCommand.PAUSE, "next": MediaCommand.NEXT,
                 "prev": MediaCommand.PREVIOUS}
        try:
            if name == "seek":
                await self._client.send_group_command(MediaCommand.SEEK, position_ms=int(float(args["seconds"]) * 1000))
            elif name in media:
                await self._client.send_group_command(media[name])
        except (ValueError, RuntimeError) as e:     # unsupported right now, or not connected
            log.warning("sendspin: %s refused: %s", name, e)

    async def release(self) -> None:
        """Evicted: leave the group (our room goes quiet; other rooms in the group keep playing) rather than pausing it."""
        if self.audio_sink is not None:
            self.audio_sink.clear()
        if self._client is None:
            return
        try:
            await self._client.send_leave()
        except Exception as e:
            log.warning("sendspin: could not leave the group (%s); the audio feed is already deselected", e)

    async def set_volume(self, level: int, muted: bool) -> None:
        self._volume, self._muted = level, muted
        self._sink_volume()
        if self.audio_sink is not None and self._client is not None:
            with contextlib.suppress(Exception):
                await self._client.send_player_state(available=True, volume=level, muted=muted)
