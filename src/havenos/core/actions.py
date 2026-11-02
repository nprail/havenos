"""The only things a touch on a room screen may ask Home Assistant to do.

An allowlist, not a pass-through: each (domain, action) maps to one fixed service, arguments are range-checked, and
the caller (HomeIntegration) has already confirmed the entity is exposed to Assist. Nothing here lets the UI (or
anything that can reach the core's command interface) call an arbitrary service.
"""
from __future__ import annotations

from typing import Any


class ActionError(ValueError):
    pass


def _pct(v: Any, field: str, lo: int = 0, hi: int = 100) -> int:
    try:
        n = round(float(v))
    except (TypeError, ValueError):
        raise ActionError(f"{field} must be a number")
    if not lo <= n <= hi:
        raise ActionError(f"{field} must be between {lo} and {hi}")
    return n


def _temp(v: Any, field: str = "temperature") -> float:
    try:
        n = float(v)
    except (TypeError, ValueError):
        raise ActionError(f"{field} must be a number")
    if not 0 <= n <= 120:                      # covers both °C and °F ranges; HA clamps to the device's own limits
        raise ActionError(f"{field} out of range")
    return n


def plan(state: dict, action: str, args: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    """Return (service domain, service, data) for an action on an entity, or raise ActionError."""
    domain = state["entity_id"].split(".", 1)[0]
    a = state.get("attributes", {})

    if domain in ("light", "switch", "fan", "input_boolean"):
        if action == "toggle":
            return domain, "toggle", {}
        if action in ("on", "off"):
            return domain, f"turn_{action}", {}
        if domain == "light" and action == "brightness":
            pct = _pct(args.get("percent"), "percent", 0, 100)
            return ("light", "turn_off", {}) if pct == 0 else ("light", "turn_on", {"brightness_pct": pct})
        if domain == "fan" and action == "percentage":
            pct = _pct(args.get("percent"), "percent")
            return ("fan", "turn_off", {}) if pct == 0 else ("fan", "set_percentage", {"percentage": pct})

    elif domain == "cover":
        if action in ("open", "close", "stop"):
            return "cover", f"{action}_cover", {}
        if action == "toggle":
            return "cover", "toggle", {}
        if action == "position":
            return "cover", "set_cover_position", {"position": _pct(args.get("percent"), "percent")}

    elif domain == "climate":
        if action == "temperature":
            return "climate", "set_temperature", {"temperature": _temp(args.get("temperature"))}
        if action == "range":
            low, high = _temp(args.get("low"), "low"), _temp(args.get("high"), "high")
            if low > high:
                raise ActionError("low must not be above high")
            return "climate", "set_temperature", {"target_temp_low": low, "target_temp_high": high}
        if action == "hvac_mode":
            mode = str(args.get("mode", ""))
            if mode not in (a.get("hvac_modes") or []):
                raise ActionError("unsupported hvac mode")
            return "climate", "set_hvac_mode", {"hvac_mode": mode}

    elif domain == "media_player":
        simple = {"playpause": "media_play_pause", "next": "media_next_track", "prev": "media_previous_track"}
        if action in simple:
            return "media_player", simple[action], {}
        if action == "volume":
            return "media_player", "volume_set", {"volume_level": _pct(args.get("percent"), "percent") / 100}

    elif domain == "lock":
        if action == "lock":
            return "lock", "lock", {}
        if action == "unlock":
            if not args.get("confirmed"):          # the UI asks the person first; this is the backstop
                raise ActionError("unlocking needs confirmation")
            return "lock", "unlock", {}

    elif domain in ("scene", "script"):
        if action == "run":
            return domain, "turn_on", {}

    elif domain == "vacuum":
        svc = {"start": "start", "pause": "pause", "dock": "return_to_base"}
        if action in svc:
            return "vacuum", svc[action], {}

    raise ActionError(f"{action!r} is not allowed on {domain}")
