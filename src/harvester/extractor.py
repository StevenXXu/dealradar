# src/harvester/extractor.py
"""Extract company names and domains from VC portfolio HTML pages."""
import asyncio
import re
import json
import random
import time
import aiohttp
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
    Parse VC portfolio HTML or Markdown and extract company name + domain pairs.

    Args:
        html: Raw HTML or Markdown from Jina Reader
        vc_source: Name of the VC firm
        base_url: Base URL for resolving relative links

    Returns:
        List of dicts: {company_name, domain, stage, vc_source, scraped_at}
    """
    companies = []
    seen_domains = set()

    # Try HTML parsing first (BeautifulSoup)
    soup = BeautifulSoup(html, "lxml")
    html_companies = _extract_from_soup(soup, vc_source, base_url, seen_domains)
    companies.extend(html_companies)

    # Also parse Markdown-style links: [text](url)
    md_companies = _extract_from_markdown(html, vc_source, base_url, seen_domains)
    companies.extend(md_companies)

    return companies


def _extract_from_soup(
    soup: BeautifulSoup,
    vc_source: str,
    base_url: str,
    seen_domains: set
) -> list[dict[str, Any]]:
    """Extract company links from BeautifulSoupparsed HTML."""
    companies = []
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        text = a_tag.get_text(strip=True)
        if not text or len(text) < 2:
            continue
        if not href.startswith("http"):
            if base_url:
                href = urljoin(base_url, href)
            else:
                continue
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


def _extract_from_markdown(
    text: str,
    vc_source: str,
    base_url: str,
    seen_domains: set
) -> list[dict[str, Any]]:
    """Extract company links from Markdown text [name](url) format."""
    companies = []
    # Match markdown links: [text](url) but exclude image links ![...](...)
    for match in re.finditer(r'\[(?!!)([^\]]+)\]\((https?://[^)]+)\)', text):
        name = match.group(1).strip()
        url = match.group(2).strip()
        if not name or len(name) < 2:
            continue
        domain = extract_domain_from_url(url)
        if not domain or domain in seen_domains:
            continue
        if is_excluded_domain(domain):
            continue
        seen_domains.add(domain)
        companies.append({
            "company_name": name[:200],
            "domain": url,
            "stage": "Unknown",
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
    Retries on rate-limit (429) with backoff; companies that can't be fetched
    are kept (marked as alive — we can't prove they're dead).
    """
    import time
    alive = []
    for company in companies:
        attempts = 0
        max_attempts = 3
        last_error = None
        while attempts < max_attempts:
            try:
                content = jina_client.fetch(company["domain"], timeout=15)
                content_lower = content.lower()
                if any(signal in content_lower for signal in ["acquired by", "ipo'd", "gone public", "shut down"]):
                    print(f"  [FILTERED] {company['company_name']} — acquired/IPO'd")
                    break  # Dead, don't add
                if "404" in content_lower and "not found" in content_lower:
                    print(f"  [FILTERED] {company['company_name']} — 404")
                    break  # Dead, don't add
                alive.append(company)
                break  # Alive, add and move on
            except Exception as e:
                last_error = e
                attempts += 1
                if attempts < max_attempts:
                    wait = (2 ** attempts) + random.uniform(1, 3)
                    time.sleep(wait)
        if attempts == max_attempts:
            # Couldn't confirm dead — keep as alive
            alive.append(company)
    return alive


async def async_filter_dead_companies(
    companies: list[dict],
    connector: aiohttp.TCPConnector | None = None,
) -> list[dict]:
    """
    Filter dead companies using async HTTP HEAD requests.
    Uses aiohttp for concurrent checks — ~10-20s for 500 companies vs 12+ minutes sequential.
    Fail-open: network errors or timeouts are treated as alive (keep the company).
    """
    if not companies:
        return []

    connector = connector or aiohttp.TCPConnector(limit=50)
    timeout = aiohttp.ClientTimeout(total=5)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        async def check_company(company: dict) -> tuple[dict, bool]:
            try:
                async with session.head(company["domain"]) as resp:
                    if resp.status == 404:
                        return company, False
                    return company, True
            except Exception:
                # Fail-open: any error (DNS, timeout, connection refused) = treat as alive
                return company, True

        tasks = [check_company(c) for c in companies]
        results = await asyncio.gather(*tasks)

    return [company for company, is_alive in results if is_alive]
