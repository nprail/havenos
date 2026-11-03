// havenOS settings page. Plain JS, no build step; styling comes from the prebuilt Tailwind app.css.
"use strict";

const $app = document.getElementById("app");
const ICONS = ["", "bulb", "thermo", "camera", "scenes", "gear"];
const CONTROL_DOMAINS = ["light", "switch", "fan", "cover", "lock", "scene", "script", "climate", "alarm_control_panel", "input_boolean"];
const ACTIONABLE = new Set(["light", "switch", "fan", "cover", "lock", "scene", "script", "input_boolean"]);

const S = {
  authed: false, cfg: null, dirty: false, saving: false, status: null,
  secrets: { ha_token: "", immich_api_key: "", ma_token: "", clear_ha_token: false, clear_immich_key: false, clear_ma_token: false },
  ha: { testing: false, result: null }, immich: { testing: false, result: null }, ma: { testing: false, result: null },
  audio: { devices: null, error: "", testing: false, result: null },
  wizard: { active: false, step: 0, finished: false, restart: false, decided: false },
  errors: {}, loginError: "",
};

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(method, path, body) {
  const res = await fetch(path, {
    method, credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-Requested-With": "havenos" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let data = {};
  try { data = await res.json(); } catch { /* empty body */ }
  if (res.status === 401 && path !== "/api/login") { S.authed = false; render(); }
  return { ok: res.ok, status: res.status, data };
}

function toast(msg, kind = "ok") {
  const t = document.getElementById("toast");
  const color = kind === "ok" ? "border-emerald-500/40 text-emerald-300" : "border-red-500/40 text-red-300";
  t.innerHTML = `<div class="pointer-events-auto rounded-lg border ${color} bg-panel px-4 py-2 text-sm shadow-lg">${esc(msg)}</div>`;
  clearTimeout(toast.t);
  toast.t = setTimeout(() => (t.innerHTML = ""), 4000);
}

// ---------- small view helpers ----------
const field = (label, inner, hint, err) =>
  `<div class="space-y-1"><label>${label}</label>${inner}${hint ? `<p class="hint">${hint}</p>` : ""}${err ? `<p class="err">${esc(err)}</p>` : ""}</div>`;
const card = (title, sub, body) =>
  `<section class="card space-y-5"><div><h2 class="text-lg font-semibold">${title}</h2>${sub ? `<p class="mt-0.5 text-sm text-muted">${sub}</p>` : ""}</div>${body}</section>`;
const input = (path, value, extra = "") => `<input data-path="${path}" value="${esc(value)}" ${extra}>`;
const err = (p) => S.errors[p];

function secretField(kind, label, isSet, hint) {
  const key = { ha: "ha_token", immich: "immich_api_key", ma: "ma_token" }[kind];
  const clearKey = { ha: "clear_ha_token", immich: "clear_immich_key", ma: "clear_ma_token" }[kind];
  const placeholder = S.secrets[clearKey] ? "will be removed on save" : isSet ? "saved. Type to replace" : "paste here";
  return field(label,
    `<div class="flex gap-2"><input type="password" autocomplete="off" data-secret="${key}" placeholder="${placeholder}" value="${esc(S.secrets[key])}">
     ${isSet ? `<button type="button" class="btn shrink-0" data-act="clear-secret" data-kind="${clearKey}">${S.secrets[clearKey] ? "Undo" : "Remove"}</button>` : ""}</div>`,
    hint);
}

function resultBox(r) {
  if (!r) return "";
  return r.ok
    ? `<div class="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-300">${r.msg}</div>`
    : `<div class="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">${esc(r.error)}</div>`;
}

// ---------- sections ----------
function loginView() {
  return `<div class="mx-auto mt-24 max-w-sm space-y-5">
    <div class="text-center"><div class="font-light text-3xl tracking-tight">havenOS</div><p class="mt-1 text-sm text-muted">Settings</p></div>
    <form id="login" class="card space-y-4">
      ${field("Setup code", `<input id="code" autocomplete="off" autocapitalize="characters" spellcheck="false" placeholder="XXXX-XXXX" class="text-center font-mono text-lg tracking-widest" autofocus>`,
        "Scan the QR code on the display with your phone. Or tap the gear on the dashboard to show the code.", S.loginError)}
      <button class="btn btn-primary w-full" type="submit">Continue</button>
    </form></div>`;
}

function statusPills() {
  const s = S.status; if (!s) return "";
  const dot = (ok) => `<span class="h-1.5 w-1.5 rounded-full ${ok ? "bg-emerald-400" : "bg-amber-400"}"></span>`;
  return `<div class="flex flex-wrap gap-2">
    <span class="pill">${dot(s.ha_status === "connected" || s.ha_status === "demo")}Home Assistant: ${esc(s.ha_status)}</span>
    <span class="pill">${dot(!!s.photo)}Photos: ${esc(s.photo_source)}${s.photo ? ` · ${s.cached_photos} cached` : " · none yet"}</span></div>`;
}

function entityOptions(domains) {
  const e = S.ha.result && S.ha.result.ok ? S.ha.result.entities : null;
  if (!e) return "";
  return domains.flatMap((d) => e[d] || []).map((r) => `<option value="${esc(r.id)}">${esc(r.name)} (${esc(r.state)})${r.exposed === false ? " · not exposed to Assist" : ""}</option>`).join("");
}

function controlsEditor(ha) {
  const rows = ha.controls.map((c, i) => {
    const domain = (c.entity || "").split(".")[0];
    const note = domain && !ACTIONABLE.has(domain) ? `<span class="text-xs text-muted">display only</span>`
      : domain === "lock" || domain === "cover" ? `<span class="text-xs text-amber-400">tap acts on a real ${domain}</span>` : "";
    return `<div class="space-y-2 rounded-xl border border-edge bg-black/20 p-3">
      <div class="grid gap-2 sm:grid-cols-[1fr_9rem_8rem]">
        <input list="dl-controls" data-ctl="${i}.entity" value="${esc(c.entity)}" placeholder="light.kitchen">
        <input data-ctl="${i}.label" value="${esc(c.label || "")}" placeholder="Label" maxlength="24">
        <select data-ctl="${i}.icon">${ICONS.map((ic) => `<option value="${ic}" ${((c.icon || "") === ic) ? "selected" : ""}>${ic || "auto icon"}</option>`).join("")}</select>
      </div>
      <div class="flex items-center justify-between">
        <div>${note}${err("homeassistant.controls." + i) ? `<span class="err">${esc(err("homeassistant.controls." + i))}</span>` : ""}</div>
        <div class="flex gap-1.5">
          <button type="button" class="btn !px-2.5 !py-1" data-act="ctl-up" data-i="${i}" ${i === 0 ? "disabled" : ""} aria-label="Move up">↑</button>
          <button type="button" class="btn !px-2.5 !py-1" data-act="ctl-down" data-i="${i}" ${i === ha.controls.length - 1 ? "disabled" : ""} aria-label="Move down">↓</button>
          <button type="button" class="btn !px-2.5 !py-1" data-act="ctl-del" data-i="${i}" aria-label="Remove">Remove</button>
        </div></div></div>`;
  }).join("");
  return `<div class="space-y-2"><label>Custom quick tiles <span class="font-normal text-muted">(optional, ${ha.controls.length}/6)</span></label>
    ${rows || `<p class="text-sm text-muted">Automatic: the dashboard shows the major entities (lights, climate, fans, covers, media) in this display's room that are exposed to Assist. Add tiles here only to override that.</p>`}
    <datalist id="dl-controls">${entityOptions(CONTROL_DOMAINS)}</datalist>
    <button type="button" class="btn" data-act="ctl-add" ${ha.controls.length >= 6 ? "disabled" : ""}>+ Add tile</button>
    <p class="hint">Only entities exposed to Assist are ever shown, even if listed here. Tapping a lock tile can only lock; unlocking is done from the room screen with a confirmation.</p></div>`;
}

function exposureNote() {
  const st = S.status, ex = st && st.exposure, room = st && st.room;
  if (!ex) return "";
  const parts = [];
  parts.push(room ? `<div class="rounded-lg border border-edge bg-black/20 px-3 py-2 text-sm">This display is in <span class="font-medium text-accent">${esc(room.name)}</span>${ex.ok ? ` · ${ex.exposed} entities exposed to Assist` : ""}.</div>`
    : (ex.ok ? `<div class="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-300">This display has no room. Assign it an area in Home Assistant (Settings → Devices → this device), or pick one above.</div>` : ""));
  if (!ex.ok && ex.error) parts.push(`<div class="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">${esc(ex.error)}. Nothing from Home Assistant is shown until this works.</div>`);
  if (ex.ok && ex.hidden && ex.hidden.length) parts.push(`<div class="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-300">Not shown because they are not exposed to Assist: <span class="font-mono">${ex.hidden.map(esc).join(", ")}</span>. Expose them in Home Assistant under Settings → Voice assistants → Expose.</div>`);
  return parts.join("");
}

function haCard() {
  const ha = S.cfg.homeassistant, r = S.ha.result;
  let res = "";
  if (r && r.ok) res = resultBox({ ok: true, msg: `Connected to Home Assistant ${esc(r.version)} · ${r.entity_count} entities · ${r.exposure_readable ? `${r.exposed_count} exposed to Assist` : "exposure settings could not be read (the token's user must be an administrator)"}. The lists below now autocomplete.` });
  else if (r) res = resultBox(r);
  return card("Home Assistant", "Weather, now playing and quick controls come from here.", `
    ${field("URL", input("homeassistant.url", ha.url, 'placeholder="http://homeassistant.local:8123" inputmode="url"'), "", err("homeassistant.url"))}
    ${secretField("ha", "Long-lived access token", S.cfg.secrets.ha_token_set, "Create one on your Home Assistant profile page (bottom of the Security tab). Stored in a private file, never shown again.")}
    <div class="flex items-center gap-3"><button type="button" class="btn" data-act="test-ha" ${S.ha.testing ? "disabled" : ""}>${S.ha.testing ? "Testing…" : "Test connection"}</button><span class="text-xs text-muted">Uses what you typed, or the saved token.</span></div>
    ${res}
    ${exposureNote()}
    ${field("Room", `<input list="dl-areas" data-path="homeassistant.room" value="${esc(ha.room)}" placeholder="Automatic (the area assigned to this device in Home Assistant)"><datalist id="dl-areas">${(S.ha.result && S.ha.result.ok ? S.ha.result.areas : []).map((a) => `<option value="${esc(a.name)}">`).join("")}</datalist>`, "This display's room decides its quick tiles and which media player it uses. Leave blank to use the area Home Assistant has for this device.", err("homeassistant.room"))}
    <div class="grid gap-4 sm:grid-cols-2">
      ${field("Weather entity", `<input list="dl-weather" data-path="homeassistant.weather" value="${esc(ha.weather)}" placeholder="weather.home"><datalist id="dl-weather">${entityOptions(["weather"])}</datalist>`, "", err("homeassistant.weather"))}
      ${field("Media player", `<input list="dl-media" data-path="homeassistant.media_player" value="${esc(ha.media_player)}" placeholder="media_player.kitchen"><datalist id="dl-media">${entityOptions(["media_player"])}</datalist>`, "", err("homeassistant.media_player"))}
    </div>
    ${controlsEditor(ha)}`);
}

function photosCard() {
  const p = S.cfg.photos, im = p.immich, r = S.immich.result;
  const seg = (v, label) => `<button type="button" data-act="source" data-v="${v}" class="flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition ${p.source === v ? "bg-accent text-black" : "text-muted hover:text-ink"}">${label}</button>`;
  let res = "";
  if (r && r.ok) res = resultBox({ ok: true, msg: `Connected. ${r.sample_photos} photos sampled, preview download works (${Math.round(r.preview_bytes / 1024)} KB)${r.albums.length ? ` · ${r.albums.length} albums` : ""}.` });
  else if (r) res = resultBox(r);
  const albums = r && r.ok && r.albums.length
    ? `<select data-path="photos.immich.album"><option value="">Whole library</option>${r.albums.map((a) => `<option value="${esc(a.id)}" ${a.id === im.album ? "selected" : ""}>${esc(a.name)} (${a.count})</option>`).join("")}</select>`
    : input("photos.immich.album", im.album, 'placeholder="Whole library (or paste an album id)"');
  const half = Number(im.recency_half_life_days);
  const nasaBody = `<p class="hint">NASA's Image of the Day, shuffled. The feed holds about 50 recent images and needs no account or key; the device needs internet access.</p>`;
  const immichBody = `
    ${field("Immich URL", input("photos.immich.url", im.url, 'placeholder="https://photos.example.com" inputmode="url"'), "", err("photos.immich.url"))}
    ${secretField("immich", "API key", S.cfg.secrets.immich_key_set, "Create one in Immich: Account Settings → API Keys. Needs asset.read and asset.view (and album.read to list albums).")}
    <div class="flex items-center gap-3"><button type="button" class="btn" data-act="test-immich" ${S.immich.testing ? "disabled" : ""}>${S.immich.testing ? "Testing…" : "Test connection"}</button></div>
    ${res}
    ${field("Album", albums, "Leave on Whole library to draw from everything.")}
    <label class="flex items-center gap-2"><input type="checkbox" data-path="photos.immich.shuffle" ${im.shuffle ? "checked" : ""}> Favor recent photos and shuffle</label>
    <div class="${im.shuffle ? "" : "pointer-events-none opacity-40"} space-y-4 rounded-xl border border-edge bg-black/20 p-4">
      ${field(`Recency preference: <span class="text-accent">${half === 0 ? "off" : `halves every ${half} days`}</span>`,
        `<input type="range" min="0" max="1460" step="30" data-path="photos.immich.recency_half_life_days" value="${half}">`,
        "Lower = recent photos dominate. A photo's chance halves each time it is this much older. 0 turns the preference off.", err("photos.immich.recency_half_life_days"))}
      ${field(`Old-photo floor: <span class="text-accent">${Math.round(im.recency_floor * 100)}%</span>`,
        `<input type="range" min="0.02" max="0.5" step="0.02" data-path="photos.immich.recency_floor" value="${im.recency_floor}">`,
        "No photo drops below this share of a brand-new photo's chance, so old ones always still appear.", err("photos.immich.recency_floor"))}
    </div>`;
  const localBody = field("Photo folder", input("photos.dir", p.dir, 'placeholder="/home/pi/Pictures (blank = built-in samples)"'), "A folder on the device.");
  return card("Photos", "Where the ambient slideshow gets its pictures.", `
    <div class="flex gap-1 rounded-lg border border-edge bg-black/30 p-1">${seg("nasa", "NASA")}${seg("local", "Local folder")}${seg("immich", "Immich")}</div>
    ${p.source === "immich" ? immichBody : p.source === "local" ? localBody : nasaBody}`);
}

function displayCard() {
  const d = S.cfg.display;
  return card("Display", "Timing and look of the ambient screen.", `
    <div class="grid gap-4 sm:grid-cols-2">
      ${field("Seconds per photo", input("display.photo_interval_s", d.photo_interval_s, 'type="number" min="2" max="3600" step="1" inputmode="decimal"'), "", err("display.photo_interval_s"))}
      ${field("Return to ambient after (seconds idle)", input("display.idle_s", d.idle_s, 'type="number" min="5" max="3600" step="5" inputmode="decimal"'), "", err("display.idle_s"))}
    </div>
    ${field(`Crossfade: <span class="text-accent">${(d.crossfade_ms / 1000).toFixed(1)} s</span>`, `<input type="range" min="0" max="4000" step="100" data-path="display.crossfade_ms" value="${d.crossfade_ms}">`, "How long one photo takes to dissolve into the next.", err("display.crossfade_ms"))}
    ${field(`Brightness: <span class="text-accent">${d.brightness}%</span>`, `<input type="range" min="10" max="100" step="5" data-path="display.brightness" value="${d.brightness}">`, "Sets the panel's backlight (software dimming where there is none). Home Assistant's Brightness control changes the same setting.", err("display.brightness"))}
    <label class="flex items-center gap-2"><input type="checkbox" data-path="display.blur" ${d.blur ? "checked" : ""}> Frosted-glass blur on panels <span class="text-xs font-normal text-muted">(turn off if the screen stutters)</span></label>`);
}

function esphomeCard() {
  const e = S.cfg.esphome, st = S.status && S.status.esphome;
  const live = st && st.running
    ? `<div class="rounded-lg border ${st.clients ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300" : "border-edge bg-black/20 text-muted"} px-3 py-2 text-sm">Running as <span class="font-mono">${esc(st.name)}</span> on port ${st.port} · ${st.clients ? "Home Assistant is connected" : "waiting for Home Assistant to add it"}</div>`
    : e.enabled ? `<div class="rounded-lg border border-edge bg-black/20 px-3 py-2 text-sm text-muted">Not running yet. Save, then restart havenOS.</div>` : "";
  return card("Home Assistant device", "Let Home Assistant see this display as a device: screen, brightness, photo controls, sensors and touch events.", `
    <label class="flex items-center gap-2"><input type="checkbox" data-path="esphome.enabled" ${e.enabled ? "checked" : ""}> Appear in Home Assistant as an ESPHome device</label>
    <div class="${e.enabled ? "" : "pointer-events-none opacity-40"} grid gap-4 sm:grid-cols-2">
      ${field("Device name", input("esphome.name", e.name, 'placeholder="havenos-<hostname>" maxlength="31" spellcheck="false"'), "Lowercase letters, digits and dashes.", err("esphome.name"))}
      ${field("Port", input("esphome.port", e.port, 'type="number" min="1024" max="65535" inputmode="numeric"'), "Home Assistant's default is 6053.", err("esphome.port"))}
    </div>
    ${live}
    <p class="hint">After saving and restarting, open Home Assistant → Settings → Devices &amp; services. The display appears as <em>Discovered</em> under ESPHome; click Configure. This link is not encrypted and has no password, so use it on your home network only.</p>`);
}

function soundCard() {
  const a = S.audio, cur = S.cfg.music.audio_device || "";
  const known = (a.devices || []).some((d) => d.value === cur);
  const opts = [`<option value="">System default</option>`,
    ...(a.devices || []).map((d) => `<option value="${esc(d.value)}" ${d.value === cur ? "selected" : ""}>${esc(d.label)}</option>`),
    ...(cur && !known ? [`<option value="${esc(cur)}" selected>${esc(cur)} (not found right now)</option>`] : [])].join("");
  const hint = a.error ? esc(a.error)
    : a.devices === null ? "Looking for sound outputs…"
    : "Where music, timers and the assistant play. Test sound saves your choice first, then plays a short chime on it. An output plugged in after havenOS started shows up after a restart.";
  return card("Sound", "Which speaker or audio output the display uses.", `
    ${field("Audio output", `<select data-path="music.audio_device">${opts}</select>`, hint, err("music.audio_device"))}
    <div class="flex flex-wrap gap-2"><button type="button" class="btn" data-act="test-audio" ${a.testing ? "disabled" : ""}>${a.testing ? "Playing…" : "Test sound"}</button></div>${resultBox(a.result)}`);
}

function musicSource(id, label, hint) {
  const m = S.cfg.music;
  return `<div class="space-y-2"><label class="flex items-center gap-2"><input type="checkbox" data-path="music.${id}.enabled" ${m[id].enabled ? "checked" : ""}> ${label}</label>
    <div class="${m[id].enabled ? "" : "pointer-events-none opacity-40"}">${field("Name shown on the sender", input(`music.${id}.name`, m[id].name, 'placeholder="havenOS <hostname>" maxlength="40"'), hint, err(`music.${id}.name`))}</div></div>`;
}

function musicCard() {
  const m = S.cfg.music, ma = m.assistant;
  const src = musicSource;
  return card("Music", "Receive music from phones and Music Assistant, and browse your library on the display.", `
    ${src("airplay", "AirPlay receiver", "Needs shairport-sync installed on the device.")}
    ${src("sendspin", "Sendspin (Music Assistant players)", "Music Assistant finds the display on its own and adds it as a player.")}
    ${src("spotify", "Spotify Connect", "Needs go-librespot and a Spotify Premium account.")}
    <p class="hint">Turning a source on or off needs a restart of havenOS.</p>
    <div class="grid gap-4 sm:grid-cols-2">
      ${field("Music Assistant URL", input("music.assistant.url", ma.url, 'placeholder="http://homeassistant.local:8095" spellcheck="false"'), "Lets the display search and play from your library.", err("music.assistant.url"))}
      ${secretField("ma", "Music Assistant token", S.cfg.secrets.ma_token_set, "Create a long-lived token in Music Assistant: Settings → Profile.")}
    </div>
    ${field("Player id (optional)", input("music.assistant.player_id", ma.player_id, 'spellcheck="false"'), "Leave blank: the display finds its own player by name.", err("music.assistant.player_id"))}
    <div class="flex flex-wrap gap-2"><button type="button" class="btn" data-act="test-ma" ${S.ma.testing ? "disabled" : ""}>${S.ma.testing ? "Testing…" : "Test connection"}</button></div>${resultBox(S.ma.result)}
    <div class="grid gap-4 sm:grid-cols-2">
      ${field("Free the speaker after pausing for (seconds)", input("music.idle_s", m.idle_s, 'type="number" min="10" max="86400" step="10" inputmode="numeric"'), "", err("music.idle_s"))}
      ${field(`Music level while speaking: <span class="text-accent">${m.duck_db} dB</span>`, `<input type="range" min="-40" max="0" step="1" data-path="music.duck_db" value="${m.duck_db}">`, "How far music drops during announcements, timers and the assistant.", err("music.duck_db"))}
    </div>
    <label class="flex items-center gap-2"><input type="checkbox" data-path="music.hint" ${m.hint ? "checked" : ""}> Show "ready to cast" on the display while nothing is playing</label>`);
}

function notificationsCard() {
  const n = S.cfg.notifications, ha = S.cfg.homeassistant;
  return card("Announcements & notifications", "Messages sent to this display from Home Assistant.", `
    ${field("Show announcements for (seconds)", input("notifications.announcement_seconds", n.announcement_seconds, 'type="number" min="3" max="600" step="1" inputmode="numeric"'), "Critical announcements stay until dismissed. Home Assistant sends them with the havenos &lt;name&gt; announce service (title, message, kind: info / warning / critical, seconds), and quieter ones with notify.", err("notifications.announcement_seconds"))}
    <label class="flex items-center gap-2"><input type="checkbox" data-path="homeassistant.persistent_notifications" ${ha.persistent_notifications ? "checked" : ""}> Also show Home Assistant's own notifications <span class="text-xs font-normal text-muted">(update available, new devices, ...)</span></label>`);
}

function accessCard() {
  return card("Access", "This page is protected by the setup code shown on the device.", `
    <div class="flex flex-wrap gap-2">
      <button type="button" class="btn" data-act="wizard">Run setup again</button>
      <button type="button" class="btn" data-act="rotate">Generate a new code</button>
      <button type="button" class="btn" data-act="logout">Sign out</button></div>
    <p class="hint">This page is served over plain HTTP, so use it on your home network only. Changing the code signs everyone out.</p>`);
}

// ---------- first-time setup ----------
const WIZARD_STEPS = ["Welcome", "Home Assistant", "Photos", "Sound", "Music", "All set"];

function wizardHaCard() {
  const ha = S.cfg.homeassistant, r = S.ha.result;
  const res = r && r.ok ? resultBox({ ok: true, msg: `Connected to Home Assistant ${esc(r.version)} · ${r.entity_count} entities.` }) : r ? resultBox(r) : "";
  return card("Home Assistant", "Optional. It gives the display weather, your lights and scenes, and room controls. Skip it to try havenOS with demo data.", `
    ${field("URL", input("homeassistant.url", ha.url, 'placeholder="http://homeassistant.local:8123" inputmode="url"'), "", err("homeassistant.url"))}
    ${secretField("ha", "Long-lived access token", S.cfg.secrets.ha_token_set, "In Home Assistant: your profile (bottom left) → Security → Long-lived access tokens → Create token. It is stored in a private file on the display and never shown again.")}
    <div class="flex items-center gap-3"><button type="button" class="btn" data-act="test-ha" ${S.ha.testing ? "disabled" : ""}>${S.ha.testing ? "Testing…" : "Test connection"}</button></div>
    ${res}
    <p class="hint">Weather, quick tiles and the room are set up later in Settings.</p>`);
}

function wizardMusicCard() {
  return card("Music", "Let phones and Music Assistant play to this display.", `
    ${musicSource("airplay", "AirPlay (iPhone, iPad, Mac)", "Shown as this name in the AirPlay menu.")}
    ${musicSource("sendspin", "Sendspin (Music Assistant)", "Music Assistant finds the display on its own and adds it as a player.")}
    <p class="hint">Spotify Connect and the Music Assistant library are in Settings. Turning a source on or off needs a restart of havenOS.</p>`);
}

function wizardWelcome() {
  const item = (t, d) => `<li class="flex gap-3"><span class="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent"></span><span><span class="font-medium">${t}</span> <span class="text-muted">${d}</span></span></li>`;
  return card("Welcome to havenOS", "You are signed in to your display. A few quick steps and it is ready; everything can be changed later in Settings.", `
    <ul class="space-y-3 text-sm">
      ${item("Home Assistant", "weather, lights and rooms (optional)")}
      ${item("Photos", "what the ambient slideshow shows")}
      ${item("Sound", "which speaker to use")}
      ${item("Music", "AirPlay and Music Assistant")}
    </ul>`);
}

function wizardReady() {
  const c = S.cfg, on = ["airplay", "sendspin"].filter((k) => c.music[k].enabled);
  const dev = (S.audio.devices || []).find((d) => d.value === c.music.audio_device);
  const row = (k, v) => `<div class="flex justify-between gap-4 border-b border-edge py-2 last:border-0"><span class="text-muted">${k}</span><span class="text-right">${v}</span></div>`;
  return card("Ready to finish", "Here is what you chose. Finish to close setup; the pairing screen then leaves the display.", `
    <div class="text-sm">
      ${row("Home Assistant", c.homeassistant.url ? esc(c.homeassistant.url) : "Not connected (demo data)")}
      ${row("Photos", { nasa: "NASA Image of the Day", local: "Local folder", immich: "Immich" }[c.photos.source] || esc(c.photos.source))}
      ${row("Sound", c.music.audio_device ? esc(dev ? dev.label : c.music.audio_device) : "System default")}
      ${row("Music", on.length ? on.map((k) => ({ airplay: "AirPlay", sendspin: "Sendspin" }[k])).join(", ") : "No sources on")}
    </div>`);
}

function wizardDone() {
  const w = S.wizard;
  return card("You're all set", "Setup is finished and the pairing screen has left the display.", `
    <div class="space-y-2 text-sm">
      <p>Try it: send a song to <span class="font-medium">${esc((S.cfg.music.airplay.name || "havenOS"))}</span> from your phone's AirPlay menu, or say a timer on the display.</p>
      ${w.restart ? `<p class="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-amber-300">The music sources you changed need a restart of havenOS to take effect. Run <span class="font-mono">sudo systemctl restart havenos</span> on the device, or unplug it for a moment.</p>` : ""}
      <p class="text-muted">The setup code on the display stays the same. You can show it again from the gear on the dashboard.</p>
    </div>`);
}

function wizardView() {
  const w = S.wizard, last = WIZARD_STEPS.length - 1;
  const body = [wizardWelcome, wizardHaCard, photosCard, soundCard, wizardMusicCard, w.finished ? wizardDone : wizardReady][w.step]();
  const bar = WIZARD_STEPS.map((_, i) => `<span class="h-1 flex-1 rounded-full ${i <= w.step ? "bg-accent" : "bg-edge"}"></span>`).join("");
  const skipLabel = w.step === 1 && !S.cfg.homeassistant.url ? "Skip for now" : "";
  const nav = w.finished
    ? `<button class="btn btn-primary" data-act="wiz-open-settings">Open settings</button>`
    : w.step === 0
      ? `<button class="btn" data-act="wiz-skip">I'll do this later</button><button class="btn btn-primary" data-act="wiz-next">Start</button>`
      : w.step === last
        ? `<button class="btn" data-act="wiz-back">Back</button><button class="btn btn-primary" data-act="wiz-finish" ${S.saving ? "disabled" : ""}>${S.saving ? "Finishing…" : "Finish"}</button>`
        : `<button class="btn" data-act="wiz-back">Back</button><span class="flex-1"></span>${skipLabel ? `<button class="btn" data-act="wiz-skipstep">${skipLabel}</button>` : ""}<button class="btn btn-primary" data-act="wiz-next" ${S.saving ? "disabled" : ""}>${S.saving ? "Saving…" : "Next"}</button>`;
  return `<header class="mb-6 space-y-3"><div class="flex items-baseline justify-between"><h1 class="text-3xl font-light tracking-tight">havenOS <span class="text-muted">setup</span></h1>
      <span class="text-sm text-muted">${w.finished ? "" : `Step ${w.step + 1} of ${WIZARD_STEPS.length}`}</span></div>
      <div class="flex gap-1.5">${bar}</div></header>
    <div class="space-y-5">${body}</div>
    <div class="fixed inset-x-0 bottom-0 z-40 border-t border-edge bg-bg/90 backdrop-blur"><div class="mx-auto flex max-w-3xl items-center justify-between gap-3 px-4 py-3 sm:px-6">${nav}</div></div>`;
}

function mainView() {
  return `<header class="mb-6 space-y-3"><div class="flex items-baseline justify-between"><h1 class="text-3xl font-light tracking-tight">havenOS <span class="text-muted">settings</span></h1></div>${statusPills()}</header>
    <div class="space-y-5">${haCard()}${photosCard()}${displayCard()}${notificationsCard()}${soundCard()}${musicCard()}${esphomeCard()}${accessCard()}</div>
    <div class="fixed inset-x-0 bottom-0 z-40 border-t border-edge bg-bg/90 backdrop-blur"><div class="mx-auto flex max-w-3xl items-center justify-between gap-3 px-4 py-3 sm:px-6">
      <span class="text-sm ${S.dirty ? "text-amber-300" : "text-muted"}">${S.dirty ? "Unsaved changes" : "All changes saved"}</span>
      <div class="flex gap-2"><button class="btn" data-act="revert" ${S.dirty ? "" : "disabled"}>Revert</button>
      <button class="btn btn-primary" data-act="save" ${S.dirty && !S.saving ? "" : "disabled"}>${S.saving ? "Saving…" : "Save & apply"}</button></div></div></div>`;
}

function render() {
  // Keep focus and caret across re-renders (typing in a field re-renders for sliders/labels).
  const a = document.activeElement, keep = a && (a.dataset.path || a.dataset.secret || a.dataset.ctl);
  const sel = a && a.selectionStart != null ? [a.selectionStart, a.selectionEnd] : null;
  const key = a && (a.dataset.path ? `[data-path="${a.dataset.path}"]` : a.dataset.secret ? `[data-secret="${a.dataset.secret}"]` : a.dataset.ctl ? `[data-ctl="${a.dataset.ctl}"]` : null);
  $app.innerHTML = S.authed ? (S.cfg ? (S.wizard.active ? wizardView() : mainView()) : `<p class="mt-20 text-center text-muted">Loading…</p>`) : loginView();
  if (keep && key) { const n = $app.querySelector(key); if (n) { n.focus(); if (sel && n.setSelectionRange) try { n.setSelectionRange(...sel); } catch {} } }
}

// ---------- state edits ----------
const get = (o, p) => p.split(".").reduce((x, k) => (x == null ? x : x[k]), o);
function set(o, p, v) { const ks = p.split("."); const last = ks.pop(); ks.reduce((x, k) => x[k], o)[last] = v; }
const NUMERIC = new Set(["notifications.announcement_seconds", "esphome.port", "music.idle_s", "music.duck_db", "display.photo_interval_s", "display.idle_s", "display.crossfade_ms", "display.brightness", "photos.immich.recency_half_life_days", "photos.immich.recency_floor"]);

function markDirty() { S.dirty = true; }

$app.addEventListener("input", (e) => {
  const t = e.target;
  if (t.dataset.path) {
    const v = t.type === "checkbox" ? t.checked : NUMERIC.has(t.dataset.path) ? (t.value === "" ? "" : Number(t.value)) : t.value;
    set(S.cfg, t.dataset.path, v); markDirty();
    delete S.errors[t.dataset.path];
    // Sliders and toggles show their value in labels / enable sub-sections: refresh.
    if (t.type === "range" || t.type === "checkbox") render(); else updateSaveBar();
  } else if (t.dataset.secret) {
    S.secrets[t.dataset.secret] = t.value; markDirty(); updateSaveBar();
  } else if (t.dataset.ctl) {
    const [i, k] = t.dataset.ctl.split("."); S.cfg.homeassistant.controls[+i][k] = t.value; markDirty(); updateSaveBar();
  }
});
$app.addEventListener("change", (e) => { if (e.target.tagName === "SELECT") { e.target.dispatchEvent(new Event("input", { bubbles: true })); render(); } });

function updateSaveBar() {
  const save = $app.querySelector('[data-act="save"]'), rev = $app.querySelector('[data-act="revert"]');
  if (save) save.disabled = !S.dirty || S.saving; if (rev) rev.disabled = !S.dirty;
  const label = save && save.closest("div.flex.max-w-3xl, div.mx-auto"); const msg = label && label.querySelector("span.text-sm");
  if (msg) { msg.textContent = S.dirty ? "Unsaved changes" : "All changes saved"; msg.className = "text-sm " + (S.dirty ? "text-amber-300" : "text-muted"); }
}

$app.addEventListener("submit", async (e) => {
  if (e.target.id !== "login") return;
  e.preventDefault();
  const r = await api("POST", "/api/login", { code: document.getElementById("code").value });
  if (r.ok) { S.loginError = ""; S.authed = true; await load(); } else { S.loginError = r.data.error || "Could not sign in"; render(); }
});

$app.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-act]"); if (!b) return;
  const act = b.dataset.act, i = Number(b.dataset.i);
  const ctl = S.cfg && S.cfg.homeassistant.controls;
  switch (act) {
    case "source": S.cfg.photos.source = b.dataset.v; markDirty(); render(); break;
    case "clear-secret": S.secrets[b.dataset.kind] = !S.secrets[b.dataset.kind]; markDirty(); render(); break;
    case "ctl-add": ctl.push({ entity: "", label: "", icon: "" }); markDirty(); render(); break;
    case "ctl-del": ctl.splice(i, 1); markDirty(); render(); break;
    case "ctl-up": [ctl[i - 1], ctl[i]] = [ctl[i], ctl[i - 1]]; markDirty(); render(); break;
    case "ctl-down": [ctl[i + 1], ctl[i]] = [ctl[i], ctl[i + 1]]; markDirty(); render(); break;
    case "test-ha": await testHA(); break;
    case "test-immich": await testImmich(); break;
    case "test-ma": await testMA(); break;
    case "test-audio": await testAudio(); break;
    case "save": await save(); break;
    case "wizard": S.wizard = { ...S.wizard, active: true, step: 0, finished: false }; render(); window.scrollTo(0, 0); break;
    case "wiz-next": if (S.wizard.step === 0 || await save()) { S.wizard.step++; render(); window.scrollTo(0, 0); } break;
    case "wiz-skipstep": S.wizard.step++; render(); window.scrollTo(0, 0); break;
    case "wiz-back": S.wizard.step--; render(); window.scrollTo(0, 0); break;
    case "wiz-skip": if (confirm("Skip setup? You can run it again from Settings.")) { S.cfg.setup.done = true; await save(); S.wizard.active = false; render(); } break;
    case "wiz-finish": S.cfg.setup.done = true; if (await save()) { S.wizard.finished = true; render(); window.scrollTo(0, 0); } break;
    case "wiz-open-settings": S.wizard.active = false; render(); window.scrollTo(0, 0); break;
    case "revert": await load(); toast("Reverted to saved settings"); break;
    case "logout": await api("POST", "/api/logout", {}); S.authed = false; S.cfg = null; render(); break;
    case "rotate": if (confirm("Generate a new setup code? You will be signed out, and the new code appears on the device.")) { await api("POST", "/api/rotate-code", {}); S.authed = false; S.cfg = null; render(); } break;
  }
});

// ---------- actions ----------
async function testHA() {
  S.ha.testing = true; S.ha.result = null; render();
  const r = await api("POST", "/api/test/ha", { url: S.cfg.homeassistant.url, token: S.secrets.ha_token });
  S.ha.testing = false; S.ha.result = r.data; render();
}
async function testImmich() {
  S.immich.testing = true; S.immich.result = null; render();
  const r = await api("POST", "/api/test/immich", { url: S.cfg.photos.immich.url, api_key: S.secrets.immich_api_key });
  S.immich.testing = false; S.immich.result = r.data; render();
}

async function loadAudio() {
  const r = await api("GET", "/api/audio/devices");
  S.audio.devices = r.ok ? r.data.devices : []; S.audio.error = r.ok ? (r.data.error || "") : "Could not list sound outputs";
}

async function testAudio() {
  if (S.dirty && !(await save())) return;                      // test what was picked, not what was saved before
  S.audio.testing = true; S.audio.result = null; render();
  const r = await api("POST", "/api/test/audio", {});
  S.audio.testing = false; S.audio.result = r.data;
  render();
}

async function testMA() {
  S.ma.testing = true; S.ma.result = null; render();
  const r = await api("POST", "/api/test/ma", { url: S.cfg.music.assistant.url, token: S.secrets.ma_token });
  S.ma.testing = false; S.ma.result = r.data; render();
}

async function save() {
  S.saving = true; S.errors = {}; render();
  const c = S.cfg;
  const body = {
    homeassistant: { url: c.homeassistant.url, weather: c.homeassistant.weather, media_player: c.homeassistant.media_player,
      room: c.homeassistant.room, persistent_notifications: c.homeassistant.persistent_notifications,
      controls: c.homeassistant.controls.filter((x) => (x.entity || "").trim()) },
    photos: { source: c.photos.source, dir: c.photos.dir, immich: c.photos.immich },
    display: c.display, esphome: c.esphome, notifications: c.notifications, music: c.music, setup: c.setup,
    secrets: { ha_token: S.secrets.ha_token, immich_api_key: S.secrets.immich_api_key, ma_token: S.secrets.ma_token,
      clear_ha_token: S.secrets.clear_ha_token, clear_immich_key: S.secrets.clear_immich_key, clear_ma_token: S.secrets.clear_ma_token },
  };
  const r = await api("PUT", "/api/config", body);
  S.saving = false;
  if (r.ok) {
    S.cfg = r.data.view; S.dirty = false;
    S.secrets = { ha_token: "", immich_api_key: "", ma_token: "", clear_ha_token: false, clear_immich_key: false, clear_ma_token: false };
    if (r.data.restart_required) S.wizard.restart = true;
    if (!S.wizard.active) toast(r.data.restart_required ? "Saved. Restart havenOS to apply the Home Assistant device settings" : "Saved and applied");
    await refreshStatus();
  } else if (r.status === 422) {
    S.errors = r.data.fields || {}; toast("Fix the highlighted fields", "err");
  } else if (r.status !== 401) {
    if (r.data.view) { S.cfg = r.data.view; S.dirty = false; }
    toast(r.data.error || "Could not save", "err");
  }
  render();
  return r.ok;
}

async function refreshStatus() { const r = await api("GET", "/api/status"); if (r.ok) S.status = r.data; }
async function load() {
  const r = await api("GET", "/api/config");
  if (r.ok) { S.cfg = r.data; S.dirty = false; S.errors = {}; S.secrets = { ha_token: "", immich_api_key: "", ma_token: "", clear_ha_token: false, clear_immich_key: false, clear_ma_token: false }; await refreshStatus(); loadAudio().then(render);
    if (!S.wizard.decided) { S.wizard.decided = true; S.wizard.active = !S.cfg.setup.done; } }
  render();
}

(async function init() {
  // The QR code on the display opens this page as /?code=XXXX-XXXX: sign in with it, then take it out of the address bar.
  const q = new URLSearchParams(location.search).get("code");
  if (q !== null) history.replaceState(null, "", location.pathname);
  if (q) {
    const l = await api("POST", "/api/login", { code: q });
    if (!l.ok) S.loginError = l.status === 429 ? l.data.error : "That link's code is out of date. Enter the code shown on the display.";
  }
  const s = await api("GET", "/api/session");
  S.authed = !!(s.data && s.data.authenticated);
  if (S.authed) await load(); else render();
  setInterval(async () => { if (S.authed && !S.saving) { await refreshStatus(); const p = document.querySelector("header .flex.flex-wrap"); if (p) p.outerHTML = statusPills(); } }, 8000);
})();
