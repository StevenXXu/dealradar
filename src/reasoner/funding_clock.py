# src/reasoner/funding_clock.py
"""Funding clock: burn rate estimation and next raise date prediction."""
from datetime import date, timedelta


# Industry average monthly burn per employee (USD), with 30% overhead
SECTOR_BURN_RATES = {
    "B2B SaaS": 15_000,
    "B2C SaaS": 12_000,
    "FinTech": 18_000,
    "HealthTech": 20_000,
    "EdTech": 10_000,
    "PropTech": 16_000,
    "AI/ML": 22_000,
    "Biotech": 25_000,
    "Hardware": 20_000,
    "Marketplace": 14_000,
    "Crypto/Blockchain": 20_000,
    "Gaming": 15_000,
    "Unknown": 15_000,
}

OVERHEAD_MULTIPLIER = 1.30


def estimate_monthly_burn(headcount: int | None, sector: str | None) -> float:
    """Estimate monthly burn = headcount x industry_avg x 1.3 overhead."""
    rate = SECTOR_BURN_RATES.get(sector or "Unknown", SECTOR_BURN_RATES["Unknown"])
    employees = headcount if headcount else 10
    return employees * rate * OVERHEAD_MULTIPLIER


def estimate_headcount_from_text(text: str) -> int | None:
    """Attempt to extract headcount from company text."""
    import re
    patterns = [
        r"(\d+)\s*(?:employees|people|team members?|staff)",
        r"team of (\d+)",
        r"we're?\s*(\d+)\s*(?:people|folks)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return int(match.group(1))
    return None


class FundingClock:
    """
    Calculate when a company will likely need their next funding round.
    Days Remaining = (Last Round Amount / Monthly Burn) - Days Since Last Round
    """

    def __init__(self, last_raise_amount: float, days_since_raise: int):
        self.last_raise_amount = last_raise_amount
        self.days_since_raise = days_since_raise

    def calculate_days_remaining(self, monthly_burn: float) -> float:
        """Returns approximate days until funding runway depletes."""
        if monthly_burn <= 0:
            return 0
        total_runway_days = self.last_raise_amount / (monthly_burn / 30)
        return max(0, total_runway_days - self.days_since_raise)

    def predict_funding_date(self, monthly_burn: float) -> date | None:
        """Returns predicted date of next funding round."""
        if self.last_raise_amount <= 0:
            return None
        days_remaining = self.calculate_days_remaining(monthly_burn)
        return date.today() + timedelta(days=int(days_remaining))
