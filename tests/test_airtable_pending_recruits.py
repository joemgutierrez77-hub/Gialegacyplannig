"""
Tests for Airtable adapter — pending applications and recruits functions.
No live Airtable connection; all HTTP calls are mocked.
"""
import pytest
from contextlib import contextmanager
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(records: list, offset: str = None) -> MagicMock:
    body = {"records": records}
    if offset:
        body["offset"] = offset
    mock = MagicMock()
    mock.json.return_value = body
    mock.raise_for_status = MagicMock()
    return mock


@contextmanager
def _settings_patches():
    with patch("config.settings.AIRTABLE_API_KEY", "test-key"), \
         patch("config.settings.AIRTABLE_BASE_ID", "appTEST"):
        yield


def _pending_record(agent_name: str, applicant_name: str, carrier: str,
                    annual_premium: float, status: str = "Pending") -> dict:
    return {
        "id": f"recPND_{applicant_name[:3].upper()}",
        "fields": {
            "Agent Name":     agent_name,
            "Agent ID":       "A1",
            "Applicant Name": applicant_name,
            "Carrier":        carrier,
            "Annual Premium": annual_premium,
            "Submit Date":    "2026-05-01",
            "Status":         status,
            "Policy Number":  "",
        },
    }


def _recruit_record(name: str, phone: str, source: str, stage: str = "lead") -> dict:
    return {
        "id": f"recREC_{name[:3].upper()}",
        "fields": {
            "Name":       name,
            "Phone":      phone,
            "Source":     source,
            "Stage":      stage,
            "Notes":      "",
            "Added Date": "2026-05-01",
        },
    }


# ---------------------------------------------------------------------------
# Pending applications
# ---------------------------------------------------------------------------

@patch("requests.get")
def test_get_pending_apps_normalises_fields(mock_get):
    mock_get.return_value = _make_response([
        _pending_record("Sara Lee", "John Doe", "Mutual of Omaha", 3600.0)
    ])
    with _settings_patches():
        from src.airtable_adapter import get_pending_apps
        apps = get_pending_apps()

    assert len(apps) == 1
    a = apps[0]
    assert a["agent_name"]     == "Sara Lee"
    assert a["applicant_name"] == "John Doe"
    assert a["carrier"]        == "Mutual of Omaha"
    assert a["annual_premium"] == 3600.0
    assert a["status"]         == "Pending"


@patch("requests.get")
def test_get_pending_apps_empty_table(mock_get):
    mock_get.return_value = _make_response([])
    with _settings_patches():
        from src.airtable_adapter import get_pending_apps
        apps = get_pending_apps()
    assert apps == []


@patch("requests.post")
def test_write_pending_app_sends_correct_fields(mock_post):
    mock_post.return_value = _make_response([])
    with _settings_patches():
        from src.airtable_adapter import write_pending_app
        write_pending_app("Tom Rivera", "Jane Smith", "Foresters", 4800.0, "2026-05-10")

    fields = mock_post.call_args[1]["json"]["fields"]
    assert fields["Agent Name"]     == "Tom Rivera"
    assert fields["Applicant Name"] == "Jane Smith"
    assert fields["Carrier"]        == "Foresters"
    assert fields["Annual Premium"] == 4800.0
    assert fields["Submit Date"]    == "2026-05-10"
    assert fields["Status"]         == "Pending"


@patch("requests.post")
def test_write_pending_app_uses_today_when_no_date(mock_post):
    mock_post.return_value = _make_response([])
    with _settings_patches():
        from src.airtable_adapter import write_pending_app
        write_pending_app("Agent A", "Client B", "Carrier C", 2000.0)

    fields = mock_post.call_args[1]["json"]["fields"]
    import re
    assert re.match(r"\d{4}-\d{2}-\d{2}", fields["Submit Date"])


@patch("requests.post")
@patch("requests.get")
@patch("requests.patch")
def test_promote_to_issued_creates_issued_record(mock_patch_req, mock_get, mock_post):
    pending_fields = {
        "Agent Name":     "Sara Kim",
        "Agent ID":       "A3",
        "Carrier":        "National Life",
        "Annual Premium": 4000.0,
    }
    mock_patch_req.return_value = _make_response([])
    mock_get.return_value       = _make_response([{"id": "recPND1", "fields": pending_fields}])
    mock_post.return_value      = _make_response([])

    with _settings_patches():
        from src.airtable_adapter import promote_to_issued
        promote_to_issued("recPND1", "POL-NEW1", "2026-05-10", 0.70)

    assert mock_patch_req.call_count == 1
    assert mock_post.call_count      == 1

    issued_fields = mock_post.call_args[1]["json"]["fields"]
    assert issued_fields["Policy Number"] == "POL-NEW1"
    assert issued_fields["Carrier"]       == "National Life"
    assert issued_fields["Issue Date"]    == "2026-05-10"


@patch("requests.get")
def test_promote_to_issued_raises_when_pending_not_found(mock_get):
    mock_get.return_value = _make_response([])  # pending re-fetch returns nothing
    with _settings_patches():
        # patch the update so it doesn't fail before the fetch
        with patch("src.airtable_adapter._update_record"):
            from src.airtable_adapter import promote_to_issued
            with pytest.raises(ValueError, match="not found"):
                promote_to_issued("recMISSING", "POL-X", "2026-05-01", 0.70)


# ---------------------------------------------------------------------------
# Recruits
# ---------------------------------------------------------------------------

@patch("requests.get")
def test_get_recruits_returns_all_when_no_stage_filter(mock_get):
    mock_get.return_value = _make_response([
        _recruit_record("Alice Wong",  "555-1", "referral", "contracted"),
        _recruit_record("Bob Nguyen",  "555-2", "event",    "new_lead"),
    ])
    with _settings_patches():
        from src.airtable_adapter import get_recruits
        recruits = get_recruits()

    assert len(recruits) == 2
    names = {r["name"] for r in recruits}
    assert "Alice Wong" in names
    assert "Bob Nguyen" in names


@patch("requests.get")
def test_get_recruits_normalises_fields(mock_get):
    mock_get.return_value = _make_response([
        _recruit_record("Carol Diaz", "555-3", "web", "committed")
    ])
    with _settings_patches():
        from src.airtable_adapter import get_recruits
        recruits = get_recruits()

    r = recruits[0]
    assert r["name"]   == "Carol Diaz"
    assert r["phone"]  == "555-3"
    assert r["source"] == "web"
    assert r["stage"]  == "committed"


@patch("requests.get")
def test_get_recruits_with_stage_filter_passes_formula(mock_get):
    mock_get.return_value = _make_response([
        _recruit_record("Dave Park", "555-4", "referral", "contracted")
    ])
    with _settings_patches():
        from src.airtable_adapter import get_recruits
        get_recruits(stage="contracted")

    params = mock_get.call_args[1]["params"]
    formula = params.get("filterByFormula", "")
    assert "contracted" in formula
    assert "Stage" in formula


@patch("requests.post")
def test_write_recruit_sends_correct_fields(mock_post):
    mock_post.return_value = _make_response([])
    with _settings_patches():
        from src.airtable_adapter import write_recruit
        write_recruit("Eve Torres", "555-5555", "church event", notes="Very motivated")

    fields = mock_post.call_args[1]["json"]["fields"]
    assert fields["Name"]   == "Eve Torres"
    assert fields["Phone"]  == "555-5555"
    assert fields["Source"] == "church event"
    assert fields["Stage"]  == "lead"
    assert fields["Notes"]  == "Very motivated"


@patch("requests.patch")
def test_advance_recruit_stage_updates_stage(mock_patch_req):
    mock_patch_req.return_value = _make_response([])
    with _settings_patches():
        from src.airtable_adapter import advance_recruit_stage
        advance_recruit_stage("recREC123", "contracted")

    fields = mock_patch_req.call_args[1]["json"]["fields"]
    assert fields["Stage"] == "contracted"
    assert "Notes" not in fields


@patch("requests.patch")
def test_advance_recruit_stage_includes_notes_when_provided(mock_patch_req):
    mock_patch_req.return_value = _make_response([])
    with _settings_patches():
        from src.airtable_adapter import advance_recruit_stage
        advance_recruit_stage("recREC123", "active", notes="Passed all exams")

    fields = mock_patch_req.call_args[1]["json"]["fields"]
    assert fields["Stage"] == "active"
    assert fields["Notes"] == "Passed all exams"
