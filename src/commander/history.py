"""History + raise detection module.

Phase order within --phase=all:
  harvest → reason → push → archive → raise detection → alerts
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

DATA_DIR = Path("data")
HISTORY_DIR = DATA_DIR / "history"
ALERTS_FILE = HISTORY_DIR / "alerts_fired.jsonl"


def archive_enriched(
    enriched_companies: list[dict],
    slug: str,
    year_month: str,  # "YYYY-MM"
) -> None:
    """
    Archive enriched companies to history for later raise detection.
    Writes to data/history/{YYYY-MM}/{slug}.json.
    """
    archive_dir = DATA_DIR / "history" / year_month
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / f"{slug}_companies.json"

    with open(archive_path, "w") as f:
        json.dump(enriched_companies, f, indent=2)


def load_latest_history(vc_slug: str) -> tuple[Optional[list[dict]], str]:
    """
    Load the most recent history file for a given VC slug.
    Returns (companies, year_month) or (None, "") if no history found.
    """
    if not HISTORY_DIR.exists():
        return None, ""

    history_files = sorted(
        HISTORY_DIR.glob(f"*/{vc_slug}_companies.json"),
        key=lambda p: p.parent.name,
        reverse=True,
    )

    if not history_files:
        return None, ""

    latest = history_files[0]
    year_month = latest.parent.name
    with open(latest) as f:
        return json.load(f), year_month


def detect_raises(
    current_companies: list[dict],
    previous_companies: list[dict],
) -> list[dict]:
    """
    Compare current enriched companies against last archived run.
    Raise event: company exists in both AND last_raise_date is newer in current.
    Returns list of raise event dicts: {domain, company_name, previous_date, current_date}.
    """
    previous_by_domain = {
        c["domain"]: c.get("last_raise_date") for c in previous_companies
    }

    raises = []
    for company in current_companies:
        domain = company["domain"]
        current_date = company.get("last_raise_date")

        if not current_date:
            continue

        previous_date = previous_by_domain.get(domain)
        if previous_date is None:
            continue

        if _parse_date(current_date) > _parse_date(previous_date):
            raises.append({
                "domain": domain,
                "company_name": company.get("company_name"),
                "vc_source": company.get("vc_source"),
                "previous_date": previous_date,
                "current_date": current_date,
                "last_raise_amount": company.get("last_raise_amount"),
                "signal_score": company.get("signal_score"),
                "one_liner": company.get("one_liner"),
            })

    return raises


def _parse_date(date_str: str) -> datetime:
    """Parse date string (various formats) to datetime for comparison."""
    for fmt in ["%Y-%m-%d", "%B %Y", "%b %Y", "%Y-%m"]:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return datetime.min


def should_suppress_alert(domain: str) -> bool:
    """Check if a raise alert was already fired for this domain within 30 days."""
    if not ALERTS_FILE.exists():
        return False

    cutoff = datetime.utcnow() - timedelta(days=30)
    with open(ALERTS_FILE) as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                if entry.get("domain") == domain:
                    alert_date_str = entry["date"].replace("Z", "+00:00")
                    alert_date = datetime.fromisoformat(alert_date_str)
                    # Make naive for comparison with cutoff
                    if alert_date.tzinfo is not None:
                        alert_date = alert_date.replace(tzinfo=None)
                    if alert_date > cutoff:
                        return True
            except (json.JSONDecodeError, ValueError):
                continue
    return False


def record_alert_fired(domain: str, company_name: str) -> None:
    """Append an alert entry to alerts_fired.jsonl."""
    ALERTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(ALERTS_FILE, "a") as f:
        f.write(json.dumps({
            "domain": domain,
            "company": company_name,
            "date": datetime.utcnow().isoformat(),
        }) + "\n")


def purge_old_alerts() -> int:
    """Remove alert entries older than 30 days. Returns number removed."""
    if not ALERTS_FILE.exists():
        return 0

    cutoff = datetime.utcnow() - timedelta(days=30)
    original_count = 0
    kept_lines = []

    with open(ALERTS_FILE) as f:
        for line in f:
            original_count += 1
            try:
                entry = json.loads(line.strip())
                alert_date_str = entry["date"].replace("Z", "+00:00")
                alert_date = datetime.fromisoformat(alert_date_str)
                # Make naive for comparison with cutoff
                if alert_date.tzinfo is not None:
                    alert_date = alert_date.replace(tzinfo=None)
                if alert_date > cutoff:
                    kept_lines.append(line)
            except (json.JSONDecodeError, ValueError):
                continue

    with open(ALERTS_FILE, "w") as f:
        f.writelines(kept_lines)

    return original_count - len(kept_lines)