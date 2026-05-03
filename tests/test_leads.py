from src.modules.leads import mortgage_protection_lead_hub


def test_hub_contains_goal_and_sections():
    hub = mortgage_protection_lead_hub(45)
    assert "Generate 45 qualified mortgage protection leads" in hub
    assert "LEAD SOURCES" in hub
    assert "FOLLOW-UP CADENCE" in hub


def test_hub_minimum_target_is_one():
    hub = mortgage_protection_lead_hub(0)
    assert "Generate 1 qualified mortgage protection leads" in hub
