# DealRadar: VC Portfolio Tracking & Cross-Border CRM

## 1. System Overview
An automated pipeline to scrape VC/PE portfolio pages, enrich the data with AI, predict future fundraising timelines, and flag cross-border business opportunities.

## 2. The 4-Step Architecture

### Step 1: The Harvester (Data Capture)
- **Input:** URL of a VC's portfolio page (e.g., Sequoia, a16z, Blackbird).
- **Process:** An AI agent (using Scrapling/Apify or Vision LLM) parses the grid/list.
- **Output:** Company Name, Website URL, and (if available) Investment Stage/Year.

### Step 2: The Enricher (Deep Context)
- **Action:** The system automatically visits the target company's URL.
- **Data Extracted:**
  - One-sentence pitch (What do they do?)
  - Industry/Sector (e.g., PropTech, Biotech, SaaS)
  - Key personnel (Founders)
  - *Crucial for Cross-Border:* Do they have offices in multiple countries? Are they hiring internationally? (Scraping the "Careers" or "About" page).

### Step 3: The Predictor (The Funding Clock)
- **Action:** Query external sources (Google News / Crunchbase API / PR Newswire) for "[Company Name] funding round".
- **Logic:** Find the date of their last funding round (e.g., Series A in Jan 2025).
- **The Trigger:** Add 18-24 months to the last funding date. This becomes the "Next Anticipated Raise" date.
- **CRM Automation:** The CRM automatically sets an alert 3 months *before* that date for Steven to initiate contact.

### Step 4: The Analyst (Internal Integration)
- **Action:** Feed the enriched data into INP's existing AI project analysis tool (e.g., SoloAnalyst).
- **Output:** A standardized 1-page memo grading the company, stored in the CRM.

## 3. The "Cross-Border" Playbook (How to use this)
Why track this? Because a US company raising a Series B usually needs to show international expansion.
- **The Hook:** Reach out 4 months before their Series B.
- **The Pitch:** "Saw you raised Series A 14 months ago and have great traction in the US. As you look towards Series B, APAC expansion will be a key narrative. INP Capital specializes in cross-border scaling and funding. Let's talk about your Asia-Pac strategy."

## 4. MVP Tech Stack
- **Data Scraping:** Apify (for parsing VC dynamic sites) or Jina Reader (for reading target sites).
- **AI Processing:** GPT-4o-mini / Gemini Flash (cheap, fast summarization).
- **Database:** Airtable or Notion (Easy Kanban views, sorting by "Time to Next Funding").
- **Automation:** Make.com or n8n to tie it all together.
