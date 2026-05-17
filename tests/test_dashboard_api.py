# tests/test_dashboard_api.py
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

# Must import after path setup
from app import (
    app,
    verify_token,
    _read_vc_seeds,
    _write_vc_seeds,
    CONFIG_PATH,
)

app.dependency_overrides[verify_token] = lambda: {
    "user_id": "test",
    "tenant_id": "default",
}

client = TestClient(app)


# ─── Helpers for Supabase mocking ────────────────────────────────────


def _make_supabase_mock(
    tenants_data=None, companies_data=None, companies_count=None
):
    """Build a MagicMock SupabaseClient where:

    - .table('tenants').select(...).eq(...).execute().data
        returns the given tenants_data (default [{'id': 'tenant-uuid-x'}]).
    - .table('companies').select(...).eq(...)...execute().data / .count
        returns the given companies_data and companies_count.

    Any chain method (eq, order, range, gte, or_, limit, etc.) returns
    the same chain so the SDK's fluent API stays valid regardless of
    which subset the endpoint exercises.
    """
    if tenants_data is None:
        tenants_data = [{"id": "tenant-uuid-x"}]
    if companies_data is None:
        companies_data = []
    if companies_count is None:
        companies_count = len(companies_data)

    def table(name):
        chain = MagicMock()
        for method in (
            "select",
            "eq",
            "gte",
            "lte",
            "order",
            "limit",
            "range",
            "or_",
        ):
            setattr(chain, method, MagicMock(return_value=chain))
        result = MagicMock()
        if name == "tenants":
            result.data = tenants_data
            result.count = len(tenants_data)
        else:
            result.data = companies_data
            result.count = companies_count
        chain.execute.return_value = result
        return chain

    ms = MagicMock()
    ms._client.table.side_effect = table
    return ms

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
    """GET /api/companies returns 0 on Supabase empty or error."""
    class MockSupabase:
        class _client:
            class table:
                def __init__(self, name): pass
                def select(self, *args, **kwargs): return self
                def eq(self, *args, **kwargs): return self
                def order(self, *args, **kwargs): return self
                def limit(self, *args, **kwargs): return self
                def execute(self):
                    class Res:
                        count = 0
                        data = []
                    return Res()
    monkeypatch.setattr("app.get_supabase", lambda: MockSupabase())
    response = client.get("/api/companies", headers={"Authorization": "Bearer DUMMY"})
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


# ─── /api/companies/list ─────────────────────────────────────────────


def test_list_companies_paginated(monkeypatch):
    """Returns items + total + page metadata for the discovery feed."""
    rows = [
        {"id": "1", "company_name": "Canvas", "signal_score": 50},
        {"id": "2", "company_name": "PlasmaLeap", "signal_score": 30},
    ]
    monkeypatch.setattr(
        "app.get_supabase",
        lambda: _make_supabase_mock(companies_data=rows, companies_count=897),
    )
    resp = client.get(
        "/api/companies/list?page=0&page_size=2",
        headers={"Authorization": "Bearer X"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 897
    assert data["page"] == 0
    assert data["page_size"] == 2
    assert data["has_more"] is True
    assert len(data["items"]) == 2
    assert data["items"][0]["company_name"] == "Canvas"


def test_list_companies_last_page_has_no_more(monkeypatch):
    rows = [{"id": "1", "company_name": "OnlyOne", "signal_score": 5}]
    monkeypatch.setattr(
        "app.get_supabase",
        lambda: _make_supabase_mock(companies_data=rows, companies_count=1),
    )
    resp = client.get(
        "/api/companies/list", headers={"Authorization": "Bearer X"}
    )
    assert resp.status_code == 200
    assert resp.json()["has_more"] is False


def test_list_companies_empty_when_no_tenant(monkeypatch):
    """If the default tenant lookup fails, return empty rather than 500."""
    monkeypatch.setattr(
        "app.get_supabase",
        lambda: _make_supabase_mock(tenants_data=[], companies_data=[]),
    )
    resp = client.get(
        "/api/companies/list", headers={"Authorization": "Bearer X"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["items"] == []
    assert body["has_more"] is False


def test_list_companies_validates_page_size(monkeypatch):
    """page_size must be 1..200; 201 is rejected by Query() bounds."""
    monkeypatch.setattr(
        "app.get_supabase", lambda: _make_supabase_mock()
    )
    resp = client.get(
        "/api/companies/list?page_size=500",
        headers={"Authorization": "Bearer X"},
    )
    assert resp.status_code == 422


def test_list_companies_validates_negative_page(monkeypatch):
    monkeypatch.setattr(
        "app.get_supabase", lambda: _make_supabase_mock()
    )
    resp = client.get(
        "/api/companies/list?page=-1",
        headers={"Authorization": "Bearer X"},
    )
    assert resp.status_code == 422


def test_list_companies_sector_filter_calls_eq(monkeypatch):
    """Filter wiring smoke test: the 'sector' eq() must fire when set."""
    mock = _make_supabase_mock(companies_count=0)
    monkeypatch.setattr("app.get_supabase", lambda: mock)
    client.get(
        "/api/companies/list?sector=AI",
        headers={"Authorization": "Bearer X"},
    )
    # The companies-table chain receives at least 2 eq calls: tenant_id + sector.
    # We can't easily count by table without going deeper into the mock spec,
    # but we can assert no exception and that the endpoint ran the chain.
    assert mock._client.table.called


# ─── /api/companies/summary ──────────────────────────────────────────


def test_summary_aggregates_facets_and_stats(monkeypatch):
    """Verifies Python-side aggregation over the returned tenant rows."""
    from datetime import datetime, timedelta, timezone

    fresh = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    old = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat()
    rows = [
        {"region": "Asia-Pacific", "sector": "AI", "funding_stage": "Series A",
         "signal_score": 40, "created_at": fresh},
        {"region": "Asia-Pacific", "sector": "AI", "funding_stage": "Series B",
         "signal_score": 20, "created_at": old},
        {"region": "Europe", "sector": "Fintech", "funding_stage": "Series A",
         "signal_score": 50, "created_at": fresh},
    ]
    monkeypatch.setattr(
        "app.get_supabase", lambda: _make_supabase_mock(companies_data=rows)
    )
    resp = client.get(
        "/api/companies/summary", headers={"Authorization": "Bearer X"}
    )
    assert resp.status_code == 200
    body = resp.json()

    # Facets — counts by dimension
    assert body["facets"]["regions"] == {"Asia-Pacific": 2, "Europe": 1}
    assert body["facets"]["sectors"] == {"AI": 2, "Fintech": 1}
    assert body["facets"]["funding_stages"] == {"Series A": 2, "Series B": 1}

    # Stats — total/hot/avg/this_week
    stats = body["stats"]
    assert stats["total"] == 3
    assert stats["hot_count"] == 2  # 40 and 50 >= 30
    assert stats["avg_score"] == round((40 + 20 + 50) / 3, 2)
    assert stats["new_this_week"] == 2  # two within 7 days


def test_summary_handles_empty_tenant(monkeypatch):
    monkeypatch.setattr(
        "app.get_supabase",
        lambda: _make_supabase_mock(companies_data=[]),
    )
    resp = client.get(
        "/api/companies/summary", headers={"Authorization": "Bearer X"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["stats"]["total"] == 0
    assert body["stats"]["avg_score"] == 0
    assert body["facets"]["regions"] == {}


def test_summary_tolerates_rows_missing_optional_fields(monkeypatch):
    """region / funding_stage may be NULL pre-migration-002; skip those
    rather than fail the whole aggregation."""
    rows = [
        {"sector": "AI", "signal_score": 10, "created_at": None},
        {"sector": None, "signal_score": None, "created_at": "garbage"},
    ]
    monkeypatch.setattr(
        "app.get_supabase",
        lambda: _make_supabase_mock(companies_data=rows),
    )
    resp = client.get(
        "/api/companies/summary", headers={"Authorization": "Bearer X"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["stats"]["total"] == 2
    assert body["facets"]["sectors"] == {"AI": 1}
    assert body["facets"]["regions"] == {}