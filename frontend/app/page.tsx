"use client";
import { useEffect, useState, useCallback, useMemo } from "react";
import { supabase } from "@/lib/supabase";
import { Company } from "@/lib/types";
import { DealCard } from "@/components/DealCard";
import { FilterSidebar, Filters, REGIONS, SECTORS, FUNDING_STAGES } from "@/components/FilterSidebar";
import { StatsBar } from "@/components/StatsBar";

type ViewMode = "grid" | "list";
const PAGE_SIZE = 50;

export default function DiscoveryDashboard() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [view, setView] = useState<ViewMode>("grid");
  const [page, setPage] = useState(0);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [schemaHasRegion, setSchemaHasRegion] = useState(false);

  const [filters, setFilters] = useState<Filters>({
    region: "All Regions",
    sector: "All Sectors",
    fundingStage: "All Stages",
    minScore: 0,
    search: "",
  });

  // Build filter counts from full dataset (for filter sidebar)
  const [allCompanies, setAllCompanies] = useState<Company[]>([]);

  // Detect if region/funding_stage columns exist
  useEffect(() => {
    supabase
      .from("companies")
      .select("region, sector, funding_stage, signal_score", { count: "exact", head: true })
      .then(({ error }) => {
        if (!error) {
          setSchemaHasRegion(true);
        }
      });
  }, []);

  // Fetch all companies for filter counts (safe, won't fail if columns missing)
  useEffect(() => {
    const fields = schemaHasRegion
      ? "region, sector, funding_stage, signal_score"
      : "sector, signal_score";
    supabase
      .from("companies")
      .select(fields, { count: "exact" })
      .then(({ data, error }) => {
        if (!error && data) {
          setAllCompanies((data as unknown) as Company[]);
        }
      });
  }, [schemaHasRegion]);

  // Main companies query
  useEffect(() => {
    setLoading(true);
    setPage(0);

    const from = 0;
    let query = supabase
      .from("companies")
      .select("*", { count: "exact" })
      .order("signal_score", { ascending: false })
      .range(from, from + PAGE_SIZE - 1);

    if (filters.sector !== "All Sectors") {
      query = query.eq("sector", filters.sector);
    }
    if (filters.minScore > 0) {
      query = query.gte("signal_score", filters.minScore);
    }
    if (filters.region !== "All Regions" && schemaHasRegion) {
      query = query.eq("region", filters.region);
    }
    if (filters.fundingStage !== "All Stages" && schemaHasRegion) {
      query = query.eq("funding_stage", filters.fundingStage);
    }
    if (filters.search.trim()) {
      const search = filters.search.trim();
      query = query.or(
        `company_name.ilike.%${search}%,domain.ilike.%${search}%,one_liner.ilike.%${search}%`
      );
    }

    query.then(({ data, count, error }) => {
      if (error) {
        console.error("Failed to fetch companies:", error);
        setCompanies([]);
        setTotalCount(0);
      } else {
        setCompanies((data || []) as Company[]);
        setTotalCount(count || 0);
      }
      setLoading(false);
    });
  }, [filters.region, filters.sector, filters.fundingStage, filters.minScore, filters.search, schemaHasRegion]);

  // Compute filter counts from allCompanies
  const counts = useMemo(() => {
    const region: Record<string, number> = {};
    const sector: Record<string, number> = {};
    const stage: Record<string, number> = {};

    REGIONS.forEach((r) => { region[r] = 0; });
    SECTORS.forEach((s) => { sector[s] = 0; });
    FUNDING_STAGES.forEach((s) => { stage[s] = 0; });

    allCompanies.forEach((c) => {
      if (c.sector) sector[c.sector] = (sector[c.sector] || 0) + 1;
      if (c.region) region[c.region] = (region[c.region] || 0) + 1;
      if ((c as Company & { funding_stage?: string }).funding_stage) {
        const s = (c as Company & { funding_stage: string }).funding_stage;
        stage[s] = (stage[s] || 0) + 1;
      }
    });
    return { region, sector, stage };
  }, [allCompanies]);

  // Compute stats
  const stats = useMemo(() => {
    const total = allCompanies.length;
    const hotCount = allCompanies.filter((c) => c.signal_score >= 30).length;
    const avgScore = total > 0
      ? allCompanies.reduce((sum, c) => sum + c.signal_score, 0) / total
      : 0;
    const oneWeekAgo = new Date();
    oneWeekAgo.setDate(oneWeekAgo.getDate() - 7);
    const newThisWeek = allCompanies.filter((c) => new Date(c.created_at) >= oneWeekAgo).length;
    return { total, hotCount, avgScore, newThisWeek };
  }, [allCompanies]);

  const totalPages = Math.ceil(totalCount / PAGE_SIZE);

  const handleFilterChange = useCallback((newFilters: Filters) => {
    setFilters(newFilters);
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
                onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))}
                className="w-full pl-10 pr-4 py-2.5 border border-gray-200 dark:border-gray-700 rounded-lg text-sm bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
              {filters.search && (
                <button
                  onClick={() => setFilters((f) => ({ ...f, search: "" }))}
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
              {filters.fundingStage !== "All Stages" && schemaHasRegion && (
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
                onClick={() =>
                  setFilters({ region: "All Regions", sector: "All Sectors", fundingStage: "All Stages", minScore: 0, search: "" })
                }
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
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
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
                      onClick={() => setPage(pageNum)}
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
                  onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
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
