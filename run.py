# run.py
"""DealRadar CLI — orchestrates all 3 phases."""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from src.harvester.pipeline import HarvesterPipeline
from src.reasoner.pipeline import ReasonerPipeline
from src.commander.notion_client import NotionClient
from src.commander.digest import WeeklyDigest
from src.commander.history import (
    archive_enriched, load_latest_history, detect_raises,
    should_suppress_alert, record_alert_fired, purge_old_alerts,
)
from src.commander.alerts import check_serpapi, send_raise_alert_email


def run_harvest(output_path: str = "data/raw_companies.json", force_restart: bool = False):
    print("=" * 60, flush=True)
    print("PHASE 1: HARVEST — Scraping VC portfolios", flush=True)
    print("=" * 60, flush=True)
    pipeline = HarvesterPipeline(
        vc_seeds_path="config/vc_seeds.json",
        output_path=output_path,
    )
    companies = pipeline.run(force_restart=force_restart)
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
    print(f"Created: {results['created']}, Updated: {results['updated']}, Skipped (unchanged): {results['skipped']}, Errors: {results['errors']}")
    return results


def run_digest(enriched_path: str = "data/enriched_companies.json"):
    print("\n" + "=" * 60)
    print("SENDING WEEKLY DIGEST")
    print("=" * 60)
    digest = WeeklyDigest()
    digest.run(enriched_path)


def run_archive_and_raise(enriched_path: str) -> list[dict]:
    """
    Archive enriched companies → detect raises vs previous history → return raise events.
    Archive runs AFTER push (push wrote to Notion without raise flags this cycle).
    Raise detection uses the previous archive as the baseline.
    """
    with open(enriched_path) as f:
        companies = json.load(f)

    year_month = datetime.now().strftime("%Y-%m")

    # Purge old alerts (30-day window)
    removed = purge_old_alerts()
    if removed > 0:
        print(f"  Purged {removed} expired alert entries")

    # Group companies by VC slug for archive/detection
    slug_to_companies: dict[str, list[dict]] = {}
    for c in companies:
        slug = c.get("slug", "unknown")
        slug_to_companies.setdefault(slug, []).append(c)

    all_raises = []

    for slug, vc_companies in slug_to_companies.items():
        # Load PREVIOUS archive (before this run) as baseline
        previous, _ = load_latest_history(slug)

        # Archive current run AFTER push, before/during raise detection
        # Note: This archive becomes the baseline for next run's detection
        archive_enriched(vc_companies, slug, year_month)

        # Detect raises against previous archive (not current)
        if previous is not None:
            raises = detect_raises(vc_companies, previous)
            all_raises.extend(raises)

    print(f"\nRaise detection: {len(all_raises)} raise events found")
    for r in all_raises:
        print(f"  [{r['signal_score']}] {r['company_name']} — {r.get('previous_date', '?')} → {r.get('current_date', '?')}")

    return all_raises


def run_alerts(raise_events: list[dict]) -> dict:
    """
    For each raise event: check suppression → SerpAPI → update Notion + send email.
    Notion update is a direct update_page() call, not a full re-push.
    """
    print("\n" + "=" * 60)
    print("PROCESSING RAISE ALERTS")
    print("=" * 60)

    results = {"alerts_sent": 0, "alerts_suppressed": 0, "alerts_degraded": 0}

    for event in raise_events:
        domain = event["domain"]

        # 1. Suppression check
        if should_suppress_alert(domain):
            print(f"  [SUPPRESSED] {event['company_name']} — alert fired within 30 days")
            results["alerts_suppressed"] += 1
            continue

        # 2. SerpAPI corroboration
        has_news = check_serpapi(domain, event["company_name"])

        # 3. Update Notion (direct update — only for companies that raised)
        notion_client = NotionClient()
        page_id = notion_client.page_exists_by_domain(domain)
        if page_id:
            today = str(datetime.now().date())
            try:
                notion_client.client.pages.update(
                    page_id,
                    properties={
                        "Raise Alert Fired": {"checkbox": True},
                        "Last Alert Date": {"date": {"start": today}},
                    }
                )
                print(f"  [NOTION] Updated Raise Alert Fired for {event['company_name']}")
            except Exception as e:
                print(f"  [ERROR] Failed to update Notion for {event['company_name']}: {e}")

        # 4. Send email if corroborated
        if has_news:
            sent = send_raise_alert_email(event)
            if sent:
                record_alert_fired(domain, event["company_name"])
                results["alerts_sent"] += 1
            else:
                print(f"  [DEGRADED] Email send failed for {event['company_name']} — Notion tag only")
                results["alerts_degraded"] += 1
        else:
            print(f"  [DEGRADED] No SerpAPI corroboration for {event['company_name']} — Notion tag only")
            results["alerts_degraded"] += 1

    print(f"  → Sent: {results['alerts_sent']}, Suppressed: {results['alerts_suppressed']}, Degraded: {results['alerts_degraded']}")
    return results


sys.stdout.reconfigure(encoding='utf-8')

def main():
    parser = argparse.ArgumentParser(description="DealRadar MVP CLI")
    parser.add_argument(
        "--phase",
        choices=["harvest", "reason", "push", "digest", "all"],
        default="all",
        help="Which phase(s) to run",
    )
    parser.add_argument(
        "--force-restart",
        action="store_true",
        help="Clear harvest state and re-scrape all VCs from scratch",
    )
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args()

    os.makedirs(args.data_dir, exist_ok=True)
    raw_path = f"{args.data_dir}/raw_companies.json"
    enriched_path = f"{args.data_dir}/enriched_companies.json"

    if args.phase in ("harvest", "all"):
        run_harvest(raw_path, force_restart=args.force_restart)

    if args.phase in ("reason", "all"):
        run_reason(raw_path, enriched_path)

    if args.phase in ("push", "all"):
        run_push(enriched_path)  # Push WITHOUT raise flags (no history to compare yet)

        if args.phase == "all":
            # Archive (after push, for next run's baseline) → raise detection
            raise_events = run_archive_and_raise(enriched_path)

            # Send raise alerts and update Notion
            if raise_events:
                run_alerts(raise_events)

    if args.phase in ("digest", "all"):
        run_digest(enriched_path)

    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)


if __name__ == "__main__":
    main()
