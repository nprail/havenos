#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="/opt/havenos"
SERVICE_USER="havenos"

echo "=== havenOS Installer ==="

# Check running as root
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (sudo ./install.sh)"
  exit 1
fi

# Install system dependencies
echo "[1/6] Installing system packages..."
apt-get update -qq
apt-get install -y curl git nodejs npm chromium-browser

# Create user
echo "[2/6] Creating service user..."
id -u $SERVICE_USER &>/dev/null || useradd -r -s /bin/false $SERVICE_USER

# Copy files
echo "[3/6] Installing havenOS files..."
mkdir -p $INSTALL_DIR
cp -r . $INSTALL_DIR/
chown -R $SERVICE_USER:$SERVICE_USER $INSTALL_DIR

# Install dependencies and build
echo "[4/6] Building frontend..."
cd $INSTALL_DIR
npm install
npm run build

# Install server dependencies
echo "[5/6] Installing server..."
cd $INSTALL_DIR/server
npm install
npm run build

# Install systemd services
echo "[6/6] Installing systemd services..."
cp $INSTALL_DIR/systemd/havenos-server.service /etc/systemd/system/havenos-server@.service
cp $INSTALL_DIR/systemd/havenos-ui.service /etc/systemd/system/havenos-ui@.service
systemctl daemon-reload
systemctl enable havenos-server@$SERVICE_USER
systemctl enable havenos-ui@$SERVICE_USER
systemctl start havenos-server@$SERVICE_USER

echo ""
echo "=== Installation complete! ==="
echo "havenOS is now running."
echo "Run: systemctl status havenos-server@$SERVICE_USER"
