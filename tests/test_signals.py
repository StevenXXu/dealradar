# tests/test_signals.py
from src.reasoner.signals import SignalDetector, SignalScore
from unittest.mock import MagicMock
import pytest

def test_score_cfo_hire_is_highest():
    detector = SignalDetector()
    score = detector.calculate_score(
        has_cfo_hire=True,
        last_raise_amount=15_000_000,
        months_since_raise=16,
        has_multilang=False,
        has_series_c_plus=False,
        has_audit_signals=False,
    )
    assert score == SignalScore.CFO_HIRE  # +40

def test_score_old_raise_without_cfo():
    detector = SignalDetector()
    score = detector.calculate_score(
        has_cfo_hire=False,
        last_raise_amount=8_000_000,
        months_since_raise=20,
        has_multilang=False,
        has_series_c_plus=False,
        has_audit_signals=False,
    )
    assert score == SignalScore.LAST_RAISE_18_PLUS  # +30

def test_score_no_signals():
    detector = SignalDetector()
    score = detector.calculate_score(
        has_cfo_hire=False,
        last_raise_amount=None,
        months_since_raise=6,
        has_multilang=False,
        has_series_c_plus=False,
        has_audit_signals=False,
    )
    assert score == 0

def test_extract_tags():
    detector = SignalDetector()
    tags = detector.extract_tags(
        has_cfo_hire=True,
        last_raise_amount=15_000_000,
        months_since_raise=16,
        has_multilang=True,
        has_series_c_plus=True,
        has_audit_signals=True,
        valuation_over_1b=True,
        robotics_supply_chain=False,
    )
    assert "Pre-IPO Watch" in tags
    assert "Cross-Border Target" in tags
    assert "Unicorn" in tags

def test_analyze_text_extracts_last_raise_date():
    detector = SignalDetector()
    assert '"last_raise_date"' in detector.SYSTEM_PROMPT


def test_analyze_text_raises_on_invalid_json():
    """JSON parse error in AI response must raise, not return error dict."""
    detector = SignalDetector()
    mock_chain = MagicMock()
    mock_chain.complete.return_value = MagicMock(text="{ not valid json")

    with pytest.raises(ValueError, match="Failed to parse AI response"):
        detector.analyze_text("any text", mock_chain)
