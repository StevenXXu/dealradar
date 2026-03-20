# src/harvester/jina_client.py
"""Jina Reader API client for extracting clean text from URLs."""
import os
import random
import time
import requests
from urllib.parse import urljoin, urlparse, quote

class JinaClient:
    """Client for Jina Reader API (https://r.jina.ai/)."""

    BASE_URL = "https://r.jina.ai/"

    def __init__(self, api_key: str | None = None):
        self.base_url = self.BASE_URL  # Expose as instance attribute for tests
        self.api_key = api_key or os.getenv("JINA_API_KEY", "")
        self.session = requests.Session()
        if self.api_key:
            self.session.headers["Authorization"] = f"Bearer {self.api_key}"

    def build_url(self, target_url: str, mode: str = "html") -> str:
        """Convert a target URL to a Jina Reader URL."""
        # URL-encode the target to handle spaces and special chars
        encoded_url = quote(target_url, safe="://")
        return f"{self.BASE_URL}{encoded_url}?mode={mode}"

    def fetch(self, url: str, timeout: int = 30) -> str:
        """
        Fetch clean markdown text from a URL using Jina Reader.
        Returns the markdown content as a string.
        Raises requests.HTTPError on failure.
        """
        jina_url = self.build_url(url)
        response = self.session.get(jina_url, timeout=timeout)
        response.raise_for_status()
        return response.text

    def fetch_with_retry(self, url: str, max_retries: int = 3) -> str:
        """Fetch with exponential backoff and random jitter."""
        for attempt in range(max_retries):
            try:
                # Random jitter 2-5 seconds
                time.sleep(random.uniform(2, 5))
                return self.fetch(url)
            except requests.RequestException as e:
                if attempt == max_retries - 1:
                    raise
                wait = (2 ** attempt) * 1.0  # 1s, 2s, 4s
                time.sleep(wait)
        raise RuntimeError("Unreachable")

    def is_different_domain(self, original_url: str, final_url: str) -> bool:
        """Check if the final URL has redirected to a different domain."""
        return urlparse(original_url).netloc != urlparse(final_url).netloc
