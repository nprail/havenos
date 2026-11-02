# Settings web UI

Everything you would otherwise edit in `config.toml` can be changed from a browser. Open `http://<device-ip>:8787` from a phone or laptop on the same network. Change the port with `[web] port` or `HAVENOS_WEB_PORT`, and turn the UI off with `HAVENOS_WEB=0`.

## What you can change

- **Home Assistant**: URL and token, the weather and media-player entities, and the quick-control tiles (with an entity picker filled from your Home Assistant).
- **Photos**: a local folder, or Immich with an album picker and the recency sliders.
- **Display**: seconds per photo, crossfade, blur and idle timeout.
- **Home Assistant device**: turn the ESPHome device on.
- **Sound**: the audio output (speaker, headphone jack, USB or HDMI) and a **Test sound** chime. Applies on save, without a restart. An output plugged in after havenOS started appears after a restart.
- **Music**: AirPlay, Sendspin, Spotify, and the Music Assistant URL and token.

**Test connection** buttons check Home Assistant, Immich and Music Assistant before you save. **Save & apply** takes effect immediately, with no restart.

## Signing in

You need the **setup code**, which is shown only on the device. Three ways to get it, none of which need the debug HUD:

- **First boot:** until setup is finished the display shows a QR code. Scan it with your phone's camera: it opens this page already signed in (the link is `http://<address>:8787/?code=XXXX-XXXX`, and the page removes the code from the address bar after signing in). The address and code are written under the QR code to type by hand.
- **Any time:** tap the **gear** on the dashboard to show the same pairing screen again.
- On the device: `~/.config/havenos/web_code` (`/var/lib/havenos/web_code` on a Pi), or the line `setup code:` in the log.

## First-time setup

The first time you sign in, a guided setup walks through: Home Assistant (optional, with a connection test), the photo source, the sound output (with a test chime), and AirPlay and Sendspin. At the end it marks setup as done and the pairing screen leaves the display. An install that already has a Home Assistant URL counts as set up. **Run setup again** is under Access.

- Wrong codes are rate-limited: 5 tries, then a 60-second lockout.
- A good code gives a session cookie (HttpOnly, SameSite=Strict, 12 hours). Changes also need an `X-Requested-With` header.
- **Generate a new code** signs everyone out.

## Secrets

Secrets are write-only. The API tells the page whether a token or key is set, never what it is. They are stored in their own `0600` files (`ha_token`, `immich_key`, `ma_token`) next to the config, and `config.toml` only points at them. An inline secret from an older config is moved out on the next save.

## What saving does

- It rewrites `config.toml`. Comments are not kept. The previous file is saved as `config.toml.bak`.
- Settings overridden by `HAVENOS_*` environment variables are listed by the API as `env_overrides` and still win.

## Network exposure

The page is plain HTTP. Use it on a trusted LAN, bind to `127.0.0.1` (`[web] host`), or put a TLS proxy in front of it.

## API

The page is a thin client of a small JSON API in `core/web.py`: `GET /api/session`, `POST /api/login`, `POST /api/logout`, `GET` and `PUT /api/config`, `GET /api/status`, `POST /api/test/ha`, `/api/test/immich` and `/api/test/ma`, and `POST /api/rotate-code`.

## Changing the styles

The page uses Tailwind CSS v4, prebuilt into `src/havenos/web/app.css` and committed, so running the app needs no Node and no internet. To change styles:

```bash
cd webui
npm install
npm run build
```
