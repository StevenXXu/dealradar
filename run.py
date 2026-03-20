# run.py
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
    print("=" * 60, flush=True)
    print("PHASE 1: HARVEST — Scraping VC portfolios", flush=True)
    print("=" * 60, flush=True)
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


import sys
sys.stdout.reconfigure(encoding='utf-8')

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
