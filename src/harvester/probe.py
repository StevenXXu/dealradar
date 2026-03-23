# src/harvester/probe.py
"""AI-guided VC URL structure probe for Faction B adaptive scraping."""
import json
import os
import time

import requests


class ProbeFailed(Exception):
    """Raised when AI probe fails to return a valid pattern."""
    pass


def call_ai_model(prompt: str) -> str:
    """
    Call lightweight AI model for URL pattern extraction.
    Falls back to full reasoner chain if primary fails.
    Raises ProbeFailed on error.
    """
    api_key = os.getenv("OPENAI_API_KEY", "")
    model = os.getenv("AI_PROBE_MODEL", "gpt-4o-mini")

    if not api_key:
        raise ProbeFailed("OPENAI_API_KEY not set")

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a URL pattern analysis tool. Return ONLY valid JSON, no preamble."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 500,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    for attempt in range(3):
        try:
            resp = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers, json=payload, timeout=30
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            if attempt == 2:
                raise ProbeFailed(f"AI API error after 3 attempts: {e}")
            time.sleep((2 ** attempt) * 1.0)


def probe_vc_structure(
    portfolio_markdown: str,
    portfolio_url: str,
    base_url: str,
) -> dict:
    """
    Use AI to analyze portfolio page content and extract the VC's URL structure.

    Args:
        portfolio_markdown: Raw markdown/text from the portfolio page (via Jina Reader).
        portfolio_url: Full URL of the portfolio page.
        base_url: Base URL of the VC website (e.g. https://www.investible.com).

    Returns:
        dict with keys: slug_regex, detail_url_template, confidence, sample_slugs, num_links_found

    Raises:
        ProbeFailed: if AI returns no valid pattern, low confidence, or API error.
    """
    prompt = f"""You are analyzing a VC portfolio page.

Portfolio page URL: {portfolio_url}
Base URL of this VC: {base_url}  (use this to resolve relative links and construct absolute URLs)

Raw content below:
---
{portfolio_markdown[:8000]}  # truncate to avoid token overflow
---

Your task:
1. Find all URLs in the content that look like individual portfolio company pages.
   Exclude: social media (linkedin.com, twitter.com, facebook.com), Crunchbase, PitchBook, Wikipedia, GitHub.
2. From those URLs, identify the common URL path pattern.
   - Example: if links are ".../company/canva", ".../company/stripe", the path pattern is "/company/{{slug}}".
   - Extract the slug (the variable path segment) from each match.
3. Determine the detail page URL template for this VC.
   - Use base_url to construct absolute URLs: base_url + the path pattern with {{slug}} placeholder.
   - Example: base_url="https://www.investible.com" + path="/company/{{slug}}" → "https://www.investible.com/company/{{slug}}"
4. Report ONLY valid JSON (no preamble, no explanation):
{{
  "slug_regex": "(?:company|portfolio)/([a-z0-9-]+)",
  "detail_url_template": "https://www.vc.com/company/{{slug}}",
  "confidence": "high",
  "sample_slugs": ["canva", "stripe", "figma"],
  "num_links_found": 42
}}

If no clear company-detail URL pattern can be found:
{{
  "slug_regex": null,
  "detail_url_template": null,
  "confidence": "low",
  "reason": "explanation of why pattern detection failed",
  "sample_slugs": [],
  "num_links_found": 0
}}"""

    raw = call_ai_model(prompt)

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        raise ProbeFailed(f"AI probe returned malformed JSON: {raw[:200]}")

    confidence = result.get("confidence", "low")
    slug_regex = result.get("slug_regex")
    detail_url_template = result.get("detail_url_template")

    if confidence == "low":
        raise ProbeFailed(f"AI probe confidence=low: {result.get('reason', '')}")
    if not slug_regex or not detail_url_template:
        raise ProbeFailed(f"AI probe returned partial result: slug_regex={slug_regex}, detail_url_template={detail_url_template}")

    return result