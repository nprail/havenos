#!/usr/bin/env bash
# Install havenOS on a fresh Raspberry Pi OS Lite (Debian 13 "trixie", 64-bit), as root. Safe to run again: it updates
# what is there and never overwrites /var/lib/havenos/config.toml.
#
#   curl -fsSL https://raw.githubusercontent.com/nprail/havenos/main/deploy/install.sh | sudo bash
#   sudo ./deploy/install.sh                       # from a checkout: installs that checkout
#   sudo ./deploy/install.sh --repo URL --ref TAG  # another fork, branch or tag
#   sudo ./deploy/install.sh --no-airplay          # skip the AirPlay 2 build (about 10 minutes on a Pi 4)
#
# What it does: apt packages (Debian's Qt 6.8 and PySide6: the pip PySide6 wheel cannot run EGLFS on aarch64, see
# docs/raspberry-pi.md, "Notes from bring-up"), the `havenos` user, the code in /opt/havenos, a venv that uses the system PySide6,
# nqptp + shairport-sync for AirPlay 2, a starter config, and the systemd units, which it enables and starts.
# Not done: Spotify Connect (needs the go-librespot binary, see docs/music/spotify.md), and picking a sound output
# (do that on the settings page, "Sound").
set -euo pipefail

REPO="${HAVENOS_REPO:-https://github.com/nprail/havenos}"
REF="${HAVENOS_REF:-main}"
SRC="${HAVENOS_SRC:-}"
PREFIX=/opt/havenos
STATE=/var/lib/havenos
AIRPLAY=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) REPO="$2"; shift 2 ;;
    --ref) REF="$2"; shift 2 ;;
    --src) SRC="$2"; shift 2 ;;
    --no-airplay) AIRPLAY=0; shift ;;
    -h|--help) sed -n 2,16p "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
done

say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
die() { echo "error: $*" >&2; exit 1; }
as_hv() { runuser -u havenos -- env HOME="$STATE" "$@"; }          # run as the service user (pip caches in its home)

[[ $EUID -eq 0 ]] || die "run as root: sudo $0"
. /etc/os-release
[[ "$(uname -m)" == aarch64 ]] || echo "warning: this is $(uname -m); havenOS is built for a 64-bit Raspberry Pi OS" >&2
[[ "${VERSION_CODENAME:-}" == trixie ]] || echo "warning: this is ${PRETTY_NAME:-unknown}, not Debian 13 (trixie). Debian's Qt must be 6.5 or newer." >&2

# When run from inside a checkout (not through curl | bash), install that checkout unless told otherwise.
if [[ -z "$SRC" && -n "${BASH_SOURCE[0]:-}" && -f "${BASH_SOURCE[0]}" ]]; then
  here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  [[ -f "$here/pyproject.toml" && -d "$here/src/havenos" ]] && SRC="$here"
fi

say "Packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
  git rsync ca-certificates curl python3 python3-venv python3-pip ffmpeg avahi-daemon avahi-utils libportaudio2 \
  libegl1 libgles2 libgbm1 libdrm2 libinput10 libxkbcommon0 libfontconfig1 libdbus-1-3 libglib2.0-0 \
  libasound2-plugins alsa-utils fonts-dejavu-core fonts-noto-color-emoji \
  qt6-qpa-plugins qt6-svg-plugins \
  python3-pyside6.qtcore python3-pyside6.qtgui python3-pyside6.qtqml python3-pyside6.qtquick python3-pyside6.qttest \
  qml6-module-qtquick qml6-module-qtquick-controls qml6-module-qtquick-effects qml6-module-qtquick-window \
  qml6-module-qtquick-templates qml6-module-qtquick-layouts qml6-module-qtqml qml6-module-qtqml-workerscript

say "User and directories"
id havenos >/dev/null 2>&1 || useradd --system --create-home --home-dir "$STATE" --groups audio havenos
usermod -aG audio,video,input,render havenos
install -d -m 755 /etc/havenos "$PREFIX"
install -d -o havenos -g havenos "$STATE"

say "havenOS code"
if [[ -n "$SRC" && "$(cd "$SRC" && pwd)" == "$PREFIX" ]]; then
  echo "already in $PREFIX"
elif [[ -n "$SRC" ]]; then
  echo "from $SRC"
  rsync -a --delete --exclude .venv --exclude .venv-sys --exclude node_modules --exclude site --exclude .git \
    --exclude __pycache__ --exclude .pytest_cache --exclude .local --exclude '*.pyc' "$SRC"/ "$PREFIX"/
elif [[ -d "$PREFIX/.git" ]]; then
  echo "updating $PREFIX from $REPO ($REF)"
  git -C "$PREFIX" fetch --depth 1 origin "$REF"
  git -C "$PREFIX" checkout -q --force FETCH_HEAD
else
  echo "cloning $REPO ($REF)"
  tmp="$(mktemp -d)"
  git clone --depth 1 --branch "$REF" "$REPO" "$tmp" || die "could not clone $REPO at $REF (use --src DIR to install a local copy)"
  rsync -a --exclude .venv-sys "$tmp"/ "$PREFIX"/
  rm -rf "$tmp"
fi
[[ -f "$PREFIX/pyproject.toml" ]] || die "$PREFIX has no pyproject.toml"
chown -R havenos:havenos "$PREFIX"

say "Python environment (Debian's PySide6, everything else from PyPI)"
cd "$PREFIX"
[[ -x .venv-sys/bin/python ]] || as_hv python3 -m venv --system-site-packages .venv-sys
# The dependencies come from pyproject.toml, minus PySide6 (the system one is used; the wheel would shadow it).
mapfile -t deps < <(.venv-sys/bin/python - <<'PY'
import tomllib
p = tomllib.load(open("pyproject.toml", "rb"))["project"]
out = list(p["dependencies"]) + list(p.get("optional-dependencies", {}).get("voice", []))
print("\n".join(d for d in out if not d.lower().startswith("pyside6")))
PY
)
as_hv .venv-sys/bin/pip install --quiet --upgrade pip
as_hv .venv-sys/bin/pip install --quiet "${deps[@]}"
as_hv .venv-sys/bin/pip install --quiet --no-deps -e .
as_hv .venv-sys/bin/python -c "from PySide6 import QtQuick, QtCore; print('Qt', QtCore.qVersion())"

say "Music: AirPlay 2 (nqptp + shairport-sync)"
if [[ $AIRPLAY == 1 ]]; then
  bash "$PREFIX/deploy/install-music.sh" airplay
else
  echo "skipped (--no-airplay)"
fi

say "Configuration"
if [[ -f "$STATE/config.toml" ]]; then
  echo "$STATE/config.toml exists: left as it is"
else
  {
    echo "# Written by deploy/install.sh. The settings page (http://<this device>:8787) edits this file."
    echo "[web]"; echo "enabled = true"; echo 'host = "0.0.0.0"'; echo "port = 8787"; echo
    if [[ $AIRPLAY == 1 ]]; then
      echo "[music.airplay]"; echo "enabled = true"; echo "manage = false          # shairport-sync runs as its own unit"; echo
    fi
    echo "[music.sendspin]"; echo "enabled = true"
  } > "$STATE/config.toml"
  chown havenos:havenos "$STATE/config.toml"; chmod 600 "$STATE/config.toml"
  echo "wrote $STATE/config.toml"
fi

say "Services"
mkdir -p /var/log/journal                       # keep logs across reboots (a crash is otherwise gone)
systemd-tmpfiles --create --prefix /var/log/journal || true
systemctl restart systemd-journald || true
journalctl --flush || true
install -m 644 "$PREFIX/deploy/havenos.service" /etc/systemd/system/havenos.service
systemctl daemon-reload
units=(havenos)
[[ $AIRPLAY == 1 ]] && units=(nqptp shairport-sync havenos)
systemctl enable "${units[@]}"
systemctl restart "${units[@]}"
sleep 20
systemctl --no-pager --plain list-units "${units[@]/%/.service}" --no-legend || true

ip="$(hostname -I | awk '{print $1}')"
code="$(journalctl -u havenos --no-pager -n 200 2>/dev/null | grep -o 'setup code: [A-Z0-9-]*' | tail -1 || true)"
say "Done"
echo "Settings page: http://${ip:-<this device>}:8787   (${code:-setup code: shown on the device (the QR code on first boot, or the gear on the dashboard), or in: journalctl -u havenos})"
echo "Pick the speaker under Settings > Sound. Logs: journalctl -u havenos -f"
if ! compgen -G "/sys/class/drm/card*-*/status" >/dev/null || ! grep -qx connected /sys/class/drm/card*-*/status 2>/dev/null; then
  echo "No display is connected: havenOS needs one to start. Connect it and reboot (a display plugged in later is not picked up)."
fi
