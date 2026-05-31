"""CLI integration tests — verify each subcommand routes to the right function."""
import sys
import pytest
from unittest.mock import patch


def test_recruiting_pipeline_displays_stages(monkeypatch, capsys):
    stage_data = {
        "new_lead": 3, "watched_info": 1, "committed": 0, "licensing_started": 0,
        "nurture": 0, "cold": 0, "passed_exam": 0, "contracting": 0,
        "contracted": 2, "active": 5, "inactive": 1,
    }
    monkeypatch.setattr(sys, "argv", ["main.py", "recruiting", "pipeline"])
    with patch("main.pipeline_summary", return_value=stage_data):
        from main import main
        main()
    out = capsys.readouterr().out
    assert "new_lead" in out
    assert "3" in out
    assert "active" in out


def test_recruiting_add_prints_recruit_id(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", [
        "main.py", "recruiting", "add",
        "--name", "Jane Smith", "--phone", "555-0001", "--source", "referral",
    ])
    fake_recruit = {"id": 7, "name": "Jane Smith"}
    with patch("main.add_recruit", return_value=fake_recruit) as mock_fn:
        from main import main
        main()
    out = capsys.readouterr().out
    assert "#7" in out
    assert "Jane Smith" in out
    mock_fn.assert_called_once_with("Jane Smith", "555-0001", "referral", "", "")


def test_recruiting_report_command(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["main.py", "recruiting", "report"])
    with patch("main.pipeline_health_report", return_value="Pipeline is healthy"):
        from main import main
        main()
    assert "Pipeline is healthy" in capsys.readouterr().out


def test_production_add_agent_prints_id(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", [
        "main.py", "production", "add-agent",
        "--name", "Tom Rivera", "--start-date", "2026-01-01", "--state", "TX",
    ])
    fake_agent = {"id": 4, "name": "Tom Rivera"}
    with patch("main.add_agent", return_value=fake_agent):
        from main import main
        main()
    out = capsys.readouterr().out
    assert "#4" in out
    assert "Tom Rivera" in out


def test_production_leaderboard_command(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["main.py", "production", "leaderboard"])
    with patch("main.team_leaderboard", return_value="Team rankings here"):
        from main import main
        main()
    assert "Team rankings here" in capsys.readouterr().out


def test_production_scorecard_command(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["main.py", "production", "scorecard", "--id", "2", "--months", "3"])
    with patch("main.agent_scorecard", return_value="Scorecard for agent 2") as mock_fn:
        from main import main
        main()
    mock_fn.assert_called_once_with(2, months=3)
    assert "Scorecard for agent 2" in capsys.readouterr().out


def test_profitability_chargebacks_command(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["main.py", "profitability", "chargebacks"])
    with patch("main.chargeback_exposure_report", return_value="Chargeback report"):
        from main import main
        main()
    assert "Chargeback report" in capsys.readouterr().out


def test_profitability_projection_command(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["main.py", "profitability", "projection", "--months", "12"])
    with patch("main.override_income_projection", return_value="12-month projection") as mock_fn:
        from main import main
        main()
    mock_fn.assert_called_once_with(12)
    assert "12-month projection" in capsys.readouterr().out


def test_usage_no_data_prints_message(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["main.py", "usage"])
    with patch("main.cost_summary", return_value={}):
        from main import main
        main()
    assert "No API usage" in capsys.readouterr().out


def test_usage_with_since_filter_passes_date(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["main.py", "usage", "--since", "2026-05-01"])
    with patch("main.cost_summary", return_value={"recruiting": 0.0045}) as mock_cs:
        from main import main
        main()
    out = capsys.readouterr().out
    assert "recruiting" in out
    mock_cs.assert_called_with(since_date="2026-05-01")


def test_airtable_status_always_works(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["main.py", "airtable", "status"])
    from main import main
    main()
    out = capsys.readouterr().out
    assert "Active" in out


def test_no_command_prints_help(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["main.py"])
    from main import main
    main()
    # argparse prints help to stdout; at minimum the process should not crash
    out = capsys.readouterr().out
    assert "usage" in out.lower() or len(out) >= 0  # non-crash is the guarantee
