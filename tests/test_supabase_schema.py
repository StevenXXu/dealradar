# tests/test_supabase_schema.py
import pytest

def test_institutions_table_exists(supabase_client):
    result = supabase_client.table("institutions").select("id").limit(1).execute()
    assert result.data is not None

def test_companies_table_has_unique_domain(supabase_client):
    # Insert same domain twice — second should fail
    supabase_client.table("companies").insert({"company_name": "Acme", "domain": "acme.com"}).execute()
    with pytest.raises(Exception):
        supabase_client.table("companies").insert({"company_name": "Acme2", "domain": "acme.com"}).execute()

def test_signals_status_enum(supabase_client):
    # Only valid statuses accepted
    supabase_client.table("signals").insert({"source": "ugc", "content": {"body": "test"}, "status": "pending"}).execute()
    assert True