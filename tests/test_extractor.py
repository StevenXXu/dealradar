# tests/test_extractor.py
import pytest
from aioresponses import aioresponses
from src.harvester.extractor import extract_companies_from_html, filter_dead_companies, async_filter_dead_companies

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


@pytest.mark.asyncio
async def test_async_filter_removes_404_domains():
    companies = [
        {"company_name": "Alive Co", "domain": "https://alive.co"},
        {"company_name": "Dead Co", "domain": "https://dead.co"},
    ]
    with aioresponses() as mocked:
        mocked.head("https://alive.co", status=200)
        mocked.head("https://dead.co", status=404)
        result = await async_filter_dead_companies(companies)
    names = [c["company_name"] for c in result]
    assert "Alive Co" in names
    assert "Dead Co" not in names

@pytest.mark.asyncio
async def test_async_filter_keeps_all_on_network_error():
    companies = [{"company_name": "Failing Co", "domain": "https://failing.co"}]
    with aioresponses() as mocked:
        mocked.head("https://failing.co", exception=Exception("DNS failure"))
        result = await async_filter_dead_companies(companies)
    assert len(result) == 1
    assert result[0]["company_name"] == "Failing Co"

@pytest.mark.asyncio
async def test_async_filter_empty_input():
    result = await async_filter_dead_companies([])
    assert result == []
