"""One-shot cleanup of garbage company_name rows left by the
pre-fix extractor bug (commit 3fd3c08).

Before that fix, ``src/harvester/extractor.py`` was emitting
``company_name='Website'`` (or 'Read More', 'Visit Site', '→', etc.)
whenever a portfolio anchor's link text was a generic UI affordance
instead of a real company name. Those rows leaked into both
``data/enriched_companies.json`` and the Supabase ``companies`` table,
where they show up as fake deals on the dashboard.

The new ``GarbageNameFilter`` in ``src/reasoner/gatekeeper`` blocks
these from FUTURE LLM runs but does not touch existing data — that's
this script's job. It is intentionally a one-shot: identify garbage
rows by running the same filter against the existing dataset, then
(with ``--apply``) delete them from JSON + Supabase and optionally
write a re-harvest queue so the harvester can re-scrape the affected
VC pages with the fixed extractor.

Usage
-----
Dry run (default — no writes):
    python scripts/purge_garbage_companies.py

Apply purge after interactive 'PURGE' confirmation:
    python scripts/purge_garbage_companies.py --apply

Apply purge AND queue affected VC pages for re-harvest:
    python scripts/purge_garbage_companies.py --apply --queue-reharvest
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from src.reasoner.gatekeeper import FilterChain, GarbageNameFilter  # noqa: E402
from src.supabase.client import SupabaseClient  # noqa: E402


ENRICHED_FILE = ROOT / "data" / "enriched_companies.json"
REHARVEST_QUEUE = ROOT / "data" / "reharvest_queue.json"
SAMPLE_LIMIT = 10
CONFIRM_TOKEN = "PURGE"


def load_enriched() -> list[dict]:
    if not ENRICHED_FILE.exists():
        print(f"[purge] No enriched file at {ENRICHED_FILE}", file=sys.stderr)
        sys.exit(1)
    try:
        data = json.loads(ENRICHED_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[purge] Failed to load {ENRICHED_FILE}: {exc}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(data, list):
        print(f"[purge] {ENRICHED_FILE} is not a JSON list", file=sys.stderr)
        sys.exit(1)
    return data


def partition(companies: list[dict]) -> tuple[list[dict], list[dict], FilterChain]:
    """Run the GarbageNameFilter inside a FilterChain so we get the
    same ``format_summary()`` output the orchestrator would print.

    Returns ``(keep, garbage, chain)``. ``keep`` reuses the original
    dicts; ``garbage`` is a list of copies annotated with
    ``_gatekeeper_skip`` (we never write those back).
    """
    chain = FilterChain()
    chain.add(GarbageNameFilter())
    keep, garbage = chain.apply(companies)
    return keep, garbage, chain


def print_summary(chain: FilterChain, garbage: list[dict]) -> None:
    print(chain.format_summary())
    if not garbage:
        return
    print()
    print(f"Sample garbage rows (up to {SAMPLE_LIMIT}):")
    for row in garbage[:SAMPLE_LIMIT]:
        name = row.get("company_name") or ""
        domain = row.get("domain") or ""
        vc = row.get("vc_source") or ""
        print(f"  name={name!r:24s} domain={domain!r}  vc={vc!r}")
    if len(garbage) > SAMPLE_LIMIT:
        print(f"  ... and {len(garbage) - SAMPLE_LIMIT} more")


def confirm_apply() -> bool:
    print()
    print(
        f"WARNING: --apply will permanently delete rows from\n"
        f"  {ENRICHED_FILE}\n"
        f"AND from the Supabase `companies` table (hard delete, no soft tombstone).\n"
        f"Type {CONFIRM_TOKEN} to proceed; anything else aborts."
    )
    try:
        answer = input("> ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer == CONFIRM_TOKEN


def write_enriched(keep: list[dict]) -> None:
    ENRICHED_FILE.write_text(
        json.dumps(keep, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"[purge] Wrote {len(keep)} non-garbage rows back to {ENRICHED_FILE}")


def delete_from_supabase(garbage: list[dict]) -> int:
    """Delete each garbage row from Supabase's ``companies`` table by
    domain. Returns the total number of rows Supabase reports as
    deleted, which the caller compares against ``len(garbage)`` to
    catch normalisation drift.

    Supabase credential failures abort Supabase deletion entirely but
    do NOT raise — the JSON purge has already happened and the user
    needs to see the mismatch warning, not a stack trace.
    """
    try:
        client = SupabaseClient()
    except Exception as exc:  # missing env vars, network, etc.
        print(
            f"[purge] Could NOT connect to Supabase: {exc}\n"
            f"[purge] JSON has been purged but Supabase rows still exist. "
            f"Fix credentials and re-run, or delete manually by domain.",
            file=sys.stderr,
        )
        return 0

    deleted_total = 0
    for row in garbage:
        domain = (row.get("domain") or "").strip()
        if not domain:
            continue
        try:
            result = (
                client._client.table("companies")
                .delete()
                .eq("domain", domain)
                .execute()
            )
        except Exception as exc:
            print(f"  [purge] FAILED delete {domain}: {exc}", file=sys.stderr)
            continue
        n = len(result.data or [])
        if n:
            deleted_total += n
            print(f"  [purge] deleted {n} row(s)  domain={domain}")
        else:
            # Either domain never made it into Supabase or the stored
            # form differs (scheme/www./trailing-slash drift). Logged
            # so the mismatch warning at the end is debuggable.
            print(f"  [purge] no Supabase match for {domain}")
    return deleted_total


def write_reharvest_queue(garbage: list[dict]) -> None:
    queue = [
        {
            "domain": (row.get("domain") or "").strip(),
            "source_url": (row.get("source_url") or "").strip(),
            "vc_source": row.get("vc_source") or "",
        }
        for row in garbage
    ]
    REHARVEST_QUEUE.write_text(
        json.dumps(queue, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"[purge] Queued {len(queue)} entries in {REHARVEST_QUEUE}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "One-shot purge of pre-3fd3c08 garbage company_name rows "
            "from data/enriched_companies.json and Supabase."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete (interactive confirm). Default is dry-run.",
    )
    parser.add_argument(
        "--queue-reharvest",
        action="store_true",
        help="With --apply, also write data/reharvest_queue.json.",
    )
    args = parser.parse_args()

    if args.queue_reharvest and not args.apply:
        print(
            "[purge] --queue-reharvest requires --apply (queueing without "
            "purging would leave duplicates on the next harvest).",
            file=sys.stderr,
        )
        return 2

    companies = load_enriched()
    keep, garbage, chain = partition(companies)
    print_summary(chain, garbage)

    if not args.apply:
        print()
        print("[purge] Dry run - no files written. Re-run with --apply to purge.")
        return 0

    if not garbage:
        print("[purge] Nothing to purge.")
        return 0

    if not confirm_apply():
        print(f"[purge] Aborted - confirmation token did not match {CONFIRM_TOKEN!r}.")
        return 1

    write_enriched(keep)
    sb_deleted = delete_from_supabase(garbage)

    if sb_deleted != len(garbage):
        print()
        print(
            f"WARNING: Supabase deleted {sb_deleted} rows but JSON had "
            f"{len(garbage)} garbage rows."
        )
        print(
            "         Likely cause: domain normalisation drift (scheme, "
            "www., trailing slash, case)."
        )
        print(
            "         Audit Supabase manually — surviving garbage will "
            "still show on the dashboard."
        )

    if args.queue_reharvest:
        write_reharvest_queue(garbage)

    print()
    print(
        f"[purge] Done. Removed {len(garbage)} rows from JSON, "
        f"{sb_deleted} from Supabase."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
