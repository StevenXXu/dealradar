"""Jina-based detail-page scraper for Faction B VC sites."""
import re
from urllib.parse import urlparse
from src.harvester.jina_client import JinaClient

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
            print(f"  [WARN] Jina detail fetch failed for {detail_url}: {e}")
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
        """Extract company name (from first heading) and domain (first non-excluded URL) from Jina markdown."""
        # Extract first ATX heading as company name
        heading_match = re.search(r'^#+\s*(.+)$', text, re.MULTILINE)
        company_name = heading_match.group(1).strip()[:200] if heading_match else None
        # Match markdown links [text](url) but not image links ![...](...)
        for match in re.finditer(r'\[(?!!)([^\]]+)\]\((https?://[^)]+)\)', text):
            url = match.group(2).strip()
            domain = self._extract_domain(url)
            if not domain:
                continue
            if self._is_excluded(domain):
                continue
            return {"company_name": company_name, "domain": domain}
        return None

    def _extract_domain(self, url: str) -> str | None:
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            if domain.startswith("www."):
                domain = domain[4:]
            return f"{parsed.scheme}://{domain}/"
        except Exception:
            return None

    def _is_excluded(self, domain: str) -> bool:
        # Strip trailing slash so netloc comparison works correctly
        netloc = urlparse(domain.rstrip("/")).netloc.replace("www.", "")
        return netloc in EXCLUDED_DOMAINS
