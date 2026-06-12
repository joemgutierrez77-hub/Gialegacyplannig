"""Test external connectors — pure logic only, no network calls."""
import json

import pytest


@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    import src.modules.connectors as con
    monkeypatch.setattr(con, "PIPELINE_FILE", str(tmp_path / "recruits" / "pipeline.json"))
    monkeypatch.setattr(con, "LEDGER_FILE", str(tmp_path / "policies" / "ledger.json"))
    monkeypatch.setattr(con, "PENDING_FILE", str(tmp_path / "policies" / "pending.json"))
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
    assert res["added"] == 3  # blank policy number gets a stable synthetic id
    assert res["skipped"] == 0
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


def test_import_pending_csv(isolated_data):
    from src.modules.connectors import import_pending_csv
    csv_file = isolated_data / "pending.csv"
    csv_file.write_text(
        "Applicant Name,Agent,Carrier,Submit Date,Annual Premium,Status\n"
        "Maria Lopez,Tom Reyes,AIG,2026-06-01,\"$3,600\",Pending\n"
        "Ken Wu,Lisa Chan,Americo,2026-06-05,2400,Approved\n"
        "Dana Cruz,Tom Reyes,AIG,2026-06-08,1800,Declined\n"
    )
    res = import_pending_csv(str(csv_file))
    assert res["added"] == 3
    pending = json.loads((isolated_data / "policies" / "pending.json").read_text())
    maria = next(p for p in pending if p["applicant_name"] == "Maria Lopez")
    assert maria["annual_premium"] == 3600.0
    assert maria["status"] == "pending"
    assert next(p for p in pending if p["applicant_name"] == "Ken Wu")["status"] == "approved"
    assert next(p for p in pending if p["applicant_name"] == "Dana Cruz")["status"] == "declined"
    # re-import never duplicates
    assert import_pending_csv(str(csv_file))["added"] == 0


def test_status_classifier():
    from src.modules.connectors import _classify_status
    assert _classify_status("Pending") == "pending"
    assert _classify_status("Submitted - Underwriting") == "pending"
    assert _classify_status("Approved") == "pending"   # approved ≠ placed yet
    assert _classify_status("Declined") == "pending"   # pending importer marks declined
    assert _classify_status("Issued") == "issued"
    assert _classify_status("Active / In Force") == "issued"
    assert _classify_status("Lapsed") == "chargeback"
    assert _classify_status("Chargeback") == "chargeback"
    assert _classify_status("Cancelled - NSF") == "chargeback"


def test_import_combined_csv_routes_all_buckets(isolated_data):
    from src.modules.connectors import import_combined_csv
    csv_file = isolated_data / "combined.csv"
    csv_file.write_text(
        "Applicant Name,Agent,Carrier,Policy Number,Submit Date,Issue Date,Annual Premium,Status\n"
        "Maria Lopez,Tom Reyes,AIG,,2026-06-01,,3600,Pending\n"
        "Ken Wu,Lisa Chan,Americo,,2026-06-05,,2400,Submitted\n"
        "Ana Diaz,Tom Reyes,AIG,P-700,2026-05-01,2026-05-20,5000,Issued\n"
        "Raj Patel,Lisa Chan,AIG,P-701,2026-03-01,2026-03-15,4000,Lapsed\n"
        "Lee Park,Tom Reyes,Americo,,2026-06-02,,1500,Declined\n"
    )
    res = import_combined_csv(str(csv_file), commission_pct=0.70)
    assert res["pending"]["added"] == 3        # Maria, Ken, Lee (declined)
    assert res["issued"]["added"] == 1         # Ana
    assert res["chargebacks"]["added"] == 1    # Raj (not previously in ledger)

    pending = json.loads((isolated_data / "policies" / "pending.json").read_text())
    assert next(p for p in pending if p["applicant_name"] == "Lee Park")["status"] == "declined"
    ledger = json.loads((isolated_data / "policies" / "ledger.json").read_text())
    raj = next(p for p in ledger if p["policy_number"] == "P-701")
    assert raj["status"] == "lapsed"
    assert raj["chargeback_actual"] == 2800.0  # no amount column -> gross fallback (4000*0.7)

    # re-import is idempotent
    res2 = import_combined_csv(str(csv_file))
    assert res2["pending"]["added"] == 0 and res2["issued"]["added"] == 0
    assert res2["chargebacks"]["added"] == 0 and res2["chargebacks"]["updated"] == 0


def test_combined_resolves_pending_when_app_issues(isolated_data):
    from src.modules.connectors import import_combined_csv
    week1 = isolated_data / "week1.csv"
    week1.write_text(
        "Applicant Name,Agent,Policy Number,Submit Date,Annual Premium,Status\n"
        "Maria Lopez,Tom,,2026-06-01,3600,Pending\n"
    )
    import_combined_csv(str(week1))
    # next week's report: same applicant, now issued with a policy number
    week2 = isolated_data / "week2.csv"
    week2.write_text(
        "Applicant Name,Agent,Policy Number,Issue Date,Annual Premium,Status\n"
        "Maria Lopez,Tom,P-800,2026-06-10,3600,Issued\n"
    )
    res = import_combined_csv(str(week2))
    assert res["issued"]["added"] == 1
    assert res["pending"]["resolved"] == 1
    pending = json.loads((isolated_data / "policies" / "pending.json").read_text())
    assert pending[0]["status"] == "approved"  # no longer counted or task-generating


def test_real_tracker_format(isolated_data):
    """Quility-style tracker: Decision column, Insured names, no policy numbers,
    M/D/YYYY dates, negative-premium chargeback rows, multi-line headers."""
    from src.modules.connectors import import_combined_csv
    f = isolated_data / "tracker.csv"
    f.write_text(
        'Agent,Agency Owner/Keyleader,Insured ,Carrier,Policy Type,Submitted,"Monthly\nPremium",'
        "APV,Decision ,Notes ,Month Counting,Created\n"
        '"Courtney Wallace\n",Base,,American Equity,,,$167.65,$2011.78,Issue Paid ,,May,6/10/2026 9:23pm\n'
        '"Darenique Slaughter\n",Base,CB\'s - 6,Mutual of Omaha,,,-$480.42,-$5765.00,Issue Paid ,,May,6/10/2026 9:31pm\n'
        "LiQuiche L Young,Base,Lakeya Doss,Mutual of Omaha,IUL Express,5/19/2026,$45.41,$544.92,Issue Paid ,,May,5/20/2026 10:01pm\n"
        "Joe Manuel Gutierrez,Base,jose lerma,Mutual of Omaha,IUL Express,5/25/2026,$46.81,$561.72,Pending ,,,5/27/2026 12:44am\n"
        "Sarah Gonzales-Gutierrez,Base,delano harris,Fidelity and Guaranty,F&G Pathsetter,5/25/2026,$233.33,$2800.00,Not at Carrier ,,,5/27/2026 12:44am\n"
    )
    res = import_combined_csv(str(f), commission_pct=0.70)
    assert res["issued"]["added"] == 2          # positive Issue Paid rows
    assert res["chargebacks"]["added"] == 1     # negative-premium row
    assert res["pending"]["added"] == 2         # Pending + Not at Carrier

    ledger = json.loads((isolated_data / "policies" / "ledger.json").read_text())
    courtney = next(p for p in ledger if p["agent_name"] == "Courtney Wallace")
    assert courtney["annual_premium"] == 2011.78
    assert courtney["issue_date"] == "2026-05-01"      # from Month Counting + Created year
    lakeya = next(p for p in ledger if p.get("applicant_name") == "Lakeya Doss")
    assert lakeya["issue_date"] == "2026-05-19"        # M/D/YYYY normalized
    cb = next(p for p in ledger if p["status"] == "lapsed")
    assert cb["agent_name"] == "Darenique Slaughter"   # newline in name cleaned
    assert cb["chargeback_actual"] == round(5765.00 * 0.70, 2)
    # idempotent re-import despite synthetic ids
    res2 = import_combined_csv(str(f))
    assert res2["issued"]["added"] == 0 and res2["chargebacks"]["added"] == 0
    assert res2["pending"]["added"] == 0


def test_pending_reimport_updates_changed_status(isolated_data):
    from src.modules.connectors import import_pending_csv
    f = isolated_data / "apps.csv"
    f.write_text("Applicant Name,Submit Date,Annual Premium,Status\n"
                 "Ken Wu,2026-06-05,2400,Pending\n")
    import_pending_csv(str(f))
    f.write_text("Applicant Name,Submit Date,Annual Premium,Status\n"
                 "Ken Wu,2026-06-05,2400,Declined\n")
    res = import_pending_csv(str(f))
    assert res["updated"] == 1 and res["added"] == 0
    pending = json.loads((isolated_data / "policies" / "pending.json").read_text())
    assert pending[0]["status"] == "declined"


def test_import_chargebacks_updates_existing_policy(isolated_data):
    from src.modules.connectors import import_policies_csv, import_chargebacks_csv
    issued = isolated_data / "issued.csv"
    issued.write_text("Policy Number,Agent,Annual Premium\nP-500,Tom Reyes,5000\n")
    import_policies_csv(str(issued), commission_pct=0.70)

    cb = isolated_data / "cb.csv"
    cb.write_text("Policy Number,Chargeback Amount\nP-500,\"$1,200\"\nP-999,800\n")
    res = import_chargebacks_csv(str(cb))
    assert res["updated"] == 1   # P-500 marked lapsed
    assert res["added"] == 1     # P-999 unknown -> added as lapsed entry
    ledger = json.loads((isolated_data / "policies" / "ledger.json").read_text())
    p500 = next(p for p in ledger if p["policy_number"] == "P-500")
    assert p500["status"] == "lapsed"
    assert p500["chargeback_actual"] == 1200.0
    # re-import is idempotent
    res2 = import_chargebacks_csv(str(cb))
    assert res2["updated"] == 0 and res2["added"] == 0 and res2["skipped"] == 2
