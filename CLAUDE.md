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
