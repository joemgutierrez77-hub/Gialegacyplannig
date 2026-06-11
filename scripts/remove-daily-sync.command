#!/bin/bash
# Removes the scheduled daily FlowHub sync installed by setup-daily-sync.command.

LABEL="com.gialegacyplanning.flowhub-sync"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

if [ -f "$PLIST" ]; then
  launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
  rm "$PLIST"
  echo "✅ Daily sync removed. You can still sync manually with FlowHub.command."
else
  echo "Nothing to remove — the daily sync isn't installed."
fi
