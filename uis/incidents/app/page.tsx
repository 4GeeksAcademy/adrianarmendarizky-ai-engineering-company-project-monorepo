"use client";

import { useCallback, useRef, useState } from "react";
import {
  analyzeIncidentsFile,
  downloadResults,
  type AnalysisResult,
} from "../lib/api";

// ---- Small presentational pieces ----

function MetricCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="rounded-xl bg-white p-5 shadow-sm border border-stone-200">
      <p className="text-xs font-semibold uppercase tracking-widest text-stone-500 mb-1">
        {label}
      </p>
      <p className="text-2xl font-bold text-stone-900">{value}</p>
      {sub && <p className="text-xs text-stone-400 mt-1">{sub}</p>}
    </div>
  );
}

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mb-4 text-lg font-semibold text-stone-700 border-b border-stone-200 pb-2">
      {children}
    </h2>
  );
}

function BreakdownBar({
  label,
  count,
  percentage,
}: {
  label: string;
  count: number;
  percentage: number;
}) {
  return (
    <div>
      <div className="flex justify-between text-sm mb-1">
        <span className="font-medium text-stone-700">{label}</span>
        <span className="text-stone-500">
          {count} ({percentage}%)
        </span>
      </div>
      <div className="h-2 rounded-full bg-stone-200 overflow-hidden">
        <div
          className="h-full bg-red-500"
          style={{ width: `${Math.min(percentage, 100)}%` }}
        />
      </div>
    </div>
  );
}

// ---- Upload zone ----

function UploadZone({
  onFileSelected,
  disabled,
}: {
  onFileSelected: (file: File) => void;
  disabled: boolean;
}) {
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setIsDragging(false);
      if (disabled) return;
      const file = e.dataTransfer.files?.[0];
      if (file) onFileSelected(file);
    },
    [onFileSelected, disabled]
  );

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setIsDragging(true);
      }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={handleDrop}
      onClick={() => !disabled && inputRef.current?.click()}
      className={`rounded-xl border-2 border-dashed p-10 text-center cursor-pointer transition-colors ${
        disabled
          ? "border-stone-200 bg-stone-50 cursor-not-allowed"
          : isDragging
          ? "border-red-400 bg-red-50"
          : "border-stone-300 bg-white hover:border-red-300"
      }`}
    >
      <p className="text-stone-700 font-medium">
        Drag and drop a CSV file here, or click to choose one
      </p>
      <p className="text-xs text-stone-400 mt-1">
        Incident report exports only (.csv)
      </p>
      <input
        ref={inputRef}
        type="file"
        accept=".csv"
        className="hidden"
        disabled={disabled}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFileSelected(file);
          e.target.value = "";
        }}
      />
    </div>
  );
}

// ---- Page ----

export default function IncidentAnalysisPage() {
  const [status, setStatus] = useState<"idle" | "loading" | "error" | "done">(
    "idle"
  );
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const handleFileSelected = useCallback(async (file: File) => {
    setStatus("loading");
    setError(null);
    try {
      const data = await analyzeIncidentsFile(file);
      setResult(data);
      setStatus("done");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
      setStatus("error");
    }
  }, []);

  const handleExport = useCallback(async () => {
    setExporting(true);
    setExportError(null);
    try {
      await downloadResults();
    } catch (err) {
      setExportError(
        err instanceof Error ? err.message : "Could not download results."
      );
    } finally {
      setExporting(false);
    }
  }, []);

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-stone-900">
          Incident Report Analysis
        </h1>
        <p className="text-sm text-stone-500 mt-1">
          Upload the monthly incident CSV to validate it and see the summary
          — no terminal needed.
        </p>
      </div>

      <UploadZone
        onFileSelected={handleFileSelected}
        disabled={status === "loading"}
      />

      {status === "loading" && (
        <p className="text-sm text-stone-500 text-center">Analyzing file…</p>
      )}

      {status === "error" && error && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          <p className="font-semibold">Couldn&apos;t analyze that file</p>
          <p className="mt-1">{error}</p>
        </div>
      )}

      {status === "done" && result && (
        <div className="space-y-8">
          <div className="flex items-center justify-between">
            <p className="text-sm text-stone-500">
              Source file:{" "}
              <span className="font-medium text-stone-700">
                {result.source_filename}
              </span>
            </p>
              <div className="flex flex-col items-end gap-1">
              <button
                onClick={handleExport}
                disabled={exporting}
                className="rounded-lg bg-stone-900 text-white text-sm font-medium px-4 py-2 hover:bg-stone-800 transition-colors disabled:opacity-50"
              >
                {exporting ? "Preparing download..." : "Download results as CSV"}
              </button>
              {exportError && (
                <p className="text-xs text-red-600">{exportError}</p>
              )}
            </div>
          </div>

          {/* General metrics */}
          <section>
            <SectionHeading>General metrics</SectionHeading>
            <div className="grid gap-4 sm:grid-cols-3">
              <MetricCard
                label="Total records"
                value={String(result.total_records)}
              />
              <MetricCard
                label="Valid records"
                value={String(result.valid_records)}
              />
              <MetricCard
                label="Invalid / incomplete"
                value={String(result.invalid_records)}
                sub={
                  result.invalid_records > 0
                    ? "excluded from the breakdowns below"
                    : "no problems found"
                }
              />
            </div>
          </section>

          {/* Invalid records */}
          {result.invalid_records > 0 && (
            <section>
              <SectionHeading>Invalid records — why they were rejected</SectionHeading>
              <div className="rounded-xl border border-stone-200 bg-white shadow-sm divide-y divide-stone-100">
                {result.invalid_breakdown
                  .filter((item) => item.count > 0)
                  .map((item) => (
                    <div
                      key={item.rule}
                      className="flex justify-between px-4 py-3 text-sm"
                    >
                      <span className="text-stone-600">{item.label}</span>
                      <span className="font-semibold text-stone-900">
                        {item.count}
                      </span>
                    </div>
                  ))}
              </div>
            </section>
          )}

          {/* Category breakdown */}
          <section>
            <SectionHeading>Breakdown by category (valid records)</SectionHeading>
            <div className="rounded-xl border border-stone-200 bg-white shadow-sm p-5 space-y-4">
              {result.category_breakdown.map((item) => (
                <BreakdownBar
                  key={item.category}
                  label={item.category}
                  count={item.count}
                  percentage={item.percentage}
                />
              ))}
            </div>
          </section>

          {/* Status breakdown */}
          <section>
            <SectionHeading>Breakdown by status (valid records)</SectionHeading>
            <div className="rounded-xl border border-stone-200 bg-white shadow-sm p-5 space-y-4">
              {result.status_breakdown.map((item) => (
                <BreakdownBar
                  key={item.status}
                  label={item.status}
                  count={item.count}
                  percentage={item.percentage}
                />
              ))}
            </div>
          </section>

          {/* Satisfaction index */}
          <section>
            <SectionHeading>Satisfaction index (closed cases)</SectionHeading>
            <div className="grid gap-4 sm:grid-cols-2 mb-4">
              <MetricCard
                label="Average score"
                value={`${result.satisfaction.average_score.toFixed(2)} / 5.00`}
              />
              <MetricCard
                label="Scored cases"
                value={`${result.satisfaction.scored_count} of ${result.satisfaction.closed_total}`}
                sub="closed cases with a recorded score"
              />
            </div>
            <div className="rounded-xl border border-stone-200 bg-white shadow-sm p-5 space-y-4">
              {result.satisfaction.distribution.map((item) => (
                <BreakdownBar
                  key={item.score}
                  label={`Score ${item.score} (${item.label})`}
                  count={item.count}
                  percentage={
                    result.satisfaction.scored_count
                      ? Math.round(
                          (item.count / result.satisfaction.scored_count) * 1000
                        ) / 10
                      : 0
                  }
                />
              ))}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
