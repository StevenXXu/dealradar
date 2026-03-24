import { SignalForm } from "@/components/SignalForm";
import Link from "next/link";

export default function SubmitPage() {
  return (
    <main className="max-w-2xl mx-auto p-6">
      <Link href="/" className="text-sm text-blue-600 hover:underline mb-4 inline-block dark:text-blue-400">
        ← Back to feed
      </Link>
      <h1 className="text-2xl font-bold mb-2 dark:text-gray-100">Submit a Signal</h1>
      <p className="text-gray-500 mb-6 dark:text-gray-400">
        Heard something about a company? Share what you know and help the community.
      </p>
      <SignalForm />
    </main>
  );
}