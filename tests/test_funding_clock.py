# tests/test_funding_clock.py
from datetime import date
from src.reasoner.funding_clock import FundingClock, estimate_monthly_burn

def test_estimate_monthly_burn():
    # B2B SaaS median ~$15K/month per employee
    burn = estimate_monthly_burn(headcount=20, sector="B2B SaaS")
    assert 250_000 < burn < 400_000  # 20 * 15K * 1.3

def test_estimate_monthly_burn_unknown_sector():
    burn = estimate_monthly_burn(headcount=10, sector="Unknown")
    assert burn > 0  # Uses fallback rate

def test_days_remaining_calculation():
    clock = FundingClock(last_raise_amount=10_000_000, days_since_raise=400)
    burn = estimate_monthly_burn(headcount=15, sector="B2B SaaS")
    days_remaining = clock.calculate_days_remaining(burn)
    assert days_remaining >= 0

def test_funding_clock_prediction():
    clock = FundingClock(last_raise_amount=12_000_000, days_since_raise=400)
    burn = estimate_monthly_burn(headcount=15, sector="B2B SaaS")
    predicted_date = clock.predict_funding_date(burn)
    assert predicted_date is not None
    assert predicted_date > date.today()
