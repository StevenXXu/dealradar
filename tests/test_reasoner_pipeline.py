# tests/test_reasoner_pipeline.py
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from src.reasoner.pipeline import ReasonerPipeline

def test_reasoner_pipeline_loads_raw_companies(tmp_path):
    raw_file = tmp_path / "raw.json"
    raw_file.write_text(json.dumps([
        {"company_name": "Canvas", "domain": "https://canvas.co", "vc_source": "TestVC"}
    ]))
    pipeline = ReasonerPipeline(raw_companies_path=str(raw_file))
    assert len(pipeline.companies) == 1

def test_reasoner_pipeline_output_schema(tmp_path):
    raw_file = tmp_path / "raw.json"
    raw_file.write_text(json.dumps([
        {"company_name": "Canvas", "domain": "https://canvas.co", "vc_source": "TestVC"}
    ]))
    out_file = tmp_path / "enriched.json"

    with patch("src.harvester.jina_client.JinaClient.fetch") as mock_fetch:
        mock_fetch.return_value = "<p>Canvas is a design tool.</p><p>They raised $12M Series A.</p>"
        with patch("src.reasoner.models.ModelChain.complete") as mock_model:
            mock_model.return_value = MagicMock(
                text='{"has_cfo_hire":false,"has_multilang_apac":false,"has_series_c_plus":false,"has_audit_signals":false,"has_supply_chain_robotics":false,"valuation_over_1b":false,"last_raise_amount_usd":12000000,"months_since_raise":10,"sector":"B2B SaaS"}'
            )
            pipeline = ReasonerPipeline(
                raw_companies_path=str(raw_file),
                output_path=str(out_file)
            )
            result = pipeline.process_company(pipeline.companies[0])

    assert "company_name" in result
    assert "signal_score" in result
    assert "tags" in result
    assert "funding_clock" in result
    assert isinstance(result["signal_score"], int)
