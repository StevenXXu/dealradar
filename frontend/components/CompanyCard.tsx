import Link from "next/link";
import { Company } from "@/lib/types";

export function CompanyCard({ company }: { company: Company }) {
  return (
    <Link href={`/company/${company.id}`} className="block border border-gray-200 dark:border-gray-700 rounded p-4 hover:shadow transition dark:bg-gray-900">
      <div className="flex justify-between items-start">
        <div>
          <h3 className="font-semibold text-lg dark:text-gray-100">{company.company_name}</h3>
          <p className="text-sm text-gray-500 dark:text-gray-400">{company.domain}</p>
        </div>
        <span className="text-sm font-medium bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 rounded px-2 py-1">
          {company.signal_score}
        </span>
      </div>
      <p className="mt-2 text-gray-700 dark:text-gray-300">{company.one_liner || "No description yet."}</p>
      <div className="mt-2 flex gap-2 flex-wrap">
        {company.sector && (
          <span className="text-xs bg-gray-100 dark:bg-gray-800 px-2 py-1 rounded dark:text-gray-300">{company.sector}</span>
        )}
        {company.tags?.slice(0, 3).map((tag) => (
          <span key={tag} className="text-xs bg-gray-100 dark:bg-gray-800 px-2 py-1 rounded dark:text-gray-300">{tag}</span>
        ))}
      </div>
    </Link>
  );
}