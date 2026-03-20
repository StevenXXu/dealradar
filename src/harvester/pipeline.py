# src/harvester/pipeline.py
"""Harvester pipeline — orchestrates scraping of all VC portfolios."""
import json
import random
import time
from pathlib import Path

from src.harvester.jina_client import JinaClient
from src.harvester.apify_client import ApifyClient
from src.harvester.playwright_scraper import PlaywrightScraper
from src.harvester.extractor import extract_companies_from_html, filter_dead_companies


class HarvesterPipeline:
    """Orchestrates the full harvest: load seeds -> scrape each VC -> extract companies."""

    def __init__(
        self,
        vc_seeds_path: str = "config/vc_seeds.json",
        jina_client: JinaClient | None = None,
        apify_client: ApifyClient | None = None,
        output_path: str = "data/raw_companies.json",
    ):
        self.vc_seeds = self._load_seeds(vc_seeds_path)
        self.jina = jina_client or JinaClient()
        self.apify = apify_client or ApifyClient()
        self.playwright = PlaywrightScraper()
        self.output_path = output_path
        self._all_companies = []

    def _load_seeds(self, path: str) -> list[dict]:
        with open(path) as f:
            return json.load(f)

    def _scrape_vc_portfolio(self, seed: dict) -> list[dict]:
        """Scrape a single VC portfolio page. Try Playwright first (JS-rendered), then Jina+Apify."""
        name = seed["name"]
        url = seed["url"]
        print(f"  Scraping {name} ({url})...", flush=True)

        # Strategy 1: Playwright for JS-rendered pages
        try:
            companies = self.playwright.scrape(url)
            if companies:
                print(f"  Playwright found {len(companies)} companies from {name}", flush=True)
                return companies
        except Exception as e:
            print(f"  Playwright failed for {name}: {e}", flush=True)

        # Strategy 2: Jina Reader + HTML/Markdown extraction
        try:
            html = self.jina.fetch_with_retry(url)
            companies = extract_companies_from_html(html, vc_source=name, base_url=url)
            if companies:
                print(f"  Jina found {len(companies)} companies from {name}", flush=True)
                return companies
        except Exception as e:
            print(f"  Jina failed for {name}: {e}", flush=True)

        # Strategy 3: Apify fallback
        try:
            result = self.apify.scrape(url)
            html = result.get("output", {}).get("text", "")
            companies = extract_companies_from_html(html, vc_source=name, base_url=url)
            if companies:
                print(f"  Apify found {len(companies)} companies from {name}", flush=True)
                return companies
        except Exception as e2:
            print(f"  Apify also failed for {name}: {e2}", flush=True)

        print(f"  No companies found for {name}", flush=True)
        return []

    def run(self) -> list[dict]:
        """Run the full harvest pipeline for all VC seeds."""
        self._all_companies = []

        for seed in self.vc_seeds:
            time.sleep(random.uniform(2, 5))  # Rate limit between VCs
            companies = self._scrape_vc_portfolio(seed)
            self._all_companies.extend(companies)

        # Filter dead companies
        print(f"\nFiltering dead companies ({len(self._all_companies)} total before filter)...", flush=True)
        self._all_companies = filter_dead_companies(self._all_companies, self.jina)

        # Deduplicate by domain
        seen = set()
        unique = []
        for c in self._all_companies:
            if c["domain"] not in seen:
                seen.add(c["domain"])
                unique.append(c)
        self._all_companies = unique

        print(f"\nHarvest complete: {len(self._all_companies)} unique companies", flush=True)
        self._save()
        return self._all_companies

    def _save(self):
        Path(self.output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_path, "w") as f:
            json.dump(self._all_companies, f, indent=2)
        print(f"Saved to {self.output_path}", flush=True)
