"""
FlowHub bridge — export live agency data into the personal productivity app.

Generates productivity/business-data.js, which FlowHub (productivity/index.html)
loads on startup to show a business overview and auto-create daily tasks from
real pipeline, production, and profitability data.

No Claude calls — this is pure data aggregation, zero API cost.
Data layer follows the rest of the system: Airtable when configured,
otherwise local JSON in data/.
"""

import json
import os
from datetime import date, datetime

from config.settings import AGENCY, DATA_DIR, USE_AIRTABLE

EXPORT_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "productivity", "business-data.js"
)

# Pipeline stages where a recruit is waiting on us and goes stale
ACTIONABLE_STAGES = {
    "new_lead":          2,   # days in stage before a follow-up task fires
    "watched_info":      3,
    "committed":         3,
    "licensing_started": 14,
    "nurture":           14,
    "passed_exam":       3,
    "contracting":       5,
}


def _load_recruits() -> list:
    if USE_AIRTABLE:
        from src.airtable_adapter import get_recruits
        return get_recruits()
    path = os.path.join(DATA_DIR, "recruits", "pipeline.json")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


def _load_agents() -> list:
    path = os.path.join(DATA_DIR, "agents", "roster.json")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


def _load_ledger() -> list:
    if USE_AIRTABLE:
        from src.airtable_adapter import get_issued_policies
        return get_issued_policies()
    path = os.path.join(DATA_DIR, "policies", "ledger.json")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


def _load_pending() -> list:
    path = os.path.join(DATA_DIR, "policies", "pending.json")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


def _days_since(date_str: str) -> int:
    try:
        return (date.today() - datetime.strptime(date_str[:10], "%Y-%m-%d").date()).days
    except (ValueError, TypeError):
        return 0


def _days_in_stage(recruit: dict) -> int:
    history = recruit.get("history") or []
    if history:
        return _days_since(history[-1].get("date", ""))
    return _days_since(recruit.get("added_date", ""))


def build_snapshot(events: list = None, extra_suggestions: list = None,
                   email_digest: list = None) -> dict:
    """Aggregate all business data into one snapshot dict for FlowHub."""
    recruits = _load_recruits()
    agents   = _load_agents()
    ledger   = _load_ledger()
    this_month = date.today().strftime("%Y-%m")

    # ---- recruiting overview -------------------------------------------
    stage_counts: dict = {}
    for r in recruits:
        stage_counts[r.get("stage", "unknown")] = stage_counts.get(r.get("stage", "unknown"), 0) + 1
    added_this_month = sum(1 for r in recruits if str(r.get("added_date", "")).startswith(this_month))
    contracted_this_month = sum(
        1 for r in recruits
        for h in (r.get("history") or [])
        if h.get("to") == "contracted" and str(h.get("date", "")).startswith(this_month)
    )

    # ---- production overview -------------------------------------------
    agent_rows = []
    for a in agents:
        if a.get("status") != "active":
            continue
        stats = a.get("monthly_stats") or []
        last = stats[-1] if stats else {}
        agent_rows.append({
            "id":          a["id"],
            "name":        a["name"],
            "last_month":  last.get("month", ""),
            "apv":         last.get("apv", 0),
            "apps_submitted": last.get("apps_submitted", 0),
            "apps_issued": last.get("apps_issued", 0),
            "persistency": last.get("persistency"),
        })

    # ---- profitability overview ----------------------------------------
    active = [p for p in ledger if p.get("status") == "active"]
    at_risk = [p for p in active if _days_since(p.get("issue_date", "")) < 396]  # < 13 months
    total_apv       = sum(p.get("annual_premium", 0) for p in active)
    total_override  = sum(p.get("agency_override", 0) for p in active)
    exposure        = sum(p.get("gross_commission", 0) for p in at_risk)
    # Show the current month if it has production, else the latest month that does
    # (reports often cover last month's business)
    months_with_data = sorted({str(p.get("issue_date", ""))[:7] for p in active
                               if p.get("issue_date")})
    month_label = this_month if (this_month in months_with_data or not months_with_data) \
        else months_with_data[-1]
    month_active    = [p for p in active if str(p.get("issue_date", "")).startswith(month_label)]
    month_apv       = sum(p.get("annual_premium", 0) for p in month_active)
    month_issued    = len(month_active)
    chargebacks_total = sum(p.get("chargeback_actual", 0) for p in ledger
                            if p.get("status") == "lapsed")

    # No roster maintained? Derive the agent leaderboard from the ledger itself.
    if not agent_rows and month_active:
        by_agent: dict = {}
        for p in month_active:
            row = by_agent.setdefault(p.get("agent_name") or "Unassigned",
                                      {"apv": 0.0, "apps": 0})
            row["apv"] += p.get("annual_premium", 0)
            row["apps"] += 1
        agent_rows = [{
            "id": "ag-" + name.lower().replace(" ", "-"),
            "name": name,
            "last_month": month_label,
            "apv": round(v["apv"], 2),
            "apps_submitted": v["apps"],
            "apps_issued": v["apps"],
            "persistency": None,
            "derived": True,
        } for name, v in sorted(by_agent.items(), key=lambda kv: -kv[1]["apv"])]

    # ---- pending applications ------------------------------------------
    pending = _load_pending()
    open_pending = [p for p in pending if p.get("status") == "pending"]
    pending_apv = sum(p.get("annual_premium", 0) for p in open_pending)

    # ---- daily task suggestions ----------------------------------------
    suggestions = _build_suggestions(
        recruits, agent_rows, this_month,
        added_this_month, contracted_this_month, exposure,
        open_pending,
    )
    # email-derived tasks (carrier/recruit/client) lead the list
    suggestions = (extra_suggestions or []) + suggestions

    return {
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "agency": AGENCY["name"],
        "source": "Airtable" if USE_AIRTABLE else "local JSON",
        "recruiting": {
            "stageCounts": stage_counts,
            "total": len(recruits),
            "addedThisMonth": added_this_month,
            "contractedThisMonth": contracted_this_month,
            "targetContacted": AGENCY["target_recruits_contacted"],
            "targetContracts": AGENCY["target_contracts_issued"],
        },
        "production": {
            "agents": agent_rows,
            "targetApv": AGENCY["target_apv_per_month"],
            "targetIssued": AGENCY["target_issued_per_month"],
            "minPersistency": AGENCY["min_persistency_rate"],
        },
        "profitability": {
            "activePolicies": len(active),
            "totalApv": round(total_apv, 2),
            "overrideIncome": round(total_override, 2),
            "chargebackExposure": round(exposure, 2),
            "chargebacksTotal": round(chargebacks_total, 2),
            "monthApv": round(month_apv, 2),
            "monthIssued": month_issued,
            "monthLabel": month_label,
        },
        "pending": {
            "count": len(open_pending),
            "apv": round(pending_apv, 2),
        },
        "suggestions": suggestions,
        "events": events or [],
        "inbox": email_digest or [],
    }


def _build_suggestions(recruits, agent_rows, this_month,
                       added_this_month, contracted_this_month, exposure,
                       open_pending=None) -> list:
    """Turn business state into concrete daily tasks with stable dedupe keys."""
    out = []

    # Pending applications sitting too long without a decision
    for p in (open_pending or []):
        days = _days_since(p.get("submit_date", ""))
        if days >= 14:
            out.append({
                "key": f"pending-stall-{p.get('id')}-{p.get('submit_date', '')}",
                "title": f"Check pending app for {p['applicant_name']} ({p.get('carrier', '?')}) — {days} days in underwriting",
                "detail": f"Submitted {p.get('submit_date', '?')} · ${p.get('annual_premium', 0):,.0f} premium · agent {p.get('agent_name', '?')}",
                "priority": "high" if days >= 30 else "medium", "tag": "production",
            })

    # Recruit follow-ups: anyone sitting in an actionable stage too long
    for r in recruits:
        stage = r.get("stage", "")
        if stage not in ACTIONABLE_STAGES:
            continue
        days = _days_in_stage(r)
        threshold = ACTIONABLE_STAGES[stage]
        if stage == "new_lead":
            out.append({
                "key": f"recruit-new-{r['id']}",
                "title": f"Reach out to new lead {r['name']}" + (f" ({r['source']})" if r.get("source") else ""),
                "detail": f"Added {r.get('added_date', '?')} — first contact" + (f" · {r['phone']}" if r.get("phone") else ""),
                "priority": "high", "tag": "recruiting",
            })
        elif days >= threshold:
            out.append({
                "key": f"recruit-stalled-{r['id']}-{stage}",
                "title": f"Follow up with {r['name']} — {stage.replace('_', ' ')} for {days} days",
                "detail": (f"{r['phone']} · " if r.get("phone") else "") + f"stalled past {threshold}-day threshold",
                "priority": "high" if days >= threshold * 2 else "medium", "tag": "recruiting",
            })

    # Monthly recruiting quota pace
    target = AGENCY["target_recruits_contacted"]
    if added_this_month < target:
        out.append({
            "key": f"recruit-quota-{this_month}",
            "title": f"Recruiting outreach: contact new prospects ({added_this_month}/{target} this month)",
            "detail": f"Monthly target is {target} new contacts",
            "priority": "medium", "tag": "recruiting",
        })

    # Production: missing stats and below-target coaching
    for a in agent_rows:
        if a["last_month"] and a["last_month"] < this_month and date.today().day >= 5 \
                and not a.get("derived"):
            out.append({
                "key": f"stats-missing-{a['id']}-{this_month}",
                "title": f"Log {this_month} production stats for {a['name']}",
                "detail": f"Last recorded month: {a['last_month']}",
                "priority": "medium", "tag": "production",
            })
        if a["last_month"]:
            below_apv = a["apv"] < AGENCY["target_apv_per_month"]
            low_persist = a["persistency"] is not None and a["persistency"] < AGENCY["min_persistency_rate"]
            if below_apv or low_persist:
                why = []
                if below_apv:
                    why.append(f"APV ${a['apv']:,.0f} vs ${AGENCY['target_apv_per_month']:,} target")
                if low_persist:
                    why.append(f"persistency {a['persistency']*100:.0f}% (floor {AGENCY['min_persistency_rate']*100:.0f}%)")
                out.append({
                    "key": f"coach-{a['id']}-{a['last_month']}",
                    "title": f"Coaching session with {a['name']}",
                    "detail": " · ".join(why),
                    "priority": "high" if low_persist else "medium", "tag": "production",
                })

    # Profitability: monthly chargeback review when there is real exposure
    if exposure > 0:
        out.append({
            "key": f"chargeback-review-{this_month}",
            "title": f"Review chargeback exposure (${exposure:,.0f} commission at risk)",
            "detail": "Run: python main.py profitability chargebacks",
            "priority": "medium", "tag": "profitability",
        })

    return out


def export_flowhub() -> str:
    """Run configured connectors, then write productivity/business-data.js."""
    from src.modules.connectors import run_connectors
    conn = run_connectors()
    if conn["teamtailor"] is not None:
        print(f"  Teamtailor: {conn['teamtailor']} new candidate(s) added to pipeline")
    if conn["calendly_events"]:
        print(f"  Calendly: {len(conn['calendly_events'])} upcoming meeting(s) found")
    if conn.get("email_accounts"):
        print(f"  Email: {conn['email_accounts']} account(s) scanned, "
              f"{len(conn['email_tasks'])} new task(s), "
              f"{len(conn['email_digest'])} in digest")
    for err in conn["errors"]:
        print(f"  ⚠ Connector error (skipped): {err}")
    snapshot = build_snapshot(events=conn["calendly_events"],
                              extra_suggestions=conn.get("email_tasks"),
                              email_digest=conn.get("email_digest"))
    path = os.path.abspath(EXPORT_FILE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write("// Auto-generated by `python main.py flowhub sync` — do not edit.\n")
        f.write("window.BUSINESS_DATA = ")
        json.dump(snapshot, f, indent=2)
        f.write(";\n")
    # Also feed the standalone Jarvis command center (dashboard.html).
    try:
        from src.modules.dashboard_export import write_dashboard
        write_dashboard(snapshot)
    except Exception as e:  # never let the dashboard feed break the FlowHub sync
        print(f"  ⚠ Dashboard feed skipped: {e}")
    return path
