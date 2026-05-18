"use client";

import Link from "next/link";
import { Company } from "@/lib/types";

interface DealCardProps {
  company: Company;
  view?: "grid" | "list";
}

function getScoreColor(score: number): string {
  if (score >= 40) return "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200";
  if (score >= 30) return "bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200";
  if (score >= 20) return "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200";
  return "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400";
}

function getScoreLabel(score: number): string {
  if (score >= 40) return "🔥 Critical";
  if (score >= 30) return "🔥 Hot";
  if (score >= 20) return "⚡ Warm";
  return "💤 Cold";
}

function FundingClockBadge({ clock }: { clock: string | null | undefined }) {
  if (!clock) return null;
  // clock is a date string — compute urgency
  const clockDate = new Date(clock);
  const now = new Date();
  const daysUntil = Math.ceil((clockDate.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
  if (daysUntil < 0) return null; // already past, skip
  if (daysUntil <= 30)
    return (
      <span className="inline-flex items-center gap-0.5 text-xs font-medium bg-red-50 text-red-700 dark:bg-red-900/40 dark:text-red-300 px-2 py-0.5 rounded">
        ⏰ {daysUntil}d left
      </span>
    );
  if (daysUntil <= 90)
    return (
      <span className="inline-flex items-center gap-0.5 text-xs font-medium bg-yellow-50 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300 px-2 py-0.5 rounded">
        ⏰ {daysUntil}d left
      </span>
    );
  return null;
}

function RegionBadge({ region }: { region: string | null | undefined }) {
  if (!region) return null;
  const flag = getRegionFlag(region);
  return (
    <span className="inline-flex items-center gap-1 text-xs font-medium bg-gray-50 text-gray-600 dark:bg-gray-800 dark:text-gray-400 px-2 py-0.5 rounded">
      {flag} {region}
    </span>
  );
}

function getRegionFlag(region: string): string {
  const flags: Record<string, string> = {
    "Australia & New Zealand": "🇦🇺",
    "North America": "🌎",
    "Europe": "🇪🇺",
    "Asia Pacific": "🌏",
    "Latin America": "🌎",
    "Middle East & Africa": "🌍",
    "Global": "🌐",
  };
  return flags[region] ?? "🌐";
}

function StageBadge({ stage }: { stage: string | null | undefined }) {
  if (!stage) return null;
  const colors: Record<string, string> = {
    "Pre-seed": "bg-purple-50 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300",
    "Seed": "bg-blue-50 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
    "Series A": "bg-cyan-50 text-cyan-700 dark:bg-cyan-900/40 dark:text-cyan-300",
    "Series B": "bg-teal-50 text-teal-700 dark:bg-teal-900/40 dark:text-teal-300",
    "Series C+": "bg-amber-50 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  };
  return (
    <span className={`inline-flex items-center text-xs font-medium px-2 py-0.5 rounded ${colors[stage] ?? ""}`}>
      {stage}
    </span>
  );
}

function RaiseBadge({ amount }: { amount: string | null | undefined }) {
  if (!amount) return null;
  return (
    <span className="text-xs text-gray-500 dark:text-gray-400 font-mono">
      {amount}
    </span>
  );
}

export function DealCard({ company, view = "grid" }: DealCardProps) {
  const scoreColor = getScoreColor(company.signal_score);
  const scoreLabel = getScoreLabel(company.signal_score);

  if (view === "list") {
    return (
      <Link
        href={`/company/${company.id}`}
        className="flex items-center gap-4 border border-gray-200 dark:border-gray-700 rounded-lg p-3 hover:shadow-md transition dark:bg-gray-900 group"
      >
        {/* Score */}
        <div className={`flex-shrink-0 w-14 h-14 rounded-lg flex flex-col items-center justify-center ${scoreColor}`}>
          <span className="text-lg font-bold">{company.signal_score}</span>
        </div>

        {/* Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="font-semibold text-gray-900 dark:text-gray-100 truncate group-hover:text-blue-600 dark:group-hover:text-blue-400">
              {company.company_name}
            </h3>
            <RegionBadge region={company.region} />
            <StageBadge stage={(company as Company & { funding_stage?: string }).funding_stage} />
          </div>
          <p className="text-sm text-gray-500 dark:text-gray-400 truncate">{company.one_liner || company.domain}</p>
        </div>

        {/* Tags */}
        <div className="hidden lg:flex gap-1 flex-wrap flex-shrink-0 max-w-[200px]">
          {company.tags?.slice(0, 3).map((tag) => (
            <span key={tag} className="text-xs bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 px-1.5 py-0.5 rounded">
              {tag}
            </span>
          ))}
        </div>

        {/* Score label */}
        <div className="flex-shrink-0 text-right">
          <p className="text-xs font-medium text-gray-500 dark:text-gray-400">{scoreLabel}</p>
          <FundingClockBadge clock={company.funding_clock} />
        </div>
      </Link>
    );
  }

  // Grid view (default)
  return (
    <Link
      href={`/company/${company.id}`}
      className="block border border-gray-200 dark:border-gray-700 rounded-xl p-5 hover:shadow-lg transition-all dark:bg-gray-900 group"
    >
      {/* Header: score + name */}
      <div className="flex justify-between items-start mb-3">
        <div className="flex items-center gap-3">
          {/* Score circle */}
          <div className={`w-12 h-12 rounded-xl flex flex-col items-center justify-center ${scoreColor}`}>
            <span className="text-lg font-bold leading-none">{company.signal_score}</span>
          </div>
          <div>
            <h3 className="font-bold text-lg text-gray-900 dark:text-gray-100 group-hover:text-blue-600 dark:group-hover:text-blue-400 leading-tight">
              {company.company_name}
            </h3>
            <p className="text-sm text-gray-500 dark:text-gray-400">{company.domain}</p>
          </div>
        </div>
        <p className={`text-xs font-semibold px-2 py-1 rounded ${scoreColor}`}>{scoreLabel}</p>
      </div>

      {/* One-liner */}
      <p className="text-sm text-gray-700 dark:text-gray-300 mb-4 line-clamp-2">
        {company.one_liner || "No description yet."}
      </p>

      {/* Badges row */}
      <div className="flex flex-wrap gap-2 mb-3">
        {company.sector && (
          <span className="text-xs font-medium bg-blue-50 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300 px-2 py-1 rounded-lg">
            {company.sector}
          </span>
        )}
        <RegionBadge region={company.region} />
        <StageBadge stage={(company as Company & { funding_stage?: string }).funding_stage} />
        <FundingClockBadge clock={company.funding_clock} />
      </div>

      {/* Tags */}
      {company.tags && company.tags.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-2">
          {company.tags.slice(0, 4).map((tag) => (
            <span key={tag} className="text-xs bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 px-2 py-0.5 rounded">
              {tag}
            </span>
          ))}
          {company.tags.length > 4 && (
            <span className="text-xs text-gray-400">+{company.tags.length - 4}</span>
          )}
        </div>
      )}

      {/* Footer */}
      <div className="flex justify-between items-center mt-4 pt-3 border-t border-gray-100 dark:border-gray-800">
        <RaiseBadge amount={company.last_raise_amount} />
        {company.source_url && (
          <span className="text-xs text-blue-600 dark:text-blue-400 font-medium">View →</span>
        )}
      </div>
    </Link>
  );
}
