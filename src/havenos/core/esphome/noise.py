"""ESPHome Noise encryption, server side (Noise_NNpsk0_25519_ChaChaPoly_SHA256).

The wire format matches what aioesphomeapi's client (and so Home Assistant) speaks:

    frame     = 0x01, length (2 bytes, big endian), payload
    hello     = client sends an empty frame; server answers 0x01 + name + 0x00 (the protocol it chose, then its name)
    handshake = client frame 0x00 + Noise message; server answers 0x00 + Noise message, or 0x01 + "Handshake MAC failure"
    data      = encrypt(type (2 bytes), length (2 bytes), protobuf payload), framed as above

The pre-shared key is 32 bytes (base64 in config and in Home Assistant's "encryption key" field). We leave the MAC out of
the hello (an extension from 2025.4): Home Assistant compares it against the one it stored, and a format mismatch would
lock a working device out.
"""
from __future__ import annotations

import base64
import binascii
import os
from typing import Iterable

from cryptography.exceptions import InvalidTag
from google.protobuf import message
from noise.connection import NoiseConnection

from .framing import PROTO_TO_TYPE, FrameError

PROTOCOL_NAME = b"Noise_NNpsk0_25519_ChaChaPoly_SHA256"
PROLOGUE = b"NoiseAPIInit\x00\x00"
MAX_FRAME = 1 << 16


def generate_key() -> str:
    """A new random key, base64, ready to paste into Home Assistant and config.toml."""
    return base64.b64encode(os.urandom(32)).decode()


def decode_key(key: str) -> bytes:
    try:
        raw = base64.b64decode(key.strip(), validate=True)
    except (binascii.Error, ValueError) as e:
        raise ValueError("the ESPHome encryption key is not valid base64") from e
    if len(raw) != 32:
        raise ValueError(f"the ESPHome encryption key must decode to 32 bytes (got {len(raw)})")
    return raw


def _frame(payload: bytes) -> bytes:
    return b"\x01" + len(payload).to_bytes(2, "big") + payload


class HandshakeError(FrameError):
    """The client's handshake failed; `reply` is what to send back before hanging up."""

    def __init__(self, text: str, reply: bytes = b"") -> None:
        super().__init__(text)
        self.reply = reply


class NoiseFramer:
    """Same shape as `framing.PlainFramer`: `feed()` returns (bytes to send back, decoded messages), `encode()` the reverse."""

    def __init__(self, psk: bytes, name: str) -> None:
        self._psk, self._name = psk, name
        self._buf = bytearray()
        self._state = "hello"
        self._proto: NoiseConnection | None = None

    @property
    def ready(self) -> bool:
        return self._state == "ready"

    def encode(self, msgs: Iterable[message.Message]) -> bytes:
        if not self.ready:
            raise RuntimeError("the Noise handshake is not finished")
        out = []
        for m in msgs:
            payload = m.SerializeToString()
            header = PROTO_TO_TYPE[type(m)].to_bytes(2, "big") + len(payload).to_bytes(2, "big")
            out.append(_frame(self._proto.encrypt(header + payload)))
        return b"".join(out)

    def feed(self, data: bytes) -> tuple[bytes, list[tuple[int, bytes]]]:
        self._buf += data
        reply, packets = b"", []
        while len(self._buf) >= 3:
            if self._buf[0] != 0x01:
                raise FrameError("bad preamble (is the client using plain text?)" if self._buf[0] == 0x00 else
                                 f"bad preamble {self._buf[0]}")
            n = int.from_bytes(self._buf[1:3], "big")
            if n > MAX_FRAME:
                raise FrameError(f"frame too large: {n}")
            if len(self._buf) < 3 + n:
                break
            frame = bytes(self._buf[3:3 + n])
            del self._buf[:3 + n]
            if self._state == "hello":
                reply += self._hello()
            elif self._state == "handshake":
                try:
                    reply += self._handshake(frame)
                except HandshakeError as e:
                    e.reply = reply + e.reply               # the client sends hello and handshake together; answer both
                    raise
            else:
                packets.append(self._decrypt(frame))
        return reply, packets

    def _hello(self) -> bytes:
        self._state = "handshake"
        return _frame(b"\x01" + self._name.encode() + b"\x00")

    def _handshake(self, frame: bytes) -> bytes:
        if not frame or frame[0] != 0:
            raise HandshakeError("handshake frame has the wrong preamble", _frame(b"\x01Bad handshake preamble"))
        proto = NoiseConnection.from_name(PROTOCOL_NAME)
        proto.set_as_responder()
        proto.set_psks(self._psk)
        proto.set_prologue(PROLOGUE)
        proto.start_handshake()
        try:
            proto.read_message(frame[1:])
            answer = proto.write_message()
        except (InvalidTag, Exception) as e:                     # a wrong key fails the AEAD check on the first message
            raise HandshakeError(f"handshake failed ({type(e).__name__}): wrong encryption key?",
                                 _frame(b"\x01Handshake MAC failure")) from e
        if not proto.handshake_finished:
            raise HandshakeError("handshake did not finish", _frame(b"\x01Handshake failure"))
        self._proto, self._state = proto, "ready"
        return _frame(b"\x00" + answer)

    def _decrypt(self, frame: bytes) -> tuple[int, bytes]:
        try:
            plain = self._proto.decrypt(frame)
        except InvalidTag as e:
            raise FrameError("encrypted frame failed authentication") from e
        if len(plain) < 4:
            raise FrameError("decrypted frame too short")
        return int.from_bytes(plain[:2], "big"), plain[4:]


if __name__ == "__main__":          # python -m havenos.core.esphome.noise: print a new key for [esphome] key = "..."
    print(generate_key())
