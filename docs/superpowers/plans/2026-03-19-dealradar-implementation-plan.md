# DealRadar MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build DealRadar MVP — an automated pipeline that scrapes VC portfolios, enriches data with AI signal analysis, and outputs to Notion CRM.

**Architecture:** 3-module pipeline: Harvester (Jina + Apify) → AI Reasoner (multi-model chain) → Commander (Notion API). Greenfield Python project, TDD-first.

**Tech Stack:** Python 3.11+, Jina Reader API, Apify, Notion API, Google AI (Gemini), OpenAI (GPT-4o-mini), SMTP/SendGrid for email

---

## File Map

```
dealradar/
├── src/
│   ├── __init__.py
│   ├── harvester/
│   │   ├── __init__.py
│   │   ├── jina_client.py      # Jina Reader API client
│   │   ├── apify_client.py     # Apify fallback client
│   │   ├── extractor.py        # Company name/domain extraction from HTML
│   │   └── pipeline.py         # Harvester pipeline orchestration
│   ├── reasoner/
│   │   ├── __init__.py
│   │   ├── models.py           # Multi-model chain (Gemini → Kimi → GLM → OpenAI)
│   │   ├── signals.py          # Signal detection rules & scoring
│   │   ├── funding_clock.py    # Burn rate & funding window calculation
│   │   ├── summarizer.py       # Semantic compression (<100 word one-liner)
│   │   └── pipeline.py         # Reasoner pipeline orchestration
│   └── commander/
│       ├── __init__.py
│       ├── notion_client.py     # Notion API read/write
│       └── digest.py            # Weekly Top 5 digest email generator
├── config/
│   └── vc_seeds.json           # 10 AUS VC portfolio URLs
├── data/                        # Created at runtime
├── tests/
│   ├── test_scaffolding.py
│   ├── test_jina_client.py
│   ├── test_apify_client.py
│   ├── test_extractor.py
│   ├── test_harvester_pipeline.py
│   ├── test_models.py
│   ├── test_signals.py
│   ├── test_funding_clock.py
│   ├── test_summarizer.py
│   ├── test_reasoner_pipeline.py
│   ├── test_notion_client.py
│   └── test_digest.py
├── run.py                      # Main CLI entry point
├── requirements.txt
├── .env.example
└── CLAUDE.md
```

---

## Task 1: Project Scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `config/vc_seeds.json`
- Create: `src/__init__.py`, `src/harvester/__init__.py`, `src/reasoner/__init__.py`, `src/commander/__init__.py`
- Create: `run.py`
- Create: `CLAUDE.md`
- Test: `tests/test_scaffolding.py`

- [ ] **Step 1: Write scaffolding test**

```python
# tests/test_scaffolding.py
import json
from pathlib import Path

def test_vc_seeds_config_exists():
    config_path = Path("config/vc_seeds.json")
    assert config_path.exists(), "vc_seeds.json must exist"

def test_vc_seeds_config_valid():
    with open("config/vc_seeds.json") as f:
        seeds = json.load(f)
    assert isinstance(seeds, list)
    assert len(seeds) == 10
    for seed in seeds:
        assert "name" in seed
        assert "url" in seed
        assert seed["url"].startswith("http")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scaffolding.py -v`
Expected: FAIL — config/vc_seeds.json does not exist

- [ ] **Step 3: Create requirements.txt**

```txt
# requirements.txt
requests>=2.31.0
beautifulsoup4>=4.12.0
lxml>=4.9.0
notion-client>=2.0.0
google-generativeai>=0.8.0
openai>=1.12.0
python-dotenv>=1.0.0
tqdm>=4.66.0
```

- [ ] **Step 4: Create config/vc_seeds.json**

```json
[
  {"name": "Blackbird", "url": "https://blackbird.vc/portfolio"},
  {"name": "Square Peg", "url": "https://squarepeg.vc/portfolio"},
  {"name": "AirTree", "url": "https://airtree.vc/portfolio"},
  {"name": "Folklore", "url": "https://folklore.vc/portfolio"},
  {"name": "Sprint Ajax", "url": "https://sprintajax.com/portfolio"},
  {"name": "TEN13", "url": "https://ten13.com/portfolio"},
  {"name": "Alto", "url": "https://alto.capital/portfolio"},
  {"name": "Rampersand", "url": "https://rampersand.com/portfolio"},
  {"name": "Base Capital", "url": "https://basecapital.com.au/portfolio"},
  {"name": "Candour", "url": "https://candour.vc/portfolio"}
]
```

- [ ] **Step 5: Create __init__.py files and run.py**

```python
# src/__init__.py
"""DealRadar - Predictive Deal Intelligence CRM"""
__version__ = "0.1.0"
```

```python
# run.py
"""DealRadar CLI entry point"""
import argparse
import json
from pathlib import Path
from src.harvester.jina_client import JinaClient
from src.harvester.extractor import extract_companies_from_html
from src.reasoner.models import ModelChain
from src.commander.notion_client import NotionClient

def main():
    parser = argparse.ArgumentParser(description="DealRadar MVP")
    parser.add_argument("--phase", choices=["harvest", "reason", "push", "all"], default="all")
    args = parser.parse_args()

    if args.phase in ("harvest", "all"):
        print("Phase 1: Harvesting VC portfolios...")

    if args.phase in ("reason", "all"):
        print("Phase 2: AI enrichment...")

    if args.phase in ("push", "all"):
        print("Phase 3: Pushing to Notion...")

if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run scaffolding tests to verify they pass**

Run: `pytest tests/test_scaffolding.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add requirements.txt config/vc_seeds.json src/__init__.py src/harvester/__init__.py src/reasoner/__init__.py src/commander/__init__.py run.py tests/test_scaffolding.py CLAUDE.md
git commit -m "feat: scaffold project structure and config

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 2: Jina Client

**Files:**
- Create: `src/harvester/jina_client.py`
- Create: `tests/test_jina_client.py`

- [ ] **Step 1: Write Jina client test**

```python
# tests/test_jina_client.py
from src.harvester.jina_client import JinaClient

def test_jina_client_initialization():
    client = JinaClient(api_key="test-key")
    assert client.base_url == "https://r.jina.ai/"

def test_jina_client_build_url():
    client = JinaClient(api_key="test-key")
    url = client.build_url("https://example.com")
    assert url == "https://r.jina.ai/https://example.com"

def test_jina_client_build_url_encodes():
    client = JinaClient(api_key="test-key")
    url = client.build_url("https://example.com/path with spaces")
    assert " " not in url
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_jina_client.py -v`
Expected: FAIL — module does not exist

- [ ] **Step 3: Write JinaClient implementation**

```python
# src/harvester/jina_client.py
"""Jina Reader API client for extracting clean text from URLs."""
import os
import random
import time
import requests
from urllib.parse import urljoin, urlparse

class JinaClient:
    """Client for Jina Reader API (https://r.jina.ai/)."""

    BASE_URL = "https://r.jina.ai/"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("JINA_API_KEY", "")
        self.session = requests.Session()
        if self.api_key:
            self.session.headers["Authorization"] = f"Bearer {self.api_key}"

    def build_url(self, target_url: str) -> str:
        """Convert a target URL to a Jina Reader URL."""
        return f"{self.BASE_URL}{target_url}"

    def fetch(self, url: str, timeout: int = 30) -> str:
        """
        Fetch clean markdown text from a URL using Jina Reader.
        Returns the markdown content as a string.
        Raises requests.HTTPError on failure.
        """
        jina_url = self.build_url(url)
        response = self.session.get(jina_url, timeout=timeout)
        response.raise_for_status()
        return response.text

    def fetch_with_retry(self, url: str, max_retries: int = 3) -> str:
        """Fetch with exponential backoff and random jitter."""
        for attempt in range(max_retries):
            try:
                # Random jitter 2-5 seconds
                time.sleep(random.uniform(2, 5))
                return self.fetch(url)
            except requests.RequestException as e:
                if attempt == max_retries - 1:
                    raise
                wait = (2 ** attempt) * 1.0  # 1s, 2s, 4s
                time.sleep(wait)
        raise RuntimeError("Unreachable")

    def is_different_domain(self, original_url: str, final_url: str) -> bool:
        """Check if the final URL has redirected to a different domain."""
        return urlparse(original_url).netloc != urlparse(final_url).netloc
```

- [ ] **Step 4: Run Jina client tests to verify they pass**

Run: `pytest tests/test_jina_client.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/harvester/jina_client.py tests/test_jina_client.py
git commit -m "feat(harvester): add Jina Reader API client with retry logic

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 3: Apify Client

**Files:**
- Create: `src/harvester/apify_client.py`
- Create: `tests/test_apify_client.py`

- [ ] **Step 1: Write Apify client test**

```python
# tests/test_apify_client.py
from src.harvester.apify_client import ApifyClient

def test_apify_client_initialization():
    client = ApifyClient(api_token="test-token")
    assert client.api_token == "test-token"

def test_apify_client_actor_url():
    client = ApifyClient(api_token="test-token")
    assert "apify.com" in client.actor_url
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_apify_client.py -v`
Expected: FAIL — module does not exist

- [ ] **Step 3: Write ApifyClient implementation**

```python
# src/harvester/apify_client.py
"""Apify client for JavaScript-rendered pages (fallback when Jina fails)."""
import os
import random
import time
import requests

class ApifyClient:
    """Client for Apify API (apify.com) — fallback for JS-rendered pages."""

    ACTOR_URL = "https://api.apify.com/v2/acts/apify~website-scraper/run-sync"

    def __init__(self, api_token: str | None = None):
        self.api_token = api_token or os.getenv("APIFY_API_TOKEN", "")

    def scrape(self, url: str, timeout: int = 60) -> dict:
        """
        Scrape a URL using Apify's website-scraper actor.
        Returns parsed JSON with text content.
        """
        if not self.api_token:
            raise ValueError("APIFY_API_TOKEN not set")

        time.sleep(random.uniform(2, 5))  # Rate limiting

        response = requests.post(
            self.ACTOR_URL,
            params={"token": self.api_token},
            json={"urls": [url]},
            timeout=timeout
        )
        response.raise_for_status()
        return response.json()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_apify_client.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/harvester/apify_client.py tests/test_apify_client.py
git commit -m "feat(harvester): add Apify fallback client for JS-rendered pages

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 4: Company Extractor

**Files:**
- Create: `src/harvester/extractor.py`
- Create: `tests/test_extractor.py`

- [ ] **Step 1: Write extractor test**

```python
# tests/test_extractor.py
from src.harvester.extractor import extract_companies_from_html, filter_dead_companies

SAMPLE_HTML = """
<html>
<body>
<a href="https://canvas.co">Canvas</a>
<a href="https://deadcompany.com">Dead Company</a>
<a href="https://acquired.com">Acquired Corp</a>
</body>
</html>
"""

def test_extract_companies_from_html_basic():
    companies = extract_companies_from_html(SAMPLE_HTML, vc_source="TestVC")
    assert len(companies) == 3
    names = [c["company_name"] for c in companies]
    assert "Canvas" in names

def test_extract_companies_from_html_schema():
    companies = extract_companies_from_html(SAMPLE_HTML, vc_source="TestVC")
    for c in companies:
        assert "company_name" in c
        assert "domain" in c
        assert "vc_source" in c
        assert "scraped_at" in c
        assert c["vc_source"] == "TestVC"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_extractor.py -v`
Expected: FAIL — module does not exist

- [ ] **Step 3: Write extractor implementation**

```python
# src/harvester/extractor.py
"""Extract company names and domains from VC portfolio HTML pages."""
import re
import json
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from src.harvester.jina_client import JinaClient
from src.harvester.apify_client import ApifyClient


def extract_companies_from_html(
    html: str,
    vc_source: str,
    base_url: str = ""
) -> list[dict[str, Any]]:
    """
    Parse VC portfolio HTML and extract company name + domain pairs.

    Args:
        html: Raw HTML/markdown from Jina Reader
        vc_source: Name of the VC firm
        base_url: Base URL for resolving relative links

    Returns:
        List of dicts: {company_name, domain, stage, vc_source, scraped_at}
    """
    soup = BeautifulSoup(html, "lxml")
    companies = []
    seen_domains = set()

    # Find all links that look like company links (external domains)
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        text = a_tag.get_text(strip=True)

        # Skip empty links or navigation
        if not text or len(text) < 2:
            continue

        # Resolve relative URLs
        if not href.startswith("http"):
            if base_url:
                href = urljoin(base_url, href)
            else:
                continue

        # Extract domain
        domain = extract_domain_from_url(href)
        if not domain or domain in seen_domains:
            continue
        if is_excluded_domain(domain):
            continue

        seen_domains.add(domain)
        companies.append({
            "company_name": text[:200],
            "domain": href,
            "stage": detect_stage_from_context(a_tag) or "Unknown",
            "vc_source": vc_source,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        })

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
    """Check if domain should be excluded (social media, Crunchbase, etc.)."""
    excluded = {
        "twitter.com", "linkedin.com", "facebook.com", "instagram.com",
        "youtube.com", "crunchbase.com", "pitchbook.com",
        "wikipedia.org", "github.com",
    }
    netloc = urlparse(domain).netloc.replace("www.", "")
    return netloc in excluded


def detect_stage_from_context(a_tag) -> str | None:
    """Attempt to detect funding stage from surrounding context."""
    parent_text = a_tag.parent.get_text() if a_tag.parent else ""
    grandparent_text = a_tag.parent.parent.get_text() if a_tag.parent and a_tag.parent.parent else ""
    combined = parent_text + " " + grandparent_text
    stage_match = re.search(r"\b(Seed|Series\s+[A-Z]|Angel|Pre-Seed|Post-Seed)\b", combined, re.I)
    if stage_match:
        return stage_match.group(0).strip()
    return None


def filter_dead_companies(companies: list[dict], jina_client: JinaClient) -> list[dict]:
    """
    Filter out dead companies (404, acquired, IPO'd) by checking their domains.
    Companies that cannot be fetched (dead domains, network errors) are skipped —
    they may be defunct sites that no longer respond.
    """
    alive = []
    for company in companies:
        try:
            content = jina_client.fetch(company["domain"], timeout=10)
            content_lower = content.lower()
            if any(signal in content_lower for signal in ["acquired by", "ipo'd", "gone public", "shut down"]):
                print(f"  [FILTERED] {company['company_name']} — acquired/IPO'd")
                continue
            if "404" in content_lower and "not found" in content_lower:
                print(f"  [FILTERED] {company['company_name']} — 404")
                continue
            alive.append(company)
        except Exception as e:
            # Cannot fetch — domain may be dead. Skip it.
            print(f"  [FILTERED] {company['company_name']} — un-fetchable ({e})")
            continue
    return alive
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_extractor.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/harvester/extractor.py tests/test_extractor.py
git commit -m "feat(harvester): add company extractor with dead company filtering

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 5: Harvester Pipeline

**Files:**
- Create: `src/harvester/pipeline.py`
- Create: `tests/test_harvester_pipeline.py`

- [ ] **Step 1: Write pipeline test**

```python
# tests/test_harvester_pipeline.py
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from src.harvester.pipeline import HarvesterPipeline

@patch("src.harvester.jina_client.JinaClient.fetch")
def test_pipeline_scrapes_vc_portfolio(mock_fetch):
    mock_fetch.return_value = "<html><body><a href='https://canvas.co'>Canvas</a></body></html>"
    pipeline = HarvesterPipeline(vc_seeds_path="config/vc_seeds.json")
    companies = pipeline.run()

    assert isinstance(companies, list)
    assert len(companies) > 0
    for c in companies:
        assert "company_name" in c
        assert "domain" in c
        assert c["vc_source"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_harvester_pipeline.py -v`
Expected: FAIL — module does not exist

- [ ] **Step 3: Write pipeline implementation**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_harvester_pipeline.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/harvester/pipeline.py tests/test_harvester_pipeline.py
git commit -m "feat(harvester): add harvester pipeline orchestration

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 6: AI Models Chain

**Files:**
- Create: `src/reasoner/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write models chain test**

```python
# tests/test_models.py
from src.reasoner.models import ModelChain, ModelProvider

def test_model_chain_initialization():
    import os
    os.environ["GEMINI_API_KEY"] = "test"
    chain = ModelChain()
    assert len(chain.providers) >= 1
    assert chain.providers[0].name == "gemini"

def test_model_provider_enum():
    assert ModelProvider.GEMINI.value == "gemini"
    assert ModelProvider.KIMI.value == "kimi"
    assert ModelProvider.OPENAI.value == "openai"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_models.py -v`
Expected: FAIL — module does not exist

- [ ] **Step 3: Write ModelChain implementation**

```python
# src/reasoner/models.py
"""Multi-model AI chain with automatic fallback: Gemini -> Kimi -> GLM -> OpenAI."""
import os
import json
from enum import Enum
from dataclasses import dataclass

import google.genai as genai
from openai import OpenAI

API_KEYS = {
    "gemini": os.getenv("GEMINI_API_KEY", ""),
    "kimi": os.getenv("KIMI_API_KEY", ""),
    "glm": os.getenv("GLM_API_KEY", ""),
    "openai": os.getenv("OPENAI_API_KEY", ""),
}


class ModelProvider(Enum):
    GEMINI = "gemini"
    KIMI = "kimi"
    GLM = "glm"
    OPENAI = "openai"


@dataclass
class ModelResponse:
    text: str
    provider: ModelProvider
    model_name: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class ModelChain:
    """
    Multi-model chain with fallback.
    Tries providers in order: Gemini -> Kimi -> GLM -> OpenAI.
    Logs which provider succeeded.
    """

    DEFAULT_MODELS = {
        ModelProvider.GEMINI: "gemini-2.0-flash",
        ModelProvider.KIMI: "moonshot-v1-8k",
        ModelProvider.GLM: "glm-4-flash",
        ModelProvider.OPENAI: "gpt-4o-mini",
    }

    def __init__(self, model_overrides: dict[ModelProvider, str] | None = None):
        self.providers = self._build_provider_list()
        self.models = model_overrides or self.DEFAULT_MODELS
        self._openai_client = OpenAI(api_key=API_KEYS["openai"]) if API_KEYS["openai"] else None

    def _build_provider_list(self) -> list[ModelProvider]:
        """Return providers in fallback order, skipping those without API keys."""
        chain = []
        for provider in [ModelProvider.GEMINI, ModelProvider.KIMI, ModelProvider.GLM, ModelProvider.OPENAI]:
            if API_KEYS[provider.value]:
                chain.append(provider)
        if not chain:
            raise ValueError("No AI API keys configured")
        return chain

    def complete(self, prompt: str, system_prompt: str = "", max_tokens: int = 1000) -> ModelResponse:
        """Send a prompt through the fallback chain. Returns first successful response."""
        for provider in self.providers:
            try:
                if provider == ModelProvider.GEMINI:
                    return self._call_gemini(prompt, system_prompt, max_tokens)
                elif provider == ModelProvider.KIMI:
                    return self._call_kimi(prompt, system_prompt, max_tokens)
                elif provider == ModelProvider.GLM:
                    return self._call_glm(prompt, system_prompt, max_tokens)
                elif provider == ModelProvider.OPENAI:
                    return self._call_openai(prompt, system_prompt, max_tokens)
            except Exception as e:
                print(f"  [{provider.value}] Failed: {e}. Trying next provider...")
                continue
        raise RuntimeError("All AI providers failed")

    def _call_gemini(self, prompt: str, system_prompt: str, max_tokens: int) -> ModelResponse:
        genai.configure(api_key=API_KEYS["gemini"])
        model_name = self.models[ModelProvider.GEMINI]
        client = genai.Client()
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        response = client.models.generate_content(model=model_name, contents=full_prompt)
        return ModelResponse(text=response.text, provider=ModelProvider.GEMINI, model_name=model_name)

    def _call_kimi(self, prompt: str, system_prompt: str, max_tokens: int) -> ModelResponse:
        import requests
        headers = {"Authorization": f"Bearer {API_KEYS['kimi']}", "Content-Type": "application/json"}
        payload = {
            "model": self.models[ModelProvider.KIMI],
            "messages": (
                [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}]
                if system_prompt else [{"role": "user", "content": prompt}]
            ),
            "max_tokens": max_tokens,
        }
        resp = requests.post("https://api.moonshot.cn/v1/chat/completions", headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        return ModelResponse(
            text=data["choices"][0]["message"]["content"],
            provider=ModelProvider.KIMI,
            model_name=self.models[ModelProvider.KIMI],
        )

    def _call_glm(self, prompt: str, system_prompt: str, max_tokens: int) -> ModelResponse:
        import requests
        headers = {"Authorization": f"Bearer {API_KEYS['glm']}", "Content-Type": "application/json"}
        payload = {
            "model": self.models[ModelProvider.GLM],
            "messages": (
                [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}]
                if system_prompt else [{"role": "user", "content": prompt}]
            ),
            "max_tokens": max_tokens,
        }
        resp = requests.post("https://open.bigmodel.cn/api/paas/v4/chat/completions", headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        return ModelResponse(
            text=data["choices"][0]["message"]["content"],
            provider=ModelProvider.GLM,
            model_name=self.models[ModelProvider.GLM],
        )

    def _call_openai(self, prompt: str, system_prompt: str, max_tokens: int) -> ModelResponse:
        if not self._openai_client:
            raise ValueError("OpenAI API key not configured")
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        response = self._openai_client.chat.completions.create(
            model=self.models[ModelProvider.OPENAI],
            messages=messages,
            max_tokens=max_tokens,
        )
        return ModelResponse(
            text=response.choices[0].message.content,
            provider=ModelProvider.OPENAI,
            model_name=self.models[ModelProvider.OPENAI],
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/reasoner/models.py tests/test_models.py
git commit -m "feat(reasoner): add multi-model AI chain with fallback (Gemini->Kimi->GLM->OpenAI)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 7: Signal Detection & Scoring

**Files:**
- Create: `src/reasoner/signals.py`
- Create: `tests/test_signals.py`

- [ ] **Step 1: Write signal scoring test**

```python
# tests/test_signals.py
from src.reasoner.signals import SignalDetector, SignalScore

def test_score_cfo_hire_is_highest():
    detector = SignalDetector()
    score = detector.calculate_score(
        has_cfo_hire=True,
        last_raise_amount=15_000_000,
        months_since_raise=16,
        has_multilang=False,
        has_series_c_plus=False,
        has_audit_signals=False,
    )
    assert score == SignalScore.CFO_HIRE  # +40

def test_score_old_raise_without_cfo():
    detector = SignalDetector()
    score = detector.calculate_score(
        has_cfo_hire=False,
        last_raise_amount=8_000_000,
        months_since_raise=20,
        has_multilang=False,
        has_series_c_plus=False,
        has_audit_signals=False,
    )
    assert score == SignalScore.LAST_RAISE_18_PLUS  # +30

def test_score_no_signals():
    detector = SignalDetector()
    score = detector.calculate_score(
        has_cfo_hire=False,
        last_raise_amount=None,
        months_since_raise=6,
        has_multilang=False,
        has_series_c_plus=False,
        has_audit_signals=False,
    )
    assert score == 0

def test_extract_tags():
    detector = SignalDetector()
    tags = detector.extract_tags(
        has_cfo_hire=True,
        last_raise_amount=15_000_000,
        months_since_raise=16,
        has_multilang=True,
        has_series_c_plus=True,
        has_audit_signals=True,
        valuation_over_1b=True,
        robotics_supply_chain=False,
    )
    assert "Pre-IPO Watch" in tags
    assert "Cross-Border Target" in tags
    assert "Unicorn" in tags
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_signals.py -v`
Expected: FAIL — module does not exist

- [ ] **Step 3: Write signals implementation**

```python
# src/reasoner/signals.py
"""Signal detection rules and scoring (mutually exclusive — highest wins)."""
from dataclasses import dataclass
from enum import IntEnum


class SignalScore(IntEnum):
    CFO_HIRE = 40
    LAST_RAISE_10_20M_15MOS = 30
    LAST_RAISE_18_PLUS = 30
    MULTI_LANG_APAC = 20
    SERIES_C_PLUS = 15
    AUDIT_SOC2 = 15


@dataclass
class SignalResult:
    score: int
    primary_signal: str
    tags: list[str]


class SignalDetector:
    """
    Signal detection with mutually exclusive scoring.
    Only the HIGHEST matching condition applies — no stacking.
    Rules evaluated top-to-bottom.
    """

    SYSTEM_PROMPT = """You are a deal intelligence analyst. Analyze the following company text and extract signals.
Return a JSON object with these fields ONLY (no other text):
{
  "has_cfo_hire": true/false,
  "has_multilang_apac": true/false,
  "has_series_c_plus": true/false,
  "has_audit_signals": true/false,
  "has_supply_chain_robotics": true/false,
  "valuation_over_1b": true/false,
  "last_raise_amount_usd": number or null,
  "months_since_raise": number or null,
  "sector": "string"
}
Be precise. Only set a field to true if there is clear evidence."""

    def __init__(self, model_chain=None):
        self.model_chain = model_chain

    def calculate_score(
        self,
        has_cfo_hire: bool,
        last_raise_amount: int | None,
        months_since_raise: int | None,
        has_multilang: bool,
        has_series_c_plus: bool,
        has_audit_signals: bool,
    ) -> int:
        """Return the signal score (mutually exclusive — highest condition only)."""
        if has_cfo_hire:
            return SignalScore.CFO_HIRE

        if last_raise_amount and months_since_raise is not None:
            if 10_000_000 <= last_raise_amount <= 20_000_000 and months_since_raise >= 15:
                return SignalScore.LAST_RAISE_10_20M_15MOS

        if months_since_raise is not None and months_since_raise >= 18:
            return SignalScore.LAST_RAISE_18_PLUS

        if has_multilang:
            return SignalScore.MULTI_LANG_APAC

        if has_series_c_plus:
            return SignalScore.SERIES_C_PLUS

        if has_audit_signals:
            return SignalScore.AUDIT_SOC2

        return 0

    def extract_tags(
        self,
        has_cfo_hire: bool,
        last_raise_amount: int | None,
        months_since_raise: int | None,
        has_multilang: bool,
        has_series_c_plus: bool,
        has_audit_signals: bool,
        valuation_over_1b: bool,
        robotics_supply_chain: bool,
    ) -> list[str]:
        """Extract all applicable tags (not mutually exclusive — can have multiple)."""
        tags = []

        if valuation_over_1b or (last_raise_amount and last_raise_amount >= 100_000_000):
            tags.append("Unicorn")

        if has_series_c_plus and (has_cfo_hire or has_audit_signals):
            tags.append("Pre-IPO Watch")

        if has_multilang:
            tags.append("Cross-Border Target")

        if last_raise_amount and months_since_raise:
            if 10_000_000 <= last_raise_amount <= 20_000_000 and months_since_raise >= 15:
                tags.append("Funding Urgency High")

        if robotics_supply_chain:
            tags.append("Venture Nexus")

        return tags

    def analyze_text(self, text: str, model_chain) -> dict:
        """Use AI to extract signal flags from raw text."""
        truncated = self._truncate_text(text, max_chars=4000)

        response = model_chain.complete(
            prompt=truncated,
            system_prompt=self.SYSTEM_PROMPT,
            max_tokens=500,
        )

        import json
        try:
            text_response = response.text.strip()
            if text_response.startswith("```"):
                text_response = "\n".join(text_response.split("\n")[1:])
            if text_response.endswith("```"):
                text_response = text_response[:-3]
            return json.loads(text_response)
        except json.JSONDecodeError:
            return {"error": "Failed to parse AI response"}

    def _truncate_text(self, text: str, max_chars: int = 4000) -> str:
        """Hard truncate to max_chars for token control."""
        return text[:max_chars] if len(text) > max_chars else text
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_signals.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/reasoner/signals.py tests/test_signals.py
git commit -m "feat(reasoner): add signal detection with mutually exclusive scoring

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 8: Funding Clock

**Files:**
- Create: `src/reasoner/funding_clock.py`
- Create: `tests/test_funding_clock.py`

- [ ] **Step 1: Write funding clock test**

```python
# tests/test_funding_clock.py
from datetime import date
from src.reasoner.funding_clock import FundingClock, estimate_monthly_burn

def test_estimate_monthly_burn():
    # B2B SaaS median ~$15K/month per employee
    burn = estimate_monthly_burn(headcount=20, sector="B2B SaaS")
    assert 250_000 < burn < 400_000  # 20 * 15K * 1.3

def test_estimate_monthly_burn_unknown_sector():
    burn = estimate_monthly_burn(headcount=10, sector="Unknown")
    assert burn > 0  # Uses fallback rate

def test_days_remaining_calculation():
    clock = FundingClock(last_raise_amount=10_000_000, days_since_raise=400)
    burn = estimate_monthly_burn(headcount=15, sector="B2B SaaS")
    days_remaining = clock.calculate_days_remaining(burn)
    assert days_remaining >= 0

def test_funding_clock_prediction():
    clock = FundingClock(last_raise_amount=12_000_000, days_since_raise=400)
    burn = estimate_monthly_burn(headcount=15, sector="B2B SaaS")
    predicted_date = clock.predict_funding_date(burn)
    assert predicted_date is not None
    assert predicted_date > date.today()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_funding_clock.py -v`
Expected: FAIL — module does not exist

- [ ] **Step 3: Write funding clock implementation**

```python
# src/reasoner/funding_clock.py
"""Funding clock: burn rate estimation and next raise date prediction."""
from datetime import date, timedelta


# Industry average monthly burn per employee (USD), with 30% overhead
SECTOR_BURN_RATES = {
    "B2B SaaS": 15_000,
    "B2C SaaS": 12_000,
    "FinTech": 18_000,
    "HealthTech": 20_000,
    "EdTech": 10_000,
    "PropTech": 16_000,
    "AI/ML": 22_000,
    "Biotech": 25_000,
    "Hardware": 20_000,
    "Marketplace": 14_000,
    "Crypto/Blockchain": 20_000,
    "Gaming": 15_000,
    "Unknown": 15_000,
}

OVERHEAD_MULTIPLIER = 1.30


def estimate_monthly_burn(headcount: int | None, sector: str | None) -> float:
    """Estimate monthly burn = headcount x industry_avg x 1.3 overhead."""
    rate = SECTOR_BURN_RATES.get(sector or "Unknown", SECTOR_BURN_RATES["Unknown"])
    employees = headcount if headcount else 10
    return employees * rate * OVERHEAD_MULTIPLIER


def estimate_headcount_from_text(text: str) -> int | None:
    """Attempt to extract headcount from company text."""
    import re
    patterns = [
        r"(\d+)\s*(?:employees|people|team members?|staff)",
        r"team of (\d+)",
        r"we're?\s*(\d+)\s*(?:people|folks)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return int(match.group(1))
    return None


class FundingClock:
    """
    Calculate when a company will likely need their next funding round.
    Days Remaining = (Last Round Amount / Monthly Burn) - Days Since Last Round
    """

    def __init__(self, last_raise_amount: float, days_since_raise: int):
        self.last_raise_amount = last_raise_amount
        self.days_since_raise = days_since_raise

    def calculate_days_remaining(self, monthly_burn: float) -> float:
        """Returns approximate days until funding runway depletes."""
        if monthly_burn <= 0:
            return 0
        total_runway_days = self.last_raise_amount / (monthly_burn / 30)
        return max(0, total_runway_days - self.days_since_raise)

    def predict_funding_date(self, monthly_burn: float) -> date | None:
        """Returns predicted date of next funding round."""
        if self.last_raise_amount <= 0:
            return None
        days_remaining = self.calculate_days_remaining(monthly_burn)
        return date.today() + timedelta(days=int(days_remaining))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_funding_clock.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/reasoner/funding_clock.py tests/test_funding_clock.py
git commit -m "feat(reasoner): add funding clock burn rate calculation

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 9: Summarizer

**Files:**
- Create: `src/reasoner/summarizer.py`
- Create: `tests/test_summarizer.py`

- [ ] **Step 1: Write summarizer test**

```python
# tests/test_summarizer.py
from src.reasoner.summarizer import Summarizer, truncate_to_p_tags

def test_truncate_to_p_tags():
    html = "<p>First</p><p>Second</p><p>Third</p><p>Fourth</p><p>Fifth</p>"
    result = truncate_to_p_tags(html, max_p_tags=3)
    assert result.count("<p>") == 3

def test_truncate_to_p_tags_preserves_content():
    html = "<p>First para</p><p>Second para</p>"
    result = truncate_to_p_tags(html, max_p_tags=10)
    assert "First para" in result
    assert "Second para" in result

def test_summarizer_prompt_includes_requirements():
    summarizer = Summarizer()
    prompt = summarizer.build_prompt("Some long text about a company")
    assert "<100 words" in prompt
    assert "one sentence" in prompt

def test_summarizer_returns_tuple():
    """summarize() should return (text, model_name) tuple."""
    from unittest.mock import MagicMock
    from src.reasoner.models import ModelResponse, ModelProvider
    summarizer = Summarizer()
    mock_response = ModelResponse(text="A design tool.", provider=ModelProvider.GEMINI, model_name="gemini-2.0-flash")
    mock_chain = MagicMock()
    mock_chain.complete.return_value = mock_response
    result = summarizer.summarize("Some text", mock_chain)
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert result[0] == "A design tool."
    assert result[1] == "gemini-2.0-flash"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_summarizer.py -v`
Expected: FAIL — module does not exist

- [ ] **Step 3: Write summarizer implementation**

```python
# src/reasoner/summarizer.py
"""Semantic compression: summarize company text to <100 word one-liner."""
from bs4 import BeautifulSoup


def truncate_to_p_tags(html: str, max_p_tags: int = 20) -> str:
    """
    Truncate HTML to the first max_p_tags <p> tags.
    Token control strategy — deterministic, simple.
    """
    soup = BeautifulSoup(html, "lxml")
    p_tags = soup.find_all("p")[:max_p_tags]
    texts = []
    for p in p_tags:
        text = p.get_text(strip=True)
        if text:
            texts.append(text)
    return "\n\n".join(texts)


class Summarizer:
    """Build prompts for semantic compression of company text."""

    SYSTEM_PROMPT = """You are a senior venture analyst. Summarize the company below in exactly ONE sentence (under 100 words).
Focus on: What do they do? Who are their customers? How do they make money?
Return ONLY the summary sentence — no labels, no bullet points."""

    def __init__(self, model_chain=None):
        self.model_chain = model_chain

    def build_prompt(self, text: str) -> str:
        truncated = truncate_to_p_tags(text, max_p_tags=20)
        return f"Summarize this company in one sentence (under 100 words):\n\n{truncated}"

    def summarize(self, text: str, model_chain) -> tuple[str, str]:
        """Call AI to produce a <100 word one-liner. Returns (text, model_name)."""
        prompt = self.build_prompt(text)
        response = model_chain.complete(
            prompt=prompt,
            system_prompt=self.SYSTEM_PROMPT,
            max_tokens=200,
        )
        return response.text.strip(), response.model_name
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_summarizer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/reasoner/summarizer.py tests/test_summarizer.py
git commit -m "feat(reasoner): add semantic summarizer with token control

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 10: Reasoner Pipeline

**Files:**
- Create: `src/reasoner/pipeline.py`
- Create: `tests/test_reasoner_pipeline.py`

- [ ] **Step 1: Write reasoner pipeline test**

```python
# tests/test_reasoner_pipeline.py
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from src.reasoner.pipeline import ReasonerPipeline

def test_reasoner_pipeline_loads_raw_companies(tmp_path):
    raw_file = tmp_path / "raw.json"
    raw_file.write_text(json.dumps([
        {"company_name": "Canvas", "domain": "https://canvas.co", "vc_source": "TestVC"}
    ]))
    pipeline = ReasonerPipeline(raw_companies_path=str(raw_file))
    assert len(pipeline.companies) == 1

def test_reasoner_pipeline_output_schema(tmp_path):
    raw_file = tmp_path / "raw.json"
    raw_file.write_text(json.dumps([
        {"company_name": "Canvas", "domain": "https://canvas.co", "vc_source": "TestVC"}
    ]))
    out_file = tmp_path / "enriched.json"

    with patch("src.harvester.jina_client.JinaClient.fetch") as mock_fetch:
        mock_fetch.return_value = "<p>Canvas is a design tool.</p><p>They raised $12M Series A.</p>"
        with patch("src.reasoner.models.ModelChain.complete") as mock_model:
            mock_model.return_value = MagicMock(
                text='{"has_cfo_hire":false,"has_multilang_apac":false,"has_series_c_plus":false,"has_audit_signals":false,"has_supply_chain_robotics":false,"valuation_over_1b":false,"last_raise_amount_usd":12000000,"months_since_raise":10,"sector":"B2B SaaS"}'
            )
            pipeline = ReasonerPipeline(
                raw_companies_path=str(raw_file),
                output_path=str(out_file)
            )
            result = pipeline.process_company(pipeline.companies[0])

    assert "company_name" in result
    assert "signal_score" in result
    assert "tags" in result
    assert "funding_clock" in result
    assert isinstance(result["signal_score"], int)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_reasoner_pipeline.py -v`
Expected: FAIL — module does not exist

- [ ] **Step 3: Write reasoner pipeline implementation**

```python
# src/reasoner/pipeline.py
"""AI Reasoner pipeline — enriches raw companies with AI signal analysis."""
import json
import random
import time
from datetime import date
from pathlib import Path

from src.harvester.jina_client import JinaClient
from src.reasoner.models import ModelChain
from src.reasoner.signals import SignalDetector
from src.reasoner.funding_clock import FundingClock, estimate_monthly_burn
from src.reasoner.summarizer import Summarizer


class ReasonerPipeline:
    """Orchestrates AI enrichment: fetch company text -> summarize -> score signals -> calculate funding clock."""

    def __init__(
        self,
        raw_companies_path: str = "data/raw_companies.json",
        output_path: str = "data/enriched_companies.json",
        jina_client: JinaClient | None = None,
        model_chain: ModelChain | None = None,
    ):
        self.raw_companies_path = raw_companies_path
        self.output_path = output_path
        self.companies = self._load_raw()
        self.jina = jina_client or JinaClient()
        self.model_chain = model_chain or ModelChain()
        self.signals = SignalDetector()
        self.summarizer = Summarizer()
        self._enriched = []

    def _load_raw(self) -> list[dict]:
        with open(self.raw_companies_path) as f:
            return json.load(f)

    def process_company(self, company: dict) -> dict:
        """Enrich a single company with AI analysis."""
        domain = company["domain"]
        print(f"  Processing: {company['company_name']} ({domain})...")

        try:
            time.sleep(random.uniform(2, 5))
            raw_text = self.jina.fetch_with_retry(domain)
        except Exception as e:
            print(f"  [WARN] Failed to fetch {domain}: {e}")
            raw_text = ""

        # Step 1: Summarize
        try:
            one_liner, model_name = self.summarizer.summarize(raw_text, self.model_chain)
        except Exception:
            one_liner = "Unable to generate summary"
            model_name = "unknown"

        # Step 2: Extract signals
        try:
            signal_data = self.signals.analyze_text(raw_text, self.model_chain)
        except Exception:
            signal_data = {}

        # Step 3: Score
        score = self.signals.calculate_score(
            has_cfo_hire=signal_data.get("has_cfo_hire", False),
            last_raise_amount=signal_data.get("last_raise_amount_usd"),
            months_since_raise=signal_data.get("months_since_raise"),
            has_multilang=signal_data.get("has_multilang_apac", False),
            has_series_c_plus=signal_data.get("has_series_c_plus", False),
            has_audit_signals=signal_data.get("has_audit_signals", False),
        )

        # Step 4: Tags
        tags = self.signals.extract_tags(
            has_cfo_hire=signal_data.get("has_cfo_hire", False),
            last_raise_amount=signal_data.get("last_raise_amount_usd"),
            months_since_raise=signal_data.get("months_since_raise"),
            has_multilang=signal_data.get("has_multilang_apac", False),
            has_series_c_plus=signal_data.get("has_series_c_plus", False),
            has_audit_signals=signal_data.get("has_audit_signals", False),
            valuation_over_1b=signal_data.get("valuation_over_1b", False),
            robotics_supply_chain=signal_data.get("has_supply_chain_robotics", False),
        )

        # Step 5: Funding clock
        last_raise = signal_data.get("last_raise_amount_usd")
        months_since = signal_data.get("months_since_raise")
        funding_clock = None
        if last_raise and months_since:
            days_since = months_since * 30
            clock = FundingClock(last_raise_amount=last_raise, days_since_raise=days_since)
            burn = estimate_monthly_burn(headcount=None, sector=signal_data.get("sector"))
            funding_clock = clock.predict_funding_date(burn)

        return {
            **company,
            "sector": signal_data.get("sector", "Unknown"),
            "one_liner": one_liner,
            "signal_score": score,
            "funding_clock": funding_clock.isoformat() if funding_clock else None,
            "tags": tags,
            "last_raise_amount": f"${last_raise/1_000_000:.0f}M" if last_raise else "Unknown",
            "last_raise_date": None,
            "ai_model_used": model_name,
            "source_citation": domain,
        }

    def run(self) -> list[dict]:
        """Process all companies."""
        self._enriched = []
        for company in self.companies:
            enriched = self.process_company(company)
            self._enriched.append(enriched)
            time.sleep(random.uniform(2, 5))

        self._save()
        return self._enriched

    def _save(self):
        Path(self.output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_path, "w") as f:
            json.dump(self._enriched, f, indent=2)
        print(f"\nEnrichment complete: {len(self._enriched)} companies. Saved to {self.output_path}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_reasoner_pipeline.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/reasoner/pipeline.py tests/test_reasoner_pipeline.py
git commit -m "feat(reasoner): add reasoner pipeline with AI enrichment

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 11: Notion Client

**Files:**
- Create: `src/commander/notion_client.py`
- Create: `tests/test_notion_client.py`

- [ ] **Step 1: Write Notion client test**

```python
# tests/test_notion_client.py
from src.commander.notion_client import NotionClient

def test_notion_client_initialization():
    client = NotionClient(integration_token="test", database_id="test-db")
    assert client.database_id == "test-db"

def test_build_company_properties():
    client = NotionClient(integration_token="test", database_id="test-db")
    company = {
        "company_name": "Canvas",
        "domain": "https://canvas.co",
        "vc_source": "Blackbird",
        "sector": "B2B SaaS",
        "one_liner": "Design tool",
        "signal_score": 40,
        "tags": ["Cross-Border Target"],
        "last_raise_amount": "$12M",
        "source_citation": "https://canvas.co",
    }
    props = client.build_properties(company)
    assert "Company" in props
    assert props["Company"]["title"][0]["text"]["content"] == "Canvas"
    assert props["Signal Score"]["number"] == 40
    assert props["Tags"]["multi_select"][0]["name"] == "Cross-Border Target"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_notion_client.py -v`
Expected: FAIL — module does not exist

- [ ] **Step 3: Write NotionClient implementation**

```python
# src/commander/notion_client.py
"""Notion API client for writing enriched company records to Notion database."""
import os
import time
from notion_client import Notion as NotionLib
from notion_client.errors import APIResponseError

from datetime import date


class NotionClient:
    """Client for writing DealRadar enriched data to Notion."""

    def __init__(
        self,
        integration_token: str | None = None,
        database_id: str | None = None,
    ):
        self.integration_token = integration_token or os.getenv("NOTION_API_KEY", "")
        self.database_id = database_id or os.getenv("NOTION_DATABASE_ID", "")
        if not self.integration_token:
            raise ValueError("NOTION_API_KEY not set")
        if not self.database_id:
            raise ValueError("NOTION_DATABASE_ID not set")

        self.client = NotionLib(auth=self.integration_token)

    def build_properties(self, company: dict) -> dict:
        """Convert a company dict to Notion page properties."""
        props = {}

        props["Company"] = {
            "title": [{"text": {"content": company["company_name"][:200]}}]
        }
        props["Domain"] = {"url": company.get("domain", "")}
        props["VC Source"] = {"rich_text": [{"text": {"content": company.get("vc_source", "")}}]}
        props["Sector"] = {"rich_text": [{"text": {"content": company.get("sector", "Unknown")}}]}
        props["One-liner"] = {"rich_text": [{"text": {"content": company.get("one_liner", "")[:2000]}}]}
        props["Signal Score"] = {"number": company.get("signal_score", 0)}

        funding_clock = company.get("funding_clock")
        if funding_clock:
            props["Funding Clock"] = {"date": {"start": funding_clock}}

        tags = company.get("tags", [])
        if isinstance(tags, list):
            props["Tags"] = {"multi_select": [{"name": t} for t in tags[:10]]}

        props["Last Raise Amount"] = {"rich_text": [{"text": {"content": company.get("last_raise_amount", "Unknown")}}]}
        props["Model Used"] = {"rich_text": [{"text": {"content": company.get("ai_model_used", "Unknown")}}]}
        props["Source URL"] = {"url": company.get("source_citation", company.get("domain", ""))}
        props["Last Scraped"] = {"date": {"start": str(date.today())}}

        last_raise_date = company.get("last_raise_date")
        if last_raise_date:
            props["Last Raise Date"] = {"date": {"start": last_raise_date}}

        return props

    def page_exists_by_domain(self, domain: str) -> str | None:
        """Query Notion for existing page with matching domain. Returns page_id or None."""
        try:
            results = self.client.databases.query(
                self.database_id,
                filter={
                    "property": "Domain",
                    "url": {"equals": domain},
                },
            )
            pages = results.get("results", [])
            return pages[0]["id"] if pages else None
        except Exception:
            return None

    def create_page(self, company: dict, max_retries: int = 3) -> str:
        """Create a new Notion page for a company."""
        properties = self.build_properties(company)
        for attempt in range(max_retries):
            try:
                result = self.client.pages.create(
                    parent={"database_id": self.database_id},
                    properties=properties,
                )
                return result["id"]
            except APIResponseError:
                if attempt == max_retries - 1:
                    raise
                wait = (2 ** attempt) * 1.0
                time.sleep(wait)

    def update_page(self, page_id: str, company: dict, max_retries: int = 3):
        """Update an existing Notion page."""
        properties = self.build_properties(company)
        properties.pop("Last Scraped", None)

        for attempt in range(max_retries):
            try:
                self.client.pages.update(page_id, properties=properties)
                return
            except APIResponseError:
                if attempt == max_retries - 1:
                    raise
                wait = (2 ** attempt) * 1.0
                time.sleep(wait)

    def upsert_company(self, company: dict) -> str:
        """Insert or update a company in Notion."""
        domain = company.get("domain")
        if not domain:
            raise ValueError(f"Company {company.get('company_name')} has no domain")

        existing_id = self.page_exists_by_domain(domain)
        if existing_id:
            print(f"  Updating existing: {company['company_name']}")
            self.update_page(existing_id, company)
            return existing_id
        else:
            print(f"  Creating new: {company['company_name']}")
            return self.create_page(company)

    def push_all(self, companies: list[dict]) -> dict:
        """Push all companies to Notion with deduplication."""
        results = {"created": 0, "updated": 0, "errors": 0}
        for company in companies:
            try:
                existing = self.page_exists_by_domain(company.get("domain", ""))
                if existing:
                    results["updated"] += 1
                else:
                    results["created"] += 1
                self.upsert_company(company)
                time.sleep(0.5)  # Notion rate limit
            except Exception as e:
                print(f"  [ERROR] {company.get('company_name')}: {e}")
                results["errors"] += 1

        return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_notion_client.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/commander/notion_client.py tests/test_notion_client.py
git commit -m "feat(commander): add Notion API client with upsert logic

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 12: Weekly Digest

**Files:**
- Create: `src/commander/digest.py`
- Create: `tests/test_digest.py`

- [ ] **Step 1: Write digest test**

```python
# tests/test_digest.py
from src.commander.digest import WeeklyDigest, format_top_companies

def test_format_top_companies():
    companies = [
        {"company_name": "A Company", "signal_score": 90, "domain": "https://a.com", "tags": ["Unicorn"]},
        {"company_name": "B Company", "signal_score": 85, "domain": "https://b.com", "tags": ["Pre-IPO Watch"]},
    ]
    formatted = format_top_companies(companies)
    assert "A Company" in formatted
    assert "90" in formatted
    assert "B Company" in formatted

def test_weekly_digest_filters_by_score():
    digest = WeeklyDigest()
    companies = [
        {"company_name": "Hot", "signal_score": 85, "domain": "https://hot.com", "tags": []},
        {"company_name": "Cold", "signal_score": 5, "domain": "https://cold.com", "tags": []},
    ]
    top5 = digest.get_top_companies(companies, top_n=5)
    assert len(top5) == 1
    assert top5[0]["company_name"] == "Hot"

def test_weekly_digest_ranks_by_score():
    digest = WeeklyDigest()
    companies = [
        {"company_name": "Score60", "signal_score": 60, "domain": "https://s60.com", "tags": []},
        {"company_name": "Score90", "signal_score": 90, "domain": "https://s90.com", "tags": []},
        {"company_name": "Score75", "signal_score": 75, "domain": "https://s75.com", "tags": []},
    ]
    top5 = digest.get_top_companies(companies, top_n=5)
    assert top5[0]["company_name"] == "Score90"
    assert top5[1]["company_name"] == "Score75"
    assert top5[2]["company_name"] == "Score60"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_digest.py -v`
Expected: FAIL — module does not exist

- [ ] **Step 3: Write digest implementation**

```python
# src/commander/digest.py
"""Weekly digest: Top 5 targets delivered via email to Steven."""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import date

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.sendgrid.net")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "dealradar@dealradar.ai")
TO_EMAIL = os.getenv("TO_EMAIL", "steven@inpcapital.com")


def format_top_companies(companies: list[dict]) -> str:
    """Format Top 5 companies as HTML for email."""
    rows = []
    for i, c in enumerate(companies, 1):
        tags = ", ".join(c.get("tags", []) or [])
        row = f"""
        <tr>
            <td>{i}</td>
            <td><a href="{c.get('domain', '')}">{c.get('company_name', '')}</a></td>
            <td>{c.get('signal_score', 0)}</td>
            <td>{c.get('vc_source', '')}</td>
            <td>{c.get('sector', 'Unknown')}</td>
            <td>{c.get('funding_clock', 'N/A')}</td>
            <td>{tags}</td>
        </tr>
        """
        rows.append(row)
    return "\n".join(rows)


class WeeklyDigest:
    """Generate and send weekly Top 5 deal targets digest email."""

    def __init__(self, top_n: int = 5):
        self.top_n = top_n

    def get_top_companies(self, companies: list[dict], top_n: int | None = None) -> list[dict]:
        """Return top N companies sorted by signal score descending."""
        n = top_n or self.top_n
        sorted_companies = sorted(companies, key=lambda c: c.get("signal_score", 0), reverse=True)
        return sorted_companies[:n]

    def build_html(self, companies: list[dict]) -> str:
        """Build HTML email body."""
        table_rows = format_top_companies(companies)
        today = date.today().isoformat()

        return f"""
        <html>
        <body>
        <h2>DealRadar Weekly Digest — {today}</h2>
        <p>Your top {len(companies)} deal targets this week, ranked by Signal Score.</p>

        <table border="1" cellpadding="8" cellspacing="0">
            <thead>
                <tr>
                    <th>#</th>
                    <th>Company</th>
                    <th>Signal Score</th>
                    <th>VC Source</th>
                    <th>Sector</th>
                    <th>Funding Clock</th>
                    <th>Tags</th>
                </tr>
            </thead>
            <tbody>
                {table_rows}
            </tbody>
        </table>

        <p style="margin-top:20px">
        <em>Generated by DealRadar MVP — INP Capital</em>
        </p>
        </body>
        </html>
        """

    def send_email(self, companies: list[dict], subject: str | None = None) -> bool:
        """Send digest email via SMTP/SendGrid."""
        if not SMTP_USER or not SMTP_PASS:
            print("[WARN] SMTP credentials not configured. Skipping email send.")
            print(f"Digest preview:\n{self.build_html(companies)}")
            return False

        to = TO_EMAIL or os.getenv("TO_EMAIL", "")
        if not to:
            print("[WARN] TO_EMAIL not configured")
            return False

        subject = subject or f"DealRadar Weekly Digest — {date.today().isoformat()}"
        html_body = self.build_html(companies)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = FROM_EMAIL
        msg["To"] = to
        msg.attach(MIMEText(html_body, "html"))

        try:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASS)
                server.send_message(msg)
            print(f"  Digest sent to {to}")
            return True
        except Exception as e:
            print(f"  [ERROR] Failed to send email: {e}")
            return False

    def run(self, enriched_companies_path: str = "data/enriched_companies.json") -> bool:
        """Load enriched companies, generate digest, send email."""
        import json
        with open(enriched_companies_path) as f:
            companies = json.load(f)

        top5 = self.get_top_companies(companies)
        print(f"\nTop {len(top5)} targets this week:")
        for c in top5:
            print(f"  [{c['signal_score']}] {c['company_name']} — {c.get('vc_source', '')}")

        return self.send_email(top5)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_digest.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/commander/digest.py tests/test_digest.py
git commit -m "feat(commander): add weekly digest email generator

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 13: End-to-End Integration

**Files:**
- Modify: `run.py` — integrate all 3 phases
- Create: `.env.example`

- [ ] **Step 1: Update run.py to integrate all phases**

```python
# run.py (updated)
"""DealRadar CLI — orchestrates all 3 phases."""
import argparse
import json
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from src.harvester.pipeline import HarvesterPipeline
from src.reasoner.pipeline import ReasonerPipeline
from src.commander.notion_client import NotionClient
from src.commander.digest import WeeklyDigest


def run_harvest(output_path: str = "data/raw_companies.json"):
    print("=" * 60)
    print("PHASE 1: HARVEST — Scraping VC portfolios")
    print("=" * 60)
    pipeline = HarvesterPipeline(
        vc_seeds_path="config/vc_seeds.json",
        output_path=output_path,
    )
    companies = pipeline.run()
    print(f"Harvested {len(companies)} companies")
    return companies


def run_reason(
    raw_path: str = "data/raw_companies.json",
    output_path: str = "data/enriched_companies.json",
):
    print("\n" + "=" * 60)
    print("PHASE 2: REASON — AI enrichment & signal scoring")
    print("=" * 60)
    pipeline = ReasonerPipeline(
        raw_companies_path=raw_path,
        output_path=output_path,
    )
    enriched = pipeline.run()
    print(f"Enriched {len(enriched)} companies")
    return enriched


def run_push(
    enriched_path: str = "data/enriched_companies.json",
):
    print("\n" + "=" * 60)
    print("PHASE 3: PUSH — Writing to Notion")
    print("=" * 60)
    with open(enriched_path) as f:
        companies = json.load(f)

    client = NotionClient()
    results = client.push_all(companies)
    print(f"Created: {results['created']}, Updated: {results['updated']}, Errors: {results['errors']}")
    return results


def run_digest(enriched_path: str = "data/enriched_companies.json"):
    print("\n" + "=" * 60)
    print("SENDING WEEKLY DIGEST")
    print("=" * 60)
    digest = WeeklyDigest()
    digest.run(enriched_path)


def main():
    parser = argparse.ArgumentParser(description="DealRadar MVP CLI")
    parser.add_argument(
        "--phase",
        choices=["harvest", "reason", "push", "digest", "all"],
        default="all",
        help="Which phase(s) to run",
    )
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args()

    os.makedirs(args.data_dir, exist_ok=True)
    raw_path = f"{args.data_dir}/raw_companies.json"
    enriched_path = f"{args.data_dir}/enriched_companies.json"

    if args.phase in ("harvest", "all"):
        run_harvest(raw_path)

    if args.phase in ("reason", "all"):
        run_reason(raw_path, enriched_path)

    if args.phase in ("push", "all"):
        run_push(enriched_path)

    if args.phase in ("digest", "all"):
        run_digest(enriched_path)

    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Create .env.example**

```bash
# .env.example — Copy to .env and fill in your API keys

# Jina Reader API (https://jina.ai/reader)
JINA_API_KEY=

# Apify (https://apify.com) — optional fallback
APIFY_API_TOKEN=

# AI Model Providers (at least one required)
GEMINI_API_KEY=
KIMI_API_KEY=
GLM_API_KEY=
OPENAI_API_KEY=

# Notion (https://www.notion.so)
NOTION_API_KEY=
NOTION_DATABASE_ID=

# Email (SMTP or SendGrid)
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASS=
FROM_EMAIL=dealradar@dealradar.ai
TO_EMAIL=steven@inpcapital.com
```

- [ ] **Step 3: Commit**

```bash
git add run.py .env.example
git commit -m "feat: integrate full pipeline in run.py CLI

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 14: CLAUDE.md

**Files:**
- Create: `CLAUDE.md`

- [ ] **Step 1: Write CLAUDE.md**

```markdown
# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DealRadar is a predictive deal intelligence CRM — an automated pipeline that scrapes VC portfolio pages, enriches company data with AI signal analysis, and outputs actionable intelligence to Notion CRM.

## Tech Stack

- **Language:** Python 3.11+
- **Scraping:** Jina Reader API (primary), Apify (fallback for JS-rendered pages)
- **AI:** Multi-model chain — Google Gemini -> Kimi K2.5 -> GLM 4.6v -> OpenAI GPT-4o-mini
- **Output:** Notion API
- **Email:** SMTP/SendGrid

## Key Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env with your API keys

# Run full pipeline
python run.py --phase=all

# Run individual phases
python run.py --phase=harvest   # Scrape VC portfolios -> data/raw_companies.json
python run.py --phase=reason    # AI enrichment -> data/enriched_companies.json
python run.py --phase=push      # Write to Notion
python run.py --phase=digest     # Send weekly email digest

# Run tests
pytest tests/ -v
pytest tests/test_harvester_pipeline.py -v
pytest tests/test_reasoner_pipeline.py -v
pytest tests/test_commander.py -v
```

## Architecture

3-module pipeline:

```
VC Portfolio Pages
       |
Harvester (Jina + Apify) -> data/raw_companies.json
       |
AI Reasoner (multi-model chain) -> data/enriched_companies.json
       |
Commander (Notion API + email digest)
```

## Project Structure

- `src/harvester/` — Data collection (Jina, Apify, extraction)
- `src/reasoner/` — AI enrichment (models, signals, funding clock, summarizer)
- `src/commander/` — Output layer (Notion, email digest)
- `config/vc_seeds.json` — List of VC URLs to scrape
- `data/` — Runtime data (raw and enriched JSON)
- `run.py` — CLI entry point

## Signal Scoring Rules (Mutually Exclusive)

Only the highest matching condition applies:

| Condition | Score |
|-----------|-------|
| CFO / General Counsel hire detected | 40 |
| Last raise $10-20M + >15 months ago | 30 |
| Last raise >18 months ago | 30 |
| Multi-language / APAC mentions | 20 |
| Series C+ stage | 15 |
| SOC2 / ESG / Big 4 auditor mentions | 15 |

## Notion Database Setup

Create a Notion database with these properties:
- Company (Title)
- Domain (URL)
- VC Source (Text)
- Sector (Text)
- One-liner (Text)
- Signal Score (Number)
- Funding Clock (Date)
- Tags (Multi-select)
- Last Raise Amount (Text)
- Last Raise Date (Date)
- Last Scraped (Date)
- Source URL (URL)
- Model Used (Text)
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add CLAUDE.md with project overview and commands

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```
