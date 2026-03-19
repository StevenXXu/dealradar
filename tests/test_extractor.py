# tests/test_extractor.py
from src.harvester.extractor import extract_companies_from_html, filter_dead_companies

SAMPLE_HTML = """
<html>
<body>
<a href="https://canvas.co">Canvas</a>
<a href="https://deadcompany.com">Dead Company</a>
<a href="https://acquired.com">Acquired Corp</a>
</body>
</html>
"""

def test_extract_companies_from_html_basic():
    companies = extract_companies_from_html(SAMPLE_HTML, vc_source="TestVC")
    assert len(companies) == 3
    names = [c["company_name"] for c in companies]
    assert "Canvas" in names

def test_extract_companies_from_html_schema():
    companies = extract_companies_from_html(SAMPLE_HTML, vc_source="TestVC")
    for c in companies:
        assert "company_name" in c
        assert "domain" in c
        assert "vc_source" in c
        assert "scraped_at" in c
        assert c["vc_source"] == "TestVC"
