"use client";

// Ingredients page for Operations. Read-only list of every ingredient
// with its live current_stock, color-coded so a supervisor can see at
// a glance what's running low -- exactly what the brief asks for
// ("Color-code it — I want to see at a glance what is low").
//
// No "create ingredient" form here: the brief's checklist for this page
// only asks for the list plus links out to the inbound/outbound forms.
// POST /inventory/products exists on the backend if that's ever wanted
// later, it's just not part of this milestone's UI.

import Link from "next/link";
import { useEffect, useState } from "react";
import { getIngredients, type Ingredient } from "@/lib/inventory";

function formatLabel(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function formatQuantity(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

// Stock-level thresholds are arbitrary and documented here on purpose,
// per the brief ("define your own thresholds — document them"). A real
// system would set these per ingredient (a reorder point from
// Operations), not one flat number across every category -- this is a
// simple stand-in until that data exists.
const LOW_STOCK_THRESHOLD = 10;

function StockBadge({ stock, unit }: { stock: number; unit: string }) {
  let colorClasses = "bg-green-100 text-green-700";
  let label = "Healthy";

  if (stock <= 0) {
    colorClasses = "bg-red-100 text-red-700";
    label = "Out of stock";
  } else if (stock < LOW_STOCK_THRESHOLD) {
    colorClasses = "bg-amber-100 text-amber-700";
    label = "Low";
  }

  return (
    <div className="flex items-center gap-2">
      <span
        className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${colorClasses}`}
      >
        {label}
      </span>
      <span className="text-sm text-stone-700">
        {formatQuantity(stock)} {unit}
      </span>
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

export default function IngredientsPage() {
  const [ingredients, setIngredients] = useState<Ingredient[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  async function loadIngredients() {
    setLoading(true);
    setLoadError(null);
    try {
      const data = await getIngredients();
      setIngredients(data);
    } catch (err) {
      setLoadError(
        err instanceof Error ? err.message : "Could not load ingredients."
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadIngredients();
  }, []);

  const lowStockCount = ingredients.filter(
    (i) => i.current_stock < LOW_STOCK_THRESHOLD
  ).length;

  return (
    <div className="mx-auto max-w-5xl space-y-10">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-stone-900">Ingredients</h1>
          <p className="text-sm text-stone-500 mt-1">
            Live stock across every location — computed from every delivery
            and consumption/waste log, never edited directly.
          </p>
        </div>
        <Link
          href="/inventory/orders"
          className="shrink-0 rounded-lg border border-stone-300 bg-white px-4 py-2 text-sm font-semibold text-stone-700 hover:bg-stone-50"
        >
          View order history
        </Link>
      </div>

      {!loading && lowStockCount > 0 && (
        <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">
          {lowStockCount} ingredient{lowStockCount === 1 ? "" : "s"} running
          low.
        </p>
      )}

      {loadError && (
        <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
          <p>{loadError}</p>
          <button
            type="button"
            onClick={loadIngredients}
            className="mt-2 rounded border border-red-200 bg-white px-2 py-1 text-xs font-semibold text-red-700 hover:bg-red-50"
          >
            Retry
          </button>
        </div>
      )}

      <section aria-labelledby="ingredients-heading">
        <SectionHeading>All ingredients</SectionHeading>

        <div className="overflow-x-auto rounded-xl border border-stone-200 bg-white shadow-sm">
          <table className="w-full text-sm">
            <thead className="bg-stone-50 text-xs uppercase tracking-widest text-stone-500">
              <tr>
                <th className="px-4 py-3 text-left">Ingredient</th>
                <th className="px-4 py-3 text-left">SKU</th>
                <th className="px-4 py-3 text-left">Category</th>
                <th className="px-4 py-3 text-left">Country</th>
                <th className="px-4 py-3 text-left">Current stock</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {loading && (
                <tr>
                  <td colSpan={6} className="px-4 py-6 text-center text-stone-400">
                    Loading ingredients...
                  </td>
                </tr>
              )}

              {!loading && ingredients.length === 0 && !loadError && (
                <tr>
                  <td colSpan={6} className="px-4 py-6 text-center text-stone-400">
                    No ingredients found.
                  </td>
                </tr>
              )}

              {!loading &&
                ingredients.map((ingredient) => (
                  <tr key={ingredient.id} className="hover:bg-stone-50">
                    <td className="px-4 py-3 font-medium text-stone-900">
                      {ingredient.name}
                    </td>
                    <td className="px-4 py-3 text-stone-500">{ingredient.sku}</td>
                    <td className="px-4 py-3 text-stone-600">
                      {formatLabel(ingredient.category)}
                    </td>
                    <td className="px-4 py-3 text-stone-600">
                      {ingredient.country}
                    </td>
                    <td className="px-4 py-3">
                      <StockBadge
                        stock={ingredient.current_stock}
                        unit={ingredient.unit}
                      />
                    </td>
                    <td className="px-4 py-3 text-right space-x-3 whitespace-nowrap">
                      <Link
                        href={`/inventory/orders/inbound?ingredient_id=${ingredient.id}`}
                        className="text-xs font-semibold text-stone-600 hover:underline"
                      >
                        Log delivery
                      </Link>
                      <Link
                        href={`/inventory/orders/outbound?ingredient_id=${ingredient.id}`}
                        className="text-xs font-semibold text-stone-600 hover:underline"
                      >
                        Log consumption/waste
                      </Link>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}