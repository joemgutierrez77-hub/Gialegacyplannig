#!/bin/bash
# Connect GoHighLevel (macOS) — double-click to link your appointment funnel.
# Your API key is stored only on this Mac, in the gitignored .env file.

cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found — install it first, then try again."
  read -rp "Press Return to close."
  exit 1
fi

echo "=== Connect your GoHighLevel appointment funnel ==="
echo ""
echo "Where to find your API key:"
echo "  • GoHighLevel → Settings → Business Profile → API Key"
echo "  • Newer accounts: Settings → Private Integrations → create a token (pit-…)"
echo "    with calendar read scopes — you'll also need your Location ID"
echo "    (Settings → Business Profile)."
echo ""
echo "Your key is saved ONLY on this Mac (.env file) — never uploaded."
echo ""

python3 - <<'PY'
import sys
sys.path.insert(0, ".")
from src.modules.connectors import save_env_key

key = input("Paste your GoHighLevel API key: ").strip()
if not key:
    print("Nothing saved — no key entered.")
    sys.exit(0)
save_env_key("GHL_API_KEY", key)
if key.startswith("pit-"):
    loc = input("Private tokens also need your Location ID: ").strip()
    if loc:
        save_env_key("GHL_LOCATION_ID", loc)
print("\n✅ Saved. Pulling your appointments now…")
PY

echo ""
echo "Syncing agency data (this pulls your funnel appointments)…"
if python3 main.py flowhub sync; then
  echo ""
  echo "✅ Done! A fresh GIA-agency-data.json is in this folder."
  echo "   In your portal: Back Office → 📊 Import Agency Data (JSON) → pick that file."
  echo "   Your funnel appointments will appear on the calendar."
else
  echo "⚠️  Sync hit a problem — check the message above, then double-click this again."
fi
read -rp "Press Return to close."
