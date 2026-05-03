"""Test recruiting pipeline data layer (no API calls)."""
import pytest


@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    """Redirect DATA_DIR to a temp folder so tests never touch real data."""
    import config.settings as cfg
    monkeypatch.setattr(cfg, "DATA_DIR", str(tmp_path))
    # Also patch the path used inside the recruiting module
    import src.modules.recruiting as rec
    monkeypatch.setattr(rec, "RECRUITS_FILE", str(tmp_path / "recruits" / "pipeline.json"))
    yield tmp_path


def test_add_recruit():
    from src.modules.recruiting import add_recruit, _load_pipeline
    r = add_recruit("Jane Smith", "555-0001", "referral", "Strong network", "jane@example.com")
    assert r["name"] == "Jane Smith"
    assert r["stage"] == "new_lead"
    assert r["email"] == "jane@example.com"
    assert r["id"] == 1
    pipeline = _load_pipeline()
    assert len(pipeline) == 1


def test_advance_stage():
    from src.modules.recruiting import add_recruit, advance_stage
    r = add_recruit("Bob Jones", "555-0002", "cold call")
    updated = advance_stage(r["id"], "watched_info", "Watched intro")
    assert updated["stage"] == "watched_info"
    assert len(updated["history"]) == 1
    assert updated["history"][0]["from"] == "new_lead"


def test_pipeline_summary_counts():
    from src.modules.recruiting import add_recruit, advance_stage, pipeline_summary
    add_recruit("Alice", "555-1", "event")
    r2 = add_recruit("Bob", "555-2", "referral")
    advance_stage(r2["id"], "watched_info")
    summary = pipeline_summary()
    assert summary["new_lead"] == 1
    assert summary["watched_info"] == 1


def test_advance_to_invalid_stage_raises():
    from src.modules.recruiting import add_recruit, advance_stage
    r = add_recruit("Test", "555-9", "web")
    with pytest.raises(ValueError, match="Invalid stage"):
        advance_stage(r["id"], "promoted")


def test_advance_unknown_id_raises():
    from src.modules.recruiting import advance_stage
    with pytest.raises(ValueError, match="not found"):
        advance_stage(999, "watched_info")
