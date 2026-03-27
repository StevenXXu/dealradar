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