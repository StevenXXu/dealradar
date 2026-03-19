# tests/test_apify_client.py
from src.harvester.apify_client import ApifyClient

def test_apify_client_initialization():
    client = ApifyClient(api_token="test-token")
    assert client.api_token == "test-token"

def test_apify_client_actor_url():
    client = ApifyClient(api_token="test-token")
    assert "apify.com" in client.actor_url
