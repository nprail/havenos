"""ESPHome plaintext frame format: 0x00, varuint(payload length), varuint(message type), payload."""
from __future__ import annotations

from aioesphomeapi.core import MESSAGE_TYPE_TO_PROTO
from google.protobuf import message

PROTO_TO_TYPE = {cls: type_id for type_id, cls in MESSAGE_TYPE_TO_PROTO.items()}
MAX_FRAME = 1 << 20          # 1 MiB: far above any real message (voice audio chunks are ~1 KiB)


def varuint(n: int) -> bytes:
    out = bytearray()
    while True:
        byte = n & 0x7F
        n >>= 7
        if n:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def encode(msg: message.Message) -> bytes:
    payload = msg.SerializeToString()
    return b"\x00" + varuint(len(payload)) + varuint(PROTO_TO_TYPE[type(msg)]) + payload


def encode_many(msgs) -> bytes:
    return b"".join(encode(m) for m in msgs)


class FrameError(Exception):
    pass


class PlainFramer:
    """Plain-text counterpart of noise.NoiseFramer: nothing to send back while decoding, no handshake."""

    ready = True

    def __init__(self) -> None:
        self._decoder = Decoder()

    def feed(self, data: bytes) -> tuple[bytes, list[tuple[int, bytes]]]:
        return b"", self._decoder.feed(data)

    def encode(self, msgs) -> bytes:
        return encode_many(msgs)


class Decoder:
    """Incremental decoder: feed() bytes, get back complete (type_id, payload) frames."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[tuple[int, bytes]]:
        self._buf += data
        frames: list[tuple[int, bytes]] = []
        while True:
            pos = 0
            if len(self._buf) < 3:
                break
            if self._buf[0] != 0:
                raise FrameError("bad preamble (is the client using Noise encryption?)")
            pos = 1
            length, pos = self._varuint(pos)
            if length is None:
                break
            mtype, pos = self._varuint(pos)
            if mtype is None:
                break
            if length > MAX_FRAME:
                raise FrameError(f"frame too large: {length}")
            if len(self._buf) < pos + length:
                break
            frames.append((mtype, bytes(self._buf[pos:pos + length])))
            del self._buf[:pos + length]
        return frames

    def _varuint(self, pos: int) -> tuple[int | None, int]:
        result = shift = 0
        while pos < len(self._buf):
            byte = self._buf[pos]
            pos += 1
            result |= (byte & 0x7F) << shift
            if not byte & 0x80:
                return result, pos
            shift += 7
            if shift > 63:
                raise FrameError("varuint too long")
        return None, pos
