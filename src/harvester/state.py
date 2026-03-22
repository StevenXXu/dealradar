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
    except (json.JSONDecodeError, OSError):
        return set()

def mark_completed(slug: str) -> None:
    """Add slug to completed_vcs atomically."""
    data = {"completed_vcs": [], "last_updated": ""}
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            pass
    if slug not in data.get("completed_vcs", []):
        data.setdefault("completed_vcs", []).append(slug)
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