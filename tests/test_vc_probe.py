import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

def test_probe_vc_structure_returns_valid_json():
    """probe_vc_structure returns slug_regex, detail_url_template, confidence from AI response."""
    mock_response = {
        "slug_regex": "(?:company|portfolio)/([a-z0-9-]+)",
        "detail_url_template": "https://investible.com/company/{slug}",
        "confidence": "high",
        "sample_slugs": ["canva", "stripe"],
        "num_links_found": 42
    }
    with patch("src.harvester.probe.call_ai_model") as mock_call:
        mock_call.return_value = json.dumps(mock_response)
        from src.harvester.probe import probe_vc_structure
        result = probe_vc_structure(
            portfolio_markdown="... /company/canva ... /company/stripe ...",
            portfolio_url="https://investible.com/portfolio",
            base_url="https://investible.com"
        )
        assert result["slug_regex"] == "(?:company|portfolio)/([a-z0-9-]+)"
        assert result["detail_url_template"] == "https://investible.com/company/{slug}"
        assert result["confidence"] == "high"

def test_probe_vc_structure_raises_on_malformed_json():
    """probe_vc_structure raises ProbeFailed on malformed AI response."""
    with patch("src.harvester.probe.call_ai_model") as mock_call:
        mock_call.return_value = "not valid json at all"
        from src.harvester.probe import probe_vc_structure, ProbeFailed
        with pytest.raises(ProbeFailed, match="malformed"):
            probe_vc_structure("...", "https://vc.com/portfolio", "https://vc.com")

def test_probe_vc_structure_raises_on_low_confidence():
    """probe_vc_structure raises ProbeFailed when confidence is low."""
    mock_response = {"slug_regex": None, "detail_url_template": None, "confidence": "low", "reason": "no pattern found"}
    with patch("src.harvester.probe.call_ai_model") as mock_call:
        mock_call.return_value = json.dumps(mock_response)
        from src.harvester.probe import probe_vc_structure, ProbeFailed
        with pytest.raises(ProbeFailed, match="confidence=low"):
            probe_vc_structure("...", "https://vc.com/portfolio", "https://vc.com")

def test_probe_vc_structure_raises_on_partial_result():
    """probe_vc_structure raises ProbeFailed when slug_regex is null."""
    mock_response = {"slug_regex": None, "detail_url_template": "https://vc.com/company/{slug}", "confidence": "high"}
    with patch("src.harvester.probe.call_ai_model") as mock_call:
        mock_call.return_value = json.dumps(mock_response)
        from src.harvester.probe import probe_vc_structure, ProbeFailed
        with pytest.raises(ProbeFailed, match="partial result"):
            probe_vc_structure("...", "https://vc.com/portfolio", "https://vc.com")