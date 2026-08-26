"use client";

// Outbound order form for Operations -- logs consumption or waste,
// which decreases an ingredient's stock. The two things the brief
// specifically calls out: the selected ingredient's current stock must
// show BEFORE the user enters a quantity, updating reactively as the
// selection changes; and a quantity above that stock gets a client-side
// warning before submit (advisory only -- the API is what actually
// enforces the rule, via the 400 this form also has to handle).

import { Suspense, useEffect, useMemo, useState, type FormEvent } from "react";
import { useSearchParams } from "next/navigation";
import {
  createOutboundOrder,
  getIngredients,
  type Ingredient,
} from "@/lib/inventory";

const LOCATION_IDS = Array.from({ length: 14 }, (_, i) => i + 1);

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

// See the same note in orders/inbound/page.tsx -- useSearchParams()
// needs a Suspense boundary around it for `next build` to succeed.
export default function OutboundOrderPage() {
  return (
    <Suspense fallback={null}>
      <OutboundOrderForm />
    </Suspense>
  );
}

function OutboundOrderForm() {
  const searchParams = useSearchParams();
  const preselectedId = searchParams.get("ingredient_id");

  const [ingredients, setIngredients] = useState<Ingredient[]>([]);
  const [loadingIngredients, setLoadingIngredients] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [ingredientId, setIngredientId] = useState(preselectedId ?? "");
  const [quantity, setQuantity] = useState("");
  const [reason, setReason] = useState<"consumption" | "waste">("consumption");
  const [locationId, setLocationId] = useState("1");

  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  // Kept separate from formError on purpose: the brief specifically
  // wants the API's insufficient-stock message inline near the
  // quantity field, not lumped in with other errors at the top.
  const [quantityError, setQuantityError] = useState<string | null>(null);
  const [confirmation, setConfirmation] = useState<string | null>(null);

  useEffect(() => {
    getIngredients()
      .then((data) => {
        setIngredients(data);
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

  // Derived from the already-fetched ingredient list -- current_stock
  // comes back on every ingredient from GET /inventory/products, so
  // this updates instantly on selection change with no extra request.
  const selectedIngredient = useMemo(
    () => ingredients.find((i) => String(i.id) === ingredientId) ?? null,
    [ingredients, ingredientId]
  );

  const parsedQuantity = Number(quantity);
  const exceedsStock =
    selectedIngredient !== null &&
    quantity !== "" &&
    !Number.isNaN(parsedQuantity) &&
    parsedQuantity > selectedIngredient.current_stock;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    setQuantityError(null);
    setConfirmation(null);

    if (!quantity || Number.isNaN(parsedQuantity) || parsedQuantity <= 0) {
      setFormError("Quantity must be a number greater than 0.");
      return;
    }

    setSubmitting(true);
    try {
      await createOutboundOrder({
        ingredient_id: Number(ingredientId),
        quantity: parsedQuantity,
        reason,
        location_id: Number(locationId),
      });
      setConfirmation("Logged.");
      setQuantity("");
      // Stock just changed on the server -- refresh so the displayed
      // current_stock (and the warning threshold) reflect it immediately.
      const refreshed = await getIngredients().catch(() => null);
      if (refreshed) setIngredients(refreshed);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Could not log this order.";
      // The backend's insufficient-stock 400 always mentions "stock" --
      // route that specific case to the inline field error; anything
      // else (network failure, 500, etc.) goes to the general banner.
      if (message.toLowerCase().includes("stock")) {
        setQuantityError(message);
      } else {
        setFormError(message);
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-stone-900">
          Log consumption or waste
        </h1>
        <p className="text-sm text-stone-500 mt-1">
          Registers an outbound order — decreases the selected ingredient&apos;s
          stock. Can&apos;t take stock below zero.
        </p>
      </div>

      <section aria-labelledby="outbound-heading">
        <SectionHeading>Order details</SectionHeading>

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

          {selectedIngredient && (
            <p className="rounded-lg bg-stone-50 px-3 py-2 text-sm text-stone-700">
              Available stock:{" "}
              <span className="font-semibold">
                {formatQuantity(selectedIngredient.current_stock)}{" "}
                {selectedIngredient.unit}
              </span>
            </p>
          )}

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
              onChange={(e) => {
                setQuantity(e.target.value);
                setQuantityError(null);
              }}
              className="w-full rounded-lg border border-stone-300 px-3 py-2 text-sm"
            />
            {exceedsStock && (
              <p className="mt-1 text-xs text-amber-700">
                This is more than the {formatQuantity(
                  selectedIngredient!.current_stock
                )}{" "}
                {selectedIngredient!.unit} currently available — the server
                will reject this.
              </p>
            )}
            {quantityError && (
              <p className="mt-1 text-xs text-red-700">{quantityError}</p>
            )}
          </label>

          <label className="block text-sm">
            <span className="mb-1 block font-medium text-stone-700">
              Reason
            </span>
            <select
              value={reason}
              onChange={(e) =>
                setReason(e.target.value as "consumption" | "waste")
              }
              className="w-full rounded-lg border border-stone-300 px-3 py-2 text-sm bg-white"
            >
              <option value="consumption">Consumption</option>
              <option value="waste">Waste</option>
            </select>
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
            {submitting ? "Logging..." : "Log order"}
          </button>
        </form>
      </section>
    </div>
  );
}
