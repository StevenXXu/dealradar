"use client";

import { useCallback } from "react";

export interface Filters {
  region: string;
  sector: string;
  fundingStage: string;
  minScore: number;
  search: string;
}

export const REGIONS = [
  "All Regions",
  "Australia & New Zealand",
  "North America",
  "Europe",
  "Asia Pacific",
  "Latin America",
  "Middle East & Africa",
  "Global",
] as const;

export const SECTORS = [
  "All Sectors",
  "SaaS",
  "Fintech",
  "Health",
  "AI",
  "Crypto",
  "E-commerce",
  "Other",
] as const;

export const FUNDING_STAGES = [
  "All Stages",
  "Pre-seed",
  "Seed",
  "Series A",
  "Series B",
  "Series C+",
] as const;

export const SCORE_RANGES = [
  { label: "Any Score", value: 0 },
  { label: "≥ 20", value: 20 },
  { label: "≥ 30", value: 30 },
  { label: "≥ 40", value: 40 },
  { label: "≥ 50", value: 50 },
] as const;

interface FilterSidebarProps {
  filters: Filters;
  onChange: (filters: Filters) => void;
  counts?: { region: Record<string, number>; sector: Record<string, number>; stage: Record<string, number> };
}

function RegionIcon() {
  return (
    <svg className="w-4 h-4 inline mr-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="12" r="10" />
      <path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
    </svg>
  );
}

function SectorIcon() {
  return (
    <svg className="w-4 h-4 inline mr-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z" />
      <line x1="7" y1="7" x2="7.01" y2="7" />
    </svg>
  );
}

function StageIcon() {
  return (
    <svg className="w-4 h-4 inline mr-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
    </svg>
  );
}

function ScoreIcon() {
  return (
    <svg className="w-4 h-4 inline mr-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
    </svg>
  );
}

export function FilterSidebar({ filters, onChange, counts }: FilterSidebarProps) {
  const update = useCallback(
    <K extends keyof Filters>(key: K, value: Filters[K]) => {
      onChange({ ...filters, [key]: value });
    },
    [filters, onChange]
  );

  const reset = useCallback(() => {
    onChange({ region: "All Regions", sector: "All Sectors", fundingStage: "All Stages", minScore: 0, search: "" });
  }, [onChange]);

  const hasActiveFilters =
    filters.region !== "All Regions" ||
    filters.sector !== "All Sectors" ||
    filters.fundingStage !== "All Stages" ||
    filters.minScore > 0 ||
    filters.search !== "";

  return (
    <aside className="w-64 flex-shrink-0 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="font-semibold text-sm text-gray-500 dark:text-gray-400 uppercase tracking-wider">Filters</h2>
        {hasActiveFilters && (
          <button
            onClick={reset}
            className="text-xs text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300"
          >
            Clear all
          </button>
        )}
      </div>

      {/* Region */}
      <div>
        <h3 className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2 flex items-center">
          <RegionIcon /> Region
        </h3>
        <div className="space-y-1">
          {REGIONS.map((region) => {
            const count = counts?.region[region] ?? null;
            return (
              <button
                key={region}
                onClick={() => update("region", region)}
                className={`w-full text-left px-3 py-1.5 rounded text-sm flex justify-between items-center transition-colors ${
                  filters.region === region
                    ? "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200 font-medium"
                    : "hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-600 dark:text-gray-400"
                }`}
              >
                <span>{region}</span>
                {count !== null && count !== undefined && (
                  <span className={`text-xs ${filters.region === region ? "text-blue-600" : "text-gray-400"}`}>
                    {count}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Sector */}
      <div>
        <h3 className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2 flex items-center">
          <SectorIcon /> Sector
        </h3>
        <div className="space-y-1">
          {SECTORS.map((sector) => {
            const count = counts?.sector[sector] ?? null;
            return (
              <button
                key={sector}
                onClick={() => update("sector", sector)}
                className={`w-full text-left px-3 py-1.5 rounded text-sm flex justify-between items-center transition-colors ${
                  filters.sector === sector
                    ? "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200 font-medium"
                    : "hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-600 dark:text-gray-400"
                }`}
              >
                <span>{sector}</span>
                {count !== null && count !== undefined && (
                  <span className={`text-xs ${filters.sector === sector ? "text-blue-600" : "text-gray-400"}`}>
                    {count}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Funding Stage */}
      <div>
        <h3 className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2 flex items-center">
          <StageIcon /> Funding Stage
        </h3>
        <div className="space-y-1">
          {FUNDING_STAGES.map((stage) => {
            const count = counts?.stage[stage] ?? null;
            return (
              <button
                key={stage}
                onClick={() => update("fundingStage", stage)}
                className={`w-full text-left px-3 py-1.5 rounded text-sm flex justify-between items-center transition-colors ${
                  filters.fundingStage === stage
                    ? "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200 font-medium"
                    : "hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-600 dark:text-gray-400"
                }`}
              >
                <span>{stage}</span>
                {count !== null && count !== undefined && (
                  <span className={`text-xs ${filters.fundingStage === stage ? "text-blue-600" : "text-gray-400"}`}>
                    {count}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Signal Score */}
      <div>
        <h3 className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2 flex items-center">
          <ScoreIcon /> Min Signal Score
        </h3>
        <div className="space-y-1">
          {SCORE_RANGES.map((range) => (
            <button
              key={range.value}
              onClick={() => update("minScore", range.value)}
              className={`w-full text-left px-3 py-1.5 rounded text-sm flex justify-between items-center transition-colors ${
                filters.minScore === range.value
                  ? "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200 font-medium"
                  : "hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-600 dark:text-gray-400"
              }`}
            >
              <span>{range.label}</span>
              {range.value > 0 && (
                <span className={`text-xs px-1.5 py-0.5 rounded ${
                  filters.minScore === range.value
                    ? "bg-blue-200 dark:bg-blue-800"
                    : "bg-gray-100 dark:bg-gray-700"
                }`}>
                  {range.value}+
                </span>
              )}
            </button>
          ))}
        </div>
      </div>
    </aside>
  );
}
