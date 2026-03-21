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
        """Fetch multiple detail pages concurrently (sequential for now, aiohttp later)."""
        results = []
        for url in detail_urls:
            result = self.fetch_detail(url)
            if result:
                results.append(result)
        return results

    def _extract_from_markdown(self, text: str) -> dict | None:
        """Extract company name (from first non-excluded link text) and domain from Jina markdown."""
        # Match markdown links [text](url) but not image links ![...](...)
        for match in re.finditer(r'\[(?!!)([^\]]+)\]\((https?://[^)]+)\)', text):
            link_text = match.group(1).strip()
            url = match.group(2).strip()
            domain = self._extract_domain(url)
            if not domain:
                continue
            if self._is_excluded(domain):
                continue
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
