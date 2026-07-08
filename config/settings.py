"""
Central configuration — all model choices, cost rates, and business thresholds live here.
Changing a model or rate in one place updates the entire system.
"""
import os

# ---------------------------------------------------------------------------
# Claude model tiers — keep costs low by matching model to task complexity
# ---------------------------------------------------------------------------
MODELS = {
    "fast":     "claude-haiku-4-5-20251001",   # data entry, simple Q&A, routing
    "standard": "claude-sonnet-5",              # reports, coaching feedback, analysis
    "advanced": "claude-opus-4-8",              # strategic planning, complex scenarios
}

# Default model per business module
MODULE_MODELS = {
    "recruiting":    MODELS["standard"],
    "production":    MODELS["standard"],
    "profitability": MODELS["advanced"],
    "data_entry":    MODELS["fast"],
    "coaching":      MODELS["standard"],
}

# ---------------------------------------------------------------------------
# API cost tracking (per million tokens, USD) — update if Anthropic pricing changes
# ---------------------------------------------------------------------------
# Cache-write is ~1.25x the input rate, cache-read is ~0.1x. List prices below;
# Sonnet 5 has promotional input/output pricing ($2/$10) through 2026-08-31.
COST_PER_MILLION = {
    MODELS["fast"]:     {"input": 1.00, "output": 5.00,  "cache_write": 1.25, "cache_read": 0.10},
    MODELS["standard"]: {"input": 3.00, "output": 15.00, "cache_write": 3.75, "cache_read": 0.30},
    MODELS["advanced"]: {"input": 5.00, "output": 25.00, "cache_write": 6.25, "cache_read": 0.50},
}

# ---------------------------------------------------------------------------
# Agency business thresholds
# ---------------------------------------------------------------------------
AGENCY = {
    "name": "GIA Legacy Planning",

    # Production targets (monthly, per agent)
    "target_apps_per_month":       8,       # submitted applications
    "target_issued_per_month":     6,       # issued policies
    "target_apv_per_month":        10000,   # Annual Premium Value ($)
    "min_persistency_rate":        0.85,    # 13-month persistency floor

    # Recruiting targets (monthly)
    "target_recruits_contacted":   20,
    "target_recruits_interviewed": 8,
    "target_contracts_issued":     3,

    # Profitability thresholds
    "min_profit_margin":           0.20,    # 20% agency margin floor
    "override_rate":               0.05,    # 5% override on agent production
    "chargeback_reserve_pct":      0.10,    # hold 10% of commissions for chargebacks
}

# ---------------------------------------------------------------------------
# Token budget guardrails (per single API call)
# ---------------------------------------------------------------------------
TOKEN_LIMITS = {
    MODELS["fast"]:     {"max_tokens": 1024},
    MODELS["standard"]: {"max_tokens": 2048},
    MODELS["advanced"]: {"max_tokens": 4096},
}

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
DATA_DIR          = os.path.join(os.path.dirname(__file__), "..", "data")
LOG_FILE          = os.path.join(DATA_DIR, "api_usage.jsonl")

# ---------------------------------------------------------------------------
# Airtable integration
# Set AIRTABLE_API_KEY and AIRTABLE_BASE_ID as environment variables.
# When both are present the system reads/writes Airtable instead of local JSON.
# Base ID is visible in your Airtable URL: airtable.com/<BASE_ID>/...
# ---------------------------------------------------------------------------
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "app6n6AKwbFtlsnXy")

# Table names — must match exactly what appears in your Airtable base
AIRTABLE_TABLES = {
    "pending":   os.environ.get("AIRTABLE_TABLE_PENDING",   "Pending"),
    "issued":    os.environ.get("AIRTABLE_TABLE_ISSUED",     "Issued"),
    "recruits":  os.environ.get("AIRTABLE_TABLE_RECRUITS",   "Recruits"),
    "agents":    os.environ.get("AIRTABLE_TABLE_AGENTS",     "Agents"),
}

# Field name mapping: internal key → your Airtable column name
# Edit the right-hand values to match your actual column headers.
AIRTABLE_FIELDS = {
    # --- Shared / identity ---
    "agent_name":           "Agent Name",
    "agent_id":             "Agent ID",

    # --- Pending applications table ---
    "applicant_name":       "Applicant Name",
    "carrier":              "Carrier",
    "face_amount":          "Face Amount",
    "annual_premium":       "Annual Premium",
    "submit_date":          "Submit Date",
    "app_status":           "Status",           # e.g. "Pending", "Approved", "Declined"
    "policy_number":        "Policy Number",

    # --- Issued policies table ---
    "issue_date":           "Issue Date",
    "commission_pct":       "Commission %",
    "gross_commission":     "Gross Commission",
    "agency_override":      "Agency Override",
    "chargeback_reserve":   "Chargeback Reserve",
    "net_to_agent":         "Net to Agent",
    "policy_status":        "Policy Status",    # "Active", "Lapsed", "Chargeback"
    "chargeback_amount":    "Chargeback Amount",
    "persistency":          "Persistency Rate",

    # --- Recruits table ---
    "recruit_name":         "Name",
    "recruit_phone":        "Phone",
    "recruit_source":       "Source",
    "recruit_stage":        "Stage",
    "recruit_notes":        "Notes",
    "recruit_added_date":   "Added Date",

    # --- Agents table ---
    "start_date":           "Start Date",
    "license_state":        "License State",
    "agent_status":         "Status",
}

USE_AIRTABLE = bool(AIRTABLE_API_KEY and AIRTABLE_BASE_ID)
