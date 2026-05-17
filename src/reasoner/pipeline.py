# src/reasoner/pipeline.py
"""AI Reasoner pipeline — enriches raw companies with AI signal analysis."""

import json
import time
from datetime import date
from pathlib import Path

import os

from src.harvester.jina_client import JinaClient
from src.reasoner.models import ModelChain
from src.reasoner.signals import SignalDetector
from src.reasoner.funding_clock import FundingClock, estimate_monthly_burn
from src.reasoner.summarizer import Summarizer
from src.reasoner.gatekeeper import FilterChain, default_chain
from src.reasoner.investment_scorer import InvestmentScorer
from src.commander.supabase_pusher import SupabasePusher
from src.reasoner.enrichment_sources import search_crunchbase_url, search_careers_url


class ReasonerPipeline:
    """Orchestrates AI enrichment: fetch company text -> summarize -> score signals -> calculate funding clock."""

    def __init__(
        self,
        raw_companies_path: str = "data/raw_companies.json",
        output_path: str = "data/enriched_companies.json",
        jina_client: JinaClient | None = None,
        model_chain: ModelChain | None = None,
        gatekeeper: FilterChain | None = None,
        investment_scorer: InvestmentScorer | None = None,
        investment_score_threshold: int | None = None,
    ):
        self.raw_companies_path = raw_companies_path
        self.output_path = output_path
        self.companies = self._load_raw()
        self.jina = jina_client or JinaClient()
        self.model_chain = model_chain or ModelChain()
        self.signals = SignalDetector()
        self.summarizer = Summarizer()
        # Pre-LLM filter chain — see src/reasoner/gatekeeper.py.
        # Default drops obvious garbage company names and already-enriched
        # domains so re-runs do not re-pay LLM costs. Pass an explicit
        # FilterChain (including an empty one) to override.
        self.gatekeeper = (
            gatekeeper if gatekeeper is not None else default_chain(output_path)
        )
        # Six-dimensional investment scoring — opt-in via the
        # INVESTMENT_SCORING_ENABLED env var because it adds 2-3 LLM
        # calls per company. Gated by a signal_score threshold so we
        # only spend LLM budget on companies the rule-based layer
        # already flagged as worth a closer look.
        if investment_scorer is not None:
            self.investment_scorer = investment_scorer
        elif os.getenv("INVESTMENT_SCORING_ENABLED", "false").lower() in (
            "1",
            "true",
            "yes",
            "on",
        ):
            self.investment_scorer = InvestmentScorer(model_chain=self.model_chain)
        else:
            self.investment_scorer = None
        if investment_score_threshold is not None:
            self.investment_score_threshold = investment_score_threshold
        else:
            self.investment_score_threshold = int(
                os.getenv("INVESTMENT_SCORE_THRESHOLD", "30")
            )
        self._enriched = []
        self.supabase_pusher = SupabasePusher()

    def _load_raw(self) -> list[dict]:
        with open(self.raw_companies_path) as f:
            return json.load(f)

    def process_company(self, company: dict, idx: int, total: int) -> dict:
        """Enrich a single company with AI analysis."""
        domain = company["domain"]
        print(
            f"  [{idx}/{total}] Processing: {company['company_name']} ({domain})...",
            flush=True,
        )

        try:
            # Pace: one call every 5s to avoid exhausting Jina's free tier (~10-20 req/min)
            time.sleep(5)
            raw_text = self.jina.fetch_with_retry(domain)

            # Fetch Crunchbase data
            crunchbase_url = search_crunchbase_url(company["company_name"])
            if crunchbase_url:
                time.sleep(2)
                cb_text = self.jina.fetch_with_retry(crunchbase_url)
                if cb_text:
                    raw_text += "\n\n--- CRUNCHBASE DATA ---\n" + cb_text

            # Fetch Careers data
            careers_url = search_careers_url(company["company_name"], domain)
            if careers_url:
                time.sleep(2)
                careers_text = self.jina.fetch_with_retry(careers_url)
                if careers_text:
                    raw_text += "\n\n--- CAREERS/JOBS DATA ---\n" + careers_text

        except Exception as e:
            print(f"  [WARN] Failed to fetch {domain} or its enrichment sources: {e}")
            raw_text = ""

        # Step 1: Summarize
        try:
            one_liner, model_name = self.summarizer.summarize(
                raw_text, self.model_chain
            )
        except Exception:
            one_liner = "Unable to generate summary"
            model_name = "unknown"

        # Step 2: Extract signals
        try:
            signal_data = self.signals.analyze_text(raw_text, self.model_chain)
        except Exception:
            signal_data = {}

        # Step 3: Score
        score = self.signals.calculate_score(
            has_cfo_hire=signal_data.get("has_cfo_hire", False),
            last_raise_amount=signal_data.get("last_raise_amount_usd"),
            months_since_raise=signal_data.get("months_since_raise"),
            has_multilang=signal_data.get("has_multilang_apac", False),
            has_series_c_plus=signal_data.get("has_series_c_plus", False),
            has_audit_signals=signal_data.get("has_audit_signals", False),
        )

        # Step 4: Tags
        tags = self.signals.extract_tags(
            has_cfo_hire=signal_data.get("has_cfo_hire", False),
            last_raise_amount=signal_data.get("last_raise_amount_usd"),
            months_since_raise=signal_data.get("months_since_raise"),
            has_multilang=signal_data.get("has_multilang_apac", False),
            has_series_c_plus=signal_data.get("has_series_c_plus", False),
            has_audit_signals=signal_data.get("has_audit_signals", False),
            valuation_over_1b=signal_data.get("valuation_over_1b", False),
            robotics_supply_chain=signal_data.get("has_supply_chain_robotics", False),
        )

        # Step 5: Funding clock
        last_raise = signal_data.get("last_raise_amount_usd")
        months_since = signal_data.get("months_since_raise")
        headcount = signal_data.get("headcount")

        funding_clock = None
        if last_raise and months_since:
            days_since = months_since * 30
            clock = FundingClock(
                last_raise_amount=last_raise, days_since_raise=days_since
            )
            burn = estimate_monthly_burn(
                headcount=headcount, sector=signal_data.get("sector")
            )
            funding_clock = clock.predict_funding_date(burn)

        enriched = {
            **company,
            "sector": signal_data.get("sector", "Unknown"),
            "one_liner": one_liner,
            "signal_score": score,
            "funding_clock": funding_clock.isoformat() if funding_clock else None,
            "tags": tags,
            "last_raise_amount": f"${last_raise / 1_000_000:.0f}M"
            if last_raise
            else "Unknown",
            "last_raise_date": signal_data.get("last_raise_date"),
            "ai_model_used": model_name,
            "source_citation": domain,
        }

        # Step 6: Six-dimensional investment scoring (opt-in).
        # Gated by signal_score threshold so we only spend the extra
        # LLM calls on companies the rule-based layer already flagged.
        if (
            self.investment_scorer is not None
            and score >= self.investment_score_threshold
        ):
            try:
                inv = self.investment_scorer.score(
                    company_name=company.get("company_name", ""),
                    product_description=one_liner,
                    industry=signal_data.get("sector", ""),
                    # dealradar doesn't extract revenue_growth pre-LLM;
                    # financial dim falls back to neutral when None.
                    revenue_growth=None,
                    # raw_text is the Jina + Crunchbase + Careers concat
                    # — the careers section in particular surfaces team
                    # background, so passing the whole blob lets the
                    # LLM cite specific signals.
                    team_context=raw_text[:8000] if raw_text else "",
                    dealradar_endorsed=bool(company.get("dealradar_endorsed", False)),
                )
                enriched["investment_score"] = inv.total
                enriched["investment_breakdown"] = inv.breakdown.as_dict()
                enriched["investment_analysis"] = inv.analysis
                enriched["investment_reasons"] = inv.reasons
                enriched["investment_endorsement_bonus"] = inv.endorsement_bonus
            except Exception as e:
                print(
                    f"  [WARN] Investment scoring failed for {company.get('company_name', domain)}: {e}",
                    flush=True,
                )

        try:
            self.supabase_pusher.push_company(enriched)
        except Exception as e:
            print(
                f"  [WARN] Supabase push failed for {company.get('company_name', domain)}: {e}"
            )
        return enriched

    def run(self) -> list[dict]:
        """Apply the gatekeeper, then process the passers.

        Prior enrichment is preserved: the saved output is the union
        of (previously enriched, newly enriched). This lets the
        AlreadyEnrichedFilter dedupe correctly across runs without
        wiping the file each time.

        Gatekeeper skippers are intentionally NOT written anywhere:
          - they don't belong in 'enriched' output
          - the GarbageNameFilter is pure-Python so re-rejecting them
            on the next run costs effectively nothing
        """
        previous = self._load_previous_enriched()
        passers, _skippers = self.gatekeeper.apply(self.companies)
        print(self.gatekeeper.format_summary(), flush=True)

        # Start with prior enrichment so this run augments rather than
        # replaces. AlreadyEnrichedFilter ensures `passers` and
        # `previous` are disjoint by domain, so no dedupe is needed.
        self._enriched = list(previous)

        total = len(passers)
        for idx, company in enumerate(passers, 1):
            enriched = self.process_company(company, idx, total)
            self._enriched.append(enriched)

        self._save()
        return self._enriched

    def _load_previous_enriched(self) -> list[dict]:
        """Read the existing enriched_companies.json so re-runs can
        augment rather than replace. Returns [] if the file is
        missing or unreadable; the pipeline must succeed on first
        run when there's nothing to carry forward."""
        path = Path(self.output_path)
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(
                f"[Reasoner] Could not read previous enrichment at {path}: {e}",
                flush=True,
            )
            return []
        if not isinstance(data, list):
            return []
        return data

    def _save(self):
        Path(self.output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_path, "w") as f:
            json.dump(self._enriched, f, indent=2)
        print(
            f"\nEnrichment complete: {len(self._enriched)} companies. Saved to {self.output_path}"
        )
