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
    "standard": "claude-sonnet-4-6",            # reports, coaching feedback, analysis
    "advanced": "claude-opus-4-7",              # strategic planning, complex scenarios
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
COST_PER_MILLION = {
    MODELS["fast"]:     {"input": 0.80,  "output": 4.00,  "cache_write": 1.00,  "cache_read": 0.08},
    MODELS["standard"]: {"input": 3.00,  "output": 15.00, "cache_write": 3.75,  "cache_read": 0.30},
    MODELS["advanced"]: {"input": 15.00, "output": 75.00, "cache_write": 18.75, "cache_read": 1.50},
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
