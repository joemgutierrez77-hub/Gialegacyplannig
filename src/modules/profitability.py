"""
Profitability module — agency-level financial analysis, contribution margins,
chargeback exposure, and override income projection.
"""

import json
import os
from pathlib import Path
from typing import Optional

from config.settings import AGENCY, DATA_DIR
from src.claude_client import call_claude

POLICIES_FILE = os.path.join(DATA_DIR, "policies", "ledger.json")
SYSTEM_PROMPT = Path(__file__).parent.parent / "prompts" / "profitability.txt"


def _load_prompt() -> str:
    return SYSTEM_PROMPT.read_text()


def _load_ledger() -> list:
    if not os.path.exists(POLICIES_FILE):
        return []
    with open(POLICIES_FILE) as f:
        return json.load(f)


def _save_ledger(data: list) -> None:
    Path(POLICIES_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(POLICIES_FILE, "w") as f:
        json.dump(data, f, indent=2)


def record_policy(
    agent_id:          int,
    agent_name:        str,
    policy_number:     str,
    carrier:           str,
    issue_date:        str,          # "YYYY-MM-DD"
    annual_premium:    float,
    agent_commission_pct: float,     # e.g. 0.70 for 70%
    status:            str = "active",  # active / lapsed / chargeback
) -> dict:
    """Add an issued policy to the agency ledger."""
    ledger   = _load_ledger()
    gross_commission = annual_premium * agent_commission_pct
    override         = annual_premium * AGENCY["override_rate"]
    reserve          = gross_commission * AGENCY["chargeback_reserve_pct"]

    entry = {
        "id":                    len(ledger) + 1,
        "agent_id":              agent_id,
        "agent_name":            agent_name,
        "policy_number":         policy_number,
        "carrier":               carrier,
        "issue_date":            issue_date,
        "annual_premium":        annual_premium,
        "agent_commission_pct":  agent_commission_pct,
        "gross_commission":      round(gross_commission, 2),
        "agency_override":       round(override, 2),
        "chargeback_reserve":    round(reserve, 2),
        "net_to_agent":          round(gross_commission - reserve, 2),
        "status":                status,
    }
    ledger.append(entry)
    _save_ledger(ledger)
    return entry


def mark_lapsed(policy_number: str, chargeback_amount: float) -> dict:
    """Record a policy lapse and chargeback against the agent."""
    ledger = _load_ledger()
    for p in ledger:
        if p["policy_number"] == policy_number:
            p["status"]             = "lapsed"
            p["chargeback_actual"]  = chargeback_amount
            p["net_to_agent"]       = p["net_to_agent"] - chargeback_amount
            _save_ledger(ledger)
            return p
    raise ValueError(f"Policy {policy_number} not found.")


def _agent_summary(ledger: list) -> dict:
    """Aggregate ledger by agent for financial analysis."""
    agents: dict = {}
    for p in ledger:
        aid  = p["agent_id"]
        name = p["agent_name"]
        if aid not in agents:
            agents[aid] = {
                "name":              name,
                "policies_active":   0,
                "policies_lapsed":   0,
                "total_apv":         0.0,
                "gross_commission":  0.0,
                "agency_override":   0.0,
                "chargebacks":       0.0,
                "net_commission":    0.0,
            }
        a = agents[aid]
        if p["status"] == "active":
            a["policies_active"]  += 1
            a["total_apv"]        += p["annual_premium"]
            a["gross_commission"] += p["gross_commission"]
            a["agency_override"]  += p["agency_override"]
            a["net_commission"]   += p["net_to_agent"]
        elif p["status"] == "lapsed":
            a["policies_lapsed"]  += 1
            a["chargebacks"]      += p.get("chargeback_actual", 0)
            a["net_commission"]   -= p.get("chargeback_actual", 0)

    return agents


def monthly_pnl_report(month: str) -> str:
    """
    Generate a full agency P&L analysis for the given month (YYYY-MM).
    Uses claude-opus (advanced) — complex financial reasoning.
    """
    ledger = [p for p in _load_ledger() if p["issue_date"].startswith(month)]
    agents = _agent_summary(ledger)
    prompt = _load_prompt()

    total_apv        = sum(a["total_apv"]        for a in agents.values())
    total_override   = sum(a["agency_override"]  for a in agents.values())
    total_chargebacks= sum(a["chargebacks"]       for a in agents.values())

    user_msg = f"""Generate a full agency P&L report for {month}.

Agency: {AGENCY['name']}
Override rate: {AGENCY['override_rate']*100:.1f}%
Chargeback reserve: {AGENCY['chargeback_reserve_pct']*100:.0f}%
Minimum profit margin target: {AGENCY['min_profit_margin']*100:.0f}%

Month summary:
- Total APV written:      ${total_apv:,.2f}
- Total agency override:  ${total_override:,.2f}
- Total chargebacks:      ${total_chargebacks:,.2f}
- Net override income:    ${total_override - total_chargebacks:,.2f}

Per-agent breakdown:
{json.dumps(list(agents.values()), indent=2)}

Provide:
1. Agency P&L table (gross override, chargebacks, net, margin %)
2. Top 3 agents by contribution (Pareto analysis)
3. Agents whose chargebacks exceeded their current production override
4. Persistency risk flag if lapse rate > 15%
5. Three specific actions to improve net margin next month
"""
    return call_claude(prompt, user_msg, module="profitability", call_type="monthly_pnl")


def chargeback_exposure_report() -> str:
    """
    Identify which active policies are at highest chargeback risk
    (issued in last 13 months with no persistency data = high risk).
    Uses claude-sonnet (standard) — analytical but not complex.
    """
    ledger = [p for p in _load_ledger() if p["status"] == "active"]
    prompt = _load_prompt()

    user_msg = f"""Analyze chargeback exposure for these active policies.

Active policy ledger:
{json.dumps(ledger[:50], indent=2)}

Total active policies shown: {len(ledger)}
Chargeback reserve rate: {AGENCY['chargeback_reserve_pct']*100:.0f}%

Identify:
1. Total gross commission at chargeback risk (policies < 13 months old)
2. Which agents carry the highest dollar exposure
3. Recommended reserve amount to hold
4. Action steps to improve persistency on at-risk policies
"""
    return call_claude(prompt, user_msg, module="profitability", call_type="chargeback_exposure")


def override_income_projection(months_ahead: int = 6) -> str:
    """
    Project agency override income based on current agent count and production trends.
    """
    ledger = _load_ledger()
    agents = _agent_summary(ledger)
    prompt = _load_prompt()

    user_msg = f"""Project agency override income for the next {months_ahead} months.

Current agency state:
- Active agents: {sum(1 for a in agents.values() if a['policies_active'] > 0)}
- Total active APV: ${sum(a['total_apv'] for a in agents.values()):,.2f}
- Monthly override rate: {AGENCY['override_rate']*100:.1f}%
- Target apps per agent per month: {AGENCY['target_apps_per_month']}
- Target APV per agent per month: ${AGENCY['target_apv_per_month']:,}
- Historical chargeback rate: ~{AGENCY['chargeback_reserve_pct']*100:.0f}%

Agent production summary:
{json.dumps([
    {k: v for k, v in a.items() if k in ['name','policies_active','total_apv','agency_override','chargebacks']}
    for a in agents.values()
], indent=2)}

Project:
1. Conservative / base / optimistic override income for each of the next {months_ahead} months
2. Break-even point (override income vs. agency fixed costs — assume $3,000/month overhead)
3. How many additional producing agents are needed to hit ${AGENCY['min_profit_margin']*100:.0f}% margin
4. Recruiting investment required to add those agents (licensing + onboarding = ~$500/agent)
"""
    return call_claude(prompt, user_msg, module="profitability", call_type="income_projection")
