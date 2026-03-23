# DealRadar Dashboard MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local browser-based dashboard for DealRadar — VC seed CRUD and real-time scraping progress via SSE. One command: `python app.py`.

**Architecture:** FastAPI backend (`app.py`) serves a single HTML dashboard (`templates/index.html`). VC CRUD reads/writes `config/vc_seeds.json` directly. "Run Harvest" spawns `run.py` subprocess, stdout is parsed and streamed to browser via SSE. A 30-minute subprocess timeout kills hung processes.

**API Endpoints:**
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/vc-seeds` | List all VC seeds |
| POST | `/api/vc-seeds` | Add new VC seed |
| PUT | `/api/vc-seeds/{slug}` | Update VC seed |
| DELETE | `/api/vc-seeds/{slug}` | Delete VC seed |
| GET | `/api/state` | Get harvest checkpoint state (completed VCs, last run time) |
| GET | `/api/companies` | Get enriched companies (summary stats) |
| POST | `/api/run/start` | Start a harvest run (spawns subprocess) |
| GET | `/api/run/status` | Get current run status (idle/running) |
| POST | `/api/run/cancel` | Kill running subprocess |

**Tech Stack:** Python 3.11+, FastAPI, Uvicorn, vanilla HTML/JS.

---

## Dependency Note

**`fastapi` and `uvicorn` must be added to `requirements.txt` before running.** The plan adds this in Task 1, Step 1.

---

## File Map

| File | Responsibility |
|------|---------------|
| `requirements.txt` | Add fastapi + uvicorn |
| `app.py` (NEW) | FastAPI backend — VC CRUD, subprocess management, SSE |
| `templates/index.html` (NEW) | Dashboard SPA — VC table, run button, live output |
| `tests/test_dashboard_api.py` (NEW) | API unit tests for VC CRUD |

---

## Task 1: FastAPI skeleton + VC CRUD API

**Files:**
- Modify: `requirements.txt`
- Create: `app.py`
- Test: `tests/test_dashboard_api.py`

### Step 1: Add fastapi + uvicorn to requirements.txt

Add to `requirements.txt`:
```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
```

Run: `pip install fastapi "uvicorn[standard]"`

### Step 2: Create `app.py` skeleton

```python
# app.py
"""DealRadar Dashboard — FastAPI backend."""
import json
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI(title="DealRadar Dashboard")

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config" / "vc_seeds.json"
STATE_PATH = BASE_DIR / "data" / "harvest_state.json"
RAW_PATH = BASE_DIR / "data" / "raw_companies.json"
ENRICHED_PATH = BASE_DIR / "data" / "enriched_companies.json"

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# ─── VC Seed CRUD ───────────────────────────────────────────────────────

def _read_vc_seeds() -> list[dict]:
    if not CONFIG_PATH.exists():
        return []
    try:
        return json.loads(CONFIG_PATH.read_text())
    except Exception:
        return []

def _write_vc_seeds(seeds: list[dict]) -> None:
    tmp = CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(seeds, indent=2))
    shutil.move(str(tmp), str(CONFIG_PATH))

@app.get("/api/vc-seeds")
def list_vc_seeds():
    return _read_vc_seeds()

@app.post("/api/vc-seeds")
def add_vc_seed(seed: dict):
    seeds = _read_vc_seeds()
    slug = seed.get("slug") or seed["name"].lower().replace(" ", "-")
    seeds.append({**seed, "slug": slug})
    _write_vc_seeds(seeds)
    return {"slug": slug}

@app.put("/api/vc-seeds/{slug}")
def update_vc_seed(slug: str, seed: dict):
    seeds = _read_vc_seeds()
    for i, s in enumerate(seeds):
        if s.get("slug") == slug:
            seeds[i] = {**s, **seed, "slug": slug}
            break
    _write_vc_seeds(seeds)
    return {"slug": slug}

@app.delete("/api/vc-seeds/{slug}")
def delete_vc_seed(slug: str):
    seeds = [s for s in _read_vc_seeds() if s.get("slug") != slug]
    _write_vc_seeds(seeds)
    return {"ok": True}

# ─── State & Stats ─────────────────────────────────────────────────────

@app.get("/api/state")
def get_state():
    if not STATE_PATH.exists():
        return {"completed_vcs": [], "last_updated": None}
    try:
        data = json.loads(STATE_PATH.read_text())
        return data
    except Exception:
        return {"completed_vcs": [], "last_updated": None}

@app.get("/api/companies")
def get_companies():
    count = 0
    last_updated = None
    if ENRICHED_PATH.exists():
        try:
            companies = json.loads(ENRICHED_PATH.read_text())
            count = len(companies)
            if companies:
                last_updated = companies[0].get("scraped_at")
        except Exception:
            pass
    return {"count": count, "last_updated": last_updated}

# ─── Subprocess Management ──────────────────────────────────────────────

_process = None
_process_lock = threading.Lock()
_process_start_time = None
_vc_start_times: dict[str, float] = {}  # vc_name -> start time

def _parse_stdout_line(line: str) -> dict | None:
    """Map stdout lines to SSE event data."""
    line = line.strip()
    if not line:
        return None
    import re
    # [VC Name] SKIPPED — already completed
    if "SKIPPED" in line:
        m = re.search(r"\[([^\]]+)\] SKIPPED", line)
        if m:
            return {"vc": m.group(1), "status": "skipped", "companies": 0, "elapsed": 0}
    # Scraping VC Name (url)...
    if "Scraping" in line and "..." in line:
        m = re.search(r"Scraping (.+?) \(", line)
        if m:
            vc_name = m.group(1).strip()
            _vc_start_times[vc_name] = time.time()
            return {"vc": vc_name, "status": "scraping", "companies": 0, "elapsed": 0}
    # Playwright|Jina|Apify found N companies from VC Name
    if "found" in line and "companies from" in line:
        m = re.search(r"found (\d+) companies from (.+)", line)
        if m:
            vc_name = m.group(2).strip()
            elapsed = 0
            if vc_name in _vc_start_times:
                elapsed = int(time.time() - _vc_start_times.pop(vc_name))
            return {"vc": vc_name, "status": "done", "companies": int(m.group(1)), "elapsed": elapsed}
    # Harvest complete: N unique companies
    if "Harvest complete" in line:
        m = re.search(r"Harvest complete: (\d+)", line)
        if m:
            return {"vc": "system", "status": "harvest_complete", "total": int(m.group(1)), "elapsed": 0}
    return {"vc": "system", "status": "info", "message": line, "elapsed": 0}

@app.post("/api/run/start")
def start_run():
    global _process, _process_start_time
    with _process_lock:
        if _process is not None and _process.poll() is None:
            return {"error": "already running"}
        _process_start_time = time.time()
        _process = subprocess.Popen(
            ["python", "run.py", "--phase=harvest"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(BASE_DIR),
        )
    return {"ok": True, "pid": _process.pid}

@app.get("/api/run/status")
def get_run_status():
    global _process
    if _process is None:
        return {"running": False, "pid": None}
    poll = _process.poll()
    return {"running": poll is None, "pid": _process.pid if poll is None else None}

@app.post("/api/run/cancel")
def cancel_run():
    global _process
    with _process_lock:
        if _process is not None and _process.poll() is None:
            _process.terminate()
            _process = None
            return {"ok": True}
        _process = None
        return {"ok": True}

# ─── SSE Stream ────────────────────────────────────────────────────────

from fastapi.responses import StreamingResponse

def _kill_process():
    """Kill the subprocess due to timeout."""
    global _process
    with _process_lock:
        if _process is not None and _process.poll() is None:
            _process.terminate()
            _process = None

@app.get("/api/run/stream")
def stream_run():
    async def event_generator():
        global _process, _process_start_time

        # Start 30-minute timeout timer
        timer = threading.Timer(30 * 60, _kill_process)

        with _process_lock:
            p = _process

        if p is None:
            yield "event: done\ndata: {}\n\n".encode()
            return

        try:
            timer.start()
            while True:
                with _process_lock:
                    p_local = _process

                if p_local is None:
                    break

                poll = p_local.poll()
                if poll is not None:
                    # Drain remaining stdout
                    try:
                        remaining = p_local.stdout.read()
                        for line in remaining.splitlines(keepends=True):
                            parsed = _parse_stdout_line(line)
                            if parsed:
                                yield f"event: progress\ndata: {json.dumps(parsed)}\n\n".encode()
                    except Exception:
                        pass
                    # Send done with total + duration
                    duration = int(time.time() - (_process_start_time or time.time()))
                    total = 0
                    try:
                        if ENRICHED_PATH.exists():
                            data = json.loads(ENRICHED_PATH.read_text())
                            total = len(data)
                    except Exception:
                        pass
                    yield f"event: done\ndata: {json.dumps({'total': total, 'duration': duration})}\n\n".encode()
                    _process = None
                    break

                # Read available stdout
                line = p_local.stdout.readline()
                if line:
                    parsed = _parse_stdout_line(line)
                    if parsed:
                        yield f"event: progress\ndata: {json.dumps(parsed)}\n\n".encode()
                else:
                    import time as t
                    t.sleep(0.5)
        finally:
            timer.cancel()

    return StreamingResponse(event_generator(), media_type="text/event-stream")

# ─── Dashboard UI ───────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def dashboard():
    return templates.TemplateResponse("index.html", {"request": {}})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
```

### Step 3: Create `templates/` directory and `templates/index.html`

Create directory: `mkdir -p templates`

```html
<!-- templates/index.html -->
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>DealRadar Dashboard</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; color: #222; }
  h1 { font-size: 1.5rem; margin-bottom: 0.5rem; }
  .toolbar { display: flex; gap: 0.5rem; align-items: center; margin-bottom: 1rem; }
  button { padding: 0.4rem 0.8rem; cursor: pointer; }
  .btn-primary { background: #2563eb; color: white; border: none; border-radius: 4px; }
  .btn-danger { background: #dc2626; color: white; border: none; border-radius: 4px; }
  .btn-ghost { background: transparent; border: 1px solid #ccc; border-radius: 4px; }
  .stats { background: #f3f4f6; border-radius: 6px; padding: 0.75rem 1rem; margin-bottom: 1rem; font-size: 0.9rem; }
  .stats span { margin-right: 1.5rem; }
  table { width: 100%; border-collapse: collapse; margin-bottom: 1rem; }
  th, td { text-align: left; padding: 0.5rem; border-bottom: 1px solid #e5e7eb; }
  th { font-size: 0.8rem; text-transform: uppercase; color: #6b7280; }
  td input { width: 100%; box-sizing: border-box; border: none; background: transparent; font: inherit; }
  td input:focus { outline: 1px solid #2563eb; background: #eff6ff; border-radius: 2px; }
  .delete-btn { color: #dc2626; cursor: pointer; opacity: 0; transition: opacity 0.2s; font-size: 0.85rem; }
  tr:hover .delete-btn { opacity: 1; }
  .add-row td { color: #6b7280; cursor: pointer; }
  .add-row:hover { background: #f9fafb; }
  #output { background: #111827; color: #e5e7eb; border-radius: 6px; padding: 1rem; font-family: monospace; font-size: 0.8rem; max-height: 300px; overflow-y: auto; white-space: pre-wrap; margin-top: 1rem; }
  .run-status { display: inline-block; margin-left: 0.5rem; font-size: 0.85rem; color: #6b7280; }
  .spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid #2563eb; border-top-color: transparent; border-radius: 50%; animation: spin 0.6s linear infinite; vertical-align: middle; margin-right: 4px; }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>

<h1>DealRadar Dashboard</h1>

<div class="toolbar">
  <button class="btn-primary" id="runBtn" onclick="startRun()">Run Harvest</button>
  <button class="btn-ghost" onclick="refresh()">Refresh</button>
  <span class="run-status" id="runStatus"></span>
</div>

<div class="stats" id="stats">
  <span>VCs: <strong id="statVCs">—</strong></span>
  <span><strong id="statCompanies">—</strong> companies scraped</span>
  <span>Last run: <strong id="statLast">—</strong></span>
</div>

<h2 style="font-size: 1.1rem; margin-bottom: 0.5rem;">VC Seed Manager</h2>
<table id="vcTable">
  <thead>
    <tr>
      <th>Name</th><th>URL</th><th>Faction</th><th></th>
    </tr>
  </thead>
  <tbody id="vcBody"></tbody>
</table>
<div class="add-row" onclick="addVC()">+ Add VC</div>

<div id="output"></div>

<script>
const API = '';
let eventSource = null;

async function refresh() {
  const [seeds, state, companies] = await Promise.all([
    fetch(API + '/api/vc-seeds').then(r => r.json()),
    fetch(API + '/api/state').then(r => r.json()),
    fetch(API + '/api/companies').then(r => r.json()),
  ]);
  document.getElementById('statVCs').textContent = seeds.length;
  document.getElementById('statCompanies').textContent = companies.count;
  document.getElementById('statLast').textContent = state.last_updated ? new Date(state.last_updated).toLocaleString() : 'Never';
  renderTable(seeds);
}

function renderTable(seeds) {
  const tbody = document.getElementById('vcBody');
  tbody.innerHTML = seeds.map(s => `
    <tr data-slug="${s.slug}">
      <td><input value="${s.name}" onblur="saveVC('${s.slug}', 'name', this.value)"></td>
      <td><input value="${s.url}" onblur="saveVC('${s.slug}', 'url', this.value)"></td>
      <td><input value="${s.faction_hint || 'a'}" onblur="saveVC('${s.slug}', 'faction_hint', this.value)"></td>
      <td class="delete-btn" onclick="deleteVC('${s.slug}')">✕</td>
    </tr>
  `).join('');
}

async function addVC() {
  const name = prompt('VC name:');
  if (!name) return;
  const url = prompt('Portfolio URL:');
  if (!url) return;
  await fetch(API + '/api/vc-seeds', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({name, url}),
  });
  refresh();
}

async function saveVC(slug, field, value) {
  await fetch(API + '/api/vc-seeds/' + slug, {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({[field]: value}),
  });
}

async function deleteVC(slug) {
  await fetch(API + '/api/vc-seeds/' + slug, {method: 'DELETE'});
  refresh();
}

async function startRun() {
  if (eventSource) { cancelRun(); return; }
  const res = await fetch(API + '/api/run/start', {method: 'POST'}).then(r => r.json());
  if (res.error === 'already running') { alert('Already running'); return; }
  document.getElementById('runBtn').textContent = 'Cancel';
  document.getElementById('runBtn').className = 'btn-danger';
  document.getElementById('runStatus').innerHTML = '<span class="spinner"></span>Running...';
  document.getElementById('output').textContent = '';

  eventSource = new EventSource(API + '/api/run/stream');
  eventSource.addEventListener('progress', e => {
    const d = JSON.parse(e.data);
    const el = document.getElementById('output');
    const icon = d.status === 'done' ? '✓' : d.status === 'skipped' ? '⊘' : '›';
    el.textContent += `${icon} [${d.vc}] ${d.status === 'done' ? d.companies + ' companies' : d.status}\n`;
    el.scrollTop = el.scrollHeight;
  });
  eventSource.addEventListener('done', e => {
    eventSource.close();
    eventSource = null;
    document.getElementById('runBtn').textContent = 'Run Harvest';
    document.getElementById('runBtn').className = 'btn-primary';
    document.getElementById('runStatus').textContent = 'Done';
    refresh();
  });
}

async function cancelRun() {
  await fetch(API + '/api/run/cancel', {method: 'POST'});
  if (eventSource) { eventSource.close(); eventSource = null; }
  document.getElementById('runBtn').textContent = 'Run Harvest';
  document.getElementById('runBtn').className = 'btn-primary';
  document.getElementById('runStatus').textContent = 'Cancelled';
}

refresh();
</script>
</body>
</html>
```

### Step 4: Create `tests/test_dashboard_api.py`

```python
# tests/test_dashboard_api.py
import json
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

# Must import after path setup
from app import app, _read_vc_seeds, _write_vc_seeds, CONFIG_PATH

client = TestClient(app)

def test_list_vc_seeds(tmp_path, monkeypatch):
    """GET /api/vc-seeds returns seed list."""
    seed_file = tmp_path / "vc_seeds.json"
    seed_file.write_text('[{"name": "TestVC", "url": "https://test.vc", "slug": "test-vc"}]')
    monkeypatch.setattr("app.CONFIG_PATH", seed_file)
    response = client.get("/api/vc-seeds")
    assert response.status_code == 200
    assert response.json()[0]["name"] == "TestVC"

def test_add_vc_seed(tmp_path, monkeypatch):
    """POST /api/vc-seeds adds a new seed."""
    seed_file = tmp_path / "vc_seeds.json"
    seed_file.write_text("[]")
    monkeypatch.setattr("app.CONFIG_PATH", seed_file)
    response = client.post("/api/vc-seeds", json={"name": "NewVC", "url": "https://new.vc"})
    assert response.status_code == 200
    data = json.loads(seed_file.read_text())
    assert len(data) == 1
    assert data[0]["name"] == "NewVC"

def test_delete_vc_seed(tmp_path, monkeypatch):
    """DELETE /api/vc-seeds/{slug} removes seed."""
    seed_file = tmp_path / "vc_seeds.json"
    seed_file.write_text('[{"name": "ToDelete", "url": "https://del.vc", "slug": "todelete"}]')
    monkeypatch.setattr("app.CONFIG_PATH", seed_file)
    response = client.delete("/api/vc-seeds/todelete")
    assert response.status_code == 200
    data = json.loads(seed_file.read_text())
    assert len(data) == 0

def test_get_companies_empty(tmp_path, monkeypatch):
    """GET /api/companies returns 0 when file doesn't exist."""
    monkeypatch.setattr("app.ENRICHED_PATH", tmp_path / "nonexistent.json")
    response = client.get("/api/companies")
    assert response.status_code == 200
    assert response.json()["count"] == 0

def test_get_state_empty(tmp_path, monkeypatch):
    """GET /api/state returns empty completed_vcs when no state."""
    monkeypatch.setattr("app.STATE_PATH", tmp_path / "nonexistent.json")
    response = client.get("/api/state")
    assert response.status_code == 200
    assert response.json()["completed_vcs"] == []
```

### Step 5: Run tests

Run: `cd /c/Users/StevenDesk/mywork/dealradar && python -m pytest tests/test_dashboard_api.py -v`
Expected: PASS

### Step 6: Commit

```bash
git add requirements.txt app.py templates/index.html tests/test_dashboard_api.py
git commit -m "$(cat <<'EOF'
feat: add DealRadar dashboard MVP

FastAPI backend with VC seed CRUD, subprocess harvest management,
SSE progress streaming. Single-page HTML dashboard for VC management
and real-time scraping progress.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Verify SSE subprocess parsing + edge cases

**Files:**
- Modify: `app.py` (stdout parser improvements)
- Test: `tests/test_dashboard_api.py` (add SSE parse tests)

### Step 1: Add `test_parse_stdout_line` tests

```python
def test_parse_stdout_scraping():
    from app import _parse_stdout_line
    line = "Scraping Blackbird (https://blackbird.vc/portfolio)..."
    result = _parse_stdout_line(line)
    assert result["vc"] == "Blackbird"
    assert result["status"] == "scraping"

def test_parse_stdout_done():
    from app import _parse_stdout_line
    line = "Playwright found 23 companies from Blackbird"
    result = _parse_stdout_line(line)
    assert result["vc"] == "Blackbird"
    assert result["status"] == "done"
    assert result["companies"] == 23

def test_parse_stdout_skipped():
    from app import _parse_stdout_line
    line = "[Blackbird] SKIPPED — already completed"
    result = _parse_stdout_line(line)
    assert result["vc"] == "Blackbird"
    assert result["status"] == "skipped"

def test_parse_stdout_harvest_complete():
    from app import _parse_stdout_line
    line = "Harvest complete: 156 unique companies"
    result = _parse_stdout_line(line)
    assert result["status"] == "harvest_complete"
    assert result["total"] == 156
```

### Step 2: Run tests

Run: `cd /c/Users/StevenDesk/mywork/dealradar && python -m pytest tests/test_dashboard_api.py -v`
Expected: PASS

### Step 3: Commit

```bash
git add tests/test_dashboard_api.py
git commit -m "$(cat <<'EOF'
test: add dashboard API and stdout parser tests

Covers VC CRUD endpoints, state/companies reads, and
_parse_stdout_line pattern matching for SSE events.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: End-to-end verify

### Step 1: Manual smoke test

Run: `cd /c/Users/StevenDesk/mywork/dealradar && python -c "from app import app; print('FastAPI app loads OK')"`
Expected: Output shows FastAPI app loads without import errors

Run: `cd /c/Users/StevenDesk/mywork/dealradar && python app.py &` (in background, 5 seconds), then `curl http://127.0.0.1:8000/api/vc-seeds`
Expected: Returns JSON list of VC seeds

### Step 2: Commit

```bash
git commit -m "$(cat <<'EOF'
test: e2e smoke test confirms dashboard runs

FastAPI loads cleanly, /api/vc-seeds returns expected data.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)" 2>/dev/null || true
```

---

## Summary of Commits

1. `feat: add DealRadar dashboard MVP`
2. `test: add dashboard API and stdout parser tests`
3. `test: e2e smoke test confirms dashboard runs`
