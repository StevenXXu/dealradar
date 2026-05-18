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

from pydantic import BaseModel
from fastapi import FastAPI, Depends, HTTPException, Query, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from src.supabase.client import SupabaseClient
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

app = FastAPI(title="DealRadar Dashboard")

# CORS — allow the Next.js dev server (localhost:3000) and any
# additional origins set via DEALRADAR_CORS_ORIGINS (comma-separated).
# Production deploys must set this explicitly; the default list is
# loopback-only on purpose so a misconfigured prod doesn't accept *.
import os as _os
_cors_origins = [
    o.strip()
    for o in _os.getenv(
        "DEALRADAR_CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)

security = HTTPBearer()


def get_supabase():
    return SupabaseClient()


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Resolve the caller's tenant context.

    WARNING — UNAUTHENTICATED. The HTTPBearer dependency only checks
    that *some* Bearer token is present in the Authorization header;
    the token value is never validated. Any caller that supplies any
    string will be authorized as the default tenant.

    This is intentional placeholder behaviour for the single-tenant
    pivot (one fund, internal use only). It MUST be replaced before:
      - exposing the API on any non-loopback interface
      - onboarding a second tenant
      - allowing untrusted users to hit /api/run/* or /api/vc-seeds

    Suggested next step (per single-tenant plan): swap to a shared API
    key check against an env-var DEALRADAR_API_KEY, then layer Clerk
    JWT validation only when multi-tenancy becomes a real requirement.
    """
    _ = credentials.credentials  # presence enforced by HTTPBearer
    return {
        "user_id": "single_tenant_user",
        "tenant_id": "default",
    }


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
        return {"completed_vcs": [], "failed_vcs": [], "last_updated": None}
    try:
        data = json.loads(STATE_PATH.read_text())
        return data
    except Exception:
        return {"completed_vcs": [], "failed_vcs": [], "last_updated": None}


@app.post("/api/state/clear/{slug}")
def clear_vc_state(slug: str):
    """Clear a VC from completed/failed state so it re-scrapes on next run."""
    from src.harvester.state import clear_vc

    clear_vc(slug)
    return {"ok": True, "slug": slug}


def _resolve_tenant_uuid(client: SupabaseClient, tenant: dict) -> str | None:
    """Map the verify_token shorthand 'default' to the actual tenants.id
    UUID. Returns None if the lookup fails (caller should treat as
    'no tenant context' and return an empty result rather than 500)."""
    t_id = tenant.get("tenant_id")
    if t_id and t_id != "default":
        return t_id
    try:
        res = (
            client._client.table("tenants")
            .select("id")
            .eq("slug", "default")
            .execute()
        )
        if res.data:
            return res.data[0]["id"]
    except Exception:
        return None
    return None


@app.get("/api/companies")
def get_companies(tenant: dict = Depends(verify_token)):
    """Legacy meta endpoint used by templates/index.html. New code
    should call /api/companies/list and /api/companies/summary."""
    client = get_supabase()
    try:
        t_id = _resolve_tenant_uuid(client, tenant)
        if t_id is None:
            return {"count": 0, "last_updated": None}

        res = (
            client._client.table("companies")
            .select("id", count="exact")
            .eq("tenant_id", t_id)
            .execute()
        )
        count = res.count if res.count is not None else len(res.data)

        latest = (
            client._client.table("companies")
            .select("updated_at")
            .eq("tenant_id", t_id)
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
        )
        last_updated = latest.data[0]["updated_at"] if latest.data else None

        return {"count": count, "last_updated": last_updated}
    except Exception as e:
        return {"count": 0, "last_updated": None, "error": str(e)}


# ─── Companies: paginated list + summary ─────────────────────────────
# Backs the Next.js discovery dashboard. Replaces direct
# Supabase queries from frontend/app/page.tsx so the frontend has a
# stable contract and we keep the service-role key off the browser.


@app.get("/api/companies/list")
def list_companies(
    sector: str | None = None,
    region: str | None = None,
    funding_stage: str | None = None,
    min_score: int = 0,
    search: str | None = None,
    page: int = Query(0, ge=0),
    page_size: int = Query(50, ge=1, le=200),
    tenant: dict = Depends(verify_token),
):
    """Paginated company list with the same filter dimensions the
    discovery dashboard exposes. All filters are AND-combined. Search
    matches company_name/domain/one_liner via ILIKE.

    Returns total count via Supabase's count='exact' so the client
    can render pagination without a second round trip.
    """
    client = get_supabase()
    try:
        t_id = _resolve_tenant_uuid(client, tenant)
        if t_id is None:
            return {
                "items": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
                "has_more": False,
            }

        start = page * page_size
        end = start + page_size - 1

        q = (
            client._client.table("companies")
            .select("*", count="exact")
            .eq("tenant_id", t_id)
            .order("signal_score", desc=True)
        )
        if sector and sector != "All Sectors":
            q = q.eq("sector", sector)
        if region and region != "All Regions":
            q = q.eq("region", region)
        if funding_stage and funding_stage != "All Stages":
            q = q.eq("funding_stage", funding_stage)
        if min_score > 0:
            q = q.gte("signal_score", min_score)
        if search and search.strip():
            s = search.strip().replace("%", "")  # avoid wildcard injection
            q = q.or_(
                f"company_name.ilike.%{s}%,"
                f"domain.ilike.%{s}%,"
                f"one_liner.ilike.%{s}%"
            )

        res = q.range(start, end).execute()
        items = res.data or []
        total = res.count if res.count is not None else len(items)
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_more": (start + len(items)) < total,
        }
    except Exception as e:
        return {
            "items": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "has_more": False,
            "error": str(e),
        }


@app.get("/api/companies/summary")
def companies_summary(tenant: dict = Depends(verify_token)):
    """Global facets (counts by region/sector/funding_stage) + header
    stats (total, hot count, average score, new-this-week) for the
    discovery dashboard sidebar and stats bar.

    Computes in Python over the full tenant set. Acceptable while the
    tenant fits in a single fetch (~1k rows today); a SQL GROUP BY
    via Supabase RPC will be needed past ~10k rows.
    """
    from datetime import datetime, timedelta, timezone

    client = get_supabase()
    try:
        t_id = _resolve_tenant_uuid(client, tenant)
        if t_id is None:
            return {
                "facets": {"regions": {}, "sectors": {}, "funding_stages": {}},
                "stats": {
                    "total": 0,
                    "hot_count": 0,
                    "avg_score": 0,
                    "new_this_week": 0,
                },
            }

        # Pull only the columns we aggregate over. region/funding_stage
        # may not exist on databases that haven't run migration 002 —
        # fall back to a narrower select in that case.
        try:
            res = (
                client._client.table("companies")
                .select("region, sector, funding_stage, signal_score, created_at")
                .eq("tenant_id", t_id)
                .execute()
            )
        except Exception:
            res = (
                client._client.table("companies")
                .select("sector, signal_score, created_at")
                .eq("tenant_id", t_id)
                .execute()
            )
        rows = res.data or []

        regions: dict[str, int] = {}
        sectors: dict[str, int] = {}
        funding_stages: dict[str, int] = {}
        total = len(rows)
        hot_count = 0
        score_sum = 0
        new_this_week = 0
        week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        for r in rows:
            region = r.get("region")
            if region:
                regions[region] = regions.get(region, 0) + 1
            sector = r.get("sector")
            if sector:
                sectors[sector] = sectors.get(sector, 0) + 1
            stage = r.get("funding_stage")
            if stage:
                funding_stages[stage] = funding_stages.get(stage, 0) + 1
            score = r.get("signal_score") or 0
            score_sum += score
            if score >= 30:
                hot_count += 1
            created = r.get("created_at")
            if created:
                try:
                    # Supabase returns ISO 8601; tolerate trailing Z
                    created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    if created_dt >= week_ago:
                        new_this_week += 1
                except (ValueError, AttributeError):
                    pass

        avg_score = (score_sum / total) if total else 0
        return {
            "facets": {
                "regions": regions,
                "sectors": sectors,
                "funding_stages": funding_stages,
            },
            "stats": {
                "total": total,
                "hot_count": hot_count,
                "avg_score": round(avg_score, 2),
                "new_this_week": new_this_week,
            },
        }
    except Exception as e:
        return {
            "facets": {"regions": {}, "sectors": {}, "funding_stages": {}},
            "stats": {
                "total": 0,
                "hot_count": 0,
                "avg_score": 0,
                "new_this_week": 0,
            },
            "error": str(e),
        }


# ─── Watchlist + monitor events ─────────────────────────────────────
# Ports dealflow monitor.py's WATCHLIST_RULES + verified_metrics
# ingestion endpoint to Supabase-backed persistence.


from src.commander.watchlist import WatchlistService, VALID_MONITOR_STATES


def get_watchlist_service() -> WatchlistService:
    return WatchlistService()


class WatchlistUpdate(BaseModel):
    watchlisted: bool
    monitor_state: str | None = None
    notes: str | None = None


class VerifiedMetricsIngest(BaseModel):
    verified_metrics: dict
    evidence_source: str | None = None


@app.get("/api/companies/{company_id}/watchlist")
def get_company_watchlist(
    company_id: str, tenant: dict = Depends(verify_token)
):
    svc = get_watchlist_service()
    state = svc.get_watchlist(company_id)
    if state is None:
        raise HTTPException(status_code=404, detail="company not found")
    return {
        "company_id": state.company_id,
        "watchlisted": state.watchlisted,
        "monitor_state": state.monitor_state,
        "watchlist_notes": state.watchlist_notes,
        "verified_metrics": state.verified_metrics,
    }


@app.put("/api/companies/{company_id}/watchlist")
def set_company_watchlist(
    company_id: str,
    update: WatchlistUpdate,
    tenant: dict = Depends(verify_token),
):
    if update.monitor_state is not None and update.monitor_state not in VALID_MONITOR_STATES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"monitor_state must be one of {sorted(VALID_MONITOR_STATES)}, "
                f"got {update.monitor_state!r}"
            ),
        )
    svc = get_watchlist_service()
    try:
        state = svc.set_watchlist(
            company_id,
            watchlisted=update.watchlisted,
            monitor_state=update.monitor_state,
            notes=update.notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if state is None:
        raise HTTPException(status_code=404, detail="company not found")
    return {
        "company_id": state.company_id,
        "watchlisted": state.watchlisted,
        "monitor_state": state.monitor_state,
        "watchlist_notes": state.watchlist_notes,
    }


@app.post("/api/companies/{company_id}/verified-metrics")
def ingest_verified_metrics(
    company_id: str,
    payload: VerifiedMetricsIngest,
    tenant: dict = Depends(verify_token),
):
    svc = get_watchlist_service()
    result = svc.ingest_verified_metrics(
        company_id,
        incoming_metrics=payload.verified_metrics,
        evidence_source=payload.evidence_source or "api",
    )
    if result.get("status") == "rejected":
        raise HTTPException(status_code=400, detail=result.get("reason", "rejected"))
    return result


@app.get("/api/monitor/events")
def list_monitor_events(
    limit: int = Query(50, ge=1, le=500),
    company_id: str | None = None,
    tenant: dict = Depends(verify_token),
):
    svc = get_watchlist_service()
    events = svc.recent_events(limit=limit, company_id=company_id)
    return {"events": events, "count": len(events)}


# ─── Tenant Alerts ───────────────────────────────────────────────────────

class AlertConfig(BaseModel):
    slack_webhook_url: str | None = None
    custom_webhook_url: str | None = None

@app.get("/api/tenant/alerts")
def get_tenant_alerts(tenant: dict = Depends(verify_token)):
    client = get_supabase()
    try:
        t_id = tenant["tenant_id"]
        if t_id == "default":
            t_res = client._client.table("tenants").select("id").eq("slug", "default").execute()
            if t_res.data:
                t_id = t_res.data[0]["id"]
        
        res = client._client.table("tenants").select("slack_webhook_url, custom_webhook_url").eq("id", t_id).execute()
        if res.data:
            return res.data[0]
        return {}
    except Exception as e:
        return {"error": str(e)}

@app.put("/api/tenant/alerts")
def update_tenant_alerts(config: AlertConfig, tenant: dict = Depends(verify_token)):
    client = get_supabase()
    try:
        t_id = tenant["tenant_id"]
        if t_id == "default":
            t_res = client._client.table("tenants").select("id").eq("slug", "default").execute()
            if t_res.data:
                t_id = t_res.data[0]["id"]
                
        client._client.table("tenants").update({
            "slack_webhook_url": config.slack_webhook_url,
            "custom_webhook_url": config.custom_webhook_url
        }).eq("id", t_id).execute()
        
        return {"ok": True}
    except Exception as e:
        return {"error": str(e)}

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
    # marked as failed, will retry
    if "marked as failed" in line:
        m = re.search(r"\[([^\]]+)\]", line)
        if m:
            return {"vc": m.group(1), "status": "failed", "companies": 0, "elapsed": 0}
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
            return {
                "vc": vc_name,
                "status": "done",
                "companies": int(m.group(1)),
                "elapsed": elapsed,
            }
    # Harvest complete: N unique companies
    if "Harvest complete" in line:
        m = re.search(r"Harvest complete: (\d+)", line)
        if m:
            return {
                "vc": "system",
                "status": "harvest_complete",
                "total": int(m.group(1)),
                "elapsed": 0,
            }
    return {"vc": "system", "status": "info", "message": line, "elapsed": 0}


import os
import redis

redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.Redis.from_url(redis_url, decode_responses=True)


def _get_celery():
    """Lazy import the worker module + Celery's AsyncResult.

    The worker imports run.py which imports the harvester, which
    imports Playwright. We do not want the bare FastAPI dashboard to
    require those heavy deps just to serve /api/companies/list, so
    everything Celery-related is deferred until the /api/run/* routes
    actually fire.
    """
    from celery.result import AsyncResult
    from src.worker.tasks import run_pipeline

    return AsyncResult, run_pipeline


@app.post("/api/run/start")
def start_run():
    AsyncResult, run_pipeline = _get_celery()
    current_task_id = redis_client.get("latest_pipeline_task")
    if current_task_id:
        task = AsyncResult(current_task_id)
        if not task.ready():
            return {"error": "already running"}

    task = run_pipeline.delay(force_restart=False)
    redis_client.set("latest_pipeline_task", task.id)
    redis_client.set("pipeline_start_time", str(time.time()))
    return {"ok": True, "task_id": task.id}


@app.get("/api/run/status")
def get_run_status():
    AsyncResult, _ = _get_celery()
    current_task_id = redis_client.get("latest_pipeline_task")
    if not current_task_id:
        return {"running": False, "task_id": None}
    task = AsyncResult(current_task_id)
    return {"running": not task.ready(), "task_id": current_task_id}


@app.post("/api/run/cancel")
def cancel_run():
    AsyncResult, _ = _get_celery()
    current_task_id = redis_client.get("latest_pipeline_task")
    if current_task_id:
        task = AsyncResult(current_task_id)
        if not task.ready():
            task.revoke(terminate=True)
            redis_client.publish(f"task_logs:{current_task_id}", "event: done\n")
            return {"ok": True}
    return {"ok": True}


@app.get("/api/run/stream")
def stream_run():
    AsyncResult, _ = _get_celery()

    async def event_generator():
        current_task_id = redis_client.get("latest_pipeline_task")
        if not current_task_id:
            yield "event: done\ndata: {}\n\n".encode()
            return

        task = AsyncResult(current_task_id)
        if task.ready():
            # If already done, just return done event
            duration = int(
                time.time()
                - float(redis_client.get("pipeline_start_time") or time.time())
            )
            total = 0
            if ENRICHED_PATH.exists():
                try:
                    data = json.loads(ENRICHED_PATH.read_text())
                    total = len(data)
                except Exception:
                    pass
            yield f"event: done\ndata: {json.dumps({'total': total, 'duration': duration})}\n\n".encode()
            return

        pubsub = redis_client.pubsub()
        channel = f"task_logs:{current_task_id}"
        pubsub.subscribe(channel)

        try:
            # Yield any existing history first
            history = redis_client.lrange(f"{channel}:history", 0, -1)
            for line in history:
                if line == "event: done\n":
                    duration = int(
                        time.time()
                        - float(redis_client.get("pipeline_start_time") or time.time())
                    )
                    total = 0
                    if ENRICHED_PATH.exists():
                        try:
                            data = json.loads(ENRICHED_PATH.read_text())
                            total = len(data)
                        except Exception:
                            pass
                    yield f"event: done\ndata: {json.dumps({'total': total, 'duration': duration})}\n\n".encode()
                    return
                parsed = _parse_stdout_line(line)
                if parsed:
                    yield f"event: progress\ndata: {json.dumps(parsed)}\n\n".encode()

            while not task.ready():
                message = pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=0.5
                )
                if message:
                    line = message["data"]
                    if line == "event: done\n":
                        break
                    parsed = _parse_stdout_line(line)
                    if parsed:
                        yield f"event: progress\ndata: {json.dumps(parsed)}\n\n".encode()
                else:
                    await asyncio.sleep(0.5)

        finally:
            pubsub.unsubscribe()
            pubsub.close()

        # Send final done message
        duration = int(
            time.time() - float(redis_client.get("pipeline_start_time") or time.time())
        )
        total = 0
        if ENRICHED_PATH.exists():
            try:
                data = json.loads(ENRICHED_PATH.read_text())
                total = len(data)
            except Exception:
                pass
        yield f"event: done\ndata: {json.dumps({'total': total, 'duration': duration})}\n\n".encode()

    from fastapi.responses import StreamingResponse

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ─── Dashboard UI ───────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return templates.TemplateResponse("index.html", {"request": {}})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
