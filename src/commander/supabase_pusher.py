"""Supabase pusher — called by ReasonerPipeline after AI enrichment.

Replaces Notion push as primary store. Runs in parallel with Notion push
during transition, then Notion push is removed in Phase 1 cleanup.
"""
import os
from src.supabase.client import SupabaseClient


class SupabasePusher:
    def __init__(self):
        self._client = None

    @property
    def client(self) -> SupabaseClient:
        if self._client is None:
            self._client = SupabaseClient()
        return self._client

    def push_company(self, company: dict) -> dict | None:
        """Upsert a single enriched company to Supabase. Returns result or None if skipped."""
        domain = company.get("domain")
        if not domain:
            return None
        return self.client.upsert_company(company)

    def push_ai_inference(
        self,
        company_id: str,
        investment_total: float,
        analysis: str,
        reasons: str,
        breakdown: dict,
        endorsement_bonus: float = 0.0,
        model_used: str | None = None,
        tenant_id: str | None = None,
    ) -> dict | None:
        """Persist an InvestmentScorer result into the ai_inferences
        table. logic_summary holds the analysis + reasons text so the
        dashboard can render full narrative; tags hold the per-dim
        breakdown as discrete labels for quick filtering.

        Returns the inserted row, or None when the required
        company_id is missing — the caller may attempt with this
        information later once the company is upserted.
        """
        if not company_id:
            return None
        tags = [
            f"tam:{round(breakdown.get('tam', 0))}",
            f"team:{round(breakdown.get('team', 0))}",
            f"moat:{round(breakdown.get('moat', 0))}",
            f"exit:{round(breakdown.get('exit_score', 0))}",
            f"industry:{round(breakdown.get('industry', 0))}",
            f"financial:{round(breakdown.get('financial', 0))}",
        ]
        if endorsement_bonus and endorsement_bonus > 0:
            tags.append("endorsed")

        logic_summary_parts = []
        if analysis:
            logic_summary_parts.append(f"ANALYSIS:\n{analysis}")
        if reasons:
            logic_summary_parts.append(f"REASONS:\n{reasons}")
        logic_summary = "\n\n".join(logic_summary_parts) or None

        return self.client.insert_ai_inference(
            {
                "company_id": company_id,
                "investment_score": investment_total,
                "logic_summary": logic_summary,
                "tags": tags,
                "model_used": model_used,
                "tenant_id": tenant_id,
            }
        )

    def push_batch(self, companies: list[dict]) -> dict:
        """Push a batch of companies. Returns summary dict."""
        results = {"pushed": 0, "skipped": 0, "errors": 0}
        for company in companies:
            try:
                result = self.push_company(company)
                if result:
                    results["pushed"] += 1
                else:
                    results["skipped"] += 1
            except Exception as e:
                print(f"  [SupabasePusher] Error pushing {company.get('company_name')}: {e}")
                results["errors"] += 1
        return results