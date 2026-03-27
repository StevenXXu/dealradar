"use client";
import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import { Company } from "@/lib/types";
import { CompanyCard } from "@/components/CompanyCard";

const SECTORS = ["All", "SaaS", "Fintech", "Health", "AI", "Crypto", "E-commerce", "Other"];

const PAGE_SIZE = 50;

export default function DiscoveryFeed() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [sector, setSector] = useState("All");
  const [sort, setSort] = useState<"score" | "name" | "newest">("score");
  const [page, setPage] = useState(0);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const from = page * PAGE_SIZE;
    let query = supabase
      .from("companies")
      .select("*", { count: "exact" })
      .order(sort === "score" ? "signal_score" : sort === "name" ? "company_name" : "created_at", { ascending: sort === "name" })
      .range(from, from + PAGE_SIZE - 1);

    if (sector !== "All") {
      query = query.eq("sector", sector);
    }

    query.then(({ data, count, error }) => {
      if (error) {
        console.error("Failed to fetch companies:", error);
        setCompanies([]);
        setTotalCount(0);
        setLoading(false);
        return;
      }
      setCompanies(data || []);
      setTotalCount(count || 0);
      setLoading(false);
    });
  }, [sector, sort, page]);

  const totalPages = Math.ceil(totalCount / PAGE_SIZE);

  return (
    <main className="max-w-4xl mx-auto p-6">
      <h1 className="text-3xl font-bold mb-2">DealRadar</h1>
      <p className="text-gray-500 mb-6">Discover companies VCs are funding before the market does.</p>

      <div className="flex gap-4 mb-6 flex-wrap">
        <div className="flex gap-2">
          {SECTORS.map((s) => (
            <button
              key={s}
              onClick={() => setSector(s)}
              className={`px-3 py-1 rounded text-sm ${sector === s ? "bg-blue-600 text-white" : "bg-gray-100"}`}
            >
              {s}
            </button>
          ))}
        </div>
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value as "score" | "name" | "newest")}
          className="border rounded px-2 py-1 text-sm"
        >
          <option value="score">Top Ranked</option>
          <option value="name">A-Z</option>
          <option value="newest">Newest</option>
        </select>
      </div>

      {loading ? (
        <p className="text-gray-400">Loading...</p>
      ) : companies.length === 0 ? (
        <p className="text-gray-400">No companies found.</p>
      ) : (
        <>
          <div className="grid gap-4">
            {companies.map((company) => (
              <CompanyCard key={company.id} company={company} />
            ))}
          </div>

          {/* Pagination */}
          <div className="flex justify-between items-center mt-6 pt-4 border-t">
            <p className="text-sm text-gray-500">
              Showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, totalCount)} of {totalCount}
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
                className="px-3 py-1 border rounded text-sm disabled:opacity-50"
              >
                ← Prev
              </button>
              <span className="px-3 py-1 text-sm">
                Page {page + 1} of {totalPages || 1}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                disabled={page >= totalPages - 1}
                className="px-3 py-1 border rounded text-sm disabled:opacity-50"
              >
                Next →
              </button>
            </div>
          </div>
        </>
      )}
    </main>
  );
}