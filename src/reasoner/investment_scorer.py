"""Six-dimensional weighted investment scoring.

Adapted from dealflow's ScorerAgent. The dealflow original:
  - hardcoded a 'team += 20' endorsement bonus BEFORE feeding team
    into the weighted total (so the +20 was multiplied by the 25%
    team weight, then ADDED again as a flat bonus elsewhere — net
    +25 instead of intended +20, with the actual logic split
    between an unused _calculate_dealradar_bonus method and inline
    code in score()).
  - had ' northwestern' (leading space) in TOP50_UNIVERSITIES so it
    never matched.
  - was tightly coupled to its Deal dataclass.

This version fixes all three and decouples from dataclasses so the
dealradar reasoner can call it with a plain dict + raw_text.

Score model (0-100 each, weighted sum):
  TAM       25% — LLM, qualitative on market size + CAGR signals
  Team      25% — LLM, founder credentials + track record
  Moat      15% — placeholder 50.0 (LLM extension reserved)
  Exit      15% — placeholder 50.0
  Industry  15% — placeholder 50.0
  Financial  5% — derived from revenue_growth (no LLM)

Endorsement bonus: +20 applied to the TOTAL when dealradar_endorsed
AND team_score >= 70. Single application, no double counting.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional


logger = logging.getLogger(__name__)


# Curated short list of top-tier institutions. Used in team scoring
# prompts to give the model an anchor set rather than relying on its
# implicit ranking. Names are lowercase, exact-match comparisons.
TOP_TIER_INSTITUTIONS: frozenset[str] = frozenset(
    {
        "mit",
        "stanford",
        "harvard",
        "oxford",
        "cambridge",
        "eth zurich",
        "epfl",
        "caltech",
        "princeton",
        "yale",
        "columbia",
        "uchicago",
        "upenn",
        "cornell",
        "northwestern",
        "duke",
        "jhu",
        "tu delft",
        "tsinghua",
        "pku",
        "nus",
        "ntu",
        "melbourne",
        "sydney",
        "anu",
        "unsw",
        "imperial",
        "ucl",
        "kth",
        "technical university of munich",
        "politecnico di milano",
        "polytechnique",
        "kaist",
    }
)

INP_CORE_INDUSTRIES: frozenset[str] = frozenset(
    {
        "ai",
        "ai+",
        "greentech",
        "robotics",
        "smart manufacturing",
        "web3",
        "fintech",
        "healthcare",
        "med-tech",
    }
)


@dataclass
class ScoreBreakdown:
    """Per-dimension scores (each 0-100) and weighted total."""

    tam: float = 0.0
    team: float = 0.0
    moat: float = 0.0
    exit_score: float = 0.0
    industry: float = 0.0
    financial: float = 0.0

    def weighted_total(self) -> float:
        return (
            self.tam * 0.25
            + self.team * 0.25
            + self.moat * 0.15
            + self.exit_score * 0.15
            + self.industry * 0.15
            + self.financial * 0.05
        )

    def as_dict(self) -> dict:
        return {
            "tam": self.tam,
            "team": self.team,
            "moat": self.moat,
            "exit_score": self.exit_score,
            "industry": self.industry,
            "financial": self.financial,
            "weighted_total": round(self.weighted_total(), 2),
        }


@dataclass
class InvestmentResult:
    """Output of InvestmentScorer.score()."""

    breakdown: ScoreBreakdown
    total: float  # weighted_total + endorsement_bonus, clamped 0..100
    endorsement_bonus: float
    analysis: str
    reasons: str
    model_used: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "breakdown": self.breakdown.as_dict(),
            "total": round(self.total, 2),
            "endorsement_bonus": self.endorsement_bonus,
            "analysis": self.analysis,
            "reasons": self.reasons,
            "model_used": self.model_used,
        }


class InvestmentScorer:
    """Six-dimensional weighted scorer using a ModelChain for the two
    qualitative dimensions (TAM, Team). The other four dimensions are
    rule-based or placeholder; the framework is left open so they can
    be promoted to LLM-derived without changing callers.

    Pass an explicit model_chain or accept the default lookup behavior
    (ModelChain() lazily instantiated). If no chain is available the
    scorer falls back to neutral 50.0 for each LLM dim and logs.
    """

    NEUTRAL_FALLBACK = 50.0

    def __init__(self, model_chain=None):
        self.model_chain = model_chain
        if self.model_chain is None:
            logger.debug(
                "InvestmentScorer: no ModelChain provided; LLM dimensions "
                "will return neutral fallback %s", self.NEUTRAL_FALLBACK,
            )

    # ─── Dimension scoring ───────────────────────────────────────────

    def _score_tam(
        self, company_name: str, product_description: str, industry: str
    ) -> float:
        if not product_description:
            return self.NEUTRAL_FALLBACK
        if self.model_chain is None:
            return self.NEUTRAL_FALLBACK

        prompt = (
            f"SCORE TAM for this company on a scale 0-100. Return ONLY a number.\n"
            f"Company: {company_name}\n"
            f"Product: {product_description}\n"
            f"Industry: {industry or 'Unknown'}\n"
            f"Consider: market size potential, CAGR signals, unicorn potential.\n"
            f"Number only:"
        )
        try:
            resp = self.model_chain.complete(
                prompt, system_prompt="Return a single number 0-100.", max_tokens=10
            )
            return _parse_score_number(resp.text)
        except Exception as exc:
            logger.warning("TAM scoring failed, using neutral fallback: %s", exc)
            return self.NEUTRAL_FALLBACK

    def _score_team(
        self, company_name: str, team_context: str = ""
    ) -> float:
        if self.model_chain is None:
            return self.NEUTRAL_FALLBACK

        # Surface the top-tier-institution list so the model can use
        # it as an anchor. Sorted for deterministic prompts (helps
        # caching upstream).
        anchors = ", ".join(sorted(TOP_TIER_INSTITUTIONS))
        prompt = (
            f"SCORE the founding team of {company_name} on a scale 0-100. "
            f"Return ONLY a number.\n"
            f"Consider in priority order:\n"
            f"  - Academic excellence (Top-tier institutions: {anchors}; PhD; Masters)\n"
            f"  - Professional track record (20+ years at PwC/industry-relevant firms)\n"
            f"  - Serial entrepreneurship (prior IPO or M&A exit)\n"
            f"  - Credentials & integrity (CA, CMA, CFA)\n"
            f"Team context:\n{team_context or '(no team context available)'}\n"
            f"Number only:"
        )
        try:
            resp = self.model_chain.complete(
                prompt, system_prompt="Return a single number 0-100.", max_tokens=10
            )
            return _parse_score_number(resp.text)
        except Exception as exc:
            logger.warning("Team scoring failed, using neutral fallback: %s", exc)
            return self.NEUTRAL_FALLBACK

    @staticmethod
    def _score_financial(revenue_growth: Optional[float]) -> float:
        """Map revenue growth % to a 0-100 financial score.

        Same buckets as dealflow:
          >=50% → 80
          >=20% → 50
          < 20% → 20
          None  → neutral 50
        """
        if revenue_growth is None:
            return 50.0
        if revenue_growth >= 50:
            return 80.0
        if revenue_growth >= 20:
            return 50.0
        return 20.0

    # ─── Analysis generation ─────────────────────────────────────────

    def _generate_analysis(
        self,
        company_name: str,
        product_description: str,
        industry: str,
        revenue_growth: Optional[float],
        breakdown: ScoreBreakdown,
    ) -> tuple[str, str]:
        """Return (analysis_paragraph, reasons_bullet_text).

        Without a model_chain this returns plain-static text so the
        caller never has to special-case the no-LLM path.
        """
        if self.model_chain is None:
            return (
                f"Static fallback analysis for {company_name}. "
                "LLM chain unavailable.",
                "Scores derived from rule-based dimensions only — no "
                "LLM-driven narrative.",
            )

        prompt = (
            f"Analyze the deal for {company_name} based on the following context:\n"
            f"Product: {product_description or 'Unknown'}\n"
            f"Industry: {industry or 'Unknown'}\n"
            f"Revenue Growth: {revenue_growth if revenue_growth is not None else 'Unknown'}\n"
            f"TAM Score: {breakdown.tam}\n"
            f"Team Score: {breakdown.team}\n\n"
            "Provide a concise analysis of the deal's potential, then list the key "
            "reasons for the score.\n"
            "Output format strictly as:\n"
            "ANALYSIS:\n<one-paragraph>\n"
            "REASONS:\n<bullet points>"
        )
        try:
            resp = self.model_chain.complete(
                prompt,
                system_prompt="Provide deal analysis and reasons.",
                max_tokens=600,
            )
            return _parse_analysis_reasons(resp.text)
        except Exception as exc:
            logger.warning("Analysis generation failed: %s", exc)
            return ("Analysis generation failed.", str(exc))

    # ─── Public entry ────────────────────────────────────────────────

    def score(
        self,
        company_name: str,
        product_description: str = "",
        industry: str = "",
        revenue_growth: Optional[float] = None,
        team_context: str = "",
        dealradar_endorsed: bool = False,
    ) -> InvestmentResult:
        """Score a single company.

        Endorsement bonus: +20 applied ONCE to the weighted total when
        dealradar_endorsed is True AND the team score is >= 70. This
        replaces dealflow's double-application (team += 20 then bonus
        elsewhere) that effectively counted endorsement +25.
        """
        tam = self._score_tam(company_name, product_description, industry)
        team = self._score_team(company_name, team_context)
        moat = self.NEUTRAL_FALLBACK
        exit_score = self.NEUTRAL_FALLBACK
        industry_score = self.NEUTRAL_FALLBACK
        financial = self._score_financial(revenue_growth)

        breakdown = ScoreBreakdown(
            tam=tam,
            team=team,
            moat=moat,
            exit_score=exit_score,
            industry=industry_score,
            financial=financial,
        )

        endorsement_bonus = 0.0
        if dealradar_endorsed and team >= 70:
            endorsement_bonus = 20.0

        total = breakdown.weighted_total() + endorsement_bonus
        total = max(0.0, min(100.0, total))

        analysis, reasons = self._generate_analysis(
            company_name, product_description, industry, revenue_growth, breakdown
        )

        model_used = None
        if self.model_chain is not None:
            # The chain logs the provider on each call; we record the
            # default for traceability when we don't have a per-call
            # provider on hand.
            try:
                model_used = getattr(
                    self.model_chain, "last_used_model", None
                ) or "model_chain"
            except Exception:
                model_used = "model_chain"

        return InvestmentResult(
            breakdown=breakdown,
            total=total,
            endorsement_bonus=endorsement_bonus,
            analysis=analysis,
            reasons=reasons,
            model_used=model_used,
        )


# ─── Parsing helpers ─────────────────────────────────────────────────


_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _parse_score_number(text: str) -> float:
    """Extract a 0-100 score from possibly-noisy LLM output.

    Accepts: '78', '78\n', 'Score: 78', '78 out of 100', '78.5'.
    Rejects negatives and clamps >100 to 100. Returns 50.0 (neutral)
    when no number is found at all.
    """
    if not text:
        return InvestmentScorer.NEUTRAL_FALLBACK
    m = _NUMBER_RE.search(text)
    if not m:
        return InvestmentScorer.NEUTRAL_FALLBACK
    try:
        n = float(m.group(0))
    except ValueError:
        return InvestmentScorer.NEUTRAL_FALLBACK
    if n < 0:
        return 0.0
    if n > 100:
        return 100.0
    return n


def _parse_analysis_reasons(text: str) -> tuple[str, str]:
    """Split a model response of the form
       'ANALYSIS:\n<...>\nREASONS:\n<...>'
    into (analysis, reasons). Lenient — accepts case variations and
    missing sections.
    """
    if not text:
        return ("", "")
    analysis_match = re.search(
        r"ANALYSIS:\s*(.*?)(?:REASONS:|$)", text, re.IGNORECASE | re.DOTALL
    )
    reasons_match = re.search(
        r"REASONS:\s*(.*)", text, re.IGNORECASE | re.DOTALL
    )
    analysis = (
        analysis_match.group(1).strip()
        if analysis_match
        else "Analysis not parsed."
    )
    reasons = (
        reasons_match.group(1).strip()
        if reasons_match
        else "Reasons not parsed."
    )
    return (analysis, reasons)
