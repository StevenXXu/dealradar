"""Pre-LLM gatekeeper — cheap filters that drop companies before
they hit the expensive Jina + LLM enrichment loop.

Adapted from dealflow's monolithic Gatekeeper class. The dealflow
version assumed Deal objects with headquarters/funding_stage/industry
fields available pre-scoring; dealradar's harvester output only has
company_name / domain / vc_source / source_url, so this module is
restructured as a small framework that composes single-purpose
Filter objects evaluated in order. Future filters (geo, ethics,
funding stage) can be added as hooks without rewriting the chain.

The two initial filters target dealradar's actual cost sinks
observed in production:

  - GarbageNameFilter: drops entries where company_name was harvested
    from generic link text ('Website', 'Read More') instead of a
    real company. Observed in the existing enriched_companies.json.

  - AlreadyEnrichedFilter: drops entries whose domain already appears
    in enriched_companies.json so re-runs do not pay LLM costs to
    re-derive identical output.

Each Filter.check(company) returns 'pass' or a skip reason string
like 'skip:garbage_name:empty'. FilterChain.apply(companies) splits
the input into (passers, skippers) and records per-reason counts on
self.stats so the orchestrator can print a summary.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse


class Filter(Protocol):
    """A single gatekeeper filter."""

    name: str

    def check(self, company: dict) -> str:
        """Return 'pass' to let the company through, or a skip reason
        string (conventionally 'skip:<name>' or 'skip:<name>:<detail>')."""
        ...


# ─── Built-in filters ─────────────────────────────────────────────────


class GarbageNameFilter:
    """Drop companies whose company_name is generic navigation text
    rather than a real company name.

    Triggered by extractor failures where an <a> tag's link text
    ('Website', 'Read More', 'Learn More') was captured as the
    company name. Cheap pure-Python check; saves a full Jina+LLM
    pass per dropped row.
    """

    name = "garbage_name"

    # Lower-cased exact-match block list. Conservative — only entries
    # that are categorically not company names. Adding fuzzy/substring
    # matching here risks dropping real companies whose name happens to
    # contain a word like 'website'.
    GARBAGE_NAMES: frozenset[str] = frozenset(
        {
            "website",
            "read more",
            "learn more",
            "view more",
            "see more",
            "show more",
            "visit",
            "visit site",
            "visit website",
            "go to website",
            "home",
            "homepage",
            "about",
            "about us",
            "contact",
            "contact us",
            "portfolio",
            "companies",
            "our companies",
            "team",
            "our team",
            "news",
            "press",
            "blog",
            "careers",
            "jobs",
            "investors",
            "investment",
            "invest",
            "more info",
            "more information",
            "details",
            "view",
            "view all",
            "all",
            "click here",
            "here",
            "link",
            "menu",
            "search",
            "next",
            "previous",
            "prev",
            "back",
        }
    )

    def check(self, company: dict) -> str:
        name = (company.get("company_name") or "").strip()
        if not name:
            return f"skip:{self.name}:empty"
        lower = name.lower()
        if lower in self.GARBAGE_NAMES:
            return f"skip:{self.name}"
        if len(name) <= 2:
            return f"skip:{self.name}:too_short"
        return "pass"


class AlreadyEnrichedFilter:
    """Drop companies whose domain is already present in the enriched
    output JSON, so re-runs do not re-pay LLM costs for unchanged data.

    Domain comparison is normalized: scheme, leading 'www.', trailing
    slash, and case are stripped. So 'https://canvas.co' and
    'http://www.canvas.co/' compare equal.

    Missing or unparseable enriched_companies.json yields an empty
    seen set (i.e. nothing is filtered), so first runs work without
    special-casing.
    """

    name = "already_enriched"

    def __init__(self, enriched_path: str | Path):
        self.enriched_path = Path(enriched_path)
        self._seen_domains: set[str] = self._load_seen()

    def _load_seen(self) -> set[str]:
        if not self.enriched_path.exists():
            return set()
        try:
            data = json.loads(self.enriched_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return set()
        if not isinstance(data, list):
            return set()
        return {
            normalized
            for c in data
            if isinstance(c, dict)
            and (normalized := self._normalize(c.get("domain")))
        }

    @staticmethod
    def _normalize(domain: str | None) -> str:
        """Return canonical host string for domain comparison.

        Empty/None inputs return ''. Inputs with no scheme are parsed
        as if 'https://' were prepended so urlparse populates netloc.
        Strips leading 'www.' and trailing slashes/whitespace.
        """
        if not domain:
            return ""
        candidate = domain if "://" in domain else f"https://{domain}"
        parsed = urlparse(candidate)
        host = (parsed.netloc or parsed.path).lower().strip().strip("/")
        if host.startswith("www."):
            host = host[4:]
        return host

    def check(self, company: dict) -> str:
        normalized = self._normalize(company.get("domain"))
        if normalized and normalized in self._seen_domains:
            return f"skip:{self.name}"
        return "pass"


# ─── Filter chain ─────────────────────────────────────────────────────


class FilterChain:
    """Composable, order-sensitive gatekeeper.

    Filters are evaluated in insertion order; the first non-'pass'
    verdict short-circuits and is recorded as the skip reason for
    that company. This means earlier filters should be cheaper than
    later ones, and the order encodes a coarse priority.

    Stats reset on each apply() call and reflect only that batch.
    """

    def __init__(self) -> None:
        self.filters: list[Filter] = []
        self.stats: dict = {"total": 0, "passed": 0, "skipped": {}}

    def add(self, filter_obj: Filter) -> "FilterChain":
        self.filters.append(filter_obj)
        return self

    def evaluate(self, company: dict) -> tuple[bool, str | None]:
        """Return (passes, reason). reason is None when passes is True."""
        for f in self.filters:
            verdict = f.check(company)
            if verdict != "pass":
                return False, verdict
        return True, None

    def apply(self, companies: list[dict]) -> tuple[list[dict], list[dict]]:
        """Split companies into (passers, skippers).

        Resets self.stats. Each skipper dict is annotated with a
        '_gatekeeper_skip' field carrying the reason, so callers can
        log or persist them without losing the why.
        """
        passers: list[dict] = []
        skippers: list[dict] = []
        self.stats = {"total": len(companies), "passed": 0, "skipped": {}}
        for c in companies:
            ok, reason = self.evaluate(c)
            if ok:
                passers.append(c)
                self.stats["passed"] += 1
            else:
                skipped_entry = dict(c)
                skipped_entry["_gatekeeper_skip"] = reason
                skippers.append(skipped_entry)
                self.stats["skipped"][reason] = (
                    self.stats["skipped"].get(reason, 0) + 1
                )
        return passers, skippers

    def format_summary(self) -> str:
        total = self.stats["total"]
        passed = self.stats["passed"]
        if total == 0:
            return "Gatekeeper: no companies to evaluate"

        lines = [
            "Gatekeeper summary:",
            f"  Total raw companies:    {total}",
            f"  Passed to LLM:          {passed} ({passed * 100 / total:.1f}%)",
        ]
        for reason, count in sorted(
            self.stats["skipped"].items(), key=lambda kv: -kv[1]
        ):
            lines.append(
                f"  Skipped {reason:<30s} {count} ({count * 100 / total:.1f}%)"
            )
        return "\n".join(lines)


def default_chain(enriched_path: str | Path) -> FilterChain:
    """Build the default gatekeeper chain used by ReasonerPipeline.

    Order is intentional: garbage_name first (no IO, instant) then
    already_enriched (loads enriched file once at construction).
    """
    chain = FilterChain()
    chain.add(GarbageNameFilter())
    chain.add(AlreadyEnrichedFilter(enriched_path))
    return chain
