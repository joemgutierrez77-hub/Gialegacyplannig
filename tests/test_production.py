"""Test production data layer (no API calls)."""
import pytest


@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    import config.settings as cfg
    monkeypatch.setattr(cfg, "DATA_DIR", str(tmp_path))
    import src.modules.production as prod
    monkeypatch.setattr(prod, "AGENTS_FILE", str(tmp_path / "agents" / "roster.json"))
    yield tmp_path


def test_add_agent():
    from src.modules.production import add_agent, _load_agents
    a = add_agent("Tom Jones", "2026-01-15", "TX")
    assert a["name"] == "Tom Jones"
    assert a["status"] == "active"
    assert _load_agents()[0]["id"] == 1


def test_log_monthly_stats():
    from src.modules.production import add_agent, log_monthly_stats
    a = add_agent("Sara Lee", "2026-02-01", "FL")
    record = log_monthly_stats(
        a["id"], "2026-04",
        contacts=80, appointments=25, apps_submitted=10,
        apps_issued=8, apv=12000, chargebacks=0, persistency=0.91
    )
    assert record["apv"] == 12000
    assert record["persistency"] == 0.91


def test_log_stats_unknown_agent_raises():
    from src.modules.production import log_monthly_stats
    with pytest.raises(ValueError, match="not found"):
        log_monthly_stats(999, "2026-04", 0, 0, 0, 0, 0, 0, 0)
