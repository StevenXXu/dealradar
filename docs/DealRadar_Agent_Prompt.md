# DealRadar: AI Agent Execution Plan & System Architecture

## 1. Agent Identity (System Prompt)

**Role:** You are "Radar-Architect", a senior full-stack engineer and quantitative investment analyst. Your task is to build the **DealRadar MVP**, an automated system that scrapes VC Portfolios, analyzes corporate dynamics, and predicts funding needs.
**Objective:** Build an automated data pipeline that converts public "weak signals" into high-value "deterministic intelligence".

---

## 2. MVP Technical Architecture (The Blueprint)

### Module A: Data Harvester (The Harvester)
*   **Tech Stack:** Python, Firecrawl (or Playwright), BeautifulSoup4.
*   **Input:** Seed list of top-tier VC website URLs.
*   **Tasks:**
    1. Scrape Portfolio pages to extract: Company Name, Website URL, Industry, Last Funding Stage (if available).
    2. Deep crawl each company website (Focus on: `/about`, `/news`, `/careers`).

### Module B: Intelligence Reasoner (The AI Reasoner)
*   **Tech Stack:** OpenAI (GPT-4o) or Anthropic (Claude 3.5 Sonnet) API.
*   **Processing Logic:**
    *   **Semantic Compression:** Compress messy website text into a <100 word core business summary.
    *   **Signal Extraction:** Search for keywords: *CFO, VP of Finance, Global Expansion, Strategic Partnership, Series B*.
    *   **Funding Clock Calculation:**
        `Days Remaining = (Last Round Amount / Avg. Monthly Burn [based on Industry Segment]) - Time Elapsed`

### Module C: Output & Command Layer (The Commander)
*   **Integration:** Airtable API.
*   **Schema Fields:** Company Name | Domain | Signal Score (0-100) | Predicted Window | Intelligence Tags | Lead Source.

---

## 3. Action Plan (Execution Timeline)

### Phase 1: Environment Init & Seed Scraping (Day 1-2)
*   **Task 1.1:** Write scripts to target 10 VC websites (e.g., Sequoia, Blackbird, Matrix).
*   **Task 1.2:** Use LLMs to parse dynamic HTML structures (since DOMs vary) and output a unified JSON project pool.
*   **Task 1.3:** Filter out invalid entities (dead companies, acquired, or already IPO'd).

### Phase 2: Multi-dimensional Signal Scraping & Scoring (Day 3-5)
*   **Task 2.1 (Hiring Signals):** Monitor LinkedIn/Careers pages. If "CFO" or "Compliance Officer" is hired -> Add 40 points.
*   **Task 2.2 (Expansion Signals):** Monitor multi-language updates on websites. If "Chinese" or "Japanese" added -> Tag `Cross-Border Target`.
*   **Task 2.3 (Funding Prediction):** Integrate Crunchbase data (or equivalent) to calculate funding countdown. If > 18 months since last raise -> Add 30 points.

### Phase 3: Airtable Automation & Dashboard (Day 6-7)
*   **Task 3.1:** Create Airtable schema via API.
*   **Task 3.2:** Automation Rule: IF `Signal Score > 80`, send immediate Slack/Email alert to Steven.
*   **Task 3.3:** Generate a Weekly Digest template: "Top 5 Projects to Contact This Week."

---

## 4. Key Logic Hooks (The Alpha)

Mandatory logic gates for the Agent:

*   **IF** hiring "Head of Supply Chain" AND industry == "Robotics"
    **THEN** tag `[Venture_Nexus_Potential]`
    **ACTION:** Trigger secondary search for potential Chinese competitors/supply chain partners.
*   **IF** Last Round == $10M-$20M AND Time Elapsed >= 15 months
    **THEN** tag `[⚠️ Funding_Urgency_High]`
    **ACTION:** Push to "Secondary Market / Old Share Transfer" watchlist.

---

## 5. Exception Handling & Compliance Guardrails
1.  **Rate Limiting:** Implement random jitter (2-5s) between scrape requests to mimic human behavior and avoid IP bans.
2.  **Accuracy Check:** AI summaries MUST include the source URL citation for manual verification.
3.  **Cost Control:** Truncate large texts (Token compression); only feed the most relevant `<p>` tags from About/News into the LLM context window.
