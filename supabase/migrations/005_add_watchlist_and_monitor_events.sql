-- 005_add_watchlist_and_monitor_events.sql
--
-- Port of dealflow monitor.py's watchlist + audit-event concepts.
--
-- Two ideas:
--   1. A per-company manual watchlist with a monitor_state label
--      ('pursue' = act now, 'monitor' = passive observation).
--      Mirrors dealflow's WATCHLIST_RULES but persisted to Postgres
--      instead of a hardcoded dict so the user can edit live.
--   2. An append-only audit log of monitor_events. Each event has a
--      deterministic event_id (uuid5 of trigger context) so repeated
--      ingestion of the same payload is idempotent — duplicate
--      inserts hit the UNIQUE constraint and no-op rather than
--      creating phantom history.
--
-- The verified_metrics JSONB column on companies is the source of
-- truth for "ground-truth signals we've personally confirmed about
-- this company" (vs. signal_score which is rule-derived and
-- investment_score which is LLM-derived). When verified_metrics
-- changes on a watchlisted company, a monitor_event fires.


-- ─── companies: watchlist columns + verified_metrics ────────────────

ALTER TABLE companies
    ADD COLUMN IF NOT EXISTS watchlisted BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE companies
    ADD COLUMN IF NOT EXISTS monitor_state TEXT
    CHECK (monitor_state IS NULL OR monitor_state IN ('pursue', 'monitor'));

ALTER TABLE companies
    ADD COLUMN IF NOT EXISTS watchlist_notes TEXT;

ALTER TABLE companies
    ADD COLUMN IF NOT EXISTS verified_metrics JSONB NOT NULL DEFAULT '{}'::jsonb;

-- Partial index — only watchlisted rows. The dashboard's watchlist
-- view scans by this filter and the cardinality is small (dozens,
-- not thousands), so a partial index keeps the index narrow.
CREATE INDEX IF NOT EXISTS idx_companies_watchlisted
    ON companies(tenant_id, monitor_state)
    WHERE watchlisted = true;


-- ─── monitor_events: append-only audit log ──────────────────────────

CREATE TABLE IF NOT EXISTS monitor_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Deterministic id derived from (company_id, canonical metric diff).
    -- UNIQUE so re-ingesting the same payload is a no-op.
    event_id UUID NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    trigger_reason TEXT,
    triggered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    evidence_source TEXT,
    metric_keys TEXT[],
    new_verified_metrics JSONB,
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_monitor_events_company
    ON monitor_events(company_id, triggered_at DESC);

CREATE INDEX IF NOT EXISTS idx_monitor_events_tenant_time
    ON monitor_events(tenant_id, triggered_at DESC);

-- RLS — match the single-tenant pattern: rely on service-role writes
-- from the backend, no per-row policy. When multi-tenant lands, add
-- a tenant_id IN (...) policy here.
ALTER TABLE monitor_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "allow_all_monitor_events" ON monitor_events FOR ALL USING (true);
