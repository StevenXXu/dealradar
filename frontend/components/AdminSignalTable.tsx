"use client";
import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import { Signal } from "@/lib/types";

export function AdminSignalTable() {
  const [signals, setSignals] = useState<(Signal & { companies?: { company_name: string; domain: string } })[]>([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    const { data, error } = await supabase
      .from("signals")
      .select("*, companies(company_name, domain)")
      .in("status", ["pending", "published", "rejected"])
      .order("created_at", { ascending: false });
    if (error) {
      console.error("Failed to load signals:", error);
      setSignals([]);
    } else {
      setSignals(data || []);
    }
    setLoading(false);
  }

  useEffect(() => { load(); }, []);

  async function approve(id: string) {
    const { error } = await supabase.from("signals").update({ status: "published" }).eq("id", id);
    if (!error) await load();
  }

  async function reject(id: string) {
    const { error } = await supabase.from("signals").update({ status: "rejected" }).eq("id", id);
    if (!error) await load();
  }

  if (loading) return <p className="text-gray-400 dark:text-gray-500">Loading...</p>;

  if (signals.length === 0) {
    return <p className="text-gray-400 dark:text-gray-500 text-sm">No signals to review.</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full border border-gray-200 dark:border-gray-700">
        <thead>
          <tr className="bg-gray-50 border-b border-gray-200 dark:bg-gray-800 dark:border-gray-700">
            <th className="text-left p-3 text-sm dark:text-gray-200">Company</th>
            <th className="text-left p-3 text-sm dark:text-gray-200">Type</th>
            <th className="text-left p-3 text-sm dark:text-gray-200">Signal</th>
            <th className="text-left p-3 text-sm dark:text-gray-200">Status</th>
            <th className="text-left p-3 text-sm dark:text-gray-200">Actions</th>
          </tr>
        </thead>
        <tbody>
          {signals.map((signal) => (
            <tr key={signal.id} className="border-b border-gray-100 dark:border-gray-700 dark:bg-gray-900">
              <td className="p-3 text-sm">
                <p className="font-medium dark:text-gray-100">{signal.companies?.company_name || "Unknown"}</p>
                <p className="text-gray-400 text-xs dark:text-gray-500">{signal.companies?.domain}</p>
              </td>
              <td className="p-3 text-sm dark:text-gray-300">{signal.content?.title || signal.source}</td>
              <td className="p-3 text-sm max-w-xs truncate dark:text-gray-300">{signal.content?.body}</td>
              <td className="p-3 text-sm">
                <span className={`px-2 py-1 rounded text-xs ${
                  signal.status === "published" ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200" :
                  signal.status === "rejected" ? "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200" :
                  "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200"
                }`}>{signal.status}</span>
              </td>
              <td className="p-3 text-sm">
                {signal.status === "pending" && (
                  <>
                    <button onClick={() => approve(signal.id)}
                            className="text-green-600 hover:underline text-sm mr-3 dark:text-green-400">Approve</button>
                    <button onClick={() => reject(signal.id)}
                            className="text-red-600 hover:underline text-sm dark:text-red-400">Reject</button>
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}