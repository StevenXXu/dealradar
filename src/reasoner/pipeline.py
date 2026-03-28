# src/reasoner/pipeline.py
"""AI Reasoner pipeline — enriches raw companies with AI signal analysis."""
import json
import time
from datetime import date
from pathlib import Path

from src.harvester.jina_client import JinaClient
from src.reasoner.models import ModelChain
from src.reasoner.signals import SignalDetector
from src.reasoner.funding_clock import FundingClock, estimate_monthly_burn
from src.reasoner.summarizer import Summarizer
from src.commander.supabase_pusher import SupabasePusher


class ReasonerPipeline:
    """Orchestrates AI enrichment: fetch company text -> summarize -> score signals -> calculate funding clock."""

    def __init__(
        self,
        raw_companies_path: str = "data/raw_companies.json",
        output_path: str = "data/enriched_companies.json",
        jina_client: JinaClient | None = None,
        model_chain: ModelChain | None = None,
    ):
        self.raw_companies_path = raw_companies_path
        self.output_path = output_path
        self.companies = self._load_raw()
        self.jina = jina_client or JinaClient()
        self.model_chain = model_chain or ModelChain()
        self.signals = SignalDetector()
        self.summarizer = Summarizer()
        self._enriched = []
        self.supabase_pusher = SupabasePusher()

    def _load_raw(self) -> list[dict]:
        with open(self.raw_companies_path) as f:
            return json.load(f)

    def process_company(self, company: dict, idx: int, total: int) -> dict:
        """Enrich a single company with AI analysis."""
        domain = company["domain"]
        print(f"  [{idx}/{total}] Processing: {company['company_name']} ({domain})...", flush=True)

        try:
            # Pace: one call every 5s to avoid exhausting Jina's free tier (~10-20 req/min)
            time.sleep(5)
            raw_text = self.jina.fetch_with_retry(domain)
        except Exception as e:
            print(f"  [WARN] Failed to fetch {domain}: {e}")
            raw_text = ""

        # Step 1: Summarize
        try:
            one_liner, model_name = self.summarizer.summarize(raw_text, self.model_chain)
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
        funding_clock = None
        if last_raise and months_since:
            days_since = months_since * 30
            clock = FundingClock(last_raise_amount=last_raise, days_since_raise=days_since)
            burn = estimate_monthly_burn(headcount=None, sector=signal_data.get("sector"))
            funding_clock = clock.predict_funding_date(burn)

        enriched = {
            **company,
            "sector": signal_data.get("sector", "Unknown"),
            "one_liner": one_liner,
            "signal_score": score,
            "funding_clock": funding_clock.isoformat() if funding_clock else None,
            "tags": tags,
            "last_raise_amount": f"${last_raise/1_000_000:.0f}M" if last_raise else "Unknown",
            "last_raise_date": signal_data.get("last_raise_date"),
            "ai_model_used": model_name,
            "source_citation": domain,
        }

        try:
            self.supabase_pusher.push_company(enriched)
        except Exception as e:
            print(f"  [WARN] Supabase push failed for {company.get('company_name', domain)}: {e}")
        return enriched

    def run(self) -> list[dict]:
        """Process all companies."""
        self._enriched = []
        total = len(self.companies)
        for idx, company in enumerate(self.companies, 1):
            enriched = self.process_company(company, idx, total)
            self._enriched.append(enriched)

        self._save()
        return self._enriched

    def _save(self):
        Path(self.output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_path, "w") as f:
            json.dump(self._enriched, f, indent=2)
        print(f"\nEnrichment complete: {len(self._enriched)} companies. Saved to {self.output_path}")
