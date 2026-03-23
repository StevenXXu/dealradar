# DealRadar Adaptive VC Scraping — Design Specification

**Date:** 2026-03-23
**Project:** DealRadar — Predictive Deal Intelligence CRM
**Status:** DRAFT
**Supersedes:** (none)

---

## Problem Statement

When a new VC is added to `vc_seeds.json`, Faction B requires knowing two things:
1. What URL path pattern do the VC's portfolio links follow? (e.g., `/company/{slug}`, `/portfolio/{slug}`)
2. What is the detail page URL template? (e.g., `https://vc.com/company/{slug}`)

Today these must be set manually in `vc_seeds.json`. If a VC uses a non-standard URL structure (e.g., `/startups/{slug}` instead of `/company/{slug}`), Faction B silently returns 0 companies and the VC goes to `failed_vcs` on every run.

Faction A handles structural diversity via its 3-tier fallback (Playwright → Jina → Apify). Faction B needs the same resilience.

---

## Design

### Core Idea

**Adaptive Faction B**: When the default slug pattern (`/(?:company|portfolio)/([a-z0-9-]+)`) yields fewer than 3 companies, the scraper calls an AI model to probe the portfolio page, discover the actual URL structure, and learn the correct slug regex + detail URL template. This is cached to `harvest_state.json` so subsequent runs use the cached pattern at no extra AI cost.

On every subsequent run, the cached pattern is used directly. Only `force_restart` or a retry-triggered probe changes the cached pattern.

---

### Data Model

**`vc_patterns` stored in `harvest_state.json`:**

```json
{
  "completed_vcs": ["investible", "archangels"],
  "failed_vcs": [],
  "last_updated": "2026-03-23T...",
  "vc_patterns": {
    "investible": {
      "slug_regex": "(?:company|portfolio)/([a-z0-9-]+)",
      "detail_url_template": "https://www.investible.com/company/{slug}",
      "probed_at": "2026-03-23T...",
      "confidence": "high"
    }
  }
}
```

- **`vc_patterns`**: keyed by `vc_key` (the VC identifier from `vc_seeds.json.slug`). Stores learned slug extraction pattern and detail URL template.
- **`probed_at`**: ISO timestamp when the pattern was learned. Used for cache staleness detection (see Cache Invalidation below).
- **`confidence`**: `high` / `medium` / `low`. Controls whether the pattern is cached (see Confidence Thresholds below).
- **Both `slug_regex` and `detail_url_template` must be non-null** for a pattern to be cached. Partial results (one field null) are treated as probe failure.

---

### Flow: Faction B with Adaptive Probing

```
1. Load vc_patterns from harvest_state.json

2. For each VC seed with faction_hint="b":
   a. If vc_patterns[vc_key] exists with both slug_regex and detail_url_template:
          → Use cached pattern. Skip to step 3 (slug extraction with learned pattern).

   b. Use slug_regex from vc_seeds.json if present, else default r"/(?:company|portfolio)/([a-z0-9-]+)"
   c. Build detail_urls using detail_url_template from vc_seeds.json if present, else:
          → If vc_patterns[vc_key] has detail_url_template: use it.
          → Else: derive from portfolio_url + slug_regex path prefix (see Template Derivation below).

   d. Attempt slug extraction with chosen slug_regex.
   e. If len(companies) >= 3:
          → Cache current slug_regex + detail_url_template to vc_patterns[vc_key].
          → Proceed to step 3.

   f. If len(companies) < 3 OR detail_url_template was absent from vc_seeds.json:
          → Trigger AI probe (see AI Probe Process below).
          → If AI probe returns non-null slug_regex AND non-null detail_url_template AND confidence != "low":
               → Validate: HEAD request to first detail URL (5s timeout). On 404/5xx: do not cache, mark_failed(vc_key), log warning. On success or network error (fail-open): cache result to vc_patterns[vc_key].
               → Retry slug extraction with learned pattern.
               → If retry len(companies) >= 3: proceed to step 3.
               → Else: mark_failed(vc_key).
          → Else (AI probe returned null, confidence="low", or partial result):
               → mark_failed(vc_key).
               → Log warning: "AI probe failed for {vc_name}".

3. Fetch detail pages for all slugs using detail_url_template.
   Validate: do a HEAD request to first detail URL. If 404/5xx: treat as probe failure (mark_failed), do not cache.
   (This prevents caching a broken pattern.)
4. Continue with standard company detail extraction (JinaDetailScraper).

```

---

### AI Probe Process

**Trigger conditions** (step 2f above):
- Default slug_regex yielded <3 companies, OR
- `detail_url_template` was absent from `vc_seeds.json` (no point trying default without a template)

**Model choice**: Use a lightweight model (GPT-4o-mini or Gemini Flash) for probing. Sufficient for URL pattern extraction. Falls back to the full reasoner model chain if the lightweight model fails.

**Prompt** — pass the raw portfolio markdown AND the base URL:

```
You are analyzing a VC portfolio page.

Portfolio page URL: {portfolio_url}
Base URL of this VC: {base_url}  (use this to resolve relative links and construct absolute URLs)

Raw content below:
---
{portfolio_markdown}
---

Your task:
1. Find all URLs in the content that look like individual portfolio company pages.
   Exclude: social media (linkedin.com, twitter.com, facebook.com), Crunchbase, PitchBook, Wikipedia, GitHub.
2. From those URLs, identify the common URL path pattern.
   - Example: if links are ".../company/canva", ".../company/stripe", the path pattern is "/company/{slug}".
   - Extract the slug (the variable path segment) from each match.
3. Determine the detail page URL template for this VC.
   - Use the base_url to construct absolute URLs: base_url + the path pattern with {slug} placeholder.
   - Example: base_url="https://www.investible.com" + path="/company/{slug}" → "https://www.investible.com/company/{slug}"
4. Report ONLY valid JSON (no preamble, no explanation):
{
  "slug_regex": "(?:company|portfolio)/([a-z0-9-]+)",  // regex with ONE capturing group for the slug
  "detail_url_template": "https://www.vc.com/company/{slug}",  // absolute URL with {slug} placeholder
  "confidence": "high",  // high: clear pattern, medium: some ambiguity, low: unclear/no clear pattern
  "sample_slugs": ["canva", "stripe", "figma"],  // up to 5 slug examples found
  "num_links_found": 42  // total candidate portfolio links found
}

If no clear company-detail URL pattern can be found:
{
  "slug_regex": null,
  "detail_url_template": null,
  "confidence": "low",
  "reason": "explanation of why pattern detection failed",
  "sample_slugs": [],
  "num_links_found": 0
}
```

**Response handling:**
- Parse JSON. If parse fails (malformed output, wrong format): treat as probe failure, do not cache.
- If `confidence == "low"`: do not cache, treat as probe failure.
- If `slug_regex` or `detail_url_template` is null: do not cache, treat as probe failure.
- If probe failure: call `mark_failed(vc_key)`, do not retry.

---

### Template Derivation (when detail_url_template absent)

When `detail_url_template` is absent from `vc_seeds.json` AND no cached pattern exists:
1. Take the portfolio URL (e.g., `https://www.investible.com/portfolio`)
2. Strip trailing path segment (`/portfolio`) → `https://www.investible.com`
3. Extract the slug_regex path prefix: take the first matching branch from the alternation, in the order it appears in the regex.
   - For `/(?:company|portfolio)/([a-z0-9-]+)` → first branch is `company`
   - For `/(?:startups|deals|company)/([a-z0-9-]+)` → first branch is `startups`
4. Append `/` + path_prefix + `/{slug}`

**Example**: `slug_regex = r"/(?:company|portfolio)/([a-z0-9-]+)"`
- Portfolio URL: `https://www.investible.com/portfolio`
- Step 2: base = `https://www.investible.com`
- Step 3: path_prefix = `company`
- Step 4: `https://www.investible.com/company/{slug}`

Note: This derivation is a fallback only. The AI probe result (step 2f) overrides it with the correct path if the AI finds a better match.

---

### Cache Invalidation

**TTL-based**: A cached pattern expires after **30 days** from `probed_at`. On each run:
- If cached pattern exists but `probed_at` > 30 days ago → re-probe (same logic as first run).
- `force_restart` also clears all `vc_patterns` entries (same as it clears completed_vcs today).

**Validation gate**: Before caching any learned pattern (from default success or AI probe), validate at least one detail URL resolves (HEAD request, 5s timeout). If 404/5xx, do not cache — treat as probe failure. This prevents a broken pattern from being locked in.

---

### Confidence Thresholds

| Confidence | Cache? | Behavior |
|---|---|---|
| `high` | Yes | Cache silently, use for scraping |
| `medium` | Yes | Cache with INFO log: "medium-confidence pattern cached for {vc_key}" |
| `low` | No | Do not cache, mark_failed, log warning |

---

### Changes to `state.py`

```python
def load_state() -> tuple[set[str], set[str], dict]:
    """Return (completed_vcs, failed_vcs, vc_patterns). Cold start if file missing or corrupt."""
    # ...

def get_vc_pattern(vc_key: str) -> dict | None:
    """Return cached pattern for vc_key, or None if missing or expired (>30 days)."""
    # reads vc_patterns[vc_key] from STATE_FILE, checks probed_at TTL

def cache_vc_pattern(vc_key: str, pattern: dict) -> None:
    """Save pattern to vc_patterns[vc_key]. Requires slug_regex and detail_url_template both non-null."""
    # validates both fields present, then writes atomically

def clear_vc_pattern(vc_key: str) -> None:
    """Remove vc_key from vc_patterns. Called by force-restart."""
    # removes key from vc_patterns dict, rewrites atomically
```

---

### Changes to `pipeline.py`

- `_scrape_faction_b(vc_entry, slug_regex=None, detail_url_template=None)` — parameters optional; if None, fall back to vc_seeds.json values → then default.
- After slug extraction, if len(slugs) < 3 and no cached pattern existed: call `probe_vc_structure()` (new function).
- `probe_vc_structure(portfolio_markdown, portfolio_url)` → calls AI model, returns `{slug_regex, detail_url_template, confidence}` or raises `ProbeFailed`.
- Before caching any learned pattern: validate first detail URL with a HEAD request. On 404/5xx: raise `ProbeFailed` (validation gate). On network error (timeout, DNS): fail-open — skip validation, proceed to cache (see Error Handling table).

---

### Error Handling

`mark_failed` does NOT delete the `vc_patterns[vc_key]` entry. Only `force_restart` or TTL expiry (>30 days) clears a cached pattern. A VC can have both a cached pattern and a `failed_vcs` entry simultaneously.

| Case | Behavior |
|------|---------|
| Default slug_regex yields <3 companies | Trigger AI probe |
| **AI probe** API error | mark_failed(vc_key), do not retry that run |
| **AI probe** timeout (>30s) | mark_failed(vc_key), do not retry that run |
| **AI probe** returns malformed JSON | mark_failed(vc_key), do not retry that run |
| **AI probe** confidence = "low" | Do not cache, mark_failed(vc_key) |
| **AI probe** returns partial result (one field null) | Do not cache, mark_failed(vc_key) |
| **Validation gate**: detail URL HEAD returns 404/5xx | Do not cache, mark_failed(vc_key), log warning |
| **Validation gate**: network error on HEAD request | Skip validation (fail-open: cache the pattern anyway), proceed |
| Cached pattern >30 days old | Re-probe as if first run |
| force_restart | Clear vc_patterns for affected VCs (along with completed_vcs) |

---

### Cost/Latency Budget

Worst case: 1 AI probe per new Faction B VC that has a non-standard URL structure.
- GPT-4o-mini probe: ~$0.001–0.005 per VC (short prompt, ~500 tokens output).
- Latency: ~2–5s per probe.
- Circuit breaker: if >10 AI probes fire in a single run, skip remaining probes, mark those VCs as failed, log warning. Prevents runaway cost on a batch of 100 new VCs with broken URLs.

---

## Testing Strategy

1. **`cache_vc_pattern` / `get_vc_pattern` roundtrip**: temp dir, write pattern, read back, verify fields.
2. **`get_vc_pattern` expiry**: seed a pattern with `probed_at` > 30 days ago, verify returns None.
3. **Faction B with mock AI — default success**: default pattern yields ≥3 companies → verify pattern cached, no AI call made.
4. **Faction B with mock AI — probe on failure**: default yields <3 → mock AI returns pattern → verify cached → verify retry with learned pattern.
5. **Faction B — validation gate**: mock AI returns valid pattern but detail URL HEAD returns 404 → verify NOT cached, mark_failed called.
6. **Confidence=low**: mock AI returns confidence=low → verify NOT cached, mark_failed called.
7. **Partial result**: mock AI returns slug_regex=null → verify NOT cached, mark_failed called.
8. **Force restart clears patterns**: verify `clear_vc_pattern` called and cached pattern gone after `--force-restart`.

---

## Open Questions

**Resolved:**
- Open Question 2 (template derivation) — yes, both `slug_regex` and `detail_url_template` are learned together during AI probe. Derivation from portfolio_url+slug_regex path prefix is a fallback when `detail_url_template` is absent but `slug_regex` is present in vc_seeds.json.
- AI model: use lightweight model (GPT-4o-mini) for probing; full chain as fallback.

**Still open:**
- Open Question 1 (model choice): confirmed lightweight. If lightweight model is unavailable, fall back to the full reasoner model chain.
