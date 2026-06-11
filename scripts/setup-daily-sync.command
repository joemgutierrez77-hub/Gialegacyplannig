#!/bin/bash
# One-time setup (macOS) — schedules `python3 main.py flowhub sync` every
# morning at 7:00 so FlowHub always opens with fresh business data.
# Double-click to install. Run scripts/remove-daily-sync.command to undo.

set -e

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.gialegacyplanning.flowhub-sync"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/flowhub-sync.log"
PYTHON_BIN="$(command -v python3 || true)"

if [ -z "$PYTHON_BIN" ]; then
  echo "ERROR: python3 was not found on this Mac."
  echo "Install it from https://www.python.org/downloads/ and run this again."
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON_BIN</string>
    <string>main.py</string>
    <string>flowhub</string>
    <string>sync</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$REPO_DIR</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>7</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>$LOG</string>
  <key>StandardErrorPath</key>
  <string>$LOG</string>
</dict>
</plist>
EOF

# Reload the agent (bootout is harmless if it wasn't loaded yet)
launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"

# Run one sync right now so today's data is fresh too
(cd "$REPO_DIR" && "$PYTHON_BIN" main.py flowhub sync)

echo ""
echo "✅ Daily sync installed."
echo "   Your agency data now refreshes every morning at 7:00."
echo "   (If the Mac is asleep at 7:00, it catches up when it wakes.)"
echo "   Log file: $LOG"
echo "   To change the time, edit the Hour/Minute in this file and re-run it."
echo "   To remove it, double-click scripts/remove-daily-sync.command."
