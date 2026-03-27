import os, pytest
from src.supabase.client import SupabaseClient

@pytest.fixture
def client():
    os.environ["SUPABASE_URL"] = "https://test-project.supabase.co"
    os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "test-key"
    return SupabaseClient()

def test_upsert_company_inserts_new(client):
    result = client.upsert_company({
        "company_name": "Acme",
        "domain": "acme.com",
        "institution_id": None,
        "sector": "SaaS",
        "one_liner": "AI-powered acme",
        "signal_score": 72,
        "ai_model_used": "gpt-4o-mini",
    })
    assert result["domain"] == "acme.com"
    assert result["signal_score"] == 72

def test_upsert_company_updates_existing(client):
    client.upsert_company({"company_name": "Acme", "domain": "acme.com", "signal_score": 50})
    result = client.upsert_company({"company_name": "Acme", "domain": "acme.com", "signal_score": 80})
    assert result["signal_score"] == 80

def test_upsert_company_deduplicates_by_domain(client):
    client.upsert_company({"company_name": "Acme", "domain": "acme.com", "institution_id": "uuid-vc-a"})
    client.upsert_company({"company_name": "Acme", "domain": "acme.com", "institution_id": "uuid-vc-b"})
    all_acme = client.get_companies_by_domain("acme.com")
    assert len(all_acme) == 1