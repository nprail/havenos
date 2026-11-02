# Troubleshooting

## The app will not start or a port is busy

**AirPlay: port 7000 or 7100 is in use.** On a Mac, the system's AirPlay Receiver holds port 7000. Set `HAVENOS_AIRPLAY_PORT=7100` (or `[music.airplay] port = 7100`).

**Port 7100 is still held after the app is gone.** SIGTERM and Ctrl-C now quit the app normally, which stops `shairport-sync` and `go-librespot` with it; a second signal kills them and exits at once. On Linux the helpers also ask the kernel to stop them if the app dies (via `setpriv`). Only a hard `kill -9` on a Mac can still leave one behind. If it is stuck:

```bash
lsof -nP -iTCP:7100 -sTCP:LISTEN
kill <pid of shairport-sync>
```

**The web UI port is busy.** A busy port is logged and the app carries on without the settings page. Change `[web] port`.

**The ESPHome port is busy.** The error is logged ("ESPHome device could not start") and the rest of the app runs. Change `[esphome] port`.

## Home Assistant

**The dashboard shows demo data.** Both a URL and a token are needed. Check **Test connection** on the settings page.

**`auth_failed` in the HUD.** The token was rejected. havenOS stops retrying on a bad token. Create a new long-lived token and save it.

**An entity does not show.** Only entities exposed to Assist and assigned to an area are shown. Fix that in Home Assistant, then wait up to five minutes. See [Home Assistant](home-assistant.md).

**The display is not discovered as an ESPHome device.**

- Check `[esphome] enabled = true` and that you restarted.
- Home Assistant discovers it over mDNS. Make sure both are on the same network segment, and that multicast is not blocked (some Wi-Fi isolation and VLAN setups do).
- Make sure nothing blocks TCP port 6053.
- You can add it manually in Home Assistant with the display's IP address and port 6053.
- Two devices with the same name collide. Set a unique `name`.

**Duplicate or missing entities after a reinstall.** The device identity is `~/.config/havenos/device_mac`. Keep that file when you move the install.

## Music

**AirPlay does not appear.** Check that `shairport-sync` was built with `--with-pipe --with-metadata --with-metadata-pipe`, that it is on `PATH` (or set `binary`), and that the music card shows it as available. On a Mac, use port 7100.

**AirPlay play, pause and next do nothing.** The sender does not offer remote control. Apple Music and iOS Music do; most third-party apps are display-only.

**Sendspin player missing in Music Assistant.** Check `[music.sendspin] enabled`, that mDNS reaches Music Assistant, and port 8928.

**Spotify never plays and the display shows a notice.** Spotify refuses audio keys to librespot-based clients on some accounts (`failed retrieving aes key with code 1`, go-librespot issues #279 and #317). There is no workaround. Send Spotify through AirPlay or Music Assistant instead. See [Spotify Connect](music/spotify.md).

**go-librespot not found.** Install it, or set `binary` / `HAVENOS_SPOTIFY_BINARY`.

**Sound comes out of the wrong device.** Choose the output under **Sound** on the settings page (or set `[music] audio_device` to part of the right device's name). Bluetooth headsets are a common cause: they are the system default and are not stereo.

**The Library button is missing.** It appears only when a Music Assistant URL is set. Playing needs Sendspin enabled.

## Photos

**Immich photos do not load.** Check the URL, key and album id with **Test connection**. If the server is down the screen keeps retrying every 10 seconds. Broken assets are skipped.

**Only the sample photos show.** Photos come from the `local` source unless Immich has both a URL and a key. Set `[photos] dir` or `HAVENOS_PHOTOS` for your own folder.

## Display and performance

**Blur is missing in screenshots.** Headless Qt (`QT_QUICK_BACKEND=software`) does not render the glass blur. That is a limit of the test environment. Judge the look in a real window.

**The glass effect does not work on a Pi.** `MultiEffect` needs Qt 6.5 or newer. Debian Bookworm ships 6.4. Use Trixie or the PySide6 wheel.

**High CPU while idle.** Check for an animation that never stops: an endless animator forces a redraw on every frame. The ambient screen's sun icon once did this and used about 145 % of a core; it now turns in short steps. The HUD (`f`) shows memory and loop lag.

## Web UI

**I do not know the sign-in code.** Tap the gear on the dashboard to show the pairing screen (a QR code, the address and the code). On first boot that screen is already up. The code is also in `~/.config/havenos/web_code`.

**Locked out.** Five wrong codes lock sign-in for 60 seconds.

## Still stuck

Run with more logging:

```bash
HAVENOS_LOG=DEBUG python -m havenos
```

and check the HUD for photo source, cached photos, Home Assistant status, memory and loop lag.
