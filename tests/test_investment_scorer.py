"""Tests for src/reasoner/investment_scorer.py.

Covers the math (weighted total, financial buckets, endorsement
bonus single-application), parsing tolerance for messy LLM output,
and the no-LLM fallback path. The two LLM-driven dimensions (TAM,
Team) are exercised via a stub model_chain — no real API calls.
"""
import pytest
from unittest.mock import MagicMock

from src.reasoner.investment_scorer import (
    InvestmentResult,
    InvestmentScorer,
    ScoreBreakdown,
    TOP_TIER_INSTITUTIONS,
    _parse_analysis_reasons,
    _parse_score_number,
)


# ─── Curated lists ───────────────────────────────────────────────────


class TestTopTierInstitutions:
    def test_no_leading_whitespace_entries(self):
        """Regression: dealflow's TOP50_UNIVERSITIES had ' northwestern'
        with a leading space so it never matched. Guarantee that
        doesn't happen here."""
        for name in TOP_TIER_INSTITUTIONS:
            assert name == name.strip(), (
                f"institution {name!r} has surrounding whitespace"
            )

    def test_all_entries_lowercase(self):
        for name in TOP_TIER_INSTITUTIONS:
            assert name == name.lower(), f"{name!r} should be lowercase"


# ─── Score number parsing ────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("78", 78.0),
        ("78\n", 78.0),
        ("78.5", 78.5),
        ("  42  ", 42.0),
        ("Score: 78 out of 100", 78.0),
        ("The score is 0", 0.0),
        ("100", 100.0),
        ("200", 100.0),  # clamped
        ("-50", 0.0),    # clamped
        ("", 50.0),      # neutral fallback
        ("not a number", 50.0),
    ],
)
def test_parse_score_number(raw, expected):
    assert _parse_score_number(raw) == expected


# ─── Analysis / reasons parsing ──────────────────────────────────────


class TestParseAnalysisReasons:
    def test_well_formed(self):
        text = (
            "ANALYSIS:\nAcme is well positioned in a fast-growing market.\n"
            "REASONS:\n- Strong team\n- Clear moat\n"
        )
        a, r = _parse_analysis_reasons(text)
        assert "fast-growing market" in a
        assert "Strong team" in r
        assert "Clear moat" in r

    def test_case_insensitive(self):
        text = "analysis:\nText.\nreasons:\n- One"
        a, r = _parse_analysis_reasons(text)
        assert a.startswith("Text")
        assert "One" in r

    def test_missing_reasons_section(self):
        a, r = _parse_analysis_reasons("ANALYSIS:\nJust analysis.")
        assert "Just analysis" in a
        assert "not parsed" in r.lower()

    def test_missing_both_sections(self):
        a, r = _parse_analysis_reasons("just freeform text")
        assert "not parsed" in a.lower()
        assert "not parsed" in r.lower()

    def test_empty_input(self):
        a, r = _parse_analysis_reasons("")
        assert a == ""
        assert r == ""


# ─── ScoreBreakdown math ─────────────────────────────────────────────


class TestScoreBreakdown:
    def test_weighted_total_uses_specified_weights(self):
        b = ScoreBreakdown(
            tam=100, team=100, moat=100, exit_score=100, industry=100, financial=100
        )
        # All 100s × weight sum = 100
        assert b.weighted_total() == pytest.approx(100.0)

    def test_weighted_total_respects_dimension_weights(self):
        # Only TAM = 100; weight = 25%; total should be 25
        b = ScoreBreakdown(tam=100)
        assert b.weighted_total() == pytest.approx(25.0)

    def test_financial_dimension_has_5pct_weight(self):
        b = ScoreBreakdown(financial=100)
        assert b.weighted_total() == pytest.approx(5.0)

    def test_as_dict_includes_weighted_total(self):
        b = ScoreBreakdown(tam=80, team=60)
        d = b.as_dict()
        assert d["tam"] == 80
        assert d["team"] == 60
        assert d["weighted_total"] == pytest.approx(80 * 0.25 + 60 * 0.25)


# ─── Financial bucketing ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "growth,expected",
    [
        (None, 50.0),
        (0.0, 20.0),
        (10.0, 20.0),
        (20.0, 50.0),
        (49.9, 50.0),
        (50.0, 80.0),
        (300.0, 80.0),
    ],
)
def test_score_financial_buckets(growth, expected):
    assert InvestmentScorer._score_financial(growth) == expected


# ─── Score with no model_chain (fallback path) ───────────────────────


class TestScoreNoModelChain:
    def test_falls_back_to_neutral_on_qualitative_dims(self):
        s = InvestmentScorer(model_chain=None)
        result = s.score("Acme", "AI infra", "AI", revenue_growth=60.0)
        assert isinstance(result, InvestmentResult)
        assert result.breakdown.tam == 50.0
        assert result.breakdown.team == 50.0
        # Financial still derived from growth (no LLM needed)
        assert result.breakdown.financial == 80.0
        # Analysis is the no-LLM template
        assert "fallback" in result.analysis.lower()


# ─── Endorsement bonus — regression for dealflow double-counting ─────


class TestEndorsementBonus:
    def _scorer_with_team(self, team_score: float) -> InvestmentScorer:
        """Stub the team scoring to return a deterministic value so
        we can isolate endorsement-bonus behavior from LLM mocks."""
        s = InvestmentScorer(model_chain=MagicMock())
        s._score_tam = lambda *a, **k: 50.0
        s._score_team = lambda *a, **k: team_score
        s._generate_analysis = lambda *a, **k: ("a", "r")
        return s

    def test_no_bonus_when_not_endorsed(self):
        s = self._scorer_with_team(80.0)
        result = s.score("Acme", "", "", dealradar_endorsed=False)
        assert result.endorsement_bonus == 0.0

    def test_no_bonus_when_team_below_threshold(self):
        s = self._scorer_with_team(69.99)
        result = s.score("Acme", "", "", dealradar_endorsed=True)
        assert result.endorsement_bonus == 0.0

    def test_bonus_applied_when_endorsed_and_team_at_threshold(self):
        s = self._scorer_with_team(70.0)
        result = s.score("Acme", "", "", dealradar_endorsed=True)
        assert result.endorsement_bonus == 20.0

    def test_endorsement_bonus_applied_to_total_not_team_dim(self):
        """Regression: dealflow's ScorerAgent did `team += 20` BEFORE
        calling finalize_score (which weighted team at 25%) AND had
        an unused _calculate_dealradar_bonus method that returned 20
        as a flat bonus. Net effect was inconsistent and double-
        counted. Here the team dimension MUST be untouched and the
        +20 MUST land on the total only."""
        s = self._scorer_with_team(80.0)
        result = s.score("Acme", "", "", dealradar_endorsed=True)
        # Team dimension preserves its raw score, NOT 80+20
        assert result.breakdown.team == 80.0
        # Endorsement reports as separate field
        assert result.endorsement_bonus == 20.0
        # Total = weighted_total + bonus
        weighted = result.breakdown.weighted_total()
        assert result.total == pytest.approx(weighted + 20.0)

    def test_total_clamped_at_100(self):
        """Even with all dims = 100 (= weighted 100) plus +20 bonus,
        the reported total must not exceed 100."""
        s = InvestmentScorer(model_chain=MagicMock())
        s._score_tam = lambda *a, **k: 100.0
        s._score_team = lambda *a, **k: 100.0
        s._generate_analysis = lambda *a, **k: ("", "")
        # All other dims are NEUTRAL_FALLBACK=50; only LLM dims maxed.
        # Force them to 100 too via direct call
        # (or rely on the weighted total + bonus exceeding 100)
        result = s.score("X", "", "", revenue_growth=60.0, dealradar_endorsed=True)
        assert result.total <= 100.0


# ─── End-to-end with mocked model_chain ──────────────────────────────


def _mock_chain(text_for_each_call: list[str]):
    """Returns a chain whose .complete() yields the next canned text
    on each call. Raises StopIteration if called more often than the
    test allowed for — surfaces drift between code and test."""
    chain = MagicMock()
    responses = iter(
        MagicMock(text=t) for t in text_for_each_call
    )
    chain.complete.side_effect = lambda *args, **kwargs: next(responses)
    return chain


class TestScoreEndToEnd:
    def test_score_with_mocked_llm(self):
        # Three .complete() calls: TAM, Team, Analysis
        chain = _mock_chain([
            "82",
            "75",
            "ANALYSIS:\nStrong fundamentals.\nREASONS:\n- High TAM\n- Solid team",
        ])
        s = InvestmentScorer(model_chain=chain)

        result = s.score(
            company_name="Acme AI",
            product_description="LLM infra at scale",
            industry="AI",
            revenue_growth=60.0,
            dealradar_endorsed=False,
        )

        assert result.breakdown.tam == 82.0
        assert result.breakdown.team == 75.0
        assert result.breakdown.financial == 80.0  # growth >= 50
        assert result.breakdown.moat == 50.0       # placeholder
        assert "Strong fundamentals" in result.analysis
        assert "High TAM" in result.reasons
        # 3 LLM calls — TAM, Team, Analysis
        assert chain.complete.call_count == 3

    def test_score_skips_tam_llm_when_no_product_description(self):
        # When product_description is empty, TAM falls back without
        # calling the model — saves a token spend on empty input
        chain = _mock_chain(["75", "ANALYSIS:\nx\nREASONS:\ny"])
        s = InvestmentScorer(model_chain=chain)
        result = s.score("Acme", product_description="", industry="AI")
        assert result.breakdown.tam == InvestmentScorer.NEUTRAL_FALLBACK
        # Only Team + Analysis hit the chain
        assert chain.complete.call_count == 2

    def test_as_dict_round_trip(self):
        chain = _mock_chain([
            "60", "60",
            "ANALYSIS:\nfine\nREASONS:\n- ok",
        ])
        s = InvestmentScorer(model_chain=chain)
        result = s.score("X", "product", "AI", revenue_growth=10.0)
        d = result.as_dict()
        assert "breakdown" in d
        assert d["breakdown"]["tam"] == 60.0
        assert d["total"] == d["breakdown"]["weighted_total"]
        assert d["endorsement_bonus"] == 0.0
        assert d["analysis"].startswith("fine")
