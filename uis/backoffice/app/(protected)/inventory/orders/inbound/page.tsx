"use client";

// Inbound order form for Operations -- logs a delivery, which increases
// an ingredient's stock. Reachable directly, or pre-filled via a
// ?ingredient_id= link from the Ingredients page.

import { Suspense, useEffect, useState, type FormEvent } from "react";
import { useSearchParams } from "next/navigation";
import {
  createInboundOrder,
  getIngredients,
  type Ingredient,
} from "@/lib/inventory";

const LOCATION_IDS = Array.from({ length: 14 }, (_, i) => i + 1);

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mb-4 text-lg font-semibold text-stone-700 border-b border-stone-200 pb-2">
      {children}
    </h2>
  );
}

// useSearchParams() requires a Suspense boundary around whatever reads
// it, or `next build` fails with a missing-suspense-boundary error --
// this wrapper is what satisfies that; all the real logic is below.
export default function InboundOrderPage() {
  return (
    <Suspense fallback={null}>
      <InboundOrderForm />
    </Suspense>
  );
}

function InboundOrderForm() {
  const searchParams = useSearchParams();
  const preselectedId = searchParams.get("ingredient_id");

  const [ingredients, setIngredients] = useState<Ingredient[]>([]);
  const [loadingIngredients, setLoadingIngredients] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [ingredientId, setIngredientId] = useState(preselectedId ?? "");
  const [quantity, setQuantity] = useState("");
  const [supplierName, setSupplierName] = useState("");
  const [locationId, setLocationId] = useState("1");

  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [confirmation, setConfirmation] = useState<string | null>(null);

  useEffect(() => {
    getIngredients()
      .then((data) => {
        setIngredients(data);
        // If the link didn't specify one (or specified an id that no
        // longer exists), default to the first ingredient so the form
        // never opens with an invalid empty selection.
        if (!data.some((i) => String(i.id) === ingredientId) && data.length > 0) {
          setIngredientId(String(data[0].id));
        }
      })
      .catch((err) => {
        setLoadError(
          err instanceof Error ? err.message : "Could not load ingredients."
        );
      })
      .finally(() => setLoadingIngredients(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    setConfirmation(null);

    const parsedQuantity = Number(quantity);
    if (!quantity || Number.isNaN(parsedQuantity) || parsedQuantity <= 0) {
      setFormError("Quantity must be a number greater than 0.");
      return;
    }
    if (!supplierName.trim()) {
      setFormError("Supplier name is required.");
      return;
    }

    setSubmitting(true);
    try {
      await createInboundOrder({
        ingredient_id: Number(ingredientId),
        quantity: parsedQuantity,
        supplier_name: supplierName.trim(),
        location_id: Number(locationId),
      });
      setConfirmation("Delivery logged.");
      setQuantity("");
      setSupplierName("");
    } catch (err) {
      // Surfaces the API's own message on a 400/500 -- never a silent
      // failure, per the brief.
      setFormError(
        err instanceof Error ? err.message : "Could not log this delivery."
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-stone-900">Log a delivery</h1>
        <p className="text-sm text-stone-500 mt-1">
          Registers an inbound order — increases the selected ingredient&apos;s
          stock.
        </p>
      </div>

      <section aria-labelledby="inbound-heading">
        <SectionHeading>Delivery details</SectionHeading>

        {loadError && (
          <p className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
            {loadError}
          </p>
        )}

        {confirmation && (
          <p className="mb-4 rounded-lg bg-green-50 px-3 py-2 text-sm text-green-700">
            {confirmation}
          </p>
        )}

        <form
          onSubmit={handleSubmit}
          className="rounded-xl border border-stone-200 bg-white p-5 shadow-sm space-y-4"
        >
          {formError && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
              {formError}
            </p>
          )}

          <label className="block text-sm">
            <span className="mb-1 block font-medium text-stone-700">
              Ingredient
            </span>
            <select
              required
              disabled={loadingIngredients}
              value={ingredientId}
              onChange={(e) => setIngredientId(e.target.value)}
              className="w-full rounded-lg border border-stone-300 px-3 py-2 text-sm bg-white disabled:bg-stone-100"
            >
              {loadingIngredients && <option>Loading...</option>}
              {ingredients.map((ingredient) => (
                <option key={ingredient.id} value={ingredient.id}>
                  {ingredient.name} ({ingredient.sku})
                </option>
              ))}
            </select>
          </label>

          <label className="block text-sm">
            <span className="mb-1 block font-medium text-stone-700">
              Quantity
            </span>
            <input
              type="number"
              min="0.01"
              step="0.01"
              required
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              className="w-full rounded-lg border border-stone-300 px-3 py-2 text-sm"
            />
          </label>

          <label className="block text-sm">
            <span className="mb-1 block font-medium text-stone-700">
              Supplier name
            </span>
            <input
              type="text"
              required
              value={supplierName}
              onChange={(e) => setSupplierName(e.target.value)}
              className="w-full rounded-lg border border-stone-300 px-3 py-2 text-sm"
            />
          </label>

          <label className="block text-sm">
            <span className="mb-1 block font-medium text-stone-700">
              Location ID
            </span>
            <select
              value={locationId}
              onChange={(e) => setLocationId(e.target.value)}
              className="w-full rounded-lg border border-stone-300 px-3 py-2 text-sm bg-white"
            >
              {LOCATION_IDS.map((id) => (
                <option key={id} value={id}>
                  {id}
                </option>
              ))}
            </select>
          </label>

          <button
            type="submit"
            disabled={submitting || loadingIngredients}
            className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-semibold text-white hover:bg-stone-800 disabled:opacity-50"
          >
            {submitting ? "Logging..." : "Log delivery"}
          </button>
        </form>
      </section>
    </div>
  );
}
