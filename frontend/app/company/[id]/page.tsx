"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { supabase } from "@/lib/supabase";
import { Company, Signal } from "@/lib/types";
import Link from "next/link";
import { DealCard } from "@/components/DealCard";

export default function CompanyDetailPage() {
  const { id } = useParams();
  const [company, setCompany] = useState<Company | null>(null);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [related, setRelated] = useState<Company[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;

    async function fetchData() {
      const { data: companyData, error: companyError } = await supabase
        .from("companies")
        .select("*")
        .eq("id", id)
        .single();

      if (companyError || !companyData) {
        console.error("Failed to fetch company:", companyError);
        setCompany(null);
        setLoading(false);
        return;
      }

      setCompany(companyData as Company);

      const { data: signalsData } = await supabase
        .from("signals")
        .select("*")
        .eq("company_id", id)
        .in("status", ["published", "pending"])
        .order("created_at", { ascending: false });

      setSignals(signalsData || []);

      // Fetch related companies (same sector, different company)
      if ((companyData as Company).sector) {
        const { data: relatedData } = await supabase
          .from("companies")
          .select("*")
          .eq("sector", (companyData as Company).sector)
          .neq("id", id)
          .order("signal_score", { ascending: false })
          .limit(3);
        setRelated(relatedData || []);
      }

      setLoading(false);
    }

    fetchData();
  }, [id]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="w-8 h-8 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!company) {
    return (
      <div className="max-w-3xl mx-auto p-6 text-center py-20">
        <p className="text-gray-500 dark:text-gray-400">Company not found.</p>
        <Link href="/" className="text-blue-600 hover:underline dark:text-blue-400 mt-2 inline-block">
          ← Back to feed
        </Link>
      </div>
    );
  }

  const scoreColor =
    company.signal_score >= 40
      ? "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200"
      : company.signal_score >= 30
      ? "bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200"
      : company.signal_score >= 20
      ? "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200"
      : "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400";

  const scoreLabel =
    company.signal_score >= 40 ? "🔥 Critical" :
    company.signal_score >= 30 ? "🔥 Hot" :
    company.signal_score >= 20 ? "⚡ Warm" : "💤 Cold";

  return (
    <main className="max-w-5xl mx-auto p-6">
      <Link href="/" className="text-sm text-blue-600 hover:underline mb-6 inline-block dark:text-blue-400">
        ← Back to Discovery
      </Link>

      <div className="grid lg:grid-cols-3 gap-6">
        {/* Main column */}
        <div className="lg:col-span-2 space-y-6">
          {/* Company card */}
          <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-2xl p-6">
            <div className="flex justify-between items-start mb-4">
              <div>
                <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">{company.company_name}</h1>
                <p className="text-gray-500 dark:text-gray-400 mt-1">{company.domain}</p>
              </div>
              <div className={`text-center px-4 py-2 rounded-xl ${scoreColor}`}>
                <p className="text-3xl font-bold">{company.signal_score}</p>
                <p className="text-xs font-medium mt-0.5">{scoreLabel}</p>
              </div>
            </div>

            <p className="text-lg text-gray-700 dark:text-gray-200 mb-4 leading-relaxed">
              {company.one_liner || "No description available."}
            </p>

            {/* Badges */}
            <div className="flex flex-wrap gap-2 mb-6">
              {company.sector && (
                <span className="text-sm font-medium bg-blue-50 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300 px-3 py-1 rounded-lg">
                  {company.sector}
                </span>
              )}
              {company.region && (
                <span className="text-sm font-medium bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300 px-3 py-1 rounded-lg">
                  🌐 {company.region}
                </span>
              )}
              {(company as Company & { funding_stage?: string }).funding_stage && (
                <span className="text-sm font-medium bg-purple-50 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300 px-3 py-1 rounded-lg">
                  📊 {(company as Company & { funding_stage: string }).funding_stage}
                </span>
              )}
              {company.funding_clock && (() => {
                const days = Math.ceil((new Date(company.funding_clock!).getTime() - Date.now()) / 86400000);
                return days > 0 ? (
                  <span className={`text-sm font-medium px-3 py-1 rounded-lg ${days <= 30 ? "bg-red-50 text-red-700 dark:bg-red-900/40 dark:text-red-300" : "bg-yellow-50 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300"}`}>
                    ⏰ Funding clock: {days}d left
                  </span>
                ) : null;
              })()}
            </div>

            {/* Details grid */}
            <div className="grid grid-cols-2 gap-4 p-4 bg-gray-50 dark:bg-gray-800 rounded-xl">
              {company.last_raise_amount && (
                <div>
                  <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-1">Last Raise</p>
                  <p className="font-semibold text-gray-900 dark:text-gray-100 font-mono">{company.last_raise_amount}</p>
                </div>
              )}
              {company.last_raise_date && (
                <div>
                  <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-1">Raise Date</p>
                  <p className="font-semibold text-gray-900 dark:text-gray-100">{company.last_raise_date}</p>
                </div>
              )}
              {(company as Company & { funding_stage?: string }).funding_stage && (
                <div>
                  <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-1">Stage</p>
                  <p className="font-semibold text-gray-900 dark:text-gray-100">
                    {(company as Company & { funding_stage: string }).funding_stage}
                  </p>
                </div>
              )}
              {company.region && (
                <div>
                  <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-1">Region</p>
                  <p className="font-semibold text-gray-900 dark:text-gray-100">{company.region}</p>
                </div>
              )}
            </div>

            {/* Tags */}
            {company.tags && company.tags.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-4">
                {company.tags.map((tag) => (
                  <span key={tag} className="text-xs bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 px-2 py-1 rounded">
                    #{tag}
                  </span>
                ))}
              </div>
            )}

            {/* Source link */}
            {company.source_url && (
              <a
                href={company.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-4 inline-flex items-center gap-1 text-sm text-blue-600 hover:underline dark:text-blue-400"
              >
                View Source URL →
              </a>
            )}
          </div>

          {/* Signals section */}
          <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-2xl p-6">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">
                Signals ({signals.length})
              </h2>
              <Link
                href={`/submit?company=${company.id}`}
                className="text-sm bg-blue-600 text-white px-4 py-1.5 rounded-lg hover:bg-blue-700 transition-colors"
              >
                Submit Signal
              </Link>
            </div>

            {signals.length === 0 ? (
              <p className="text-gray-400 text-sm dark:text-gray-500 py-4 text-center">
                No signals yet. Be the first to submit one.
              </p>
            ) : (
              <div className="space-y-4">
                {signals.map((signal) => (
                  <div key={signal.id} className="border-b border-gray-100 dark:border-gray-800 last:border-0 pb-4 last:pb-0">
                    <div className="flex gap-2 mb-2">
                      <span className={`text-xs font-medium px-2 py-0.5 rounded ${
                        signal.status === "published"
                          ? "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300"
                          : "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300"
                      }`}>
                        {signal.status}
                      </span>
                      <span className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{signal.source}</span>
                    </div>
                    <p className="text-sm font-medium text-gray-800 dark:text-gray-200">
                      {signal.content?.title && <span className="font-semibold">{signal.content.title} — </span>}
                      {signal.content?.body}
                    </p>
                    {signal.content?.author && (
                      <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">by {signal.content.author}</p>
                    )}
                    <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                      {new Date(signal.created_at).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" })}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Sidebar column */}
        <div className="space-y-6">
          {/* Quick stats */}
          <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-2xl p-6">
            <h3 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-4">
              Deal Indicators
            </h3>
            <div className="space-y-3">
              <div className="flex justify-between items-center">
                <span className="text-sm text-gray-600 dark:text-gray-400">Signal Score</span>
                <span className={`font-bold text-lg ${company.signal_score >= 30 ? "text-orange-600" : "text-gray-900 dark:text-gray-100"}`}>
                  {company.signal_score}
                </span>
              </div>
              {company.last_raise_amount && (
                <div className="flex justify-between items-center">
                  <span className="text-sm text-gray-600 dark:text-gray-400">Last Raise</span>
                  <span className="text-sm font-mono font-medium text-gray-900 dark:text-gray-100">
                    {company.last_raise_amount}
                  </span>
                </div>
              )}
              {(company as Company & { funding_stage?: string }).funding_stage && (
                <div className="flex justify-between items-center">
                  <span className="text-sm text-gray-600 dark:text-gray-400">Stage</span>
                  <span className="text-sm font-medium text-purple-700 dark:text-purple-300">
                    {(company as Company & { funding_stage: string }).funding_stage}
                  </span>
                </div>
              )}
              {company.region && (
                <div className="flex justify-between items-center">
                  <span className="text-sm text-gray-600 dark:text-gray-400">Region</span>
                  <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                    {company.region}
                  </span>
                </div>
              )}
              {company.funding_clock && (
                <div className="flex justify-between items-center">
                  <span className="text-sm text-gray-600 dark:text-gray-400">Funding Clock</span>
                  <span className={`text-sm font-medium ${
                    Math.ceil((new Date(company.funding_clock).getTime() - Date.now()) / 86400000) <= 30
                      ? "text-red-600"
                      : "text-yellow-600"
                  }`}>
                    {company.funding_clock}
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Related deals */}
          {related.length > 0 && (
            <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-2xl p-6">
              <h3 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-4">
                Similar Deals
              </h3>
              <div className="space-y-3">
                {related.map((rel) => (
                  <DealCard key={rel.id} company={rel} view="list" />
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
