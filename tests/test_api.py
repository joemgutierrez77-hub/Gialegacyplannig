"""Test the mobile API layer — only the AI-free (data) endpoints, no Claude calls."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    """Redirect every module's data file to a temp folder so tests never touch real data."""
    import config.settings as cfg
    monkeypatch.setattr(cfg, "DATA_DIR", str(tmp_path))

    import src.modules.recruiting as rec
    import src.modules.production as prod
    import src.modules.profitability as prof
    monkeypatch.setattr(rec, "RECRUITS_FILE", str(tmp_path / "recruits" / "pipeline.json"))
    monkeypatch.setattr(prod, "AGENTS_FILE", str(tmp_path / "agents" / "roster.json"))
    monkeypatch.setattr(prof, "POLICIES_FILE", str(tmp_path / "policies" / "ledger.json"))
    monkeypatch.setattr(prof, "USE_AIRTABLE", False)
    yield tmp_path


@pytest.fixture
def client():
    from api import app
    return TestClient(app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_recruit_lifecycle(client):
    created = client.post("/recruiting/recruits", json={
        "name": "Jane Smith", "phone": "555-0001", "source": "referral",
    })
    assert created.status_code == 201
    rid = created.json()["id"]

    advanced = client.post(f"/recruiting/recruits/{rid}/advance", json={"stage": "watched_info"})
    assert advanced.status_code == 200
    assert advanced.json()["stage"] == "watched_info"

    pipeline = client.get("/recruiting/pipeline").json()
    assert pipeline["watched_info"] == 1

    assert len(client.get("/recruiting/recruits").json()) == 1


def test_advance_invalid_stage_returns_400(client):
    client.post("/recruiting/recruits", json={"name": "Bob", "phone": "x", "source": "cold"})
    r = client.post("/recruiting/recruits/1/advance", json={"stage": "not_a_stage"})
    assert r.status_code == 400


def test_agent_and_stats(client):
    a = client.post("/production/agents", json={
        "name": "Tom Jones", "start_date": "2026-01-15", "license_state": "TX",
    })
    assert a.status_code == 201
    aid = a.json()["id"]

    s = client.post(f"/production/agents/{aid}/stats", json={
        "month": "2026-06", "contacts": 40, "appointments": 12,
        "apps_submitted": 8, "apps_issued": 6, "apv": 10000,
    })
    assert s.status_code == 201
    assert client.get("/production/agents").json()[0]["monthly_stats"][0]["apps_issued"] == 6


def test_stats_unknown_agent_returns_404(client):
    r = client.post("/production/agents/999/stats", json={
        "month": "2026-06", "contacts": 1, "appointments": 1,
        "apps_submitted": 1, "apps_issued": 1, "apv": 1,
    })
    assert r.status_code == 404


def test_policy_lifecycle(client):
    p = client.post("/profitability/policies", json={
        "agent_id": "1", "agent_name": "Tom Jones", "policy_number": "P-100",
        "carrier": "Mutual", "issue_date": "2026-06-01",
        "annual_premium": 1200, "agent_commission_pct": 0.70,
    })
    assert p.status_code == 201
    assert p.json()["gross_commission"] == pytest.approx(840.0)

    lapse = client.post("/profitability/policies/P-100/lapse", json={"chargeback_amount": 500})
    assert lapse.status_code == 200
    assert lapse.json()["status"] == "lapsed"


def test_dashboard(client):
    client.post("/production/agents", json={
        "name": "Tom", "start_date": "2026-01-15", "license_state": "TX",
    })
    body = client.get("/dashboard").json()
    assert body["production"]["roster_size"] == 1
    assert "pipeline" in body["recruiting"]
    assert "net_override" in body["profitability"]
