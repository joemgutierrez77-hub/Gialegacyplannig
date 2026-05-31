"""Tests for src/claude_client.py — initialization, usage logging, cost summary, prompt caching."""
import json
import os
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_anthropic_response(text="OK", input_tokens=100, output_tokens=50,
                              cache_write=0, cache_read=0):
    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens
    usage.cache_creation_input_tokens = cache_write
    usage.cache_read_input_tokens = cache_read

    content = MagicMock()
    content.text = text

    resp = MagicMock()
    resp.content = [content]
    resp.usage = usage
    return resp


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the module-level _client singleton before and after every test."""
    import src.claude_client as cc
    cc._client = None
    yield
    cc._client = None


# ---------------------------------------------------------------------------
# get_client
# ---------------------------------------------------------------------------

def test_get_client_raises_without_api_key():
    with patch("src.claude_client.ANTHROPIC_API_KEY", ""):
        from src.claude_client import get_client
        with pytest.raises(EnvironmentError, match="ANTHROPIC_API_KEY"):
            get_client()


def test_get_client_returns_singleton():
    mock_anthropic = MagicMock()
    mock_instance  = MagicMock()
    mock_anthropic.Anthropic.return_value = mock_instance

    with patch("src.claude_client.ANTHROPIC_API_KEY", "sk-test"), \
         patch.dict("sys.modules", {"anthropic": mock_anthropic}):
        import src.claude_client as cc
        cc._client = None
        c1 = cc.get_client()
        c2 = cc.get_client()

    assert c1 is c2
    mock_anthropic.Anthropic.assert_called_once()


# ---------------------------------------------------------------------------
# _log_usage
# ---------------------------------------------------------------------------

def test_log_usage_writes_jsonl_record(tmp_path):
    log_file = str(tmp_path / "usage.jsonl")
    mock_usage = MagicMock()
    mock_usage.input_tokens = 200
    mock_usage.output_tokens = 75
    mock_usage.cache_creation_input_tokens = 50
    mock_usage.cache_read_input_tokens = 10

    from config.settings import MODELS
    with patch("src.claude_client.LOG_FILE", log_file):
        from src.claude_client import _log_usage
        _log_usage(MODELS["fast"], mock_usage, module="recruiting", call_type="draft")

    assert os.path.exists(log_file)
    with open(log_file) as f:
        record = json.loads(f.read().strip())

    assert record["module"]        == "recruiting"
    assert record["call_type"]     == "draft"
    assert record["input_tokens"]  == 200
    assert record["output_tokens"] == 75
    assert record["cache_write"]   == 50
    assert record["cache_read"]    == 10
    assert "est_cost_usd" in record
    assert "ts" in record


def test_log_usage_appends_multiple_records(tmp_path):
    log_file = str(tmp_path / "usage.jsonl")
    mock_usage = MagicMock()
    mock_usage.input_tokens = 10
    mock_usage.output_tokens = 5
    mock_usage.cache_creation_input_tokens = 0
    mock_usage.cache_read_input_tokens = 0

    from config.settings import MODELS
    with patch("src.claude_client.LOG_FILE", log_file):
        from src.claude_client import _log_usage
        _log_usage(MODELS["fast"], mock_usage, "recruiting", "draft")
        _log_usage(MODELS["fast"], mock_usage, "production", "report")

    with open(log_file) as f:
        lines = f.readlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["module"] == "recruiting"
    assert json.loads(lines[1])["module"] == "production"


# ---------------------------------------------------------------------------
# cost_summary
# ---------------------------------------------------------------------------

def test_cost_summary_aggregates_by_module(tmp_path):
    log_file = str(tmp_path / "usage.jsonl")
    records = [
        {"ts": "2026-05-01T10:00:00+00:00", "module": "recruiting",    "est_cost_usd": 0.002},
        {"ts": "2026-05-01T11:00:00+00:00", "module": "recruiting",    "est_cost_usd": 0.003},
        {"ts": "2026-05-01T12:00:00+00:00", "module": "profitability", "est_cost_usd": 0.010},
    ]
    with open(log_file, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    with patch("src.claude_client.LOG_FILE", log_file):
        from src.claude_client import cost_summary
        totals = cost_summary()

    assert totals["recruiting"]    == pytest.approx(0.005, abs=1e-6)
    assert totals["profitability"] == pytest.approx(0.010, abs=1e-6)


def test_cost_summary_filters_by_since_date(tmp_path):
    log_file = str(tmp_path / "usage.jsonl")
    records = [
        {"ts": "2026-04-30T23:59:00+00:00", "module": "recruiting", "est_cost_usd": 0.001},
        {"ts": "2026-05-01T00:00:00+00:00", "module": "recruiting", "est_cost_usd": 0.002},
        {"ts": "2026-05-02T10:00:00+00:00", "module": "recruiting", "est_cost_usd": 0.003},
    ]
    with open(log_file, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    with patch("src.claude_client.LOG_FILE", log_file):
        from src.claude_client import cost_summary
        totals = cost_summary(since_date="2026-05-01")

    assert totals["recruiting"] == pytest.approx(0.005, abs=1e-6)


def test_cost_summary_returns_empty_when_no_log(tmp_path):
    with patch("src.claude_client.LOG_FILE", str(tmp_path / "nonexistent.jsonl")):
        from src.claude_client import cost_summary
        assert cost_summary() == {}


def test_cost_summary_sorted_by_cost_descending(tmp_path):
    log_file = str(tmp_path / "usage.jsonl")
    records = [
        {"ts": "2026-05-01T10:00:00+00:00", "module": "recruiting",    "est_cost_usd": 0.001},
        {"ts": "2026-05-01T11:00:00+00:00", "module": "profitability", "est_cost_usd": 0.050},
        {"ts": "2026-05-01T12:00:00+00:00", "module": "production",    "est_cost_usd": 0.010},
    ]
    with open(log_file, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    with patch("src.claude_client.LOG_FILE", log_file):
        from src.claude_client import cost_summary
        totals = cost_summary()

    keys = list(totals.keys())
    assert keys[0] == "profitability"  # highest cost first


# ---------------------------------------------------------------------------
# call_claude — caching behaviour
# ---------------------------------------------------------------------------

def test_call_claude_injects_cache_control(tmp_path):
    log_file = str(tmp_path / "usage.jsonl")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_anthropic_response("Result")

    with patch("src.claude_client.get_client", return_value=mock_client), \
         patch("src.claude_client.LOG_FILE", log_file):
        from src.claude_client import call_claude
        result = call_claude("system prompt", "user msg", module="recruiting", cache_system=True)

    assert result == "Result"
    system_block = mock_client.messages.create.call_args[1]["system"]
    assert system_block[0].get("cache_control") == {"type": "ephemeral"}


def test_call_claude_skips_cache_when_disabled(tmp_path):
    log_file = str(tmp_path / "usage.jsonl")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_anthropic_response()

    with patch("src.claude_client.get_client", return_value=mock_client), \
         patch("src.claude_client.LOG_FILE", log_file):
        from src.claude_client import call_claude
        call_claude("system prompt", "user msg", module="recruiting", cache_system=False)

    system_block = mock_client.messages.create.call_args[1]["system"]
    assert "cache_control" not in system_block[0]


def test_call_claude_uses_module_model_routing(tmp_path):
    from config.settings import MODULE_MODELS
    log_file = str(tmp_path / "usage.jsonl")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_anthropic_response()

    with patch("src.claude_client.get_client", return_value=mock_client), \
         patch("src.claude_client.LOG_FILE", log_file):
        from src.claude_client import call_claude
        call_claude("sys", "msg", module="profitability")

    model_used = mock_client.messages.create.call_args[1]["model"]
    assert model_used == MODULE_MODELS["profitability"]


def test_call_claude_model_override(tmp_path):
    from config.settings import MODELS
    log_file = str(tmp_path / "usage.jsonl")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_anthropic_response()

    with patch("src.claude_client.get_client", return_value=mock_client), \
         patch("src.claude_client.LOG_FILE", log_file):
        from src.claude_client import call_claude
        call_claude("sys", "msg", module="profitability", model=MODELS["fast"])

    model_used = mock_client.messages.create.call_args[1]["model"]
    assert model_used == MODELS["fast"]
