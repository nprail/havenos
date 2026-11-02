"""Settings web UI: a small authenticated JSON API plus a static page (Tailwind, prebuilt, no CDN).

Security model, because this edits API keys on a device that sits on a home network:
  - Access needs a setup code that is shown only on the device (the pairing screen with its QR code, and the stats HUD) and in its log/file. No code, no entry.
  - A correct code yields a random session cookie (HttpOnly, SameSite=Strict, 12 h). Failures are rate-limited per IP.
  - State-changing calls must carry `X-Requested-With: havenos` (CSRF defence in depth).
  - Secrets are write-only: the API reports whether a secret is set, never its value.
  - Plain HTTP. Fine on a trusted LAN; put it behind a TLS reverse proxy (or bind to 127.0.0.1) otherwise.
"""
from __future__ import annotations

import asyncio
import hmac
import logging
import os
import secrets
import socket
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

from aiohttp import web

from . import settings as st
from .config import Config, ImmichConfig
from .core import Core
from .ha import HAError, probe as ha_probe
from .immich import ImmichError, ImmichSource

log = logging.getLogger(__name__)

SESSION_COOKIE = "havenos_session"
SESSION_TTL_S = 12 * 3600
MAX_FAILS, LOCKOUT_S = 5, 60
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"       # no 0/O/1/I
ENTITY_DOMAINS = ("weather", "media_player", "light", "switch", "fan", "cover", "lock", "scene", "script",
                  "climate", "alarm_control_panel", "input_boolean")


def new_code() -> str:
    c = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
    return f"{c[:4]}-{c[4:]}"


def lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))          # no packet is sent; this just picks the outbound interface
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


class WebUI:
    def __init__(self, core: Core, assets: Path, *, clock: Callable[[], float] = time.monotonic,
                 esphome: Any = None) -> None:
        self.core = core
        self.esphome = esphome                  # the running ESPHomeDevice, if enabled (for status only)
        self.assets = assets
        self._clock = clock
        self._static = Path(__file__).resolve().parent.parent / "web"
        self._sessions: dict[str, float] = {}
        self._fails: dict[str, list[float]] = {}
        self._runner: web.AppRunner | None = None
        self.port = 0
        self.code = ""

    # ---- paths ----------------------------------------------------------------------------

    @property
    def _cfg_path(self) -> Path:
        return self.core.config.config_path

    @property
    def _dir(self) -> Path:
        return self._cfg_path.parent

    # ---- lifecycle ------------------------------------------------------------------------

    def _load_code(self) -> str:
        f = self._dir / "web_code"
        if f.exists() and f.read_text().strip():
            return f.read_text().strip()
        return self._write_code()

    def _write_code(self) -> str:
        code = new_code()
        st.write_secret(self._dir / "web_code", code)
        return code

    async def start(self) -> bool:
        cfg = self.core.config
        self.code = self._load_code()
        app = web.Application(middlewares=[self._guard], client_max_size=64 * 1024)
        r = app.router
        r.add_get("/", self._index)
        r.add_static("/static/", self._static, show_index=False)
        r.add_get("/api/session", self._session)
        r.add_post("/api/login", self._login)
        r.add_post("/api/logout", self._logout)
        r.add_get("/api/config", self._get_config)
        r.add_put("/api/config", self._put_config)
        r.add_get("/api/status", self._status)
        r.add_post("/api/test/ha", self._test_ha)
        r.add_post("/api/test/immich", self._test_immich)
        r.add_post("/api/test/ma", self._test_ma)
        r.add_get("/api/audio/devices", self._audio_devices)
        r.add_post("/api/test/audio", self._test_audio)
        r.add_post("/api/rotate-code", self._rotate)
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        try:
            site = web.TCPSite(self._runner, cfg.web_host, cfg.web_port)
            await site.start()
        except OSError as e:
            log.error("settings web UI could not start on %s:%s (%s); continuing without it", cfg.web_host, cfg.web_port, e)
            await self._runner.cleanup()
            self._runner = None
            return False
        self.port = site._server.sockets[0].getsockname()[1]
        host = lan_ip() if cfg.web_host in ("0.0.0.0", "") else cfg.web_host
        self._publish(f"http://{host}:{self.port}")
        log.info("settings UI at http://%s:%s  (setup code: %s)", host, self.port, self.code)
        return True

    def _publish(self, url: str) -> None:
        """What the display shows to pair: the address, the code, and a QR code that opens the page already signed in."""
        from .qr import matrix
        link = f"{url}/?code={self.code}"
        self.core._set(web={"url": url, "code": self.code, "link": link, "qr": matrix(link)})

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()
            self._runner = None

    # ---- auth -----------------------------------------------------------------------------

    def _authed(self, request: web.Request) -> bool:
        tok = request.cookies.get(SESSION_COOKIE, "")
        exp = self._sessions.get(tok)
        if exp is None:
            return False
        if exp < self._clock():
            del self._sessions[tok]
            return False
        return True

    @web.middleware
    async def _guard(self, request: web.Request, handler):
        if request.path.startswith("/api/") and request.path not in ("/api/session", "/api/login"):
            if not self._authed(request):
                return _json({"error": "login required"}, 401)
        if request.method not in ("GET", "HEAD") and request.headers.get("X-Requested-With") != "havenos":
            return _json({"error": "missing X-Requested-With header"}, 403)
        resp = await handler(request)
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        return resp

    async def _session(self, request: web.Request) -> web.Response:
        return _json({"authenticated": self._authed(request)})

    async def _login(self, request: web.Request) -> web.Response:
        ip = request.remote or "?"
        now = self._clock()
        fails = [t for t in self._fails.get(ip, []) if now - t < LOCKOUT_S]
        self._fails[ip] = fails
        if len(fails) >= MAX_FAILS:
            return _json({"error": f"too many attempts; wait {LOCKOUT_S} seconds"}, 429)
        body = await _body(request)
        given = str(body.get("code", "")).strip().upper().replace(" ", "")
        if hmac.compare_digest(given.encode(), self.code.encode()):
            tok = secrets.token_urlsafe(32)
            self._sessions[tok] = now + SESSION_TTL_S
            self._fails.pop(ip, None)
            resp = _json({"ok": True})
            resp.set_cookie(SESSION_COOKIE, tok, max_age=SESSION_TTL_S, httponly=True, samesite="Strict", path="/")
            return resp
        fails.append(now)
        return _json({"error": "wrong code"}, 401)

    async def _logout(self, request: web.Request) -> web.Response:
        self._sessions.pop(request.cookies.get(SESSION_COOKIE, ""), None)
        resp = _json({"ok": True})
        resp.del_cookie(SESSION_COOKIE, path="/")
        return resp

    async def _rotate(self, request: web.Request) -> web.Response:
        self.code = self._write_code()
        self._sessions.clear()
        self._publish(self.core.state["web"]["url"] if self.core.state["web"] else "")
        return _json({"ok": True, "note": "new code is shown on the device"})

    # ---- pages ----------------------------------------------------------------------------

    async def _index(self, request: web.Request) -> web.Response:
        return web.FileResponse(self._static / "index.html")

    # ---- config ---------------------------------------------------------------------------

    def _view(self) -> dict:
        toml = st.read_toml(self._cfg_path)
        present = {
            "ha_token": _has_secret(toml, "homeassistant", "token", "HAVENOS_HA_TOKEN", self._dir / "ha_token"),
            "immich_key": _has_secret(toml, "photos.immich", "api_key", "HAVENOS_IMMICH_KEY", self._dir / "immich_key"),
            "ma_token": _has_secret(toml, "music.assistant", "token", "HAVENOS_MA_TOKEN", self._dir / "ma_token"),
        }
        env = [n for n in ("HAVENOS_HA_URL", "HAVENOS_HA_TOKEN", "HAVENOS_IMMICH_URL", "HAVENOS_IMMICH_KEY",
                           "HAVENOS_IMMICH_ALBUM", "HAVENOS_PHOTO_SOURCE", "HAVENOS_INTERVAL", "HAVENOS_IDLE",
                           "HAVENOS_BLUR", "HAVENOS_CROSSFADE", "HAVENOS_PHOTOS", "HAVENOS_AUDIO_DEVICE") if os.environ.get(n)]
        return st.public_view(toml, present, env)

    async def _get_config(self, request: web.Request) -> web.Response:
        return _json(self._view())

    async def _put_config(self, request: web.Request) -> web.Response:
        body = await _body(request)
        toml = st.read_toml(self._cfg_path)
        try:
            new = st.apply_update(toml, body)
        except st.SettingsError as e:
            return _json({"error": "invalid settings", "fields": e.errors}, 422)
        secrets_in = body.get("secrets") or {}
        self._store_secret(new, "homeassistant", "token", "ha_token", secrets_in.get("ha_token"),
                           bool(secrets_in.get("clear_ha_token")))
        self._store_secret(new, "photos.immich", "api_key", "immich_key", secrets_in.get("immich_api_key"),
                           bool(secrets_in.get("clear_immich_key")))
        self._store_secret(new, "music.assistant", "token", "ma_token", secrets_in.get("ma_token"),
                           bool(secrets_in.get("clear_ma_token")))
        # Compare what would actually run, with defaults filled in: writing a default for the first time is not a change.
        view = lambda t, key: st._merge(st.defaults()[key], t.get(key, {}))
        restart = any(view(toml, "esphome")[k] != view(new, "esphome")[k] for k in ("enabled", "name", "port"))     # bound at startup
        restart = restart or any((view(toml, "music")[src]["enabled"], view(toml, "music")[src]["name"])
                                 != (view(new, "music")[src]["enabled"], view(new, "music")[src]["name"])
                                 for src in ("sendspin", "airplay", "spotify"))                                     # so are the music sources
        st.write_toml(self._cfg_path, new)
        try:
            cfg = Config.from_env(self.assets)
            await self.core.apply_config(cfg)
        except Exception as e:
            log.exception("saved settings but applying them failed")
            return _json({"error": f"saved, but could not apply: {e}", "view": self._view()}, 500)
        return _json({"ok": True, "view": self._view(), "restart_required": restart})

    def _store_secret(self, root: dict, table: str, key: str, filename: str, value: str | None, clear: bool) -> None:
        """Write a secret to its own 0600 file and point the TOML at it. Blank means 'leave as is'."""
        tbl = _node(root, table, create=True)
        path = Path(tbl.get(key + "_file") or self._dir / filename).expanduser()
        if clear:
            path.unlink(missing_ok=True)
            tbl.pop(key, None)
            tbl.pop(key + "_file", None)
        elif value and value.strip():
            st.write_secret(path, value)
            tbl[key + "_file"] = str(path)
            tbl.pop(key, None)                    # migrate any inline secret out of config.toml

    async def _status(self, request: web.Request) -> web.Response:
        s = self.core.state
        return _json({"ha_status": s["ha_status"], "photo_source": s["photo_source"],
                      "photo": (s["photo"] or {}).get("name"), "mode": s["mode"],
                      "cached_photos": self.core._playlist.cached_count if self.core._playlist else 0,
                      "room": s["room"], "exposure": s["ha_exposure"],
                      "esphome": ({"running": True, "name": self.esphome.name, "port": self.esphome.port,
                                   "clients": len(self.esphome.server.connections)} if self.esphome else {"running": False})})

    # ---- connection tests (use stored secret when none typed) -----------------------------------

    def _stored(self, table: str, key: str, env: str, filename: str) -> str | None:
        """The secret currently in effect (env, inline, or file), for 'Test' when nothing new was typed."""
        if os.environ.get(env):
            return os.environ[env].strip()
        tbl = _node(st.read_toml(self._cfg_path), table)
        if tbl.get(key):
            return str(tbl[key]).strip()
        p = Path(tbl.get(key + "_file") or self._dir / filename).expanduser()
        return p.read_text().strip() if p.exists() else None

    async def _audio_devices(self, request: web.Request) -> web.Response:
        try:
            devices = await asyncio.get_running_loop().run_in_executor(None, self.core.audio_choices)
        except Exception as e:                      # no PortAudio, or no sound hardware at all
            return _json({"devices": [], "error": f"could not list sound outputs: {e}"})
        return _json({"devices": devices})

    async def _test_audio(self, request: web.Request) -> web.Response:
        try:
            self.core.audio_test()
        except Exception as e:
            return _json({"ok": False, "error": f"could not play: {e}"})
        return _json({"ok": True, "msg": "Playing a short chime on the current output."})

    async def _test_ha(self, request: web.Request) -> web.Response:
        body = await _body(request)
        url = (body.get("url") or "").strip()
        token = (body.get("token") or "").strip() or self._stored("homeassistant", "token", "HAVENOS_HA_TOKEN", "ha_token")
        if not url or not token:
            return _json({"ok": False, "error": "enter the URL and a token (or save one first)"})
        try:
            probe = await ha_probe(url, token)
        except HAError as e:
            return _json({"ok": False, "error": str(e)})
        except (OSError, asyncio.TimeoutError, Exception) as e:      # noqa: BLE001 - surface any network failure as text
            return _json({"ok": False, "error": f"could not connect: {type(e).__name__}: {e}"})
        states, exposed = probe["states"], probe["exposed"]
        ents: dict[str, list] = {d: [] for d in ENTITY_DOMAINS}
        for s in states:
            d = s["entity_id"].split(".", 1)[0]
            if d in ents and len(ents[d]) < 300:
                ents[d].append({"id": s["entity_id"], "name": s["attributes"].get("friendly_name", ""), "state": s["state"],
                                "exposed": None if exposed is None else s["entity_id"] in exposed})
        for rows in ents.values():
            rows.sort(key=lambda r: r["id"])
        return _json({"ok": True, "version": probe["version"], "entity_count": len(states), "entities": ents,
                      "areas": probe["areas"], "exposure_readable": exposed is not None,
                      "exposed_count": None if exposed is None else len(exposed)})

    async def _test_immich(self, request: web.Request) -> web.Response:
        body = await _body(request)
        url = (body.get("url") or "").strip().rstrip("/")
        key = (body.get("api_key") or "").strip() or self._stored("photos.immich", "api_key", "HAVENOS_IMMICH_KEY", "immich_key")
        if not url or not key:
            return _json({"ok": False, "error": "enter the URL and an API key (or save one first)"})
        with tempfile.TemporaryDirectory() as tmp:
            src = ImmichSource(ImmichConfig(url=url, api_key=key, album_id=(body.get("album") or None), shuffle=False), Path(tmp))
            try:
                info = await src.probe()
            except ImmichError as e:
                return _json({"ok": False, "error": str(e)})
            except Exception as e:                                    # noqa: BLE001
                return _json({"ok": False, "error": f"could not connect: {type(e).__name__}: {e}"})
            finally:
                await src.close()
        return _json({"ok": True, **info})

    async def _test_ma(self, request: web.Request) -> web.Response:
        from .media.library import LibraryError, MusicAssistantClient
        body = await _body(request)
        url = (body.get("url") or "").strip().rstrip("/")
        token = (body.get("token") or "").strip() or self._stored("music.assistant", "token", "HAVENOS_MA_TOKEN", "ma_token") or ""
        if not url:
            return _json({"ok": False, "error": "enter the Music Assistant URL"})
        client = MusicAssistantClient(url, token, timeout=6)
        try:
            await client.call("music/recently_played_items", limit=1)
        except LibraryError as e:
            return _json({"ok": False, "error": str(e)})
        finally:
            await client.close()
        return _json({"ok": True, "msg": f"Connected to Music Assistant {client.server_info.get('server_version', '')}".strip()})


# ---- helpers ----------------------------------------------------------------------------------

def _json(data: dict, status: int = 200) -> web.Response:
    return web.json_response(data, status=status)


async def _body(request: web.Request) -> dict:
    try:
        data = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text='{"error": "body must be JSON"}', content_type="application/json")
    if not isinstance(data, dict):
        raise web.HTTPBadRequest(text='{"error": "body must be a JSON object"}', content_type="application/json")
    return data


def _node(root: dict, dotted: str, create: bool = False) -> dict:
    cur = root
    for part in dotted.split("."):
        cur = cur.setdefault(part, {}) if create else cur.get(part, {})
    return cur


def _has_secret(toml: dict, table: str, key: str, env: str, default: Path) -> bool:
    if os.environ.get(env):
        return True
    tbl = _node(toml, table)
    if tbl.get(key):
        return True
    p = Path(tbl.get(key + "_file") or default).expanduser()
    return p.exists() and bool(p.read_text().strip())
