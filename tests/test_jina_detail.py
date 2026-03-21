from src.harvester.jina_detail import JinaDetailScraper

SAMPLE_MARKDOWN = """#农业科技公司
[Website](https://agridigital.com.au)
[LinkedIn](https://linkedin.com/company/agridigital)
"""

def test_extracts_website_link_from_markdown():
    scraper = JinaDetailScraper()
    result = scraper._extract_from_markdown(SAMPLE_MARKDOWN)
    assert result["domain"] == "https://agridigital.com.au/"
    assert result["company_name"] == "Website"

def test_excludes_social_media_links():
    scraper = JinaDetailScraper()
    result = scraper._extract_from_markdown(SAMPLE_MARKDOWN)
    assert "linkedin.com" not in result["domain"]
    assert result["domain"] == "https://agridigital.com.au/"
    assert result["company_name"] == "Website"

def test_empty_markdown_returns_none():
    scraper = JinaDetailScraper()
    result = scraper._extract_from_markdown("")
    assert result is None

def test_social_only_markdown_returns_none():
    scraper = JinaDetailScraper()
    markdown = """[LinkedIn](https://linkedin.com/company/agridigital)
[Twitter](https://twitter.com/agridigital)"""
    result = scraper._extract_from_markdown(markdown)
    assert result is None
