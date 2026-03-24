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
    """Add slug to failed_vcs. Removes from completed_vcs. Does NOT delete vc_patterns entry."""
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
    """Remove a VC from both completed and failed sets AND from vc_patterns. Allows full re-scrape."""
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
    for key in ("completed_vcs", "failed_vcs"):
        if slug in data.get(key, []):
            data[key].remove(slug)
    # Also clear the cached pattern (Task 6 addition)
    if slug in data.get("vc_patterns", {}):
        del data["vc_patterns"][slug]
    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    shutil.move(str(tmp), str(STATE_FILE))

def mark_completed(slug: str) -> None:
    """Add slug to completed_vcs atomically. Removes from failed_vcs on success."""
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