#!/usr/bin/env python3
"""
GIA Legacy Planning — Mobile API layer.

A thin FastAPI wrapper around the existing recruiting / production /
profitability modules so a phone app (native, or a no-code tool like
Glide/Softr) can drive the whole agency system from the field.

Run locally:
    pip install -r requirements.txt
    export ANTHROPIC_API_KEY=sk-ant-...
    uvicorn api:app --reload

Interactive docs (great for testing from a phone browser):
    http://localhost:8000/docs

Design notes:
  - Read-only "dashboard" and "list" endpoints never call Claude, so they
    are instant and free — perfect for a mobile home screen.
  - AI endpoints (score, report, scorecard, pnl, ...) call Claude through
    the same cost-controlled `call_claude` path the CLI uses.
  - Every endpoint reuses the existing module functions; no business logic
    is duplicated here.
"""

from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from config.settings import AGENCY
from src.claude_client import cost_summary
from src.modules import production as prod_mod
from src.modules import profitability as prof_mod
from src.modules import recruiting as rec_mod

app = FastAPI(
    title="GIA Legacy Planning API",
    description="Mobile-ready endpoints for recruiting, production, and profitability.",
    version="1.0.0",
)


# ---------------------------------------------------------------------------
# Request models (response bodies are plain dicts / strings for simplicity)
# ---------------------------------------------------------------------------
class RecruitIn(BaseModel):
    name: str
    phone: str
    source: str
    notes: str = ""
    email: str = ""


class AdvanceIn(BaseModel):
    stage: str = Field(..., description=f"One of: {', '.join(rec_mod.STAGES)}")
    notes: str = ""


class ScoreIn(BaseModel):
    notes: str = Field(..., description="Interview / conversation notes to score.")


class OutreachIn(BaseModel):
    name: str
    source: str
    context: str = ""


class AgentIn(BaseModel):
    name: str
    start_date: str = Field(..., description="YYYY-MM-DD")
    license_state: str


class MonthlyStatsIn(BaseModel):
    month: str = Field(..., description="YYYY-MM")
    contacts: int
    appointments: int
    apps_submitted: int
    apps_issued: int
    apv: float
    chargebacks: float = 0.0
    persistency: float = Field(0.0, description="13-month persistency 0.0–1.0")


class PolicyIn(BaseModel):
    agent_id: str
    agent_name: str
    policy_number: str
    carrier: str
    issue_date: str = Field(..., description="YYYY-MM-DD")
    annual_premium: float
    agent_commission_pct: float = Field(..., description="e.g. 0.70 for 70%")


class LapseIn(BaseModel):
    chargeback_amount: float


# ---------------------------------------------------------------------------
# Health & dashboard
# ---------------------------------------------------------------------------
@app.get("/health", tags=["system"])
def health():
    return {"status": "ok", "agency": AGENCY["name"]}


@app.get("/dashboard", tags=["system"])
def dashboard():
    """
    Fast, AI-free home screen for the phone app: pipeline counts, this
    month's team production vs. targets, and override income snapshot.
    """
    this_month = datetime.today().strftime("%Y-%m")

    # --- Recruiting ---
    pipeline = rec_mod.pipeline_summary()
    total_recruits = sum(pipeline.values())

    # --- Production (aggregate current-month stats across the roster) ---
    agents = prod_mod._load_agents()
    team = {"apps_submitted": 0, "apps_issued": 0, "apv": 0.0, "contacts": 0}
    producing_agents = 0
    for a in agents:
        current = next(
            (m for m in a.get("monthly_stats", []) if m.get("month") == this_month),
            None,
        )
        if current:
            producing_agents += 1
            team["apps_submitted"] += current.get("apps_submitted", 0)
            team["apps_issued"] += current.get("apps_issued", 0)
            team["apv"] += current.get("apv", 0.0)
            team["contacts"] += current.get("contacts", 0)

    roster_size = len(agents)
    team_targets = {
        "apps_submitted": AGENCY["target_apps_per_month"] * roster_size,
        "apps_issued": AGENCY["target_issued_per_month"] * roster_size,
        "apv": AGENCY["target_apv_per_month"] * roster_size,
    }

    # --- Profitability (override income snapshot from the ledger) ---
    ledger = prof_mod._load_ledger()
    gross_override = sum(p.get("agency_override", 0.0) for p in ledger if p.get("status") == "active")
    chargebacks = sum(p.get("chargeback_actual", 0.0) for p in ledger if p.get("status") == "lapsed")

    return {
        "month": this_month,
        "recruiting": {
            "pipeline": pipeline,
            "total_in_pipeline": total_recruits,
            "monthly_contact_target": AGENCY["target_recruits_contacted"],
        },
        "production": {
            "roster_size": roster_size,
            "producing_this_month": producing_agents,
            "actual": team,
            "targets": team_targets,
        },
        "profitability": {
            "active_policies": sum(1 for p in ledger if p.get("status") == "active"),
            "gross_override": round(gross_override, 2),
            "chargebacks": round(chargebacks, 2),
            "net_override": round(gross_override - chargebacks, 2),
        },
    }


# ---------------------------------------------------------------------------
# Recruiting
# ---------------------------------------------------------------------------
@app.get("/recruiting/pipeline", tags=["recruiting"])
def recruiting_pipeline():
    return rec_mod.pipeline_summary()


@app.get("/recruiting/recruits", tags=["recruiting"])
def list_recruits():
    return rec_mod._load_pipeline()


@app.post("/recruiting/recruits", tags=["recruiting"], status_code=201)
def create_recruit(body: RecruitIn):
    return rec_mod.add_recruit(body.name, body.phone, body.source, body.notes, body.email)


@app.post("/recruiting/recruits/{recruit_id}/advance", tags=["recruiting"])
def advance_recruit(recruit_id: int, body: AdvanceIn):
    try:
        return rec_mod.advance_stage(recruit_id, body.stage, body.notes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/recruiting/report", tags=["recruiting"])
def recruiting_report():
    """AI pipeline health report (calls Claude)."""
    return {"report": rec_mod.pipeline_health_report()}


@app.post("/recruiting/score", tags=["recruiting"])
def score_recruit(body: ScoreIn):
    """AI candidate scoring (calls Claude)."""
    return {"result": rec_mod.score_candidate(body.notes)}


@app.post("/recruiting/outreach", tags=["recruiting"])
def outreach(body: OutreachIn):
    """AI-drafted first-contact message (calls Claude)."""
    return {"message": rec_mod.draft_outreach(body.name, body.source, body.context)}


# ---------------------------------------------------------------------------
# Production
# ---------------------------------------------------------------------------
@app.get("/production/agents", tags=["production"])
def list_agents():
    return prod_mod._load_agents()


@app.post("/production/agents", tags=["production"], status_code=201)
def create_agent(body: AgentIn):
    return prod_mod.add_agent(body.name, body.start_date, body.license_state)


@app.post("/production/agents/{agent_id}/stats", tags=["production"], status_code=201)
def log_stats(agent_id: int, body: MonthlyStatsIn):
    try:
        return prod_mod.log_monthly_stats(
            agent_id, body.month, body.contacts, body.appointments,
            body.apps_submitted, body.apps_issued, body.apv,
            body.chargebacks, body.persistency,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/production/leaderboard", tags=["production"])
def leaderboard():
    """AI team leaderboard (calls Claude)."""
    return {"leaderboard": prod_mod.team_leaderboard()}


@app.get("/production/agents/{agent_id}/scorecard", tags=["production"])
def scorecard(agent_id: int, months: int = 3):
    """AI coaching scorecard (calls Claude)."""
    try:
        return {"scorecard": prod_mod.agent_scorecard(agent_id, months=months)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/production/agents/{agent_id}/gaps", tags=["production"])
def gaps(agent_id: int):
    """AI funnel gap analysis (calls Claude)."""
    try:
        return {"analysis": prod_mod.activity_gap_analysis(agent_id)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ---------------------------------------------------------------------------
# Profitability
# ---------------------------------------------------------------------------
@app.get("/profitability/policies", tags=["profitability"])
def list_policies():
    return prof_mod._load_ledger()


@app.post("/profitability/policies", tags=["profitability"], status_code=201)
def create_policy(body: PolicyIn):
    return prof_mod.record_policy(
        agent_id=body.agent_id,
        agent_name=body.agent_name,
        policy_number=body.policy_number,
        carrier=body.carrier,
        issue_date=body.issue_date,
        annual_premium=body.annual_premium,
        agent_commission_pct=body.agent_commission_pct,
    )


@app.post("/profitability/policies/{policy_number}/lapse", tags=["profitability"])
def lapse_policy(policy_number: str, body: LapseIn):
    try:
        return prof_mod.mark_lapsed(policy_number, body.chargeback_amount)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/profitability/pnl", tags=["profitability"])
def pnl(month: str):
    """AI monthly P&L (calls Claude). month = YYYY-MM."""
    return {"report": prof_mod.monthly_pnl_report(month)}


@app.get("/profitability/chargebacks", tags=["profitability"])
def chargebacks():
    """AI chargeback exposure report (calls Claude)."""
    return {"report": prof_mod.chargeback_exposure_report()}


@app.get("/profitability/projection", tags=["profitability"])
def projection(months: int = 6):
    """AI override income projection (calls Claude)."""
    return {"report": prof_mod.override_income_projection(months)}


# ---------------------------------------------------------------------------
# Usage / cost audit
# ---------------------------------------------------------------------------
@app.get("/usage", tags=["system"])
def usage(since: Optional[str] = None):
    return cost_summary(since_date=since)
