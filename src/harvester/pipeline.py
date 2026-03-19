# src/harvester/pipeline.py
"""Harvester pipeline — orchestrates scraping of all VC portfolios."""
import json
import random
import time
from pathlib import Path

from src.harvester.jina_client import JinaClient
from src.harvester.apify_client import ApifyClient
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
        self.output_path = output_path
        self._all_companies = []

    def _load_seeds(self, path: str) -> list[dict]:
        with open(path) as f:
            return json.load(f)

    def _scrape_vc_portfolio(self, seed: dict) -> list[dict]:
        """Scrape a single VC portfolio page. Try Jina first, Apify on failure."""
        name = seed["name"]
        url = seed["url"]
        print(f"  Scraping {name} ({url})...")

        try:
            html = self.jina.fetch_with_retry(url)
            companies = extract_companies_from_html(html, vc_source=name, base_url=url)
        except Exception as e:
            print(f"  Jina failed for {name}, falling back to Apify: {e}")
            try:
                result = self.apify.scrape(url)
                html = result.get("output", {}).get("text", "")
                companies = extract_companies_from_html(html, vc_source=name, base_url=url)
            except Exception as e2:
                print(f"  Apify also failed for {name}: {e2}")
                return []

        print(f"  Found {len(companies)} companies from {name}")
        return companies

    def run(self) -> list[dict]:
        """Run the full harvest pipeline for all VC seeds."""
        self._all_companies = []

        for seed in self.vc_seeds:
            time.sleep(random.uniform(2, 5))  # Rate limit between VCs
            companies = self._scrape_vc_portfolio(seed)
            self._all_companies.extend(companies)

        # Filter dead companies
        print(f"\nFiltering dead companies ({len(self._all_companies)} total before filter)...")
        self._all_companies = filter_dead_companies(self._all_companies, self.jina)

        # Deduplicate by domain
        seen = set()
        unique = []
        for c in self._all_companies:
            if c["domain"] not in seen:
                seen.add(c["domain"])
                unique.append(c)
        self._all_companies = unique

        print(f"\nHarvest complete: {len(self._all_companies)} unique companies")
        self._save()
        return self._all_companies

    def _save(self):
        Path(self.output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_path, "w") as f:
            json.dump(self._all_companies, f, indent=2)
        print(f"Saved to {self.output_path}")
