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


# ─── push_ai_inference ───────────────────────────────────────────────


def _breakdown(**overrides) -> dict:
    base = {
        "tam": 82,
        "team": 75,
        "moat": 50,
        "exit_score": 50,
        "industry": 50,
        "financial": 80,
        "weighted_total": 67.75,
    }
    base.update(overrides)
    return base


def test_push_ai_inference_builds_tags_for_each_dimension():
    from src.commander.supabase_pusher import SupabasePusher
    pusher = SupabasePusher()
    mock_client = MagicMock()
    mock_client.insert_ai_inference.return_value = {"id": "ai-uuid"}
    pusher._client = mock_client

    pusher.push_ai_inference(
        company_id="company-uuid",
        investment_total=68.0,
        analysis="Strong fundamentals.",
        reasons="- TAM is large\n- Team is solid",
        breakdown=_breakdown(),
    )
    mock_client.insert_ai_inference.assert_called_once()
    payload = mock_client.insert_ai_inference.call_args[0][0]
    # Tags carry the per-dim breakdown as 'dim:value' strings so the
    # dashboard can filter on individual scores
    assert "tam:82" in payload["tags"]
    assert "team:75" in payload["tags"]
    assert "moat:50" in payload["tags"]
    assert "exit:50" in payload["tags"]
    assert "industry:50" in payload["tags"]
    assert "financial:80" in payload["tags"]


def test_push_ai_inference_adds_endorsed_tag_when_bonus_applied():
    from src.commander.supabase_pusher import SupabasePusher
    pusher = SupabasePusher()
    mock_client = MagicMock()
    mock_client.insert_ai_inference.return_value = {}
    pusher._client = mock_client

    pusher.push_ai_inference(
        company_id="company-uuid",
        investment_total=88.0,
        analysis="x",
        reasons="y",
        breakdown=_breakdown(),
        endorsement_bonus=20.0,
    )
    payload = mock_client.insert_ai_inference.call_args[0][0]
    assert "endorsed" in payload["tags"]


def test_push_ai_inference_omits_endorsed_tag_when_no_bonus():
    from src.commander.supabase_pusher import SupabasePusher
    pusher = SupabasePusher()
    mock_client = MagicMock()
    mock_client.insert_ai_inference.return_value = {}
    pusher._client = mock_client

    pusher.push_ai_inference(
        company_id="company-uuid",
        investment_total=68.0,
        analysis="x",
        reasons="y",
        breakdown=_breakdown(),
        endorsement_bonus=0.0,
    )
    payload = mock_client.insert_ai_inference.call_args[0][0]
    assert "endorsed" not in payload["tags"]


def test_push_ai_inference_combines_analysis_and_reasons_into_logic_summary():
    from src.commander.supabase_pusher import SupabasePusher
    pusher = SupabasePusher()
    mock_client = MagicMock()
    mock_client.insert_ai_inference.return_value = {}
    pusher._client = mock_client

    pusher.push_ai_inference(
        company_id="company-uuid",
        investment_total=68.0,
        analysis="Strong fundamentals.",
        reasons="- TAM is large",
        breakdown=_breakdown(),
    )
    payload = mock_client.insert_ai_inference.call_args[0][0]
    assert "ANALYSIS:" in payload["logic_summary"]
    assert "Strong fundamentals" in payload["logic_summary"]
    assert "REASONS:" in payload["logic_summary"]
    assert "TAM is large" in payload["logic_summary"]


def test_push_ai_inference_short_circuits_on_missing_company_id():
    from src.commander.supabase_pusher import SupabasePusher
    pusher = SupabasePusher()
    mock_client = MagicMock()
    pusher._client = mock_client

    result = pusher.push_ai_inference(
        company_id="",
        investment_total=50.0,
        analysis="",
        reasons="",
        breakdown=_breakdown(),
    )
    assert result is None
    mock_client.insert_ai_inference.assert_not_called()


def test_push_ai_inference_threads_tenant_id():
    from src.commander.supabase_pusher import SupabasePusher
    pusher = SupabasePusher()
    mock_client = MagicMock()
    mock_client.insert_ai_inference.return_value = {}
    pusher._client = mock_client

    pusher.push_ai_inference(
        company_id="company-uuid",
        investment_total=68.0,
        analysis="x",
        reasons="y",
        breakdown=_breakdown(),
        tenant_id="tenant-uuid",
        model_used="gemini-2.0-flash",
    )
    payload = mock_client.insert_ai_inference.call_args[0][0]
    assert payload["tenant_id"] == "tenant-uuid"
    assert payload["model_used"] == "gemini-2.0-flash"


# ─── SupabaseClient.insert_ai_inference ──────────────────────────────


def test_insert_ai_inference_rounds_float_score_to_int():
    """Schema's investment_score is INT — non-integer scores must be
    rounded rather than triggering a type error on insert."""
    from src.supabase.client import SupabaseClient

    client = SupabaseClient.__new__(SupabaseClient)
    client._client = MagicMock()
    execute_mock = MagicMock()
    execute_mock.data = [{"id": "ai-1"}]
    client._client.table.return_value.insert.return_value.execute.return_value = (
        execute_mock
    )

    client.insert_ai_inference({
        "company_id": "c1",
        "investment_score": 67.75,
        "logic_summary": "x",
        "tags": ["tam:80"],
    })

    inserted = client._client.table.return_value.insert.call_args[0][0]
    assert inserted["investment_score"] == 68  # rounded from 67.75
    assert isinstance(inserted["investment_score"], int)


def test_insert_ai_inference_accepts_none_score():
    """Some early-pipeline writes may not yet have a score; the column
    is nullable in the schema."""
    from src.supabase.client import SupabaseClient

    client = SupabaseClient.__new__(SupabaseClient)
    client._client = MagicMock()
    execute_mock = MagicMock()
    execute_mock.data = [{"id": "ai-1"}]
    client._client.table.return_value.insert.return_value.execute.return_value = (
        execute_mock
    )

    client.insert_ai_inference({"company_id": "c1", "investment_score": None})
    inserted = client._client.table.return_value.insert.call_args[0][0]
    assert inserted["investment_score"] is None