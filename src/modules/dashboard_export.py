"""
Dashboard feed — translate the FlowHub business snapshot into the shape the
Jarvis-style command center (dashboard.html at the repo root) expects, and
write it to dashboard-data.js next to that file.

This is what makes the dashboard "live": `python main.py flowhub sync` builds
the same snapshot used by FlowHub, then this module reshapes it and drops
dashboard-data.js beside dashboard.html. Open the page and it fills in from
your real email digest, pipeline, production, and Calendly meetings.

Pure data shaping — no Claude calls, no network. dashboard-data.js is
gitignored (it contains your live business data), exactly like business-data.js.
"""

import json
import os
from datetime import datetime, timedelta

DASHBOARD_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "dashboard-data.js"
)

# Internal pipeline stage keys → the 7 Teamtailor stages shown on the dashboard.
# Best-effort: anything unrecognized lands in "Applied / Connected".
STAGE_MAP = {
    "new_lead":          "Applied / Connected",
    "contacted":         "Applied / Connected",
    "watched_info":      "Interview Scheduled",
    "interview":         "Interview Scheduled",
    "committed":         "Hired / Onboarding",
    "onboarding":        "Hired / Onboarding",
    "licensing_started": "Pre-Licensing",
    "nurture":           "Pre-Licensing",
    "exam_scheduled":    "Exam Scheduled",
    "passed_exam":       "Exam Scheduled",
    "licensed":          "Licensed",
    "contracting":       "Licensed",
    "contracted":        "Active Producer",
    "active":            "Active Producer",
}
TEAMTAILOR_STAGES = [
    "Applied / Connected", "Interview Scheduled", "Hired / Onboarding",
    "Pre-Licensing", "Exam Scheduled", "Licensed", "Active Producer",
]

PRIORITY_MAP = {"high": "high", "medium": "med", "med": "med", "low": "low"}


def _pipeline(snapshot: dict) -> list:
    counts = {s: 0 for s in TEAMTAILOR_STAGES}
    for stage, n in (snapshot.get("recruiting", {}).get("stageCounts") or {}).items():
        bucket = STAGE_MAP.get(str(stage).lower(), "Applied / Connected")
        counts[bucket] += n
    return [{"stage": s, "count": counts[s]} for s in TEAMTAILOR_STAGES]


def _events(snapshot: dict) -> list:
    """Calendly meetings (date/time/duration) → dashboard start/end strings."""
    out = []
    for e in (snapshot.get("events") or []):
        d, t = e.get("date", ""), (e.get("time") or "09:00")
        if not d:
            continue
        try:
            start = datetime.strptime(f"{d} {t}", "%Y-%m-%d %H:%M")
        except ValueError:
            try:
                start = datetime.strptime(d, "%Y-%m-%d")
            except ValueError:
                continue
        end = start + timedelta(minutes=int(e.get("duration") or 30))
        out.append({
            "start": start.strftime("%Y-%m-%dT%H:%M"),
            "end":   end.strftime("%Y-%m-%dT%H:%M"),
            "title": e.get("title", "Meeting"),
            "where": e.get("notes") or e.get("location") or "",
            "link":  e.get("link") or e.get("location") or "",
        })
    return sorted(out, key=lambda x: x["start"])


def _inbox(snapshot: dict) -> list:
    out = []
    for it in (snapshot.get("inbox") or [])[:8]:
        cat = it.get("category", "")
        out.append({
            "priority": PRIORITY_MAP.get(it.get("priority", "low"), "low"),
            "from":     it.get("from", "")[:40] or cat or "Inbox",
            "subject":  it.get("subject", "")[:90],
            "action":   {"carrier": "Carrier — review & respond",
                         "recruit": "Recruit reply — follow up",
                         "client":  "Client — respond"}.get(cat, ""),
        })
    return out


def _top3(snapshot: dict) -> list:
    rank = {"high": 0, "medium": 1, "med": 1, "low": 2}
    sugg = sorted((snapshot.get("suggestions") or []),
                  key=lambda s: rank.get(s.get("priority", "low"), 2))[:3]
    return [{
        "id":    s.get("key", f"t{i}"),
        "rank":  f"Priority {i + 1}",
        "title": s.get("title", ""),
        "sub":   s.get("detail", ""),
    } for i, s in enumerate(sugg)]


def _agents(snapshot: dict) -> list:
    out = []
    for a in (snapshot.get("production", {}).get("agents") or [])[:8]:
        out.append({
            "name":   a.get("name", ""),
            "status": "Active" if not a.get("derived") else "Producing",
            "next":   f"Last logged {a.get('last_month') or '—'} · "
                      f"APV ${a.get('apv', 0):,.0f}, {a.get('apps_issued', 0)} apps",
        })
    return out


def _production(snapshot: dict) -> list:
    out = []
    for a in (snapshot.get("production", {}).get("agents") or []):
        out.append({
            "name":       a.get("name", ""),
            "dials":      a.get("dials", 0),
            "contacts":   a.get("contacts", 0),
            "apps":       a.get("apps_issued", 0),
            "closes":     a.get("apps_issued", 0),
            "commission": int(a.get("net_to_agent", 0) or 0),
            "apv":        int(a.get("apv", 0) or 0),
        })
    return out


def build_dashboard_data(snapshot: dict) -> dict:
    """Reshape a FlowHub snapshot into the dashboard.html DATA contract."""
    top3 = _top3(snapshot)
    mission = ("Stay on pace: " + top3[0]["title"]) if top3 else \
        "Work the pipeline and protect today's appointments."
    return {
        "meta": {
            "owner":   "Joe",
            "agency":  snapshot.get("agency", "G.I.A. Legacy Planning"),
            "updated": snapshot.get("generatedAt", ""),
            "source":  snapshot.get("source", ""),
        },
        "mission":    mission,
        "top3":       top3,
        "events":     _events(snapshot),
        "inbox":      _inbox(snapshot),
        "pipeline":   _pipeline(snapshot),
        "agents":     _agents(snapshot),
        "production": _production(snapshot),
    }


def write_dashboard(snapshot: dict) -> str:
    """Write dashboard-data.js next to dashboard.html. Returns the path."""
    data = build_dashboard_data(snapshot)
    path = os.path.abspath(DASHBOARD_FILE)
    with open(path, "w") as f:
        f.write("// Auto-generated by `python main.py flowhub sync` — do not edit.\n")
        f.write("// Open dashboard.html and it reads this file automatically.\n")
        f.write("window.DASHBOARD_DATA = ")
        json.dump(data, f, indent=2)
        f.write(";\n")
    return path
