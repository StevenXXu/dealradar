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
