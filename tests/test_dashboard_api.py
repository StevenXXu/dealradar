# tests/test_dashboard_api.py
import json
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

# Must import after path setup
from app import app, _read_vc_seeds, _write_vc_seeds, CONFIG_PATH

client = TestClient(app)

def test_list_vc_seeds(tmp_path, monkeypatch):
    """GET /api/vc-seeds returns seed list."""
    seed_file = tmp_path / "vc_seeds.json"
    seed_file.write_text('[{"name": "TestVC", "url": "https://test.vc", "slug": "test-vc"}]')
    monkeypatch.setattr("app.CONFIG_PATH", seed_file)
    response = client.get("/api/vc-seeds")
    assert response.status_code == 200
    assert response.json()[0]["name"] == "TestVC"

def test_add_vc_seed(tmp_path, monkeypatch):
    """POST /api/vc-seeds adds a new seed."""
    seed_file = tmp_path / "vc_seeds.json"
    seed_file.write_text("[]")
    monkeypatch.setattr("app.CONFIG_PATH", seed_file)
    response = client.post("/api/vc-seeds", json={"name": "NewVC", "url": "https://new.vc"})
    assert response.status_code == 200
    data = json.loads(seed_file.read_text())
    assert len(data) == 1
    assert data[0]["name"] == "NewVC"

def test_delete_vc_seed(tmp_path, monkeypatch):
    """DELETE /api/vc-seeds/{slug} removes seed."""
    seed_file = tmp_path / "vc_seeds.json"
    seed_file.write_text('[{"name": "ToDelete", "url": "https://del.vc", "slug": "todelete"}]')
    monkeypatch.setattr("app.CONFIG_PATH", seed_file)
    response = client.delete("/api/vc-seeds/todelete")
    assert response.status_code == 200
    data = json.loads(seed_file.read_text())
    assert len(data) == 0

def test_get_companies_empty(tmp_path, monkeypatch):
    """GET /api/companies returns 0 when file doesn't exist."""
    monkeypatch.setattr("app.ENRICHED_PATH", tmp_path / "nonexistent.json")
    response = client.get("/api/companies")
    assert response.status_code == 200
    assert response.json()["count"] == 0

def test_get_state_empty(tmp_path, monkeypatch):
    """GET /api/state returns empty completed_vcs when no state."""
    monkeypatch.setattr("app.STATE_PATH", tmp_path / "nonexistent.json")
    response = client.get("/api/state")
    assert response.status_code == 200
    assert response.json()["completed_vcs"] == []

def test_parse_stdout_scraping():
    from app import _parse_stdout_line
    line = "  Scraping Blackbird (https://blackbird.vc/portfolio)..."
    result = _parse_stdout_line(line)
    assert result["vc"] == "Blackbird"
    assert result["status"] == "scraping"
    assert result["companies"] == 0
    assert "elapsed" in result

def test_parse_stdout_done():
    from app import _parse_stdout_line
    line = "  Playwright found 23 companies from Blackbird"
    result = _parse_stdout_line(line)
    assert result["vc"] == "Blackbird"
    assert result["status"] == "done"
    assert result["companies"] == 23

def test_parse_stdout_skipped():
    from app import _parse_stdout_line
    line = "  [Blackbird] SKIPPED — already completed"
    result = _parse_stdout_line(line)
    assert result["vc"] == "Blackbird"
    assert result["status"] == "skipped"
    assert result["companies"] == 0

def test_parse_stdout_harvest_complete():
    from app import _parse_stdout_line
    line = "\nHarvest complete: 156 unique companies"
    result = _parse_stdout_line(line)
    assert result["status"] == "harvest_complete"
    assert result["total"] == 156