from src.commander.history import (
    archive_enriched,
    load_latest_history,
    detect_raises,
    should_suppress_alert,
    purge_old_alerts,
)
from pathlib import Path
import json, tempfile, os

def test_archive_enriched_writes_to_correct_path(tmp_path, monkeypatch):
    companies = [{"company_name": "TestCo", "domain": "https://test.co"}]
    archive_path = tmp_path / "data/history/2026-03/slug_test_companies.json"
    monkeypatch.setattr("src.commander.history.DATA_DIR", tmp_path / "data")
    archive_enriched(companies, "slug_test", "2026-03")
    assert archive_path.exists()
    data = json.loads(archive_path.read_text())
    assert data == companies

def test_detect_raises_finds_updated_last_raise_date():
    previous = [{"domain": "https://test.co", "last_raise_date": "2023-09-01"}]
    current = [{"domain": "https://test.co", "last_raise_date": "2024-09-01"}]
    raises = detect_raises(current, previous)
    assert len(raises) == 1
    assert raises[0]["domain"] == "https://test.co"

def test_detect_raises_excludes_new_companies():
    previous = []
    current = [{"domain": "https://new.co", "last_raise_date": "2024-09-01"}]
    raises = detect_raises(current, previous)
    assert len(raises) == 0

def test_should_suppress_alert_true_within_30_days(tmp_path, monkeypatch):
    monkeypatch.setattr("src.commander.history.ALERTS_FILE", tmp_path / "alerts_fired.jsonl")
    (tmp_path / "alerts_fired.jsonl").write_text(
        '{"domain": "https://test.co", "date": "2026-03-20", "company": "TestCo"}\n'
    )
    assert should_suppress_alert("https://test.co") == True

def test_should_suppress_alert_false_after_30_days(tmp_path, monkeypatch):
    monkeypatch.setattr("src.commander.history.ALERTS_FILE", tmp_path / "alerts_fired.jsonl")
    (tmp_path / "alerts_fired.jsonl").write_text(
        '{"domain": "https://test.co", "date": "2026-02-01", "company": "TestCo"}\n'
    )
    assert should_suppress_alert("https://test.co") == False

def test_purge_old_alerts_removes_entries_over_30_days(tmp_path, monkeypatch):
    monkeypatch.setattr("src.commander.history.ALERTS_FILE", tmp_path / "alerts_fired.jsonl")
    (tmp_path / "alerts_fired.jsonl").write_text(
        '{"domain": "https://old.co", "date": "2026-01-01", "company": "OldCo"}\n'
        '{"domain": "https://recent.co", "date": "2026-03-20", "company": "RecentCo"}\n'
    )
    purge_old_alerts()
    content = (tmp_path / "alerts_fired.jsonl").read_text()
    assert "old.co" not in content
    assert "recent.co" in content