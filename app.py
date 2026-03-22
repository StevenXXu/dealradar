# app.py
"""DealRadar Dashboard — FastAPI backend."""
import asyncio
import json
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

app = FastAPI(title="DealRadar Dashboard")

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config" / "vc_seeds.json"
STATE_PATH = BASE_DIR / "data" / "harvest_state.json"
ENRICHED_PATH = BASE_DIR / "data" / "enriched_companies.json"

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# ─── VC Seed CRUD ───────────────────────────────────────────────────────

def _read_vc_seeds() -> list[dict]:
    if not CONFIG_PATH.exists():
        return []
    try:
        return json.loads(CONFIG_PATH.read_text())
    except Exception as e:
        print(f"[WARN] Failed to read vc_seeds.json: {e}")
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
    slug = seed.get("slug") or seed.get("name", "").lower().replace(" ", "-")
    if not slug:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="name or slug required")
    with _vc_lock:
        seeds = _read_vc_seeds()
        seeds.append({**seed, "slug": slug})
        _write_vc_seeds(seeds)
    return {"slug": slug}

@app.put("/api/vc-seeds/{slug}")
def update_vc_seed(slug: str, seed: dict):
    with _vc_lock:
        seeds = _read_vc_seeds()
        found = False
        for i, s in enumerate(seeds):
            if s.get("slug") == slug:
                seeds[i] = {**s, **seed, "slug": slug}
                found = True
                break
        if not found:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="slug not found")
        _write_vc_seeds(seeds)
    return {"slug": slug}

@app.delete("/api/vc-seeds/{slug}")
def delete_vc_seed(slug: str):
    with _vc_lock:
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
_vc_lock = threading.Lock()
_process_start_time = None
_vc_start_times: dict[str, float] = {}  # vc_name -> start time

def _parse_stdout_line(line: str) -> dict | None:
    """Map stdout lines to SSE event data."""
    line = line.strip()
    if not line:
        return None
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
                line = await asyncio.to_thread(p_local.stdout.readline)
                if line:
                    parsed = _parse_stdout_line(line)
                    if parsed:
                        yield f"event: progress\ndata: {json.dumps(parsed)}\n\n".encode()
                else:
                    time.sleep(0.5)
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