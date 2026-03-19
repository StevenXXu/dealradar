# DealRadar MVP - Internal Use & Pre-IPO Unicorn Tracker

## 1. MVP Scope (Internal First)
Before selling to others, DealRadar must be battle-tested by INP Capital.
*   **Goal:** Replace manual deal sourcing and tracking with an automated, AI-enriched database.
*   **Initial Focus:** Scrape 10-20 top-tier VC portfolios (US, AUS, Asia) relevant to INP's thesis (e.g., PropTech, DeepTech, AI).
*   **Core MVP Output:** A centralized Notion or Airtable database where every row is a portfolio company, enriched with AI summaries, funding dates, and actionable tags.

## 2. The "Pre-IPO Unicorn" Discovery Engine
Adding this layer makes the tool immensely valuable for late-stage secondary investments or pre-IPO rounds.

### How to identify and tag "Unicorn / Pre-IPO" candidates during the scrape:
1.  **Valuation Signals (The "Unicorn" Tag):**
    *   *Trigger:* When querying recent news/funding API, if "Valuation > $1B" or "Raised > $100M in a single round" is detected.
    *   *Action:* Auto-tag the company as `🦄 Unicorn`.
2.  **Maturity Signals (The "Pre-IPO Watchlist" Tag):**
    *   *Trigger A (Funding Stage):* Company is at Series C, D, or later.
    *   *Trigger B (Executive Hiring):* The AI scraper detects the hiring of a new "Chief Financial Officer (CFO)" with public market experience, or a "General Counsel." (This is the classic 12-18 month pre-IPO signal).
    *   *Trigger C (Audit/Compliance):* Press releases mentioning "SOC2 Type II", "Big 4 Auditor appointed", or "ESG compliance."
    *   *Action:* Auto-tag the company as `📈 Pre-IPO Watch`.
3.  **The Play:** INP can use this list to source secondary shares from early employees/founders who want liquidity before the IPO, or participate in the final crossover/Pre-IPO funding round.

## 3. The MVP Workflow (Action Plan)

### Step 1: The Input List (Seed Data)
- Compile a list of 10 target VC firm website URLs (e.g., Blackbird Ventures portfolio page, Square Peg, Sequoia Capital).

### Step 2: The Scrape & Extract (Apify/Scrapling)
- Build a script that visits the VC URL and extracts all the company names and their website links. (This is often tricky because VCs use dynamic loading grids).

### Step 3: AI Enrichment (The Brain)
- For every extracted company link, pass the URL to `jina.ai` (to extract readable text) and then to `gemini-3.1-pro-preview` or `gpt-4o-mini` with a strict JSON schema prompt:
  ```json
  {
    "company_name": "string",
    "one_liner": "string",
    "sector": "string",
    "is_cross_border_potential": "boolean (based on multiple office locations)",
    "pre_ipo_signals": "boolean (Series C+, heavy executive hiring)"
  }
  ```

### Step 4: External Data Overlay (Funding & News)
- Query an external API (like Crunchbase, or even a targeted Google Custom Search) for "[Company Name] funding" to get the last raised amount and date.
- Calculate: `Months Since Last Raise`. If > 18, flag as `⚠️ Seeking Capital`.

### Step 5: The INP Internal Dashboard
- Push this JSON data via API into an INP Airtable base.
- Setup views:
  - "Hot Cross-Border Targets"
  - "Pre-IPO Unicorn Watchlist"
  - "Approaching Funding Cliff (Next 3 Months)"

## Next Actions for Steven
1.  Provide 2-3 specific VC website URLs (e.g., Blackbird, AirTree) you want to use as the initial test subjects.
2.  Confirm if Airtable or Notion is the preferred internal database for INP Capital's team to view this.
