"""Watchlist + monitor-event service.

Ports the behavior of dealflow's monitor.py:
  - WATCHLIST_RULES (hardcoded dict)         → companies.watchlisted/
                                                companies.monitor_state
  - MONITORED_DEAL_REREVIEW_EVENTS (in-mem)  → monitor_events table
  - _append_monitored_deal_rereview_event    → ingest_verified_metrics

The dealflow version stored everything in process-local globals and
lost it on every restart. This version reads/writes Postgres so the
audit trail survives, the watchlist is editable live, and the data
is consistent across multiple worker processes.

Event identity is deterministic — same (company_id, canonical metric
diff) → same event_id (uuid5 of those bytes). The DB has a UNIQUE
constraint on event_id, so duplicate ingests are no-ops rather than
producing phantom rows. The dealflow version recomputed the uuid5
but had no DB-level guard, so concurrent ingests could race and
double-insert.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Optional

from src.supabase.client import SupabaseClient


# Valid values for the monitor_state column. Matches the
# CHECK constraint in migration 005.
VALID_MONITOR_STATES: frozenset[str] = frozenset({"pursue", "monitor"})

EVENT_TYPE_REREVIEW = "monitored_deal_rereview_triggered"
TRIGGER_REASON_NEW_METRICS = "new_verified_metrics"


@dataclass
class WatchlistState:
    """Read-only snapshot of a company's watchlist columns."""

    company_id: str
    watchlisted: bool
    monitor_state: Optional[str]
    watchlist_notes: Optional[str]
    verified_metrics: dict


def _normalize_metrics(value) -> dict:
    """Defensive coercion — DB JSONB sometimes round-trips as a
    string under certain Supabase client paths. Always return a
    dict so downstream diffing has consistent input."""
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}


def _extract_new_or_changed(existing: dict, incoming: dict) -> dict:
    """Return only the (key, value) pairs in `incoming` whose value
    differs from `existing`. Equivalent to dealflow's
    _extract_new_verified_metrics. Order-stable: iteration follows
    sorted-key order so the resulting JSON canonicalizes
    deterministically for event_id derivation."""
    new_or_changed: dict = {}
    for key in sorted(incoming.keys()):
        if existing.get(key) != incoming.get(key):
            new_or_changed[key] = incoming.get(key)
    return new_or_changed


def _make_event_id(company_id: str, metric_diff: dict) -> str:
    """Deterministic uuid5 derived from (company_id, canonical diff).
    Sorted keys + minimal separators in the JSON ensure the same
    logical diff always produces the same UUID across runs / clients."""
    canonical = json.dumps(metric_diff, sort_keys=True, separators=(",", ":"))
    key = f"{company_id}|{canonical}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))


class WatchlistService:
    """Business logic over the watchlist + monitor_events tables.

    Holds a SupabaseClient (default lazy-instantiated). All writes
    use service-role + RLS bypass, so the service is intended for
    backend use; do not expose it to a browser-side caller.
    """

    def __init__(self, client: SupabaseClient | None = None):
        self._client = client or SupabaseClient()

    # ─── Watchlist CRUD ─────────────────────────────────────────────

    def get_watchlist(self, company_id: str) -> Optional[WatchlistState]:
        row = self._client.get_company_by_id(company_id)
        if not row:
            return None
        return WatchlistState(
            company_id=row["id"],
            watchlisted=bool(row.get("watchlisted", False)),
            monitor_state=row.get("monitor_state"),
            watchlist_notes=row.get("watchlist_notes"),
            verified_metrics=_normalize_metrics(row.get("verified_metrics")),
        )

    def set_watchlist(
        self,
        company_id: str,
        watchlisted: bool,
        monitor_state: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Optional[WatchlistState]:
        """Set or clear watchlist state for one company.

        When watchlisted=False, monitor_state and notes are cleared
        regardless of arguments — there's no meaningful 'monitor_state
        for a non-watchlisted company' value.
        """
        if monitor_state is not None and monitor_state not in VALID_MONITOR_STATES:
            raise ValueError(
                f"monitor_state must be one of {sorted(VALID_MONITOR_STATES)}, "
                f"got {monitor_state!r}"
            )

        if watchlisted:
            fields = {
                "watchlisted": True,
                "monitor_state": monitor_state,
                "watchlist_notes": notes,
            }
        else:
            fields = {
                "watchlisted": False,
                "monitor_state": None,
                "watchlist_notes": None,
            }

        updated = self._client.update_company(company_id, fields)
        if not updated:
            return None
        return self.get_watchlist(company_id)

    # ─── Verified-metrics ingestion ────────────────────────────────

    def ingest_verified_metrics(
        self,
        company_id: str,
        incoming_metrics: dict,
        evidence_source: str = "sol-38-monitoring-pipeline",
    ) -> dict:
        """Merge incoming verified_metrics into the company row and,
        if the company is watchlisted AND there's a non-empty diff,
        emit a monitor_event.

        Returns a result dict:
            {
                "status": "processed",
                "company_id": str,
                "triggered": bool,
                "new_verified_metric_keys": list[str],
                "audit_event": event_dict | None,
            }

        Idempotent at the event layer: re-posting the same incoming
        metrics yields triggered=False (no diff, no new event).
        Re-posting a partial overlap yields only the changed keys
        as triggers — never the full payload.
        """
        if not isinstance(incoming_metrics, dict):
            return {
                "status": "rejected",
                "reason": "incoming_metrics must be a dict",
                "company_id": company_id,
                "triggered": False,
            }

        state = self.get_watchlist(company_id)
        if state is None:
            return {
                "status": "rejected",
                "reason": "company not found",
                "company_id": company_id,
                "triggered": False,
            }

        new_or_changed = _extract_new_or_changed(state.verified_metrics, incoming_metrics)

        # Merge into the persistent record regardless of watchlist
        # status — verified_metrics is independently useful as
        # context even for non-watchlisted companies. The event is
        # the watchlist-gated part.
        if incoming_metrics:
            merged = dict(state.verified_metrics)
            merged.update(incoming_metrics)
            self._client.update_company(company_id, {"verified_metrics": merged})

        # Watchlist gate: no event for non-watchlisted companies or
        # for diff-empty re-posts.
        if not state.watchlisted or not new_or_changed:
            return {
                "status": "processed",
                "company_id": company_id,
                "triggered": False,
                "new_verified_metric_keys": sorted(new_or_changed.keys()),
                "audit_event": None,
            }

        event_id = _make_event_id(company_id, new_or_changed)
        # tenant_id comes from the company row; we re-read here to
        # avoid making get_watchlist return it (keeps WatchlistState
        # focused on user-facing fields).
        full_row = self._client.get_company_by_id(company_id)
        tenant_id = full_row.get("tenant_id") if full_row else None

        event_payload = {
            "event_id": event_id,
            "event_type": EVENT_TYPE_REREVIEW,
            "trigger_reason": TRIGGER_REASON_NEW_METRICS,
            "company_id": company_id,
            "evidence_source": evidence_source,
            "metric_keys": sorted(new_or_changed.keys()),
            "new_verified_metrics": new_or_changed,
            "tenant_id": tenant_id,
        }
        inserted = self._client.insert_monitor_event(event_payload)
        # If the insert was a UNIQUE-violation no-op (duplicate event),
        # we still report triggered=True because the event existed —
        # the caller asked the right question, just twice.
        return {
            "status": "processed",
            "company_id": company_id,
            "triggered": True,
            "new_verified_metric_keys": sorted(new_or_changed.keys()),
            "audit_event": event_payload,
            "duplicate": bool(inserted.get("duplicate", False)),
        }

    # ─── Event review ──────────────────────────────────────────────

    def recent_events(
        self,
        limit: int = 50,
        company_id: str | None = None,
        tenant_id: str | None = None,
    ) -> list[dict]:
        return self._client.list_monitor_events(
            company_id=company_id, tenant_id=tenant_id, limit=limit
        )
