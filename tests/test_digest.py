# tests/test_digest.py
from src.commander.digest import WeeklyDigest, format_top_companies

def test_format_top_companies():
    companies = [
        {"company_name": "A Company", "signal_score": 90, "domain": "https://a.com", "tags": ["Unicorn"]},
        {"company_name": "B Company", "signal_score": 85, "domain": "https://b.com", "tags": ["Pre-IPO Watch"]},
    ]
    formatted = format_top_companies(companies)
    assert "A Company" in formatted
    assert "90" in formatted
    assert "B Company" in formatted

def test_weekly_digest_filters_by_score():
    digest = WeeklyDigest()
    companies = [
        {"company_name": "Hot", "signal_score": 85, "domain": "https://hot.com", "tags": []},
        {"company_name": "Cold", "signal_score": 5, "domain": "https://cold.com", "tags": []},
    ]
    top5 = digest.get_top_companies(companies, top_n=5)
    # top_n=5 means get top 5 companies; with 2 companies returns both sorted by score
    assert len(top5) == 2
    assert top5[0]["company_name"] == "Hot"  # 85 is higher than 5
    assert top5[1]["company_name"] == "Cold"

def test_weekly_digest_ranks_by_score():
    digest = WeeklyDigest()
    companies = [
        {"company_name": "Score60", "signal_score": 60, "domain": "https://s60.com", "tags": []},
        {"company_name": "Score90", "signal_score": 90, "domain": "https://s90.com", "tags": []},
        {"company_name": "Score75", "signal_score": 75, "domain": "https://s75.com", "tags": []},
    ]
    top5 = digest.get_top_companies(companies, top_n=5)
    assert top5[0]["company_name"] == "Score90"
    assert top5[1]["company_name"] == "Score75"
    assert top5[2]["company_name"] == "Score60"
