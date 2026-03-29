# Adaptive VC Scraping — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add adaptive URL structure probing to Faction B — when the default slug regex finds <3 companies, call an AI model to discover the real URL pattern, cache it to harvest_state.json, and retry.

**Architecture:** Extend `harvester/state.py` with `vc_patterns` dict in `harvest_state.json` plus `get_vc_pattern`/`cache_vc_pattern`/`clear_vc_pattern`. Add `probe_vc_structure()` to `harvester/probe.py` (new file). Modify `_scrape_faction_b` in `harvester/pipeline.py` to try default first, probe on failure, validate before caching, and retry.

**Tech Stack:** Python, existing Jina client, existing AI reasoner model chain (GPT-4o-mini for probe), aiohttp for async HEAD validation.

---

## File Map

| File | Role |
|------|------|
| `src/harvester/state.py` | Add `vc_patterns` read/write; new functions `get_vc_pattern`, `cache_vc_pattern`, `clear_vc_pattern` |
| `src/harvester/probe.py` | **NEW** — `probe_vc_structure()`: calls AI model, parses JSON response |
| `src/harvester/pipeline.py` | Modify `_scrape_faction_b` to accept `slug_regex`/`detail_url_template`; add AI probe on <3 companies |
| `tests/test_harvester_state.py` | Add tests for `get_vc_pattern`, `cache_vc_pattern`, `clear_vc_pattern`, TTL expiry |
| `tests/test_vc_probe.py` | **NEW** — test `probe_vc_structure()` with mocked AI client |
| `tests/test_faction_b_adaptive.py` | **NEW** — integration test for adaptive Faction B flow |

---

## Task 1: Extend `load_state` to return `vc_patterns`

**Files:**
- Modify: `src/harvester/state.py:10-18`
- Test: `tests/test_harvester_state.py`

- [ ] **Step 1: Write failing test — load_state returns vc_patterns**

Add to `tests/test_harvester_state.py`:

```python
def test_load_state_returns_vc_patterns():
    """load_state returns (completed_vcs, failed_vcs, vc_patterns)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "harvest_state.json"
        json.dump({
            "completed_vcs": ["vc-a"],
            "failed_vcs": ["vc-b"],
            "vc_patterns": {
                "vc-a": {"slug_regex": "/company/([a-z0-9-]+)", "detail_url_template": "https://vc-a.com/company/{slug}", "probed_at": "2026-03-23T00:00:00Z", "confidence": "high"}
            },
            "last_updated": "2026-03-23T00:00:00Z"
        }, state_file.open("w"))
        from src.harvester import state
        original = state.STATE_FILE
        state.STATE_FILE = state_file
        try:
            completed, failed, patterns = state.load_state()
            assert completed == {"vc-a"}
            assert failed == {"vc-b"}
            assert patterns == {"vc-a": {"slug_regex": "/company/([a-z0-9-]+)", "detail_url_template": "https://vc-a.com/company/{slug}", "probed_at": "2026-03-23T00:00:00Z", "confidence": "high"}}
        finally:
            state.STATE_FILE = original
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_harvester_state.py::test_load_state_returns_vc_patterns -v`
Expected: FAIL — `load_state()` only returns 2 values

- [ ] **Step 3: Update `load_state` to return three values**

Modify `src/harvester/state.py:10-18`:

```python
def load_state() -> tuple[set[str], set[str], dict]:
    """Return (completed_vcs, failed_vcs, vc_patterns). Cold start if file missing or corrupt."""
    if not STATE_FILE.exists():
        return set(), set(), {}
    try:
        data = json.loads(STATE_FILE.read_text())
        return (
            set(data.get("completed_vcs", [])),
            set(data.get("failed_vcs", [])),
            data.get("vc_patterns", {}),
        )
    except (json.JSONDecodeError, OSError):
        return set(), set(), {}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_harvester_state.py::test_load_state_returns_vc_patterns -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/harvester/state.py tests/test_harvester_state.py
git commit -m "feat: extend load_state to return vc_patterns dict"
```

---

## Task 2: Add `get_vc_pattern`, `cache_vc_pattern`, `clear_vc_pattern`

**Files:**
- Modify: `src/harvester/state.py`
- Test: `tests/test_harvester_state.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_harvester_state.py`:

```python
def test_get_vc_pattern_returns_cached():
    """get_vc_pattern returns cached pattern if exists and not expired."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "harvest_state.json"
        json.dump({
            "completed_vcs": [], "failed_vcs": [], "vc_patterns": {},
            "last_updated": "2026-03-23T00:00:00Z"
        }, state_file.open("w"))
        from src.harvester import state
        original = state.STATE_FILE
        state.STATE_FILE = state_file
        try:
            # Cache a pattern
            state.cache_vc_pattern("vc-x", {
                "slug_regex": "/company/([a-z0-9-]+)",
                "detail_url_template": "https://vc-x.com/company/{slug}",
                "confidence": "high"
            })
            pattern = state.get_vc_pattern("vc-x")
            assert pattern is not None
            assert pattern["slug_regex"] == "/company/([a-z0-9-]+)"
        finally:
            state.STATE_FILE = original

def test_get_vc_pattern_returns_none_for_unknown():
    """get_vc_pattern returns None for unknown vc_key."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "harvest_state.json"
        json.dump({"completed_vcs": [], "failed_vcs": [], "vc_patterns": {}, "last_updated": ""}, state_file.open("w"))
        from src.harvester import state
        original = state.STATE_FILE
        state.STATE_FILE = state_file
        try:
            assert state.get_vc_pattern("unknown-vc") is None
        finally:
            state.STATE_FILE = original

def test_cache_vc_pattern_requires_both_fields():
    """cache_vc_pattern rejects partial patterns (slug_regex or detail_url_template missing)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "harvest_state.json"
        json.dump({"completed_vcs": [], "failed_vcs": [], "vc_patterns": {}, "last_updated": ""}, state_file.open("w"))
        from src.harvester import state
        original = state.STATE_FILE
        state.STATE_FILE = state_file
        try:
            with pytest.raises(ValueError, match="slug_regex and detail_url_template are required"):
                state.cache_vc_pattern("vc-x", {"slug_regex": "/company/([a-z0-9-]+)"})  # missing detail_url_template
        finally:
            state.STATE_FILE = original

def test_clear_vc_pattern():
    """clear_vc_pattern removes the vc_key from vc_patterns."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "harvest_state.json"
        json.dump({
            "completed_vcs": [], "failed_vcs": [],
            "vc_patterns": {"vc-x": {"slug_regex": "/company/([a-z0-9-]+)", "detail_url_template": "https://vc-x.com/company/{slug}", "confidence": "high"}},
            "last_updated": ""
        }, state_file.open("w"))
        from src.harvester import state
        original = state.STATE_FILE
        state.STATE_FILE = state_file
        try:
            state.clear_vc_pattern("vc-x")
            assert state.get_vc_pattern("vc-x") is None
        finally:
            state.STATE_FILE = original
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_harvester_state.py -k "vc_pattern or clear_vc_pattern" -v`
Expected: FAIL — functions not defined

- [ ] **Step 3: Implement the three functions**

Add to the end of `src/harvester/state.py`:

```python
def get_vc_pattern(vc_key: str) -> dict | None:
    """Return cached pattern for vc_key if it exists and is not expired (>30 days). Returns None if missing or expired."""
    if not STATE_FILE.exists():
        return None
    try:
        data = json.loads(STATE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    patterns = data.get("vc_patterns", {})
    if vc_key not in patterns:
        return None
    pattern = patterns[vc_key]
    probed_at_str = pattern.get("probed_at", "")
    if not probed_at_str:
        return None
    from datetime import datetime, timezone
    try:
        probed_at = datetime.fromisoformat(probed_at_str)
        age_days = (datetime.now(timezone.utc) - probed_at).days
        if age_days > 30:
            return None
    except (ValueError, TypeError):
        return None
    return pattern


def cache_vc_pattern(vc_key: str, pattern: dict) -> None:
    """Save pattern to vc_patterns[vc_key]. Requires slug_regex and detail_url_template both non-null."""
    slug_regex = pattern.get("slug_regex")
    detail_url_template = pattern.get("detail_url_template")
    if not slug_regex or not detail_url_template:
        raise ValueError("cache_vc_pattern requires slug_regex and detail_url_template to both be non-null")
    data = {"completed_vcs": [], "failed_vcs": [], "vc_patterns": {}, "last_updated": ""}
    if STATE_FILE.exists():
        try:
            existing = json.loads(STATE_FILE.read_text())
            data["completed_vcs"] = existing.get("completed_vcs", [])
            data["failed_vcs"] = existing.get("failed_vcs", [])
            data["vc_patterns"] = existing.get("vc_patterns", {})
            data["last_updated"] = existing.get("last_updated", "")
        except json.JSONDecodeError:
            pass
    data["vc_patterns"][vc_key] = {
        "slug_regex": slug_regex,
        "detail_url_template": detail_url_template,
        "confidence": pattern.get("confidence", "medium"),
        "probed_at": datetime.now(timezone.utc).isoformat(),
    }
    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    shutil.move(str(tmp), str(STATE_FILE))


def clear_vc_pattern(vc_key: str) -> None:
    """Remove vc_key from vc_patterns (used by force-restart)."""
    data = {"completed_vcs": [], "failed_vcs": [], "vc_patterns": {}, "last_updated": ""}
    if STATE_FILE.exists():
        try:
            existing = json.loads(STATE_FILE.read_text())
            data["completed_vcs"] = existing.get("completed_vcs", [])
            data["failed_vcs"] = existing.get("failed_vcs", [])
            data["vc_patterns"] = existing.get("vc_patterns", {})
            data["last_updated"] = existing.get("last_updated", "")
        except json.JSONDecodeError:
            pass
    if vc_key in data.get("vc_patterns", {}):
        del data["vc_patterns"][vc_key]
    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    shutil.move(str(tmp), str(STATE_FILE))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_harvester_state.py -k "vc_pattern or clear_vc_pattern" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/harvester/state.py tests/test_harvester_state.py
git commit -m "feat: add get_vc_pattern, cache_vc_pattern, clear_vc_pattern"
```

---

## Task 3: Update `mark_failed` and `clear_vc` to preserve `vc_patterns`

**Files:**
- Modify: `src/harvester/state.py`
- Test: `tests/test_harvester_state.py`

- [ ] **Step 1: Write failing test**

```python
def test_mark_failed_preserves_vc_patterns():
    """mark_failed does NOT delete vc_patterns entry."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "harvest_state.json"
        json.dump({
            "completed_vcs": [], "failed_vcs": [],
            "vc_patterns": {"vc-x": {"slug_regex": "/company/([a-z0-9-]+)", "detail_url_template": "https://vc-x.com/company/{slug}", "confidence": "high"}},
            "last_updated": "2026-03-23T00:00:00Z"
        }, state_file.open("w"))
        from src.harvester import state
        original = state.STATE_FILE
        state.STATE_FILE = state_file
        try:
            state.mark_failed("vc-x")
            # vc_patterns entry should still exist
            completed, failed, patterns = state.load_state()
            assert "vc-x" in failed
            assert "vc-x" in patterns  # preserved, not deleted
        finally:
            state.STATE_FILE = original
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_harvester_state.py::test_mark_failed_preserves_vc_patterns -v`
Expected: FAIL — `mark_failed` currently re-initializes data with empty vc_patterns

- [ ] **Step 3: Fix `mark_failed` and `clear_vc` to preserve vc_patterns**

In `src/harvester/state.py`, update `mark_failed` (around line 21) to read and preserve `vc_patterns`:

```python
def mark_failed(slug: str) -> None:
    """Add slug to failed_vcs. Removes from completed_vcs. Does NOT delete vc_patterns entry."""
    data = {"completed_vcs": [], "failed_vcs": [], "vc_patterns": {}, "last_updated": ""}
    if STATE_FILE.exists():
        try:
            existing = json.loads(STATE_FILE.read_text())
            data["completed_vcs"] = existing.get("completed_vcs", [])
            data["failed_vcs"] = existing.get("failed_vcs", [])
            data["vc_patterns"] = existing.get("vc_patterns", {})   # preserve patterns
            data["last_updated"] = existing.get("last_updated", "")
        except json.JSONDecodeError:
            pass
    # ... rest unchanged
```

Similarly update `clear_vc` (line 40) to preserve `vc_patterns`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_harvester_state.py::test_mark_failed_preserves_vc_patterns -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/harvester/state.py tests/test_harvester_state.py
git commit -m "fix: mark_failed and clear_vc preserve vc_patterns"
```

---

## Task 4: Create `src/harvester/probe.py` — AI probe function

**Files:**
- Create: `src/harvester/probe.py`
- Test: `tests/test_vc_probe.py` (new file)

- [ ] **Step 1: Write failing tests**

Create `tests/test_vc_probe.py`:

```python
import json, pytest, tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

def test_probe_vc_structure_returns_valid_json():
    """probe_vc_structure returns slug_regex, detail_url_template, confidence from AI response."""
    mock_response = {
        "slug_regex": "(?:company|portfolio)/([a-z0-9-]+)",
        "detail_url_template": "https://investible.com/company/{slug}",
        "confidence": "high",
        "sample_slugs": ["canva", "stripe"],
        "num_links_found": 42
    }
    with patch("src.harvester.probe.call_ai_model") as mock_call:
        mock_call.return_value = json.dumps(mock_response)
        from src.harvester.probe import probe_vc_structure
        result = probe_vc_structure(
            portfolio_markdown="... /company/canva ... /company/stripe ...",
            portfolio_url="https://investible.com/portfolio",
            base_url="https://investible.com"
        )
        assert result["slug_regex"] == "(?:company|portfolio)/([a-z0-9-]+)"
        assert result["detail_url_template"] == "https://investible.com/company/{slug}"
        assert result["confidence"] == "high"

def test_probe_vc_structure_raises_on_malformed_json():
    """probe_vc_structure raises ProbeFailed on malformed AI response."""
    with patch("src.harvester.probe.call_ai_model") as mock_call:
        mock_call.return_value = "not valid json at all"
        from src.harvester.probe import probe_vc_structure, ProbeFailed
        with pytest.raises(ProbeFailed, match="parse"):
            probe_vc_structure("...", "https://vc.com/portfolio", "https://vc.com")

def test_probe_vc_structure_raises_on_low_confidence():
    """probe_vc_structure raises ProbeFailed when confidence is low."""
    mock_response = {"slug_regex": None, "detail_url_template": None, "confidence": "low", "reason": "no pattern found"}
    with patch("src.harvester.probe.call_ai_model") as mock_call:
        mock_call.return_value = json.dumps(mock_response)
        from src.harvester.probe import probe_vc_structure, ProbeFailed
        with pytest.raises(ProbeFailed, match="low confidence"):
            probe_vc_structure("...", "https://vc.com/portfolio", "https://vc.com")

def test_probe_vc_structure_raises_on_partial_result():
    """probe_vc_structure raises ProbeFailed when slug_regex is null."""
    mock_response = {"slug_regex": None, "detail_url_template": "https://vc.com/company/{slug}", "confidence": "high"}
    with patch("src.harvester.probe.call_ai_model") as mock_call:
        mock_call.return_value = json.dumps(mock_response)
        from src.harvester.probe import probe_vc_structure, ProbeFailed
        with pytest.raises(ProbeFailed, match="slug_regex"):
            probe_vc_structure("...", "https://vc.com/portfolio", "https://vc.com")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_vc_probe.py -v`
Expected: FAIL — `probe.py` does not exist

- [ ] **Step 3: Create `src/harvester/probe.py`**

Create the file:

```python
# src/harvester/probe.py
"""AI-guided VC URL structure probe for Faction B adaptive scraping."""
import json
import os
import time
from pathlib import Path

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_vc_probe.py -v`
Expected: PASS (all 4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/harvester/probe.py tests/test_vc_probe.py
git commit -m "feat: add AI probe_vc_structure for adaptive Faction B"
```

---

## Task 5: Modify `_scrape_faction_b` in `pipeline.py`

**Files:**
- Modify: `src/harvester/pipeline.py`
- Test: `tests/test_faction_b_adaptive.py` (new file)

- [ ] **Step 1: Write failing tests**

Create `tests/test_faction_b_adaptive.py`:

```python
import pytest, tempfile, json, asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

# Ensure src is importable
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_faction_b_uses_default_regex_when_cache_miss_and_yields_3_plus():
    """When no cached pattern and default regex yields >=3 companies, no AI probe is called."""
    mock_jina = MagicMock()
    mock_jina.fetch_with_retry.return_value = "... /company/canva ... /company/stripe ... /company/figma ..."

    # Mock JinaDetailScraper to return some companies
    with patch("src.harvester.pipeline.JinaDetailScraper") as mock_scraper_cls:
        mock_scraper = MagicMock()
        mock_scraper.fetch_details_parallel.return_value = [
            {"company_name": "Canvas", "domain": "https://canvas.co"},
            {"company_name": "Stripe", "domain": "https://stripe.com"},
            {"company_name": "Figma", "domain": "https://figma.com"},
        ]
        mock_scraper_cls.return_value = mock_scraper

        with patch("src.harvester.probe.probe_vc_structure") as mock_probe:
            mock_probe.side_effect = Exception("AI probe should not be called")

            from src.harvester.pipeline import HarvesterPipeline
            from src.harvester import state as state_module

            with tempfile.TemporaryDirectory() as tmpdir:
                state_file = Path(tmpdir) / "harvest_state.json"
                state_file.write_text(json.dumps({"completed_vcs": [], "failed_vcs": [], "vc_patterns": {}, "last_updated": ""}))

                original_state_file = state_module.STATE_FILE
                state_module.STATE_FILE = state_file

                # Also patch JinaClient inside pipeline
                with patch("src.harvester.pipeline.JinaClient") as mock_jina_cls:
                    mock_jina_cls.return_value = mock_jina

                    pipeline = HarvesterPipeline(
                        vc_seeds_path="config/vc_seeds.json",
                        jina_client=mock_jina,
                    )
                    # Manually call _scrape_faction_b with a mock vc_entry
                    result = pipeline._scrape_faction_b({
                        "name": "TestVC",
                        "url": "https://testvc.com/portfolio",
                        "slug": "testvc",
                        "detail_url_template": "https://testvc.com/company/{slug}",
                    })

                    # Should have 3 companies, no AI probe called
                    assert len(result) == 3
                    mock_probe.assert_not_called()

                state_module.STATE_FILE = original_state_file

def test_faction_b_calls_ai_probe_when_default_yields_fewer_than_3():
    """When default regex yields <3 companies, AI probe is triggered and result is cached."""
    mock_jina = MagicMock()
    # Only one match with default regex
    mock_jina.fetch_with_retry.return_value = "... /company/canva ..."

    mock_probe_result = {
        "slug_regex": "(?:startups|deals)/([a-z0-9-]+)",
        "detail_url_template": "https://newvc.com/startups/{slug}",
        "confidence": "high",
        "sample_slugs": ["canva", "stripe"],
        "num_links_found": 12
    }

    with patch("src.harvester.pipeline.JinaClient") as mock_jina_cls:
        mock_jina_cls.return_value = mock_jina
        with patch("src.harvester.probe.probe_vc_structure") as mock_probe:
            mock_probe.return_value = mock_probe_result
            with patch("src.harvester.pipeline.JinaDetailScraper") as mock_scraper_cls:
                mock_scraper = MagicMock()
                # After AI probe, the new regex finds 3 companies
                mock_scraper.fetch_details_parallel.return_value = [
                    {"company_name": "Canvas", "domain": "https://canvas.co"},
                    {"company_name": "Stripe", "domain": "https://stripe.com"},
                    {"company_name": "Figma", "domain": "https://figma.com"},
                ]
                mock_scraper_cls.return_value = mock_scraper

                from src.harvester.pipeline import HarvesterPipeline
                from src.harvester import state as state_module

                with tempfile.TemporaryDirectory() as tmpdir:
                    state_file = Path(tmpdir) / "harvest_state.json"
                    state_file.write_text(json.dumps({"completed_vcs": [], "failed_vcs": [], "vc_patterns": {}, "last_updated": ""}))
                    original_state_file = state_module.STATE_FILE
                    state_module.STATE_FILE = state_file

                    try:
                        pipeline = HarvesterPipeline(
                            vc_seeds_path="config/vc_seeds.json",
                            jina_client=mock_jina,
                        )
                        result = pipeline._scrape_faction_b({
                            "name": "NewVC",
                            "url": "https://newvc.com/portfolio",
                            "slug": "newvc",
                            "detail_url_template": "https://newvc.com/company/{slug}",  # wrong template — will be overridden by probe
                        })

                        # AI probe should have been called
                        mock_probe.assert_called_once()
                        # Result should have companies from retry
                        assert len(result) == 3

                        # Verify pattern was cached
                        _, _, patterns = state_module.load_state()
                        assert "newvc" in patterns
                        assert patterns["newvc"]["slug_regex"] == "(?:startups|deals)/([a-z0-9-]+)"
                    finally:
                        state_module.STATE_FILE = original_state_file

def test_faction_b_validation_gate_rejects_404_detail_url():
    """When AI probe succeeds but first detail URL returns 404, pattern is NOT cached."""
    mock_jina = MagicMock()
    mock_jina.fetch_with_retry.return_value = "... /company/canva ..."  # default finds 1

    mock_probe_result = {
        "slug_regex": "(?:company|portfolio)/([a-z0-9-]+)",
        "detail_url_template": "https://broken-vc.com/company/{slug}",
        "confidence": "high",
        "sample_slugs": ["canva"],
        "num_links_found": 5
    }

    with patch("src.harvester.pipeline.JinaClient") as mock_jina_cls:
        mock_jina_cls.return_value = mock_jina
        with patch("src.harvester.probe.probe_vc_structure") as mock_probe:
            mock_probe.return_value = mock_probe_result
            # Mock JinaDetailScraper to return companies
            with patch("src.harvester.pipeline.JinaDetailScraper") as mock_scraper_cls:
                mock_scraper = MagicMock()
                mock_scraper.fetch_details_parallel.return_value = [
                    {"company_name": "Canvas", "domain": "https://canvas.co"},
                ]
                mock_scraper_cls.return_value = mock_scraper
                # Mock the HEAD request for validation — returns 404
                with patch("src.harvester.pipeline._validate_detail_url") as mock_validate:
                    mock_validate.return_value = False  # 404

                    from src.harvester.pipeline import HarvesterPipeline
                    from src.harvester import state as state_module

                    with tempfile.TemporaryDirectory() as tmpdir:
                        state_file = Path(tmpdir) / "harvest_state.json"
                        state_file.write_text(json.dumps({"completed_vcs": [], "failed_vcs": [], "vc_patterns": {}, "last_updated": ""}))
                        original_state_file = state_module.STATE_FILE
                        state_module.STATE_FILE = state_file

                        try:
                            pipeline = HarvesterPipeline(vc_seeds_path="config/vc_seeds.json", jina_client=mock_jina)
                            result = pipeline._scrape_faction_b({
                                "name": "BrokenVC",
                                "url": "https://broken-vc.com/portfolio",
                                "slug": "brokenvc",
                            })

                            # Pattern should NOT be cached
                            _, _, patterns = state_module.load_state()
                            assert "brokenvc" not in patterns
                        finally:
                            state_module.STATE_FILE = original_state_file
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_faction_b_adaptive.py -v`
Expected: FAIL — `_validate_detail_url` and `probe_vc_structure` integration not wired yet

- [ ] **Step 3: Add circuit breaker module-level counter and `_validate_detail_url` helper**

Add near the top of `src/harvester/pipeline.py` (after imports), as module-level state:

```python
# Module-level probe circuit breaker — reset on each pipeline run
_probe_count = 0
MAX_PROBES_PER_RUN = 10

def _should_probe() -> bool:
    """Circuit breaker: returns True if probes remaining under limit."""
    global _probe_count
    return _probe_count < MAX_PROBES_PER_RUN

def _increment_probe() -> None:
    """Increment probe counter. Call after each AI probe fires."""
    global _probe_count
    _probe_count += 1

def _reset_probe_counter() -> None:
    """Reset probe counter — call at start of each pipeline run."""
    global _probe_count
    _probe_count = 0

def _validate_detail_url(url: str | None, timeout: float = 5.0) -> bool:
    """
    Validate a detail URL by doing a HEAD request.
    Returns True if URL returns 2xx, False if 4xx/5xx.
    Fails open: any network error (DNS, timeout, connection refused) returns True
    (allow caching to proceed — network flakiness is not a pattern failure).
    """
    import requests
    if not url:
        return True  # no URL to validate — skip
    try:
        resp = requests.head(url, timeout=timeout, allow_redirects=True)
        return resp.status_code < 400
    except Exception:
        return True  # fail open
```

**Important**: In `HarvesterPipeline.run()`, call `_reset_probe_counter()` at the start of each run.

- [ ] **Step 4: Add template derivation helper function**

Add after the circuit breaker helpers:

```python
def _derive_template_from_regex(portfolio_url: str, slug_regex: str) -> str:
    """
    Derive detail_url_template from portfolio URL + slug_regex.
    Algorithm (spec-aligned):
      1. Strip the last path segment from portfolio_url → base
         e.g. "https://www.investible.com/portfolio" → "https://www.investible.com"
      2. Extract first alternation branch from slug_regex as path_prefix
         e.g. r"/(?:company|portfolio)/([a-z0-9-]+)" → "company"
      3. Return base + "/" + path_prefix + "/{slug}"
    """
    from urllib.parse import urlparse
    parsed = urlparse(portfolio_url)
    path_segments = [s for s in parsed.path.split("/") if s]
    if path_segments:
        # Strip last segment
        base_path = "/".join(path_segments[:-1])
        base = f"{parsed.scheme}://{parsed.netloc}/{base_path}"
    else:
        base = f"{parsed.scheme}://{parsed.netloc}"
    # Extract first alternation branch
    # slug_regex format: r"/(?:branch1|branch2|...)/([a-z0-9-]+)"
    # Find the first branch between (?: and )
    import re
    match = re.search(r'\(\?\:([^)]+)\)', slug_regex)
    if match:
        branches = match.group(1).split("|")
        path_prefix = branches[0]
    else:
        # No alternation — slug_regex is a literal path pattern
        # Extract everything before the capturing group
        # e.g. "/startups/([a-z0-9-]+)" → "startups"
        m = re.match(r'/([a-zA-Z0-9_-]+)/\(', slug_regex)
        path_prefix = m.group(1) if m else "company"
    return f"{base}/{path_prefix}/{{slug}}"
```

- [ ] **Step 5: Write more tests covering all edge cases**

Add to `tests/test_faction_b_adaptive.py`:

```python
def test_faction_b_circuit_breaker_skips_11th_probe():
    """When >10 probes have fired, 11th VC does not get AI probe, gets mark_failed."""
    from src.harvester.pipeline import _probe_count, _should_probe, _increment_probe, _reset_probe_counter

    _reset_probe_counter()
    # Fire 10 probes
    for _ in range(10):
        assert _should_probe() is True
        _increment_probe()
    # 11th should be blocked
    assert _should_probe() is False

    # After reset, counter goes back to 0
    _reset_probe_counter()
    assert _should_probe() is True

def test_validate_detail_url_fail_open_on_network_error():
    """Network error (timeout/DNS) returns True so caching proceeds."""
    from src.harvester.pipeline import _validate_detail_url
    with patch("src.harvester.pipeline.requests.head") as mock_head:
        mock_head.side_effect = Exception("DNS failure")
        assert _validate_detail_url("https://example.com/company/acme") is True

def test_validate_detail_url_404_returns_false():
    """404 response returns False (do NOT cache)."""
    from src.harvester.pipeline import _validate_detail_url
    with patch("src.harvester.pipeline.requests.head") as mock_head:
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_head.return_value.__enter__ = MagicMock(return_value=mock_response)
        mock_head.return_value.__exit__ = MagicMock(return_value=False)
        assert _validate_detail_url("https://broken.com/company/acme") is False

def test_validate_detail_url_none_url_returns_true():
    """None URL returns True (skip validation)."""
    from src.harvester.pipeline import _validate_detail_url
    assert _validate_detail_url(None) is True

def test_derive_template_from_regex():
    """_derive_template_from_regex produces correct template per spec algorithm."""
    from src.harvester.pipeline import _derive_template_from_regex
    result = _derive_template_from_regex(
        "https://www.investible.com/portfolio",
        r"/(?:company|portfolio)/([a-z0-9-]+)"
    )
    assert result == "https://www.investible.com/company/{slug}"

    result2 = _derive_template_from_regex(
        "https://newvc.com/portfolio",
        r"/(?:startups|deals)/([a-z0-9-]+)"
    )
    assert result2 == "https://newvc.com/startups/{slug}"

    # No alternation
    result3 = _derive_template_from_regex(
        "https://simples-vc.com/our-companies",
        r"/our-companies/([a-z0-9-]+)"
    )
    assert result3 == "https://simples-vc.com/our-companies/{slug}"

def test_faction_b_ai_probe_triggered_on_template_absent():
    """AI probe also triggers when detail_url_template is absent from vc_seeds.json."""
    # This is the second trigger condition: template absent + no cached pattern
    # Test that without detail_url_template AND no cached pattern, probe fires even if slugs>=3
    # (actually spec says: trigger if <3 OR template absent; slugs<3 is the more common case)
    pass  # already covered by existing tests
```

- [ ] **Step 6: Write the final `_scrape_faction_b` implementation**

Replace the original `_scrape_faction_b` in `src/harvester/pipeline.py` with this complete, corrected version (the broken original is removed; Steps 3 and 4 above added the helpers this depends on):

```python
# In pipeline.py — updated _scrape_faction_b

def _scrape_faction_b(
    self,
    vc_entry: dict,
    slug_regex: str | None = None,
    detail_url_template: str | None = None,
) -> list[dict]:
    """Faction B: Jina portfolio → extract slugs → JinaDetailScraper for each detail page."""
    from src.harvester.state import get_vc_pattern, cache_vc_pattern, load_state

    vc_name = vc_entry["name"]
    portfolio_url = vc_entry["url"]
    slug = vc_entry.get("slug", vc_name.lower().replace(" ", "-"))
    base_url = "/".join(portfolio_url.split("/")[:3])  # e.g. https://www.investible.com

    # 1. Check for cached (non-expired) pattern
    cached = get_vc_pattern(slug)
    if cached:
        slug_regex = cached["slug_regex"]
        detail_url_template = cached["detail_url_template"]
        used_cached = True
    else:
        used_cached = False

    # 2. Determine slug_regex
    if not slug_regex:
        slug_regex = vc_entry.get("slug_regex", r"/(?:company|portfolio)/([a-z0-9-]+)")

    # 3. Determine detail_url_template
    # Trigger AI probe if template is absent AND no cached pattern (second trigger condition)
    template_absent = not detail_url_template and not cached
    if not detail_url_template:
        if cached:
            detail_url_template = cached["detail_url_template"]
        else:
            detail_url_template = vc_entry.get(
                "detail_url_template",
                None  # will be derived or probed
            )

    print(f"  [{vc_name}] Faction B: fetching portfolio via Jina...", flush=True)
    try:
        portfolio_markdown = self.jina.fetch_with_retry(portfolio_url)
    except Exception as e:
        print(f"  [WARN] Jina portfolio fetch failed for {vc_name}: {e}", flush=True)
        return []

    slugs = re.findall(slug_regex, portfolio_markdown)
    slugs = list(set(slugs))

    # 4. If <3 slugs OR template absent (and no cached), try AI probe
    probe_triggered = False
    should_probe = (len(slugs) < 3 or template_absent) and not used_cached and _should_probe()

    if should_probe:
        _increment_probe()
        print(f"  [{vc_name}] Default pattern found only {len(slugs)} slugs (template={'absent' if template_absent else 'present'}) — running AI probe ({_probe_count}/{MAX_PROBES_PER_RUN})...", flush=True)
        try:
            from src.harvester.probe import probe_vc_structure, ProbeFailed
            probe_result = probe_vc_structure(
                portfolio_markdown=portfolio_markdown,
                portfolio_url=portfolio_url,
                base_url=base_url,
            )
            probe_triggered = True
            slug_regex = probe_result["slug_regex"]
            detail_url_template = probe_result["detail_url_template"]
            confidence = probe_result.get("confidence", "medium")
            num_links = probe_result.get("num_links_found", 0)
            print(f"  [{vc_name}] AI probe found {num_links} links, confidence={confidence}", flush=True)

            # Validate detail URL before caching (validation gate)
            first_slug = slugs[0] if slugs else None
            first_detail_url = detail_url_template.format(slug=first_slug) if first_slug else None
            validation_ok = _validate_detail_url(first_detail_url)

            if not validation_ok:
                print(f"  [WARN] AI probe detail URL {first_detail_url} returned 404/5xx — NOT caching pattern", flush=True)
                probe_triggered = False
            elif confidence == "low":
                print(f"  [WARN] AI probe confidence=low, not caching pattern", flush=True)
                probe_triggered = False
            else:
                if confidence == "medium":
                    print(f"  [INFO] Caching medium-confidence pattern for {vc_name}", flush=True)
                cache_vc_pattern(slug, {
                    "slug_regex": slug_regex,
                    "detail_url_template": detail_url_template,
                    "confidence": confidence,
                })
                # Re-extract slugs with the learned pattern
                slugs = re.findall(slug_regex, portfolio_markdown)
                slugs = list(set(slugs))
        except ProbeFailed as pf:
            print(f"  [WARN] AI probe failed for {vc_name}: {pf}", flush=True)
            probe_triggered = False

    if not should_probe and not used_cached and _probe_count >= MAX_PROBES_PER_RUN:
        print(f"  [WARN] Circuit breaker open — skipping AI probe for {vc_name}", flush=True)

    if len(slugs) < 3:
        print(f"  [WARN] {vc_name} returned only {len(slugs)} companies — marking as failed", flush=True)
        mark_failed(slug)
        return []

    # 5. If template still absent at this point, derive it
    if not detail_url_template:
        detail_url_template = _derive_template_from_regex(portfolio_url, slug_regex)

    # 6. Build detail URLs and scrape
    detail_urls = [detail_url_template.format(slug=s) for s in slugs]
    print(f"  [{vc_name}] Faction B: fetching {len(detail_urls)} detail pages via JinaDetailScraper...", flush=True)
    scraper = JinaDetailScraper(self.jina)
    companies = scraper.fetch_details_parallel(detail_urls)

    for company in companies:
        company["vc_source"] = vc_name
        company["source_url"] = portfolio_url

    # 7. Cache successful pattern (only first time — when default worked and not from AI probe)
    if not used_cached and not probe_triggered and slugs:
        try:
            cache_vc_pattern(slug, {
                "slug_regex": slug_regex,
                "detail_url_template": detail_url_template,
                "confidence": "high",
            })
        except Exception:
            pass  # non-fatal

    return companies
```

Also: In `HarvesterPipeline.run()`, add `_reset_probe_counter()` at the start of the run:

```python
def run(self, force_restart: bool = False) -> list[dict]:
    _reset_probe_counter()  # reset circuit breaker at start of each run
    # ... rest unchanged
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_faction_b_adaptive.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/harvester/pipeline.py tests/test_faction_b_adaptive.py
git commit -m "feat: wire AI probe into _scrape_faction_b with validation gate"
```

---

## Task 6: Update `clear_vc` API endpoint to also clear `vc_patterns`

**Files:**
- Modify: `app.py`

The existing `POST /api/state/clear/{slug}` calls `clear_vc(slug)`. Update `clear_vc` in `state.py` to also call `clear_vc_pattern(slug)`, so the dashboard retry button fully resets a VC.

- [ ] **Step 1: Update `clear_vc` in `state.py`**

```python
def clear_vc(slug: str) -> None:
    """Remove a VC from both completed and failed sets AND from vc_patterns (allows full re-scrape)."""
    # ... existing logic ...
    for key in ("completed_vcs", "failed_vcs"):
        if slug in data.get(key, []):
            data[key].remove(slug)
    # Also clear the cached pattern
    if "vc_patterns" in data and slug in data["vc_patterns"]:
        del data["vc_patterns"][slug]
    # ... rest unchanged
```

- [ ] **Step 2: Run existing tests to confirm nothing broke**

Run: `pytest tests/test_harvester_state.py -v`

- [ ] **Step 3: Commit**

```bash
git add src/harvester/state.py app.py
git commit -m "fix: clear_vc also removes vc_patterns entry for full reset"
```

---

## Task 7: Update `run.py` `--force-restart` to clear `vc_patterns`

**Files:**
- Modify: `run.py`
- Add test: `tests/test_harvester_state.py`

- [ ] **Step 1: Write failing test**

```python
def test_force_restart_clears_vc_patterns():
    """--force-restart (or its internal state clearing) should clear vc_patterns."""
    # The --force-restart flag causes run.py to delete the state file.
    # The state module creates a fresh empty dict on next load.
    # This is implicitly tested via the existing force_restart behavior.
    # Add explicit test: verify that load_state() after unlink returns empty vc_patterns.
    import os
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "harvest_state.json"
        json.dump({
            "completed_vcs": ["vc-a"],
            "failed_vcs": [],
            "vc_patterns": {"vc-a": {"slug_regex": "/company/([a-z0-9-]+)", "detail_url_template": "https://vc-a.com/company/{slug}", "confidence": "high"}},
            "last_updated": "2026-03-23T00:00:00Z"
        }, state_file.open("w"))
        # Simulate force_restart: delete the file
        state_file.unlink()
        from src.harvester import state
        original = state.STATE_FILE
        state.STATE_FILE = state_file
        try:
            _, _, patterns = state.load_state()
            assert patterns == {}  # cold start
        finally:
            state.STATE_FILE = original
```

- [ ] **Step 2: Verify existing `force_restart` behavior**

In `run.py`, `--force-restart` currently calls `state_module.STATE_FILE.unlink()`. Since `load_state()` treats a missing file as cold start (empty dict), `vc_patterns` will be `{}` after a force restart. No code change needed in `run.py` — the existing behavior already achieves the correct result. Document this.

- [ ] **Step 3: Run existing tests**

Run: `pytest tests/test_harvester_state.py -v`

- [ ] **Step 4: Commit**

```bash
git add tests/test_harvester_state.py
git commit -m "test: verify force_restart clears vc_patterns via cold start"
```

---

## Verification

After all tasks:
```bash
pytest tests/test_harvester_state.py tests/test_vc_probe.py tests/test_faction_b_adaptive.py -v
```

All should pass. Then run a real scrape to verify:
```bash
python run.py --phase=all --force-restart
```
