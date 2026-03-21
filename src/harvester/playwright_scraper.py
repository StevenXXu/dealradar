# src/harvester/playwright_scraper.py
"""Playwright-based scraper for JavaScript-rendered VC portfolio pages."""
import random
import time
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

from playwright.sync_api import sync_playwright


class PlaywrightScraper:
    """
    Uses Playwright to scrape JS-rendered portfolio pages.
    Handles the common case where VC portfolio data is loaded via API/JS.
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

            # Strategy 1: /all-companies pattern (e.g. Main Sequence)
            if "/all-companies" in current_url or "/all-companies" in url:
                companies = self._scrape_msv_style(browser, page, url)
            # Strategy 2: Blackbird /portfolio/{slug} pattern — internal page links + VISIT WEBSITE
            elif "blackbird.vc" in current_url.lower() and "/portfolio" in current_url:
                companies = self._scrape_blackbird_style(browser, page, url)
            else:
                # Fallback: generic heading + link extraction
                companies = self._scrape_generic(page, url)

            browser.close()
            return companies

    def _scrape_msv_style(self, browser, page, base_url: str) -> list[dict]:
        """Extract companies from pages like mseq.vc/all-companies. Reuses the given browser."""
        links = page.query_selector_all("a[href]")
        seen_slugs = set()
        slug_map = {}  # slug -> (name, company_page_url)

        for link in links:
            href = link.get_attribute("href") or ""
            text = link.inner_text().strip()
            if "/msv-company-page/" in href and text:
                slug = href.split("/msv-company-page/")[-1].split("?")[0]
                name = text.split("\n")[0].strip()
                # Skip if slug looks malformed (has description appended)
                if " " in slug or any(c in slug for c in ["?", "#"]):
                    continue
                if name and len(name) > 1 and len(name) < 100 and slug not in seen_slugs:
                    seen_slugs.add(slug)
                    slug_map[slug] = (name, urljoin("https://www.mseq.vc", href))

        # Visit each company page to get the actual domain (reuses the browser)
        companies = []
        for slug, (name, page_url) in slug_map.items():
            domain = self._get_company_domain_from_page(browser, page_url, slug)
            companies.append({
                "company_name": name,
                "domain": domain or f"https://{slug}.com",
                "vc_source": "Main Sequence",
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            })
            time.sleep(random.uniform(0.5, 1.5))

        return companies

    def _scrape_blackbird_style(self, browser, page, base_url: str) -> list[dict]:
        """
        Extract companies from Blackbird portfolio pages.
        Blackbird uses /portfolio/{slug} internal pages with VISIT WEBSITE links.
        """
        print("  Using Blackbird strategy (internal page traversal)...", flush=True)
        companies = []
        seen_domains = set()
        seen_slugs = set()

        # Find all /portfolio/{slug} links on the main page
        all_links = page.query_selector_all("a[href]")
        slug_map = {}  # slug -> (name_placeholder, page_url)

        for link in all_links:
            href = link.get_attribute("href") or ""
            text = link.inner_text().strip()
            # Match /portfolio/{slug} but not /portfolio itself
            if "/portfolio/" in href:
                slug = href.split("/portfolio/")[-1].split("?")[0].split("#")[0]
                if slug and slug not in seen_slugs:
                    seen_slugs.add(slug)
                    # Name will be extracted from the company page
                    slug_map[slug] = (None, f"https://www.blackbird.vc/portfolio/{slug}")

        print(f"  Found {len(slug_map)} company slugs, scraping each page...", flush=True)

        for slug, (_, page_url) in slug_map.items():
            try:
                company_page = browser.new_page()
                company_page.goto(page_url, timeout=self.timeout, wait_until="domcontentloaded")
                company_page.wait_for_timeout(3000)

                # Extract company name from h1
                name = None
                try:
                    h1 = company_page.query_selector("h1")
                    if h1:
                        name = h1.inner_text().strip()
                except:
                    pass

                # Find VISIT WEBSITE link
                domain = None
                links = company_page.query_selector_all("a[href]")
                for link in links:
                    text = link.inner_text().strip().lower()
                    href = link.get_attribute("href") or ""
                    if "visit website" in text or "view website" in text:
                        if href.startswith("http") and "blackbird" not in href.lower():
                            domain = href
                            break

                if name and domain:
                    # Dedupe by domain
                    parsed = urlparse(domain)
                    netloc = parsed.netloc.lower().replace("www.", "")
                    if netloc not in seen_domains:
                        seen_domains.add(netloc)
                        companies.append({
                            "company_name": name[:200],
                            "domain": domain,
                            "vc_source": "Blackbird",
                            "scraped_at": datetime.now(timezone.utc).isoformat(),
                        })
                        print(f"    {name} -> {domain}", flush=True)

                company_page.close()
            except Exception as e:
                try:
                    company_page.close()
                except:
                    pass
                print(f"    Failed to scrape /portfolio/{slug}: {e}", flush=True)

            time.sleep(random.uniform(0.5, 1.5))

        print(f"  Blackbird found {len(companies)} companies", flush=True)
        return companies

    def _get_company_domain_from_page(self, browser, company_page_url: str, slug: str) -> str | None:
        """Visit a company page and extract the company's external website URL. Reuses browser."""
        page = browser.new_page()
        page.goto(company_page_url, timeout=self.timeout, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        links = page.query_selector_all("a[href]")

        # Priority 1: "View Website" link
        for link in links:
            href = link.get_attribute("href") or ""
            text = link.inner_text().strip().lower()
            if "view website" in text or "view site" in text:
                if href.startswith("http") and "mseq" not in href.lower():
                    page.close()
                    return href

        # Priority 2: any external link (skip social media, jobs, etc.)
        excluded = {
            "linkedin.com/company/mainsequence",
            "medium.com/main-sequence",
            "jobs.mseq.vc",
            "twitter.com", "youtube.com", "facebook.com",
            "instagram.com", "github.com", "crunchbase.com",
            "pitchbook.com", "wikipedia.org",
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

    def _scrape_generic(self, page, base_url: str) -> list[dict]:
        """
        Generic extraction: collect company name + domain from external links.
        Also handles pagination (_page=N query param) to scrape all pages.
        """
        vc_source = self._vc_name_from_url(base_url)
        companies = []
        seen_names = set()

        # Collect companies from current page
        companies, seen_names = self._collect_from_page(page, base_url, vc_source, seen_names)

        # Handle pagination — look for _page=N links
        pagination_links = page.query_selector_all("a[href]")
        page_urls = set()
        for link in pagination_links:
            href = link.get_attribute("href") or ""
            # Match pagination pattern: ?{anything}_page=N
            if "_page=" in href and "portfolio" in href.lower():
                if not href.startswith("http"):
                    href = urljoin(base_url, href)
                page_urls.add(href)

        # Also check for page links in the URL pattern
        current_base = base_url.split("?")[0]

        if page_urls:
            print(f"  Found {len(page_urls)} pagination pages, scraping all...", flush=True)
            for page_url in sorted(page_urls):
                try:
                    new_page = page.browser.new_page()
                    new_page.goto(page_url, timeout=self.timeout, wait_until="domcontentloaded")
                    new_page.wait_for_timeout(3000)
                    # Scroll
                    for _ in range(3):
                        new_page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        new_page.wait_for_timeout(1500)
                    companies, seen_names = self._collect_from_page(
                        new_page, page_url, vc_source, seen_names
                    )
                    new_page.close()
                except Exception as e:
                    print(f"  Pagination page failed: {e}", flush=True)
                    try:
                        new_page.close()
                    except:
                        pass

        return companies

    def _collect_from_page(self, page, base_url: str, vc_source: str, seen_names: set) -> tuple:
        """Collect company links from a single page."""
        companies = []
        links = page.query_selector_all("a[href]")
        for link in links:
            href = link.get_attribute("href") or ""
            text = link.inner_text().strip()
            if not href.startswith("http"):
                href = urljoin(base_url, href)
            if not self._is_external_company_link(href, text):
                continue

            # Company name is first line of link text
            name = text.split("\n")[0].strip()
            name = self._clean_company_name(name)
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
            # Portfolio page section names
            "people", "community", "perspectives", "close", "privacy policy",
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
        # Skip all-uppercase menu items
        if text.isupper():
            return False
        if not any(c.isupper() for c in text):
            return False
        return True

    def _is_external_company_link(self, href: str, text: str) -> bool:
        excluded = {
            "linkedin.com", "twitter.com", "youtube.com", "facebook.com",
            "instagram.com", "github.com", "crunchbase.com", "pitchbook.com",
            "wikipedia.org", "google.com", "googletagmanager.com",
            "mseq.vc", "blackbird.vc", "squarepeg.vc", "airtree.vc",
            "folklore.vc", "sprintajax.com", "ten13.com", "alto.capital",
            "rampersand.com", "basecapital.com.au", "candour.vc",
            # Blockchain / crypto
            "solana.com", "sui.io", "polkadot.com", "fantom.foundation",
            "avax.network", "algorand.com", "binance.com", "near.org",
            "filecoin.io", "thegraph.com", "0x.org", "zilliqa.com",
            "loopring.org", "thorchain.org", "oasisprotocol.org",
            "skale.network", "ankr.com", "tezos.com", "nkn.org",
            "cere.network", "agoric.com", "aergo.io", "singularitynet.io",
            "minaprotocol.com", "sui.io", "peaq.network", "holyheld.com",
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
        if text and len(text) > 2:
            return True
        return False

    def _extract_domain(self, url: str) -> str | None:
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            if domain.startswith("www."):
                domain = domain[4:]
            if not domain:
                return None
            return f"{parsed.scheme}://{domain}/"
        except Exception:
            return None

    def _clean_company_name(self, text: str) -> str:
        name = text.split("\n")[0].strip()
        for suffix in [" - Wikipedia", " | Crunchbase", " - LinkedIn"]:
            if name.endswith(suffix):
                name = name[: -len(suffix)].strip()
        if len(name) < 2:
            return ""
        return name[:200]

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

