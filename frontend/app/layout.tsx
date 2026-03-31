import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "DealRadar — VC Deal Intelligence",
  description: "Discover high-signal startup deals before the market does. Filter by region, sector, and funding stage.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col bg-gray-50 dark:bg-gray-950">
        {/* Top Navigation */}
        <header className="bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 sticky top-0 z-50">
          <div className="max-w-7xl mx-auto px-6 h-14 flex items-center justify-between">
            {/* Logo */}
            <Link href="/" className="flex items-center gap-2 group">
              <div className="w-8 h-8 bg-gradient-to-br from-blue-600 to-blue-700 rounded-lg flex items-center justify-center">
                <svg className="w-5 h-5 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <circle cx="12" cy="12" r="3" />
                  <path d="M12 2v3M12 19v3M4.22 4.22l2.12 2.12M17.66 17.66l2.12 2.12M2 12h3M19 12h3M4.22 19.78l2.12-2.12M17.66 6.34l2.12-2.12" />
                </svg>
              </div>
              <span className="font-bold text-lg text-gray-900 dark:text-gray-100 group-hover:text-blue-600 transition-colors">
                DealRadar
              </span>
            </Link>

            {/* Nav links */}
            <nav className="flex items-center gap-6">
              <Link
                href="/"
                className="text-sm font-medium text-gray-600 dark:text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
              >
                Discover
              </Link>
              <Link
                href="/signals"
                className="text-sm font-medium text-gray-600 dark:text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
              >
                Signals
              </Link>
              <Link
                href="/submit"
                className="text-sm font-medium bg-blue-600 text-white px-4 py-1.5 rounded-lg hover:bg-blue-700 transition-colors"
              >
                Submit Deal
              </Link>
            </nav>
          </div>
        </header>

        {/* Page content */}
        <div className="flex-1">{children}</div>

        {/* Footer */}
        <footer className="border-t border-gray-200 dark:border-gray-800 py-6 bg-white dark:bg-gray-900">
          <div className="max-w-7xl mx-auto px-6 flex flex-col sm:flex-row justify-between items-center gap-3">
            <p className="text-xs text-gray-400 dark:text-gray-500">
              DealRadar — AI-powered deal intelligence for angel investors.
            </p>
            <div className="flex gap-4">
              <Link href="/signals" className="text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
                Signal Queue
              </Link>
              <Link href="/submit" className="text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
                Submit
              </Link>
            </div>
          </div>
        </footer>
      </body>
    </html>
  );
}