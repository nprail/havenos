#!/bin/bash
# havenOS against fake Home Assistant + fake Immich (scripts/dev_servers.py). Try real integrations without real servers.
cd "$(dirname "$0")/.." || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
[ -d .venv ] || { echo "run scripts/launch.command once first to create the venv"; exit 1; }
. .venv/bin/activate
python scripts/dev_servers.py &
SERVERS=$!
trap 'kill $SERVERS 2>/dev/null' EXIT
sleep 1
# State (pairing code, device id, saved settings) goes in the ignored .local/dev, not next to the scripts.
mkdir -p .local/dev && cp scripts/dev-config.toml .local/dev/config.toml
HAVENOS_CONFIG=.local/dev/config.toml HAVENOS_STATS=${HAVENOS_STATS:-1} python -m havenos
