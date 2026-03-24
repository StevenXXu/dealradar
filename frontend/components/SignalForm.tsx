"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

const SIGNAL_TYPES = ["Hiring", "Founder Move", "Fundraising", "Technical Signal", "Other"];

export function SignalForm({ companyId }: { companyId?: string }) {
  const router = useRouter();
  const [company, setCompany] = useState(companyId || "");
  const [signalType, setSignalType] = useState("Hiring");
  const [body, setBody] = useState("");
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "submitting" | "success" | "error">("idle");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (body.length < 20) {
      alert("Description must be at least 20 characters.");
      return;
    }
    setStatus("submitting");
    const res = await fetch("/api/signals", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ company_id: company, source: "ugc", signal_type: signalType, body, email }),
    });
    if (res.ok) {
      setStatus("success");
    } else {
      setStatus("error");
    }
  }

  if (status === "success") {
    return (
      <div className="text-center py-8">
        <h2 className="text-xl font-semibold text-green-600 dark:text-green-400">Signal Submitted!</h2>
        <p className="text-gray-500 mt-2 dark:text-gray-400">Thank you. Your signal will appear on the company page once reviewed.</p>
        <button onClick={() => router.push("/")} className="mt-4 text-blue-600 hover:underline dark:text-blue-400">
          ← Back to feed
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4 max-w-md">
      <div>
        <label className="block text-sm font-medium mb-1 dark:text-gray-200">Company Domain or ID</label>
        <input
          value={company}
          onChange={(e) => setCompany(e.target.value)}
          placeholder="acme.com or company-uuid"
          required
          className="w-full border border-gray-200 dark:border-gray-700 rounded px-3 py-2 dark:bg-gray-900 dark:text-gray-100"
        />
      </div>

      <div>
        <label className="block text-sm font-medium mb-1 dark:text-gray-200">Signal Type</label>
        <select value={signalType} onChange={(e) => setSignalType(e.target.value)}
                className="w-full border border-gray-200 dark:border-gray-700 rounded px-3 py-2 dark:bg-gray-900 dark:text-gray-100">
          {SIGNAL_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>

      <div>
        <label className="block text-sm font-medium mb-1 dark:text-gray-200">Description (min 20 chars)</label>
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder="e.g. Company X just posted a job ad for a CFO..."
          required
          minLength={20}
          rows={4}
          className="w-full border border-gray-200 dark:border-gray-700 rounded px-3 py-2 dark:bg-gray-900 dark:text-gray-100"
        />
      </div>

      <div>
        <label className="block text-sm font-medium mb-1 dark:text-gray-200">Your Email (optional)</label>
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="for follow-up only"
          className="w-full border border-gray-200 dark:border-gray-700 rounded px-3 py-2 dark:bg-gray-900 dark:text-gray-100"
        />
      </div>

      {status === "error" && (
        <p className="text-red-500 text-sm dark:text-red-400">Something went wrong. Please try again.</p>
      )}

      <button
        type="submit"
        disabled={status === "submitting"}
        className="w-full bg-blue-600 text-white rounded px-4 py-2 hover:bg-blue-700 disabled:opacity-50 dark:bg-blue-700 dark:hover:bg-blue-600"
      >
        {status === "submitting" ? "Submitting..." : "Submit Signal"}
      </button>
    </form>
  );
}