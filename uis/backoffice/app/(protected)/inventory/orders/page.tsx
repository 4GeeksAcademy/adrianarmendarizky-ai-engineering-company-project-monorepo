"use client";

// Order history for Operations -- read-only feed of every inbound and
// outbound order. No edit/delete actions, per the brief.

import { useEffect, useState } from "react";
import {
  getIngredients,
  getOrders,
  type Ingredient,
  type InventoryOrder,
} from "@/lib/inventory";

function formatQuantity(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mb-4 text-lg font-semibold text-stone-700 border-b border-stone-200 pb-2">
      {children}
    </h2>
  );
}

function TypeBadge({ type }: { type: "inbound" | "outbound" }) {
  const isInbound = type === "inbound";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold ${
        isInbound ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
      }`}
    >
      {isInbound ? "↓ Inbound" : "↑ Outbound"}
    </span>
  );
}

export default function OrdersHistoryPage() {
  const [orders, setOrders] = useState<InventoryOrder[]>([]);
  // Orders don't carry `unit` themselves -- joined in here from the
  // ingredients list purely for display ("50 kg" instead of just "50").
  const [unitsBySku, setUnitsBySku] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  async function loadOrders() {
    setLoading(true);
    setLoadError(null);
    try {
      const [ordersData, ingredientsData]: [InventoryOrder[], Ingredient[]] =
        await Promise.all([getOrders(), getIngredients()]);
      setOrders(ordersData);
      setUnitsBySku(
        Object.fromEntries(ingredientsData.map((i) => [i.sku, i.unit]))
      );
    } catch (err) {
      setLoadError(
        err instanceof Error ? err.message : "Could not load order history."
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadOrders();
  }, []);

  return (
    <div className="mx-auto max-w-5xl space-y-10">
      <div>
        <h1 className="text-2xl font-bold text-stone-900">Order history</h1>
        <p className="text-sm text-stone-500 mt-1">
          Every delivery, consumption, and waste log across every
          ingredient — read-only.
        </p>
      </div>

      {loadError && (
        <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
          <p>{loadError}</p>
          <button
            type="button"
            onClick={loadOrders}
            className="mt-2 rounded border border-red-200 bg-white px-2 py-1 text-xs font-semibold text-red-700 hover:bg-red-50"
          >
            Retry
          </button>
        </div>
      )}

      <section aria-labelledby="orders-heading">
        <SectionHeading>All orders</SectionHeading>

        <div className="overflow-x-auto rounded-xl border border-stone-200 bg-white shadow-sm">
          <table className="w-full text-sm">
            <thead className="bg-stone-50 text-xs uppercase tracking-widest text-stone-500">
              <tr>
                <th className="px-4 py-3 text-left">Type</th>
                <th className="px-4 py-3 text-left">Ingredient</th>
                <th className="px-4 py-3 text-left">Quantity</th>
                <th className="px-4 py-3 text-left">Detail</th>
                <th className="px-4 py-3 text-left">Logged by</th>
                <th className="px-4 py-3 text-left">Date</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {loading && (
                <tr>
                  <td colSpan={6} className="px-4 py-6 text-center text-stone-400">
                    Loading orders...
                  </td>
                </tr>
              )}

              {!loading && orders.length === 0 && !loadError && (
                <tr>
                  <td colSpan={6} className="px-4 py-6 text-center text-stone-400">
                    No orders yet.
                  </td>
                </tr>
              )}

              {!loading &&
                orders.map((order) => (
                  <tr key={`${order.type}-${order.id}`} className="hover:bg-stone-50">
                    <td className="px-4 py-3">
                      <TypeBadge type={order.type} />
                    </td>
                    <td className="px-4 py-3">
                      <p className="font-medium text-stone-900">
                        {order.ingredient_name}
                      </p>
                      <p className="text-xs text-stone-400">
                        {order.ingredient_sku}
                      </p>
                    </td>
                    <td className="px-4 py-3 text-stone-700">
                      {formatQuantity(order.quantity)}{" "}
                      {unitsBySku[order.ingredient_sku] ?? ""}
                    </td>
                    <td className="px-4 py-3 text-stone-600">
                      {order.type === "inbound"
                        ? order.supplier_name
                        : order.reason === "waste"
                        ? "Waste"
                        : "Consumption"}
                    </td>
                    <td className="px-4 py-3 text-stone-500 text-xs">
                      {order.user_uuid}
                    </td>
                    <td className="px-4 py-3 text-stone-400 text-xs">
                      {new Date(order.created_at).toLocaleString()}
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
