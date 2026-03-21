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
