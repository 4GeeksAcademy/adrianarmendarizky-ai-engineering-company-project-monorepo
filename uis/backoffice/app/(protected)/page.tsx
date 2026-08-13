// This page imports the Milestone 2 business-logic layer directly from its
// original location in the monorepo (src/) — never copied, always imported.
// It runs the logic against the sample data and renders the results on screen.

// Imported directly from the Milestone 2 logic layer — not copied.
// Relative paths resolve correctly when turbopack.root is the monorepo root.
import {
  sampleLocations,
  sampleSales,
  sampleMenuItems,
} from "../../../../src/types/models";
import {
  rankLocationsByPerformance,
  calculateCountryComparison,
  calculateAverageTicket,
  countSalesByPaymentMethod,
} from "../../../../src/utils/transformations";
import { filterActiveLocations } from "../../../../src/utils/collections";

// Run the Milestone 2 functions at render time (server component).
const ranked = rankLocationsByPerformance(
  sampleLocations,
  sampleSales,
  [],
  sampleMenuItems
);

const countryComparison = calculateCountryComparison(
  sampleSales,
  sampleLocations,
  sampleMenuItems
);

const avgTicketUSD = calculateAverageTicket(sampleSales, "USD");
const avgTicketCOP = calculateAverageTicket(sampleSales, "COP");
const paymentCounts = countSalesByPaymentMethod(sampleSales);
const activeLocations = filterActiveLocations(sampleLocations);

// ---- Sub-components ----

function StatCard({
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

// ---- Page ----

export default function BackofficeDashboard() {
  return (
    <div className="mx-auto max-w-5xl space-y-10">
      <div>
        <h1 className="text-2xl font-bold text-stone-900">
          Operations Overview
        </h1>
        <p className="text-sm text-stone-500 mt-1">
          Powered by the Milestone 2 TypeScript business-logic layer —
          imported from{" "}
          <code className="rounded bg-stone-200 px-1 text-xs">src/</code>.
          Sample data: {sampleLocations.length} locations,{" "}
          {sampleSales.length} sales, {sampleMenuItems.length} menu items.
        </p>
      </div>

      {/* KPI cards */}
      <section aria-labelledby="kpi-heading">
        <SectionHeading>Key metrics</SectionHeading>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard
            label="Active locations"
            value={String(activeLocations.length)}
            sub="out of all locations"
          />
          <StatCard
            label="Avg ticket (USD)"
            value={`$${avgTicketUSD}`}
            sub={`COP ${avgTicketCOP.toLocaleString()}`}
          />
          <StatCard
            label="Total sales"
            value={String(sampleSales.length)}
            sub="in sample dataset"
          />
          <StatCard
            label="Menu items"
            value={String(sampleMenuItems.length)}
            sub="in sample dataset"
          />
        </div>
      </section>

      {/* Location performance ranking */}
      <section aria-labelledby="ranking-heading">
        <SectionHeading>Location performance ranking</SectionHeading>
        <div className="overflow-x-auto rounded-xl border border-stone-200 bg-white shadow-sm">
          <table className="w-full text-sm">
            <thead className="bg-stone-50 text-xs uppercase tracking-widest text-stone-500">
              <tr>
                <th className="px-4 py-3 text-left">Rank</th>
                <th className="px-4 py-3 text-left">Location</th>
                <th className="px-4 py-3 text-left">City</th>
                <th className="px-4 py-3 text-left">Country</th>
                <th className="px-4 py-3 text-left">Capacity</th>
                <th className="px-4 py-3 text-right">Score / 100</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {ranked.map(({ location, score }, i) => (
                <tr key={location.id} className="hover:bg-stone-50">
                  <td className="px-4 py-3 font-semibold text-stone-400">
                    #{i + 1}
                  </td>
                  <td className="px-4 py-3 font-medium text-stone-900">
                    {location.name}
                  </td>
                  <td className="px-4 py-3 text-stone-600">{location.city}</td>
                  <td className="px-4 py-3 text-stone-600">
                    {location.country}
                  </td>
                  <td className="px-4 py-3 text-stone-600">
                    {location.seatingCapacity} seats
                  </td>
                  <td className="px-4 py-3 text-right">
                    <span
                      className={`font-bold ${
                        score >= 50
                          ? "text-green-600"
                          : score >= 25
                          ? "text-amber-600"
                          : "text-red-600"
                      }`}
                    >
                      {score}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Country comparison */}
      <section aria-labelledby="country-heading">
        <SectionHeading>Country comparison</SectionHeading>
        <div className="grid gap-6 sm:grid-cols-2">
          {(["Colombia", "USA"] as const).map((country) => {
            const metrics = countryComparison[country];
            return (
              <div
                key={country}
                className="rounded-xl border border-stone-200 bg-white p-5 shadow-sm"
              >
                <p className="mb-3 font-semibold text-stone-900">{country}</p>
                <dl className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <dt className="text-stone-500">Locations</dt>
                    <dd className="font-medium">{metrics.totalLocations}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-stone-500">Total revenue (USD)</dt>
                    <dd className="font-medium">
                      ${metrics.totalRevenue.USD.toLocaleString()}
                    </dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-stone-500">Total revenue (COP)</dt>
                    <dd className="font-medium">
                      {metrics.totalRevenue.COP.toLocaleString()}
                    </dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-stone-500">Avg revenue / location (USD)</dt>
                    <dd className="font-medium">
                      ${metrics.averageRevenuePerLocation.USD.toLocaleString()}
                    </dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-stone-500">Total sales</dt>
                    <dd className="font-medium">{metrics.totalSales}</dd>
                  </div>
                </dl>
              </div>
            );
          })}
        </div>
      </section>

      {/* Payment method breakdown */}
      <section aria-labelledby="payment-heading">
        <SectionHeading>Sales by payment method</SectionHeading>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Object.entries(paymentCounts).map(([method, count]) => (
            <StatCard
              key={method}
              label={method}
              value={String(count)}
              sub="transactions"
            />
          ))}
        </div>
      </section>
    </div>
  );
}
