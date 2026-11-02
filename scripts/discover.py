"""Read-only check of real servers: lists useful HA entities and probes Immich. Calls no services, changes nothing.

    python scripts/discover.py http://homeassistant.local:8123 https://photos.example.com [album-id]

Secrets come from ~/.config/havenos/ha_token and immich_key (never printed).
"""
import asyncio
import sys
from pathlib import Path

import aiohttp

CFG = Path.home() / ".config" / "havenos"
DOMAINS = ("weather", "media_player", "light", "switch", "lock", "scene", "climate", "alarm_control_panel", "cover", "fan", "script")


async def ha(url: str) -> None:
    token = (CFG / "ha_token").read_text().strip()
    ws_url = url.rstrip("/").replace("http", "ws", 1) + "/api/websocket"
    async with aiohttp.ClientSession() as s, s.ws_connect(ws_url, timeout=10) as ws:
        await ws.receive_json()
        await ws.send_json({"type": "auth", "access_token": token})
        reply = await ws.receive_json()
        print(f"HA auth: {reply['type']}" + (f" (HA {reply.get('ha_version')})" if reply["type"] == "auth_ok" else ""))
        if reply["type"] != "auth_ok":
            return
        await ws.send_json({"id": 1, "type": "get_states"})
        states = (await ws.receive_json())["result"]
    by = {d: [] for d in DOMAINS}
    for st in states:
        d = st["entity_id"].split(".", 1)[0]
        if d in by:
            by[d].append(st)
    print(f"{len(states)} entities total. Candidates:")
    for d in DOMAINS:
        rows = by[d]
        if not rows:
            continue
        print(f"\n[{d}] {len(rows)}")
        for st in sorted(rows, key=lambda x: x["entity_id"])[:25]:
            a = st["attributes"]
            extra = ""
            if d == "weather":
                extra = f" temp={a.get('temperature')}{a.get('temperature_unit', '')}"
            elif d == "media_player":
                extra = f" title={a.get('media_title')!r}"
            print(f"  {st['entity_id']:<45} {st['state']:<12} {a.get('friendly_name', '')}{extra}")
        if len(rows) > 25:
            print(f"  ... and {len(rows) - 25} more")


async def immich(url: str, album: str | None) -> None:
    key = (CFG / "immich_key").read_text().strip()
    url = url.rstrip("/")
    async with aiohttp.ClientSession(headers={"x-api-key": key}, timeout=aiohttp.ClientTimeout(total=30)) as s:
        async with s.get(f"{url}/api/server/ping") as r:
            print(f"\nImmich ping: HTTP {r.status}")
        if album:
            async with s.get(f"{url}/api/albums/{album}") as r:
                print(f"album {album}: HTTP {r.status}")
                assets = (await r.json()).get("assets", []) if r.status == 200 else []
        else:
            async with s.post(f"{url}/api/search/random", json={"size": 20, "type": "IMAGE"}) as r:
                print(f"search/random: HTTP {r.status}")
                body = await r.json() if r.status == 200 else []
                assets = body if isinstance(body, list) else body.get("assets", {}).get("items", [])
        imgs = [a for a in assets if a.get("type") == "IMAGE"]
        print(f"{len(imgs)} image assets returned")
        if imgs:
            async with s.get(f"{url}/api/assets/{imgs[0]['id']}/thumbnail", params={"size": "preview"}) as r:
                data = await r.read()
                print(f"preview download: HTTP {r.status}, {len(data) // 1024} KB, {r.headers.get('content-type')}")


async def main() -> None:
    ha_url, im_url = sys.argv[1], sys.argv[2]
    album = sys.argv[3] if len(sys.argv) > 3 else None
    for name, coro in (("Home Assistant", ha(ha_url)), ("Immich", immich(im_url, album))):
        try:
            await coro
        except Exception as e:
            print(f"{name} FAILED: {type(e).__name__}: {e}")


asyncio.run(main())
