// lib/inventory.ts
//
// Every call to /inventory/* lives here — pages import these functions,
// never fetch() or authFetch() directly. Mirrors the domain-module
// pattern the brief asks for, built on top of the existing authFetch()
// in lib/api.ts (token attachment + 401 handling already happens there).
//
// Naming note: CONTEXT.md calls this entity "Ingredient", but the
// backend's actual endpoint paths are /inventory/products/... (that's
// what's specified in CONTEXT-brasaland.md's own API Router table, not
// a mismatch). The URL segment stays "products" to match the real API;
// every user-facing label in the pages that use this module says
// "Ingredient" instead, per CONTEXT.md's domain vocabulary.

import { authFetch } from "./api";
import { track } from "./telemetry";

export type Ingredient = {
  id: number;
  name: string;
  sku: string;
  unit: string;
  category: string;
  country: string;
  current_stock: number;
  minimum_stock: number | null;
};

export type InventoryOrder = {
  type: "inbound" | "outbound";
  id: number;
  ingredient_id: number;
  ingredient_name: string;
  ingredient_sku: string;
  quantity: number;
  location_id: number;
  created_at: string;
  user_uuid: string;
  supplier_name?: string | null;
  reason?: string | null;
};

export type CreateInboundOrderInput = {
  ingredient_id: number;
  quantity: number;
  supplier_name: string;
  location_id: number;
  unit_cost?: number | null;
};

export type CreateOutboundOrderInput = {
  ingredient_id: number;
  quantity: number;
  reason: "consumption" | "waste";
  location_id: number;
  waste_reason?: "expired" | "kitchen_error" | "theft_suspected" | null;
};

export type IngredientEntry = {
  id: number;
  ingredient_id: number;
  quantity: number;
  supplier_name: string;
  location_id: number;
  created_at: string;
  user_uuid: string;
  unit_cost: number | null;
  historical_avg_cost: number | null;
  product_category: string;
  unit: string;
};

export type IngredientExit = {
  id: number;
  ingredient_id: number;
  quantity: number;
  reason: string;
  location_id: number;
  created_at: string;
  user_uuid: string;
  waste_reason: string | null;
  product_category: string;
  unit: string;
  current_stock: number;
  minimum_stock: number | null;
  unit_cost: number | null;
};

// country/currency are null on every inventory event below, on
// purpose: there is no reliable way to derive a location's country
// from inventory's location_id today (see telemetry-plan.md §2). This
// is not a bug to fix here -- filling in a guessed value would be
// worse than an honest null.
const LOCATION_COUNTRY_UNRESOLVED = null;
const LOCATION_CURRENCY_UNRESOLVED = null;

// A price move beyond this magnitude (either direction) is what
// CONTEXT-brasaland.md's example threshold calls "abnormal" -- see
// ingredient_price_variance_detected in the plan.
const PRICE_VARIANCE_THRESHOLD_PCT = 10;

// Pulls the API's own error message out of a failed response, falling
// back to a generic one -- same convention as lib/api.ts's other
// functions (updateProfile, changePassword, etc.), so a 400 "Insufficient
// stock for ingredient 'X'..." reaches the screen verbatim instead of
// being swallowed into a generic "something went wrong".
async function readErrorMessage(res: Response, fallback: string): Promise<string> {
  const body = await res.json().catch(() => null);
  if (body && typeof body.detail === "string") return body.detail;
  return `${fallback} (${res.status})`;
}

export async function getIngredients(): Promise<Ingredient[]> {
  const res = await authFetch("/inventory/products");
  if (!res.ok) {
    throw new Error(await readErrorMessage(res, "Could not load ingredients"));
  }
  return res.json();
}

// Mandatory telemetry event (inbound_order_created) plus the
// identified opportunity ingredient_price_variance_detected, both
// fired from here rather than the calling page -- same "instrument at
// the service layer, not scattered across components" pattern as the
// auth functions above.
export async function createInboundOrder(
  input: CreateInboundOrderInput
): Promise<IngredientEntry> {
  const requestId = crypto.randomUUID();
  const res = await authFetch("/inventory/orders/inbound", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) {
    throw new Error(await readErrorMessage(res, "Could not log this delivery"));
  }
  const entry: IngredientEntry = await res.json();

  track(
    "inbound_order_created",
    {
      location_id: entry.location_id,
      country: LOCATION_COUNTRY_UNRESOLVED,
      product_id: entry.ingredient_id,
      product_category: entry.product_category,
      quantity: entry.quantity,
      unit: entry.unit,
      currency: LOCATION_CURRENCY_UNRESOLVED,
      supplier_name: entry.supplier_name,
      // Was already computed server-side (used two lines below for the
      // price-variance check) but never actually captured on this event
      // itself -- Purchase Cost per Location in the business performance
      // pipeline needs it. See PIPELINE_DESIGN.md, "Schema prerequisite #1".
      unit_cost: entry.unit_cost,
    },
    requestId
  );

  if (
    entry.unit_cost != null &&
    entry.historical_avg_cost != null &&
    entry.historical_avg_cost !== 0
  ) {
    const variancePct =
      ((entry.unit_cost - entry.historical_avg_cost) / entry.historical_avg_cost) * 100;
    if (Math.abs(variancePct) > PRICE_VARIANCE_THRESHOLD_PCT) {
      track(
        "ingredient_price_variance_detected",
        {
          location_id: entry.location_id,
          country: LOCATION_COUNTRY_UNRESOLVED,
          product_id: entry.ingredient_id,
          product_category: entry.product_category,
          supplier_name: entry.supplier_name,
          unit_cost: entry.unit_cost,
          historical_avg_cost: entry.historical_avg_cost,
          variance_pct: Math.round(variancePct * 100) / 100,
          currency: LOCATION_CURRENCY_UNRESOLVED,
        },
        requestId
      );
    }
  }

  return entry;
}

// Mandatory events outbound_order_created / stock_waste_registered /
// stock_threshold_triggered all fire from here. Which of the first two
// fires depends on `reason`; the third fires additionally, only when
// this exit pushed stock below a configured minimum.
export async function createOutboundOrder(
  input: CreateOutboundOrderInput
): Promise<IngredientExit> {
  const requestId = crypto.randomUUID();
  const res = await authFetch("/inventory/orders/outbound", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) {
    // This is the path that carries the backend's insufficient-stock
    // HTTP 400 ("Insufficient stock for ingredient 'X'. Available: Y,
    // requested: Z.") -- readErrorMessage surfaces that exact text.
    throw new Error(await readErrorMessage(res, "Could not log this order"));
  }
  const exit_: IngredientExit = await res.json();

  const baseProperties = {
    location_id: exit_.location_id,
    country: LOCATION_COUNTRY_UNRESOLVED,
    product_id: exit_.ingredient_id,
    product_category: exit_.product_category,
    quantity: exit_.quantity,
    unit: exit_.unit,
  };

  if (exit_.reason === "waste") {
    track(
      "stock_waste_registered",
      {
        ...baseProperties,
        waste_reason: exit_.waste_reason,
        // New field -- didn't exist anywhere in the waste path before.
        // Backend fills it in from the ingredient's most recent purchase
        // price (routes/inventory.py's create_exit); Waste Cost per
        // Location needs it. See PIPELINE_DESIGN.md, "Schema prerequisite #1".
        unit_cost: exit_.unit_cost,
      },
      requestId
    );
  } else {
    track("outbound_order_created", baseProperties, requestId);
  }

  if (exit_.minimum_stock != null && exit_.current_stock < exit_.minimum_stock) {
    track(
      "stock_threshold_triggered",
      {
        location_id: exit_.location_id,
        country: LOCATION_COUNTRY_UNRESOLVED,
        product_id: exit_.ingredient_id,
        product_category: exit_.product_category,
        current_stock: exit_.current_stock,
        minimum_stock: exit_.minimum_stock,
      },
      requestId
    );
  }

  return exit_;
}

export async function getOrders(): Promise<InventoryOrder[]> {
  const res = await authFetch("/inventory/orders");
  if (!res.ok) {
    throw new Error(await readErrorMessage(res, "Could not load order history"));
  }
  return res.json();
}
