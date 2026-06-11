"""Test external connectors — pure logic only, no network calls."""
import json

import pytest


@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    import src.modules.connectors as con
    monkeypatch.setattr(con, "PIPELINE_FILE", str(tmp_path / "recruits" / "pipeline.json"))
    monkeypatch.setattr(con, "LEDGER_FILE", str(tmp_path / "policies" / "ledger.json"))
    monkeypatch.setattr(con, "ENV_FILE", str(tmp_path / ".env"))
    yield tmp_path


def _tt_candidate(cid, first, last, phone="", email="", created="2026-06-01"):
    return {"id": cid, "attributes": {
        "first-name": first, "last-name": last, "phone": phone,
        "email": email, "created-at": created + "T10:00:00Z"}}


def test_teamtailor_merge_adds_new_candidates():
    from src.modules.connectors import merge_candidates_into_pipeline
    pipeline = []
    added = merge_candidates_into_pipeline(
        [_tt_candidate("1", "Jane", "Smith", "555-1")], pipeline)
    assert added == 1
    assert pipeline[0]["name"] == "Jane Smith"
    assert pipeline[0]["stage"] == "new_lead"
    assert pipeline[0]["external_id"] == "tt-1"
    assert pipeline[0]["source"] == "Teamtailor"


def test_teamtailor_merge_never_duplicates_or_moves():
    from src.modules.connectors import merge_candidates_into_pipeline
    pipeline = [{"id": 1, "name": "Jane Smith", "phone": "555-1", "source": "Teamtailor",
                 "stage": "committed", "notes": "", "email": "", "added_date": "2026-05-01",
                 "history": [], "external_id": "tt-1"}]
    added = merge_candidates_into_pipeline(
        [_tt_candidate("1", "Jane", "Smith", "555-1")], pipeline)
    assert added == 0
    assert pipeline[0]["stage"] == "committed"  # stage untouched


def test_teamtailor_merge_matches_manual_entries_by_identity():
    from src.modules.connectors import merge_candidates_into_pipeline
    # Recruit added by hand (no external_id) must not be re-added from Teamtailor
    pipeline = [{"id": 1, "name": "Bob Jones", "phone": "555-2", "source": "referral",
                 "stage": "new_lead", "notes": "", "email": "", "added_date": "2026-06-01",
                 "history": []}]
    added = merge_candidates_into_pipeline(
        [_tt_candidate("9", "Bob", "Jones", "555-2")], pipeline)
    assert added == 0


def test_calendly_parse_converts_events():
    from src.modules.connectors import parse_calendly_events
    payload = {"collection": [{
        "uri": "https://api.calendly.com/scheduled_events/abc123",
        "name": "Recruiting interview",
        "start_time": "2026-06-15T17:00:00.000000Z",
        "end_time": "2026-06-15T17:30:00.000000Z",
    }]}
    events = parse_calendly_events(payload)
    assert len(events) == 1
    ev = events[0]
    assert ev["key"] == "cal-abc123"
    assert ev["title"] == "Recruiting interview"
    assert ev["duration"] == 30
    assert ev["date"] == "2026-06-15"  # may shift with local tz, but format holds
    assert len(ev["time"]) == 5


def test_calendly_parse_skips_malformed():
    from src.modules.connectors import parse_calendly_events
    payload = {"collection": [{"name": "Broken", "start_time": "not-a-date", "end_time": ""}]}
    assert parse_calendly_events(payload) == []


def test_csv_column_matching_is_flexible():
    from src.modules.connectors import _match_columns
    m = _match_columns(["Policy #", "Writing Agent", "ANNUALIZED PREMIUM", "Company", "Random"])
    assert m["policy_number"] == "Policy #"
    assert m["agent_name"] == "Writing Agent"
    assert m["annual_premium"] == "ANNUALIZED PREMIUM"
    assert m["carrier"] == "Company"


def test_import_policies_csv(isolated_data):
    from src.modules.connectors import import_policies_csv
    csv_file = isolated_data / "report.csv"
    csv_file.write_text(
        "Policy Number,Agent,Carrier,Issue Date,Annual Premium,Status\n"
        "P-100,Tom Reyes,AIG,2026-05-01,\"$4,800\",Active\n"
        "P-101,Lisa Chan,Americo,2026-05-15,3200,Lapsed\n"
        ",No Policy,X,2026-01-01,100,Active\n"
    )
    res = import_policies_csv(str(csv_file), commission_pct=0.70)
    assert res["added"] == 2
    assert res["skipped"] == 1  # blank policy number
    ledger = json.loads((isolated_data / "policies" / "ledger.json").read_text())
    p = next(x for x in ledger if x["policy_number"] == "P-100")
    assert p["annual_premium"] == 4800.0
    assert p["gross_commission"] == 3360.0
    assert p["status"] == "active"
    assert next(x for x in ledger if x["policy_number"] == "P-101")["status"] == "lapsed"
    # re-import must not duplicate
    res2 = import_policies_csv(str(csv_file))
    assert res2["added"] == 0


def test_import_policies_csv_unmappable_raises(isolated_data):
    from src.modules.connectors import import_policies_csv
    bad = isolated_data / "bad.csv"
    bad.write_text("Foo,Bar\n1,2\n")
    with pytest.raises(ValueError):
        import_policies_csv(str(bad))


def test_env_round_trip(isolated_data):
    from src.modules.connectors import load_env, save_env_key
    save_env_key("TEAMTAILOR_API_KEY", "tt-secret")
    save_env_key("CALENDLY_API_TOKEN", "cal-secret")
    save_env_key("TEAMTAILOR_API_KEY", "tt-updated")  # update preserves the other
    env = load_env()
    assert env["TEAMTAILOR_API_KEY"] == "tt-updated"
    assert env["CALENDLY_API_TOKEN"] == "cal-secret"
