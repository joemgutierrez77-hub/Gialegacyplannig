#!/bin/bash
# Dashboard launcher (macOS) — double-click to refresh your live data and open
# the G.I.A. command center. Lives in the project root; works wherever the
# folder is moved.

cd "$(dirname "$0")" || exit 1

echo "G.I.A. Command Center — refreshing live data..."
if command -v python3 >/dev/null 2>&1; then
  if python3 main.py flowhub sync; then
    echo "Data refreshed — dashboard-data.js is up to date."
  else
    echo "Refresh failed — opening the dashboard with the last data on file."
  fi
else
  echo "python3 not found — opening the dashboard with the data on file."
fi

open "dashboard.html"
