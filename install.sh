#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="/opt/havenos"
SERVICE_USER="havenos"
SKIP_PACKAGES=false
SKIP_NODE=false
SKIP_KIOSK=false
YES=false

usage() {
  cat <<EOF
Usage: sudo ./install.sh [OPTIONS]

Options:
  --yes            Non-interactive (accept all defaults)
  --user NAME      Service user name (default: havenos)
  --skip-packages  Skip apt package installation
  --skip-node      Skip Node.js installation via NodeSource
  --skip-kiosk     Skip Chromium kiosk service installation
  -h, --help       Show this help
EOF
  exit 0
}

# Parse flags
while [[ $# -gt 0 ]]; do
  case $1 in
    --yes) YES=true ;;
    --user) SERVICE_USER="$2"; shift ;;
    --skip-packages) SKIP_PACKAGES=true ;;
    --skip-node) SKIP_NODE=true ;;
    --skip-kiosk) SKIP_KIOSK=true ;;
    -h|--help) usage ;;
    *) echo "Unknown option: $1"; usage ;;
  esac
  shift
done

# ──────────────────────────────────────────────
# Preflight checks
# ──────────────────────────────────────────────
echo "=== havenOS Installer ==="

if [ "$EUID" -ne 0 ]; then
  echo "❌  Please run as root: sudo ./install.sh"
  exit 1
fi

# OS check
if ! grep -qi "raspberry\|debian\|ubuntu" /etc/os-release 2>/dev/null; then
  echo "⚠️  Unsupported OS. havenOS is designed for Raspberry Pi OS / Debian/Ubuntu."
  if [ "$YES" != "true" ]; then
    read -rp "Continue anyway? [y/N] " ans
    [[ "$ans" =~ ^[Yy]$ ]] || exit 1
  fi
fi

# Architecture check
ARCH=$(uname -m)
if [[ "$ARCH" != "aarch64" && "$ARCH" != "x86_64" && "$ARCH" != "armv7l" ]]; then
  echo "⚠️  Unexpected architecture: $ARCH"
fi

# Disk space check (require 2GB free)
FREE_KB=$(df /opt --output=avail 2>/dev/null | tail -1 || echo 0)
if [ "$FREE_KB" -lt 2097152 ]; then
  echo "❌  Insufficient disk space. Need at least 2GB free in /opt."
  exit 1
fi

# Network check
if ! curl -sf --max-time 5 https://deb.nodesource.com > /dev/null 2>&1; then
  echo "⚠️  Cannot reach deb.nodesource.com — check network connectivity."
fi

# ──────────────────────────────────────────────
# Step 1: System packages
# ──────────────────────────────────────────────
if [ "$SKIP_PACKAGES" != "true" ]; then
  echo ""
  echo "[1/6] Installing system packages..."
  apt-get update -qq
  apt-get install -y \
    ca-certificates curl git jq unzip rsync \
    build-essential \
    shairport-sync \
    chromium-browser
else
  echo "[1/6] Skipping system packages (--skip-packages)"
fi

# ──────────────────────────────────────────────
# Step 2: Node.js 20+ via NodeSource
# ──────────────────────────────────────────────
if [ "$SKIP_NODE" != "true" ]; then
  echo ""
  echo "[2/6] Installing Node.js 20 via NodeSource..."
  # Check if already at v20+
  if command -v node &>/dev/null && node -e "process.exit(parseInt(process.version.slice(1)) >= 20 ? 0 : 1)" 2>/dev/null; then
    echo "    Node.js $(node --version) already installed — skipping."
  else
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y nodejs
  fi
  echo "    Node.js $(node --version)  npm $(npm --version)"
else
  echo "[2/6] Skipping Node.js installation (--skip-node)"
fi

# ──────────────────────────────────────────────
# Step 3: Create service user
# ──────────────────────────────────────────────
echo ""
echo "[3/6] Creating service user '$SERVICE_USER'..."
id -u "$SERVICE_USER" &>/dev/null && echo "    User already exists — skipping." || \
  useradd -r -m -s /bin/false "$SERVICE_USER"

# ──────────────────────────────────────────────
# Step 4: Install havenOS files
# ──────────────────────────────────────────────
echo ""
echo "[4/6] Installing havenOS files to $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"
# rsync preserves structure, skips .git and node_modules
rsync -a --exclude='.git' --exclude='node_modules' --exclude='server/node_modules' \
  "$(dirname "$0")/" "$INSTALL_DIR/"
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"

# Build as root (npm needs write access to install dir)
echo "    Installing npm dependencies..."
cd "$INSTALL_DIR"
npm install --prefer-offline 2>&1 | tail -5
echo "    Building frontend..."
npm run build 2>&1 | tail -5

echo "    Building server..."
cd "$INSTALL_DIR/server"
npm install --prefer-offline 2>&1 | tail -5
npm run build 2>&1 | tail -5

# ──────────────────────────────────────────────
# Step 5: Create default config
# ──────────────────────────────────────────────
echo ""
echo "[5/6] Creating default config..."
CONFIG_DIR="/home/$SERVICE_USER/.havenOS"
CONFIG_FILE="$CONFIG_DIR/config.json"

if [ ! -f "$CONFIG_FILE" ]; then
  mkdir -p "$CONFIG_DIR"
  cat > "$CONFIG_FILE" << 'CONFIGEOF'
{
  "ha": { "url": "http://homeassistant.local:8123", "token": "" },
  "weather": { "entity": "weather.home" },
  "music": { "maUrl": "http://musicassistant.local:8095", "playerId": "" },
  "voice": { "host": "localhost", "port": 6053 },
  "immich": { "url": "http://immich.local:2283", "apiKey": "", "mode": "favorites", "albumId": "" },
  "display": { "name": "havenOS Display", "brightness": 100, "quietHoursStart": "22:00", "quietHoursEnd": "07:00", "theme": "auto", "accentColor": "blue" },
  "timers": { "chimeFile": "", "chimeVolume": 80 },
  "cycleInterval": 60,
  "haUrl": ""
}
CONFIGEOF
  chown -R "$SERVICE_USER:$SERVICE_USER" "$CONFIG_DIR"
  echo "    Config written to $CONFIG_FILE"
else
  echo "    Config already exists — skipping."
fi

# ──────────────────────────────────────────────
# Step 6: Systemd services
# ──────────────────────────────────────────────
echo ""
echo "[6/6] Installing systemd service files..."
cp "$INSTALL_DIR/systemd/havenos-server.service" /etc/systemd/system/havenos-server@.service

if [ "$SKIP_KIOSK" != "true" ]; then
  cp "$INSTALL_DIR/systemd/havenos-ui.service" /etc/systemd/system/havenos-ui@.service
fi

systemctl daemon-reload
systemctl enable "havenos-server@$SERVICE_USER"
systemctl start  "havenos-server@$SERVICE_USER" || true

if [ "$SKIP_KIOSK" != "true" ]; then
  systemctl enable "havenos-ui@$SERVICE_USER" || true
fi

# ──────────────────────────────────────────────
# Done
# ──────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   havenOS installation complete! ✅      ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "  Server:  systemctl status havenos-server@$SERVICE_USER"
echo "  Kiosk:   systemctl status havenos-ui@$SERVICE_USER"
echo "  Config:  /home/$SERVICE_USER/.havenOS/config.json"
echo ""
echo "Edit the config file to add your HA token and Immich API key."
