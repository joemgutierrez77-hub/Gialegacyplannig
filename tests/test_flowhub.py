"""Test FlowHub export bridge (no API calls)."""
import json
from datetime import date, timedelta

import pytest


@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    """Redirect DATA_DIR and the export path to a temp folder."""
    import src.modules.flowhub as fh
    monkeypatch.setattr(fh, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(fh, "EXPORT_FILE", str(tmp_path / "business-data.js"))
    yield tmp_path


def _seed(tmp_path, recruits=None, agents=None, ledger=None):
    for sub, name, data in [
        ("recruits", "pipeline.json", recruits or []),
        ("agents", "roster.json", agents or []),
        ("policies", "ledger.json", ledger or []),
    ]:
        d = tmp_path / sub
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_text(json.dumps(data))


def test_snapshot_empty_data(isolated_data):
    from src.modules.flowhub import build_snapshot
    snap = build_snapshot()
    assert snap["recruiting"]["total"] == 0
    assert snap["production"]["agents"] == []
    assert snap["profitability"]["activePolicies"] == 0
    # Only the monthly recruiting quota suggestion fires with no data
    keys = [s["key"] for s in snap["suggestions"]]
    assert any(k.startswith("recruit-quota-") for k in keys)


def test_new_lead_generates_high_priority_task(isolated_data):
    from src.modules.flowhub import build_snapshot
    today = date.today().isoformat()
    _seed(isolated_data, recruits=[{
        "id": 1, "name": "Jane", "phone": "555-1", "source": "referral",
        "stage": "new_lead", "added_date": today, "history": [],
    }])
    snap = build_snapshot()
    sug = next(s for s in snap["suggestions"] if s["key"] == "recruit-new-1")
    assert sug["priority"] == "high"
    assert "Jane" in sug["title"]


def test_stalled_recruit_fires_after_threshold(isolated_data):
    from src.modules.flowhub import build_snapshot
    old = (date.today() - timedelta(days=10)).isoformat()
    _seed(isolated_data, recruits=[{
        "id": 2, "name": "Mike", "phone": "", "source": "",
        "stage": "committed", "added_date": old,
        "history": [{"from": "watched_info", "to": "committed", "date": old}],
    }])
    snap = build_snapshot()
    keys = [s["key"] for s in snap["suggestions"]]
    assert "recruit-stalled-2-committed" in keys


def test_below_target_agent_gets_coaching_task(isolated_data):
    from src.modules.flowhub import build_snapshot
    last_month = (date.today().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    _seed(isolated_data, agents=[{
        "id": 1, "name": "Tom", "start_date": "2026-01-01",
        "license_state": "TX", "status": "active",
        "monthly_stats": [{
            "month": last_month, "contacts": 10, "appointments": 4,
            "apps_submitted": 3, "apps_issued": 2, "apv": 4000,
            "chargebacks": 0, "persistency": 0.90,
        }],
    }])
    snap = build_snapshot()
    sug = next(s for s in snap["suggestions"] if s["key"].startswith("coach-1-"))
    assert "Tom" in sug["title"]
    assert "APV" in sug["detail"]


def test_chargeback_exposure_and_review_task(isolated_data):
    from src.modules.flowhub import build_snapshot
    recent = (date.today() - timedelta(days=30)).isoformat()
    _seed(isolated_data, ledger=[{
        "id": 1, "agent_id": 1, "agent_name": "Tom", "policy_number": "P-1",
        "carrier": "AIG", "issue_date": recent, "annual_premium": 5000,
        "agent_commission_pct": 0.7, "gross_commission": 3500,
        "agency_override": 250, "chargeback_reserve": 350,
        "net_to_agent": 3150, "status": "active",
    }])
    snap = build_snapshot()
    assert snap["profitability"]["chargebackExposure"] == 3500
    keys = [s["key"] for s in snap["suggestions"]]
    assert any(k.startswith("chargeback-review-") for k in keys)


def test_export_writes_valid_js(isolated_data):
    from src.modules.flowhub import export_flowhub
    path = export_flowhub()
    content = open(path).read()
    assert content.startswith("// Auto-generated")
    payload = content.split("window.BUSINESS_DATA = ", 1)[1].rstrip().rstrip(";")
    snap = json.loads(payload)
    assert snap["agency"] == "GIA Legacy Planning"
    assert "suggestions" in snap


def test_pending_apps_in_snapshot_and_stall_task(isolated_data):
    from src.modules.flowhub import build_snapshot
    old = (date.today() - timedelta(days=20)).isoformat()
    recent = (date.today() - timedelta(days=2)).isoformat()
    d = isolated_data / "policies"
    d.mkdir(parents=True, exist_ok=True)
    (d / "pending.json").write_text(json.dumps([
        {"id": 1, "applicant_name": "Maria Lopez", "agent_name": "Tom", "carrier": "AIG",
         "submit_date": old, "annual_premium": 3600, "status": "pending"},
        {"id": 2, "applicant_name": "Ken Wu", "agent_name": "Lisa", "carrier": "Americo",
         "submit_date": recent, "annual_premium": 2400, "status": "pending"},
        {"id": 3, "applicant_name": "Done Deal", "agent_name": "Tom", "carrier": "AIG",
         "submit_date": old, "annual_premium": 999, "status": "approved"},
    ]))
    snap = build_snapshot()
    assert snap["pending"]["count"] == 2          # approved one excluded
    assert snap["pending"]["apv"] == 6000.0
    keys = [s["key"] for s in snap["suggestions"]]
    assert f"pending-stall-1-{old}" in keys       # 20 days -> stalled
    assert f"pending-stall-2-{recent}" not in keys  # 2 days -> fine


def test_suggestion_keys_are_stable(isolated_data):
    """Keys must be deterministic so FlowHub never duplicates tasks."""
    from src.modules.flowhub import build_snapshot
    today = date.today().isoformat()
    _seed(isolated_data, recruits=[{
        "id": 7, "name": "Ana", "phone": "", "source": "",
        "stage": "new_lead", "added_date": today, "history": [],
    }])
    k1 = [s["key"] for s in build_snapshot()["suggestions"]]
    k2 = [s["key"] for s in build_snapshot()["suggestions"]]
    assert k1 == k2
