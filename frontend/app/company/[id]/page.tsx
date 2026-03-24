"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { supabase } from "@/lib/supabase";
import { Company, Signal } from "@/lib/types";
import Link from "next/link";

export default function CompanyDetailPage() {
  const { id } = useParams();
  const [company, setCompany] = useState<Company | null>(null);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;

    async function fetchData() {
      const { data: companyData, error: companyError } = await supabase
        .from("companies")
        .select("*")
        .eq("id", id)
        .single();

      if (companyError) {
        console.error("Failed to fetch company:", companyError);
        setCompany(null);
        setLoading(false);
        return;
      }

      setCompany(companyData);

      const { data: signalsData, error: signalsError } = await supabase
        .from("signals")
        .select("*")
        .eq("company_id", id)
        .in("status", ["published", "pending"])
        .order("created_at", { ascending: false });

      if (signalsError) {
        console.error("Failed to fetch signals:", signalsError);
        setSignals([]);
      } else {
        setSignals(signalsData || []);
      }
      setLoading(false);
    }

    fetchData();
  }, [id]);

  if (loading) return <p className="p-6 text-gray-500">Loading...</p>;
  if (!company) return <p className="p-6 text-gray-500">Company not found.</p>;

  return (
    <main className="max-w-3xl mx-auto p-6">
      <Link href="/" className="text-sm text-blue-600 hover:underline mb-4 inline-block dark:text-blue-400">
        ← Back to feed
      </Link>

      <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-6 mb-6 dark:bg-gray-900">
        <div className="flex justify-between items-start">
          <div>
            <h1 className="text-2xl font-bold dark:text-gray-100">{company.company_name}</h1>
            <p className="text-gray-500 dark:text-gray-400">{company.domain}</p>
          </div>
          <span className="text-2xl font-bold text-blue-600 dark:text-blue-400">{company.signal_score}</span>
        </div>

        <p className="mt-4 text-lg dark:text-gray-200">{company.one_liner || "No description available."}</p>

        <div className="mt-4 flex gap-2 flex-wrap">
          {company.sector && (
            <span className="bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 px-2 py-1 rounded text-sm">{company.sector}</span>
          )}
          {company.tags?.map((tag) => (
            <span key={tag} className="bg-gray-100 dark:bg-gray-800 px-2 py-1 rounded text-sm dark:text-gray-300">{tag}</span>
          ))}
        </div>

        <div className="mt-4 grid grid-cols-2 gap-4 text-sm">
          {company.last_raise_amount && (
            <div>
              <p className="text-gray-500 dark:text-gray-400">Last Raise</p>
              <p className="font-medium dark:text-gray-200">{company.last_raise_amount}</p>
            </div>
          )}
          {company.last_raise_date && (
            <div>
              <p className="text-gray-500 dark:text-gray-400">Raise Date</p>
              <p className="font-medium dark:text-gray-200">{company.last_raise_date}</p>
            </div>
          )}
          {company.funding_clock && (
            <div>
              <p className="text-gray-500 dark:text-gray-400">Funding Clock</p>
              <p className="font-medium dark:text-gray-200">{company.funding_clock}</p>
            </div>
          )}
        </div>

        {company.source_url && (
          <a href={company.source_url} target="_blank" rel="noopener noreferrer"
             className="mt-4 inline-block text-sm text-blue-600 hover:underline dark:text-blue-400">
            View Source →
          </a>
        )}
      </div>

      {/* Signals Section */}
      <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-6 dark:bg-gray-900">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-semibold dark:text-gray-100">Signals</h2>
          <Link href={`/submit?company=${company.id}`} className="text-sm bg-blue-600 text-white px-3 py-1 rounded dark:bg-blue-700">
            Submit Signal
          </Link>
        </div>

        {signals.length === 0 ? (
          <p className="text-gray-400 text-sm">No signals yet. Be the first to submit one.</p>
        ) : (
          <div className="space-y-3">
            {signals.map((signal) => (
              <div key={signal.id} className="border-b border-gray-100 dark:border-gray-700 pb-3 last:border-0">
                <p className="text-sm font-medium dark:text-gray-200">{signal.content?.body || "No content"}</p>
                <p className="text-xs text-gray-400 mt-1">
                  {signal.source} · {new Date(signal.created_at).toLocaleDateString()}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}