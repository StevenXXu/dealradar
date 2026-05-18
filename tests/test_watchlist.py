"""Tests for src/commander/watchlist.py.

Covers metric-diff math, deterministic event ID derivation,
watchlist CRUD, and the verified-metrics ingestion gate.
SupabaseClient is mocked throughout — no network calls.
"""
import json
from unittest.mock import MagicMock

import pytest

from src.commander.watchlist import (
    EVENT_TYPE_REREVIEW,
    TRIGGER_REASON_NEW_METRICS,
    VALID_MONITOR_STATES,
    WatchlistService,
    WatchlistState,
    _extract_new_or_changed,
    _make_event_id,
    _normalize_metrics,
)


# ─── _normalize_metrics ──────────────────────────────────────────────


class TestNormalizeMetrics:
    def test_dict_passes_through(self):
        assert _normalize_metrics({"a": 1}) == {"a": 1}

    def test_none_returns_empty(self):
        assert _normalize_metrics(None) == {}

    def test_json_string_is_parsed(self):
        assert _normalize_metrics('{"a": 1}') == {"a": 1}

    def test_non_dict_json_returns_empty(self):
        assert _normalize_metrics('[1, 2, 3]') == {}
        assert _normalize_metrics('"just a string"') == {}

    def test_garbage_string_returns_empty(self):
        assert _normalize_metrics("not json") == {}

    def test_unexpected_type_returns_empty(self):
        assert _normalize_metrics(42) == {}


# ─── _extract_new_or_changed ─────────────────────────────────────────


class TestExtractNewOrChanged:
    def test_empty_inputs(self):
        assert _extract_new_or_changed({}, {}) == {}

    def test_all_new_keys(self):
        out = _extract_new_or_changed({}, {"a": 1, "b": 2})
        assert out == {"a": 1, "b": 2}

    def test_unchanged_keys_excluded(self):
        out = _extract_new_or_changed({"a": 1, "b": 2}, {"a": 1, "b": 2})
        assert out == {}

    def test_changed_value_included(self):
        out = _extract_new_or_changed({"a": 1}, {"a": 2})
        assert out == {"a": 2}

    def test_partial_diff(self):
        # b changes, c is new, a unchanged
        out = _extract_new_or_changed({"a": 1, "b": 2}, {"a": 1, "b": 3, "c": 4})
        assert out == {"b": 3, "c": 4}

    def test_key_removal_not_reported(self):
        # Existing key dropped in incoming → not flagged
        # (dealflow behavior; treat absent as 'no opinion')
        out = _extract_new_or_changed({"a": 1, "b": 2}, {"a": 1})
        assert out == {}


# ─── _make_event_id ──────────────────────────────────────────────────


class TestMakeEventId:
    def test_deterministic_same_inputs(self):
        a = _make_event_id("c1", {"headcount": 50, "arr": 1_000_000})
        b = _make_event_id("c1", {"headcount": 50, "arr": 1_000_000})
        assert a == b

    def test_key_order_independent(self):
        a = _make_event_id("c1", {"headcount": 50, "arr": 1_000_000})
        b = _make_event_id("c1", {"arr": 1_000_000, "headcount": 50})
        assert a == b

    def test_different_company_id_different_event(self):
        a = _make_event_id("c1", {"headcount": 50})
        b = _make_event_id("c2", {"headcount": 50})
        assert a != b

    def test_different_diff_different_event(self):
        a = _make_event_id("c1", {"headcount": 50})
        b = _make_event_id("c1", {"headcount": 60})
        assert a != b

    def test_returns_valid_uuid_string(self):
        import uuid as uuid_mod

        eid = _make_event_id("c1", {"a": 1})
        # Round-trips through UUID parse without error
        parsed = uuid_mod.UUID(eid)
        assert parsed.version == 5


# ─── WatchlistService.get_watchlist ─────────────────────────────────


def _client_with_company(row):
    """Build a SupabaseClient stub where get_company_by_id returns the
    given row (or {} for any other call)."""
    c = MagicMock()
    c.get_company_by_id.return_value = row
    return c


class TestGetWatchlist:
    def test_returns_none_when_company_missing(self):
        svc = WatchlistService(client=_client_with_company({}))
        assert svc.get_watchlist("missing-id") is None

    def test_returns_state_with_defaults(self):
        svc = WatchlistService(client=_client_with_company({
            "id": "c1",
            "watchlisted": False,
            "monitor_state": None,
            "watchlist_notes": None,
            "verified_metrics": {},
        }))
        state = svc.get_watchlist("c1")
        assert isinstance(state, WatchlistState)
        assert state.company_id == "c1"
        assert state.watchlisted is False
        assert state.monitor_state is None
        assert state.verified_metrics == {}

    def test_returns_state_when_watchlisted(self):
        svc = WatchlistService(client=_client_with_company({
            "id": "c1",
            "watchlisted": True,
            "monitor_state": "pursue",
            "watchlist_notes": "high prio",
            "verified_metrics": {"headcount": 50},
        }))
        state = svc.get_watchlist("c1")
        assert state.watchlisted is True
        assert state.monitor_state == "pursue"
        assert state.watchlist_notes == "high prio"
        assert state.verified_metrics == {"headcount": 50}

    def test_normalizes_json_string_metrics(self):
        # Supabase JSONB columns can round-trip as JSON strings under
        # some client paths. Service must coerce back to dict.
        svc = WatchlistService(client=_client_with_company({
            "id": "c1",
            "watchlisted": False,
            "verified_metrics": '{"headcount": 50}',
        }))
        state = svc.get_watchlist("c1")
        assert state.verified_metrics == {"headcount": 50}


# ─── WatchlistService.set_watchlist ─────────────────────────────────


class TestSetWatchlist:
    def test_invalid_monitor_state_raises(self):
        svc = WatchlistService(client=MagicMock())
        with pytest.raises(ValueError):
            svc.set_watchlist("c1", watchlisted=True, monitor_state="invalid")

    def test_valid_monitor_states_accepted(self):
        for state in VALID_MONITOR_STATES:
            client = MagicMock()
            client.update_company.return_value = {"id": "c1"}
            client.get_company_by_id.return_value = {
                "id": "c1", "watchlisted": True, "monitor_state": state,
                "watchlist_notes": None, "verified_metrics": {},
            }
            svc = WatchlistService(client=client)
            result = svc.set_watchlist("c1", watchlisted=True, monitor_state=state)
            assert result.monitor_state == state

    def test_setting_watchlisted_persists_state_and_notes(self):
        client = MagicMock()
        client.update_company.return_value = {"id": "c1"}
        client.get_company_by_id.return_value = {
            "id": "c1", "watchlisted": True, "monitor_state": "pursue",
            "watchlist_notes": "high prio", "verified_metrics": {},
        }
        svc = WatchlistService(client=client)
        svc.set_watchlist("c1", watchlisted=True, monitor_state="pursue", notes="high prio")
        fields = client.update_company.call_args[0][1]
        assert fields["watchlisted"] is True
        assert fields["monitor_state"] == "pursue"
        assert fields["watchlist_notes"] == "high prio"

    def test_unsetting_clears_state_and_notes_regardless_of_args(self):
        client = MagicMock()
        client.update_company.return_value = {"id": "c1"}
        client.get_company_by_id.return_value = {
            "id": "c1", "watchlisted": False, "monitor_state": None,
            "watchlist_notes": None, "verified_metrics": {},
        }
        svc = WatchlistService(client=client)
        # User incorrectly passes a state when unsetting — must be ignored
        svc.set_watchlist("c1", watchlisted=False, monitor_state="pursue", notes="x")
        fields = client.update_company.call_args[0][1]
        assert fields["watchlisted"] is False
        assert fields["monitor_state"] is None
        assert fields["watchlist_notes"] is None


# ─── WatchlistService.ingest_verified_metrics ────────────────────────


def _make_svc_with_company(company_row):
    """Build a service whose underlying client returns company_row
    from get_company_by_id and a successful insert from
    insert_monitor_event."""
    client = MagicMock()
    client.get_company_by_id.return_value = company_row
    client.update_company.return_value = {"id": company_row.get("id", "c1")}
    client.insert_monitor_event.return_value = {"id": "evt-1"}
    return WatchlistService(client=client), client


class TestIngestVerifiedMetrics:
    BASE_ROW = {
        "id": "c1",
        "watchlisted": False,
        "monitor_state": None,
        "watchlist_notes": None,
        "verified_metrics": {},
        "tenant_id": "t1",
    }

    def test_rejects_non_dict_payload(self):
        svc, _ = _make_svc_with_company(self.BASE_ROW)
        result = svc.ingest_verified_metrics("c1", "not a dict")  # type: ignore
        assert result["status"] == "rejected"
        assert result["triggered"] is False

    def test_rejects_unknown_company(self):
        svc, _ = _make_svc_with_company({})
        result = svc.ingest_verified_metrics("missing-id", {"a": 1})
        assert result["status"] == "rejected"

    def test_non_watchlisted_no_event_but_metrics_merged(self):
        svc, client = _make_svc_with_company(self.BASE_ROW)
        result = svc.ingest_verified_metrics("c1", {"headcount": 50})
        assert result["triggered"] is False
        assert result["audit_event"] is None
        # update_company called to merge verified_metrics
        update_call = client.update_company.call_args[0][1]
        assert update_call["verified_metrics"] == {"headcount": 50}
        # No event insert
        client.insert_monitor_event.assert_not_called()

    def test_watchlisted_with_new_metrics_emits_event(self):
        row = dict(self.BASE_ROW, watchlisted=True, monitor_state="pursue")
        svc, client = _make_svc_with_company(row)
        result = svc.ingest_verified_metrics(
            "c1", {"headcount": 50, "arr": 1_000_000}
        )
        assert result["triggered"] is True
        assert result["audit_event"]["event_type"] == EVENT_TYPE_REREVIEW
        assert result["audit_event"]["trigger_reason"] == TRIGGER_REASON_NEW_METRICS
        assert sorted(result["audit_event"]["metric_keys"]) == ["arr", "headcount"]
        assert result["audit_event"]["tenant_id"] == "t1"
        client.insert_monitor_event.assert_called_once()

    def test_watchlisted_same_metrics_no_event(self):
        # verified_metrics already has the same values → no diff → no event
        row = dict(
            self.BASE_ROW,
            watchlisted=True,
            verified_metrics={"headcount": 50},
        )
        svc, client = _make_svc_with_company(row)
        result = svc.ingest_verified_metrics("c1", {"headcount": 50})
        assert result["triggered"] is False
        client.insert_monitor_event.assert_not_called()

    def test_watchlisted_partial_diff_only_changed_keys_in_event(self):
        row = dict(
            self.BASE_ROW,
            watchlisted=True,
            verified_metrics={"headcount": 50, "arr": 1_000_000},
        )
        svc, client = _make_svc_with_company(row)
        # arr unchanged, headcount changed, sector new
        result = svc.ingest_verified_metrics(
            "c1",
            {"headcount": 60, "arr": 1_000_000, "sector": "AI"},
        )
        assert result["triggered"] is True
        assert sorted(result["new_verified_metric_keys"]) == ["headcount", "sector"]

    def test_empty_payload_no_event(self):
        row = dict(self.BASE_ROW, watchlisted=True)
        svc, client = _make_svc_with_company(row)
        result = svc.ingest_verified_metrics("c1", {})
        assert result["triggered"] is False
        client.insert_monitor_event.assert_not_called()

    def test_duplicate_event_still_reports_triggered(self):
        """If the same diff is ingested twice, the DB UNIQUE
        constraint makes the second insert a no-op (returns
        duplicate=True). The service should still report triggered=True
        because the event exists — the caller asked the right
        question, just twice."""
        row = dict(self.BASE_ROW, watchlisted=True)
        client = MagicMock()
        client.get_company_by_id.return_value = row
        client.update_company.return_value = {}
        client.insert_monitor_event.return_value = {
            "event_id": "deterministic-uuid",
            "duplicate": True,
        }
        svc = WatchlistService(client=client)
        result = svc.ingest_verified_metrics("c1", {"headcount": 50})
        assert result["triggered"] is True
        assert result["duplicate"] is True

    def test_event_id_deterministic_across_runs(self):
        """A second ingest with the same diff produces the same
        event_id — proves the uuid5 derivation is stable."""
        row = dict(self.BASE_ROW, watchlisted=True)
        svc1, client1 = _make_svc_with_company(row)
        svc2, client2 = _make_svc_with_company(row)
        r1 = svc1.ingest_verified_metrics("c1", {"headcount": 50})
        r2 = svc2.ingest_verified_metrics("c1", {"headcount": 50})
        assert r1["audit_event"]["event_id"] == r2["audit_event"]["event_id"]


# ─── WatchlistService.recent_events ─────────────────────────────────


def test_recent_events_passes_through_filters():
    client = MagicMock()
    client.list_monitor_events.return_value = [{"event_id": "e1"}]
    svc = WatchlistService(client=client)
    out = svc.recent_events(limit=10, company_id="c1", tenant_id="t1")
    client.list_monitor_events.assert_called_once_with(
        company_id="c1", tenant_id="t1", limit=10
    )
    assert len(out) == 1
