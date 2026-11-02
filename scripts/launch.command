#!/bin/bash
# havenOS (Python core + Qt Quick, one process). Run from anywhere; it works from the project root.
cd "$(dirname "$0")/.." || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
PY=$(command -v python3.12 || command -v python3.13 || command -v python3)
[ -d .venv ] || "$PY" -m venv .venv
. .venv/bin/activate
python -c "import PySide6, PIL" 2>/dev/null || pip install -e '.[dev]'
HAVENOS_STATS=${HAVENOS_STATS:-1} python -m havenos
