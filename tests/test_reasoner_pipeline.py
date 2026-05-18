# tests/test_reasoner_pipeline.py
import json
import re
from pathlib import Path
from unittest.mock import patch, MagicMock
from src.reasoner.pipeline import ReasonerPipeline


def test_reasoner_pipeline_loads_raw_companies(tmp_path):
    raw_file = tmp_path / "raw.json"
    raw_file.write_text(
        json.dumps(
            [
                {
                    "company_name": "Canvas",
                    "domain": "https://canvas.co",
                    "vc_source": "TestVC",
                }
            ]
        )
    )
    pipeline = ReasonerPipeline(raw_companies_path=str(raw_file))
    assert len(pipeline.companies) == 1


def test_reasoner_pipeline_output_schema(tmp_path):
    raw_file = tmp_path / "raw.json"
    raw_file.write_text(
        json.dumps(
            [
                {
                    "company_name": "Canvas",
                    "domain": "https://canvas.co",
                    "vc_source": "TestVC",
                }
            ]
        )
    )
    out_file = tmp_path / "enriched.json"

    with patch("src.harvester.jina_client.JinaClient.fetch") as mock_fetch:
        mock_fetch.return_value = (
            "<p>Canvas is a design tool.</p><p>They raised $12M Series A.</p>"
        )
        with patch("src.reasoner.models.ModelChain.complete") as mock_model:
            mock_model.return_value = MagicMock(
                text='{"has_cfo_hire":false,"has_multilang_apac":false,"has_series_c_plus":false,"has_audit_signals":false,"has_supply_chain_robotics":false,"valuation_over_1b":false,"last_raise_amount_usd":12000000,"months_since_raise":10,"sector":"B2B SaaS"}'
            )
            pipeline = ReasonerPipeline(
                raw_companies_path=str(raw_file), output_path=str(out_file)
            )
            result = pipeline.process_company(pipeline.companies[0], idx=1, total=1)

    assert "company_name" in result
    assert "signal_score" in result
    assert "tags" in result
    assert "funding_clock" in result
    assert isinstance(result["signal_score"], int)


def test_pipeline_uses_last_raise_date_from_signal_data():
    pipeline_src = (
        Path(__file__)
        .parent.parent.joinpath("src", "reasoner", "pipeline.py")
        .read_text()
    )
    # Find the line that sets last_raise_date
    lines = pipeline_src.splitlines()
    last_raise_line = None
    for line in lines:
        if "last_raise_date" in line:
            last_raise_line = line
            break
    assert last_raise_line is not None, "last_raise_date not found in pipeline.py"
    # The line must reference signal_data, not hardcoded None
    assert "signal_data" in last_raise_line, (
        f"last_raise_date line does not use signal_data: {last_raise_line!r}"
    )


# ─── Gatekeeper integration ─────────────────────────────────────────


def test_run_drops_garbage_named_companies_before_llm(tmp_path):
    """The gatekeeper must reject 'Website'/'Read More' style extractor
    failures before any expensive LLM call is made. Verifies via a
    mock that process_company is not invoked for skipped rows."""
    raw_file = tmp_path / "raw.json"
    raw_file.write_text(
        json.dumps(
            [
                {"company_name": "Website", "domain": "https://x.com", "vc_source": "VC"},
                {"company_name": "Read More", "domain": "https://y.com", "vc_source": "VC"},
                {"company_name": "Canvas", "domain": "https://canvas.co", "vc_source": "VC"},
            ]
        )
    )
    out_file = tmp_path / "enriched.json"  # does not exist yet → empty seen set

    pipeline = ReasonerPipeline(
        raw_companies_path=str(raw_file), output_path=str(out_file)
    )
    # Stub process_company so we can assert call count without doing real IO
    pipeline.process_company = MagicMock(
        side_effect=lambda c, idx, total: {**c, "signal_score": 0}
    )

    result = pipeline.run()

    # Only the real company should reach the LLM step
    assert pipeline.process_company.call_count == 1
    assert pipeline.process_company.call_args[0][0]["company_name"] == "Canvas"
    # Output should contain just the processed passer
    assert len(result) == 1
    assert result[0]["company_name"] == "Canvas"


def test_run_preserves_previous_enrichment_across_runs(tmp_path):
    """A second run must keep the first run's enrichment in the output
    even when the second run processes zero new companies. Without
    this, the AlreadyEnrichedFilter would short-circuit run() to write
    an empty file and wipe production data on every re-run."""
    raw_file = tmp_path / "raw.json"
    raw_file.write_text(
        json.dumps(
            [
                {"company_name": "Canvas", "domain": "https://canvas.co", "vc_source": "VC"},
            ]
        )
    )
    out_file = tmp_path / "enriched.json"
    # Seed an existing enrichment record for the same domain
    out_file.write_text(
        json.dumps(
            [
                {
                    "company_name": "Canvas",
                    "domain": "https://canvas.co",
                    "vc_source": "VC",
                    "signal_score": 42,
                    "sector": "Design",
                }
            ]
        )
    )

    pipeline = ReasonerPipeline(
        raw_companies_path=str(raw_file), output_path=str(out_file)
    )
    pipeline.process_company = MagicMock()  # must NOT be called

    result = pipeline.run()

    # AlreadyEnrichedFilter should drop the only raw entry
    assert pipeline.process_company.call_count == 0
    # The previously-enriched record must still be in the output
    assert len(result) == 1
    assert result[0]["signal_score"] == 42
    # And the on-disk file must still have it (not be wiped)
    saved = json.loads(out_file.read_text())
    assert len(saved) == 1
    assert saved[0]["signal_score"] == 42
