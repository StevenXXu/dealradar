# src/harvester/pipeline.py
"""Harvester pipeline — orchestrates scraping of all VC portfolios."""
import asyncio
import json
import random
import re
import time
from pathlib import Path
import requests

from src.harvester.jina_client import JinaClient
from src.harvester.apify_client import ApifyClient
from src.harvester.jina_detail import JinaDetailScraper
from src.harvester.playwright_scraper import PlaywrightScraper
from src.harvester.extractor import extract_companies_from_html, async_filter_dead_companies
from src.harvester import state as state_module
from src.harvester.state import load_state, mark_completed, mark_failed, append_and_dedupe

# Module-level probe circuit breaker — reset on each pipeline run
_probe_count = 0
MAX_PROBES_PER_RUN = 10

def _should_probe() -> bool:
    """Circuit breaker: returns True if probes remaining under limit."""
    global _probe_count
    return _probe_count < MAX_PROBES_PER_RUN

def _increment_probe() -> None:
    """Increment probe counter. Call after each AI probe fires."""
    global _probe_count
    _probe_count += 1

def _reset_probe_counter() -> None:
    """Reset probe counter — call at start of each pipeline run."""
    global _probe_count
    _probe_count = 0

def _validate_detail_url(url: str | None, timeout: float = 5.0) -> bool:
    """
    Validate a detail URL by doing a HEAD request.
    Returns True if URL returns 2xx, False if 4xx/5xx.
    Fails open: any network error (DNS, timeout, connection refused) returns True
    (allow caching to proceed — network flakiness is not a pattern failure).
    """
    if not url:
        return True  # no URL to validate — skip
    try:
        resp = requests.head(url, timeout=timeout, allow_redirects=True)
        return resp.status_code < 400
    except Exception:
        return True  # fail open

def _derive_template_from_regex(portfolio_url: str, slug_regex: str) -> str:
    """
    Derive detail_url_template from portfolio URL + slug_regex.
    Algorithm (spec-aligned):
      1. Strip the last path segment from portfolio_url → base
         e.g. "https://www.investible.com/portfolio" → "https://www.investible.com"
      2. Extract first alternation branch from slug_regex as path_prefix
         e.g. r"/(?:company|portfolio)/([a-z0-9-]+)" → "company"
      3. Return base + "/" + path_prefix + "/{slug}"
    """
    from urllib.parse import urlparse
    import re
    parsed = urlparse(portfolio_url)
    path_segments = [s for s in parsed.path.split("/") if s]
    if path_segments:
        base_path = "/".join(path_segments[:-1])
        if base_path:
            base = f"{parsed.scheme}://{parsed.netloc}/{base_path}"
        else:
            base = f"{parsed.scheme}://{parsed.netloc}"
    else:
        base = f"{parsed.scheme}://{parsed.netloc}"
    match = re.search(r'\(\?\:([^)]+)\)', slug_regex)
    if match:
        branches = match.group(1).split("|")
        path_prefix = branches[0]
    else:
        m = re.match(r'/([a-zA-Z0-9_-]+)/\(', slug_regex)
        path_prefix = m.group(1) if m else "company"
    return f"{base}/{path_prefix}/{{slug}}"


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

    def _scrape_faction_b(
        self,
        vc_entry: dict,
        slug_regex: str | None = None,
        detail_url_template: str | None = None,
    ) -> list[dict]:
        """Faction B: Jina portfolio → extract slugs → JinaDetailScraper for each detail page."""
        from src.harvester.state import get_vc_pattern, cache_vc_pattern

        vc_name = vc_entry["name"]
        portfolio_url = vc_entry["url"]
        slug = vc_entry.get("slug", vc_name.lower().replace(" ", "-"))
        base_url = "/".join(portfolio_url.split("/")[:3])

        # 1. Check for cached (non-expired) pattern
        cached = get_vc_pattern(slug)
        if cached:
            slug_regex = cached["slug_regex"]
            detail_url_template = cached["detail_url_template"]
            used_cached = True
        else:
            used_cached = False

        # 2. Determine slug_regex
        if not slug_regex:
            slug_regex = vc_entry.get("slug_regex", r"/(?:company|portfolio)/([a-z0-9-]+)")

        # 3. Determine detail_url_template from all sources (parameter > cached > vc_entry)
        template_absent = False
        if not detail_url_template:
            if cached:
                detail_url_template = cached["detail_url_template"]
            elif vc_entry.get("detail_url_template"):
                detail_url_template = vc_entry["detail_url_template"]
            else:
                template_absent = True

        print(f"  [{vc_name}] Faction B: fetching portfolio via Jina...", flush=True)
        try:
            portfolio_markdown = self.jina.fetch_with_retry(portfolio_url)
        except Exception as e:
            print(f"  [WARN] Jina portfolio fetch failed for {vc_name}: {e}", flush=True)
            return []

        slugs = re.findall(slug_regex, portfolio_markdown)
        # Filter out slugs that are clearly domain names or known corporations
        known_corps = {
            "google", "apple", "microsoft", "amazon", "facebook", "meta", "nvidia",
            "intel", "cisco", "oracle", "ibm", "salesforce", "adobe", "netflix",
            "spotify", "slack", "paypal", "ebay", "uber", "airbnb", "linkedin",
            "twitter", "github", "youtube", "instagram", "reddit", "snap",
            "microsoft", "apple", "nvidia",
        }
        slugs = [s for s in slugs if s.lower() not in known_corps and "." not in s]
        slugs = list(set(slugs))

        # 4. If <3 slugs OR template absent (and no cached), try AI probe
        probe_triggered = False
        should_probe = (len(slugs) < 3 or template_absent) and not used_cached and _should_probe()

        if should_probe:
            _increment_probe()
            print(f"  [{vc_name}] Default pattern found only {len(slugs)} slugs (template={'absent' if template_absent else 'present'}) — running AI probe ({_probe_count}/{MAX_PROBES_PER_RUN})...", flush=True)
            try:
                from src.harvester.probe import probe_vc_structure, ProbeFailed
                probe_result = probe_vc_structure(
                    portfolio_markdown=portfolio_markdown,
                    portfolio_url=portfolio_url,
                    base_url=base_url,
                )
                probe_triggered = True
                slug_regex = probe_result["slug_regex"]
                detail_url_template = probe_result["detail_url_template"]
                confidence = probe_result.get("confidence", "medium")
                num_links = probe_result.get("num_links_found", 0)
                print(f"  [{vc_name}] AI probe found {num_links} links, confidence={confidence}", flush=True)

                first_slug = slugs[0] if slugs else None
                first_detail_url = detail_url_template.format(slug=first_slug) if first_slug else None
                validation_ok = _validate_detail_url(first_detail_url)

                if not validation_ok:
                    print(f"  [WARN] AI probe detail URL {first_detail_url} returned 404/5xx — NOT caching pattern", flush=True)
                    probe_triggered = False
                elif confidence == "low":
                    print(f"  [WARN] AI probe confidence=low, not caching pattern", flush=True)
                    probe_triggered = False
                else:
                    if confidence == "medium":
                        print(f"  [INFO] Caching medium-confidence pattern for {vc_name}", flush=True)
                    cache_vc_pattern(slug, {
                        "slug_regex": slug_regex,
                        "detail_url_template": detail_url_template,
                        "confidence": confidence,
                    })
                    slugs = re.findall(slug_regex, portfolio_markdown)
                    slugs = list(set(slugs))
                    # If re-extraction found fewer than probe reported, use sample_slugs from probe
                    if len(slugs) < num_links and probe_result.get("sample_slugs"):
                        slugs = probe_result["sample_slugs"]
            except ProbeFailed as pf:
                print(f"  [WARN] AI probe failed for {vc_name}: {pf}", flush=True)
                probe_triggered = False

        if not should_probe and not used_cached and _probe_count >= MAX_PROBES_PER_RUN:
            print(f"  [WARN] Circuit breaker open — skipping AI probe for {vc_name}", flush=True)

        if len(slugs) < 3:
            print(f"  [WARN] {vc_name} returned only {len(slugs)} companies — marking as failed", flush=True)
            mark_failed(slug)
            return []

        # 5. If template still absent at this point, derive it
        if not detail_url_template:
            detail_url_template = _derive_template_from_regex(portfolio_url, slug_regex)

        # 6. Build detail URLs and scrape
        detail_urls = [detail_url_template.format(slug=s) for s in slugs]
        print(f"  [{vc_name}] Faction B: fetching {len(detail_urls)} detail pages via JinaDetailScraper...", flush=True)
        scraper = JinaDetailScraper(self.jina)
        companies = scraper.fetch_details_parallel(detail_urls)

        for company in companies:
            company["vc_source"] = vc_name
            company["source_url"] = portfolio_url

        # 7. Cache successful pattern (only first time — when default worked and not from AI probe)
        if not used_cached and not probe_triggered and slugs:
            try:
                cache_vc_pattern(slug, {
                    "slug_regex": slug_regex,
                    "detail_url_template": detail_url_template,
                    "confidence": "high",
                })
            except Exception:
                pass

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

    def run(self, force_restart: bool = False) -> list[dict]:
        """Run the full harvest pipeline for all VC seeds."""
        _reset_probe_counter()  # reset circuit breaker at start of each run
        if force_restart and state_module.STATE_FILE.exists():
            state_module.STATE_FILE.unlink()

        self._all_companies = []
        vc_results = []
        completed_vcs, failed_vcs, _ = load_state()

        for seed in self.vc_seeds:
            time.sleep(random.uniform(2, 5))  # Rate limit between VCs
            slug = seed.get("slug", seed["name"].lower().replace(" ", "-"))

            # Skip already-completed VCs (but NOT failed VCs — those retry on every run)
            if slug in completed_vcs:
                print(f"  [{seed['name']}] SKIPPED — already completed successfully", flush=True)
                continue

            if slug in failed_vcs:
                print(f"  [{seed['name']}] RETRY — previously returned <3 companies", flush=True)

            companies = self._scrape_vc(seed)
            vc_results.append(companies)
            self._all_companies.extend(companies)

            # Mark completed and persist incrementally
            if len(companies) >= 3:
                mark_completed(slug)
                append_and_dedupe(companies, self.output_path)
            else:
                # Soft failure — mark as failed so it's retried on next run
                # unless --force-restart is used
                mark_failed(slug)
                print(f"  [WARN] {seed['name']} returned only {len(companies)} companies — marked as failed, will retry on next run", flush=True)

        # Filter dead companies
        print(f"\nFiltering dead companies ({len(self._all_companies)} total before filter)...", flush=True)
        self._all_companies = asyncio.run(async_filter_dead_companies(self._all_companies))

        # Final dedupe pass
        seen = set()
        unique = []
        for c in self._all_companies:
            if c["domain"] not in seen:
                seen.add(c["domain"])
                unique.append(c)
        self._all_companies = unique

        print(f"\nHarvest complete: {len(self._all_companies)} unique companies", flush=True)
        return self._all_companies

    def _save(self):
        Path(self.output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_path, "w") as f:
            json.dump(self._all_companies, f, indent=2)
        print(f"Saved to {self.output_path}", flush=True)
