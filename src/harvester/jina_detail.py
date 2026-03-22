"""Jina-based detail-page scraper for Faction B VC sites."""
import logging
import re
from urllib.parse import urlparse
from src.harvester.jina_client import JinaClient

logger = logging.getLogger(__name__)

EXCLUDED_DOMAINS = {
    "twitter.com", "x.com", "linkedin.com", "instagram.com",
    "facebook.com", "youtube.com", "crunchbase.com", "pitchbook.com",
    "wikipedia.org", "github.com",
    # Job boards — these appear on VC detail pages but aren't company sites
    "greenhouse.io", "greenhouse.tech", "lever.co", "workday.com",
    "ashbyhq.com", "bamboohr.com",
    # VC/investment platform domains that appear on their own detail pages
    "investible.com", "archangel.vc",
}

class JinaDetailScraper:
    """Fetch VC detail pages via Jina and extract company domain + name."""

    def __init__(self, jina_client: JinaClient | None = None):
        self.jina = jina_client or JinaClient()

    def fetch_detail(self, detail_url: str) -> dict | None:
        """Fetch a single detail page, extract company domain and name."""
        try:
            markdown = self.jina.fetch_with_retry(detail_url)
            return self._extract_from_markdown(markdown)
        except Exception as e:
            logger.warning("Jina detail fetch failed for %s: %s", detail_url, e)
            return None

    def fetch_details_parallel(self, detail_urls: list[str]) -> list[dict]:
        """Fetch multiple detail pages sequentially with a delay to avoid rate limits."""
        import time
        results = []
        for i, url in enumerate(detail_urls):
            result = self.fetch_detail(url)
            if result:
                results.append(result)
            # Small delay between requests to avoid 429 from Jina
            if i < len(detail_urls) - 1:
                time.sleep(1.0)
        return results

    def _extract_from_markdown(self, text: str) -> dict | None:
        """Extract company name and domain from Jina markdown.

        Strategy:
        1. First pass: look for [Website] or [Visit Website] links — highest signal
        2. Second pass: any non-excluded external link
        """
        all_links: list[tuple[str, str]] = []  # (link_text, url)

        for match in re.finditer(r'\[(?!!)([^\]]+)\]\((https?://[^)]+)\)', text):
            link_text = match.group(1).strip()
            url = match.group(2).strip()
            domain = self._extract_domain(url)
            if not domain:
                continue
            if self._is_excluded(domain):
                continue
            all_links.append((link_text, domain))

        # Pass 1: [Website] or [Visit Website] links — best signal
        for link_text, domain in all_links:
            text_lower = link_text.lower()
            if "website" in text_lower or text_lower in ("visit", "visit site", "view site"):
                return {"company_name": link_text, "domain": domain}

        # Pass 2: first valid external link
        if all_links:
            link_text, domain = all_links[0]
            return {"company_name": link_text, "domain": domain}

        return None

    def _strip_www(self, netloc: str) -> str:
        """Strip leading www. from a netloc (host) string."""
        return netloc.lower().replace("www.", "")

    def _extract_domain(self, url: str) -> str | None:
        try:
            parsed = urlparse(url)
            netloc = self._strip_www(parsed.netloc)
            return f"{parsed.scheme}://{netloc}/"
        except Exception:
            return None

    def _is_excluded(self, domain: str) -> bool:
        # Strip trailing slash so netloc comparison works correctly
        netloc = urlparse(domain.rstrip("/")).netloc
        return self._strip_www(netloc) in EXCLUDED_DOMAINS
