#!/bin/bash
# GIA Text (macOS) — double-click to send each recruit their own personal text
# through the Messages app on this Mac (which sends through your iPhone).
#
# Your list lives in data/gia-text-list.txt, one person per line:  Name|+15551234567
# Your message lives in data/gia-text-message.txt — {first_name} is filled in for you.
# Both stay only on this Mac (data/ is gitignored and kept by UpdateFlowHub).
# Anyone already texted with the same message is skipped, so re-running is safe.

cd "$(dirname "$0")" || exit 1
mkdir -p data
LIST="data/gia-text-list.txt"
MSG_FILE="data/gia-text-message.txt"
SENT_LOG="data/gia-text-sent.log"
DELAY_SECONDS=4

if [ ! -s "$MSG_FILE" ]; then
  cat > "$MSG_FILE" <<'EOF'
Hi {first_name}, it's Joe with GIA Legacy Planning.

Thanks for applying for Remote-Life Insurance Sales Professional-Entrepreneurial Opportunity!

Book your 30-min virtual interview here: https://calendly.com/joeg-11/group-interviews-symmtery-financial-group Reply STOP to opt out

--
Joe Gutierrez
GIA Legacy Planning
EOF
fi

if [ ! -s "$LIST" ]; then
  cat > "$LIST" <<'EOF'
# Paste your list below (one per line), then Save (Cmd+S) and close this window.
# Format:  Name|+15551234567
EOF
fi

echo "Opening your text list. Paste the names/numbers, press Cmd+S, then come back here."
open -e "$LIST"
read -rp "Press Return when your list is saved... "

MESSAGE_TEMPLATE="$(cat "$MSG_FILE")"
names=(); phones=()
while IFS='|' read -r name phone || [ -n "$name" ]; do
  name="$(echo "$name" | xargs)"; phone="$(echo "$phone" | tr -cd '+0-9')"
  [ -z "$name" ] && continue
  case "$name" in \#*) continue ;; esac
  if [ -z "$phone" ]; then echo "⚠️  Skipping \"$name\" — no phone number."; continue; fi
  names+=("$name"); phones+=("$phone")
done < "$LIST"

if [ ${#names[@]} -eq 0 ]; then
  echo "No one on the list. Add lines like  Reymundo|+17864438678  and run again."
  read -rp "Press Return to close."; exit 0
fi

# Fingerprint the message so editing it lets you re-send to the same people.
MSG_ID="$(printf '%s' "$MESSAGE_TEMPLATE" | shasum | cut -c1-10)"
touch "$SENT_LOG"

echo ""
echo "Preview (first person):"
echo "----------------------------------------"
first="${names[0]%% *}"
echo "${MESSAGE_TEMPLATE//\{first_name\}/$first}"
echo "----------------------------------------"
echo ""
queue=()
for i in "${!names[@]}"; do
  if grep -q "^${phones[$i]}|$MSG_ID|" "$SENT_LOG"; then
    echo "  ⏭  ${names[$i]} (${phones[$i]}) — already sent this message"
  else
    echo "  •  ${names[$i]} (${phones[$i]})"; queue+=("$i")
  fi
done

if [ ${#queue[@]} -eq 0 ]; then
  echo ""; echo "Everyone on the list already got this message."
  read -rp "Press Return to close."; exit 0
fi

echo ""
read -rp "Send ${#queue[@]} individual text(s) now? Type y and press Return: " ok
[ "$ok" = "y" ] || [ "$ok" = "Y" ] || { echo "Cancelled — nothing sent."; read -rp "Press Return to close."; exit 0; }

sent=0; failed=0
for i in "${queue[@]}"; do
  first="${names[$i]%% *}"
  body="${MESSAGE_TEMPLATE//\{first_name\}/$first}"
  # Try SMS through your iPhone first (works for every phone), then iMessage.
  result="$(osascript - "${phones[$i]}" "$body" <<'APPLESCRIPT' 2>&1
on run argv
  set targetPhone to item 1 of argv
  set targetMessage to item 2 of argv
  tell application "Messages"
    try
      set smsAccount to first account whose service type = SMS and enabled is true
      send targetMessage to participant targetPhone of smsAccount
      return "SMS"
    on error
      set imAccount to first account whose service type = iMessage
      send targetMessage to participant targetPhone of imAccount
      return "iMessage"
    end try
  end tell
end run
APPLESCRIPT
)"
  if [ $? -eq 0 ]; then
    echo "  ✅ ${names[$i]} — sent ($result)"
    echo "${phones[$i]}|$MSG_ID|$(date '+%Y-%m-%d %H:%M')|${names[$i]}" >> "$SENT_LOG"
    sent=$((sent + 1))
  else
    echo "  ❌ ${names[$i]} — not sent: $result"
    failed=$((failed + 1))
  fi
  sleep "$DELAY_SECONDS"
done

echo ""
echo "Done: $sent sent, $failed failed."
if [ $failed -gt 0 ]; then
  echo "If every text failed: open System Settings → Privacy & Security → Automation"
  echo "and allow Terminal to control Messages. On your iPhone: Settings → Messages →"
  echo "Text Message Forwarding → turn ON this Mac."
fi
read -rp "Press Return to close."
