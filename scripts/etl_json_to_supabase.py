"""Idempotent ETL: load existing JSON data into Supabase.

Run: python scripts/etl_json_to_supabase.py

Deduplication: companies deduped by domain (same domain = same company row).
ETL is idempotent — safe to re-run.
"""
import json, os, sys
from pathlib import Path

# Add project root to path so src.supabase.client resolves
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.supabase.client import SupabaseClient

RAW_FILE = Path("data/raw_companies.json")
ENRICHED_FILE = Path("data/enriched_companies.json")
VC_SEEDS_FILE = Path("config/vc_seeds.json")


def load_enriched() -> list[dict]:
    if not ENRICHED_FILE.exists():
        print(f"[ETL] No enriched file at {ENRICHED_FILE}, skipping")
        return []
    return json.loads(ENRICHED_FILE.read_text())


def load_raw() -> list[dict]:
    if not RAW_FILE.exists():
        print(f"[ETL] No raw file at {RAW_FILE}, skipping")
        return []
    return json.loads(RAW_FILE.read_text())


def load_vc_seeds() -> list[dict]:
    if not VC_SEEDS_FILE.exists():
        print(f"[ETL] No vc_seeds file at {VC_SEEDS_FILE}, skipping")
        return []
    return json.loads(VC_SEEDS_FILE.read_text())


def run_etl():
    print("[ETL] Starting...")
    try:
        client = SupabaseClient()
    except Exception as e:
        print(f"[ETL] Failed to connect to Supabase: {e}")
        return

    # 1. Load institutions from vc_seeds
    seeds = load_vc_seeds()
    institution_map: dict[str, str] = {}  # slug → id
    inst_errors = 0
    for seed in seeds:
        try:
            inst = client.upsert_institution({
                "name": seed["name"],
                "slug": seed["slug"],
                "website_url": seed.get("url", ""),
                "tier": seed.get("tier", 3),
                "portfolio_url": seed.get("url", ""),
            })
            institution_map[seed["slug"]] = inst["id"]
            print(f"  [ETL] Institution: {seed['name']} ({inst['id']})")
        except Exception as e:
            print(f"[ETL] Failed to upsert institution {seed['name']}: {e}")
            inst_errors += 1
            continue

    def _normalize_domain(domain: str) -> str:
        """Strip leading www. to prevent same-company dupes."""
        return domain.lower().lstrip("www.")

    def _parse_date(value: str) -> str | None:
        """Parse various date formats, return ISO date string or None."""
        if not value:
            return None
        value = value.strip()
        # Already ISO format YYYY-MM-DD
        if len(value) == 10 and value[4] == "-" and value[7] == "-":
            return value
        # Year-month YYYY-MM → first of month
        if len(value) == 7 and value[4] == "-":
            return f"{value}-01"
        # YYYY/MM/DD
        if "/" in value:
            parts = value.split("/")
            if len(parts) == 3:
                return f"{parts[0]}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"
        # Month DD, YYYY (e.g. "November 11, 2025")
        try:
            from datetime import datetime
            dt = datetime.strptime(value, "%B %d, %Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
        return None

    # 2. Dedupe companies: group by domain across all raw entries
    # KNOWN LIMITATION: if a company appears in multiple VC portfolios, only the
    # first-seen institution_id is recorded. A junction table (company_institutions)
    # would fix this but is Phase 2 scope.
    domain_map: dict[str, dict] = {}  # normalized_domain → merged company dict
    for company in load_raw():
        raw_domain = company.get("domain", "")
        if not raw_domain:
            continue
        domain = _normalize_domain(raw_domain)
        if domain not in domain_map:
            domain_map[domain] = company.copy()
            domain_map[domain]["_normalized_domain"] = domain
        # Keep first seen institution if not yet set
        if not domain_map[domain].get("institution_slug"):
            domain_map[domain]["institution_slug"] = company.get("vc_source", "")

    # 3. Apply enriched fields
    # Use same _normalize_domain to ensure www.stripped domains match enriched data
    enriched_by_domain: dict[str, dict] = {
        _normalize_domain(c.get("domain", "")): c
        for c in load_enriched()
        if c.get("domain")
    }
    for domain, company in domain_map.items():
        enriched = enriched_by_domain.get(domain, {})
        company.update({k: v for k, v in enriched.items() if v})

    # 4. Upsert all companies
    total = len(domain_map)
    errors = 0
    for i, (domain, company) in enumerate(domain_map.items()):
        institution_slug = company.get("institution_slug", "")
        institution_id = institution_map.get(institution_slug)

        try:
            result = client.upsert_company({
                "company_name": company.get("company_name", domain),
                "domain": domain,
                "institution_id": institution_id,
                "sector": company.get("sector"),
                "one_liner": company.get("one_liner"),
                "signal_score": company.get("signal_score", 0),
                "tags": company.get("tags", []),
                "last_raise_amount": company.get("last_raise_amount"),
                "last_raise_date": _parse_date(str(company.get("last_raise_date", ""))),
                "funding_clock": _parse_date(str(company.get("funding_clock", ""))),
                "ai_model_used": company.get("ai_model_used"),
                "source_url": company.get("source_citation") or company.get("domain", ""),
            })
        except Exception as e:
            print(f"[ETL] Failed to upsert {domain}: {e}")
            errors += 1
            continue
        if (i + 1) % 50 == 0:
            print(f"  [ETL] Processed {i+1}/{total} companies...")

    print(f"[ETL] Done. {total} unique companies upserted. Errors: {errors}")


if __name__ == "__main__":
    run_etl()