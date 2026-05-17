// frontend/lib/api.ts
// Typed client for the FastAPI backend. All new frontend code should
// fetch through these helpers rather than calling Supabase directly,
// so the service-role / RLS boundary stays on the backend.
//
// Existing pages that still query Supabase via lib/supabase.ts:
//   - frontend/app/company/[id]/page.tsx
//   - frontend/app/vc/[slug]/page.tsx
//   - frontend/components/AdminSignalTable.tsx
// These need their own backend endpoints + refactor (tracked
// separately). Once they migrate, lib/supabase.ts can be deleted.

import { Company } from "@/lib/types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ─── Auth ────────────────────────────────────────────────────────────
// Backend verify_token currently accepts any Bearer token (see the
// WARNING docstring on app.py:verify_token). page.tsx is a read-only
// public dashboard and does not require Clerk sign-in, so it sends a
// static placeholder. The alerts settings page wires in the real
// Clerk getToken() because it writes per-tenant config. When real
// auth lands, both client and server should switch in the same PR.
const DASHBOARD_BEARER = "dashboard";

function authHeaders(token?: string): HeadersInit {
  return {
    Authorization: `Bearer ${token || DASHBOARD_BEARER}`,
    "Content-Type": "application/json",
  };
}

// ─── Companies ───────────────────────────────────────────────────────

export interface CompaniesListFilters {
  sector?: string;
  region?: string;
  fundingStage?: string;
  minScore?: number;
  search?: string;
}

export interface CompaniesListResponse {
  items: Company[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
  error?: string;
}

export interface CompaniesSummaryResponse {
  facets: {
    regions: Record<string, number>;
    sectors: Record<string, number>;
    funding_stages: Record<string, number>;
  };
  stats: {
    total: number;
    hot_count: number;
    avg_score: number;
    new_this_week: number;
  };
  error?: string;
}

/**
 * Fetch a paginated, filtered slice of the companies table for the
 * discovery feed. "All Regions" / "All Sectors" / "All Stages" are
 * treated as 'no filter' on the backend.
 */
export async function fetchCompaniesList(
  filters: CompaniesListFilters,
  page: number,
  pageSize: number,
  token?: string,
): Promise<CompaniesListResponse> {
  const params = new URLSearchParams();
  if (filters.sector && filters.sector !== "All Sectors") {
    params.set("sector", filters.sector);
  }
  if (filters.region && filters.region !== "All Regions") {
    params.set("region", filters.region);
  }
  if (filters.fundingStage && filters.fundingStage !== "All Stages") {
    params.set("funding_stage", filters.fundingStage);
  }
  if (filters.minScore && filters.minScore > 0) {
    params.set("min_score", String(filters.minScore));
  }
  if (filters.search && filters.search.trim()) {
    params.set("search", filters.search.trim());
  }
  params.set("page", String(page));
  params.set("page_size", String(pageSize));

  const res = await fetch(
    `${API_BASE}/api/companies/list?${params.toString()}`,
    { headers: authHeaders(token) },
  );
  if (!res.ok) {
    return {
      items: [],
      total: 0,
      page,
      page_size: pageSize,
      has_more: false,
      error: `HTTP ${res.status}`,
    };
  }
  return res.json();
}

/**
 * Fetch the global facets + header stats for the discovery feed.
 * No filters apply — values reflect the full tenant dataset.
 */
export async function fetchCompaniesSummary(
  token?: string,
): Promise<CompaniesSummaryResponse> {
  const res = await fetch(`${API_BASE}/api/companies/summary`, {
    headers: authHeaders(token),
  });
  if (!res.ok) {
    return {
      facets: { regions: {}, sectors: {}, funding_stages: {} },
      stats: { total: 0, hot_count: 0, avg_score: 0, new_this_week: 0 },
      error: `HTTP ${res.status}`,
    };
  }
  return res.json();
}

// ─── Tenant alerts ───────────────────────────────────────────────────

export interface TenantAlertsConfig {
  slack_webhook_url?: string | null;
  custom_webhook_url?: string | null;
}

export async function fetchTenantAlerts(
  token?: string,
): Promise<TenantAlertsConfig> {
  const res = await fetch(`${API_BASE}/api/tenant/alerts`, {
    headers: authHeaders(token),
  });
  if (!res.ok) return {};
  return res.json();
}

export async function updateTenantAlerts(
  config: TenantAlertsConfig,
  token?: string,
): Promise<{ ok: boolean }> {
  const res = await fetch(`${API_BASE}/api/tenant/alerts`, {
    method: "PUT",
    headers: authHeaders(token),
    body: JSON.stringify(config),
  });
  return { ok: res.ok };
}
