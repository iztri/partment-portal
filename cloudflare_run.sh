#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────
# Run the portal via Cloudflare Tunnel (free, no random stranger access)
# Install:  brew install cloudflared
# Usage:    bash cloudflare_run.sh
# ──────────────────────────────────────────────────────────────────────────
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

if ! command -v cloudflared &> /dev/null; then
  echo "✗ cloudflared not found."
  echo ""
  echo "  Install it:"
  echo "    macOS: brew install cloudflared"
  echo "    Linux: curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared"
  echo "    Or download from: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
  echo ""
  echo "  Then re-run: bash cloudflare_run.sh"
  exit 1
fi

echo "→ Starting Flask server on port 5000..."
python3 app.py &
FLASK_PID=$!
sleep 2

echo "→ Starting Cloudflare Tunnel..."
echo ""
echo "═══════════════════════════════════════"
echo "  Tunnel URL will appear below:       "
echo "  (it's a https://xxxx.trycloudflare.com URL)"
echo "═══════════════════════════════════════"
echo ""
echo "  Press Ctrl+C to stop"
echo ""

cloudflared tunnel --url http://127.0.0.1:5000

# Cleanup
kill $FLASK_PID 2>/dev/null
