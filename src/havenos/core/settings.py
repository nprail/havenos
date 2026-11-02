"""Reading, validating and writing the user's settings (config.toml + secret files).

The web UI is the editor; this module is the only thing that touches the files. Secrets (HA token, Immich
API key) go in their own 0600 files and are never written into config.toml or returned to a client.
"""
from __future__ import annotations

import copy
import os
import re
import shutil
import tempfile
import tomllib
from pathlib import Path
from typing import Any

import tomli_w

ICONS = ("bulb", "thermo", "camera", "scenes", "gear")
MAX_CONTROLS = 6


class SettingsError(ValueError):
    """Invalid input. `errors` maps a dotted field name to a message the UI can show next to that field."""

    def __init__(self, errors: dict[str, str]) -> None:
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))
        self.errors = errors


# ---- files ------------------------------------------------------------------------------------

def read_toml(path: Path) -> dict:
    return tomllib.loads(path.read_text()) if path.exists() else {}


def _atomic_write(path: Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def write_toml(path: Path, data: dict) -> None:
    if path.exists():
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))      # comments are not preserved; keep the old file
    _atomic_write(path, tomli_w.dumps(data).encode(), 0o600)


def secret_path(toml: dict, table: str, key: str, default: Path) -> Path:
    f = toml.get(table, {}).get(key + "_file")
    return Path(f).expanduser() if f else default


def write_secret(path: Path, value: str) -> None:
    _atomic_write(path, value.strip().encode() + b"\n", 0o600)


# ---- public view ------------------------------------------------------------------------------

def defaults() -> dict:
    return {
        "homeassistant": {"url": "", "weather": "", "media_player": "", "controls": [], "room": "", "persistent_notifications": False},
        "photos": {"source": "nasa", "dir": "",
                   "immich": {"url": "", "album": "", "shuffle": True, "recency_half_life_days": 365.0,
                              "recency_floor": 0.1, "list_size": 120}},
        "display": {"photo_interval_s": 8.0, "idle_s": 30.0, "crossfade_ms": 1500, "brightness": 100, "blur": True},
        "esphome": {"enabled": False, "name": "", "port": 6053},
        "notifications": {"announcement_seconds": 20},
        "music": {"idle_s": 600.0, "hint": False, "duck_db": -20.0, "audio_device": "",
                  "assistant": {"url": "", "player_id": ""},
                  "sendspin": {"enabled": False, "name": ""}, "airplay": {"enabled": False, "name": ""},
                  "spotify": {"enabled": False, "name": ""}},
    }


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else copy.deepcopy(v)
    return out


def setup_done(toml: dict) -> bool:
    """First-run setup counts as done once the wizard finished, or Home Assistant was configured by hand."""
    return bool(toml.get("setup", {}).get("done")) or bool(toml.get("homeassistant", {}).get("url"))


def public_view(toml: dict, secrets_set: dict[str, bool], env_overrides: list[str]) -> dict:
    """What the UI may see: settings with defaults filled in, and only *whether* each secret is set."""
    view = _merge(defaults(), {k: toml.get(k, {}) for k in ("homeassistant", "photos", "display", "esphome", "notifications", "music")})
    view["secrets"] = {"ha_token_set": secrets_set.get("ha_token", False),
                       "immich_key_set": secrets_set.get("immich_key", False),
                       "ma_token_set": secrets_set.get("ma_token", False)}
    view["setup"] = {"done": setup_done(toml)}
    view["env_overrides"] = env_overrides
    return view


# ---- validation + merge -----------------------------------------------------------------------

def _num(v: Any, lo: float, hi: float, field: str, errors: dict, integer: bool = False) -> float | int | None:
    try:
        n = float(v)
    except (TypeError, ValueError):
        errors[field] = "must be a number"
        return None
    if not lo <= n <= hi:
        errors[field] = f"must be between {lo:g} and {hi:g}"
        return None
    return int(n) if integer else n


def _url(v: Any, field: str, errors: dict, required: bool = False) -> str:
    v = (v or "").strip().rstrip("/")
    if not v:
        if required:
            errors[field] = "required"
        return ""
    if not (v.startswith("http://") or v.startswith("https://")) or " " in v or len(v) < 10:
        errors[field] = "must be a full http:// or https:// URL"
    return v


def apply_update(existing: dict, update: dict) -> dict:
    """Validate `update` (the editable subset of the public view) and return the new TOML dict.
    Unknown keys in `existing` (e.g. token_file paths, [web]) are preserved."""
    errors: dict[str, str] = {}
    new = copy.deepcopy(existing)

    se_u = update.get("setup")
    if se_u is not None and "done" in se_u:
        new.setdefault("setup", {})["done"] = bool(se_u["done"])

    ha_u = update.get("homeassistant")
    if ha_u is not None:
        ha = new.setdefault("homeassistant", {})
        url = _url(ha_u.get("url"), "homeassistant.url", errors)
        ha["url"] = url
        for key in ("weather", "media_player"):
            v = (ha_u.get(key) or "").strip()
            if v and "." not in v:
                errors[f"homeassistant.{key}"] = "must be an entity id like weather.home"
            ha[key] = v
        room = (ha_u.get("room") or "").strip()
        ha["room"] = room
        ha["persistent_notifications"] = bool(ha_u.get("persistent_notifications"))
        controls = ha_u.get("controls") or []
        if len(controls) > MAX_CONTROLS:
            errors["homeassistant.controls"] = f"at most {MAX_CONTROLS} tiles"
        clean = []
        for i, c in enumerate(controls[:MAX_CONTROLS]):
            ent = (c.get("entity") or "").strip()
            if "." not in ent:
                errors[f"homeassistant.controls.{i}"] = "entity must look like light.kitchen"
                continue
            row: dict[str, Any] = {"entity": ent}
            if (c.get("label") or "").strip():
                row["label"] = c["label"].strip()[:24]
            if c.get("icon"):
                if c["icon"] not in ICONS:
                    errors[f"homeassistant.controls.{i}"] = "unknown icon"
                else:
                    row["icon"] = c["icon"]
            clean.append(row)
        ha["controls"] = clean
        for k in [k for k, v in ha.items() if v in ("", [], None, False)]:
            del ha[k]            # keep the file tidy: absent == unset

    ph_u = update.get("photos")
    if ph_u is not None:
        ph = new.setdefault("photos", {})
        if ph_u.get("source") not in ("nasa", "local", "immich"):
            errors["photos.source"] = "must be nasa, local or immich"
        else:
            ph["source"] = ph_u["source"]
        d = (ph_u.get("dir") or "").strip()
        if d:
            if ph_u.get("source") == "local" and not Path(d).expanduser().is_dir():
                errors["photos.dir"] = "that folder does not exist on the device"
            ph["dir"] = d
        else:
            ph.pop("dir", None)
        im_u = ph_u.get("immich")
        if im_u is not None:
            im = ph.setdefault("immich", {})
            im["url"] = _url(im_u.get("url"), "photos.immich.url", errors)
            album = (im_u.get("album") or "").strip()
            if album:
                im["album"] = album
            else:
                im.pop("album", None)
            im["shuffle"] = bool(im_u.get("shuffle", True))
            for key, lo, hi, integer in (("recency_half_life_days", 0, 3650, False), ("recency_floor", 0.01, 1, False),
                                         ("list_size", 10, 500, True)):
                if key in im_u:
                    n = _num(im_u[key], lo, hi, f"photos.immich.{key}", errors, integer)
                    if n is not None:
                        im[key] = n
            if not im["url"]:
                im.pop("url")

    di_u = update.get("display")
    if di_u is not None:
        di = new.setdefault("display", {})
        for key, lo, hi, integer in (("photo_interval_s", 2, 3600, False), ("idle_s", 5, 3600, False),
                                     ("crossfade_ms", 0, 5000, True), ("brightness", 10, 100, True)):
            if key in di_u:
                n = _num(di_u[key], lo, hi, f"display.{key}", errors, integer)
                if n is not None:
                    di[key] = n
        if "blur" in di_u:
            di["blur"] = bool(di_u["blur"])

    no_u = update.get("notifications")
    if no_u is not None and "announcement_seconds" in no_u:
        n = _num(no_u["announcement_seconds"], 3, 600, "notifications.announcement_seconds", errors)
        if n is not None:
            new.setdefault("notifications", {})["announcement_seconds"] = n

    es_u = update.get("esphome")
    if es_u is not None:
        es = new.setdefault("esphome", {})
        es["enabled"] = bool(es_u.get("enabled"))
        name = (es_u.get("name") or "").strip().lower()
        if name and not re.fullmatch(r"[a-z0-9]([a-z0-9-]{0,29}[a-z0-9])?", name):
            errors["esphome.name"] = "lowercase letters, digits and dashes only (max 31)"
        elif name:
            es["name"] = name
        else:
            es.pop("name", None)
        if "port" in es_u:
            n = _num(es_u["port"], 1024, 65535, "esphome.port", errors, True)
            if n is not None:
                es["port"] = n

    mu_u = update.get("music")
    if mu_u is not None:
        mu = new.setdefault("music", {})
        for key, lo, hi in (("idle_s", 10, 86400), ("duck_db", -60, 0)):
            if key in mu_u:
                n = _num(mu_u[key], lo, hi, f"music.{key}", errors)
                if n is not None:
                    mu[key] = n
        if "hint" in mu_u:
            mu["hint"] = bool(mu_u["hint"])
        if "audio_device" in mu_u:
            dev = (mu_u["audio_device"] or "").strip() if isinstance(mu_u["audio_device"], str) else ""
            if len(dev) > 120:
                errors["music.audio_device"] = "at most 120 characters"
            elif dev:
                mu["audio_device"] = dev
            else:
                mu.pop("audio_device", None)          # absent == the system default
        ma_u = mu_u.get("assistant")
        if ma_u is not None:
            ma = mu.setdefault("assistant", {})
            ma["url"] = _url(ma_u.get("url"), "music.assistant.url", errors)
            pid = (ma_u.get("player_id") or "").strip()
            ma["player_id"] = pid
            for k in [k for k, v in ma.items() if v == ""]:
                del ma[k]
        for src in ("sendspin", "airplay", "spotify"):
            su = mu_u.get(src)
            if su is None:
                continue
            row = mu.setdefault(src, {})
            row["enabled"] = bool(su.get("enabled"))
            name = (su.get("name") or "").strip()
            if len(name) > 40:
                errors[f"music.{src}.name"] = "at most 40 characters"
            elif name:
                row["name"] = name
            else:
                row.pop("name", None)

    if (new.get("photos", {}).get("source") == "immich") and not new.get("photos", {}).get("immich", {}).get("url"):
        errors.setdefault("photos.immich.url", "required when the photo source is Immich")
    if errors:
        raise SettingsError(errors)
    return new
