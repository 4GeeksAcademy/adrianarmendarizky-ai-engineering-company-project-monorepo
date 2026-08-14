"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, type Incident, listIncidents, updateIncidentStatus } from "../../lib/api";
import {
  BRANCHES,
  branchLabel,
  categoryLabel,
  ORIGINS,
  STATUSES,
  VALID_TRANSITIONS,
} from "../../lib/incidentOptions";

type LoadState = "loading" | "error" | "ready";

export default function IncidentListPage() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [filters, setFilters] = useState({ status: "", origin: "", branch: "" });
  const [rowError, setRowError] = useState<Record<number, string>>({});
  const [rowUpdating, setRowUpdating] = useState<Record<number, boolean>>({});

  const fetchIncidents = useCallback(async () => {
    setLoadState("loading");
    try {
      const data = await listIncidents({
        status: filters.status || undefined,
        origin: filters.origin || undefined,
        branch: filters.branch || undefined,
      });
      setIncidents(data);
      setLoadState("ready");
    } catch {
      setLoadState("error");
    }
  }, [filters]);

  useEffect(() => {
    fetchIncidents();
  }, [fetchIncidents]);

  async function handleStatusChange(incident: Incident, newStatus: string) {
    const previousStatus = incident.status;

    // Optimistic update -- shows the change immediately, reverted below
    // if the request actually fails.
    setIncidents((prev) =>
      prev.map((i) => (i.id === incident.id ? { ...i, status: newStatus } : i))
    );
    setRowUpdating((prev) => ({ ...prev, [incident.id]: true }));
    setRowError((prev) => ({ ...prev, [incident.id]: "" }));

    try {
      const updated = await updateIncidentStatus(incident.id, newStatus);
      setIncidents((prev) => prev.map((i) => (i.id === incident.id ? updated : i)));
    } catch (err) {
      setIncidents((prev) =>
        prev.map((i) => (i.id === incident.id ? { ...i, status: previousStatus } : i))
      );
      const message = err instanceof ApiError ? err.message : "Update failed. Please try again.";
      setRowError((prev) => ({ ...prev, [incident.id]: message }));
    } finally {
      setRowUpdating((prev) => ({ ...prev, [incident.id]: false }));
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-stone-900">Incidents</h1>
        <p className="text-sm text-stone-500 mt-1">All registered incidents across Brasaland.</p>
      </div>

      <div className="flex flex-wrap gap-3">
        <select
          value={filters.status}
          onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))}
          className="rounded-lg border border-stone-300 px-3 py-2 text-sm bg-white"
        >
          <option value="">All statuses</option>
          {STATUSES.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
        <select
          value={filters.origin}
          onChange={(e) => setFilters((f) => ({ ...f, origin: e.target.value }))}
          className="rounded-lg border border-stone-300 px-3 py-2 text-sm bg-white"
        >
          <option value="">All origins</option>
          {ORIGINS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <select
          value={filters.branch}
          onChange={(e) => setFilters((f) => ({ ...f, branch: e.target.value }))}
          className="rounded-lg border border-stone-300 px-3 py-2 text-sm bg-white"
        >
          <option value="">All branches</option>
          {BRANCHES.map((b) => (
            <option key={b.value} value={b.value}>
              {b.label}
            </option>
          ))}
        </select>
      </div>

      {loadState === "loading" && (
        <p className="text-sm text-stone-500 text-center py-10">Loading incidents…</p>
      )}

      {loadState === "error" && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-center">
          <p className="text-sm text-red-700 mb-3">We couldn&apos;t load the incident list.</p>
          <button
            onClick={fetchIncidents}
            className="rounded-lg bg-stone-900 text-white text-sm font-medium px-4 py-2 hover:bg-stone-800"
          >
            Try again
          </button>
        </div>
      )}

      {loadState === "ready" && incidents.length === 0 && (
        <div className="rounded-xl border border-stone-200 bg-white p-10 text-center text-sm text-stone-500">
          No incidents match these filters yet.
        </div>
      )}

      {loadState === "ready" && incidents.length > 0 && (
        <div className="rounded-xl border border-stone-200 bg-white shadow-sm divide-y divide-stone-100">
          {incidents.map((incident) => {
            const nextStatuses = VALID_TRANSITIONS[incident.status] ?? [];
            const isFinal = nextStatuses.length === 0;
            return (
              <div
                key={incident.id}
                className="p-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-stone-900 truncate">{incident.title}</p>
                  <p className="text-xs text-stone-500 mt-0.5">
                    {categoryLabel(incident.category)} · {branchLabel(incident.branch)} ·{" "}
                    {new Date(incident.created_at).toLocaleDateString()}
                  </p>
                  {rowError[incident.id] && (
                    <p className="text-xs text-red-600 mt-1">{rowError[incident.id]}</p>
                  )}
                </div>
                <select
                  value={incident.status}
                  disabled={rowUpdating[incident.id] || isFinal}
                  onChange={(e) => handleStatusChange(incident, e.target.value)}
                  className="rounded-lg border border-stone-300 px-3 py-2 text-sm bg-white disabled:opacity-60 shrink-0"
                >
                  <option value={incident.status}>
                    {STATUSES.find((s) => s.value === incident.status)?.label}
                  </option>
                  {nextStatuses.map((s) => (
                    <option key={s} value={s}>
                      {STATUSES.find((st) => st.value === s)?.label}
                    </option>
                  ))}
                </select>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
