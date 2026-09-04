#!/bin/bash
# Local dev server. Port 5000 is taken by macOS AirPlay, so default to 5055.
set -e
cd "$(dirname "$0")"
export PORT="${PORT:-5055}"
exec python3 app.py
