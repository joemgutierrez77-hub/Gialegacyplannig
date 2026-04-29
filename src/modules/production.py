"""
Production module — track agent activity, metrics, and generate coaching reports.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from config.settings import AGENCY, DATA_DIR
from src.claude_client import call_claude

AGENTS_FILE   = os.path.join(DATA_DIR, "agents", "roster.json")
SYSTEM_PROMPT = Path(__file__).parent.parent / "prompts" / "production.txt"


def _load_prompt() -> str:
    return SYSTEM_PROMPT.read_text()


def _load_agents() -> list:
    if not os.path.exists(AGENTS_FILE):
        return []
    with open(AGENTS_FILE) as f:
        return json.load(f)


def _save_agents(data: list) -> None:
    Path(AGENTS_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(AGENTS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def add_agent(name: str, start_date: str, license_state: str) -> dict:
    """Add a newly contracted agent to the roster."""
    agents = _load_agents()
    agent = {
        "id":            len(agents) + 1,
        "name":          name,
        "start_date":    start_date,
        "license_state": license_state,
        "status":        "active",
        "monthly_stats": [],
    }
    agents.append(agent)
    _save_agents(agents)
    return agent


def log_monthly_stats(
    agent_id: int,
    month: str,            # "YYYY-MM"
    contacts: int,
    appointments: int,
    apps_submitted: int,
    apps_issued: int,
    apv: float,            # Annual Premium Value of issued policies
    chargebacks: float,    # $ of chargebacks received this month
    persistency: float,    # 13-month persistency rate (0.0–1.0)
) -> dict:
    """Record one month of production data for an agent."""
    agents = _load_agents()
    for a in agents:
        if a["id"] == agent_id:
            record = {
                "month":          month,
                "contacts":       contacts,
                "appointments":   appointments,
                "apps_submitted": apps_submitted,
                "apps_issued":    apps_issued,
                "apv":            apv,
                "chargebacks":    chargebacks,
                "persistency":    persistency,
                "logged_at":      datetime.today().strftime("%Y-%m-%d"),
            }
            a["monthly_stats"].append(record)
            _save_agents(agents)
            return record
    raise ValueError(f"Agent ID {agent_id} not found.")


def agent_scorecard(agent_id: int, months: int = 3) -> str:
    """
    Generate a Claude coaching report for one agent based on recent stats.
    Automatically flags chargeback risk and identifies the production bottleneck.
    """
    agents  = _load_agents()
    agent   = next((a for a in agents if a["id"] == agent_id), None)
    if not agent:
        raise ValueError(f"Agent ID {agent_id} not found.")

    recent = agent["monthly_stats"][-months:] if agent["monthly_stats"] else []
    prompt = _load_prompt()

    user_msg = f"""Generate a production coaching report for this agent.

Agent: {agent['name']}
Tenure: started {agent['start_date']}
License state: {agent['license_state']}

Recent {months}-month production data:
{json.dumps(recent, indent=2)}

Agency targets:
- Apps submitted/month: {AGENCY['target_apps_per_month']}
- Issued policies/month: {AGENCY['target_issued_per_month']}
- APV/month target: ${AGENCY['target_apv_per_month']:,}
- Minimum persistency: {AGENCY['min_persistency_rate']*100:.0f}%
"""
    return call_claude(prompt, user_msg, module="production", call_type="agent_scorecard")


def team_leaderboard() -> str:
    """
    Rank all agents by last-month APV and flag who is above/below target.
    Uses claude-haiku (fast) — straightforward ranking task.
    """
    from config.settings import MODELS
    agents = _load_agents()
    prompt = _load_prompt()

    # Build compact summary for each agent
    summaries = []
    for a in agents:
        last = a["monthly_stats"][-1] if a["monthly_stats"] else {}
        summaries.append({
            "name":        a["name"],
            "last_month":  last.get("month", "no data"),
            "apv":         last.get("apv", 0),
            "apps_issued": last.get("apps_issued", 0),
            "persistency": last.get("persistency", None),
        })

    user_msg = f"""Create a team leaderboard ranked by APV.

Team data (last month):
{json.dumps(summaries, indent=2)}

Target APV per agent per month: ${AGENCY['target_apv_per_month']:,}

Show:
1. Ranked table (rank, name, APV, vs target %, persistency status)
2. Who is at risk of chargeback (persistency < {AGENCY['min_persistency_rate']*100:.0f}%)
3. One-line recognition for #1 agent
4. One-line priority action for last-place agent
"""
    return call_claude(
        prompt, user_msg,
        module="production", call_type="leaderboard",
        model=MODELS["fast"]
    )


def activity_gap_analysis(agent_id: int) -> str:
    """
    Pinpoint where an agent is losing deals in their funnel.
    """
    agents = _load_agents()
    agent  = next((a for a in agents if a["id"] == agent_id), None)
    if not agent:
        raise ValueError(f"Agent ID {agent_id} not found.")

    last = agent["monthly_stats"][-1] if agent["monthly_stats"] else {}
    prompt = _load_prompt()

    user_msg = f"""Perform an activity gap analysis for this agent.

Agent: {agent['name']}
Last month's funnel:
  Contacts made:       {last.get('contacts', 0)}
  Appointments set:    {last.get('appointments', 0)}
  Apps submitted:      {last.get('apps_submitted', 0)}
  Apps issued:         {last.get('apps_issued', 0)}
  APV:                 ${last.get('apv', 0):,.0f}

Calculate each conversion rate, compare to these benchmarks:
  Contact → Appointment:  30%+
  Appointment → App:      60%+
  App → Issued:           75%+

Identify exactly where the funnel breaks down and give a targeted fix.
"""
    return call_claude(prompt, user_msg, module="production", call_type="gap_analysis")
