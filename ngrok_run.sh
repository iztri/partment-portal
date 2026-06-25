#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────
# Run the portal with ngrok tunnel (accessible from anywhere)
# Install ngrok: https://ngrok.com/download
# Usage:  bash ngrok_run.sh
# ──────────────────────────────────────────────────────────────────────────
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

if ! command -v ngrok &> /dev/null; then
  echo "✗ ngrok not found. Download from https://ngrok.com/download"
  echo ""
  echo "  Or install via:"
  echo "    brew install ngrok"
  echo ""
  exit 1
fi

echo "→ Starting Flask server on port 5000..."
python3 app.py &
FLASK_PID=$!
sleep 2

echo "→ Starting ngrok tunnel..."
echo ""
echo "═══════════════════════════════════════"
echo "  Open http://127.0.0.1:4040 to see    "
echo "  the ngrok URL in the web UI          "
echo "═══════════════════════════════════════"
echo ""
echo "  Press Ctrl+C to stop"
echo ""

ngrok http 5000

kill $FLASK_PID 2>/dev/null
