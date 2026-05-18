"use client";
import { useEffect, useState, useCallback, useMemo } from "react";
import { Company } from "@/lib/types";
import {
  fetchCompaniesList,
  fetchCompaniesSummary,
  CompaniesSummaryResponse,
} from "@/lib/api";
import { DealCard } from "@/components/DealCard";
import {
  FilterSidebar,
  Filters,
  REGIONS,
  SECTORS,
  FUNDING_STAGES,
} from "@/components/FilterSidebar";
import { StatsBar } from "@/components/StatsBar";

type ViewMode = "grid" | "list";
const PAGE_SIZE = 50;

const EMPTY_SUMMARY: CompaniesSummaryResponse = {
  facets: { regions: {}, sectors: {}, funding_stages: {} },
  stats: { total: 0, hot_count: 0, avg_score: 0, new_this_week: 0 },
};

// Normalize the LLM-emitted free-form sector strings into the small
// set of canonical buckets the sidebar exposes. Backend returns the
// raw sector field as-is (does not know about these buckets), so this
// mapping stays client-side. Same logic as the prior implementation —
// keeping it here means the backend can stay agnostic.
function normalizeSector(s: string | null | undefined): string {
  if (!s) return "Other";
  const lower = s.toLowerCase();
  if (
    lower.includes("ai") ||
    lower.includes("artificial intelligence") ||
    lower.includes("generative") ||
    lower.includes("llm") ||
    lower.includes("llmops") ||
    lower.includes("machine learning") ||
    lower.includes("machine intelligence")
  )
    return "AI";
  if (
    lower.includes("fintech") ||
    lower.includes("financial") ||
    lower.includes("banking") ||
    lower.includes("payment") ||
    lower.includes("insurtech") ||
    lower.includes("wealth") ||
    lower.includes("crypto") ||
    lower.includes("trading platform")
  )
    return "Fintech";
  if (
    lower.includes("health") ||
    lower.includes("medtech") ||
    lower.includes("medical") ||
    lower.includes("biotech") ||
    lower.includes("pharma") ||
    lower.includes("telemed") ||
    lower.includes("diagnostic")
  )
    return "Health";
  if (
    lower.includes("ecommerce") ||
    lower.includes("e-commerce") ||
    lower.includes("retail") ||
    lower.includes("shop") ||
    lower.includes("marketplace")
  )
    return "E-commerce";
  if (
    lower.includes("saas") ||
    lower.includes("software") ||
    lower.includes("cloud") ||
    lower.includes("paas") ||
    lower.includes("iaas") ||
    lower.includes("api") ||
    lower.includes("platform") ||
    lower.includes("tool") ||
    lower.includes("automation") ||
    lower.includes("productivity")
  )
    return "SaaS";
  if (
    lower.includes("energy") ||
    lower.includes("climate") ||
    lower.includes("carbon") ||
    lower.includes("renewable") ||
    lower.includes("solar") ||
    lower.includes("sustainab")
  )
    return "Climate Tech";
  if (
    lower.includes("robot") ||
    lower.includes("drone") ||
    lower.includes("autonom") ||
    lower.includes("industrial") ||
    lower.includes("manufactur")
  )
    return "Robotics";
  if (
    lower.includes("cyber") ||
    lower.includes("security") ||
    lower.includes("privacy") ||
    lower.includes("fraud")
  )
    return "Security";
  if (
    lower.includes("educat") ||
    lower.includes("edtech") ||
    lower.includes("learn") ||
    lower.includes("training")
  )
    return "EdTech";
  if (
    lower.includes("real estate") ||
    lower.includes("proptech") ||
    lower.includes("property")
  )
    return "PropTech";
  if (
    lower.includes("logistics") ||
    lower.includes("supply chain") ||
    lower.includes("delivery") ||
    lower.includes("shipping") ||
    lower.includes("transport")
  )
    return "Logistics";
  return "Other";
}

const DEFAULT_FILTERS: Filters = {
  region: "All Regions",
  sector: "All Sectors",
  fundingStage: "All Stages",
  minScore: 0,
  search: "",
};

// Combine filters + page into a single query state so React 19's
// set-state-in-effect rule doesn't flag a cascading setPage(0) on
// filter change. Updating filters atomically resets the page, which
// is also what the user expects (filter change shouldn't strand them
// on an out-of-range page).
interface QueryState {
  filters: Filters;
  page: number;
}

export default function DiscoveryDashboard() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [view, setView] = useState<ViewMode>("grid");
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState<CompaniesSummaryResponse>(EMPTY_SUMMARY);
  const [query, setQuery] = useState<QueryState>({
    filters: DEFAULT_FILTERS,
    page: 0,
  });
  const { filters, page } = query;

  // Summary (facets + header stats) — global, no filters, fetched once
  // per mount. Cheap on the backend (single tenant scan, aggregated
  // in Python). Re-fetch on demand could be added if data freshness
  // matters more than a stable sidebar.
  useEffect(() => {
    fetchCompaniesSummary().then(setSummary);
  }, []);

  // Main list fetch — re-runs on any filter or page change.
  // Standard fetch-driven-by-URL-state pattern: the setLoading +
  // .then(setData) is the canonical way to bind an async call to a
  // declarative dep array. The React 19 lint rule flags it but no
  // cleaner equivalent exists without pulling in SWR/React Query.
  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    fetchCompaniesList(query.filters, query.page, PAGE_SIZE).then((data) => {
      if (cancelled) return;
      if (data.error) {
        console.error("Failed to fetch companies:", data.error);
      }
      setCompanies(data.items);
      setTotalCount(data.total);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [query]);

  // Sidebar counts: derive sector buckets from raw sector facets using
  // normalizeSector; regions and funding_stages come through directly.
  const counts = useMemo(() => {
    const region: Record<string, number> = {};
    const sector: Record<string, number> = {};
    const stage: Record<string, number> = {};

    REGIONS.forEach((r) => {
      region[r] = summary.facets.regions[r] || 0;
    });
    SECTORS.forEach((s) => {
      sector[s] = 0;
    });
    FUNDING_STAGES.forEach((s) => {
      stage[s] = summary.facets.funding_stages[s] || 0;
    });
    for (const [raw, n] of Object.entries(summary.facets.sectors)) {
      const bucket = normalizeSector(raw);
      sector[bucket] = (sector[bucket] || 0) + n;
    }
    return { region, sector, stage };
  }, [summary]);

  // Stats now come straight from the backend.
  const stats = {
    total: summary.stats.total,
    hotCount: summary.stats.hot_count,
    avgScore: summary.stats.avg_score,
    newThisWeek: summary.stats.new_this_week,
  };

  const totalPages = Math.ceil(totalCount / PAGE_SIZE);

  // Filter change resets the page. Inline search updates also go
  // through this so a typing user doesn't get stranded on page 7.
  const handleFilterChange = useCallback((newFilters: Filters) => {
    setQuery({ filters: newFilters, page: 0 });
  }, []);

  const updateSearch = useCallback((search: string) => {
    setQuery((q) => ({ filters: { ...q.filters, search }, page: 0 }));
  }, []);

  const goToPage = useCallback((p: number) => {
    setQuery((q) => ({ ...q, page: p }));
  }, []);

  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <FilterSidebar filters={filters} onChange={handleFilterChange} counts={counts} />

      {/* Main content */}
      <main className="flex-1 min-w-0 border-l border-gray-200 dark:border-gray-800">
        <div className="max-w-6xl mx-auto p-6">
          {/* Header */}
          <div className="mb-6">
            <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100 mb-1">DealRadar</h1>
            <p className="text-gray-500 dark:text-gray-400">
              Discover high-signal deals before the market does.
            </p>
          </div>

          {/* Stats bar */}
          <StatsBar {...stats} />

          {/* Search + View Toggle */}
          <div className="flex gap-3 mb-6">
            {/* Keyword search */}
            <div className="relative flex-1">
              <svg
                className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <circle cx="11" cy="11" r="8" />
                <line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>
              <input
                type="text"
                placeholder="Search companies, domains, keywords..."
                value={filters.search}
                onChange={(e) => updateSearch(e.target.value)}
                className="w-full pl-10 pr-4 py-2.5 border border-gray-200 dark:border-gray-700 rounded-lg text-sm bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
              {filters.search && (
                <button
                  onClick={() => updateSearch("")}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                >
                  ✕
                </button>
              )}
            </div>

            {/* View toggle */}
            <div className="flex border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
              <button
                onClick={() => setView("grid")}
                className={`px-3 py-2 text-sm transition-colors ${
                  view === "grid"
                    ? "bg-blue-600 text-white"
                    : "bg-white dark:bg-gray-900 text-gray-500 hover:bg-gray-50 dark:hover:bg-gray-800"
                }`}
                title="Grid view"
              >
                <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" />
                  <rect x="3" y="14" width="7" height="7" /><rect x="14" y="14" width="7" height="7" />
                </svg>
              </button>
              <button
                onClick={() => setView("list")}
                className={`px-3 py-2 text-sm transition-colors ${
                  view === "list"
                    ? "bg-blue-600 text-white"
                    : "bg-white dark:bg-gray-900 text-gray-500 hover:bg-gray-50 dark:hover:bg-gray-800"
                }`}
                title="List view"
              >
                <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="8" y1="6" x2="21" y2="6" /><line x1="8" y1="12" x2="21" y2="12" />
                  <line x1="8" y1="18" x2="21" y2="18" /><line x1="3" y1="6" x2="3.01" y2="6" />
                  <line x1="3" y1="12" x2="3.01" y2="12" /><line x1="3" y1="18" x2="3.01" y2="18" />
                </svg>
              </button>
            </div>
          </div>

          {/* Active filter pills */}
          {(filters.region !== "All Regions" ||
            filters.sector !== "All Sectors" ||
            filters.fundingStage !== "All Stages" ||
            filters.minScore > 0 ||
            filters.search) && (
            <div className="flex flex-wrap gap-2 mb-4">
              {filters.region !== "All Regions" && (
                <span className="inline-flex items-center gap-1 text-xs bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200 px-2 py-1 rounded-full">
                  🌐 {filters.region}
                </span>
              )}
              {filters.sector !== "All Sectors" && (
                <span className="inline-flex items-center gap-1 text-xs bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200 px-2 py-1 rounded-full">
                  🏷️ {filters.sector}
                </span>
              )}
              {filters.fundingStage !== "All Stages" && (
                <span className="inline-flex items-center gap-1 text-xs bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200 px-2 py-1 rounded-full">
                  📊 {filters.fundingStage}
                </span>
              )}
              {filters.minScore > 0 && (
                <span className="inline-flex items-center gap-1 text-xs bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200 px-2 py-1 rounded-full">
                  ⭐ Score ≥ {filters.minScore}
                </span>
              )}
              {filters.search && (
                <span className="inline-flex items-center gap-1 text-xs bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200 px-2 py-1 rounded-full">
                  🔍 &quot;{filters.search}&quot;
                </span>
              )}
            </div>
          )}

          {/* Results count */}
          {!loading && (
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
              {totalCount === 0
                ? "No deals match your filters."
                : `Showing ${companies.length} of ${totalCount} deals`}
            </p>
          )}

          {/* Loading */}
          {loading && (
            <div className="flex items-center justify-center py-20">
              <div className="flex flex-col items-center gap-3">
                <div className="w-8 h-8 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
                <p className="text-gray-500 dark:text-gray-400 text-sm">Loading deals...</p>
              </div>
            </div>
          )}

          {/* Empty state */}
          {!loading && companies.length === 0 && (
            <div className="text-center py-20">
              <div className="text-5xl mb-4">🔍</div>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">No deals found</h3>
              <p className="text-gray-500 dark:text-gray-400 mb-4">
                Try adjusting your filters to see more results.
              </p>
              <button
                onClick={() => handleFilterChange(DEFAULT_FILTERS)}
                className="text-sm text-blue-600 hover:underline dark:text-blue-400"
              >
                Clear all filters
              </button>
            </div>
          )}

          {/* Grid view */}
          {!loading && companies.length > 0 && view === "grid" && (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 mb-8">
              {companies.map((company) => (
                <DealCard key={company.id} company={company} view="grid" />
              ))}
            </div>
          )}

          {/* List view */}
          {!loading && companies.length > 0 && view === "list" && (
            <div className="space-y-2 mb-8">
              {companies.map((company) => (
                <DealCard key={company.id} company={company} view="list" />
              ))}
            </div>
          )}

          {/* Pagination */}
          {!loading && totalPages > 1 && (
            <div className="flex justify-between items-center pt-4 border-t border-gray-200 dark:border-gray-800">
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Page {page + 1} of {totalPages}
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => goToPage(Math.max(0, page - 1))}
                  disabled={page === 0}
                  className="px-3 py-1.5 border border-gray-200 dark:border-gray-700 rounded text-sm disabled:opacity-40 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
                >
                  ← Prev
                </button>
                {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                  let pageNum = i;
                  if (totalPages > 5) {
                    if (page < 3) pageNum = i;
                    else if (page > totalPages - 4) pageNum = totalPages - 5 + i;
                    else pageNum = page - 2 + i;
                  }
                  return (
                    <button
                      key={pageNum}
                      onClick={() => goToPage(pageNum)}
                      className={`px-3 py-1.5 rounded text-sm transition-colors ${
                        page === pageNum
                          ? "bg-blue-600 text-white"
                          : "border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800"
                      }`}
                    >
                      {pageNum + 1}
                    </button>
                  );
                })}
                <button
                  onClick={() => goToPage(Math.min(totalPages - 1, page + 1))}
                  disabled={page >= totalPages - 1}
                  className="px-3 py-1.5 border border-gray-200 dark:border-gray-700 rounded text-sm disabled:opacity-40 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
                >
                  Next →
                </button>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
