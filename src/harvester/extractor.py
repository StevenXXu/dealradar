# src/harvester/extractor.py
"""Extract company names and domains from VC portfolio HTML pages."""
import re
import json
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from src.harvester.jina_client import JinaClient
from src.harvester.apify_client import ApifyClient


def extract_companies_from_html(
    html: str,
    vc_source: str,
    base_url: str = ""
) -> list[dict[str, Any]]:
    """
    Parse VC portfolio HTML and extract company name + domain pairs.

    Args:
        html: Raw HTML/markdown from Jina Reader
        vc_source: Name of the VC firm
        base_url: Base URL for resolving relative links

    Returns:
        List of dicts: {company_name, domain, stage, vc_source, scraped_at}
    """
    soup = BeautifulSoup(html, "lxml")
    companies = []
    seen_domains = set()

    # Find all links that look like company links (external domains)
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        text = a_tag.get_text(strip=True)

        # Skip empty links or navigation
        if not text or len(text) < 2:
            continue

        # Resolve relative URLs
        if not href.startswith("http"):
            if base_url:
                href = urljoin(base_url, href)
            else:
                continue

        # Extract domain
        domain = extract_domain_from_url(href)
        if not domain or domain in seen_domains:
            continue
        if is_excluded_domain(domain):
            continue

        seen_domains.add(domain)
        companies.append({
            "company_name": text[:200],
            "domain": href,
            "stage": detect_stage_from_context(a_tag) or "Unknown",
            "vc_source": vc_source,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        })

    return companies


def extract_domain_from_url(url: str) -> str | None:
    """Extract and validate domain from URL."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if not domain:
            return None
        if domain.startswith("www."):
            domain = domain[4:]
        return f"{parsed.scheme}://{domain}/"
    except Exception:
        return None


def is_excluded_domain(domain: str) -> bool:
    """Check if domain should be excluded (social media, Crunchbase, etc.)."""
    excluded = {
        "twitter.com", "linkedin.com", "facebook.com", "instagram.com",
        "youtube.com", "crunchbase.com", "pitchbook.com",
        "wikipedia.org", "github.com",
    }
    netloc = urlparse(domain).netloc.replace("www.", "")
    return netloc in excluded


def detect_stage_from_context(a_tag) -> str | None:
    """Attempt to detect funding stage from surrounding context."""
    parent_text = a_tag.parent.get_text() if a_tag.parent else ""
    grandparent_text = a_tag.parent.parent.get_text() if a_tag.parent and a_tag.parent.parent else ""
    combined = parent_text + " " + grandparent_text
    stage_match = re.search(r"\b(Seed|Series\s+[A-Z]|Angel|Pre-Seed|Post-Seed)\b", combined, re.I)
    if stage_match:
        return stage_match.group(0).strip()
    return None


def filter_dead_companies(companies: list[dict], jina_client: JinaClient) -> list[dict]:
    """
    Filter out dead companies (404, acquired, IPO'd) by checking their domains.
    Companies that cannot be fetched (dead domains, network errors) are skipped —
    they may be defunct sites that no longer respond.
    """
    alive = []
    for company in companies:
        try:
            content = jina_client.fetch(company["domain"], timeout=10)
            content_lower = content.lower()
            if any(signal in content_lower for signal in ["acquired by", "ipo'd", "gone public", "shut down"]):
                print(f"  [FILTERED] {company['company_name']} — acquired/IPO'd")
                continue
            if "404" in content_lower and "not found" in content_lower:
                print(f"  [FILTERED] {company['company_name']} — 404")
                continue
            alive.append(company)
        except Exception as e:
            # Cannot fetch — domain may be dead. Skip it.
            print(f"  [FILTERED] {company['company_name']} — un-fetchable ({e})")
            continue
    return alive
