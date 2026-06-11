#!/bin/bash
# FlowHub launcher (macOS) — double-click to sync business data and open the app.
# Lives in the project root; works no matter where the folder is moved.

cd "$(dirname "$0")" || exit 1

echo "FlowHub — syncing agency data..."
if command -v python3 >/dev/null 2>&1; then
  if python3 main.py flowhub sync; then
    echo "Sync complete."
  else
    echo "Sync failed — opening FlowHub with the last synced data."
  fi
else
  echo "python3 not found — opening FlowHub without syncing."
fi

open "productivity/index.html"
