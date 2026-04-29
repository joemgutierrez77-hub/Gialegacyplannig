"""
Recruiting module — manage candidate pipeline, score prospects, generate outreach.
"""

import json
import os
from datetime import datetime
from pathlib import Path

from config.settings import DATA_DIR
from src.claude_client import call_claude

RECRUITS_FILE = os.path.join(DATA_DIR, "recruits", "pipeline.json")
SYSTEM_PROMPT = Path(__file__).parent.parent / "prompts" / "recruiting.txt"


def _load_prompt() -> str:
    return SYSTEM_PROMPT.read_text()


def _load_pipeline() -> list:
    if not os.path.exists(RECRUITS_FILE):
        return []
    with open(RECRUITS_FILE) as f:
        return json.load(f)


def _save_pipeline(data: list) -> None:
    Path(RECRUITS_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(RECRUITS_FILE, "w") as f:
        json.dump(data, f, indent=2)


STAGES = [
    "lead",
    "contacted",
    "interviewed",
    "contracted",
    "licensed",
    "active",
    "inactive",
]


def add_recruit(name: str, phone: str, source: str, notes: str = "") -> dict:
    """Add a new recruit to the pipeline at the 'lead' stage."""
    pipeline = _load_pipeline()
    recruit = {
        "id":         len(pipeline) + 1,
        "name":       name,
        "phone":      phone,
        "source":     source,
        "stage":      "lead",
        "notes":      notes,
        "added_date": datetime.today().strftime("%Y-%m-%d"),
        "history":    [],
    }
    pipeline.append(recruit)
    _save_pipeline(pipeline)
    return recruit


def advance_stage(recruit_id: int, new_stage: str, notes: str = "") -> dict:
    """Move a recruit to the next pipeline stage."""
    if new_stage not in STAGES:
        raise ValueError(f"Invalid stage. Choose from: {STAGES}")
    pipeline = _load_pipeline()
    for r in pipeline:
        if r["id"] == recruit_id:
            r["history"].append({
                "from":  r["stage"],
                "to":    new_stage,
                "date":  datetime.today().strftime("%Y-%m-%d"),
                "notes": notes,
            })
            r["stage"] = new_stage
            _save_pipeline(pipeline)
            return r
    raise ValueError(f"Recruit ID {recruit_id} not found.")


def pipeline_summary() -> dict:
    """Count recruits at each stage."""
    pipeline = _load_pipeline()
    counts = {s: 0 for s in STAGES}
    for r in pipeline:
        counts[r["stage"]] = counts.get(r["stage"], 0) + 1
    return counts


def score_candidate(candidate_info: str) -> str:
    """
    Ask Claude to score a candidate based on interview notes.
    Uses claude-sonnet (standard tier) with cached system prompt.
    """
    prompt = _load_prompt()
    user_msg = f"""Score this candidate and provide a recommendation.

Candidate information:
{candidate_info}

Provide:
1. Score out of 100 (weighted by criteria)
2. Top 2 strengths
3. Top 2 concerns or red flags
4. Recommendation: Proceed / Proceed with caution / Do not contract
5. One specific onboarding focus if hired
"""
    return call_claude(prompt, user_msg, module="recruiting", call_type="score_candidate")


def draft_outreach(recruit_name: str, source: str, context: str = "") -> str:
    """
    Generate a personalized first-contact message for a recruit.
    Uses claude-haiku (fast tier) — simple task, low cost.
    """
    from config.settings import MODELS
    prompt = _load_prompt()
    user_msg = f"""Write a short, warm, personal first-contact text message (under 160 characters) to:

Name: {recruit_name}
Source: {source}
Context: {context if context else 'no additional context'}

The message should feel personal, not salesy. Reference our agency values (faith, family, legacy).
End with an open question to start a conversation.
"""
    return call_claude(
        prompt, user_msg,
        module="recruiting", call_type="draft_outreach",
        model=MODELS["fast"]
    )


def pipeline_health_report() -> str:
    """
    Ask Claude to analyze the current pipeline and flag conversion bottlenecks.
    """
    summary = pipeline_summary()
    pipeline = _load_pipeline()
    prompt   = _load_prompt()

    user_msg = f"""Analyze this recruiting pipeline and identify bottlenecks.

Stage counts:
{json.dumps(summary, indent=2)}

Total recruits tracked: {len(pipeline)}

Targets: 20 contacted/month, 8 interviewed/month, 3 contracted/month.

Provide:
1. Pipeline conversion rates between each stage
2. The single biggest bottleneck
3. Three specific actions to fix the bottleneck this week
4. Overall pipeline health: Healthy / At Risk / Critical
"""
    return call_claude(prompt, user_msg, module="recruiting", call_type="pipeline_report")
