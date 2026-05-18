# tests/test_extractor.py
import pytest
from aioresponses import aioresponses
from src.harvester.extractor import (
    extract_companies_from_html,
    filter_dead_companies,
    async_filter_dead_companies,
)

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


# ─── Garbage-link-text resolution ────────────────────────────────────
# Regression suite for the "Website" / "Read More" / "→" extractor bug.
# Real-data audit found 14.8% of harvested companies had link text as
# company_name. The extractor now walks the DOM for a real name when
# the link text is generic, falling back to URL-derived names.


class TestGenericLinkTextResolution:
    def test_h3_sibling_is_used_when_link_text_is_website(self):
        html = """
        <div class="portfolio-item">
          <h3>Acme AI</h3>
          <p>LLM infra at scale.</p>
          <a href="https://acme.ai">Website</a>
        </div>
        """
        companies = extract_companies_from_html(html, vc_source="TestVC")
        assert len(companies) == 1
        assert companies[0]["company_name"] == "Acme AI"
        assert companies[0]["domain"] == "https://acme.ai"

    def test_h2_in_same_container_used(self):
        html = """
        <article>
          <h2>Stables Money</h2>
          <a href="https://stables.money">Read more</a>
        </article>
        """
        companies = extract_companies_from_html(html, vc_source="TestVC")
        assert companies[0]["company_name"] == "Stables Money"

    def test_class_name_pattern_is_picked_up(self):
        html = """
        <div class="company-card">
          <span class="company-name">PlasmaLeap</span>
          <a href="https://plasmaleap.com">Visit</a>
        </div>
        """
        companies = extract_companies_from_html(html, vc_source="TestVC")
        assert companies[0]["company_name"] == "PlasmaLeap"

    def test_data_attribute_on_parent_is_used(self):
        html = """
        <div data-company="Botsync">
          <a href="https://botsync.com">→</a>
        </div>
        """
        companies = extract_companies_from_html(html, vc_source="TestVC")
        assert companies[0]["company_name"] == "Botsync"

    def test_image_alt_text_fallback(self):
        html = """
        <div>
          <img src="logo.png" alt="Eureka Robotics">
          <a href="https://eurekarobotics.com">Visit website</a>
        </div>
        """
        companies = extract_companies_from_html(html, vc_source="TestVC")
        assert companies[0]["company_name"] == "Eureka Robotics"

    def test_url_derived_name_when_no_dom_context(self):
        # Flat link with no DOM hints — name must come from the URL
        html = '<a href="https://canvas.co">Website</a>'
        companies = extract_companies_from_html(html, vc_source="TestVC")
        assert len(companies) == 1
        assert companies[0]["company_name"] == "Canvas"

    def test_url_derived_handles_hyphens_and_subdomains(self):
        html = '<a href="https://www.acme-ai.com/about">Read more</a>'
        companies = extract_companies_from_html(html, vc_source="TestVC")
        assert companies[0]["company_name"] == "Acme Ai"

    def test_excluded_domain_drops_row_entirely(self):
        # Generic link text + excluded domain → no real name available.
        # Drop the row rather than persist a garbage 'Website' entry.
        html = '<a href="https://linkedin.com/in/foo">Website</a>'
        companies = extract_companies_from_html(html, vc_source="TestVC")
        assert companies == []

    def test_normal_link_text_unaffected(self):
        # The fix must not regress the happy path — when link text is
        # already a real name, that name is preserved verbatim.
        html = '<a href="https://canvas.co">Canvas</a>'
        companies = extract_companies_from_html(html, vc_source="TestVC")
        assert companies[0]["company_name"] == "Canvas"

    def test_case_insensitive_generic_match(self):
        # 'WEBSITE' / 'Website' / 'website' all treated as generic
        for variant in ("WEBSITE", "Website", "website", "  Website  "):
            html = (
                f'<div><h3>Acme</h3><a href="https://acme.ai">{variant}</a></div>'
            )
            companies = extract_companies_from_html(html, vc_source="TestVC")
            assert companies[0]["company_name"] == "Acme", (
                f"variant {variant!r} not treated as generic"
            )

    def test_arrow_and_chevron_are_generic(self):
        # Common UI affordances on portfolio cards
        html = """
        <div>
          <h3>Galatek</h3>
          <a href="https://galatek.com">→</a>
        </div>
        """
        companies = extract_companies_from_html(html, vc_source="TestVC")
        assert companies[0]["company_name"] == "Galatek"


# ─── Markdown extraction fixes ────────────────────────────────────────


class TestMarkdownGenericResolution:
    def test_markdown_generic_text_falls_back_to_url(self):
        # Common Jina Reader output for portfolio pages
        md = "[Website](https://acme.ai) — AI infra"
        companies = extract_companies_from_html(md, vc_source="TestVC")
        assert companies[0]["company_name"] == "Acme"

    def test_markdown_generic_text_excluded_domain_drops(self):
        md = "[Read More](https://linkedin.com/in/foo)"
        companies = extract_companies_from_html(md, vc_source="TestVC")
        assert companies == []

    def test_markdown_normal_text_unaffected(self):
        md = "[Canvas](https://canvas.co)"
        companies = extract_companies_from_html(md, vc_source="TestVC")
        assert companies[0]["company_name"] == "Canvas"


# ─── Real-portfolio-shape fixture ─────────────────────────────────────


class TestRealPortfolioShape:
    """Approximates the structure observed on actual VC portfolio
    pages where every company card has a uniform 'Website' link.
    Catches the case where the bug originally surfaced — entire
    portfolios coming back as repeated 'Website' rows with different
    domains."""

    def test_uniform_website_links_yield_real_names(self):
        html = """
        <ul class="portfolio">
          <li class="portfolio-item">
            <h3>Acme AI</h3>
            <p>LLM infra.</p>
            <a href="https://acme.ai">Website</a>
          </li>
          <li class="portfolio-item">
            <h3>Stables Money</h3>
            <p>Treasury platform.</p>
            <a href="https://stables.money">Website</a>
          </li>
          <li class="portfolio-item">
            <h3>PlasmaLeap</h3>
            <p>Green ammonia reactors.</p>
            <a href="https://plasmaleap.com">Website</a>
          </li>
        </ul>
        """
        companies = extract_companies_from_html(html, vc_source="TestVC")
        names = [c["company_name"] for c in companies]
        assert "Acme AI" in names
        assert "Stables Money" in names
        assert "PlasmaLeap" in names
        assert "Website" not in names
