import json
import os
import sys
from pathlib import Path

# Add src to path so we can import supabase_client
sys.path.append(str(Path(__file__).parent.parent))

from src.supabase.client import SupabaseClient

def get_or_create_default_tenant(client: SupabaseClient) -> str:
    # Check if exists
    result = client._client.table("tenants").select("id").eq("slug", "default").execute()
    if result.data:
        return result.data[0]["id"]
    
    # Create
    print("Creating default tenant...")
    result = client._client.table("tenants").insert({
        "name": "Default System Tenant",
        "slug": "default"
    }).execute()
    return result.data[0]["id"]

def migrate():
    print("Starting migration to Postgres...")
    client = SupabaseClient()
    
    # Get or create default tenant
    tenant_id = get_or_create_default_tenant(client)
    print(f"Using Tenant ID: {tenant_id}")
    
    # Load enriched data
    data_path = Path(__file__).parent.parent / "data" / "enriched_companies.json"
    if not data_path.exists():
        print("No enriched_companies.json found. Skipping.")
        return
        
    with open(data_path, "r", encoding="utf-8") as f:
        companies = json.load(f)
        
    print(f"Found {len(companies)} companies to migrate.")
    
    # Cache institution IDs
    institutions_cache = {}
    
    for idx, comp in enumerate(companies):
        vc_name = comp.get("vc_source", "Unknown VC")
        
        # Upsert institution
        if vc_name not in institutions_cache:
            # Create a simple slug
            slug = vc_name.lower().replace(" ", "-").replace(".", "")
            inst_data = client.upsert_institution({
                "name": vc_name,
                "slug": slug,
                "tenant_id": tenant_id
            })
            if inst_data and "id" in inst_data:
                institutions_cache[vc_name] = inst_data["id"]
            else:
                print(f"Failed to upsert institution: {vc_name}")
                continue
                
        inst_id = institutions_cache.get(vc_name)
        
        # Upsert company
        company_data = {
            "company_name": comp.get("company_name", "Unknown"),
            "domain": comp.get("domain", ""),
            "institution_id": inst_id,
            "sector": comp.get("sector"),
            "one_liner": comp.get("one_liner"),
            "signal_score": comp.get("signal_score", 0),
            "tags": comp.get("tags", []),
            "last_raise_amount": comp.get("last_raise_amount"),
            "last_raise_date": comp.get("last_raise_date"),
            "funding_clock": comp.get("funding_clock"),
            "ai_model_used": comp.get("ai_model_used"),
            "source_url": comp.get("source_url") or comp.get("source_citation"),
            "tenant_id": tenant_id
        }
        
        # Domain is required for upsert
        if not company_data["domain"]:
            print(f"Skipping {company_data['company_name']} - no domain")
            continue
            
        res = client.upsert_company(company_data)
        if res:
            print(f"[{idx+1}/{len(companies)}] Migrated: {company_data['company_name']}")
        else:
            print(f"[{idx+1}/{len(companies)}] Failed to migrate: {company_data['company_name']}")

    print("Migration complete.")

if __name__ == "__main__":
    try:
        migrate()
    except Exception as e:
        print(f"Migration failed: {e}")
