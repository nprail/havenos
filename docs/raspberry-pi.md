# Installing on a Raspberry Pi

> **Tested on one Pi so far:** a Raspberry Pi 4 (2 GB) with an 800x480 DSI touch panel, on Trixie. The app, touch, AirPlay 2, Sendspin and a real Home Assistant work there. Not yet done: an install from a blank card, Spotify, voice (no microphone was attached), and the performance gates. Read each script before you run it.

## Target

A Raspberry Pi 4 with a DSI or HDMI display, running a 64-bit Raspberry Pi OS. The UI uses Qt's `MultiEffect` for the glass look, which needs **Qt 6.5 or newer**. Debian Bookworm ships Qt 6.4, so use Trixie (Qt 6.8). **Use Trixie's own PySide6, not the pip wheel:** the PySide6 6.12 aarch64 wheel lacks `libQt6EglFsKmsGbmSupport`, so EGLFS cannot start with it (see [Notes from bring-up](#notes-from-bring-up)).

havenOS runs without a desktop or compositor: Qt draws straight to the display through EGLFS (`QT_QPA_PLATFORM=eglfs`).

## Layout used by the units

| Path | What |
|---|---|
| `/opt/havenos` | The project, with `.venv` inside |
| `/var/lib/havenos` | State: `config.toml`, secrets, pairing, device identity, the music pipes |
| `/etc/havenos` | Configs for shairport-sync and go-librespot |
| user `havenos` | Owns state; in the groups `audio video input render` |

## Quick install

On a fresh Raspberry Pi OS Lite (Trixie, 64-bit), with the display connected:

```bash
curl -fsSL https://raw.githubusercontent.com/nprail/havenos/main/deploy/install.sh | sudo bash
```

Or from a copy of the project: `sudo ./deploy/install.sh` (add `--no-airplay` to skip the roughly ten-minute AirPlay 2 build, `--repo URL --ref TAG` for a fork or tag, `--src DIR` for a local copy). The script installs the packages below, creates the `havenos` user, puts the code in `/opt/havenos`, builds the venv, builds nqptp and shairport-sync, writes a starter `/var/lib/havenos/config.toml` (never overwriting an existing one), then enables and starts the services. It is safe to run again to update. It does not install Spotify Connect (needs the go-librespot binary). Then open the settings page it prints and choose the speaker under **Sound**.

> The script was run on the existing Pi, which already had everything, so it is checked for an update re-run but **not yet from a blank card**.

The rest of this page is the same thing by hand.

## 1. Put the app on the Pi

By hand:

```bash
sudo useradd --system --create-home --home-dir /var/lib/havenos --groups audio havenos
sudo mkdir -p /opt/havenos && sudo chown "$USER" /opt/havenos
git clone <your copy of the project> /opt/havenos     # or copy the folder across
cd /opt/havenos
sudo apt-get install -y --no-install-recommends git python3-venv python3-pip ffmpeg avahi-daemon libportaudio2 \
  libegl1 libgles2 libgbm1 libdrm2 libinput10 libxkbcommon0 libfontconfig1 libasound2-plugins alsa-utils \
  qt6-qpa-plugins qt6-svg-plugins python3-pyside6.qtcore python3-pyside6.qtgui python3-pyside6.qtqml python3-pyside6.qtquick \
  qml6-module-qtquick qml6-module-qtquick-controls qml6-module-qtquick-effects qml6-module-qtquick-window \
  qml6-module-qtquick-templates qml6-module-qtquick-layouts qml6-module-qtqml qml6-module-qtqml-workerscript
python3 -m venv --system-site-packages .venv-sys     # system PySide6; do not let pip install the PySide6 wheel
.venv-sys/bin/pip install Pillow aiohttp qasync tomli-w aioesphomeapi zeroconf "aiosendspin>=10.2.2,<11" sounddevice numpy pymicro-wakeword
.venv-sys/bin/pip install --no-deps -e .
```

`qt6-svg-plugins` is needed or every icon fails to load. For development on the Pi (tests), a normal `.venv` with `pip install -e ".[dev]"` also works, but it cannot run EGLFS.

Python 3.12 or newer is required.

## 2. Install the music daemons (optional)

`deploy/install-music.sh` builds nqptp and shairport-sync with AirPlay 2, installs the go-librespot config and installs the systemd units.

```bash
sudo deploy/install-music.sh            # AirPlay 2 and go-librespot
sudo deploy/install-music.sh airplay    # only AirPlay 2
```

For Spotify, download the go-librespot release for your architecture into `/usr/local/bin` first; otherwise the script skips it. Remember that [Spotify Connect only works on some accounts](music/spotify.md).

| File | Purpose |
|---|---|
| `nqptp.service`, `shairport-sync.service`, `shairport-sync.conf` | AirPlay 2 receiver writing PCM and metadata to pipes in `/var/lib/havenos/airplay/` |
| `go-librespot.service`, `go-librespot/config.yml` | Spotify Connect writing PCM to `/var/lib/havenos/spotify/audio.pipe`, API on 127.0.0.1:3678 |
| `havenos.service` | The display app |

## 3. Configure

`/var/lib/havenos/config.toml`, for the unit layout above:

```toml
[music.airplay]
enabled = true
manage = false          # shairport-sync runs as its own unit

[music.spotify]
enabled = true
manage = false

[music.sendspin]
enabled = true          # in-process; nothing to install

[music.assistant]
url = "http://homeassistant.local:8095"
token_file = "/var/lib/havenos/ma_token"
```

Keep the pipe paths in the unit files, the shairport-sync config and the go-librespot config identical to the state directory the app uses (the directory of `HAVENOS_CONFIG`). The adapters read their FIFOs from there.

## 4. Start

```bash
sudo systemctl enable --now nqptp shairport-sync go-librespot havenos
```

`havenos.service` sets `HAVENOS_CONFIG=/var/lib/havenos/config.toml`, `QT_QPA_PLATFORM=eglfs`, `QT_QPA_EGLFS_HIDECURSOR=1` (a touch screen needs no pointer) and `HAVENOS_FULLSCREEN=1`, and restarts on failure after 3 seconds. Its `ExecStart` points at `/opt/havenos/.venv-sys/bin/python`, so adjust it if you installed elsewhere.

Open `http://<pi-address>:8787` for the [settings page](settings-ui.md). On first boot the display shows a QR code: scan it with your phone to sign in and follow the guided setup. The address and code are written under it, and the gear on the dashboard shows it again.

## Notes from bring-up

Things that went wrong on the first Pi, and what the install script does about them:

- **Use Debian's PySide6, not the pip wheel.** The PySide6 6.12 aarch64 wheel lacks `libQt6EglFsKmsGbmSupport`, so EGLFS cannot start with it (`Failed to load EGL device integration "eglfs_kms"`). Install `python3-pyside6.*` from apt and a venv with `--system-site-packages`.
- **Icons need `qt6-svg-plugins`.** Without it every SVG icon logs `Unsupported image format`.
- **A display must be connected at start.** With no screen the app exits with `Cannot create window: no screens available`. A display plugged in later needs a restart (or reboot). The service restarts itself every few seconds until one is there.
- **The touch controller shows up as a mouse**, so EGLFS draws a cursor. The unit sets `QT_QPA_EGLFS_HIDECURSOR=1`.
- **The photo pool's two worker processes can outlive a crashed main process** when run by hand (systemd cleans them up on stop).
- **mDNS:** AirPlay and Sendspin need `avahi-daemon`. Check what the Pi advertises with `avahi-browse -art` (package `avahi-utils`).
- **Logs:** a Pi image has no persistent journal. `install.sh` turns it on (`/var/log/journal`), so a crash or a Wi-Fi drop leaves a trail.
- **Wi-Fi:** if the display drops off the network, Wi-Fi power saving is a common cause on a Pi (`nmcli connection modify <name> 802-11-wireless.powersave 2`).
- **Memory:** about 300 MB resident for the main process plus about 110 MB for each of two photo workers, in the first minutes on a 2 GB Pi 4. Boot to the settings page answering takes about a minute (25 s system, the rest the app).

## What is not done yet

These come from the project's open list:

- Real backlight and screen power. Today brightness is software dimming (a DSI panel's backlight is at `/sys/class/backlight/`).
- A watchdog that restarts a hung interface.
- The Pi gates: idle memory under 350 MB with no growth over 12 hours, at most one slow frame per 10 seconds, boot to first photo under 18 seconds, hung-GUI recovery under 15 seconds.
- Software echo cancellation for the wake word, if a microphone board turns out to need it.

Mac numbers (about 180 MB resident, 2 to 6 % of a core idle) say nothing about Pi performance. See the [specs](specs/03-qt-python-single.md) for the gates and the plan.
