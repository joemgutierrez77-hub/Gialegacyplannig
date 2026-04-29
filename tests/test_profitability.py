"""Test profitability data layer (no API calls)."""
import pytest


@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    import config.settings as cfg
    monkeypatch.setattr(cfg, "DATA_DIR", str(tmp_path))
    import src.modules.profitability as prof
    monkeypatch.setattr(prof, "POLICIES_FILE", str(tmp_path / "policies" / "ledger.json"))
    yield tmp_path


def test_record_policy_calculates_financials():
    from src.modules.profitability import record_policy
    p = record_policy(1, "Tom Jones", "POL-001", "Foresters", "2026-04-01", 5000, 0.70)
    assert p["gross_commission"] == 3500.0
    assert p["agency_override"] == 250.0       # 5% of 5000
    assert p["chargeback_reserve"] == 350.0    # 10% of 3500
    assert p["net_to_agent"] == 3150.0         # 3500 - 350
    assert p["status"] == "active"


def test_mark_lapsed_updates_status():
    from src.modules.profitability import record_policy, mark_lapsed
    record_policy(1, "Tom Jones", "POL-002", "Foresters", "2026-04-01", 4000, 0.70)
    p = mark_lapsed("POL-002", 1200.0)
    assert p["status"] == "lapsed"
    assert p["chargeback_actual"] == 1200.0
    # gross=2800, reserve=10% of 2800=280, net_initial=2520, after chargeback=1320
    assert p["net_to_agent"] == pytest.approx(2520.0 - 1200.0)


def test_mark_lapsed_unknown_policy_raises():
    from src.modules.profitability import mark_lapsed
    with pytest.raises(ValueError, match="not found"):
        mark_lapsed("UNKNOWN-999", 500.0)
