"use client";

import { useCallback, useEffect, useState } from "react";
import { getIncidentSummary, type IncidentSummary } from "../../lib/api";
import { BRANCHES, CATEGORIES, ORIGINS, STATUSES } from "../../lib/incidentOptions";

type LoadState = "loading" | "error" | "ready";

function MetricBar({ label, count, total }: { label: string; count: number; total: number }) {
  const pct = total > 0 ? Math.round((count / total) * 1000) / 10 : 0;
  return (
    <div>
      <div className="flex justify-between text-sm mb-1">
        <span className="font-medium text-stone-700">{label}</span>
        <span className="text-stone-500">
          {count}
          {total > 0 ? ` (${pct}%)` : ""}
        </span>
      </div>
      <div className="h-2 rounded-full bg-stone-200 overflow-hidden">
        <div className="h-full bg-red-500" style={{ width: `${Math.min(pct, 100)}%` }} />
      </div>
    </div>
  );
}

function MetricSection({
  title,
  options,
  counts,
  total,
}: {
  title: string;
  options: readonly { value: string; label: string }[];
  counts: Record<string, number>;
  total: number;
}) {
  return (
    <section>
      <h2 className="mb-4 text-lg font-semibold text-stone-700 border-b border-stone-200 pb-2">
        {title}
      </h2>
      <div className="rounded-xl border border-stone-200 bg-white shadow-sm p-5 space-y-4">
        {options.map((o) => (
          <MetricBar key={o.value} label={o.label} count={counts[o.value] ?? 0} total={total} />
        ))}
      </div>
    </section>
  );
}

export default function SummaryPage() {
  const [summary, setSummary] = useState<IncidentSummary | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("loading");

  const fetchSummary = useCallback(async () => {
    setLoadState("loading");
    try {
      const data = await getIncidentSummary();
      setSummary(data);
      setLoadState("ready");
    } catch {
      setLoadState("error");
    }
  }, []);

  useEffect(() => {
    fetchSummary();
  }, [fetchSummary]);

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-stone-900">Incident Summary</h1>
        <p className="text-sm text-stone-500 mt-1">Aggregated totals across all branches.</p>
      </div>

      {loadState === "loading" && (
        <p className="text-sm text-stone-500 text-center py-10">Loading summary…</p>
      )}

      {loadState === "error" && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-center">
          <p className="text-sm text-red-700 mb-3">We couldn&apos;t load the summary right now.</p>
          <button
            onClick={fetchSummary}
            className="rounded-lg bg-stone-900 text-white text-sm font-medium px-4 py-2 hover:bg-stone-800"
          >
            Try again
          </button>
        </div>
      )}

      {loadState === "ready" && summary && (
        <div className="space-y-8">
          <div className="rounded-xl bg-white p-5 shadow-sm border border-stone-200 text-center">
            <p className="text-xs font-semibold uppercase tracking-widest text-stone-500 mb-1">
              Total incidents
            </p>
            <p className="text-3xl font-bold text-stone-900">{summary.total}</p>
          </div>

          <MetricSection
            title="By status"
            options={STATUSES}
            counts={summary.by_status}
            total={summary.total}
          />
          <MetricSection
            title="By category"
            options={CATEGORIES}
            counts={summary.by_category}
            total={summary.total}
          />
          <MetricSection
            title="By origin"
            options={ORIGINS}
            counts={summary.by_origin}
            total={summary.total}
          />
          <MetricSection
            title="By branch"
            options={BRANCHES}
            counts={summary.by_branch}
            total={summary.total}
          />
        </div>
      )}
    </div>
  );
}
