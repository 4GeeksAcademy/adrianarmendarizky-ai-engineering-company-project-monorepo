"use client";

import { useState } from "react";
import Link from "next/link";

interface FormValues {
  full_name: string;
  email: string;
  phone: string;
  country: string;
  city: string;
  experience_years: string;
  location_type: string;
  investment_usd: string;
  referral_source: string;
  message: string;
}

type FormErrors = Partial<Record<keyof FormValues, string>>;

const EMPTY: FormValues = {
  full_name: "",
  email: "",
  phone: "",
  country: "",
  city: "",
  experience_years: "",
  location_type: "",
  investment_usd: "",
  referral_source: "",
  message: "",
};

function validate(values: FormValues): FormErrors {
  const errors: FormErrors = {};
  if (!values.full_name.trim()) errors.full_name = "Full name is required.";
  if (!values.email.trim()) {
    errors.email = "Email is required.";
  } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(values.email)) {
    errors.email = "Enter a valid email address.";
  }
  if (!values.phone.trim()) errors.phone = "Phone number is required.";
  if (!values.country) errors.country = "Select a country of interest.";
  if (!values.city.trim()) errors.city = "City is required.";
  if (!values.experience_years || Number(values.experience_years) < 0)
    errors.experience_years = "Enter years of business experience (0 or more).";
  if (!values.location_type) errors.location_type = "Select a preferred location type.";
  if (!values.investment_usd || Number(values.investment_usd) <= 0)
    errors.investment_usd = "Enter your available investment range in USD.";
  if (!values.referral_source) errors.referral_source = "Tell us how you heard about us.";
  return errors;
}

export default function ApplyPage() {
  const [values, setValues] = useState<FormValues>(EMPTY);
  const [errors, setErrors] = useState<FormErrors>({});
  const [submitted, setSubmitted] = useState(false);

  function handleChange(
    e: React.ChangeEvent<
      HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement
    >
  ) {
    setValues((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const errs = validate(values);
    setErrors(errs);
    if (Object.keys(errs).length === 0) {
      setSubmitted(true);
    }
  }

  function handleClear() {
    setValues(EMPTY);
    setErrors({});
    setSubmitted(false);
  }

  if (submitted) {
    return (
      <main className="min-h-screen bg-stone-50 flex items-center justify-center px-6">
        <div className="max-w-md text-center">
          <div className="mb-4 text-5xl">🔥</div>
          <h1 className="mb-3 text-2xl font-bold text-stone-900">
            Application received
          </h1>
          <p className="mb-6 text-stone-600">
            Thank you for your interest in Brasaland. Our team will review your
            enquiry and be in touch within 5 business days.
          </p>
          <Link
            href="/"
            className="rounded-md bg-red-600 px-6 py-2 text-white hover:bg-red-700 transition-colors"
          >
            Back to home
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-stone-50 py-16 px-6">
      <div className="mx-auto max-w-2xl">
        <Link
          href="/"
          className="mb-6 inline-block text-sm text-red-600 hover:underline"
        >
          ← Back to Brasaland
        </Link>

        <h1 className="mb-2 text-3xl font-bold text-stone-900">
          Partnership enquiry
        </h1>
        <p className="mb-8 text-stone-600">
          Interested in working with Brasaland? Fill in the form below and our
          team will be in touch.
        </p>

        <form onSubmit={handleSubmit} noValidate className="space-y-5">
          <fieldset className="space-y-5">
            <legend className="mb-4 text-sm font-semibold uppercase tracking-widest text-stone-500">
              Personal information
            </legend>

            <Field label="Full name" error={errors.full_name} required>
              <input
                type="text"
                name="full_name"
                value={values.full_name}
                onChange={handleChange}
                className="input"
                placeholder="María García"
              />
            </Field>

            <div className="grid gap-5 sm:grid-cols-2">
              <Field label="Email" error={errors.email} required>
                <input
                  type="email"
                  name="email"
                  value={values.email}
                  onChange={handleChange}
                  className="input"
                  placeholder="maria@example.com"
                />
              </Field>
              <Field label="Phone" error={errors.phone} required>
                <input
                  type="tel"
                  name="phone"
                  value={values.phone}
                  onChange={handleChange}
                  className="input"
                  placeholder="+57 300 000 0000"
                />
              </Field>
            </div>
          </fieldset>

          <fieldset className="space-y-5 border-t border-stone-200 pt-5">
            <legend className="mb-4 text-sm font-semibold uppercase tracking-widest text-stone-500">
              Business details
            </legend>

            <div className="grid gap-5 sm:grid-cols-2">
              <Field label="Country of interest" error={errors.country} required>
                <select
                  name="country"
                  value={values.country}
                  onChange={handleChange}
                  className="input"
                >
                  <option value="">Select country</option>
                  <option value="Colombia">Colombia</option>
                  <option value="United States">United States</option>
                </select>
              </Field>
              <Field label="City" error={errors.city} required>
                <input
                  type="text"
                  name="city"
                  value={values.city}
                  onChange={handleChange}
                  className="input"
                  placeholder="Medellín"
                />
              </Field>
            </div>

            <div className="grid gap-5 sm:grid-cols-2">
              <Field
                label="Years of business experience"
                error={errors.experience_years}
                required
              >
                <input
                  type="number"
                  name="experience_years"
                  value={values.experience_years}
                  onChange={handleChange}
                  min={0}
                  className="input"
                  placeholder="5"
                />
              </Field>
              <Field
                label="Preferred location type"
                error={errors.location_type}
                required
              >
                <select
                  name="location_type"
                  value={values.location_type}
                  onChange={handleChange}
                  className="input"
                >
                  <option value="">Select type</option>
                  <option value="Urban">Urban</option>
                  <option value="Suburban">Suburban</option>
                  <option value="Tourist area">Tourist area</option>
                </select>
              </Field>
            </div>

            <div className="grid gap-5 sm:grid-cols-2">
              <Field
                label="Available investment (USD)"
                error={errors.investment_usd}
                required
              >
                <input
                  type="number"
                  name="investment_usd"
                  value={values.investment_usd}
                  onChange={handleChange}
                  min={0}
                  className="input"
                  placeholder="150000"
                />
              </Field>
              <Field
                label="How did you hear about us?"
                error={errors.referral_source}
                required
              >
                <select
                  name="referral_source"
                  value={values.referral_source}
                  onChange={handleChange}
                  className="input"
                >
                  <option value="">Select source</option>
                  <option value="Social media">Social media</option>
                  <option value="Referral">Referral</option>
                  <option value="Event">Event</option>
                  <option value="Other">Other</option>
                </select>
              </Field>
            </div>

            <Field label="Message / motivation" error={errors.message}>
              <textarea
                name="message"
                value={values.message}
                onChange={handleChange}
                rows={4}
                className="input resize-none"
                placeholder="Tell us about your background and why Brasaland interests you."
              />
            </Field>
          </fieldset>

          <div className="flex gap-3 pt-2">
            <button
              type="submit"
              className="rounded-md bg-red-600 px-6 py-2 text-sm font-semibold text-white hover:bg-red-700 transition-colors"
            >
              Submit application
            </button>
            <button
              type="button"
              onClick={handleClear}
              className="rounded-md border border-stone-300 px-6 py-2 text-sm font-semibold text-stone-700 hover:bg-stone-100 transition-colors"
            >
              Clear form
            </button>
          </div>
        </form>
      </div>

      {/* Shared input style injected via globals — Tailwind utility class group */}
      <style jsx global>{`
        .input {
          width: 100%;
          border-radius: 0.375rem;
          border: 1px solid #d6d3d1;
          padding: 0.5rem 0.75rem;
          font-size: 0.875rem;
          background: white;
          outline: none;
        }
        .input:focus {
          border-color: #dc2626;
          box-shadow: 0 0 0 2px rgba(220, 38, 38, 0.15);
        }
      `}</style>
    </main>
  );
}

function Field({
  label,
  error,
  required,
  children,
}: {
  label: string;
  error?: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block font-medium text-stone-700">
        {label}{" "}
        {required && <span className="text-red-500" aria-hidden="true">*</span>}
      </span>
      {children}
      {error && (
        <span role="alert" className="mt-1 block text-xs text-red-600">
          {error}
        </span>
      )}
    </label>
  );
}
