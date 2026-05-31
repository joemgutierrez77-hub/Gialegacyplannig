"""Edge cases for financial calculations, recruiting data layer, and SMTP notifications."""
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def isolated_profitability(tmp_path, monkeypatch):
    import config.settings as cfg
    import src.modules.profitability as prof
    monkeypatch.setattr(cfg, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(prof, "POLICIES_FILE", str(tmp_path / "policies" / "ledger.json"))
    monkeypatch.setattr(prof, "USE_AIRTABLE", False)
    yield tmp_path


@pytest.fixture
def isolated_recruiting(tmp_path, monkeypatch):
    import config.settings as cfg
    import src.modules.recruiting as rec
    monkeypatch.setattr(cfg, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(rec, "RECRUITS_FILE", str(tmp_path / "recruits" / "pipeline.json"))
    yield tmp_path


# ---------------------------------------------------------------------------
# Financial edge cases — record_policy
# ---------------------------------------------------------------------------

def test_record_policy_zero_commission(isolated_profitability):
    from src.modules.profitability import record_policy
    p = record_policy("A1", "Bob", "POL-Z", "Carrier", "2026-05-01", 5000, 0.0)
    assert p["gross_commission"]   == 0.0
    assert p["chargeback_reserve"] == 0.0
    assert p["net_to_agent"]       == 0.0
    assert p["agency_override"]    == pytest.approx(250.0)   # 5000 * 5%


def test_record_policy_full_commission(isolated_profitability):
    from src.modules.profitability import record_policy
    p = record_policy("A1", "Bob", "POL-F", "Carrier", "2026-05-01", 10000, 1.0)
    assert p["gross_commission"]   == 10000.0
    assert p["chargeback_reserve"] == pytest.approx(1000.0)  # 10% of 10000
    assert p["net_to_agent"]       == pytest.approx(9000.0)


def test_record_policy_defaults_to_active_status(isolated_profitability):
    from src.modules.profitability import record_policy
    p = record_policy("A1", "Bob", "POL-S", "Carrier", "2026-05-01", 3000, 0.70)
    assert p["status"] == "active"


# ---------------------------------------------------------------------------
# Financial edge cases — mark_lapsed
# ---------------------------------------------------------------------------

def test_mark_lapsed_chargeback_exceeds_net(isolated_profitability):
    """Net to agent can go negative when chargeback exceeds initial net — expected behavior."""
    from src.modules.profitability import record_policy, mark_lapsed
    record_policy("A1", "Joe", "POL-NEG", "Carrier", "2026-05-01", 1000, 0.70)
    p = mark_lapsed("POL-NEG", 5000.0)
    assert p["net_to_agent"] < 0
    assert p["chargeback_actual"] == 5000.0


def test_mark_lapsed_updates_status_to_lapsed(isolated_profitability):
    from src.modules.profitability import record_policy, mark_lapsed
    record_policy("A1", "Joe", "POL-LAP", "Carrier", "2026-05-01", 4000, 0.70)
    p = mark_lapsed("POL-LAP", 300.0)
    assert p["status"] == "lapsed"


def test_mark_lapsed_unknown_policy_raises(isolated_profitability):
    from src.modules.profitability import mark_lapsed
    with pytest.raises(ValueError, match="not found"):
        mark_lapsed("GHOST-999", 100.0)


# ---------------------------------------------------------------------------
# _agent_summary aggregation
# ---------------------------------------------------------------------------

def test_agent_summary_active_vs_lapsed_aggregation(isolated_profitability):
    from src.modules.profitability import record_policy, mark_lapsed, _agent_summary, _load_ledger
    record_policy("A1", "Tom", "POL-ACT", "C", "2026-05-01", 5000, 0.70)
    record_policy("A1", "Tom", "POL-LAP", "C", "2026-05-01", 3000, 0.70)
    mark_lapsed("POL-LAP", 300.0)

    summary = _agent_summary(_load_ledger())
    a = summary["A1"]
    assert a["policies_active"] == 1
    assert a["policies_lapsed"] == 1
    assert a["total_apv"]       == pytest.approx(5000.0)   # active only
    assert a["chargebacks"]     == pytest.approx(300.0)


def test_agent_summary_empty_ledger():
    from src.modules.profitability import _agent_summary
    assert _agent_summary([]) == {}


def test_agent_summary_ignores_unknown_status(isolated_profitability):
    from src.modules.profitability import _agent_summary
    ledger = [{
        "agent_id": "A1", "agent_name": "Tom", "status": "pending",
        "annual_premium": 5000, "gross_commission": 3500,
        "agency_override": 250, "net_to_agent": 3150,
    }]
    summary = _agent_summary(ledger)
    # "pending" is neither active nor lapsed — agent appears but counts are 0
    assert summary["A1"]["policies_active"] == 0
    assert summary["A1"]["policies_lapsed"] == 0
    assert summary["A1"]["total_apv"]       == 0.0


# ---------------------------------------------------------------------------
# Recruiting data layer edge cases
# ---------------------------------------------------------------------------

def test_multiple_recruits_have_sequential_ids(isolated_recruiting):
    from src.modules.recruiting import add_recruit
    r1 = add_recruit("Alice", "555-1", "event")
    r2 = add_recruit("Bob",   "555-2", "referral")
    r3 = add_recruit("Carol", "555-3", "web")
    assert r1["id"] == 1
    assert r2["id"] == 2
    assert r3["id"] == 3


def test_pipeline_summary_empty_pipeline(isolated_recruiting):
    from src.modules.recruiting import pipeline_summary
    summary = pipeline_summary()
    assert all(v == 0 for v in summary.values())
    assert "new_lead"  in summary
    assert "active"    in summary
    assert "inactive"  in summary


def test_advance_stage_to_same_stage_records_history(isolated_recruiting):
    from src.modules.recruiting import add_recruit, advance_stage
    r = add_recruit("Dave", "555-4", "cold call")
    updated = advance_stage(r["id"], "new_lead", "Re-confirmed")
    assert updated["stage"] == "new_lead"
    assert len(updated["history"]) == 1
    assert updated["history"][0]["from"] == "new_lead"
    assert updated["history"][0]["to"]   == "new_lead"


def test_advance_stage_accumulates_full_history(isolated_recruiting):
    from src.modules.recruiting import add_recruit, advance_stage
    r = add_recruit("Eve", "555-5", "referral")
    advance_stage(r["id"], "watched_info")
    advance_stage(r["id"], "committed")
    final = advance_stage(r["id"], "licensing_started")
    assert len(final["history"]) == 3
    assert final["history"][-1]["from"] == "committed"
    assert final["history"][-1]["to"]   == "licensing_started"


def test_add_recruit_empty_email_defaults_to_empty_string(isolated_recruiting):
    from src.modules.recruiting import add_recruit
    r = add_recruit("Frank", "555-6", "event")
    assert r["email"] == ""


# ---------------------------------------------------------------------------
# SMTP phase-change email
# ---------------------------------------------------------------------------

def test_smtp_skipped_when_no_smtp_config(isolated_recruiting, monkeypatch):
    """advance_stage completes silently when SMTP env vars are absent."""
    monkeypatch.delenv("SMTP_HOST",     raising=False)
    monkeypatch.delenv("SMTP_USER",     raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)

    from src.modules.recruiting import add_recruit, advance_stage
    r = add_recruit("Grace", "555-7", "web", email="grace@example.com")
    with patch("smtplib.SMTP") as mock_smtp:
        advance_stage(r["id"], "watched_info")
    mock_smtp.assert_not_called()


def test_smtp_skipped_when_recruit_has_no_email(isolated_recruiting):
    from src.modules.recruiting import add_recruit, advance_stage
    r = add_recruit("Henry", "555-8", "event")   # no email
    with patch("smtplib.SMTP") as mock_smtp:
        advance_stage(r["id"], "watched_info")
    mock_smtp.assert_not_called()


def test_smtp_called_when_fully_configured(isolated_recruiting, monkeypatch):
    monkeypatch.setenv("SMTP_HOST",     "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT",     "587")
    monkeypatch.setenv("SMTP_USER",     "user@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("FROM_EMAIL",    "noreply@example.com")

    from src.modules.recruiting import add_recruit, advance_stage
    r = add_recruit("Ivy", "555-9", "event", email="ivy@example.com")

    mock_server = MagicMock()
    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_cls.return_value.__exit__  = MagicMock(return_value=False)
        advance_stage(r["id"], "watched_info")

    mock_smtp_cls.assert_called_once_with("smtp.example.com", 587, timeout=15)
    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once_with("user@example.com", "secret")
