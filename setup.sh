#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────
# Setup script for Apartment Detail Portal
# Run once:  bash setup.sh
# ──────────────────────────────────────────────────────────────────────────
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "═══ Apartment Detail Portal — Setup ═══"
echo ""

# 1. Install Python dependencies
echo "→ Installing Python packages..."
pip install -r requirements.txt
echo ""

# 2. Check for service_account.json
if [ ! -f service_account.json ]; then
  echo "⚠ WARNING: service_account.json not found!"
  echo ""
  echo "  You need a Google Service Account to access Google Sheets."
  echo ""
  echo "  Steps:"
  echo "    1. Go to https://console.cloud.google.com"
  echo "    2. Create a project (or use 'iztri-prod')"
  echo "    3. Enable 'Google Sheets API'"
  echo "    4. Go to Credentials → Create Credentials → Service Account"
  echo "    5. Name it 'apartment-portal' → Create → Done"
  echo "    6. Click the new service account → Keys → Add Key → JSON"
  echo "    7. Download the JSON and move it here as:"
  echo "       service_account.json"
  echo "    8. Create a Google Sheet, note its ID from the URL:"
  echo "       https://docs.google.com/spreadsheets/d/<SHEET_ID>/edit"
  echo "    9. Share the sheet with the service account email (Viewer+Editor)"
  echo "   10. Edit config.py → set SHEET_ID = '<your-sheet-id>'"
  echo ""
  echo "  Then re-run: python app.py"
  echo ""
  exit 1
fi

echo "✓ service_account.json found"

# 3. Validate config
if grep -q "YOUR_GOOGLE_SHEET_ID" config.py; then
  echo "⚠ WARNING: SHEET_ID is not set in config.py"
  echo "  Edit config.py and replace 'YOUR_GOOGLE_SHEET_ID' with your actual Sheet ID"
  exit 1
fi

echo "✓ SHEET_ID configured"
echo ""
echo "═══ Setup complete! ═══"
echo ""
echo "  Run the server:  python app.py"
echo "  Or with ngrok:   bash ngrok_run.sh"
echo ""
