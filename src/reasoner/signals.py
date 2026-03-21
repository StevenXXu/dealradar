# src/reasoner/signals.py
"""Signal detection rules and scoring (mutually exclusive — highest wins)."""
from dataclasses import dataclass
from enum import IntEnum


class SignalScore(IntEnum):
    CFO_HIRE = 40
    LAST_RAISE_10_20M_15MOS = 30
    LAST_RAISE_18_PLUS = 30
    MULTI_LANG_APAC = 20
    SERIES_C_PLUS = 15
    AUDIT_SOC2 = 15


@dataclass
class SignalResult:
    score: int
    primary_signal: str
    tags: list[str]


class SignalDetector:
    """
    Signal detection with mutually exclusive scoring.
    Only the HIGHEST matching condition applies — no stacking.
    Rules evaluated top-to-bottom.
    """

    SYSTEM_PROMPT = """You are a deal intelligence analyst. Analyze the following company text and extract signals.
Return a JSON object with these fields ONLY (no other text):
{
  "has_cfo_hire": true/false,
  "has_multilang_apac": true/false,
  "has_series_c_plus": true/false,
  "has_audit_signals": true/false,
  "has_supply_chain_robotics": true/false,
  "valuation_over_1b": true/false,
  "last_raise_amount_usd": number or null,
  "months_since_raise": number or null,
  "last_raise_date": "string or null",
  "sector": "string"
}
Be precise. Only set a field to true if there is clear evidence."""

    def __init__(self, model_chain=None):
        self.model_chain = model_chain

    def calculate_score(
        self,
        has_cfo_hire: bool,
        last_raise_amount: int | None,
        months_since_raise: int | None,
        has_multilang: bool,
        has_series_c_plus: bool,
        has_audit_signals: bool,
    ) -> int:
        """Return the signal score (mutually exclusive — highest condition only)."""
        if has_cfo_hire:
            return SignalScore.CFO_HIRE

        if last_raise_amount and months_since_raise is not None:
            if 10_000_000 <= last_raise_amount <= 20_000_000 and months_since_raise >= 15:
                return SignalScore.LAST_RAISE_10_20M_15MOS

        if months_since_raise is not None and months_since_raise >= 18:
            return SignalScore.LAST_RAISE_18_PLUS

        if has_multilang:
            return SignalScore.MULTI_LANG_APAC

        if has_series_c_plus:
            return SignalScore.SERIES_C_PLUS

        if has_audit_signals:
            return SignalScore.AUDIT_SOC2

        return 0

    def extract_tags(
        self,
        has_cfo_hire: bool,
        last_raise_amount: int | None,
        months_since_raise: int | None,
        has_multilang: bool,
        has_series_c_plus: bool,
        has_audit_signals: bool,
        valuation_over_1b: bool,
        robotics_supply_chain: bool,
    ) -> list[str]:
        """Extract all applicable tags (not mutually exclusive — can have multiple)."""
        tags = []

        if valuation_over_1b or (last_raise_amount and last_raise_amount >= 100_000_000):
            tags.append("Unicorn")

        if has_series_c_plus and (has_cfo_hire or has_audit_signals):
            tags.append("Pre-IPO Watch")

        if has_multilang:
            tags.append("Cross-Border Target")

        if last_raise_amount and months_since_raise:
            if 10_000_000 <= last_raise_amount <= 20_000_000 and months_since_raise >= 15:
                tags.append("Funding Urgency High")

        if robotics_supply_chain:
            tags.append("Venture Nexus")

        return tags

    def analyze_text(self, text: str, model_chain) -> dict:
        """Use AI to extract signal flags from raw text."""
        truncated = self._truncate_text(text, max_chars=4000)

        response = model_chain.complete(
            prompt=truncated,
            system_prompt=self.SYSTEM_PROMPT,
            max_tokens=500,
        )

        import json
        try:
            text_response = response.text.strip()
            if text_response.startswith("```"):
                text_response = "\n".join(text_response.split("\n")[1:])
            if text_response.endswith("```"):
                text_response = text_response[:-3]
            return json.loads(text_response)
        except json.JSONDecodeError:
            return {"error": "Failed to parse AI response"}

    def _truncate_text(self, text: str, max_chars: int = 4000) -> str:
        """Hard truncate to max_chars for token control."""
        return text[:max_chars] if len(text) > max_chars else text
