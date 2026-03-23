import json
import os
import tempfile
from pathlib import Path

def test_load_state_missing_file():
    """Missing state file returns (empty set, empty set, empty dict)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        from src.harvester import state
        original = state.STATE_FILE
        state.STATE_FILE = Path(tmpdir) / "nonexistent.json"
        try:
            completed, failed, patterns = state.load_state()
            assert completed == set()
            assert failed == set()
            assert patterns == {}
        finally:
            state.STATE_FILE = original

def test_load_state_existing():
    """Existing state file returns (completed_vcs, failed_vcs, vc_patterns)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "harvest_state.json"
        json.dump({"completed_vcs": ["vc-a", "vc-b"], "failed_vcs": ["vc-c"], "last_updated": "2026-01-01T00:00:00Z"}, state_file.open("w"))
        from src.harvester import state
        original = state.STATE_FILE
        state.STATE_FILE = state_file
        try:
            completed, failed, patterns = state.load_state()
            assert completed == {"vc-a", "vc-b"}
            assert failed == {"vc-c"}
            assert patterns == {}
        finally:
            state.STATE_FILE = original

def test_load_state_corrupt_json():
    """Corrupt JSON treated as cold start."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "harvest_state.json"
        state_file.write_text("{not valid json")
        from src.harvester import state
        original = state.STATE_FILE
        state.STATE_FILE = state_file
        try:
            completed, failed, patterns = state.load_state()
            assert completed == set()
            assert failed == set()
            assert patterns == {}
        finally:
            state.STATE_FILE = original

def test_mark_completed_single():
    """Mark one slug as completed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "harvest_state.json"
        from src.harvester import state
        original = state.STATE_FILE
        state.STATE_FILE = state_file
        try:
            state.mark_completed("vc-x")
            data = json.load(state_file.open())
            assert data["completed_vcs"] == ["vc-x"]
            assert "last_updated" in data
        finally:
            state.STATE_FILE = original

def test_mark_completed_accumulates():
    """mark_completed adds to existing slugs, does not overwrite."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "harvest_state.json"
        json.dump({"completed_vcs": ["vc-a"], "last_updated": "2026-01-01T00:00:00Z"}, state_file.open("w"))
        from src.harvester import state
        original = state.STATE_FILE
        state.STATE_FILE = state_file
        try:
            state.mark_completed("vc-b")
            data = json.load(state_file.open())
            assert data["completed_vcs"] == ["vc-a", "vc-b"]
        finally:
            state.STATE_FILE = original

def test_mark_completed_idempotent():
    """Marking the same slug twice does not duplicate."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "harvest_state.json"
        json.dump({"completed_vcs": ["vc-a"], "last_updated": "2026-01-01T00:00:00Z"}, state_file.open("w"))
        from src.harvester import state
        original = state.STATE_FILE
        state.STATE_FILE = state_file
        try:
            state.mark_completed("vc-a")
            data = json.load(state_file.open())
            assert data["completed_vcs"] == ["vc-a"]  # still just one
            assert "failed_vcs" in data  # new field present
        finally:
            state.STATE_FILE = original

def test_append_and_dedupe_new_companies():
    """New companies appended to empty file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "raw_companies.json"
        from src.harvester import state
        companies = [
            {"company_name": "Acme", "domain": "https://acme.co"},
            {"company_name": "Beta", "domain": "https://beta.io"},
        ]
        state.append_and_dedupe(companies, str(output_path))
        result = json.load(output_path.open())
        assert len(result) == 2
        assert result[0]["company_name"] == "Acme"

def test_append_and_dedupe_merges_with_existing():
    """Existing companies kept, new ones appended, duplicates by domain dropped."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "raw_companies.json"
        existing = [{"company_name": "Acme", "domain": "https://acme.co"}]
        json.dump(existing, output_path.open("w"))
        from src.harvester import state
        new_companies = [
            {"company_name": "Acme", "domain": "https://acme.co"},  # duplicate — skip
            {"company_name": "Beta", "domain": "https://beta.io"},
        ]
        state.append_and_dedupe(new_companies, str(output_path))
        result = json.load(output_path.open())
        assert len(result) == 2
        domains = {c["domain"] for c in result}
        assert "https://acme.co" in domains
        assert "https://beta.io" in domains

def test_append_and_dedupe_preserves_existing():
    """Existing companies are preserved when new companies are appended."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "raw_companies.json"
        existing = [{"company_name": "Existing", "domain": "https://existing.com"}]
        json.dump(existing, output_path.open("w"))
        from src.harvester import state
        new_companies = [{"company_name": "New", "domain": "https://new.com"}]
        state.append_and_dedupe(new_companies, str(output_path))
        result = json.load(output_path.open())
        assert len(result) == 2
        assert any(c["company_name"] == "Existing" for c in result)

def test_mark_failed_adds_to_failed_list():
    """mark_failed adds slug to failed_vcs and removes from completed_vcs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "harvest_state.json"
        json.dump({"completed_vcs": ["vc-a"], "failed_vcs": [], "last_updated": "2026-01-01T00:00:00Z"}, state_file.open("w"))
        from src.harvester import state
        original = state.STATE_FILE
        state.STATE_FILE = state_file
        try:
            state.mark_failed("vc-a")
            data = json.load(state_file.open())
            assert "vc-a" in data["failed_vcs"]
            assert "vc-a" not in data["completed_vcs"]
        finally:
            state.STATE_FILE = original

def test_mark_failed_removes_from_completed_on_retry():
    """A VC that was completed but now fails is moved from completed to failed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "harvest_state.json"
        json.dump({"completed_vcs": ["vc-b"], "failed_vcs": [], "last_updated": "2026-01-01T00:00:00Z"}, state_file.open("w"))
        from src.harvester import state
        original = state.STATE_FILE
        state.STATE_FILE = state_file
        try:
            state.mark_failed("vc-b")
            data = json.load(state_file.open())
            assert "vc-b" in data["failed_vcs"]
            assert "vc-b" not in data["completed_vcs"]
        finally:
            state.STATE_FILE = original

def test_clear_vc_removes_from_both_lists():
    """clear_vc removes slug from both completed and failed lists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "harvest_state.json"
        json.dump({"completed_vcs": ["vc-a"], "failed_vcs": ["vc-b"], "last_updated": "2026-01-01T00:00:00Z"}, state_file.open("w"))
        from src.harvester import state
        original = state.STATE_FILE
        state.STATE_FILE = state_file
        try:
            state.clear_vc("vc-a")
            data = json.load(state_file.open())
            assert "vc-a" not in data["completed_vcs"]
            assert "vc-a" not in data["failed_vcs"]
            assert "vc-b" in data["failed_vcs"]  # other entry untouched
        finally:
            state.STATE_FILE = original

def test_mark_completed_removes_from_failed():
    """mark_completed removes slug from failed_vcs (successful retry)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "harvest_state.json"
        json.dump({"completed_vcs": [], "failed_vcs": ["vc-x"], "last_updated": "2026-01-01T00:00:00Z"}, state_file.open("w"))
        from src.harvester import state
        original = state.STATE_FILE
        state.STATE_FILE = state_file
        try:
            state.mark_completed("vc-x")
            data = json.load(state_file.open())
            assert "vc-x" in data["completed_vcs"]
            assert "vc-x" not in data["failed_vcs"]
        finally:
            state.STATE_FILE = original

def test_load_state_returns_vc_patterns():
    """load_state returns (completed_vcs, failed_vcs, vc_patterns)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "harvest_state.json"
        json.dump({
            "completed_vcs": ["vc-a"],
            "failed_vcs": ["vc-b"],
            "vc_patterns": {
                "vc-a": {"slug_regex": "/company/([a-z0-9-]+)", "detail_url_template": "https://vc-a.com/company/{slug}", "probed_at": "2026-03-23T00:00:00Z", "confidence": "high"}
            },
            "last_updated": "2026-03-23T00:00:00Z"
        }, state_file.open("w"))
        from src.harvester import state
        original = state.STATE_FILE
        state.STATE_FILE = state_file
        try:
            completed, failed, patterns = state.load_state()
            assert completed == {"vc-a"}
            assert failed == {"vc-b"}
            assert patterns == {"vc-a": {"slug_regex": "/company/([a-z0-9-]+)", "detail_url_template": "https://vc-a.com/company/{slug}", "probed_at": "2026-03-23T00:00:00Z", "confidence": "high"}}
        finally:
            state.STATE_FILE = original


def test_get_vc_pattern_returns_cached():
    """get_vc_pattern returns cached pattern if exists and not expired."""
    import pytest
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "harvest_state.json"
        json.dump({
            "completed_vcs": [], "failed_vcs": [], "vc_patterns": {},
            "last_updated": "2026-03-23T00:00:00Z"
        }, state_file.open("w"))
        from src.harvester import state
        original = state.STATE_FILE
        state.STATE_FILE = state_file
        try:
            # Cache a pattern
            state.cache_vc_pattern("vc-x", {
                "slug_regex": "/company/([a-z0-9-]+)",
                "detail_url_template": "https://vc-x.com/company/{slug}",
                "confidence": "high"
            })
            pattern = state.get_vc_pattern("vc-x")
            assert pattern is not None
            assert pattern["slug_regex"] == "/company/([a-z0-9-]+)"
        finally:
            state.STATE_FILE = original


def test_get_vc_pattern_returns_none_for_unknown():
    """get_vc_pattern returns None for unknown vc_key."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "harvest_state.json"
        json.dump({"completed_vcs": [], "failed_vcs": [], "vc_patterns": {}, "last_updated": ""}, state_file.open("w"))
        from src.harvester import state
        original = state.STATE_FILE
        state.STATE_FILE = state_file
        try:
            assert state.get_vc_pattern("unknown-vc") is None
        finally:
            state.STATE_FILE = original


def test_cache_vc_pattern_requires_both_fields():
    """cache_vc_pattern rejects partial patterns (slug_regex or detail_url_template missing)."""
    import pytest
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "harvest_state.json"
        json.dump({"completed_vcs": [], "failed_vcs": [], "vc_patterns": {}, "last_updated": ""}, state_file.open("w"))
        from src.harvester import state
        original = state.STATE_FILE
        state.STATE_FILE = state_file
        try:
            with pytest.raises(ValueError, match="cache_vc_pattern requires slug_regex and detail_url_template to both be non-null"):
                state.cache_vc_pattern("vc-x", {"slug_regex": "/company/([a-z0-9-]+)"})  # missing detail_url_template
        finally:
            state.STATE_FILE = original


def test_clear_vc_pattern():
    """clear_vc_pattern removes the vc_key from vc_patterns and preserves others."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "harvest_state.json"
        json.dump({
            "completed_vcs": [], "failed_vcs": [],
            "vc_patterns": {
                "vc-x": {"slug_regex": "/company/([a-z0-9-]+)", "detail_url_template": "https://vc-x.com/company/{slug}", "confidence": "high"},
                "vc-y": {"slug_regex": "/startups/([a-z0-9-]+)", "detail_url_template": "https://vc-y.com/startups/{slug}", "probed_at": "2026-03-23T00:00:00Z", "confidence": "medium"},
            },
            "last_updated": ""
        }, state_file.open("w"))
        from src.harvester import state
        original = state.STATE_FILE
        state.STATE_FILE = state_file
        try:
            state.clear_vc_pattern("vc-x")
            assert state.get_vc_pattern("vc-x") is None
            # vc-y should be preserved
            assert state.get_vc_pattern("vc-y") is not None
            assert state.get_vc_pattern("vc-y")["slug_regex"] == "/startups/([a-z0-9-]+)"
        finally:
            state.STATE_FILE = original


def test_get_vc_pattern_returns_none_after_30_days():
    """get_vc_pattern returns None if pattern is older than 30 days."""
    from datetime import datetime, timezone, timedelta
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "harvest_state.json"
        old_date = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
        json.dump({
            "completed_vcs": [], "failed_vcs": [],
            "vc_patterns": {"vc-old": {"slug_regex": "/company/([a-z0-9-]+)", "detail_url_template": "https://old.com/company/{slug}", "probed_at": old_date, "confidence": "high"}},
            "last_updated": old_date
        }, state_file.open("w"))
        from src.harvester import state
        original = state.STATE_FILE
        state.STATE_FILE = state_file
        try:
            assert state.get_vc_pattern("vc-old") is None  # expired
        finally:
            state.STATE_FILE = original
