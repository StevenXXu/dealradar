# tests/test_harvester_pipeline.py
import json
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
