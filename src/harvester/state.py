# src/harvester/state.py
"""Harvest checkpoint state management."""
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

STATE_FILE = Path("data/harvest_state.json")

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


def mark_failed(slug: str) -> None:
    """Add slug to failed_vcs (soft failure — will retry on next run unless force-restart)."""
    data = {"completed_vcs": [], "failed_vcs": [], "last_updated": ""}
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            pass
    if slug not in data.get("failed_vcs", []):
        data.setdefault("failed_vcs", []).append(slug)
    # Remove from completed if it was there (re-coverify after a failure)
    if slug in data.get("completed_vcs", []):
        data["completed_vcs"].remove(slug)
    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    shutil.move(str(tmp), str(STATE_FILE))


def clear_vc(slug: str) -> None:
    """Remove a VC from both completed and failed sets (allows re-scrape)."""
    data = {"completed_vcs": [], "failed_vcs": [], "last_updated": ""}
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            pass
    for key in ("completed_vcs", "failed_vcs"):
        if slug in data.get(key, []):
            data[key].remove(slug)
    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    shutil.move(str(tmp), str(STATE_FILE))

def mark_completed(slug: str) -> None:
    """Add slug to completed_vcs atomically. Removes from failed_vcs on success."""
    data = {"completed_vcs": [], "failed_vcs": [], "last_updated": ""}
    if STATE_FILE.exists():
        try:
            existing = json.loads(STATE_FILE.read_text())
            data["completed_vcs"] = existing.get("completed_vcs", [])
            data["failed_vcs"] = existing.get("failed_vcs", [])
            data["last_updated"] = existing.get("last_updated", "")
        except json.JSONDecodeError:
            pass
    if slug not in data["completed_vcs"]:
        data["completed_vcs"].append(slug)
    # On success, remove from failed if it was there
    if slug in data["failed_vcs"]:
        data["failed_vcs"].remove(slug)
    data["last_updated"] = datetime.now(timezone.utc).isoformat()
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
        except json.JSONDecodeError:
            existing = []
    seen_domains = {c["domain"] for c in existing if c.get("domain")}
    for c in new_companies:
        if not c.get("domain"):
            continue
        if c["domain"] not in seen_domains:
            seen_domains.add(c["domain"])
            existing.append(c)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(existing, indent=2))
    shutil.move(str(tmp), str(p))