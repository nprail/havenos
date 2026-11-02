"""Simulated Assist round-trip (listening -> transcript -> thinking -> reply). Replaced by real Assist in M4."""
from __future__ import annotations

from typing import Awaitable, Callable

Sleep = Callable[[float], Awaitable[None]]
Patch = Callable[..., None]

WORDS = ["turn", "turn on", "turn on the", "turn on the kitchen", "turn on the kitchen lights"]
REPLY = "Okay, turning on the kitchen lights."


async def simulate_assist(patch: Patch, sleep: Sleep) -> None:
    patch(voice="listening", transcript="", response="")
    await sleep(0.42)
    for w in WORDS:
        patch(transcript=w)
        await sleep(0.42 if w != WORDS[-1] else 0.5)
    patch(voice="processing")
    await sleep(1.2)
    patch(voice="responding", response=REPLY)
    await sleep(2.6)
    patch(voice="idle")
