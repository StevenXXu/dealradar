from src.harvester.jina_detail import JinaDetailScraper

SAMPLE_MARKDOWN = """#农业科技公司
[Website](https://agridigital.com.au)
[LinkedIn](https://linkedin.com/company/agridigital)
"""

def test_extracts_website_link_from_markdown():
    scraper = JinaDetailScraper()
    result = scraper._extract_from_markdown(SAMPLE_MARKDOWN)
    assert result["domain"] == "https://agridigital.com.au/"
    assert result["company_name"] == "农业科技公司"

def test_excludes_social_media_links():
    scraper = JinaDetailScraper()
    result = scraper._extract_from_markdown(SAMPLE_MARKDOWN)
    assert "linkedin.com" not in result["domain"]
