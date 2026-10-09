#!/bin/sh
set -eu
PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then PYTHON_BIN=python3; fi
exec "$PYTHON_BIN" "$PROJECT_ROOT/scripts/build.py" --platform macos
