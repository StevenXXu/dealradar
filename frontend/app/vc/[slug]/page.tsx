"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { supabase } from "@/lib/supabase";
import { Company, Institution } from "@/lib/types";
import { CompanyCard } from "@/components/CompanyCard";
import Link from "next/link";

export default function VCPortfolioPage() {
  const { slug } = useParams();
  const [institution, setInstitution] = useState<Institution | null>(null);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!slug) return;

    async function fetchData() {
      const { data: instData, error: instError } = await supabase
        .from("institutions")
        .select("*")
        .eq("slug", slug)
        .single();

      if (instError || !instData) {
        console.error("Failed to fetch institution:", instError);
        setInstitution(null);
        setLoading(false);
        return;
      }

      setInstitution(instData);

      const { data: companiesData, error: companiesError } = await supabase
        .from("companies")
        .select("*")
        .eq("institution_id", instData.id)
        .order("signal_score", { ascending: false });

      if (companiesError) {
        console.error("Failed to fetch companies:", companiesError);
        setCompanies([]);
      } else {
        setCompanies(companiesData || []);
      }
      setLoading(false);
    }

    fetchData();
  }, [slug]);

  if (loading) return <p className="p-6 text-gray-500 dark:text-gray-400">Loading...</p>;
  if (!institution) return <p className="p-6 text-gray-500 dark:text-gray-400">VC not found.</p>;

  return (
    <main className="max-w-4xl mx-auto p-6">
      <Link href="/" className="text-sm text-blue-600 hover:underline mb-4 inline-block dark:text-blue-400">
        ← Back to feed
      </Link>

      <div className="mb-6">
        <h1 className="text-3xl font-bold dark:text-gray-100">{institution.name}</h1>
        {institution.website_url && (
          <a href={institution.website_url} target="_blank" rel="noopener noreferrer"
             className="text-sm text-blue-600 hover:underline dark:text-blue-400">
            {institution.website_url} →
          </a>
        )}
        <p className="text-gray-500 mt-1 dark:text-gray-400">{companies.length} companies in portfolio</p>
      </div>

      {companies.length === 0 ? (
        <p className="text-gray-400 dark:text-gray-500 text-sm">No companies in portfolio yet.</p>
      ) : (
        <div className="grid gap-4">
          {companies.map((company) => (
            <CompanyCard key={company.id} company={company} />
          ))}
        </div>
      )}
    </main>
  );
}