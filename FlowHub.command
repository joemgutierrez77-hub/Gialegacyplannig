#!/bin/bash
# GIA Command launcher (macOS) — double-click to auto-update, sync, and open.
# Lives in the project root; works no matter where the folder is moved.

cd "$(dirname "$0")" || exit 1

echo "GIA Command — checking for updates..."
if command -v git >/dev/null 2>&1 && [ -d .git ]; then
  if git pull --ff-only >/dev/null 2>&1; then
    echo "You're on the latest version."
  else
    echo "Couldn't auto-update (offline or local changes) — opening current version."
  fi
fi

echo "GIA Command — syncing agency data..."
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
