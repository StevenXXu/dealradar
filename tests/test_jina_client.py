# tests/test_jina_client.py
from src.harvester.jina_client import JinaClient

def test_jina_client_initialization():
    client = JinaClient(api_key="test-key")
    assert client.base_url == "https://r.jina.ai/"

def test_jina_client_build_url():
    client = JinaClient(api_key="test-key")
    url = client.build_url("https://example.com")
    assert url == "https://r.jina.ai/https://example.com"

def test_jina_client_build_url_encodes():
    client = JinaClient(api_key="test-key")
    url = client.build_url("https://example.com/path with spaces")
    assert " " not in url
