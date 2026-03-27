"""Supabase client wrapper for DealRadar pipeline and ETL."""
import os
from datetime import datetime, timezone
from supabase import create_client, Client

class SupabaseClient:
    def __init__(self, url: str | None = None, service_role_key: str | None = None):
        self.url = url or os.getenv("SUPABASE_URL", "")
        self.service_key = service_role_key or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        if not self.url or not self.service_key:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
        self._client: Client = create_client(self.url, self.service_key)

    def upsert_company(self, company: dict) -> dict:
        """Insert or update a company. Deduplicates by domain."""
        try:
            result = self._client.table("companies").upsert(
                {
                    "company_name": company["company_name"],
                    "domain": company["domain"],
                    "institution_id": company.get("institution_id"),
                    "sector": company.get("sector"),
                    "one_liner": company.get("one_liner"),
                    "signal_score": company.get("signal_score", 0),
                    "tags": company.get("tags", []),
                    "last_raise_amount": company.get("last_raise_amount"),
                    "last_raise_date": company.get("last_raise_date"),
                    "funding_clock": company.get("funding_clock"),
                    "ai_model_used": company.get("ai_model_used"),
                    "source_url": company.get("source_url"),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
                on_conflict="domain",
                ignore_duplicates=False,
            ).execute()
            return result.data[0] if result.data else {}
        except Exception as e:
            print(f"[SupabaseClient] upsert_company error: {e}")
            return {}

    def get_companies_by_domain(self, domain: str) -> list[dict]:
        try:
            result = self._client.table("companies").select("*").eq("domain", domain).execute()
            return result.data or []
        except Exception as e:
            print(f"[SupabaseClient] get_companies_by_domain error: {e}")
            return []

    def upsert_institution(self, institution: dict) -> dict:
        try:
            result = self._client.table("institutions").upsert(
                {
                    "name": institution["name"],
                    "slug": institution["slug"],
                    "website_url": institution.get("website_url"),
                    "tier": institution.get("tier", 3),
                    "portfolio_url": institution.get("portfolio_url"),
                },
                on_conflict="name",
            ).execute()
            return result.data[0] if result.data else {}
        except Exception as e:
            print(f"[SupabaseClient] upsert_institution error: {e}")
            return {}

    def insert_signal(self, signal: dict) -> dict:
        try:
            result = self._client.table("signals").insert(
                {
                    "company_id": signal["company_id"],
                    "source": signal.get("source", "ugc"),
                    "content": signal.get("content", {}),
                    "signal_score": signal.get("signal_score", 0),
                    "status": signal.get("status", "pending"),
                }
            ).execute()
            return result.data[0] if result.data else {}
        except Exception as e:
            print(f"[SupabaseClient] insert_signal error: {e}")
            return {}

    def get_pending_signals(self) -> list[dict]:
        try:
            result = (
                self._client.table("signals")
                .select("*, companies(company_name, domain)")
                .eq("status", "pending")
                .execute()
            )
            return result.data or []
        except Exception as e:
            print(f"[SupabaseClient] get_pending_signals error: {e}")
            return []

    def approve_signal(self, signal_id: str) -> dict:
        try:
            result = (
                self._client.table("signals")
                .update({"status": "published"})
                .eq("id", signal_id)
                .execute()
            )
            return result.data[0] if result.data else {}
        except Exception as e:
            print(f"[SupabaseClient] approve_signal error: {e}")
            return {}

    def reject_signal(self, signal_id: str) -> dict:
        try:
            result = (
                self._client.table("signals")
                .update({"status": "rejected"})
                .eq("id", signal_id)
                .execute()
            )
            return result.data[0] if result.data else {}
        except Exception as e:
            print(f"[SupabaseClient] reject_signal error: {e}")
            return {}