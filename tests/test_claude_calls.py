"""Tests for all Claude-AI-powered functions across recruiting, production, and profitability.
All tests mock call_claude to avoid live API calls.
"""
import pytest
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def isolated_recruiting(tmp_path, monkeypatch):
    import config.settings as cfg
    import src.modules.recruiting as rec
    monkeypatch.setattr(cfg, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(rec, "RECRUITS_FILE", str(tmp_path / "recruits" / "pipeline.json"))
    yield tmp_path


@pytest.fixture
def isolated_production(tmp_path, monkeypatch):
    import config.settings as cfg
    import src.modules.production as prod
    monkeypatch.setattr(cfg, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(prod, "AGENTS_FILE", str(tmp_path / "agents" / "roster.json"))
    yield tmp_path


@pytest.fixture
def isolated_profitability(tmp_path, monkeypatch):
    import config.settings as cfg
    import src.modules.profitability as prof
    monkeypatch.setattr(cfg, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(prof, "POLICIES_FILE", str(tmp_path / "policies" / "ledger.json"))
    monkeypatch.setattr(prof, "USE_AIRTABLE", False)
    yield tmp_path


# ---------------------------------------------------------------------------
# Recruiting: score_candidate
# ---------------------------------------------------------------------------

def test_score_candidate_calls_claude_with_candidate_info():
    with patch("src.modules.recruiting.call_claude", return_value="Score: 85/100") as mock_cc:
        from src.modules.recruiting import score_candidate
        result = score_candidate("10 years experience, strong network")

    mock_cc.assert_called_once()
    _, user_msg = mock_cc.call_args[0][0], mock_cc.call_args[0][1]
    assert "10 years experience" in user_msg
    assert mock_cc.call_args[1]["module"] == "recruiting"
    assert mock_cc.call_args[1]["call_type"] == "score_candidate"
    assert result == "Score: 85/100"


# ---------------------------------------------------------------------------
# Recruiting: draft_outreach
# ---------------------------------------------------------------------------

def test_draft_outreach_uses_haiku_model():
    from config.settings import MODELS
    with patch("src.modules.recruiting.call_claude", return_value="Hey Jane!") as mock_cc:
        from src.modules.recruiting import draft_outreach
        result = draft_outreach("Jane Doe", "referral", "met at church")

    _, user_msg = mock_cc.call_args[0][0], mock_cc.call_args[0][1]
    assert "Jane Doe" in user_msg
    assert "referral" in user_msg
    assert mock_cc.call_args[1]["model"] == MODELS["fast"]
    assert result == "Hey Jane!"


def test_draft_outreach_without_context_uses_fallback_text():
    with patch("src.modules.recruiting.call_claude", return_value="Hi!") as mock_cc:
        from src.modules.recruiting import draft_outreach
        draft_outreach("Bob Smith", "cold call")

    _, user_msg = mock_cc.call_args[0][0], mock_cc.call_args[0][1]
    assert "no additional context" in user_msg


# ---------------------------------------------------------------------------
# Recruiting: pipeline_health_report
# ---------------------------------------------------------------------------

def test_pipeline_health_report_includes_stage_counts(isolated_recruiting):
    from src.modules.recruiting import add_recruit, pipeline_health_report
    add_recruit("Alice", "555-1", "event")
    add_recruit("Bob", "555-2", "referral")

    with patch("src.modules.recruiting.call_claude", return_value="Healthy pipeline") as mock_cc:
        result = pipeline_health_report()

    _, user_msg = mock_cc.call_args[0][0], mock_cc.call_args[0][1]
    assert "new_lead" in user_msg
    assert mock_cc.call_args[1]["module"] == "recruiting"
    assert mock_cc.call_args[1]["call_type"] == "pipeline_report"
    assert result == "Healthy pipeline"


# ---------------------------------------------------------------------------
# Production: agent_scorecard
# ---------------------------------------------------------------------------

def test_agent_scorecard_calls_claude(isolated_production):
    from src.modules.production import add_agent, log_monthly_stats, agent_scorecard
    a = add_agent("Tom Rivera", "2025-01-01", "TX")
    log_monthly_stats(a["id"], "2026-04", 80, 30, 8, 6, 9000, 0, 0.90)

    with patch("src.modules.production.call_claude", return_value="Coaching report") as mock_cc:
        result = agent_scorecard(a["id"])

    _, user_msg = mock_cc.call_args[0][0], mock_cc.call_args[0][1]
    assert "Tom Rivera" in user_msg
    assert mock_cc.call_args[1]["module"] == "production"
    assert mock_cc.call_args[1]["call_type"] == "agent_scorecard"
    assert result == "Coaching report"


def test_agent_scorecard_unknown_id_raises(isolated_production):
    from src.modules.production import agent_scorecard
    with pytest.raises(ValueError, match="not found"):
        agent_scorecard(999)


def test_agent_scorecard_respects_months_param(isolated_production):
    from src.modules.production import add_agent, log_monthly_stats, agent_scorecard
    a = add_agent("Sam Lee", "2025-06-01", "CA")
    for m in ["2026-01", "2026-02", "2026-03", "2026-04"]:
        log_monthly_stats(a["id"], m, 50, 20, 6, 4, 7000, 0, 0.88)

    with patch("src.modules.production.call_claude", return_value="report") as mock_cc:
        agent_scorecard(a["id"], months=2)

    _, user_msg = mock_cc.call_args[0][0], mock_cc.call_args[0][1]
    assert "2026-04" in user_msg
    assert "2026-03" in user_msg
    assert "2026-01" not in user_msg


# ---------------------------------------------------------------------------
# Production: team_leaderboard
# ---------------------------------------------------------------------------

def test_team_leaderboard_uses_haiku_model(isolated_production):
    from config.settings import MODELS
    from src.modules.production import add_agent, log_monthly_stats, team_leaderboard
    a = add_agent("Maria Cruz", "2025-03-01", "FL")
    log_monthly_stats(a["id"], "2026-04", 60, 25, 7, 5, 8000, 0, 0.87)

    with patch("src.modules.production.call_claude", return_value="Leaderboard") as mock_cc:
        result = team_leaderboard()

    assert mock_cc.call_args[1]["model"] == MODELS["fast"]
    assert result == "Leaderboard"


def test_team_leaderboard_with_no_agents(isolated_production):
    with patch("src.modules.production.call_claude", return_value="No agents yet") as mock_cc:
        from src.modules.production import team_leaderboard
        team_leaderboard()

    _, user_msg = mock_cc.call_args[0][0], mock_cc.call_args[0][1]
    assert "[]" in user_msg


# ---------------------------------------------------------------------------
# Production: activity_gap_analysis
# ---------------------------------------------------------------------------

def test_activity_gap_analysis_includes_funnel_data(isolated_production):
    from src.modules.production import add_agent, log_monthly_stats, activity_gap_analysis
    a = add_agent("Lena Park", "2025-09-01", "NY")
    log_monthly_stats(a["id"], "2026-04", 100, 20, 10, 7, 12000, 0, 0.91)

    with patch("src.modules.production.call_claude", return_value="Gap analysis") as mock_cc:
        result = activity_gap_analysis(a["id"])

    _, user_msg = mock_cc.call_args[0][0], mock_cc.call_args[0][1]
    assert "100" in user_msg
    assert "20" in user_msg
    assert mock_cc.call_args[1]["call_type"] == "gap_analysis"
    assert result == "Gap analysis"


def test_activity_gap_analysis_unknown_id_raises(isolated_production):
    from src.modules.production import activity_gap_analysis
    with pytest.raises(ValueError, match="not found"):
        activity_gap_analysis(999)


# ---------------------------------------------------------------------------
# Profitability: monthly_pnl_report
# ---------------------------------------------------------------------------

def test_monthly_pnl_report_calls_claude(isolated_profitability):
    from src.modules.profitability import record_policy, monthly_pnl_report
    record_policy("A1", "Tom Jones", "POL-001", "Foresters", "2026-04-10", 5000, 0.70)

    with patch("src.modules.profitability.call_claude", return_value="P&L report") as mock_cc:
        result = monthly_pnl_report("2026-04")

    _, user_msg = mock_cc.call_args[0][0], mock_cc.call_args[0][1]
    assert "2026-04" in user_msg
    assert mock_cc.call_args[1]["module"] == "profitability"
    assert mock_cc.call_args[1]["call_type"] == "monthly_pnl"
    assert result == "P&L report"


# ---------------------------------------------------------------------------
# Profitability: chargeback_exposure_report
# ---------------------------------------------------------------------------

def test_chargeback_exposure_report_calls_claude(isolated_profitability):
    from src.modules.profitability import record_policy, chargeback_exposure_report
    record_policy("A1", "Tom Jones", "POL-002", "Foresters", "2026-01-01", 6000, 0.70)

    with patch("src.modules.profitability.call_claude", return_value="Exposure report") as mock_cc:
        result = chargeback_exposure_report()

    assert mock_cc.call_args[1]["call_type"] == "chargeback_exposure"
    assert result == "Exposure report"


# ---------------------------------------------------------------------------
# Profitability: override_income_projection
# ---------------------------------------------------------------------------

def test_override_income_projection_calls_claude(isolated_profitability):
    from src.modules.profitability import record_policy, override_income_projection
    record_policy("A1", "Tom Jones", "POL-003", "Foresters", "2026-01-01", 5000, 0.70)

    with patch("src.modules.profitability.call_claude", return_value="Projection") as mock_cc:
        result = override_income_projection(months_ahead=3)

    _, user_msg = mock_cc.call_args[0][0], mock_cc.call_args[0][1]
    assert "3" in user_msg
    assert mock_cc.call_args[1]["call_type"] == "income_projection"
    assert result == "Projection"
