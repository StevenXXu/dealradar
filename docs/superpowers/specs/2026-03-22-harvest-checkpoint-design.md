# DealRadar Harvest Checkpoint / Resume Design

## Status

Approved 2026-03-22.

## Overview

Add checkpoint-based resume to the Harvest phase so that interrupted runs can continue from the next uncompleted VC, and incremental results are persisted after each VC completes.

## Problem

`HarvesterPipeline.run()` currently processes all VC seeds sequentially and writes `raw_companies.json` only at the very end. Any interruption — network error, crash, Ctrl+C — causes all progress since the last manual save to be lost.

## Solution

A lightweight JSON state file (`data/harvest_state.json`) tracks completed VC slugs. The pipeline skips completed VCs on restart, appends new results to `raw_companies.json` rather than overwriting, and supports a `--force-restart` flag to clear state.

## State File

**Path:** `data/harvest_state.json`

**Schema:**
```json
{
  "completed_vcs": ["vc-slug-1", "vc-slug-2"],
  "last_updated": "2026-03-22T12:00:00Z"
}
```

## Components

### `src/harvester/state.py` (new)

```python
STATE_FILE = Path("data/harvest_state.json")

def load_state() -> set[str]:
    """Return set of completed VC slugs, or empty set if no state file."""

def mark_completed(slug: str) -> None:
    """Add slug to completed_vcs and save."""

def append_and_dedupe(new_companies: list[dict], output_path: str) -> None:
    """
    Load existing raw_companies.json (if exists),
    merge new_companies, dedupe by domain,
    write back atomically (rename pattern).
    """
```

Key behaviors:
- `load_state()`: if file missing or corrupt, return empty set (cold start)
- `mark_completed()`: read → modify → write atomically (read existing, update, write back)
- `append_and_dedupe()`: use `Path.rename` swap for atomic write so interruption cannot corrupt the file

### `src/harvester/pipeline.py` (modified)

In `run()`:

```
1. Load completed_vcs from state
2. Before scraping each VC: if slug in completed_vcs → skip
3. After each VC completes: mark_completed(slug); append_and_dedupe(new_companies)
4. --force-restart flag: delete state file before run
```

## Behavior by Scenario

| Scenario | Behavior |
|----------|----------|
| Run interrupted mid-VC | On restart, last completed VC is re-run; partial results from interrupted run are lost |
| Run completes all VCs | All slugs marked complete; next run skips all |
| VC list gains new VCs | Only new VCs are scraped |
| VC list removes a VC | Existing data preserved; stale state entry silently skipped |
| State file missing | Cold start — run all VCs |
| State file corrupt | Treated as empty — run all VCs |
| `--force-restart` passed | Clear state file, run all VCs from scratch |

## Files Changed

| File | Change |
|------|--------|
| `src/harvester/state.py` | New — state management |
| `src/harvester/pipeline.py` | Modify `run()` to use state; add `--force-restart` arg |
| `src/harvester/__init__.py` | Export state functions if needed |
| `tests/test_harvester_pipeline.py` | Add checkpoint tests |

## Testing

- `test_state_load_missing`: missing file → empty set
- `test_state_mark_completed`: marks slug, persists, accumulates
- `test_append_dedupe`: new companies merged, duplicate by domain removed
- `test_pipeline_skips_completed_vcs`: mock state, verify skipped
- `test_pipeline_force_restart`: verify state cleared on flag

## Out of Scope

- Detail-page-level (within a VC) resume
- Concurrent VC processing
- State file GC / pruning old entries
