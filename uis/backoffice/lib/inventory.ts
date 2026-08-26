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

export type Ingredient = {
  id: number;
  name: string;
  sku: string;
  unit: string;
  category: string;
  country: string;
  current_stock: number;
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
};

export type CreateOutboundOrderInput = {
  ingredient_id: number;
  quantity: number;
  reason: "consumption" | "waste";
  location_id: number;
};

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

export async function createInboundOrder(
  input: CreateInboundOrderInput
): Promise<void> {
  const res = await authFetch("/inventory/orders/inbound", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) {
    throw new Error(await readErrorMessage(res, "Could not log this delivery"));
  }
}

export async function createOutboundOrder(
  input: CreateOutboundOrderInput
): Promise<void> {
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
}

export async function getOrders(): Promise<InventoryOrder[]> {
  const res = await authFetch("/inventory/orders");
  if (!res.ok) {
    throw new Error(await readErrorMessage(res, "Could not load order history"));
  }
  return res.json();
}
