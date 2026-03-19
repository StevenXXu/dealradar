# tests/test_notion_client.py
from src.commander.notion_client import NotionClient

def test_notion_client_initialization():
    client = NotionClient(integration_token="test", database_id="test-db")
    assert client.database_id == "test-db"

def test_build_company_properties():
    client = NotionClient(integration_token="test", database_id="test-db")
    company = {
        "company_name": "Canvas",
        "domain": "https://canvas.co",
        "vc_source": "Blackbird",
        "sector": "B2B SaaS",
        "one_liner": "Design tool",
        "signal_score": 40,
        "tags": ["Cross-Border Target"],
        "last_raise_amount": "$12M",
        "source_citation": "https://canvas.co",
    }
    props = client.build_properties(company)
    assert "Company" in props
    assert props["Company"]["title"][0]["text"]["content"] == "Canvas"
    assert props["Signal Score"]["number"] == 40
    assert props["Tags"]["multi_select"][0]["name"] == "Cross-Border Target"
