import pytest, tempfile, json, asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_faction_b_uses_default_regex_when_cache_miss_and_yields_3_plus():
    """When no cached pattern and default regex yields >=3 companies, no AI probe is called."""
    mock_jina = MagicMock()
    mock_jina.fetch_with_retry.return_value = "... /company/canva ... /company/stripe ... /company/figma ..."

    with patch("src.harvester.pipeline.JinaDetailScraper") as mock_scraper_cls:
        mock_scraper = MagicMock()
        mock_scraper.fetch_details_parallel.return_value = [
            {"company_name": "Canvas", "domain": "https://canvas.co"},
            {"company_name": "Stripe", "domain": "https://stripe.com"},
            {"company_name": "Figma", "domain": "https://figma.com"},
        ]
        mock_scraper_cls.return_value = mock_scraper

        with patch("src.harvester.probe.probe_vc_structure") as mock_probe:
            mock_probe.side_effect = Exception("AI probe should not be called")

            from src.harvester.pipeline import HarvesterPipeline
            from src.harvester import state as state_module

            with tempfile.TemporaryDirectory() as tmpdir:
                state_file = Path(tmpdir) / "harvest_state.json"
                state_file.write_text(json.dumps({"completed_vcs": [], "failed_vcs": [], "vc_patterns": {}, "last_updated": ""}))

                original_state_file = state_module.STATE_FILE
                state_module.STATE_FILE = state_file

                with patch("src.harvester.pipeline.JinaClient") as mock_jina_cls:
                    mock_jina_cls.return_value = mock_jina

                    pipeline = HarvesterPipeline(vc_seeds_path="config/vc_seeds.json", jina_client=mock_jina)
                    result = pipeline._scrape_faction_b({
                        "name": "TestVC",
                        "url": "https://testvc.com/portfolio",
                        "slug": "testvc",
                        "detail_url_template": "https://testvc.com/company/{slug}",
                    })

                    assert len(result) == 3
                    mock_probe.assert_not_called()

                state_module.STATE_FILE = original_state_file

def test_faction_b_calls_ai_probe_when_default_yields_fewer_than_3():
    """When default regex yields <3 companies, AI probe is triggered and result is cached."""
    mock_jina = MagicMock()
    mock_jina.fetch_with_retry.return_value = "... /company/canva ..."

    mock_probe_result = {
        "slug_regex": "(?:startups|deals)/([a-z0-9-]+)",
        "detail_url_template": "https://newvc.com/startups/{slug}",
        "confidence": "high",
        "sample_slugs": ["canva", "stripe"],
        "num_links_found": 12
    }

    with patch("src.harvester.pipeline.JinaClient") as mock_jina_cls:
        mock_jina_cls.return_value = mock_jina
        with patch("src.harvester.probe.probe_vc_structure") as mock_probe:
            mock_probe.return_value = mock_probe_result
            with patch("src.harvester.pipeline.JinaDetailScraper") as mock_scraper_cls:
                mock_scraper = MagicMock()
                mock_scraper.fetch_details_parallel.return_value = [
                    {"company_name": "Canvas", "domain": "https://canvas.co"},
                    {"company_name": "Stripe", "domain": "https://stripe.com"},
                    {"company_name": "Figma", "domain": "https://figma.com"},
                ]
                mock_scraper_cls.return_value = mock_scraper

                from src.harvester.pipeline import HarvesterPipeline
                from src.harvester import state as state_module

                with tempfile.TemporaryDirectory() as tmpdir:
                    state_file = Path(tmpdir) / "harvest_state.json"
                    state_file.write_text(json.dumps({"completed_vcs": [], "failed_vcs": [], "vc_patterns": {}, "last_updated": ""}))
                    original_state_file = state_module.STATE_FILE
                    state_module.STATE_FILE = state_file

                    try:
                        pipeline = HarvesterPipeline(vc_seeds_path="config/vc_seeds.json", jina_client=mock_jina)
                        result = pipeline._scrape_faction_b({
                            "name": "NewVC",
                            "url": "https://newvc.com/portfolio",
                            "slug": "newvc",
                            "detail_url_template": "https://newvc.com/company/{slug}",
                        })

                        mock_probe.assert_called_once()
                        assert len(result) == 3

                        _, _, patterns = state_module.load_state()
                        assert "newvc" in patterns
                        assert patterns["newvc"]["slug_regex"] == "(?:startups|deals)/([a-z0-9-]+)"
                    finally:
                        state_module.STATE_FILE = original_state_file

def test_faction_b_validation_gate_rejects_404_detail_url():
    """When AI probe succeeds but first detail URL returns 404, pattern is NOT cached."""
    mock_jina = MagicMock()
    mock_jina.fetch_with_retry.return_value = "... /company/canva ..."

    mock_probe_result = {
        "slug_regex": "(?:company|portfolio)/([a-z0-9-]+)",
        "detail_url_template": "https://broken-vc.com/company/{slug}",
        "confidence": "high",
        "sample_slugs": ["canva"],
        "num_links_found": 5
    }

    with patch("src.harvester.pipeline.JinaClient") as mock_jina_cls:
        mock_jina_cls.return_value = mock_jina
        with patch("src.harvester.probe.probe_vc_structure") as mock_probe:
            mock_probe.return_value = mock_probe_result
            with patch("src.harvester.pipeline.JinaDetailScraper") as mock_scraper_cls:
                mock_scraper = MagicMock()
                mock_scraper.fetch_details_parallel.return_value = [{"company_name": "Canvas", "domain": "https://canvas.co"}]
                mock_scraper_cls.return_value = mock_scraper
                with patch("src.harvester.pipeline._validate_detail_url") as mock_validate:
                    mock_validate.return_value = False  # 404

                    from src.harvester.pipeline import HarvesterPipeline
                    from src.harvester import state as state_module

                    with tempfile.TemporaryDirectory() as tmpdir:
                        state_file = Path(tmpdir) / "harvest_state.json"
                        state_file.write_text(json.dumps({"completed_vcs": [], "failed_vcs": [], "vc_patterns": {}, "last_updated": ""}))
                        original_state_file = state_module.STATE_FILE
                        state_module.STATE_FILE = state_file

                        try:
                            pipeline = HarvesterPipeline(vc_seeds_path="config/vc_seeds.json", jina_client=mock_jina)
                            result = pipeline._scrape_faction_b({
                                "name": "BrokenVC",
                                "url": "https://broken-vc.com/portfolio",
                                "slug": "brokenvc",
                            })

                            _, _, patterns = state_module.load_state()
                            assert "brokenvc" not in patterns
                        finally:
                            state_module.STATE_FILE = original_state_file

def test_faction_b_circuit_breaker_skips_11th_probe():
    """When >10 probes have fired, 11th VC does not get AI probe."""
    from src.harvester.pipeline import _probe_count, _should_probe, _increment_probe, _reset_probe_counter

    _reset_probe_counter()
    for _ in range(10):
        assert _should_probe() is True
        _increment_probe()
    assert _should_probe() is False

    _reset_probe_counter()
    assert _should_probe() is True

def test_validate_detail_url_fail_open_on_network_error():
    """Network error (timeout/DNS) returns True so caching proceeds."""
    from src.harvester.pipeline import _validate_detail_url
    with patch("src.harvester.pipeline.requests.head") as mock_head:
        mock_head.side_effect = Exception("DNS failure")
        assert _validate_detail_url("https://example.com/company/acme") is True

def test_validate_detail_url_404_returns_false():
    """404 response returns False (do NOT cache)."""
    from src.harvester.pipeline import _validate_detail_url
    with patch("src.harvester.pipeline.requests.head") as mock_head:
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = False
        mock_head.return_value = mock_response
        assert _validate_detail_url("https://broken.com/company/acme") is False

def test_validate_detail_url_none_url_returns_true():
    """None URL returns True (skip validation)."""
    from src.harvester.pipeline import _validate_detail_url
    assert _validate_detail_url(None) is True

def test_derive_template_from_regex():
    """_derive_template_from_regex produces correct template per spec algorithm."""
    from src.harvester.pipeline import _derive_template_from_regex
    result = _derive_template_from_regex(
        "https://www.investible.com/portfolio",
        r"/(?:company|portfolio)/([a-z0-9-]+)"
    )
    assert result == "https://www.investible.com/company/{slug}"

    result2 = _derive_template_from_regex(
        "https://newvc.com/portfolio",
        r"/(?:startups|deals)/([a-z0-9-]+)"
    )
    assert result2 == "https://newvc.com/startups/{slug}"

    result3 = _derive_template_from_regex(
        "https://simples-vc.com/our-companies",
        r"/our-companies/([a-z0-9-]+)"
    )
    assert result3 == "https://simples-vc.com/our-companies/{slug}"