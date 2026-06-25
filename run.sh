#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────
# Run the portal on local network (phone + laptop on same WiFi)
# Usage:  bash run.sh [port]
# Default port: 5000
# ──────────────────────────────────────────────────────────────────────────
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

PORT=${1:-5000}

echo "═══ Apartment Detail Portal ═══"
echo ""

# Get local IP
if [[ "$OSTYPE" == "darwin"* ]]; then
  IP=$(ipconfig getifaddr en0 2>/dev/null || ifconfig | grep "inet " | grep -v 127.0.0.1 | awk '{print $2}' | head -1)
else
  IP=$(hostname -I | awk '{print $1}')
fi

echo "  Local URL:    http://127.0.0.1:$PORT"
echo "  Network URL:  http://$IP:$PORT"
echo ""
echo "  Other users on same WiFi can open the Network URL above"
echo "  Press Ctrl+C to stop"
echo ""

PORT=$PORT python app.py
