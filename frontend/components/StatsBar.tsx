"use client";

interface StatsBarProps {
  total: number;
  hotCount: number;
  avgScore: number;
  newThisWeek: number;
}

function FireIcon() {
  return (
    <svg className="w-4 h-4 text-orange-500" viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 14H9V8l7 4-5.5 4z" />
    </svg>
  );
}

function StarIcon() {
  return (
    <svg className="w-4 h-4 text-yellow-500" viewBox="0 0 24 24" fill="currentColor">
      <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
    </svg>
  );
}

function TrendingUpIcon() {
  return (
    <svg className="w-4 h-4 text-green-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <polyline points="23 6 13.5 15.5 8.5 10.5 1 18" />
      <polyline points="17 6 23 6 23 12" />
    </svg>
  );
}

function ZapIcon() {
  return (
    <svg className="w-4 h-4 text-blue-500" viewBox="0 0 24 24" fill="currentColor">
      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
    </svg>
  );
}

export function StatsBar({ total, hotCount, avgScore, newThisWeek }: StatsBarProps) {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
      <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg p-4 flex items-center gap-3">
        <div className="p-2 bg-blue-50 dark:bg-blue-900/30 rounded-lg">
          <ZapIcon />
        </div>
        <div>
          <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">{total.toLocaleString()}</p>
          <p className="text-xs text-gray-500 dark:text-gray-400">Total Deals</p>
        </div>
      </div>

      <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg p-4 flex items-center gap-3">
        <div className="p-2 bg-orange-50 dark:bg-orange-900/30 rounded-lg">
          <FireIcon />
        </div>
        <div>
          <p className="text-2xl font-bold text-orange-600 dark:text-orange-400">{hotCount.toLocaleString()}</p>
          <p className="text-xs text-gray-500 dark:text-gray-400">Hot Deals (Score ≥30)</p>
        </div>
      </div>

      <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg p-4 flex items-center gap-3">
        <div className="p-2 bg-yellow-50 dark:bg-yellow-900/30 rounded-lg">
          <StarIcon />
        </div>
        <div>
          <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">{avgScore.toFixed(1)}</p>
          <p className="text-xs text-gray-500 dark:text-gray-400">Avg Signal Score</p>
        </div>
      </div>

      <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg p-4 flex items-center gap-3">
        <div className="p-2 bg-green-50 dark:bg-green-900/30 rounded-lg">
          <TrendingUpIcon />
        </div>
        <div>
          <p className="text-2xl font-bold text-green-600 dark:text-green-400">{newThisWeek.toLocaleString()}</p>
          <p className="text-xs text-gray-500 dark:text-gray-400">New This Week</p>
        </div>
      </div>
    </div>
  );
}
