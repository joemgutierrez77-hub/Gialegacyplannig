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
PENDING_FILE = os.path.join(DATA_DIR, "policies", "pending.json")
ROSTER_FILE = os.path.join(DATA_DIR, "agents", "roster.json")


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
    "agent_name":     ["agent", "agent name", "agentname", "writing agent",
                       "producer", "producer name"],
    "applicant_name": ["client", "client name", "insured", "applicant", "applicant name"],
    "apps_submitted": ["apps", "apps submitted", "submitted apps", "applications",
                       "app count", "# apps"],
    "carrier":        ["carrier", "company", "insurer"],
    "issue_date":     ["issue date", "issued", "effective date", "date issued"],
    "annual_premium": ["annual premium", "apv", "premium", "annualized premium", "ap"],
    "status":         ["status", "policy status", "app status", "application status", "decision"],
    "submit_date":    ["submit date", "submitted", "date submitted", "application date", "app date", "date"],
    "chargeback_amount": ["chargeback amount", "chargeback", "amount", "debit amount", "charged back"],
    "month_counting": ["month counting", "counting month"],
    "created":        ["created", "created at", "date created"],
}


def _norm_header(h: str) -> str:
    """Normalize a header: lowercase, collapse newlines/extra spaces, strip."""
    return " ".join(str(h).replace("\n", " ").lower().split())


def _match_columns(headers: list) -> dict:
    """Map internal field names to CSV column names (pure, testable)."""
    lower = {_norm_header(h): h for h in headers}
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


def _clean_text(val: str) -> str:
    """Collapse newlines/extra whitespace inside cell values (e.g. agent names)."""
    return " ".join(str(val or "").split())


def parse_date_any(val: str) -> str:
    """Normalize common date formats (5/20/2026, 2026-05-20, with times) to ISO."""
    s = str(val or "").strip()
    if not s:
        return ""
    token = s.split()[0]
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(token, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def _month_from_counting(month_name: str, created_iso: str) -> str:
    """Resolve a 'Month Counting' value like 'May' to an ISO first-of-month date,
    inferring the year from the row's Created date."""
    import calendar
    name = _clean_text(month_name).lower()
    months = {calendar.month_name[i].lower(): i for i in range(1, 13)}
    months.update({calendar.month_abbr[i].lower(): i for i in range(1, 13)})
    if name not in months:
        return ""
    m = months[name]
    year = int(created_iso[:4]) if created_iso[:4].isdigit() else datetime.today().year
    if created_iso[5:7].isdigit() and m > int(created_iso[5:7]) + 6:
        year -= 1  # e.g. December production logged in a January-created row
    return f"{year}-{m:02d}-01"


def _synth_id(prefix: str, *parts) -> str:
    """Stable synthetic policy id for reports that have no policy numbers."""
    import hashlib
    digest = hashlib.md5("|".join(str(p) for p in parts).encode()).hexdigest()[:10]
    return f"{prefix}-{digest}"


def _row_dates(get) -> tuple:
    """Best-available (issue_date, submit_date) for a row, ISO or ''."""
    submit = parse_date_any(get("submit_date"))
    issue = parse_date_any(get("issue_date")) or submit
    if not issue:
        created = parse_date_any(get("created"))
        issue = _month_from_counting(get("month_counting"), created)
    return issue, submit


def _row_getter(row: dict, mapping: dict):
    return lambda field: str(row.get(mapping.get(field, ""), "") or "").strip()


def _import_policy_rows(rows: list, mapping: dict, commission_pct: float = 0.70) -> dict:
    """Add issued policies to the ledger. Deduplicates by policy number."""
    ledger = []
    if os.path.exists(LEDGER_FILE):
        with open(LEDGER_FILE) as f:
            ledger = json.load(f)
    known = {str(p.get("policy_number")) for p in ledger}

    added = skipped = 0
    for row in rows:
        get = _row_getter(row, mapping)
        agent = _clean_text(get("agent_name"))
        applicant = _clean_text(get("applicant_name"))
        carrier = _clean_text(get("carrier"))
        premium = _parse_money(get("annual_premium"))
        issue_date, submit = _row_dates(get)
        policy_no = get("policy_number") or \
            _synth_id("auto", agent, applicant, carrier, premium, submit or issue_date)
        if premium <= 0 or policy_no in known:
            skipped += 1
            continue
        gross = premium * commission_pct
        status_raw = get("status").lower()
        status = "lapsed" if "laps" in status_raw or "charge" in status_raw else "active"
        ledger.append({
            "id": max((p["id"] for p in ledger), default=0) + 1,
            "agent_id": 0,
            "agent_name": agent or "Unassigned",
            "applicant_name": applicant,
            "policy_number": policy_no,
            "carrier": carrier or "Unknown",
            "issue_date": issue_date or datetime.today().strftime("%Y-%m-%d"),
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
    return {"added": added, "skipped": skipped}


def import_policies_csv(path: str, commission_pct: float = 0.70) -> dict:
    """
    Import an issued-policy report (e.g. downloaded from Quility HQ) into the ledger.
    Deduplicates by policy number. Returns {'added': n, 'skipped': n, 'unmapped': [...]}.
    """
    rows, mapping, headers = _read_csv(path, required=["annual_premium"])
    res = _import_policy_rows(rows, mapping, commission_pct)
    res["unmapped"] = [h for h in headers if h not in mapping.values()]
    return res


def _read_csv(path: str, required: list) -> tuple:
    """Open a CSV, match columns, validate required fields. Returns (rows, mapping, headers)."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        mapping = _match_columns(headers)
        missing = [k for k in required if k not in mapping]
        if missing:
            raise ValueError(
                f"Could not find columns for {missing} in this file. "
                f"Columns present: {headers}"
            )
        return list(reader), mapping, headers


def _pending_status(status_raw: str) -> str:
    s = status_raw.lower()
    if "declin" in s or "withdraw" in s:
        return "declined"
    if "approv" in s or "issu" in s:
        return "approved"
    return "pending"


def _import_pending_rows(rows: list, mapping: dict) -> dict:
    """
    Add submitted/pending applications, deduplicated by applicant + submit date.
    Re-importing a known application with a changed status (e.g. now Declined)
    updates the record instead of skipping it.
    """
    pending = []
    if os.path.exists(PENDING_FILE):
        with open(PENDING_FILE) as f:
            pending = json.load(f)
    known = {(p["applicant_name"].lower(), p.get("submit_date", "")): p for p in pending}

    added = updated = skipped = 0
    for row in rows:
        get = _row_getter(row, mapping)
        applicant = _clean_text(get("applicant_name"))
        submit = parse_date_any(get("submit_date"))
        status = _pending_status(get("status"))
        if not applicant:
            skipped += 1
            continue
        existing = known.get((applicant.lower(), submit))
        if existing:
            if existing.get("status") != status:
                existing["status"] = status
                updated += 1
            else:
                skipped += 1
            continue
        pending.append({
            "id": max((p["id"] for p in pending), default=0) + 1,
            "applicant_name": applicant,
            "agent_name": _clean_text(get("agent_name")) or "Unassigned",
            "carrier": _clean_text(get("carrier")) or "Unknown",
            "submit_date": submit or datetime.today().strftime("%Y-%m-%d"),
            "annual_premium": _parse_money(get("annual_premium")),
            "status": status,
        })
        known[(applicant.lower(), submit)] = pending[-1]
        added += 1

    os.makedirs(os.path.dirname(PENDING_FILE), exist_ok=True)
    with open(PENDING_FILE, "w") as f:
        json.dump(pending, f, indent=2)
    return {"added": added, "updated": updated, "skipped": skipped}


def _resolve_pending(rows: list, mapping: dict, new_status: str) -> int:
    """
    Combined imports: when an application now shows as issued or charged back,
    close out any matching open pending record so it stops counting (and stops
    generating stalled-underwriting tasks). Matches by applicant name.
    """
    if not rows or not os.path.exists(PENDING_FILE):
        return 0
    with open(PENDING_FILE) as f:
        pending = json.load(f)
    def norm_carrier(c):
        c = _clean_text(c).lower()
        return "" if c in ("", "unknown") else c

    # applicant -> carriers placed; carrier "" acts as a wildcard so reports
    # without a carrier column still resolve, while a known carrier never
    # closes the same client's pending app at a different carrier
    placed: dict = {}
    for row in rows:
        get = _row_getter(row, mapping)
        name = _clean_text(get("applicant_name")).lower()
        if name:
            placed.setdefault(name, set()).add(norm_carrier(get("carrier")))
    changed = 0
    for p in pending:
        if p.get("status") != "pending":
            continue
        carriers = placed.get(p["applicant_name"].lower())
        if carriers is None:
            continue
        pc = norm_carrier(p.get("carrier", ""))
        if pc == "" or "" in carriers or pc in carriers:
            p["status"] = new_status
            changed += 1
    if changed:
        with open(PENDING_FILE, "w") as f:
            json.dump(pending, f, indent=2)
    return changed


def import_pending_csv(path: str) -> dict:
    """
    Import a submitted/pending applications report into data/policies/pending.json.
    Deduplicates by applicant + submit date. Returns {'added','skipped','unmapped'}.
    """
    rows, mapping, headers = _read_csv(path, required=["applicant_name", "annual_premium"])
    res = _import_pending_rows(rows, mapping)
    res["unmapped"] = [h for h in headers if h not in mapping.values()]
    return res


def _import_chargeback_rows(rows: list, mapping: dict, commission_pct: float = 0.70,
                            fallback_amount: bool = False) -> dict:
    """
    Mark policies lapsed with chargeback amounts. When fallback_amount is True
    (combined imports without an amount column), the gross commission is used
    as the chargeback — the standard full first-year chargeback assumption.
    """
    ledger = []
    if os.path.exists(LEDGER_FILE):
        with open(LEDGER_FILE) as f:
            ledger = json.load(f)
    by_no = {str(p.get("policy_number")): p for p in ledger}

    updated = added = skipped = 0
    for row in rows:
        get = _row_getter(row, mapping)
        agent = _clean_text(get("agent_name"))
        applicant = _clean_text(get("applicant_name"))
        carrier = _clean_text(get("carrier"))
        premium = _parse_money(get("annual_premium"))
        issue_date, _submit = _row_dates(get)
        policy_no = get("policy_number") or \
            _synth_id("cb", agent, applicant, carrier, premium, issue_date)
        amount = _parse_money(get("chargeback_amount"))
        existing = by_no.get(policy_no) if policy_no else None
        if amount <= 0 and fallback_amount:
            # Negative-premium CB rows (tracker style): the reversed APV × commission
            # is the clawed-back amount; otherwise fall back to gross commission.
            amount = (existing or {}).get("gross_commission") or \
                round(abs(premium) * commission_pct, 2)
        if not policy_no or amount <= 0:
            skipped += 1
            continue
        if existing:
            if existing.get("status") == "lapsed" and existing.get("chargeback_actual"):
                skipped += 1  # already recorded
                continue
            existing["status"] = "lapsed"
            existing["chargeback_actual"] = amount
            existing["net_to_agent"] = round(existing.get("net_to_agent", 0) - amount, 2)
            updated += 1
        else:
            ledger.append({
                "id": max((p["id"] for p in ledger), default=0) + 1,
                "agent_id": 0,
                "agent_name": agent or "Unassigned",
                "applicant_name": applicant,
                "policy_number": policy_no,
                "carrier": carrier or "Unknown",
                "issue_date": issue_date or datetime.today().strftime("%Y-%m-%d"),
                "annual_premium": abs(premium),
                "agent_commission_pct": 0.0,
                "gross_commission": 0.0,
                "agency_override": 0.0,
                "chargeback_reserve": 0.0,
                "net_to_agent": round(-amount, 2),
                "chargeback_actual": amount,
                "status": "lapsed",
            })
            by_no[policy_no] = ledger[-1]
            added += 1

    os.makedirs(os.path.dirname(LEDGER_FILE), exist_ok=True)
    with open(LEDGER_FILE, "w") as f:
        json.dump(ledger, f, indent=2)
    return {"updated": updated, "added": added, "skipped": skipped}


def import_chargebacks_csv(path: str) -> dict:
    """
    Import a chargeback report. Policies already in the ledger are marked lapsed
    with the chargeback amount; unknown policy numbers are added as lapsed
    entries so exposure totals stay honest.
    Returns {'updated','added','skipped','unmapped'}.
    """
    rows, mapping, headers = _read_csv(path, required=["policy_number", "chargeback_amount"])
    res = _import_chargeback_rows(rows, mapping)
    res["unmapped"] = [h for h in headers if h not in mapping.values()]
    return res


def _classify_status(status: str) -> str:
    """Route a combined-report row by its status text (pure, testable)."""
    s = status.lower()
    if any(k in s for k in ("laps", "charge", "cancel", "term", "nsf")):
        return "chargeback"
    if any(k in s for k in ("issu", "activ", "inforce", "in force", "placed", "paid")):
        return "issued"
    # pending, submitted, underwriting, approved, declined, withdrawn → pending
    # records (the pending importer normalizes approved/declined itself)
    return "pending"


def import_combined_csv(path: str, commission_pct: float = 0.70) -> dict:
    """
    Import ONE report containing pending, issued, and charged-back rows mixed
    together, routed by the Status column. Returns per-bucket results.
    """
    rows, mapping, headers = _read_csv(path, required=["status"])
    buckets = {"pending": [], "issued": [], "chargeback": []}
    for row in rows:
        get = _row_getter(row, mapping)
        # Tracker-style chargebacks: negative premium rows, whatever the status says
        if _parse_money(get("annual_premium")) < 0:
            buckets["chargeback"].append(row)
        else:
            buckets[_classify_status(get("status"))].append(row)

    result = {
        "pending": _import_pending_rows(buckets["pending"], mapping)
        if buckets["pending"] else {"added": 0, "updated": 0, "skipped": 0},
        "issued": _import_policy_rows(buckets["issued"], mapping, commission_pct)
        if buckets["issued"] else {"added": 0, "skipped": 0},
        "chargebacks": _import_chargeback_rows(buckets["chargeback"], mapping,
                                               commission_pct, fallback_amount=True)
        if buckets["chargeback"] else {"updated": 0, "added": 0, "skipped": 0},
        "unmapped": [h for h in headers if h not in mapping.values()],
    }
    # Close out pending records for applicants whose policies are now placed/lapsed
    resolved = _resolve_pending(buckets["issued"], mapping, "approved")
    resolved += _resolve_pending(buckets["chargeback"], mapping, "approved")
    result["pending"]["resolved"] = resolved
    return result


# ---------------------------------------------------------------------------
# Agent production summary (per-agent APV + app counts, e.g. Quility HQ
# "Submitted Details"). These reports carry no per-policy identity, so they
# feed the agent roster's monthly stats — NOT the policy ledger. Routing them
# through the policy importer would lose agent names and mis-book submitted
# business as issued, paid policies.
# ---------------------------------------------------------------------------

def _is_production_summary(mapping: dict) -> bool:
    """
    True when a report is a per-agent production summary: it names an agent and
    counts apps, but has no per-policy identity (no applicant/client, no policy
    number). Pure and testable off the column mapping alone.
    """
    return (
        "agent_name" in mapping
        and "apps_submitted" in mapping
        and "applicant_name" not in mapping
        and "policy_number" not in mapping
    )


def _import_production_rows(rows: list, mapping: dict, month: str) -> dict:
    """
    Upsert per-agent submitted production into the roster's monthly_stats.
    One row = one agent's total for the month; re-importing the same agent+month
    replaces that record (so duplicate rows and weekly re-pulls never double-count).
    """
    roster = []
    if os.path.exists(ROSTER_FILE):
        with open(ROSTER_FILE) as f:
            roster = json.load(f)
    by_name = {a["name"].lower(): a for a in roster}
    pre_existing = set(by_name)          # agents on the roster before this import

    seen = {}                            # name -> final row values (last row wins)
    for row in rows:
        get = _row_getter(row, mapping)
        name = _clean_text(get("agent_name"))
        if not name:
            continue
        apv = _parse_money(get("annual_premium"))
        apps = int(round(_parse_money(get("apps_submitted"))))
        agent = by_name.get(name.lower())
        if not agent:
            agent = {
                "id": max((a["id"] for a in roster), default=0) + 1,
                "name": name,
                "start_date": datetime.today().strftime("%Y-%m-%d"),
                "license_state": "",
                "status": "active",
                "monthly_stats": [],
            }
            roster.append(agent)
            by_name[name.lower()] = agent
        record = {
            "month":          month,
            "contacts":       0,
            "appointments":   0,
            "apps_submitted": apps,
            "apps_issued":    0,
            "apv":            round(apv, 2),
            "chargebacks":    0.0,
            "persistency":    None,
            "logged_at":      datetime.today().strftime("%Y-%m-%d"),
            "source":         "submitted_details",
        }
        agent["monthly_stats"] = [s for s in agent.get("monthly_stats", [])
                                  if s.get("month") != month] + [record]
        seen[name.lower()] = {"name": name, "apps": apps, "apv": round(apv, 2)}

    added = sum(1 for k in seen if k not in pre_existing)
    updated = sum(1 for k in seen if k in pre_existing)

    os.makedirs(os.path.dirname(ROSTER_FILE), exist_ok=True)
    with open(ROSTER_FILE, "w") as f:
        json.dump(roster, f, indent=2)
    return {"added": added, "updated": updated, "month": month,
            "agents": list(seen.values())}


def import_production_summary_csv(path: str, month: str = None) -> dict:
    """
    Import a per-agent production summary (APV + app counts) into the roster.
    `month` defaults to the current calendar month (YYYY-MM).
    Returns {'added','updated','month','agents':[...],'unmapped':[...]}.
    """
    month = month or datetime.today().strftime("%Y-%m")
    rows, mapping, headers = _read_csv(path, required=["agent_name", "apps_submitted"])
    res = _import_production_rows(rows, mapping, month)
    res["unmapped"] = [h for h in headers if h not in mapping.values()]
    return res


def import_all_auto(path: str, commission_pct: float = 0.70, month: str = None) -> dict:
    """
    Route a report to the right importer by its shape. Per-agent production
    summaries go to the roster; per-policy reports go through the combined
    pending/issued/chargeback importer. Returns the chosen importer's result
    with a 'type' key ('production' or 'policy').
    """
    _rows, mapping, _headers = _read_csv(path, required=[])
    if _is_production_summary(mapping):
        return {"type": "production", **import_production_summary_csv(path, month=month)}
    return {"type": "policy", **import_combined_csv(path, commission_pct=commission_pct)}


# ---------------------------------------------------------------------------
# Orchestration — called by `flowhub sync`
# ---------------------------------------------------------------------------

def run_connectors() -> dict:
    """Run every configured connector. Fail-soft per connector."""
    env = load_env()
    result = {"teamtailor": None, "calendly_events": [],
              "email_tasks": [], "email_digest": [], "email_accounts": 0,
              "errors": []}

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

    try:
        from src.modules.email_connector import run_email_connector
        email_res = run_email_connector()
        result["email_tasks"] = email_res["tasks"]
        result["email_digest"] = email_res["digest"]
        result["email_accounts"] = email_res["accounts"]
        result["errors"].extend(email_res["errors"])
    except Exception as e:
        result["errors"].append(f"Email: {e}")

    return result
