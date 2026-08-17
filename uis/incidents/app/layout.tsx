import type { Metadata } from "next";
import NavLinks from "@/components/NavLinks";
import RouteGuard from "@/components/RouteGuard";
import "./globals.css";

export const metadata: Metadata = {
  title: "Brasaland Incidents",
  description: "Upload and review after-sales incident reports — Brasaland Digital team.",
};

export default function WebLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-stone-100 text-stone-900 antialiased">
        <div className="flex min-h-screen flex-col">
          <header className="bg-stone-900 text-white px-6 py-3 flex items-center gap-3 shadow">
            <span className="text-red-500 font-bold text-lg">BRASA</span>
            <span className="font-semibold text-stone-300">Digital</span>
            <NavLinks />
            <span className="ml-auto text-xs text-stone-500 uppercase tracking-widest">
              Internal · Brasaland Digital
            </span>
          </header>
          <main className="flex-1 px-6 py-8">
            <RouteGuard>{children}</RouteGuard>
          </main>
          <footer className="border-t border-stone-200 bg-white px-6 py-3 text-xs text-stone-400 text-center">
            Brasaland Digital — for internal use only
          </footer>
        </div>
      </body>
    </html>
  );
}
