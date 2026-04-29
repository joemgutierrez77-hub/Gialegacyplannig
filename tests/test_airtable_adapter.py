"""
Test the Airtable adapter logic using mocked HTTP responses.
No live Airtable connection is made.
"""
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers to build fake Airtable API responses
# ---------------------------------------------------------------------------

def _make_response(records: list, offset: str = None) -> MagicMock:
    body = {"records": records}
    if offset:
        body["offset"] = offset
    mock = MagicMock()
    mock.json.return_value = body
    mock.raise_for_status = MagicMock()
    return mock


def _issued_record(policy_number: str, agent_name: str, annual_premium: float,
                   status: str = "Active") -> dict:
    return {
        "id": f"rec_{policy_number}",
        "fields": {
            "Agent Name":        agent_name,
            "Agent ID":          "A1",
            "Policy Number":     policy_number,
            "Carrier":           "Foresters",
            "Issue Date":        "2026-04-01",
            "Annual Premium":    annual_premium,
            "Commission %":      0.70,
            "Gross Commission":  round(annual_premium * 0.70, 2),
            "Agency Override":   round(annual_premium * 0.05, 2),
            "Chargeback Reserve":round(annual_premium * 0.70 * 0.10, 2),
            "Net to Agent":      round(annual_premium * 0.70 * 0.90, 2),
            "Policy Status":     status,
        },
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@patch("requests.get")
def test_get_issued_policies_normalises_fields(mock_get):
    mock_get.return_value = _make_response([
        _issued_record("POL-001", "Tom Jones", 5000),
    ])
    with patch("config.settings.USE_AIRTABLE", True), \
         patch("config.settings.AIRTABLE_API_KEY", "test-key"), \
         patch("config.settings.AIRTABLE_BASE_ID", "appTEST"):
        from src.airtable_adapter import get_issued_policies
        policies = get_issued_policies()

    assert len(policies) == 1
    p = policies[0]
    assert p["policy_number"]   == "POL-001"
    assert p["agent_name"]      == "Tom Jones"
    assert p["annual_premium"]  == 5000.0
    assert p["gross_commission"]== 3500.0
    assert p["status"]          == "active"   # lowercased


@patch("requests.get")
@patch("requests.patch")
def test_mark_policy_lapsed_updates_net(mock_patch, mock_get):
    record = _issued_record("POL-002", "Sara Lee", 4000)
    mock_get.return_value  = _make_response([record])
    mock_patch.return_value = _make_response([])

    with patch("config.settings.USE_AIRTABLE", True), \
         patch("config.settings.AIRTABLE_API_KEY", "test-key"), \
         patch("config.settings.AIRTABLE_BASE_ID", "appTEST"):
        from src.airtable_adapter import mark_policy_lapsed
        mark_policy_lapsed("POL-002", 1200.0)

    # Verify the PATCH call was made with correct fields
    # requests receives a dict via json= kwarg — no need to decode
    fields = mock_patch.call_args[1]["json"]["fields"]
    assert fields["Policy Status"]    == "Lapsed"
    assert fields["Chargeback Amount"]== 1200.0


@patch("requests.get")
def test_get_issued_policies_unknown_policy_raises(mock_get):
    mock_get.return_value = _make_response([])  # empty table

    with patch("config.settings.USE_AIRTABLE", True), \
         patch("config.settings.AIRTABLE_API_KEY", "test-key"), \
         patch("config.settings.AIRTABLE_BASE_ID", "appTEST"):
        from src.airtable_adapter import mark_policy_lapsed
        with pytest.raises(ValueError, match="not found"):
            mark_policy_lapsed("UNKNOWN-999", 500.0)


@patch("requests.get")
def test_get_issued_policies_pagination(mock_get):
    """Adapter must follow the offset token to fetch all pages."""
    page1 = _make_response([_issued_record("POL-A", "Agent A", 3000)], offset="page2token")
    page2 = _make_response([_issued_record("POL-B", "Agent B", 4000)])
    mock_get.side_effect = [page1, page2]

    with patch("config.settings.USE_AIRTABLE", True), \
         patch("config.settings.AIRTABLE_API_KEY", "test-key"), \
         patch("config.settings.AIRTABLE_BASE_ID", "appTEST"):
        from src.airtable_adapter import get_issued_policies
        policies = get_issued_policies()

    assert len(policies) == 2
    assert mock_get.call_count == 2


@patch("requests.post")
def test_write_issued_policy_calculates_financials(mock_post):
    mock_post.return_value = _make_response([])

    with patch("config.settings.USE_AIRTABLE", True), \
         patch("config.settings.AIRTABLE_API_KEY", "test-key"), \
         patch("config.settings.AIRTABLE_BASE_ID", "appTEST"):
        from src.airtable_adapter import write_issued_policy
        write_issued_policy("A1", "Tom Jones", "POL-003", "Foresters",
                            "2026-04-15", 6000, 0.70)

    fields = mock_post.call_args[1]["json"]["fields"]
    assert fields["Gross Commission"]   == 4200.0   # 6000 * 0.70
    assert fields["Agency Override"]    == 300.0    # 6000 * 0.05
    assert fields["Chargeback Reserve"] == 420.0    # 4200 * 0.10
    assert fields["Net to Agent"]       == 3780.0   # 4200 - 420
