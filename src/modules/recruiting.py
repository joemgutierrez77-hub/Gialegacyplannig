"""
Recruiting module — manage candidate pipeline, score prospects, generate outreach.
"""

import json
import os
import smtplib
from datetime import datetime
from email.message import EmailMessage
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
    "new_lead",
    "watched_info",
    "committed",
    "licensing_started",
    "nurture",
    "cold",
    "passed_exam",
    "contracting",
    "contracted",
    "active",
    "inactive",
]


def _send_phase_change_email(recruit: dict, previous_stage: str, new_stage: str) -> None:
    """Send a phase-change email when SMTP configuration and recruit email are present."""
    to_email = recruit.get("email", "").strip()
    if not to_email:
        return

    smtp_host = os.environ.get("SMTP_HOST", "").strip()
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "").strip()
    smtp_pass = os.environ.get("SMTP_PASSWORD", "").strip()
    from_email = os.environ.get("FROM_EMAIL", smtp_user).strip()

    if not all([smtp_host, smtp_user, smtp_pass, from_email]):
        return

    msg = EmailMessage()
    msg["Subject"] = f"Your onboarding phase is now: {new_stage.replace('_', ' ').title()}"
    msg["From"] = from_email
    msg["To"] = to_email
    msg.set_content(
        f"Hi {recruit['name']},\n\n"
        f"Quick update: we moved you from {previous_stage.replace('_', ' ').title()} to "
        f"{new_stage.replace('_', ' ').title()}.\n\n"
        "Reply to this email if you need help with next steps.\n\n"
        "- GIA Legacy Planning"
    )

    with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)


def add_recruit(name: str, phone: str, source: str, notes: str = "", email: str = "") -> dict:
    """Add a new recruit to the pipeline at the 'new_lead' stage."""
    pipeline = _load_pipeline()
    recruit = {
        "id":         len(pipeline) + 1,
        "name":       name,
        "phone":      phone,
        "source":     source,
        "stage":      "new_lead",
        "notes":      notes,
        "email":      email,
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
            previous_stage = r["stage"]
            r["history"].append({
                "from":  previous_stage,
                "to":    new_stage,
                "date":  datetime.today().strftime("%Y-%m-%d"),
                "notes": notes,
            })
            r["stage"] = new_stage
            _save_pipeline(pipeline)
            _send_phase_change_email(r, previous_stage, new_stage)
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
