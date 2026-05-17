"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useAuth } from "@clerk/nextjs";
import { fetchTenantAlerts, updateTenantAlerts } from "@/lib/api";

export default function AlertsPage() {
  const { getToken } = useAuth();
  const [slackUrl, setSlackUrl] = useState("");
  const [customUrl, setCustomUrl] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    async function loadAlerts() {
      try {
        const token = await getToken({ template: "supabase" });
        const data = await fetchTenantAlerts(token || undefined);
        if (data.slack_webhook_url) setSlackUrl(data.slack_webhook_url);
        if (data.custom_webhook_url) setCustomUrl(data.custom_webhook_url);
      } catch (e) {
        console.error("Failed to load alerts config", e);
      } finally {
        setLoading(false);
      }
    }
    loadAlerts();
  }, [getToken]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setMessage("");

    try {
      const token = await getToken({ template: "supabase" });
      const { ok } = await updateTenantAlerts(
        {
          slack_webhook_url: slackUrl,
          custom_webhook_url: customUrl,
        },
        token || undefined,
      );
      setMessage(
        ok ? "Settings saved successfully!" : "Failed to save settings.",
      );
    } catch (e) {
      console.error(e);
      setMessage("An error occurred while saving.");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <main className="max-w-2xl mx-auto p-6">
        <div className="animate-pulse">Loading settings...</div>
      </main>
    );
  }

  return (
    <main className="max-w-2xl mx-auto p-6">
      <Link href="/" className="text-sm text-blue-600 hover:underline mb-4 inline-block dark:text-blue-400">
        ← Back to feed
      </Link>
      <h1 className="text-2xl font-bold mb-2 dark:text-gray-100">Alert Settings</h1>
      <p className="text-gray-500 mb-6 dark:text-gray-400">
        Configure where you want to receive real-time notifications for company raises.
      </p>

      <form onSubmit={handleSave} className="space-y-6">
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Slack Webhook URL
          </label>
          <input
            type="url"
            value={slackUrl}
            onChange={(e) => setSlackUrl(e.target.value)}
            placeholder="https://hooks.slack.com/services/..."
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-800 dark:border-gray-700 dark:text-gray-100"
          />
          <p className="text-xs text-gray-500 mt-1">
            Get pinged in Slack when a tracked company raises funding.
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Custom Webhook URL
          </label>
          <input
            type="url"
            value={customUrl}
            onChange={(e) => setCustomUrl(e.target.value)}
            placeholder="https://api.example.com/webhooks/raise"
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-800 dark:border-gray-700 dark:text-gray-100"
          />
          <p className="text-xs text-gray-500 mt-1">
            We will POST a JSON payload with company details to this URL.
          </p>
        </div>

        <div className="flex items-center gap-4">
          <button
            type="submit"
            disabled={saving}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {saving ? "Saving..." : "Save Settings"}
          </button>
          {message && (
            <span className={`text-sm ${message.includes("success") ? "text-green-600" : "text-red-600"}`}>
              {message}
            </span>
          )}
        </div>
      </form>
    </main>
  );
}