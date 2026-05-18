import os
import requests
import time
from typing import Optional


def search_crunchbase_url(company_name: str) -> Optional[str]:
    """Search SerpAPI for the company's crunchbase profile."""
    api_key = os.getenv("SERPAPI_API_KEY")
    if not api_key:
        return None

    try:
        params = {
            "engine": "google",
            "q": f"{company_name} crunchbase",
            "api_key": api_key,
            "num": 3,
        }
        resp = requests.get("https://serpapi.com/search", params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        for result in data.get("organic_results", []):
            link = result.get("link", "")
            if "crunchbase.com/organization/" in link:
                return link
    except Exception as e:
        print(f"  [WARN] Failed to find Crunchbase URL for {company_name}: {e}")
    return None


def search_careers_url(company_name: str, domain: str) -> Optional[str]:
    """Search SerpAPI for the company's career page."""
    api_key = os.getenv("SERPAPI_API_KEY")
    if not api_key:
        return None

    try:
        params = {
            "engine": "google",
            "q": f"site:{domain} careers OR jobs",
            "api_key": api_key,
            "num": 3,
        }
        resp = requests.get("https://serpapi.com/search", params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        for result in data.get("organic_results", []):
            link = result.get("link", "")
            if any(
                term in link.lower()
                for term in [
                    "career",
                    "job",
                    "lever.co",
                    "greenhouse.io",
                    "workable.com",
                ]
            ):
                return link

        # Fallback to LinkedIn jobs
        params["q"] = f"{company_name} jobs linkedin"
        resp = requests.get("https://serpapi.com/search", params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        for result in data.get("organic_results", []):
            link = result.get("link", "")
            if "linkedin.com/company/" in link or "linkedin.com/jobs/" in link:
                return link

    except Exception as e:
        print(f"  [WARN] Failed to find Careers URL for {company_name}: {e}")
    return None
