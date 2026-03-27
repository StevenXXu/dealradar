# tests/test_supabase_pusher.py
import pytest, os
from unittest.mock import MagicMock

os.environ["SUPABASE_URL"] = "https://test.supabase.co"
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "test-key"

def test_pusher_called_after_enrichment():
    from src.commander.supabase_pusher import SupabasePusher
    pusher = SupabasePusher()
    mock_client = MagicMock()
    mock_client.upsert_company.return_value = {"domain": "acme.com"}
    pusher._client = mock_client
    company = {"company_name": "Acme", "domain": "acme.com", "signal_score": 72}
    result = pusher.push_company(company)
    mock_client.upsert_company.assert_called_once_with(company)
    assert result["domain"] == "acme.com"

def test_pusher_skips_missing_domain():
    from src.commander.supabase_pusher import SupabasePusher
    pusher = SupabasePusher()
    mock_client = MagicMock()
    pusher._client = mock_client
    result = pusher.push_company({"company_name": "No Domain Co"})
    mock_client.upsert_company.assert_not_called()
    assert result is None