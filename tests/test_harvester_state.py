import json
import os
import tempfile
from pathlib import Path

def test_load_state_missing_file():
    """Missing state file returns empty set."""
    with tempfile.TemporaryDirectory() as tmpdir:
        from src.harvester import state
        original = state.STATE_FILE
        state.STATE_FILE = Path(tmpdir) / "nonexistent.json"
        try:
            result = state.load_state()
            assert result == set()
        finally:
            state.STATE_FILE = original

def test_load_state_existing():
    """Existing state file returns set of slugs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "harvest_state.json"
        json.dump({"completed_vcs": ["vc-a", "vc-b"], "last_updated": "2026-01-01T00:00:00Z"}, state_file.open("w"))
        from src.harvester import state
        original = state.STATE_FILE
        state.STATE_FILE = state_file
        try:
            result = state.load_state()
            assert result == {"vc-a", "vc-b"}
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
            result = state.load_state()
            assert result == set()
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

def test_append_and_dedupe_atomic():
    """Interruption during write does not corrupt existing file."""
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
