# DealRadar MVP - Design Specification

**Date:** 2026-03-19
**Project:** DealRadar - Predictive Deal Intelligence CRM
**Status:** Revised (v2 — fixed funding clock data source, signal scoring overlap, tag format, dead filter criteria, token truncation criteria, digest format)

---

## 1. Overview

DealRadar MVP is an automated pipeline that scrapes VC portfolio pages, enriches company data with AI signal analysis, and outputs actionable intelligence to Notion CRM. The system predicts when portfolio companies will seek their next funding round and flags cross-border expansion signals.

**Core Value:** Convert public "weak signals" (hiring patterns, website updates, funding history) into deterministic deal flow intelligence 3-6 months before a raise is public.

---

## 2. Architecture

### 2.1 Three-Module Pipeline

```
VC Portfolio Pages
       ↓
┌─────────────────┐
│   Harvester     │  Jina Reader API (primary)
│   (Module A)    │  Apify (fallback for JS-rendered sites)
└────────┬────────┘
         ↓
┌─────────────────┐
│   AI Reasoner   │  Multi-model chain: Gemini → Kimi K2.5 → GLM 4.6v → OpenAI
│   (Module B)    │  Signal extraction, funding clock, semantic compression
└────────┬────────┘
         ↓
┌─────────────────┐
│   Commander     │  Notion API (primary output)
│   (Module C)    │  Deduplication, rate limiting, retry logic
└─────────────────┘
```

### 2.2 Seed VC List (Phase 1 - AUS)

| VC Firm | Portfolio URL |
|---------|---------------|
| Blackbird | blackbird.vc |
| Square Peg | squarepeg.vc |
| AirTree | airtree.vc |
| Folklore | folklore.vc |
| Sprint Ajax | sprintajax.com |
| TEN13 | ten13.com |
| Alto | alto.capital |
| Rampersand | rampersand.com |
| Base Capital | basecapital.com.au |
| Candour | candour.vc |

---

## 3. Module Specifications

### 3.1 Harvester (Module A)

**Purpose:** Extract company names and domains from VC portfolio pages.

**Tech Stack:**
- Jina Reader API (`https://r.jina.ai/https://{url}`) — primary text extraction
- Apify (`apify.com`) — fallback for JavaScript-rendered pages

**Process:**
1. Load seed list of 10 VC portfolio URLs
2. For each VC URL:
   - Attempt Jina Reader API first (scrapes VC portfolio page, e.g., `blackbird.vc/portfolio`)
   - If Jina fails or detects JS content, fall back to Apify
   - Extract: Company Name, Domain URL, Investment Stage (if available)
3. Output: JSON array of `{vc_source, company_name, domain, stage, scraped_at}`
4. Apply basic filtering: remove dead companies (HTTP 404), IPOs, acquired entities (detected via URL redirects or "acquired by" in page text)

**Note:** The Harvester extracts company domains from VC portfolio pages. The AI Reasoner then scrapes each individual company website (a separate URL) to extract funding history, hiring signals, and business context. This is why Jina is called twice — once per VC page, once per company page.

**Rate Limiting:** 2-5 second random jitter between requests

**Output Schema:**
```json
{
  "vc_source": "Blackbird",
  "company_name": "Canvas",
  "domain": "https://canvas.co",
  "stage": "Series A",
  "scraped_at": "2026-03-19T12:00:00Z"
}
```

### 3.2 AI Reasoner (Module B)

**Purpose:** Enrich raw company data with AI-analyzed signals and predicted funding timeline.

**Tech Stack:** Multi-model fallback chain
1. Google Gemini (primary)
2. Kimi K2.5 (fallback 1)
3. GLM 4.6v (fallback 2)
4. OpenAI GPT-4o-mini (final fallback)

**Process for each company:**
1. **Text Extraction:** Send company domain to Jina Reader API → get clean markdown from About, News, Careers pages
2. **Semantic Compression:** AI model summarizes to <100 word one-liner
3. **Signal Extraction:** Detect keywords (CFO, VP Finance, Global Expansion, Series B, etc.)
4. **Funding History Extraction:** AI parses the scraped text for last raise amount and date (e.g., "raised $12M Series A in September 2024"). If not found in text, mark `last_raise_amount` and `last_raise_date` as "Unknown" — funding clock cannot be calculated without this data.
5. **Funding Clock Calculation:**
   ```
   Monthly Burn ≈ Headcount × (Industry Avg Salary × 1.3 overhead)
   Days Remaining ≈ (Last Round Amount / Monthly Burn) - Days Since Last Round
   ```
   *Note: Headcount estimated from company careers page or "About Us" text. If unavailable, use sector median.*
6. **Tag Assignment:** Based on detected signals

**Signal Scoring Rules (mutually exclusive — only highest applies):**
| Condition | Points |
|-----------|--------|
| Hiring CFO / General Counsel | +40 |
| Last raise $10-20M AND >15 months ago | +30 |
| Last raise >18 months ago | +30 |
| Multi-language website / APAC mentions | +20 |
| Series C+ stage | +15 |
| SOC2 / ESG / Big 4 auditor mentions | +15 |

**Scoring Logic:** Rules are evaluated top-to-bottom. Only the **highest matching condition** applies (no stacking). This prevents inflated scores from overlapping conditions.

**Tag Definitions (emojis are visual markers in docs only — Notion output uses plain text):**
- `Unicorn` — Valuation >$1B or single round >$100M
- `Pre-IPO Watch` — Series C+, CFO hire, audit signals
- `Cross-Border Target` — Multiple office locations, international hiring
- `Funding Urgency High` — $10-20M last raise, >15 months elapsed
- `Venture Nexus` — Supply chain hire in Robotics/Hardware

**Token Control:** Max 4K tokens input per company. Truncate long pages to first 20 `<p>` tags by DOM order (simple and deterministic).

**Output Schema:**
```json
{
  "company_name": "Canvas",
  "domain": "https://canvas.co",
  "vc_source": "Blackbird",
  "sector": "B2B SaaS",
  "one_liner": "Project management tool for enterprise design teams...",
  "signal_score": 72,
  "funding_clock": "2026-06-15",
  "tags": ["Cross-Border Target", "Funding Urgency High"],
  "last_raise_amount": "$12M",
  "last_raise_date": "2024-09-01",
  "ai_model_used": "gemini-2.0-flash",
  "source_citation": "https://canvas.co/about"
}
```

### 3.3 Commander (Module C)

**Purpose:** Write enriched company records to Notion and manage the output pipeline.

**Tech Stack:** Notion API

**Notion Database Schema:**
| Field Name | Type | Notes |
|------------|------|-------|
| Company | Title | Company name |
| Domain | URL | Company website |
| VC Source | Text | Origin VC |
| Sector | Text | Industry classification |
| One-liner | Text | AI summary |
| Signal Score | Number | 0-100 |
| Funding Clock | Date | Predicted next raise |
| Tags | Multi-select | Signal tags |
| Last Raise Amount | Text | e.g., "$12M Series A" |
| Last Raise Date | Date | |
| Last Scraped | Date | |
| Source URL | URL | Verification link |
| Model Used | Text | Which AI model generated |

**Logic:**
1. Check if company already exists in Notion (by domain)
2. If exists: update record, preserve original scrape date
3. If new: create record
4. If Signal Score > 80: trigger high-priority flag for immediate review

**Retry Logic:** 3 retries with exponential backoff (1s, 2s, 4s)

---

## 4. MVP Phases

### Phase 1: Environment & Seed Scrape (Days 1-2)
- [ ] Set up project structure (Python + virtualenv)
- [ ] Configure API keys (Jina, Apify, Notion, AI providers)
- [ ] Build Harvester v1 — scrape 10 AUS VC portfolios
- [ ] Output: `data/raw_companies.json`

### Phase 2: AI Enrichment (Days 3-5)
- [ ] Integrate multi-model AI chain
- [ ] Implement signal scoring algorithm
- [ ] Implement funding clock calculation
- [ ] Add token truncation and cost controls
- [ ] Output: `data/enriched_companies.json`

### Phase 3: Notion Integration & Digest (Days 6-7)
- [ ] Create Notion database with schema
- [ ] Build Commander module — write to Notion
- [ ] Build weekly digest generator — Top 5 targets, delivered as email (SMTP/SendGrid) to Steven
- [ ] End-to-end test

---

## 5. Project Structure

```
dealradar/
├── src/
│   ├── __init__.py
│   ├── harvester/
│   │   ├── __init__.py
│   │   ├── jina_client.py      # Jina Reader API
│   │   ├── apify_client.py     # Apify fallback
│   │   └── extractor.py        # Company extraction logic
│   ├── reasoner/
│   │   ├── __init__.py
│   │   ├── models.py           # Multi-model chain
│   │   ├── signals.py          # Signal detection rules
│   │   ├── funding_clock.py    # Burn rate & timing
│   │   └── summarizer.py       # Semantic compression
│   └── commander/
│       ├── __init__.py
│       ├── notion_client.py    # Notion API
│       └── digest.py           # Weekly report generator
├── data/
│   ├── raw_companies.json
│   └── enriched_companies.json
├── config/
│   └── vc_seeds.json          # List of VC URLs to scrape
├── tests/
├── docs/
├── CLAUDE.md
├── requirements.txt
└── run.py                      # Main entry point
```

---

## 6. Exception Handling & Guardrails

1. **Rate Limiting:** 2-5s random jitter between all external API calls
2. **Source Citations:** Every AI-generated field includes the source URL
3. **Token Control:** Hard 4K token limit per company; truncate long pages
4. **Dead Company Filter:** Skip companies that are acquired, IPO'd, or defunct. Detection: HTTP 404/410 response, "acquired by" or "IPO" text on homepage, or URL redirects to a different domain
5. **Model Fallback:** If primary model fails, try next in chain; log which model succeeded
6. **Retry Logic:** Exponential backoff (1s, 2s, 4s) for transient failures

---

## 7. Out of Scope (v1)

- LinkedIn hiring signal scraping (use Proxycurl/Coresignal in v2)
- Real-time monitoring / webhooks
- Multi-language expansion beyond AUS/US/Asia seed
- Airtable support (Notion only for MVP)
- User authentication / multi-tenant SaaS
