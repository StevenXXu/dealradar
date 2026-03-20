# src/commander/notion_client.py
"""Notion API client for writing enriched company records to Notion database."""
import os
import time
from notion_client import Client as NotionClientLib
from notion_client.errors import APIResponseError

from datetime import date


class NotionClient:
    """Client for writing DealRadar enriched data to Notion."""

    def __init__(
        self,
        integration_token: str | None = None,
        database_id: str | None = None,
    ):
        self.integration_token = integration_token or os.getenv("NOTION_API_KEY", "")
        self.database_id = database_id or os.getenv("NOTION_DATABASE_ID", "")
        if not self.integration_token:
            raise ValueError("NOTION_API_KEY not set")
        if not self.database_id:
            raise ValueError("NOTION_DATABASE_ID not set")

        self.client = NotionClientLib(auth=self.integration_token)

    def build_properties(self, company: dict) -> dict:
        """Convert a company dict to Notion page properties."""
        props = {}

        props["Name"] = {
            "title": [{"text": {"content": company["company_name"][:200]}}]
        }
        props["Domain"] = {"url": company.get("domain", "")}
        props["VC Source"] = {"rich_text": [{"text": {"content": company.get("vc_source", "")}}]}
        props["Sector"] = {"rich_text": [{"text": {"content": company.get("sector", "Unknown")}}]}
        props["One-liner"] = {"rich_text": [{"text": {"content": company.get("one_liner", "")[:2000]}}]}
        props["Signal Score"] = {"number": company.get("signal_score", 0)}

        funding_clock = company.get("funding_clock")
        if funding_clock:
            props["Funding Clock"] = {"date": {"start": funding_clock}}

        tags = company.get("tags", [])
        if isinstance(tags, list):
            props["Tags"] = {"multi_select": [{"name": t} for t in tags[:10]]}

        props["Last Raise Amount"] = {"rich_text": [{"text": {"content": company.get("last_raise_amount", "Unknown")}}]}
        props["Model Used"] = {"rich_text": [{"text": {"content": company.get("ai_model_used", "Unknown")}}]}
        props["Source URL"] = {"url": company.get("source_citation", company.get("domain", ""))}
        props["Last Scraped"] = {"date": {"start": str(date.today())}}

        last_raise_date = company.get("last_raise_date")
        if last_raise_date:
            props["Last Raise Date"] = {"date": {"start": last_raise_date}}

        return props

    def page_exists_by_domain(self, domain: str) -> str | None:
        """Query Notion for existing page with matching domain. Returns page_id or None."""
        try:
            results = self.client.databases.query(
                self.database_id,
                filter={
                    "property": "Domain",
                    "url": {"equals": domain},
                },
            )
            pages = results.get("results", [])
            return pages[0]["id"] if pages else None
        except Exception:
            return None

    def create_page(self, company: dict, max_retries: int = 3) -> str:
        """Create a new Notion page for a company."""
        properties = self.build_properties(company)
        for attempt in range(max_retries):
            try:
                result = self.client.pages.create(
                    parent={"database_id": self.database_id},
                    properties=properties,
                )
                return result["id"]
            except APIResponseError:
                if attempt == max_retries - 1:
                    raise
                wait = (2 ** attempt) * 1.0
                time.sleep(wait)

    def update_page(self, page_id: str, company: dict, max_retries: int = 3):
        """Update an existing Notion page."""
        properties = self.build_properties(company)
        properties.pop("Last Scraped", None)

        for attempt in range(max_retries):
            try:
                self.client.pages.update(page_id, properties=properties)
                return
            except APIResponseError:
                if attempt == max_retries - 1:
                    raise
                wait = (2 ** attempt) * 1.0
                time.sleep(wait)

    def upsert_company(self, company: dict) -> str:
        """Insert or update a company in Notion."""
        domain = company.get("domain")
        if not domain:
            raise ValueError(f"Company {company.get('company_name')} has no domain")

        existing_id = self.page_exists_by_domain(domain)
        if existing_id:
            print(f"  Updating existing: {company['company_name']}")
            self.update_page(existing_id, company)
            return existing_id
        else:
            print(f"  Creating new: {company['company_name']}")
            return self.create_page(company)

    def push_all(self, companies: list[dict]) -> dict:
        """Push all companies to Notion with deduplication."""
        results = {"created": 0, "updated": 0, "errors": 0}
        for company in companies:
            try:
                existing = self.page_exists_by_domain(company.get("domain", ""))
                if existing:
                    results["updated"] += 1
                else:
                    results["created"] += 1
                self.upsert_company(company)
                time.sleep(0.5)  # Notion rate limit
            except Exception as e:
                print(f"  [ERROR] {company.get('company_name')}: {e}")
                results["errors"] += 1

        return results
