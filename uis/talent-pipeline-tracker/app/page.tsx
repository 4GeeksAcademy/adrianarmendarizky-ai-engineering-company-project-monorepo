"use client";

import { useEffect, useState, useMemo, Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Candidate } from "@/types/candidate";
import { getCandidates } from "@/services/api";
import { statusLabel, stageLabel, STATUS_OPTIONS, STAGE_OPTIONS } from "@/lib/labels";
import { statusTone, stageTone } from "@/lib/tones";
import Badge from "@/components/Badge";

function CandidateListInner() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Current filter/search values come from the URL query params.
  const statusFilter = searchParams.get("status") ?? "";
  const stageFilter = searchParams.get("stage") ?? "";
  const searchTerm = searchParams.get("q") ?? "";

  // Fetch once on mount.
  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        setError(null);
        const response = await getCandidates();
        setCandidates(response.data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Something went wrong.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  // Update a query param without reloading the page.
  function setParam(key: string, value: string) {
    const params = new URLSearchParams(searchParams.toString());
    if (value) {
      params.set(key, value);
    } else {
      params.delete(key);
    }
    router.replace(`/?${params.toString()}`);
  }

  // Filtering + search run in memory over the fetched list.
  const visible = useMemo(() => {
    return candidates.filter((c) => {
      if (statusFilter && c.status !== statusFilter) return false;
      if (stageFilter && c.stage !== stageFilter) return false;
      if (searchTerm) {
        const term = searchTerm.toLowerCase();
        const matchesName = c.full_name.toLowerCase().includes(term);
        const matchesEmail = c.email.toLowerCase().includes(term);
        if (!matchesName && !matchesEmail) return false;
      }
      return true;
    });
  }, [candidates, statusFilter, stageFilter, searchTerm]);

  return (
    <main className="mx-auto max-w-5xl px-4 py-8">
      <header className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Candidates</h1>
          <p className="text-sm text-gray-500">
            Executive Assistant · Brasaland, Medellín
          </p>
        </div>
        <Link
          href="/candidates/new"
          className="rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-700"
        >
          Register candidate
        </Link>
      </header>

      {/* Filters + search */}
      <section className="mb-6 grid gap-3 sm:grid-cols-3">
        <input
          type="text"
          placeholder="Search by name or email"
          value={searchTerm}
          onChange={(e) => setParam("q", e.target.value)}
          className="rounded-md border border-gray-300 px-3 py-2 text-sm"
        />
        <select
          value={statusFilter}
          onChange={(e) => setParam("status", e.target.value)}
          className="rounded-md border border-gray-300 px-3 py-2 text-sm"
        >
          <option value="">All statuses</option>
          {STATUS_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <select
          value={stageFilter}
          onChange={(e) => setParam("stage", e.target.value)}
          className="rounded-md border border-gray-300 px-3 py-2 text-sm"
        >
          <option value="">All stages</option>
          {STAGE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </section>

      {/* States */}
      {loading && <p className="text-gray-500">Loading candidates…</p>}

      {error && (
        <div className="rounded-md bg-red-50 p-4 text-sm text-red-800">
          {error} <button onClick={() => location.reload()} className="underline">Retry</button>
        </div>
      )}

      {!loading && !error && visible.length === 0 && (
        <p className="text-gray-500">No candidates match these filters.</p>
      )}

      {!loading && !error && visible.length > 0 && (
        <ul className="divide-y divide-gray-200 rounded-md border border-gray-200">
          {visible.map((c) => (
            <li key={c.id}>
              <Link
                href={`/candidates/${c.id}`}
                className="flex items-center justify-between px-4 py-3 hover:bg-gray-50"
              >
                <div>
                  <p className="font-medium text-gray-900">{c.full_name}</p>
                  <p className="text-sm text-gray-500">{c.position}</p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge label={stageLabel(c.stage)} tone={stageTone()} />
                  <Badge label={statusLabel(c.status)} tone={statusTone(c.status)} />
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}

// useSearchParams requires a Suspense boundary in the App Router.
export default function HomePage() {
  return (
    <Suspense fallback={<p className="p-8 text-gray-500">Loading…</p>}>
      <CandidateListInner />
    </Suspense>
  );
}