"use client";

// Weekly Location Cost & Waste Report -- the Part 3 business dashboard.
// Fetches GET /reporting/weekly-location-performance and renders every
// KPI from CONTEXT-brasaland.md's "KPIs to Measure" section, labeled
// with the same names used there. This is the page Mariana and Felipe
// actually look at -- the pipeline (data/pipelines/pipeline.py) and its
// endpoints (services/api/routes/reporting.py) exist to feed this, not
// the other way around.
//
// Client component (like the suppliers page) because the week selector
// needs to re-fetch without a full page reload.

import { useEffect, useState, type FormEvent } from "react";
import { authFetch } from "@/lib/api";

// ---- Types (mirror reporting_models.py / routes/reporting.py) ----

type CountryValue = "CO" | "US";
type CurrencyValue = "COP" | "USD";

type LocationPerformance = {
  location_id: string;
  country: CountryValue;
  total_purchase_cost: number;
  total_waste_cost: number;
  waste_ratio: number;
  stockout_events_count: number;
  price_alert_events_count: number;
  currency: CurrencyValue;
};

type WeeklyLocationPerformanceResponse = {
  week_start: string | null;
  locations: LocationPerformance[];
};

// ---- Formatting helpers ----

function formatMoney(amount: number, currency: CurrencyValue): string {
  return currency === "USD"
    ? `$${amount.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    : `${amount.toLocaleString("es-CO", { maximumFractionDigits: 0 })} COP`;
}

function formatPercent(ratio: number): string {
  return `${(ratio * 100).toFixed(1)}%`;
}

function formatWeekLabel(weekStart: string | null): string {
  if (!weekStart) return "No data yet";
  const start = new Date(`${weekStart}T00:00:00Z`);
  const end = new Date(start);
  end.setUTCDate(end.getUTCDate() + 6);
  const fmt = (d: Date) =>
    d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
  return `Week of ${fmt(start)} – ${fmt(end)}, ${start.getUTCFullYear()}`;
}

// ---- Small pieces, styled to match the rest of the backoffice ----

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mb-4 text-lg font-semibold text-stone-700 border-b border-stone-200 pb-2">
      {children}
    </h2>
  );
}

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
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

// ---- Page ----

export default function ReportingPage() {
  const [data, setData] = useState<WeeklyLocationPerformanceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [weekInput, setWeekInput] = useState("");

  async function loadWeek(weekStart?: string) {
    setLoading(true);
    setLoadError(null);
    try {
      const path = weekStart
        ? `/reporting/weekly-location-performance?week_start=${weekStart}`
        : `/reporting/weekly-location-performance`;
      const res = await authFetch(path);
      if (!res.ok) throw new Error(`API returned ${res.status}`);
      const body: WeeklyLocationPerformanceResponse = await res.json();
      setData(body);
    } catch (err) {
      setLoadError(
        err instanceof Error
          ? `Could not load the report: ${err.message}`
          : "Could not load the report."
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadWeek();
  }, []);

  function handleWeekSubmit(e: FormEvent) {
    e.preventDefault();
    if (weekInput) loadWeek(weekInput);
  }

  const locations = data?.locations ?? [];

  // Aggregate per currency -- NEVER summed together across COP and USD,
  // per CONTEXT-brasaland.md section 7's business constraint. The same
  // rule the pipeline itself follows when it writes these rows applies
  // here when the dashboard summarizes them.
  const totalsByCurrency = locations.reduce<Record<string, { purchase: number; waste: number }>>(
    (acc, loc) => {
      const bucket = acc[loc.currency] ?? { purchase: 0, waste: 0 };
      bucket.purchase += loc.total_purchase_cost;
      bucket.waste += loc.total_waste_cost;
      acc[loc.currency] = bucket;
      return acc;
    },
    {}
  );

  return (
    <div className="mx-auto max-w-5xl space-y-10">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-stone-900">
            Weekly Location Cost &amp; Waste Report
          </h1>
          <p className="text-sm text-stone-500 mt-1">
            {formatWeekLabel(data?.week_start ?? null)} — purchase cost, waste, and stock
            risk, per location. The Monday report Mariana asked for, built from telemetry.
          </p>
        </div>

        <form onSubmit={handleWeekSubmit} className="flex shrink-0 items-end gap-2">
          <label className="block text-xs">
            <span className="mb-1 block font-medium text-stone-600">
              View a different week (Monday)
            </span>
            <input
              type="date"
              value={weekInput}
              onChange={(e) => setWeekInput(e.target.value)}
              className="rounded-lg border border-stone-300 px-3 py-2 text-sm"
            />
          </label>
          <button
            type="submit"
            className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-semibold text-white hover:bg-stone-800"
          >
            View
          </button>
        </form>
      </div>

      {loadError && (
        <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
          <p>{loadError}</p>
          <button
            type="button"
            onClick={() => loadWeek(weekInput || undefined)}
            className="mt-2 rounded border border-red-200 bg-white px-2 py-1 text-xs font-semibold text-red-700 hover:bg-red-50"
          >
            Retry
          </button>
        </div>
      )}

      {/* Summary cards -- one pair per currency present, never combined */}
      {!loading && locations.length > 0 && (
        <section aria-labelledby="summary-heading">
          <SectionHeading>Summary</SectionHeading>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            {Object.entries(totalsByCurrency).map(([currency, totals]) => (
              <StatCard
                key={`${currency}-purchase`}
                label={`Total Purchase Cost (${currency})`}
                value={formatMoney(totals.purchase, currency as CurrencyValue)}
              />
            ))}
            {Object.entries(totalsByCurrency).map(([currency, totals]) => (
              <StatCard
                key={`${currency}-waste`}
                label={`Total Waste Cost (${currency})`}
                value={formatMoney(totals.waste, currency as CurrencyValue)}
              />
            ))}
          </div>
        </section>
      )}

      {/* Per-location KPI table -- every KPI from CONTEXT-brasaland.md's
          "KPIs to Measure" section, one column each, labeled with the
          same names used there. */}
      <section aria-labelledby="locations-heading">
        <SectionHeading>By location</SectionHeading>

        <div className="overflow-x-auto rounded-xl border border-stone-200 bg-white shadow-sm">
          <table className="w-full text-sm">
            <thead className="bg-stone-50 text-xs uppercase tracking-widest text-stone-500">
              <tr>
                <th className="px-4 py-3 text-left">Location</th>
                <th className="px-4 py-3 text-left">Country</th>
                <th className="px-4 py-3 text-right">Purchase Cost per Location</th>
                <th className="px-4 py-3 text-right">Waste Cost per Location</th>
                <th className="px-4 py-3 text-right">Waste Ratio</th>
                <th className="px-4 py-3 text-right">Stockout Frequency</th>
                <th className="px-4 py-3 text-right">Price Alert Frequency</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {loading && (
                <tr>
                  <td colSpan={7} className="px-4 py-6 text-center text-stone-400">
                    Loading report...
                  </td>
                </tr>
              )}

              {!loading && locations.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-6 text-center text-stone-400">
                    No data for this week yet. Run the pipeline (see
                    data/pipelines/pipeline.py) to compute it.
                  </td>
                </tr>
              )}

              {!loading &&
                locations.map((loc) => (
                  <tr key={loc.location_id} className="hover:bg-stone-50">
                    <td className="px-4 py-3 font-medium text-stone-900">
                      Location {loc.location_id}
                    </td>
                    <td className="px-4 py-3 text-stone-600">{loc.country}</td>
                    <td className="px-4 py-3 text-right text-stone-900">
                      {formatMoney(loc.total_purchase_cost, loc.currency)}
                    </td>
                    <td className="px-4 py-3 text-right text-stone-900">
                      {formatMoney(loc.total_waste_cost, loc.currency)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span
                        className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                          loc.waste_ratio > 0.15
                            ? "bg-red-100 text-red-700"
                            : loc.waste_ratio > 0.05
                            ? "bg-amber-100 text-amber-700"
                            : "bg-green-100 text-green-700"
                        }`}
                      >
                        {formatPercent(loc.waste_ratio)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right text-stone-600">
                      {loc.stockout_events_count}
                    </td>
                    <td className="px-4 py-3 text-right text-stone-600">
                      {loc.price_alert_events_count}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>

        <p className="mt-3 text-xs text-stone-400">
          Amounts are shown in each location&rsquo;s own local currency and are never combined
          across COP and USD. Locations without an assigned country are not yet reported
          here — see LOCATION_REGISTRY in data/pipelines/pipeline.py.
        </p>
      </section>
    </div>
  );
}
