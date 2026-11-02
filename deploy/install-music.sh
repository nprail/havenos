#!/usr/bin/env bash
# Install the music daemons on a Raspberry Pi OS (Debian bookworm or newer) device, as root.
# Run once on a Raspberry Pi 4 (the airplay part; go-librespot is not installed by it). Read it before running.
#
#   sudo ./install-music.sh            # AirPlay 2 (nqptp + shairport-sync) and go-librespot
#   sudo ./install-music.sh airplay    # only AirPlay 2
set -euo pipefail
what="${1:-all}"
here="$(cd "$(dirname "$0")" && pwd)"

id havenos >/dev/null 2>&1 || useradd --system --create-home --home-dir /var/lib/havenos --groups audio havenos
install -d -m 755 /etc/havenos /var/lib/havenos

build_airplay=1
if [[ -x /usr/local/bin/shairport-sync && -x /usr/local/bin/nqptp && "${FORCE_REBUILD:-0}" != 1 ]]; then
  echo "shairport-sync and nqptp are already installed: skipping the build (FORCE_REBUILD=1 to rebuild)"
  build_airplay=0
fi

if [[ "$what" == all || "$what" == airplay ]]; then
  if [[ $build_airplay == 1 ]]; then
  apt-get update
  apt-get install -y --no-install-recommends build-essential git autoconf automake libtool pkg-config xxd \
    libpopt-dev libconfig-dev libssl-dev libsoxr-dev libavahi-client-dev avahi-daemon libplist-dev libsodium-dev \
    libgcrypt-dev libavutil-dev libavcodec-dev libavformat-dev uuid-dev libglib2.0-dev libplist-utils
  work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
  git clone --depth 1 https://github.com/mikebrady/nqptp.git "$work/nqptp"
  (cd "$work/nqptp" && autoreconf -fi && ./configure --with-systemd-startup=no && make && make install)
  git clone --depth 1 https://github.com/mikebrady/shairport-sync.git "$work/ssync"
  (cd "$work/ssync" && autoreconf -fi && \
    ./configure --sysconfdir=/etc --with-pipe --with-metadata --with-airplay-2 --with-ssl=openssl --with-avahi --with-soxr && \
    make && make install)
  fi
  install -m 644 "$here/shairport-sync.conf" /etc/havenos/shairport-sync.conf
  install -m 644 "$here/nqptp.service" "$here/shairport-sync.service" /etc/systemd/system/
fi

if [[ "$what" == all ]]; then
  # go-librespot publishes release tarballs per architecture (https://github.com/devgianlu/go-librespot/releases):
  # put the linux arm64 (or armv6) binary in /usr/local/bin first, then run this script.
  if [[ ! -x /usr/local/bin/go-librespot ]]; then
    echo "go-librespot is not in /usr/local/bin: skipping Spotify Connect" >&2
  else
    install -d -m 755 /etc/havenos/go-librespot
    install -m 644 "$here/go-librespot/config.yml" /etc/havenos/go-librespot/config.yml
    install -d -o havenos -g havenos /var/lib/havenos/spotify
    install -m 644 "$here/go-librespot.service" /etc/systemd/system/
  fi
fi

install -m 644 "$here/havenos.service" /etc/systemd/system/
systemctl daemon-reload
echo "Installed. Set manage = false under [music.airplay] and [music.spotify] in /var/lib/havenos/config.toml, then:"
echo "  systemctl enable --now nqptp shairport-sync go-librespot havenos"
