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
    html: str, vc_source: str, base_url: str = ""
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


# Generic link texts that show up where a real company name should
# be. When the <a> inner text is one of these, we know the link IS
# the company's external site (so the domain is good) but the link
# text itself is useless as a company name — we need to look at the
# surrounding DOM or derive from the URL instead.
#
# Conservative exact-match set. Adding fuzzy/substring matching here
# is too aggressive — 'Read AI' is a real company. The gatekeeper
# (src/reasoner/gatekeeper.py:GarbageNameFilter) is the safety net
# for anything that still slips through.
_GENERIC_LINK_TEXTS: frozenset[str] = frozenset(
    {
        "website",
        "read more",
        "learn more",
        "view more",
        "see more",
        "show more",
        "visit",
        "visit site",
        "visit website",
        "go to website",
        "home",
        "homepage",
        "about",
        "about us",
        "contact",
        "more info",
        "more information",
        "details",
        "view",
        "view all",
        "click here",
        "here",
        "link",
        "more",
        "->",
        "→",
        "»",
    }
)


def _is_generic_link_text(text: str) -> bool:
    return text.strip().lower() in _GENERIC_LINK_TEXTS


_NAME_FLAVORED_TOKENS: frozenset[str] = frozenset({"name", "title", "brand"})


def _class_signals_company_name(cls) -> bool:
    """True if any class token equals one of the name-flavored words,
    splitting on whitespace/hyphen/underscore. Matches 'company-name'
    and 'portfolio_title' without matching 'filename' or 'subtitle'.
    BeautifulSoup passes a list of class strings here.
    """
    if not cls:
        return False
    if isinstance(cls, (list, tuple)):
        joined = " ".join(cls)
    else:
        joined = str(cls)
    tokens = re.split(r"[\s\-_]+", joined.lower())
    return any(t in _NAME_FLAVORED_TOKENS for t in tokens)


def _find_name_near_link(a_tag, max_levels: int = 3) -> str | None:
    """Walk up to `max_levels` parents looking for a heading or
    'name'/'title' class element that names the company. Common
    portfolio-page pattern:

        <div class="portfolio-item">
          <h3 class="company-name">Acme AI</h3>
          <p>Cross-border treasury</p>
          <a href="https://acme.ai">Website</a>
        </div>

    Returns the first non-empty, non-generic candidate found.
    """
    NAME_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")

    node = a_tag.parent
    for _ in range(max_levels):
        if node is None:
            break

        for h in node.find_all(NAME_TAGS, limit=3):
            candidate = h.get_text(strip=True)
            if candidate and not _is_generic_link_text(candidate) and len(candidate) > 2:
                return candidate[:200]

        # data-* and title attributes on the parent container
        for attr in ("data-name", "data-title", "data-company", "title", "aria-label"):
            value = node.get(attr) if hasattr(node, "get") else None
            if value and not _is_generic_link_text(value) and len(value) > 2:
                return value.strip()[:200]

        # Elements with name/title-flavored classes inside the container.
        # Uses a function matcher rather than a regex because BS4 hands
        # the class attribute as a list of tokens — 'company-name' must
        # split on hyphen before token comparison.
        for el in node.find_all(class_=_class_signals_company_name, limit=3):
            candidate = el.get_text(strip=True)
            if candidate and not _is_generic_link_text(candidate) and len(candidate) > 2:
                return candidate[:200]

        # img alt text inside the same container (logo alt)
        img = node.find("img", alt=True)
        if img and img.get("alt"):
            alt = img["alt"].strip()
            if alt and not _is_generic_link_text(alt) and len(alt) > 2:
                return alt[:200]

        node = node.parent

    return None


def _derive_name_from_url(url: str) -> str | None:
    """Last-resort: turn 'https://www.acme-ai.com/about' into 'Acme Ai'.
    Returns None if the host is in the excluded-domain list (generic
    webmail, social, infra) or yields nothing usable.

    Does NOT go through extract_domain_from_url, which prepends the
    scheme back into its return value — that helper is the wrong
    primitive when we want just the host string.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    host = (parsed.netloc or "").lower()
    if not host:
        return None
    if host.startswith("www."):
        host = host[4:]
    # Reuse the existing exclusion list (operates on the helper's
    # 'scheme://host/' form, so reconstitute it).
    if is_excluded_domain(f"https://{host}/"):
        return None
    base = host.split(".")[0]
    cleaned = re.sub(r"[^a-zA-Z0-9]+", " ", base).strip()
    if len(cleaned) <= 2:
        return None
    return cleaned.title()


def _resolve_company_name(text: str, a_tag, url: str) -> str | None:
    """Decide the company_name for a link.

    Cases that need the DOM/URL fallback:
      - empty link text (e.g. <a><img alt="Acme"/></a>)
      - single-character text ('→', '»' — common portfolio affordances)
      - text in the curated generic-link-text set ('Website', etc.)

    Anything else is treated as a real name and used verbatim. Returns
    None when no usable name can be derived — the caller drops the row.
    """
    text = (text or "").strip()
    needs_fallback = (
        not text
        or len(text) < 2
        or _is_generic_link_text(text)
    )
    if needs_fallback:
        return _find_name_near_link(a_tag) or _derive_name_from_url(url)
    return text[:200]


def _extract_from_soup(
    soup: BeautifulSoup, vc_source: str, base_url: str, seen_domains: set
) -> list[dict[str, Any]]:
    """Extract company links from BeautifulSoup-parsed HTML."""
    companies = []
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        text = a_tag.get_text(strip=True)
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

        name = _resolve_company_name(text, a_tag, href)
        if not name:
            # Generic link text + no DOM hint + URL didn't yield a
            # usable name (excluded domain). Drop rather than emit
            # 'Website' as the company name.
            continue

        seen_domains.add(domain)
        companies.append(
            {
                "company_name": name,
                "domain": href,
                "stage": detect_stage_from_context(a_tag) or "Unknown",
                "vc_source": vc_source,
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    return companies


def _extract_from_markdown(
    text: str, vc_source: str, base_url: str, seen_domains: set
) -> list[dict[str, Any]]:
    """Extract company links from Markdown text [name](url) format.

    Markdown is flat — no surrounding DOM to inspect. If the link text
    is generic ('Website') we can only fall back to a URL-derived
    name, then drop the row if even that fails.
    """
    companies = []
    for match in re.finditer(r"\[(?!!)([^\]]+)\]\((https?://[^)]+)\)", text):
        name = match.group(1).strip()
        url = match.group(2).strip()
        domain = extract_domain_from_url(url)
        if not domain or domain in seen_domains:
            continue
        if is_excluded_domain(domain):
            continue

        if not name or len(name) < 2:
            continue
        if _is_generic_link_text(name):
            derived = _derive_name_from_url(url)
            if not derived:
                continue
            name = derived

        seen_domains.add(domain)
        companies.append(
            {
                "company_name": name[:200],
                "domain": url,
                "stage": "Unknown",
                "vc_source": vc_source,
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            }
        )
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
    """Check if domain should be excluded (social media, Crunchbase, big tech, etc.)."""
    # Major tech/public companies that are not early-stage startups
    major_corporations = {
        # Big Tech
        "google.com",
        "youtube.com",
        "blog.google",
        "play.google",
        "apple.com",
        "icloud.com",
        "microsoft.com",
        "windows.com",
        "azure.com",
        "github.com",
        "amazon.com",
        "aws.amazon.com",
        "alexa.amazon.com",
        "facebook.com",
        "meta.com",
        "instagram.com",
        "whatsapp.com",
        "oculus.com",
        "twitter.com",
        "x.com",
        "linkedin.com",
        "netflix.com",
        "spotify.com",
        "nvidia.com",
        "nvidia.dev",
        "cisco.com",
        "webex.com",
        "salesforce.com",
        "slack.com",
        "tableau.com",
        "adobe.com",
        "omnichannel.com",
        "ibm.com",
        "cloud.ibm.com",
        "oracle.com",
        "intel.com",
        "paypal.com",
        "venmo.com",
        "ebay.com",
        "reddit.com",
        "snap.com",
        "snapchat.com",
        "pinterest.com",
        "tumblr.com",
        "flickr.com",
        "dropbox.com",
        "box.com",
        "yahoo.com",
        "bing.com",
        "baidu.com",
        "qq.com",
        "weibo.com",
        "tencent.com",
        "alibaba.com",
        "alibaba.net",
        "163.com",
        "sina.com.cn",
        "sohu.com",
        "ifeng.com",
        # Major public companies in VC portfolios
        "klarna.com",
        "airbnb.com",
        "airbnb.co.uk",
        "airbnb.eu",
        "uber.com",
        "uber Eats",
        "doordash.com",
        "instacart.com",
        "lyft.com",
        "shopify.com",
        "stripe.com",
        "squareup.com",
        "block.xyz",
        "snowflake.com",
        "snowflake.net",
        "mongodb.com",
        "atlassian.com",
        "atlassian.net",
        "slack.com",
        "zoom.us",
        "datadog.com",
        "crowdstrike.com",
        "zscaler.com",
        "okta.com",
        "cloudflare.com",
        "twilio.com",
        "sendgrid.com",
        "mapbox.com",
        "github.com",
        "gitlab.com",
        "bitbucket.org",
        "stackoverflow.com",
        "stackexchange.com",
        "medium.com",
        "wordpress.com",
        "wix.com",
        "squarespace.com",
        "shopify.com",
        "etsy.com",
        "snap.com",
        # Social / reference
        "twitter.com",
        "linkedin.com",
        "facebook.com",
        "instagram.com",
        "youtube.com",
        "crunchbase.com",
        "pitchbook.com",
        "wikipedia.org",
        "github.com",
        # Job boards / HR
        "indeed.com",
        "linkedin.com",
        "glassdoor.com",
        "getro.com",
        "lever.co",
        "greenhouse.io",
        "workday.com",
        "icims.com",
        "sap.com",
        "workday.com",
        # Navigation / misc noise
        "mail.google.com",
        "drive.google.com",
        "calendar.google.com",
        "chrome.google.com",
        "store.google.com",
        "support.google.com",
        "maps.google.com",
        "adobe.com",
        "stock.adobe.com",
        "teams.microsoft.com",
        "office.microsoft.com",
        "amazon.com",
        "smile.amazon.com",
        "aws.amazon.com",
        "窟.com",  # etc
    }
    excluded = {
        "twitter.com",
        "linkedin.com",
        "facebook.com",
        "instagram.com",
        "youtube.com",
        "crunchbase.com",
        "pitchbook.com",
        "wikipedia.org",
        "github.com",
    }
    netloc = urlparse(domain).netloc.replace("www.", "").lower()
    # Check exact match
    if netloc in excluded or netloc in major_corporations:
        return True
    # Check if domain contains a major corp (e.g. "microsoft.com" in "support.microsoft.com")
    for corp in major_corporations:
        if corp in netloc or netloc in corp:
            return True
    return False


def detect_stage_from_context(a_tag) -> str | None:
    """Attempt to detect funding stage from surrounding context."""
    parent_text = a_tag.parent.get_text() if a_tag.parent else ""
    grandparent_text = (
        a_tag.parent.parent.get_text() if a_tag.parent and a_tag.parent.parent else ""
    )
    combined = parent_text + " " + grandparent_text
    stage_match = re.search(
        r"\b(Seed|Series\s+[A-Z]|Angel|Pre-?Seed|Post-?Seed|Growth|Series\s+[A-Z]\+)\b",
        combined,
        re.I,
    )
    if stage_match:
        stage = stage_match.group(0).strip().title()
        stage = stage.replace("Preseed", "Pre-Seed").replace("Pre Seed", "Pre-Seed")
        stage = stage.replace("Postseed", "Post-Seed").replace("Post Seed", "Post-Seed")
        if stage.lower().startswith("series "):
            stage = "Series " + stage.split()[-1].upper()
        return stage
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
                if any(
                    signal in content_lower
                    for signal in ["acquired by", "ipo'd", "gone public", "shut down"]
                ):
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
                    wait = (2**attempts) + random.uniform(1, 3)
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

    close_connector = connector is None
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

    if close_connector:
        await connector.close()

    return [company for company, is_alive in results if is_alive]
