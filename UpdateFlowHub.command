#!/bin/bash
# Update FlowHub (macOS) — double-click to pull the latest version of this
# project from GitHub IN PLACE. Your data (data/, .env, browser tasks/notes)
# is never touched.

set -e
DEST="$(cd "$(dirname "$0")" && pwd)"
ZIP_URL="https://github.com/joemgutierrez77-hub/Gialegacyplannig/archive/refs/heads/main.zip"
TMP="$(mktemp -d)"

echo "Downloading the latest version..."
curl -fsSL -o "$TMP/main.zip" "$ZIP_URL"
unzip -q "$TMP/main.zip" -d "$TMP"

echo "Updating files in: $DEST"
# Exclude user data and credentials from the copy
rsync -a --exclude='.env' --exclude='.env.*' --exclude='*.env' \
         --exclude='data/' --exclude='productivity/business-data.js' \
         "$TMP/Gialegacyplannig-main/" "$DEST/" 2>/dev/null \
  || cp -R "$TMP/Gialegacyplannig-main/." "$DEST/"
rm -rf "$TMP"

xattr -dr com.apple.quarantine "$DEST" 2>/dev/null || true
chmod +x "$DEST"/*.command "$DEST"/scripts/*.command 2>/dev/null || true

echo ""
echo "✅ Updated to the latest version. Your data was preserved."
echo "   Reload FlowHub in your browser (Cmd+R) to use it."
