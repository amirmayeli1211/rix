#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
exec python3 app.py --host "${HOST:-127.0.0.1}" --port "${PORT:-8765}"
