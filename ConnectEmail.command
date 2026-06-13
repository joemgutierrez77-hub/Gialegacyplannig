#!/bin/bash
# Connect Email (macOS) — double-click to add an email account FlowHub will
# scan for carrier, recruit, and client messages. Repeat for each account.
# Your password is stored only on this Mac, in the gitignored .env file.

cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found — install it first, then try again."
  exit 1
fi

echo "This adds ONE email account. Run it again for each inbox you use."
echo ""
echo "IMPORTANT: you need an APP PASSWORD, not your normal email password."
echo "  • Gmail:    myaccount.google.com → Security → 2-Step Verification → App passwords"
echo "  • Outlook / Hotmail: account.microsoft.com → Security → Advanced security → App passwords"
echo ""

python3 main.py flowhub connect-email

echo ""
echo "When you've added all your accounts, double-click FlowHub.command to scan them."
read -rp "Press Return to close."
