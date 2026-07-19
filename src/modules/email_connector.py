"""
Email connector — surface carrier, recruit, and client emails as FlowHub
tasks plus a daily inbox digest.

Uses IMAP, so it works with Gmail, Outlook / Microsoft 365, and Hotmail using
only an email address + app password per account (no OAuth app registration).

Everything runs locally on your Mac. Email contents are never uploaded or
committed — only the derived tasks and a short digest land in
productivity/business-data.js (which is gitignored).

Credentials live in .env (gitignored), one line per account:
  EMAIL_ACCOUNT_1=gmail|you@gmail.com|app-password-here
  EMAIL_ACCOUNT_2=outlook|you@company.com|app-password-here
  EMAIL_ACCOUNT_3=hotmail|you@hotmail.com|app-password-here
"""

import hashlib
import json
import os
import re
from datetime import date, timedelta

from config.settings import DATA_DIR

ENV_FILE = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
SEEN_FILE = os.path.join(DATA_DIR, "email", "seen.json")

IMAP_HOSTS = {
    "gmail":     "imap.gmail.com",
    "outlook":   "outlook.office365.com",
    "office365": "outlook.office365.com",
    "microsoft": "outlook.office365.com",
    "hotmail":   "outlook.office365.com",
    "live":      "outlook.office365.com",
    "yahoo":     "imap.mail.yahoo.com",
}

# Carrier name/domain tokens drawn from the agency's actual book of business.
CARRIER_TOKENS = [
    "mutual of omaha", "mutualofomaha", "omaha", "aig", "corebridge", "americo",
    "national life", "nationallife", "nlg", "fidelity and guaranty", "fglife", "f&g",
    "american amicable", "amaminsurance", "assurity", "transamerica",
    "lafayette life", "american equity", "americanequity", "amerilife",
    "underwriting", "newbusiness", "new business", "policyservice", "policy service",
]

# Subject/body keywords that bump a carrier email to high priority.
URGENT_KEYWORDS = [
    "declined", "denied", "requirement", "outstanding", "action required",
    "action needed", "needs", "missing", "lapse", "lapsed", "cancel", "cancelled",
    "nsf", "returned", "draft failed", "payment failed", "past due", "not taken",
    "rejected", "incomplete", "expire", "expiring", "reinstate",
]
# Keywords that still make a carrier email worth a task, at medium priority.
INFO_KEYWORDS = [
    "approved", "issued", "in force", "inforce", "underwriting", "pending",
    "received", "policy", "premium", "payment", "update", "status", "submitted",
]


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------

def load_email_accounts() -> list:
    """Parse EMAIL_ACCOUNT_* lines from .env into account dicts.

    Two on-disk formats are accepted:
      provider|address|password               (legacy, host from provider map)
      provider|address|host|password          (explicit IMAP host; host may be
                                                empty to fall back to the map)
    """
    accounts = []
    path = os.path.abspath(ENV_FILE)
    if not os.path.exists(path):
        return accounts
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line.startswith("EMAIL_ACCOUNT_") or "=" not in line:
                continue
            _, val = line.split("=", 1)
            val = val.strip().strip('"').strip("'")
            parts = val.split("|")
            if len(parts) == 3:
                provider, address, password = parts[0], parts[1], parts[2]
                host = ""
            elif len(parts) >= 4:
                provider, address, host = parts[0], parts[1], parts[2]
                password = "|".join(parts[3:])  # password may contain '|'
            else:
                continue
            provider = provider.strip().lower()
            accounts.append({
                "provider": provider,
                "address": address.strip(),
                "password": password.strip(),
                "host": host.strip() or IMAP_HOSTS.get(provider, IMAP_HOSTS.get("gmail")),
            })
    return accounts


def save_email_account(provider: str, address: str, password: str, host: str = "") -> int:
    """Append one EMAIL_ACCOUNT_N line to .env. Returns the index used."""
    path = os.path.abspath(ENV_FILE)
    lines = []
    used = 0
    if os.path.exists(path):
        with open(path) as f:
            lines = [ln.rstrip("\n") for ln in f]
        for ln in lines:
            m = re.match(r"EMAIL_ACCOUNT_(\d+)=", ln.strip())
            if m:
                used = max(used, int(m.group(1)))
    idx = used + 1
    lines.append(f"EMAIL_ACCOUNT_{idx}={provider.lower()}|{address}|{host}|{password}")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(path, 0o600)  # credentials: owner read/write only
    return idx


# Consumer domains map straight to an IMAP host (no DNS lookup needed).
CONSUMER_HOSTS = {
    "gmail.com": "imap.gmail.com", "googlemail.com": "imap.gmail.com",
    "outlook.com": "outlook.office365.com", "hotmail.com": "outlook.office365.com",
    "live.com": "outlook.office365.com", "msn.com": "outlook.office365.com",
    "yahoo.com": "imap.mail.yahoo.com", "aol.com": "imap.aol.com",
    "icloud.com": "imap.mail.me.com", "me.com": "imap.mail.me.com",
}


def _imap_from_mx(mx_blob: str) -> str:
    """Map a domain's MX records (joined lowercase string) to an IMAP host (pure)."""
    b = mx_blob.lower()
    if "google" in b or "googlemail" in b or "aspmx" in b:
        return "imap.gmail.com"
    if "outlook" in b or "office365" in b or "protection.outlook" in b or "microsoft" in b:
        return "outlook.office365.com"
    if "secureserver" in b or "godaddy" in b:
        return "imap.secureserver.net"
    if "zoho" in b:
        return "imap.zoho.com"
    if "yahoodns" in b or "yahoo" in b:
        return "imap.mail.yahoo.com"
    return ""


def detect_imap_host(address: str) -> str:
    """Best-effort IMAP host for an address: consumer map, else MX lookup."""
    domain = address.split("@")[-1].strip().lower()
    if not domain:
        return ""
    if domain in CONSUMER_HOSTS:
        return CONSUMER_HOSTS[domain]
    try:
        import subprocess
        out = subprocess.run(["nslookup", "-type=mx", domain],
                             capture_output=True, text=True, timeout=10)
        host = _imap_from_mx(out.stdout + out.stderr)
        if host:
            return host
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------------
# Parsing & classification (pure — unit tested without a network)
# ---------------------------------------------------------------------------

def split_sender(raw: str) -> tuple:
    """Return (display_name, email_address) from a From header value."""
    raw = str(raw or "").strip()
    m = re.match(r"^(.*?)<([^>]+)>", raw)
    if m:
        return m.group(1).strip().strip('"'), m.group(2).strip().lower()
    if "@" in raw:
        return "", raw.lower()
    return raw, ""


def _contains_name(haystack: str, names: set) -> str:
    """Return the first known name found as a whole-word match in haystack."""
    h = " " + re.sub(r"[^a-z ]", " ", haystack.lower()) + " "
    for name in names:
        if not name:
            continue
        parts = [p for p in name.split() if len(p) > 1]
        if parts and all(f" {p} " in h for p in parts):
            return name
    return ""


def classify_email(sender: str, subject: str, body: str,
                   recruit_index: dict, client_index: dict) -> dict:
    """
    Classify one email into carrier / recruit / client / other.
    Pure function — returns {category, priority, reason, matched}.
    """
    display, addr = split_sender(sender)
    text = f"{display} {addr} {subject} {body}".lower()
    subj_body = f"{subject} {body}".lower()

    # 1. Carrier — by sender/subject carrier token
    if any(tok in text for tok in CARRIER_TOKENS):
        if any(k in subj_body for k in URGENT_KEYWORDS):
            return {"category": "carrier", "priority": "high",
                    "reason": "carrier action needed", "matched": ""}
        if any(k in subj_body for k in INFO_KEYWORDS):
            return {"category": "carrier", "priority": "medium",
                    "reason": "carrier update", "matched": ""}
        return {"category": "carrier", "priority": "medium",
                "reason": "carrier email", "matched": ""}

    # 2. Recruit — sender email or name matches the pipeline
    if addr and addr in recruit_index.get("emails", set()):
        return {"category": "recruit", "priority": "medium",
                "reason": "recruit reply", "matched": display or addr}
    rmatch = _contains_name(display, recruit_index.get("names", set()))
    if rmatch:
        return {"category": "recruit", "priority": "medium",
                "reason": "recruit reply", "matched": rmatch.title()}

    # 3. Client — sender name matches an insured/applicant
    cmatch = _contains_name(display, client_index.get("names", set()))
    if cmatch:
        return {"category": "client", "priority": "medium",
                "reason": "client message", "matched": cmatch.title()}

    return {"category": "other", "priority": "low", "reason": "", "matched": ""}


def _msg_hash(msg: dict) -> str:
    src = msg.get("message_id") or f"{msg.get('from','')}|{msg.get('subject','')}|{msg.get('date','')}"
    return hashlib.md5(src.encode("utf-8", "ignore")).hexdigest()[:12]


def build_email_items(messages: list, recruit_index: dict, client_index: dict,
                      seen: set) -> tuple:
    """
    Turn fetched messages into (tasks, digest, new_seen).
    Tasks are created once per message (deduped via the seen set); the digest
    is regenerated every run. Pure — no I/O.
    """
    tasks, digest = [], []
    new_seen = set(seen)
    for m in messages:
        cat = classify_email(m.get("from", ""), m.get("subject", ""),
                             m.get("body", ""), recruit_index, client_index)
        display, addr = split_sender(m.get("from", ""))
        subject = (m.get("subject") or "(no subject)").strip()
        digest.append({
            "from": display or addr,
            "subject": subject[:80],
            "date": m.get("date", ""),
            "category": cat["category"],
            "priority": cat["priority"],
        })
        if cat["category"] == "other":
            continue
        h = _msg_hash(m)
        if h in new_seen:
            continue
        new_seen.add(h)
        if cat["category"] == "carrier":
            title = f"Carrier email: {subject[:70]}"
            tag = "policy"
        elif cat["category"] == "recruit":
            who = cat["matched"] or display or addr
            title = f"Reply to recruit {who}: {subject[:50]}"
            tag = "recruiting"
        else:
            who = cat["matched"] or display or addr
            title = f"Client {who}: {subject[:55]}"
            tag = "client"
        snippet = re.sub(r"\s+", " ", m.get("body", ""))[:140]
        tasks.append({
            "key": f"email-{h}",
            "title": title,
            "detail": f"From {display or addr}" + (f" · {snippet}" if snippet else ""),
            "priority": cat["priority"],
            "tag": tag,
        })
    return tasks, digest, new_seen


# ---------------------------------------------------------------------------
# IMAP fetch (network — fail soft)
# ---------------------------------------------------------------------------

def _decode(value) -> str:
    from email.header import decode_header
    out = []
    for chunk, enc in decode_header(str(value or "")):
        if isinstance(chunk, bytes):
            out.append(chunk.decode(enc or "utf-8", "ignore"))
        else:
            out.append(chunk)
    return "".join(out)


def parse_message(msg) -> dict:
    """Extract from/subject/date/body/message_id from an email.message.Message."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and \
                    "attachment" not in str(part.get("Content-Disposition", "")):
                try:
                    body = part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", "ignore")
                    break
                except (AttributeError, UnicodeDecodeError):
                    continue
    else:
        try:
            body = msg.get_payload(decode=True).decode(
                msg.get_content_charset() or "utf-8", "ignore")
        except (AttributeError, UnicodeDecodeError):
            body = ""
    return {
        "from": _decode(msg.get("From")),
        "subject": _decode(msg.get("Subject")),
        "date": _decode(msg.get("Date"))[:31],
        "message_id": str(msg.get("Message-ID") or "").strip(),
        "body": body.strip(),
    }


def fetch_recent(account: dict, days: int = 3, limit: int = 80) -> list:
    """Fetch recent INBOX messages for one account via IMAP."""
    import email
    import imaplib
    out = []
    M = imaplib.IMAP4_SSL(account["host"])
    try:
        M.login(account["address"], account["password"])
        M.select("INBOX")
        since = (date.today() - timedelta(days=days)).strftime("%d-%b-%Y")
        typ, data = M.search(None, f'(SINCE {since})')
        if typ == "OK" and data and data[0]:
            for num in data[0].split()[-limit:]:
                typ, msg_data = M.fetch(num, "(RFC822)")
                if typ != "OK" or not msg_data or not msg_data[0]:
                    continue
                out.append(parse_message(email.message_from_bytes(msg_data[0][1])))
    finally:
        try:
            M.logout()
        except Exception:
            pass
    return out


# ---------------------------------------------------------------------------
# Persistence + orchestration
# ---------------------------------------------------------------------------

def _load_seen() -> set:
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE) as f:
                return set(json.load(f))
        except (ValueError, OSError):
            return set()
    return set()


def _save_seen(seen: set) -> None:
    os.makedirs(os.path.dirname(SEEN_FILE), exist_ok=True)
    with open(SEEN_FILE, "w") as f:
        json.dump(sorted(seen)[-3000:], f)  # cap growth


def _build_indexes() -> tuple:
    """Build recruit and client name/email indexes from the agency data."""
    recruits, ledger, pending = [], [], []
    for sub, name, target in [
        ("recruits", "pipeline.json", "recruits"),
        ("policies", "ledger.json", "ledger"),
        ("policies", "pending.json", "pending"),
    ]:
        p = os.path.join(DATA_DIR, sub, name)
        if os.path.exists(p):
            try:
                with open(p) as f:
                    data = json.load(f)
            except (ValueError, OSError):
                data = []
            if target == "recruits":
                recruits = data
            elif target == "ledger":
                ledger = data
            else:
                pending = data
    recruit_index = {
        "names": {r.get("name", "").lower() for r in recruits if r.get("name")},
        "emails": {r.get("email", "").lower() for r in recruits if r.get("email")},
    }
    client_names = {p.get("applicant_name", "").lower()
                    for p in ledger + pending if p.get("applicant_name")}
    return recruit_index, {"names": client_names}


def run_email_connector() -> dict:
    """
    Fetch from every configured account, classify, and return
    {tasks, digest, accounts, errors}. Fail-soft per account.
    """
    accounts = load_email_accounts()
    result = {"tasks": [], "digest": [], "accounts": 0, "errors": []}
    if not accounts:
        return result
    seen = _load_seen()
    all_msgs = []
    for acct in accounts:
        try:
            all_msgs.extend(fetch_recent(acct))
            result["accounts"] += 1
        except Exception as e:  # auth/network must never break the sync
            result["errors"].append(f"Email {acct['address']}: {e}")
    recruit_index, client_index = _build_indexes()
    tasks, digest, new_seen = build_email_items(all_msgs, recruit_index, client_index, seen)
    # newest first, cap the digest for display
    digest.sort(key=lambda d: d.get("date", ""), reverse=True)
    result["tasks"] = tasks
    result["digest"] = digest[:25]
    if new_seen != seen:
        _save_seen(new_seen)
    return result
