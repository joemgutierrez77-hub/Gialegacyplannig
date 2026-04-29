"""Verify configuration values are internally consistent."""
from config.settings import MODELS, MODULE_MODELS, COST_PER_MILLION, TOKEN_LIMITS, AGENCY


def test_all_module_models_are_valid():
    valid = set(MODELS.values())
    for module, model in MODULE_MODELS.items():
        assert model in valid, f"Module '{module}' references unknown model '{model}'"


def test_cost_table_covers_all_models():
    for tier, model in MODELS.items():
        assert model in COST_PER_MILLION, f"No cost entry for {tier} model '{model}'"
        rates = COST_PER_MILLION[model]
        for key in ("input", "output", "cache_write", "cache_read"):
            assert key in rates, f"Missing '{key}' rate for model '{model}'"


def test_token_limits_cover_all_models():
    for tier, model in MODELS.items():
        assert model in TOKEN_LIMITS, f"No token limit for {tier} model '{model}'"
        assert TOKEN_LIMITS[model]["max_tokens"] > 0


def test_agency_targets_are_positive():
    for key, val in AGENCY.items():
        if isinstance(val, (int, float)):
            assert val > 0, f"Agency target '{key}' must be positive, got {val}"


def test_persistency_rate_is_fraction():
    rate = AGENCY["min_persistency_rate"]
    assert 0 < rate < 1, f"min_persistency_rate should be 0–1, got {rate}"


def test_margin_is_fraction():
    margin = AGENCY["min_profit_margin"]
    assert 0 < margin < 1, f"min_profit_margin should be 0–1, got {margin}"
