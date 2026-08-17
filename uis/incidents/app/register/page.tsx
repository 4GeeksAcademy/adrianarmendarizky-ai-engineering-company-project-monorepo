"use client";

import { useState } from "react";
import { ApiError, FieldValidationError, createIncident } from "../../lib/api";
import { BRANCHES, CATEGORIES, ORIGINS } from "../../lib/incidentOptions";

type FormState = {
  title: string;
  description: string;
  category: string;
  origin: string;
  branch: string;
};

const EMPTY_FORM: FormState = {
  title: "",
  description: "",
  category: "",
  origin: "",
  branch: "",
};

function validate(form: FormState): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!form.title.trim()) errors.title = "Title is required.";
  if (!form.description.trim()) errors.description = "Description is required.";
  if (!form.category) errors.category = "Choose a category.";
  if (!form.origin) errors.origin = "Choose an origin.";
  if (!form.branch) errors.branch = "Choose a branch.";
  return errors;
}

export default function RegisterIncidentPage() {
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [confirmed, setConfirmed] = useState(false);

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
    setConfirmed(false);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    setConfirmed(false);

    const errors = validate(form);
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;

    setSubmitting(true);
    try {
      await createIncident(form);
      setForm(EMPTY_FORM);
      setFieldErrors({});
      setConfirmed(true);
    } catch (err) {
      if (err instanceof FieldValidationError) {
        setFieldErrors({ [err.field]: err.message });
      } else if (err instanceof ApiError) {
        setFormError("We couldn't register that incident. Please try again.");
      } else {
        setFormError("Something went wrong. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  const branchHighlighted = form.origin === "branch";
  const inputClass = (hasError: boolean) =>
    `w-full rounded-lg border px-3 py-2.5 text-base bg-white ${
      hasError ? "border-red-400" : "border-stone-300"
    }`;

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-stone-900">Register an Incident</h1>
        <p className="text-sm text-stone-500 mt-1">
          Log an operational, customer, or internal issue for the operations team to track.
        </p>
      </div>

      {confirmed && (
        <div className="rounded-xl border border-green-200 bg-green-50 p-4 text-sm text-green-800">
          Incident registered. The operations team will follow up from here.
        </div>
      )}

      {formError && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {formError}
        </div>
      )}

      <form
        onSubmit={handleSubmit}
        noValidate
        className="space-y-5 rounded-xl border border-stone-200 bg-white p-6 shadow-sm"
      >
        <div>
          <label className="block text-sm font-medium text-stone-700 mb-1">Title</label>
          <input
            type="text"
            value={form.title}
            onChange={(e) => update("title", e.target.value)}
            className={inputClass(!!fieldErrors.title)}
          />
          {fieldErrors.title && <p className="mt-1 text-xs text-red-600">{fieldErrors.title}</p>}
        </div>

        <div>
          <label className="block text-sm font-medium text-stone-700 mb-1">Description</label>
          <textarea
            rows={4}
            value={form.description}
            onChange={(e) => update("description", e.target.value)}
            className={inputClass(!!fieldErrors.description)}
          />
          {fieldErrors.description && (
            <p className="mt-1 text-xs text-red-600">{fieldErrors.description}</p>
          )}
        </div>

        <div className="grid gap-5 sm:grid-cols-2">
          <div>
            <label className="block text-sm font-medium text-stone-700 mb-1">Category</label>
            <select
              value={form.category}
              onChange={(e) => update("category", e.target.value)}
              className={inputClass(!!fieldErrors.category)}
            >
              <option value="">Select a category…</option>
              {CATEGORIES.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </select>
            {fieldErrors.category && (
              <p className="mt-1 text-xs text-red-600">{fieldErrors.category}</p>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-stone-700 mb-1">Origin</label>
            <select
              value={form.origin}
              onChange={(e) => update("origin", e.target.value)}
              className={inputClass(!!fieldErrors.origin)}
            >
              <option value="">Select an origin…</option>
              {ORIGINS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
            {fieldErrors.origin && <p className="mt-1 text-xs text-red-600">{fieldErrors.origin}</p>}
          </div>
        </div>

        <div
          className={`rounded-lg p-3 -mx-3 transition-colors ${
            branchHighlighted ? "bg-red-50 ring-2 ring-red-300" : ""
          }`}
        >
          <label className="block text-sm font-medium text-stone-700 mb-1">
            Branch
            {branchHighlighted && (
              <span className="ml-2 text-xs font-semibold text-red-600 uppercase tracking-wide">
                Reporting from this location
              </span>
            )}
          </label>
          <select
            value={form.branch}
            onChange={(e) => update("branch", e.target.value)}
            className={inputClass(!!fieldErrors.branch)}
          >
            <option value="">Select a branch…</option>
            {BRANCHES.map((b) => (
              <option key={b.value} value={b.value}>
                {b.label}
              </option>
            ))}
          </select>
          {fieldErrors.branch && <p className="mt-1 text-xs text-red-600">{fieldErrors.branch}</p>}
        </div>

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-lg bg-stone-900 text-white font-medium py-3 text-base hover:bg-stone-800 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {submitting ? "Submitting…" : "Register incident"}
        </button>
      </form>
    </div>
  );
}
