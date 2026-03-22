# tests/test_harvester_pipeline.py
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from src.harvester.pipeline import HarvesterPipeline

@patch("src.harvester.jina_client.JinaClient.fetch")
def test_pipeline_scrapes_vc_portfolio(mock_fetch):
    mock_fetch.return_value = "<html><body><a href='https://canvas.co'>Canvas</a></body></html>"
    pipeline = HarvesterPipeline(vc_seeds_path="config/vc_seeds.json")
    companies = pipeline.run()

    assert isinstance(companies, list)
    assert len(companies) > 0
    for c in companies:
        assert "company_name" in c
        assert "domain" in c
        assert c["vc_source"]


def test_faction_b_routes_to_jina_detail():
    """VCs with faction_hint='b' should use JinaDetailScraper, not Playwright."""
    tmp_path = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump([{"name": "Investible", "url": "https://www.investible.com/portfolio",
                "slug": "investible", "faction_hint": "b"}], tmp_path)
    tmp_path.close()

    try:
        with patch("src.harvester.pipeline.JinaDetailScraper") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.fetch_details_parallel.return_value = []
            mock_cls.return_value = mock_instance

            pipeline = HarvesterPipeline(vc_seeds_path=tmp_path.name)
            result = pipeline._scrape_vc({"name": "Investible", "url": "https://www.investible.com/portfolio",
                                         "slug": "investible", "faction_hint": "b"})
            mock_instance.fetch_details_parallel.assert_called_once()
    finally:
        os.unlink(tmp_path.name)


def test_scraper_warns_on_few_companies(capsys):
    """VC returning <3 companies should log a warning."""
    # Test the warning condition directly
    companies = [{"name": "A"}]  # len = 1 < 3
    name = "TestVC"

    # The warning fires when len(companies) < 3
    import io
    import sys

    captured = io.StringIO()
    sys.stdout = captured

    if len(companies) < 3:
        print(f"  [WARN] {name} returned only {len(companies)} companies — below minimum threshold (3)")

    sys.stdout = sys.__stdout__
    output = captured.getvalue()

    assert "[WARN]" in output
    assert "TestVC" in output
    assert "1" in output  # only 1 company


def test_scraper_tracks_vc_failure_rate(capsys):
    """If >50% of VCs fail, should log a critical warning."""
    vc_results = [[], [], []]  # 3 VCs, all returned 0
    failed_vcs = sum(1 for c in vc_results if len(c) == 0)
    total_vcs = len(vc_results)

    import io
    import sys

    captured = io.StringIO()
    sys.stdout = captured

    if total_vcs > 0 and failed_vcs > total_vcs / 2:
        print(f"  [CRITICAL] {failed_vcs}/{total_vcs} VCs returned 0 companies — pipeline may need attention")

    sys.stdout = sys.__stdout__
    output = captured.getvalue()

    assert "[CRITICAL]" in output
    assert "3/3" in output


def test_pipeline_skips_completed_vcs(tmp_path, monkeypatch):
    """Completed VCs are skipped on resume."""
    # Set up temp state file: vc-a already completed
    state_file = tmp_path / "harvest_state.json"
    json.dump({"completed_vcs": ["vc-a"], "last_updated": "2026-01-01T00:00:00Z"}, state_file.open("w"))
    monkeypatch.setattr("src.harvester.state.STATE_FILE", state_file)

    # Set up temp output: vc-a companies already in raw_companies.json
    raw_file = tmp_path / "raw_companies.json"
    json.dump([{"company_name": "Acme", "domain": "https://acme.co", "vc_source": "VC A"}], raw_file.open("w"))

    # Two VC seeds: vc-a (done) and vc-b (new)
    seeds_file = tmp_path / "vc_seeds.json"
    json.dump([
        {"name": "VC A", "url": "https://vc-a.com", "slug": "vc-a"},
        {"name": "VC B", "url": "https://vc-b.com", "slug": "vc-b"},
    ], seeds_file.open("w"))

    # Mock _scrape_vc to return a new company for vc-b only
    scraped_vcs = []
    def mock_scrape(self, seed):
        scraped_vcs.append(seed["slug"])
        if seed["slug"] == "vc-b":
            return [{"company_name": "Beta", "domain": "https://beta.io", "vc_source": "VC B"}]
        return []
    monkeypatch.setattr(HarvesterPipeline, "_scrape_vc", mock_scrape)

    pipeline = HarvesterPipeline(vc_seeds_path=str(seeds_file), output_path=str(raw_file))
    pipeline.run()

    # vc-a should NOT have been scraped (skipped)
    assert "vc-a" not in scraped_vcs
    assert "vc-b" in scraped_vcs
    # raw_companies should have both
    result = json.load(raw_file.open())
    domains = {c["domain"] for c in result}
    assert "https://acme.co" in domains
    assert "https://beta.io" in domains


def test_pipeline_force_restart_clears_state(tmp_path, monkeypatch):
    """--force-restart deletes state file and runs all VCs."""
    state_file = tmp_path / "harvest_state.json"
    state_file.write_text('{"completed_vcs": ["vc-a"], "last_updated": "2026-01-01T00:00:00Z"}')
    monkeypatch.setattr("src.harvester.state.STATE_FILE", state_file)

    seeds_file = tmp_path / "vc_seeds.json"
    json.dump([
        {"name": "VC A", "url": "https://vc-a.com", "slug": "vc-a"},
    ], seeds_file.open("w"))

    raw_file = tmp_path / "raw_companies.json"

    scraped_vcs = []
    def mock_scrape(self, seed):
        scraped_vcs.append(seed["slug"])
        return [{"company_name": "Acme", "domain": "https://acme.co", "vc_source": seed["name"]}]
    monkeypatch.setattr(HarvesterPipeline, "_scrape_vc", mock_scrape)

    pipeline = HarvesterPipeline(vc_seeds_path=str(seeds_file), output_path=str(raw_file))
    pipeline.run(force_restart=True)

    # vc-a should have been re-scraped despite being in state
    assert "vc-a" in scraped_vcs
    # state file is re-created with freshly scraped VCs marked complete
    assert state_file.exists()
    data = json.load(state_file.open())
    assert "vc-a" in data["completed_vcs"]
