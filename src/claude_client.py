"""
Centralized Claude API client.

Key cost-control features:
  - Prompt caching: system prompts are cached; repeated calls pay ~10x less
  - Model routing: each call picks the cheapest model that fits the task
  - Token budgets: per-model max_tokens caps prevent runaway output
  - Usage logging: every call is written to data/api_usage.jsonl for cost auditing
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config.settings import (
    ANTHROPIC_API_KEY,
    COST_PER_MILLION,
    LOG_FILE,
    MODULE_MODELS,
    TOKEN_LIMITS,
)

# Singleton client — one connection, reused across all modules
_client = None


def get_client():
    global _client
    if _client is None:
        import anthropic as _anthropic
        if not ANTHROPIC_API_KEY:
            raise EnvironmentError("ANTHROPIC_API_KEY is not set.")
        _client = _anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


def _log_usage(model: str, usage, module: str, call_type: str) -> dict:
    """Write token counts and estimated cost to the usage log."""
    rates = COST_PER_MILLION.get(model, {})
    input_tokens  = getattr(usage, "input_tokens", 0)
    output_tokens = getattr(usage, "output_tokens", 0)
    cache_write   = getattr(usage, "cache_creation_input_tokens", 0)
    cache_read    = getattr(usage, "cache_read_input_tokens", 0)

    cost = (
        (input_tokens  / 1_000_000) * rates.get("input",       0) +
        (output_tokens / 1_000_000) * rates.get("output",      0) +
        (cache_write   / 1_000_000) * rates.get("cache_write", 0) +
        (cache_read    / 1_000_000) * rates.get("cache_read",  0)
    )

    record = {
        "ts":            datetime.now(timezone.utc).isoformat(),
        "module":        module,
        "call_type":     call_type,
        "model":         model,
        "input_tokens":  input_tokens,
        "output_tokens": output_tokens,
        "cache_write":   cache_write,
        "cache_read":    cache_read,
        "est_cost_usd":  round(cost, 6),
    }

    Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(record) + "\n")

    return record


def call_claude(
    system_prompt: str,
    user_message: str,
    module: str = "general",
    call_type: str = "query",
    model: Optional[str] = None,
    cache_system: bool = True,
) -> str:
    """
    Single entry point for all Claude calls in this project.

    Args:
        system_prompt:  The role/context prompt. Cached by default — first call
                        writes the cache, subsequent calls pay ~10x less.
        user_message:   The specific user request (not cached — changes each call).
        module:         Business module name, used for model routing and logging.
        call_type:      Short label for the log (e.g. "report", "score", "draft").
        model:          Override the auto-selected model.
        cache_system:   Set False to skip caching (useful for one-off calls).

    Returns:
        The assistant's text response.
    """
    client    = get_client()
    model     = model or MODULE_MODELS.get(module, MODULE_MODELS["production"])
    max_tok   = TOKEN_LIMITS[model]["max_tokens"]

    system_block: list = [{"type": "text", "text": system_prompt}]
    if cache_system:
        system_block[0]["cache_control"] = {"type": "ephemeral"}

    response = client.messages.create(
        model=model,
        max_tokens=max_tok,
        system=system_block,
        messages=[{"role": "user", "content": user_message}],
    )

    _log_usage(model, response.usage, module, call_type)
    return response.content[0].text


def cost_summary(since_date: Optional[str] = None) -> dict:
    """
    Read the usage log and return aggregated cost by module.
    since_date format: 'YYYY-MM-DD'  (filters to that day onward)
    """
    if not os.path.exists(LOG_FILE):
        return {}

    totals: dict = {}
    with open(LOG_FILE) as f:
        for line in f:
            r = json.loads(line)
            if since_date and r["ts"][:10] < since_date:
                continue
            mod  = r["module"]
            cost = r["est_cost_usd"]
            totals[mod] = totals.get(mod, 0.0) + cost

    return {k: round(v, 4) for k, v in sorted(totals.items(), key=lambda x: -x[1])}
