# src/harvester/apify_client.py
"""Apify client for JavaScript-rendered pages (fallback when Jina fails)."""
import os
import random
import time
import requests

class ApifyClient:
    """Client for Apify API (apify.com) — fallback for JS-rendered pages."""

    ACTOR_URL = "https://api.apify.com/v2/acts/apify~website-scraper/run-sync"

    def __init__(self, api_token: str | None = None):
        self.actor_url = self.ACTOR_URL  # Expose as instance attribute for tests
        self.api_token = api_token or os.getenv("APIFY_API_TOKEN", "")

    def scrape(self, url: str, timeout: int = 60) -> dict:
        """
        Scrape a URL using Apify's website-scraper actor.
        Returns parsed JSON with text content.
        """
        if not self.api_token:
            raise ValueError("APIFY_API_TOKEN not set")

        time.sleep(random.uniform(2, 5))  # Rate limiting

        response = requests.post(
            self.ACTOR_URL,
            params={"token": self.api_token},
            json={"urls": [url]},
            timeout=timeout
        )
        response.raise_for_status()
        return response.json()
