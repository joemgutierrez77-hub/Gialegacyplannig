"""
External connectors — pull live business data from outside tools into the
agency data layer, so `flowhub sync` reflects reality without retyping.

Supported:
  • Teamtailor (recruiting ATS)  → candidates merge into the recruit pipeline
  • Calendly (scheduling)        → upcoming events appear on the FlowHub calendar
  • Quility HQ (no public API)   → CSV report importer for the policy ledger

Credentials live in a .env file at the project root (gitignored):
  TEAMTAILOR_API_KEY=...
  CALENDLY_API_TOKEN=...

Run `python main.py flowhub connect` for a guided setup.
All network calls fail soft: a connector that errors is reported and skipped,
never blocking the rest of the sync.
"""

import csv
import json
import os
from datetime import datetime, timezone

from config.settings import AGENCY, DATA_DIR

ENV_FILE = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
PIPELINE_FILE = os.path.join(DATA_DIR, "recruits", "pipeline.json")
LEDGER_FILE = os.path.join(DATA_DIR, "policies", "ledger.json")


# ---------------------------------------------------------------------------
# .env handling
# ---------------------------------------------------------------------------

def load_env() -> dict:
    """Read KEY=value pairs from .env (also honors real environment vars)."""
    vals = {}
    path = os.path.abspath(ENV_FILE)
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    vals[k.strip()] = v.strip().strip('"').strip("'")
    for key in ("TEAMTAILOR_API_KEY", "CALENDLY_API_TOKEN"):
        if os.environ.get(key):
            vals[key] = os.environ[key]
    return vals


def save_env_key(key: str, value: str) -> None:
    """Add or update one key in .env, preserving everything else."""
    path = os.path.abspath(ENV_FILE)
    lines = []
    if os.path.exists(path):
        with open(path) as f:
            lines = [ln.rstrip("\n") for ln in f]
    lines = [ln for ln in lines if not ln.strip().startswith(f"{key}=")]
    lines.append(f"{key}={value}")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Teamtailor → recruit pipeline
# ---------------------------------------------------------------------------

def fetch_teamtailor_candidates(api_key: str) -> list:
    """Fetch all candidates from the Teamtailor API (paginated)."""
    import requests
    headers = {
        "Authorization": f"Token token={api_key}",
        "X-Api-Version": "20210218",
    }
    url = "https://api.teamtailor.com/v1/candidates?page[size]=100"
    out = []
    while url:
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
        payload = resp.json()
        out.extend(payload.get("data", []))
        url = (payload.get("links") or {}).get("next")
    return out


def merge_candidates_into_pipeline(candidates: list, pipeline: list) -> int:
    """
    Merge Teamtailor candidates into the recruit pipeline (pure, testable).
    New candidates enter at 'new_lead'; existing ones are never moved or
    duplicated (matched by external id, then by name+phone). Returns count added.
    """
    by_ext = {r.get("external_id"): r for r in pipeline if r.get("external_id")}
    by_identity = {(r["name"].lower(), r.get("phone", "")) for r in pipeline}
    added = 0
    for c in candidates:
        attrs = c.get("attributes", {})
        ext_id = f"tt-{c.get('id')}"
        name = f"{attrs.get('first-name', '')} {attrs.get('last-name', '')}".strip()
        phone = attrs.get("phone") or ""
        if not name or ext_id in by_ext or (name.lower(), phone) in by_identity:
            continue
        pipeline.append({
            "id": max((r["id"] for r in pipeline), default=0) + 1,
            "name": name,
            "phone": phone,
            "source": "Teamtailor",
            "stage": "new_lead",
            "notes": "",
            "email": attrs.get("email") or "",
            "added_date": str(attrs.get("created-at", ""))[:10] or datetime.today().strftime("%Y-%m-%d"),
            "history": [],
            "external_id": ext_id,
        })
        by_ext[ext_id] = pipeline[-1]
        added += 1
    return added


def sync_teamtailor(api_key: str) -> int:
    candidates = fetch_teamtailor_candidates(api_key)
    pipeline = []
    if os.path.exists(PIPELINE_FILE):
        with open(PIPELINE_FILE) as f:
            pipeline = json.load(f)
    added = merge_candidates_into_pipeline(candidates, pipeline)
    if added:
        os.makedirs(os.path.dirname(PIPELINE_FILE), exist_ok=True)
        with open(PIPELINE_FILE, "w") as f:
            json.dump(pipeline, f, indent=2)
    return added


# ---------------------------------------------------------------------------
# Calendly → FlowHub calendar events
# ---------------------------------------------------------------------------

def parse_calendly_events(payload: dict) -> list:
    """Convert a Calendly scheduled_events response into FlowHub events (pure)."""
    out = []
    for ev in payload.get("collection", []):
        start = ev.get("start_time", "")
        end = ev.get("end_time", "")
        try:
            s = datetime.fromisoformat(start.replace("Z", "+00:00")).astimezone()
            e = datetime.fromisoformat(end.replace("Z", "+00:00")).astimezone()
            duration = max(int((e - s).total_seconds() // 60), 15)
        except ValueError:
            continue
        out.append({
            "key": "cal-" + (ev.get("uri", "").rsplit("/", 1)[-1] or start),
            "title": ev.get("name") or "Calendly meeting",
            "date": s.strftime("%Y-%m-%d"),
            "time": s.strftime("%H:%M"),
            "duration": duration,
        })
    return out


def fetch_calendly_events(token: str) -> list:
    """Fetch upcoming scheduled events for the token's Calendly user."""
    import requests
    headers = {"Authorization": f"Bearer {token}"}
    me = requests.get("https://api.calendly.com/users/me", headers=headers, timeout=20)
    me.raise_for_status()
    user_uri = me.json()["resource"]["uri"]
    resp = requests.get(
        "https://api.calendly.com/scheduled_events",
        headers=headers,
        params={
            "user": user_uri,
            "status": "active",
            "min_start_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "count": 100,
        },
        timeout=20,
    )
    resp.raise_for_status()
    return parse_calendly_events(resp.json())


# ---------------------------------------------------------------------------
# Quility HQ (or any carrier report) → policy ledger via CSV
# ---------------------------------------------------------------------------

# Flexible header matching: internal field → accepted column names (lowercased)
CSV_ALIASES = {
    "policy_number":  ["policy number", "policy #", "policy", "policy_no", "policy num"],
    "agent_name":     ["agent", "agent name", "writing agent", "producer"],
    "applicant_name": ["client", "client name", "insured", "applicant", "applicant name"],
    "carrier":        ["carrier", "company", "insurer"],
    "issue_date":     ["issue date", "issued", "effective date", "date issued"],
    "annual_premium": ["annual premium", "apv", "premium", "annualized premium", "ap"],
    "status":         ["status", "policy status"],
}


def _match_columns(headers: list) -> dict:
    """Map internal field names to CSV column names (pure, testable)."""
    lower = {h.lower().strip(): h for h in headers}
    mapping = {}
    for field, aliases in CSV_ALIASES.items():
        for alias in aliases:
            if alias in lower:
                mapping[field] = lower[alias]
                break
    return mapping


def _parse_money(val: str) -> float:
    try:
        return float(str(val).replace("$", "").replace(",", "").strip() or 0)
    except ValueError:
        return 0.0


def import_policies_csv(path: str, commission_pct: float = 0.70) -> dict:
    """
    Import a policy report (e.g. downloaded from Quility HQ) into the ledger.
    Deduplicates by policy number. Returns {'added': n, 'skipped': n, 'unmapped': [...]}.
    """
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        mapping = _match_columns(headers)
        missing = [k for k in ("policy_number", "annual_premium") if k not in mapping]
        if missing:
            raise ValueError(
                f"Could not find columns for {missing} in this file. "
                f"Columns present: {headers}"
            )
        rows = list(reader)

    ledger = []
    if os.path.exists(LEDGER_FILE):
        with open(LEDGER_FILE) as f:
            ledger = json.load(f)
    known = {str(p.get("policy_number")) for p in ledger}

    added = skipped = 0
    for row in rows:
        get = lambda field: str(row.get(mapping.get(field, ""), "") or "").strip()  # noqa: E731
        policy_no = get("policy_number")
        if not policy_no or policy_no in known:
            skipped += 1
            continue
        premium = _parse_money(get("annual_premium"))
        gross = premium * commission_pct
        status_raw = get("status").lower()
        status = "lapsed" if "laps" in status_raw or "charge" in status_raw else "active"
        ledger.append({
            "id": max((p["id"] for p in ledger), default=0) + 1,
            "agent_id": 0,
            "agent_name": get("agent_name") or "Unassigned",
            "policy_number": policy_no,
            "carrier": get("carrier") or "Unknown",
            "issue_date": get("issue_date")[:10] or datetime.today().strftime("%Y-%m-%d"),
            "annual_premium": premium,
            "agent_commission_pct": commission_pct,
            "gross_commission": round(gross, 2),
            "agency_override": round(premium * AGENCY["override_rate"], 2),
            "chargeback_reserve": round(gross * AGENCY["chargeback_reserve_pct"], 2),
            "net_to_agent": round(gross * (1 - AGENCY["chargeback_reserve_pct"]), 2),
            "status": status,
        })
        known.add(policy_no)
        added += 1

    os.makedirs(os.path.dirname(LEDGER_FILE), exist_ok=True)
    with open(LEDGER_FILE, "w") as f:
        json.dump(ledger, f, indent=2)
    return {"added": added, "skipped": skipped, "unmapped": [h for h in headers if h not in mapping.values()]}


# ---------------------------------------------------------------------------
# Orchestration — called by `flowhub sync`
# ---------------------------------------------------------------------------

def run_connectors() -> dict:
    """Run every configured connector. Fail-soft per connector."""
    env = load_env()
    result = {"teamtailor": None, "calendly_events": [], "errors": []}

    if env.get("TEAMTAILOR_API_KEY"):
        try:
            result["teamtailor"] = sync_teamtailor(env["TEAMTAILOR_API_KEY"])
        except Exception as e:  # network/auth issues must not break the sync
            result["errors"].append(f"Teamtailor: {e}")

    if env.get("CALENDLY_API_TOKEN"):
        try:
            result["calendly_events"] = fetch_calendly_events(env["CALENDLY_API_TOKEN"])
        except Exception as e:
            result["errors"].append(f"Calendly: {e}")

    return result
