import { AdminSignalTable } from "@/components/AdminSignalTable";
import { auth } from "@clerk/nextjs/server";
import Link from "next/link";

// Force dynamic rendering. The Clerk server auth() call requires
// runtime request context and a configured ClerkProvider chain;
// running it during Vercel's static prerender pass throws the same
// way /alerts did at commit 1c15677. Marking this page dynamic
// defers auth() to request time so build succeeds even before
// Clerk env vars are wired up. When Clerk is fully onboarded this
// can stay as-is (dynamic) or be re-evaluated.
export const dynamic = "force-dynamic";

export default async function SignalsAdminPage() {
  // Phase 1: any authenticated user can access. Tighten to specific user emails in Phase 2.
  await auth();
  return (
    <main className="max-w-6xl mx-auto p-6">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold dark:text-gray-100">Signal Queue</h1>
          <p className="text-gray-500 text-sm dark:text-gray-400">Review and approve community-submitted signals</p>
        </div>
        <Link href="/" className="text-sm text-blue-600 hover:underline dark:text-blue-400">
          ← Back to feed
        </Link>
      </div>
      <AdminSignalTable />
    </main>
  );
}