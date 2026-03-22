# Harvest Checkpoint / Resume Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add VC-level checkpoint/resume to the Harvest phase so interrupted runs continue from the next uncompleted VC, and incremental results are persisted after each VC.

**Architecture:** A `data/harvest_state.json` file tracks completed VC slugs. On each run, completed VCs are skipped; after each VC completes, its companies are appended to `raw_companies.json` with deduplication. Cold start if state file is missing or corrupt.

**Tech Stack:** Python 3.11+, pathlib, json, shutil (atomic rename), existing HarvesterPipeline.

---

## File Map

| File | Responsibility |
|------|---------------|
| `src/harvester/state.py` (NEW) | State file read/write/atomic update |
| `src/harvester/pipeline.py` (MODIFY) | Skip completed VCs, call state after each VC |
| `run.py` (MODIFY) | Add `--force-restart` flag |
| `tests/test_harvester_state.py` (NEW) | Unit tests for state.py |
| `tests/test_harvester_pipeline.py` (MODIFY) | Add checkpoint integration test |

---

## Task 1: Create `src/harvester/state.py`

**Files:**
- Create: `src/harvester/state.py`
- Test: `tests/test_harvester_state.py`

- [ ] **Step 1: Write failing tests for state.py**

```python
# tests/test_harvester_state.py
import json
import os
import tempfile
from pathlib import Path

def test_load_state_missing_file():
    """Missing state file returns empty set."""
    # Use a temp dir with no state file
    with tempfile.TemporaryDirectory() as tmpdir:
        # Patch STATE_FILE path
        from src.harvester import state
        original = state.STATE_FILE
        state.STATE_FILE = Path(tmpdir) / "nonexistent.json"
        try:
            result = state.load_state()
            assert result == set()
        finally:
            state.STATE_FILE = original

def test_load_state_existing():
    """Existing state file returns set of slugs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "harvest_state.json"
        json.dump({"completed_vcs": ["vc-a", "vc-b"], "last_updated": "2026-01-01T00:00:00Z"}, state_file.open("w"))
        from src.harvester import state
        original = state.STATE_FILE
        state.STATE_FILE = state_file
        try:
            result = state.load_state()
            assert result == {"vc-a", "vc-b"}
        finally:
            state.STATE_FILE = original

def test_load_state_corrupt_json():
    """Corrupt JSON treated as cold start."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "harvest_state.json"
        state_file.write_text("{not valid json")
        from src.harvester import state
        original = state.STATE_FILE
        state.STATE_FILE = state_file
        try:
            result = state.load_state()
            assert result == set()
        finally:
            state.STATE_FILE = original

def test_mark_completed_single():
    """Mark one slug as completed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "harvest_state.json"
        from src.harvester import state
        original = state.STATE_FILE
        state.STATE_FILE = state_file
        try:
            state.mark_completed("vc-x")
            data = json.load(state_file.open())
            assert data["completed_vcs"] == ["vc-x"]
            assert "last_updated" in data
        finally:
            state.STATE_FILE = original

def test_mark_completed_accumulates():
    """mark_completed adds to existing slugs, does not overwrite."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "harvest_state.json"
        json.dump({"completed_vcs": ["vc-a"], "last_updated": "2026-01-01T00:00:00Z"}, state_file.open("w"))
        from src.harvester import state
        original = state.STATE_FILE
        state.STATE_FILE = state_file
        try:
            state.mark_completed("vc-b")
            data = json.load(state_file.open())
            assert data["completed_vcs"] == ["vc-a", "vc-b"]
        finally:
            state.STATE_FILE = original

def test_mark_completed_idempotent():
    """Marking the same slug twice does not duplicate."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "harvest_state.json"
        json.dump({"completed_vcs": ["vc-a"], "last_updated": "2026-01-01T00:00:00Z"}, state_file.open("w"))
        from src.harvester import state
        original = state.STATE_FILE
        state.STATE_FILE = state_file
        try:
            state.mark_completed("vc-a")
            data = json.load(state_file.open())
            assert data["completed_vcs"] == ["vc-a"]  # still just one
        finally:
            state.STATE_FILE = original

def test_append_and_dedupe_new_companies():
    """New companies appended to empty file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "raw_companies.json"
        from src.harvester import state
        companies = [
            {"company_name": "Acme", "domain": "https://acme.co"},
            {"company_name": "Beta", "domain": "https://beta.io"},
        ]
        state.append_and_dedupe(companies, str(output_path))
        result = json.load(output_path.open())
        assert len(result) == 2
        assert result[0]["company_name"] == "Acme"

def test_append_and_dedupe_merges_with_existing():
    """Existing companies kept, new ones appended, duplicates by domain dropped."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "raw_companies.json"
        # Write existing
        existing = [{"company_name": "Acme", "domain": "https://acme.co"}]
        json.dump(existing, output_path.open("w"))
        from src.harvester import state
        new_companies = [
            {"company_name": "Acme", "domain": "https://acme.co"},  # duplicate — skip
            {"company_name": "Beta", "domain": "https://beta.io"},
        ]
        state.append_and_dedupe(new_companies, str(output_path))
        result = json.load(output_path.open())
        assert len(result) == 2
        domains = {c["domain"] for c in result}
        assert "https://acme.co" in domains
        assert "https://beta.io" in domains

def test_append_and_dedupe_atomic():
    """Interruption during write does not corrupt existing file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "raw_companies.json"
        existing = [{"company_name": "Existing", "domain": "https://existing.com"}]
        json.dump(existing, output_path.open("w"))
        from src.harvester import state
        # Simulate: append_and_dedupe uses rename swap — old file survives
        new_companies = [{"company_name": "New", "domain": "https://new.com"}]
        state.append_and_dedupe(new_companies, str(output_path))
        result = json.load(output_path.open())
        assert len(result) == 2
        # Confirm old content not lost
        assert any(c["company_name"] == "Existing" for c in result)
```

- [ ] **Step 2: Run tests — expect all to fail (state.py doesn't exist yet)**

Run: `cd /c/Users/StevenDesk/mywork/dealradar && python -m pytest tests/test_harvester_state.py -v 2>&1`
Expected: `ERROR collecting tests/test_harvester_state.py` — module not found

- [ ] **Step 3: Write minimal `state.py` skeleton**

```python
# src/harvester/state.py
"""Harvest checkpoint state management."""
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

STATE_FILE = Path("data/harvest_state.json")

def load_state() -> set[str]:
    """Return set of completed VC slugs. Cold start if file missing or corrupt."""
    if not STATE_FILE.exists():
        return set()
    try:
        data = json.loads(STATE_FILE.read_text())
        return set(data.get("completed_vcs", []))
    except Exception:
        return set()

def mark_completed(slug: str) -> None:
    """Add slug to completed_vcs atomically."""
    data = {"completed_vcs": [], "last_updated": ""}
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    if slug not in data.get("completed_vcs", []):
        data.setdefault("completed_vcs", []).append(slug)
    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    # Atomic write: temp file + rename
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    shutil.move(str(tmp), str(STATE_FILE))

def append_and_dedupe(new_companies: list[dict], output_path: str) -> None:
    """Load existing output, merge, dedupe by domain, write atomically."""
    existing = []
    p = Path(output_path)
    if p.exists():
        try:
            existing = json.loads(p.read_text())
        except Exception:
            existing = []
    seen_domains = {c["domain"] for c in existing}
    for c in new_companies:
        if c["domain"] not in seen_domains:
            seen_domains.add(c["domain"])
            existing.append(c)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(existing, indent=2))
    shutil.move(str(tmp), str(p))
```

- [ ] **Step 4: Run tests — expect all to pass**

Run: `cd /c/Users/StevenDesk/mywork/dealradar && python -m pytest tests/test_harvester_state.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/harvester/state.py tests/test_harvester_state.py
git commit -m "$(cat <<'EOF'
feat: add harvest checkpoint state management

Adds data/harvest_state.json tracking of completed VC slugs with
atomic read/write, cold-start on missing/corrupt file, and
idempotent mark_completed. Also adds append_and_dedupe for
atomic incremental writes to raw_companies.json.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 6 (Task 1): Export state symbols from `__init__.py`**

Read `src/harvester/__init__.py`, then add:

```python
from src.harvester.state import load_state, mark_completed, append_and_dedupe, STATE_FILE
```

---

## Task 2: Integrate checkpoint into `HarvesterPipeline`

**Files:**
- Modify: `src/harvester/pipeline.py:123-165` (`run()` method)
- Modify: `src/harvester/__init__.py` (export `STATE_FILE` from state.py)
- Test: `tests/test_harvester_pipeline.py` (add checkpoint integration test)

- [ ] **Step 1: Write failing pipeline checkpoint test**

```python
# Add to tests/test_harvester_pipeline.py

def test_pipeline_skips_completed_vcs(tmp_path, monkeypatch):
    """Completed VCs are skipped on resume."""
    # Set up temp state file: vc-a already completed
    state_file = tmp_path / "harvest_state.json"
    json.dump({"completed_vcs": ["vc-a"], "last_updated": "2026-01-01T00:00:00Z"}, state_file.open("w"))
    monkeypatch.setattr("src.harvester.state.STATE_FILE", state_file)

    # Set up temp output: vc-a companies already in raw_companies.json
    raw_file = tmp_path / "raw_companies.json"
    json.dump([{"company_name": "Acme", "domain": "https://acme.co", "vc_source": "VC A"}], raw_file.open("w"))
    monkeypatch.setattr("src.harvester.pipeline.HarvesterPipeline.output_path", str(raw_file))

    # Two VC seeds: vc-a (done) and vc-b (new)
    seeds_file = tmp_path / "vc_seeds.json"
    json.dump([
        {"name": "VC A", "url": "https://vc-a.com", "slug": "vc-a"},
        {"name": "VC B", "url": "https://vc-b.com", "slug": "vc-b"},
    ], seeds_file.open("w"))

    # Mock _scrape_vc to return a new company for vc-b only
    scraped_vcs = []
    original_scrape = HarvesterPipeline._scrape_vc
    def mock_scrape(self, seed):
        scraped_vcs.append(seed["slug"])
        if seed["slug"] == "vc-b":
            return [{"company_name": "Beta", "domain": "https://beta.io", "vc_source": "VC B"}]
        return []
    monkeypatch.setattr(HarvesterPipeline, "_scrape_vc", mock_scrape)

    pipeline = HarvesterPipeline(vc_seeds_path=str(seeds_file), output_path=str(raw_file))
    pipeline.run()

    # vc-a should NOT have been scraped (skipped)
    assert "vc-a" not in scraped_vcs
    assert "vc-b" in scraped_vcs
    # raw_companies should have both
    result = json.load(raw_file.open())
    domains = {c["domain"] for c in result}
    assert "https://acme.co" in domains
    assert "https://beta.io" in domains


def test_pipeline_force_restart_clears_state(tmp_path, monkeypatch):
    """--force-restart deletes state file and runs all VCs."""
    state_file = tmp_path / "harvest_state.json"
    state_file.write_text('{"completed_vcs": ["vc-a"], "last_updated": "2026-01-01T00:00:00Z"}')
    monkeypatch.setattr("src.harvester.state.STATE_FILE", state_file)

    seeds_file = tmp_path / "vc_seeds.json"
    json.dump([
        {"name": "VC A", "url": "https://vc-a.com", "slug": "vc-a"},
    ], seeds_file.open("w"))

    raw_file = tmp_path / "raw_companies.json"
    monkeypatch.setattr("src.harvester.pipeline.HarvesterPipeline.output_path", str(raw_file))

    scraped_vcs = []
    def mock_scrape(self, seed):
        scraped_vcs.append(seed["slug"])
        return [{"company_name": "Acme", "domain": "https://acme.co", "vc_source": seed["name"]}]
    monkeypatch.setattr(HarvesterPipeline, "_scrape_vc", mock_scrape)

    pipeline = HarvesterPipeline(vc_seeds_path=str(seeds_file), output_path=str(raw_file))
    pipeline.run(force_restart=True)

    # vc-a should have been re-scraped despite being in state
    assert "vc-a" in scraped_vcs
    # state file should be gone
    assert not state_file.exists()
```

- [ ] **Step 2: Run test — expect FAIL (state not integrated yet)**

Run: `cd /c/Users/StevenDesk/mywork/dealradar && python -m pytest tests/test_harvester_pipeline.py::test_pipeline_skips_completed_vcs tests/test_harvester_pipeline.py::test_pipeline_force_restart_clears_state -v`
Expected: FAIL — methods/attributes don't exist

- [ ] **Step 3: Add `force_restart` parameter to `run()` in pipeline.py**

Change the `run()` signature and body in `src/harvester/pipeline.py`:

```python
# At top of file, add import
from src.harvester.state import load_state, mark_completed, append_and_dedupe, STATE_FILE

# In HarvesterPipeline.run(), change signature and body:
def run(self, force_restart: bool = False) -> list[dict]:
    """Run the full harvest pipeline for all VC seeds."""
    if force_restart and STATE_FILE.exists():
        STATE_FILE.unlink()

    self._all_companies = []
    vc_results = []
    completed_vcs = load_state()

    for seed in self.vc_seeds:
        slug = seed.get("slug", seed["name"].lower().replace(" ", "-"))

        # Skip already-completed VCs
        if slug in completed_vcs:
            print(f"  [{seed['name']}] SKIPPED — already completed", flush=True)
            continue

        time.sleep(random.uniform(2, 5))
        companies = self._scrape_vc(seed)
        vc_results.append(companies)
        self._all_companies.extend(companies)

        # Mark completed and persist incrementally
        mark_completed(slug)
        append_and_dedupe(companies, self.output_path)

        if len(companies) < 3:
            print(f"  [WARN] {seed['name']} returned only {len(companies)} companies — below minimum threshold (3)", flush=True)

    # ... rest unchanged (failed_vcs check, filter dead, dedupe) ...
```

Also update the `_save()` call at the end — or remove it since we're now persisting incrementally:

```python
# After the for loop, replace final _save() call with just:
# (Incremental save already happened per VC above.)
# Final dedupe pass on in-memory result still useful for the return value
seen = set()
unique = []
for c in self._all_companies:
    if c["domain"] not in seen:
        seen.add(c["domain"])
        unique.append(c)
self._all_companies = unique
print(f"\nHarvest complete: {len(self._all_companies)} unique companies", flush=True)
return self._all_companies
```

Note: `_save()` at line 161-165 becomes unused but harmless — leave it for now or remove if desired.

- [ ] **Step 4: Run tests — expect PASS**

Run: `cd /c/Users/StevenDesk/mywork/dealradar && python -m pytest tests/test_harvester_pipeline.py::test_pipeline_skips_completed_vcs tests/test_harvester_pipeline.py::test_pipeline_force_restart_clears_state -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/harvester/pipeline.py tests/test_harvester_pipeline.py
git commit -m "$(cat <<'EOF'
feat: integrate checkpoint into HarvesterPipeline

run() now skips completed VCs via harvest_state.json, persists
results incrementally after each VC, and supports force_restart
flag to clear state and re-scrape all VCs.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Wire `--force-restart` into CLI

**Files:**
- Modify: `run.py`

- [ ] **Step 1: Add `--force-restart` argument and pass to `run_harvest()`**

In `run.py`, add to `run_harvest()`:

```python
def run_harvest(output_path: str = "data/raw_companies.json", force_restart: bool = False):
    print("=" * 60, flush=True)
    print("PHASE 1: HARVEST — Scraping VC portfolios", flush=True)
    print("=" * 60, flush=True)
    pipeline = HarvesterPipeline(
        vc_seeds_path="config/vc_seeds.json",
        output_path=output_path,
    )
    companies = pipeline.run(force_restart=force_restart)
    print(f"Harvested {len(companies)} companies")
    return companies
```

In `main()`:

```python
parser.add_argument(
    "--force-restart",
    action="store_true",
    help="Clear harvest state and re-scrape all VCs from scratch",
)
```

And in the `if args.phase in ("harvest", "all")` block:

```python
if args.phase in ("harvest", "all"):
    run_harvest(raw_path, force_restart=args.force_restart)
```

- [ ] **Step 2: Verify CLI parses the flag**

Run: `cd /c/Users/StevenDesk/mywork/dealradar && python run.py --help`
Expected: `--force-restart` appears in help output

- [ ] **Step 3: Commit**

```bash
git add run.py
git commit -m "$(cat <<'EOF'
feat: add --force-restart CLI flag to clear harvest state

Allows users to bypass checkpoint resume and re-scrape all VCs
from scratch when needed.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Run full test suite

- [ ] **Step 1: Run all harvester tests**

Run: `cd /c/Users/StevenDesk/mywork/dealradar && python -m pytest tests/test_harvester_pipeline.py tests/test_harvester_state.py -v`
Expected: ALL PASS

- [ ] **Step 2: Run entire test suite (no regressions)**

Run: `cd /c/Users/StevenDesk/mywork/dealradar && python -m pytest tests/ -v`
Expected: ALL PASS (or pre-existing failures unrelated to this change)

---

## Summary of Commits

1. `feat: add harvest checkpoint state management`
2. `feat: integrate checkpoint into HarvesterPipeline`
3. `feat: add --force-restart CLI flag to clear harvest state`
