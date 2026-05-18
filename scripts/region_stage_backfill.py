"""
Region & Funding Stage Backfill Script
Populates region and funding_stage from existing company data.
Run: python scripts/region_stage_backfill.py

Region mapping: VC institution slug → region
Funding Stage: parsed from last_raise_amount
"""

import re
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    # Fallback for direct env values
    SUPABASE_URL = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "")
    SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

# VC slug → region mapping
VC_REGION_MAP: dict[str, str] = {
    # Australia & New Zealand (all APAC)
    "investible": "Australia & New Zealand",
    "archangels": "Australia & New Zealand",
    "startmate": "Australia & New Zealand",
    "unsw-founders": "Australia & New Zealand",
    "main-sequence": "Australia & New Zealand",
    "folklore": "Australia & New Zealand",
    "blackbird": "Australia & New Zealand",
    "square-peg": "Australia & New Zealand",
    "airtree": "Australia & New Zealand",
    "one-ventures": "Australia & New Zealand",
    "sa-fund": "Australia & New Zealand",
    "carthona": "Australia & New Zealand",
    "kosmos": "Australia & New Zealand",
    "skip-capital": "Australia & New Zealand",
    "five-v": "Australia & New Zealand",
    "afterwork": "Australia & New Zealand",
    "tidal": "Australia & New Zealand",
    "blacksheep": "Australia & New Zealand",
    "shearwater": "Australia & New Zealand",
    "giantleap": "Australia & New Zealand",
    "aura": "Australia & New Zealand",
    "cicada": "Australia & New Zealand",
    # Global / Unknown → Global
    "sequoia": "North America",
    "a16z": "North America",
    "founders-fund": "North America",
    "y-combinator": "North America",
    "accel": "Europe",
    "index-ventures": "Europe",
    "bessemer": "North America",
    "greylock": "North America",
    "benchmark": "North America",
    "spark": "North America",
    "general-catalyst": "North America",
    "tiger-global": "Asia Pacific",
    "sequoia-india": "Asia Pacific",
    "ggv": "Asia Pacific",
    "hillhouse": "Asia Pacific",
    "shunwei": "Asia Pacific",
    "source-code": "North America",
    "felicis": "North America",
    "first-round": "North America",
    "boxgroup": "North America",
}

# Regex patterns for last_raise_amount parsing
# Matches: "$5M", "A$20M", "$2.5M", "¥100M", "£10M", "€15M"
AMOUNT_PATTERN = re.compile(
    r"\$?\s*([A-Z]?\$|¥|£|€|USD|AUD|NZD|SGD|HKD)?\s*([\d,\.]+)\s*(M|B|K|KB|MB|BB| Million| Billion| Thousand| million| billion| thousand)?",
    re.IGNORECASE
)

MULTIPLIER = {"B": 1e9, "BB": 1e9, "M": 1e6, "MB": 1e6, "K": 1e3, "KB": 1e3,
              "million": 1e6, "billion": 1e9, "thousand": 1e3, "Million": 1e6, "Billion": 1e9, "Thousand": 1e3}


def parse_raise_amount(text: str | None) -> float | None:
    """Parse raise amount text → USD equivalent in millions."""
    if not text:
        return None
    text = text.strip()
    match = AMOUNT_PATTERN.search(text)
    if not match:
        return None
    currency_prefix = (match.group(1) or "$").upper()
    number_str = match.group(2).replace(",", "")
    unit = match.group(3)

    try:
        number = float(number_str)
    except ValueError:
        return None

    if unit:
        unit = unit.strip()
        multiplier = MULTIPLIER.get(unit, 1e6)  # default to millions if unclear
    else:
        # Heuristic: assume M if no unit and number < 1000
        if number < 1000:
            multiplier = 1e6
        else:
            multiplier = 1

    usd_amount = number * multiplier

    # Currency conversion to USD (approximate rates)
    conversions = {
        "A$": 0.65, "AUD": 0.65, "NZD": 0.60, "SGD": 0.74, "HKD": 0.13,
        "£": 1.27, "€": 1.08, "¥": 0.0067, "USD": 1.0, "$": 1.0,
    }
    rate = conversions.get(currency_prefix, 1.0)
    return usd_amount * rate / 1e6  # return in millions


def derive_funding_stage(amount_millions: float | None) -> str | None:
    """Map raise amount to funding stage."""
    if amount_millions is None:
        return None
    if amount_millions < 1:
        return "Pre-seed"
    elif amount_millions < 5:
        return "Seed"
    elif amount_millions < 15:
        return "Series A"
    elif amount_millions < 50:
        return "Series B"
    else:
        return "Series C+"


def get_vc_slug_from_url(portfolio_url: str | None) -> str | None:
    """Extract slug from VC portfolio URL."""
    if not portfolio_url:
        return None
    # Handle common VC portfolio URL patterns
    patterns = [
        r"/portfolio/([^/]+)/?$",
        r"/companies/([^/]+)/?$",
        r"/our-portfolio",
        r"/company/([^/]+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, portfolio_url, re.IGNORECASE)
        if m and m.group(1):
            return m.group(1).lower().replace("-", "_").replace(" ", "_")
    return None


def backfill(supabase: Client) -> dict:
    """Run the backfill and return stats."""
    # Get all institutions to build slug→region map
    inst_result = supabase.table("institutions").select("id, slug, name, portfolio_url").execute()
    institutions = inst_result.data or []

    # Build slug → region from institution data
    slug_to_region = {}
    for inst in institutions:
        slug = inst.get("slug", "").lower()
        url = inst.get("portfolio_url", "")
        # Check VC_REGION_MAP first
        if slug in VC_REGION_MAP:
            slug_to_region[slug] = VC_REGION_MAP[slug]
        # Also try URL-based slug extraction
        if not slug_to_region.get(slug) and url:
            url_slug = get_vc_slug_from_url(url)
            if url_slug and url_slug in VC_REGION_MAP:
                slug_to_region[slug] = VC_REGION_MAP[url_slug]

    print(f"Loaded {len(institutions)} institutions, mapped {len(slug_to_region)} to regions")

    # Get all companies with their institution_id
    companies_result = supabase.table("companies").select("id, institution_id, last_raise_amount, region, funding_stage").execute()
    companies = companies_result.data or []

    updated = 0
    skipped = 0

    for company in companies:
        updates: dict = {}
        inst_id = company.get("institution_id")

        # Region
        if not company.get("region") and inst_id:
            # Find institution for this company
            inst = next((i for i in institutions if i["id"] == inst_id), None)
            if inst:
                slug = inst.get("slug", "").lower()
                region = slug_to_region.get(slug)
                if region:
                    updates["region"] = region
                elif inst.get("name"):
                    # Fallback: search VC name for region hints
                    name_lower = inst["name"].lower()
                    if any(w in name_lower for w in ["australia", "sydney", "melbourne", "nz", "new zealand"]):
                        updates["region"] = "Australia & New Zealand"
                    elif any(w in name_lower for w in ["europe", "london", "berlin", "paris"]):
                        updates["region"] = "Europe"
                    elif any(w in name_lower for w in ["india", "singapore", "china", "japan", "asia"]):
                        updates["region"] = "Asia Pacific"
                    else:
                        updates["region"] = "Global"  # default unknown VCs

        # Funding Stage
        if not company.get("funding_stage"):
            amount_text = company.get("last_raise_amount")
            amount_m = parse_raise_amount(amount_text)
            if amount_m is not None:
                stage = derive_funding_stage(amount_m)
                if stage:
                    updates["funding_stage"] = stage

        if updates:
            supabase.table("companies").update(updates).eq("id", company["id"]).execute()
            updated += 1
        else:
            skipped += 1

    return {"updated": updated, "skipped": skipped, "total": len(companies)}


if __name__ == "__main__":
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env")
        sys.exit(1)

    client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("Starting region + funding_stage backfill...")
    stats = backfill(client)
    print(f"Done! Updated {stats['updated']}/{stats['total']} companies. "
          f"Skipped {stats['skipped']} (already populated or unparseable).")
