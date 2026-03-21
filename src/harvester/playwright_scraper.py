# src/harvester/playwright_scraper.py
"""Playwright-based scraper for JavaScript-rendered VC portfolio pages.

Auto-detects site structure and routes to the optimal extraction strategy:
  - Faction A: Direct external links (Skip Capital, Antler, Carthona style)
  - Faction B: Internal /portfolio/{slug} detail pages (Square Peg, AirTree, Five V style)
  - Faction A GiantLeap: Rich text with sector+company name in link text
  - Pagination: _page=N query params (Antler, Blackbird)
"""
import random
import time
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

from playwright.sync_api import sync_playwright


# Thread pool for concurrent detail-page fetching
_MAX_WORKERS = 8


class PlaywrightScraper:
    """
    Uses Playwright to scrape JS-rendered portfolio pages.
    Handles the common case where VC portfolio data is loaded via API/JS.
    Auto-detects site structure and applies the best strategy.
    """

    def __init__(self, headless: bool = True, timeout: int = 30000):
        self.headless = headless
        self.timeout = timeout

    def scrape(self, url: str) -> list[dict]:
        """
        Scrape a VC portfolio page using Playwright.
        Returns list of {company_name, domain, vc_source} dicts.
        """
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            page = browser.new_page()

            # Block heavy resources to speed up
            page.route("**/*.woff2", lambda route: route.abort())
            page.route("**/*.font", lambda route: route.abort())
            page.route("**/*.png", lambda route: route.abort())
            page.route("**/*.jpg", lambda route: route.abort())
            page.route("**/*.avif", lambda route: route.abort())

            page.goto(url, timeout=self.timeout, wait_until="domcontentloaded")
            page.wait_for_timeout(5000)

            # Scroll to trigger lazy loading
            for _ in range(5):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(2000)

            current_url = page.url
            vc_source = self._vc_name_from_url(current_url)

            # ── Strategy dispatch ─────────────────────────────────────────────
            # 1. /all-companies pattern (Main Sequence)
            if "/all-companies" in current_url or "/all-companies" in url:
                companies = self._scrape_msv_style(browser, page, url)

            # 2. Auto-detect Faction B: internal portfolio detail pages
            #    (Square Peg, AirTree, Five V, Archangels, Carthona, etc.)
            elif self._detect_faction_b(page):
                companies = self._scrape_faction_b(browser, page, current_url, vc_source)

            # 3. GiantLeap: rich text with sector + company name in link text
            elif "giantleap.com.au" in current_url.lower():
                companies = self._scrape_giantleap_style(page, current_url, vc_source)

            # 4. Fallback: generic external-link extraction
            else:
                companies = self._scrape_faction_a(page, current_url, vc_source)

            browser.close()
            return companies

    # ── Faction detection ───────────────────────────────────────────────────

    def _detect_faction_b(self, page) -> bool:
        """Return True if page has >10 internal portfolio detail links."""
        links = page.query_selector_all("a[href]")
        detail_patterns = ("/portfolio/", "/companies/", "/company/", "/investment/")
        count = 0
        for link in links:
            href = link.get_attribute("href") or ""
            if any(p in href.lower() for p in detail_patterns) and not href.startswith("http"):
                count += 1
        return count > 10

    # ── Faction A: Direct external links ────────────────────────────────────

    def _scrape_faction_a(self, page, base_url: str, vc_source: str) -> list[dict]:
        """
        Faction A: VC lists companies with direct external links.
        Also handles pagination (_page=N) if present.
        """
        print(f"  Using Faction A strategy (direct external links)...", flush=True)
        parsed_a = urlparse(base_url)
        vc_brand = parsed_a.netloc.lower().replace("www.", "").split(".")[0]
        companies = []
        seen_names = set()

        companies, seen_names = self._collect_companies_from_page(
            page, base_url, vc_source, seen_names, vc_brand
        )

        # Handle pagination
        pagination_urls = self._collect_pagination_urls(page, base_url)
        if pagination_urls:
            print(f"  Found {len(pagination_urls)} pagination pages, scraping all...", flush=True)
            for page_url in sorted(pagination_urls):
                try:
                    new_page = page.browser.new_page()
                    new_page.goto(page_url, timeout=self.timeout, wait_until="domcontentloaded")
                    new_page.wait_for_timeout(3000)
                    for _ in range(3):
                        new_page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        new_page.wait_for_timeout(1500)
                    companies, seen_names = self._collect_companies_from_page(
                        new_page, page_url, vc_source, seen_names, vc_brand
                    )
                    new_page.close()
                except Exception as e:
                    print(f"  Pagination page failed: {e}", flush=True)
                    try:
                        new_page.close()
                    except Exception:
                        pass

        print(f"  Faction A found {len(companies)} companies", flush=True)
        return companies

    # ── Faction B: Internal detail page traversal ───────────────────────────

    def _scrape_faction_b(
        self, browser, page, base_url: str, vc_source: str
    ) -> list[dict]:
        """
        Faction B: VC uses internal /portfolio/{slug} detail pages.
        Visit each detail page to extract company name + VISIT WEBSITE link.
        Sequential (Playwright sync is not thread-safe for concurrent page access).
        """
        print("  Using Faction B strategy (internal detail page traversal)...", flush=True)
        # Extract root domain for filtering (just the brand name, not TLD)
        parsed_base = urlparse(base_url)
        vc_domain_root = parsed_base.netloc.lower().replace("www.", "")  # "airtree.vc"
        # Only use the brand part (first segment) to avoid filtering all .com/.vc/.au domains
        vc_brand = vc_domain_root.split(".")[0]  # "airtree"

        # Collect all internal detail-page URLs
        links = page.query_selector_all("a[href]")
        slug_map = {}  # slug -> detail_page_url

        for link in links:
            href = link.get_attribute("href") or ""
            if not any(
                p in href.lower()
                for p in ("/portfolio/", "/companies/", "/company/", "/investment/")
            ):
                continue
            if href.startswith("http"):
                continue
            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)
            path_parts = [p for p in parsed.path.split("/") if p]
            if path_parts:
                slug = path_parts[-1].split("?")[0].split("#")[0]
                if slug and slug not in slug_map:
                    slug_map[slug] = full_url

        print(f"  Found {len(slug_map)} detail pages, scraping each sequentially...", flush=True)

        companies = []
        seen_domains = set()

        for slug, detail_url in slug_map.items():
            # Use a fresh page for each detail URL
            detail_page = browser.new_page()
            try:
                detail_page.goto(detail_url, timeout=self.timeout, wait_until="domcontentloaded")
                detail_page.wait_for_timeout(3000)

                # Extract company name from h1, or fall back to slug
                name = None
                try:
                    h1 = detail_page.query_selector("h1")
                    if h1:
                        name = h1.inner_text().strip().split("\n")[0]
                except Exception:
                    pass
                if not name:
                    name = self._name_from_slug(slug)

                # Find VISIT WEBSITE / VIEW WEBSITE external link
                domain = None
                detail_links = detail_page.query_selector_all("a[href]")
                for dlink in detail_links:
                    text = dlink.inner_text().strip()
                    text_lower = text.lower()
                    href = dlink.get_attribute("href") or ""
                    if ("visit website" in text_lower or "view website" in text_lower or "view site" in text_lower) and \
                            href.startswith("http") and vc_brand not in href.lower():
                        domain = href
                        break

                # Fallback: find first external link that's not a jobs/social link
                if not domain:
                    for dlink in detail_links:
                        href = dlink.get_attribute("href") or ""
                        text = dlink.inner_text().strip()
                        if href.startswith("http") and vc_brand not in href.lower():
                            skip_patterns = (
                                "linkedin.com", "twitter.com", "jobs.", "angel.co",
                                "crunchbase", "getro.com", "glassdoor.com",
                                "indeed.com", "seek.com", "jora.com",
                            )
                            if any(ex in href.lower() for ex in skip_patterns):
                                continue
                            domain = href
                            break

                detail_page.close()

                if name and domain:
                    parsed_d = urlparse(domain)
                    netloc = parsed_d.netloc.lower().replace("www.", "")
                    if netloc not in seen_domains:
                        seen_domains.add(netloc)
                        companies.append({
                            "company_name": name[:200],
                            "domain": domain,
                            "vc_source": vc_source,
                            "scraped_at": datetime.now(timezone.utc).isoformat(),
                        })
                        print(f"    {name} -> {domain}", flush=True)
            except Exception as e:
                try:
                    detail_page.close()
                except Exception:
                    pass
                print(f"    Failed to fetch {detail_url}: {e}", flush=True)

            time.sleep(random.uniform(0.5, 1.5))

        print(f"  Faction B found {len(companies)} companies", flush=True)
        return companies

    # ── GiantLeap: Rich text with sector + company name ─────────────────────

    def _scrape_giantleap_style(
        self, page, base_url: str, vc_source: str
    ) -> list[dict]:
        """
        GiantLeap and similar VCs: link text contains sector tags + company name.
        Format: 'SECTOR\\nCompany Name\\nDescription'  or  'SECTOR\\nCompany Name'
        """
        print("  Using GiantLeap strategy (rich text extraction)...", flush=True)
        parsed_g = urlparse(base_url)
        vc_domain = parsed_g.netloc.lower().replace("www.", "")
        vc_brand = vc_domain.split(".")[0]
        companies = []
        seen_names = set()

        links = page.query_selector_all("a[href]")
        for link in links:
            href = link.get_attribute("href") or ""
            full_text = link.inner_text().strip()
            if not href.startswith("http"):
                href = urljoin(base_url, href)

            # Skip own VC domain (check netloc contains VC domain part)
            try:
                parsed_h = urlparse(href)
                netloc = parsed_h.netloc.lower()
                if vc_brand in netloc:
                    continue
            except Exception:
                pass

            if not self._is_external_company_link(href, full_text):
                continue
            lines = [l.strip() for l in full_text.split("\n") if l.strip()]

            # GiantLeap format: SECTOR\nCompany Name\n[Description]
            # The actual company name is the first line AFTER the sector tag
            # or the last meaningful line that looks like a company name
            name = None
            for line in lines:
                if self._is_likely_company_name(line):
                    name = line
                    break

            if not name:
                # Fallback: try URL reverse naming
                name = self._name_from_url(href)

            if not name or name.lower() in seen_names:
                continue
            if not self._is_likely_company_name(name):
                continue

            seen_names.add(name.lower())
            companies.append({
                "company_name": name,
                "domain": href,
                "vc_source": vc_source,
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            })

        print(f"  GiantLeap found {len(companies)} companies", flush=True)
        return companies

    # ── Main Sequence (all-companies) ───────────────────────────────────────

    def _scrape_msv_style(self, browser, page, base_url: str) -> list[dict]:
        """Extract companies from pages like mseq.vc/all-companies."""
        links = page.query_selector_all("a[href]")
        seen_slugs = set()
        slug_map = {}

        for link in links:
            href = link.get_attribute("href") or ""
            text = link.inner_text().strip()
            if "/msv-company-page/" in href and text:
                slug = href.split("/msv-company-page/")[-1].split("?")[0]
                name = text.split("\n")[0].strip()
                if " " in slug or any(c in slug for c in ["?", "#"]):
                    continue
                if name and len(name) > 1 and len(name) < 100 and slug not in seen_slugs:
                    seen_slugs.add(slug)
                    slug_map[slug] = (name, urljoin("https://www.mseq.vc", href))

        companies = []
        for slug, (name, page_url) in slug_map.items():
            domain = self._get_msv_company_domain(browser, page_url, slug)
            companies.append({
                "company_name": name,
                "domain": domain or f"https://{slug}.com",
                "vc_source": "Main Sequence",
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            })
            time.sleep(random.uniform(0.5, 1.5))

        return companies

    def _get_msv_company_domain(
        self, browser, company_page_url: str, slug: str
    ) -> str | None:
        """Visit a Main Sequence company page and extract the external website URL."""
        page = browser.new_page()
        page.goto(company_page_url, timeout=self.timeout, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        links = page.query_selector_all("a[href]")
        for link in links:
            href = link.get_attribute("href") or ""
            text = link.inner_text().strip().lower()
            if ("view website" in text or "view site" in text) and \
                    href.startswith("http") and "mseq" not in href.lower():
                page.close()
                return href

        excluded = {
            "linkedin.com/company/mainsequence", "medium.com/main-sequence",
            "jobs.mseq.vc", "twitter.com", "youtube.com", "facebook.com",
            "instagram.com", "github.com", "crunchbase.com", "pitchbook.com",
            "wikipedia.org",
        }
        for link in links:
            href = link.get_attribute("href") or ""
            text = link.inner_text().strip()
            if href.startswith("http") and "mseq" not in href.lower():
                if any(ex in href.lower() for ex in excluded):
                    continue
                if text and len(text) > 3:
                    page.close()
                    return href

        page.close()
        return None

    # ── Shared helpers ──────────────────────────────────────────────────────

    def _collect_pagination_urls(self, page, base_url: str) -> set[str]:
        """Collect all pagination page URLs (_page=N pattern)."""
        pagination_links = page.query_selector_all("a[href]")
        page_urls = set()
        for link in pagination_links:
            href = link.get_attribute("href") or ""
            if "_page=" in href and "portfolio" in href.lower():
                if not href.startswith("http"):
                    href = urljoin(base_url, href)
                page_urls.add(href)
        return page_urls

    def _collect_companies_from_page(
        self, page, base_url: str, vc_source: str, seen_names: set,
        vc_brand: str = None
    ) -> tuple:
        """Collect company links from a single Faction A page."""
        companies = []
        links = page.query_selector_all("a[href]")
        for link in links:
            href = link.get_attribute("href") or ""
            text = link.inner_text().strip()
            if not href.startswith("http"):
                href = urljoin(base_url, href)
            if not self._is_external_company_link(href, text, vc_brand):
                continue

            name = text.split("\n")[0].strip()
            name = self._clean_company_name(name)
            if not name:
                # Fallback: derive name from URL domain
                name = self._name_from_url(href)
            if not name or len(name) < 2 or len(name) > 80:
                continue
            if not self._is_likely_company_name(name):
                continue
            if name.lower() in seen_names:
                continue

            seen_names.add(name.lower())
            companies.append({
                "company_name": name,
                "domain": href,
                "vc_source": vc_source,
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            })
        return companies, seen_names

    def _is_likely_company_name(self, text: str) -> bool:
        skip = {
            "portfolio", "investment", "about", "team", "careers", "contact",
            "founder", "founders", "stories", "blog", "news", "events",
            "community", "programs", "search", "get investment", "for investors",
            "join", "home", "homepage", "back", "next", "learn more",
            "read more", "view all", "our portfolio", "why founders",
            "the flock", "meet our", "want to join", "researcher",
            "overview", "what we do", "conclusion", "introduction",
            "back to top", "get directions", "site by", "reset filters",
            "open in a new tab", "view website", "view site",
            "privacy policy", "terms of use", "disclaimer", "legal notice",
            "about us", "approach", "insights", "jobs", "connect",
            "lp portal", "investor portal", "investor log", "foundation",
            "acquired", "ipo", "acquired by",
            "people", "community", "perspectives", "close",
            "fintech", "edtech", "healthtech", "cleantech", "cybersecurity",
            "ai & robotics", "hr tech", "legal tech", "real estate",
            "marketplace", "construction", "manufacturing", "consumer",
            "open source", "it operations", "marketing", "gaming",
            "volunteer management", "end of life management", "enterprise",
            "saas", "b2b", "b2c", "deep tech", "web3", "blockchain",
        }
        text_lower = text.lower().strip()
        if len(text) < 3 or len(text) > 80:
            return False
        if any(s in text_lower for s in skip):
            return False
        if text.isupper():
            return False
        if not any(c.isupper() for c in text):
            return False
        return True

    def _is_external_company_link(self, href: str, text: str, vc_brand: str = None) -> bool:
        excluded = {
            "linkedin.com", "twitter.com", "youtube.com", "facebook.com",
            "instagram.com", "github.com", "crunchbase.com", "pitchbook.com",
            "wikipedia.org", "google.com", "googletagmanager.com",
            "mseq.vc", "blackbird.vc", "squarepeg.vc", "airtree.vc",
            "folklore.vc", "sprintajax.com", "ten13.com", "alto.capital",
            "rampersand.com", "basecapital.com.au", "candour.vc",
            "skipcapital.com", "fivevcapital.com", "antler.co",
            "archangel.vc", "carthonacapital.com",
            "blacksheepcapital.com.au", "investible.com",
            # Blockchain / crypto
            "solana.com", "sui.io", "polkadot.com", "fantom.foundation",
            "avax.network", "algorand.com", "binance.com", "near.org",
            "filecoin.io", "thegraph.com", "0x.org", "zilliqa.com",
            "loopring.org", "thorchain.org", "oasisprotocol.org",
            "skale.network", "ankr.com", "tezos.com", "nkn.org",
            "cere.network", "agoric.com", "aergo.io", "singularitynet.io",
            "minaprotocol.com", "peaq.network", "holyheld.com",
            "nabit.org", "razor.network", "bluzelle.com", "bnb.com",
            # Noise domains
            "webqem.com", "mailchi.mp", "getro.com", "fundpanel.io",
            "investorvision.intralinks.com", "dynamo.dynamosoftware.com",
            "share.hsforms.com", "goo.gl", "maps.app.goo.gl",
            "fund", "vc-portal", "lp-portal",
        }
        if not href.startswith("http"):
            return False
        href_lower = href.lower()
        if any(ex in href_lower for ex in excluded):
            return False
        # Exclude VC's own domain by checking netloc contains VC brand part
        if vc_brand:
            try:
                parsed = urlparse(href)
                netloc = parsed.netloc.lower()
                if vc_brand in netloc:
                    return False
            except Exception:
                pass
        # Accept if text is meaningful, OR if URL looks like a company domain
        if text and len(text) > 2:
            return True
        # Accept domain-only links (logo images often have empty alt text)
        if "." in href:
            return True
        return False

    def _clean_company_name(self, text: str) -> str:
        name = text.split("\n")[0].strip()
        for suffix in [" - Wikipedia", " | Crunchbase", " - LinkedIn"]:
            if name.endswith(suffix):
                name = name[: -len(suffix)].strip()
        if len(name) < 2:
            return ""
        return name[:200]

    def _name_from_url(self, url: str) -> str:
        """Reverse naming: extract company name from domain URL."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            if domain.startswith("www."):
                domain = domain[4:]
            name = re.sub(r"\.(com|io|ai|co|tech|health|life|vc|au|uk|com\.au|org|net)", "", domain)
            return name.capitalize()
        except Exception:
            return ""

    def _name_from_slug(self, slug: str) -> str:
        """Derive company name from URL slug: 'ai-hay' -> 'Ai Hay'."""
        if not slug:
            return ""
        # Replace common separators and capitalize
        name = slug.replace("-", " ").replace("_", " ").replace("/", " ")
        return name.title()

    def _vc_name_from_url(self, url: str) -> str:
        try:
            parsed = urlparse(url)
            netloc = parsed.netloc.lower()
            parts = netloc.replace("www.", "").split(".")
            if len(parts) >= 2:
                return parts[-2].replace("-", " ").title()
            return netloc
        except Exception:
            return "Unknown VC"
