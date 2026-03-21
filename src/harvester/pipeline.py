# src/harvester/pipeline.py
"""Harvester pipeline — orchestrates scraping of all VC portfolios."""
import asyncio
import json
import random
import re
import time
from pathlib import Path

from src.harvester.jina_client import JinaClient
from src.harvester.apify_client import ApifyClient
from src.harvester.jina_detail import JinaDetailScraper
from src.harvester.playwright_scraper import PlaywrightScraper
from src.harvester.extractor import extract_companies_from_html, async_filter_dead_companies


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

    def _scrape_faction_b(self, vc_entry: dict) -> list[dict]:
        """Faction B: Jina portfolio → extract slugs → JinaDetailScraper for each detail page."""
        vc_name = vc_entry["name"]
        portfolio_url = vc_entry["url"]
        slug = vc_entry.get("slug", vc_name.lower().replace(" ", "-"))

        print(f"  [{vc_name}] Faction B: fetching portfolio via Jina...", flush=True)
        try:
            portfolio_markdown = self.jina.fetch_with_retry(portfolio_url)
        except Exception as e:
            print(f"  [WARN] Jina portfolio fetch failed for {vc_name}: {e}", flush=True)
            return []

        # Extract slugs from markdown links like /company/{slug} or /portfolio/{slug}
        slugs = re.findall(r'/(?:company|portfolio)/([a-z0-9-]+)', portfolio_markdown)
        slugs = list(set(slugs))

        if not slugs:
            print(f"  [WARN] No slugs found in {vc_name} portfolio page", flush=True)
            return []

        # Build detail URLs based on VC
        if "investible" in slug.lower():
            detail_urls = [f"https://www.investible.com/company/{s}" for s in slugs]
        elif "archangel" in slug.lower():
            detail_urls = [f"https://www.archangel.vc/portfolio/{s}" for s in slugs]
        else:
            detail_urls = [f"{portfolio_url.rstrip('/')}/{s}" for s in slugs]

        print(f"  [{vc_name}] Faction B: fetching {len(detail_urls)} detail pages via JinaDetailScraper...", flush=True)
        scraper = JinaDetailScraper(self.jina)
        companies = scraper.fetch_details_parallel(detail_urls)

        for company in companies:
            company["vc_source"] = vc_name
            company["source_url"] = portfolio_url

        return companies

    def _scrape_vc(self, vc_entry: dict) -> list[dict]:
        """Route to Faction B handler or Faction A (Playwright-first) handler."""
        faction = vc_entry.get("faction_hint", "a")
        if faction == "b":
            return self._scrape_faction_b(vc_entry)
        return self._scrape_vc_portfolio(vc_entry)

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
        vc_results = []

        for seed in self.vc_seeds:
            time.sleep(random.uniform(2, 5))  # Rate limit between VCs
            companies = self._scrape_vc(seed)
            vc_results.append(companies)
            self._all_companies.extend(companies)

            # Sanity check: warn if VC returned fewer than 3 companies
            if len(companies) < 3:
                print(f"  [WARN] {seed['name']} returned only {len(companies)} companies — below minimum threshold (3)", flush=True)

        # Sanity check: warn if >50% of VCs returned 0 companies
        failed_vcs = sum(1 for c in vc_results if len(c) == 0)
        total_vcs = len(vc_results)
        if total_vcs > 0 and failed_vcs > total_vcs / 2:
            print(f"  [CRITICAL] {failed_vcs}/{total_vcs} VCs returned 0 companies — pipeline may need attention", flush=True)

        # Filter dead companies
        print(f"\nFiltering dead companies ({len(self._all_companies)} total before filter)...", flush=True)
        self._all_companies = asyncio.run(async_filter_dead_companies(self._all_companies))

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
