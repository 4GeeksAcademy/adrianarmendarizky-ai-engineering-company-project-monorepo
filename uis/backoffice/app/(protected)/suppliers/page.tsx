"use client";

// Supplier Directory page for Lucía (Procurement). Talks to the FastAPI
// backend in services/api. This has to be a client component (not a
// server component like the dashboard page) because filters, the
// add-supplier form, and rate/status updates all need to update the
// screen without a full page reload.

import { useEffect, useState, type FormEvent } from "react";
import { authFetch } from "@/lib/api";

// ---- Types (mirror services/api/models.py) ----

type CountryValue = "Colombia" | "USA";
type CurrencyValue = "COP" | "USD";
type StatusValue = "active" | "suspended";
type CategoryValue =
  | "carne"
  | "verduras_y_hortalizas"
  | "salsas_y_condimentos"
  | "bebidas"
  | "packaging"
  | "productos_limpieza"
  | "lacteos"
  | "carbon_y_combustible";

type Supplier = {
  id: number;
  name: string;
  country: CountryValue;
  categories: CategoryValue[];
  rate_per_unit: number;
  currency: CurrencyValue;
  status: StatusValue;
  contact_email?: string | null;
  notes?: string | null;
  updated_at: string;
};

const ALL_CATEGORIES: CategoryValue[] = [
  "carne",
  "verduras_y_hortalizas",
  "salsas_y_condimentos",
  "bebidas",
  "packaging",
  "productos_limpieza",
  "lacteos",
  "carbon_y_combustible",
];

// Same mapping the backend enforces -- used here so the create form
// never even offers an invalid country/currency combination.
const COUNTRY_CURRENCY: Record<CountryValue, CurrencyValue> = {
  Colombia: "COP",
  USA: "USD",
};

function formatLabel(value: string): string {
  return value
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function formatRate(rate: number, currency: CurrencyValue): string {
  return currency === "USD"
    ? `$${rate.toFixed(2)}`
    : `${rate.toLocaleString("es-CO")} COP`;
}

// ---- Small pieces, styled to match the dashboard page ----

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mb-4 text-lg font-semibold text-stone-700 border-b border-stone-200 pb-2">
      {children}
    </h2>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-white p-5 shadow-sm border border-stone-200">
      <p className="text-xs font-semibold uppercase tracking-widest text-stone-500 mb-1">
        {label}
      </p>
      <p className="text-2xl font-bold text-stone-900">{value}</p>
    </div>
  );
}

function StatusBadge({ status }: { status: StatusValue }) {
  const isActive = status === "active";
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${
        isActive ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
      }`}
    >
      {isActive ? "Active" : "Suspended"}
    </span>
  );
}

// ---- Add-supplier form state ----

type FormState = {
  name: string;
  country: CountryValue;
  categories: CategoryValue[];
  rate_per_unit: string;
  contact_email: string;
  notes: string;
};

const EMPTY_FORM: FormState = {
  name: "",
  country: "Colombia",
  categories: [],
  rate_per_unit: "",
  contact_email: "",
  notes: "",
};

// ---- Page ----

export default function SuppliersPage() {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [countryFilter, setCountryFilter] = useState<CountryValue | "">("");
  const [categoryFilter, setCategoryFilter] = useState<CategoryValue | "">("");

  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [editingRateId, setEditingRateId] = useState<number | null>(null);
  const [rateDraft, setRateDraft] = useState("");
  const [rowBusyId, setRowBusyId] = useState<number | null>(null);
  const [rowErrors, setRowErrors] = useState<Record<number, string>>({});

  async function loadSuppliers() {
    setLoading(true);
    setLoadError(null);
    try {
      const params = new URLSearchParams();
      if (countryFilter) params.set("country", countryFilter);
      if (categoryFilter) params.set("category", categoryFilter);
      const res = await authFetch(`/suppliers?${params.toString()}`);
      if (!res.ok) throw new Error(`API returned ${res.status}`);
      const data: Supplier[] = await res.json();
      setSuppliers(data);
    } catch (err) {
      setLoadError(
        err instanceof Error
          ? `Could not load suppliers: ${err.message}`
          : "Could not load suppliers."
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadSuppliers();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [countryFilter, categoryFilter]);

  function toggleFormCategory(cat: CategoryValue) {
    setForm((prev) => ({
      ...prev,
      categories: prev.categories.includes(cat)
        ? prev.categories.filter((c) => c !== cat)
        : [...prev.categories, cat],
    }));
  }

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setFormError(null);

    // Client-side checks first, so obvious mistakes never hit the network.
    if (!form.name.trim()) {
      setFormError("Name is required.");
      return;
    }
    if (form.categories.length === 0) {
      setFormError("Pick at least one category.");
      return;
    }
    const rate = Number(form.rate_per_unit);
    if (!form.rate_per_unit || Number.isNaN(rate) || rate <= 0) {
      setFormError("Rate must be a number greater than 0.");
      return;
    }

    setSubmitting(true);
    try {
      const res = await authFetch(`/suppliers`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: form.name.trim(),
          country: form.country,
          currency: COUNTRY_CURRENCY[form.country],
          categories: form.categories,
          rate_per_unit: rate,
          status: "active",
          contact_email: form.contact_email.trim() || undefined,
          notes: form.notes.trim() || undefined,
        }),
      });

      if (!res.ok) {
        // Surface whatever the API's 422 validator said, so the person
        // sees the real reason instead of a generic error.
        const body = await res.json().catch(() => null);
        const detail =
          body && typeof body.detail === "string"
            ? body.detail
            : "The server rejected this supplier — check the fields.";
        throw new Error(detail);
      }

      setForm(EMPTY_FORM);
      setShowForm(false);
      await loadSuppliers();
    } catch (err) {
      setFormError(
        err instanceof Error ? err.message : "Could not save supplier."
      );
    } finally {
      setSubmitting(false);
    }
  }

  function startRateEdit(supplier: Supplier) {
    setEditingRateId(supplier.id);
    setRateDraft(String(supplier.rate_per_unit));
  }

  async function saveRate(id: number) {
    const rate = Number(rateDraft);
    if (!rateDraft || Number.isNaN(rate) || rate <= 0) return;

    setRowBusyId(id);
    setRowErrors((prev) => ({ ...prev, [id]: "" }));
    try {
      const res = await authFetch(`/suppliers/${id}/rate`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rate_per_unit: rate }),
      });
      if (!res.ok) throw new Error(`API returned ${res.status}`);
      const updated: Supplier = await res.json();
      setSuppliers((prev) => prev.map((s) => (s.id === id ? updated : s)));
      setEditingRateId(null);
    } catch (err) {
      setRowErrors((prev) => ({
        ...prev,
        [id]: err instanceof Error ? err.message : "Could not save rate. Try again.",
      }));
    } finally {
      setRowBusyId(null);
    }
  }

  async function toggleStatus(supplier: Supplier) {
    const nextStatus: StatusValue =
      supplier.status === "active" ? "suspended" : "active";
    setRowErrors((prev) => ({ ...prev, [supplier.id]: "" }));
    setRowBusyId(supplier.id);
    try {
      const res = await authFetch(
        `/suppliers/${supplier.id}/status`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status: nextStatus }),
        }
      );
      if (!res.ok) throw new Error(`API returned ${res.status}`);
      const updated: Supplier = await res.json();
      setSuppliers((prev) =>
        prev.map((s) => (s.id === supplier.id ? updated : s))
      );
    } catch (err) {
      setRowErrors((prev) => ({
        ...prev,
        [supplier.id]: err instanceof Error ? err.message : "Could not update status. Try again.",
      }));
    } finally {
      setRowBusyId(null);
    }
  }

  const activeCount = suppliers.filter((s) => s.status === "active").length;
  const suspendedCount = suppliers.length - activeCount;

  return (
    <div className="mx-auto max-w-5xl space-y-10">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-stone-900">
            Supplier Directory
          </h1>
          <p className="text-sm text-stone-500 mt-1">
            The single source of truth for supplier rates and status —
            replaces the shared spreadsheet.
          </p>
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="shrink-0 rounded-lg bg-stone-900 px-4 py-2 text-sm font-semibold text-white hover:bg-stone-800"
        >
          {showForm ? "Cancel" : "Add supplier"}
        </button>
      </div>

      {/* KPI cards */}
      <section aria-labelledby="kpi-heading">
        <SectionHeading>At a glance</SectionHeading>
        <div className="grid gap-4 sm:grid-cols-3">
          <StatCard label="Total suppliers" value={String(suppliers.length)} />
          <StatCard label="Active" value={String(activeCount)} />
          <StatCard label="Suspended" value={String(suspendedCount)} />
        </div>
      </section>

      {/* Add-supplier form */}
      {showForm && (
        <section aria-labelledby="add-heading">
          <SectionHeading>Register a new supplier</SectionHeading>
          <form
            onSubmit={handleCreate}
            className="rounded-xl border border-stone-200 bg-white p-5 shadow-sm space-y-4"
          >
            {formError && (
              <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
                {formError}
              </p>
            )}

            <div className="grid gap-4 sm:grid-cols-2">
              <label className="block text-sm">
                <span className="mb-1 block font-medium text-stone-700">
                  Name
                </span>
                <input
                  type="text"
                  required
                  value={form.name}
                  onChange={(e) =>
                    setForm((p) => ({ ...p, name: e.target.value }))
                  }
                  className="w-full rounded-lg border border-stone-300 px-3 py-2 text-sm"
                />
              </label>

              <label className="block text-sm">
                <span className="mb-1 block font-medium text-stone-700">
                  Country
                </span>
                <select
                  value={form.country}
                  onChange={(e) =>
                    setForm((p) => ({
                      ...p,
                      country: e.target.value as CountryValue,
                    }))
                  }
                  className="w-full rounded-lg border border-stone-300 px-3 py-2 text-sm"
                >
                  <option value="Colombia">Colombia (COP)</option>
                  <option value="USA">USA (USD)</option>
                </select>
              </label>

              <label className="block text-sm">
                <span className="mb-1 block font-medium text-stone-700">
                  Rate per unit
                </span>
                <input
                  type="number"
                  min="0.01"
                  step="0.01"
                  required
                  value={form.rate_per_unit}
                  onChange={(e) =>
                    setForm((p) => ({ ...p, rate_per_unit: e.target.value }))
                  }
                  className="w-full rounded-lg border border-stone-300 px-3 py-2 text-sm"
                />
              </label>

              <label className="block text-sm">
                <span className="mb-1 block font-medium text-stone-700">
                  Contact email (optional)
                </span>
                <input
                  type="email"
                  value={form.contact_email}
                  onChange={(e) =>
                    setForm((p) => ({ ...p, contact_email: e.target.value }))
                  }
                  className="w-full rounded-lg border border-stone-300 px-3 py-2 text-sm"
                />
              </label>
            </div>

            <div>
              <span className="mb-2 block text-sm font-medium text-stone-700">
                Categories
              </span>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                {ALL_CATEGORIES.map((cat) => (
                  <label
                    key={cat}
                    className="flex items-center gap-2 text-sm text-stone-600"
                  >
                    <input
                      type="checkbox"
                      checked={form.categories.includes(cat)}
                      onChange={() => toggleFormCategory(cat)}
                    />
                    {formatLabel(cat)}
                  </label>
                ))}
              </div>
            </div>

            <label className="block text-sm">
              <span className="mb-1 block font-medium text-stone-700">
                Notes (optional)
              </span>
              <textarea
                value={form.notes}
                onChange={(e) =>
                  setForm((p) => ({ ...p, notes: e.target.value }))
                }
                rows={2}
                className="w-full rounded-lg border border-stone-300 px-3 py-2 text-sm"
              />
            </label>

            <button
              type="submit"
              disabled={submitting}
              className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-semibold text-white hover:bg-stone-800 disabled:opacity-50"
            >
              {submitting ? "Saving..." : "Save supplier"}
            </button>
          </form>
        </section>
      )}

      {/* Filters + table */}
      <section aria-labelledby="directory-heading">
        <SectionHeading>All suppliers</SectionHeading>

        <div className="mb-4 flex flex-wrap gap-3">
          <select
            value={countryFilter}
            onChange={(e) =>
              setCountryFilter(e.target.value as CountryValue | "")
            }
            className="rounded-lg border border-stone-300 px-3 py-2 text-sm bg-white"
          >
            <option value="">All countries</option>
            <option value="Colombia">Colombia</option>
            <option value="USA">USA</option>
          </select>

          <select
            value={categoryFilter}
            onChange={(e) =>
              setCategoryFilter(e.target.value as CategoryValue | "")
            }
            className="rounded-lg border border-stone-300 px-3 py-2 text-sm bg-white"
          >
            <option value="">All categories</option>
            {ALL_CATEGORIES.map((cat) => (
              <option key={cat} value={cat}>
                {formatLabel(cat)}
              </option>
            ))}
          </select>
        </div>

        {loadError && (
          <div className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
            <p>{loadError}</p>
            <button
              type="button"
              onClick={loadSuppliers}
              className="mt-2 rounded border border-red-200 bg-white px-2 py-1 text-xs font-semibold text-red-700 hover:bg-red-50"
            >
              Retry
            </button>
          </div>
        )}

        <div className="overflow-x-auto rounded-xl border border-stone-200 bg-white shadow-sm">
          <table className="w-full text-sm">
            <thead className="bg-stone-50 text-xs uppercase tracking-widest text-stone-500">
              <tr>
                <th className="px-4 py-3 text-left">Name</th>
                <th className="px-4 py-3 text-left">Country</th>
                <th className="px-4 py-3 text-left">Categories</th>
                <th className="px-4 py-3 text-left">Contact</th>
                <th className="px-4 py-3 text-left">Rate</th>
                <th className="px-4 py-3 text-left">Status</th>
                <th className="px-4 py-3 text-left">Last updated</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {loading && (
                <tr>
                  <td colSpan={8} className="px-4 py-6 text-center text-stone-400">
                    Loading suppliers...
                  </td>
                </tr>
              )}

              {!loading && suppliers.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-6 text-center text-stone-400">
                    No suppliers match these filters.
                  </td>
                </tr>
              )}

              {!loading &&
                suppliers.map((s) => (
                  <tr key={s.id} className="hover:bg-stone-50">
                    <td className="px-4 py-3">
                      <p className="font-medium text-stone-900">{s.name}</p>
                      {s.notes && (
                        <p
                          className="text-xs text-stone-400 truncate max-w-xs"
                          title={s.notes}
                        >
                          {s.notes}
                        </p>
                      )}
                    </td>
                    <td className="px-4 py-3 text-stone-600">{s.country}</td>
                    <td className="px-4 py-3 text-stone-600">
                      {s.categories.map(formatLabel).join(", ")}
                    </td>
                    <td className="px-4 py-3 text-stone-500">
                      {s.contact_email || "—"}
                    </td>
                    <td className="px-4 py-3 text-stone-600">
                      {editingRateId === s.id ? (
                        <div className="flex items-center gap-2">
                          <input
                            type="number"
                            min="0.01"
                            step="0.01"
                            value={rateDraft}
                            onChange={(e) => setRateDraft(e.target.value)}
                            className="w-24 rounded border border-stone-300 px-2 py-1 text-sm"
                            autoFocus
                          />
                          <button
                            onClick={() => saveRate(s.id)}
                            disabled={rowBusyId === s.id}
                            className="text-xs font-semibold text-green-700 hover:underline disabled:opacity-50"
                          >
                            Save
                          </button>
                          <button
                            onClick={() => setEditingRateId(null)}
                            className="text-xs text-stone-400 hover:underline"
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        formatRate(s.rate_per_unit, s.currency)
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={s.status} />
                    </td>
                    <td className="px-4 py-3 text-stone-400 text-xs">
                      {new Date(s.updated_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-right space-x-3 whitespace-nowrap">
                      {editingRateId !== s.id && (
                        <button
                          onClick={() => startRateEdit(s)}
                          className="text-xs font-semibold text-stone-600 hover:underline"
                        >
                          Edit rate
                        </button>
                      )}
                      <button
                        onClick={() => toggleStatus(s)}
                        disabled={rowBusyId === s.id}
                        className={`text-xs font-semibold hover:underline disabled:opacity-50 ${
                          s.status === "active"
                            ? "text-red-600"
                            : "text-green-700"
                        }`}
                      >
                        {s.status === "active" ? "Suspend" : "Activate"}
                      </button>
                      {rowErrors[s.id] && (
                        <p className="mt-1 text-right text-xs text-red-600">
                          {rowErrors[s.id]}
                        </p>
                      )}
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