#!/bin/bash
# Import Reports (macOS) — double-click, pick the report type, drag the CSV in.
# Imports into the agency data files, then refreshes FlowHub automatically.

cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found — install it first (it comes with Apple's developer tools)."
  exit 1
fi

echo "Which report are you importing?"
echo "  1) Combined report — one file with a Status column (pending/issued/chargeback mixed)"
echo "  2) Submitted / pending applications only"
echo "  3) Issued policies only"
echo "  4) Chargebacks only"
read -rp "Enter 1, 2, 3 or 4: " choice

case "$choice" in
  1) action="import-all" ;;
  2) action="import-pending" ;;
  3) action="import-policies" ;;
  4) action="import-chargebacks" ;;
  *) echo "Please run again and enter 1, 2, 3 or 4."; exit 1 ;;
esac

echo ""
echo "Now DRAG the CSV file from Finder into this window, then press Return:"
read -r rawpath
# Dragged paths arrive backslash-escaped (spaces, parens, etc). macOS paths don't
# contain literal backslashes, so removing them safely unescapes the whole path.
file="${rawpath//\\/}"

if [ ! -f "$file" ]; then
  echo "Could not find a file at: $file"
  echo "Try again — make sure to drag the file itself, not a folder."
  exit 1
fi

python3 main.py flowhub "$action" --file "$file" || exit 1
echo ""
python3 main.py flowhub sync
echo ""
echo "✅ Done — reload FlowHub in your browser to see the update."
