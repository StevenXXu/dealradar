import { AdminSignalTable } from "@/components/AdminSignalTable";
import { auth } from "@clerk/nextjs/server";
import Link from "next/link";

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